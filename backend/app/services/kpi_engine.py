"""Motor seguro de KPIs.

Evalúa fórmulas de texto definidas por el usuario sobre un catálogo CERRADO de
métricas. NUNCA traduce la fórmula a SQL ni ejecuta código arbitrario: usa el
módulo `ast` de Python con una lista blanca estricta de nodos, operadores y
funciones.
"""

from __future__ import annotations

import ast
import math
import re
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import (
    Chofer,
    Cliente,
    EstadoFactura,
    EstadoViaje,
    Factura,
    GastoViaje,
    Mantenimiento,
    PautaMantenimiento,
    Rampla,
    Tracto,
    Viaje,
)

# ------------------------------------------------------------
# Catálogo de métricas (documentado para el editor)
# ------------------------------------------------------------
CATALOGO_GLOBAL = [
    ("ingresos_mes", "Ingresos del mes (suma de fletes finalizados/facturados)"),
    ("gastos_mes", "Gastos de viaje registrados en el mes"),
    ("margen_bruto", "Ingresos del mes menos gastos del mes"),
    ("margen_pct", "Margen bruto como porcentaje de los ingresos"),
    ("cuentas_por_cobrar", "Total de facturas pendientes de pago"),
    ("cuentas_atrasadas", "Total de facturas vencidas impagas"),
    ("iva_a_pagar", "IVA débito menos crédito del mes"),
    ("facturacion_mes", "Total facturado en el mes (facturas no anuladas)"),
    ("viajes_mes", "Cantidad de viajes finalizados o facturados en el mes"),
    ("viajes_activos", "Viajes programados o en ruta en este momento"),
    ("flete_promedio", "Ingreso promedio por viaje del mes"),
    ("costo_mantenimiento_mes", "Costo de mantenciones registradas en el mes"),
    ("mantenimientos_pendientes", "Ítems de mantención vencidos por kilometraje"),
    ("vencimientos_30d", "Documentos (rev. técnica, seguro, licencias) que vencen en 30 días"),
    ("comision_total_mes", "Comisiones de choferes del mes"),
    ("costo_choferes_mes", "Sueldos base de choferes activos más comisiones del mes"),
    ("choferes_activos", "Cantidad de choferes activos"),
]

CATALOGO_VIAJE = [
    ("flete_viaje", "Valor flete neto del viaje"),
    ("gastos_viaje", "Gastos registrados del viaje"),
    ("comision_viaje", "Comisión del chofer del viaje"),
    ("margen_viaje", "Flete menos gastos menos comisión"),
    ("margen_viaje_pct", "Margen del viaje como porcentaje del flete"),
]

FUNCIONES_AYUDA = [
    ("SI(condicion, a, b)", "Devuelve a si la condición es verdadera, si no b"),
    ("REDONDEAR(x, n)", "Redondea x a n decimales"),
    ("MIN(a, b, ...)", "El menor de los valores"),
    ("MAX(a, b, ...)", "El mayor de los valores"),
    ("ABS(x)", "Valor absoluto"),
]

_FUNCIONES = {"SI", "IF", "REDONDEAR", "ROUND", "MIN", "MAX", "ABS", "ABSOLUTO"}


def catalogo(ambito: str) -> dict:
    metricas = CATALOGO_GLOBAL if ambito == "global" else CATALOGO_VIAJE
    return {
        "ambito": ambito,
        "metricas": [{"nombre": n, "descripcion": d} for n, d in metricas],
        "funciones": [{"nombre": n, "descripcion": d} for n, d in FUNCIONES_AYUDA],
        "operadores": ["+", "-", "*", "/", "(", ")", "<", ">", "<=", ">=", "=", "Y", "O"],
    }


# ------------------------------------------------------------
# Evaluador seguro
# ------------------------------------------------------------
def _normalizar(formula: str) -> str:
    # Permite '=' como igualdad (lo convierte en '=='), sin tocar <=, >=, !=, ==
    texto = re.sub(r"(?<![<>=!])=(?!=)", "==", formula)
    # Permite los operadores lógicos en español Y / O (palabras sueltas)
    texto = re.sub(r"(?<![A-Za-z0-9_])Y(?![A-Za-z0-9_])", " and ", texto)
    texto = re.sub(r"(?<![A-Za-z0-9_])O(?![A-Za-z0-9_])", " or ", texto)
    return texto


