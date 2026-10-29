"""Aritmética temporal del motor de disponibilidad.

Reglas no negociables:
- Se almacena y compara en UTC.
- Los rangos son semiabiertos `[inicio, fin)`: un viaje que termina a las
  13:00 no bloquea otro que empieza a las 13:00.
- Un datetime sin tzinfo se rechaza. Aceptar naive en un ERP de flota es una
  invitación a corromper la agenda en el cambio de hora de Chile.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

ZONA_DEFAULT = "America/Santiago"
TZ_SANTIAGO = ZoneInfo(ZONA_DEFAULT)


class ErrorTemporal(ValueError):
    """Error de dominio para fechas/horas inválidas."""


def zona(nombre: str | None = None) -> ZoneInfo:
    try:
        return ZoneInfo(nombre or ZONA_DEFAULT)
    except Exception as exc:  # pragma: no cover - depende de tzdata del SO
        raise ErrorTemporal(f"Zona horaria inválida: {nombre!r}") from exc


def exigir_aware(valor: datetime, campo: str = "fecha") -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ErrorTemporal(
            f"{campo} debe incluir zona horaria (ej. 2026-11-01T08:00:00-03:00). "
            "No se aceptan datetimes naive."
        )
    return valor


def a_utc(valor: datetime, campo: str = "fecha") -> datetime:
    return exigir_aware(valor, campo).astimezone(timezone.utc)


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def fecha_local(valor: datetime, zona_horaria: str | None = None) -> date:
    return a_utc(valor).astimezone(zona(zona_horaria)).date()


def inicio_dia_local(dia: date, zona_horaria: str | None = None) -> datetime:
    """Medianoche local. Si la medianoche no existe por DST, usa la primera hora válida."""
    z = zona(zona_horaria)
    candidato = datetime.combine(dia, time(0, 0), tzinfo=z)
    # En cambios de hora, zoneinfo puede devolver un offset pre-transición.
    # Normalizar y verificar que la hora local sea realmente 00:00.
    normalizado = candidato.astimezone(timezone.utc).astimezone(z)
    if normalizado.date() != dia or normalizado.hour != 0:
        # Chile salta de 00:00 a 01:00: el primer instante del día es 01:00.
        candidato = datetime.combine(dia, time(1, 0), tzinfo=z)
    return candidato.astimezone(timezone.utc)


def fin_dia_local(dia: date, zona_horaria: str | None = None) -> datetime:
    return inicio_dia_local(dia + timedelta(days=1), zona_horaria)


@dataclass(frozen=True, slots=True)
class Intervalo:
    inicio: datetime
    fin: datetime
    tipo: str = "ocupacion"
    motivo: str | None = None
    referencia_id: str | None = None

    def __post_init__(self) -> None:
        inicio = a_utc(self.inicio, "intervalo.inicio")
        fin = a_utc(self.fin, "intervalo.fin")
        if fin <= inicio:
            raise ErrorTemporal("Un intervalo debe tener fin > inicio")
        object.__setattr__(self, "inicio", inicio)
        object.__setattr__(self, "fin", fin)

    @property
    def duracion_minutos(self) -> int:
        return int((self.fin - self.inicio).total_seconds() // 60)

    def solapa(self, desde: datetime, hasta: datetime) -> bool:
        desde_u = a_utc(desde, "desde")
        hasta_u = a_utc(hasta, "hasta")
        if hasta_u <= desde_u:
            raise ErrorTemporal("La ventana consultada debe tener hasta > desde")
        return self.inicio < hasta_u and self.fin > desde_u


def ordenar_intervalos(intervalos: Iterable[Intervalo]) -> list[Intervalo]:
    return sorted(intervalos, key=lambda i: (i.inicio, i.fin))


def calcular_libre_desde(
    desde: datetime,
    intervalos: Sequence[Intervalo],
) -> datetime:
    """Primer instante en que el recurso queda libre desde `desde`.

    - Si está libre ahora, devuelve `desde` (no inventa una espera).
    - Si está ocupado, avanza por la cadena contigua de ocupaciones.
    - Un hueco, por pequeño que sea, corta la cadena: el recurso está libre en
      ese hueco, aunque no alcance para un viaje completo. El llamador decide
      si la ventana solicitada cabe.
    - Los buffers operacionales ya vienen incluidos en las reservas de viaje.
    """
    cursor = a_utc(desde, "desde")
    for intervalo in ordenar_intervalos(intervalos):
        if intervalo.fin <= cursor:
            continue
        if intervalo.inicio > cursor:
            break
        cursor = max(cursor, intervalo.fin)
    return cursor


def solapamientos(
    desde: datetime,
    hasta: datetime,
    intervalos: Sequence[Intervalo],
) -> list[Intervalo]:
    desde_u = a_utc(desde, "desde")
    hasta_u = a_utc(hasta, "hasta")
    if hasta_u <= desde_u:
        raise ErrorTemporal("La ventana consultada debe tener hasta > desde")
    return [i for i in ordenar_intervalos(intervalos) if i.solapa(desde_u, hasta_u)]


def inicio_operativo_posible(
    libre_desde: datetime,
    minutos_traslado: int,
) -> datetime:
    if minutos_traslado < 0 or minutos_traslado > 24 * 60:
        raise ErrorTemporal("Los minutos de traslado deben estar entre 0 y 1440")
    return a_utc(libre_desde, "libre_desde") + timedelta(minutes=minutos_traslado)


def formatear_en_zona(valor: datetime, zona_horaria: str | None = None) -> str:
    return a_utc(valor).astimezone(zona(zona_horaria)).isoformat(timespec="minutes")
