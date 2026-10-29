"""API de maestros del núcleo y documentos.

Rutas:
- CRUD de clientes, tractos, ramplas y choferes.
- Documentos versionados con archivo en Storage.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlmodel import Session

from app.core.database import get_session
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.permisos import requiere_permiso
from app.nucleo.models import (
    Chofer,
    Cliente,
    Rampla,
    TipoDocumento,
    TipoRecurso,
    Tracto,
)
from app.nucleo.schemas import (
    ChoferCreateNucleo,
    ClienteCreateNucleo,
    DocumentoOutNucleo,
    DocumentoUrlOut,
    RamplaCreateNucleo,
    TractoCreateNucleo,
)
from app.nucleo.servicio_maestros import ServicioMaestros

router = APIRouter(prefix="/nucleo", tags=["nucleo-maestros"])


def get_servicio_lectura(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("maestros:leer")),
) -> ServicioMaestros:
    return ServicioMaestros(session, contexto)


def get_servicio_escritura(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("maestros:escribir")),
) -> ServicioMaestros:
    return ServicioMaestros(session, contexto)


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------
@router.get("/clientes", response_model=list[Cliente])
def listar_clientes(
    activo: bool | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    servicio: ServicioMaestros = Depends(get_servicio_lectura),
):
    return servicio.listar_clientes(activo=activo, q=q)


@router.post("/clientes", response_model=Cliente, status_code=status.HTTP_201_CREATED)
def crear_cliente(
    body: ClienteCreateNucleo,
    servicio: ServicioMaestros = Depends(get_servicio_escritura),
):
    return servicio.crear_cliente(body)


@router.put("/clientes/{cliente_id}", response_model=Cliente)
def actualizar_cliente(
    cliente_id: UUID,
    body: ClienteCreateNucleo,
    servicio: ServicioMaestros = Depends(get_servicio_escritura),
):
    return servicio.actualizar_cliente(cliente_id, body)


@router.delete("/clientes/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def desactivar_cliente(
    cliente_id: UUID,
    servicio: ServicioMaestros = Depends(get_servicio_escritura),
):
    servicio.desactivar_cliente(cliente_id)


# ---------------------------------------------------------------------------
# Tractos
# ---------------------------------------------------------------------------
@router.get("/tractos", response_model=list[Tracto])
def listar_tractos(
    activo: bool | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    servicio: ServicioMaestros = Depends(get_servicio_lectura),
):
    return servicio.listar_tractos(activo=activo, q=q)


@router.post("/tractos", response_model=Tracto, status_code=status.HTTP_201_CREATED)
def crear_tracto(
    body: TractoCreateNucleo,
    servicio: ServicioMaestros = Depends(get_servicio_escritura),
):
    return servicio.crear_tracto(body)


@router.put("/tractos/{tracto_id}", response_model=Tracto)
def actualizar_tracto(
    tracto_id: UUID,
    body: TractoCreateNucleo,
    servicio: ServicioMaestros = Depends(get_servicio_escritura),
):
    return servicio.actualizar_tracto(tracto_id, body)


@router.delete("/tractos/{tracto_id}", status_code=status.HTTP_204_NO_CONTENT)
def desactivar_tracto(
    tracto_id: UUID,
    servicio: ServicioMaestros = Depends(get_servicio_escritura),
):
    servicio.desactivar_tracto(tracto_id)


# ---------------------------------------------------------------------------
# Ramplas
# ---------------------------------------------------------------------------
@router.get("/ramplas", response_model=list[Rampla])
def listar_ramplas(
    activo: bool | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    servicio: ServicioMaestros = Depends(get_servicio_lectura),
):
    return servicio.listar_ramplas(activo=activo, q=q)


@router.post("/ramplas", response_model=Rampla, status_code=status.HTTP_201_CREATED)
def crear_rampla(
    body: RamplaCreateNucleo,
    servicio: ServicioMaestros = Depends(get_servicio_escritura),
):
    return servicio.crear_rampla(body)


@router.put("/ramplas/{rampla_id}", response_model=Rampla)
def actualizar_rampla(
    rampla_id: UUID,
    body: RamplaCreateNucleo,
    servicio: ServicioMaestros = Depends(get_servicio_escritura),
):
    return servicio.actualizar_rampla(rampla_id, body)


@router.delete("/ramplas/{rampla_id}", status_code=status.HTTP_204_NO_CONTENT)
def desactivar_rampla(
    rampla_id: UUID,
    servicio: ServicioMaestros = Depends(get_servicio_escritura),
):
    servicio.desactivar_rampla(rampla_id)


# ---------------------------------------------------------------------------
# Choferes
# ---------------------------------------------------------------------------
@router.get("/choferes", response_model=list[Chofer])
def listar_choferes(
    activo: bool | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    servicio: ServicioMaestros = Depends(get_servicio_lectura),
):
    return servicio.listar_choferes(activo=activo, q=q)


@router.post("/choferes", response_model=Chofer, status_code=status.HTTP_201_CREATED)
def crear_chofer(
    body: ChoferCreateNucleo,
    servicio: ServicioMaestros = Depends(get_servicio_escritura),
):
    return servicio.crear_chofer(body)


@router.put("/choferes/{chofer_id}", response_model=Chofer)
def actualizar_chofer(
    chofer_id: UUID,
    body: ChoferCreateNucleo,
    servicio: ServicioMaestros = Depends(get_servicio_escritura),
):
    return servicio.actualizar_chofer(chofer_id, body)


@router.delete("/choferes/{chofer_id}", status_code=status.HTTP_204_NO_CONTENT)
def desactivar_chofer(
    chofer_id: UUID,
    servicio: ServicioMaestros = Depends(get_servicio_escritura),
):
    servicio.desactivar_chofer(chofer_id)


# ---------------------------------------------------------------------------
# Documentos
# ---------------------------------------------------------------------------
@router.get("/documentos", response_model=list[DocumentoOutNucleo])
def listar_documentos(
    recurso_tipo: TipoRecurso = Query(...),
    recurso_id: UUID = Query(...),
    servicio: ServicioMaestros = Depends(get_servicio_lectura),
):
    return servicio.listar_documentos(recurso_tipo, recurso_id)


@router.post(
    "/documentos",
    response_model=DocumentoOutNucleo,
    status_code=status.HTTP_201_CREATED,
)
async def subir_documento(
    recurso_tipo: TipoRecurso = Form(...),
    recurso_id: UUID = Form(...),
    tipo: TipoDocumento = Form(...),
    numero: str | None = Form(default=None),
    entidad_emisora: str | None = Form(default=None),
    emitido_en: date | None = Form(default=None),
    vence_en: date = Form(...),
    observaciones: str | None = Form(default=None),
    archivo: UploadFile = File(...),
    servicio: ServicioMaestros = Depends(get_servicio_escritura),
):
    contenido = await archivo.read()
    return servicio.subir_documento(
        recurso_tipo=recurso_tipo,
        recurso_id=recurso_id,
        tipo=tipo,
        numero=numero,
        entidad_emisora=entidad_emisora,
        emitido_en=emitido_en,
        vence_en=vence_en,
        observaciones=observaciones,
        nombre_archivo=archivo.filename or "documento",
        contenido=contenido,
        content_type=archivo.content_type,
    )


@router.get("/documentos/{documento_id}/url", response_model=DocumentoUrlOut)
def url_documento(
    documento_id: UUID,
    servicio: ServicioMaestros = Depends(get_servicio_lectura),
):
    return servicio.url_documento(documento_id)
