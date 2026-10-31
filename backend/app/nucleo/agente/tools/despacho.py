"""Ejecutores de lectura del componente `despacho` (O2.1).

Contrato: `docs/arquitectura/conector-agente-whatsapp.md` §5.2 (C1), §5.3 (K1)
y §5.4 (A1).

Reglas que se aplican acá y no se delegan al modelo:

- **SQL fijo.** El texto de la consulta es constante; solo cambian los valores
  de los parámetros y la *presencia* de un filtro opcional, elegido por clave
  de un diccionario cerrado. El modelo nunca aporta fragmentos de SQL.
- **Entidad forzada.** C1 usa `contexto.entidad_id` (cliente) y K1
  `contexto.entidad_id` (chofer). Si el contexto no la trae, el ejecutor falla
  cerrado: no hay consulta de empresa "por si acaso".
- **Proyección exacta.** Se seleccionan solo las columnas declaradas en el
  schema de salida. Nada de `select *`, costo, margen ni patentes.
- **`max_filas`.** El registry entrega el tope ya combinado con `limite`; el
  ejecutor lo aplica como `LIMIT` y devuelve `total` (cuántas filas cumplen el
  filtro) para calcular `truncado`.
- **Sin `commit()`.** La sesión y la transacción las controla el registry
  (§4.10). El ejecutor solo lee.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlmodel import Session

from app.nucleo.agente.contexto import ContextoAgente, RolContacto
from app.nucleo.agente.tipos import ResultadoTool

ZONA_CHILE = ZoneInfo("America/Santiago")


def _resultado(
    items: list[dict[str, Any]], total: int, ids: tuple[str, ...]
) -> ResultadoTool:
    """Construye el resultado con un solo cálculo de `truncado`.

    `truncado` viaja en dos lugares a propósito: dentro de `datos` porque el
    JSON Schema de salida lo exige, y en `ResultadoTool` porque el envelope lo
    publica en `meta`. Calcularlo una sola vez impide que ambos discrepen.
    """
    truncado = total > len(items)
    return ResultadoTool(
        datos={"items": items, "total": total, "truncado": truncado},
        filas=len(items),
        total=total,
        truncado=truncado,
        ids=ids,
    )

# ---------------------------------------------------------------------------
# C1 — despacho.mis_fletes (cliente forzado)
# ---------------------------------------------------------------------------

_BASE_C1 = """
select v.id::text            as viaje_id,
       v.id_comercial_flete,
       v.inicio_planificado,
       v.origen_nombre,
       v.destino_nombre,
       v.estado::text        as estado,
       v.tipo_carga::text    as tipo_carga
  from nucleo.viajes v
 where v.empresa_id = :empresa_id
   and v.cliente_id = :cliente_id
