import io
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlmodel import Session, select

from app.api.deps import get_current_user, require_roles
from app.core.database import get_session
from app.models import (
    AjusteLiquidacion,
    AnticipoChofer,
    Chofer,
    EstadoLiquidacion,
    EstadoViaje,
    Liquidacion,
    RolUsuario,
    TipoAjuste,
    Viaje,
)

router = APIRouter(tags=["liquidaciones"])

lectura = Depends(get_current_user)
escritura = Depends(require_roles(RolUsuario.admin, RolUsuario.contabilidad))

MES_PATRON = __import__("re").compile(r"^\d{4}-\d{2}$")


def _validar_mes(mes: str) -> None:
    if not MES_PATRON.match(mes):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El mes debe tener formato YYYY-MM")


def _rango_mes(mes: str) -> tuple[date, date]:
    anio, m = map(int, mes.split("-"))
    inicio = date(anio, m, 1)
    fin = date(anio + 1, 1, 1) if m == 12 else date(anio, m + 1, 1)
    return inicio, fin


def _comision_chofer(session: Session, chofer_id: UUID, mes: str) -> tuple[Decimal, list[Viaje]]:
    inicio, fin = _rango_mes(mes)
    viajes = session.exec(
        select(Viaje).where(
            Viaje.chofer_id == chofer_id,
            Viaje.estado.in_([EstadoViaje.finalizado, EstadoViaje.facturado]),
            func.coalesce(Viaje.fecha_fin, Viaje.fecha_inicio) >= inicio,
            func.coalesce(Viaje.fecha_fin, Viaje.fecha_inicio) < fin,
        )
    ).all()
    chofer = session.get(Chofer, chofer_id)
    porcentaje = chofer.porcentaje_produccion if chofer else Decimal("0")
    suma = sum((v.valor_flete_neto for v in viajes), Decimal("0"))
    comision = (suma * porcentaje).quantize(Decimal("0.01"))
    return comision, viajes


# ------------------------------------------------------------
# Anticipos
# ------------------------------------------------------------
@router.get("/anticipos", response_model=list[AnticipoChofer])
def listar_anticipos(
    chofer_id: UUID | None = Query(default=None),
    mes: str | None = Query(default=None),
    session: Session = Depends(get_session),
    _=lectura,
):
    stmt = select(AnticipoChofer)
    if chofer_id is not None:
        stmt = stmt.where(AnticipoChofer.chofer_id == chofer_id)
    if mes is not None:
        stmt = stmt.where(AnticipoChofer.mes_liquidacion == mes)
    return session.exec(stmt.order_by(AnticipoChofer.fecha.desc())).all()  # type: ignore[attr-defined]


@router.post("/anticipos", response_model=AnticipoChofer, status_code=status.HTTP_201_CREATED)
def crear_anticipo(
    chofer_id: UUID,
    fecha: date | None = None,
    monto: Decimal = 0,
    mes_liquidacion: str = "",
    notas: str | None = None,
    session: Session = Depends(get_session),
    _=escritura,
):
    chofer = session.get(Chofer, chofer_id)
    if not chofer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chofer no encontrado")
    if monto <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El monto debe ser mayor a cero")
    _validar_mes(mes_liquidacion)
    anticipo = AnticipoChofer(
        chofer_id=chofer_id,
        fecha=fecha or date.today(),
        monto=monto,
        mes_liquidacion=mes_liquidacion,
        notas=notas,
    )
    session.add(anticipo)
    session.commit()
    session.refresh(anticipo)
    return anticipo


@router.delete("/anticipos/{anticipo_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_anticipo(
    anticipo_id: UUID,
    session: Session = Depends(get_session),
    _=escritura,
):
    anticipo = session.get(AnticipoChofer, anticipo_id)
    if not anticipo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anticipo no encontrado")
    session.delete(anticipo)
    session.commit()


# ------------------------------------------------------------
# Ajustes (bonos / descuentos)
# ------------------------------------------------------------
@router.get("/ajustes", response_model=list[AjusteLiquidacion])
def listar_ajustes(
    chofer_id: UUID | None = Query(default=None),
    mes: str | None = Query(default=None),
    session: Session = Depends(get_session),
    _=lectura,
):
    stmt = select(AjusteLiquidacion)
    if chofer_id is not None:
        stmt = stmt.where(AjusteLiquidacion.chofer_id == chofer_id)
    if mes is not None:
        stmt = stmt.where(AjusteLiquidacion.mes == mes)
    return session.exec(stmt.order_by(AjusteLiquidacion.created_at.desc())).all()  # type: ignore[attr-defined]