def _a_numero(valor) -> float:
    if isinstance(valor, bool):
        return 1.0 if valor else 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, Decimal):
        return float(valor)
    raise ValueError("La fórmula produjo un valor no numérico")


def evaluar_formula(formula: str, valores: dict[str, float]) -> float:
    """Evalúa una fórmula de KPI de forma segura y devuelve un float."""
    if not formula or not formula.strip():
        raise ValueError("La fórmula está vacía")

    texto = _normalizar(formula)
    try:
        arbol = ast.parse(texto, mode="eval")
    except SyntaxError:
        raise ValueError("La fórmula tiene un error de sintaxis")

    resultado = _evaluar(arbol.body, valores)

    # Las condiciones puras (comparaciones) devuelven bool → se interpretan 0/1
    numero = _a_numero(resultado)
    if math.isnan(numero) or math.isinf(numero):
        raise ValueError("La fórmula produjo un valor no válido (infinito o indeterminado)")
    return numero


def _evaluar(nodo: ast.AST, valores: dict[str, float]):
    if isinstance(nodo, ast.Constant):
        if isinstance(nodo.value, bool):
            return nodo.value
        if isinstance(nodo.value, (int, float)):
            return float(nodo.value)
        raise ValueError("Solo se permiten números en la fórmula")

    if isinstance(nodo, ast.Name):
        clave = nodo.id.lower()
        if clave in valores:
            return float(valores[clave])
        raise ValueError(f"Métrica desconocida: '{nodo.id}'")

    if isinstance(nodo, ast.BinOp):
        izq = _evaluar(nodo.left, valores)
        der = _evaluar(nodo.right, valores)
        if isinstance(nodo.op, ast.Add):
            return _a_numero(izq) + _a_numero(der)
        if isinstance(nodo.op, ast.Sub):
            return _a_numero(izq) - _a_numero(der)
        if isinstance(nodo.op, ast.Mult):
            return _a_numero(izq) * _a_numero(der)
        if isinstance(nodo.op, ast.Div):
            if _a_numero(der) == 0:
                raise ValueError("División por cero en la fórmula")
            return _a_numero(izq) / _a_numero(der)
        if isinstance(nodo.op, ast.Mod):
            if _a_numero(der) == 0:
                raise ValueError("División por cero en la fórmula")
            return _a_numero(izq) % _a_numero(der)
        if isinstance(nodo.op, ast.Pow):
            return _a_numero(izq) ** _a_numero(der)
        raise ValueError("Operador no permitido en la fórmula")

    if isinstance(nodo, ast.UnaryOp):
        valor = _a_numero(_evaluar(nodo.operand, valores))
        if isinstance(nodo.op, ast.USub):
            return -valor
        if isinstance(nodo.op, ast.UAdd):
            return valor
        raise ValueError("Operador unario no permitido")

    if isinstance(nodo, ast.Compare):
        izquierda = _evaluar(nodo.left, valores)
        for op, comparador in zip(nodo.ops, nodo.comparators):
            derecha = _evaluar(comparador, valores)
            if isinstance(op, ast.Lt):
                ok = _a_numero(izquierda) < _a_numero(derecha)
            elif isinstance(op, ast.LtE):
                ok = _a_numero(izquierda) <= _a_numero(derecha)
            elif isinstance(op, ast.Gt):
                ok = _a_numero(izquierda) > _a_numero(derecha)
            elif isinstance(op, ast.GtE):
                ok = _a_numero(izquierda) >= _a_numero(derecha)
            elif isinstance(op, ast.Eq):
                ok = _a_numero(izquierda) == _a_numero(derecha)
            elif isinstance(op, ast.NotEq):
                ok = _a_numero(izquierda) != _a_numero(derecha)
            else:
                raise ValueError("Comparador no permitido")
            if not ok:
                return False
            izquierda = derecha
        return True

    if isinstance(nodo, ast.BoolOp):
        resultados = [_evaluar(v, valores) for v in nodo.values]
        if isinstance(nodo.op, ast.And):
            return all(bool(r) for r in resultados)
        if isinstance(nodo.op, ast.Or):
            return any(bool(r) for r in resultados)
        raise ValueError("Operador lógico no permitido")

    if isinstance(nodo, ast.Call):
        if not isinstance(nodo.func, ast.Name):
            raise ValueError("Llamada de función no permitida")
        nombre = nodo.func.id.upper()
        if nombre not in _FUNCIONES:
            raise ValueError(f"Función no permitida: {nodo.func.id}")
        if nodo.keywords:
            raise ValueError("No se permiten argumentos con nombre")
        # SI/IF evalúa SOLO la rama elegida (evita divisiones por cero en la no usada)
        if nombre in ("SI", "IF"):
            if len(nodo.args) != 3:
                raise ValueError("SI(condición, valor_si, valor_no) requiere 3 argumentos")
            condicion = _evaluar(nodo.args[0], valores)
            rama = nodo.args[1] if bool(condicion) else nodo.args[2]
            return _evaluar(rama, valores)

        args = [_evaluar(a, valores) for a in nodo.args]
        if nombre in ("REDONDEAR", "ROUND"):
            if len(args) == 1:
                return round(_a_numero(args[0]))
            if len(args) == 2:
                return round(_a_numero(args[0]), int(_a_numero(args[1])))
            raise ValueError("REDONDEAR(x, decimales) requiere 1 o 2 argumentos")
        if nombre == "MIN":
            if not args:
                raise ValueError("MIN requiere al menos un argumento")
            return min(_a_numero(a) for a in args)
        if nombre == "MAX":
            if not args:
                raise ValueError("MAX requiere al menos un argumento")
            return max(_a_numero(a) for a in args)
        if nombre in ("ABS", "ABSOLUTO"):
            if len(args) != 1:
                raise ValueError("ABS(x) requiere 1 argumento")
            return abs(_a_numero(args[0]))

    raise ValueError("La fórmula contiene una expresión no permitida")


