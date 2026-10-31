"""Ola C — routers legacy desmontados (ADR-0002 §6.5, 2026-10-31).

Guarda de regresión del retiro: las rutas de negocio de `public` ya no están
montadas. Si alguien vuelve a incluir un `include_router` legacy en
`backend/app/api/router.py`, estas pruebas fallan.

Qué **no** cambia en esta ola (y por eso se prueba explícitamente):
- `/api/v1/auth/me` sigue operativo: el shell lo consume y la identidad se
  retira en la Ola E (G0.1).
- El núcleo sigue montado bajo `/api/v1/nucleo`.
"""

from __future__ import annotations

import pytest

from app.main import app

API = "/api/v1"

# Inventario representativo: un endpoint por cada router retirado.
RUTAS_RETIRADAS = [
    ("GET", f"{API}/clientes"),  # catalogos
    ("GET", f"{API}/choferes"),  # catalogos
    ("GET", f"{API}/viajes"),  # viajes
    ("POST", f"{API}/viajes"),  # viajes
    ("PATCH", f"{API}/viajes/00000000-0000-0000-0000-000000000000/estado"),
    ("GET", f"{API}/viajes/00000000-0000-0000-0000-000000000000/gastos"),  # gastos
    ("GET", f"{API}/dashboard"),  # dashboard
    ("GET", f"{API}/facturas"),  # facturas
    ("PATCH", f"{API}/facturas/00000000-0000-0000-0000-000000000000/estado"),
    ("GET", f"{API}/cobranzas"),  # finanzas
    ("GET", f"{API}/iva/resumen"),  # finanzas
    ("GET", f"{API}/pautas"),  # mantenimiento
    ("GET", f"{API}/anticipos"),  # liquidaciones
    ("GET", f"{API}/configuracion"),  # configuracion
    ("GET", f"{API}/export/viajes"),  # export
    ("GET", f"{API}/kpis"),  # kpis
]


@pytest.mark.parametrize("metodo, ruta", RUTAS_RETIRADAS, ids=lambda v: v)
def test_ruta_retirada_no_esta_en_openapi(metodo: str, ruta: str):
    """El contrato publicado deja de ofrecer las rutas legacy."""
    esquema = app.openapi()
    operaciones = esquema["paths"].get(ruta, {})
    assert metodo.lower() not in operaciones, (
        f"{metodo} {ruta} sigue publicado en OpenAPI: el router legacy volvió a "
        "montarse (ADR-0002 §6.5)."
    )


def test_no_quedan_rutas_de_negocio_fuera_de_nucleo_y_auth():
    """Invariante del estado final de la Ola C (ADR-0002 §4.1.1)."""
    rutas = sorted(app.openapi()["paths"])
    fuera = [
        ruta
        for ruta in rutas
        if ruta.startswith(API)
        and not ruta.startswith(f"{API}/nucleo")
        and not ruta.startswith(f"{API}/auth")
    ]
    assert fuera == [], f"rutas no-núcleo/no-auth publicadas: {fuera}"


@pytest.mark.parametrize(
    "metodo, ruta",
    [par for par in RUTAS_RETIRADAS if par[0] == "GET"],
    ids=lambda v: v,
)
def test_ruta_retirada_responde_404_http(client, metodo: str, ruta: str):
    """HTTP real: una ruta retirada no responde 200/401/409, responde 404.

    Solo se ejercitan `GET` para no depender del flag de congelamiento; la
    ausencia de los verbos de escritura la cubre la prueba de OpenAPI.
    """
    resp = client.get(ruta)
    assert resp.status_code == 404, resp.text


def test_auth_me_sigue_existiendo_y_pide_token(client):
    """El retiro no toca la identidad (Ola E)."""
    sin_token = client.get(f"{API}/auth/me")
    assert sin_token.status_code == 401, sin_token.text
