from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, col, select

from app.api.deps import get_current_user, require_roles
from app.core.database import get_session
from app.core.settings_db import get_config_decimal
from app.models import (
    Cliente,
    EstadoFactura,
    EstadoViaje,
    Factura,
    FacturaViaje,
    RolUsuario,
    TipoFactura,
    Viaje,
)
from app.schemas.facturas import (
    FacturaCreate,
    FacturaEstadoUpdate,
    FacturaRead,
    FacturaUpdate,
    ViajeFacturadoResumen,
)

router = APIRouter(tags=["facturas"])

lectura = Depends(get_current_user)
escritura = Depends(require_roles(RolUsuario.admin, RolUsuario.operacion, RolUsuario.contabilidad))


def _tasa_iva(session: Session) -> Decimal:
    return get_config_decimal(session, "iva_porcentaje", "19")


def _iva_de(session: Session, neto: Decimal, tipo: TipoFactura) -> Decimal:
    if tipo == TipoFactura.exenta:
        return Decimal("0")
    return (neto * _tasa_iva(session) / Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _viajes_de_factura(session: Session, factura_id: UUID) -> list[ViajeFacturadoResumen]:
    filas = session.exec(
        select(FacturaViaje, Viaje)
        .join(Viaje, Viaje.id == FacturaViaje.viaje_id)
        .where(FacturaViaje.factura_id == factura_id)
    ).all()
    return [
        ViajeFacturadoResumen(
            id=str(v.id),
            origen=v.origen,
            destino=v.destino,
            valor_flete_neto=v.valor_flete_neto,
        )
        for _, v in filas
    ]


def _to_read(session: Session, factura: Factura) -> FacturaRead:
    cliente = session.get(Cliente, factura.cliente_id)
    return FacturaRead(
        **factura.model_dump(mode="json"),
        cliente_nombre=cliente.razon_social if cliente else "-",
        viajes=_viajes_de_factura(session, factura.id),
    )


@router.get("/facturas", response_model=list[FacturaRead])
def listar_facturas(
    estado: EstadoFactura | None = Query(default=None),
    cliente_id: UUID | None = Query(default=None),
    session: Session = Depends(get_session),
    _=lectura,
):
    stmt = select(Factura)
    if estado is not None:
        stmt = stmt.where(Factura.estado == estado)
    if cliente_id is not None:
        stmt = stmt.where(Factura.cliente_id == cliente_id)
    facturas = session.exec(stmt.order_by(col(Factura.fecha_emision).desc())).all()
    return [_to_read(session, f) for f in facturas]


@router.get("/facturas/{factura_id}", response_model=FacturaRead)
def obtener_factura(
    factura_id: UUID,
    session: Session = Depends(get_session),
    _=lectura,
):
    factura = session.get(Factura, factura_id)
    if not factura:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Factura no encontrada")
    return _to_read(session, factura)


@router.post("/facturas", response_model=FacturaRead, status_code=status.HTTP_201_CREATED)
def crear_factura(
    body: FacturaCreate,
    session: Session = Depends(get_session),
    _=escritura,
):
    cliente = session.get(Cliente, UUID(body.cliente_id))
    if not cliente or not cliente.activo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cliente no válido")

    if not body.viaje_ids:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Debe seleccionar al menos un viaje para facturar"
        )

    viajes: list[Viaje] = []
    neto = Decimal("0")
    for vid in body.viaje_ids:
        viaje = session.get(Viaje, UUID(vid))
        if not viaje:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Viaje {vid} no encontrado")
        if viaje.cliente_id != cliente.id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Todos los viajes deben pertenecer al mismo cliente",
            )
        if viaje.estado != EstadoViaje.finalizado:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"El viaje {viaje.origen}→{viaje.destino} no está finalizado",
            )
        ya_facturado = session.exec(
            select(FacturaViaje).where(FacturaViaje.viaje_id == viaje.id)
        ).first()
        if ya_facturado:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"El viaje {viaje.origen}→{viaje.destino} ya está asociado a otra factura",
            )
        viajes.append(viaje)
        neto += viaje.valor_flete_neto

    iva = _iva_de(session, neto, body.tipo)
    fecha_emision = body.fecha_emision or date.today()
    fecha_vencimiento = body.fecha_vencimiento or (
        fecha_emision + __import__("datetime").timedelta(days=cliente.dias_pago)
    )

    factura = Factura(
        numero_sii=body.numero_sii.strip(),
        cliente_id=cliente.id,
        tipo=body.tipo,
        monto_neto=neto,
        iva=iva,
        total=neto + iva,
        fecha_emision=fecha_emision,
        fecha_vencimiento=fecha_vencimiento,
        estado=EstadoFactura.pendiente,
        notas=body.notas,
    )
    session.add(factura)
    session.flush()

    for viaje in viajes:
        session.add(FacturaViaje(factura_id=factura.id, viaje_id=viaje.id))
        viaje.estado = EstadoViaje.facturado
        session.add(viaje)

    session.commit()
    session.refresh(factura)
    return _to_read(session, factura)


