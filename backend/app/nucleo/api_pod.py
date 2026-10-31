"""API de POD y evidencia (P0-06)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlmodel import Session

from app.core.database import get_session_nucleo
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import DatosInvalidos
from app.nucleo.permisos import requiere_permiso
from app.nucleo.schemas import PODOut, PODUpdate
from app.nucleo.servicio_pod import MAX_FOTOS, ServicioPOD
from app.nucleo.storage import (
    MAX_BYTES,
    detectar_content_type,
    detectar_content_type_imagen,
    leer_archivo_acotado,
)

router = APIRouter(prefix="/nucleo/expediente/viajes", tags=["nucleo-pod"])

MAX_FIRMA_BYTES = 5 * 1024 * 1024


def _validar_cantidad_fotos(fotos: list[UploadFile] | None) -> None:
    """SEC-023: corta por CANTIDAD antes de leer un solo byte de las fotos.

    FastAPI ya bufferizó el multipart (SEC-021, ver informe), pero leer cientos
    de fotos de 10 MB a memoria en `leer_archivo_acotado` es lo que agotaba el
    worker. `MAX_FOTOS` es la misma constante que revalida `servicio_pod`.
    """
    if fotos and len(fotos) > MAX_FOTOS:
        raise DatosInvalidos(
            f"El POD admite como máximo {MAX_FOTOS} fotos por envío; "
            f"se recibieron {len(fotos)}."
        )


def get_servicio_lectura(
    session: Session = Depends(get_session_nucleo),
    contexto: ContextoEmpresa = Depends(requiere_permiso("pod:leer")),
) -> ServicioPOD:
    return ServicioPOD(session, contexto)


def get_servicio_escritura(
    session: Session = Depends(get_session_nucleo),
    contexto: ContextoEmpresa = Depends(requiere_permiso("pod:escribir")),
) -> ServicioPOD:
    return ServicioPOD(session, contexto)


@router.get("/{viaje_id}/pod", response_model=PODOut | None)
def obtener_pod(
    viaje_id: UUID,
    servicio: ServicioPOD = Depends(get_servicio_lectura),
):
    return servicio.obtener(viaje_id)


@router.post(
    "/{viaje_id}/pod", response_model=PODOut, status_code=status.HTTP_201_CREATED
)
async def crear_pod(
    viaje_id: UUID,
    receptor_nombre: str = Form(...),
    receptor_rut: str | None = Form(default=None),
    receptor_cargo: str | None = Form(default=None),
    fecha_hora: datetime | None = Form(default=None),
    lat: Decimal | None = Form(default=None),
    lon: Decimal | None = Form(default=None),
    danios: str | None = Form(default=None),
    observaciones: str | None = Form(default=None),
    firma: UploadFile = File(...),
    fotos: list[UploadFile] | None = File(default=None),
    servicio: ServicioPOD = Depends(get_servicio_escritura),
):
    _validar_cantidad_fotos(fotos)
    firma_contenido = await leer_archivo_acotado(firma, MAX_FIRMA_BYTES)
    # La firma es SOLO imagen: el PDF/HEIC renombrado .jpg se rechaza acá y en
    # el servicio (`_validar_firma`), que vuelve a validar por firma detectada.
    firma_content_type = detectar_content_type_imagen(firma_contenido)
    if firma_content_type is None:
        raise DatosInvalidos(
            "La firma no es una imagen válida (PNG, JPG, JPEG o WEBP)."
        )
    fotos_leidas: list[tuple[str, bytes, str | None]] = []
    for foto in fotos or []:
        contenido = await leer_archivo_acotado(foto, MAX_BYTES)
        fotos_leidas.append(
            (
                foto.filename or "foto",
                contenido,
                detectar_content_type(contenido),
            )
        )
    return servicio.crear(
        viaje_id,
        receptor_nombre=receptor_nombre,
        receptor_rut=receptor_rut,
        receptor_cargo=receptor_cargo,
        fecha_hora=fecha_hora,
        lat=lat,
        lon=lon,
        danios=danios,
        observaciones=observaciones,
        firma_nombre=firma.filename or "firma.png",
        firma_contenido=firma_contenido,
        firma_content_type=firma_content_type,
        fotos=fotos_leidas,
    )


@router.put("/{viaje_id}/pod", response_model=PODOut)
async def actualizar_pod(
    viaje_id: UUID,
    receptor_nombre: str = Form(...),
    receptor_rut: str | None = Form(default=None),
    receptor_cargo: str | None = Form(default=None),
    fecha_hora: datetime | None = Form(default=None),
    lat: Decimal | None = Form(default=None),
    lon: Decimal | None = Form(default=None),
    danios: str | None = Form(default=None),
    observaciones: str | None = Form(default=None),
    version: int | None = Form(default=None),
    firma: UploadFile | None = File(default=None),
    fotos: list[UploadFile] | None = File(default=None),
    servicio: ServicioPOD = Depends(get_servicio_escritura),
):
    _validar_cantidad_fotos(fotos)
    firma_contenido = (
        await leer_archivo_acotado(firma, MAX_FIRMA_BYTES) if firma is not None else None
    )
    firma_content_type = (
        detectar_content_type_imagen(firma_contenido)
        if firma_contenido is not None
        else None
    )
    if firma is not None and firma_content_type is None:
        raise DatosInvalidos(
            "La firma no es una imagen válida (PNG, JPG, JPEG o WEBP)."
        )
    fotos_leidas: list[tuple[str, bytes, str | None]] = []
    for foto in fotos or []:
        contenido = await leer_archivo_acotado(foto, MAX_BYTES)
        fotos_leidas.append(
            (
                foto.filename or "foto",
                contenido,
                detectar_content_type(contenido),
            )
        )
    return servicio.actualizar(
        viaje_id,
        PODUpdate(
            receptor_nombre=receptor_nombre,
            receptor_rut=receptor_rut,
            receptor_cargo=receptor_cargo,
            fecha_hora=fecha_hora,
            lat=lat,
            lon=lon,
            danios=danios,
            observaciones=observaciones,
            version=version,
        ),
        firma_nombre=firma.filename if firma is not None else None,
        firma_contenido=firma_contenido,
        firma_content_type=firma_content_type,
        fotos=fotos_leidas,
    )
