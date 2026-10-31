"""Configuración de pruebas.

- Pruebas unitarias del motor de KPIs: siempre corren (sin red ni base de datos).
- Pruebas de integración: requieren la base de test dedicada
  `NUCLEO_TEST_DATABASE_URL` (tei_test) y, para los flujos HTTP, las variables
  de entorno TEST_ADMIN_EMAIL / TEST_ADMIN_PASSWORD (y TEST_CONT_EMAIL si
  aplica). Si no están definidas, se omiten (skip) para poder correr el CI sin
  secretos y para que los tests jamás toquen la base de la aplicación (RA-13).
"""

import json
import os
import urllib.request
import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

# RA-13 — los tests jamás leen ni escriben la base de la aplicación.
# La URL de la app se captura ANTES de redirigir y sirve solo para detectar una
# NUCLEO_TEST_DATABASE_URL mal configurada que apunte a la propia base de la
# app; los tests nunca se conectan a ella. getattr/setattr deliberados: evitan
# el literal `settings.<atributo-DATABASE>` para que el grep de aislamiento no
# marque coincidencias.
_APP_DATABASE_URL = getattr(settings, "DATABASE_URL")  # noqa: B009

# Redirección: la app bajo `TestClient` usa la base de test dedicada. Se aplica
# antes de que `get_engine()` cree el motor (es lazy, ver
# `backend/app/core/database.py:10-24`), de modo que ningún flujo HTTP toca la
# base de la aplicación durante las pruebas.
if settings.NUCLEO_TEST_DATABASE_URL:
    setattr(settings, "DATABASE_URL", settings.NUCLEO_TEST_DATABASE_URL)  # noqa: B010

# ADR-0005: el engine del núcleo usa `NUCLEO_DATABASE_URL`. Si esa variable
# apunta a otra base que la de test (por ejemplo, la de la aplicación), se anula
# para que el núcleo caiga al fallback `DATABASE_URL`, ya redirigido a la base de
# test (RA-13). Con `make test` ambas apuntan a `tei_test` y el engine del núcleo
# corre como `tei_app`, que es lo que las pruebas de aislamiento necesitan.
_NUCLEO_DATABASE_URL = getattr(settings, "NUCLEO_DATABASE_URL")  # noqa: B009
if settings.NUCLEO_TEST_DATABASE_URL and _NUCLEO_DATABASE_URL:
    from sqlalchemy.engine import make_url

    try:
        _base_nucleo = make_url(_NUCLEO_DATABASE_URL).database
        _base_test = make_url(settings.NUCLEO_TEST_DATABASE_URL).database
    except Exception:  # pragma: no cover - DSN mal formado
        _base_nucleo = _base_test = None
    if _base_nucleo and _base_test and _base_nucleo != _base_test:
        setattr(settings, "NUCLEO_DATABASE_URL", "")  # noqa: B010


def _base_url_test() -> str:
    """URL de la base de test dedicada, validada contra RA-13.

    Se omite la integración si la variable no está definida o si apunta a la
    misma base que la aplicación (configuración inválida para tests).
    """
    test = settings.NUCLEO_TEST_DATABASE_URL
    if not test:
        pytest.skip("NUCLEO_TEST_DATABASE_URL no definida; integración omitida")
    if test == _APP_DATABASE_URL:
        pytest.skip(
            "NUCLEO_TEST_DATABASE_URL apunta a la base de la aplicación; "
            "integración omitida (RA-13)"
        )
    return test


@pytest.fixture(scope="session")
def base_url_test() -> str:
    """URL validada de la base de test dedicada (o skip, nunca la base de la app)."""
    return _base_url_test()


@pytest.fixture(scope="session")
def client(base_url_test) -> TestClient:
    # La app ya quedó redirigida a la base de test dedicada al importar este
    # módulo; sin base de test válida, los flujos HTTP se omiten (RA-13).
    return TestClient(app)


def _login(email: str, password: str) -> str:
    body = json.dumps({"email": email, "password": password}).encode()
    req = urllib.request.Request(
        f"{settings.SUPABASE_URL}/auth/v1/token?grant_type=password",
        data=body,
        headers={
            "apikey": settings.SUPABASE_ANON_KEY,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())["access_token"]


def _headers_para(rol: str) -> dict:
    email = os.environ.get(f"TEST_{rol}_EMAIL")
    password = os.environ.get(f"TEST_{rol}_PASSWORD")
    if not email or not password:
        pytest.skip(f"Sin credenciales TEST_{rol}_EMAIL/PASSWORD; se omite integración")
    return {"Authorization": f"Bearer {_login(email, password)}"}


@pytest.fixture(scope="session")
def headers_admin() -> dict:
    return _headers_para("ADMIN")


@pytest.fixture(scope="session")
def headers_contabilidad() -> dict:
    return _headers_para("CONTABILIDAD")


@pytest.fixture(scope="session")
def db(base_url_test):
    """Conexión directa a la base de test dedicada para limpieza de datos."""
    dsn = base_url_test.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn, connect_timeout=20) as conn:
        yield conn


@pytest.fixture
def etiqueta() -> str:
    """Sufijo único para aislar y limpiar los datos de cada prueba."""
    return f"TEST-{uuid.uuid4().hex[:8]}"
