"""Manifiesto del módulo agente: carga y validación estricta.

Contrato: `docs/arquitectura/conector-agente-whatsapp.md` §2 (reglas V1–V16) y
§3 (descriptor de tool).

Decisiones de implementación que el contrato no resuelve literalmente:

1. **V5 y los `$ref` de entrada/salida.** El texto de V5 exige que todo `$ref`
   empiece con `tools/`, pero §3.1 define `entrada`/`salida` como
   `{"$ref": "schemas/<archivo>.json"}`. Se interpreta V5 como aplicable a los
   `$ref` del array `tools[]` del manifiesto; los `$ref` de un descriptor deben
   empezar con `schemas/`. Ambos se resuelven con la misma función, que rechaza
   rutas absolutas, `..`, barras invertidas y archivos inexistentes.
2. **`jsonschema` no está instalado y no se autorizó instalar dependencias.**
   Se implementa un validador del subconjunto realmente usado por los seis
   schemas del módulo: `type`, `enum`, `const`, `format` (`date-time`, `date`,
   `uuid`), `minimum`/`maximum`, `required`, `properties`,
   `additionalProperties=false`, `items`, `minItems`/`maxItems`,
   `minLength`/`maxLength`, `pattern`. Cualquier keyword no soportada invalida
   el schema (fail-closed): un portero que ignora lo que no entiende no es
   estricto.
3. **Reglas de §3.3 no numeradas en la tabla V.** Se aplican igual y se
   reportan con la V más cercana y el motivo explícito: campos de autoridad en
   el body (`empresa_id`, `contacto_id`, `rol`, `usuario_empresa_id`,
   `version`) y palabras de SQL (`sql`, `query`, `tabla`, `where`, `orden`,
   `join`, `select`).
4. **Sin corrección silenciosa.** Un valor fuera de rango no se recorta: el
   manifiesto completo se rechaza. El registry queda con 0 tools y la API sigue
   viva (§2.5).

El módulo no toca la base al cargar: solo lee archivos. La verificación de
tablas (`to_regclass`) es del endpoint de estado y del gate, no del manifiesto.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger("app.nucleo.agente.manifest")

RAIZ_PAQUETE = Path(__file__).resolve().parent
MODULO_ID = "agente-whatsapp"
DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"

# Conjunto cerrado de §2.4 V15 y roles de `nucleo.rol_contacto_whatsapp`.
PERMISOS_MODULO = frozenset({"agente:buzon", "agente:aprobar", "agente:contactos"})
ROLES_CONTACTO = frozenset({"admin", "cliente_final", "conductor"})
TIPOS_TOOL = frozenset({"lectura", "escritura_solicitud"})
ALCANCES = frozenset({"propio", "empresa"})

# §3.3.2 / §3.3.3: campos que no pueden venir del modelo.
CAMPOS_AUTORIDAD = frozenset(
    {"empresa_id", "contacto_id", "rol", "usuario_empresa_id", "version"}
)
CAMPOS_SQL = frozenset({"sql", "query", "tabla", "where", "orden", "join", "select"})
CAMPOS_ENTIDAD_PROPIA = frozenset({"cliente_id", "chofer_id"})

_NOMBRE_TOOL = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
_NOMBRE_COMPONENTE = re.compile(r"^[a-z][a-z0-9_]*$")
_NOMBRE_VARIABLE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

# ---------------------------------------------------------------------------
# Validador JSON Schema (subconjunto, fail-closed)
# ---------------------------------------------------------------------------

_PALABRAS_CLAVE = frozenset(
    {
        "$schema",
        "title",
        "description",
        "type",
        "enum",
        "const",
        "format",
        "minimum",
        "maximum",
        "required",
        "properties",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
        "pattern",
    }
)
_TIPOS = frozenset(
    {"object", "array", "string", "integer", "number", "boolean", "null"}
)
_FORMATOS = frozenset({"date-time", "date", "uuid"})


class ErrorManifiesto(Exception):
    """Manifiesto o descriptor inválido. Lleva la regla y la ruta del campo."""

    def __init__(self, regla: str, ruta: str, motivo: str) -> None:
        self.regla = regla
        self.ruta = ruta
        self.motivo = motivo
        super().__init__(f"{regla} en {ruta}: {motivo}")


class EntradaInvalida(Exception):
    """Entrada de tool que no cumple el schema declarado (→ DATOS_INVALIDOS)."""

    def __init__(self, campo: str, motivo: str) -> None:
        self.campo = campo
        self.motivo = motivo
        super().__init__(f"{campo}: {motivo}")


def _tipos_de(nodo: dict[str, Any], ruta: str) -> tuple[str, ...]:
    tipo = nodo.get("type")
    if isinstance(tipo, str):
        tipos = (tipo,)
    elif isinstance(tipo, list) and tipo and all(isinstance(t, str) for t in tipo):
        tipos = tuple(tipo)
    else:
        raise ErrorManifiesto("V13", ruta, "cada schema debe declarar `type`")
    desconocidos = [t for t in tipos if t not in _TIPOS]
    if desconocidos:
        raise ErrorManifiesto("V13", ruta, f"tipo no soportado: {desconocidos[0]}")
    if len(set(tipos)) != len(tipos):
        raise ErrorManifiesto("V13", ruta, "`type` repite tipos")
    return tipos


def _validar_nodo(nodo: Any, ruta: str) -> None:
    if not isinstance(nodo, dict):
        raise ErrorManifiesto("V13", ruta, "el schema debe ser un objeto JSON")
    desconocidas = sorted(set(nodo) - _PALABRAS_CLAVE)
    if desconocidas:
        raise ErrorManifiesto(
            "V13",
            ruta,
            f"keyword no soportada (fail-closed): {', '.join(desconocidas)}",
        )
    tipos = _tipos_de(nodo, ruta)

    if "object" in tipos:
        propiedades = nodo.get("properties")
        if not isinstance(propiedades, dict):
            raise ErrorManifiesto("V13", ruta, "objeto sin `properties`")
        if nodo.get("additionalProperties") is not False:
            raise ErrorManifiesto(
                "V13", ruta, "todo objeto exige `additionalProperties=false`"
            )
        for nombre, sub in propiedades.items():
            _validar_nodo(sub, f"{ruta}.{nombre}")
        requeridos = nodo.get("required")
        if requeridos is not None:
            if not isinstance(requeridos, list) or not all(
                isinstance(x, str) for x in requeridos
            ):
                raise ErrorManifiesto("V13", ruta, "`required` debe ser lista de strings")
            faltan = sorted(set(requeridos) - set(propiedades))
            if faltan:
                raise ErrorManifiesto(
                    "V13", ruta, f"`required` declara propiedades inexistentes: {faltan}"
                )

    if "array" in tipos:
        if "items" not in nodo:
            raise ErrorManifiesto("V13", ruta, "array sin `items`")
        _validar_nodo(nodo["items"], f"{ruta}[]")

    formato = nodo.get("format")
    if formato is not None and formato not in _FORMATOS:
        raise ErrorManifiesto("V13", ruta, f"formato no soportado: {formato!r}")

    patron = nodo.get("pattern")
    if patron is not None:
        if not isinstance(patron, str):
            raise ErrorManifiesto("V13", ruta, "`pattern` debe ser string")
        try:
            re.compile(patron)
        except re.error as exc:
            raise ErrorManifiesto("V13", ruta, f"`pattern` inválido: {exc}") from exc

    for clave in ("minimum", "maximum"):
        valor = nodo.get(clave)
        if valor is not None and (
            isinstance(valor, bool) or not isinstance(valor, (int, float))
        ):
            raise ErrorManifiesto("V13", ruta, f"`{clave}` debe ser numérico")
    if (
        isinstance(nodo.get("minimum"), (int, float))
        and isinstance(nodo.get("maximum"), (int, float))
        and nodo["minimum"] > nodo["maximum"]
    ):
        raise ErrorManifiesto("V13", ruta, "`minimum` mayor que `maximum`")

    for clave in ("minItems", "maxItems", "minLength", "maxLength"):
        valor = nodo.get(clave)
        if valor is not None and (
            isinstance(valor, bool) or not isinstance(valor, int) or valor < 0
        ):
            raise ErrorManifiesto("V13", ruta, f"`{clave}` debe ser entero >= 0")

    enumeracion = nodo.get("enum")
    if enumeracion is not None and (
        not isinstance(enumeracion, list) or not enumeracion
    ):
        raise ErrorManifiesto("V13", ruta, "`enum` debe ser lista no vacía")


def validar_documento_schema(documento: Any, etiqueta: str) -> None:
    """Valida que un documento sea un JSON Schema del subconjunto soportado."""
    if not isinstance(documento, dict):
        raise ErrorManifiesto("V13", etiqueta, "el schema debe ser un objeto JSON")
    declarado = documento.get("$schema")
    if declarado is not None and declarado != DRAFT_2020_12:
        raise ErrorManifiesto(
            "V13", etiqueta, f"$schema distinto de draft 2020-12: {declarado!r}"
        )
    if documento.get("type") != "object":
        raise ErrorManifiesto("V13", etiqueta, "la raíz del schema debe ser object")
    _validar_nodo(documento, etiqueta)


def _tipo_coincide(tipo: str, valor: Any) -> bool:
    if tipo == "null":
        return valor is None
    if tipo == "boolean":
        return isinstance(valor, bool)
    if tipo == "integer":
        return isinstance(valor, int) and not isinstance(valor, bool)
    if tipo == "number":
        return isinstance(valor, (int, float)) and not isinstance(valor, bool)
    if tipo == "string":
        return isinstance(valor, str)
    if tipo == "object":
        return isinstance(valor, dict)
    if tipo == "array":
        return isinstance(valor, list)
    return False


_FECHA_HORA = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)


def _validar_formato(formato: str, valor: str, ruta: str) -> None:
    if formato == "date-time":
        if not _FECHA_HORA.fullmatch(valor):
            raise EntradaInvalida(ruta, "no es fecha-hora RFC 3339 con zona")
        try:
            datetime.fromisoformat(valor.replace("Z", "+00:00").replace("z", "+00:00"))
        except ValueError as exc:
            raise EntradaInvalida(ruta, "fecha-hora inválida") from exc
    elif formato == "date":
        try:
            date.fromisoformat(valor)
        except ValueError as exc:
            raise EntradaInvalida(ruta, "fecha inválida (se espera YYYY-MM-DD)") from exc
    elif formato == "uuid":
        try:
            UUID(valor)
        except (ValueError, TypeError) as exc:
            raise EntradaInvalida(ruta, "UUID inválido") from exc


def _validar_valor(schema: dict[str, Any], valor: Any, ruta: str) -> None:
    tipos = _tipos_de(schema, ruta)
    if not any(_tipo_coincide(t, valor) for t in tipos):
        raise EntradaInvalida(ruta, f"se esperaba {'/'.join(tipos)}")

    if "const" in schema and valor != schema["const"]:
        raise EntradaInvalida(ruta, f"se esperaba {schema['const']!r}")
    enumeracion = schema.get("enum")
    if enumeracion is not None and valor not in enumeracion:
        raise EntradaInvalida(ruta, "valor fuera del enum")

    if isinstance(valor, bool):
        return

    if isinstance(valor, dict):
        propiedades = schema.get("properties", {})
        requeridos = schema.get("required", [])
        faltan = [k for k in requeridos if k not in valor]
        if faltan:
            raise EntradaInvalida(ruta, f"faltan campos obligatorios: {faltan}")
        if schema.get("additionalProperties") is False:
            extra = sorted(set(valor) - set(propiedades))
            if extra:
                raise EntradaInvalida(ruta, f"campos no declarados: {extra}")
        for clave, sub in propiedades.items():
            if clave in valor:
                _validar_valor(sub, valor[clave], f"{ruta}.{clave}")
        return

    if isinstance(valor, list):
        minimo = schema.get("minItems")
        maximo = schema.get("maxItems")
        if minimo is not None and len(valor) < minimo:
            raise EntradaInvalida(ruta, f"mínimo {minimo} elementos")
        if maximo is not None and len(valor) > maximo:
            raise EntradaInvalida(ruta, f"máximo {maximo} elementos")
        if "items" in schema:
            for indice, elemento in enumerate(valor):
                _validar_valor(schema["items"], elemento, f"{ruta}[{indice}]")
        return

    if isinstance(valor, str):
        minimo = schema.get("minLength")
        maximo = schema.get("maxLength")
        if minimo is not None and len(valor) < minimo:
            raise EntradaInvalida(ruta, f"largo mínimo {minimo}")
        if maximo is not None and len(valor) > maximo:
            raise EntradaInvalida(ruta, f"largo máximo {maximo}")
        patron = schema.get("pattern")
        if patron is not None and re.search(patron, valor) is None:
            raise EntradaInvalida(ruta, "no cumple el patrón declarado")
        formato = schema.get("format")
        if formato is not None:
            _validar_formato(formato, valor, ruta)
        return

    if isinstance(valor, (int, float)):
        minimo = schema.get("minimum")
        maximo = schema.get("maximum")
        if minimo is not None and valor < minimo:
            raise EntradaInvalida(ruta, f"menor que el mínimo {minimo}")
        if maximo is not None and valor > maximo:
            raise EntradaInvalida(ruta, f"mayor que el máximo {maximo}")


def validar_instancia(schema: dict[str, Any], valor: Any) -> None:
    """Valida una instancia contra el schema. Lanza `EntradaInvalida`."""
    _validar_valor(schema, valor, "$")


# ---------------------------------------------------------------------------
# Modelos Pydantic (extra=forbid, strict) — §2.3 / §3.1
# ---------------------------------------------------------------------------


class _Estricto(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, populate_by_name=True, strict=True
    )


class Aprobacion(_Estricto):
    # Se valida en `_validar_manifiesto` con la regla V15 (no con un Literal):
    # así el diagnóstico dice V15 y no un genérico V2.
    modo: str
    autoaprobacion: bool


class Modalidades(_Estricto):
    texto: bool
    voz: bool
    imagen: bool
    pdf: bool


class Modelo(_Estricto):
    proveedor: str = Field(min_length=1)
    modelo: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)


class Modelos(_Estricto):
    orquestador: Modelo
    asr: Modelo | None = None
    vision: Modelo | None = None
    pdf: Modelo | None = None


class RefTool(_Estricto):
    ref: str = Field(alias="$ref", min_length=1)


class Manifiesto(_Estricto):
    esquema: str = Field(alias="schema", min_length=1)
    modulo_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    # V3 y V4 se validan explícitamente más abajo, para conservar el número
    # de regla en el diagnóstico.
    habilitado_por_defecto: bool
    schema_di: str
    migraciones: list[str]
    roles: list[str] = Field(min_length=1)
    componentes: list[str] = Field(min_length=1)
    permisos_modulo: list[str]
    aprobacion: Aprobacion
    modalidades: Modalidades
    modelos: Modelos
    tools: list[RefTool]


class Idempotencia(_Estricto):
    modo: str
    campo: str | None


class RefSchema(_Estricto):
    ref: str = Field(alias="$ref", min_length=1)


class Descriptor(_Estricto):
    nombre: str = Field(min_length=1)
    componente: str = Field(min_length=1)
    variable: str = Field(min_length=1)
    permiso: str = Field(min_length=1)
    tipo: Literal["lectura", "escritura_solicitud"]
    alcance: Literal["propio", "empresa"]
    roles: list[str] = Field(min_length=1)
    descripcion: str = Field(min_length=1, max_length=240)
    entrada: RefSchema
    salida: RefSchema
    ejecutor: str = Field(min_length=1)
    idempotencia: Idempotencia
    timeout_ms: int = Field(strict=True)
    max_filas: int | None
    version: int = Field(strict=True)


@dataclass(frozen=True, slots=True)
class ModuloCargado:
    """Manifiesto + descriptores + schemas resueltos, ya validados."""

    manifiesto: Manifiesto
    descriptores: Mapping[str, Descriptor]
    esquemas_entrada: Mapping[str, dict[str, Any]]
    esquemas_salida: Mapping[str, dict[str, Any]]


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------


def _sin_duplicados(pares: list[tuple[str, Any]]) -> dict[str, Any]:
    claves = [clave for clave, _ in pares]
    duplicadas = sorted({c for c in claves if claves.count(c) > 1})
    if duplicadas:
        raise ErrorManifiesto("V1", "json", f"claves duplicadas: {duplicadas}")
    return dict(pares)


def leer_json_estricto(ruta: Path) -> Any:
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError as exc:
        raise ErrorManifiesto("V1", str(ruta), f"no se pudo leer: {exc}") from exc
    try:
        return json.loads(texto, object_pairs_hook=_sin_duplicados)
    except json.JSONDecodeError as exc:
        raise ErrorManifiesto(
            "V1", str(ruta), f"JSON inválido en línea {exc.lineno}: {exc.msg}"
        ) from exc


def _formatear_validacion(exc: ValidationError) -> str:
    partes = []
    for error in exc.errors()[:5]:
        ruta = ".".join(str(p) for p in error.get("loc", ())) or "<raíz>"
        partes.append(f"{ruta}: {error.get('msg', 'inválido')}")
    return "; ".join(partes)


def _resolver_ref(ref: Any, prefijo: str, raiz: Path, regla: str) -> Path:
    if not isinstance(ref, str) or not ref:
        raise ErrorManifiesto(regla, "tools", "`$ref` vacío o no textual")
    if "#" in ref or "\\" in ref:
        raise ErrorManifiesto(regla, ref, "`$ref` no admite fragmento ni `\\`")
    partes = PurePosixPath(ref)
    if partes.is_absolute():
        raise ErrorManifiesto(regla, ref, "`$ref` absoluto")
    if ".." in partes.parts:
        raise ErrorManifiesto(regla, ref, "`$ref` con `..`")
    if len(partes.parts) < 2 or partes.parts[0] != prefijo:
        raise ErrorManifiesto(regla, ref, f"`$ref` debe empezar con `{prefijo}/`")
    destino = (raiz.joinpath(*partes.parts)).resolve()
    raiz_resuelta = raiz.resolve()
    if raiz_resuelta not in destino.parents:
        raise ErrorManifiesto(regla, ref, "`$ref` sale del paquete")
    if not destino.is_file():
        raise ErrorManifiesto(regla, ref, "el archivo referenciado no existe")
    return destino


def _validar_manifiesto(manifiesto: Manifiesto) -> None:
    if manifiesto.esquema != "agente-modulo/v1":
        raise ErrorManifiesto(
            "V2", "schema", f"se esperaba 'agente-modulo/v1', llegó {manifiesto.esquema!r}"
        )
    if manifiesto.habilitado_por_defecto is not False:
        raise ErrorManifiesto(
            "V3", "habilitado_por_defecto", "debe ser exactamente false"
        )
    if manifiesto.schema_di != "di/v1":
        raise ErrorManifiesto(
            "V4", "schema_di", f"se esperaba 'di/v1', llegó {manifiesto.schema_di!r}"
        )
    if manifiesto.modulo_id != MODULO_ID:
        raise ErrorManifiesto(
            "V2", "modulo_id", f"se esperaba {MODULO_ID!r}, llegó {manifiesto.modulo_id!r}"
        )
    if len(set(manifiesto.roles)) != len(manifiesto.roles):
        raise ErrorManifiesto("V2", "roles", "roles duplicados")
    invalidos = sorted(set(manifiesto.roles) - ROLES_CONTACTO)
    if invalidos:
        raise ErrorManifiesto("V2", "roles", f"rol no soportado: {invalidos[0]}")
    if len(set(manifiesto.componentes)) != len(manifiesto.componentes):
        raise ErrorManifiesto("V2", "componentes", "componentes duplicados")
    for componente in manifiesto.componentes:
        if not _NOMBRE_COMPONENTE.fullmatch(componente):
            raise ErrorManifiesto(
                "V2", "componentes", f"nombre de componente inválido: {componente!r}"
            )
    fuera = sorted(set(manifiesto.permisos_modulo) - PERMISOS_MODULO)
    if fuera:
        raise ErrorManifiesto("V15", "permisos_modulo", f"permiso fuera del conjunto: {fuera[0]}")
    if len(set(manifiesto.permisos_modulo)) != len(manifiesto.permisos_modulo):
        raise ErrorManifiesto("V15", "permisos_modulo", "permisos duplicados")
    # V15: `modo`/`autoaprobacion` ya son Literal; se deja explícito por claridad.
    if manifiesto.aprobacion.modo != "solicitud" or manifiesto.aprobacion.autoaprobacion:
        raise ErrorManifiesto("V15", "aprobacion", "aprobación debe ser por solicitud")

    modelos = manifiesto.modelos
    exigencias = (
        ("voz", modelos.asr, "asr"),
        ("imagen", modelos.vision, "vision"),
        ("pdf", modelos.pdf, "pdf"),
    )
    for modalidad, modelo, nombre in exigencias:
        if getattr(manifiesto.modalidades, modalidad) and modelo is None:
            raise ErrorManifiesto(
                "V16", f"modelos.{nombre}", f"modalidad {modalidad} exige {nombre}"
            )


def _validar_descriptor(
    descriptor: Descriptor,
    manifiesto: Manifiesto,
    ejecutores: Mapping[str, Any],
    ruta_ref: str,
) -> None:
    if not _NOMBRE_TOOL.fullmatch(descriptor.nombre):
        raise ErrorManifiesto(
            "V6", f"{ruta_ref}.nombre", f"nombre fuera del patrón: {descriptor.nombre!r}"
        )
    if not _NOMBRE_VARIABLE.fullmatch(descriptor.variable):
        raise ErrorManifiesto(
            "V6", f"{ruta_ref}.variable", f"variable fuera del patrón: {descriptor.variable!r}"
        )
    if descriptor.componente not in manifiesto.componentes:
        raise ErrorManifiesto(
            "V7", f"{ruta_ref}.componente", f"{descriptor.componente!r} no está en componentes"
        )
    fuera = sorted(set(descriptor.roles) - set(manifiesto.roles))
    if fuera:
        raise ErrorManifiesto(
            "V8", f"{ruta_ref}.roles", f"rol fuera del manifiesto: {fuera[0]}"
        )
    esperado = f"{descriptor.componente}:{descriptor.variable}"
    if descriptor.permiso != esperado:
        raise ErrorManifiesto(
            "V9", f"{ruta_ref}.permiso", f"se esperaba {esperado!r}"
        )
    if descriptor.ejecutor not in ejecutores:
        raise ErrorManifiesto(
            "V10", f"{ruta_ref}.ejecutor", f"{descriptor.ejecutor!r} no está en la allow-list"
        )
    if not (100 <= descriptor.timeout_ms <= 5000):
        raise ErrorManifiesto(
            "V11", f"{ruta_ref}.timeout_ms", f"fuera de 100–5000: {descriptor.timeout_ms}"
        )
    if descriptor.tipo == "lectura":
        if descriptor.max_filas is None or not (1 <= descriptor.max_filas <= 200):
            raise ErrorManifiesto(
                "V11",
                f"{ruta_ref}.max_filas",
                f"lectura exige 1–200, llegó {descriptor.max_filas!r}",
            )
    elif descriptor.max_filas is not None:
        raise ErrorManifiesto(
            "V11", f"{ruta_ref}.max_filas", "escritura exige max_filas null"
        )
    if descriptor.tipo == "escritura_solicitud":
        if descriptor.idempotencia.modo != "clave":
            raise ErrorManifiesto(
                "V12", f"{ruta_ref}.idempotencia.modo", "escritura exige modo=clave"
            )
        if descriptor.idempotencia.campo != "clave_idempotencia":
            raise ErrorManifiesto(
                "V12",
                f"{ruta_ref}.idempotencia.campo",
                "escritura exige campo=clave_idempotencia",
            )


def _cargar_schema(ref: str, raiz: Path, etiqueta: str) -> dict[str, Any]:
    ruta = _resolver_ref(ref, "schemas", raiz, "V13")
    documento = leer_json_estricto(ruta)
    validar_documento_schema(documento, etiqueta)
    if not isinstance(documento, dict):  # ya validado; ayuda a los tipos
        raise ErrorManifiesto("V13", etiqueta, "schema no es objeto")
    return documento


def _propiedades_recursivas(schema: dict[str, Any]) -> dict[str, str]:
    """Nombres de propiedad del schema y de sus objetos anidados → ruta.

    Un `cliente_id` escondido dentro de un objeto anidado burlaría una revisión
    de primer nivel (`SEC-035`). Se recorre `properties` e `items`. Si un nombre
    aparece en dos ramas se conserva la primera ruta: la prohibición es por
    nombre, no por ubicación.
    """
    encontradas: dict[str, str] = {}

    def _recorrer(nodo: Any, ruta: str) -> None:
        if not isinstance(nodo, dict):
            return
        propiedades = nodo.get("properties")
        if isinstance(propiedades, dict):
            for nombre, sub in propiedades.items():
                encontradas.setdefault(nombre, f"{ruta}.{nombre}")
                _recorrer(sub, f"{ruta}.{nombre}")
        items = nodo.get("items")
        if isinstance(items, dict):
            _recorrer(items, f"{ruta}[]")

    _recorrer(schema, "entrada")
    return encontradas


def _prohibidos_en_entrada(
    descriptor: Descriptor, schema_entrada: dict[str, Any], ruta_ref: str
) -> None:
    propiedades = set(_propiedades_recursivas(schema_entrada))
    autoridad = sorted(propiedades & CAMPOS_AUTORIDAD)
    if autoridad:
        raise ErrorManifiesto(
            "V14", f"{ruta_ref}.entrada", f"campo de autoridad en el body: {autoridad[0]}"
        )
    sql = sorted(propiedades & CAMPOS_SQL)
    if sql:
        raise ErrorManifiesto(
            "V13", f"{ruta_ref}.entrada", f"campo de SQL en el body: {sql[0]}"
        )
    if descriptor.alcance == "propio":
        entidad = sorted(propiedades & CAMPOS_ENTIDAD_PROPIA)
        if entidad:
            raise ErrorManifiesto(
                "V14", f"{ruta_ref}.entrada", f"alcance propio no admite {entidad[0]}"
            )


def cargar_modulo(
    raiz: Path = RAIZ_PAQUETE,
    ejecutores: Mapping[str, Any] | None = None,
) -> ModuloCargado:
    """Carga y valida manifiesto + descriptores + schemas. No toca la base."""
    from app.nucleo.agente.ejecutores import EJECUTORES

    permitidos: Mapping[str, Any] = ejecutores or EJECUTORES
    crudo = leer_json_estricto(raiz / "manifest.json")
    try:
        manifiesto = Manifiesto.model_validate(crudo)
    except ValidationError as exc:
        raise ErrorManifiesto("V2", "manifest.json", _formatear_validacion(exc)) from exc
    _validar_manifiesto(manifiesto)

    descriptores: dict[str, Descriptor] = {}
    entradas: dict[str, dict[str, Any]] = {}
    salidas: dict[str, dict[str, Any]] = {}
    for referencia in manifiesto.tools:
        ruta_descriptor = _resolver_ref(referencia.ref, "tools", raiz, "V5")
        crudo_descriptor = leer_json_estricto(ruta_descriptor)
        try:
            descriptor = Descriptor.model_validate(crudo_descriptor)
        except ValidationError as exc:
            raise ErrorManifiesto(
                "V6", referencia.ref, _formatear_validacion(exc)
            ) from exc
        _validar_descriptor(descriptor, manifiesto, permitidos, referencia.ref)
        if descriptor.nombre in descriptores:
            raise ErrorManifiesto(
                "V6", referencia.ref, f"nombre de tool duplicado: {descriptor.nombre}"
            )
        if descriptor.tipo == "escritura_solicitud":
            schema_previo = _cargar_schema(
                descriptor.entrada.ref, raiz, f"{descriptor.nombre}.entrada"
            )
            if "clave_idempotencia" not in schema_previo.get("properties", {}):
                raise ErrorManifiesto(
                    "V12",
                    f"{referencia.ref}.entrada",
                    "escritura exige declarar `clave_idempotencia` en la entrada",
                )
        schema_entrada = _cargar_schema(
            descriptor.entrada.ref, raiz, f"{descriptor.nombre}.entrada"
        )
        schema_salida = _cargar_schema(
            descriptor.salida.ref, raiz, f"{descriptor.nombre}.salida"
        )
        _prohibidos_en_entrada(descriptor, schema_entrada, referencia.ref)
        descriptores[descriptor.nombre] = descriptor
        entradas[descriptor.nombre] = schema_entrada
        salidas[descriptor.nombre] = schema_salida

    return ModuloCargado(
        manifiesto=manifiesto,
        descriptores=MappingProxyType(descriptores),
        esquemas_entrada=MappingProxyType(entradas),
        esquemas_salida=MappingProxyType(salidas),
    )
