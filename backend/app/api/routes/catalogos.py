from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, col, select

from app.api.deps import get_current_user, require_roles
from app.core.database import get_session
from app.models import Chofer, Cliente, Rampla, RolUsuario, Tracto
from app.schemas.catalogos import (
    ChoferCreate,
    ChoferUpdate,
    ClienteCreate,
    ClienteUpdate,
    RamplaCreate,
    RamplaUpdate,
    TractoCreate,
    TractoUpdate,
)

router = APIRouter(tags=["catalogos"])

lectura = Depends(get_current_user)
escritura = Depends(require_roles(RolUsuario.admin, RolUsuario.operacion))


# ------------------------------------------------------------
# CLIENTES
# ------------------------------------------------------------
@router.get("/clientes", response_model=list[Cliente])
def listar_clientes(
    activo: bool | None = Query(default=None),
    q: str | None = Query(default=None),
    session: Session = Depends(get_session),
    _=lectura,
):
    stmt = select(Cliente)
    if activo is not None:
        stmt = stmt.where(Cliente.activo == activo)
    if q:
        busqueda = f"%{q}%"
        stmt = stmt.where(
            col(Cliente.razon_social).ilike(busqueda) | col(Cliente.rut).ilike(busqueda)
        )
    return session.exec(stmt.order_by(Cliente.razon_social)).all()


@router.post("/clientes", response_model=Cliente, status_code=status.HTTP_201_CREATED)
def crear_cliente(
    body: ClienteCreate,
    session: Session = Depends(get_session),
    _=escritura,
):
    cliente = Cliente(**body.model_dump())
    session.add(cliente)
    session.commit()
    session.refresh(cliente)
    return cliente


@router.put("/clientes/{cliente_id}", response_model=Cliente)
def actualizar_cliente(
    cliente_id,
    body: ClienteUpdate,
    session: Session = Depends(get_session),
    _=escritura,
):
    cliente = session.get(Cliente, cliente_id)
    if not cliente:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado")
    for campo, valor in body.model_dump(exclude_unset=True).items():
        setattr(cliente, campo, valor)
    session.add(cliente)
    session.commit()
    session.refresh(cliente)
    return cliente


@router.delete("/clientes/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def desactivar_cliente(
    cliente_id,
    session: Session = Depends(get_session),
    _=escritura,
):
    cliente = session.get(Cliente, cliente_id)
    if not cliente:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado")
    cliente.activo = False
    session.add(cliente)
    session.commit()


# ------------------------------------------------------------
# CHOFERES
# ------------------------------------------------------------
@router.get("/choferes", response_model=list[Chofer])
def listar_choferes(
    activo: bool | None = Query(default=None),
    q: str | None = Query(default=None),
    session: Session = Depends(get_session),
    _=lectura,
):
    stmt = select(Chofer)
    if activo is not None:
        stmt = stmt.where(Chofer.activo == activo)
    if q:
        busqueda = f"%{q}%"
        stmt = stmt.where(
            col(Chofer.nombre).ilike(busqueda) | col(Chofer.rut).ilike(busqueda)
        )
    return session.exec(stmt.order_by(Chofer.nombre)).all()


@router.post("/choferes", response_model=Chofer, status_code=status.HTTP_201_CREATED)
def crear_chofer(
    body: ChoferCreate,
    session: Session = Depends(get_session),
    _=escritura,
):
    chofer = Chofer(**body.model_dump())
    session.add(chofer)
    session.commit()
    session.refresh(chofer)
    return chofer


@router.put("/choferes/{chofer_id}", response_model=Chofer)
def actualizar_chofer(
    chofer_id,
    body: ChoferUpdate,
    session: Session = Depends(get_session),
    _=escritura,
):
    chofer = session.get(Chofer, chofer_id)
    if not chofer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chofer no encontrado")
    for campo, valor in body.model_dump(exclude_unset=True).items():
        setattr(chofer, campo, valor)
    session.add(chofer)
    session.commit()
    session.refresh(chofer)
    return chofer


