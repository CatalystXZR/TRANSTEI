"""F1 Ola 4 (2026-10-30) — infra de request: SEC-021 + contexto de transacción.

Cubre:
- SEC-021: middleware ASGI de tope de cuerpo (413 `CUERPO_EXCESO`) por
  `Content-Length` declarado y por conteo real de bytes (chunked), antes de que
  FastAPI parsee formularios y resuelva auth.
- Contexto de empresa/auditoría: `app.empresa_id`, `nucleo.auth_id` y
  `nucleo.request_id` sobreviven a los `commit()` intermedios de un request
  (listener `begin` del engine) y quedan vacíos fuera de un request
  (fail-closed).

Sin base de datos: las pruebas del middleware y del `ContextVar` (corren en
cualquier entorno). Con base: las de GUC y la integración con
`get_contexto_empresa` (se omiten si no hay `NUCLEO_TEST_DATABASE_URL`).
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings
from app.core.contexto import (
    contexto_actual,
    contexto_de_request,
    fijar_auth_id,
    fijar_empresa,
    fijar_request_id,
    limpiar_request_id,
)
from app.core.database import get_engine
from app.main import (
    LIMITE_CUERPO_BYTES,
    LIMITE_CUERPO_POD_BYTES,
    LimiteCuerpoMiddleware,
    limite_para_cuerpo,
)
from app.nucleo import deps
from app.nucleo.deps import get_contexto_empresa
from app.nucleo.errores import AccesoDenegado
from app.nucleo.models import Empresa, RolEmpresa, UsuarioEmpresa

API = "/api/v1"

PNG_OK = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ---------------------------------------------------------------------------
# Utilidades ASGI (sin TestClient: se prueba el middleware aislado)
# ---------------------------------------------------------------------------


def _scope(path: str = "/api/v1/x", method: str = "POST", headers=None) -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (nombre.lower().encode(), str(valor).encode())
            for nombre, valor in (headers or {}).items()
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }


def _ejecutar(app_asgi, scope: dict, mensajes: list[dict]) -> list[dict]:
    enviado: list[dict] = []

    async def receive():
        return mensajes.pop(0)

    async def send(mensaje):
        enviado.append(mensaje)

    asyncio.run(app_asgi(scope, receive, send))
    return enviado


def _status_y_cuerpo(enviado: list[dict]) -> tuple[int, dict]:
    inicio = next(m for m in enviado if m["type"] == "http.response.start")
    cuerpo = b"".join(
        m.get("body", b"") for m in enviado if m["type"] == "http.response.body"
    )
    return inicio["status"], json.loads(cuerpo)


# ---------------------------------------------------------------------------
# SEC-021 — cotas y comportamiento del middleware
# ---------------------------------------------------------------------------


def test_cota_global_documentada():
    """32 MB: documento de 10 MB + margen multipart/JSON (no es regla de negocio)."""
    assert LIMITE_CUERPO_BYTES == 32 * 1024 * 1024


def test_cota_pod_derivada_de_las_constantes_del_dominio():
    """El POD admite 10 fotos de 10 MB + firma de 5 MB + 1 MB de holgura."""
    assert LIMITE_CUERPO_POD_BYTES == 10 * 10 * 1024 * 1024 + 5 * 1024 * 1024 + 1024 * 1024
    assert limite_para_cuerpo(f"{API}/nucleo/expediente/viajes/{uuid.uuid4()}/pod") == (
        LIMITE_CUERPO_POD_BYTES
    )
    assert limite_para_cuerpo(f"{API}/nucleo/maestros/documentos") == LIMITE_CUERPO_BYTES
    assert limite_para_cuerpo("/api/v1/nucleo/viajes") == LIMITE_CUERPO_BYTES


def test_content_length_excesivo_responde_413_sin_leer_el_cuerpo():
    recibidos: list[int] = []

    async def app_que_no_debe_correr(scope, receive, send):
        raise AssertionError("el middleware debe cortar antes de la app")

    async def receive():  # pragma: no cover - no debe invocarse
        recibidos.append(1)
        return {"type": "http.request", "body": b"x", "more_body": False}

    enviado: list[dict] = []

    async def send(mensaje):
        enviado.append(mensaje)

    scope = _scope(headers={"content-length": LIMITE_CUERPO_BYTES + 1})
    asyncio.run(LimiteCuerpoMiddleware(app_que_no_debe_correr)(scope, receive, send))

    status, cuerpo = _status_y_cuerpo(enviado)
    assert status == 413
    assert cuerpo["codigo"] == "CUERPO_EXCESO"
    assert recibidos == [], "no se debe leer el cuerpo si Content-Length ya delata el exceso"
    headers = dict(enviado[0]["headers"])
    assert headers[b"connection"] == b"close"


def test_content_length_en_el_limite_exacto_pasa():
    llamado: list[bool] = []

    async def app_ok(scope, receive, send):
        llamado.append(True)
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    scope = _scope(headers={"content-length": LIMITE_CUERPO_BYTES})
    enviado = _ejecutar(LimiteCuerpoMiddleware(app_ok), scope, [])
    assert enviado[0]["status"] == 204
    assert llamado == [True]


def test_chunked_sin_content_length_bajo_la_cota_pasa():
    """Sin Content-Length, el conteo real deja pasar un cuerpo bajo la cota."""
    leidos: list[int] = []

    async def app_que_consume(scope, receive, send):
        while True:
            mensaje = await receive()
            leidos.append(len(mensaje.get("body", b"")))
            if not mensaje.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mensajes = [
        {"type": "http.request", "body": b"12345", "more_body": True},
        {"type": "http.request", "body": b"67890", "more_body": False},
    ]
    enviado = _ejecutar(LimiteCuerpoMiddleware(app_que_consume), _scope(), mensajes)

    assert enviado[0]["status"] == 200
    assert leidos == [5, 5]


def test_chunked_corta_cuando_supera_la_cota(monkeypatch):
    """Cota chica inyectada: 6 + 6 > 10 ⇒ 413 antes de terminar de leer."""
    leidos: list[int] = []

    async def app_que_consume(scope, receive, send):
        while True:
            mensaje = await receive()
            leidos.append(len(mensaje.get("body", b"")))
            if not mensaje.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    monkeypatch.setattr("app.main.limite_para_cuerpo", lambda path: 10)
    mensajes = [
        {"type": "http.request", "body": b"123456", "more_body": True},
        {"type": "http.request", "body": b"123456", "more_body": False},
    ]
    enviado = _ejecutar(LimiteCuerpoMiddleware(app_que_consume), _scope(), mensajes)

    status, cuerpo = _status_y_cuerpo(enviado)
    assert status == 413
    assert cuerpo["codigo"] == "CUERPO_EXCESO"
    # Solo se consumió el primer chunk; el segundo ya no se leyó.
    assert leidos == [6]


# ---------------------------------------------------------------------------
# Contexto de request (ContextVar) — sin base
# ---------------------------------------------------------------------------


def test_contexto_de_request_se_limpia_al_salir():
    with contexto_de_request(request_id="RID-UNIT"):
        fijar_auth_id("auth-x")
        fijar_empresa(uuid.uuid4())
        actual = contexto_actual()
        assert actual is not None
        assert actual.auth_id == "auth-x"
        assert actual.request_id == "RID-UNIT"
    assert contexto_actual() is None, "un request no debe heredar el contexto anterior"


def test_request_id_se_acota_a_un_charset_inocuo():
    assert limpiar_request_id("abc-123_X.Y:z") == "abc-123_X.Y:z"
    assert limpiar_request_id("x" * 200) is None
    assert limpiar_request_id("con espacios") is None
    assert limpiar_request_id("") is None
    assert limpiar_request_id(None) is None
    with contexto_de_request(request_id="mal id"):
        fijar_request_id("otro mal id")
        assert contexto_actual().request_id is None


# ---------------------------------------------------------------------------
# Contexto por transacción — requiere PostgreSQL de test
# ---------------------------------------------------------------------------


def _url_test() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite integración de contexto")
    return url


def _gucs(session: Session) -> tuple[str, str, str]:
    fila = session.execute(
        text(
            "select current_setting('app.empresa_id', true),"
            " current_setting('nucleo.auth_id', true),"
            " current_setting('nucleo.request_id', true)"
        )
    ).one()
    return tuple(fila)  # type: ignore[return-value]


def test_gucs_sobreviven_a_commits_intermedios():
    _url_test()
    engine = get_engine()
    empresa_id = uuid.uuid4()
    auth_id = str(uuid.uuid4())

    with contexto_de_request(request_id="RID-COMMIT"):
        fijar_empresa(empresa_id)
        fijar_auth_id(auth_id)
        with Session(engine) as session:
            esperado = (str(empresa_id), auth_id, "RID-COMMIT")
            assert _gucs(session) == esperado
            session.commit()
            assert _gucs(session) == esperado, "el commit pierde set_config(is_local=true)"
            session.commit()
            assert _gucs(session) == esperado


def test_sin_contexto_los_gucs_quedan_vacios_y_la_politica_filtra():
    """Fail-closed: sin empresa, `nucleo.ctx_empresa()` es NULL (0 filas)."""
    _url_test()
    engine = get_engine()

    with Session(engine) as session:
        assert _gucs(session) == ("", "", "")
        assert session.execute(text("select nucleo.ctx_empresa()")).scalar_one() is None


def test_listener_neutraliza_un_guc_de_sesion_previo():
    """Un valor `is_local=false` heredado de la conexión no debe filtrar datos."""
    _url_test()
    engine = get_engine()
    ajeno = uuid.uuid4()

    with engine.connect() as conn:
        try:
            conn.execute(
                text("select set_config('app.empresa_id', :v, false)"), {"v": str(ajeno)}
            )
            conn.commit()
            # Nueva transacción sobre la MISMA conexión: el listener debe vaciarlo.
            assert (
                conn.execute(
                    text("select current_setting('app.empresa_id', true)")
                ).scalar_one()
                == ""
            )
        finally:
            # Higiene: no dejar el GUC de sesión pegado en una conexión del pool.
            conn.execute(text("select set_config('app.empresa_id', '', false)"))
            conn.commit()


def _empresa_con_membresia(auth_id: str) -> UUID:
    engine = get_engine()
    token = uuid.uuid4().hex[:8]
    with Session(engine) as session:
        empresa = Empresa(
            codigo=f"OLA4-{token}",
            razon_social=f"Empresa Ola4 {token}",
            # RUT solo dígitos: `uq_empresas_rut_norm` normaliza y un RUT
            # alfanumérico colisiona entre corridas.
            rut=str(uuid.uuid4().int)[:12],
        )
        session.add(empresa)
        session.commit()
        session.refresh(empresa)
        empresa_id = empresa.id
        session.add(
            UsuarioEmpresa(
                empresa_id=empresa_id,
                auth_id=UUID(auth_id),
                rol=RolEmpresa.admin,
            )
        )
        session.commit()
    return empresa_id


def test_get_contexto_empresa_fija_la_transaccion_verificada(monkeypatch):
    """Integración: el GUC de empresa sale de la membresía del servidor."""
    _url_test()
    engine = get_engine()
    auth_id = str(uuid.uuid4())
    empresa_id = _empresa_con_membresia(auth_id)
    monkeypatch.setattr(deps, "auth_id_from_credentials", lambda credentials: auth_id)

    with contexto_de_request(request_id="RID-DEP"), Session(engine) as session:
        contexto = get_contexto_empresa(
            x_empresa_id=empresa_id,
            x_request_id="RID-DEP",
            credentials=object(),
            session=session,
        )
        assert contexto.empresa_id == empresa_id
        esperado = (str(empresa_id), auth_id, "RID-DEP")
        assert _gucs(session) == esperado
        session.commit()
        assert _gucs(session) == esperado


def test_get_contexto_empresa_sin_membresia_no_fija_empresa(monkeypatch):
    """Sin membresía no hay `app.empresa_id`: las políticas no verían filas."""
    _url_test()
    engine = get_engine()
    auth_id = str(uuid.uuid4())
    empresa_id = _empresa_con_membresia(auth_id)
    monkeypatch.setattr(
        deps, "auth_id_from_credentials", lambda credentials: str(uuid.uuid4())
    )

    with contexto_de_request(request_id="RID-DENEG"), Session(engine) as session:
        with pytest.raises(AccesoDenegado):
            get_contexto_empresa(
                x_empresa_id=empresa_id,
                x_request_id="RID-DENEG",
                credentials=object(),
                session=session,
            )
        assert _gucs(session)[0] == ""


# ---------------------------------------------------------------------------
# SEC-021 — HTTP contra la app real
# ---------------------------------------------------------------------------


def test_http_413_antes_de_autenticar(client):
    """El 413 llega por Content-Length sin token: antes del parseo y de la auth."""
    resp = client.post(
        f"{API}/nucleo/viajes",
        content=b"x",
        headers={
            "Content-Length": str(LIMITE_CUERPO_BYTES + 1),
            "X-Empresa-ID": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 413, resp.text
    assert resp.json()["codigo"] == "CUERPO_EXCESO"


def test_http_pod_usa_su_cota_propia_mayor_que_la_global(client):
    """La cota del POD (10 fotos) es mayor que la global y se respeta por ruta."""
    resp = client.post(
        f"{API}/nucleo/expediente/viajes/{uuid.uuid4()}/pod",
        content=b"x",
        headers={
            "Content-Length": str(LIMITE_CUERPO_BYTES + 1),
            "X-Empresa-ID": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 401, resp.text  # pasa el tope; lo rechaza la auth


def test_http_multipart_pequeno_sigue_su_curso_normal(client):
    """Un cuerpo pequeño no se bloquea: el rechazo lo hace la auth (401)."""
    resp = client.post(
        f"{API}/nucleo/expediente/viajes/{uuid.uuid4()}/pod",
        data={"receptor_nombre": "Receptora Ola4"},
        files=[("firma", ("firma.png", PNG_OK, "image/png"))],
        headers={"X-Empresa-ID": str(uuid.uuid4())},
    )
    assert resp.status_code == 401, resp.text
