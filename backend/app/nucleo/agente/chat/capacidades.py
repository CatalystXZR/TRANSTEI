"""Catálogo de capacidades configurables del chat in-app.

La **fuente de verdad es este archivo**, no la base. `nucleo.agente_capacidades`
(migración `0032`) solo guarda el *override* por empresa y agente; una fila con
`habilitada = true` no puede conceder nada que el catálogo no permita.

Cada `Capacidad` declara cuatro límites duros y uno configurable:

- `agentes`: quiénes **pueden** tenerla. La secretaria nunca aparece en las
  capacidades financieras estratégicas, de gastos, de configuración ni en las
  escrituras de operación/comercial. Una fila de la tabla para un agente no
  listado se ignora en el runtime y la API la rechaza;
- `permiso`: permiso humano requerido. El rol se evalúa siempre en el servidor
  (`permisos.tiene_permiso`); si el rol no lo tiene, la capacidad no está
  disponible aunque exista la fila;
- `modulo`: si depende de un módulo premium, se consulta el muro de pago
  (`servicio_modulos`) en cada turno. Un módulo inactivo deshabilita la
  capacidad y la tool devuelve `upsell`;
- `por_defecto`: valor cuando la empresa no guardó un override;
- `riesgo`: clasificación informativa para el panel (`bajo|medio|alto`).

Decisiones de esta entrega (documentadas en `docs/backend/agente-capacidades.md`):

- `finanzas.leer_estrategico` **no** se ata al módulo `finanzas_pro`: el tenant
  piloto no tiene esa suscripción y el requisito explícito es que el gerente
  responda margen. El gate por módulo queda para una fase posterior;
- `whatsapp.recordatorio` sí queda gateada por `whatsapp`;
- el gerente no puede configurarse a sí mismo: no existe tool de configuración
  de capacidades y la API del panel exige `agente:configurar` (solo `admin`).

Este módulo no importa `runtime` (evita ciclos): `runtime` lo consume a él.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session

from app.nucleo.agente.chat import personas as catalogo_personas
from app.nucleo.agente.chat import servicio_modulos
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import AccesoDenegado, DatosInvalidos, ReglaNegocioViolada
from app.nucleo.permisos import tiene_permiso

AGENTES: tuple[str, ...] = ("gerente", "secretaria")
RIESGOS: tuple[str, ...] = ("bajo", "medio", "alto")

_MENSAJE_CAPACIDAD = "Esa capacidad no está habilitada para este agente."


@dataclass(frozen=True, slots=True)
class Capacidad:
    clave: str
    nombre: str
    descripcion: str
    grupo: str
    riesgo: str
    permiso: str
    agentes: tuple[str, ...]
    por_defecto: dict[str, bool]
    modulo: str | None = None


def _capacidad(
    clave: str,
    nombre: str,
    descripcion: str,
    *,
    permiso: str,
    agentes: tuple[str, ...],
    riesgo: str = "bajo",
    por_defecto: dict[str, bool] | None = None,
    modulo: str | None = None,
) -> Capacidad:
    return Capacidad(
        clave=clave,
        nombre=nombre,
        descripcion=descripcion,
        grupo=clave.split(".", 1)[0],
        riesgo=riesgo,
        permiso=permiso,
        agentes=agentes,
        por_defecto=por_defecto or {agente: True for agente in agentes},
        modulo=modulo,
    )


_AMBOS = AGENTES
_SOLO_GERENTE = ("gerente",)
_SOLO_SECRETARIA = ("secretaria",)

CAPACIDADES: dict[str, Capacidad] = {
    capacidad.clave: capacidad
    for capacidad in (
        _capacidad(
            "operacion.leer",
            "Consultar operación",
            "Ver viajes, su estado y su agenda.",
            permiso="operacion:leer",
            agentes=_AMBOS,
        ),
        _capacidad(
            "operacion.crear_viaje",
            "Crear viajes",
            "Registrar un viaje confirmado. No asigna tracto, rampla ni chofer.",
            permiso="operacion:escribir",
            agentes=_SOLO_GERENTE,
            riesgo="alto",
        ),
        _capacidad(
            "operacion.anular_viaje",
            "Anular viajes",
            "Anular un viaje con motivo, liberando sus reservas.",
            permiso="comercial:aprobar",
            agentes=_SOLO_GERENTE,
            riesgo="alto",
        ),
        _capacidad(
            "comercial.leer",
            "Consultar comercial",
            "Ver clientes, tarifas y órdenes de compra.",
            permiso="comercial:leer",
            agentes=_AMBOS,
        ),
        _capacidad(
            "comercial.escribir",
            "Modificar comercial",
            "Crear tarifas y órdenes de compra.",
            permiso="comercial:escribir",
            agentes=_SOLO_GERENTE,
            riesgo="alto",
        ),
        _capacidad(
            "finanzas.leer_operativo",
            "Consultar facturación y cobranza",
            "Ver facturas, saldos y aging. Sin costos, márgenes ni utilidad.",
            permiso="facturacion:leer",
            agentes=_AMBOS,
        ),
        _capacidad(
            "finanzas.leer_estrategico",
            "Analizar rentabilidad",
            "Ver costos, margen por camión y resumen económico del período.",
            permiso="rentabilidad:leer",
            agentes=_SOLO_GERENTE,
            riesgo="alto",
        ),
        _capacidad(
            "finanzas.leer_iva",
            "Consultar IVA",
            "Ver el resumen de IVA del período.",
            permiso="iva:leer",
            agentes=_SOLO_GERENTE,
            riesgo="medio",
        ),
        _capacidad(
            "gastos.leer",
            "Consultar gastos",
            "Ver gastos de viaje y su estado de aprobación.",
            permiso="gastos:leer",
            agentes=_SOLO_GERENTE,
            riesgo="medio",
        ),
        _capacidad(
            "configuracion.leer",
            "Consultar configuración",
            "Ver el catálogo vigente y las reglas abiertas de la empresa.",
            permiso="configuracion:leer",
            agentes=_SOLO_GERENTE,
            riesgo="medio",
        ),
        _capacidad(
            "configuracion.escribir_catalogo",
            "Cambiar catálogo",
            "Actualizar IVA y umbrales de alerta del catálogo cerrado.",
            permiso="configuracion:escribir",
            agentes=_SOLO_GERENTE,
            riesgo="alto",
        ),
        _capacidad(
            "configuracion.escribir_reglas",
            "Escribir reglas",
            "Registrar directivas y reglas por entidad de la empresa.",
            permiso="configuracion:escribir",
            agentes=_SOLO_GERENTE,
            riesgo="medio",
        ),
        _capacidad(
            "maestros.leer",
            "Consultar maestros",
            "Ver clientes, choferes, tractos y ramplas para resolver datos.",
            permiso="maestros:leer",
            agentes=_AMBOS,
        ),
        _capacidad(
            "alertas.leer",
            "Consultar alertas",
            "Ver el tablero de alertas de la empresa.",
            permiso="alertas:leer",
            agentes=_AMBOS,
        ),
        _capacidad(
            "agente.crear_solicitud",
            "Dejar solicitudes",
            "Preparar solicitudes que el dueño aprueba en el buzón.",
            permiso="agente:buzon",
            agentes=_SOLO_SECRETARIA,
            riesgo="medio",
        ),
        _capacidad(
            "whatsapp.recordatorio",
            "Recordatorios por WhatsApp",
            "Preparar un recordatorio de viaje. Requiere el módulo WhatsApp.",
            permiso="agente:chat",
            agentes=_SOLO_SECRETARIA,
            modulo="whatsapp",
        ),
        _capacidad(
            "auditoria.leer",
            "Consultar auditoría",
            "Ver el registro de auditoría de la empresa.",
            permiso="auditoria:leer",
            agentes=_SOLO_GERENTE,
            riesgo="alto",
            por_defecto={"gerente": False},
        ),
    )
}


# ---------------------------------------------------------------------------
# Lectura del override por empresa
# ---------------------------------------------------------------------------
def obtener(clave: Any) -> Capacidad | None:
    """Capacidad del catálogo o `None`. No consulta la base."""
    if not isinstance(clave, str):
        return None
    return CAPACIDADES.get(clave)


def overrides(session: Session, empresa_id: UUID) -> dict[tuple[str, str], bool]:
    """Filas guardadas por la empresa: `{(agente, capacidad): habilitada}`.

    No valida el catálogo: `habilitadas` y `configuracion_agente` descartan las
    claves o agentes que no correspondan. Una fila huérfana (capacidad retirada
    del código) no rompe el turno ni se borra sola.
    """
    filas = session.execute(
        text(
            """
            select agente, capacidad, habilitada
              from nucleo.agente_capacidades
             where empresa_id = :empresa_id
            """
        ),
        {"empresa_id": empresa_id},
    ).mappings()
    return {
        (str(fila["agente"]), str(fila["capacidad"])): bool(fila["habilitada"])
        for fila in filas
    }


def _estado_modulo(
    session: Session, contexto: ContextoEmpresa, modulo: str, cache: dict[str, bool]
) -> bool:
    if modulo not in cache:
        cache[modulo] = bool(
            servicio_modulos.estado(session, contexto, modulo)["activo"]
        )
    return cache[modulo]


def habilitadas(
    session: Session, contexto: ContextoEmpresa, agente: str
) -> frozenset[str]:
    """Capacidades efectivas de un agente en esta empresa y para este rol.

    Intersección de: agente permitido por el catálogo, permiso humano del rol,
    módulo premium activo (si aplica) y valor efectivo (override o default).
    Una fila `habilitada = true` para un agente no permitido **no** concede nada.
    """
    _validar_agente(agente)
    guardadas = overrides(session, contexto.empresa_id)
    modulos: dict[str, bool] = {}
    efectivas: set[str] = set()
    for capacidad in CAPACIDADES.values():
        if agente not in capacidad.agentes:
            continue
        if not tiene_permiso(contexto.rol, capacidad.permiso):
            continue
        if capacidad.modulo is not None and not _estado_modulo(
            session, contexto, capacidad.modulo, modulos
        ):
            continue
        habilitada = guardadas.get(
            (agente, capacidad.clave),
            capacidad.por_defecto.get(agente, False),
        )
        if habilitada:
            efectivas.add(capacidad.clave)
    return frozenset(efectivas)


def configuracion_agente(
    session: Session, contexto: ContextoEmpresa, agente: str
) -> dict[str, Any]:
    """Configuración visible en el panel para un agente.

    Solo lista las capacidades que el catálogo permite a ese agente. `habilitada`
    es el valor **efectivo** (un módulo inactivo o un permiso faltante la dejan
    en `false` aunque la fila diga lo contrario) y `motivo_no_disponible` explica
    por qué no se puede activar.
    """
    _validar_agente(agente)
    guardadas = overrides(session, contexto.empresa_id)
    modulos: dict[str, bool] = {}
    items: list[dict[str, Any]] = []
    for capacidad in CAPACIDADES.values():
        if agente not in capacidad.agentes:
            continue
        permiso_ok = tiene_permiso(contexto.rol, capacidad.permiso)
        modulo_activo = True
        if capacidad.modulo is not None:
            modulo_activo = _estado_modulo(
                session, contexto, capacidad.modulo, modulos
            )
        disponible = permiso_ok and modulo_activo
        if not disponible:
            motivo = "permiso" if not permiso_ok else "modulo_inactivo"
        else:
            motivo = None
        valor = guardadas.get(
            (agente, capacidad.clave),
            capacidad.por_defecto.get(agente, False),
        )
        items.append(
            {
                "clave": capacidad.clave,
                "nombre": capacidad.nombre,
                "descripcion": capacidad.descripcion,
                "grupo": capacidad.grupo,
                "riesgo": capacidad.riesgo,
                "permiso": capacidad.permiso,
                "habilitada": bool(valor) and disponible,
                "por_defecto": bool(capacidad.por_defecto.get(agente, False)),
                "disponible": disponible,
                "motivo_no_disponible": motivo,
                "modulo": capacidad.modulo,
                "modulo_activo": modulo_activo,
            }
        )
    persona = catalogo_personas.AGENTES[agente]
    return {
        "clave": agente,
        "nombre": persona.nombre,
        "capacidades": items,
    }


# ---------------------------------------------------------------------------
# Escritura del override (sin commit: cierra el endpoint)
# ---------------------------------------------------------------------------
def actualizar(
    session: Session,
    contexto: ContextoEmpresa,
    agente: str,
    cambios: list[dict[str, Any]],
) -> dict[str, Any]:
    """Guarda overrides y devuelve la configuración resultante del agente.

    Valida, en este orden: agente, capacidad del catálogo, límite duro de
    agente, duplicados, tipo de `habilitada`, permiso humano y módulo activo.
    No hace `commit()` ni `rollback()`: la transacción la cierra el endpoint.
    """
    _validar_agente(agente)
    if not cambios:
        raise DatosInvalidos("Debe indicar al menos un cambio de capacidad.")

    filas: list[tuple[str, bool]] = []
    vistos: set[str] = set()
    for cambio in cambios:
        if not isinstance(cambio, dict):
            raise DatosInvalidos("Cada cambio debe ser un objeto.")
        clave = cambio.get("capacidad")
        habilitada = cambio.get("habilitada")
        capacidad = obtener(clave)
        if capacidad is None:
            raise DatosInvalidos(
                "Capacidad desconocida.",
                contexto={"capacidad": clave, "capacidades": sorted(CAPACIDADES)},
            )
        if agente not in capacidad.agentes:
            raise DatosInvalidos(
                "Esa capacidad no aplica a este agente.",
                contexto={"capacidad": capacidad.clave, "agente": agente},
            )
        if capacidad.clave in vistos:
            raise DatosInvalidos(
                "Capacidad repetida en el mismo cambio.",
                contexto={"capacidad": capacidad.clave},
            )
        vistos.add(capacidad.clave)
        if not isinstance(habilitada, bool):
            raise DatosInvalidos("`habilitada` debe ser booleano.")
        if not tiene_permiso(contexto.rol, capacidad.permiso):
            raise AccesoDenegado(
                "Su rol no permite habilitar esa capacidad.",
                contexto={"permiso_requerido": capacidad.permiso},
            )
        if habilitada and capacidad.modulo is not None:
            if not servicio_modulos.estado(
                session, contexto, capacidad.modulo
            )["activo"]:
                raise ReglaNegocioViolada(
                    "El módulo de esa capacidad no está activo; no se puede "
                    "habilitar.",
                    contexto={"capacidad": capacidad.clave, "modulo": capacidad.modulo},
                )
        filas.append((capacidad.clave, habilitada))

    for clave, habilitada in filas:
        session.execute(
            text(
                """
                insert into nucleo.agente_capacidades
                    (empresa_id, agente, capacidad, habilitada,
                     created_by, updated_by)
                values
                    (:empresa_id, :agente, :capacidad, :habilitada,
                     :auth_id, :auth_id)
                on conflict (empresa_id, agente, capacidad)
                do update set habilitada = excluded.habilitada,
                              updated_by = excluded.updated_by
                """
            ),
            {
                "empresa_id": contexto.empresa_id,
                "agente": agente,
                "capacidad": clave,
                "habilitada": habilitada,
                "auth_id": contexto.auth_id,
            },
        )

    return configuracion_agente(session, contexto, agente)


def restablecer(
    session: Session, contexto: ContextoEmpresa, agente: str
) -> dict[str, Any]:
    """Devuelve todas las capacidades del agente a su valor por defecto.

    No usa `DELETE` (`tei_app` no tiene ese grant en `0032`): escribe el default
    con `insert ... on conflict do update`. Guarda el default **crudo**; si el
    módulo o el permiso no están disponibles, el runtime y `configuracion_agente`
    los siguen mostrando como no disponibles.
    """
    _validar_agente(agente)
    for capacidad in CAPACIDADES.values():
        if agente not in capacidad.agentes:
            continue
        session.execute(
            text(
                """
                insert into nucleo.agente_capacidades
                    (empresa_id, agente, capacidad, habilitada,
                     created_by, updated_by)
                values
                    (:empresa_id, :agente, :capacidad, :habilitada,
                     :auth_id, :auth_id)
                on conflict (empresa_id, agente, capacidad)
                do update set habilitada = excluded.habilitada,
                              updated_by = excluded.updated_by
                """
            ),
            {
                "empresa_id": contexto.empresa_id,
                "agente": agente,
                "capacidad": capacidad.clave,
                "habilitada": bool(capacidad.por_defecto.get(agente, False)),
                "auth_id": contexto.auth_id,
            },
        )
    return configuracion_agente(session, contexto, agente)


def _validar_agente(agente: Any) -> str:
    if not isinstance(agente, str) or agente not in AGENTES:
        raise DatosInvalidos(
            "Agente no válido.",
            contexto={"agentes": list(AGENTES)},
        )
    return agente


MENSAJE_CAPACIDAD_NO_HABILITADA = _MENSAJE_CAPACIDAD
