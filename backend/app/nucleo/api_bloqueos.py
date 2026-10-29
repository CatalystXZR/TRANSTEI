"""API de bloqueos de recursos y agenda (P0-04)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.core.database import get_session
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.models import TipoRecurso, TipoReserva
from app.nucleo.permisos import requiere_permiso
from app.nucleo.schemas import (
    AgendaOut,
    BloqueoCreate,
    BloqueoOut,
    BloqueoUpdate,
    CancelarBloqueo,
)
from app.nucleo.servicio_bloqueos import ServicioBloqueos

router = APIRouter(prefix="/nucleo", tags=["nucleo-agenda"])

def get_servicio_lectura(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("agenda:leer")),
) -> ServicioBloqueos:
    return ServicioBloqueos(session, contexto)


def get_servicio_escritura(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("agenda:escribir")),
) -> ServicioBloqueos:
    return ServicioBloqueos(session, contexto)


@router.get("/bloqueos", response_model=list[BloqueoOut])
def listar_bloqueos(
    desde: datetime,
    hasta: datetime,
    tipo_reserva: TipoReserva | None = Query(default=None),
    recurso_tipo: TipoRecurso | None = Query(default=None),
    recurso_id: UUID | None = Query(default=None),
    incluir_inactivos: bool = Query(default=False),
    servicio: ServicioBloqueos = Depends(get_servicio_lectura),
):
    return servicio.listar_bloqueos(
        desde=desde,
        hasta=hasta,
        tipo_reserva=tipo_reserva,
        recurso_tipo=recurso_tipo,
        recurso_id=recurso_id,
        incluir_inactivos=incluir_inactivos,
    )


@router.post("/bloqueos", response_model=BloqueoOut, status_code=status.HTTP_201_CREATED)
def crear_bloqueo(
    body: BloqueoCreate,
    servicio: ServicioBloqueos = Depends(get_servicio_escritura),
):
    return servicio.crear_bloqueo(body)


@router.put("/bloqueos/{bloqueo_id}", response_model=BloqueoOut)
def actualizar_bloqueo(
    bloqueo_id: UUID,
    body: BloqueoUpdate,
    servicio: ServicioBloqueos = Depends(get_servicio_escritura),
):
    return servicio.actualizar_bloqueo(bloqueo_id, body)


@router.post("/bloqueos/{bloqueo_id}/cancelar", response_model=BloqueoOut)
def cancelar_bloqueo(
    bloqueo_id: UUID,
    body: CancelarBloqueo,
    servicio: ServicioBloqueos = Depends(get_servicio_escritura),
):
    return servicio.cancelar_bloqueo(bloqueo_id, body)


@router.get("/agenda", response_model=AgendaOut)
def agenda(
    desde: datetime,
    hasta: datetime,
    recurso_tipo: TipoRecurso | None = Query(default=None),
    servicio: ServicioBloqueos = Depends(get_servicio_lectura),
):
    return servicio.agenda(desde=desde, hasta=hasta, recurso_tipo=recurso_tipo)
