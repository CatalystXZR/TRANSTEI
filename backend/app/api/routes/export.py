import csv
import io
import re
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.api.deps import get_current_user, require_roles
from app.core.database import get_session
from app.models import (
    Chofer,
    Cliente,
    EstadoLiquidacion,
    Factura,
    RolUsuario,
    Viaje,
)

router = APIRouter(prefix="/export", tags=["export"])

lectura = Depends(get_current_user)
escritura = Depends(require_roles(RolUsuario.admin, RolUsuario.operacion))


def _respuesta_csv(nombre: str, filas: list[dict]) -> StreamingResponse:
    buffer = io.StringIO()
    if filas:
        writer = csv.DictWriter(
            buffer,
            fieldnames=list(filas[0].keys()),
            delimiter=";",
            quoting=csv.QUOTE_MINIMAL,
        )
        writer.writeheader()
        for fila in filas:
            writer.writerow({k: (v if v is not None else "") for k, v in fila.items()})
    contenido = "\ufeff" + buffer.getvalue()  # BOM para Excel
    return StreamingResponse(
        iter([contenido.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/viajes")
def exportar_viajes(
    desde: date | None = Query(default=None),
    hasta: date | None = Query(default=None),
    session: Session = Depends(get_session),
    _=lectura,
):
    stmt = select(Viaje)
    if desde:
        stmt = stmt.where(Viaje.fecha_inicio >= desde)
    if hasta:
        stmt = stmt.where(Viaje.fecha_inicio <= hasta)
    viajes = session.exec(stmt.order_by(Viaje.fecha_inicio)).all()

    filas = []
    for v in viajes:
        cliente = session.get(Cliente, v.cliente_id)
        chofer = session.get(Chofer, v.chofer_id)
        filas.append(
            {
                "fecha_inicio": v.fecha_inicio.isoformat(),
                "fecha_fin": v.fecha_fin.isoformat() if v.fecha_fin else "",
                "origen": v.origen,
                "destino": v.destino,
                "estado": v.estado.value,
                "valor_flete_neto": f"{v.valor_flete_neto:.2f}".replace(".", ","),
                "cliente": cliente.razon_social if cliente else "",
                "chofer": chofer.nombre if chofer else "",
            }
        )
    return _respuesta_csv("viajes.csv", filas)


@router.get("/facturas")
def exportar_facturas(
    session: Session = Depends(get_session),
    _=lectura,
):
    facturas = session.exec(select(Factura).order_by(Factura.fecha_emision)).all()
    filas = []
    for f in facturas:
        cliente = session.get(Cliente, f.cliente_id)
        filas.append(
            {
                "numero_sii": f.numero_sii,
                "cliente": cliente.razon_social if cliente else "",
                "tipo": f.tipo.value,
                "monto_neto": f"{f.monto_neto:.2f}".replace(".", ","),
                "iva": f"{f.iva:.2f}".replace(".", ","),
                "total": f"{f.total:.2f}".replace(".", ","),
                "fecha_emision": f.fecha_emision.isoformat(),
                "fecha_vencimiento": f.fecha_vencimiento.isoformat() if f.fecha_vencimiento else "",
                "fecha_pago": f.fecha_pago.isoformat() if f.fecha_pago else "",
                "estado": f.estado.value,
            }
        )
    return _respuesta_csv("facturas.csv", filas)


@router.get("/liquidaciones")
def exportar_liquidaciones(
    mes: str = Query(...),
    session: Session = Depends(get_session),
    _=lectura,
):
    from app.api.routes.liquidaciones import _comision_chofer, _validar_mes

    _validar_mes(mes)
    from sqlalchemy import func

    from app.models import AjusteLiquidacion, AnticipoChofer, Liquidacion, TipoAjuste

    filas = []
    for chofer in session.exec(select(Chofer).where(Chofer.activo == True)).all():  # noqa: E712
        comision, _ = _comision_chofer(session, chofer.id, mes)
        anticipos = Decimal(
            session.exec(
                select(func.coalesce(func.sum(AnticipoChofer.monto), 0)).where(
                    AnticipoChofer.chofer_id == chofer.id,
                    AnticipoChofer.mes_liquidacion == mes,
                )
            ).one()
        )
        bonos = Decimal(
            session.exec(
                select(func.coalesce(func.sum(AjusteLiquidacion.monto), 0)).where(
                    AjusteLiquidacion.chofer_id == chofer.id,
                    AjusteLiquidacion.mes == mes,
                    AjusteLiquidacion.tipo == TipoAjuste.bono,
                )
            ).one()
        )
        descuentos = Decimal(
            session.exec(
                select(func.coalesce(func.sum(AjusteLiquidacion.monto), 0)).where(
                    AjusteLiquidacion.chofer_id == chofer.id,
                    AjusteLiquidacion.mes == mes,
                    AjusteLiquidacion.tipo == TipoAjuste.descuento,
                )
            ).one()
        )
        liq = session.exec(
            select(Liquidacion).where(
                Liquidacion.chofer_id == chofer.id, Liquidacion.mes == mes
            )
        ).first()
        filas.append(
            {
                "rut": chofer.rut,
                "nombre": chofer.nombre,
                "sueldo_base": f"{chofer.sueldo_base:.2f}".replace(".", ","),
                "comision": f"{comision:.2f}".replace(".", ","),
                "bonos": f"{bonos:.2f}".replace(".", ","),
                "descuentos": f"{descuentos:.2f}".replace(".", ","),
                "anticipos": f"{anticipos:.2f}".replace(".", ","),
                "total_liquido": f"{chofer.sueldo_base + comision + bonos - descuentos - anticipos:.2f}".replace(".", ","),
                "estado": liq.estado.value if liq else "",
            }
        )
    return _respuesta_csv(f"liquidaciones_{mes}.csv", filas)


# ------------------------------------------------------------
# Importación de planillas (catálogos)
# ------------------------------------------------------------
def _leer_csv(contenido: bytes) -> list[dict]:
    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            texto = contenido.decode("latin-1")
        except UnicodeDecodeError:
            raise HTTPException(400, "Codificación no reconocida; use UTF-8 o Latin-1")
    lineas = texto.splitlines()
    separador = ";" if lineas and ";" in lineas[0] else ","
    try:
        return list(csv.DictReader(io.StringIO(texto), delimiter=separador))
    except Exception:
        raise HTTPException(400, "No se pudo leer el CSV")


def _normalizar_claves(fila: dict) -> dict:
    return {k.strip().lower().replace(" ", "_"): v for k, v in fila.items() if k is not None}


@router.post("/import/clientes")
async def importar_clientes(
    archivo: UploadFile = File(...),
    session: Session = Depends(get_session),
    _=escritura,
):
    contenido = await archivo.read()
    filas = _leer_csv(contenido)
    if not filas:
        raise HTTPException(400, "El archivo está vacío")

    importados, omitidos = 0, []
    for i, fila in enumerate(filas, start=2):
        f = _normalizar_claves(fila)
        razon = (f.get("razon_social") or f.get("razon") or f.get("nombre") or "").strip()
        rut = (f.get("rut") or "").strip()
        if not razon or not rut:
            omitidos.append({"fila": i, "motivo": "Faltan columnas razon_social/rut"})
            continue
        existente = session.exec(select(Cliente).where(Cliente.rut == rut)).first()
        if existente:
            omitidos.append({"fila": i, "motivo": f"RUT {rut} ya existe"})
            continue
        session.add(
            Cliente(
                razon_social=razon,
                rut=rut,
                dias_pago=int(f.get("dias_pago") or 30),
                telefono=(f.get("telefono") or "").strip() or None,
                email=(f.get("email") or "").strip() or None,
            )
        )
        importados += 1
    session.commit()
    return {"importados": importados, "omitidos": omitidos}


@router.post("/import/choferes")
async def importar_choferes(
    archivo: UploadFile = File(...),
    session: Session = Depends(get_session),
    _=escritura,
):
    contenido = await archivo.read()
    filas = _leer_csv(contenido)
    if not filas:
        raise HTTPException(400, "El archivo está vacío")

    importados, omitidos = 0, []
    for i, fila in enumerate(filas, start=2):
        f = _normalizar_claves(fila)
        nombre = (f.get("nombre") or "").strip()
        rut = (f.get("rut") or "").strip()
        if not nombre or not rut:
            omitidos.append({"fila": i, "motivo": "Faltan columnas nombre/rut"})
            continue
        existente = session.exec(select(Chofer).where(Chofer.rut == rut)).first()
        if existente:
            omitidos.append({"fila": i, "motivo": f"RUT {rut} ya existe"})
            continue
        try:
            sueldo = Decimal(str(f.get("sueldo_base") or "0").replace(",", "."))
            porcentaje = Decimal(str(f.get("porcentaje_produccion") or "0").replace(",", "."))
            if porcentaje > 1:
                porcentaje = porcentaje / 100
        except Exception:
            omitidos.append({"fila": i, "motivo": "Sueldo o porcentaje inválido"})
            continue
        session.add(
            Chofer(
                nombre=nombre,
                rut=rut,
                sueldo_base=sueldo,
                porcentaje_produccion=porcentaje,
            )
        )
        importados += 1
    session.commit()
    return {"importados": importados, "omitidos": omitidos}