@router.post("/ajustes", response_model=AjusteLiquidacion, status_code=status.HTTP_201_CREATED)
def crear_ajuste(
    chofer_id: UUID,
    mes: str = Query(...),
    tipo: TipoAjuste = Query(...),
    concepto: str = Query(...),
    monto: Decimal = Query(...),
    session: Session = Depends(get_session),
    _=escritura,
):
    chofer = session.get(Chofer, chofer_id)
    if not chofer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chofer no encontrado")
    _validar_mes(mes)
    if monto < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El monto no puede ser negativo")
    ajuste = AjusteLiquidacion(
        chofer_id=chofer_id,
        mes=mes,
        tipo=tipo,
        concepto=concepto.strip(),
        monto=monto,
    )
    session.add(ajuste)
    session.commit()
    session.refresh(ajuste)
    return ajuste


@router.delete("/ajustes/{ajuste_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_ajuste(
    ajuste_id: UUID,
    session: Session = Depends(get_session),
    _=escritura,
):
    ajuste = session.get(AjusteLiquidacion, ajuste_id)
    if not ajuste:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ajuste no encontrado")
    session.delete(ajuste)
    session.commit()


# ------------------------------------------------------------
# Liquidaciones
# ------------------------------------------------------------
@router.get("/liquidaciones/resumen")
def resumen_liquidaciones(
    mes: str = Query(...),
    session: Session = Depends(get_session),
    _=lectura,
):
    _validar_mes(mes)
    choferes = session.exec(select(Chofer).where(Chofer.activo == True)).all()  # noqa: E712
    resultado = []
    for chofer in choferes:
        comision, _ = _comision_chofer(session, chofer.id, mes)
        anticipos = session.exec(
            select(func.coalesce(func.sum(AnticipoChofer.monto), 0)).where(
                AnticipoChofer.chofer_id == chofer.id,
                AnticipoChofer.mes_liquidacion == mes,
            )
        ).one()
        bonos = session.exec(
            select(func.coalesce(func.sum(AjusteLiquidacion.monto), 0)).where(
                AjusteLiquidacion.chofer_id == chofer.id,
                AjusteLiquidacion.mes == mes,
                AjusteLiquidacion.tipo == TipoAjuste.bono,
            )
        ).one()
        descuentos = session.exec(
            select(func.coalesce(func.sum(AjusteLiquidacion.monto), 0)).where(
                AjusteLiquidacion.chofer_id == chofer.id,
                AjusteLiquidacion.mes == mes,
                AjusteLiquidacion.tipo == TipoAjuste.descuento,
            )
        ).one()
        total = chofer.sueldo_base + comision + bonos - descuentos - anticipos
        liquidacion = session.exec(
            select(Liquidacion).where(
                Liquidacion.chofer_id == chofer.id, Liquidacion.mes == mes
            )
        ).first()
        resultado.append(
            {
                "chofer_id": str(chofer.id),
                "nombre": chofer.nombre,
                "rut": chofer.rut,
                "sueldo_base": str(chofer.sueldo_base),
                "comision": str(comision),
                "anticipos": str(anticipos),
                "bonos": str(bonos),
                "descuentos": str(descuentos),
                "total": str(total),
                "liquidacion_id": str(liquidacion.id) if liquidacion else None,
                "estado": liquidacion.estado.value if liquidacion else None,
            }
        )
    resultado.sort(key=lambda r: r["nombre"])
    return {"mes": mes, "choferes": resultado}