"""

_FILTROS_C1: dict[str, str] = {
    "estado": "   and v.estado = cast(:estado as nucleo.estado_viaje)\n",
    "desde": "   and v.inicio_planificado >= cast(:desde as timestamptz)\n",
    "hasta": "   and v.inicio_planificado <= cast(:hasta as timestamptz)\n",
}


def _where_c1(entrada: dict[str, Any], contexto: ContextoAgente) -> tuple[str, dict[str, Any]]:
    if contexto.rol is not RolContacto.cliente_final or contexto.entidad_id is None:
        raise ValueError("despacho.mis_fletes exige contacto cliente_final con cliente_id")
    fragmento = "".join(
        _FILTROS_C1[clave] for clave in _FILTROS_C1 if clave in entrada
    )
    parametros: dict[str, Any] = {
        "empresa_id": contexto.empresa_id,
        "cliente_id": contexto.entidad_id,
    }
    for clave in _FILTROS_C1:
        if clave in entrada:
            parametros[clave] = entrada[clave]
    return fragmento, parametros


def despacho_mis_fletes(
    contexto: ContextoAgente,
    entrada: dict[str, Any],
    limite: int | None,
    session: Session,
) -> ResultadoTool:
    fragmento, parametros = _where_c1(entrada, contexto)
    total = int(
        session.execute(
            text(
                "select count(*) from nucleo.viajes v "
                "where v.empresa_id = :empresa_id and v.cliente_id = :cliente_id"
                + fragmento
            ),
            parametros,
        ).scalar_one()
    )
    filas = session.execute(
        text(_BASE_C1 + fragmento + " order by v.inicio_planificado desc, v.id\n limit :limite"),
        {**parametros, "limite": limite},
    ).all()

    items = [
        {
            "id_comercial_flete": fila.id_comercial_flete,
            "fecha": _iso_utc(fila.inicio_planificado),
            "origen": fila.origen_nombre,
            "destino": fila.destino_nombre,
            "estado": fila.estado,
            "tipo_carga": fila.tipo_carga,
        }
        for fila in filas
    ]
    ids = tuple(
        fila.id_comercial_flete or fila.viaje_id for fila in filas
    )
    return _resultado(items, total, ids)


# ---------------------------------------------------------------------------
# K1 — despacho.mis_viajes_asignados (chofer forzado)
# ---------------------------------------------------------------------------

_BASE_K1 = """
select v.id::text            as viaje_id,
       v.id_comercial_flete,
       c.razon_social       as cliente_nombre,
       v.origen_nombre,
       v.destino_nombre,
       v.inicio_planificado,
       v.estado::text        as estado
  from nucleo.viajes v
  join nucleo.clientes c
    on c.empresa_id = v.empresa_id
   and c.id = v.cliente_id
 where v.empresa_id = :empresa_id
   and v.chofer_id = :chofer_id
"""

_FILTROS_K1: dict[str, str] = {
    "estado": "   and v.estado = cast(:estado as nucleo.estado_viaje)\n",
    "desde": "   and v.inicio_planificado >= cast(:desde as timestamptz)\n",
    "hasta": "   and v.inicio_planificado <= cast(:hasta as timestamptz)\n",
}


def _where_k1(entrada: dict[str, Any], contexto: ContextoAgente) -> tuple[str, dict[str, Any]]:
    if contexto.rol is not RolContacto.conductor or contexto.entidad_id is None:
        raise ValueError(
            "despacho.mis_viajes_asignados exige contacto conductor con chofer_id"
        )
    fragmento = "".join(
        _FILTROS_K1[clave] for clave in _FILTROS_K1 if clave in entrada
    )
    parametros: dict[str, Any] = {
        "empresa_id": contexto.empresa_id,
        "chofer_id": contexto.entidad_id,
    }
    for clave in _FILTROS_K1:
        if clave in entrada:
            parametros[clave] = entrada[clave]
    return fragmento, parametros


def _conteo_k1(fragmento: str, parametros: dict[str, Any], session: Session) -> int:
    return int(
        session.execute(
            text(
                "select count(*) from nucleo.viajes v "
                "join nucleo.clientes c "
                "  on c.empresa_id = v.empresa_id and c.id = v.cliente_id "
                "where v.empresa_id = :empresa_id and v.chofer_id = :chofer_id"
                + fragmento
            ),
            parametros,
        ).scalar_one()
    )


def despacho_mis_viajes_asignados(
    contexto: ContextoAgente,
    entrada: dict[str, Any],
    limite: int | None,
    session: Session,
) -> ResultadoTool:
    fragmento, parametros = _where_k1(entrada, contexto)
    total = _conteo_k1(fragmento, parametros, session)
    filas = session.execute(
        text(_BASE_K1 + fragmento + " order by v.inicio_planificado desc, v.id\n limit :limite"),
        {**parametros, "limite": limite},
    ).all()
    items = [
        {
            "viaje_id": fila.viaje_id,
            "id_comercial_flete": fila.id_comercial_flete,
            "cliente_nombre": fila.cliente_nombre,
            "origen": fila.origen_nombre,
            "destino": fila.destino_nombre,
            "fecha": _iso_utc(fila.inicio_planificado),
            "estado": fila.estado,
        }
        for fila in filas
    ]
    return _resultado(items, total, tuple(fila.viaje_id for fila in filas))


# ---------------------------------------------------------------------------
# A1 — despacho.viajes_del_dia (empresa, solo admin)
# ---------------------------------------------------------------------------

_BASE_A1 = """
select v.id::text            as viaje_id,
       v.id_comercial_flete,
       c.razon_social       as cliente_nombre,
       v.origen_nombre,
       v.destino_nombre,
       v.inicio_planificado,
       v.estado::text        as estado
  from nucleo.viajes v
  join nucleo.clientes c
    on c.empresa_id = v.empresa_id
   and c.id = v.cliente_id
 where v.empresa_id = :empresa_id
   and v.inicio_planificado >= :desde
   and v.inicio_planificado < :hasta