@router.delete("/choferes/{chofer_id}", status_code=status.HTTP_204_NO_CONTENT)
def desactivar_chofer(
    chofer_id,
    session: Session = Depends(get_session),
    _=escritura,
):
    chofer = session.get(Chofer, chofer_id)
    if not chofer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chofer no encontrado")
    chofer.activo = False
    session.add(chofer)
    session.commit()


# ------------------------------------------------------------
# TRACTOS
# ------------------------------------------------------------
@router.get("/tractos", response_model=list[Tracto])
def listar_tractos(
    activo: bool | None = Query(default=None),
    q: str | None = Query(default=None),
    session: Session = Depends(get_session),
    _=lectura,
):
    stmt = select(Tracto)
    if activo is not None:
        stmt = stmt.where(Tracto.activo == activo)
    if q:
        busqueda = f"%{q}%"
        stmt = stmt.where(
            col(Tracto.patente).ilike(busqueda) | col(Tracto.marca).ilike(busqueda)
        )
    return session.exec(stmt.order_by(Tracto.patente)).all()


@router.post("/tractos", response_model=Tracto, status_code=status.HTTP_201_CREATED)
def crear_tracto(
    body: TractoCreate,
    session: Session = Depends(get_session),
    _=escritura,
):
    tracto = Tracto(**body.model_dump())
    session.add(tracto)
    session.commit()
    session.refresh(tracto)
    return tracto


@router.put("/tractos/{tracto_id}", response_model=Tracto)
def actualizar_tracto(
    tracto_id,
    body: TractoUpdate,
    session: Session = Depends(get_session),
    _=escritura,
):
    tracto = session.get(Tracto, tracto_id)
    if not tracto:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tracto no encontrado")
    if body.km_actual is not None and body.km_actual < tracto.km_actual:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "El kilometraje no puede ser menor al actual. Regístrelo mediante una mantención.",
        )
    for campo, valor in body.model_dump(exclude_unset=True).items():
        setattr(tracto, campo, valor)
    session.add(tracto)
    session.commit()
    session.refresh(tracto)
    return tracto


@router.delete("/tractos/{tracto_id}", status_code=status.HTTP_204_NO_CONTENT)
def desactivar_tracto(
    tracto_id,
    session: Session = Depends(get_session),
    _=escritura,
):
    tracto = session.get(Tracto, tracto_id)
    if not tracto:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tracto no encontrado")
    tracto.activo = False
    session.add(tracto)
    session.commit()


# ------------------------------------------------------------
# RAMPLAS
# ------------------------------------------------------------
@router.get("/ramplas", response_model=list[Rampla])
def listar_ramplas(
    activo: bool | None = Query(default=None),
    q: str | None = Query(default=None),
    session: Session = Depends(get_session),
    _=lectura,
):
    stmt = select(Rampla)
    if activo is not None:
        stmt = stmt.where(Rampla.activo == activo)
    if q:
        busqueda = f"%{q}%"
        stmt = stmt.where(col(Rampla.patente).ilike(busqueda))
    return session.exec(stmt.order_by(Rampla.patente)).all()


@router.post("/ramplas", response_model=Rampla, status_code=status.HTTP_201_CREATED)
def crear_rampla(
    body: RamplaCreate,
    session: Session = Depends(get_session),
    _=escritura,
):
    rampla = Rampla(**body.model_dump())
    session.add(rampla)
    session.commit()
    session.refresh(rampla)
    return rampla


@router.put("/ramplas/{rampla_id}", response_model=Rampla)
def actualizar_rampla(
    rampla_id,
    body: RamplaUpdate,
    session: Session = Depends(get_session),
    _=escritura,
):
    rampla = session.get(Rampla, rampla_id)
    if not rampla:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rampla no encontrada")
    for campo, valor in body.model_dump(exclude_unset=True).items():
        setattr(rampla, campo, valor)
    session.add(rampla)
    session.commit()
    session.refresh(rampla)
    return rampla


@router.delete("/ramplas/{rampla_id}", status_code=status.HTTP_204_NO_CONTENT)
def desactivar_rampla(
    rampla_id,
    session: Session = Depends(get_session),
    _=escritura,
):
    rampla = session.get(Rampla, rampla_id)
    if not rampla:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rampla no encontrada")
    rampla.activo = False
    session.add(rampla)
    session.commit()
