"""Contrato de `pregunta_resumida` (SEC-033, contrato §7.3.1).

Caso 6 del contrato (mutación) se cubre en la prueba de integración: aquí se
prueba la función pura y su criterio de descarte.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.nucleo.agente.ejecutores import EJECUTORES
from app.nucleo.agente.manifest import RAIZ_PAQUETE, cargar_modulo
from app.nucleo.agente.registry import _nombre_seguro, _pregunta_resumida

_MODULO = cargar_modulo(RAIZ_PAQUETE, EJECUTORES)
_DESCRIPTOR = _MODULO.descriptores["despacho.mis_fletes"]
_SCHEMA = _MODULO.esquemas_entrada["despacho.mis_fletes"]


def _pregunta(explicita: str | None, entrada: dict[str, Any] | None = None) -> str:
    return _pregunta_resumida(
        _nombre_seguro("despacho.mis_fletes"),
        {"limite": 1} if entrada is None else entrada,
        explicita,
        descriptor=_DESCRIPTOR,
        schema=_SCHEMA,
    )


def test_caso_1_texto_libre_con_telefono_se_descarta() -> None:
    """Un teléfono entregado por el llamador nunca llega a la fila."""
    valor = _pregunta("+56912345678")
    assert valor == "despacho.mis_fletes [limite]"
    assert "5691" not in valor


def test_caso_2_forma_canonica_valida_se_conserva() -> None:
    assert _pregunta("despacho.mis_fletes [limite,estado]") == (
        "despacho.mis_fletes [limite,estado]"
    )


def test_caso_3_clave_no_declarada_cae_a_derivacion() -> None:
    assert _pregunta("despacho.mis_fletes [telefono]") == "despacho.mis_fletes [limite]"


def test_caso_4_none_deriva() -> None:
    assert _pregunta(None, {"limite": 1, "estado": "en_ruta"}) == (
        "despacho.mis_fletes [estado,limite]"
    )


def test_caso_5_tool_desconocida_solo_nombre_saneado() -> None:
    valor = _pregunta_resumida(
        _nombre_seguro("despacho.inventada"),
        {"secreto": "x"},
        "cualquier texto libre",
        descriptor=None,
        schema=None,
    )
    assert valor == "despacho.inventada"
    assert "texto libre" not in valor


def test_derivacion_filtra_claves_no_declaradas() -> None:
    """Una entrada inválida no deja su clave inventada en la auditoría."""
    valor = _pregunta(None, {"limite": 1, "cliente_id": "otro"})
    assert valor == "despacho.mis_fletes [limite]"
    assert "cliente_id" not in valor


@pytest.mark.parametrize(
    "valor",
    [
        "despacho.otra [limite]",          # herramienta distinta
        "despacho.mis_fletes [Límite]",    # forma no canónica
        "despacho.mis_fletes [limite] " + "x" * 300,  # demasiado largo
        "texto sin corchetes",
    ],
)
def test_valores_no_conformes_siempre_derivan(valor: str) -> None:
    assert _pregunta(valor) == "despacho.mis_fletes [limite]"
