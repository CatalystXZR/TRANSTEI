from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.api.deps import get_current_user, require_roles
from app.core.database import get_session
from app.models import Kpi, RolUsuario, Usuario
from app.schemas.kpis import KpiCreate, KpiPreviewRequest, KpiUpdate, KpiValor
from app.services import kpi_engine

router = APIRouter(tags=["kpis"])

lectura = Depends(get_current_user)
solo_admin = Depends(require_roles(RolUsuario.admin))

AMBITOS = {"global", "viaje"}
FORMATOS = {"clp", "numero", "porcentaje"}
USOS = {"dashboard", "rentabilidad_viaje", "interno"}


def _validar_campos(ambito: str, formato: str, uso: str, formula: str) -> None:
    if ambito not in AMBITOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Ámbito inválido: {ambito}")
    if formato not in FORMATOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Formato inválido: {formato}")
    if uso not in USOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Uso inválido: {uso}")
    try:
        kpi_engine.validar_metricas(formula, ambito)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


# ------------------------------------------------------------
# Rutas estáticas (antes de /kpis/{id})
# ------------------------------------------------------------
@router.get("/kpis/catalogo")
def catalogo(
    ambito: str = Query(default="global"),
    _=lectura,
):
    if ambito not in AMBITOS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ámbito inválido")
    return kpi_engine.catalogo(ambito)


@router.get("/kpis/valores", response_model=list[KpiValor])
def valores(
    periodo: str | None = Query(default=None),
    session: Session = Depends(get_session),
    _=lectura,
):
    kpis = session.exec(
        select(Kpi)
        .where(Kpi.activo == True, Kpi.uso == "dashboard")  # noqa: E712
        .order_by(Kpi.orden, Kpi.nombre)
    ).all()

    try:
        metricas = kpi_engine.metricas_global(session, periodo)
    except Exception:
        metricas = {}

    resultado = []
    for kpi in kpis:
        try:
            valor = kpi_engine.evaluar_formula(kpi.formula, metricas)
            color = kpi_engine.color_para(valor, kpi.reglas_color)
            resultado.append(
                KpiValor(
                    id=str(kpi.id),
                    nombre=kpi.nombre,
                    descripcion=kpi.descripcion,
                    formato=kpi.formato,
                    valor=valor,
                    color=color,
                    periodo=periodo,
                )
            )
        except ValueError as e:
            resultado.append(
                KpiValor(
                    id=str(kpi.id),
                    nombre=kpi.nombre,
                    descripcion=kpi.descripcion,
                    formato=kpi.formato,
                    valor=None,
                    color="gris",
                    error=str(e),
                    periodo=periodo,
                )
            )
    return resultado


@router.post("/kpis/preview")
def preview(
    body: KpiPreviewRequest,
    session: Session = Depends(get_session),
    _=solo_admin,
):
    try:
        kpi_engine.validar_metricas(body.formula, body.ambito)
        if body.ambito == "global":
            metricas = kpi_engine.metricas_global(session, body.periodo)
        else:
            metricas = kpi_engine.metricas_viaje(
                session,
                viaje_id=UUID(body.viaje_id) if body.viaje_id else None,
                flete=body.flete_viaje,
                chofer_id=UUID(body.chofer_id) if body.chofer_id else None,
                gastos=body.gastos_viaje,
            )
        valor = kpi_engine.evaluar_formula(body.formula, metricas)
        return {"valor": valor, "metricas": metricas, "error": None}
    except ValueError as e:
        return {"valor": None, "metricas": {}, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"valor": None, "metricas": {}, "error": f"Error al evaluar: {e}"}


# ------------------------------------------------------------
# CRUD
# ------------------------------------------------------------
@router.get("/kpis", response_model=list[Kpi])
def listar(
    ambito: str | None = Query(default=None),
    activo: bool | None = Query(default=None),
    session: Session = Depends(get_session),
    _=lectura,
):
    stmt = select(Kpi)
    if ambito is not None:
        stmt = stmt.where(Kpi.ambito == ambito)
    if activo is not None:
        stmt = stmt.where(Kpi.activo == activo)
    return session.exec(stmt.order_by(Kpi.orden, Kpi.nombre)).all()


@router.post("/kpis", response_model=Kpi, status_code=status.HTTP_201_CREATED)
def crear(
    body: KpiCreate,
    session: Session = Depends(get_session),
    usuario: Usuario = solo_admin,
):
    _validar_campos(body.ambito, body.formato, body.uso, body.formula)
    kpi = Kpi(
        nombre=body.nombre.strip(),
        descripcion=body.descripcion,
        ambito=body.ambito,
        formula=body.formula.strip(),
        formato=body.formato,
        periodo=body.periodo,
        reglas_color=body.reglas_color,
        uso=body.uso,
        activo=body.activo,
        orden=body.orden,
        created_by=usuario.id,
    )
    session.add(kpi)
    session.commit()
    session.refresh(kpi)
    return kpi


@router.put("/kpis/{kpi_id}", response_model=Kpi)
def actualizar(
    kpi_id: UUID,
    body: KpiUpdate,
    session: Session = Depends(get_session),
    _=solo_admin,
):
    kpi = session.get(Kpi, kpi_id)
    if not kpi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "KPI no encontrado")

    datos = body.model_dump(exclude_unset=True)
    nuevo_ambito = datos.get("ambito", kpi.ambito)
    nuevo_formato = datos.get("formato", kpi.formato)
    nuevo_uso = datos.get("uso", kpi.uso)
    nueva_formula = datos.get("formula", kpi.formula)
    _validar_campos(nuevo_ambito, nuevo_formato, nuevo_uso, nueva_formula)

    for campo, valor in datos.items():
        setattr(kpi, campo, valor)
    session.add(kpi)
    session.commit()
    session.refresh(kpi)
    return kpi


@router.delete("/kpis/{kpi_id}", status_code=status.HTTP_204_NO_CONTENT)
def desactivar(
    kpi_id: UUID,
    session: Session = Depends(get_session),
    _=solo_admin,
):
    kpi = session.get(Kpi, kpi_id)
    if not kpi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "KPI no encontrado")
    kpi.activo = False
    session.add(kpi)
    session.commit()
