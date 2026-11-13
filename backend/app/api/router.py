from fastapi import APIRouter

# Retiro legacy completado (Ola E, 2026-11): no queda ningún router de negocio
# fuera del núcleo. `auth` se conserva solo por `/auth/me`, que el shell
# consume para resolver la identidad del usuario.
from app.api.routes import auth
from app.nucleo.api import router as nucleo_router
from app.nucleo.agente.api import router as nucleo_agente_router
from app.nucleo.agente.api_contactos import router as nucleo_agente_contactos_router
from app.nucleo.agente.api_solicitudes import router as nucleo_agente_solicitudes_router
from app.nucleo.agente.chat.api import router as nucleo_agente_chat_router
from app.nucleo.agente.chat.api_configuracion import (
    router as nucleo_agente_configuracion_router,
)
from app.nucleo.api_alertas import router as nucleo_alertas_router
from app.nucleo.api_bloqueos import router as nucleo_bloqueos_router
from app.nucleo.api_comercial import router as nucleo_comercial_router
from app.nucleo.api_conductor import router as nucleo_conductor_router
from app.nucleo.api_expediente import router as nucleo_expediente_router
from app.nucleo.api_facturacion import router as nucleo_facturacion_router
from app.nucleo.api_gastos import router as nucleo_gastos_router
from app.nucleo.api_maestros import router as nucleo_maestros_router
from app.nucleo.api_permisos import router as nucleo_permisos_router
from app.nucleo.api_pod import router as nucleo_pod_router
from app.nucleo.api_rentabilidad import router as nucleo_rentabilidad_router

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(nucleo_router)
api_router.include_router(nucleo_agente_router)
api_router.include_router(nucleo_agente_contactos_router)
api_router.include_router(nucleo_agente_solicitudes_router)
api_router.include_router(nucleo_agente_chat_router)
api_router.include_router(nucleo_agente_configuracion_router)
api_router.include_router(nucleo_maestros_router)
api_router.include_router(nucleo_comercial_router)
api_router.include_router(nucleo_bloqueos_router)
api_router.include_router(nucleo_expediente_router)
api_router.include_router(nucleo_pod_router)
api_router.include_router(nucleo_conductor_router)
api_router.include_router(nucleo_gastos_router)
api_router.include_router(nucleo_rentabilidad_router)
api_router.include_router(nucleo_facturacion_router)
api_router.include_router(nucleo_alertas_router)
api_router.include_router(nucleo_permisos_router)
