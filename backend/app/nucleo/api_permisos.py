"""API de roles, permisos y auditoría visible (P0-12)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.database import get_session
from app.nucleo.deps import ContextoEmpresa, get_contexto_empresa
from app.nucleo.models import RolEmpresa
from app.nucleo.permisos import ROLES_PERMISOS, permisos_de, requiere_permiso
from app.nucleo.schemas import (
    MatrizPermisosOut,
    MisPermisosOut,
    PaginaAuditoriaOut,
    PermisoRolOut,
    TablaAuditoriaOut,
)
from app.nucleo.servicio_auditoria import ServicioAuditoria

router = APIRouter(prefix="/nucleo", tags=["nucleo-permisos"])


@router.get("/permisos/mios", response_model=MisPermisosOut)
def mis_permisos(
    contexto: ContextoEmpresa = Depends(get_contexto_empresa),
):
    return MisPermisosOut(
        rol=contexto.rol,
        permisos=sorted(permisos_de(contexto.rol)),
        empresa_id=contexto.empresa.id,
    )


@router.get("/permisos/matriz", response_model=MatrizPermisosOut)
def matriz_permisos(
    contexto: ContextoEmpresa = Depends(requiere_permiso("roles:leer")),
):
    return MatrizPermisosOut(
        roles=[
            PermisoRolOut(rol=rol, permisos=sorted(permisos_de(rol)))
            for rol in RolEmpresa
        ],
        permisos=sorted({p for permisos in ROLES_PERMISOS.values() for p in permisos}),
    )


@router.get("/permisos/verificar")
def verificar_permiso(
    permiso: str = Query(..., max_length=80),
    contexto: ContextoEmpresa = Depends(get_contexto_empresa),
):
    return {
        "rol": contexto.rol.value,
        "permiso": permiso,
        "permitido": permiso in permisos_de(contexto.rol),
    }


# ---------------------------------------------------------------------------
# Auditoría
# ---------------------------------------------------------------------------
def get_servicio_auditoria(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("auditoria:leer")),
) -> ServicioAuditoria:
    return ServicioAuditoria(session, contexto)


@router.get("/auditoria", response_model=PaginaAuditoriaOut)
def listar_auditoria(
    tabla: str | None = Query(default=None, max_length=200),
    registro_id: UUID | None = Query(default=None),
    operacion: str | None = Query(default=None),
    auth_id: str | None = Query(default=None, max_length=200),
    desde: datetime | None = Query(default=None),
    hasta: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    servicio: ServicioAuditoria = Depends(get_servicio_auditoria),
):
    return servicio.listar(
        tabla=tabla,
        registro_id=registro_id,
        operacion=operacion,
        auth_id=auth_id,
        desde=desde,
        hasta=hasta,
        limit=limit,
        offset=offset,
    )


@router.get("/auditoria/tablas", response_model=list[TablaAuditoriaOut])
def tablas_auditoria(
    servicio: ServicioAuditoria = Depends(get_servicio_auditoria),
):
    return servicio.tablas()
