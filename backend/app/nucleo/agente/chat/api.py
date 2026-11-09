"""Endpoints del chat in-app (`/api/v1/nucleo/agente/chat`).

Permiso único: `agente:chat` (deny-by-default). Está en `PERMISOS_AGENTE`, que
`admin` hereda de `TODOS_LOS_PERMISOS` y `gerente` excluye por AB-02: el dueño
opera el chat con el rol `admin`, no con el rol `gerente` del ERP.

La empresa se resuelve **siempre** en `get_contexto_empresa` (`X-Empresa-ID` +
membresía). El body no tiene `empresa_id` y `extra="forbid"` rechaza el intento.
`clave_idempotencia` es obligatoria (8–128): sin ella un doble POST crearía dos
turnos. La UI envía `crypto.randomUUID()`.

La transacción la cierra este endpoint: `ServicioChat.enviar` compone memoria y
tools, y ante cualquier excepción se hace `rollback()` (la solicitud del buzón
queda pendiente, nunca a medias).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from app.core.config import settings
from app.core.database import get_session_nucleo
from app.nucleo.agente.chat.llm import ClienteLLM, get_cliente_llm
from app.nucleo.agente.chat.runtime import ServicioChat
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import ErrorNucleo
from app.nucleo.permisos import requiere_permiso

router = APIRouter(prefix="/nucleo/agente/chat", tags=["agente"])


class AgenteOcupado(ErrorNucleo):
    """No hay cupo de turnos concurrentes (SEC-053)."""

    status_code = 429
    codigo = "AGENTE_OCUPADO"


# Tope por proceso: el pool de conexiones y el proveedor LLM son recursos
# finitos. No sustituye un rate limit distribuido; cada worker tiene el suyo.
_SEMAFORO = threading.BoundedSemaphore(
    max(1, int(settings.AGENTE_CHAT_MAX_CONCURRENT))
)


def requiere_cupo_chat() -> Iterator[None]:
    """Adquiere un cupo de chat; si no hay, responde 429 sin tocar la BD.

    Se declara como primera dependencia del POST: se resuelve antes que la
    autenticación y la sesión, así un servidor saturado no abre transacción ni
    consulta membresía para rechazar el turno.
    """
    if not _SEMAFORO.acquire(blocking=False):
        raise AgenteOcupado(
            "El agente está atendiendo otros turnos; reintenta en unos segundos."
        )
    try:
        yield
    finally:
        _SEMAFORO.release()


class _Cerrado(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatIn(_Cerrado):
    agente: Literal["gerente", "secretaria"]
    mensaje: str = Field(min_length=1, max_length=4000)
    conversacion_id: UUID | None = None
    # SEC-062: obligatoria. Sin clave, un doble POST crearía dos turnos y dos
    # solicitudes. La UI envía `crypto.randomUUID()` (36 caracteres).
    clave_idempotencia: str = Field(min_length=8, max_length=128)


class HerramientaOut(_Cerrado):
    nombre: str
    estado: str
    resumen: str


class UpsellOut(_Cerrado):
    modulo: str
    mensaje: str


class ChatOut(_Cerrado):
    conversacion_id: str
    mensaje_id: str
    agente: str
    respuesta: str
    herramientas: list[HerramientaOut]
    upsell: UpsellOut | None


class AgenteOut(_Cerrado):
    clave: str
    nombre: str
    configurado: bool
    herramientas: list[str]


class MensajeOut(_Cerrado):
    id: str
    rol: str
    contenido: str | None
    tool_calls: Any = None
    tool_call_id: str | None
    nombre_herramienta: str | None
    metadata: dict[str, Any]
    creado_en: str | None


class ConversacionOut(_Cerrado):
    id: str
    agente: str
    activa: bool
    abierta_en: str | None
    cerrada_en: str | None
    resumen: str | None
    resumen_en: str | None
    version: int


class HistorialOut(_Cerrado):
    conversacion: ConversacionOut
    mensajes: list[MensajeOut]


@router.get("/agentes", response_model=list[AgenteOut])
def listar_agentes(
    contexto: ContextoEmpresa = Depends(requiere_permiso("agente:chat")),
    session: Session = Depends(get_session_nucleo),
    cliente_llm: ClienteLLM = Depends(get_cliente_llm),
) -> list[AgenteOut]:
    """Agentes disponibles y si su clave está configurada. Nunca la clave."""
    servicio = ServicioChat(session, contexto, cliente_llm)
    return [AgenteOut(**a) for a in servicio.agentes_disponibles()]


@router.post("", response_model=ChatOut)
def enviar_mensaje(
    body: ChatIn,
    _cupo: None = Depends(requiere_cupo_chat),
    contexto: ContextoEmpresa = Depends(requiere_permiso("agente:chat")),
    session: Session = Depends(get_session_nucleo),
    cliente_llm: ClienteLLM = Depends(get_cliente_llm),
) -> ChatOut:
    servicio = ServicioChat(session, contexto, cliente_llm)
    try:
        salida = servicio.enviar(
            body.agente,
            body.mensaje,
            conversacion_id=(
                None if body.conversacion_id is None else str(body.conversacion_id)
            ),
            clave_idempotencia=body.clave_idempotencia,
        )
    except Exception:
        session.rollback()
        raise
    session.commit()
    return ChatOut(**salida)


@router.get("/{conversacion_id}", response_model=HistorialOut)
def obtener_conversacion(
    conversacion_id: UUID,
    contexto: ContextoEmpresa = Depends(requiere_permiso("agente:chat")),
    session: Session = Depends(get_session_nucleo),
    cliente_llm: ClienteLLM = Depends(get_cliente_llm),
) -> HistorialOut:
    servicio = ServicioChat(session, contexto, cliente_llm)
    return HistorialOut(**servicio.historial(str(conversacion_id)))
