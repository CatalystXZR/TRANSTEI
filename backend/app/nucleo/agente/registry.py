"""Registry inmutable de tools y ejecución a través del gate.

Contrato: `docs/arquitectura/conector-agente-whatsapp.md` §2.5, §2.6, §4.

Garantías que implementa:

- **Fail-closed por manifiesto.** Si la carga falla, el registry queda con cero
  tools, registra el error y toda invocación devuelve `MODULO_INACTIVO`. La API
  no se cae (§2.5).
- **Sin caché de autorización.** El gate se re-evalúa en cada `invocar` (§4.8).
- **Transacción controlada acá.** El ejecutor recibe una `Session`; no crea
  sesiones ni hace `commit()` (§3.4, §4.10). La lectura termina con rollback
  explícito antes de auditar.
- **Timeout por tool.** `statement_timeout` se fija local a la transacción con
  el `timeout_ms` del descriptor; al vencer se devuelve `TIMEOUT_TOOL`.
- **Auditoría separada.** Una fila por intento terminado (§7.2). En lectura, si
  la auditoría falla no se entregan datos (`AUDITORIA_FALLIDA`).
- **Proyección verificada.** La salida se valida contra el schema declarado
  antes de devolverla; un desvío es `ERROR_INTERNO`, no un dato crudo.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError, SQLAlchemyError

from app.core.contexto import aplicar_contexto_sesion
from app.core.database import sesion_nucleo
from app.nucleo.agente.auditoria import datos_tocados, registrar_consulta
from app.nucleo.agente.contexto import (
    ContextoAgente,
    RolContacto,
    contexto_de_agente,
)
from app.nucleo.agente.ejecutores import EJECUTORES, EjecutorTool
from app.nucleo.agente.gate import Decision, FuenteGate, FuenteGateBD, autorizar
from app.nucleo.agente.manifest import (
    RAIZ_PAQUETE,
    Descriptor,
    EntradaInvalida,
    ErrorManifiesto,
    Manifiesto,
    ModuloCargado,
    cargar_modulo,
    validar_instancia,
)
from app.nucleo.agente.tipos import ResultadoTool

logger = logging.getLogger("app.nucleo.agente.registry")

_REINTENTABLES = frozenset(
    {"TIMEOUT_TOOL", "CONFLICTO_CONCURRENCIA", "CODIGO_AMBIGUO", "AUDITORIA_FALLIDA"}
)

_SQL_TIMEOUT = text("select set_config('statement_timeout', :valor, true)")

_SIN_TOOLS: Mapping[str, Descriptor] = MappingProxyType({})
_SIN_SCHEMAS: Mapping[str, dict[str, Any]] = MappingProxyType({})


def _sqlstate_exc(exc: BaseException) -> str | None:
    actual: BaseException | None = exc
    for _ in range(4):
        if actual is None:
            return None
        orig = getattr(actual, "orig", None)
        estado = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
        if estado:
            return str(estado)
        actual = actual.__cause__ or actual.__context__
    return None


def clasificar_error(exc: BaseException) -> str:
    """SQLSTATE → código estable de tool (§4.6). No expone el mensaje de PG."""
    estado = _sqlstate_exc(exc)
    if isinstance(exc, IntegrityError):
        return {
            "23505": "CONFLICTO_IDEMPOTENCIA",
            "23514": "REGLA_NEGOCIO",
            "23503": "REFERENCIA_INVALIDA",
            "40001": "CONFLICTO_CONCURRENCIA",
            "40P01": "CONFLICTO_CONCURRENCIA",
        }.get(estado or "", "ERROR_INTERNO")
    if isinstance(exc, ProgrammingError) and estado == "42501":
        return "NO_AUTORIZADO"
    if estado == "57014":
        return "TIMEOUT_TOOL"
    if estado in {"40001", "40P01"}:
        return "CONFLICTO_CONCURRENCIA"
    return "ERROR_INTERNO"


def _limite(descriptor: Descriptor, entrada: dict[str, Any]) -> int | None:
    if descriptor.tipo != "lectura":
        return None
    tope = int(descriptor.max_filas)  # validado en V11
    pedido = entrada.get("limite")
    if pedido is None:
        return tope
    return max(1, min(int(pedido), tope))


def _nombre_seguro(nombre: Any) -> str:
    """Nombre de tool apto para envelope y auditoría (`SEC-032`).

    El nombre lo elige el modelo cuando intenta una tool inexistente; puede
    traer megabytes o caracteres de control. Se conserva solo lo que cabe en un
    identificador razonable y se recorta duro.
    """
    texto = nombre if isinstance(nombre, str) else repr(nombre)
    limpio = "".join(c for c in texto if c.isprintable())[:120]
    return limpio or "<vacío>"


_RE_PREGUNTA = re.compile(r"^[a-z][a-z0-9_.]{0,63}( \[[a-z0-9_,]{0,300}\])?$")
_LARGO_PREGUNTA = 200


def _derivacion(
    herramienta: str, entrada: dict[str, Any], schema: dict[str, Any] | None
) -> str:
    """`<herramienta> [<clave>,…]` con **solo** claves declaradas en el schema.

    Se filtran las claves no declaradas: una entrada inválida no debe dejar su
    nombre en la auditoría (contrato §7.3.1).
    """
    propiedades = schema.get("properties", {}) if isinstance(schema, dict) else {}
    claves = sorted(clave for clave in entrada if clave in propiedades)
    return f"{herramienta} [{','.join(claves)}]"[:_LARGO_PREGUNTA]


def _pregunta_resumida(
    herramienta: str,
    entrada: dict[str, Any],
    explicita: str | None,
    *,
    descriptor: Descriptor | None,
    schema: dict[str, Any] | None,
) -> str:
    """Etiqueta de auditoría cerrada (§7.3.1): qué tool y con qué claves.

    El registry **no confía** en el runtime: si el valor no tiene la forma
    canónica o trae una clave no declarada, se descarta y se persiste la
    derivación determinista. No se "limpia" el texto: se sustituye, porque la
    tabla es append-only y no se purga.
    """
    # Tool desconocida: solo el nombre saneado, sin claves ni texto del llamador.
    if descriptor is None:
        return herramienta[:_LARGO_PREGUNTA]

    derivada = _derivacion(herramienta, entrada, schema)
    if explicita is None:
        return derivada

    candidata = explicita.strip()
    if len(candidata) > _LARGO_PREGUNTA or not _RE_PREGUNTA.fullmatch(candidata):
        logger.warning(
            "agente.pregunta_no_conforme herramienta=%s motivo=forma", herramienta
        )
        return derivada

    cabeza, _, resto = candidata.partition(" [")
    if cabeza != herramienta:
        logger.warning(
            "agente.pregunta_no_conforme herramienta=%s motivo=tool", herramienta
        )
        return derivada

    propiedades = schema.get("properties", {}) if isinstance(schema, dict) else {}
    claves = [c for c in resto.rstrip("]").split(",") if c]
    if any(clave not in propiedades for clave in claves):
        logger.warning(
            "agente.pregunta_no_conforme herramienta=%s motivo=clave", herramienta
        )
        return derivada
    return candidata


def _envelope_ok(
    descriptor: Descriptor,
    resultado: ResultadoTool,
    *,
    request_id: str,
    auditoria_id: int | None,
) -> dict[str, Any]:
    return {
        "ok": True,
        "datos": resultado.datos,
        "meta": {
            "herramienta": descriptor.nombre,
            "version": descriptor.version,
            "filas": resultado.filas,
            "truncado": resultado.truncado,
            "request_id": request_id,
            "auditoria_id": auditoria_id,
        },
    }


def _envelope_error(
    codigo: str,
    *,
    descriptor: Descriptor | None,
    herramienta: str,
    request_id: str,
    auditoria_id: int | None,
    decision: Decision | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "codigo": codigo,
        "reintentable": codigo in _REINTENTABLES,
    }
    if decision is not None and decision.nivel is not None:
        # Motivo estructurado de §4.7: el runtime redacta la frase, el gate no.
        error["nivel"] = decision.nivel
        error["componente"] = decision.componente
        error["variable"] = decision.variable
    return {
        "ok": False,
        "error": error,
        "meta": {
            "herramienta": herramienta,
            "version": descriptor.version if descriptor is not None else None,
            "request_id": request_id,
            "auditoria_id": auditoria_id,
        },
    }


class Registry:
    """Vista inmutable del manifiesto validado + ejecución autorizada."""

    def __init__(
        self,
        *,
        modulo: ModuloCargado | None,
        valido: bool,
        motivo: str | None,
        ejecutores: Mapping[str, EjecutorTool] | None = None,
        fuente: FuenteGate | None = None,
    ) -> None:
        self._modulo = modulo
        self._valido = valido
        self._motivo = motivo
        self._descriptores: Mapping[str, Descriptor] = (
            modulo.descriptores if modulo is not None else _SIN_TOOLS
        )
        self._entradas: Mapping[str, dict[str, Any]] = (
            modulo.esquemas_entrada if modulo is not None else _SIN_SCHEMAS
        )
        self._salidas: Mapping[str, dict[str, Any]] = (
            modulo.esquemas_salida if modulo is not None else _SIN_SCHEMAS
        )
        self._ejecutores = ejecutores if ejecutores is not None else EJECUTORES
        self._fuente = fuente if fuente is not None else FuenteGateBD()

    # ------------------------------ lectura ------------------------------

    @property
    def valido(self) -> bool:
        return self._valido

    @property
    def motivo(self) -> str | None:
        return self._motivo

    @property
    def manifiesto(self) -> Manifiesto | None:
        return self._modulo.manifiesto if self._modulo is not None else None

    @property
    def tools_cargadas(self) -> int:
        return len(self._descriptores)

    @property
    def migraciones(self) -> tuple[str, ...]:
        return tuple(self.manifiesto.migraciones) if self.manifiesto else ()

    def get(self, nombre: str) -> Descriptor | None:
        return self._descriptores.get(nombre)

    def tools_para_rol(self, rol: RolContacto) -> list[Descriptor]:
        """Ayuda de prompt (§4.9). **No** autoriza: eso ocurre en `invocar`."""
        return sorted(
            (d for d in self._descriptores.values() if str(rol) in d.roles),
            key=lambda d: d.nombre,
        )

    def por_componente(self) -> dict[str, int]:
        conteo: dict[str, int] = {}
        for descriptor in self._descriptores.values():
            conteo[descriptor.componente] = conteo.get(descriptor.componente, 0) + 1
        return {clave: conteo[clave] for clave in sorted(conteo)}

    def estado(self) -> dict[str, Any]:
        manifiesto = self.manifiesto
        return {
            "valido": self._valido,
            "version": manifiesto.version if manifiesto else None,
            "schema_di": manifiesto.schema_di if manifiesto else None,
            "motivo": self._motivo,
        }

    # ----------------------------- ejecución -----------------------------

    def invocar(
        self,
        nombre: str,
        entrada: dict[str, Any],
        contexto: ContextoAgente,
        *,
        pregunta_resumida: str | None = None,
    ) -> dict[str, Any]:
        """Aplica el gate, ejecuta y audita. Devuelve el envelope de §4.5."""
        with contexto_de_agente(
            empresa_id=contexto.empresa_id,
            request_id=contexto.request_id,
            contacto_id=contexto.contacto_id,
        ):
            return self._invocar(nombre, entrada, contexto, pregunta_resumida)

    def _invocar(
        self,
        nombre: str,
        entrada: dict[str, Any],
        contexto: ContextoAgente,
        pregunta: str | None,
    ) -> dict[str, Any]:
        herramienta = _nombre_seguro(nombre)
        descriptor = self._descriptores.get(nombre) if self._valido else None
        pregunta = _pregunta_resumida(
            herramienta,
            entrada,
            pregunta,
            descriptor=descriptor,
            schema=self._entradas.get(nombre),
        )

        if not self._valido:
            decision = Decision(
                permitido=False,
                codigo="MODULO_INACTIVO",
                nivel="modulo",
                componente="agente",
                variable=None,
                respuesta="MODULO_INACTIVO",
            )
            return self._denegar(
                contexto,
                herramienta=herramienta,
                descriptor=None,
                decision=decision,
                pregunta=pregunta,
            )

        if descriptor is None:
            decision = Decision(
                permitido=False,
                codigo="TOOL_DESCONOCIDA",
                nivel="tool",
                componente="agente",
                variable=None,
                respuesta="TOOL_DESCONOCIDA",
            )
            return self._denegar(
                contexto,
                herramienta=herramienta,
                descriptor=None,
                decision=decision,
                pregunta=pregunta,
            )

        try:
            decision = autorizar(
                descriptor=descriptor,
                contexto=contexto,
                manifiesto_valido=self._valido,
                fuente=self._fuente,
            )
        except HTTPException:
            # Guarda de rol del engine (503 `nucleo_rls_inactivo`): es un fallo
            # de despliegue, no una decisión del gate. Se propaga tal cual.
            raise
        except Exception as exc:  # noqa: BLE001 — se clasifica por SQLSTATE
            # Si el gate no puede leer sus llaves (p. ej. `42501` en
            # `permisos_contacto`), la respuesta es denegar. Antes de esto la
            # excepción escapaba de `invocar` y la denegación quedaba **sin
            # fila de auditoría** (`SEC-031`), justo el caso que §7.4 exige
            # registrar.
            codigo = clasificar_error(exc)
            logger.error(
                "agente.gate_error herramienta=%s codigo=%s sqlstate=%s tipo=%s",
                herramienta,
                codigo,
                _sqlstate_exc(exc),
                type(exc.orig).__name__ if getattr(exc, "orig", None) is not None else type(exc).__name__,
            )
            decision = Decision(
                permitido=False,
                codigo="NO_AUTORIZADO",
                nivel="variable",
                componente=descriptor.componente,
                variable=descriptor.variable,
                respuesta=f"NO_AUTORIZADO:gate_error:{codigo}",
            )
        if not decision.permitido:
            return self._denegar(
                contexto,
                herramienta=herramienta,
                descriptor=descriptor,
                decision=decision,
                pregunta=pregunta,
            )

        # Paso 8: la autorización ya pasó; una entrada mal formada se audita
        # con `acceso_otorgado=true` (§7.5).
        try:
            validar_instancia(self._entradas[nombre], entrada)
        except EntradaInvalida as exc:
            logger.info(
                "agente.entrada_invalida tool=%s campo=%s", herramienta, exc.campo
            )
            auditoria_id = self._auditar(
                contexto,
                componente=descriptor.componente,
                variable=descriptor.variable,
                herramienta=herramienta,
                acceso=True,
                respuesta="DATOS_INVALIDOS",
                pregunta=pregunta,
            )
            return _envelope_error(
                "DATOS_INVALIDOS",
                descriptor=descriptor,
                herramienta=herramienta,
                request_id=contexto.request_id,
                auditoria_id=auditoria_id,
            )

        limite = _limite(descriptor, entrada)
        try:
            resultado = self._ejecutar(descriptor, contexto, entrada, limite)
        except Exception as exc:
            codigo = clasificar_error(exc)
            estado = _sqlstate_exc(exc)
            if not isinstance(exc, SQLAlchemyError):
                # Bug de código: el traceback no arrastra parámetros de SQL.
                logger.exception("agente.tool_error tool=%s", herramienta)
            else:
                # Error de base: se registran código y tipo, nunca `repr(exc)`
                # ni el traceback, porque el mensaje de SQLAlchemy incluye el
                # SQL y los parámetros ligados (AGENTS.md §4).
                logger.error(
                    "agente.tool_error tool=%s codigo=%s sqlstate=%s tipo=%s",
                    herramienta,
                    codigo,
                    estado,
                    type(exc.orig).__name__ if exc.orig is not None else type(exc).__name__,
                )
            auditoria_id = self._auditar(
                contexto,
                componente=descriptor.componente,
                variable=descriptor.variable,
                herramienta=herramienta,
                acceso=True,
                respuesta=codigo,
                pregunta=pregunta,
            )
            return _envelope_error(
                codigo,
                descriptor=descriptor,
                herramienta=herramienta,
                request_id=contexto.request_id,
                auditoria_id=auditoria_id,
            )

        try:
            validar_instancia(self._salidas[nombre], resultado.datos)
        except (EntradaInvalida, ErrorManifiesto) as exc:
            logger.error(
                "agente.salida_invalida tool=%s motivo=%s", herramienta, exc
            )
            auditoria_id = self._auditar(
                contexto,
                componente=descriptor.componente,
                variable=descriptor.variable,
                herramienta=herramienta,
                acceso=True,
                respuesta="ERROR_INTERNO",
                pregunta=pregunta,
            )
            return _envelope_error(
                "ERROR_INTERNO",
                descriptor=descriptor,
                herramienta=herramienta,
                request_id=contexto.request_id,
                auditoria_id=auditoria_id,
            )

        auditoria_id = self._auditar(
            contexto,
            componente=descriptor.componente,
            variable=descriptor.variable,
            herramienta=herramienta,
            acceso=True,
            respuesta=f"OK:{resultado.filas}",
            pregunta=pregunta,
            datos=datos_tocados(
                ids=resultado.ids,
                total=resultado.total,
                tool_version=descriptor.version,
                schema_di=self.manifiesto.schema_di if self.manifiesto else "di/v1",
            ),
        )
        if descriptor.tipo == "lectura" and auditoria_id is None:
            # §7.2: no se entrega dato sin rastro.
            return _envelope_error(
                "AUDITORIA_FALLIDA",
                descriptor=descriptor,
                herramienta=herramienta,
                request_id=contexto.request_id,
                auditoria_id=None,
            )
        return _envelope_ok(
            descriptor,
            resultado,
            request_id=contexto.request_id,
            auditoria_id=auditoria_id,
        )

    # ----------------------------- internos ------------------------------

    def _ejecutar(
        self,
        descriptor: Descriptor,
        contexto: ContextoAgente,
        entrada: dict[str, Any],
        limite: int | None,
    ) -> ResultadoTool:
        ejecutor = self._ejecutores[descriptor.ejecutor]
        with sesion_nucleo() as session:
            aplicar_contexto_sesion(session)
            session.execute(_SQL_TIMEOUT, {"valor": str(descriptor.timeout_ms)})
            try:
                return ejecutor(contexto, entrada, limite, session)
            finally:
                # Lectura: no hay nada que confirmar y no se deja la
                # transacción abierta mientras se escribe la auditoría.
                session.rollback()

    def _auditar(
        self,
        contexto: ContextoAgente,
        *,
        componente: str,
        variable: str | None,
        herramienta: str,
        acceso: bool,
        respuesta: str,
        pregunta: str,
        datos: dict[str, Any] | None = None,
    ) -> int | None:
        return registrar_consulta(
            contexto=contexto,
            componente=componente,
            variable=variable,
            herramienta=herramienta,
            acceso_otorgado=acceso,
            respuesta=respuesta,
            pregunta_resumida=pregunta,
            datos=datos,
        )

    def _denegar(
        self,
        contexto: ContextoAgente,
        *,
        herramienta: str,
        descriptor: Descriptor | None,
        decision: Decision,
        pregunta: str,
    ) -> dict[str, Any]:
        auditoria_id = self._auditar(
            contexto,
            componente=decision.componente,
            variable=decision.variable,
            herramienta=herramienta,
            acceso=False,
            respuesta=decision.respuesta or decision.codigo or "NO_AUTORIZADO",
            pregunta=pregunta,
        )
        return _envelope_error(
            decision.codigo or "NO_AUTORIZADO",
            descriptor=descriptor,
            herramienta=herramienta,
            request_id=contexto.request_id,
            auditoria_id=auditoria_id,
            decision=decision,
        )


# ---------------------------------------------------------------------------
# Singleton por proceso
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_registry: Registry | None = None


def _motivo_publicable(texto: str) -> str:
    """Quita la ruta absoluta del despliegue del mensaje de diagnóstico.

    `/nucleo/agente/estado` devuelve `manifest.motivo`; publicar
    `/Users/…/backend/app/nucleo/agente` revela la estructura del host sin
    aportar nada al operador (`SEC-034`).
    """
    return texto.replace(str(RAIZ_PAQUETE), "<paquete-agente>")


def cargar_registry(*, recargar: bool = False) -> Registry:
    """Carga el módulo una vez por proceso. Nunca lanza (§2.5)."""
    global _registry
    if _registry is not None and not recargar:
        return _registry
    with _lock:
        if _registry is not None and not recargar:
            return _registry
        try:
            modulo = cargar_modulo(RAIZ_PAQUETE, EJECUTORES)
        except ErrorManifiesto as exc:
            logger.error("agente.manifest_invalido %s", exc)
            _registry = Registry(
                modulo=None, valido=False, motivo=_motivo_publicable(str(exc))
            )
        except Exception as exc:
            # Un schema que rompe el validador de otra forma (bug propio, archivo
            # ilegible por permisos, keyword nueva) no puede tumbar la API: se
            # deja el registry cerrado y el detalle va al log (`SEC-036`).
            logger.exception(
                "agente.manifest_no_cargable tipo=%s", type(exc).__name__
            )
            _registry = Registry(
                modulo=None,
                valido=False,
                motivo=f"manifiesto no cargable: {type(exc).__name__}",
            )
        else:
            _registry = Registry(modulo=modulo, valido=True, motivo=None)
        return _registry
