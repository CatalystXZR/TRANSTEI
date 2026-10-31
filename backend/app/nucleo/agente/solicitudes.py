"""Buzón de solicitudes del agente (O2.2). Contrato §6.1–§6.7.

Reglas que este módulo impone y que no dependen de la UI:

- **Empresa desde la membresía.** Todo `select`/`update` lleva
  `empresa_id = :empresa_id` resuelto por `get_contexto_empresa`; nunca viene del
  body ni de un query param. RLS actúa como segunda barrera.
- **Un recurso de otra empresa es 404, no 403** (§6.1): no se filtra existencia.
- **Una transacción por decisión.** El ejecutor recibe la `Session` y no hace
  `commit()` propio (§6.6): o se aprueba y se aplica el efecto, o no pasa nada.
- **Bloqueo optimista + `FOR UPDATE`** (§6.4). El segundo aprobador espera el
  lock y, al reanudar, ve el estado terminal: 409, nunca doble efecto.
- **El buzón no consulta el flag del módulo** (§6.7). Apagar el agente no puede
  dejar solicitudes irresolubles.
- **Sin `Idempotency-Key`**: un reintento tras un 200 devuelve 409
  `SOLICITUD_YA_DECIDIDA`; no hay un segundo efecto.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session

from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import (
    Autoaprobacion,
    ConflictoConcurrencia,
    DatosInvalidos,
    RecursoNoEncontrado,
    ReglaNegocioViolada,
    SolicitudYaDecidida,
    TipoSinEjecutor,
)

ESTADOS_FILTRO = frozenset(
    {"pendiente", "aprobada", "rechazada", "cancelada", "todas"}
)
TIPOS = frozenset({"agendamiento", "documentos", "hoja_de_ruta", "otra"})
ACCIONES = frozenset({"confirmar", "rechazar", "modificar"})
ESTADOS_TERMINALES = frozenset({"aprobada", "rechazada", "cancelada"})

TIPO_LEGIBLE = {
    "agendamiento": "Agendamiento",
    "documentos": "Documentos",
    "hoja_de_ruta": "Hoja de ruta",
    "otra": "Solicitud",
}

# ---------------------------------------------------------------------------
# Proyección
# ---------------------------------------------------------------------------

_SELECT_LISTA = """
select s.id::text                        as id,
       s.tipo::text                      as tipo,
       s.estado::text                    as estado,
       s.solicitante_contacto_id::text   as solicitante_contacto_id,
       s.solicitante_usuario_empresa_id::text as solicitante_usuario_empresa_id,
       s.viaje_id::text                  as viaje_id,
       s.payload,
       s.valores_modificados,
       s.created_at,
       s.decidido_en,
       s.aprobado_por,
       s.version,
       ct.nombre                         as contacto_nombre,
       v.id_comercial_flete
  from nucleo.solicitudes s
  left join nucleo.contactos_whatsapp ct
         on ct.empresa_id = s.empresa_id
        and ct.id = s.solicitante_contacto_id
  left join nucleo.viajes v
         on v.empresa_id = s.empresa_id
        and v.id = s.viaje_id
 where s.empresa_id = :empresa_id
"""

_FILTROS_LISTA: dict[str, str] = {
    "estado": "   and s.estado = cast(:estado as nucleo.estado_solicitud)\n",
    "tipo": "   and s.tipo = cast(:tipo as nucleo.tipo_solicitud)\n",
    "viaje_id": "   and s.viaje_id = cast(:viaje_id as uuid)\n",
}

_CONTEOS_LISTA = """
select count(*)
  from nucleo.solicitudes s
 where s.empresa_id = :empresa_id
"""

_SELECT_DETALLE = _SELECT_LISTA + "   and s.id = cast(:solicitud_id as uuid)\n"

_SELECT_BLOQUEO = """
select s.id::text        as id,
       s.tipo::text      as tipo,
       s.estado::text    as estado,
       s.version,
       s.payload,
       s.valores_modificados,
       s.solicitante_contacto_id::text as solicitante_contacto_id,
       s.solicitante_usuario_empresa_id::text as solicitante_usuario_empresa_id,
       ct.usuario_empresa_id::text as contacto_usuario_empresa_id
  from nucleo.solicitudes s
  left join nucleo.contactos_whatsapp ct
         on ct.empresa_id = s.empresa_id
        and ct.id = s.solicitante_contacto_id
 where s.empresa_id = :empresa_id
   and s.id = cast(:solicitud_id as uuid)
   for update of s
