"""Registro de herramientas del chat in-app.

Cada `Herramienta` declara:

- `agente`: dueño de la tool. Una tool fuera de la allowlist de la persona se
  rechaza aunque el LLM la invente (`runtime.py`);
- `modulo`: si pertenece a un módulo premium, el runtime consulta el muro de
  pago **antes** de ejecutarla;
- `parametros`: JSON Schema que se entrega al proveedor; la validación real de
  los argumentos ocurre aquí, en servidor (deny-by-default), no en el prompt.

Escrituras:
- el gerente escribe `nucleo.configuracion_empresa` (directivas) y
  `nucleo.tenant_reglas_entidad` (reglas por entidad);
- la secretaria **solo** inserta en `nucleo.solicitudes` (`tipo='otra'`). Nunca
  ejecuta la acción: eso ocurre al aprobar en el buzón (`agente/solicitudes.py`).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.nucleo.agente.chat import servicio_modulos
from app.nucleo.agente.solicitudes import ACCIONES_CRITICAS
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import (
    AccesoDenegado,
    ConflictoConcurrencia,
    DatosInvalidos,
    RecursoNoEncontrado,
    traducir_integrity_error,
)
from app.nucleo.models import EstadoViaje
from app.nucleo.schemas import (
    OrdenCompraCreate,
    SolicitudAnulacionViaje,
    TarifaCreate,
    ViajeCreateNucleo,
)
from app.nucleo.servicio_alertas import ServicioAlertas
from app.nucleo.servicio_comercial import ServicioComercial
from app.nucleo.servicio_configuracion import CATALOGO, ServicioConfiguracion
from app.nucleo.servicio_disponibilidad import ServicioDisponibilidad
from app.nucleo.servicio_facturacion import ServicioFacturacion
from app.nucleo.servicio_iva import ServicioIva
from app.nucleo.servicio_transiciones import ServicioTransiciones

ENTIDADES = frozenset({"cliente", "chofer", "tracto", "rampla", "contacto"})
_COLUMNA_ENTIDAD = {
    "cliente": "cliente_id",
    "chofer": "chofer_id",
    "tracto": "tracto_id",
    "rampla": "rampla_id",
    "contacto": "contacto_id",
}
_TABLA_ENTIDAD = {
    "cliente": "clientes",
    "chofer": "choferes",
    "tracto": "tractos",
    "rampla": "ramplas",
    "contacto": "contactos_whatsapp",
}

ACCIONES_SIN_EJECUTOR = frozenset({"crear_viajes_masivo", "cambiar_tarifa"})

_PATRON_CLAVE_REGLA = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_PATRON_DIRECTIVA = re.compile(r"^directiva_[a-z0-9_]{2,60}$")


# ---------------------------------------------------------------------------
# Validadores (unitarios, sin base)
# ---------------------------------------------------------------------------
def validar_entidad(entidad: Any) -> str:
    if not isinstance(entidad, str) or entidad not in ENTIDADES:
        raise DatosInvalidos(
            "Entidad no válida.",
            contexto={"entidades_permitidas": sorted(ENTIDADES)},
        )
    return entidad


def validar_clave_regla(clave: Any) -> str:
    if not isinstance(clave, str) or not _PATRON_CLAVE_REGLA.fullmatch(clave):
        raise DatosInvalidos(
            "Clave de regla inválida: use 3 a 64 caracteres en minúsculas, "
            "empezando por letra (dígitos y guion bajo permitidos).",
            contexto={"clave": clave},
        )
    return clave


def validar_clave_directiva(clave: Any) -> str:
    if isinstance(clave, str) and clave in CATALOGO:
        # SEC-051: el catálogo (IVA, alertas) no se toca desde el chat. El
        # prompt lo prohíbe, pero la UI/prompt no son autoridad: el backend sí.
        raise DatosInvalidos(
            "Esa clave se cambia por el flujo de configuración, no por el chat.",
            contexto={"clave": clave, "claves_catalogo": sorted(CATALOGO)},
        )
    if not isinstance(clave, str) or not _PATRON_DIRECTIVA.fullmatch(clave):
        raise DatosInvalidos(
            "Clave de directiva inválida: use `directiva_` seguido de 2 a 60 "
            "caracteres en minúsculas, dígitos o guion bajo.",
            contexto={"clave": clave},
        )
    return clave


def validar_accion_critica(accion: Any) -> str:
    if not isinstance(accion, str) or accion not in ACCIONES_CRITICAS:
        raise DatosInvalidos(
            "Acción no permitida para el buzón.",
            contexto={"acciones_permitidas": sorted(ACCIONES_CRITICAS)},
        )
    return accion


def _json_serializable(valor: Any, campo: str) -> None:
    try:
        json.dumps(valor, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise DatosInvalidos(
            f"`{campo}` debe ser JSON serializable."
        ) from exc


def _mismo_json(actual: Any, nuevo: Any) -> bool:
    try:
        return json.dumps(
            actual, sort_keys=True, ensure_ascii=False, allow_nan=False
        ) == json.dumps(
            nuevo, sort_keys=True, ensure_ascii=False, allow_nan=False
        )
    except (TypeError, ValueError):
        return actual == nuevo


# ---------------------------------------------------------------------------
# Helpers de contexto y lectura
# ---------------------------------------------------------------------------
def _usuario_empresa_id(session: Session, contexto: ContextoEmpresa) -> str:
    fila = session.execute(
        text(
            """
            select id::text
              from nucleo.usuarios_empresa
             where empresa_id = :empresa_id
               and auth_id = :auth_id
               and activo
             limit 1
            """
        ),
        {"empresa_id": contexto.empresa_id, "auth_id": contexto.auth_id},
    ).scalar_one_or_none()
    if fila is None:
        raise AccesoDenegado(
            "El usuario no tiene una membresía activa en la empresa."
        )
    return str(fila)


def _viajes_por_estado(
    session: Session, empresa_id: UUID, *, dias: int = 30
) -> list[dict[str, Any]]:
    filas = session.execute(
        text(
            """
            select estado::text as estado, count(*)::int as total
              from nucleo.viajes
             where empresa_id = :empresa_id
               and inicio_planificado >= now() - make_interval(days => :dias)
             group by estado
             order by estado
            """
        ),
        {"empresa_id": empresa_id, "dias": dias},
    ).mappings()
    return [dict(f) for f in filas]


def configuracion_vigente(
    session: Session, empresa_id: UUID
) -> list[dict[str, Any]]:
    filas = session.execute(
        text(
            """
            select clave, valor
              from nucleo.configuracion_empresa
             where empresa_id = :empresa_id and vigente_hasta is null
             order by clave
            """
        ),
        {"empresa_id": empresa_id},
    ).mappings()
    return [dict(f) for f in filas]


def reglas_abiertas(
    session: Session, empresa_id: UUID, *, limit: int = 50
) -> list[dict[str, Any]]:
    """Reglas por entidad vigentes (máx. 50) de la empresa."""
    filas = session.execute(
        text(
            """
            select entidad::text as entidad,
                   clave,
                   valor,
                   coalesce(cliente_id, chofer_id, tracto_id,
                            rampla_id, contacto_id)::text as entidad_id
              from nucleo.tenant_reglas_entidad
             where empresa_id = :empresa_id and vigente_hasta is null
             order by entidad, clave
             limit :limit
            """
        ),
        {"empresa_id": empresa_id, "limit": limit},
    ).mappings()
    return [dict(f) for f in filas]


def _iso(valor: Any) -> Any:
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    return valor


_Q2 = Decimal("0.01")


def _fecha_opcional(valor: Any, campo: str) -> date | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, bool):
        raise DatosInvalidos(f"`{campo}` debe ser una fecha ISO (AAAA-MM-DD).")
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor.strip())
        except ValueError as exc:
            raise DatosInvalidos(
                f"`{campo}` debe ser una fecha ISO (AAAA-MM-DD)."
            ) from exc
    raise DatosInvalidos(f"`{campo}` debe ser una fecha ISO (AAAA-MM-DD).")


def _periodo(args: dict[str, Any]) -> tuple[date, date]:
    """Período semiabierto `[desde, hasta)`. Por defecto, el mes en curso."""
    hoy = date.today()
    desde = _fecha_opcional(args.get("desde"), "desde") or hoy.replace(day=1)
    hasta = _fecha_opcional(args.get("hasta"), "hasta") or (hoy + timedelta(days=1))
    if hasta <= desde:
        raise DatosInvalidos("`hasta` debe ser posterior a `desde`.")
    if (hasta - desde).days > 3660:
        raise DatosInvalidos("El período no puede superar 10 años.")
    return desde, hasta


def _uuid_opcional(valor: Any, campo: str) -> UUID | None:
    if valor in (None, ""):
        return None
    try:
        return UUID(str(valor))
    except (TypeError, ValueError) as exc:
        raise DatosInvalidos(f"`{campo}` debe ser un UUID.") from exc


def _limite(args: dict[str, Any], por_defecto: int = 20, maximo: int = 100) -> int:
    valor = args.get("limite")
    if valor is None:
        return por_defecto
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise DatosInvalidos("`limite` debe ser un entero.")
    return max(1, min(maximo, valor))


def _q2(valor: Any) -> Decimal:
    return Decimal(valor or 0).quantize(_Q2, rounding=ROUND_HALF_UP)


def _filas_json(filas: Any) -> list[dict[str, Any]]:
    return [
        {clave: _iso(valor) for clave, valor in fila.items()} for fila in filas
    ]


def _texto_opcional(valor: Any, campo: str, *, maximo: int = 120) -> str | None:
    if valor in (None, ""):
        return None
    if not isinstance(valor, str):
        raise DatosInvalidos(f"`{campo}` debe ser texto.")
    limpio = valor.strip()
    if len(limpio) > maximo:
        raise DatosInvalidos(f"`{campo}` supera {maximo} caracteres.")
    return limpio or None


# ---------------------------------------------------------------------------
# Tools del gerente
# ---------------------------------------------------------------------------
def _gerente_leer_contexto(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    return {
        "empresa": getattr(contexto.empresa, "razon_social", "la empresa"),
        "viajes_30_dias": _viajes_por_estado(session, contexto.empresa_id),
        "configuracion_vigente": configuracion_vigente(
            session, contexto.empresa_id
        ),
        "reglas_abiertas": reglas_abiertas(session, contexto.empresa_id),
        "estado_tool": "ok",
        "resumen": "Contexto de la empresa leído.",
    }


def _gerente_upsert_directiva(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    clave = validar_clave_directiva(args.get("clave"))
    valor = args.get("valor")
    motivo = args.get("motivo")
    if valor is None:
        raise DatosInvalidos("Falta `valor` de la directiva.")

    # SEC-051: solo `directiva_*`. Las claves del catálogo (IVA, alertas) se
    # cambian por el flujo de configuración y el chat no puede escribirlas.
    servicio = ServicioConfiguracion(session, contexto)
    item, cambiado = servicio.actualizar_directiva(clave, valor, commit=False)

    return {
        "clave": item.clave,
        "valor": item.valor,
        "cambiado": cambiado,
        "motivo": motivo,
        "estado_tool": "ok" if cambiado else "sin_cambios",
        "resumen": (
            f"Directiva {item.clave} actualizada."
            if cambiado
            else f"Directiva {item.clave} sin cambios (valor idéntico)."
        ),
    }


def _gerente_upsert_regla_entidad(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    entidad = validar_entidad(args.get("entidad"))
    clave = validar_clave_regla(args.get("clave"))
    valor = args.get("valor")
    if valor is None:
        raise DatosInvalidos("Falta `valor` de la regla.")
    _json_serializable(valor, "valor")
    try:
        entidad_id = UUID(str(args.get("entidad_id")))
    except (TypeError, ValueError) as exc:
        raise DatosInvalidos("`entidad_id` debe ser un UUID.") from exc

    columna = _COLUMNA_ENTIDAD[entidad]
    tabla = _TABLA_ENTIDAD[entidad]
    existe = session.execute(
        text(
            f"select 1 from nucleo.{tabla} "
            " where empresa_id = :empresa_id and id = :entidad_id"
        ),
        {"empresa_id": contexto.empresa_id, "entidad_id": entidad_id},
    ).first()
    if existe is None:
        raise RecursoNoEncontrado(
            f"La entidad {entidad} no existe en la empresa."
        )

    vigente = session.execute(
        text(
            f"""
            select id::text as id, valor
              from nucleo.tenant_reglas_entidad
             where empresa_id = :empresa_id
               and entidad = cast(:entidad as nucleo.tipo_entidad_regla)
               and clave = :clave
               and {columna} = :entidad_id
               and vigente_hasta is null
             limit 1
             for update
            """
        ),
        {
            "empresa_id": contexto.empresa_id,
            "entidad": entidad,
            "clave": clave,
            "entidad_id": entidad_id,
        },
    ).mappings().first()
    if vigente is not None and _mismo_json(vigente["valor"], valor):
        return {
            "entidad": entidad,
            "entidad_id": str(entidad_id),
            "clave": clave,
            "valor": vigente["valor"],
            "cambiado": False,
            "estado_tool": "sin_cambios",
            "resumen": f"Regla {clave} sin cambios (valor idéntico).",
        }

    try:
        fila = session.execute(
            text(
                f"""
                with cerrada as (
                    update nucleo.tenant_reglas_entidad
                       set vigente_hasta = now(),
                           updated_at = now(),
                           updated_by = :auth_id
                     where empresa_id = :empresa_id
                       and entidad = cast(:entidad as nucleo.tipo_entidad_regla)
                       and clave = :clave
                       and {columna} = :entidad_id
                       and vigente_hasta is null
                     returning vigente_hasta
                )
                insert into nucleo.tenant_reglas_entidad
                    (empresa_id, entidad, {columna}, clave, valor,
                     vigente_desde, created_by)
                select :empresa_id,
                       cast(:entidad as nucleo.tipo_entidad_regla),
                       :entidad_id, :clave, cast(:valor as jsonb),
                       coalesce((select vigente_hasta from cerrada), now()),
                       :auth_id
                returning id::text, valor
                """
            ),
            {
                "empresa_id": contexto.empresa_id,
                "entidad": entidad,
                "clave": clave,
                "entidad_id": entidad_id,
                "valor": json.dumps(valor, ensure_ascii=False),
                "auth_id": contexto.auth_id,
            },
        ).mappings().one()
    except IntegrityError as exc:
        estado = _sqlstate(exc)
        if estado in {"23505", "23P01"}:
            raise ConflictoConcurrencia(
                "Otra transacción cambió la misma regla al mismo tiempo. "
                "Recargue y reintente."
            ) from exc
        if estado == "23514":
            raise DatosInvalidos(
                "El valor de la regla no cumple una restricción de la base."
            ) from exc
        raise traducir_integrity_error(exc) from exc

    return {
        "entidad": entidad,
        "entidad_id": str(entidad_id),
        "clave": clave,
        "valor": fila["valor"],
        "cambiado": True,
        "estado_tool": "ok",
        "resumen": f"Regla {clave} registrada para {entidad}.",
    }


def _gerente_listar_reglas(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    reglas = reglas_abiertas(session, contexto.empresa_id)
    return {
        "reglas": reglas,
        "total": len(reglas),
        "estado_tool": "ok",
        "resumen": f"{len(reglas)} regla(s) abierta(s).",
    }


def _gerente_solicitar_modulo(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    modulo = args.get("modulo")
    if not isinstance(modulo, str):
        raise DatosInvalidos("Falta `modulo`.")
    estado = servicio_modulos.estado(session, contexto, modulo)
    if not estado["activo"]:
        return {
            **estado,
            "mensaje": estado["mensaje_upsell"],
            "estado_tool": "upsell",
            "resumen": estado["mensaje_upsell"],
        }
    return {
        **estado,
        "estado_tool": "ok",
        "resumen": f"El módulo {modulo} ya está activo.",
    }


# ---------------------------------------------------------------------------
# Tools de la secretaria
# ---------------------------------------------------------------------------
def _secretaria_consultar_viajes(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    filas = session.execute(
        text(
            """
            select id::text as id,
                   numero_viaje,
                   estado::text as estado,
                   inicio_planificado,
                   fin_planificado
              from nucleo.viajes
             where empresa_id = :empresa_id
             order by inicio_planificado desc, id desc
             limit 10
            """
        ),
        {"empresa_id": contexto.empresa_id},
    ).mappings()
    ultimos = [
        {
            "id": f["id"],
            "numero_viaje": f["numero_viaje"],
            "estado": f["estado"],
            "inicio_planificado": _iso(f["inicio_planificado"]),
            "fin_planificado": _iso(f["fin_planificado"]),
        }
        for f in filas
    ]
    return {
        "por_estado": _viajes_por_estado(session, contexto.empresa_id),
        "ultimos": ultimos,
        "estado_tool": "ok",
        "resumen": f"{len(ultimos)} viaje(s) reciente(s).",
    }


def _secretaria_consultar_solicitudes(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    filas = session.execute(
        text(
            """
            select id::text as id,
                   tipo::text as tipo,
                   estado::text as estado,
                   coalesce(payload->>'accion', '') as accion,
                   created_at
              from nucleo.solicitudes
             where empresa_id = :empresa_id and estado = 'pendiente'
             order by created_at desc, id desc
             limit 20
            """
        ),
        {"empresa_id": contexto.empresa_id},
    ).mappings()
    items = [
        {
            "id": f["id"],
            "tipo": f["tipo"],
            "estado": f["estado"],
            "accion": f["accion"],
            "creada_en": _iso(f["created_at"]),
        }
        for f in filas
    ]
    return {
        "items": items,
        "total": len(items),
        "estado_tool": "ok",
        "resumen": f"{len(items)} solicitud(es) pendiente(s).",
    }


def _secretaria_whatsapp_recordatorio(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    """Prepara (no envía) un recordatorio de viaje por WhatsApp.

    SEC-052: es una tool **premium** (`modulo="whatsapp"`). El runtime consulta
    el muro de pago antes de llamarla; si el módulo no está activo, ni siquiera
    se ejecuta esta función. Aquí no hay proveedor ni envío real: solo se valida
    el viaje de la empresa y se devuelve el texto listo.
    """
    try:
        viaje_uuid = UUID(str(args.get("viaje_id")))
    except (TypeError, ValueError) as exc:
        raise DatosInvalidos("`viaje_id` debe ser un UUID.") from exc
    mensaje = args.get("mensaje")
    if mensaje is not None and not isinstance(mensaje, str):
        raise DatosInvalidos("`mensaje` debe ser texto.")

    fila = session.execute(
        text(
            """
            select numero_viaje, estado::text as estado
              from nucleo.viajes
             where empresa_id = :empresa_id and id = :viaje_id
            """
        ),
        {"empresa_id": contexto.empresa_id, "viaje_id": viaje_uuid},
    ).mappings().first()
    if fila is None:
        raise RecursoNoEncontrado("El viaje indicado no existe en la empresa.")

    return {
        "canal": "whatsapp",
        "viaje_id": str(viaje_uuid),
        "numero_viaje": fila["numero_viaje"],
        "estado_viaje": fila["estado"],
        "mensaje": mensaje
        or f"Recordatorio del viaje {fila['numero_viaje']}",
        "estado": "preparado",
        "enviado": False,
        "estado_tool": "ok",
        "resumen": "Recordatorio preparado; no se envió nada.",
    }


def _secretaria_crear_solicitud(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    accion = validar_accion_critica(args.get("accion"))
    datos = args.get("datos")
    if datos is None:
        datos = {}
    if not isinstance(datos, dict):
        raise DatosInvalidos("`datos` debe ser un objeto JSON.")
    motivo = args.get("motivo")
    viaje_id = args.get("viaje_id") or datos.get("viaje_id")
    if viaje_id is not None:
        try:
            viaje_uuid = UUID(str(viaje_id))
        except (TypeError, ValueError) as exc:
            raise DatosInvalidos("`viaje_id` debe ser un UUID.") from exc
        existe = session.execute(
            text(
                "select 1 from nucleo.viajes "
                " where empresa_id = :empresa_id and id = :viaje_id"
            ),
            {"empresa_id": contexto.empresa_id, "viaje_id": viaje_uuid},
        ).first()
        if existe is None:
            raise RecursoNoEncontrado(
                "El viaje indicado no existe en la empresa."
            )
    else:
        viaje_uuid = None

    datos_validados = dict(datos)
    if accion == "crear_viaje":
        try:
            ViajeCreateNucleo(**datos_validados)
        except ValidationError as exc:
            raise DatosInvalidos(
                "Los datos del viaje no son válidos.",
                errores=[
                    {"campo": ".".join(str(p) for p in e["loc"]), "mensaje": e["msg"]}
                    for e in exc.errors()[:10]
                ],
            ) from exc
    elif accion == "anular_viaje":
        motivo_final = motivo or datos_validados.get("motivo")
        if viaje_uuid is None:
            raise DatosInvalidos("Anular un viaje exige `viaje_id`.")
        try:
            anulacion = SolicitudAnulacionViaje(motivo=motivo_final)
        except ValidationError as exc:
            raise DatosInvalidos(
                "La anulación exige un motivo de al menos 5 caracteres."
            ) from exc
        datos_validados["viaje_id"] = str(viaje_uuid)
        datos_validados["motivo"] = anulacion.motivo
    else:
        # Acciones cuyo payload aún no tiene schema propio: al menos exigir
        # contenido; el ejecutor del buzón las rechazará con 501 al confirmar.
        if not datos_validados:
            raise DatosInvalidos(
                f"La acción {accion} exige un objeto `datos` no vacío."
            )
        _json_serializable(datos_validados, "datos")
        if motivo:
            datos_validados["motivo"] = motivo

    if accion in ACCIONES_SIN_EJECUTOR:
        # No es un rechazo: la solicitud se registra; el aviso queda en la
        # respuesta para que el modelo no prometa ejecución inmediata.
        aviso = (
            "La acción quedará pendiente y su ejecución todavía no está "
            "automatizada en el buzón."
        )
    else:
        aviso = None

    # SEC-055/057: la procedencia queda persistida y la clave es única por
    # invocación. La idempotencia del *turno* ya la cubre
    # `agente_chat_mensajes.clave_idempotencia`: un reintento del cliente no
    # vuelve a ejecutar la tool. Repetir la misma acción meses después sí debe
    # crear una solicitud nueva, no devolver una ya decidida.
    payload = {
        "accion": accion,
        "datos": datos_validados,
        "origen": "chat_inapp",
        "agente": "secretaria",
    }
    clave = f"chat-{uuid4()}"
    usuario = _usuario_empresa_id(session, contexto)

    fila = session.execute(
        text(
            """
            insert into nucleo.solicitudes
                (empresa_id, tipo, solicitante_usuario_empresa_id, viaje_id,
                 payload, clave_idempotencia)
            values
                (:empresa_id, 'otra', :usuario, cast(:viaje_id as uuid),
                 cast(:payload as jsonb), :clave)
            on conflict (empresa_id, clave_idempotencia)
                where clave_idempotencia is not null
            do nothing
            returning id::text as id, estado::text as estado
            """
        ),
        {
            "empresa_id": contexto.empresa_id,
            "usuario": usuario,
            "viaje_id": None if viaje_uuid is None else str(viaje_uuid),
            "payload": json.dumps(payload, ensure_ascii=False),
            "clave": clave,
        },
    ).mappings().first()
    creada = fila is not None
    if fila is None:
        fila = session.execute(
            text(
                """
                select id::text as id, estado::text as estado
                  from nucleo.solicitudes
                 where empresa_id = :empresa_id
                   and clave_idempotencia = :clave
                """
            ),
            {"empresa_id": contexto.empresa_id, "clave": clave},
        ).mappings().one()

    resultado: dict[str, Any] = {
        "solicitud_id": fila["id"],
        "estado": fila["estado"],
        "mensaje": "Requiere aprobación del dueño",
        "creada": creada,
        "estado_tool": "ok",
        "resumen": (
            f"Solicitud de {accion} "
            + ("creada" if creada else "ya existente")
            + "; pendiente de aprobación."
        ),
    }
    if aviso:
        resultado["aviso"] = aviso
    return resultado


# ---------------------------------------------------------------------------
# Tools de consulta compartidas (gerente y secretaria)
# ---------------------------------------------------------------------------
def _consultar_clientes(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    desde, hasta = _periodo(args)
    q = _texto_opcional(args.get("q"), "q")
    patron = f"%{q}%" if q else None
    limite = _limite(args)
    filas = session.execute(
        text(
            """
            select c.id::text as id,
                   c.razon_social,
                   c.rut,
                   c.dias_pago,
                   c.credito_autorizado,
                   c.activo,
                   count(v.id)::int as viajes
              from nucleo.clientes c
              left join nucleo.viajes v
                on v.empresa_id = c.empresa_id
               and v.cliente_id = c.id
               and v.inicio_planificado >= :desde
               and v.inicio_planificado < :hasta
             where c.empresa_id = :empresa_id
               and (:patron is null
                    or c.razon_social ilike :patron
                    or c.rut ilike :patron)
             group by c.id
             order by c.razon_social
             limit :limite
            """
        ),
        {
            "empresa_id": contexto.empresa_id,
            "desde": desde,
            "hasta": hasta,
            "patron": patron,
            "limite": limite,
        },
    ).mappings()
    items = _filas_json(filas)
    return {
        "clientes": items,
        "total": len(items),
        "periodo": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
        "estado_tool": "ok",
        "resumen": f"{len(items)} cliente(s) encontrados.",
    }


def _consultar_viajes(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    desde, hasta = _periodo(args)
    estado = _texto_opcional(args.get("estado"), "estado", maximo=30)
    if estado is not None:
        try:
            estado = EstadoViaje(estado).value
        except ValueError as exc:
            raise DatosInvalidos(
                "Estado de viaje no válido.",
                contexto={"estados": [e.value for e in EstadoViaje]},
            ) from exc
    cliente_id = _uuid_opcional(args.get("cliente_id"), "cliente_id")
    patente = _texto_opcional(args.get("patente"), "patente", maximo=20)
    patron_patente = f"%{patente}%" if patente else None
    limite = _limite(args)
    filas = session.execute(
        text(
            """
            select v.id::text as id,
                   v.numero_viaje,
                   v.estado::text as estado,
                   c.razon_social as cliente,
                   v.inicio_planificado,
                   v.fin_planificado,
                   v.monto_total_neto,
                   t.patente,
                   nullif(trim(coalesce(ch.nombre, '') || ' ' ||
                               coalesce(ch.apellido_paterno, '')), '') as chofer
              from nucleo.viajes v
              join nucleo.clientes c
                on c.empresa_id = v.empresa_id and c.id = v.cliente_id
              left join nucleo.tractos t
                on t.empresa_id = v.empresa_id and t.id = v.tracto_id
              left join nucleo.choferes ch
                on ch.empresa_id = v.empresa_id and ch.id = v.chofer_id
             where v.empresa_id = :empresa_id
               and v.inicio_planificado >= :desde
               and v.inicio_planificado < :hasta
               and (:estado is null or v.estado::text = :estado)
               and (:cliente_id is null or v.cliente_id = :cliente_id)
               and (:patron_patente is null or t.patente ilike :patron_patente)
             order by v.inicio_planificado desc, v.id desc
             limit :limite
            """
        ),
        {
            "empresa_id": contexto.empresa_id,
            "desde": desde,
            "hasta": hasta,
            "estado": estado,
            "cliente_id": cliente_id,
            "patron_patente": patron_patente,
            "limite": limite,
        },
    ).mappings()
    items = _filas_json(filas)
    return {
        "viajes": items,
        "total": len(items),
        "periodo": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
        "estado_tool": "ok",
        "resumen": f"{len(items)} viaje(s) encontrados.",
    }


def _consultar_facturas(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    desde, hasta = _periodo(args)
    cliente_id = _uuid_opcional(args.get("cliente_id"), "cliente_id")
    estado = _texto_opcional(args.get("estado"), "estado", maximo=20)
    q = _texto_opcional(args.get("q"), "q")
    limite = _limite(args)
    facturas = ServicioFacturacion(session, contexto).listar_facturas(
        cliente_id=cliente_id,
        estado=estado,
        solo_vencidas=bool(args.get("solo_vencidas", False)),
        q=q,
        limit=1000,
    )
    filtradas = [
        f for f in facturas if desde <= f.fecha_emision < hasta
    ][:limite]
    items = [f.model_dump(mode="json") for f in filtradas]
    return {
        "facturas": items,
        "total": len(items),
        "periodo": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
        "estado_tool": "ok",
        "resumen": f"{len(items)} factura(s) en el período.",
    }


def _secretaria_facturas_pendientes(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    cliente_id = _uuid_opcional(args.get("cliente_id"), "cliente_id")
    limite = _limite(args, por_defecto=30)
    facturas = ServicioFacturacion(session, contexto).listar_facturas(
        cliente_id=cliente_id, limit=1000
    )
    pendientes = [
        f for f in facturas if f.saldo > 0 and f.estado != "anulada"
    ][:limite]
    items = [
        {
            "id": str(f.id),
            "numero_factura": f.numero_factura,
            "cliente": f.cliente_nombre,
            "fecha_emision": f.fecha_emision.isoformat(),
            "fecha_vencimiento": f.fecha_vencimiento.isoformat(),
            "total": str(_q2(f.total)),
            "saldo": str(_q2(f.saldo)),
            "dias_atraso": f.dias_atraso,
            "aging": f.aging,
        }
        for f in pendientes
    ]
    total = _q2(sum((f.saldo for f in pendientes), Decimal("0")))
    return {
        "facturas": items,
        "total": len(items),
        "saldo_total": str(total),
        "estado_tool": "ok",
        "resumen": (
            f"{len(items)} factura(s) pendientes; saldo ${total:,.2f}."
        ),
    }


def _consultar_cobranza(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    desde, hasta = _periodo(args)
    aging = ServicioFacturacion(session, contexto).aging().model_dump(mode="json")
    filas = session.execute(
        text(
            """
            select p.fecha,
                   p.monto,
                   f.numero_factura,
                   c.razon_social as cliente
              from nucleo.pagos_nucleo p
              join nucleo.facturas_nucleo f
                on f.empresa_id = p.empresa_id and f.id = p.factura_id
              join nucleo.clientes c
                on c.empresa_id = f.empresa_id and c.id = f.cliente_id
             where p.empresa_id = :empresa_id
               and p.fecha >= :desde and p.fecha < :hasta
             order by p.fecha desc, p.id desc
             limit 20
            """
        ),
        {"empresa_id": contexto.empresa_id, "desde": desde, "hasta": hasta},
    ).mappings()
    pagos = _filas_json(filas)
    return {
        "cartera": aging,
        "pagos_recientes": pagos,
        "periodo": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
        "estado_tool": "ok",
        "resumen": (
            f"Cartera ${aging.get('total_cxc', '0')}; "
            f"{len(pagos)} pago(s) en el período."
        ),
    }


def _resumen_economico(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    desde, hasta = _periodo(args)
    params = {"empresa_id": contexto.empresa_id, "desde": desde, "hasta": hasta}
    viajes = session.execute(
        text(
            """
            select estado::text as estado, count(*)::int as total
              from nucleo.viajes
             where empresa_id = :empresa_id
               and inicio_planificado >= :desde
               and inicio_planificado < :hasta
             group by estado
             order by estado
            """
        ),
        params,
    ).mappings()
    facturado = session.execute(
        text(
            """
            select coalesce(sum(neto), 0) as neto,
                   coalesce(sum(total), 0) as total
              from nucleo.facturas_nucleo
             where empresa_id = :empresa_id
               and estado <> 'anulada'
               and fecha_emision >= :desde
               and fecha_emision < :hasta
            """
        ),
        params,
    ).mappings().one()
    cobrado = session.execute(
        text(
            """
            select coalesce(sum(monto), 0) as total
              from nucleo.pagos_nucleo
             where empresa_id = :empresa_id
               and fecha >= :desde and fecha < :hasta
            """
        ),
        params,
    ).scalar_one()
    costos = session.execute(
        text(
            """
            select coalesce(sum(g.monto_neto), 0) as total
              from nucleo.viaje_gastos g
              join nucleo.viajes v
                on v.empresa_id = g.empresa_id and v.id = g.viaje_id
             where g.empresa_id = :empresa_id
               and g.estado = 'aprobado'
               and g.activo
               and v.inicio_planificado >= :desde
               and v.inicio_planificado < :hasta
            """
        ),
        params,
    ).scalar_one()
    aging = ServicioFacturacion(session, contexto).aging()
    margen = _q2(Decimal(facturado["neto"]) - Decimal(costos))
    return {
        "periodo": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
        "viajes_por_estado": _filas_json(viajes),
        "facturado_neto": str(_q2(facturado["neto"])),
        "facturado_total": str(_q2(facturado["total"])),
        "cobrado": str(_q2(cobrado)),
        "costos_aprobados": str(_q2(costos)),
        "margen_operativo": str(margen),
        "cartera": aging.model_dump(mode="json"),
        "nota": (
            "Resumen operativo calculado con facturas, pagos y gastos "
            "aprobados; no es un balance contable formal."
        ),
        "estado_tool": "ok",
        "resumen": (
            f"Facturado neto ${_q2(facturado['neto']):,.2f}; "
            f"margen operativo ${margen:,.2f}."
        ),
    }


def _margen_por_camion(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    desde, hasta = _periodo(args)
    limite = _limite(args, por_defecto=30)
    filas = session.execute(
        text(
            """
            select t.patente,
                   count(v.id)::int as viajes,
                   coalesce(sum(coalesce(v.monto_total_neto,
                                         v.valor_flete_neto + v.monto_recargos,
                                         0)), 0) as ingreso,
                   coalesce(sum(g.costo), 0) as costo
              from nucleo.viajes v
              join nucleo.tractos t
                on t.empresa_id = v.empresa_id and t.id = v.tracto_id
              left join lateral (
                  select coalesce(sum(vg.monto_neto), 0) as costo
                    from nucleo.viaje_gastos vg
                   where vg.empresa_id = v.empresa_id
                     and vg.viaje_id = v.id
                     and vg.estado = 'aprobado'
                     and vg.activo
              ) g on true
             where v.empresa_id = :empresa_id
               and v.tracto_id is not null
               and v.estado <> 'anulado'
               and v.inicio_planificado >= :desde
               and v.inicio_planificado < :hasta
             group by t.patente
             order by (coalesce(sum(coalesce(v.monto_total_neto,
                                            v.valor_flete_neto + v.monto_recargos,
                                            0)), 0)
                       - coalesce(sum(g.costo), 0)) desc
             limit :limite
            """
        ),
        {
            "empresa_id": contexto.empresa_id,
            "desde": desde,
            "hasta": hasta,
            "limite": limite,
        },
    ).mappings()
    items = []
    for fila in filas:
        ingreso = _q2(fila["ingreso"])
        costo = _q2(fila["costo"])
        margen = _q2(ingreso - costo)
        porcentaje = (
            (margen / ingreso * Decimal("100")).quantize(
                _Q2, rounding=ROUND_HALF_UP
            )
            if ingreso > 0
            else None
        )
        items.append(
            {
                "patente": fila["patente"],
                "viajes": int(fila["viajes"]),
                "ingreso": str(ingreso),
                "costo": str(costo),
                "margen": str(margen),
                "margen_pct": None if porcentaje is None else str(porcentaje),
            }
        )
    return {
        "camiones": items,
        "total": len(items),
        "periodo": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
        "estado_tool": "ok",
        "resumen": f"Margen calculado para {len(items)} camión(es).",
    }


def _consultar_gastos(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    desde, hasta = _periodo(args)
    tipo = _texto_opcional(args.get("tipo"), "tipo", maximo=30)
    viaje_id = _uuid_opcional(args.get("viaje_id"), "viaje_id")
    limite = _limite(args)
    filas = session.execute(
        text(
            """
            select g.id::text as id,
                   g.fecha,
                   g.tipo,
                   g.proveedor,
                   g.monto_neto,
                   g.monto_total,
                   g.estado,
                   v.numero_viaje,
                   c.razon_social as cliente
              from nucleo.viaje_gastos g
              join nucleo.viajes v
                on v.empresa_id = g.empresa_id and v.id = g.viaje_id
              join nucleo.clientes c
                on c.empresa_id = v.empresa_id and c.id = v.cliente_id
             where g.empresa_id = :empresa_id
               and g.activo
               and g.fecha >= :desde and g.fecha < :hasta
               and (:tipo is null or g.tipo = :tipo)
               and (:viaje_id is null or g.viaje_id = :viaje_id)
             order by g.fecha desc, g.id desc
             limit :limite
            """
        ),
        {
            "empresa_id": contexto.empresa_id,
            "desde": desde,
            "hasta": hasta,
            "tipo": tipo,
            "viaje_id": viaje_id,
            "limite": limite,
        },
    ).mappings()
    items = _filas_json(filas)
    return {
        "gastos": items,
        "total": len(items),
        "periodo": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
        "estado_tool": "ok",
        "resumen": f"{len(items)} gasto(s) en el período.",
    }


def _consultar_tarifas(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    cliente_id = _uuid_opcional(args.get("cliente_id"), "cliente_id")
    q = _texto_opcional(args.get("q"), "q")
    patron = f"%{q}%" if q else None
    limite = _limite(args)
    filas = session.execute(
        text(
            """
            select t.id::text as id,
                   c.razon_social as cliente,
                   t.codigo,
                   t.nombre,
                   t.modalidad::text as modalidad,
                   t.origen,
                   t.destino,
                   t.precio_unitario,
                   t.moneda,
                   t.vigencia_desde,
                   t.vigencia_hasta
              from nucleo.tarifas t
              join nucleo.clientes c
                on c.empresa_id = t.empresa_id and c.id = t.cliente_id
             where t.empresa_id = :empresa_id
               and t.activo
               and (t.vigencia_hasta is null or t.vigencia_hasta >= current_date)
               and (:cliente_id is null or t.cliente_id = :cliente_id)
               and (:patron is null
                    or t.codigo ilike :patron
                    or t.nombre ilike :patron
                    or t.origen ilike :patron
                    or t.destino ilike :patron)
             order by t.codigo
             limit :limite
            """
        ),
        {
            "empresa_id": contexto.empresa_id,
            "cliente_id": cliente_id,
            "patron": patron,
            "limite": limite,
        },
    ).mappings()
    items = _filas_json(filas)
    return {
        "tarifas": items,
        "total": len(items),
        "estado_tool": "ok",
        "resumen": f"{len(items)} tarifa(s) vigentes.",
    }


def _consultar_ordenes_compra(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    cliente_id = _uuid_opcional(args.get("cliente_id"), "cliente_id")
    estado = _texto_opcional(args.get("estado"), "estado", maximo=20)
    limite = _limite(args)
    filas = session.execute(
        text(
            """
            select o.id::text as id,
                   c.razon_social as cliente,
                   o.numero_oc,
                   o.monto_autorizado,
                   o.monto_consumido,
                   o.sobregiro_autorizado,
                   o.moneda,
                   o.vigencia_desde,
                   o.vigencia_hasta,
                   o.estado::text as estado
              from nucleo.ordenes_compra o
              join nucleo.clientes c
                on c.empresa_id = o.empresa_id and c.id = o.cliente_id
             where o.empresa_id = :empresa_id
               and o.vigencia_hasta >= current_date
               and (:cliente_id is null or o.cliente_id = :cliente_id)
               and (:estado is null or o.estado::text = :estado)
             order by o.vigencia_hasta, o.numero_oc
             limit :limite
            """
        ),
        {
            "empresa_id": contexto.empresa_id,
            "cliente_id": cliente_id,
            "estado": estado,
            "limite": limite,
        },
    ).mappings()
    items = _filas_json(filas)
    return {
        "ordenes_compra": items,
        "total": len(items),
        "estado_tool": "ok",
        "resumen": f"{len(items)} orden(es) de compra vigentes.",
    }


def _consultar_maestros(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    limite = _limite(args, por_defecto=100, maximo=200)
    choferes = session.execute(
        text(
            """
            select id::text as id,
                   rut,
                   nullif(trim(coalesce(nombre, '') || ' ' ||
                               coalesce(apellido_paterno, '')), '') as nombre,
                   activo
              from nucleo.choferes
             where empresa_id = :empresa_id
             order by nombre
             limit :limite
            """
        ),
        {"empresa_id": contexto.empresa_id, "limite": limite},
    ).mappings()
    tractos = session.execute(
        text(
            """
            select id::text as id, patente, marca, modelo, activo
              from nucleo.tractos
             where empresa_id = :empresa_id
             order by patente
             limit :limite
            """
        ),
        {"empresa_id": contexto.empresa_id, "limite": limite},
    ).mappings()
    ramplas = session.execute(
        text(
            """
            select id::text as id, patente, tipo::text as tipo, activo
              from nucleo.ramplas
             where empresa_id = :empresa_id
             order by patente
             limit :limite
            """
        ),
        {"empresa_id": contexto.empresa_id, "limite": limite},
    ).mappings()
    return {
        "choferes": _filas_json(choferes),
        "tractos": _filas_json(tractos),
        "ramplas": _filas_json(ramplas),
        "estado_tool": "ok",
        "resumen": "Maestros de la empresa leídos.",
    }


def _consultar_configuracion(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    return {
        "configuracion": configuracion_vigente(session, contexto.empresa_id),
        "reglas_abiertas": reglas_abiertas(session, contexto.empresa_id),
        "estado_tool": "ok",
        "resumen": "Configuración y reglas vigentes leídas.",
    }


def _consultar_iva(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    desde, hasta = _periodo(args)
    resumen = ServicioIva(session, contexto).resumen(
        desde, hasta - timedelta(days=1)
    )
    return {
        "iva": resumen.model_dump(mode="json"),
        "periodo": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
        "estado_tool": "ok",
        "resumen": "Resumen de IVA del período.",
    }


def _consultar_alertas(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    tablero = ServicioAlertas(session, contexto).tablero()
    return {
        "alertas": tablero.model_dump(mode="json"),
        "estado_tool": "ok",
        "resumen": "Tablero de alertas leído.",
    }


# ---------------------------------------------------------------------------
# Tools de escritura del gerente
# ---------------------------------------------------------------------------
def _gerente_crear_viaje(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    datos = args.get("datos")
    if not isinstance(datos, dict):
        raise DatosInvalidos("`datos` debe ser un objeto con el viaje.")
    try:
        propuesta = ViajeCreateNucleo(**datos)
    except ValidationError as exc:
        raise DatosInvalidos(
            "Los datos del viaje no son válidos.",
            errores=[
                {"campo": ".".join(str(p) for p in e["loc"]), "mensaje": e["msg"]}
                for e in exc.errors()[:10]
            ],
        ) from exc
    viaje = ServicioDisponibilidad(session, contexto).crear_viaje(
        propuesta, commit=False
    )
    return {
        "viaje": viaje.model_dump(mode="json"),
        "estado_tool": "ok",
        "resumen": f"Viaje {viaje.numero_viaje} creado.",
    }


def _gerente_anular_viaje(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    viaje_id = _uuid_opcional(args.get("viaje_id"), "viaje_id")
    if viaje_id is None:
        raise DatosInvalidos("Falta `viaje_id`.")
    try:
        data = SolicitudAnulacionViaje(motivo=args.get("motivo"))
    except ValidationError as exc:
        raise DatosInvalidos(
            "La anulación exige un motivo de al menos 5 caracteres."
        ) from exc
    resultado = ServicioTransiciones(session, contexto).anular(
        viaje_id, data, commit=False
    )
    return {
        "viaje": resultado.model_dump(mode="json"),
        "estado_tool": "ok",
        "resumen": "Viaje anulado y reservas liberadas.",
    }


def _gerente_crear_tarifa(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    datos = args.get("datos")
    if not isinstance(datos, dict):
        raise DatosInvalidos("`datos` debe ser un objeto con la tarifa.")
    try:
        data = TarifaCreate(**datos)
    except ValidationError as exc:
        raise DatosInvalidos(
            "Los datos de la tarifa no son válidos.",
            errores=[
                {"campo": ".".join(str(p) for p in e["loc"]), "mensaje": e["msg"]}
                for e in exc.errors()[:10]
            ],
        ) from exc
    tarifa = ServicioComercial(session, contexto).crear_tarifa(
        data, commit=False
    )
    return {
        "tarifa": tarifa.model_dump(mode="json"),
        "estado_tool": "ok",
        "resumen": f"Tarifa {tarifa.codigo} creada.",
    }


def _gerente_crear_orden_compra(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    datos = args.get("datos")
    if not isinstance(datos, dict):
        raise DatosInvalidos("`datos` debe ser un objeto con la orden de compra.")
    try:
        data = OrdenCompraCreate(**datos)
    except ValidationError as exc:
        raise DatosInvalidos(
            "Los datos de la orden de compra no son válidos.",
            errores=[
                {"campo": ".".join(str(p) for p in e["loc"]), "mensaje": e["msg"]}
                for e in exc.errors()[:10]
            ],
        ) from exc
    oc = ServicioComercial(session, contexto).crear_oc(data, commit=False)
    return {
        "orden_compra": oc.model_dump(mode="json"),
        "estado_tool": "ok",
        "resumen": f"Orden de compra {oc.numero_oc} creada.",
    }


def _gerente_actualizar_catalogo(
    session: Session, contexto: ContextoEmpresa, args: dict[str, Any]
) -> dict[str, Any]:
    clave = args.get("clave")
    if not isinstance(clave, str) or clave not in CATALOGO:
        raise DatosInvalidos(
            "Clave de configuración no reconocida.",
            contexto={"claves_permitidas": sorted(CATALOGO)},
        )
    valor = args.get("valor")
    if valor is None:
        raise DatosInvalidos("Falta `valor`.")
    item = ServicioConfiguracion(session, contexto).actualizar(
        clave, valor, commit=False
    )
    return {
        "clave": item.clave,
        "valor": item.valor,
        "estado_tool": "ok",
        "resumen": f"Configuración {item.clave} actualizada.",
    }


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------
EjecutarHerramienta = Callable[
    [Session, ContextoEmpresa, dict[str, Any]], dict[str, Any]
]


@dataclass(frozen=True, slots=True)
class Herramienta:
    nombre: str
    descripcion: str
    parametros: dict[str, Any]
    agente: str
    ejecutar: EjecutarHerramienta
    # Capacidad del catálogo (`capacidades.py`) que autoriza esta tool. El
    # runtime la exige antes de ejecutar y filtra las especificaciones que ve
    # el modelo. No es opcional: una tool sin capacidad no se ejecuta.
    capacidad: str
    modulo: str | None = None

    def especificacion_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.nombre,
                "description": self.descripcion,
                "parameters": self.parametros,
            },
        }


def _objeto(propiedades: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": propiedades,
        "required": required,
        "additionalProperties": False,
    }


HERRAMIENTAS: dict[str, Herramienta] = {
    "gerente_leer_contexto": Herramienta(
        nombre="gerente_leer_contexto",
        descripcion=(
            "Lee el resumen de la empresa: viajes de los últimos 30 días por "
            "estado, configuración vigente y reglas abiertas."
        ),
        parametros=_objeto({}, []),
        agente="gerente",
        capacidad="operacion.leer",
        ejecutar=_gerente_leer_contexto,
    ),
    "gerente_upsert_directiva": Herramienta(
        nombre="gerente_upsert_directiva",
        descripcion=(
            "Crea o actualiza una directiva libre con prefijo `directiva_`. "
            "No acepta claves del catálogo de configuración (IVA, alertas): "
            "esas se cambian por su propio flujo, nunca por el chat. "
            "Idempotente si el valor vigente es idéntico."
        ),
        parametros=_objeto(
            {
                "clave": {"type": "string", "minLength": 3, "maxLength": 70},
                "valor": {},
                "motivo": {"type": "string", "maxLength": 500},
            },
            ["clave", "valor"],
        ),
        agente="gerente",
        capacidad="configuracion.escribir_reglas",
        ejecutar=_gerente_upsert_directiva,
    ),
    "gerente_upsert_regla_entidad": Herramienta(
        nombre="gerente_upsert_regla_entidad",
        descripcion=(
            "Crea o actualiza una regla vigente para un cliente, chofer, "
            "tracto, rampla o contacto de la empresa. Cierra la vigencia "
            "anterior; el historial cerrado no se edita."
        ),
        parametros=_objeto(
            {
                "entidad": {"type": "string", "enum": sorted(ENTIDADES)},
                "entidad_id": {"type": "string", "format": "uuid"},
                "clave": {"type": "string", "minLength": 3, "maxLength": 64},
                "valor": {},
                "motivo": {"type": "string", "maxLength": 500},
            },
            ["entidad", "entidad_id", "clave", "valor"],
        ),
        agente="gerente",
        capacidad="configuracion.escribir_reglas",
        ejecutar=_gerente_upsert_regla_entidad,
    ),
    "gerente_listar_reglas": Herramienta(
        nombre="gerente_listar_reglas",
        descripcion="Lista hasta 50 reglas por entidad vigentes de la empresa.",
        parametros=_objeto({}, []),
        agente="gerente",
        capacidad="configuracion.leer",
        ejecutar=_gerente_listar_reglas,
    ),
    "gerente_solicitar_modulo": Herramienta(
        nombre="gerente_solicitar_modulo",
        descripcion=(
            "Consulta si un módulo premium está activo. Si no lo está, "
            "devuelve el mensaje de upsell; no enciende el módulo."
        ),
        parametros=_objeto(
            {
                "modulo": {
                    "type": "string",
                    "enum": sorted(servicio_modulos.MODULOS),
                }
            },
            ["modulo"],
        ),
        agente="gerente",
        capacidad="configuracion.leer",
        ejecutar=_gerente_solicitar_modulo,
    ),
    "secretaria_consultar_viajes": Herramienta(
        nombre="secretaria_consultar_viajes",
        descripcion=(
            "Lista los 10 viajes más recientes y el conteo por estado de los "
            "últimos 30 días."
        ),
        parametros=_objeto({}, []),
        agente="secretaria",
        capacidad="operacion.leer",
        ejecutar=_secretaria_consultar_viajes,
    ),
    "secretaria_consultar_solicitudes": Herramienta(
        nombre="secretaria_consultar_solicitudes",
        descripcion="Lista hasta 20 solicitudes pendientes del buzón.",
        parametros=_objeto({}, []),
        agente="secretaria",
        capacidad="agente.crear_solicitud",
        ejecutar=_secretaria_consultar_solicitudes,
    ),
    "secretaria_whatsapp_recordatorio": Herramienta(
        nombre="secretaria_whatsapp_recordatorio",
        descripcion=(
            "Prepara un recordatorio de viaje por WhatsApp **sin enviarlo**. "
            "Requiere el módulo WhatsApp activo; si no lo está, el runtime "
            "devuelve el upsell y esta tool no se ejecuta."
        ),
        parametros=_objeto(
            {
                "viaje_id": {"type": "string", "format": "uuid"},
                "mensaje": {"type": "string", "maxLength": 500},
            },
            ["viaje_id"],
        ),
        agente="secretaria",
        capacidad="whatsapp.recordatorio",
        modulo="whatsapp",
        ejecutar=_secretaria_whatsapp_recordatorio,
    ),
    "secretaria_crear_solicitud": Herramienta(
        nombre="secretaria_crear_solicitud",
        descripcion=(
            "Deja en el buzón una solicitud para una acción crítica "
            "(crear_viaje, crear_viajes_masivo, anular_viaje, cambiar_tarifa). "
            "NO ejecuta la acción: queda pendiente de aprobación del dueño."
        ),
        parametros=_objeto(
            {
                "accion": {"type": "string", "enum": sorted(ACCIONES_CRITICAS)},
                "datos": {"type": "object"},
                "viaje_id": {"type": "string", "format": "uuid"},
                "motivo": {"type": "string", "maxLength": 500},
            },
            ["accion", "datos"],
        ),
        agente="secretaria",
        capacidad="agente.crear_solicitud",
        ejecutar=_secretaria_crear_solicitud,
    ),
    # ------------------------------------------------------------------
    # Consultas del gerente
    # ------------------------------------------------------------------
    "gerente_consultar_clientes": Herramienta(
        nombre="gerente_consultar_clientes",
        descripcion=(
            "Busca clientes por nombre o RUT y devuelve sus datos de crédito "
            "y el número de viajes del período."
        ),
        parametros=_objeto(
            {
                "q": {"type": "string", "maxLength": 120},
                "desde": {"type": "string", "format": "date"},
                "hasta": {"type": "string", "format": "date"},
                "limite": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            [],
        ),
        agente="gerente",
        capacidad="comercial.leer",
        ejecutar=_consultar_clientes,
    ),
    "gerente_consultar_viajes": Herramienta(
        nombre="gerente_consultar_viajes",
        descripcion=(
            "Lista viajes del período filtrando por estado, cliente o patente. "
            "Devuelve número, cliente, estado, fechas, monto neto, tracto y chofer."
        ),
        parametros=_objeto(
            {
                "desde": {"type": "string", "format": "date"},
                "hasta": {"type": "string", "format": "date"},
                "estado": {"type": "string", "maxLength": 30},
                "cliente_id": {"type": "string", "format": "uuid"},
                "patente": {"type": "string", "maxLength": 20},
                "limite": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            [],
        ),
        agente="gerente",
        capacidad="operacion.leer",
        ejecutar=_consultar_viajes,
    ),
    "gerente_consultar_facturas": Herramienta(
        nombre="gerente_consultar_facturas",
        descripcion=(
            "Lista facturas del período por cliente o estado, con saldo, días "
            "de atraso y tramo de aging. No incluye costos ni márgenes."
        ),
        parametros=_objeto(
            {
                "desde": {"type": "string", "format": "date"},
                "hasta": {"type": "string", "format": "date"},
                "cliente_id": {"type": "string", "format": "uuid"},
                "estado": {"type": "string", "maxLength": 20},
                "solo_vencidas": {"type": "boolean"},
                "q": {"type": "string", "maxLength": 60},
                "limite": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            [],
        ),
        agente="gerente",
        capacidad="finanzas.leer_operativo",
        ejecutar=_consultar_facturas,
    ),
    "gerente_consultar_cobranza": Herramienta(
        nombre="gerente_consultar_cobranza",
        descripcion=(
            "Devuelve la cartera por tramos de aging y los últimos pagos del "
            "período."
        ),
        parametros=_objeto(
            {
                "desde": {"type": "string", "format": "date"},
                "hasta": {"type": "string", "format": "date"},
            },
            [],
        ),
        agente="gerente",
        capacidad="finanzas.leer_operativo",
        ejecutar=_consultar_cobranza,
    ),
    "gerente_resumen_economico": Herramienta(
        nombre="gerente_resumen_economico",
        descripcion=(
            "Resumen operativo del período: viajes por estado, facturado neto "
            "y total, cobrado, costos aprobados, margen operativo y cartera. "
            "No es un balance contable formal."
        ),
        parametros=_objeto(
            {
                "desde": {"type": "string", "format": "date"},
                "hasta": {"type": "string", "format": "date"},
            },
            [],
        ),
        agente="gerente",
        capacidad="finanzas.leer_estrategico",
        ejecutar=_resumen_economico,
    ),
    "gerente_margen_por_camion": Herramienta(
        nombre="gerente_margen_por_camion",
        descripcion=(
            "Calcula ingreso, costo directo aprobado, margen y porcentaje por "
            "tracto en el período."
        ),
        parametros=_objeto(
            {
                "desde": {"type": "string", "format": "date"},
                "hasta": {"type": "string", "format": "date"},
                "limite": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            [],
        ),
        agente="gerente",
        capacidad="finanzas.leer_estrategico",
        ejecutar=_margen_por_camion,
    ),
    "gerente_consultar_gastos": Herramienta(
        nombre="gerente_consultar_gastos",
        descripcion=(
            "Lista gastos activos del período por tipo o viaje, con monto neto, "
            "total, estado y proveedor."
        ),
        parametros=_objeto(
            {
                "desde": {"type": "string", "format": "date"},
                "hasta": {"type": "string", "format": "date"},
                "tipo": {"type": "string", "maxLength": 30},
                "viaje_id": {"type": "string", "format": "uuid"},
                "limite": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            [],
        ),
        agente="gerente",
        capacidad="gastos.leer",
        ejecutar=_consultar_gastos,
    ),
    "gerente_consultar_tarifas": Herramienta(
        nombre="gerente_consultar_tarifas",
        descripcion=(
            "Lista tarifas vigentes por cliente, código, origen o destino."
        ),
        parametros=_objeto(
            {
                "cliente_id": {"type": "string", "format": "uuid"},
                "q": {"type": "string", "maxLength": 120},
                "limite": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            [],
        ),
        agente="gerente",
        capacidad="comercial.leer",
        ejecutar=_consultar_tarifas,
    ),
    "gerente_consultar_ordenes_compra": Herramienta(
        nombre="gerente_consultar_ordenes_compra",
        descripcion=(
            "Lista órdenes de compra vigentes por cliente o estado, con monto "
            "autorizado, consumido y saldo."
        ),
        parametros=_objeto(
            {
                "cliente_id": {"type": "string", "format": "uuid"},
                "estado": {"type": "string", "maxLength": 20},
                "limite": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            [],
        ),
        agente="gerente",
        capacidad="comercial.leer",
        ejecutar=_consultar_ordenes_compra,
    ),
    "gerente_consultar_configuracion": Herramienta(
        nombre="gerente_consultar_configuracion",
        descripcion=(
            "Lee el catálogo de configuración vigente y las reglas abiertas de "
            "la empresa."
        ),
        parametros=_objeto({}, []),
        agente="gerente",
        capacidad="configuracion.leer",
        ejecutar=_consultar_configuracion,
    ),
    "gerente_consultar_iva": Herramienta(
        nombre="gerente_consultar_iva",
        descripcion=(
            "Resumen informativo de IVA débito del período. No es una "
            "declaración ni un F29."
        ),
        parametros=_objeto(
            {
                "desde": {"type": "string", "format": "date"},
                "hasta": {"type": "string", "format": "date"},
            },
            [],
        ),
        agente="gerente",
        capacidad="finanzas.leer_iva",
        ejecutar=_consultar_iva,
    ),
    "gerente_consultar_alertas": Herramienta(
        nombre="gerente_consultar_alertas",
        descripcion="Lee el tablero de alertas de la empresa.",
        parametros=_objeto({}, []),
        agente="gerente",
        capacidad="alertas.leer",
        ejecutar=_consultar_alertas,
    ),
    "gerente_consultar_maestros": Herramienta(
        nombre="gerente_consultar_maestros",
        descripcion=(
            "Lista choferes, tractos y ramplas de la empresa para resolver "
            "identificadores."
        ),
        parametros=_objeto(
            {"limite": {"type": "integer", "minimum": 1, "maximum": 200}},
            [],
        ),
        agente="gerente",
        capacidad="maestros.leer",
        ejecutar=_consultar_maestros,
    ),
    # ------------------------------------------------------------------
    # Escrituras del gerente
    # ------------------------------------------------------------------
    "gerente_crear_viaje": Herramienta(
        nombre="gerente_crear_viaje",
        descripcion=(
            "Crea un viaje con los datos del payload. No asigna tracto, rampla "
            "ni chofer: eso se hace en despacho."
        ),
        parametros=_objeto({"datos": {"type": "object"}}, ["datos"]),
        agente="gerente",
        capacidad="operacion.crear_viaje",
        ejecutar=_gerente_crear_viaje,
    ),
    "gerente_anular_viaje": Herramienta(
        nombre="gerente_anular_viaje",
        descripcion=(
            "Anula un viaje con un motivo de al menos 5 caracteres y libera "
            "sus reservas."
        ),
        parametros=_objeto(
            {
                "viaje_id": {"type": "string", "format": "uuid"},
                "motivo": {"type": "string", "minLength": 5, "maxLength": 500},
            },
            ["viaje_id", "motivo"],
        ),
        agente="gerente",
        capacidad="operacion.anular_viaje",
        ejecutar=_gerente_anular_viaje,
    ),
    "gerente_crear_tarifa": Herramienta(
        nombre="gerente_crear_tarifa",
        descripcion="Crea una tarifa para un cliente con los datos del payload.",
        parametros=_objeto({"datos": {"type": "object"}}, ["datos"]),
        agente="gerente",
        capacidad="comercial.escribir",
        ejecutar=_gerente_crear_tarifa,
    ),
    "gerente_crear_orden_compra": Herramienta(
        nombre="gerente_crear_orden_compra",
        descripcion="Crea una orden de compra con los datos del payload.",
        parametros=_objeto({"datos": {"type": "object"}}, ["datos"]),
        agente="gerente",
        capacidad="comercial.escribir",
        ejecutar=_gerente_crear_orden_compra,
    ),
    "gerente_actualizar_catalogo": Herramienta(
        nombre="gerente_actualizar_catalogo",
        descripcion=(
            "Actualiza una clave del catálogo cerrado de configuración "
            "(iva_porcentaje, alerta_km_mantenimiento, dias_alerta_vencimientos, "
            "dias_alerta_cobranza). No acepta directivas libres."
        ),
        parametros=_objeto(
            {
                "clave": {"type": "string", "enum": sorted(CATALOGO)},
                "valor": {},
            },
            ["clave", "valor"],
        ),
        agente="gerente",
        capacidad="configuracion.escribir_catalogo",
        ejecutar=_gerente_actualizar_catalogo,
    ),
    # ------------------------------------------------------------------
    # Consultas de la secretaria
    # ------------------------------------------------------------------
    "secretaria_consultar_clientes": Herramienta(
        nombre="secretaria_consultar_clientes",
        descripcion=(
            "Busca clientes y devuelve el total de fletes por cliente en el "
            "período. Sin costos ni márgenes."
        ),
        parametros=_objeto(
            {
                "q": {"type": "string", "maxLength": 120},
                "desde": {"type": "string", "format": "date"},
                "hasta": {"type": "string", "format": "date"},
                "limite": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            [],
        ),
        agente="secretaria",
        capacidad="comercial.leer",
        ejecutar=_consultar_clientes,
    ),
    "secretaria_consultar_facturas_pendientes": Herramienta(
        nombre="secretaria_consultar_facturas_pendientes",
        descripcion=(
            "Lista facturas con saldo pendiente y su atraso. Sin costos, "
            "márgenes ni utilidad."
        ),
        parametros=_objeto(
            {
                "cliente_id": {"type": "string", "format": "uuid"},
                "limite": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            [],
        ),
        agente="secretaria",
        capacidad="finanzas.leer_operativo",
        ejecutar=_secretaria_facturas_pendientes,
    ),
    "secretaria_consultar_tarifas": Herramienta(
        nombre="secretaria_consultar_tarifas",
        descripcion="Lista tarifas vigentes para preparar un flete.",
        parametros=_objeto(
            {
                "cliente_id": {"type": "string", "format": "uuid"},
                "q": {"type": "string", "maxLength": 120},
                "limite": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            [],
        ),
        agente="secretaria",
        capacidad="comercial.leer",
        ejecutar=_consultar_tarifas,
    ),
    "secretaria_consultar_ordenes_compra": Herramienta(
        nombre="secretaria_consultar_ordenes_compra",
        descripcion="Lista órdenes de compra vigentes del cliente.",
        parametros=_objeto(
            {
                "cliente_id": {"type": "string", "format": "uuid"},
                "estado": {"type": "string", "maxLength": 20},
                "limite": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            [],
        ),
        agente="secretaria",
        capacidad="comercial.leer",
        ejecutar=_consultar_ordenes_compra,
    ),
    "secretaria_consultar_maestros": Herramienta(
        nombre="secretaria_consultar_maestros",
        descripcion="Lista choferes, tractos y ramplas de la empresa.",
        parametros=_objeto(
            {"limite": {"type": "integer", "minimum": 1, "maximum": 200}},
            [],
        ),
        agente="secretaria",
        capacidad="maestros.leer",
        ejecutar=_consultar_maestros,
    ),
}


def especificaciones(
    persona_tools: tuple[str, ...], habilitadas: frozenset[str] | None = None
) -> list[dict[str, Any]]:
    """Especificaciones OpenAI de las tools efectivas, en orden estable.

    `habilitadas` es el conjunto de capacidades del turno. Si se omite, no se
    filtra (compatibilidad con pruebas y usos internos); el runtime siempre lo
    pasa. Una tool cuya capacidad no está habilitada no se ofrece al modelo.
    """
    return [
        HERRAMIENTAS[nombre].especificacion_openai()
        for nombre in persona_tools
        if nombre in HERRAMIENTAS
        and (
            habilitadas is None
            or HERRAMIENTAS[nombre].capacidad in habilitadas
        )
    ]


def _sqlstate(exc: IntegrityError) -> str | None:
    orig = getattr(exc, "orig", None)
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
