"""API de control de cutover legacy (P0-13)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.permisos import requiere_permiso
from app.nucleo.schemas import CutoverAccion, CutoverEstadoOut
from app.nucleo.servicio_cutover import ServicioCutover

router = APIRouter(prefix="/nucleo/cutover", tags=["nucleo-cutover"])


def get_servicio_lectura(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("configuracion:leer")),
) -> ServicioCutover:
    return ServicioCutover(session, contexto)


def get_servicio_escritura(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("configuracion:escribir")),
) -> ServicioCutover:
    return ServicioCutover(session, contexto)


@router.get("/estado", response_model=CutoverEstadoOut)
def estado(
    servicio: ServicioCutover = Depends(get_servicio_lectura),
):
    return servicio.estado()


@router.post("/congelar", response_model=CutoverEstadoOut)
def congelar(
    body: CutoverAccion,
    servicio: ServicioCutover = Depends(get_servicio_escritura),
):
    return servicio.congelar(body.motivo)


@router.post("/descongelar", response_model=CutoverEstadoOut)
def descongelar(
    body: CutoverAccion,
    servicio: ServicioCutover = Depends(get_servicio_escritura),
):
    return servicio.descongelar(body.motivo)
