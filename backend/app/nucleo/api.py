"""API del núcleo operacional v2.

Endpoints:
- GET  /nucleo/disponibilidad/recursos
- GET  /nucleo/disponibilidad/recursos/{tipo}/{id}/libre-desde
- POST /nucleo/disponibilidad/validar-asignacion
- POST /nucleo/viajes/{id}/asignar
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import auth_id_from_credentials, bearer_scheme
from app.nucleo.deps import ContextoEmpresa, get_contexto_empresa
from app.nucleo.permisos import requiere_permiso
from app.nucleo.models import EstadoViaje, TipoRampla, TipoRecurso
from app.nucleo.schemas import (
    AsignacionConfirmada,
    EmpresaMembresiaOut,
    EmpresaOut,
    LibreDesdeOut,
    ListaRecursosOut,
    ListaViajesOut,
    OrdenCompraOpcionOut,
    ResultadoValidacion,
    SolicitudAsignacion,
    SolicitudValidacionAsignacion,
    TarifaOpcionOut,
    ViajeCreateNucleo,
    ViajeResumenOut,
)
from app.nucleo.servicio_disponibilidad import (
    ServicioDisponibilidad,
    listar_empresas_usuario,
)

router = APIRouter(prefix="/nucleo", tags=["nucleo"])


def get_servicio_lectura(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("operacion:leer")),
) -> ServicioDisponibilidad:
    return ServicioDisponibilidad(session, contexto)


def get_servicio_escritura(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("operacion:escribir")),
) -> ServicioDisponibilidad:
    return ServicioDisponibilidad(session, contexto)


@router.get("/empresa", response_model=EmpresaOut)
def empresa_actual(
    contexto: ContextoEmpresa = Depends(get_contexto_empresa),
):
    """Datos de la empresa activa resueltos desde `X-Empresa-ID`."""
    return EmpresaOut.model_validate(contexto.empresa)


@router.get("/mis-empresas", response_model=list[EmpresaMembresiaOut])
def mis_empresas(
    credentials=Depends(bearer_scheme),
    session: Session = Depends(get_session),
):
    """Empresas activas del usuario, sin exigir X-Empresa-ID."""
    auth_id = auth_id_from_credentials(credentials)
    return listar_empresas_usuario(session, auth_id)


@router.get("/tarifas/opciones", response_model=list[TarifaOpcionOut])
def listar_tarifas_nucleo(
    cliente_id: UUID | None = Query(default=None),
    servicio: ServicioDisponibilidad = Depends(get_servicio_lectura),
):
    return servicio.listar_tarifas_nucleo(cliente_id=cliente_id)


@router.get("/ordenes-compra/opciones", response_model=list[OrdenCompraOpcionOut])
def listar_ocs_nucleo(
    cliente_id: UUID | None = Query(default=None),
    servicio: ServicioDisponibilidad = Depends(get_servicio_lectura),
):
    return servicio.listar_ocs_nucleo(cliente_id=cliente_id)


@router.post("/viajes", response_model=ViajeResumenOut, status_code=201)
def crear_viaje_nucleo(
    body: ViajeCreateNucleo,
    servicio: ServicioDisponibilidad = Depends(get_servicio_escritura),
):
    return servicio.crear_viaje(body)


@router.get("/viajes", response_model=ListaViajesOut)
def listar_viajes(
    estado: EstadoViaje | None = Query(default=None),
    desde: datetime | None = Query(default=None),
    hasta: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    servicio: ServicioDisponibilidad = Depends(get_servicio_lectura),
):
    """Viajes confirmados y asignados para la mesa de despacho."""
    return servicio.listar_viajes(
        estado=estado,
        desde=desde,
        hasta=hasta,
        limit=limit,
        offset=offset,
    )


@router.get("/disponibilidad/recursos", response_model=ListaRecursosOut)
def listar_recursos(
    tipo: TipoRecurso,
    desde: datetime,
    hasta: datetime,
    capacidad_min_kg: Decimal | None = Query(default=None, ge=0),
    tipo_rampla: TipoRampla | None = Query(default=None),
    carga_peligrosa: bool = Query(default=False),
    refrigerada: bool = Query(default=False),
    solo_aptos: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    servicio: ServicioDisponibilidad = Depends(get_servicio_lectura),
):
    return servicio.listar_recursos(
        tipo,
        desde=desde,
        hasta=hasta,
        capacidad_min_kg=capacidad_min_kg,
        tipo_rampla=tipo_rampla,
        carga_peligrosa=carga_peligrosa,
        refrigerada=refrigerada,
        solo_aptos=solo_aptos,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/disponibilidad/recursos/{tipo}/{recurso_id}/libre-desde",
    response_model=LibreDesdeOut,
)
def libre_desde(
    tipo: TipoRecurso,
    recurso_id: UUID,
    desde: datetime | None = Query(default=None),
    minutos_traslado: int = Query(default=0, ge=0, le=1440),
    servicio: ServicioDisponibilidad = Depends(get_servicio_lectura),
):
    return servicio.libre_desde(
        tipo,
        recurso_id,
        desde=desde,
        minutos_traslado=minutos_traslado,
    )


@router.post("/disponibilidad/validar-asignacion", response_model=ResultadoValidacion)
def validar_asignacion(
    body: SolicitudValidacionAsignacion,
    servicio: ServicioDisponibilidad = Depends(get_servicio_lectura),
):
    """Previsualización sin escribir nada. Devuelve bloqueos y 'libre desde'."""
    return servicio.validar_asignacion(body.viaje_id, body)


@router.post("/viajes/{viaje_id}/asignar", response_model=AsignacionConfirmada)
def asignar_viaje(
    viaje_id: UUID,
    body: SolicitudAsignacion,
    servicio: ServicioDisponibilidad = Depends(get_servicio_escritura),
):
    """Confirma la asignación de forma atómica.

    La validación previa es necesaria pero no suficiente: la restricción
    EXCLUDE de PostgreSQL es la que impide la doble asignación concurrente.
    """
    return servicio.confirmar_asignacion(viaje_id, body)
