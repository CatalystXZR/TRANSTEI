"""Muro de pago de módulos premium del chat.

El catálogo es **código**, no base: la plataforma decide qué módulos existen y
con qué `modulo_id` (este paquete no crea módulos ni precios). Un módulo premium
queda activo solo si se cumplen **las dos** condiciones:

1. `nucleo.modulos_empresa.habilitado` para `(empresa, modulo_id)`;
2. una `nucleo.tenant_suscripciones` con `estado='activa'`, vigente y
   `plan_codigo` dentro de `AGENTE_PLANES_PREMIUM`.

`tei_app` solo **lee** `modulos_empresa` (la escritura se revocó en 0029): la
activación es de plataforma. Por eso este servicio nunca enciende el flag; solo
informa el estado y el mensaje de upsell.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import DatosInvalidos

MODULOS: dict[str, dict[str, Any]] = {
    "whatsapp": {"modulo_id": "agente-whatsapp", "plan_requerido": True},
    "finanzas_pro": {"modulo_id": "finanzas-pro", "plan_requerido": True},
}

_MENSAJE_UPSELL = (
    "El módulo '{modulo}' requiere un plan premium activo. "
    "Solicítalo al administrador de la plataforma para habilitarlo."
)


def estado(
    session: Session, contexto: ContextoEmpresa, modulo: str
) -> dict[str, Any]:
    """`{activo, motivo, mensaje_upsell, modulo}` para un módulo del catálogo."""
    definicion = MODULOS.get(modulo)
    if definicion is None:
        raise DatosInvalidos(
            "Módulo no reconocido.",
            contexto={"modulos": sorted(MODULOS)},
        )

    if not definicion["plan_requerido"]:
        return {
            "modulo": modulo,
            "activo": True,
            "motivo": "sin_plan",
            "mensaje_upsell": None,
        }

    habilitado = session.execute(
        text(
            """
            select 1
              from nucleo.modulos_empresa
             where empresa_id = :empresa_id
               and modulo_id = :modulo_id
               and habilitado
             limit 1
            """
        ),
        {
            "empresa_id": contexto.empresa_id,
            "modulo_id": definicion["modulo_id"],
        },
    ).first() is not None

    planes = settings.planes_premium_list
    suscripcion = False
    if planes:
        suscripcion = session.execute(
            text(
                """
                select 1
                  from nucleo.tenant_suscripciones
                 where empresa_id = :empresa_id
                   and estado = 'activa'
                   and vigente_desde <= now()
                   and (vigente_hasta is null or vigente_hasta > now())
                   and plan_codigo = any(cast(:planes as text[]))
                 limit 1
                """
            ),
            {"empresa_id": contexto.empresa_id, "planes": planes},
        ).first() is not None

    if habilitado and suscripcion:
        return {
            "modulo": modulo,
            "activo": True,
            "motivo": "activo",
            "mensaje_upsell": None,
        }

    motivo = "sin_suscripcion" if not suscripcion else "modulo_deshabilitado"
    return {
        "modulo": modulo,
        "activo": False,
        "motivo": motivo,
        "mensaje_upsell": _MENSAJE_UPSELL.format(modulo=modulo),
    }
