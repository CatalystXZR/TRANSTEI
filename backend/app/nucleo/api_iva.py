"""API de IVA y configuración por empresa del núcleo (Ola B, 0026).

`/iva/resumen` devuelve **solo débito** (ver `servicio_iva.py`). La configuración
es por empresa, con vigencia e historial; el PUT cierra la vigencia anterior e
inserta el valor nuevo en el mismo instante.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Path, Query
from sqlmodel import Session

from app.core.database import get_session_nucleo
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.permisos import requiere_permiso
from app.nucleo.schemas import (
    ConfiguracionItemOut,
    ConfiguracionOut,
    ConfiguracionUpdate,
    IvaResumenOut,
)
from app.nucleo.servicio_configuracion import ServicioConfiguracion
from app.nucleo.servicio_iva import ServicioIva

router = APIRouter(tags=["nucleo-iva-configuracion"])

PATRON_CLAVE = r"^[a-z][a-z0-9_]{2,63}$"


def get_configuracion_lectura(
    session: Session = Depends(get_session_nucleo),
    contexto: ContextoEmpresa = Depends(requiere_permiso("configuracion:leer")),
) -> ServicioConfiguracion:
    return ServicioConfiguracion(session, contexto)


def get_configuracion_escritura(
    session: Session = Depends(get_session_nucleo),
    contexto: ContextoEmpresa = Depends(requiere_permiso("configuracion:escribir")),
) -> ServicioConfiguracion:
    return ServicioConfiguracion(session, contexto)


@router.get("/iva/resumen", response_model=IvaResumenOut)
def resumen_iva(
    desde: date = Query(...),
    hasta: date = Query(...),
    session: Session = Depends(get_session_nucleo),
    contexto: ContextoEmpresa = Depends(requiere_permiso("iva:leer")),
):
    return ServicioIva(session, contexto).resumen(desde, hasta)


@router.get("/configuracion", response_model=ConfiguracionOut)
def listar_configuracion(
    servicio: ServicioConfiguracion = Depends(get_configuracion_lectura),
):
    return servicio.listar()


@router.get("/configuracion/{clave}", response_model=ConfiguracionItemOut)
def obtener_configuracion(
    clave: str = Path(pattern=PATRON_CLAVE),
    servicio: ServicioConfiguracion = Depends(get_configuracion_lectura),
):
    return servicio.obtener(clave)


@router.put("/configuracion/{clave}", response_model=ConfiguracionItemOut)
def actualizar_configuracion(
    body: ConfiguracionUpdate,
    clave: str = Path(pattern=PATRON_CLAVE),
    servicio: ServicioConfiguracion = Depends(get_configuracion_escritura),
):
    return servicio.actualizar(clave, body.valor)
