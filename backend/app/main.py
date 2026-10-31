from __future__ import annotations

import json
import re

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.api.router import api_router
from app.core.config import settings
from app.core.contexto import contexto_de_request, limpiar_request_id
from app.nucleo.errores import (
    ErrorNucleo,
    _sqlstate,
    manejador_error_nucleo,
    traducir_integrity_error,
)
from app.nucleo.servicio_cutover import legacy_congelado
from app.nucleo.servicio_pod import MAX_FIRMA_BYTES, MAX_FOTOS
from app.nucleo.storage import MAX_BYTES
from app.nucleo.tiempo import ErrorTemporal

# ============================================================================
# SEC-021 — tope de cuerpo a nivel de transporte
# ============================================================================
# FastAPI 0.115 evalúa `request.form()` ANTES de resolver las dependencias de
# auth (fastapi/routing.py:247 vs :291) y Starlette 0.46 spool-ea los archivos
# a disco con `max_files=1000` (formparsers.py:135). Un POST gigante sin token
# consume disco/RAM antes de recibir el 401. Este middleware es ASGI puro: se
# ejecuta antes del parseo, no lee el cuerpo cuando `Content-Length` delata el
# exceso y cuenta los bytes reales cuando el cliente usa chunked.
#
# Cotas (documentadas en docs/backend/informes/f1-ola4-infra.md):
#   · global 32 MB: cubre el documento de 10 MB (`storage.MAX_BYTES`) con
#     margen para multipart y cuerpos JSON del núcleo;
#   · POD 106 MB: `MAX_FOTOS(10) × MAX_BYTES(10 MB) + MAX_FIRMA_BYTES(5 MB) +
#     1 MB` de holgura multipart. No es una regla de negocio nueva: reproduce
#     el tope que ya aceptan `api_pod.py` y `servicio_pod.py`. Sin esta
#     excepción, un POD legítimo con 4+ fotos de 10 MB pasaría a 413.
LIMITE_CUERPO_BYTES = 32 * 1024 * 1024
LIMITE_CUERPO_POD_BYTES = (
    MAX_FOTOS * MAX_BYTES + MAX_FIRMA_BYTES + 1024 * 1024
)

_RUTA_POD = re.compile(
    rf"^{re.escape(settings.API_V1_PREFIX)}/nucleo/expediente/viajes/[^/]+/pod$"
)


def limite_para_cuerpo(path: str) -> int:
    """Cota de cuerpo aplicable a `path` (por defecto la global)."""
    return LIMITE_CUERPO_POD_BYTES if _RUTA_POD.match(path) else LIMITE_CUERPO_BYTES


class CuerpoExceso(Exception):
    """Se lanza desde el `receive` envuelto al superar la cota sin Content-Length."""

    def __init__(self, limite: int) -> None:
        super().__init__(f"cuerpo excede {limite} bytes")
        self.limite = limite


