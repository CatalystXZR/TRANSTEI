from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.core.database import get_session
from app.core.settings_db import get_config
from app.models import (
    CategoriaGasto,
    Cliente,
    EstadoFactura,
    Factura,
    FacturaViaje,
    GastoViaje,
    TipoFactura,
)
from app.schemas.facturas import CobranzaItem, CobranzasResumen, IvaResumen

router = APIRouter(tags=["finanzas"])

lectura = Depends(get_current_user)


@router.get("/facturacion/fletes-por-facturar")
def fletes_por_facturar(
    session: Session = Depends(get_session),
    _=lectura,
):
    from app.api.routes.viajes import _to_read
    from app.models import EstadoViaje, Viaje

    viajes = session.exec(
        select(Viaje).where(Viaje.estado == EstadoViaje.finalizado)
    ).all()

    facturados = set(
        session.exec(select(FacturaViaje.viaje_id)).all()
    )
    pendientes = [v for v in viajes if v.id not in facturados]

    grupos: dict = {}
    for v in pendientes:
        key = str(v.cliente_id)
        if key not in grupos:
            cliente = session.get(Cliente, v.cliente_id)
            grupos[key] = {
                "cliente_id": key,
                "cliente_nombre": cliente.razon_social if cliente else "-",
                "dias_pago": cliente.dias_pago if cliente else 30,
                "viajes": [],
                "total_neto": Decimal("0"),
            }
        grupos[key]["viajes"].append(_to_read(session, v).model_dump(mode="json"))
        grupos[key]["total_neto"] += v.valor_flete_neto

    resultado = sorted(grupos.values(), key=lambda g: g["cliente_nombre"])
    for g in resultado:
        g["total_neto"] = str(g["total_neto"])
    return resultado


@router.get("/cobranzas", response_model=CobranzasResumen)
def cobranzas(
    session: Session = Depends(get_session),
    _=lectura,
):
    hoy = date.today()
    dias_alerta = int(get_config(session, "dias_alerta_cobranza", "5"))

    facturas = session.exec(
        select(Factura).where(Factura.estado == EstadoFactura.pendiente)
    ).all()

    items: list[CobranzaItem] = []
    total_vencidas = Decimal("0")
    total_por_vencer = Decimal("0")
    total_al_dia = Decimal("0")

    for f in facturas:
        cliente = session.get(Cliente, f.cliente_id)
        dias_restantes = (f.fecha_vencimiento - hoy).days if f.fecha_vencimiento else None
        if dias_restantes is not None and dias_restantes < 0:
            semaforo = "vencida"
            total_vencidas += f.total
        elif dias_restantes is not None and dias_restantes <= dias_alerta:
            semaforo = "por_vencer"
            total_por_vencer += f.total
        else:
            semaforo = "al_dia"
            total_al_dia += f.total
        items.append(
            CobranzaItem(
                id=str(f.id),
                numero_sii=f.numero_sii,
                cliente=cliente.razon_social if cliente else "-",
                total=f.total,
                fecha_emision=f.fecha_emision,
                fecha_vencimiento=f.fecha_vencimiento,
                dias_restantes=dias_restantes,
                semaforo=semaforo,
            )
        )

    items.sort(key=lambda i: i.dias_restantes if i.dias_restantes is not None else 99999)
    return CobranzasResumen(
        total_vencidas=total_vencidas,
        total_por_vencer=total_por_vencer,
        total_al_dia=total_al_dia,
        items=items,
    )


@router.get("/iva/resumen", response_model=IvaResumen)
def iva_resumen(
    mes: str = Query(default=""),
    session: Session = Depends(get_session),
    _=lectura,
):
    hoy = date.today()
    if mes:
        anio, m = map(int, mes.split("-"))
        inicio = date(anio, m, 1)
        fin = date(anio + 1, 1, 1) if m == 12 else date(anio, m + 1, 1)
    else:
        inicio = date(hoy.year, hoy.month, 1)
        fin = date(hoy.year + 1, 1, 1) if hoy.month == 12 else date(hoy.year, hoy.month + 1, 1)

    from app.core.settings_db import get_config_decimal

    tasa = get_config_decimal(session, "iva_porcentaje", "19")

    facturas = session.exec(
        select(Factura).where(
            Factura.tipo == TipoFactura.afecta,
            Factura.estado != EstadoFactura.anulada,
            Factura.fecha_emision >= inicio,
            Factura.fecha_emision < fin,
        )
    ).all()
    debito = sum((f.iva for f in facturas), Decimal("0"))

    gastos = session.exec(
        select(GastoViaje).where(
            GastoViaje.iva_recuperable == True,  # noqa: E712
            GastoViaje.fecha >= inicio,
            GastoViaje.fecha < fin,
        )
    ).all()
    factor = tasa / (Decimal(100) + tasa)
    credito = sum((g.monto * factor for g in gastos), Decimal("0"))

    facturas_out = []
    for f in facturas:
        cliente = session.get(Cliente, f.cliente_id)
        facturas_out.append(
            {
                "numero_sii": f.numero_sii,
                "cliente": cliente.razon_social if cliente else "-",
                "neto": str(f.monto_neto),
                "iva": str(f.iva),
            }
        )
    gastos_out = [
        {
            "id": str(g.id),
            "categoria": g.categoria.value if isinstance(g.categoria, CategoriaGasto) else str(g.categoria),
            "monto": str(g.monto),
            "iva_credito": str((g.monto * factor).quantize(Decimal("0.01"))),
            "fecha": g.fecha.isoformat(),
        }
        for g in gastos
    ]

    return IvaResumen(
        mes=f"{inicio.year:04d}-{inicio.month:02d}",
        tasa=tasa,
        debito=debito.quantize(Decimal("0.01")),
        credito=credito.quantize(Decimal("0.01")),
        a_pagar=max(debito - credito, Decimal("0")).quantize(Decimal("0.01")),
        facturas=facturas_out,
        gastos=gastos_out,
    )