@router.post("/liquidaciones/calcular", response_model=Liquidacion)
def calcular_liquidacion(
    chofer_id: UUID,
    mes: str = Query(...),
    notas: str | None = Query(default=None),
    session: Session = Depends(get_session),
    _=escritura,
):
    _validar_mes(mes)
    chofer = session.get(Chofer, chofer_id)
    if not chofer or not chofer.activo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chofer no encontrado o inactivo")

    comision, _ = _comision_chofer(session, chofer_id, mes)
    anticipos = Decimal(
        session.exec(
            select(func.coalesce(func.sum(AnticipoChofer.monto), 0)).where(
                AnticipoChofer.chofer_id == chofer_id,
                AnticipoChofer.mes_liquidacion == mes,
            )
        ).one()
    )
    bonos = Decimal(
        session.exec(
            select(func.coalesce(func.sum(AjusteLiquidacion.monto), 0)).where(
                AjusteLiquidacion.chofer_id == chofer_id,
                AjusteLiquidacion.mes == mes,
                AjusteLiquidacion.tipo == TipoAjuste.bono,
            )
        ).one()
    )
    descuentos = Decimal(
        session.exec(
            select(func.coalesce(func.sum(AjusteLiquidacion.monto), 0)).where(
                AjusteLiquidacion.chofer_id == chofer_id,
                AjusteLiquidacion.mes == mes,
                AjusteLiquidacion.tipo == TipoAjuste.descuento,
            )
        ).one()
    )

    liquidacion = session.exec(
        select(Liquidacion).where(
            Liquidacion.chofer_id == chofer_id, Liquidacion.mes == mes
        )
    ).first()
    if liquidacion is None:
        liquidacion = Liquidacion(chofer_id=chofer_id, mes=mes)

    liquidacion.sueldo_base = chofer.sueldo_base
    liquidacion.comision = comision
    liquidacion.total_anticipos = anticipos
    liquidacion.total_ajustes = bonos - descuentos
    liquidacion.total_liquido = chofer.sueldo_base + comision + bonos - descuentos - anticipos
    if notas is not None:
        liquidacion.notas = notas
    session.add(liquidacion)
    session.commit()
    session.refresh(liquidacion)
    return liquidacion


@router.post("/liquidaciones/{liquidacion_id}/emitir", response_model=Liquidacion)
def emitir_liquidacion(
    liquidacion_id: UUID,
    session: Session = Depends(get_session),
    _=escritura,
):
    liquidacion = session.get(Liquidacion, liquidacion_id)
    if not liquidacion:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Liquidación no encontrada")
    liquidacion.estado = EstadoLiquidacion.emitida
    session.add(liquidacion)
    session.commit()
    session.refresh(liquidacion)
    return liquidacion


def _formato_clp(valor: Decimal) -> str:
    entero = int(valor.quantize(Decimal("1")))
    return f"{entero:,}".replace(",", ".")


def _formato_rut(rut: str) -> str:
    cuerpo = rut[:-1][::-1]
    puntos = ".".join(cuerpo[i : i + 3] for i in range(0, len(cuerpo), 3))[::-1]
    return f"{puntos}-{rut[-1]}"


