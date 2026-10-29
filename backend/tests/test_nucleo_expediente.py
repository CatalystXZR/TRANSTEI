"""Pruebas P0-05: expediente, checklist, incidentes y cierre."""

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
from app.nucleo.errores import DatosInvalidos
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
from app.nucleo.schemas import (
    ChecklistItemUpdate,
    CerrarViaje,
    EventoCreate,
    IncidenteCreate,
    IncidenteUpdate,
    ParadaCreate,
    ParadaUpdate,
)
from app.nucleo.servicio_expediente import ServicioExpediente


def _url() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite integración del expediente")
    return url


def test_expediente_completo_en_postgresql():
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("select 1 from nucleo.viaje_checklist limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover
                pytest.skip(f"Falta aplicar la migración 0007: {exc}")

        sufijo = uuid4().hex[:8]
        ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        inicio = ahora - timedelta(days=2)
        fin = inicio + timedelta(hours=5)
        vence = date.today() + timedelta(days=365)

        with Session(engine) as session:
            empresa = Empresa(
                codigo=f"EXP-{sufijo}",
                razon_social=f"Empresa Expediente {sufijo}",
                rut=f"EXP-{sufijo}",
            )
            session.add(empresa)
            session.commit()
            session.refresh(empresa)

            cliente = Cliente(
                empresa_id=empresa.id,
                razon_social=f"Cliente Expediente {sufijo}",
                rut=f"CEX-{sufijo}",
            )
            tracto = Tracto(
                empresa_id=empresa.id,
                patente=f"E{sufijo[:6].upper()}",
                peso_bruto_kg=Decimal("39000"),
                tara_kg=Decimal("9000"),
                capacidad_carga_kg=Decimal("30000"),
            )
            rampla = Rampla(
                empresa_id=empresa.id,
                patente=f"P{sufijo[:6].upper()}",
                tipo=TipoRampla.plana,
                capacidad_carga_kg=Decimal("30000"),
            )
            chofer = Chofer(
                empresa_id=empresa.id,
                rut=f"CHO-{sufijo}",
                nombre=f"Chofer {sufijo}",
                numero_licencia=f"LIC-{sufijo}",
                # R-02 / 0016: la base rechaza (23514) todo viaje con chofer
                # que no sea clase A5; el fixture debe cumplir la regla vigente.
                licencia_clase="A5",
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
                codigo=f"T-EXP-{sufijo}",
                nombre="Ruta expediente",
                modalidad=ModalidadTarifa.viaje,
                vigencia_desde=date.today() - timedelta(days=30),
                vigencia_hasta=vence,
                precio_unitario=Decimal("100000"),
            )
            oc = OrdenCompra(
                empresa_id=empresa.id,
                cliente_id=cliente.id,
                numero_oc=f"OC-EXP-{sufijo}",
                vigencia_desde=date.today() - timedelta(days=30),
                vigencia_hasta=vence,
                monto_autorizado=Decimal("1000000"),
            )
            session.add_all(docs + [tarifa, oc])
            session.commit()

            viaje = Viaje(
                empresa_id=empresa.id,
                cliente_id=cliente.id,
                orden_compra_id=oc.id,
                tarifa_id=tarifa.id,
                tracto_id=tracto.id,
                rampla_id=rampla.id,
                chofer_id=chofer.id,
                estado=EstadoViaje.pod_pendiente,
                inicio_planificado=inicio,
                fin_planificado=fin,
                buffer_minutos=60,
                peso_bruto_kg=Decimal("20000"),
                origen_nombre="Santiago",
                destino_nombre="Concepción",
                valor_flete_neto=Decimal("100000"),
            )
            session.add(viaje)
            session.commit()
            session.refresh(viaje)

            contexto = ContextoEmpresa(
                auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.despacho
            )
            servicio = ServicioExpediente(session, contexto)

            detalle = servicio.obtener(viaje.id)
            assert detalle.numero_viaje.startswith("VJ-")
            assert len(detalle.paradas) == 2
            assert len(detalle.checklist) == 5
            assert len(detalle.eventos) >= 1
            assert detalle.qr_url.startswith("data:image/png;base64,")
            assert detalle.resumen.checklist_requeridos_pendientes == 5
            assert detalle.resumen.puede_cerrar is False

            # Paradas: crear, editar y desactivar.
            parada = servicio.crear_parada(
                viaje.id,
                ParadaCreate(
                    tipo="carga",
                    nombre="Bodega intermedia",
                    ciudad="Rancagua",
                    ventana_desde=inicio + timedelta(hours=1),
                    ventana_hasta=inicio + timedelta(hours=2),
                ),
            )
            assert parada.orden == 3
            parada = servicio.actualizar_parada(
                viaje.id,
                parada.id,
                ParadaUpdate(
                    orden=3,
                    tipo="carga",
                    nombre="Bodega intermedia editada",
                    estado="completada",
                    version=parada.version,
                ),
            )
            assert parada.estado == "completada"
            assert servicio.desactivar_parada(viaje.id, parada.id).activo is False

            # Checklist: completar todos los ítems.
            for item in servicio.listar_checklist(viaje.id):
                servicio.actualizar_item_checklist(
                    viaje.id,
                    item.id,
                    ChecklistItemUpdate(completado=True, version=item.version),
                )
            detalle = servicio.obtener(viaje.id)
            assert detalle.resumen.checklist_requeridos_pendientes == 0
            assert detalle.resumen.puede_cerrar is True

            # Evento manual.
            evento = servicio.crear_evento(
                viaje.id,
                EventoCreate(
                    tipo="nota",
                    descripcion="Cliente confirmó ventana de descarga",
                ),
            )
            assert evento.descripcion.startswith("Cliente confirmó")

            # Incidente alto abierto bloquea el cierre.
            incidente = servicio.crear_incidente(
                viaje.id,
                IncidenteCreate(
                    tipo="averia",
                    severidad="alta",
                    descripcion="Falla del sistema de frenos en ruta",
                ),
            )
            assert incidente.estado == "abierto"
            detalle = servicio.obtener(viaje.id)
            assert detalle.resumen.incidentes_abiertos == 1
            assert detalle.resumen.puede_cerrar is False
            with pytest.raises(DatosInvalidos):
                servicio.cerrar_viaje(viaje.id, CerrarViaje())

            resuelto = servicio.actualizar_incidente(
                viaje.id,
                incidente.id,
                IncidenteUpdate(
                    estado="resuelto",
                    resolucion="Se reemplazó la válvula y se probó el sistema",
                    version=incidente.version,
                ),
            )
            assert resuelto.estado == "resuelto"
            assert resuelto.resuelto_en is not None

            cerrado = servicio.cerrar_viaje(
                viaje.id,
                CerrarViaje(observaciones="Cierre probado en integración"),
            )
            assert cerrado.estado == EstadoViaje.cerrado
            assert cerrado.fin_real is not None
            assert any(e.tipo == "cerrado" for e in cerrado.eventos)
            assert cerrado.resumen.puede_cerrar is False  # ya está cerrado

            # La bitácora es inmutable.
            with pytest.raises(SQLAlchemyError):
                session.execute(
                    text(
                        "update nucleo.viaje_eventos set descripcion = 'alterado' "
                        "where viaje_id = :viaje_id"
                    ),
                    {"viaje_id": viaje.id},
                )
            session.rollback()
    finally:
        engine.dispose()
