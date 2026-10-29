from decimal import Decimal

import pytest

from app.nucleo.models import ModalidadTarifa
from app.nucleo.tarifas import ErrorTarifa, calcular_flete


def test_tarifa_por_viaje_es_flat():
    assert (
        calcular_flete(
            modalidad=ModalidadTarifa.viaje,
            precio_unitario=Decimal("450000"),
            minimo_cobro=Decimal("0"),
        )
        == Decimal("450000.00")
    )


def test_tarifa_por_km():
    assert (
        calcular_flete(
            modalidad=ModalidadTarifa.km,
            precio_unitario=Decimal("1000"),
            minimo_cobro=Decimal("0"),
            distancia_km=Decimal("500"),
        )
        == Decimal("500000.00")
    )


def test_tarifa_por_tonelada():
    assert (
        calcular_flete(
            modalidad=ModalidadTarifa.tonelada,
            precio_unitario=Decimal("30000"),
            minimo_cobro=Decimal("0"),
            peso_bruto_kg=Decimal("25000"),
        )
        == Decimal("750000.00")
    )


def test_tarifa_por_tonelada_km():
    assert (
        calcular_flete(
            modalidad=ModalidadTarifa.tonelada_km,
            precio_unitario=Decimal("1000"),
            minimo_cobro=Decimal("0"),
            peso_bruto_kg=Decimal("25000"),
            distancia_km=Decimal("500"),
        )
        == Decimal("12500000.00")
    )


def test_tarifa_por_hora():
    assert (
        calcular_flete(
            modalidad=ModalidadTarifa.hora,
            precio_unitario=Decimal("50000"),
            minimo_cobro=Decimal("0"),
            tiempo_estimado_h=Decimal("5"),
        )
        == Decimal("250000.00")
    )


def test_tarifa_por_contenedor():
    assert (
        calcular_flete(
            modalidad=ModalidadTarifa.contenedor,
            precio_unitario=Decimal("100000"),
            minimo_cobro=Decimal("0"),
            cantidad_contenedores=2,
        )
        == Decimal("200000.00")
    )


def test_minimo_de_cobro():
    assert (
        calcular_flete(
            modalidad=ModalidadTarifa.viaje,
            precio_unitario=Decimal("10000"),
            minimo_cobro=Decimal("50000"),
        )
        == Decimal("50000.00")
    )


def test_km_sin_distancia_falla():
    with pytest.raises(ErrorTarifa):
        calcular_flete(
            modalidad=ModalidadTarifa.km,
            precio_unitario=Decimal("1000"),
            minimo_cobro=Decimal("0"),
        )


def test_modalidad_mixta_no_se_inventa():
    with pytest.raises(ErrorTarifa):
        calcular_flete(
            modalidad=ModalidadTarifa.mixta,
            precio_unitario=Decimal("1000"),
            minimo_cobro=Decimal("0"),
        )
