from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.api.deps import get_current_user, require_roles
from app.core.database import get_session
from app.models import (
    Chofer,
    Cliente,
    EstadoViaje,
    GastoViaje,
    Kpi,
    Rampla,
    RolUsuario,
    Tracto,
    Viaje,
)
from app.schemas.viajes import (
    RentabilidadPreview,
    ViajeCreate,
    ViajeEstadoUpdate,
    ViajeRead,
    ViajeUpdate,
)
from app.services import kpi_engine

router = APIRouter(tags=["viajes"])

lectura = Depends(get_current_user)
escritura = Depends(require_roles(RolUsuario.admin, RolUsuario.operacion))

TRANSICIONES: dict[EstadoViaje, set[EstadoViaje]] = {
    EstadoViaje.programado: {EstadoViaje.en_ruta},
    EstadoViaje.en_ruta: {EstadoViaje.programado, EstadoViaje.finalizado},
    EstadoViaje.finalizado: {EstadoViaje.en_ruta},
    EstadoViaje.facturado: {EstadoViaje.finalizado},
}


def _nombres(session: Session, viaje: Viaje) -> dict:
    cliente = session.get(Cliente, viaje.cliente_id)
    chofer = session.get(Chofer, viaje.chofer_id)
    tracto = session.get(Tracto, viaje.tracto_id)
    rampla = session.get(Rampla, viaje.rampla_id)
    return {
        "cliente_nombre": cliente.razon_social if cliente else "-",
        "chofer_nombre": chofer.nombre if chofer else "-",
        "tracto_patente": tracto.patente if tracto else "-",
        "rampla_patente": rampla.patente if rampla else "-",
    }


def _total_gastos(session: Session, viaje_id: UUID) -> Decimal:
    total = session.exec(
        select(func.coalesce(func.sum(GastoViaje.monto), 0)).where(
            GastoViaje.viaje_id == viaje_id
        )
    ).one()
    return Decimal(total)


def _to_read(session: Session, viaje: Viaje) -> ViajeRead:
    return ViajeRead(
        **viaje.model_dump(mode="json"),
        **_nombres(session, viaje),
        total_gastos=_total_gastos(session, viaje.id),
    )


def _validar_recursos(
    session: Session, cliente_id: UUID, chofer_id: UUID, tracto_id: UUID, rampla_id: UUID
) -> None:
    cliente = session.get(Cliente, cliente_id)
    chofer = session.get(Chofer, chofer_id)
    tracto = session.get(Tracto, tracto_id)
    rampla = session.get(Rampla, rampla_id)
    if not cliente or not cliente.activo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cliente no válido o inactivo")
    if not chofer or not chofer.activo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Chofer no válido o inactivo")
    if not tracto or not tracto.activo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tracto no válido o inactivo")
    if not rampla or not rampla.activo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rampla no válida o inactiva")


def _validar_fechas(fecha_inicio: date | None, fecha_fin: date | None) -> None:
    if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "La fecha de fin no puede ser anterior a la fecha de inicio",
        )


def _validar_tracto_disponible(
    session: Session, tracto_id: UUID, excluir_viaje_id: UUID | None = None
) -> None:
    stmt = select(Viaje).where(
        Viaje.tracto_id == tracto_id,
        Viaje.estado.in_([EstadoViaje.programado, EstadoViaje.en_ruta]),
    )
    if excluir_viaje_id is not None:
        stmt = stmt.where(Viaje.id != excluir_viaje_id)
    ocupado = session.exec(stmt).first()
    if ocupado:
        tracto = session.get(Tracto, tracto_id)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"El tracto {tracto.patente if tracto else ''} ya está asignado a un viaje activo "
            f"({ocupado.origen} → {ocupado.destino})",
        )


@router.get("/viajes", response_model=list[ViajeRead])
def listar_viajes(
    estado: EstadoViaje | None = Query(default=None),
    cliente_id: UUID | None = Query(default=None),
    desde: date | None = Query(default=None),
    hasta: date | None = Query(default=None),
    session: Session = Depends(get_session),
    _=lectura,
):
    stmt = select(Viaje)
    if estado is not None:
        stmt = stmt.where(Viaje.estado == estado)
    if cliente_id is not None:
        stmt = stmt.where(Viaje.cliente_id == cliente_id)
    if desde is not None:
        stmt = stmt.where(Viaje.fecha_inicio >= desde)
    if hasta is not None:
        stmt = stmt.where(Viaje.fecha_inicio <= hasta)
    viajes = session.exec(stmt.order_by(col(Viaje.fecha_inicio).desc())).all()
    return [_to_read(session, v) for v in viajes]


@router.get("/viajes/{viaje_id}", response_model=ViajeRead)
def obtener_viaje(
    viaje_id: UUID,
    session: Session = Depends(get_session),
    _=lectura,
):
    viaje = session.get(Viaje, viaje_id)
    if not viaje:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Viaje no encontrado")
    return _to_read(session, viaje)


@router.post("/viajes", response_model=ViajeRead, status_code=status.HTTP_201_CREATED)
def crear_viaje(
    body: ViajeCreate,
    session: Session = Depends(get_session),
    _=escritura,
):
    _validar_recursos(
        session,
        UUID(body.cliente_id),
        UUID(body.chofer_id),
        UUID(body.tracto_id),
        UUID(body.rampla_id),
    )
    _validar_fechas(body.fecha_inicio, body.fecha_fin)
    _validar_tracto_disponible(session, UUID(body.tracto_id))
    viaje = Viaje(
        **body.model_dump(exclude={"cliente_id", "chofer_id", "tracto_id", "rampla_id"}),
        cliente_id=UUID(body.cliente_id),
        chofer_id=UUID(body.chofer_id),
        tracto_id=UUID(body.tracto_id),
        rampla_id=UUID(body.rampla_id),
        estado=EstadoViaje.programado,
    )
    session.add(viaje)
    session.commit()
    session.refresh(viaje)
    return _to_read(session, viaje)


