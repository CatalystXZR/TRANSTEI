from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.core.database import get_session
from app.models import (
    Chofer,
    Cliente,
    EstadoFactura,
    EstadoViaje,
    Factura,
    GastoViaje,
    Rampla,
    Tracto,
    Viaje,
)
from app.schemas.viajes import ViajeRead

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

lectura = Depends(get_current_user)


def _get_config(session: Session, clave: str, default: str) -> str:
    from app.models import Configuracion

    fila = session.get(Configuracion, clave)
    return fila.valor if fila else default


def _viajes_read(session: Session, viajes: list[Viaje]) -> list[ViajeRead]:
    from app.api.routes.viajes import _to_read

    return [_to_read(session, v) for v in viajes]


@router.get("/resumen")
def resumen(
    mes: str | None = Query(default=None),
    session: Session = Depends(get_session),
    _=lectura,
):
    hoy = date.today()
    if mes:
        anio, m = map(int, mes.split("-"))
        inicio_mes = date(anio, m, 1)
        fin_mes = date(anio + 1, 1, 1) if m == 12 else date(anio, m + 1, 1)
    else:
        inicio_mes = date(hoy.year, hoy.month, 1)
        fin_mes = date(hoy.year + 1, 1, 1) if hoy.month == 12 else date(hoy.year, hoy.month + 1, 1)

    ingresos = session.exec(
        select(func.coalesce(func.sum(Viaje.valor_flete_neto), 0)).where(
            Viaje.estado.in_([EstadoViaje.finalizado, EstadoViaje.facturado]),
            func.coalesce(Viaje.fecha_fin, Viaje.fecha_inicio) >= inicio_mes,
            func.coalesce(Viaje.fecha_fin, Viaje.fecha_inicio) < fin_mes,
        )
    ).one()

    por_cobrar = session.exec(
        select(func.coalesce(func.sum(Factura.total), 0)).where(
            Factura.estado == EstadoFactura.pendiente
        )
    ).one()

    atrasadas = session.exec(
        select(func.coalesce(func.sum(Factura.total), 0)).where(
            Factura.estado == EstadoFactura.pendiente,
            Factura.fecha_vencimiento < hoy,
        )
    ).one()

    gastos_mes = session.exec(
        select(func.coalesce(func.sum(GastoViaje.monto), 0)).where(
            GastoViaje.fecha >= inicio_mes, GastoViaje.fecha < fin_mes
        )
    ).one()

    viajes_activos = session.exec(
        select(Viaje)
        .where(Viaje.estado.in_([EstadoViaje.programado, EstadoViaje.en_ruta]))
        .order_by(Viaje.fecha_inicio)
    ).all()

    return {
        "mes": f"{inicio_mes.year:04d}-{inicio_mes.month:02d}",
        "ingresos_mes": Decimal(ingresos),
        "cuentas_por_cobrar": Decimal(por_cobrar),
        "cuentas_atrasadas": Decimal(atrasadas),
        "gastos_mes": Decimal(gastos_mes),
        "viajes_activos": _viajes_read(session, viajes_activos),
    }


@router.get("/alertas")
def alertas(
    session: Session = Depends(get_session),
    _=lectura,
):
    hoy = date.today()
    dias_alerta = int(_get_config(session, "dias_alerta_vencimientos", "30"))
    limite = hoy + timedelta(days=dias_alerta)

    vencimientos: list[dict] = []

    for tracto in session.exec(select(Tracto).where(Tracto.activo == True)).all():
        for campo, etiqueta in (
            ("vencimiento_revision_tecnica", "Rev. Técnica"),
            ("vencimiento_seguro", "Seguro"),
        ):
            fecha = getattr(tracto, campo)
            if fecha and fecha <= limite:
                vencimientos.append(
                    {
                        "tipo": "tracto",
                        "equipo": tracto.patente,
                        "concepto": etiqueta,
                        "fecha": fecha.isoformat(),
                        "dias_restantes": (fecha - hoy).days,
                    }
                )

    for rampla in session.exec(select(Rampla).where(Rampla.activo == True)).all():
        if rampla.vencimiento_revision_tecnica and rampla.vencimiento_revision_tecnica <= limite:
            vencimientos.append(
                {
                    "tipo": "rampla",
                    "equipo": rampla.patente,
                    "concepto": "Rev. Técnica",
                    "fecha": rampla.vencimiento_revision_tecnica.isoformat(),
                    "dias_restantes": (rampla.vencimiento_revision_tecnica - hoy).days,
                }
            )

    for chofer in session.exec(select(Chofer).where(Chofer.activo == True)).all():
        if chofer.vencimiento_licencia and chofer.vencimiento_licencia <= limite:
            vencimientos.append(
                {
                    "tipo": "chofer",
                    "equipo": chofer.nombre,
                    "concepto": "Licencia",
                    "fecha": chofer.vencimiento_licencia.isoformat(),
                    "dias_restantes": (chofer.vencimiento_licencia - hoy).days,
                }
            )

    vencimientos.sort(key=lambda v: v["dias_restantes"])

    facturas_vencidas = session.exec(
        select(Factura).where(
            Factura.estado == EstadoFactura.pendiente,
            Factura.fecha_vencimiento < hoy,
        )
    ).all()
    facturas_vencidas_out = []
    for f in facturas_vencidas:
        cliente = session.get(Cliente, f.cliente_id)
        facturas_vencidas_out.append(
            {
                "id": str(f.id),
                "numero_sii": f.numero_sii,
                "cliente": cliente.razon_social if cliente else "-",
                "total": f.total,
                "fecha_vencimiento": f.fecha_vencimiento.isoformat()
                if f.fecha_vencimiento
                else None,
                "dias_atraso": (hoy - f.fecha_vencimiento).days if f.fecha_vencimiento else None,
            }
        )

    return {
        "vencimientos": vencimientos,
        "facturas_vencidas": facturas_vencidas_out,
    }
