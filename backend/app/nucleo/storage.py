"""Acceso a Supabase Storage para archivos del núcleo.

El backend usa `service_role`; nunca expone la clave al navegador. Las rutas
devueltas se firman por tiempo limitado y se validan antes de entregarlas.
El formato se valida por **firma (magic bytes)**, no por la extensión ni por
el content-type declarado por el cliente (F0-05).
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import UploadFile

from app.core.config import settings
from app.nucleo.errores import DatosInvalidos, ErrorPersistencia

BUCKET = "respaldos"
MAX_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic"}

# Firma de los primeros bytes por formato. El tipo detectado manda: un archivo
# con firma PNG declarado como PDF se rechaza.
#
# SEC-018: la firma PDF exige `%PDF-` al inicio Y la marca de fin `%%EOF` dentro
# de los últimos `VENTANA_FIN_PDF` bytes. Con solo `%PDF` (3 bytes) bastaba
# para declarar "PDF" cualquier contenido arbitrario.
_FIRMA_PDF = b"%PDF-"
_MARCA_FIN_PDF = b"%%EOF"
VENTANA_FIN_PDF = 2048
_FIRMA_JPEG = b"\xff\xd8\xff"
_FIRMA_PNG = b"\x89PNG\r\n\x1a\n"

# Content-type canónico fijado por el servidor, nunca tomado del cliente.
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
}

# Subconjunto de formatos que son imágenes (firma del POD, comprobantes).
CONTENT_TYPES_IMAGEN = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/heic"}
)
EXTENSIONES_IMAGEN = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic"})


def firma_pdf_valida(contenido: bytes) -> bool:
    """PDF real: `%PDF-` al inicio y `%%EOF` en la cola acotada del archivo."""
    return contenido.startswith(_FIRMA_PDF) and (
        _MARCA_FIN_PDF in contenido[-VENTANA_FIN_PDF:]
    )


def firma_valida(ext: str, contenido: bytes) -> bool:
    """¿Los primeros bytes corresponden al formato declarado por la extensión?"""
    if ext in {".jpg", ".jpeg"}:
        return contenido.startswith(_FIRMA_JPEG)
    if ext == ".png":
        return contenido.startswith(_FIRMA_PNG)
    if ext == ".pdf":
        return firma_pdf_valida(contenido)
    if ext == ".webp":
        # RIFF....WEBP: los bytes 8-11 identifican el subtipo dentro de RIFF.
        return (
            len(contenido) >= 12
            and contenido.startswith(b"RIFF")
            and contenido[8:12] == b"WEBP"
        )
    if ext == ".heic":
        # ISO BMFF: caja de tamaño (4 bytes) seguida de "ftyp".
        return len(contenido) >= 12 and contenido[4:8] == b"ftyp"
    return False


def content_type_para(ext: str) -> str:
    """Content-type canónico para una extensión validada."""
    return CONTENT_TYPES[ext]


def detectar_content_type(contenido: bytes) -> str | None:
    """Detecta el content-type por firma; None si no coincide con ninguno."""
    if contenido.startswith(_FIRMA_PNG):
        return "image/png"
    if contenido.startswith(_FIRMA_JPEG):
        return "image/jpeg"
    if firma_pdf_valida(contenido):
        return "application/pdf"
    if (
        len(contenido) >= 12
        and contenido.startswith(b"RIFF")
        and contenido[8:12] == b"WEBP"
    ):
        return "image/webp"
    if len(contenido) >= 12 and contenido[4:8] == b"ftyp":
        return "image/heic"
    return None


def es_imagen(content_type: str | None) -> bool:
    """¿El content-type detectado pertenece a un formato de imagen aceptado?"""
    return content_type in CONTENT_TYPES_IMAGEN


def detectar_content_type_imagen(contenido: bytes) -> str | None:
    """Detecta el content-type solo si el contenido es una imagen aceptada."""
    ct = detectar_content_type(contenido)
    return ct if es_imagen(ct) else None


async def leer_archivo_acotado(archivo: UploadFile, max_bytes: int = MAX_BYTES) -> bytes:
    """Lee un UploadFile en trozos, acotado a `max_bytes` (sin exceder la memoria)."""
    trozos: list[bytes] = []
    total = 0
    while True:
        trozo = await archivo.read(min(64 * 1024, max_bytes + 1 - total))
        if not trozo:
            break
        trozos.append(trozo)
        total += len(trozo)
        if total > max_bytes:
            raise DatosInvalidos(
                f"El archivo no puede superar {max_bytes // (1024 * 1024)} MB."
            )
    return b"".join(trozos)


def leer_archivo_acotado_sync(
    archivo: UploadFile, max_bytes: int = MAX_BYTES
) -> bytes:
    """Igual que `leer_archivo_acotado` para rutas legacy síncronas (SEC-019)."""
    trozos: list[bytes] = []
    total = 0
    while True:
        trozo = archivo.file.read(min(64 * 1024, max_bytes + 1 - total))
        if not trozo:
            break
        trozos.append(trozo)
        total += len(trozo)
        if total > max_bytes:
            raise DatosInvalidos(
                f"El archivo no puede superar {max_bytes // (1024 * 1024)} MB."
            )
    return b"".join(trozos)


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
    if not firma_valida(ext, contenido):
        raise DatosInvalidos(
            "El contenido del archivo no corresponde al formato indicado por "
            "la extensión. Suba un archivo PDF, JPG, JPEG, PNG, WEBP o HEIC válido."
        )
    return ext


def validar_imagen(
    nombre: str,
    contenido: bytes,
    *,
    max_bytes: int = MAX_BYTES,
    extensiones: frozenset[str] = EXTENSIONES_IMAGEN,
    etiqueta: str = "La imagen",
) -> tuple[str, str]:
    """Valida que el contenido sea una imagen real y devuelve (extensión, CT).

    El content-type lo determina la firma del contenido, no la extensión ni el
    header declarado por el cliente (SEC-018 / hallazgo POD de qa).
    """
    if not contenido:
        raise DatosInvalidos(f"{etiqueta} está vacía.")
    if len(contenido) > max_bytes:
        raise DatosInvalidos(
            f"{etiqueta} no puede superar {max_bytes // (1024 * 1024)} MB."
        )
    ext = os.path.splitext(nombre)[1].lower()
    if ext not in extensiones:
        permitidas = ", ".join(sorted(e.lstrip(".").upper() for e in extensiones))
        raise DatosInvalidos(f"Formato no permitido. Use {permitidas}.")
    content_type = detectar_content_type_imagen(contenido)
    if content_type is None:
        raise DatosInvalidos(
            "El contenido del archivo no es una imagen válida "
            "(PNG, JPG, JPEG, WEBP o HEIC)."
        )
    return ext, content_type


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