"""


def _rango_dia_chile(dia: date) -> tuple[datetime, datetime]:
    """Día calendario `America/Santiago` como rango semiabierto en UTC.

    `[00:00 local, 00:00 local del día siguiente)`. La aritmética es de reloj
    de pared, así que cubre los cambios de hora de Chile sin asumir 24 h.
    """
    inicio_local = datetime.combine(dia, time.min, tzinfo=ZONA_CHILE)
    fin_local = datetime.combine(dia + timedelta(days=1), time.min, tzinfo=ZONA_CHILE)
    return (
        inicio_local.astimezone(UTC),
        fin_local.astimezone(UTC),
    )


def despacho_viajes_del_dia(
    contexto: ContextoAgente,
    entrada: dict[str, Any],
    limite: int | None,
    session: Session,
) -> ResultadoTool:
    if contexto.rol is not RolContacto.admin:
        raise ValueError("despacho.viajes_del_dia exige contacto admin")
    dia = (
        date.fromisoformat(entrada["fecha"])
        if "fecha" in entrada
        else datetime.now(ZONA_CHILE).date()
    )
    desde, hasta = _rango_dia_chile(dia)
    fragmento = ""
    parametros: dict[str, Any] = {
        "empresa_id": contexto.empresa_id,
        "desde": desde,
        "hasta": hasta,
    }
    if "estado" in entrada:
        fragmento = "   and v.estado = cast(:estado as nucleo.estado_viaje)\n"
        parametros["estado"] = entrada["estado"]

    total = int(
        session.execute(
            text(
                "select count(*) from nucleo.viajes v "
                "join nucleo.clientes c "
                "  on c.empresa_id = v.empresa_id and c.id = v.cliente_id "
                "where v.empresa_id = :empresa_id "
                "  and v.inicio_planificado >= :desde "
                "  and v.inicio_planificado < :hasta" + fragmento
            ),
            parametros,
        ).scalar_one()
    )
    filas = session.execute(
        text(_BASE_A1 + fragmento + " order by v.inicio_planificado, v.id\n limit :limite"),
        {**parametros, "limite": limite},
    ).all()
    items = [
        {
            "viaje_id": fila.viaje_id,
            "id_comercial_flete": fila.id_comercial_flete,
            "cliente_nombre": fila.cliente_nombre,
            "origen": fila.origen_nombre,
            "destino": fila.destino_nombre,
            "fecha": _iso_utc(fila.inicio_planificado),
            "estado": fila.estado,
        }
        for fila in filas
    ]
    return _resultado(items, total, tuple(fila.viaje_id for fila in filas))


def _iso_utc(valor: datetime) -> str:
    """`timestamptz` → RFC 3339 en UTC con `Z` (contrato §3.3 regla 6)."""
    if valor.tzinfo is None:
        raise ValueError("se esperaba un datetime con zona (timestamptz)")
    return valor.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
