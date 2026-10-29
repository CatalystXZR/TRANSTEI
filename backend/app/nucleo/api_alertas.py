"""API de alertas y tablero del dueño (P0-11)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.permisos import requiere_permiso
from app.nucleo.schemas import TableroOut
from app.nucleo.servicio_alertas import ServicioAlertas

router = APIRouter(prefix="/nucleo/alertas", tags=["nucleo-alertas"])


def get_servicio(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("alertas:leer")),
) -> ServicioAlertas:
    return ServicioAlertas(session, contexto)


@router.get("/tablero", response_model=TableroOut)
def tablero(
    servicio: ServicioAlertas = Depends(get_servicio),
):
    return servicio.tablero()