async def _responder_cuerpo_exceso(send, limite: int) -> None:
    cuerpo = json.dumps(
        {
            "codigo": "CUERPO_EXCESO",
            "mensaje": (
                "El cuerpo del request supera el máximo permitido "
                f"({limite // (1024 * 1024)} MB)."
            ),
        }
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(cuerpo)).encode()),
                # El cuerpo no se drena: cerrar evita reutilizar una conexión
                # con bytes pendientes (desincronización HTTP).
                (b"connection", b"close"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": cuerpo})


class LimiteCuerpoMiddleware:
    """ASGI puro: rechaza cuerpos sobre la cota antes de cualquier parseo."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limite = limite_para_cuerpo(scope.get("path", ""))
        declarado = _content_length(scope)
        if declarado is not None and declarado > limite:
            await _responder_cuerpo_exceso(send, limite)
            return

        recibido = 0
        respuesta_iniciada = False

        async def receive_acotado():
            nonlocal recibido
            mensaje = await receive()
            if mensaje.get("type") == "http.request":
                recibido += len(mensaje.get("body", b""))
                if recibido > limite:
                    raise CuerpoExceso(limite)
            return mensaje

        async def send_seguido(mensaje):
            nonlocal respuesta_iniciada
            if mensaje.get("type") == "http.response.start":
                respuesta_iniciada = True
            await send(mensaje)

        try:
            await self.app(scope, receive_acotado, send_seguido)
        except CuerpoExceso:
            if respuesta_iniciada:
                # Ya se comprometió el status: no se puede reescribir.
                raise
            await _responder_cuerpo_exceso(send, limite)


def _content_length(scope) -> int | None:
    for nombre, valor in scope.get("headers", []):
        if nombre == b"content-length":
            try:
                return int(valor)
            except ValueError:
                return None
    return None


class ContextoRequestMiddleware:
    """Abre y limpia el contexto de request (empresa/auth/request_id).

    El valor lo rellena `get_contexto_empresa` tras verificar la membresía; el
    GUC se reaplica en cada transacción (`app/core/database.py`). Al terminar
    el request el `ContextVar` se resetea: no hay herencia entre requests.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        with contexto_de_request(request_id=_request_id(scope)):
            await self.app(scope, receive, send)


def _request_id(scope) -> str | None:
    for nombre, valor in scope.get("headers", []):
        if nombre == b"x-request-id":
            return limpiar_request_id(valor.decode("latin-1", "replace"))
    return None


app = FastAPI(title=settings.PROJECT_NAME)

# Pila de middlewares, de afuera hacia adentro (el último `add_middleware`
# queda más afuera): congelar-legacy → CORS → tope de cuerpo → contexto →
# router. El tope queda dentro de CORS para que el 413 lleve sus headers.
app.add_middleware(ContextoRequestMiddleware)
app.add_middleware(LimiteCuerpoMiddleware)

app.add_exception_handler(ErrorNucleo, manejador_error_nucleo)


@app.exception_handler(ErrorTemporal)
async def manejador_error_temporal(request: Request, exc: ErrorTemporal):
    return JSONResponse(
        status_code=422,
        content={"codigo": "FECHA_INVALIDA", "mensaje": str(exc)},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.middleware("http")
async def congelar_escritura_legacy(request: Request, call_next):
    """Bloquea escrituras legacy cuando el cutover está congelado.

    El schema `nucleo` y el login siguen operativos. Las lecturas legacy no se
    bloquean para permitir consultas de contingencia.
    """
    path = request.url.path
    prefijo = settings.API_V1_PREFIX
    es_legacy = (
        path.startswith(prefijo)
        and not path.startswith(f"{prefijo}/nucleo")
        and not path.startswith(f"{prefijo}/auth")
    )
    if request.method not in {"GET", "HEAD", "OPTIONS"} and es_legacy and legacy_congelado():
        return JSONResponse(
            status_code=409,
            content={
                "codigo": "CUTOVER_LEGACY_CONGELADO",
                "mensaje": (
                    "La escritura legacy está congelada por el cutover. "
                    "Use el módulo del núcleo o descongele desde /nucleo/cutover."
                ),
            },
        )
    return await call_next(request)


@app.exception_handler(IntegrityError)
async def manejador_integrity_error(request: Request, exc: IntegrityError):
    """Traduce violaciones de PostgreSQL a códigos HTTP de dominio.

    AGENTS.md §8: nunca un 500 por conflicto de negocio ni el mensaje crudo de
    PostgreSQL al cliente. Mapeo por sqlstate:
    - 23505 / 23P01 → 409 (duplicado / conflicto de disponibilidad);
    - 23514 / 23502 / 23503 → 422 (regla de dominio / campo obligatorio /
      referencia inexistente);
    - cualquier otro → 500 con mensaje genérico (el detalle queda en el log).
    """
    import logging

    logger = logging.getLogger("app.main.integrity")
    state = _sqlstate(exc)
    if state in {"23505", "23P01"}:
        error = traducir_integrity_error(exc)
        return JSONResponse(
            status_code=error.status_code,
            content={"codigo": error.codigo, "detail": error.mensaje},
        )
    if state in {"23514", "23502", "23503"}:
        logger.warning("IntegrityError traducido a 422 (sqlstate=%s).", state)
        return JSONResponse(
            status_code=422,
            content={
                "codigo": "DATOS_INVALIDOS",
                "detail": (
                    "Los datos enviados violan una regla de integridad de la "
                    "base de datos. Revise los valores e intente nuevamente."
                ),
            },
        )
    # Nunca `repr(exc)`: el mensaje de SQLAlchemy arrastra la sentencia y los
    # parámetros ligados, que pueden contener datos personales o financieros
    # (AGENTS.md §4; hallazgo SEC-038).
    logger.error(
        "IntegrityError sin traducción específica sqlstate=%s tipo=%s",
        state,
        type(exc.orig).__name__ if exc.orig is not None else type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={
            "codigo": "ERROR_INTEGRIDAD",
            "detail": "No fue posible guardar la operación. El cambio fue revertido.",
        },
    )


@app.exception_handler(ProgrammingError)
async def manejador_programming_error(request: Request, exc: ProgrammingError):
    """Traduce `42501` (RLS/GRANT) a 403; el resto a 500 genérico.

    Contrato del conector §4.6: `InsufficientPrivilege` llega como
    `sqlalchemy.exc.ProgrammingError`, **no** como `IntegrityError`, así que no
    pasa por `manejador_integrity_error`. Antes de este handler quedaba sin
    traducción y salía 500 por el manejador por defecto.
    """
    import logging

    logger = logging.getLogger("app.main.programming")
    state = _sqlstate(exc)
    if state == "42501":
        logger.warning("ProgrammingError 42501 traducido a 403 (RLS/GRANT).")
        return JSONResponse(
            status_code=403,
            content={
                "codigo": "ACCESO_DENEGADO",
                "detail": (
                    "La operación no está permitida para el rol de base de datos."
                ),
            },
        )
    # Nunca se registra `repr(exc)`: en SQLAlchemy el repr de un
    # `StatementError` incluye el SQL y los parámetros ligados, que pueden
    # contener datos personales o financieros (AGENTS.md §4).
    logger.error(
        "ProgrammingError sin traducción sqlstate=%s tipo=%s",
        state,
        type(exc.orig).__name__ if exc.orig is not None else type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={
            "codigo": "ERROR_BASE_DATOS",
            "detail": "No fue posible completar la operación.",
        },
    )


@app.get("/", include_in_schema=False)
def raiz():
    """Este puerto es la API. Redirige a la aplicación web."""
    return RedirectResponse(url=settings.FRONTEND_URL)


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.PROJECT_NAME}
