"""Cálculo de flete en backend, según la modalidad de la tarifa.

Las fórmulas viven aquí, no en el frontend. El resultado se redondea a peso
chileno (2 decimales internos) y se compara contra el mínimo de cobro.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.nucleo.models import ModalidadTarifa

CENTAVO = Decimal("0.01")
MIL = Decimal("1000")


class ErrorTarifa(ValueError):
    """Datos insuficientes o inconsistentes para calcular el flete."""


def _decimal(valor: Decimal | int | float | str | None) -> Decimal:
    if valor is None:
        return Decimal("0")
    return Decimal(str(valor))


def calcular_flete(
    *,
    modalidad: ModalidadTarifa,
    precio_unitario: Decimal | None,
    minimo_cobro: Decimal | None,
    distancia_km: Decimal | None = None,
    peso_bruto_kg: Decimal | None = None,
    tiempo_estimado_h: Decimal | None = None,
    cantidad_contenedores: int = 1,
) -> Decimal:
    """Calcula el flete base de un viaje.

    Modalidades soportadas en el alta de viaje:
    - viaje: precio flat.
    - km: precio × distancia.
    - tonelada: precio × toneladas.
    - tonelada_km: precio × toneladas × km.
    - hora: precio × horas.
    - contenedor: precio × cantidad.

    `estadia` y `mixta` requieren reglas adicionales; se rechazan en el alta
    para no inventar un precio.
    """
    precio = _decimal(precio_unitario)
    minimo = _decimal(minimo_cobro)

    if modalidad == ModalidadTarifa.viaje:
        base = precio
    elif modalidad == ModalidadTarifa.km:
        if distancia_km is None or _decimal(distancia_km) <= 0:
            raise ErrorTarifa("La tarifa por km requiere una distancia mayor a 0.")
        base = precio * _decimal(distancia_km)
    elif modalidad == ModalidadTarifa.tonelada:
        if peso_bruto_kg is None or _decimal(peso_bruto_kg) <= 0:
            raise ErrorTarifa("La tarifa por tonelada requiere peso de carga.")
        base = precio * (_decimal(peso_bruto_kg) / MIL)
    elif modalidad == ModalidadTarifa.tonelada_km:
        if peso_bruto_kg is None or _decimal(peso_bruto_kg) <= 0:
            raise ErrorTarifa("La tarifa por tonelada-km requiere peso de carga.")
        if distancia_km is None or _decimal(distancia_km) <= 0:
            raise ErrorTarifa("La tarifa por tonelada-km requiere distancia.")
        base = precio * (_decimal(peso_bruto_kg) / MIL) * _decimal(distancia_km)
    elif modalidad == ModalidadTarifa.hora:
        if tiempo_estimado_h is None or _decimal(tiempo_estimado_h) <= 0:
            raise ErrorTarifa("La tarifa por hora requiere tiempo estimado.")
        base = precio * _decimal(tiempo_estimado_h)
    elif modalidad == ModalidadTarifa.contenedor:
        if cantidad_contenedores <= 0:
            raise ErrorTarifa("La cantidad de contenedores debe ser mayor a 0.")
        base = precio * Decimal(cantidad_contenedores)
    elif modalidad in (ModalidadTarifa.estadia, ModalidadTarifa.mixta):
        raise ErrorTarifa(
            f"La modalidad {modalidad.value} requiere reglas adicionales; "
            "use una tarifa por viaje, km, tonelada, tonelada-km, hora o contenedor."
        )
    else:
        raise ErrorTarifa(f"Modalidad de tarifa no soportada: {modalidad}")

    total = max(base, minimo)
    return total.quantize(CENTAVO, rounding=ROUND_HALF_UP)
