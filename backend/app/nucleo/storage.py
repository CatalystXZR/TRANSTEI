"""Acceso a Supabase Storage para archivos del núcleo.

El backend usa `service_role`; nunca expone la clave al navegador. Las rutas
devueltas se firman por tiempo limitado y se validan antes de entregarlas.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from app.core.config import settings
from app.nucleo.errores import DatosInvalidos, ErrorPersistencia

BUCKET = "respaldos"
MAX_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic"}


def validar_archivo(nombre: str, contenido: bytes) -> str:
    if not contenido:
        raise DatosInvalidos("El archivo está vacío.")
    if len(contenido) > MAX_BYTES:
        raise DatosInvalidos("El archivo no puede superar 10 MB.")
    ext = os.path.splitext(nombre)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise DatosInvalidos(
            "Formato no permitido. Use PDF, JPG, JPEG, PNG, WEBP o HEIC."
        )
    return ext


def cliente_storage():
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise ErrorPersistencia("Storage no configurado.")
    from supabase import create_client

    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def ruta_archivo(*partes: str, extension: str) -> str:
    limpios = [str(p).strip("/") for p in partes if p is not None]
    return "/".join(limpios) + f"/{uuid.uuid4().hex}{extension}"


def subir_archivo(
    path: str, contenido: bytes, content_type: str | None = None
) -> None:
    storage = cliente_storage()
    try:
        storage.storage.from_(BUCKET).upload(
            path,
            contenido,
            {"content-type": content_type or "application/octet-stream"},
        )
    except Exception as exc:  # pragma: no cover - depende de Storage
        raise ErrorPersistencia("No se pudo subir el archivo a Storage.") from exc


def url_firmada(path: str, expires_in: int = 3600) -> str:
    storage = cliente_storage()
    try:
        resultado: Any = storage.storage.from_(BUCKET).create_signed_url(
            path, expires_in
        )
    except Exception as exc:  # pragma: no cover - depende de Storage
        raise ErrorPersistencia("No se pudo generar el enlace del archivo.") from exc
    url = resultado.get("signedURL") if isinstance(resultado, dict) else None
    if not url:
        raise ErrorPersistencia("No se pudo generar el enlace del archivo.")
    return url


def eliminar_archivo(path: str) -> None:
    try:
        cliente_storage().storage.from_(BUCKET).remove([path])
    except Exception:
        # El registro no se creó; dejar el archivo huérfano es preferible a
        # ocultar el error original. La limpieza puede hacerse por job.
        pass
