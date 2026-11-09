"""Notificador WhatsApp para el OTP de enrolamiento.

Modos:
- `fake` (default local/tests): guarda el envío en una outbox en memoria. No
  sale a la red y el código solo es accesible desde pruebas; nunca se expone
  por la API ni se registra en logs.
- `meta`: adaptador pendiente de proveedor. Exige `WHATSAPP_API_URL`,
  `WHATSAPP_TOKEN` y `WHATSAPP_PHONE_ID`; sin ellos falla cerrado.

El envío real se conecta cuando el dueño elija proveedor (AB-04). El flujo de
negocio (generar, hashear, guardar, verificar) ya queda operativo.
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.nucleo.errores import ErrorPersistencia

logger = logging.getLogger(__name__)

# Solo se usa en modo `fake`. En producción no se llena.
_OUTBOX: list[dict[str, str]] = []


def enviar_otp(telefono: str, codigo: str) -> bool:
    """Envía el OTP por WhatsApp. Devuelve True si se encoló/entregó."""
    modo = (settings.WHATSAPP_MODE or "fake").strip().lower()

    if modo == "fake":
        _OUTBOX.append({"telefono": telefono, "codigo": codigo})
        logger.info("WhatsApp fake: OTP encolado para %s", telefono)
        return True

    if modo == "meta":
        if not (
            settings.WHATSAPP_API_URL
            and settings.WHATSAPP_TOKEN
            and settings.WHATSAPP_PHONE_ID
        ):
            raise ErrorPersistencia(
                "WhatsApp real no configurado: faltan WHATSAPP_API_URL, "
                "WHATSAPP_TOKEN o WHATSAPP_PHONE_ID."
            )
        # Punto de integración real (Meta Cloud API). Se deja explícito para no
        # fingir un envío: sin proveedor configurado, el flujo falla cerrado.
        raise ErrorPersistencia(
            "Adaptador WhatsApp 'meta' pendiente de implementación (AB-04)."
        )

    raise ErrorPersistencia(f"WHATSAPP_MODE inválido: {modo!r}.")


def outbox_fake() -> list[dict[str, str]]:
    """Copia de la outbox local. Solo para pruebas; no exponer por API."""
    return list(_OUTBOX)