"""

_SELECT_HOJA_RUTA = """
select id::text, estado::text, payload
  from nucleo.hoja_ruta
 where empresa_id = :empresa_id
   and solicitud_id = cast(:solicitud_id as uuid)
"""

_SELECT_MEMBRESIA = """
select id::text from nucleo.usuarios_empresa
 where empresa_id = :empresa_id and auth_id = :auth_id
"""


def _iso(valor: Any) -> str | None:
    if valor is None:
        return None
    return valor.isoformat().replace("+00:00", "Z")


def _faltantes(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    crudo = payload.get("faltantes")
    if isinstance(crudo, list):
        return [str(x) for x in crudo]
    return []


def _resumen(tipo: str, payload: Any) -> str:
    """Síntesis del payload, nunca el payload (§6.2).

    No aplica reglas de negocio: cuenta campos y, si el payload declara
    `faltantes`, cuántos son. El detalle completo vive en §6.3.
    """
    campos = len(payload) if isinstance(payload, dict) else 0
    base = f"{TIPO_LEGIBLE.get(tipo, tipo)} con {campos} campos"
    faltan = _faltantes(payload)
    if faltan:
        base += f"; faltan {len(faltan)}"
    return base[:200]


def _solicitante(fila: Any) -> dict[str, Any]:
    """Contacto o usuario; nunca el teléfono (§6.2).

    `nucleo.usuarios_empresa` no tiene columna de nombre (solo `auth_id` y
    `rol`), así que para un solicitante usuario `nombre` queda `None` en vez de
    inventar un identificador.
    """
    if fila.solicitante_contacto_id is not None:
        return {
            "tipo": "contacto",
            "id": fila.solicitante_contacto_id,
            "nombre": fila.contacto_nombre,
        }
    return {
        "tipo": "usuario",
        "id": fila.solicitante_usuario_empresa_id,
        "nombre": None,
    }


def _diff(payload: Any, modificados: Any) -> list[dict[str, Any]]:
    """Diff campo a campo, derivado al leer y no persistido (§6.3)."""
    if not isinstance(modificados, dict):
        return []
    original = payload if isinstance(payload, dict) else {}
    salida = [
        {
            "campo": campo,
            "propuesto": original.get(campo),
            "modificado": nuevo,
        }
        for campo, nuevo in sorted(modificados.items())
        if original.get(campo) != nuevo
    ]
    return salida


def _item_lista(fila: Any) -> dict[str, Any]:
    return {
        "id": fila.id,
        "tipo": fila.tipo,
        "estado": fila.estado,
        "solicitante": _solicitante(fila),
        "viaje_id": fila.viaje_id,
        "id_comercial_flete": fila.id_comercial_flete,
        "resumen": _resumen(fila.tipo, fila.payload),
        "creada_en": _iso(fila.created_at),
        "decidida_en": _iso(fila.decidido_en),
        "tiene_modificaciones": fila.valores_modificados is not None,
        "version": fila.version,
    }


def _evidencia(payload: Any) -> list[dict[str, Any]]:
    """Solo referencias; el contenido se lee con su propio permiso (§6.3)."""
    if not isinstance(payload, dict):
        return []
    crudo = payload.get("evidencia")
    if not isinstance(crudo, list):
        return []
    salida: list[dict[str, Any]] = []
    for elemento in crudo:
        if not isinstance(elemento, dict):
            continue
        salida.append(
            {
                "tipo": elemento.get("tipo"),
                "ref": elemento.get("ref"),
            }
        )
    return salida


def _detalle(fila: Any, hoja: Any) -> dict[str, Any]:
    return {
        "id": fila.id,
        "tipo": fila.tipo,
        "estado": fila.estado,
        "solicitante": _solicitante(fila),
        "viaje_id": fila.viaje_id,
        "id_comercial_flete": fila.id_comercial_flete,
        "payload": fila.payload,
        "valores_modificados": fila.valores_modificados,
        "diff": _diff(fila.payload, fila.valores_modificados),
        "evidencia": _evidencia(fila.payload),
        "hoja_ruta": None
        if hoja is None
        else {
            "id": hoja[0],
            "estado": hoja[1],
            "faltantes": _faltantes(hoja[2]),
        },
        "creada_en": _iso(fila.created_at),
        "decidida_en": _iso(fila.decidido_en),
        "aprobado_por": fila.aprobado_por,
        "version": fila.version,
    }


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------


def listar(
    session: Session,
    contexto: ContextoEmpresa,
    *,
    estado: str = "pendiente",
    tipo: str | None = None,
    viaje_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    if estado not in ESTADOS_FILTRO:
        raise DatosInvalidos(f"Estado no válido: {estado}.")
    if tipo is not None and tipo not in TIPOS:
        raise DatosInvalidos(f"Tipo no válido: {tipo}.")
    if not (1 <= limit <= 100):
        raise DatosInvalidos("`limit` debe estar entre 1 y 100.")
    if offset < 0:
        raise DatosInvalidos("`offset` no puede ser negativo.")

    parametros: dict[str, Any] = {"empresa_id": contexto.empresa_id}
    filtros = ""
    if estado != "todas":
        filtros += _FILTROS_LISTA["estado"]
        parametros["estado"] = estado
    if tipo is not None:
        filtros += _FILTROS_LISTA["tipo"]
        parametros["tipo"] = tipo
    if viaje_id is not None:
        filtros += _FILTROS_LISTA["viaje_id"]
        parametros["viaje_id"] = str(viaje_id)

    total = int(
        session.execute(text(_CONTEOS_LISTA + filtros), parametros).scalar_one()
    )
    filas = session.execute(
        text(
            _SELECT_LISTA
            + filtros
            + " order by s.created_at desc, s.id desc\n limit :limit offset :offset"
        ),
        {**parametros, "limit": limit, "offset": offset},
    ).all()
    return {
        "items": [_item_lista(f) for f in filas],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _hoja_ruta(session: Session, empresa_id: UUID, solicitud_id: str) -> Any:
    return session.execute(
        text(_SELECT_HOJA_RUTA),
        {"empresa_id": empresa_id, "solicitud_id": solicitud_id},
    ).first()


def obtener(
    session: Session, contexto: ContextoEmpresa, solicitud_id: UUID
) -> dict[str, Any]:
    fila = session.execute(
        text(_SELECT_DETALLE),
        {"empresa_id": contexto.empresa_id, "solicitud_id": str(solicitud_id)},
    ).first()
    if fila is None:
        raise RecursoNoEncontrado("La solicitud no existe.")
    return _detalle(fila, _hoja_ruta(session, contexto.empresa_id, fila.id))


# ---------------------------------------------------------------------------
# Ejecutores por tipo (§6.6)
# ---------------------------------------------------------------------------


def _confirmar_hoja_ruta(
    session: Session,
    contexto: ContextoEmpresa,
    solicitud: Any,
    valores: dict[str, Any] | None,
) -> dict[str, Any]:
    """`solicitud_creada → cargado` + `valores_cargados`.

    El `payload` propuesto **no** se reescribe: la corrección va a
    `valores_cargados` (ADR-0003 §14.2; lo impone `fn_hoja_ruta_transicion`,
    0022). El estado lo valida el trigger: aquí no se duplica esa regla.

    Prioridad de los valores (SEC-041): lo que envía el aprobador en este
    request; si no envía nada, la corrección que ya persistió al **modificar**;
    solo si nunca se modificó, el payload original. Cargar el `payload` después
    de un `modificar` dejaría el registro con la corrección y la hoja de ruta con
    el valor viejo.
    """
    if valores is not None:
        cargados = valores
    elif solicitud.valores_modificados is not None:
        cargados = solicitud.valores_modificados
    else:
        cargados = solicitud.payload
    if not isinstance(cargados, dict) or not cargados:
        # SEC-042: un objeto vacío marcaba `cargado` sin datos y el CHECK solo
        # exige "no nulo".
        raise DatosInvalidos(
            "Confirmar exige valores: no hay payload ni corrección que cargar."
        )

    fila = session.execute(
        text(
            """
            update nucleo.hoja_ruta
               set estado = 'cargado',
                   valores_cargados = cast(:valores as jsonb),
                   updated_by = :actor
             where empresa_id = :empresa_id
               and solicitud_id = cast(:solicitud_id as uuid)
               and estado = 'solicitud_creada'
            returning id::text, estado::text
            """
        ),
        {
            "empresa_id": contexto.empresa_id,
            "solicitud_id": solicitud.id,
            "valores": json.dumps(cargados, ensure_ascii=False),
            "actor": f"agente:{contexto.auth_id}",
        },
    ).first()
    if fila is None:
        # Sin fila en `solicitud_creada` la transición no es posible: el estado
        # real de la hoja de ruta no admite `cargado`.
        raise ReglaNegocioViolada(
            "La hoja de ruta no está en estado que permita cargarla."
        )
    return {"tipo": "hoja_de_ruta", "ref": fila[0], "estado": fila[1]}


EjecutorSolicitud = Callable[
    [Session, ContextoEmpresa, Any, "dict[str, Any] | None"], dict[str, Any]
]

# Solo los tipos cuyo efecto vive en tablas del módulo (§6.6). Los demás
# devuelven 501 hasta que el servicio dueño acepte participar en la transacción
# del endpoint; un `confirmar` que a veces deja el sistema a medias es peor.
EJECUTORES_SOLICITUD: Mapping[str, EjecutorSolicitud] = MappingProxyType(
    {"hoja_de_ruta": _confirmar_hoja_ruta}
)


# ---------------------------------------------------------------------------
# Decisión
# ---------------------------------------------------------------------------


def _membresia(session: Session, contexto: ContextoEmpresa) -> str | None:
    return session.execute(
        text(_SELECT_MEMBRESIA),
        {"empresa_id": contexto.empresa_id, "auth_id": contexto.auth_id},
    ).scalar_one_or_none()


def _verificar_autoaprobacion(
    session: Session, contexto: ContextoEmpresa, solicitud: Any
) -> None:
    """403 si el aprobador es el solicitante (§6.4).

    Para un contacto se compara el `usuario_empresa_id` vinculado; si el
    contacto no tiene vínculo, no hay autoaprobación posible por esa vía.
    """
    if solicitud.solicitante_usuario_empresa_id is not None:
        actual = _membresia(session, contexto)
        if actual is not None and actual == solicitud.solicitante_usuario_empresa_id:
            raise Autoaprobacion(
                "Quien solicita no puede aprobar su propia solicitud."
            )
        return
    if solicitud.contacto_usuario_empresa_id is not None:
        actual = _membresia(session, contexto)
        if actual is not None and actual == solicitud.contacto_usuario_empresa_id:
            raise Autoaprobacion(
                "Quien solicita no puede aprobar su propia solicitud."
            )


def _validar_cuerpo(accion: str, motivo: str | None, valores: Any) -> None:
    if accion not in ACCIONES:
        raise DatosInvalidos(f"Acción no válida: {accion}.")
    if accion == "rechazar" and (motivo is None or not motivo.strip()):
        raise DatosInvalidos("Rechazar exige un motivo.")
    if accion == "modificar" and (not isinstance(valores, dict) or not valores):
        raise DatosInvalidos("Modificar exige valores_modificados.")


def decidir(
    session: Session,
    contexto: ContextoEmpresa,
    solicitud_id: UUID,
    *,
    accion: str,
    version: int,
    motivo_rechazo: str | None = None,
    valores_modificados: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Aplica una decisión y devuelve `(solicitud, resultado)`.

    No hace `commit()`: el endpoint cierra la transacción. Así el efecto del
    ejecutor y el estado de la solicitud son atómicos (§6.6).
    """
    _validar_cuerpo(accion, motivo_rechazo, valores_modificados)

    solicitud = session.execute(
        text(_SELECT_BLOQUEO),
        {"empresa_id": contexto.empresa_id, "solicitud_id": str(solicitud_id)},
    ).first()
    if solicitud is None:
        raise RecursoNoEncontrado("La solicitud no existe.")
    if solicitud.estado in ESTADOS_TERMINALES:
        raise SolicitudYaDecidida(
            f"La solicitud ya está en estado {solicitud.estado}."
        )
    if int(solicitud.version) != int(version):
        raise ConflictoConcurrencia(
            "La solicitud cambió desde que la abrió. Recargue y reintente."
        )

    _verificar_autoaprobacion(session, contexto, solicitud)

    resultado: dict[str, Any] | None = None
    actor = f"agente:{contexto.auth_id}"

    if accion == "confirmar":
        ejecutor = EJECUTORES_SOLICITUD.get(solicitud.tipo)
        if ejecutor is None:
            raise TipoSinEjecutor(
                f"El tipo {solicitud.tipo} todavía no tiene ejecutor."
            )
        resultado = ejecutor(
            session, contexto, solicitud, valores_modificados
        )
        nuevo_estado = "aprobada"
        parametros_extra = {
            "aprobado_por": actor,
            "decidido_en": True,
            "motivo_rechazo": None,
        }
    elif accion == "rechazar":
        nuevo_estado = "rechazada"
        parametros_extra = {
            "aprobado_por": actor,
            "decidido_en": True,
            "motivo_rechazo": motivo_rechazo.strip(),
        }
        _rechazar_hoja_ruta(session, contexto, solicitud, motivo_rechazo.strip())
    else:  # modificar
        nuevo_estado = "pendiente"
        parametros_extra = {
            "aprobado_por": None,
            "decidido_en": False,
            "motivo_rechazo": None,
        }

    filas = session.execute(
        text(
            """
            update nucleo.solicitudes
               set estado = cast(:estado as nucleo.estado_solicitud),
                   aprobado_por = :aprobado_por,
                   decidido_en = case when :poner_decidido then now() else decidido_en end,
                   motivo_rechazo = :motivo_rechazo,
                   valores_modificados = coalesce(cast(:valores as jsonb), valores_modificados),
                   modificado_por = case when :es_modificar then :actor else modificado_por end,
                   modificado_en = case when :es_modificar then now() else modificado_en end,
                   updated_by = :actor,
                   version = version + 1
             where empresa_id = :empresa_id
               and id = cast(:solicitud_id as uuid)
               and estado = 'pendiente'
               and version = :version
            returning version
            """
        ),
        {
            "estado": nuevo_estado,
            "aprobado_por": parametros_extra["aprobado_por"],
            "poner_decidido": parametros_extra["decidido_en"],
            "motivo_rechazo": parametros_extra["motivo_rechazo"],
            "valores": None
            if valores_modificados is None
            else json.dumps(valores_modificados, ensure_ascii=False),
            "es_modificar": accion == "modificar",
            "actor": actor,
            "empresa_id": contexto.empresa_id,
            "solicitud_id": str(solicitud_id),
            "version": int(version),
        },
    ).first()
    if filas is None:
        # El lock ya existía: solo un cambio concurrente explica este caso.
        raise SolicitudYaDecidida(
            "La solicitud fue decidida por otro aprobador."
        )

    actual = session.execute(
        text(_SELECT_DETALLE),
        {"empresa_id": contexto.empresa_id, "solicitud_id": str(solicitud_id)},
    ).first()
    if actual is None:  # pragma: no cover - la fila existe y está bloqueada
        raise RecursoNoEncontrado("La solicitud no existe.")
    detalle = _detalle(actual, _hoja_ruta(session, contexto.empresa_id, str(solicitud_id)))
    return detalle, resultado


