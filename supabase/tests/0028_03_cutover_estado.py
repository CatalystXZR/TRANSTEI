"""Sonda de solo lectura: `ServicioCutover.estado()` después de retirar `public`.

Demuestra que la única lectura `nucleo -> public` del backend
(`backend/app/nucleo/servicio_cutover.py:97`) es fail-soft: al no existir
`public.viajes`, el servicio degrada a 0 con `warning` y sigue respondiendo.
No imprime credenciales.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlmodel import Session

from app.core.database import get_engine_nucleo
from app.nucleo.servicio_cutover import ServicioCutover

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


class _Empresa:
    id = UUID("11111111-1111-1111-1111-111111111111")


class _Contexto:
    empresa = _Empresa()


with Session(get_engine_nucleo()) as session:
    estado = ServicioCutover(session, _Contexto()).estado()

print("legacy_escritura_congelada =", estado.legacy_escritura_congelada)
print("legacy_viajes_abiertos     =", estado.legacy_viajes_abiertos)
print("nucleo_viajes              =", estado.nucleo_viajes)
print("mensaje                    =", estado.mensaje)
