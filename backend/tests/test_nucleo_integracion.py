"""Prueba de integración real del núcleo v2.

Requiere una base PostgreSQL dedicada con la migración 0004 aplicada:

    export NUCLEO_TEST_DATABASE_URL="postgresql+psycopg://postgres:...@host:5432/db"

No usa `create_all`: el DDL se aplica con Supabase CLI/Alembic. Si la variable
no está definida, la prueba se omite para no romper el CI sin secretos.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from app.core.config import settings
from app.nucleo.deps import ContextoEmpresa, RolEmpresa
from app.nucleo.errores import ConflictoDisponibilidad
from app.nucleo.models import (
    Chofer,
    Cliente,
    Documento,
    Empresa,
    EstadoViaje,
    ModalidadTarifa,
    OrdenCompra,
    Rampla,
    Tarifa,
    TipoDocumento,
    TipoRampla,
    TipoRecurso,
    Tracto,
    UsuarioEmpresa,
    Viaje,
)
from app.nucleo.schemas import SolicitudAsignacion, ViajeCreateNucleo
from app.nucleo.servicio_disponibilidad import (
    ServicioDisponibilidad,
    listar_empresas_usuario,
)
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine

pytestmark = pytest.mark.integracion


def _url() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite integración del núcleo")
    return url


def test_asignacion_y_doble_asignacion_en_postgresql_real():
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("select 1 from nucleo.empresas limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover - depende del entorno
                pytest.skip(f"Falta aplicar la migración 0004: {exc}")

        sufijo = uuid4().hex[:8]
        ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        inicio = ahora + timedelta(days=30)
        fin = inicio + timedelta(hours=4)

        with Session(engine) as session:
            empresa = Empresa(
                codigo=f"TEST-{sufijo}",
                razon_social=f"Empresa Test {sufijo}",
                rut=f"TEST-{sufijo}",
                buffer_operacional_min=60,
            )
            # El tenant se persiste primero: no hay relationships ORM que
            # ordenen automáticamente los INSERT dependientes en un solo flush.
            session.add(empresa)
            session.commit()

            auth_id = uuid4()
            session.add(
                UsuarioEmpresa(
                    empresa_id=empresa.id,
                    auth_id=auth_id,
                    rol=RolEmpresa.despacho,
                )
            )
            session.commit()

            cliente = Cliente(
                empresa_id=empresa.id,
                razon_social=f"Cliente Test {sufijo}",
                rut=f"CLI-{sufijo}",
            )
            tracto = Tracto(
                empresa_id=empresa.id,
                patente=f"T{sufijo[:6].upper()}",
                peso_bruto_kg=Decimal("39000"),
                tara_kg=Decimal("9000"),
                capacidad_carga_kg=Decimal("30000"),
                licencias_permitidas=["A5"],
            )
            rampla = Rampla(
                empresa_id=empresa.id,
                patente=f"R{sufijo[:6].upper()}",
                tipo=TipoRampla.plana,
                capacidad_carga_kg=Decimal("30000"),
                volumen_m3=Decimal("80"),
            )
            chofer = Chofer(
                empresa_id=empresa.id,
                rut=f"CHO-{sufijo}",
                nombre=f"Chofer {sufijo}",
                numero_licencia=f"LIC-{sufijo}",
                licencia_clase="A5",
            )
            session.add_all([cliente, tracto, rampla, chofer])
            session.commit()

            vence = date.today() + timedelta(days=365)
            docs = [
                Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.tracto, tracto_id=tracto.id, tipo=TipoDocumento.revision_tecnica, vence_en=vence),
                Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.tracto, tracto_id=tracto.id, tipo=TipoDocumento.permiso_circulacion, vence_en=vence),
                Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.tracto, tracto_id=tracto.id, tipo=TipoDocumento.seguro_obligatorio, vence_en=vence),
                Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.tracto, tracto_id=tracto.id, tipo=TipoDocumento.soap, vence_en=vence),
                Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.rampla, rampla_id=rampla.id, tipo=TipoDocumento.revision_tecnica, vence_en=vence),
                Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.rampla, rampla_id=rampla.id, tipo=TipoDocumento.permiso_circulacion, vence_en=vence),
                Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.rampla, rampla_id=rampla.id, tipo=TipoDocumento.seguro_carga, vence_en=vence),
                Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.chofer, chofer_id=chofer.id, tipo=TipoDocumento.licencia_conducir, vence_en=vence),
                Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.chofer, chofer_id=chofer.id, tipo=TipoDocumento.examen_medico, vence_en=vence),
            ]
            tarifa = Tarifa(
                empresa_id=empresa.id,
                cliente_id=cliente.id,
                codigo=f"T-{sufijo}",
                nombre="Ruta test",
                modalidad=ModalidadTarifa.viaje,
                vigencia_desde=date.today(),
                vigencia_hasta=date.today() + timedelta(days=365),
                precio_unitario=Decimal("100000"),
            )
            oc = OrdenCompra(
                empresa_id=empresa.id,
                cliente_id=cliente.id,
                numero_oc=f"OC-{sufijo}",
                vigencia_desde=date.today(),
                vigencia_hasta=date.today() + timedelta(days=365),
                monto_autorizado=Decimal("1000000"),
            )
            session.add_all(docs + [tarifa, oc])
            session.commit()

            viaje = Viaje(
                empresa_id=empresa.id,
                numero_viaje=f"VJ-{sufijo}-1",
                cliente_id=cliente.id,
                orden_compra_id=oc.id,
                tarifa_id=tarifa.id,
                estado=EstadoViaje.confirmado,
                inicio_planificado=inicio,
                fin_planificado=fin,
                buffer_minutos=60,
                peso_bruto_kg=Decimal("25000"),
                origen_nombre="Santiago",
                destino_nombre="Concepción",
                valor_flete_neto=Decimal("100000"),
            )
            session.add(viaje)
            session.commit()
            session.refresh(viaje)

            # El folio debe generarlo PostgreSQL, no el frontend.
            viaje_folio = Viaje(
                empresa_id=empresa.id,
                cliente_id=cliente.id,
                orden_compra_id=oc.id,
                tarifa_id=tarifa.id,
                estado=EstadoViaje.confirmado,
                inicio_planificado=inicio + timedelta(days=60),
                fin_planificado=inicio + timedelta(days=60, hours=4),
                buffer_minutos=60,
                peso_bruto_kg=Decimal("20000"),
                origen_nombre="Santiago",
                destino_nombre="Rancagua",
                valor_flete_neto=Decimal("50000"),
            )
            session.add(viaje_folio)
            session.commit()
            session.refresh(viaje_folio)
            assert viaje_folio.numero_viaje is not None
            assert viaje_folio.numero_viaje.startswith("VJ-")

            contexto = ContextoEmpresa(
                auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.despacho
            )
            servicio = ServicioDisponibilidad(session, contexto)
            empresas_usuario = listar_empresas_usuario(session, str(auth_id))
            assert any(e.id == empresa.id for e in empresas_usuario)

            listado = servicio.listar_viajes(
                desde=inicio - timedelta(days=1),
                hasta=inicio + timedelta(days=1),
            )
            assert any(v.id == viaje.id for v in listado.items)

            creado = servicio.crear_viaje(
                ViajeCreateNucleo(
                    cliente_id=cliente.id,
                    orden_compra_id=oc.id,
                    tarifa_id=tarifa.id,
                    inicio_planificado=inicio + timedelta(days=20),
                    fin_planificado=inicio + timedelta(days=20, hours=4),
                    origen_nombre="Santiago",
                    destino_nombre="Valparaíso",
                    distancia_km=Decimal("120"),
                    peso_bruto_kg=Decimal("20000"),
                    tipo_carga="general",
                    descripcion_carga="Carga creada en integración",
                )
            )
            assert creado.estado == EstadoViaje.confirmado
            assert creado.numero_viaje.startswith("VJ-")
            assert creado.flete_total == Decimal("100000.00")
            assert creado.oc_numero == oc.numero_oc

            propuesta = SolicitudAsignacion(
                tracto_id=tracto.id,
                rampla_id=rampla.id,
                chofer_id=chofer.id,
                inicio_planificado=inicio,
                fin_planificado=fin,
            )

            confirmada = servicio.confirmar_asignacion(viaje.id, propuesta)
            assert confirmada.estado == EstadoViaje.asignado
            assert len(confirmada.reservas) == 3
            assert confirmada.audit_ok is True

            viaje2 = Viaje(
                empresa_id=empresa.id,
                numero_viaje=f"VJ-{sufijo}-2",
                cliente_id=cliente.id,
                orden_compra_id=oc.id,
                tarifa_id=tarifa.id,
                estado=EstadoViaje.confirmado,
                inicio_planificado=inicio + timedelta(hours=1),
                fin_planificado=fin + timedelta(hours=1),
                buffer_minutos=60,
                peso_bruto_kg=Decimal("20000"),
                origen_nombre="Santiago",
                destino_nombre="Talca",
                valor_flete_neto=Decimal("50000"),
            )
            session.add(viaje2)
            session.commit()
            session.refresh(viaje2)

            segunda = SolicitudAsignacion(
                tracto_id=tracto.id,
                rampla_id=rampla.id,
                chofer_id=chofer.id,
                inicio_planificado=viaje2.inicio_planificado,
                fin_planificado=viaje2.fin_planificado,
            )
            preview = servicio.validar_asignacion(viaje2.id, segunda)
            assert preview.apto is False
            assert preview.conflictos

            with pytest.raises(ConflictoDisponibilidad):
                servicio.confirmar_asignacion(viaje2.id, segunda)
    finally:
        engine.dispose()