def _generar_pdf(
    liquidacion: Liquidacion,
    chofer: Chofer,
    comision: Decimal,
    viajes: list[Viaje],
    bonos: Decimal,
    descuentos: Decimal,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    w, h = letter
    AZUL = colors.HexColor("#2A237A")
    AMARILLO = colors.HexColor("#FCD116")
    GRIS = colors.HexColor("#4D4D4D")

    # Encabezado corporativo
    c.setFillColor(AZUL)
    c.rect(0, h - 38 * mm, w, 38 * mm, fill=1, stroke=0)
    c.setFillColor(AMARILLO)
    c.rect(0, h - 40 * mm, w, 2 * mm, fill=1, stroke=0)

    # Logo placeholder (se reemplaza por el logo real cuando se entregue)
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.white)
    c.setLineWidth(1.5)
    c.rect(18 * mm, h - 30 * mm, 24 * mm, 18 * mm, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(30 * mm, h - 24 * mm, "TEI")
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(50 * mm, h - 17 * mm, "TRANSPORTES TEI SpA")
    c.setFont("Helvetica", 10)
    c.drawString(50 * mm, h - 23 * mm, "Transporte de Carga Terrestre")
    c.drawString(50 * mm, h - 28 * mm, "RUT: 00.000.000-0")

    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(AZUL)
    c.drawCentredString(w / 2, h - 48 * mm, "LIQUIDACIÓN DE REMUNERACIONES")
    c.setFont("Helvetica", 10)
    c.setFillColor(GRIS)
    c.drawCentredString(w / 2, h - 54 * mm, f"Período: {liquidacion.mes}")

    # Datos del trabajador
    y = h - 66 * mm
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(18 * mm, y, "DATOS DEL TRABAJADOR")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    c.drawString(18 * mm, y - 6 * mm, f"Nombre: {chofer.nombre}")
    c.drawString(18 * mm, y - 11 * mm, f"RUT: {_formato_rut(chofer.rut)}")

    # Tabla de haberes y descuentos
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(18 * mm, y - 22 * mm, "HABERES")
    c.drawString(w / 2 + 10 * mm, y - 22 * mm, "DESCUENTOS")

    c.setFont("Helvetica", 10)
    c.setFillColor(colors.black)
    filas_haberes = [
        ("Sueldo Base", liquidacion.sueldo_base),
        ("Comisión por producción", comision),
        ("Bonos", bonos),
    ]
    filas_descuentos = [
        ("Anticipos", liquidacion.total_anticipos),
        ("Descuentos", descuentos),
    ]

    yy = y - 29 * mm
    for concepto, monto in filas_haberes:
        c.drawString(18 * mm, yy, concepto)
        c.drawRightString(w / 2 - 10 * mm, yy, f"$ {_formato_clp(monto)}")
        yy -= 6 * mm
    yy = y - 29 * mm
    for concepto, monto in filas_descuentos:
        c.drawString(w / 2 + 10 * mm, yy, concepto)
        c.drawRightString(w - 18 * mm, yy, f"$ {_formato_clp(monto)}")
        yy -= 6 * mm

    # Total líquido
    yy_total = min(yy, y - 29 * mm - 5 * 6 * mm) - 8 * mm
    c.setFillColor(AZUL)
    c.rect(18 * mm, yy_total - 6 * mm, w - 36 * mm, 14 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(24 * mm, yy_total - 1 * mm, "TOTAL LÍQUIDO A PAGAR")
    c.drawRightString(w - 24 * mm, yy_total - 1 * mm, f"$ {_formato_clp(liquidacion.total_liquido)}")

    # Detalle de viajes considerados
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(18 * mm, yy_total - 20 * mm, "DETALLE DE VIAJES DEL PERÍODO")
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.black)
    c.drawString(18 * mm, yy_total - 26 * mm, "Ruta")
    c.drawString(w / 2 + 10 * mm, yy_total - 26 * mm, "Fecha")
    c.drawRightString(w - 18 * mm, yy_total - 26 * mm, "Valor Flete")
    yy = yy_total - 32 * mm
    for viaje in viajes:
        c.drawString(18 * mm, yy, f"{viaje.origen} → {viaje.destino}")
        c.drawString(w / 2 + 10 * mm, yy, (viaje.fecha_fin or viaje.fecha_inicio).strftime("%d/%m/%Y"))
        c.drawRightString(w - 18 * mm, yy, f"$ {_formato_clp(viaje.valor_flete_neto)}")
        yy -= 5.5 * mm

    # Firmas
    yy = max(yy - 12 * mm, 60 * mm)
    c.setStrokeColor(colors.black)
    c.line(18 * mm, yy, 80 * mm, yy)
    c.line(w - 80 * mm, yy, w - 18 * mm, yy)
    c.setFont("Helvetica", 10)
    c.drawCentredString(49 * mm, yy - 5 * mm, "Firma Trabajador")
    c.drawCentredString(w - 49 * mm, yy - 5 * mm, "Firma Empleador")

    c.setFillColor(GRIS)
    c.setFont("Helvetica", 8)
    c.drawCentredString(w / 2, 20 * mm, "Documento generado por Sistema de Gestión Transportes TEI")

    c.showPage()
    c.save()
    return buffer.getvalue()


@router.get("/liquidaciones/{liquidacion_id}/pdf")
def pdf_liquidacion(
    liquidacion_id: UUID,
    session: Session = Depends(get_session),
    _=lectura,
):
    liquidacion = session.get(Liquidacion, liquidacion_id)
    if not liquidacion:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Liquidación no encontrada")
    chofer = session.get(Chofer, liquidacion.chofer_id)
    if not chofer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chofer no encontrado")

    comision, viajes = _comision_chofer(session, chofer.id, liquidacion.mes)
    bonos = Decimal(
        session.exec(
            select(func.coalesce(func.sum(AjusteLiquidacion.monto), 0)).where(
                AjusteLiquidacion.chofer_id == chofer.id,
                AjusteLiquidacion.mes == liquidacion.mes,
                AjusteLiquidacion.tipo == TipoAjuste.bono,
            )
        ).one()
    )
    descuentos = Decimal(
        session.exec(
            select(func.coalesce(func.sum(AjusteLiquidacion.monto), 0)).where(
                AjusteLiquidacion.chofer_id == chofer.id,
                AjusteLiquidacion.mes == liquidacion.mes,
                AjusteLiquidacion.tipo == TipoAjuste.descuento,
            )
        ).one()
    )

    contenido = _generar_pdf(liquidacion, chofer, comision, viajes, bonos, descuentos)
    nombre = f"liquidacion_{chofer.rut}_{liquidacion.mes}.pdf"
    return StreamingResponse(
        io.BytesIO(contenido),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )
