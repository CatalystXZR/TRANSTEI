"""Pruebas unitarias del motor seguro de KPIs (sin base de datos)."""

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services import kpi_engine as ke


def test_aritmetica_basica():
    assert ke.evaluar_formula("2 + 3 * 4", {}) == 14
    assert ke.evaluar_formula("(2 + 3) * 4", {}) == 20
    assert ke.evaluar_formula("10 / 4", {}) == 2.5
    assert ke.evaluar_formula("10 % 3", {}) == 1
    assert ke.evaluar_formula("2 ** 3", {}) == 8


def test_metricas_y_porcentaje():
    valor = ke.evaluar_formula(
        "(ingresos_mes - gastos_mes) / ingresos_mes * 100",
        {"ingresos_mes": 1000, "gastos_mes": 250},
    )
    assert valor == pytest.approx(75.0)


def test_funcion_si_con_cortocircuito():
    # La rama no elegida NO debe evaluarse (evita división por cero)
    formula = "SI(ingresos_mes = 0, 0, margen_bruto / ingresos_mes * 100)"
    assert ke.evaluar_formula(formula, {"ingresos_mes": 0, "margen_bruto": 0}) == 0
    assert ke.evaluar_formula(formula, {"ingresos_mes": 100, "margen_bruto": 50}) == 50


def test_funciones_varias():
    assert ke.evaluar_formula("REDONDEAR(margen_pct, 1)", {"margen_pct": 33.333}) == 33.3
    assert ke.evaluar_formula("ROUND(2.7)", {}) == 3
    assert ke.evaluar_formula("MIN(a, b, c)", {"a": 5, "b": 1, "c": 3}) == 1
    assert ke.evaluar_formula("MAX(a, b)", {"a": 5, "b": 9}) == 9
    assert ke.evaluar_formula("ABS(0 - 7)", {}) == 7


def test_comparaciones_y_logica():
    assert ke.evaluar_formula("5 > 3", {}) == 1
    assert ke.evaluar_formula("3 >= 3", {}) == 1
    assert ke.evaluar_formula("2 = 2", {}) == 1
    assert ke.evaluar_formula("a > 1 Y b < 5", {"a": 2, "b": 3}) == 1
    assert ke.evaluar_formula("a > 1 O b > 5", {"a": 2, "b": 3}) == 1


def test_errores_controlados():
    with pytest.raises(ValueError):
        ke.evaluar_formula("ingresos_inexistente + 1", {"ingresos_mes": 1})
    with pytest.raises(ValueError):
        ke.evaluar_formula("ingresos_mes / 0", {"ingresos_mes": 1})
    with pytest.raises(ValueError):
        ke.evaluar_formula("", {})
    with pytest.raises(ValueError):
        ke.evaluar_formula("ingresos_mes +", {"ingresos_mes": 1})


def test_seguridad_no_ejecuta_codigo():
    for peligrosa in (
        "import os",
        "__import__('os').system('echo x')",
        "open('/etc/passwd')",
        "lambda: 1",
        "[x for x in range(3)]",
    ):
        with pytest.raises(ValueError):
            ke.evaluar_formula(peligrosa, {})


def test_color_para():
    reglas = [
        {"operador": "<", "valor": 10, "color": "rojo"},
        {"operador": "<", "valor": 20, "color": "amarillo"},
        {"operador": ">=", "valor": 20, "color": "verde"},
    ]
    assert ke.color_para(5, reglas) == "rojo"
    assert ke.color_para(15, reglas) == "amarillo"
    assert ke.color_para(30, reglas) == "verde"
    assert ke.color_para(30, None) == "gris"
    assert ke.color_para(30, []) == "gris"
    # regla malformada se ignora sin romper
    assert ke.color_para(30, [{"operador": "??", "valor": "x"}]) == "gris"


def test_nombres_y_validacion_metricas():
    assert ke.nombres_metricas("ingresos_mes + gastos_mes") == {"ingresos_mes", "gastos_mes"}
    # SI es función, no métrica
    assert "si" not in ke.nombres_metricas("SI(a = 1, a, 0)")
    with pytest.raises(ValueError):
        ke.validar_metricas("metrica_falsa", "global")
    ke.validar_metricas("ingresos_mes", "global")  # no lanza


# ---------------------------------------------------------------------------
# F-04 (2026-10-30): el dinero no pasa por float dentro del cálculo
# ---------------------------------------------------------------------------


class _SesionConChofer:
    """Sesión mínima: `metricas_viaje` solo hace `session.get(Chofer, id)`."""

    def __init__(self, porcentaje: Decimal):
        self._porcentaje = porcentaje

    def get(self, modelo, ident):
        return SimpleNamespace(porcentaje_produccion=self._porcentaje)


def test_metricas_viaje_no_pierde_centavos():
    """0.30 − 0.10 − comisión 10 % = 0.17 exacto, no 0.16999999999999998.

    El camino anterior (`float(viaje.valor_flete_neto)` + `flete * float(...)`)
    producía `0.16999999999999998`; el valor de dominio ahora es `Decimal`.
    """
    metricas = ke.metricas_viaje(
        _SesionConChofer(Decimal("0.10")),
        flete=0.3,
        gastos=0.1,
        chofer_id=uuid.uuid4(),
    )

    assert all(isinstance(v, Decimal) for v in metricas.values()), metricas
    assert metricas["flete_viaje"] == Decimal("0.3")
    assert metricas["gastos_viaje"] == Decimal("0.1")
    assert metricas["comision_viaje"] == Decimal("0.03")
    assert metricas["margen_viaje"] == Decimal("0.17")
    # La resta en float difiere: la prueba falla si alguien reintroduce float().
    assert metricas["margen_viaje"] != Decimal(str(0.3 - 0.1 - 0.3 * 0.1))
    assert float(metricas["margen_viaje_pct"]) == pytest.approx(56.6667, abs=1e-3)


def test_metricas_para_json_convierte_solo_en_el_borde():
    """El borde JSON sigue devolviendo `number` (contrato del frontend)."""
    salida = ke.metricas_para_json(
        {"margen_viaje": Decimal("0.17"), "flete_viaje": Decimal("100000.00")}
    )

    assert salida == {"margen_viaje": 0.17, "flete_viaje": 100000.0}
    assert all(isinstance(v, float) for v in salida.values())
