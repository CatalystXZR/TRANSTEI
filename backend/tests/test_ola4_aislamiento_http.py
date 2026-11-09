"""Aislamiento multiempresa en las rutas nuevas (Ola 4, HTTP real).

Ataca la frontera que declara `get_contexto_empresa`:

- un JWT válido de TEI con `X-Empresa-ID` de TES debe ser **403**, no 200 y no
  404 con datos: la membresía se resuelve en el servidor;
- `empresa_id` en el body no se acepta (`extra="forbid"`): 422, sin tocar la
  empresa del header ni la del body;
- sin `X-Empresa-ID` la petición es 422 (header obligatorio), no una empresa por
  defecto.

Se usan las rutas nuevas de la Ola 4: chat, configuracion (si estuviera
montada), transición, anulación y buzón. El JWT es el real del seed
(`headers_admin`); la empresa TES se busca por código en `tei_test`.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.config import settings

pytestmark = pytest.mark.integracion

API = settings.API_V1_PREFIX


def _empresa_por_codigo(db, codigo: str) -> str:
    fila = db.execute(
        "select id::text from nucleo.empresas where codigo = %s", (codigo,)
    ).fetchone()
    assert fila is not None, f"tei_test sin la empresa {codigo}; ejecute `make seed`"
    return fila[0]


def _headers(headers_admin: dict, empresa_id: str) -> dict:
    return {**headers_admin, "X-Empresa-ID": empresa_id}


# ---------------------------------------------------------------------------
# JWT de TEI + X-Empresa-ID de TES ⇒ 403
# ---------------------------------------------------------------------------
def test_chat_agentes_con_token_tei_y_empresa_tes_es_403(client, db, headers_admin):
    tes = _empresa_por_codigo(db, "TES")
    r = client.get(
        f"{API}/nucleo/agente/chat/agentes", headers=_headers(headers_admin, tes)
    )
    assert r.status_code == 403, r.text
    assert r.json()["codigo"] == "ACCESO_DENEGADO"


def test_chat_post_con_token_tei_y_empresa_tes_es_403_y_no_escribe(
    client, db, headers_admin
):
    tes = _empresa_por_codigo(db, "TES")
    clave = f"ola4-aislamiento-{uuid4()}"
    r = client.post(
        f"{API}/nucleo/agente/chat",
        headers=_headers(headers_admin, tes),
        json={
            "agente": "gerente",
            "mensaje": "Intento cross-tenant",
            "clave_idempotencia": clave,
        },
    )
    assert r.status_code == 403, r.text
    assert r.json()["codigo"] == "ACCESO_DENEGADO"

    mensajes = db.execute(
        "select count(*) from nucleo.agente_chat_mensajes "
        " where empresa_id::text = %s and clave_idempotencia = %s",
        (tes, clave),
    ).fetchone()[0]
    assert mensajes == 0, "un 403 no debe persistir el turno en la empresa ajena"


@pytest.mark.parametrize(
    "ruta_sufijo,body",
    [
        ("/nucleo/viajes/{viaje_id}/transicion", {"estado_destino": "asignado"}),
        ("/nucleo/viajes/{viaje_id}/anular", {"motivo": "Intento cross-tenant"}),
    ],
    ids=["transicion", "anular"],
)
def test_transiciones_con_token_tei_y_empresa_tes_es_403(
    client, db, headers_admin, ruta_sufijo, body
):
    tes = _empresa_por_codigo(db, "TES")
    ruta = f"{API}{ruta_sufijo.format(viaje_id=uuid4())}"
    r = client.post(ruta, headers=_headers(headers_admin, tes), json=body)
    assert r.status_code == 403, r.text
    assert r.json()["codigo"] == "ACCESO_DENEGADO"


def test_solicitudes_con_token_tei_y_empresa_tes_es_403(client, db, headers_admin):
    tes = _empresa_por_codigo(db, "TES")
    r = client.get(
        f"{API}/nucleo/agente/solicitudes",
        headers=_headers(headers_admin, tes),
    )
    assert r.status_code == 403, r.text
    assert r.json()["codigo"] == "ACCESO_DENEGADO"


# ---------------------------------------------------------------------------
# `empresa_id` en el body: rechazado, no una segunda fuente de verdad
# ---------------------------------------------------------------------------
def test_empresa_id_en_el_body_del_chat_es_422_y_no_llama_al_llm(
    client, db, headers_admin, monkeypatch
):
    from app.main import app
    from app.nucleo.agente.chat.llm import get_cliente_llm

    class Nunca:
        llamadas = 0

        def responder(self, *args, **kwargs):  # pragma: no cover
            self.llamadas += 1
            raise AssertionError("el LLM no debe llamarse")

    nunca = Nunca()
    monkeypatch.setattr(settings, "GERENTE_API_KEY", "sk-test-" + "A" * 60)
    app.dependency_overrides[get_cliente_llm] = lambda: nunca
    tei = _empresa_por_codigo(db, "TEI")
    tes = _empresa_por_codigo(db, "TES")
    try:
        r = client.post(
            f"{API}/nucleo/agente/chat",
            headers=_headers(headers_admin, tei),
            json={
                "agente": "gerente",
                "mensaje": "Intento de fijar empresa en el body",
                "clave_idempotencia": f"ola4-{uuid4()}",
                "empresa_id": tes,
            },
        )
    finally:
        app.dependency_overrides.pop(get_cliente_llm, None)

    assert r.status_code == 422, r.text
    campos = [e.get("loc", [])[-1:] for e in r.json().get("detail", [])]
    assert ["empresa_id"] in campos, campos
    assert nunca.llamadas == 0


def test_empresa_id_en_el_body_de_transicion_es_422(client, db, headers_admin):
    tei = _empresa_por_codigo(db, "TEI")
    r = client.post(
        f"{API}/nucleo/viajes/{uuid4()}/transicion",
        headers=_headers(headers_admin, tei),
        json={"estado_destino": "asignado", "empresa_id": str(uuid4())},
    )
    assert r.status_code == 422, r.text
    campos = [e.get("loc", [])[-1:] for e in r.json().get("detail", [])]
    assert ["empresa_id"] in campos, campos


# ---------------------------------------------------------------------------
# Sin header no hay empresa por defecto
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "metodo,ruta",
    [
        ("get", f"{API}/nucleo/agente/chat/agentes"),
        ("get", f"{API}/nucleo/agente/solicitudes"),
        ("post", f"{API}/nucleo/viajes/{{viaje_id}}/transicion"),
    ],
    ids=["chat-agentes", "solicitudes", "transicion"],
)
def test_sin_x_empresa_id_es_422(client, headers_admin, metodo, ruta):
    ruta = ruta.format(viaje_id=uuid4())
    if metodo == "post":
        r = client.post(
            ruta, headers=headers_admin, json={"estado_destino": "asignado"}
        )
    else:
        r = client.get(ruta, headers=headers_admin)
    assert r.status_code == 422, r.text
    assert any(
        e.get("loc", [])[-1:] == ["X-Empresa-ID"]
        for e in r.json().get("detail", [])
    ), r.json()
