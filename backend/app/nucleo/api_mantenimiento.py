"""API de mantenimiento preventivo del núcleo (Ola B, 0024).

Rutas bajo `/api/v1/nucleo/mantenimiento`. El tenant sale de `X-Empresa-ID`
resuelto por `get_contexto_empresa`; nunca del body.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.core.database import get_session_nucleo
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.models import TipoRecurso
from app.nucleo.permisos import requiere_permiso
from app.nucleo.schemas import (
    EstadoMantenimientoOut,
    MantenimientoCreate,
    MantenimientoOut,
    MotivoAnulacion,
    PautaMantenimientoCreate,
    PautaMantenimientoOut,
)
from app.nucleo.servicio_mantenimiento import ServicioMantenimiento

router = APIRouter(prefix="/mantenimiento", tags=["nucleo-mantenimiento"])


def get_servicio_lectura(
    session: Session = Depends(get_session_nucleo),
    contexto: ContextoEmpresa = Depends(requiere_permiso("mantenimiento:leer")),
) -> ServicioMantenimiento:
    return ServicioMantenimiento(session, contexto)


def get_servicio_escritura(
    session: Session = Depends(get_session_nucleo),
    contexto: ContextoEmpresa = Depends(requiere_permiso("mantenimiento:escribir")),
) -> ServicioMantenimiento:
    return ServicioMantenimiento(session, contexto)


@router.get("/pautas", response_model=list[PautaMantenimientoOut])
def listar_pautas(
    recurso_tipo: TipoRecurso | None = Query(default=None),
    incluir_inactivas: bool = Query(default=False),
    servicio: ServicioMantenimiento = Depends(get_servicio_lectura),
):
    return servicio.listar_pautas(
        recurso_tipo=recurso_tipo, incluir_inactivas=incluir_inactivas
    )


@router.post(
    "/pautas",
    response_model=PautaMantenimientoOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_pauta(
    body: PautaMantenimientoCreate,
    servicio: ServicioMantenimiento = Depends(get_servicio_escritura),
):
    return servicio.crear_pauta(body)


@router.get("/mantenimientos", response_model=list[MantenimientoOut])
def listar_mantenimientos(
    recurso_tipo: TipoRecurso | None = Query(default=None),
    recurso_id: UUID | None = Query(default=None),
    pauta_id: UUID | None = Query(default=None),
    estado: str | None = Query(default=None),
    desde: date | None = Query(default=None),
    hasta: date | None = Query(default=None),
    servicio: ServicioMantenimiento = Depends(get_servicio_lectura),
):
    return servicio.listar_mantenimientos(
        recurso_tipo=recurso_tipo,
        recurso_id=recurso_id,
        pauta_id=pauta_id,
        estado=estado,
        desde=desde,
        hasta=hasta,
    )


@router.post(
    "/mantenimientos",
    response_model=MantenimientoOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_mantenimiento(
    body: MantenimientoCreate,
    servicio: ServicioMantenimiento = Depends(get_servicio_escritura),
):
    return servicio.crear_mantenimiento(body)


@router.post(
    "/mantenimientos/{mantenimiento_id}/anular",
    response_model=MantenimientoOut,
)
def anular_mantenimiento(
    mantenimiento_id: UUID,
    body: MotivoAnulacion,
    servicio: ServicioMantenimiento = Depends(get_servicio_escritura),
):
    """Reemplaza el `DELETE` del legacy: el histórico se conserva."""
    return servicio.anular_mantenimiento(mantenimiento_id, body.motivo)


@router.get("/estado", response_model=list[EstadoMantenimientoOut])
def estado_mantenimiento(
    recurso_tipo: TipoRecurso | None = Query(default=None),
    recurso_id: UUID | None = Query(default=None),
    estado: str | None = Query(default=None),
    servicio: ServicioMantenimiento = Depends(get_servicio_lectura),
):
    return servicio.estado(
        recurso_tipo=recurso_tipo, recurso_id=recurso_id, estado=estado
    )
