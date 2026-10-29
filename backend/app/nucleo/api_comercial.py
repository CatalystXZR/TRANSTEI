"""API comercial del núcleo (P0-03).

Rutas:
- Centros de costo (catálogo).
- Tarifas editables con historial.
- Órdenes de compra, líneas, consumo y aprobación de sobregiro.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.core.database import get_session
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.permisos import requiere_permiso
from app.nucleo.models import EstadoOC
from app.nucleo.schemas import (
    AprobacionSobregiro,
    CentroCostoCreate,
    CentroCostoOut,
    CentroCostoUpdate,
    HistorialCambioOut,
    OrdenCompraCreate,
    OrdenCompraLineaCreate,
    OrdenCompraLineaUpdate,
    OrdenCompraOut,
    OrdenCompraResumenOut,
    OrdenCompraUpdate,
    RechazoSobregiro,
    SolicitudSobregiro,
    TarifaCreate,
    TarifaOut,
    TarifaUpdate,
)
from app.nucleo.servicio_comercial import ServicioComercial

router = APIRouter(prefix="/nucleo", tags=["nucleo-comercial"])


def get_servicio_lectura(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("comercial:leer")),
) -> ServicioComercial:
    return ServicioComercial(session, contexto)


def get_servicio_escritura(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("comercial:escribir")),
) -> ServicioComercial:
    return ServicioComercial(session, contexto)


def get_servicio_aprobacion(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("comercial:aprobar")),
) -> ServicioComercial:
    return ServicioComercial(session, contexto)


# ---------------------------------------------------------------------------
# Centros de costo
# ---------------------------------------------------------------------------
@router.get("/centros-costo", response_model=list[CentroCostoOut])
def listar_centros_costo(
    activo: bool | None = Query(default=None),
    servicio: ServicioComercial = Depends(get_servicio_lectura),
):
    return servicio.listar_centros_costo(activo=activo)


@router.post(
    "/centros-costo",
    response_model=CentroCostoOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_centro_costo(
    body: CentroCostoCreate,
    servicio: ServicioComercial = Depends(get_servicio_escritura),
):
    return servicio.crear_centro_costo(body)


@router.put("/centros-costo/{centro_id}", response_model=CentroCostoOut)
def actualizar_centro_costo(
    centro_id: UUID,
    body: CentroCostoUpdate,
    servicio: ServicioComercial = Depends(get_servicio_escritura),
):
    return servicio.actualizar_centro_costo(centro_id, body)


@router.delete("/centros-costo/{centro_id}", response_model=CentroCostoOut)
def desactivar_centro_costo(
    centro_id: UUID,
    servicio: ServicioComercial = Depends(get_servicio_escritura),
):
    return servicio.desactivar_centro_costo(centro_id)


# ---------------------------------------------------------------------------
# Tarifas
# ---------------------------------------------------------------------------
@router.get("/tarifas", response_model=list[TarifaOut])
def listar_tarifas(
    cliente_id: UUID | None = Query(default=None),
    activo: bool | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    solo_vigentes: bool = Query(default=False),
    servicio: ServicioComercial = Depends(get_servicio_lectura),
):
    return servicio.listar_tarifas(
        cliente_id=cliente_id,
        activo=activo,
        q=q,
        solo_vigentes=solo_vigentes,
    )


@router.get("/tarifas/{tarifa_id}", response_model=TarifaOut)
def obtener_tarifa(
    tarifa_id: UUID,
    servicio: ServicioComercial = Depends(get_servicio_lectura),
):
    return servicio.obtener_tarifa(tarifa_id)


@router.get("/tarifas/{tarifa_id}/historial", response_model=list[HistorialCambioOut])
def historial_tarifa(
    tarifa_id: UUID,
    servicio: ServicioComercial = Depends(get_servicio_lectura),
):
    return servicio.historial_tarifa(tarifa_id)


@router.post("/tarifas", response_model=TarifaOut, status_code=status.HTTP_201_CREATED)
def crear_tarifa(
    body: TarifaCreate,
    servicio: ServicioComercial = Depends(get_servicio_escritura),
):
    return servicio.crear_tarifa(body)


@router.put("/tarifas/{tarifa_id}", response_model=TarifaOut)
def actualizar_tarifa(
    tarifa_id: UUID,
    body: TarifaUpdate,
    servicio: ServicioComercial = Depends(get_servicio_escritura),
):
    return servicio.actualizar_tarifa(tarifa_id, body)


@router.delete("/tarifas/{tarifa_id}", response_model=TarifaOut)
def desactivar_tarifa(
    tarifa_id: UUID,
    servicio: ServicioComercial = Depends(get_servicio_escritura),
):
    return servicio.desactivar_tarifa(tarifa_id)


# ---------------------------------------------------------------------------
# Órdenes de compra
# ---------------------------------------------------------------------------
@router.get("/ordenes-compra", response_model=list[OrdenCompraResumenOut])
def listar_ordenes_compra(
    cliente_id: UUID | None = Query(default=None),
    estado: EstadoOC | None = Query(default=None),
    solo_con_saldo: bool = Query(default=False),
    solo_alertas: bool = Query(default=False),
    q: str | None = Query(default=None, max_length=120),
    servicio: ServicioComercial = Depends(get_servicio_lectura),
):
    return servicio.listar_ocs(
        cliente_id=cliente_id,
        estado=estado,
        solo_con_saldo=solo_con_saldo,
        solo_alertas=solo_alertas,
        q=q,
    )


@router.get("/ordenes-compra/{oc_id}", response_model=OrdenCompraOut)
def obtener_orden_compra(
    oc_id: UUID,
    servicio: ServicioComercial = Depends(get_servicio_lectura),
):
    return servicio.obtener_oc(oc_id)


@router.get(
    "/ordenes-compra/{oc_id}/historial", response_model=list[HistorialCambioOut]
)
def historial_orden_compra(
    oc_id: UUID,
    servicio: ServicioComercial = Depends(get_servicio_lectura),
):
    return servicio.historial_oc(oc_id)


@router.post(
    "/ordenes-compra",
    response_model=OrdenCompraOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_orden_compra(
    body: OrdenCompraCreate,
    servicio: ServicioComercial = Depends(get_servicio_escritura),
):
    return servicio.crear_oc(body)


@router.put("/ordenes-compra/{oc_id}", response_model=OrdenCompraOut)
def actualizar_orden_compra(
    oc_id: UUID,
    body: OrdenCompraUpdate,
    servicio: ServicioComercial = Depends(get_servicio_escritura),
):
    return servicio.actualizar_oc(oc_id, body)


@router.delete("/ordenes-compra/{oc_id}", response_model=OrdenCompraOut)
def anular_orden_compra(
    oc_id: UUID,
    servicio: ServicioComercial = Depends(get_servicio_escritura),
):
    """Anula la OC; nunca se borra físicamente."""
    return servicio.anular_oc(oc_id)


@router.post(
    "/ordenes-compra/{oc_id}/lineas",
    response_model=OrdenCompraOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_linea_orden_compra(
    oc_id: UUID,
    body: OrdenCompraLineaCreate,
    servicio: ServicioComercial = Depends(get_servicio_escritura),
):
    return servicio.crear_linea_oc(oc_id, body)


@router.put(
    "/ordenes-compra/{oc_id}/lineas/{linea_id}", response_model=OrdenCompraOut
)
def actualizar_linea_orden_compra(
    oc_id: UUID,
    linea_id: UUID,
    body: OrdenCompraLineaUpdate,
    servicio: ServicioComercial = Depends(get_servicio_escritura),
):
    return servicio.actualizar_linea_oc(oc_id, linea_id, body)


@router.delete(
    "/ordenes-compra/{oc_id}/lineas/{linea_id}", response_model=OrdenCompraOut
)
def desactivar_linea_orden_compra(
    oc_id: UUID,
    linea_id: UUID,
    servicio: ServicioComercial = Depends(get_servicio_escritura),
):
    return servicio.desactivar_linea_oc(oc_id, linea_id)


# ---------------------------------------------------------------------------
# Sobregiro
# ---------------------------------------------------------------------------
@router.post(
    "/ordenes-compra/{oc_id}/sobregiro/solicitar", response_model=OrdenCompraOut
)
def solicitar_sobregiro(
    oc_id: UUID,
    body: SolicitudSobregiro,
    servicio: ServicioComercial = Depends(get_servicio_escritura),
):
    return servicio.solicitar_sobregiro(oc_id, body)


@router.post(
    "/ordenes-compra/{oc_id}/sobregiro/aprobar", response_model=OrdenCompraOut
)
def aprobar_sobregiro(
    oc_id: UUID,
    body: AprobacionSobregiro,
    servicio: ServicioComercial = Depends(get_servicio_aprobacion),
):
    return servicio.aprobar_sobregiro(oc_id, body)


@router.post(
    "/ordenes-compra/{oc_id}/sobregiro/rechazar", response_model=OrdenCompraOut
)
def rechazar_sobregiro(
    oc_id: UUID,
    body: RechazoSobregiro,
    servicio: ServicioComercial = Depends(get_servicio_aprobacion),
):
    return servicio.rechazar_sobregiro(oc_id, body)
