from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError

from app.api.router import api_router
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


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
