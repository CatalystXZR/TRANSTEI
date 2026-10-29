"""API de la PWA del conductor (P0-07)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.database import get_session
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.permisos import requiere_permiso
from app.nucleo.schemas import (
    CheckInOutConductor,
    MiViajeOut,
    TransicionConductor,
)
from app.nucleo.servicio_conductor import ServicioConductor

router = APIRouter(prefix="/nucleo/conductor", tags=["nucleo-conductor"])

def get_servicio(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("conductor:usar")),
) -> ServicioConductor:
    return ServicioConductor(session, contexto)


@router.get("/mi-viaje", response_model=MiViajeOut)
def mi_viaje(
    chofer_id: UUID | None = Query(default=None),
    servicio: ServicioConductor = Depends(get_servicio),
):
    return servicio.mi_viaje(chofer_id=chofer_id)


@router.post("/viajes/{viaje_id}/transicion", response_model=MiViajeOut)
def transicion(
    viaje_id: UUID,
    body: TransicionConductor,
    chofer_id: UUID | None = Query(default=None),
    servicio: ServicioConductor = Depends(get_servicio),
):
    return servicio.transicion(viaje_id, body, chofer_id=chofer_id)


@router.post("/viajes/{viaje_id}/check-in", response_model=MiViajeOut)
def check_in(
    viaje_id: UUID,
    body: CheckInOutConductor,
    chofer_id: UUID | None = Query(default=None),
    servicio: ServicioConductor = Depends(get_servicio),
):
    return servicio.check_in(viaje_id, body, chofer_id=chofer_id)


@router.post("/viajes/{viaje_id}/check-out", response_model=MiViajeOut)
def check_out(
    viaje_id: UUID,
    body: CheckInOutConductor,
    chofer_id: UUID | None = Query(default=None),
    servicio: ServicioConductor = Depends(get_servicio),
):
    return servicio.check_out(viaje_id, body, chofer_id=chofer_id)
