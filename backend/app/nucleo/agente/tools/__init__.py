"""Ejecutores del módulo agente, uno por archivo de componente."""

from app.nucleo.agente.tools.despacho import (
    despacho_mis_fletes,
    despacho_mis_viajes_asignados,
    despacho_viajes_del_dia,
)

__all__ = [
    "despacho_mis_fletes",
    "despacho_mis_viajes_asignados",
    "despacho_viajes_del_dia",
]
