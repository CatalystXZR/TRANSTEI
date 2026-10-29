"""API de POD y evidencia (P0-06)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlmodel import Session

from app.core.database import get_session
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.permisos import requiere_permiso
from app.nucleo.schemas import PODOut, PODUpdate
from app.nucleo.servicio_pod import ServicioPOD

router = APIRouter(prefix="/nucleo/expediente/viajes", tags=["nucleo-pod"])


def get_servicio_lectura(
    session: Session = Depends(get_session),
    contexto: ContextoEmpresa = Depends(requiere_permiso("pod:leer")),
) -> ServicioPOD:
    return ServicioPOD(session, contexto)


def get_servicio_escritura(
    session: Session = Depends(get_session),
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
    firma_contenido = await firma.read()
    fotos_leidas: list[tuple[str, bytes, str | None]] = []
    for foto in fotos or []:
        fotos_leidas.append(
            (
                foto.filename or "foto",
                await foto.read(),
                foto.content_type,
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
        firma_content_type=firma.content_type,
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
    firma_contenido = await firma.read() if firma is not None else None
    fotos_leidas: list[tuple[str, bytes, str | None]] = []
    for foto in fotos or []:
        fotos_leidas.append(
            (
                foto.filename or "foto",
                await foto.read(),
                foto.content_type,
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
        firma_content_type=firma.content_type if firma is not None else None,
        fotos=fotos_leidas,
    )
