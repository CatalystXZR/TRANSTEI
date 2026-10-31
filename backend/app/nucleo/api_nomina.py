"""API de nómina del núcleo: liquidaciones, anticipos y ajustes (Ola B, 0025).

Todas las rutas bajo `/api/v1/nucleo`. La nómina es dato laboral sensible: la
lectura y la escritura comparten el permiso explícito y no se concede a
`tesorería`, `taller`, `conductor` ni `auditor` (mismo criterio que SEC-008 en el
legacy, que restringió la lectura a admin/contabilidad).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.core.database import get_session_nucleo
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.permisos import requiere_permiso
from app.nucleo.schemas import (
    AjusteCreate,
    AjusteOut,
    AnticipoCreate,
    AnticipoOut,
    AnularLiquidacion,
    LiquidacionCreate,
    LiquidacionOut,
)
from app.nucleo.servicio_nomina import ServicioNomina

router = APIRouter(tags=["nucleo-nomina"])


def get_servicio_lectura(
    session: Session = Depends(get_session_nucleo),
    contexto: ContextoEmpresa = Depends(requiere_permiso("liquidaciones:leer")),
) -> ServicioNomina:
    return ServicioNomina(session, contexto)


def get_servicio_escritura(
    session: Session = Depends(get_session_nucleo),
    contexto: ContextoEmpresa = Depends(requiere_permiso("liquidaciones:escribir")),
) -> ServicioNomina:
    return ServicioNomina(session, contexto)


# ---------------------------------------------------------------- liquidaciones
@router.get("/liquidaciones", response_model=list[LiquidacionOut])
def listar_liquidaciones(
    mes: str | None = Query(default=None),
    chofer_id: UUID | None = Query(default=None),
    estado: str | None = Query(default=None),
    servicio: ServicioNomina = Depends(get_servicio_lectura),
):
    return servicio.listar_liquidaciones(mes=mes, chofer_id=chofer_id, estado=estado)


@router.post(
    "/liquidaciones",
    response_model=LiquidacionOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_liquidacion(
    body: LiquidacionCreate,
    servicio: ServicioNomina = Depends(get_servicio_escritura),
):
    """Crea el borrador con la comisión calculada desde `nucleo.viajes`."""
    return servicio.crear_liquidacion(body)


@router.post("/liquidaciones/{liquidacion_id}/emitir", response_model=LiquidacionOut)
def emitir_liquidacion(
    liquidacion_id: UUID,
    servicio: ServicioNomina = Depends(get_servicio_escritura),
):
    """Snapshot inmutable e imputación de anticipos/ajustes del período."""
    return servicio.emitir(liquidacion_id)


@router.post("/liquidaciones/{liquidacion_id}/anular", response_model=LiquidacionOut)
def anular_liquidacion(
    liquidacion_id: UUID,
    body: AnularLiquidacion,
    servicio: ServicioNomina = Depends(get_servicio_escritura),
):
    return servicio.anular(liquidacion_id, body.motivo)


# -------------------------------------------------------------------- anticipos
@router.get("/anticipos", response_model=list[AnticipoOut])
def listar_anticipos(
    chofer_id: UUID | None = Query(default=None),
    mes: str | None = Query(default=None),
    estado: str | None = Query(default=None),
    servicio: ServicioNomina = Depends(get_servicio_lectura),
):
    return servicio.listar_anticipos(chofer_id=chofer_id, mes=mes, estado=estado)


@router.post(
    "/anticipos",
    response_model=AnticipoOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_anticipo(
    body: AnticipoCreate,
    servicio: ServicioNomina = Depends(get_servicio_escritura),
):
    return servicio.crear_anticipo(body)


# ---------------------------------------------------------------------- ajustes
@router.get("/ajustes", response_model=list[AjusteOut])
def listar_ajustes(
    chofer_id: UUID | None = Query(default=None),
    mes: str | None = Query(default=None),
    estado: str | None = Query(default=None),
    servicio: ServicioNomina = Depends(get_servicio_lectura),
):
    return servicio.listar_ajustes(chofer_id=chofer_id, mes=mes, estado=estado)


@router.post(
    "/ajustes",
    response_model=AjusteOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_ajuste(
    body: AjusteCreate,
    servicio: ServicioNomina = Depends(get_servicio_escritura),
):
    return servicio.crear_ajuste(body)