def nombres_metricas(formula: str) -> set[str]:
    """Extrae los nombres de métricas usados en una fórmula (para validar)."""
    try:
        arbol = ast.parse(_normalizar(formula), mode="eval")
    except SyntaxError:
        raise ValueError("La fórmula tiene un error de sintaxis")
    nombres = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Name) and nodo.id.upper() not in _FUNCIONES:
            nombres.add(nodo.id.lower())
    return nombres


# ------------------------------------------------------------
# Reglas de color (semáforo)
# ------------------------------------------------------------
_OPERADORES = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "=": lambda a, b: a == b,
    "==": lambda a, b: a == b,
}

COLORES = {"rojo", "amarillo", "verde", "azul", "gris"}


def color_para(valor: float, reglas: list | None) -> str:
    """Devuelve el color según la primera regla que se cumpla (o gris)."""
    if not reglas:
        return "gris"
    for regla in reglas:
        try:
            op = str(regla.get("operador", ""))
            limite = float(regla.get("valor"))
            color = str(regla.get("color", "gris"))
        except (TypeError, ValueError):
            continue
        if op in _OPERADORES and _OPERADORES[op](valor, limite):
            return color if color in COLORES else "gris"
    return "gris"


# ------------------------------------------------------------
# Resolución de métricas
# ------------------------------------------------------------
def rango_periodo(periodo: str | None) -> tuple[date, date]:
    hoy = date.today()
    if periodo:
        try:
            anio, mes = map(int, periodo.split("-"))
            return date(anio, mes, 1), date(anio + 1, 1, 1) if mes == 12 else date(anio, mes + 1, 1)
        except (ValueError, AttributeError):
            pass
    return (
        date(hoy.year, hoy.month, 1),
        date(hoy.year + 1, 1, 1) if hoy.month == 12 else date(hoy.year, hoy.month + 1, 1),
    )


def _dec(valor) -> Decimal:
    return Decimal(str(valor)) if valor is not None else Decimal("0")