@router.put("/viajes/{viaje_id}", response_model=ViajeRead)
def actualizar_viaje(
    viaje_id: UUID,
    body: ViajeUpdate,
    session: Session = Depends(get_session),
    _=escritura,
):
    viaje = session.get(Viaje, viaje_id)
    if not viaje:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Viaje no encontrado")
    if viaje.estado == EstadoViaje.facturado:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No se puede editar un viaje facturado")

    datos = body.model_dump(exclude_unset=True)
    for campo in ("cliente_id", "chofer_id", "tracto_id", "rampla_id"):
        if campo in datos:
            datos[campo] = UUID(datos[campo])
    if any(k in datos for k in ("cliente_id", "chofer_id", "tracto_id", "rampla_id")):
        _validar_recursos(
            session,
            datos.get("cliente_id", viaje.cliente_id),
            datos.get("chofer_id", viaje.chofer_id),
            datos.get("tracto_id", viaje.tracto_id),
            datos.get("rampla_id", viaje.rampla_id),
        )
    _validar_fechas(
        datos.get("fecha_inicio", viaje.fecha_inicio),
        datos.get("fecha_fin", viaje.fecha_fin),
    )
    if "tracto_id" in datos:
        _validar_tracto_disponible(session, datos["tracto_id"], excluir_viaje_id=viaje.id)
    for campo, valor in datos.items():
        setattr(viaje, campo, valor)
    session.add(viaje)
    session.commit()
    session.refresh(viaje)
    return _to_read(session, viaje)


@router.patch("/viajes/{viaje_id}/estado", response_model=ViajeRead)
def cambiar_estado(
    viaje_id: UUID,
    body: ViajeEstadoUpdate,
    session: Session = Depends(get_session),
    _=escritura,
):
    viaje = session.get(Viaje, viaje_id)
    if not viaje:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Viaje no encontrado")

    if body.estado == EstadoViaje.facturado:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "El estado 'facturado' se asigna automáticamente al asociar una factura",
        )
    if body.estado not in TRANSICIONES.get(viaje.estado, set()):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Transición no permitida: {viaje.estado.value} → {body.estado.value}",
        )

    viaje.estado = body.estado
    if body.estado == EstadoViaje.en_ruta:
        viaje.fecha_fin = None
    if body.estado == EstadoViaje.finalizado and viaje.fecha_fin is None:
        viaje.fecha_fin = date.today()
    session.add(viaje)
    session.commit()
    session.refresh(viaje)
    return _to_read(session, viaje)


@router.delete("/viajes/{viaje_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_viaje(
    viaje_id: UUID,
    session: Session = Depends(get_session),
    _=escritura,
):
    viaje = session.get(Viaje, viaje_id)
    if not viaje:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Viaje no encontrado")
    if viaje.estado != EstadoViaje.programado:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Solo se pueden eliminar viajes en estado 'programado'",
        )
    session.delete(viaje)
    session.commit()


@router.get("/viajes/{viaje_id}/rentabilidad")
def rentabilidad_viaje(
    viaje_id: UUID,
    session: Session = Depends(get_session),
    _=lectura,
):
    """Rentabilidad del viaje evaluada con el KPI de rentabilidad configurable."""
    viaje = session.get(Viaje, viaje_id)
    if not viaje:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Viaje no encontrado")

    kpi = session.exec(
        select(Kpi).where(
            Kpi.activo == True,  # noqa: E712
            Kpi.uso == "rentabilidad_viaje",
        )
    ).first()

    formula = kpi.formula if kpi else "SI(flete_viaje = 0, 0, margen_viaje / flete_viaje * 100)"
    reglas = kpi.reglas_color if kpi else []
    formato = kpi.formato if kpi else "porcentaje"

    metricas = kpi_engine.metricas_viaje(session, viaje_id=viaje_id)
    try:
        valor = kpi_engine.evaluar_formula(formula, metricas)
        color = kpi_engine.color_para(valor, reglas)
        error = None
    except ValueError as e:
        valor = None
        color = "gris"
        error = str(e)

    return {
        "valor": valor,
        "color": color,
        "formato": formato,
        "detalle": metricas,
        "error": error,
    }


@router.post("/viajes/preview-rentabilidad")
def preview_rentabilidad(
    body: RentabilidadPreview,
    session: Session = Depends(get_session),
    _=lectura,
):
    """Rentabilidad estimada antes de crear el viaje (para el semáforo)."""
    kpi = session.exec(
        select(Kpi).where(
            Kpi.activo == True,  # noqa: E712
            Kpi.uso == "rentabilidad_viaje",
        )
    ).first()
    formula = kpi.formula if kpi else "SI(flete_viaje = 0, 0, margen_viaje / flete_viaje * 100)"
    reglas = kpi.reglas_color if kpi else []
    formato = kpi.formato if kpi else "porcentaje"

    try:
        metricas = kpi_engine.metricas_viaje(
            session,
            flete=body.flete_viaje,
            chofer_id=UUID(body.chofer_id) if body.chofer_id else None,
            gastos=body.gastos_viaje,
        )
        valor = kpi_engine.evaluar_formula(formula, metricas)
        color = kpi_engine.color_para(valor, reglas)
        error = None
    except ValueError as e:
        metricas, valor, color, error = {}, None, "gris", str(e)

    return {
        "valor": valor,
        "color": color,
        "formato": formato,
        "detalle": metricas,
        "error": error,
    }
