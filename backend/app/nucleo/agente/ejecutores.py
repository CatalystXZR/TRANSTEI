"""Allow-list cerrada de ejecutores (contrato §3.4).

El manifiesto nombra un ejecutor por clave; **no** puede apuntar a un import
path, a una clase ni a una función arbitraria. Este diccionario es el único
puente entre configuración y código: si un descriptor declara una clave que no
está acá, la validación V10 invalida el manifiesto completo.

Agregar una tool de escritura exige, además, un ejecutor que no haga `commit()`
propio (§3.4, §4.10) y una revisión de seguridad, porque toca el buzón de
aprobación humana.
"""

from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType

from sqlmodel import Session

from app.nucleo.agente.contexto import ContextoAgente
from app.nucleo.agente.tipos import ResultadoTool
from app.nucleo.agente.tools.despacho import (
    despacho_mis_fletes,
    despacho_mis_viajes_asignados,
    despacho_viajes_del_dia,
)

EjecutorTool = Callable[
    [ContextoAgente, dict, "int | None", Session], ResultadoTool
]

EJECUTORES: MappingProxyType[str, EjecutorTool] = MappingProxyType(
    {
        "despacho_mis_fletes": despacho_mis_fletes,
        "despacho_mis_viajes_asignados": despacho_mis_viajes_asignados,
        "despacho_viajes_del_dia": despacho_viajes_del_dia,
    }
)