def metricas_global(session: Session, periodo: str | None = None) -> dict[str, float]:
    inicio, fin = rango_periodo(periodo)
    hoy = date.today()
    from app.core.settings_db import get_config, get_config_decimal

    ingresos = _dec(
        session.exec(
            select(func.coalesce(func.sum(Viaje.valor_flete_neto), 0)).where(
                Viaje.estado.in_([EstadoViaje.finalizado, EstadoViaje.facturado]),
                func.coalesce(Viaje.fecha_fin, Viaje.fecha_inicio) >= inicio,
                func.coalesce(Viaje.fecha_fin, Viaje.fecha_inicio) < fin,
            )
        ).one()
    )
    gastos = _dec(
        session.exec(
            select(func.coalesce(func.sum(GastoViaje.monto), 0)).where(
                GastoViaje.fecha >= inicio, GastoViaje.fecha < fin
            )
        ).one()
    )
    por_cobrar = _dec(
        session.exec(
            select(func.coalesce(func.sum(Factura.total), 0)).where(
                Factura.estado == EstadoFactura.pendiente
            )
        ).one()
    )
    atrasadas = _dec(
        session.exec(
            select(func.coalesce(func.sum(Factura.total), 0)).where(
                Factura.estado == EstadoFactura.pendiente,
                Factura.fecha_vencimiento < hoy,
            )
        ).one()
    )
    facturacion = _dec(
        session.exec(
            select(func.coalesce(func.sum(Factura.total), 0)).where(
                Factura.estado != EstadoFactura.anulada,
                Factura.fecha_emision >= inicio,
                Factura.fecha_emision < fin,
            )
        ).one()
    )
    viajes_mes = int(
        session.exec(
            select(func.count()).select_from(Viaje).where(
                Viaje.estado.in_([EstadoViaje.finalizado, EstadoViaje.facturado]),
                func.coalesce(Viaje.fecha_fin, Viaje.fecha_inicio) >= inicio,
                func.coalesce(Viaje.fecha_fin, Viaje.fecha_inicio) < fin,
            )
        ).one()
    )
    viajes_activos = int(
        session.exec(
            select(func.count()).select_from(Viaje).where(
                Viaje.estado.in_([EstadoViaje.programado, EstadoViaje.en_ruta])
            )
        ).one()
    )

    # Comisiones del mes
    viajes_com = session.exec(
        select(Viaje).where(
            Viaje.estado.in_([EstadoViaje.finalizado, EstadoViaje.facturado]),
            func.coalesce(Viaje.fecha_fin, Viaje.fecha_inicio) >= inicio,
            func.coalesce(Viaje.fecha_fin, Viaje.fecha_inicio) < fin,
        )
    ).all()
    comision_total = Decimal("0")
    for v in viajes_com:
        chofer = session.get(Chofer, v.chofer_id)
        if chofer:
            comision_total += v.valor_flete_neto * chofer.porcentaje_produccion

    choferes_activos = int(
        session.exec(select(func.count()).select_from(Chofer).where(Chofer.activo == True)).one()  # noqa: E712
    )
    sueldos_base = _dec(
        session.exec(
            select(func.coalesce(func.sum(Chofer.sueldo_base), 0)).where(Chofer.activo == True)  # noqa: E712
        ).one()
    )

    costo_mant = _dec(
        session.exec(
            select(func.coalesce(func.sum(Mantenimiento.costo), 0)).where(
                Mantenimiento.fecha >= inicio, Mantenimiento.fecha < fin
            )
        ).one()
    )

    # IVA
    tasa = get_config_decimal(session, "iva_porcentaje", "19")
    debito = _dec(
        session.exec(
            select(func.coalesce(func.sum(Factura.iva), 0)).where(
                Factura.tipo == "afecta",
                Factura.estado != EstadoFactura.anulada,
                Factura.fecha_emision >= inicio,
                Factura.fecha_emision < fin,
            )
        ).one()
    )
    base_credito = _dec(
        session.exec(
            select(func.coalesce(func.sum(GastoViaje.monto), 0)).where(
                GastoViaje.iva_recuperable == True,  # noqa: E712
                GastoViaje.fecha >= inicio,
                GastoViaje.fecha < fin,
            )
        ).one()
    )
    credito = base_credito * (tasa / (Decimal("100") + tasa))

    # Mantenimientos pendientes por km
    mantenimientos_pendientes = _contar_mantenimientos_pendientes(session)

    # Vencimientos próximos 30 días
    limite = hoy + timedelta(days=int(get_config(session, "dias_alerta_vencimientos", "30")))
    vencimientos = 0
    for t in session.exec(select(Tracto).where(Tracto.activo == True)).all():  # noqa: E712
        for fecha in (t.vencimiento_revision_tecnica, t.vencimiento_seguro):
            if fecha and fecha <= limite:
                vencimientos += 1
    for r in session.exec(select(Rampla).where(Rampla.activo == True)).all():  # noqa: E712
        if r.vencimiento_revision_tecnica and r.vencimiento_revision_tecnica <= limite:
            vencimientos += 1
    for ch in session.exec(select(Chofer).where(Chofer.activo == True)).all():  # noqa: E712
        if ch.vencimiento_licencia and ch.vencimiento_licencia <= limite:
            vencimientos += 1

    margen = ingresos - gastos
    return {
        "ingresos_mes": float(ingresos),
        "gastos_mes": float(gastos),
        "margen_bruto": float(margen),
        "margen_pct": float(margen / ingresos * 100) if ingresos else 0.0,
        "cuentas_por_cobrar": float(por_cobrar),
        "cuentas_atrasadas": float(atrasadas),
        "iva_a_pagar": float(max(debito - credito, Decimal("0"))),
        "facturacion_mes": float(facturacion),
        "viajes_mes": float(viajes_mes),
        "viajes_activos": float(viajes_activos),
        "flete_promedio": float(ingresos / viajes_mes) if viajes_mes else 0.0,
        "costo_mantenimiento_mes": float(costo_mant),
        "mantenimientos_pendientes": float(mantenimientos_pendientes),
        "vencimientos_30d": float(vencimientos),
        "comision_total_mes": float(comision_total),
        "costo_choferes_mes": float(sueldos_base + comision_total),
        "choferes_activos": float(choferes_activos),
    }


