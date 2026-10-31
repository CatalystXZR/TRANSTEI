"""Configuración por empresa con vigencia (migración 0026).

Reemplaza a la tabla legacy `configuracion` (schema `public`) (global, sin validación ni historial). Las
reglas que **sí** se implementan:

- catálogo explícito de claves conocidas (deny-by-default);
- validación de tipo y rango en servidor (`iva_porcentaje` en 0–100);
- un cambio de valor = cerrar la vigencia vigente e insertar una fila nueva con
  el **mismo instante** (`now()`), para que el `EXCLUDE` no detecte solape;
- valor idéntico = no-op (idempotente);
- el historial no se edita ni se borra (triggers de `0026`).

No se define la tasa de IVA: el valor sembrado (19) es paridad con el legacy y
sigue pendiente de `P-01`/`D-21`.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import (
    ConflictoConcurrencia,
    DatosInvalidos,
    RecursoNoEncontrado,
    traducir_integrity_error,
)
from app.nucleo.schemas import ConfiguracionItemOut, ConfiguracionOut

# (tipo, mínimo, máximo). El catálogo es del servicio; la base solo acota la
# forma de la clave y el rango estructural de iva_porcentaje.
CATALOGO: dict[str, tuple[str, Decimal | None, Decimal | None]] = {
    "iva_porcentaje": ("numero", Decimal("0"), Decimal("100")),
    "alerta_km_mantenimiento": ("entero", Decimal("0"), None),
    "dias_alerta_vencimientos": ("entero", Decimal("0"), None),
    "dias_alerta_cobranza": ("entero", Decimal("0"), None),
}

_COLUMNAS = "clave, valor, vigente_desde, updated_at, version"
MENSAJE = (
    "Configuración vigente por empresa. Los cambios quedan en historial "
    "append-only; el valor anterior se cierra, no se edita."
)


def _normalizar(clave: str, valor: Any) -> int | float:
    """Valida y normaliza el valor según el catálogo. Devuelve un JSON primitivo."""
    if clave not in CATALOGO:
        raise DatosInvalidos(
            "Clave de configuración no reconocida.",
            contexto={"claves_permitidas": sorted(CATALOGO)},
        )
    tipo, minimo, maximo = CATALOGO[clave]
    if isinstance(valor, bool) or valor is None:
        raise DatosInvalidos("El valor debe ser numérico.")
    if tipo == "entero":
        if isinstance(valor, float) and not valor.is_integer():
            raise DatosInvalidos("El valor debe ser un entero.")
        try:
            numero = Decimal(str(valor))
        except (InvalidOperation, ValueError) as exc:
            raise DatosInvalidos("El valor debe ser un entero.") from exc
        if numero != numero.to_integral_value():
            raise DatosInvalidos("El valor debe ser un entero.")
        entero = int(numero)
        if minimo is not None and entero < minimo:
            raise DatosInvalidos(
                "El valor está por debajo del mínimo permitido.",
                contexto={"minimo": str(minimo)},
            )
        if maximo is not None and entero > maximo:
            raise DatosInvalidos(
                "El valor supera el máximo permitido.",
                contexto={"maximo": str(maximo)},
            )
        return entero

    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError) as exc:
        raise DatosInvalidos("El valor debe ser numérico.") from exc
    if not numero.is_finite():
        raise DatosInvalidos("El valor debe ser un número finito.")
    if minimo is not None and numero < minimo:
        raise DatosInvalidos(
            "El valor está por debajo del mínimo permitido.",
            contexto={"minimo": str(minimo)},
        )
    if maximo is not None and numero > maximo:
        raise DatosInvalidos(
            "El valor supera el máximo permitido.",
            contexto={"maximo": str(maximo)},
        )
    # jsonb no tiene Decimal: se persiste como número JSON.
    return int(numero) if numero == numero.to_integral_value() else float(numero)


def _sqlstate(exc: IntegrityError) -> str | None:
    orig = getattr(exc, "orig", None)
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)


class ServicioConfiguracion:
    def __init__(self, session: Session, contexto: ContextoEmpresa) -> None:
        self.session = session
        self.contexto = contexto
        self.empresa_id = contexto.empresa_id

    def listar(self) -> ConfiguracionOut:
        filas = self.session.execute(
            text(
                f"""
                select {_COLUMNAS}
                  from nucleo.configuracion_empresa
                 where empresa_id = :empresa_id and vigente_hasta is null
                 order by clave
                """
            ),
            {"empresa_id": self.empresa_id},
        ).mappings()
        return ConfiguracionOut(
            items=[ConfiguracionItemOut.model_validate(dict(f)) for f in filas],
            mensaje=MENSAJE,
        )

    def valor_vigente(self, clave: str) -> Any:
        return self.session.execute(
            text("select nucleo.config_vigente(:empresa_id, :clave)"),
            {"empresa_id": self.empresa_id, "clave": clave},
        ).scalar_one()

    def _vigente(self, clave: str) -> dict | None:
        fila = self.session.execute(
            text(
                f"""
                select {_COLUMNAS}, id
                  from nucleo.configuracion_empresa
                 where empresa_id = :empresa_id and clave = :clave
                   and vigente_hasta is null
                """
            ),
            {"empresa_id": self.empresa_id, "clave": clave},
        ).mappings().first()
        return dict(fila) if fila is not None else None

    def actualizar(self, clave: str, valor: Any) -> ConfiguracionItemOut:
        normalizado = _normalizar(clave, valor)
        actual = self._vigente(clave)
        if actual is not None and _mismo_valor(actual["valor"], normalizado):
            # PUT idempotente: no se crea una versión nueva si el valor no cambia.
            return ConfiguracionItemOut.model_validate(actual)

        try:
            fila = self.session.execute(
                text(
                    f"""
                    with cerrada as (
                        update nucleo.configuracion_empresa
                           set vigente_hasta = now(),
                               updated_at = now(),
                               updated_by = :auth_id
                         where empresa_id = :empresa_id and clave = :clave
                           and vigente_hasta is null
                        returning vigente_hasta
                    )
                    insert into nucleo.configuracion_empresa
                        (empresa_id, clave, valor, vigente_desde, created_by)
                    select :empresa_id, :clave, cast(:valor as jsonb),
                           coalesce((select vigente_hasta from cerrada), now()),
                           :auth_id
                    returning {_COLUMNAS}
                    """
                ),
                {
                    "empresa_id": self.empresa_id,
                    "clave": clave,
                    "valor": json.dumps(normalizado),
                    "auth_id": self.contexto.auth_id,
                },
            ).mappings().one()
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            estado = _sqlstate(exc)
            if estado in {"23P01", "23505"}:
                # Otra transacción cerró/insertó la vigencia al mismo tiempo.
                raise ConflictoConcurrencia(
                    "Otro usuario cambió la configuración al mismo tiempo. "
                    "Recargue y reintente."
                ) from exc
            if estado == "23514":
                raise DatosInvalidos(
                    "El valor no cumple una regla de la configuración."
                ) from exc
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return ConfiguracionItemOut.model_validate(dict(fila))

    def obtener(self, clave: str) -> ConfiguracionItemOut:
        if clave not in CATALOGO:
            raise DatosInvalidos(
                "Clave de configuración no reconocida.",
                contexto={"claves_permitidas": sorted(CATALOGO)},
            )
        fila = self._vigente(clave)
        if fila is None:
            raise RecursoNoEncontrado(
                "La empresa no tiene un valor vigente para esa clave."
            )
        return ConfiguracionItemOut.model_validate(fila)


def _mismo_valor(actual: Any, nuevo: Any) -> bool:
    if isinstance(actual, bool) or isinstance(nuevo, bool):
        return actual is nuevo
    try:
        return Decimal(str(actual)) == Decimal(str(nuevo))
    except (InvalidOperation, ValueError):
        return actual == nuevo
