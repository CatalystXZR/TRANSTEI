"""API de export CSV de solo lectura del núcleo (Ola B).

Cada endpoint declara el permiso del módulo que expone:

- `liquidaciones:leer` (nómina: dato laboral sensible);
- `operacion:leer` (viajes);
- `facturacion:leer` (facturas).

No se porta el import CSV del legacy. No se recalcula ningún monto: se exporta
lo almacenado (evita el defecto CN-09 del export legacy).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.database import get_session_nucleo
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.permisos import requiere_permiso
from app.nucleo.servicio_export import ServicioExport

router = APIRouter(prefix="/export", tags=["nucleo-export"])


@router.get("/liquidaciones")
def exportar_liquidaciones(
    mes: str | None = Query(default=None),
    session: Session = Depends(get_session_nucleo),
    contexto: ContextoEmpresa = Depends(requiere_permiso("liquidaciones:leer")),
):
    return ServicioExport(session, contexto).liquidaciones(mes=mes)


@router.get("/viajes")
def exportar_viajes(
    desde: date | None = Query(default=None),
    hasta: date | None = Query(default=None),
    session: Session = Depends(get_session_nucleo),
    contexto: ContextoEmpresa = Depends(requiere_permiso("operacion:leer")),
):
    return ServicioExport(session, contexto).viajes(desde=desde, hasta=hasta)


@router.get("/facturas")
def exportar_facturas(
    session: Session = Depends(get_session_nucleo),
    contexto: ContextoEmpresa = Depends(requiere_permiso("facturacion:leer")),
):
    return ServicioExport(session, contexto).facturas()
