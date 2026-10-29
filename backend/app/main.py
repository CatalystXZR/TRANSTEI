from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError

from app.api.router import api_router
from app.core.config import settings
from app.nucleo.errores import ErrorNucleo, manejador_error_nucleo
from app.nucleo.servicio_cutover import legacy_congelado
from app.nucleo.tiempo import ErrorTemporal

app = FastAPI(title=settings.PROJECT_NAME)

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
async def manejador_duplicados(request: Request, exc: IntegrityError):
    return JSONResponse(
        status_code=400,
        content={
            "detail": (
                "Ya existe un registro con esos datos (RUT o patente duplicada). "
                "Revise la información e intente nuevamente."
            )
        },
    )


@app.get("/", include_in_schema=False)
def raiz():
    """Este puerto es la API. Redirige a la aplicación web."""
    return RedirectResponse(url=settings.FRONTEND_URL)


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.PROJECT_NAME}