def _contar_mantenimientos_pendientes(session: Session) -> int:
    from app.core.settings_db import get_config

    alerta = int(get_config(session, "alerta_km_mantenimiento", "5000"))
    tractos = session.exec(select(Tracto).where(Tracto.activo == True)).all()  # noqa: E712
    pautas = session.exec(
        select(PautaMantenimiento).where(PautaMantenimiento.activo == True)  # noqa: E712
    ).all()
    ultimos = session.exec(
        select(Mantenimiento).order_by(
            Mantenimiento.tracto_id, Mantenimiento.pauta_id, Mantenimiento.km.desc()
        )
    ).all()
    mapa: dict[tuple, Mantenimiento] = {}
    for m in ultimos:
        clave = (str(m.tracto_id), str(m.pauta_id))
        if clave not in mapa:
            mapa[clave] = m
    pendientes = 0
    for tracto in tractos:
        for pauta in pautas:
            ultimo = mapa.get((str(tracto.id), str(pauta.id)))
            if ultimo is None:
                continue
            if (tracto.km_actual - (ultimo.km + pauta.intervalo_km)) >= 0:
                pendientes += 1
    return pendientes


def metricas_viaje(
    session: Session,
    *,
    viaje_id: UUID | None = None,
    flete: float | None = None,
    chofer_id: UUID | None = None,
    gastos: float | None = None,
) -> dict[str, float]:
    if viaje_id is not None:
        viaje = session.get(Viaje, viaje_id)
        if not viaje:
            raise ValueError("Viaje no encontrado")
        flete = float(viaje.valor_flete_neto)
        chofer_id = viaje.chofer_id
        gastos = float(metricas_gastos_viaje(session, viaje_id))
    else:
        flete = float(flete or 0)
        gastos = float(gastos or 0)

    porcentaje = Decimal("0")
    if chofer_id is not None:
        chofer = session.get(Chofer, chofer_id)
        if chofer:
            porcentaje = chofer.porcentaje_produccion

    comision = flete * float(porcentaje)
    margen = flete - float(gastos) - comision
    return {
        "flete_viaje": flete,
        "gastos_viaje": float(gastos),
        "comision_viaje": comision,
        "margen_viaje": margen,
        "margen_viaje_pct": (margen / flete * 100) if flete else 0.0,
    }


def metricas_gastos_viaje(session: Session, viaje_id: UUID) -> Decimal:
    return _dec(
        session.exec(
            select(func.coalesce(func.sum(GastoViaje.monto), 0)).where(
                GastoViaje.viaje_id == viaje_id
            )
        ).one()
    )


def validar_metricas(formula: str, ambito: str) -> None:
    """Valida que todas las métricas usadas existan en el catálogo del ámbito."""
    permitidas = {n for n, _ in (CATALOGO_GLOBAL if ambito == "global" else CATALOGO_VIAJE)}
    usadas = nombres_metricas(formula)
    desconocidas = sorted(usadas - permitidas)
    if desconocidas:
        raise ValueError(
            "Métrica(s) desconocida(s): " + ", ".join(desconocidas)
        )