def _rechazar_hoja_ruta(
    session: Session,
    contexto: ContextoEmpresa,
    solicitud: Any,
    motivo: str,
) -> None:
    """Rechazar no necesita ejecutor: solo toca tablas del módulo (§6.6).

    Fail-closed (SEC-043): si la hoja de ruta existe pero no está en
    `solicitud_creada`, el trigger no permite la transición y el `update` no
    toca filas. Antes la solicitud quedaba `rechazada` con la hoja de ruta en su
    estado anterior, es decir, un rechazo a medias.
    """
    if solicitud.tipo != "hoja_de_ruta":
        return
    resultado = session.execute(
        text(
            """
            update nucleo.hoja_ruta
               set estado = 'rechazado',
                   motivo_rechazo = :motivo,
                   updated_by = :actor
             where empresa_id = :empresa_id
               and solicitud_id = cast(:solicitud_id as uuid)
               and estado = 'solicitud_creada'
            """
        ),
        {
            "empresa_id": contexto.empresa_id,
            "solicitud_id": solicitud.id,
            "motivo": motivo,
            "actor": f"agente:{contexto.auth_id}",
        },
    )
    if resultado.rowcount == 0:
        raise ReglaNegocioViolada(
            "La hoja de ruta no está en estado que permita rechazarla."
        )
