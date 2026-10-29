"""Pruebas P0-04: bloqueos de recursos y agenda."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine

from app.core.config import settings
from app.nucleo.deps import ContextoEmpresa, RolEmpresa
from app.nucleo.errores import (
    ConflictoConcurrencia,
    ConflictoDisponibilidad,
    RecursoNoEncontrado,
)
from app.nucleo.models import (
    Cliente,
    Empresa,
    EstadoViaje,
    ReservaRecurso,
    TipoRecurso,
    TipoReserva,
    Tracto,
    Viaje,
)
from app.nucleo.schemas import BloqueoCreate, BloqueoUpdate, CancelarBloqueo
from app.nucleo.servicio_bloqueos import ServicioBloqueos


def _url() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite integración de bloqueos")
    return url


def test_schema_bloqueo_rechaza_viaje_y_fechas_invalidas():
    base = dict(
        recurso_tipo="tracto",
        recurso_id=uuid4(),
        inicio=datetime.now(timezone.utc),
        fin=datetime.now(timezone.utc) + timedelta(hours=2),
        motivo="Mantención preventiva",
    )
    with pytest.raises(ValidationError):
        BloqueoCreate(tipo_reserva="viaje", **base)
    with pytest.raises(ValidationError):
        BloqueoCreate(
            tipo_reserva="mantenimiento",
            **{**base, "fin": base["inicio"]},
        )


def test_bloqueos_y_agenda_en_postgresql():
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("select 1 from nucleo.reservas_recurso limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover
                pytest.skip(f"Falta aplicar la migración 0004/0006: {exc}")

        sufijo = uuid4().hex[:8]
        ahora = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        inicio = ahora + timedelta(days=15)
        fin = inicio + timedelta(hours=6)

        with Session(engine) as session:
            empresa = Empresa(
                codigo=f"BLQ-{sufijo}",
                razon_social=f"Empresa Bloqueos {sufijo}",
                rut=f"BLQ-{sufijo}",
            )
            session.add(empresa)
            session.commit()
            session.refresh(empresa)

            tracto = Tracto(
                empresa_id=empresa.id,
                patente=f"B{sufijo[:6].upper()}",
                peso_bruto_kg=Decimal("39000"),
                tara_kg=Decimal("9000"),
                capacidad_carga_kg=Decimal("30000"),
            )
            cliente = Cliente(
                empresa_id=empresa.id,
                razon_social=f"Cliente Bloqueo {sufijo}",
                rut=f"CBL-{sufijo}",
            )
            session.add_all([tracto, cliente])
            session.commit()
            session.refresh(tracto)
            session.refresh(cliente)

            contexto = ContextoEmpresa(
                auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.despacho
            )
            servicio = ServicioBloqueos(session, contexto)

            bloqueo = servicio.crear_bloqueo(
                BloqueoCreate(
                    recurso_tipo=TipoRecurso.tracto,
                    recurso_id=tracto.id,
                    inicio=inicio,
                    fin=fin,
                    tipo_reserva=TipoReserva.mantenimiento,
                    motivo="Mantención de 250.000 km",
                )
            )
            assert bloqueo.activa is True
            assert bloqueo.etiqueta == tracto.patente

            with pytest.raises(ConflictoDisponibilidad):
                servicio.crear_bloqueo(
                    BloqueoCreate(
                        recurso_tipo=TipoRecurso.tracto,
                        recurso_id=tracto.id,
                        inicio=inicio + timedelta(hours=1),
                        fin=fin + timedelta(hours=2),
                        tipo_reserva=TipoReserva.bloqueo_manual,
                        motivo="Choque con mantención",
                    )
                )

            # Un viaje reservado en la misma ventana también bloquea.
            viaje = Viaje(
                empresa_id=empresa.id,
                numero_viaje=f"VJ-BLQ-{sufijo}",
                cliente_id=cliente.id,
                tracto_id=tracto.id,
                estado=EstadoViaje.confirmado,
                inicio_planificado=fin + timedelta(days=1),
                fin_planificado=fin + timedelta(days=1, hours=4),
                buffer_minutos=0,
                peso_bruto_kg=Decimal("20000"),
                origen_nombre="Santiago",
                destino_nombre="Talca",
                valor_flete_neto=Decimal("100000"),
            )
            session.add(viaje)
            session.commit()
            session.refresh(viaje)
            session.execute(
                text(
                    """
                    insert into nucleo.reservas_recurso
                      (empresa_id, recurso_tipo, tracto_id, ventana, tipo_reserva,
                       viaje_id, motivo, activa, creado_por)
                    values
                      (:empresa_id, 'tracto', :tracto_id,
                       tstzrange(:inicio, :fin, '[)'), 'viaje', :viaje_id,
                       'Viaje de prueba', true, 'test')
                    """
                ),
                {
                    "empresa_id": empresa.id,
                    "tracto_id": tracto.id,
                    "inicio": viaje.inicio_planificado,
                    "fin": viaje.fin_planificado,
                    "viaje_id": viaje.id,
                },
            )
            session.commit()

            with pytest.raises(ConflictoDisponibilidad, match="viaje"):
                servicio.crear_bloqueo(
                    BloqueoCreate(
                        recurso_tipo=TipoRecurso.tracto,
                        recurso_id=tracto.id,
                        inicio=viaje.inicio_planificado,
                        fin=viaje.fin_planificado,
                        tipo_reserva=TipoReserva.bloqueo_manual,
                        motivo="Choque con viaje",
                    )
                )

            # Actualización con versión obsoleta.
            with pytest.raises(ConflictoConcurrencia):
                servicio.actualizar_bloqueo(
                    bloqueo.id,
                    BloqueoUpdate(
                        recurso_tipo=TipoRecurso.tracto,
                        recurso_id=tracto.id,
                        inicio=inicio,
                        fin=fin + timedelta(hours=1),
                        tipo_reserva=TipoReserva.mantenimiento,
                        motivo="Mantención extendida",
                        version=bloqueo.version + 3,
                    ),
                )

            actualizado = servicio.actualizar_bloqueo(
                bloqueo.id,
                BloqueoUpdate(
                    recurso_tipo=TipoRecurso.tracto,
                    recurso_id=tracto.id,
                    inicio=inicio,
                    fin=fin + timedelta(hours=1),
                    tipo_reserva=TipoReserva.mantenimiento,
                    motivo="Mantención extendida",
                    version=bloqueo.version,
                ),
            )
            assert actualizado.version > bloqueo.version

            agenda = servicio.agenda(
                desde=ahora,
                hasta=ahora + timedelta(days=30),
                recurso_tipo=TipoRecurso.tracto,
            )
            assert agenda.total_bloqueos == 1
            assert agenda.total_viajes == 1
            assert any(r.recurso_id == tracto.id for r in agenda.recursos)
            fila = next(r for r in agenda.recursos if r.recurso_id == tracto.id)
            assert any(i.origen == "bloqueo" for i in fila.items)
            assert any(i.origen == "viaje" for i in fila.items)

            cancelado = servicio.cancelar_bloqueo(
                bloqueo.id,
                CancelarBloqueo(motivo="Reprogramado por el taller"),
            )
            assert cancelado.activa is False
            assert cancelado.cancelado_motivo == "Reprogramado por el taller"

            # Al cancelar, la ventana queda libre para otro bloqueo.
            nuevo = servicio.crear_bloqueo(
                BloqueoCreate(
                    recurso_tipo=TipoRecurso.tracto,
                    recurso_id=tracto.id,
                    inicio=inicio,
                    fin=fin,
                    tipo_reserva=TipoReserva.descanso,
                    motivo="Descanso reprogramado",
                )
            )
            assert nuevo.activa is True

            with pytest.raises(RecursoNoEncontrado):
                servicio.cancelar_bloqueo(
                    uuid4(), CancelarBloqueo(motivo="No existe")
                )

            # La reserva cancelada no se borra.
            assert session.get(ReservaRecurso, bloqueo.id) is not None
    finally:
        engine.dispose()
