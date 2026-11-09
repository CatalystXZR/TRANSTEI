"""Modelos del turno LLM (dataclasses, sin dependencias del proveedor).

Se separan de los schemas HTTP y de las filas de la base a propósito:

- `MensajeLLM` es el formato de conversación que consume el cliente del LLM;
- `LlamadaHerramienta` es una `tool_call` ya parseada;
- `RespuestaLLM` es lo que devuelve el proveedor en un turno.

`argumentos` es un `dict` (no el string JSON crudo): la conversión y su
validación ocurren en `llm.py`, donde un JSON inválido se traduce a un error de
dominio (502) y no a un `ValueError` que escape al cliente.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LlamadaHerramienta:
    id: str
    nombre: str
    argumentos: dict[str, Any] = field(default_factory=dict)

    def a_openai(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.nombre,
                "arguments": json.dumps(
                    self.argumentos, ensure_ascii=False, sort_keys=True
                ),
            },
        }


@dataclass(slots=True)
class MensajeLLM:
    role: str
    content: str | None = None
    tool_calls: list[LlamadaHerramienta] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None

    def a_openai(self) -> dict[str, Any]:
        mensaje: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            mensaje["tool_calls"] = [c.a_openai() for c in self.tool_calls]
        if self.tool_call_id is not None:
            mensaje["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            mensaje["name"] = self.name
        return mensaje


@dataclass(slots=True)
class RespuestaLLM:
    contenido: str | None = None
    llamadas: list[LlamadaHerramienta] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
