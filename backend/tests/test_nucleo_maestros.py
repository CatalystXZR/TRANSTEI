"""Integración de CRUD de maestros del núcleo.

Requiere una base PostgreSQL con la migración 0004. No toca Storage; la subida
de documentos se prueba en la API/UI local porque depende del bucket.
"""

from __future__ import annotations

import os
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine

from app.core.config import settings
from app.nucleo.deps import ContextoEmpresa, RolEmpresa
from app.nucleo.models import Empresa
from app.nucleo.schemas import (
    ChoferCreateNucleo,
    ClienteCreateNucleo,
    RamplaCreateNucleo,
    TractoCreateNucleo,
)
from app.nucleo.servicio_maestros import ServicioMaestros

pytestmark = pytest.mark.integracion


def _url() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite integración de maestros")
    return url


def test_crud_maestros_y_versionado():
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("select 1 from nucleo.empresas limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover
                pytest.skip(f"Falta aplicar la migración 0004: {exc}")

        sufijo = uuid4().hex[:8]
        with Session(engine) as session:
            empresa = Empresa(
                codigo=f"MAE-{sufijo}",
                razon_social=f"Empresa Maestros {sufijo}",
                rut=f"MAE-{sufijo}",
            )
            session.add(empresa)
            session.commit()
            session.refresh(empresa)

            servicio = ServicioMaestros(
                session,
                ContextoEmpresa(
                    auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.admin
                ),
            )

            cliente = servicio.crear_cliente(
                ClienteCreateNucleo(
                    razon_social=f"Cliente {sufijo}",
                    rut=f"CLI-{sufijo}",
                    dias_pago=30,
                )
            )
            assert cliente.activo is True
            version_inicial = cliente.version

            cliente = servicio.actualizar_cliente(
                cliente.id,
                ClienteCreateNucleo(
                    razon_social=f"Cliente editado {sufijo}",
                    rut=f"CLI-{sufijo}",
                    dias_pago=45,
                ),
            )
            assert cliente.razon_social.startswith("Cliente editado")
            assert cliente.version > version_inicial

            cliente = servicio.desactivar_cliente(cliente.id)
            assert cliente.activo is False

            tracto = servicio.crear_tracto(
                TractoCreateNucleo(
                    patente=f"T{sufijo[:6].upper()}",
                    peso_bruto_kg=Decimal("39000"),
                    tara_kg=Decimal("9000"),
                    capacidad_carga_kg=Decimal("30000"),
                    licencias_permitidas=["A5"],
                )
            )
            assert tracto.activo is True
            tracto = servicio.desactivar_tracto(tracto.id)
            assert tracto.activo is False

            rampla = servicio.crear_rampla(
                RamplaCreateNucleo(
                    patente=f"R{sufijo[:6].upper()}",
                    capacidad_carga_kg=Decimal("30000"),
                    volumen_m3=Decimal("80"),
                )
            )
            assert rampla.activo is True
            rampla = servicio.desactivar_rampla(rampla.id)
            assert rampla.activo is False

            chofer = servicio.crear_chofer(
                ChoferCreateNucleo(
                    rut=f"CHO-{sufijo}",
                    nombre="Chofer",
                    apellido_paterno="Maestros",
                    numero_licencia=f"LIC-{sufijo}",
                    licencia_clase="A5",
                )
            )
            assert chofer.activo is True
            chofer = servicio.desactivar_chofer(chofer.id)
            assert chofer.activo is False
    finally:
        engine.dispose()