@router.put("/facturas/{factura_id}", response_model=FacturaRead)
def actualizar_factura(
    factura_id: UUID,
    body: FacturaUpdate,
    session: Session = Depends(get_session),
    _=escritura,
):
    factura = session.get(Factura, factura_id)
    if not factura:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Factura no encontrada")
    if factura.estado != EstadoFactura.pendiente:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Solo se pueden editar facturas pendientes"
        )

    datos = body.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(factura, campo, valor)
    if "tipo" in datos:
        factura.iva = _iva_de(session, factura.monto_neto, factura.tipo)
        factura.total = factura.monto_neto + factura.iva
    session.add(factura)
    session.commit()
    session.refresh(factura)
    return _to_read(session, factura)


@router.patch("/facturas/{factura_id}/estado", response_model=FacturaRead)
def cambiar_estado_factura(
    factura_id: UUID,
    body: FacturaEstadoUpdate,
    session: Session = Depends(get_session),
    _=escritura,
):
    factura = session.get(Factura, factura_id)
    if not factura:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Factura no encontrada")

    if body.estado == EstadoFactura.pagada and factura.estado == EstadoFactura.pendiente:
        factura.estado = EstadoFactura.pagada
        factura.fecha_pago = date.today()
    elif body.estado == EstadoFactura.pendiente and factura.estado == EstadoFactura.pagada:
        factura.estado = EstadoFactura.pendiente
        factura.fecha_pago = None
    elif body.estado == EstadoFactura.anulada and factura.estado == EstadoFactura.pendiente:
        factura.estado = EstadoFactura.anulada
        filas = session.exec(
            select(FacturaViaje).where(FacturaViaje.factura_id == factura.id)
        ).all()
        for fila in filas:
            viaje = session.get(Viaje, fila.viaje_id)
            if viaje:
                viaje.estado = EstadoViaje.finalizado
                session.add(viaje)
            session.delete(fila)
    else:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Transición no permitida: {factura.estado.value} → {body.estado.value}",
        )

    session.add(factura)
    session.commit()
    session.refresh(factura)
    return _to_read(session, factura)


@router.delete("/facturas/{factura_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_factura(
    factura_id: UUID,
    session: Session = Depends(get_session),
    _=escritura,
):
    factura = session.get(Factura, factura_id)
    if not factura:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Factura no encontrada")
    if factura.estado != EstadoFactura.pendiente:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Solo se pueden eliminar facturas pendientes"
        )
    asociados = session.exec(
        select(FacturaViaje).where(FacturaViaje.factura_id == factura.id)
    ).all()
    if asociados:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "La factura tiene viajes asociados; anúlela para desasociarlos",
        )
    session.delete(factura)
    session.commit()
