"""Pruebas P0-13: control de cutover y congelamiento legacy."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine

from app.core.config import settings
from app.nucleo.deps import ContextoEmpresa, RolEmpresa
from app.nucleo.models import Empresa
from app.nucleo.servicio_cutover import ServicioCutover, invalidar_cache, legacy_congelado


def _url() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite integración de cutover")
    return url


def test_congelar_y_descongelar_legacy():
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("select 1 from nucleo.cutover_control limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover
                pytest.skip(f"Falta aplicar la migración 0014: {exc}")

        with Session(engine) as session:
            empresa = Empresa(
                codigo=f"CUT-{uuid4().hex[:8]}",
                razon_social="Empresa Cutover",
                rut=f"CUT-{uuid4().hex[:8]}",
            )
            session.add(empresa)
            session.commit()
            session.refresh(empresa)

            contexto = ContextoEmpresa(
                auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.admin
            )
            servicio = ServicioCutover(session, contexto)
            inicial = servicio.estado()
            try:
                congelado = servicio.congelar("Prueba de cutover")
                assert congelado.legacy_escritura_congelada is True
                invalidar_cache()
                assert legacy_congelado() is True

                descongelado = servicio.descongelar("Fin de prueba")
                assert descongelado.legacy_escritura_congelada is False
                invalidar_cache()
                assert legacy_congelado() is False
            finally:
                if inicial.legacy_escritura_congelada:
                    servicio.congelar("Restaurar estado previo")
                else:
                    servicio.descongelar("Restaurar estado previo")
                invalidar_cache()
    finally:
        engine.dispose()
