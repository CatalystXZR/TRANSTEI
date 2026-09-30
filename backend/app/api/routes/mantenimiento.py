from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.api.deps import get_current_user, require_roles
from app.core.database import get_session
from app.core.settings_db import get_config
from app.models import (
    Mantenimiento,
    PautaMantenimiento,
    RolUsuario,
    Tracto,
)

router = APIRouter(tags=["mantenimiento"])

lectura = Depends(get_current_user)
escritura = Depends(require_roles(RolUsuario.admin, RolUsuario.operacion))


# ------------------------------------------------------------
# Pautas
# ------------------------------------------------------------
@router.get("/pautas", response_model=list[PautaMantenimiento])
def listar_pautas(
    session: Session = Depends(get_session),
    _=lectura,
):
    return session.exec(
        select(PautaMantenimiento)
        .where(PautaMantenimiento.activo == True)  # noqa: E712
        .order_by(PautaMantenimiento.orden)
    ).all()


@router.post("/pautas", response_model=PautaMantenimiento, status_code=status.HTTP_201_CREATED)
def crear_pauta(
    body: PautaMantenimiento,
    session: Session = Depends(get_session),
    _=escritura,
):
    pauta = PautaMantenimiento(
        item=body.item.strip(),
        intervalo_km=body.intervalo_km,
        orden=body.orden,
    )
    session.add(pauta)
    session.commit()
    session.refresh(pauta)
    return pauta


@router.put("/pautas/{pauta_id}", response_model=PautaMantenimiento)
def actualizar_pauta(
    pauta_id: UUID,
    body: PautaMantenimiento,
    session: Session = Depends(get_session),
    _=escritura,
):
    pauta = session.get(PautaMantenimiento, pauta_id)
    if not pauta:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ítem de pauta no encontrado")
    pauta.item = body.item.strip()
    pauta.intervalo_km = body.intervalo_km
    pauta.orden = body.orden
    session.add(pauta)
    session.commit()
    session.refresh(pauta)
    return pauta


@router.delete("/pautas/{pauta_id}", status_code=status.HTTP_204_NO_CONTENT)
def desactivar_pauta(
    pauta_id: UUID,
    session: Session = Depends(get_session),
    _=escritura,
):
    pauta = session.get(PautaMantenimiento, pauta_id)
    if not pauta:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ítem de pauta no encontrado")
    pauta.activo = False
    session.add(pauta)
    session.commit()


# ------------------------------------------------------------
# Registro de mantenciones
# ------------------------------------------------------------
@router.get("/mantenimientos", response_model=list[Mantenimiento])
def listar_mantenimientos(
    tracto_id: UUID | None = Query(default=None),
    session: Session = Depends(get_session),
    _=lectura,
):
    stmt = select(Mantenimiento).order_by(col(Mantenimiento.fecha).desc())
    if tracto_id is not None:
        stmt = stmt.where(Mantenimiento.tracto_id == tracto_id)
    return session.exec(stmt).all()


@router.post("/mantenimientos", response_model=Mantenimiento, status_code=status.HTTP_201_CREATED)
def crear_mantenimiento(
    tracto_id: UUID,
    pauta_id: UUID,
    fecha: date | None = None,
    km: int = 0,
    costo: Decimal = Decimal("0"),
    notas: str | None = None,
    session: Session = Depends(get_session),
    _=escritura,
):
    tracto = session.get(Tracto, tracto_id)
    if not tracto:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tracto no encontrado")
    pauta = session.get(PautaMantenimiento, pauta_id)
    if not pauta or not pauta.activo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ítem de pauta no válido")

    mantencion = Mantenimiento(
        tracto_id=tracto_id,
        pauta_id=pauta_id,
        fecha=fecha or date.today(),
        km=km,
        costo=costo,
        notas=notas,
    )
    session.add(mantencion)

    if km > tracto.km_actual:
        tracto.km_actual = km
        session.add(tracto)

    session.commit()
    session.refresh(mantencion)
    return mantencion


@router.delete("/mantenimientos/{mantencion_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_mantenimiento(
    mantencion_id: UUID,
    session: Session = Depends(get_session),
    _=escritura,
):
    mantencion = session.get(Mantenimiento, mantencion_id)
    if not mantencion:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registro no encontrado")
    session.delete(mantencion)
    session.commit()


# ------------------------------------------------------------
# Estado de mantenimiento por tracto (alertas por km)
# ------------------------------------------------------------
@router.get("/mantenimiento/estado")
def estado_mantenimiento(
    session: Session = Depends(get_session),
    _=lectura,
):
    alerta_km = int(get_config(session, "alerta_km_mantenimiento", "5000"))
    tractos = session.exec(select(Tracto).where(Tracto.activo == True)).all()  # noqa: E712
    pautas = session.exec(
        select(PautaMantenimiento).where(PautaMantenimiento.activo == True)  # noqa: E712
    ).all()

    # último registro por (tracto, pauta): el de mayor km
    ultimos = session.exec(
        select(Mantenimiento).order_by(
            Mantenimiento.tracto_id, Mantenimiento.pauta_id, col(Mantenimiento.km).desc()
        )
    ).all()
    mapa_ultimo: dict[tuple, Mantenimiento] = {}
    for m in ultimos:
        clave = (str(m.tracto_id), str(m.pauta_id))
        if clave not in mapa_ultimo:
            mapa_ultimo[clave] = m

    resultado = []
    for tracto in tractos:
        items = []
        for pauta in pautas:
            ultimo = mapa_ultimo.get((str(tracto.id), str(pauta.id)))
            if ultimo is None:
                items.append(
                    {
                        "pauta_id": str(pauta.id),
                        "item": pauta.item,
                        "intervalo_km": pauta.intervalo_km,
                        "ultimo_km": None,
                        "ultima_fecha": None,
                        "proximo_km": None,
                        "km_restante": None,
                        "estado": "sin_registro",
                    }
                )
                continue
            proximo = ultimo.km + pauta.intervalo_km
            restante = proximo - tracto.km_actual
            if restante <= 0:
                estado = "pendiente"
            elif restante <= alerta_km:
                estado = "por_vencer"
            else:
                estado = "ok"
            items.append(
                {
                    "pauta_id": str(pauta.id),
                    "item": pauta.item,
                    "intervalo_km": pauta.intervalo_km,
                    "ultimo_km": ultimo.km,
                    "ultima_fecha": ultimo.fecha.isoformat(),
                    "proximo_km": proximo,
                    "km_restante": restante,
                    "estado": estado,
                }
            )
        resultado.append(
            {
                "tracto_id": str(tracto.id),
                "patente": tracto.patente,
                "km_actual": tracto.km_actual,
                "items": items,
            }
        )
    return resultado
