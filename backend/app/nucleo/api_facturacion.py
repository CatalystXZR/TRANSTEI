"""API de facturación y cobranza del núcleo (P0-10)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.core.database import get_session
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.permisos import requiere_permiso
from app.nucleo.schemas import (
    AgingOut,
    FacturaCreate,
    FacturaOut,
    FacturaResumenOut,
    NotaCreditoCreate,
    PagoCreate,
    PromesaPagoCreate,
    ViajeFacturableOut,
)
from app.nucleo.servicio_facturacion import ServicioFacturacion

router = APIRouter(prefix="/nucleo/cobranza", tags=["nucleo-cobranza"])

def get_servicio_lectura(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("facturacion:leer")),
) -> ServicioFacturacion:
    return ServicioFacturacion(session, contexto)


def get_servicio_emision(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("facturacion:emitir")),
) -> ServicioFacturacion:
    return ServicioFacturacion(session, contexto)


def get_servicio_cobranza(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("cobranza:registrar")),
) -> ServicioFacturacion:
    return ServicioFacturacion(session, contexto)


@router.get("/viajes-facturables", response_model=list[ViajeFacturableOut])
def viajes_facturables(
    cliente_id: UUID | None = Query(default=None),
    orden_compra_id: UUID | None = Query(default=None),
    servicio: ServicioFacturacion = Depends(get_servicio_lectura),
):
    return servicio.viajes_facturables(
        cliente_id=cliente_id, orden_compra_id=orden_compra_id
    )


@router.get("/facturas", response_model=list[FacturaResumenOut])
def listar_facturas(
    cliente_id: UUID | None = Query(default=None),
    estado: str | None = Query(default=None),
    solo_vencidas: bool = Query(default=False),
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    servicio: ServicioFacturacion = Depends(get_servicio_lectura),
):
    return servicio.listar_facturas(
        cliente_id=cliente_id,
        estado=estado,
        solo_vencidas=solo_vencidas,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/facturas", response_model=FacturaOut, status_code=status.HTTP_201_CREATED
)
def crear_factura(
    body: FacturaCreate,
    servicio: ServicioFacturacion = Depends(get_servicio_emision),
):
    return servicio.crear_factura(body)


@router.get("/facturas/{factura_id}", response_model=FacturaOut)
def obtener_factura(
    factura_id: UUID,
    servicio: ServicioFacturacion = Depends(get_servicio_lectura),
):
    return servicio.obtener_factura(factura_id)


@router.post("/facturas/{factura_id}/pagos", response_model=FacturaOut)
def registrar_pago(
    factura_id: UUID,
    body: PagoCreate,
    servicio: ServicioFacturacion = Depends(get_servicio_cobranza),
):
    return servicio.registrar_pago(factura_id, body)


@router.post("/facturas/{factura_id}/notas-credito", response_model=FacturaOut)
def crear_nota_credito(
    factura_id: UUID,
    body: NotaCreditoCreate,
    servicio: ServicioFacturacion = Depends(get_servicio_cobranza),
):
    return servicio.crear_nota_credito(factura_id, body)


@router.post("/facturas/{factura_id}/promesas", response_model=FacturaOut)
def crear_promesa(
    factura_id: UUID,
    body: PromesaPagoCreate,
    servicio: ServicioFacturacion = Depends(get_servicio_cobranza),
):
    return servicio.crear_promesa(factura_id, body)


@router.get("/aging", response_model=AgingOut)
def aging(
    servicio: ServicioFacturacion = Depends(get_servicio_lectura),
):
    return servicio.aging()
