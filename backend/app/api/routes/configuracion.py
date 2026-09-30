from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.api.deps import get_current_user, require_roles
from app.core.database import get_session
from app.models import Configuracion, RolUsuario

router = APIRouter(prefix="/configuracion", tags=["configuracion"])

lectura = Depends(get_current_user)
solo_admin = Depends(require_roles(RolUsuario.admin))


@router.get("")
def obtener_configuracion(
    session: Session = Depends(get_session),
    _=lectura,
):
    filas = session.exec(select(Configuracion)).all()
    return {f.clave: f.valor for f in filas}


@router.put("/{clave}")
def actualizar_configuracion(
    clave: str,
    valor: str = Query(...),
    session: Session = Depends(get_session),
    _=solo_admin,
):
    permitidas = {"iva_porcentaje", "alerta_km_mantenimiento", "dias_alerta_vencimientos", "dias_alerta_cobranza"}
    if clave not in permitidas:
        raise HTTPException(400, f"Clave no permitida: {clave}")
    fila = session.get(Configuracion, clave)
    if fila is None:
        fila = Configuracion(clave=clave, valor=valor)
    else:
        fila.valor = valor
    session.add(fila)
    session.commit()
    return {clave: valor}
