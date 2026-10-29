"""Pruebas P0-07: mi viaje, check-in/out y transiciones del conductor."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine

from app.core.config import settings
from app.nucleo.deps import ContextoEmpresa, RolEmpresa
from app.nucleo.errores import AccesoDenegado, EstadoViajeInvalido
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
    Viaje,
)
from app.nucleo.schemas import CheckInOutConductor, TransicionConductor
from app.nucleo.servicio_conductor import ServicioConductor


def _url() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite integración del conductor")
    return url


def _crear_escenario(session: Session, empresa: Empresa, sufijo: str, auth_id: str):
    token = uuid4().hex[:8]
    digitos = str(uuid4().int)[:10]
    vence = date.today() + timedelta(days=365)
    cliente = Cliente(
        empresa_id=empresa.id,
        razon_social=f"Cliente Conductor {sufijo}",
        rut=digitos,
    )
    tracto = Tracto(
        empresa_id=empresa.id,
        patente=f"C{token[:6].upper()}",
        peso_bruto_kg=Decimal("39000"),
        tara_kg=Decimal("9000"),
        capacidad_carga_kg=Decimal("30000"),
    )
    rampla = Rampla(
        empresa_id=empresa.id,
        patente=f"K{token[:6].upper()}",
        tipo=TipoRampla.plana,
        capacidad_carga_kg=Decimal("30000"),
    )
    chofer = Chofer(
        empresa_id=empresa.id,
        rut=str(int(digitos) + 1),
        nombre="Conductor",
        apellido_paterno=sufijo,
        numero_licencia=f"LC-{token}",
        licencia_clase="A5",
        auth_id=auth_id,
    )
    session.add_all([cliente, tracto, rampla, chofer])
    session.commit()
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
        codigo=f"TC-{token}",
        nombre="Ruta conductor",
        modalidad=ModalidadTarifa.viaje,
        vigencia_desde=date.today() - timedelta(days=30),
        vigencia_hasta=vence,
        precio_unitario=Decimal("100000"),
    )
    oc = OrdenCompra(
        empresa_id=empresa.id,
        cliente_id=cliente.id,
        numero_oc=f"OCC-{token}",
        vigencia_desde=date.today() - timedelta(days=30),
        vigencia_hasta=vence,
        monto_autorizado=Decimal("1000000"),
    )
    session.add_all(docs + [tarifa, oc])
    session.commit()
    ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    inicio = ahora - timedelta(hours=6)
    viaje = Viaje(
        empresa_id=empresa.id,
        cliente_id=cliente.id,
        orden_compra_id=oc.id,
        tarifa_id=tarifa.id,
        tracto_id=tracto.id,
        rampla_id=rampla.id,
        chofer_id=chofer.id,
        estado=EstadoViaje.asignado,
        inicio_planificado=inicio,
        fin_planificado=inicio + timedelta(hours=5),
        buffer_minutos=60,
        peso_bruto_kg=Decimal("20000"),
        origen_nombre="Santiago",
        destino_nombre="Concepción",
        valor_flete_neto=Decimal("100000"),
    )
    session.add(viaje)
    session.commit()
    session.refresh(viaje)
    return chofer, viaje


def test_conductor_mi_viaje_y_transiciones():
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("select auth_id from nucleo.choferes limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover
                pytest.skip(f"Falta aplicar la migración 0010: {exc}")

        sufijo = uuid4().hex[:8]
        with Session(engine) as session:
            empresa = Empresa(
                codigo=f"CON-{sufijo}",
                razon_social=f"Empresa Conductor {sufijo}",
                rut=f"CON-{sufijo}",
            )
            session.add(empresa)
            session.commit()
            session.refresh(empresa)

            auth_id = str(uuid4())
            chofer, viaje = _crear_escenario(session, empresa, sufijo, auth_id)
            contexto = ContextoEmpresa(
                auth_id=auth_id, empresa=empresa, rol=RolEmpresa.conductor
            )
            servicio = ServicioConductor(session, contexto)

            mi = servicio.mi_viaje()
            assert mi.viaje is not None
            assert mi.viaje.id == viaje.id
            assert mi.chofer.id == chofer.id
            assert "iniciar carga" in (mi.siguiente_accion or "").lower()
            assert mi.acciones_disponibles == ["en_carga"]

            with pytest.raises(EstadoViajeInvalido):
                servicio.transicion(
                    viaje.id,
                    TransicionConductor(estado_destino=EstadoViaje.en_ruta),
                )

            mi = servicio.check_in(viaje.id, CheckInOutConductor(nota="Llegué a origen"))
            assert mi.viaje is not None
            assert mi.viaje.estado == EstadoViaje.en_carga
            assert mi.viaje.inicio_real is not None
            assert any(e.tipo == "check_in" for e in mi.viaje.eventos)

            mi = servicio.transicion(
                viaje.id,
                TransicionConductor(estado_destino=EstadoViaje.cargado),
            )
            assert mi.viaje is not None and mi.viaje.estado == EstadoViaje.cargado

            mi = servicio.transicion(
                viaje.id,
                TransicionConductor(estado_destino=EstadoViaje.en_ruta),
            )
            assert mi.viaje is not None and mi.viaje.estado == EstadoViaje.en_ruta

            mi = servicio.transicion(
                viaje.id,
                TransicionConductor(estado_destino=EstadoViaje.en_descarga),
            )
            assert mi.viaje is not None and mi.viaje.estado == EstadoViaje.en_descarga

            mi = servicio.check_out(
                viaje.id, CheckInOutConductor(nota="Descarga terminada")
            )
            assert mi.viaje is not None
            assert mi.viaje.estado == EstadoViaje.descargado
            assert mi.viaje.fin_real is not None

            mi = servicio.transicion(
                viaje.id,
                TransicionConductor(estado_destino=EstadoViaje.pod_pendiente),
            )
            assert mi.viaje is not None and mi.viaje.estado == EstadoViaje.pod_pendiente

            # Otro usuario no puede ver ni mover el viaje.
            otro = ServicioConductor(
                session,
                ContextoEmpresa(
                    auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.conductor
                ),
            )
            with pytest.raises(AccesoDenegado):
                otro.mi_viaje()

            # Despacho puede previsualizar el viaje de un chofer.
            preview = ServicioConductor(
                session,
                ContextoEmpresa(
                    auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.despacho
                ),
            ).mi_viaje(chofer_id=chofer.id)
            assert preview.viaje is not None
            assert preview.viaje.id == viaje.id
    finally:
        engine.dispose()
