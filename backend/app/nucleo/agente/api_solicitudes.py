"""Endpoints del buzón de solicitudes (O2.2). Contrato §6.1–§6.4.

Permisos (§6.1):
- `agente:buzon`  → listar y ver el detalle.
- `agente:aprobar` → decidir.

Decisiones de implementación que el contrato no fija literalmente:

1. **`commit()` en el endpoint, no en el servicio.** `decidir` compone el efecto
   del ejecutor y el cambio de estado; si el servicio confirmara por su cuenta,
   un fallo del segundo paso dejaría medio efecto aplicado (§6.6). Aquí se hace
   un único `commit()` al final y `rollback()` ante cualquier excepción.
2. **404 antes que 403 para recursos de otra empresa** (§6.1): el `select` filtra
   por `empresa_id`, así que un id ajeno simplemente no existe para esta empresa.
3. **`solicitante.nombre` puede ser `null`** cuando quien solicita es un usuario:
   `nucleo.usuarios_empresa` no tiene columna de nombre (solo `auth_id` y `rol`).
   No se inventa un identificador.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from app.core.database import get_session_nucleo
from app.nucleo.agente import solicitudes as servicio
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.permisos import requiere_permiso

router = APIRouter(prefix="/nucleo/agente", tags=["agente"])


class _Cerrado(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Solicitante(_Cerrado):
    tipo: Literal["contacto", "usuario"]
    id: str | None
    nombre: str | None


class SolicitudItem(_Cerrado):
    id: str
    tipo: str
    estado: str
    solicitante: Solicitante
    viaje_id: str | None
    id_comercial_flete: str | None
    resumen: str
    creada_en: str | None
    decidida_en: str | None
    tiene_modificaciones: bool
    version: int


class ListaOut(_Cerrado):
    items: list[SolicitudItem]
    total: int
    limit: int
    offset: int


class HojaRutaOut(_Cerrado):
    id: str
    estado: str
    faltantes: list[str]


class EvidenciaOut(_Cerrado):
    tipo: str | None = None
    ref: str | None = None


class DiffOut(_Cerrado):
    campo: str
    propuesto: Any = None
    modificado: Any = None


class SolicitudDetalle(_Cerrado):
    id: str
    tipo: str
    estado: str
    solicitante: Solicitante
    viaje_id: str | None
    id_comercial_flete: str | None
    payload: dict[str, Any]
    valores_modificados: dict[str, Any] | None
    diff: list[DiffOut]
    evidencia: list[EvidenciaOut]
    hoja_ruta: HojaRutaOut | None
    creada_en: str | None
    decidida_en: str | None
    aprobado_por: str | None
    version: int


class DecidirIn(_Cerrado):
    accion: Literal["confirmar", "rechazar", "modificar"]
    version: int = Field(ge=1)
    motivo_rechazo: str | None = Field(default=None, max_length=500)
    valores_modificados: dict[str, Any] | None = None


class ResultadoOut(_Cerrado):
    tipo: str
    ref: str
    estado: str


class DecisionOut(_Cerrado):
    solicitud: SolicitudDetalle
    resultado: ResultadoOut | None


@router.get("/solicitudes", response_model=ListaOut)
def listar_solicitudes(
    estado: str = Query(default="pendiente"),
    tipo: str | None = Query(default=None),
    viaje_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    contexto: ContextoEmpresa = Depends(requiere_permiso("agente:buzon")),
    session: Session = Depends(get_session_nucleo),
) -> ListaOut:
    return ListaOut(
        **servicio.listar(
            session,
            contexto,
            estado=estado,
            tipo=tipo,
            viaje_id=viaje_id,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/solicitudes/{solicitud_id}", response_model=SolicitudDetalle)
def obtener_solicitud(
    solicitud_id: UUID,
    contexto: ContextoEmpresa = Depends(requiere_permiso("agente:buzon")),
    session: Session = Depends(get_session_nucleo),
) -> SolicitudDetalle:
    return SolicitudDetalle(**servicio.obtener(session, contexto, solicitud_id))


@router.post("/solicitudes/{solicitud_id}/decidir", response_model=DecisionOut)
def decidir_solicitud(
    solicitud_id: UUID,
    body: DecidirIn,
    contexto: ContextoEmpresa = Depends(requiere_permiso("agente:aprobar")),
    session: Session = Depends(get_session_nucleo),
) -> DecisionOut:
    try:
        detalle, resultado = servicio.decidir(
            session,
            contexto,
            solicitud_id,
            accion=body.accion,
            version=body.version,
            motivo_rechazo=body.motivo_rechazo,
            valores_modificados=body.valores_modificados,
        )
    except Exception:
        # Una transacción por decisión: o queda el efecto y el estado, o nada.
        session.rollback()
        raise
    session.commit()
    return DecisionOut(
        solicitud=SolicitudDetalle(**detalle),
        resultado=None if resultado is None else ResultadoOut(**resultado),
    )
