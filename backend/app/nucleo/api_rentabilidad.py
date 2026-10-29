"""API de margen, tarifa piso, Freight Score y simulador (P0-09)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.database import get_session
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.permisos import requiere_permiso
from app.nucleo.schemas import (
    ConfiguracionCostosOut,
    ConfiguracionCostosUpdate,
    ResultadoRentabilidadOut,
    RentabilidadViajeOut,
    SimulacionFlete,
)
from app.nucleo.servicio_rentabilidad import ServicioRentabilidad

router = APIRouter(prefix="/nucleo", tags=["nucleo-rentabilidad"])

def get_servicio_lectura(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("rentabilidad:leer")),
) -> ServicioRentabilidad:
    return ServicioRentabilidad(session, contexto)


def get_servicio_config(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("rentabilidad:configurar")),
) -> ServicioRentabilidad:
    return ServicioRentabilidad(session, contexto)


@router.get("/rentabilidad/configuracion", response_model=ConfiguracionCostosOut)
def obtener_configuracion(
    servicio: ServicioRentabilidad = Depends(get_servicio_lectura),
):
    return servicio.obtener_config()


@router.put("/rentabilidad/configuracion", response_model=ConfiguracionCostosOut)
def guardar_configuracion(
    body: ConfiguracionCostosUpdate,
    servicio: ServicioRentabilidad = Depends(get_servicio_config),
):
    return servicio.guardar_config(body)


@router.post("/rentabilidad/simulador", response_model=ResultadoRentabilidadOut)
def simular(
    body: SimulacionFlete,
    servicio: ServicioRentabilidad = Depends(get_servicio_lectura),
):
    return servicio.simular(body)


@router.get(
    "/expediente/viajes/{viaje_id}/rentabilidad",
    response_model=RentabilidadViajeOut,
)
def rentabilidad_viaje(
    viaje_id: UUID,
    servicio: ServicioRentabilidad = Depends(get_servicio_lectura),
):
    return servicio.rentabilidad_viaje(viaje_id)
