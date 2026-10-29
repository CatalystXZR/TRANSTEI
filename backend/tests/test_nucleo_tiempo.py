from datetime import date, datetime, timedelta, timezone

import pytest
from app.nucleo.tiempo import (
    ErrorTemporal,
    Intervalo,
    calcular_libre_desde,
    inicio_dia_local,
    inicio_operativo_posible,
    solapamientos,
)

UTC = timezone.utc


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def test_rechaza_datetime_naive():
    with pytest.raises(ErrorTemporal):
        calcular_libre_desde(datetime(2026, 11, 1, 8, 0), [])

    with pytest.raises(ErrorTemporal):
        Intervalo(datetime(2026, 11, 1, 8, 0), datetime(2026, 11, 1, 9, 0))


def test_libre_desde_sin_ocupacion_es_el_mismo_instante():
    desde = dt("2026-11-01T12:00:00-03:00")
    assert calcular_libre_desde(desde, []) == desde.astimezone(UTC)


def test_libre_desde_avanza_por_cadena_contigua():
    desde = dt("2026-11-01T08:00:00-03:00")
    intervalos = [
        Intervalo(dt("2026-11-01T07:00:00-03:00"), dt("2026-11-01T10:00:00-03:00")),
        Intervalo(dt("2026-11-01T10:00:00-03:00"), dt("2026-11-01T12:00:00-03:00")),
    ]
    assert calcular_libre_desde(desde, intervalos) == dt("2026-11-01T12:00:00-03:00").astimezone(UTC)


def test_un_hueco_corta_la_cadena():
    desde = dt("2026-11-01T08:00:00-03:00")
    intervalos = [
        Intervalo(dt("2026-11-01T07:00:00-03:00"), dt("2026-11-01T09:00:00-03:00")),
        Intervalo(dt("2026-11-01T10:00:00-03:00"), dt("2026-11-01T12:00:00-03:00")),
    ]
    # A las 09:00 hay un hueco de una hora: el recurso está libre, aunque no
    # alcance para un viaje largo. La decisión de si cabe es del llamador.
    assert calcular_libre_desde(desde, intervalos) == dt("2026-11-01T09:00:00-03:00").astimezone(UTC)


def test_intervalo_que_termina_exactamente_en_desde_no_bloquea():
    desde = dt("2026-11-01T13:00:00+00:00")
    intervalos = [
        Intervalo(dt("2026-11-01T08:00:00+00:00"), dt("2026-11-01T13:00:00+00:00")),
    ]
    assert calcular_libre_desde(desde, intervalos) == desde


def test_rango_semiabierto_no_marca_conflicto_en_el_borde():
    desde = dt("2026-11-01T13:00:00+00:00")
    hasta = dt("2026-11-01T17:00:00+00:00")
    intervalos = [
        Intervalo(dt("2026-11-01T08:00:00+00:00"), dt("2026-11-01T13:00:00+00:00")),
    ]
    assert solapamientos(desde, hasta, intervalos) == []

    intervalos[0] = Intervalo(
        dt("2026-11-01T12:59:59+00:00"), dt("2026-11-01T13:00:01+00:00")
    )
    assert len(solapamientos(desde, hasta, intervalos)) == 1


def test_zonas_distintas_se_comparan_en_utc():
    desde = dt("2026-11-01T12:00:00-03:00")
    intervalos = [Intervalo(dt("2026-11-01T14:00:00+00:00"), dt("2026-11-01T16:00:00+00:00"))]
    # 12:00 -03:00 = 15:00 UTC; ya está dentro del intervalo.
    assert calcular_libre_desde(desde, intervalos) == dt("2026-11-01T16:00:00+00:00")


def test_inicio_dia_local_maneja_salto_dst_de_chile():
    # Chile adelanta el reloj el primer domingo de septiembre a las 00:00.
    # 2026-09-06 00:00 no existe; el primer instante del día es 01:00 -03.
    inicio = inicio_dia_local(date(2026, 9, 6), "America/Santiago")
    assert inicio == datetime(2026, 9, 6, 4, 0, tzinfo=UTC)


def test_inicio_dia_local_dia_normal():
    inicio = inicio_dia_local(date(2026, 11, 1), "America/Santiago")
    assert inicio == datetime(2026, 11, 1, 3, 0, tzinfo=UTC)


def test_inicio_operativo_suma_traslado():
    libre = dt("2026-11-01T12:00:00+00:00")
    assert inicio_operativo_posible(libre, 90) == libre + timedelta(minutes=90)


def test_inicio_operativo_rechaza_traslado_absurdo():
    libre = dt("2026-11-01T12:00:00+00:00")
    with pytest.raises(ErrorTemporal):
        inicio_operativo_posible(libre, 1441)
