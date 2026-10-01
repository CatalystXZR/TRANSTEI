"""Configuración de pruebas.

- Pruebas unitarias del motor de KPIs: siempre corren (sin red ni base de datos).
- Pruebas de integración: requieren las variables de entorno
  TEST_ADMIN_EMAIL / TEST_ADMIN_PASSWORD (y TEST_CONT_EMAIL si aplica).
  Si no están definidas, se omiten (skip) para poder correr el CI sin secretos.
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


@pytest.fixture(scope="session")
def client() -> TestClient:
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
def db():
    """Conexión directa para limpieza de datos de prueba."""
    if not settings.DATABASE_URL:
        pytest.skip("Sin DATABASE_URL")
    dsn = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn, connect_timeout=20) as conn:
        yield conn


@pytest.fixture
def etiqueta() -> str:
    """Sufijo único para aislar y limpiar los datos de cada prueba."""
    return f"TEST-{uuid.uuid4().hex[:8]}"
