"""API del expediente del viaje (P0-05)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlmodel import Session

from app.core.database import get_session_nucleo
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import DatosInvalidos
from app.nucleo.models import EstadoViaje
from app.nucleo.permisos import requiere_permiso
from app.nucleo.schemas import (
    ChecklistItemCreate,
    ChecklistItemOut,
    ChecklistItemUpdate,
    CerrarViaje,
    EventoCreate,
    EventoOut,
    IncidenteCreate,
    IncidenteOut,
    IncidenteUpdate,
    ListaExpedienteOut,
    ParadaCreate,
    ParadaOut,
    ParadaUpdate,
    ViajeDocumentoOut,
    ViajeExpedienteOut,
)
from app.nucleo.servicio_expediente import ServicioExpediente
from app.nucleo.storage import detectar_content_type, leer_archivo_acotado

router = APIRouter(prefix="/nucleo/expediente", tags=["nucleo-expediente"])

def get_servicio_lectura(
    session: Session = Depends(get_session_nucleo),
    contexto: ContextoEmpresa = Depends(requiere_permiso("expediente:leer")),
) -> ServicioExpediente:
    return ServicioExpediente(session, contexto)


def get_servicio_escritura(
    session: Session = Depends(get_session_nucleo),
    contexto: ContextoEmpresa = Depends(requiere_permiso("expediente:escribir")),
) -> ServicioExpediente:
    return ServicioExpediente(session, contexto)


@router.get("/viajes", response_model=ListaExpedienteOut)
def listar_viajes_expediente(
    estado: EstadoViaje | None = Query(default=None),
    cliente_id: UUID | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    desde: datetime | None = Query(default=None),
    hasta: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    servicio: ServicioExpediente = Depends(get_servicio_lectura),
):
    return servicio.listar_viajes(
        estado=estado,
        cliente_id=cliente_id,
        q=q,
        desde=desde,
        hasta=hasta,
        limit=limit,
        offset=offset,
    )


@router.get("/viajes/{viaje_id}", response_model=ViajeExpedienteOut)
def obtener_expediente(
    viaje_id: UUID,
    servicio: ServicioExpediente = Depends(get_servicio_lectura),
):
    return servicio.obtener(viaje_id)


@router.get("/viajes/{viaje_id}/qr")
def qr_viaje(
    viaje_id: UUID,
    servicio: ServicioExpediente = Depends(get_servicio_lectura),
):
    svg = servicio.qr_svg(viaje_id)
    return Response(content=svg, media_type="image/svg+xml")


@router.post("/viajes/{viaje_id}/cerrar", response_model=ViajeExpedienteOut)
def cerrar_viaje(
    viaje_id: UUID,
    body: CerrarViaje,
    servicio: ServicioExpediente = Depends(get_servicio_escritura),
):
    return servicio.cerrar_viaje(viaje_id, body)


# ---------------------------------------------------------------------------
# Paradas
# ---------------------------------------------------------------------------
@router.post(
    "/viajes/{viaje_id}/paradas",
    response_model=ParadaOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_parada(
    viaje_id: UUID,
    body: ParadaCreate,
    servicio: ServicioExpediente = Depends(get_servicio_escritura),
):
    return servicio.crear_parada(viaje_id, body)


@router.put("/viajes/{viaje_id}/paradas/{parada_id}", response_model=ParadaOut)
def actualizar_parada(
    viaje_id: UUID,
    parada_id: UUID,
    body: ParadaUpdate,
    servicio: ServicioExpediente = Depends(get_servicio_escritura),
):
    return servicio.actualizar_parada(viaje_id, parada_id, body)


@router.delete("/viajes/{viaje_id}/paradas/{parada_id}", response_model=ParadaOut)
def desactivar_parada(
    viaje_id: UUID,
    parada_id: UUID,
    servicio: ServicioExpediente = Depends(get_servicio_escritura),
):
    return servicio.desactivar_parada(viaje_id, parada_id)


# ---------------------------------------------------------------------------
# Checklist
# ---------------------------------------------------------------------------
@router.get("/viajes/{viaje_id}/checklist", response_model=list[ChecklistItemOut])
def listar_checklist(
    viaje_id: UUID,
    servicio: ServicioExpediente = Depends(get_servicio_lectura),
):
    return servicio.listar_checklist(viaje_id)


@router.post(
    "/viajes/{viaje_id}/checklist",
    response_model=ChecklistItemOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_item_checklist(
    viaje_id: UUID,
    body: ChecklistItemCreate,
    servicio: ServicioExpediente = Depends(get_servicio_escritura),
):
    return servicio.crear_item_checklist(viaje_id, body)


@router.put(
    "/viajes/{viaje_id}/checklist/{item_id}", response_model=ChecklistItemOut
)
def actualizar_item_checklist(
    viaje_id: UUID,
    item_id: UUID,
    body: ChecklistItemUpdate,
    servicio: ServicioExpediente = Depends(get_servicio_escritura),
):
    return servicio.actualizar_item_checklist(viaje_id, item_id, body)


# ---------------------------------------------------------------------------
# Eventos
# ---------------------------------------------------------------------------
@router.get("/viajes/{viaje_id}/eventos", response_model=list[EventoOut])
def listar_eventos(
    viaje_id: UUID,
    servicio: ServicioExpediente = Depends(get_servicio_lectura),
):
    return servicio.listar_eventos(viaje_id)


@router.post(
    "/viajes/{viaje_id}/eventos",
    response_model=EventoOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_evento(
    viaje_id: UUID,
    body: EventoCreate,
    servicio: ServicioExpediente = Depends(get_servicio_escritura),
):
    return servicio.crear_evento(viaje_id, body)


# ---------------------------------------------------------------------------
# Incidentes
# ---------------------------------------------------------------------------
@router.get("/viajes/{viaje_id}/incidentes", response_model=list[IncidenteOut])
def listar_incidentes(
    viaje_id: UUID,
    servicio: ServicioExpediente = Depends(get_servicio_lectura),
):
    return servicio.listar_incidentes(viaje_id)


@router.post(
    "/viajes/{viaje_id}/incidentes",
    response_model=IncidenteOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_incidente(
    viaje_id: UUID,
    body: IncidenteCreate,
    servicio: ServicioExpediente = Depends(get_servicio_escritura),
):
    return servicio.crear_incidente(viaje_id, body)


@router.put(
    "/viajes/{viaje_id}/incidentes/{incidente_id}", response_model=IncidenteOut
)
def actualizar_incidente(
    viaje_id: UUID,
    incidente_id: UUID,
    body: IncidenteUpdate,
    servicio: ServicioExpediente = Depends(get_servicio_escritura),
):
    return servicio.actualizar_incidente(viaje_id, incidente_id, body)


# ---------------------------------------------------------------------------
# Documentos
# ---------------------------------------------------------------------------
@router.get("/viajes/{viaje_id}/documentos", response_model=list[ViajeDocumentoOut])
def listar_documentos(
    viaje_id: UUID,
    servicio: ServicioExpediente = Depends(get_servicio_lectura),
):
    return servicio.listar_documentos(viaje_id)


@router.post(
    "/viajes/{viaje_id}/documentos",
    response_model=ViajeDocumentoOut,
    status_code=status.HTTP_201_CREATED,
)
async def subir_documento(
    viaje_id: UUID,
    tipo: str = Form(default="otro"),
    observaciones: str | None = Form(default=None),
    archivo: UploadFile = File(...),
    servicio: ServicioExpediente = Depends(get_servicio_escritura),
):
    # SEC-019: lectura acotada (no se bufferiza un multipart sin límite).
    contenido = await leer_archivo_acotado(archivo)
    # SEC-018: el content-type lo determina el servidor por firma; el header
    # multipart del cliente se ignora por completo.
    content_type = detectar_content_type(contenido)
    if content_type is None:
        raise DatosInvalidos(
            "El contenido del archivo no es un formato permitido "
            "(PDF, JPG, JPEG, PNG, WEBP o HEIC)."
        )
    return servicio.subir_documento(
        viaje_id,
        tipo=tipo,
        nombre_archivo=archivo.filename or "documento",
        contenido=contenido,
        content_type=content_type,
        observaciones=observaciones,
    )


@router.delete(
    "/viajes/{viaje_id}/documentos/{documento_id}",
    response_model=ViajeDocumentoOut,
)
def desactivar_documento(
    viaje_id: UUID,
    documento_id: UUID,
    servicio: ServicioExpediente = Depends(get_servicio_escritura),
):
    return servicio.desactivar_documento(viaje_id, documento_id)
