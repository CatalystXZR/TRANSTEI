"""Tipos neutrales del paquete agente.

Viven aquí (y no en `ejecutores.py`) para romper el ciclo de imports:

    tools/*  ->  tipos
    ejecutores  ->  tools/*
    registry  ->  ejecutores, manifest, gate

`ResultadoTool` es lo único que un ejecutor devuelve. No incluye la sesión, ni
la transacción, ni el envelope: esos los controla el registry (contrato §3.4 y
§4.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ResultadoTool:
    """Resultado ya proyectado de un ejecutor.

    - `datos`: cumple el JSON Schema de salida declarado por el descriptor.
    - `filas`: número de elementos devueltos (`len(items)`), no el total.
    - `total`: filas que cumplen el filtro (puede ser mayor que `filas`).
    - `truncado`: `total > filas`. Se guarda en el envelope (`meta.truncado`)
      para que el runtime sepa si el modelo vio la lista completa. También es
      parte obligatoria del schema de salida de las tools de lectura, así que
      el ejecutor lo incluye en `datos`; aquí se duplica a propósito: el
      envelope no debe inferirlo de un diccionario que podría no traerlo.
    - `ids`: identificadores devueltos, solo para `datos_tocados` de auditoría.
    """

    datos: dict[str, Any]
    filas: int
    total: int
    truncado: bool
    ids: tuple[str, ...] = field(default=())
