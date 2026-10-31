"""F2 (2026-10-31) — gate del legacy monoempresa para el segundo tenant.

Cubre:

1. Clasificador de rutas: legacy (`/api/v1/*`) vs núcleo (`/api/v1/nucleo/*`),
   auth (`/api/v1/auth/*`) y rutas fuera del prefijo (`/health`, `/`).
2. `GateLegacyMiddleware` aislado (ASGI puro, sin base): sin token, token
   inválido, token sin `sub`, membresía ausente (403 `LEGACY_SOLO_TEI`),
   membresía presente, y verbos secundarios.
3. `tiene_membresia_activa` fail-closed con identificadores mal formados (sin
   llegar a la base).
4. HTTP contra la app real: `admin2@tei.local` (tenant TES) recibe **403** en el
   prefijo legacy y **200** en `/nucleo/*` con `X-Empresa-ID`; `admin@tei.local`
   (tenant TEI) **no** recibe 403 del gate (tras la Ola C la ruta legacy ya no
   existe: 404) y `/auth/me` informa `es_legacy`.

Los flujos HTTP requieren la base de test (`NUCLEO_TEST_DATABASE_URL`) y el
segundo tenant sembrado. `make test-db` clona la base local (que ya tiene TES);
si el usuario de prueba no existe la prueba **falla con mensaje claro**: no se
omite en silencio.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import tiene_membresia_activa
from app.main import GateLegacyMiddleware, es_ruta_legacy

API = "/api/v1"
# Segundo tenant (TES) sembrado en la base local por scripts/seed_segundo_tenant.py
# y clonado a tei_test por `make test-db`.
TES_EMPRESA_ID = "22222222-2222-2222-2222-222222222222"
TEI_EMPRESA_ID = "11111111-1111-1111-1111-111111111111"


# ---------------------------------------------------------------------------
# Utilidades ASGI (se prueba el middleware aislado, sin TestClient)
# ---------------------------------------------------------------------------


def _scope(path: str = f"{API}/clientes", method: str = "GET", headers=None) -> dict:
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


def _ejecutar(app_asgi, scope: dict) -> list[dict]:
    enviado: list[dict] = []

    async def receive():  # pragma: no cover - el gate no lee el cuerpo
        return {"type": "http.request", "body": b"", "more_body": False}

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


class _AppInterior:
    """App ASGI que registra si la ruta se ejecutó."""

    def __init__(self, status: int = 200, cuerpo: dict | None = None) -> None:
        self.llamadas: list[str] = []
        self.status = status
        self.cuerpo = cuerpo or {"ok": True}

    async def __call__(self, scope, receive, send):
        self.llamadas.append(scope["path"])
        cuerpo = json.dumps(self.cuerpo).encode()
        await send(
            {
                "type": "http.response.start",
                "status": self.status,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": cuerpo})


# ---------------------------------------------------------------------------
# 1. Clasificador de rutas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path, legacy",
    [
        (f"{API}/clientes", True),
        (f"{API}/viajes", True),
        (f"{API}/viajes/123/estado", True),
        (f"{API}/nucleos", True),  # no es `/nucleo`: no se exenta por prefijo
        (API, True),
        (f"{API}/nucleo", False),
        (f"{API}/nucleo/clientes", False),
        (f"{API}/nucleo/expediente/viajes", False),
        (f"{API}/auth", False),
        (f"{API}/auth/me", False),
        ("/health", False),
        ("/", False),
        ("/docs", False),
        (f"{API}0/clientes", False),  # frontera: `/api/v10` no es `/api/v1`
    ],
)
def test_clasificador_de_rutas(path: str, legacy: bool):
    assert es_ruta_legacy(path) is legacy


# ---------------------------------------------------------------------------
# 2. Gate aislado
# ---------------------------------------------------------------------------


def _gate_con(monkeypatch, *, sub: str | None, membresia: bool) -> _AppInterior:
    interior = _AppInterior()

    def _decode(token: str) -> dict:
        assert token == "TOKEN-OK"
        return {"sub": sub} if sub is not None else {}

    def _membresia(auth_id, empresa_id) -> bool:
        assert auth_id == sub
        assert empresa_id == settings.LEGACY_EMPRESA_ID
        return membresia

    monkeypatch.setattr("app.main.decode_token", _decode)
    monkeypatch.setattr("app.main.tiene_membresia_activa", _membresia)
    return interior


def test_sin_token_deja_pasar_para_que_la_ruta_responda_401(monkeypatch):
    interior = _AppInterior(status=401, cuerpo={"detail": "Se requiere autenticación"})
    monkeypatch.setattr(
        "app.main.decode_token",
        lambda token: pytest.fail("sin token no se debe decodificar"),
    )
    monkeypatch.setattr(
        "app.main.tiene_membresia_activa",
        lambda auth_id, empresa_id: pytest.fail("sin token no se consulta membresía"),
    )

    enviado = _ejecutar(GateLegacyMiddleware(interior), _scope())

    assert interior.llamadas == [f"{API}/clientes"]
    assert enviado[0]["status"] == 401


def test_token_valido_sin_membresia_es_403_legacy_solo_tei(monkeypatch):
    interior = _gate_con(monkeypatch, sub=str(uuid.uuid4()), membresia=False)

    enviado = _ejecutar(
        GateLegacyMiddleware(interior),
        _scope(headers={"authorization": "Bearer TOKEN-OK"}),
    )

    status, cuerpo = _status_y_cuerpo(enviado)
    assert status == 403
    assert cuerpo["codigo"] == "LEGACY_SOLO_TEI"
    assert "detail" in cuerpo
    assert interior.llamadas == [], "no se debe tocar `public` sin membresía"
    headers = dict(enviado[0]["headers"])
    assert headers[b"connection"] == b"close"


def test_token_valido_con_membresia_pasa_al_router(monkeypatch):
    interior = _gate_con(monkeypatch, sub=str(uuid.uuid4()), membresia=True)

    enviado = _ejecutar(
        GateLegacyMiddleware(interior),
        _scope(headers={"authorization": "Bearer TOKEN-OK"}),
    )

    assert enviado[0]["status"] == 200
    assert interior.llamadas == [f"{API}/clientes"]


def test_token_invalido_deja_pasar_para_no_reescribir_el_401(monkeypatch):
    interior = _AppInterior(status=401, cuerpo={"detail": "Token inválido"})

    def _decode(token: str) -> dict:
        raise HTTPException(status_code=401, detail="Token inválido")

    monkeypatch.setattr("app.main.decode_token", _decode)
    monkeypatch.setattr(
        "app.main.tiene_membresia_activa",
        lambda auth_id, empresa_id: pytest.fail("token inválido no consulta membresía"),
    )

    enviado = _ejecutar(
        GateLegacyMiddleware(interior),
        _scope(headers={"authorization": "Bearer VENCIDO"}),
    )

    assert enviado[0]["status"] == 401
    assert interior.llamadas == [f"{API}/clientes"]


def test_token_sin_sub_deja_pasar(monkeypatch):
    interior = _gate_con(monkeypatch, sub=None, membresia=False)

    enviado = _ejecutar(
        GateLegacyMiddleware(interior),
        _scope(headers={"authorization": "Bearer TOKEN-OK"}),
    )

    assert enviado[0]["status"] == 200
    assert interior.llamadas == [f"{API}/clientes"]


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_el_gate_tambien_cubre_verbos_secundarios(monkeypatch, method: str):
    """El legacy se cierra para *todos* los verbos, no solo GET."""
    interior = _gate_con(monkeypatch, sub=str(uuid.uuid4()), membresia=False)

    enviado = _ejecutar(
        GateLegacyMiddleware(interior),
        _scope(method=method, headers={"authorization": "Bearer TOKEN-OK"}),
    )

    status, cuerpo = _status_y_cuerpo(enviado)
    assert status == 403
    assert cuerpo["codigo"] == "LEGACY_SOLO_TEI"
    assert interior.llamadas == []


@pytest.mark.parametrize("path", [f"{API}/nucleo/clientes", f"{API}/auth/me", "/health"])
def test_nucleo_auth_y_health_no_consultan_membresia(monkeypatch, path: str):
    interior = _AppInterior()

    monkeypatch.setattr(
        "app.main.decode_token",
        lambda token: pytest.fail("estas rutas no pasan por el gate legacy"),
    )
    monkeypatch.setattr(
        "app.main.tiene_membresia_activa",
        lambda auth_id, empresa_id: pytest.fail("estas rutas no pasan por el gate"),
    )

    enviado = _ejecutar(
        GateLegacyMiddleware(interior),
        _scope(path=path, headers={"authorization": "Bearer TOKEN-OK"}),
    )

    assert enviado[0]["status"] == 200
    assert interior.llamadas == [path]


def test_header_authorization_no_bearer_no_se_interpreta(monkeypatch):
    interior = _AppInterior(status=401, cuerpo={"detail": "Se requiere autenticación"})
    monkeypatch.setattr(
        "app.main.decode_token",
        lambda token: pytest.fail("un esquema distinto de Bearer no se decodifica"),
    )

    enviado = _ejecutar(
        GateLegacyMiddleware(interior),
        _scope(headers={"authorization": "Basic dXNlcjpwYXNz"}),
    )

    assert enviado[0]["status"] == 401
    assert interior.llamadas == [f"{API}/clientes"]


# ---------------------------------------------------------------------------
# 3. Membresía: fail-closed sin tocar la base
# ---------------------------------------------------------------------------


def test_membresia_con_empresa_mal_formada_deniega():
    assert tiene_membresia_activa(str(uuid.uuid4()), "no-es-uuid") is False


def test_membresia_con_auth_id_mal_formado_deniega():
    assert tiene_membresia_activa("no-es-uuid", TEI_EMPRESA_ID) is False


# ---------------------------------------------------------------------------
# 4. HTTP contra la app real (base de test + tenants sembrados)
# ---------------------------------------------------------------------------


def _login(email: str, password: str) -> str:
    import httpx

    r = httpx.post(
        f"{settings.SUPABASE_URL}/auth/v1/token?grant_type=password",
        json={"email": email, "password": password},
        headers={"apikey": settings.SUPABASE_ANON_KEY},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def headers_admin2(base_url_test) -> dict:
    """Token del admin del segundo tenant (TES) en la base de test.

    Si el usuario no existe, la prueba **falla** con la instrucción concreta:
    el segundo tenant se siembra con `scripts/seed_segundo_tenant.py` y llega a
    `tei_test` con `make test-db`. No se omite en silencio.
    """
    email = os.environ.get("TEST_ADMIN2_EMAIL", "admin2@tei.local")
    password = os.environ.get("TEST_ADMIN2_PASSWORD", "TEI2026!")
    try:
        token = _login(email, password)
    except Exception as exc:  # noqa: BLE001 - se convierte en fallo con contexto
        pytest.fail(
            f"No se pudo autenticar al usuario del segundo tenant ({email}): "
            f"{type(exc).__name__}. La base de test debe contener TES; "
            "ejecute `make test-db` (clona la base local con el segundo tenant) "
            "antes de la suite.",
            pytrace=False,
        )
    return {"Authorization": f"Bearer {token}"}


def test_http_tenant2_no_entra_al_legacy(client, headers_admin2):
    """Hueco original: el legacy respondía 200 a un usuario de otra empresa."""
    resp = client.get(f"{API}/clientes", headers=headers_admin2)
    assert resp.status_code == 403, resp.text
    assert resp.json()["codigo"] == "LEGACY_SOLO_TEI"


def test_http_tenant2_usa_el_nucleo_con_su_empresa(client, headers_admin2):
    resp = client.get(
        f"{API}/nucleo/clientes",
        headers={**headers_admin2, "X-Empresa-ID": TES_EMPRESA_ID},
    )
    assert resp.status_code == 200, resp.text
    filas = resp.json()
    assert filas, "el segundo tenant debe tener sus clientes sembrados"
    # Aislamiento: todos los clientes devueltos son del tenant TES.
    assert {fila["empresa_id"] for fila in filas} == {TES_EMPRESA_ID}


def test_http_tenant2_no_puede_leer_el_nucleo_de_TEI(client, headers_admin2):
    resp = client.get(
        f"{API}/nucleo/clientes",
        headers={**headers_admin2, "X-Empresa-ID": TEI_EMPRESA_ID},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["codigo"] == "ACCESO_DENEGADO"


def test_http_tenant1_no_es_bloqueado_por_el_gate(client, headers_admin):
    """El gate no bloquea a TEI; la ruta legacy retirada responde 404 (Ola C).

    Antes de la Ola C este contrato era 200 (el router legacy servía la
    respuesta). El gate sigue siendo la frontera para TES —ver
    `test_http_tenant2_no_entra_al_legacy`— y la desaparición de la ruta es
    parte del retiro, no del gate.
    """
    resp = client.get(f"{API}/clientes", headers=headers_admin)
    assert resp.status_code == 404, resp.text


def test_http_auth_me_expone_es_legacy_por_tenant(client, headers_admin, headers_admin2):
    me_tei = client.get(f"{API}/auth/me", headers=headers_admin)
    assert me_tei.status_code == 200, me_tei.text
    cuerpo_tei = me_tei.json()
    assert cuerpo_tei["es_legacy"] is True
    # Compatibilidad: el contrato previo sigue completo.
    assert {"id", "nombre", "email", "rol"} <= set(cuerpo_tei)

    me_tes = client.get(f"{API}/auth/me", headers=headers_admin2)
    assert me_tes.status_code == 200, me_tes.text
    assert me_tes.json()["es_legacy"] is False
    assert me_tes.json()["rol"] == "admin"


def test_http_sin_token_ruta_retirada_responde_404(client):
    """Sin token, el gate deja pasar; la ruta retirada responde 404 (Ola C).

    El contrato "sin token el gate no reescribe el 401" se prueba en el
    middleware aislado (`test_sin_token_deja_pasar_para_que_la_ruta_responda_401`):
    aquí ya no hay router legacy que devuelva 401.
    """
    resp = client.get(f"{API}/clientes")
    assert resp.status_code == 404, resp.text
