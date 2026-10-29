"""API de gastos, combustible y costos reales (P0-08)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlmodel import Session

from app.core.database import get_session
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.permisos import requiere_permiso
from app.nucleo.schemas import (
    AprobarGasto,
    CostosViajeOut,
    GastoCreate,
    GastoOut,
    PrecioDieselCreate,
    PrecioDieselOut,
    RechazarGasto,
)
from app.nucleo.servicio_gastos import ServicioGastos

router = APIRouter(prefix="/nucleo", tags=["nucleo-gastos"])

def get_servicio_lectura(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("gastos:leer")),
) -> ServicioGastos:
    return ServicioGastos(session, contexto)


def get_servicio_escritura(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("gastos:escribir")),
) -> ServicioGastos:
    return ServicioGastos(session, contexto)


def get_servicio_aprobacion(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("gastos:aprobar")),
) -> ServicioGastos:
    return ServicioGastos(session, contexto)


@router.get("/combustible/precios", response_model=list[PrecioDieselOut])
def listar_precios(
    servicio: ServicioGastos = Depends(get_servicio_lectura),
):
    return servicio.listar_precios()


@router.get("/combustible/precio-vigente", response_model=PrecioDieselOut | None)
def precio_vigente(
    fecha: date | None = Query(default=None),
    servicio: ServicioGastos = Depends(get_servicio_lectura),
):
    return servicio.precio_vigente(fecha)


@router.post(
    "/combustible/precios",
    response_model=PrecioDieselOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_precio(
    body: PrecioDieselCreate,
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("comercial:escribir")),
):
    return ServicioGastos(session, contexto).crear_precio(body)


@router.get(
    "/expediente/viajes/{viaje_id}/gastos", response_model=list[GastoOut]
)
def listar_gastos(
    viaje_id: UUID,
    estado: str | None = Query(default=None),
    incluir_inactivos: bool = Query(default=False),
    servicio: ServicioGastos = Depends(get_servicio_lectura),
):
    return servicio.listar_gastos(
        viaje_id, estado=estado, incluir_inactivos=incluir_inactivos
    )


@router.post(
    "/expediente/viajes/{viaje_id}/gastos",
    response_model=GastoOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_gasto(
    viaje_id: UUID,
    body: GastoCreate,
    servicio: ServicioGastos = Depends(get_servicio_escritura),
):
    return servicio.crear_gasto(viaje_id, body)


@router.post(
    "/expediente/gastos/{gasto_id}/comprobante", response_model=GastoOut
)
async def adjuntar_comprobante(
    gasto_id: UUID,
    archivo: UploadFile = File(...),
    servicio: ServicioGastos = Depends(get_servicio_escritura),
):
    contenido = await archivo.read()
    return servicio.adjuntar_comprobante(
        gasto_id,
        nombre_archivo=archivo.filename or "comprobante",
        contenido=contenido,
        content_type=archivo.content_type,
    )


@router.post("/expediente/gastos/{gasto_id}/aprobar", response_model=GastoOut)
def aprobar_gasto(
    gasto_id: UUID,
    body: AprobarGasto,
    servicio: ServicioGastos = Depends(get_servicio_aprobacion),
):
    return servicio.aprobar_gasto(gasto_id, body)


@router.post("/expediente/gastos/{gasto_id}/rechazar", response_model=GastoOut)
def rechazar_gasto(
    gasto_id: UUID,
    body: RechazarGasto,
    servicio: ServicioGastos = Depends(get_servicio_aprobacion),
):
    return servicio.rechazar_gasto(gasto_id, body)


@router.get(
    "/expediente/viajes/{viaje_id}/costos", response_model=CostosViajeOut
)
def costos_viaje(
    viaje_id: UUID,
    servicio: ServicioGastos = Depends(get_servicio_lectura),
):
    return servicio.costos(viaje_id)
