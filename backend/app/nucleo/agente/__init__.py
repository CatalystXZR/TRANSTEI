"""Módulo agente WhatsApp — O2.1 (registry, gate y tools de lectura).

Punto de entrada:

    from app.nucleo.agente import cargar_registry, resolver_contacto

No importa la base ni carga el manifiesto al importar el paquete: `cargar_registry`
lo hace de forma perezosa y fail-closed.
"""

from app.nucleo.agente.contexto import (
    ContextoAgente,
    EstadoOtp,
    RolContacto,
    contexto_de_agente,
    normalizar_telefono,
    resolver_contacto,
)
from app.nucleo.agente.registry import Registry, cargar_registry

__all__ = [
    "ContextoAgente",
    "EstadoOtp",
    "Registry",
    "RolContacto",
    "cargar_registry",
    "contexto_de_agente",
    "normalizar_telefono",
    "resolver_contacto",
]
