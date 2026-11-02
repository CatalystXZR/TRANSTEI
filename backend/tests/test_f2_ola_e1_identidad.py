"""F2 · Ola E1 (2026-11-01) — identidad sin `public.usuarios`.

Qué prueba
----------
1. Mapeo rol del núcleo → rol de menú (`admin|operacion|contabilidad`) y
   desempate determinista cuando hay varias membresías.
2. `GET /api/v1/auth/me` con JWT real de TEI y de TES: responde 200 con
   `{id, nombre, email, rol}`, `id` = `sub` del JWT y **sin** `es_legacy`.
3. Sin token → 401. Token válido sin membresía utilizable → 403.
4. El RLS de `nucleo.usuarios_empresa` (política `usuarios_empresa_lectura` por
   `nucleo.auth_id`) devuelve 0 filas para un `auth_id` sin membresía.
5. Guarda estática: `backend/app` no referencia `public.usuarios` y los módulos
   legacy (`app.models`, `app.core.settings_db`) fueron retirados.
6. Regresión de aislamiento del segundo tenant en el núcleo (la puerta legacy
   se retiró con las rutas legacy; `/api/v1/*` fuera de núcleo/auth es 404).

Requiere la base de test (`NUCLEO_TEST_DATABASE_URL`) y los tenants sembrados;
`make test` los aporta. Los flujos HTTP sin credenciales se omiten según
`conftest.py` (nunca se aprueban en silencio: `skip` ≠ pasado).
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from fastapi import HTTPException

from app.api.deps import (
    ROL_MENU_POR_ROL_EMPRESA,
    _membresias_utilizables,
    get_current_user,
    rol_menu_efectivo,
)
from app.core.config import settings
from app.core.database import get_session_nucleo
from app.nucleo.models import RolEmpresa

API = "/api/v1"
TEI_EMPRESA_ID = "11111111-1111-1111-1111-111111111111"
TES_EMPRESA_ID = "22222222-2222-2222-2222-222222222222"

RAIZ = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 1. Mapeo de roles
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rol, menu",
    [
        (RolEmpresa.admin, "admin"),
        (RolEmpresa.gerente, "admin"),
        (RolEmpresa.despacho, "operacion"),
        (RolEmpresa.taller, "operacion"),
        (RolEmpresa.conductor, "operacion"),
        (RolEmpresa.contador, "contabilidad"),
        (RolEmpresa.tesoreria, "contabilidad"),
        (RolEmpresa.auditor, "contabilidad"),
    ],
)
def test_mapeo_rol_empresa_a_rol_de_menu(rol: RolEmpresa, menu: str):
    assert ROL_MENU_POR_ROL_EMPRESA[rol].value == menu
    assert rol_menu_efectivo([rol]) is ROL_MENU_POR_ROL_EMPRESA[rol]


def test_todos_los_roles_del_nucleo_tienen_menu():
    """Un rol nuevo sin mapeo dejaría al usuario sin navegación en silencio."""
    assert set(ROL_MENU_POR_ROL_EMPRESA) == set(RolEmpresa)


def test_desempate_entre_varias_membresias_es_determinista():
    assert rol_menu_efectivo([]) is None
    assert rol_menu_efectivo([RolEmpresa.contador]).value == "contabilidad"
    assert (
        rol_menu_efectivo([RolEmpresa.contador, RolEmpresa.despacho]).value
        == "operacion"
    )
    assert (
        rol_menu_efectivo([RolEmpresa.despacho, RolEmpresa.gerente]).value == "admin"
    )
    # El orden de entrada no cambia el resultado.
    assert rol_menu_efectivo(
        [RolEmpresa.auditor, RolEmpresa.conductor, RolEmpresa.admin]
    ).value == "admin"


class _MembresiaFalsa:
    def __init__(self, rol: RolEmpresa) -> None:
        self.rol = rol


def _identidad_con(monkeypatch, payload: dict):
    monkeypatch.setattr(
        "app.api.deps.payload_from_credentials", lambda credentials: payload
    )
    monkeypatch.setattr(
        "app.api.deps._membresias_utilizables",
        lambda session, auth_id: [_MembresiaFalsa(RolEmpresa.gerente)],
    )
    return get_current_user(credentials=object(), session=object())


def test_get_current_user_nombre_desde_user_metadata(monkeypatch):
    identidad = _identidad_con(
        monkeypatch,
        {
            "sub": str(uuid4()),
            "email": "persona@tei.local",
            "user_metadata": {"nombre": "Persona TEI"},
        },
    )
    assert identidad.nombre == "Persona TEI"
    assert identidad.email == "persona@tei.local"
    assert identidad.rol.value == "admin"  # gerente → admin


def test_get_current_user_nombre_cae_al_email(monkeypatch):
    identidad = _identidad_con(
        monkeypatch,
        {"sub": str(uuid4()), "email": "sin.nombre@tei.local"},
    )
    assert identidad.nombre == "sin.nombre@tei.local"


def test_get_current_user_sub_no_uuid_responde_401(monkeypatch):
    monkeypatch.setattr(
        "app.api.deps.payload_from_credentials",
        lambda credentials: {"sub": "no-es-uuid", "email": "x@tei.local"},
    )
    with pytest.raises(HTTPException) as excinfo:
        get_current_user(credentials=object(), session=object())
    assert excinfo.value.status_code == 401


# ---------------------------------------------------------------------------
# 2/3. Contrato HTTP de /auth/me
# ---------------------------------------------------------------------------


def _claims(headers: dict) -> dict:
    """Payload del token **sin** verificar firma: solo para comparar identidad."""
    token = headers["Authorization"].split(" ", 1)[1]
    return jwt.decode(token, options={"verify_signature": False, "verify_aud": False})


def test_auth_me_sin_token_responde_401(client):
    resp = client.get(f"{API}/auth/me")
    assert resp.status_code == 401, resp.text
    assert "autenticación" in resp.json()["detail"]


def test_auth_me_tei_sin_es_legacy(client, headers_admin):
    claims = _claims(headers_admin)
    resp = client.get(f"{API}/auth/me", headers=headers_admin)
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()

    assert set(cuerpo) == {"id", "nombre", "email", "rol"}, cuerpo
    assert "es_legacy" not in cuerpo
    # Identidad tomada del JWT, no de `public.usuarios`.
    assert cuerpo["id"] == claims["sub"]
    assert UUID(cuerpo["id"])
    assert cuerpo["email"] == claims["email"]
    assert cuerpo["nombre"] == (
        claims.get("user_metadata", {}).get("nombre") or claims["email"]
    )
    assert cuerpo["rol"] == "admin"


def test_auth_me_tes_sin_es_legacy(client, headers_admin2):
    """El tenant 2 ya no necesita espejo en `public.usuarios`."""
    claims = _claims(headers_admin2)
    resp = client.get(f"{API}/auth/me", headers=headers_admin2)
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()

    assert set(cuerpo) == {"id", "nombre", "email", "rol"}, cuerpo
    assert "es_legacy" not in cuerpo
    assert cuerpo["id"] == claims["sub"]
    assert cuerpo["rol"] == "admin"


def test_auth_me_contabilidad_mapea_el_rol_del_nucleo(client, headers_contabilidad):
    resp = client.get(f"{API}/auth/me", headers=headers_contabilidad)
    assert resp.status_code == 200, resp.text
    assert resp.json()["rol"] == "contabilidad"


def test_auth_me_sin_membresia_utilizable_responde_403(
    client, headers_admin, monkeypatch
):
    """Mismo JWT válido, sin membresías: la autorización es del servidor."""
    monkeypatch.setattr(
        "app.api.deps._membresias_utilizables",
        lambda session, auth_id: [],
    )
    resp = client.get(f"{API}/auth/me", headers=headers_admin)
    assert resp.status_code == 403, resp.text
    assert "membresía" in resp.json()["detail"]


def test_membresias_por_auth_id_sin_membresia_devuelve_vacio(base_url_test):
    """RLS: un `auth_id` ajeno no ve membresías (fail-closed)."""
    generador = get_session_nucleo()
    session = next(generador)
    try:
        assert _membresias_utilizables(session, str(uuid4())) == []
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 5. Guardas estáticas de la Ola E1
# ---------------------------------------------------------------------------


def test_backend_no_usa_public_usuarios():
    """Ninguna consulta del backend lee/escribe `public.usuarios`."""
    import re

    patron = re.compile(
        r"\b(?:from|into|update|join|table)\s+public\.usuarios\b", re.IGNORECASE
    )
    infracciones = [
        str(archivo.relative_to(RAIZ))
        for archivo in sorted((RAIZ / "backend" / "app").rglob("*.py"))
        if patron.search(archivo.read_text(encoding="utf-8"))
    ]
    assert infracciones == [], infracciones


def test_modulos_legacy_retirados():
    assert not (RAIZ / "backend" / "app" / "models" / "__init__.py").exists()
    assert not (RAIZ / "backend" / "app" / "core" / "settings_db.py").exists()


def test_gate_legacy_retirado():
    from app import main

    assert not hasattr(main, "GateLegacyMiddleware")
    assert not hasattr(main, "tiene_membresia_activa")
    assert not hasattr(settings, "LEGACY_EMPRESA_ID")


# ---------------------------------------------------------------------------
# 6. Regresión de aislamiento del segundo tenant
# ---------------------------------------------------------------------------


def _login(email: str, password: str) -> str:
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


def test_http_tenant2_usa_el_nucleo_con_su_empresa(client, headers_admin2):
    resp = client.get(
        f"{API}/nucleo/clientes",
        headers={**headers_admin2, "X-Empresa-ID": TES_EMPRESA_ID},
    )
    assert resp.status_code == 200, resp.text
    filas = resp.json()
    assert filas, "el segundo tenant debe tener sus clientes sembrados"
    assert {fila["empresa_id"] for fila in filas} == {TES_EMPRESA_ID}


def test_http_tenant2_no_puede_leer_el_nucleo_de_TEI(client, headers_admin2):
    resp = client.get(
        f"{API}/nucleo/clientes",
        headers={**headers_admin2, "X-Empresa-ID": TEI_EMPRESA_ID},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["codigo"] == "ACCESO_DENEGADO"


def test_http_ruta_legacy_retirada_responde_404(client, headers_admin2):
    """La puerta legacy se retiró junto con las rutas; ya no hay 403 de gate."""
    resp = client.get(f"{API}/clientes", headers=headers_admin2)
    assert resp.status_code == 404, resp.text
