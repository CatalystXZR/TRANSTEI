"""Identidad del agente WhatsApp (`ContextoAgente`).

Decisión: `docs/arquitectura/adr/ADR-0006-identidad-y-alcance-tools-agente.md`.
Contrato: `docs/arquitectura/conector-agente-whatsapp.md` §4.1.

Por qué NO se reutiliza `ContextoEmpresa`
-----------------------------------------
El contacto de WhatsApp no es un usuario del núcleo: no tiene JWT, no tiene
`nucleo.usuarios_empresa` y su rol (`admin | cliente_final | conductor`) es un
enum distinto de `RolEmpresa`. Construir un `ContextoEmpresa` ficticio
implicaría impersonar un rol y abriría el camino de permisos del núcleo
(`requiere_permiso`) a un actor que no está autenticado por Supabase.

Ruteo por empresa (límite conocido)
-----------------------------------
`nucleo.contactos_whatsapp` tiene RLS por empresa. Un proceso que solo conoce
el teléfono **no puede** resolver la empresa: la consulta sin `app.empresa_id`
devuelve 0 filas (fail-closed, correcto). Por eso `resolver_contacto` recibe
`empresa_id` explícito, que en producción viene del número de negocio de Meta
(`metadata.phone_number_id` → una empresa), no del cuerpo del mensaje. La fila
del contacto se valida **dentro** de esa empresa; si el teléfono pertenece a
otra, el resultado es 0 filas y se deniega. Búsqueda global por teléfono queda
pendiente: requeriría una función `security definer` con revisión de seguridad
(registrado en `docs/backend/agente-o2-1.md`).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import text

from app.core.contexto import (
    contexto_de_request,
    fijar_auth_id,
    fijar_empresa,
    fijar_request_id,
)
from app.core.database import sesion_nucleo


# `nucleo.rol_contacto_whatsapp` (0021:151). No se reutiliza `RolEmpresa`.
class RolContacto(StrEnum):
    admin = "admin"
    cliente_final = "cliente_final"
    conductor = "conductor"


# `nucleo.estado_otp` (0021:152).
class EstadoOtp(StrEnum):
    pendiente = "pendiente"
    verificado = "verificado"


TELEFONO_E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")

# El índice global `uq_contactos_telefono_activo` (0021:222-223) garantiza a lo
# sumo un contacto activo por teléfono. Se pide `limit 2` para detectar la
# violación en lugar de asumirla.
_SQL_CONTACTO = text(
    """
    select id,
           rol::text        as rol,
           cliente_id,
           chofer_id,
           otp_estado::text as otp_estado,
           activo
      from nucleo.contactos_whatsapp
     where empresa_id = :empresa_id
       and telefono = :telefono
       and activo
     limit 2
    """
)


@dataclass(frozen=True, slots=True)
class ContextoAgente:
    """Actor del agente. Inmutable y sin privilegios implícitos."""

    empresa_id: UUID
    contacto_id: UUID
    rol: RolContacto
    entidad_id: UUID | None
    activo: bool
    otp_estado: str
    telefono: str
    request_id: str
    # Los resuelve el runtime contra `conversaciones`/`conversacion_mensajes`
    # (§4.1 paso 5). Si no existen, quedan None y la tool puede ejecutarse: la
    # auditoría pierde el vínculo, no la fila.
    conversacion_id: UUID | None = None
    mensaje_id: UUID | None = None


def normalizar_telefono(telefono: str) -> str:
    """Valida E.164 y devuelve el teléfono sin separadores visuales.

    No inventa prefijos: un número local (`912345678`) es un error del runtime,
    no algo que el backend pueda adivinar.
    """
    limpio = re.sub(r"[\s().-]", "", (telefono or "").strip())
    if not TELEFONO_E164.fullmatch(limpio):
        raise ValueError("El teléfono no está en formato E.164 (ej. +56912345678).")
    return limpio


@contextmanager
def contexto_de_agente(
    *,
    empresa_id: UUID,
    request_id: str,
    contacto_id: UUID | None = None,
) -> Iterator[None]:
    """Fija los GUCs del agente para todas las transacciones del bloque.

    `nucleo.auth_id = "agente:<contacto_id>"` es un marcador de actor para
    `created_by`/auditoría; no crea membresía ni impersona un `RolEmpresa`
    (ADR-0006, contrato §4.1 paso 6).
    """
    with contexto_de_request(request_id=request_id):
        fijar_empresa(empresa_id)
        fijar_request_id(request_id)
        fijar_auth_id(f"agente:{contacto_id}" if contacto_id else None)
        yield


def _entidad_del_rol(
    rol: RolContacto, cliente_id: UUID | None, chofer_id: UUID | None
) -> UUID | None:
    if rol is RolContacto.cliente_final:
        return cliente_id
    if rol is RolContacto.conductor:
        return chofer_id
    return None


def resolver_contacto(
    *,
    empresa_id: UUID,
    telefono: str,
    request_id: str,
) -> ContextoAgente | None:
    """Resuelve el contacto activo dentro de `empresa_id` (fail-closed).

    Devuelve `None` si no hay fila, si hay más de una (integridad rota) o si el
    rol exige entidad y la fila no la tiene. No lanza por datos de negocio: el
    runtime responde con el mensaje genérico de enrolamiento.
    """
    numero = normalizar_telefono(telefono)
    with (
        contexto_de_agente(empresa_id=empresa_id, request_id=request_id),
        sesion_nucleo() as session,
    ):
        filas = (
            session.execute(
                _SQL_CONTACTO,
                {"empresa_id": empresa_id, "telefono": numero},
            )
            .mappings()
            .all()
        )

    if len(filas) != 1:
        return None

    fila = filas[0]
    rol = RolContacto(fila["rol"])
    entidad = _entidad_del_rol(rol, fila["cliente_id"], fila["chofer_id"])
    if rol is not RolContacto.admin and entidad is None:
        # La base lo impide con `ck_contacto_entidad` (0021:210-214); si llega
        # aquí, la fila se escribió con BYPASSRLS y no es confiable.
        return None

    return ContextoAgente(
        empresa_id=empresa_id,
        contacto_id=fila["id"],
        rol=rol,
        entidad_id=entidad,
        activo=bool(fila["activo"]),
        otp_estado=fila["otp_estado"],
        telefono=numero,
        request_id=request_id,
    )
