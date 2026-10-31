"""F1 · Ola 5 — dos engines (ADR-0005) y aislamiento multiempresa real.

Qué prueba
----------
1. El engine del núcleo conecta como `tei_app` (`rolbypassrls=false`) y el
   engine legacy conserva el rol del DSN `DATABASE_URL`. Evidencia:
   `select current_user` por engine (no se infiere del código).
2. Con `tei_app`: dos empresas del fixture no se ven entre sí y **sin contexto
   la tabla devuelve 0 filas** (fail-closed). Incluye que el GUC sobrevive a un
   `commit()` intermedio (los servicios commitean a mitad de request).
3. HTTP real (`TestClient`): el usuario de A solo ve datos de A; pedir la
   empresa B devuelve 403 sin fuga; sin `X-Empresa-ID` y con UUID inválido, 4xx.
4. `GET /nucleo/mis-empresas` (sin `X-Empresa-ID`) resuelve por `nucleo.auth_id`.
5. Fallback sin `NUCLEO_DATABASE_URL`: se usa `DATABASE_URL`, se registra
   `RLS inerte: configure NUCLEO_DATABASE_URL` y la sesión sigue funcionando.
6. Guarda de rol: un DSN explícito que conecta con `BYPASSRLS` ⇒ 503.
7. Prueba estática: solo `servicio_cutover.py` referencia `public.` o importa el
   engine legacy (excepción declarada del ADR-0005 §3.2 regla 4).

Autorización de las pruebas HTTP
--------------------------------
El token real de Supabase (JWKS) se reserva para las pruebas de auth. Aquí se
sustituye **solo** la extracción del `sub` (`auth_id_from_credentials`) por un
`auth_id` de fixture; la autorización que se prueba (membresía en
`nucleo.usuarios_empresa` + estado de empresa + RLS) sigue siendo la real.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from rut_helpers import rut_empresa
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlmodel import Session

from app.core import database as db_nucleo
from app.core.config import settings
from app.core.contexto import contexto_de_request, fijar_empresa
from app.core.database import get_engine, get_engine_nucleo
from app.nucleo import api as api_nucleo
from app.nucleo import deps
from app.nucleo.models import Cliente, Empresa, RolEmpresa, UsuarioEmpresa

API = "/api/v1"


# ---------------------------------------------------------------------------
# Helpers (devuelven UUIDs: las instancias ORM quedan fuera de sesión)
# ---------------------------------------------------------------------------
def _url_test() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite integración")
    return url


def _url_nucleo() -> str:
    url = (settings.NUCLEO_DATABASE_URL or "").strip()
    if not url:
        pytest.skip(
            "Sin NUCLEO_DATABASE_URL; el núcleo corre en modo fallback y RLS es "
            "inerte. Ejecute `make test` para probar el rol tei_app."
        )
    return url


def _crear_empresa(session: Session, prefijo: str) -> UUID:
    token = uuid4().hex[:8]
    empresa = Empresa(
        codigo=f"{prefijo}-{token}",
        razon_social=f"Empresa {prefijo} {token}",
        rut=rut_empresa(),
    )
    session.add(empresa)
    session.commit()
    return empresa.id


def _crear_cliente(session: Session, empresa_id: UUID, prefijo: str) -> UUID:
    token = uuid4().hex[:8]
    cliente = Cliente(
        empresa_id=empresa_id,
        razon_social=f"Cliente {prefijo} {token}",
        rut=str(uuid4().int)[:9],
    )
    session.add(cliente)
    session.commit()
    return cliente.id


def _membresia(session: Session, empresa_id: UUID, auth_id: str) -> None:
    session.add(
        UsuarioEmpresa(
            empresa_id=empresa_id,
            auth_id=UUID(auth_id),
            rol=RolEmpresa.admin,
        )
    )
    session.commit()


def _limpiar(empresas: list[UUID]) -> None:
    """Borra el fixture con el rol de plataforma (postgres)."""
    if not empresas:
        return
    with Session(get_engine()) as session:
        session.execute(
            text("delete from nucleo.clientes where empresa_id = any(:ids)"),
            {"ids": empresas},
        )
        session.execute(
            text("delete from nucleo.usuarios_empresa where empresa_id = any(:ids)"),
            {"ids": empresas},
        )
        session.execute(
            text("delete from nucleo.empresas where id = any(:ids)"),
            {"ids": empresas},
        )
        session.commit()


# ---------------------------------------------------------------------------
# 1. Rol efectivo por engine
# ---------------------------------------------------------------------------
def test_nucleo_corre_como_rol_sin_bypassrls():
    """`select current_user` del engine del núcleo = rol del DSN, sin BYPASSRLS."""
    _url_test()
    esperado = make_url(_url_nucleo()).username
    rol, bypass = db_nucleo._estado_rol(get_engine_nucleo())
    assert rol == esperado, f"el núcleo conecta como {rol!r}, se esperaba {esperado!r}"
    assert rol == "tei_app", "ADR-0005: el rol de aplicación del núcleo es tei_app"
    assert bypass is False, "un rol con rolbypassrls=true deja RLS inerte"


def test_legacy_conserva_su_rol():
    """El legacy sigue con el rol de `DATABASE_URL` (no se degrada ni se cambia)."""
    _url_test()
    esperado = make_url(settings.DATABASE_URL).username
    rol, _ = db_nucleo._estado_rol(get_engine())
    assert rol == esperado
    if (settings.NUCLEO_DATABASE_URL or "").strip():
        rol_nucleo, _ = db_nucleo._estado_rol(get_engine_nucleo())
        assert rol != rol_nucleo, "los dos engines no pueden compartir rol"


# ---------------------------------------------------------------------------
# 2. Aislamiento en base con el engine del núcleo
# ---------------------------------------------------------------------------
def test_rls_aisla_empresas_y_es_fail_closed():
    _url_test()
    _url_nucleo()
    empresas: list[UUID] = []
    try:
        with Session(get_engine()) as semilla:
            empresa_a = _crear_empresa(semilla, "AIS-A")
            empresa_b = _crear_empresa(semilla, "AIS-B")
            empresas = [empresa_a, empresa_b]
            cliente_a = _crear_cliente(semilla, empresa_a, "A")
            cliente_b = _crear_cliente(semilla, empresa_b, "B")

        engine = get_engine_nucleo()
        with contexto_de_request():
            fijar_empresa(empresa_a)
            with Session(engine) as session:
                filas = session.execute(
                    text("select id, empresa_id from nucleo.clientes")
                ).all()
                ids = {f.id for f in filas}
                assert all(f.empresa_id == empresa_a for f in filas)
                assert cliente_a in ids
                assert cliente_b not in ids, "fuga: se ve un cliente de otra empresa"

                # Los servicios commitean a mitad de request: el GUC debe
                # re-aplicarse en la transacción siguiente.
                session.commit()
                filas_tras_commit = session.execute(
                    text("select id, empresa_id from nucleo.clientes")
                ).all()
                assert {f.id for f in filas_tras_commit} == ids

            fijar_empresa(empresa_b)
            with Session(engine) as session:
                filas_b = session.execute(
                    text("select id, empresa_id from nucleo.clientes")
                ).all()
                assert filas_b, "la empresa B debe ver sus propios clientes"
                assert all(f.empresa_id == empresa_b for f in filas_b)
                assert cliente_a not in {f.id for f in filas_b}

            # Fail-closed: sin `app.empresa_id` no hay filas, nunca "todas".
            fijar_empresa(None)
            with Session(engine) as session:
                assert (
                    session.execute(
                        text("select count(*) from nucleo.clientes")
                    ).scalar_one()
                    == 0
                )
                assert (
                    session.execute(text("select nucleo.ctx_empresa()")).scalar_one()
                    is None
                )
    finally:
        _limpiar(empresas)


def test_empresa_ajena_no_se_puede_escribir():
    """`WITH CHECK`: INSERT con `empresa_id` de otra empresa ⇒ 42501 (RLS)."""
    _url_test()
    _url_nucleo()
    empresas: list[UUID] = []
    try:
        with Session(get_engine()) as semilla:
            empresa_a = _crear_empresa(semilla, "ESC-A")
            empresa_b = _crear_empresa(semilla, "ESC-B")
            empresas = [empresa_a, empresa_b]

        with contexto_de_request():
            fijar_empresa(empresa_a)
            with (
                Session(get_engine_nucleo()) as session,
                pytest.raises(ProgrammingError) as excinfo,
            ):
                session.execute(
                    text(
                        "insert into nucleo.clientes"
                        " (empresa_id, razon_social, rut)"
                        " values (:empresa_id, 'Intruso', :rut)"
                    ),
                    {"empresa_id": empresa_b, "rut": str(uuid4().int)[:9]},
                )
                session.commit()
        mensaje = str(excinfo.value)
        assert "row-level security" in mensaje or "42501" in mensaje, mensaje
    finally:
        _limpiar(empresas)


# ---------------------------------------------------------------------------
# 3-4. HTTP: aislamiento y resolución de auth_id
# ---------------------------------------------------------------------------
def _auth_de_fixture(monkeypatch, auth_id: str) -> None:
    """Sustituye solo la extracción del `sub` del JWT (ver docstring del módulo)."""
    monkeypatch.setattr(deps, "auth_id_from_credentials", lambda credentials: auth_id)
    monkeypatch.setattr(
        api_nucleo, "auth_id_from_credentials", lambda credentials: auth_id
    )


def test_http_aislamiento_entre_empresas(client, monkeypatch):
    _url_test()
    auth_id = str(uuid4())
    empresas: list[UUID] = []
    try:
        with Session(get_engine()) as semilla:
            empresa_a = _crear_empresa(semilla, "HTTP-A")
            empresa_b = _crear_empresa(semilla, "HTTP-B")
            empresas = [empresa_a, empresa_b]
            _membresia(semilla, empresa_a, auth_id)
            cliente_a = _crear_cliente(semilla, empresa_a, "A")
            cliente_b = _crear_cliente(semilla, empresa_b, "B")

        _auth_de_fixture(monkeypatch, auth_id)

        # a) El usuario de A ve datos de A (y nunca de B).
        resp = client.get(
            f"{API}/nucleo/clientes", headers={"X-Empresa-ID": str(empresa_a)}
        )
        assert resp.status_code == 200, resp.text
        cuerpo = resp.json()
        ids = {fila["id"] for fila in cuerpo}
        assert str(cliente_a) in ids
        assert str(cliente_b) not in ids
        assert {fila["empresa_id"] for fila in cuerpo} == {str(empresa_a)}

        # b) Empresa B con un usuario que no es miembro: 403 sin fuga.
        resp_b = client.get(
            f"{API}/nucleo/clientes", headers={"X-Empresa-ID": str(empresa_b)}
        )
        assert resp_b.status_code == 403, resp_b.text
        assert resp_b.json()["codigo"] == "ACCESO_DENEGADO"
        assert str(cliente_b) not in resp_b.text

        # c) Sin `X-Empresa-ID`: 4xx (el tenant no se resuelve por defecto).
        sin_header = client.get(f"{API}/nucleo/clientes")
        assert 400 <= sin_header.status_code < 500, sin_header.text

        # d) UUID inválido: 422 antes de tocar la base (no 22P02).
        invalido = client.get(
            f"{API}/nucleo/clientes", headers={"X-Empresa-ID": "no-es-uuid"}
        )
        assert 400 <= invalido.status_code < 500, invalido.text
    finally:
        _limpiar(empresas)


def test_http_mis_empresas_resuelve_por_auth_id(client, monkeypatch):
    """Sin `X-Empresa-ID` la lista sale del GUC `nucleo.auth_id`, no de un body."""
    _url_test()
    auth_id = str(uuid4())
    empresas: list[UUID] = []
    try:
        with Session(get_engine()) as semilla:
            empresa_a = _crear_empresa(semilla, "MIS-A")
            empresa_b = _crear_empresa(semilla, "MIS-B")
            empresas = [empresa_a, empresa_b]
            _membresia(semilla, empresa_a, auth_id)

        _auth_de_fixture(monkeypatch, auth_id)

        resp = client.get(f"{API}/nucleo/mis-empresas")
        assert resp.status_code == 200, resp.text
        ids = {fila["id"] for fila in resp.json()}
        assert str(empresa_a) in ids
        assert str(empresa_b) not in ids
    finally:
        _limpiar(empresas)


# ---------------------------------------------------------------------------
# 5-6. Fallback y guarda de rol
# ---------------------------------------------------------------------------
def test_fallback_sin_nucleo_database_url_funciona_y_avisa(monkeypatch, caplog):
    _url_test()
    monkeypatch.setattr(settings, "NUCLEO_DATABASE_URL", "")
    monkeypatch.setattr(db_nucleo, "_engine_nucleo", None)
    monkeypatch.setattr(db_nucleo, "_rol_nucleo", None)
    monkeypatch.setattr(db_nucleo, "_nucleo_es_fallback", False)

    url, es_fallback = db_nucleo.url_nucleo()
    assert es_fallback is True
    assert url == settings.DATABASE_URL

    with caplog.at_level(logging.WARNING, logger="app.core.database"):
        engine = get_engine_nucleo()
    assert any(
        "RLS inerte: configure NUCLEO_DATABASE_URL" in m for m in caplog.messages
    ), caplog.messages
    assert make_url(str(engine.url)).database == make_url(settings.DATABASE_URL).database

    with Session(engine) as session:
        assert session.execute(text("select 1")).scalar_one() == 1
    engine.dispose()


def test_guarda_rechaza_dsn_explicito_con_bypassrls():
    """ADR-0005 §3.2.3: si el DSN del núcleo bypasea RLS, 503 (no se sirve tráfico)."""
    _url_test()
    _, bypass = db_nucleo._estado_rol(get_engine())
    if not bypass:
        pytest.skip("El rol legacy no tiene BYPASSRLS en este entorno")
    with pytest.raises(HTTPException) as excinfo:
        db_nucleo.verificar_rol_nucleo(get_engine(), fallback=False)
    assert excinfo.value.status_code == 503
    # El mensaje al cliente no filtra el rol ni detalles de PostgreSQL.
    assert "bypass" not in str(excinfo.value.detail).lower()


def test_http_nucleo_responde_503_si_el_dsn_bypasea_rls(client, monkeypatch):
    """ADR-0005 criterio 2, extremo a extremo: nunca se sirve tráfico sin RLS."""
    _url_test()
    _, bypass = db_nucleo._estado_rol(get_engine())
    if not bypass:
        pytest.skip("El rol legacy no tiene BYPASSRLS en este entorno")
    # Simula el despliegue defectuoso: el DSN "del núcleo" apunta al rol
    # privilegiado (el engine legacy) y no es fallback.
    monkeypatch.setattr(db_nucleo, "_engine_nucleo", get_engine())
    monkeypatch.setattr(db_nucleo, "_rol_nucleo", None)
    monkeypatch.setattr(db_nucleo, "_nucleo_es_fallback", False)

    resp = client.get(f"{API}/nucleo/mis-empresas")
    assert resp.status_code == 503, resp.text
    assert "bypass" not in resp.text.lower()
    assert "postgres" not in resp.text.lower()


def test_guarda_en_fallback_solo_avisa(caplog):
    """El fallback es un modo declarado de esta ola: avisa, no bloquea."""
    _url_test()
    _, bypass = db_nucleo._estado_rol(get_engine())
    if not bypass:
        pytest.skip("El rol legacy no tiene BYPASSRLS en este entorno")
    with caplog.at_level(logging.WARNING, logger="app.core.database"):
        rol = db_nucleo.verificar_rol_nucleo(get_engine(), fallback=True)
    assert rol
    assert any("RLS inerte" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# 7. Frontera estática: el núcleo no lee `public`
# ---------------------------------------------------------------------------
def test_solo_servicio_cutover_usa_el_engine_legacy():
    raiz = Path(__file__).resolve().parents[1] / "app" / "nucleo"
    infracciones: list[str] = []
    for archivo in sorted(raiz.glob("*.py")):
        if archivo.name == "servicio_cutover.py":
            continue
        contenido = archivo.read_text(encoding="utf-8")
        if re.search(r"\bpublic\.", contenido):
            infracciones.append(f"{archivo.name}: referencia a public.*")
        if re.search(r"core\.database import (get_engine|get_session)\b", contenido):
            infracciones.append(f"{archivo.name}: importa el engine/sesión legacy")
    assert infracciones == [], infracciones
