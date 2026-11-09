#!/usr/bin/env python3
"""Dataset operativo de demostración para el tenant TEI (datos 100% ficticios).

UBICACIÓN: este archivo se creó en `docs/datos/` porque el agente `datos` tiene
denegada la escritura en `scripts/**` (ver `docs/datos/demo-transporte.md` §6).
Debe moverse a `scripts/seed_demo_transporte.py` por `orquestador`:

    git mv docs/datos/seed_demo_transporte.py scripts/seed_demo_transporte.py

Qué hace
--------
Agrega **sin borrar nada** una operación realista de una empresa de ~40 camiones
con 3 meses de historia al tenant `TEI` (`empresa_id = 1111...1111`) de la base
local `postgres`:

  * 40 tractos, 44 ramplas, 45 choferes y 14 clientes nuevos (patentes, RUT y
    nombres inventados);
  * 18 tarifas, 28 órdenes de compra, ~754 viajes entre 2026-08-01 y 2026-11-15;
  * expediente por viaje (checklist, eventos, paradas), POD, gastos, incidentes;
  * ~120 facturas con IVA 19 %, pagos totales/parciales, 1 nota de crédito;
  * mantenimiento, precios de diésel, reglas de entidad y chat demo.

Garantías de ejecución
----------------------
  * **Una sola transacción**: `commit()` solo al final; cualquier excepción hace
    `rollback()` y no deja filas a medias.
  * **Idempotente**: todos los UUID son deterministas (`uuid5` con prefijo
    `tei-demo:`), las fechas son fijas (`TEI_DEMO_HOY`, por defecto 2026-11-02) y
    cada inserción se salta si su id ya existe. Un segundo run no duplica nada.
  * **No borra** ni modifica filas preexistentes de TEI ni de otras empresas.
  * **No usa** `siguiente_folio` para facturas (usa `FAC-DEMO-0001`); para viajes
    el folio lo genera el trigger `nucleo.fn_viaje_ventana`.

Por qué el orden importa
------------------------
`fn_viaje_validar`, `validar_documentos_recurso`, `fn_oc_recalcular`,
`fn_viaje_facturacion` y `fn_factura_estado` corren en la base. El script los
respeta en vez de saltarlos: primero documentos y OC, después viajes, después POD
y facturación. Ningún estado se "fuerza": `cobrado` lo pone `fn_factura_estado`
al insertar el pago; `anulado` se alcanza con un UPDATE que la matriz
`nucleo.transiciones_viaje` permite y que exige motivo.

Uso
---
    .venv/bin/python scripts/seed_demo_transporte.py            # escribe
    .venv/bin/python scripts/seed_demo_transporte.py --dry-run  # solo planifica

    DATABASE_URL=postgresql://... .venv/bin/python scripts/seed_demo_transporte.py

Privacidad
----------
Nombres de personas, razones sociales, RUT, patentes, teléfonos y correos son
inventados. No corresponden a personas ni empresas reales.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Json

ROOT = Path(__file__).resolve().parents[1]

URL_DEFAULT = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
).replace("postgresql+psycopg://", "postgresql://")

EMPRESA_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

# Fecha de referencia del dataset. Fija a propósito: el resultado es reproducible
# y las consultas de aging/vencimientos tienen sentido. Se puede mover con
# `TEI_DEMO_HOY` antes de la primera carga (cambiarla después crea un segundo set).
FECHA_DEMO = date.fromisoformat(os.environ.get("TEI_DEMO_HOY", "2026-11-02"))

try:
    ZONA = ZoneInfo("America/Santiago")
except Exception:  # pragma: no cover - entorno sin tzdata
    ZONA = timezone(timedelta(hours=-3))

SEMILLA = 20261102

INICIO_HISTORICO = date(2026, 8, 1)
FIN_HISTORICO = date(2026, 10, 31)
CORTE_TALLER = date(2026, 10, 15)  # los 2 tractos en taller no viajan después
MES_HISTORICO = 730

PERIODOS_OC = (
    (date(2026, 7, 15), date(2026, 9, 20)),   # P1
    (date(2026, 9, 18), date(2026, 11, 30)),  # P2
)


# ---------------------------------------------------------------------------
# Utilidades deterministas
# ---------------------------------------------------------------------------
def uid(tipo: str, n: Any) -> uuid.UUID:
    """UUID determinista del dataset demo."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"tei-demo:{tipo}:{n}")


def dv_rut(cuerpo: int) -> str:
    """Dígito verificador chileno (módulo 11)."""
    suma = 0
    factor = 2
    for digito in reversed(str(cuerpo)):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def rut(cuerpo: int) -> str:
    """RUT ficticio con DV válido, formateado 12.345.678-9."""
    return f"{cuerpo:,}".replace(",", ".") + "-" + dv_rut(cuerpo)


def local(anio: int, mes: int, dia: int, hora: int = 0, minuto: int = 0) -> datetime:
    """Instante con zona horaria de Chile (maneja el cambio de hora)."""
    return datetime(anio, mes, dia, hora, minuto, tzinfo=ZONA)


def a_local(d: date, hora: int = 0, minuto: int = 0) -> datetime:
    return local(d.year, d.month, d.day, hora, minuto)


def redondear(monto: float | Decimal, paso: int = 100) -> int:
    return int(round(float(monto) / paso) * paso)


def dos_decimales(monto: float | Decimal) -> Decimal:
    return Decimal(str(monto)).quantize(Decimal("0.01"))


def vin(prefijo: str, i: int) -> str:
    return f"{prefijo}{i:010d}"


# ---------------------------------------------------------------------------
# Catálogos ficticios (nombres inventados, no reales)
# ---------------------------------------------------------------------------
NOMBRES = [
    "Álvaro", "Bastián", "Camila", "Damián", "Emilia", "Facundo", "Gabriel",
    "Héctor", "Ignacia", "Joaquín", "Karen", "Lorena", "Matías", "Nicolás",
    "Olivia", "Patricio", "Rocío", "Sebastián", "Tamara", "Ulises", "Valentina",
    "Wladimir", "Ximena", "Yerko", "Zacarías", "Ariel", "Bárbara", "Cristián",
    "Daniela", "Esteban", "Fernanda", "Gonzalo", "Hilda", "Iván", "Javiera",
    "Katherine", "Leonardo", "Marisol", "Néstor", "Óscar", "Paula", "Rodrigo",
    "Sofía", "Tomás", "Úrsula", "Víctor",
]

APELLIDOS = [
    "Alarcón", "Bustamante", "Cáceres", "Donoso", "Escobar", "Fuentes",
    "Gallardo", "Herrera", "Ibarra", "Jorquera", "Lagos", "Maldonado",
    "Navarrete", "Orellana", "Pizarro", "Quezada", "Rivas", "Sandoval", "Tapia",
    "Urrutia", "Valdés", "Yáñez", "Zúñiga", "Abarca", "Bascuñán", "Cortés",
    "Díaz", "Elgueta", "Farías", "Godoy", "Henríquez", "Iturra", "Jara",
    "Klein", "Lazo", "Mora", "Núñez", "Ojeda", "Paredes", "Retamal",
    "Sepúlveda", "Torres", "Vargas", "Weber", "Ossandón", "Poblete",
]

CIUDADES: dict[str, tuple[str, str, float, float]] = {
    "Santiago": ("Santiago", "Región Metropolitana", -33.4489, -70.6693),
    "Concepción": ("Concepción", "Biobío", -36.8270, -73.0503),
    "Temuco": ("Temuco", "La Araucanía", -38.7359, -72.5904),
    "Puerto Montt": ("Puerto Montt", "Los Lagos", -41.4693, -72.9424),
    "Castro": ("Castro", "Los Lagos", -42.4721, -73.7732),
    "Curicó": ("Curicó", "Maule", -34.9829, -71.2393),
    "Talca": ("Talca", "Maule", -35.4264, -71.6554),
    "Los Ángeles": ("Los Ángeles", "Biobío", -37.4697, -72.3537),
    "Valparaíso": ("Valparaíso", "Valparaíso", -33.0472, -71.6127),
    "San Antonio": ("San Antonio", "Valparaíso", -33.5933, -71.6075),
    "Quintero": ("Quintero", "Valparaíso", -32.7833, -71.5333),
    "Rancagua": ("Rancagua", "O'Higgins", -34.1708, -70.7444),
    "La Serena": ("La Serena", "Coquimbo", -29.9027, -71.2519),
    "Antofagasta": ("Antofagasta", "Antofagasta", -23.6509, -70.3975),
    "Calama": ("Calama", "Antofagasta", -22.4567, -68.9236),
    "Iquique": ("Iquique", "Tarapacá", -20.2133, -70.1503),
}

# (razon_social, giro, ciudad, dias_pago, exige_oc, contacto)
CLIENTES_DEMO: list[tuple[str, str, str, int, bool, str]] = [
    ("Comercial Andes Retail SpA", "Comercio al por menor", "Santiago", 30, False, "Verónica Salas"),
    ("Supermercados Valle Central Ltda", "Supermercados", "Santiago", 15, False, "Manuel Contreras"),
    ("Minera Quebrada Azul SpA", "Minería del cobre", "Antofagasta", 60, False, "Paola Reyes"),
    ("Minera Valle del Salado Ltda", "Minería no metálica", "Calama", 45, False, "Iván Morales"),
    ("Salmones Aysén del Sur SpA", "Acuicultura", "Puerto Montt", 30, False, "Carolina Vidal"),
    ("Cultivos Marinos Chiloé Ltda", "Acuicultura", "Castro", 45, False, "Hernán Aguilar"),
    ("Cementos Precordillera SpA", "Fabricación de cemento", "Concepción", 60, False, "Rodrigo Peña"),
    ("Hormigones Maipo Ltda", "Hormigón premezclado", "Santiago", 30, False, "Andrea Muñoz"),
    ("Agrofrutícola Curicó SpA", "Fruticultura", "Curicó", 45, False, "Luis Fuenzalida"),
    ("Viña Alto Maule Ltda", "Vitivinicultura", "Talca", 60, False, "María José Lira"),
    ("Constructora Ribera del Mapocho SpA", "Construcción", "Santiago", 30, False, "Felipe Cárcamo"),
    ("Química Industrial Ventanas SpA", "Química básica", "Quintero", 45, False, "Sandra Ortiz"),
    ("Forestal Araucanía Verde SpA", "Silvicultura", "Temuco", 60, False, "Julio Catrileo"),
    ("Servicios Logísticos Lircay Ltda", "Operador logístico", "Talca", 30, True, "Camila Sepúlveda"),
]

MARCAS_TRACTOS = [
    ("Volvo", "FH 460"), ("Volvo", "FH 540"), ("Scania", "R 450"),
    ("Scania", "R 500"), ("Scania", "S 520"), ("Mercedes-Benz", "Actros 2645"),
    ("Mercedes-Benz", "Actros 2545"), ("Kenworth", "T680"), ("Kenworth", "T800"),
]

MARCAS_RAMPLAS = [
    ("Randon", "SR 30"), ("Fruehauf", "FH 3E"), ("Krone", "Profi Liner"),
    ("Carrocerías del Sur", "CarSur 900"), ("Thermo King", "SLXi"),
    ("Heil", "Tanker 4E"), ("Mauricio López", "Cama Baja 4E"),
]

TIPOS_RAMPLA_ORDEN = (
    [("plana", 10)]
    + [("sider", 12)]
    + [("refrigerada", 6)]
    + [("portacontenedor", 6)]
    + [("cisterna", 4)]
    + [("granelera", 3)]
    + [("cama_baja", 3)]
)

CAPACIDAD_RAMPLA = {
    "plana": 30000,
    "sider": 29000,
    "refrigerada": 28000,
    "portacontenedor": 30000,
    "cisterna": 28000,
    "granelera": 31000,
    "cama_baja": 33000,
}

VOLUMEN_RAMPLA = {
    "plana": None,
    "sider": 92,
    "refrigerada": 60,
    "portacontenedor": 67,
    "cisterna": 30,
    "granelera": 45,
    "cama_baja": None,
}

TEMPERATURA_RAMPLA = (-25, -18)  # solo refrigeradas

# Rutas por familia: (origen, destino, km)
RUTAS: dict[str, list[tuple[str, str, int]]] = {
    "general": [
        ("Santiago", "Concepción", 500),
        ("Santiago", "Temuco", 680),
        ("Santiago", "Puerto Montt", 1020),
        ("Santiago", "La Serena", 470),
        ("Concepción", "Santiago", 500),
        ("Santiago", "Talca", 255),
        ("Talca", "Santiago", 255),
        ("Santiago", "Antofagasta", 1360),
        ("Temuco", "Santiago", 680),
        ("Santiago", "Rancagua", 90),
    ],
    "refrigerada": [
        ("Puerto Montt", "Santiago", 1020),
        ("Santiago", "Puerto Montt", 1020),
        ("Castro", "Santiago", 1200),
        ("Curicó", "Santiago", 200),
        ("Santiago", "La Serena", 470),
        ("La Serena", "Santiago", 470),
    ],
    "contenedor": [
        ("San Antonio", "Santiago", 120),
        ("Santiago", "San Antonio", 120),
        ("Valparaíso", "Santiago", 130),
        ("Santiago", "Valparaíso", 130),
        ("Santiago", "Concepción", 500),
    ],
    "cisterna": [
        ("Concepción", "Santiago", 500),
        ("Quintero", "Santiago", 150),
        ("Santiago", "Rancagua", 90),
        ("Santiago", "Concepción", 500),
    ],
    "granel": [
        ("Curicó", "Santiago", 200),
        ("Talca", "Santiago", 255),
        ("Los Ángeles", "Santiago", 520),
        ("Santiago", "Talca", 255),
    ],
    "maquinaria": [
        ("Santiago", "Antofagasta", 1360),
        ("Antofagasta", "Santiago", 1360),
        ("Santiago", "Calama", 1700),
        ("Santiago", "Concepción", 500),
    ],
}

FAMILIA_POR_TIPO = {
    "plana": "general",
    "sider": "general",
    "refrigerada": "refrigerada",
    "portacontenedor": "contenedor",
    "cisterna": "cisterna",
    "granelera": "granel",
    "cama_baja": "maquinaria",
}

TIPO_CARGA_POR_FAMILIA = {
    "general": "general",
    "refrigerada": "refrigerada",
    "contenedor": "contenedor",
    "cisterna": "granel",
    "granel": "granel",
    "maquinaria": "maquinaria",
}

CLIENTES_POR_FAMILIA = {
    "general": (0, 1, 7, 12, 13),
    "refrigerada": (4, 5, 8, 9),
    "contenedor": (0, 1, 11),
    "cisterna": (11, 8),
    "granel": (6, 8, 12),
    "maquinaria": (2, 3, 10),
}

PESO_POR_FAMILIA = {
    "general": (18000, 26500),
    "refrigerada": (19000, 25000),
    "contenedor": (22000, 27000),
    "cisterna": (24000, 27000),
    "granel": (25000, 29000),
    "maquinaria": (22000, 30000),
}

MOTIVOS_ANULACION = [
    "Cliente reprogramó la carga",
    "Falta de documentación del cliente en planta de origen",
    "Cambio de tarifa solicitado por el cliente",
    "Reasignado a otro operador por el cliente",
    "Daño de rampla previo al carguío",
    "Error de digitación en la orden de compra",
]

PROVEEDORES_COMBUSTIBLE = ["Copec", "Shell", "Petrobras", "Enex", "Lipigas"]
PROVEEDORES_PEAJE = ["Autopista Central", "Ruta del Maipo", "Vespucio Norte", "Ruta 5 Sur"]

# (cliente_idx, codigo, nombre, modalidad, origen, destino, precio, tipo_rampla)
TARIFAS_DEMO: list[tuple[int, str, str, str, str, str, int, str]] = [
    (0, "TAR-AND-RM", "Santiago - Concepción", "viaje", "Santiago", "Concepción", 620000, "sider"),
    (1, "TAR-COR-RM", "Santiago - Temuco", "viaje", "Santiago", "Temuco", 780000, "sider"),
    (2, "TAR-CAZ-ANF", "Antofagasta - Santiago", "km", "Antofagasta", "Santiago", 1180, "cama_baja"),
    (3, "TAR-MVS-CAL", "Calama - Santiago", "viaje", "Calama", "Santiago", 1450000, "plana"),
    (4, "TAR-SAS-PMO", "Puerto Montt - Santiago", "viaje", "Puerto Montt", "Santiago", 1180000, "refrigerada"),
    (5, "TAR-CMC-CTS", "Castro - Santiago", "viaje", "Castro", "Santiago", 1320000, "refrigerada"),
    (6, "TAR-CBN-LAN", "Los Ángeles - Santiago", "tonelada", "Los Ángeles", "Santiago", 24500, "granelera"),
    (7, "TAR-HMA-RAN", "Santiago - Rancagua", "viaje", "Santiago", "Rancagua", 310000, "plana"),
    (8, "TAR-AFC-CUR", "Curicó - Santiago", "tonelada", "Curicó", "Santiago", 21800, "granelera"),
    (9, "TAR-VLR-TAL", "Talca - Santiago", "viaje", "Talca", "Santiago", 395000, "sider"),
    (10, "TAR-CRM-CCP", "Santiago - Concepción", "viaje", "Santiago", "Concepción", 640000, "cama_baja"),
    (11, "TAR-QIV-QUI", "Quintero - Santiago", "km", "Quintero", "Santiago", 1320, "cisterna"),
    (12, "TAR-FAV-TEM", "Temuco - Santiago", "viaje", "Temuco", "Santiago", 760000, "granelera"),
    (13, "TAR-SLL-TAL", "Talca - Santiago", "viaje", "Talca", "Santiago", 410000, "sider"),
    # Tarifas adicionales: rutas alternativas de clientes recurrentes.
    (7, "TAR-HMA-RM", "Santiago - Concepción", "viaje", "Santiago", "Concepción", 630000, "plana"),
    (4, "TAR-SAS-LSC", "Santiago - La Serena", "viaje", "Santiago", "La Serena", 690000, "refrigerada"),
    (9, "TAR-VLR-CUR", "Curicó - Santiago", "tonelada", "Curicó", "Santiago", 22800, "sider"),
    (11, "TAR-QIV-CCP", "Santiago - Concepción", "km", "Santiago", "Concepción", 1150, "cisterna"),
]


def construir_tarifas() -> list[dict[str, Any]]:
    return [
        {
            "idx": i,
            "cliente": cli,
            "codigo": codigo,
            "nombre": nombre,
            "modalidad": modalidad,
            "origen": origen,
            "destino": destino,
            "precio": precio,
            "tipo_rampla": tipo_rampla,
        }
        for i, (cli, codigo, nombre, modalidad, origen, destino, precio, tipo_rampla)
        in enumerate(TARIFAS_DEMO)
    ]


TARIFAS: list[dict[str, Any]] = construir_tarifas()


# ---------------------------------------------------------------------------
# Planificación (sin tocar la base)
# ---------------------------------------------------------------------------
@dataclass
class TractoPlan:
    idx: int
    patente: str
    marca: str
    modelo: str
    anio: int
    km_actual: int
    capacidad: int
    peso_bruto: int
    tara: int
    estado: str


@dataclass
class RamplaPlan:
    idx: int
    patente: str
    tipo: str
    marca: str
    modelo: str
    anio: int
    capacidad: int
    volumen: int | None
    certificado_gases: bool


@dataclass
class ChoferPlan:
    idx: int
    rut: str
    nombre: str
    apellido_paterno: str
    apellido_materno: str
    telefono: str
    email: str
    numero_licencia: str
    estado: str
    licencia_vence: date
    examen_vence: date
    sueldo_base: int


@dataclass
class ClientePlan:
    idx: int
    razon_social: str
    rut: str
    giro: str
    ciudad: str
    dias_pago: int
    exige_oc: bool
    contacto: str
    telefono: str
    email: str


@dataclass
class Equipo:
    idx: int
    tracto: int
    rampla: int
    chofer: int
    familia: str
    cursor: datetime
    taller: bool = False
    contador: int = 0


@dataclass
class ViajePlan:
    idx: int
    equipo: int
    cliente: int
    tarifa_idx: int
    tracto: int
    rampla: int
    chofer: int
    familia: str
    tipo_carga: str
    refrigerada: bool
    origen: str
    destino: str
    distancia: float
    inicio: datetime
    fin_planificado: datetime
    inicio_real: datetime | None
    fin_real: datetime | None
    fin_estimado: datetime | None
    buffer: int
    peso: int
    valor: int
    recargos: int
    estado_objetivo: str
    oc_idx: int | None = None
    motivo_anulacion: str | None = None
    con_pod: bool = True
    danios: str | None = None
    observaciones: str | None = None
    eventos: list[tuple[str, str, datetime]] = field(default_factory=list)
    # True solo si el viaje se insertó en ESTA ejecución. Los hijos (POD,
    # gastos, eventos, facturas) se crean únicamente para esos viajes: así un
    # re-run no agrega hijos a viajes ya existentes ni cambia su estado.
    insertado: bool = False


def construir_tractos() -> list[TractoPlan]:
    plan: list[TractoPlan] = []
    for i in range(40):
        marca, modelo = MARCAS_TRACTOS[i % len(MARCAS_TRACTOS)]
        capacidad = 28000 + (i % 5) * 1000
        peso_bruto = max(39000, capacidad + 9000)
        tara = peso_bruto - capacidad - 500
        plan.append(
            TractoPlan(
                idx=i,
                patente=f"LJAA{i + 1:02d}",
                marca=marca,
                modelo=modelo,
                anio=2016 + (i * 3) % 9,
                km_actual=120000 + (i * 17311) % 660000,
                capacidad=capacidad,
                peso_bruto=peso_bruto,
                tara=tara,
                estado="en_taller" if i in (38, 39) else "disponible",
            )
        )
    return plan


def construir_ramplas() -> list[RamplaPlan]:
    plan: list[RamplaPlan] = []
    idx = 0
    for tipo, cantidad in TIPOS_RAMPLA_ORDEN:
        for _ in range(cantidad):
            marca, modelo = MARCAS_RAMPLAS[idx % len(MARCAS_RAMPLAS)]
            # 4 de las 6 refrigeradas tienen certificado de gases vigente; las
            # otras 2 quedan como repuesto y nunca se usan en un viaje.
            plan.append(
                RamplaPlan(
                    idx=idx,
                    patente=f"RPDA{idx + 1:02d}",
                    tipo=tipo,
                    marca=marca,
                    modelo=modelo,
                    anio=2015 + (idx * 5) % 10,
                    capacidad=CAPACIDAD_RAMPLA[tipo],
                    volumen=VOLUMEN_RAMPLA[tipo],
                    certificado_gases=tipo == "refrigerada" and idx in (22, 23, 24, 25),
                )
            )
            idx += 1
    return plan


def construir_choferes() -> list[ChoferPlan]:
    plan: list[ChoferPlan] = []
    for i in range(45):
        if i == 42:
            # Licencia y examen vencen en 20 días: solo viajes históricos.
            licencia_vence = FECHA_DEMO + timedelta(days=20)
            examen_vence = FECHA_DEMO + timedelta(days=20)
        else:
            licencia_vence = date(2028, 3, 31) - timedelta(days=(i % 12) * 17)
            examen_vence = date(2027, 9, 30) - timedelta(days=(i % 9) * 23)
        plan.append(
            ChoferPlan(
                idx=i,
                rut=rut(12_500_000 + i * 811),
                nombre=NOMBRES[i % len(NOMBRES)],
                apellido_paterno=APELLIDOS[(i * 3) % len(APELLIDOS)],
                apellido_materno=APELLIDOS[(i * 7 + 5) % len(APELLIDOS)],
                telefono=f"+56 9 {6000 + i * 37:04d} {1000 + (i * 53) % 9000:04d}",
                email=f"conductor{i + 1:02d}@demo-tei.cl",
                numero_licencia=f"A5-2026-{i + 1:04d}",
                estado="vacaciones" if i in (40, 41) else "disponible",
                licencia_vence=licencia_vence,
                examen_vence=examen_vence,
                sueldo_base=650000 + (i % 6) * 35000,
            )
        )
    return plan


def construir_clientes() -> list[ClientePlan]:
    plan: list[ClientePlan] = []
    for i, (razon, giro, ciudad, dias, exige, contacto) in enumerate(CLIENTES_DEMO):
        plan.append(
            ClientePlan(
                idx=i,
                razon_social=razon,
                rut=rut(79_400_000 + i * 1357),
                giro=giro,
                ciudad=ciudad,
                dias_pago=dias,
                exige_oc=exige,
                contacto=contacto,
                telefono=f"+56 2 {2400 + i * 11:04d} {3000 + (i * 97) % 6000:04d}",
                email=f"logistica{i + 1:02d}@cliente-demo.cl",
            )
        )
    return plan


def duracion_dias(km: float) -> int:
    if km <= 160:
        return 2
    if km <= 620:
        return 3
    return 4


def valor_flete(tarifa: dict[str, Any], km: float, peso: int) -> int:
    modalidad = tarifa["modalidad"]
    if modalidad == "km":
        bruto = tarifa["precio"] * km
    elif modalidad == "tonelada":
        bruto = tarifa["precio"] * (peso / 1000)
    else:
        # Un viaje "por viaje" igual escala algo con la distancia.
        bruto = tarifa["precio"] * (1 + max(0.0, (km - 200) / 4000))
    return redondear(bruto, 1000)


def tarifa_para(cliente: int, familia: str, origen: str, destino: str) -> int:
    candidatas = [t for t in TARIFAS if t["cliente"] == cliente]
    for t in candidatas:
        if t["origen"] == origen and t["destino"] == destino:
            return t["idx"]
    for t in candidatas:
        if FAMILIA_POR_TIPO.get(t["tipo_rampla"]) == familia:
            return t["idx"]
    return candidatas[0]["idx"]


def construir_equipos(ramplas: list[RamplaPlan]) -> list[Equipo]:
    """40 equipos con rampla compatible; los 2 últimos son tractos en taller."""
    indices_rampla = (
        list(range(0, 10))       # plana
        + list(range(10, 22))    # sider
        + [22, 23, 24, 25]       # refrigerada CON certificado de gases
        + list(range(28, 34))    # portacontenedor
        + list(range(34, 38))    # cisterna
        + [38, 39, 40]           # granelera
        + [41]                   # cama_baja
    )
    assert len(indices_rampla) == 40, len(indices_rampla)
    equipos: list[Equipo] = []
    for i, ri in enumerate(indices_rampla):
        equipos.append(
            Equipo(
                idx=i,
                tracto=i,
                rampla=ri,
                chofer=42 if i == 39 else i,
                familia=FAMILIA_POR_TIPO[ramplas[ri].tipo],
                cursor=a_local(INICIO_HISTORICO, 6, 0) + timedelta(minutes=25 * i),
                taller=i in (38, 39),
            )
        )
    return equipos


def planificar_viajes(
    tractos: list[TractoPlan],
    ramplas: list[RamplaPlan],
    equipos: list[Equipo],
    rng: random.Random,
) -> list[ViajePlan]:
    """Genera el plan. Ningún recurso se solapa: el cursor avanza con fin_real."""
    plan: list[ViajePlan] = []
    fin_tope = a_local(FIN_HISTORICO, 23, 0)

    def nuevo(eq: Equipo, inicio: datetime) -> ViajePlan:
        familia = eq.familia
        origen, destino, km = RUTAS[familia][eq.contador % len(RUTAS[familia])]
        pool = CLIENTES_POR_FAMILIA[familia]
        cliente = pool[eq.contador % len(pool)]
        tarifa_idx = tarifa_para(cliente, familia, origen, destino)
        dur = duracion_dias(km)

        inicio = inicio.replace(minute=rng.choice([0, 15, 30, 45]))
        fin_plan = inicio + timedelta(days=dur) - timedelta(minutes=rng.randint(0, 180))
        if fin_plan <= inicio:
            fin_plan = inicio + timedelta(hours=26)
        # 12 % de los viajes históricos llega tarde (2–30 h). El resto llega
        # antes de lo planificado: una desviación de minutos no es "atraso".
        if rng.random() < 0.12:
            fin_real = fin_plan + timedelta(minutes=rng.randint(120, 1800))
        else:
            fin_real = fin_plan - timedelta(minutes=rng.randint(20, 150))
        inicio_real = inicio + timedelta(minutes=rng.randint(-45, 240))
        if fin_real < inicio_real + timedelta(hours=8):
            fin_real = inicio_real + timedelta(hours=8)

        peso_min, peso_max = PESO_POR_FAMILIA[familia]
        peso = min(
            rng.randint(peso_min, peso_max),
            tractos[eq.tracto].capacidad,
            ramplas[eq.rampla].capacidad,
        )
        return ViajePlan(
            idx=len(plan),
            equipo=eq.idx,
            cliente=cliente,
            tarifa_idx=tarifa_idx,
            tracto=eq.tracto,
            rampla=eq.rampla,
            chofer=eq.chofer,
            familia=familia,
            tipo_carga=TIPO_CARGA_POR_FAMILIA[familia],
            refrigerada=familia == "refrigerada",
            origen=origen,
            destino=destino,
            distancia=km,
            inicio=inicio,
            fin_planificado=fin_plan,
            inicio_real=inicio_real,
            fin_real=fin_real,
            fin_estimado=None,
            buffer=rng.choice([60, 75, 90, 90, 105, 120]),
            peso=peso,
            valor=valor_flete(TARIFAS[tarifa_idx], km, peso),
            recargos=0,
            estado_objetivo="cerrado",
        )

    # --- 1. Histórico (2026-08-01 → 2026-10-31) --------------------------
    rondas = 0
    while len(plan) < MES_HISTORICO and rondas < 40:
        for eq in equipos:
            if len(plan) >= MES_HISTORICO:
                break
            tope = a_local(CORTE_TALLER, 23, 0) if eq.taller else fin_tope
            v = nuevo(eq, eq.cursor)
            if v.fin_planificado <= tope:
                plan.append(v)
                # Ocupación real = fin_real + buffer; el cursor parte de ahí.
                eq.cursor = v.fin_real + timedelta(
                    minutes=v.buffer + rng.randint(120, 900)
                )
            eq.contador += 1
        rondas += 1

    # --- 2. En curso (2026-11-01 / 02) ----------------------------------
    estados_curso = [
        "en_ruta", "en_ruta", "en_ruta", "en_ruta", "en_ruta",
        "en_descarga", "en_descarga", "en_descarga", "en_descarga",
        "pod_pendiente", "pod_pendiente", "pod_pendiente",
    ]
    for k, estado in enumerate(estados_curso):
        eq = equipos[k]
        inicio = a_local(date(2026, 11, 1), 5 + (k % 5), 0)
        if eq.cursor > inicio:
            inicio = eq.cursor
        v = nuevo(eq, inicio)
        v.estado_objetivo = estado
        if estado == "pod_pendiente":
            v.fin_estimado = None
            v.fin_real = v.fin_planificado - timedelta(hours=2)
        else:
            v.fin_estimado = v.fin_planificado
            v.fin_real = None
        eq.cursor = v.fin_planificado + timedelta(minutes=v.buffer + 240)
        eq.contador += 1
        plan.append(v)

    # --- 3. Futuros (2026-11-03 → 2026-11-15) ---------------------------
    estados_futuro = [
        "asignado", "asignado", "asignado", "asignado", "asignado", "asignado",
        "confirmado", "confirmado", "confirmado", "confirmado", "confirmado",
        "confirmado",
    ]
    for k, estado in enumerate(estados_futuro):
        eq = equipos[(k * 3) % 38]
        inicio = a_local(date(2026, 11, 3 + (k % 12)), 7 + (k % 4), 0)
        if eq.cursor > inicio:
            inicio = eq.cursor
        if inicio.date() > date(2026, 11, 15):
            inicio = a_local(date(2026, 11, 15), 8, 0)
        v = nuevo(eq, inicio)
        v.estado_objetivo = estado
        v.inicio_real = None
        v.fin_real = None
        v.fin_estimado = None
        if estado == "confirmado":
            # Aún sin recursos: es lo que falta asignar en la mesa de despacho.
            v.tracto = -1
            v.rampla = -1
            v.chofer = -1
        else:
            eq.cursor = v.fin_planificado + timedelta(minutes=v.buffer + 240)
        eq.contador += 1
        plan.append(v)

    return plan


def asignar_estados(plan: list[ViajePlan], rng: random.Random) -> None:
    """Reparte cobrado/facturado/cerrado/anulado en el histórico."""
    for v in plan:
        if v.idx >= MES_HISTORICO:
            continue
        r = rng.random()
        if r < 0.085:
            v.estado_objetivo = "anulado"
            v.motivo_anulacion = MOTIVOS_ANULACION[v.idx % len(MOTIVOS_ANULACION)]
        elif r < 0.125:
            v.estado_objetivo = "cerrado"
        elif r < 0.262:
            v.estado_objetivo = "facturado"
        else:
            v.estado_objetivo = "cobrado"


def construir_ocs(clientes: list[ClientePlan]) -> list[dict[str, Any]]:
    """Esqueleto de OC con vigencias; el monto se calcula al asignar viajes."""
    ocs: list[dict[str, Any]] = []
    idx = 0
    for cl in clientes:
        periodos = (
            PERIODOS_OC if cl.idx != 13
            else ((date(2026, 7, 15), date(2026, 10, 15)),)
        )
        for p, (desde, hasta) in enumerate(periodos):
            ocs.append(
                {
                    "idx": idx,
                    "cliente": cl.idx,
                    "desde": desde,
                    "hasta": hasta,
                    "periodo": p,
                    "estado_inicial": "abierta",
                    "factor": 1.08,
                    "numero": f"OC-DEMO-{idx + 1:04d}",
                }
            )
            idx += 1
        if cl.idx == 13:
            # Reemplazo anulado por el cliente antes de emitir el primer viaje.
            ocs.append(
                {
                    "idx": idx,
                    "cliente": cl.idx,
                    "desde": date(2026, 10, 16),
                    "hasta": date(2026, 12, 31),
                    "periodo": 99,
                    "estado_inicial": "anulada",
                    "factor": 1.0,
                    "numero": f"OC-DEMO-{idx + 1:04d}",
                }
            )
            idx += 1
    return ocs


def asignar_ordenes_compra(plan: list[ViajePlan], ocs: list[dict[str, Any]]) -> None:
    """Cada viaje usa la OC de su cliente que cubre el rango completo."""
    for v in plan:
        if v.estado_objetivo == "anulado":
            continue
        inicio = v.inicio.date()
        # `fn_viaje_validar` compara contra el fin efectivo + buffer: el mismo
        # cálculo aquí evita asignar una OC que el trigger va a rechazar.
        fin_efectivo = (
            v.fin_real or v.fin_estimado or v.fin_planificado
        ) + timedelta(minutes=v.buffer)
        fin = fin_efectivo.date()
        elegida = None
        for oc in ocs:
            if oc["cliente"] != v.cliente or oc["estado_inicial"] != "abierta":
                continue
            if oc["desde"] <= inicio and fin <= oc["hasta"]:
                elegida = oc["idx"]
                break
        v.oc_idx = elegida
        if elegida is None and v.estado_objetivo in ("cobrado", "facturado"):
            # Sin OC vigente no se puede facturar: queda cerrado sin facturar.
            v.estado_objetivo = "cerrado"


# ---------------------------------------------------------------------------
# Escritura idempotente
# ---------------------------------------------------------------------------
class Cargador:
    """Inserta filas del dataset demo sin duplicar en re-ejecuciones."""

    def __init__(self, cur: psycopg.Cursor, verbose: bool = True) -> None:
        self.cur = cur
        self.verbose = verbose
        self.insertados: dict[str, int] = {}
        self.existentes: dict[str, set[Any]] = {}

    def log(self, mensaje: str) -> None:
        if self.verbose:
            print(mensaje, flush=True)

    def precargar(self, tabla: str, columna: str = "id") -> set[Any]:
        self.cur.execute(
            f"select {columna} from nucleo.{tabla} where empresa_id = %s",
            (EMPRESA_ID,),
        )
        self.existentes[tabla] = {fila[0] for fila in self.cur.fetchall()}
        return self.existentes[tabla]

    def nuevo(self, tabla: str, identificador: Any) -> bool:
        """True si la clave no se había visto todavía."""
        vistos = self.existentes.setdefault(tabla, set())
        if identificador in vistos:
            return False
        vistos.add(identificador)
        self.insertados[tabla] = self.insertados.get(tabla, 0) + 1
        return True


TABLAS_CON_ID = (
    "tractos", "ramplas", "choferes", "clientes", "tarifas", "documentos",
    "ordenes_compra", "viajes", "pautas_mantenimiento", "mantenimientos",
    "precios_diesel", "tenant_reglas_entidad", "solicitudes",
    "configuracion_empresa", "reservas_recurso", "pod", "viaje_gastos",
    "viaje_incidentes", "pagos_nucleo", "notas_credito_nucleo", "centros_costo",
)


def precargar_todo(c: Cargador) -> None:
    for tabla in TABLAS_CON_ID:
        c.precargar(tabla)
    c.precargar("facturas_nucleo", "numero_factura")


def cargar_tractos_y_ramplas(c: Cargador, tractos, ramplas) -> None:
    cur = c.cur
    for t in tractos:
        tid = uid("tracto", t.idx)
        if not c.nuevo("tractos", tid):
            continue
        cur.execute(
            """
            insert into nucleo.tractos
              (id, empresa_id, patente, marca, modelo, ano, vin, color,
               configuracion_ejes, peso_bruto_kg, tara_kg, capacidad_carga_kg,
               km_actual, licencias_permitidas, estado, activo,
               ubicacion_ciudad, observaciones, created_by)
            values
              (%(id)s, %(empresa)s, %(patente)s, %(marca)s, %(modelo)s,
               %(anio)s, %(vin)s, %(color)s, '6x4', %(pb)s, %(tara)s,
               %(cap)s, %(km)s, array['A5'],
               %(estado)s::nucleo.estado_recurso, true, 'Santiago',
               %(obs)s, 'demo')
            """,
            {
                "id": tid, "empresa": EMPRESA_ID, "patente": t.patente,
                "marca": t.marca, "modelo": t.modelo, "anio": t.anio,
                "vin": vin("DEMOVIN", t.idx),
                "color": ["Blanco", "Azul", "Rojo", "Gris", "Verde"][t.idx % 5],
                "pb": t.peso_bruto, "tara": t.tara, "cap": t.capacidad,
                "km": t.km_actual, "estado": t.estado,
                "obs": f"Unidad demo {t.idx + 1}",
            },
        )

    for r in ramplas:
        rid = uid("rampla", r.idx)
        if not c.nuevo("ramplas", rid):
            continue
        refrigerada = r.tipo == "refrigerada"
        cur.execute(
            """
            insert into nucleo.ramplas
              (id, empresa_id, patente, tipo, marca, modelo, ano, vin,
               capacidad_carga_kg, volumen_m3, largo_m, ancho_m, alto_m,
               peso_tara_kg, ejes, temperatura_min_c, temperatura_max_c,
               estado, activo, ubicacion_ciudad, observaciones, created_by)
            values
              (%(id)s, %(empresa)s, %(patente)s,
               %(tipo)s::nucleo.tipo_rampla, %(marca)s, %(modelo)s, %(anio)s,
               %(vin)s, %(cap)s, %(vol)s, 13.6, 2.6, 2.9, 7200, 3,
               %(tmin)s, %(tmax)s, 'disponible', true, 'Santiago', %(obs)s,
               'demo')
            """,
            {
                "id": rid, "empresa": EMPRESA_ID, "patente": r.patente,
                "tipo": r.tipo, "marca": r.marca, "modelo": r.modelo,
                "anio": r.anio, "vin": vin("DEMORV", r.idx), "cap": r.capacidad,
                "vol": r.volumen,
                "tmin": TEMPERATURA_RAMPLA[0] if refrigerada else None,
                "tmax": TEMPERATURA_RAMPLA[1] if refrigerada else None,
                "obs": f"Rampla demo {r.idx + 1}",
            },
        )


def cargar_choferes_y_clientes(c: Cargador, choferes, clientes) -> None:
    cur = c.cur
    for ch in choferes:
        cid = uid("chofer", ch.idx)
        if not c.nuevo("choferes", cid):
            continue
        cur.execute(
            """
            insert into nucleo.choferes
              (id, empresa_id, rut, nombre, apellido_paterno, apellido_materno,
               fecha_nacimiento, telefono, email, comuna, ciudad,
               numero_licencia, licencia_clase, autorizado_carga_peligrosa,
               sueldo_base, porcentaje_comision, estado, activo,
               contacto_emergencia_nombre, contacto_emergencia_telefono,
               observaciones, created_by)
            values
              (%(id)s, %(empresa)s, %(rut)s, %(nombre)s, %(ap)s, %(am)s,
               %(nacimiento)s, %(telefono)s, %(email)s, 'Santiago', 'Santiago',
               %(licencia)s, 'A5', false, %(sueldo)s, 0.10,
               %(estado)s::nucleo.estado_recurso, true, 'Contacto demo',
               '+56 9 5555 0000', %(obs)s, 'demo')
            """,
            {
                "id": cid, "empresa": EMPRESA_ID, "rut": ch.rut,
                "nombre": ch.nombre, "ap": ch.apellido_paterno,
                "am": ch.apellido_materno,
                "nacimiento": date(1972 + ch.idx % 25, 1 + ch.idx % 12, 1 + ch.idx % 27),
                "telefono": ch.telefono, "email": ch.email,
                "licencia": ch.numero_licencia, "sueldo": ch.sueldo_base,
                "estado": ch.estado, "obs": f"Conductor demo {ch.idx + 1}",
            },
        )

    for cl in clientes:
        clid = uid("cliente", cl.idx)
        if not c.nuevo("clientes", clid):
            continue
        cur.execute(
            """
            insert into nucleo.clientes
              (id, empresa_id, razon_social, rut, giro, direccion, comuna,
               ciudad, contacto_nombre, contacto_email, contacto_telefono,
               dias_pago, credito_autorizado, exige_oc, activo, observaciones,
               created_by)
            values
              (%(id)s, %(empresa)s, %(razon)s, %(rut)s, %(giro)s, %(dir)s,
               %(ciudad)s, %(ciudad)s, %(contacto)s, %(email)s, %(telefono)s,
               %(dias)s, %(credito)s, %(exige)s, true, %(obs)s, 'demo')
            """,
            {
                "id": clid, "empresa": EMPRESA_ID, "razon": cl.razon_social,
                "rut": cl.rut, "giro": cl.giro,
                "dir": f"Av. Industrial {100 + cl.idx * 37}",
                "ciudad": cl.ciudad, "contacto": cl.contacto,
                "email": cl.email, "telefono": cl.telefono,
                "dias": cl.dias_pago, "credito": 15000000 + cl.idx * 2500000,
                "exige": cl.exige_oc,
                "obs": "Cliente ficticio del dataset demo",
            },
        )


def cargar_documentos(c: Cargador, tractos, ramplas, choferes) -> None:
    cur = c.cur

    def insertar(fid, recurso_tipo, tipo, vence, columna, recurso_id, numero):
        if not c.nuevo("documentos", fid):
            return
        cur.execute(
            f"""
            insert into nucleo.documentos
              (id, empresa_id, recurso_tipo, {columna}, tipo, numero,
               entidad_emisora, emitido_en, vence_en, es_vigente,
               observaciones, created_by)
            values
              (%(id)s, %(empresa)s, %(recurso)s::nucleo.tipo_recurso,
               %(recurso_id)s, %(tipo)s::nucleo.tipo_documento, %(numero)s,
               'Organismo demo', %(emitido)s, %(vence)s, true,
               'Documento ficticio demo', 'demo')
            """,
            {
                "id": fid, "empresa": EMPRESA_ID, "recurso": recurso_tipo,
                "recurso_id": recurso_id, "tipo": tipo, "numero": numero,
                "emitido": vence - timedelta(days=365), "vence": vence,
            },
        )

    for t in tractos:
        for tipo in ("revision_tecnica", "permiso_circulacion",
                     "seguro_obligatorio", "soap"):
            if tipo == "revision_tecnica":
                vence = date(2026, 11, 15) if t.idx in (38, 39) else date(2027, 6, 30)
            elif tipo == "permiso_circulacion":
                vence = date(2027, 6, 30)
            else:
                vence = date(2027, 3, 31)
            insertar(
                uid("documento", f"tracto:{t.idx}:{tipo}"), "tracto", tipo,
                vence, "tracto_id", uid("tracto", t.idx),
                f"{tipo[:3].upper()}-{t.patente}",
            )

    for r in ramplas:
        for tipo in ("revision_tecnica", "permiso_circulacion", "seguro_carga"):
            insertar(
                uid("documento", f"rampla:{r.idx}:{tipo}"), "rampla", tipo,
                date(2027, 6, 30), "rampla_id", uid("rampla", r.idx),
                f"{tipo[:3].upper()}-{r.patente}",
            )
        if r.certificado_gases:
            insertar(
                uid("documento", f"rampla:{r.idx}:certificado_gases"), "rampla",
                "certificado_gases", date(2027, 5, 31), "rampla_id",
                uid("rampla", r.idx), f"GAS-{r.patente}",
            )

    for ch in choferes:
        insertar(
            uid("documento", f"chofer:{ch.idx}:licencia_conducir"), "chofer",
            "licencia_conducir", ch.licencia_vence, "chofer_id",
            uid("chofer", ch.idx), ch.numero_licencia,
        )
        insertar(
            uid("documento", f"chofer:{ch.idx}:examen_medico"), "chofer",
            "examen_medico", ch.examen_vence, "chofer_id",
            uid("chofer", ch.idx), f"MED-{ch.rut}",
        )


def cargar_tarifas_y_oc(
    c: Cargador,
    tarifas: list[dict[str, Any]],
    clientes: list[ClientePlan],
    viajes: list[ViajePlan],
    ocs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cur = c.cur
    for t in tarifas:
        tid = uid("tarifa", t["idx"])
        if not c.nuevo("tarifas", tid):
            continue
        cur.execute(
            """
            insert into nucleo.tarifas
              (id, empresa_id, cliente_id, codigo, nombre, descripcion,
               modalidad, origen, destino, tipo_rampla, tipo_carga,
               vigencia_desde, vigencia_hasta, moneda, precio_unitario,
               minimo_cobro, incluye_peajes, incluye_combustible,
               precio_diesel_base, rendimiento_km_l, recargos, condiciones,
               activo, created_by)
            values
              (%(id)s, %(empresa)s, %(cliente)s, %(codigo)s, %(nombre)s,
               %(desc)s, %(modalidad)s::nucleo.modalidad_tarifa, %(origen)s,
               %(destino)s, %(tipo_rampla)s::nucleo.tipo_rampla,
               %(tipo_carga)s::nucleo.tipo_carga, '2026-01-01', '2026-12-31',
               'CLP', %(precio)s, 0, false, false, 1000, 2.6,
               '{"estadia_clp_por_dia": 85000}'::jsonb,
               '{"origen": "catalogo demo"}'::jsonb, true, 'demo')
            """,
            {
                "id": tid, "empresa": EMPRESA_ID,
                "cliente": uid("cliente", t["cliente"]), "codigo": t["codigo"],
                "nombre": t["nombre"], "desc": f"Tarifa demo {t['codigo']}",
                "modalidad": t["modalidad"], "origen": t["origen"],
                "destino": t["destino"], "tipo_rampla": t["tipo_rampla"],
                "tipo_carga": TIPO_CARGA_POR_FAMILIA[
                    FAMILIA_POR_TIPO[t["tipo_rampla"]]
                ],
                "precio": t["precio"],
            },
        )

    # El monto autorizado se dimensiona con el plan ya resuelto.
    consumo: dict[int, int] = {oc["idx"]: 0 for oc in ocs}
    for v in viajes:
        if v.oc_idx is not None:
            consumo[v.oc_idx] += v.valor + v.recargos

    abiertas = [oc for oc in ocs if oc["estado_inicial"] == "abierta"]
    for oc in sorted(abiertas, key=lambda x: consumo[x["idx"]], reverse=True)[:2]:
        oc["factor"] = 1.005  # dos OC "cerca del límite" (>= 99 %)

    for oc in ocs:
        oid = uid("oc", oc["idx"])
        oc["id"] = oid
        if not c.nuevo("ordenes_compra", oid):
            continue
        monto = (
            12_000_000
            if oc["estado_inicial"] == "anulada"
            else max(1_000_000,
                     math.ceil(consumo[oc["idx"]] * oc["factor"] / 10000) * 10000)
        )
        cur.execute(
            """
            insert into nucleo.ordenes_compra
              (id, empresa_id, cliente_id, numero_oc, referencia_interna,
               fecha_emision, vigencia_desde, vigencia_hasta, monto_autorizado,
               condiciones_pago_dias, estado, aprobado_por, aprobado_en,
               centro_costo_id, observaciones, created_by)
            values
              (%(id)s, %(empresa)s, %(cliente)s, %(numero)s, %(ref)s, %(emision)s,
               %(desde)s, %(hasta)s, %(monto)s, %(dias)s,
               %(estado)s::nucleo.estado_oc, 'demo', now(), %(cc)s, %(obs)s,
               'demo')
            """,
            {
                "id": oid, "empresa": EMPRESA_ID,
                "cliente": uid("cliente", oc["cliente"]), "numero": oc["numero"],
                "ref": f"DEMO-{oc['numero']}",
                "emision": oc["desde"] - timedelta(days=5),
                "desde": oc["desde"], "hasta": oc["hasta"], "monto": monto,
                "dias": clientes[oc["cliente"]].dias_pago,
                "estado": oc["estado_inicial"],
                "cc": next(iter(c.existentes.get("centros_costo", [])), None),
                "obs": "OC ficticia del dataset demo",
            },
        )
    return ocs


def cargar_viajes(
    c: Cargador,
    viajes: list[ViajePlan],
    tractos: list[TractoPlan],
    ramplas: list[RamplaPlan],
    clientes: list[ClientePlan],
    ocs: list[dict[str, Any]],
    rng: random.Random,
) -> None:
    cur = c.cur
    ocs_por_idx = {oc["idx"]: oc for oc in ocs}
    total = len(viajes)

    for n, v in enumerate(viajes, start=1):
        if n % 150 == 0:
            c.log(f"  viajes: {n}/{total}")
        vid = uid("viaje", v.idx)
        if not c.nuevo("viajes", vid):
            continue
        v.insertado = True

        cliente = clientes[v.cliente]
        origen = CIUDADES[v.origen]
        destino = CIUDADES[v.destino]
        tracto = tractos[v.tracto] if v.tracto >= 0 else None

        estado_insert = v.estado_objetivo
        if estado_insert in ("cobrado", "facturado"):
            estado_insert = "cerrado"
        elif estado_insert == "anulado":
            estado_insert = "confirmado"

        fin_est = v.fin_estimado
        fin_real = v.fin_real
        inicio_real = v.inicio_real
        if v.estado_objetivo == "confirmado":
            fin_est = fin_real = inicio_real = None
        elif v.estado_objetivo in ("en_ruta", "en_descarga"):
            fin_real = None
        elif v.estado_objetivo == "pod_pendiente":
            fin_est = None

        cur.execute(
            """
            insert into nucleo.viajes
              (id, empresa_id, cliente_id, orden_compra_id, tarifa_id,
               tracto_id, rampla_id, chofer_id, estado,
               inicio_planificado, fin_planificado, fin_estimado,
               inicio_real, fin_real, buffer_minutos, prioridad, tipo_carga,
               descripcion_carga, peso_bruto_kg, refrigerada,
               temperatura_min_c, temperatura_max_c,
               origen_nombre, origen_direccion, origen_comuna, origen_ciudad,
               origen_region, origen_lat, origen_lon,
               destino_nombre, destino_direccion, destino_comuna,
               destino_ciudad, destino_region, destino_lat, destino_lon,
               distancia_km, tiempo_estimado_h, valor_flete_neto,
               monto_recargos, moneda, condiciones_pago_dias,
               contacto_origen_nombre, contacto_origen_telefono,
               contacto_destino_nombre, contacto_destino_telefono,
               observaciones, created_by)
            values
              (%(id)s, %(empresa)s, %(cliente)s, %(oc)s, %(tarifa)s,
               %(tracto)s, %(rampla)s, %(chofer)s,
               %(estado)s::nucleo.estado_viaje,
               %(inicio)s, %(fin_plan)s, %(fin_est)s, %(inicio_real)s,
               %(fin_real)s, %(buffer)s, 3, %(tipo_carga)s::nucleo.tipo_carga,
               %(descripcion)s, %(peso)s, %(refrigerada)s, %(tmin)s, %(tmax)s,
               %(o_nombre)s, %(o_dir)s, %(o_comuna)s, %(o_ciudad)s,
               %(o_region)s, %(o_lat)s, %(o_lon)s,
               %(d_nombre)s, %(d_dir)s, %(d_comuna)s, %(d_ciudad)s,
               %(d_region)s, %(d_lat)s, %(d_lon)s,
               %(km)s, %(horas)s, %(valor)s, %(recargos)s, 'CLP', %(dias)s,
               %(contacto)s, %(telefono)s, %(contacto)s, %(telefono)s,
               %(obs)s, 'demo')
            """,
            {
                "id": vid, "empresa": EMPRESA_ID,
                "cliente": uid("cliente", v.cliente),
                "oc": ocs_por_idx[v.oc_idx]["id"] if v.oc_idx is not None else None,
                "tarifa": uid("tarifa", v.tarifa_idx),
                "tracto": uid("tracto", v.tracto) if tracto else None,
                "rampla": uid("rampla", v.rampla) if v.rampla >= 0 else None,
                "chofer": uid("chofer", v.chofer) if v.chofer >= 0 else None,
                "estado": estado_insert,
                "inicio": v.inicio, "fin_plan": v.fin_planificado,
                "fin_est": fin_est, "inicio_real": inicio_real,
                "fin_real": fin_real, "buffer": v.buffer,
                "tipo_carga": v.tipo_carga,
                "descripcion": descripcion_carga(v), "peso": v.peso,
                "refrigerada": v.refrigerada,
                "tmin": TEMPERATURA_RAMPLA[0] if v.refrigerada else None,
                "tmax": TEMPERATURA_RAMPLA[1] if v.refrigerada else None,
                "o_nombre": f"Planta {v.origen}",
                "o_dir": f"Ruta acceso {100 + v.idx % 400}",
                "o_comuna": origen[0], "o_ciudad": v.origen,
                "o_region": origen[1], "o_lat": origen[2], "o_lon": origen[3],
                "d_nombre": f"Centro {v.destino}",
                "d_dir": f"Ruta acceso {200 + v.idx % 400}",
                "d_comuna": destino[0], "d_ciudad": v.destino,
                "d_region": destino[1], "d_lat": destino[2], "d_lon": destino[3],
                "km": v.distancia, "horas": round(v.distancia / 55, 1),
                "valor": v.valor, "recargos": v.recargos,
                "dias": cliente.dias_pago, "contacto": cliente.contacto,
                "telefono": cliente.telefono,
                "obs": v.observaciones or f"Carga {v.tipo_carga} demo",
            },
        )

        if v.estado_objetivo == "anulado":
            cur.execute(
                """
                update nucleo.viajes
                   set estado = 'anulado', motivo_anulacion = %s
                 where empresa_id = %s and id = %s and estado = 'confirmado'
                """,
                (v.motivo_anulacion, EMPRESA_ID, vid),
            )
            v.eventos.extend([
                ("confirmacion", "Cupo confirmado con el cliente",
                 v.inicio - timedelta(days=2)),
                ("anulacion", f"Viaje anulado: {v.motivo_anulacion}",
                 v.inicio - timedelta(hours=6)),
            ])
        elif v.estado_objetivo in ("cerrado", "facturado", "cobrado"):
            v.eventos.extend([
                ("asignacion", "Recursos asignados por despacho",
                 v.inicio - timedelta(hours=10)),
                ("inicio", f"Salida desde {v.origen}", v.inicio_real or v.inicio),
                ("llegada", f"Llegada a {v.destino}",
                 v.fin_real or v.fin_planificado),
            ])
        elif v.estado_objetivo == "en_ruta":
            v.eventos.extend([
                ("asignacion", "Recursos asignados por despacho",
                 v.inicio - timedelta(hours=10)),
                ("inicio", f"Salida desde {v.origen}", v.inicio_real or v.inicio),
                ("ruta", f"En tránsito hacia {v.destino}", v.inicio + timedelta(hours=8)),
            ])
        elif v.estado_objetivo == "en_descarga":
            v.eventos.extend([
                ("asignacion", "Recursos asignados por despacho",
                 v.inicio - timedelta(hours=10)),
                ("inicio", f"Salida desde {v.origen}", v.inicio_real or v.inicio),
                ("llegada", f"Llegada a {v.destino}", v.inicio + timedelta(days=1)),
                ("descarga", "Descarga en curso en destino",
                 v.inicio + timedelta(days=1, hours=2)),
            ])
        elif v.estado_objetivo == "pod_pendiente":
            v.eventos.extend([
                ("asignacion", "Recursos asignados por despacho",
                 v.inicio - timedelta(hours=10)),
                ("inicio", f"Salida desde {v.origen}", v.inicio_real or v.inicio),
                ("llegada", f"Llegada a {v.destino}", v.fin_real or v.inicio),
            ])
        elif v.estado_objetivo == "asignado":
            v.eventos.extend([
                ("asignacion", "Recursos asignados por despacho",
                 v.inicio - timedelta(hours=12)),
                ("documentos", "Documentación del viaje validada",
                 v.inicio - timedelta(hours=8)),
            ])
        elif v.estado_objetivo == "confirmado":
            v.eventos.extend([
                ("confirmacion", "Cupo confirmado con el cliente",
                 v.inicio - timedelta(days=3)),
                ("agenda", "Viaje programado en la agenda de despacho",
                 v.inicio - timedelta(days=1)),
            ])

        cargar_expediente(c, vid, v, rng)


def descripcion_carga(v: ViajePlan) -> str:
    return {
        "refrigerada": "Pallet de producto congelado, cadena de frío",
        "contenedor": "Contenedor 40' HC consolidado",
        "cisterna": "Carga líquida a granel",
        "granel": "Carga a granel ensacada",
        "maquinaria": "Maquinaria sobre cama baja",
    }.get(v.familia, "Carga general palletizada")


def cargar_expediente(
    c: Cargador, viaje_id: uuid.UUID, v: ViajePlan, rng: random.Random
) -> None:
    """Checklist, paradas y eventos coherentes con el estado del viaje."""
    cur = c.cur
    completados = {
        "cobrado": 5, "facturado": 5, "cerrado": 5, "pod_pendiente": 4,
        "en_descarga": 3, "en_ruta": 2, "confirmado": 0, "asignado": 0,
        "anulado": 1,
    }[v.estado_objetivo]

    momento = v.fin_real or v.fin_planificado
    cur.execute(
        """
        update nucleo.viaje_checklist
           set requerido = (orden <= 3),
               completado = (orden <= %(n)s),
               completado_en = case when orden <= %(n)s then %(m)s else null end,
               completado_por = case when orden <= %(n)s then 'demo' else null end
         where empresa_id = %(empresa)s and viaje_id = %(viaje)s
        """,
        {"n": completados, "m": momento, "empresa": EMPRESA_ID, "viaje": viaje_id},
    )

    if v.estado_objetivo in ("anulado",):
        estados = ("omitida", "omitida")
    elif v.estado_objetivo in ("confirmado", "asignado"):
        estados = ("pendiente", "pendiente")
    elif v.estado_objetivo == "en_ruta":
        estados = ("completada", "pendiente")
    elif v.estado_objetivo == "en_descarga":
        estados = ("completada", "en_curso")
    else:
        estados = ("completada", "completada")

    cur.execute(
        """
        update nucleo.viaje_paradas
           set estado = case when orden = 1 then %(o1)s else %(o2)s end,
               ventana_hasta = coalesce(ventana_hasta, %(hasta)s)
         where empresa_id = %(empresa)s and viaje_id = %(viaje)s
        """,
        {
            "o1": estados[0], "o2": estados[1], "hasta": v.fin_planificado,
            "empresa": EMPRESA_ID, "viaje": viaje_id,
        },
    )

    filas = [
        (
            uid("evento", f"{v.idx}:{i}"), EMPRESA_ID, viaje_id, tipo,
            descripcion, cuando, "demo",
        )
        for i, (tipo, descripcion, cuando) in enumerate(v.eventos)
    ]
    if filas:
        cur.executemany(
            """
            insert into nucleo.viaje_eventos
              (id, empresa_id, viaje_id, tipo, descripcion, ocurrido_en, auth_id)
            values (%s, %s, %s, %s, %s, %s, %s)
            """,
            filas,
        )
        c.insertados["viaje_eventos"] = c.insertados.get("viaje_eventos", 0) + len(filas)


def normalizar_llegadas(c: Cargador) -> None:
    """Deja 88 % de los viajes a tiempo y 12 % con 2–30 h de atraso.

    El primer run usó una banda de ruido de ±90 min; esta pasada, idempotente,
    elimina esa banda (solo toca `0 < atraso <= 2 h`) para que la distribución
    cumpla la regla del dataset. Los triggers del núcleo recalculan `ventana` y
    las reservas; la ventana solo se acorta, así que no puede crear solapes.
    """
    c.cur.execute(
        """
        update nucleo.viajes
           set fin_real = fin_planificado
                          - make_interval(
                              mins => 20 + (abs(hashtext(id::text)) %% 120))
         where empresa_id = %s
           and created_by = 'demo'
           and fin_real is not null
           and fin_real > fin_planificado
           and fin_real <= fin_planificado + interval '2 hours'
        """,
        (EMPRESA_ID,),
    )
    if c.cur.rowcount:
        c.log(f"  llegadas normalizadas: {c.cur.rowcount}")


def cargar_gastos(
    c: Cargador, viajes: list[ViajePlan], diesel: dict[date, int], rng: random.Random
) -> None:
    """Combustible, peaje y viático en la mayoría de los viajes."""
    cur = c.cur
    rechazado = False
    for v in viajes:
        if not v.insertado:
            continue
        if v.estado_objetivo in ("anulado", "confirmado"):
            continue
        vid = uid("viaje", v.idx)
        fecha = (v.inicio_real or v.inicio).date()
        precio = diesel.get(fecha) or min(diesel.values())
        litros = max(40.0, v.distancia / 2.6)
        neto_peaje = rng.randrange(4700, 50000, 500)

        filas = [
            (
                "combustible",
                PROVEEDORES_COMBUSTIBLE[v.idx % len(PROVEEDORES_COMBUSTIBLE)],
                f"FAC-{v.idx:06d}", fecha,
                dos_decimales(litros * precio * 1.19),
                dos_decimales(litros * precio * 0.19),
                round(litros, 3), precio,
                "Estación demo",
            ),
            (
                "peaje",
                PROVEEDORES_PEAJE[v.idx % len(PROVEEDORES_PEAJE)],
                f"TP-{v.idx:06d}", fecha,
                dos_decimales(neto_peaje * 1.19),
                dos_decimales(neto_peaje * 0.19),
                None, None, None,
            ),
        ]
        if v.idx % 10 != 3:
            filas.append(
                ("viatico", "Viático conductor", f"VD-{v.idx:06d}", fecha,
                 dos_decimales(rng.randrange(25000, 70000, 1000)),
                 Decimal("0"), None, None, None)
            )
        if v.recargos:
            filas.append(
                ("estadia", "Terminal de descarga", f"ES-{v.idx:06d}", fecha,
                 dos_decimales(v.recargos * 1.19),
                 dos_decimales(v.recargos * 0.19), None, None, None)
            )

        for i, (tipo, proveedor, numdoc, f, monto, iva, litros_, precio_l, estacion) in enumerate(filas):
            gid = uid("gasto", f"{v.idx}:{i}:{tipo}")
            if not c.nuevo("viaje_gastos", gid):
                continue
            es_rechazo = False
            if not rechazado and tipo == "peaje" and v.idx > 400:
                rechazado = True
                es_rechazo = True
            cur.execute(
                """
                insert into nucleo.viaje_gastos
                  (id, empresa_id, viaje_id, tipo, proveedor, numero_documento,
                   fecha, monto_total, iva, litros, precio_litro, estacion,
                   estado, motivo_rechazo, aprobado_por, aprobado_en,
                   observaciones, created_by)
                values
                  (%(id)s, %(empresa)s, %(viaje)s, %(tipo)s, %(proveedor)s,
                   %(numdoc)s, %(fecha)s, %(monto)s, %(iva)s, %(litros)s,
                   %(precio)s, %(estacion)s, %(estado)s, %(motivo)s,
                   %(aprobado_por)s, %(aprobado_en)s, %(obs)s, 'demo')
                """,
                {
                    "id": gid, "empresa": EMPRESA_ID, "viaje": vid,
                    "tipo": tipo, "proveedor": proveedor, "numdoc": numdoc,
                    "fecha": f, "monto": monto, "iva": iva, "litros": litros_,
                    "precio": precio_l, "estacion": estacion,
                    "estado": "rechazado" if es_rechazo else "aprobado",
                    "motivo": "Comprobante no coincide con el monto declarado"
                    if es_rechazo else None,
                    "aprobado_por": None if es_rechazo else "demo",
                    "aprobado_en": None if es_rechazo else v.fin_planificado,
                    "obs": f"Gasto demo {tipo}",
                },
            )


def cargar_pod(
    c: Cargador, viajes: list[ViajePlan], clientes: list[ClientePlan]
) -> None:
    cur = c.cur
    for v in viajes:
        if not v.insertado:
            continue
        if v.estado_objetivo not in ("cerrado", "facturado", "cobrado"):
            continue
        if not v.con_pod:
            continue
        pid = uid("pod", v.idx)
        if not c.nuevo("pod", pid):
            continue
        fotos = [f"demo/pod/{v.idx:05d}-foto1.jpg",
                 f"demo/pod/{v.idx:05d}-foto2.jpg"]
        if v.idx % 3 == 0:
            fotos.append(f"demo/pod/{v.idx:05d}-foto3.jpg")
        cur.execute(
            """
            insert into nucleo.pod
              (id, empresa_id, viaje_id, receptor_nombre, receptor_rut,
               receptor_cargo, fecha_hora, lat, lon, firma_url, fotos,
               danios, observaciones, created_by)
            values
              (%(id)s, %(empresa)s, %(viaje)s, %(receptor)s, %(rut)s,
               'Jefe de bodega', %(fecha)s, %(lat)s, %(lon)s, %(firma)s,
               %(fotos)s::jsonb, %(danios)s, %(obs)s, 'demo')
            """,
            {
                "id": pid, "empresa": EMPRESA_ID, "viaje": uid("viaje", v.idx),
                "receptor": f"Receptor {clientes[v.cliente].razon_social.split()[0]} {v.idx % 90:02d}",
                "rut": rut(20_000_000 + v.idx * 13),
                "fecha": v.fin_real or v.fin_planificado,
                "lat": CIUDADES[v.destino][2], "lon": CIUDADES[v.destino][3],
                "firma": f"demo/pod/{v.idx:05d}.png",
                "fotos": Json(fotos), "danios": v.danios,
                "obs": "Entrega con observaciones" if v.danios else "Entrega conforme",
            },
        )


def cargar_incidentes(c: Cargador, viajes: list[ViajePlan]) -> None:
    """10 incidentes: 3 abiertos (2 de severidad alta) y 7 resueltos."""
    cur = c.cur
    candidatos = [
        v for v in viajes
        if v.insertado
        and v.idx < MES_HISTORICO
        and v.estado_objetivo in ("cerrado", "facturado", "cobrado")
    ]
    if len(candidatos) < 10:
        return
    definiciones = [
        ("bascula", "alta", "abierto",
         "Control de báscula en Ruta 5: diferencia de 380 kg contra la guía de "
         "despacho. El peso cargado está dentro de la capacidad del equipo.", None),
        ("bascula", "media", "abierto",
         "Segunda pesada en planta de destino arroja 240 kg menos que en origen. "
         "Se solicita revisión del ticket de pesaje.", None),
        ("documento", "alta", "abierto",
         "El cliente observa el sello de la guía de despacho y retiene la "
         "recepción hasta validar con su bodega central.", None),
        ("retraso", "media", "cerrado",
         "Espera de 4 horas en portería por turno de carga saturado.",
         "Se reprogramó la ventana de carga y se avisó al cliente."),
        ("falla_mecanica", "alta", "cerrado",
         "Falla del sistema de frenos detectada en ruta; se detuvo la unidad.",
         "Se reemplazó la válvula moduladora en taller. Viaje retomado."),
        ("retraso", "baja", "cerrado",
         "Congestión en el acceso al puerto de San Antonio.",
         "Se informó al cliente y se ajustó la ventana de descarga."),
        ("danio_carga", "media", "cerrado",
         "Dos pallets con embalaje deformado por manipulación en bodega.",
         "Se acordó nota de cargo con el cliente y se reclasificó la carga."),
        ("clima", "media", "cerrado",
         "Corte de ruta por nieve en el paso hacia la cordillera.",
         "Se desvió el viaje por ruta alternativa con 6 horas de demora."),
        ("retraso", "baja", "cerrado",
         "El cliente no tenía grúa disponible al momento de la llegada.",
         "Se acordó nueva ventana de descarga al día siguiente."),
        ("combustible", "baja", "cerrado",
         "Diferencia de 12 litros entre el surtidor y el rendimiento esperado.",
         "Se revisó el odómetro y se ajustó el registro de combustible."),
    ]
    for i, (tipo, severidad, estado, descripcion, resolucion) in enumerate(definiciones):
        v = candidatos[(i * 47) % len(candidatos)]
        iid = uid("incidente", i)
        if not c.nuevo("viaje_incidentes", iid):
            continue
        ocurrido = (v.inicio_real or v.inicio) + timedelta(hours=6 + i)
        cur.execute(
            """
            insert into nucleo.viaje_incidentes
              (id, empresa_id, viaje_id, tipo, severidad, descripcion, estado,
               ocurrido_en, reportado_por, resolucion, resuelto_por,
               resuelto_en, created_by)
            values
              (%(id)s, %(empresa)s, %(viaje)s, %(tipo)s, %(sev)s, %(desc)s,
               %(estado)s, %(ocurrido)s, 'demo', %(resolucion)s, %(por)s,
               %(resuelto)s, 'demo')
            """,
            {
                "id": iid, "empresa": EMPRESA_ID, "viaje": uid("viaje", v.idx),
                "tipo": tipo, "sev": severidad, "desc": descripcion,
                "estado": estado, "ocurrido": ocurrido,
                "resolucion": resolucion,
                "por": "demo" if resolucion else None,
                "resuelto": ocurrido + timedelta(days=1) if resolucion else None,
            },
        )
        if tipo == "bascula":
            v.observaciones = "Incidente de báscula registrado (ver expediente)"


def cargar_mantenimiento(
    c: Cargador, tractos: list[TractoPlan], ramplas: list[RamplaPlan]
) -> None:
    cur = c.cur
    pautas = [
        ("tracto", "Cambio de aceite y filtros", 15000, 6, 3000),
        ("tracto", "Revisión de frenos", 40000, 12, 5000),
        ("tracto", "Neumáticos y alineación", 60000, 18, 6000),
        ("rampla", "Revisión de suspensión", 50000, 12, 5000),
    ]
    ids_pautas: list[tuple[uuid.UUID, int, int, int]] = []
    for i, (recurso, item, intervalo, meses, alerta) in enumerate(pautas):
        pid = uid("pauta", i)
        ids_pautas.append((pid, intervalo, meses, alerta))
        if not c.nuevo("pautas_mantenimiento", pid):
            continue
        cur.execute(
            """
            insert into nucleo.pautas_mantenimiento
              (id, empresa_id, recurso_tipo, item, intervalo_km,
               intervalo_meses, alerta_km, orden, activo, created_by)
            values (%s, %s, %s::nucleo.tipo_recurso, %s, %s, %s, %s, %s,
                    true, 'demo')
            """,
            (pid, EMPRESA_ID, recurso, item, intervalo, meses, alerta, i),
        )

    rng = random.Random(SEMILLA + 7)
    mas_km = max(range(40), key=lambda i: tractos[i].km_actual)

    for i in range(24):
        mid = uid("mantenimiento", i)
        if not c.nuevo("mantenimientos", mid):
            continue
        fecha = date(2026, 8, 5) + timedelta(days=i * 3 + (i % 4))
        if i == 0:
            # Mantención FUERA DE PAUTA: 250.000 km después del último servicio
            # de frenos (intervalo 40.000) sobre el tracto de mayor odómetro.
            tracto_idx, pauta_i = mas_km, 1
            km = tractos[mas_km].km_actual - 250000
        else:
            tracto_idx = (i * 7) % 40
            pauta_i = i % 3
            km = max(0, tractos[tracto_idx].km_actual - rng.randint(2000, 28000))
        pid, intervalo, meses, alerta = ids_pautas[pauta_i]
        anulado = i == 17
        cur.execute(
            """
            insert into nucleo.mantenimientos
              (id, empresa_id, tracto_id, pauta_id, fecha, km, costo, estado,
               motivo_anulacion, anulada_en, anulada_por,
               intervalo_km_snapshot, intervalo_meses_snapshot,
               alerta_km_snapshot, observaciones, respaldo_url, created_by)
            values
              (%(id)s, %(empresa)s, %(tracto)s, %(pauta)s, %(fecha)s, %(km)s,
               %(costo)s, %(estado)s, %(motivo)s, %(anulada_en)s, %(por)s,
               %(intervalo)s, %(meses)s, %(alerta)s, %(obs)s, %(respaldo)s,
               'demo')
            """,
            {
                "id": mid, "empresa": EMPRESA_ID,
                "tracto": uid("tracto", tracto_idx), "pauta": pid,
                "fecha": fecha, "km": km,
                "costo": rng.randrange(180000, 2400000, 1000),
                "estado": "anulado" if anulado else "realizado",
                "motivo": "Duplicado: ya existía una orden de taller para el mismo trabajo"
                if anulado else None,
                "anulada_en": local(2026, 9, 1, 10) if anulado else None,
                "por": "demo" if anulado else None,
                "intervalo": intervalo, "meses": meses, "alerta": alerta,
                "obs": "Mantención fuera de pauta: intervalo excedido respecto "
                "de la programación" if i == 0 else f"Mantención demo {i + 1}",
                "respaldo": f"respaldos/demo/mantencion-{i:03d}.pdf",
            },
        )

    mid = uid("mantenimiento", 100)
    if c.nuevo("mantenimientos", mid):
        pid, intervalo, meses, alerta = ids_pautas[3]
        cur.execute(
            """
            insert into nucleo.mantenimientos
              (id, empresa_id, rampla_id, pauta_id, fecha, km, costo, estado,
               intervalo_km_snapshot, intervalo_meses_snapshot,
               alerta_km_snapshot, observaciones, respaldo_url, created_by)
            values (%s, %s, %s, %s, %s, %s, %s, 'realizado', %s, %s, %s, %s,
                    %s, 'demo')
            """,
            (
                mid, EMPRESA_ID, uid("rampla", 3), pid, date(2026, 9, 22),
                120000, 890000, intervalo, meses, alerta,
                "Revisión de suspensión de rampla",
                "respaldos/demo/mantencion-rampla.pdf",
            ),
        )

    reservas = [
        (uid("reserva", 1), "tracto", uid("tracto", 38), None,
         local(2026, 10, 20, 8), local(2026, 10, 24, 18), "mantenimiento",
         "Reparación de caja de cambios (unidad en taller)"),
        (uid("reserva", 2), "chofer", None, uid("chofer", 40),
         local(2026, 10, 26, 0), local(2026, 11, 8, 0), "vacaciones",
         "Vacaciones legales programadas"),
    ]
    for rid, recurso, tracto_id, chofer_id, desde, hasta, tipo, motivo in reservas:
        if not c.nuevo("reservas_recurso", rid):
            continue
        cur.execute(
            """
            insert into nucleo.reservas_recurso
              (id, empresa_id, recurso_tipo, tracto_id, chofer_id, ventana,
               tipo_reserva, motivo, activa, creado_por)
            values (%s, %s, %s::nucleo.tipo_recurso, %s, %s,
                    tstzrange(%s, %s, '[)'), %s::nucleo.tipo_reserva, %s,
                    true, 'demo')
            """,
            (rid, EMPRESA_ID, recurso, tracto_id, chofer_id, desde, hasta,
             tipo, motivo),
        )


def cargar_diesel(c: Cargador) -> dict[date, int]:
    cur = c.cur
    rng = random.Random(SEMILLA + 11)
    precios: dict[date, int] = {}
    fecha = date(2026, 8, 3)
    for _ in range(13):
        precio = 950 + rng.randrange(0, 200, 5)
        precios[fecha] = precio
        did = uid("diesel", fecha.isoformat())
        if c.nuevo("precios_diesel", did):
            cur.execute(
                """
                insert into nucleo.precios_diesel
                  (id, empresa_id, fecha, precio_litro, fuente, created_by)
                values (%s, %s, %s, %s, 'Precio ficticio demo', 'demo')
                """,
                (did, EMPRESA_ID, fecha, precio),
            )
        fecha += timedelta(days=7)
    return precios


def cargar_chat_y_config(
    c: Cargador,
    clientes: list[ClientePlan],
    choferes: list[ChoferPlan],
    viajes: list[ViajePlan],
) -> uuid.UUID | None:
    """Reglas de entidad, directivas, módulo apagado y solicitud pendiente."""
    cur = c.cur

    reglas_cliente = [
        (clientes[0].idx, "ventana_recepcion",
         {"desde": "07:30", "hasta": "16:00",
          "dias": ["lun", "mar", "mie", "jue", "vie"]}),
        (clientes[6].idx, "orden_compra_requerida",
         {"requerida": True,
          "nota": "Bodega central exige OC impresa en portería"}),
    ]
    for i, (ref_idx, clave, valor) in enumerate(reglas_cliente):
        rid = uid("regla", i)
        if not c.nuevo("tenant_reglas_entidad", rid):
            continue
        cur.execute(
            """
            insert into nucleo.tenant_reglas_entidad
              (id, empresa_id, entidad, cliente_id, clave, valor,
               vigente_desde, created_by)
            values (%s, %s, 'cliente', %s, %s, %s, %s, 'demo')
            """,
            (rid, EMPRESA_ID, uid("cliente", ref_idx), clave,
             Json(valor), local(2026, 7, 1, 9)),
        )

    rid = uid("regla", 2)
    if c.nuevo("tenant_reglas_entidad", rid):
        cur.execute(
            """
            insert into nucleo.tenant_reglas_entidad
              (id, empresa_id, entidad, chofer_id, clave, valor,
               vigente_desde, created_by)
            values (%s, %s, 'chofer', %s, %s, %s, %s, 'demo')
            """,
            (rid, EMPRESA_ID, uid("chofer", choferes[0].idx), "zona_preferente",
             Json({"ciudades": ["Santiago", "Concepción", "Talca"],
                   "nota": "Preferencia declarada"}),
             local(2026, 7, 1, 9)),
        )

    directivas = [
        ("directiva_prioridad_sobrepeso",
         {"texto": "Ante sobrepeso en báscula, avisar a despacho antes de mover "
                   "el camión."}),
        ("directiva_cobranza_recordatorio",
         {"dias_antes_vencimiento": 5,
          "texto": "Recordar al cliente por correo 5 días antes del vencimiento."}),
    ]
    for i, (clave, valor) in enumerate(directivas):
        cid = uid("directiva", i)
        if not c.nuevo("configuracion_empresa", cid):
            continue
        cur.execute(
            """
            insert into nucleo.configuracion_empresa
              (id, empresa_id, clave, valor, vigente_desde, created_by)
            values (%s, %s, %s, %s, %s, 'demo')
            """,
            (cid, EMPRESA_ID, clave, Json(valor), local(2026, 8, 1, 9)),
        )

    # Módulo WhatsApp apagado: sin fila, o con false, el gate está cerrado.
    cur.execute(
        """
        insert into nucleo.modulos_empresa
          (empresa_id, modulo_id, habilitado, created_by)
        values (%s, 'agente-whatsapp', false, 'demo')
        on conflict (empresa_id, modulo_id) do nothing
        """,
        (EMPRESA_ID,),
    )

    futuro = next((v for v in viajes if v.estado_objetivo == "asignado"), None)
    if futuro is None:
        return None
    sid = uid("solicitud", 1)
    if not c.nuevo("solicitudes", sid):
        return uid("viaje", futuro.idx)

    cur.execute(
        """
        select ue.id
          from nucleo.usuarios_empresa ue
          join auth.users au on au.id = ue.auth_id
         where ue.empresa_id = %s and au.email = 'admin@tei.local'
         limit 1
        """,
        (EMPRESA_ID,),
    )
    fila = cur.fetchone()
    if fila is None:
        c.log("  aviso: no se encontró la membresía de admin@tei.local")
        return None
    payload = {
        "accion": "anular_viaje",
        "datos": {"motivo": "Cliente reprogramó la carga"},
        "origen": "chat_inapp",
        "agente": "secretaria",
    }
    cur.execute(
        """
        insert into nucleo.solicitudes
          (id, empresa_id, tipo, solicitante_usuario_empresa_id, viaje_id,
           payload, clave_idempotencia, estado, created_by)
        values (%s, %s, 'otra', %s, %s, %s, %s, 'pendiente', 'demo')
        """,
        (sid, EMPRESA_ID, fila[0], uid("viaje", futuro.idx), Json(payload),
         "demo-chat-anulacion-001"),
    )
    return uid("viaje", futuro.idx)


# ---------------------------------------------------------------------------
# Facturación
# ---------------------------------------------------------------------------
def agrupar_facturas(viajes: list[ViajePlan]) -> list[dict[str, Any]]:
    grupos: dict[tuple[int, str], list[ViajePlan]] = {}
    for v in viajes:
        if not v.insertado:
            continue
        if v.estado_objetivo not in ("cobrado", "facturado") or v.oc_idx is None:
            continue
        grupos.setdefault((v.cliente, v.estado_objetivo), []).append(v)

    facturas: list[dict[str, Any]] = []
    numero = 0
    for (cliente_idx, tipo), lista in sorted(grupos.items()):
        lista.sort(key=lambda x: (x.fin_real or x.fin_planificado))
        bloques: list[list[ViajePlan]] = []
        actual: list[ViajePlan] = []
        for v in lista:
            actual.append(v)
            if len(actual) >= 4 + (len(bloques) % 3):  # 4, 5 o 6 viajes
                bloques.append(actual)
                actual = []
        if actual:
            # Reequilibrar para que ningún bloque quede con 1–3 viajes.
            while len(actual) < 4 and bloques and len(bloques[-1]) > 4:
                actual.insert(0, bloques[-1].pop())
            if len(actual) >= 4 or not bloques:
                bloques.append(actual)
            else:
                bloques[-1].extend(actual)
        for bloque in bloques:
            numero += 1
            facturas.append(
                {
                    "numero": numero,
                    "cliente": cliente_idx,
                    "tipo": tipo,
                    "viajes": bloque,
                    "oc": Counter(v.oc_idx for v in bloque).most_common(1)[0][0],
                }
            )
    facturas.sort(key=lambda f: f["viajes"][0].fin_real or f["viajes"][0].fin_planificado)
    return facturas


def cargar_pago(
    c: Cargador, factura_id: uuid.UUID, fecha: date, monto: Decimal, n: int
) -> None:
    pid = uid("pago", n)
    if not c.nuevo("pagos_nucleo", pid):
        return
    c.cur.execute(
        """
        insert into nucleo.pagos_nucleo
          (id, empresa_id, factura_id, fecha, monto, metodo, referencia,
           observaciones, created_by)
        values (%s, %s, %s, %s, %s, 'transferencia', %s, 'Pago demo', 'demo')
        """,
        (pid, EMPRESA_ID, factura_id, fecha, monto, f"TRF-{n:05d}"),
    )


def cargar_facturacion(
    c: Cargador,
    viajes: list[ViajePlan],
    clientes: list[ClientePlan],
    ocs: list[dict[str, Any]],
) -> dict[str, int]:
    cur = c.cur
    ocs_por_idx = {oc["idx"]: oc for oc in ocs}
    facturas = agrupar_facturas(viajes)

    facturadas = [f for f in facturas if f["tipo"] == "facturado"]
    # Las 2 más recientes llevan pago parcial; el resto queda impaga.
    parciales = {id(f) for f in facturadas[-2:]}
    # Cliente con pagos crónicamente atrasados (demo de cobranza).
    cronico = 0

    creadas = vencidas = parciales_creadas = 0
    for f in facturas:
        fid = uid("factura", f["numero"])
        numero_factura = f"FAC-DEMO-{f['numero']:04d}"
        f["id"] = fid
        f["numero_factura"] = numero_factura
        ya_existe = numero_factura in c.existentes.get("facturas_nucleo", set())
        if not ya_existe:
            creadas += 1
        c.existentes.setdefault("facturas_nucleo", set()).add(numero_factura)
        if ya_existe:
            continue

        cliente = clientes[f["cliente"]]
        neto = sum(v.valor + v.recargos for v in f["viajes"])
        iva = dos_decimales(Decimal(neto) * Decimal("0.19"))
        neto_d = dos_decimales(neto)
        fin_max = max((v.fin_real or v.fin_planificado) for v in f["viajes"])
        emision = fin_max.date() + timedelta(days=3)
        vencimiento = emision + timedelta(days=cliente.dias_pago)

        if f["tipo"] == "facturado" and id(f) in parciales:
            emision = min(emision, FECHA_DEMO - timedelta(days=45))
            vencimiento = emision + timedelta(days=cliente.dias_pago)

        cur.execute(
            """
            insert into nucleo.facturas_nucleo
              (id, empresa_id, numero_factura, cliente_id, orden_compra_id,
               fecha_emision, fecha_vencimiento, moneda, neto, iva,
               observaciones, created_by)
            values (%s, %s, %s, %s, %s, %s, %s, 'CLP', %s, %s, %s, 'demo')
            """,
            (
                fid, EMPRESA_ID, numero_factura, uid("cliente", f["cliente"]),
                ocs_por_idx[f["oc"]]["id"] if f["oc"] is not None else None,
                emision, vencimiento, neto_d, iva,
                f"Factura demo con {len(f['viajes'])} viajes",
            ),
        )

        cur.executemany(
            """
            insert into nucleo.factura_viajes
              (empresa_id, factura_id, viaje_id, monto)
            values (%s, %s, %s, %s)
            """,
            [(EMPRESA_ID, fid, uid("viaje", v.idx), v.valor + v.recargos)
             for v in f["viajes"]],
        )

        for v in f["viajes"]:
            cur.execute(
                """
                update nucleo.viajes
                   set estado = 'facturado'
                 where empresa_id = %s and id = %s and estado = 'cerrado'
                """,
                (EMPRESA_ID, uid("viaje", v.idx)),
            )
            evid = uid("evento", f"{v.idx}:facturacion")
            if c.nuevo("viaje_eventos", evid):
                cur.execute(
                    """
                    insert into nucleo.viaje_eventos
                      (id, empresa_id, viaje_id, tipo, descripcion, ocurrido_en,
                       auth_id)
                    values (%s, %s, %s, 'facturacion', %s, %s, 'demo')
                    """,
                    (evid, EMPRESA_ID, uid("viaje", v.idx),
                     f"Incluido en factura {numero_factura}",
                     datetime.combine(emision, time(12), tzinfo=ZONA)),
                )

        total = dos_decimales(neto_d + iva)

        if f["tipo"] == "cobrado":
            if f["cliente"] == cronico:
                # 7 a 15 días después del vencimiento.
                atraso = 7 + f["numero"] % 9
            else:
                # Paga entre 5 días antes y el día del vencimiento.
                atraso = -(f["numero"] % 6)
            fecha_pago = vencimiento + timedelta(days=atraso)
            fecha_pago = max(fecha_pago, emision + timedelta(days=2))
            fecha_pago = min(fecha_pago, FECHA_DEMO)
            cargar_pago(c, fid, fecha_pago, total, f["numero"])
        elif id(f) in parciales:
            parciales_creadas += 1
            cargar_pago(c, fid, FECHA_DEMO - timedelta(days=8),
                        dos_decimales(total * Decimal("0.45")), f["numero"])
            if parciales_creadas == 1:
                ncid = uid("nota_credito", 1)
                if c.nuevo("notas_credito_nucleo", ncid):
                    cur.execute(
                        """
                        insert into nucleo.notas_credito_nucleo
                          (id, empresa_id, factura_id, numero, fecha, monto,
                           motivo, estado, created_by)
                        values (%s, %s, %s, %s, %s, %s, %s, 'aplicada', 'demo')
                        """,
                        (
                            ncid, EMPRESA_ID, fid, "NC-DEMO-0001",
                            FECHA_DEMO - timedelta(days=6),
                            dos_decimales(Decimal(neto) * Decimal("0.12")),
                            "Diferencia de tarifa por cambio de ruta autorizado",
                        ),
                    )

        # El estado lo calcula la función, no el script.
        cur.execute("select nucleo.fn_factura_estado(%s)", (fid,))
        cur.execute("select estado from nucleo.facturas_nucleo where id = %s", (fid,))
        if cur.fetchone()[0] == "vencida":
            vencidas += 1

    # Una factura vencida hace 45 días (cliente 7) para el reporte de cobranza.
    objetivo = next((f for f in facturadas if f["cliente"] == 7), None)
    if objetivo is not None and objetivo["numero_factura"] in c.existentes.get(
        "facturas_nucleo", set()
    ):
        cur.execute(
            """
            update nucleo.facturas_nucleo
               set fecha_emision = %s, fecha_vencimiento = %s, observaciones = %s
             where empresa_id = %s and id = %s
            """,
            (
                FECHA_DEMO - timedelta(days=75),
                FECHA_DEMO - timedelta(days=45),
                "Factura vencida hace 45 días (demo de cobranza)",
                EMPRESA_ID, objetivo["id"],
            ),
        )
        cur.execute("select nucleo.fn_factura_estado(%s)", (objetivo["id"],))

    return {"creadas": creadas, "vencidas": vencidas, "parciales": parciales_creadas}


# ---------------------------------------------------------------------------
# Reset del dataset demo
# ---------------------------------------------------------------------------
# Orden hijo → padre. `None` = filtrar solo por `created_by='demo'`.
_DEMO = "created_by = 'demo'"

RESET_ORDEN: list[tuple[str, str]] = [
    ("factura_viajes",
     "factura_id in (select id from nucleo.facturas_nucleo "
     "where empresa_id = %(empresa)s and created_by = 'demo')"),
    ("pagos_nucleo", _DEMO),
    ("notas_credito_nucleo", _DEMO),
    ("facturas_nucleo", _DEMO),
    ("pod", _DEMO),
    ("viaje_gastos", _DEMO),
    ("viaje_incidentes", _DEMO),
    ("viaje_eventos", "auth_id = 'demo'"),
    ("viaje_checklist", _DEMO),
    ("viaje_paradas", _DEMO),
    ("solicitudes", _DEMO),
    ("reservas_recurso", "creado_por = 'demo'"),
    ("viajes", _DEMO),
    ("documentos", _DEMO),
    ("mantenimientos", _DEMO),
    ("pautas_mantenimiento", _DEMO),
    ("ordenes_compra", _DEMO),
    ("tarifas", _DEMO),
    ("configuracion_empresa", _DEMO),
    ("precios_diesel", _DEMO),
    ("clientes", _DEMO + " and id <> all(%(protegidos)s::uuid[])"),
    ("choferes", _DEMO + " and id <> all(%(protegidos)s::uuid[])"),
    ("ramplas", _DEMO),
    ("tractos", _DEMO),
]

# Triggers append-only que impiden borrar. Solo se desactivan dentro de esta
# transacción y se reactivan de inmediato: el reset nunca deja el control apagado.
# `tenant_reglas_entidad` NO está aquí: su dueño es `supabase_admin` y `postgres`
# no puede desactivar sus triggers. Sus 3 reglas demo se conservan (y los
# clientes/choferes que referencian) para no romper la FK.
RESET_TRIGGERS = [
    ("pod", "trg_pod_no_delete"),
    ("viaje_eventos", "trg_eventos_inmutable"),
    ("documentos", "trg_documentos_no_delete"),
    ("reservas_recurso", "trg_reservas_no_delete"),
    ("mantenimientos", "trg_mantenimientos_no_borrar"),
    ("viajes", "trg_viajes_20_proteccion"),
    ("configuracion_empresa", "trg_config_empresa_no_borrar"),
]


def _ids_protegidos(cur: psycopg.Cursor, tabla: str, columna: str) -> list[uuid.UUID]:
    """Ids demo referenciados por `tenant_reglas_entidad` (no se pueden borrar)."""
    cur.execute(
        f"select distinct {columna} from nucleo.tenant_reglas_entidad "
        f"where empresa_id = %s and {columna} is not null",
        (EMPRESA_ID,),
    )
    return [fila[0] for fila in cur.fetchall()]


def reset_demo(conn: psycopg.Connection, verbose: bool = True) -> None:
    """Borra **solo** las filas del dataset demo (`created_by='demo'`).

    Cada DELETE lleva la marca en el WHERE: nunca toca filas del seed original
    ni de otras empresas. Los triggers append-only se desactivan y reactivan
    dentro de la misma transacción; si algo falla, el rollback los deja como
    estaban.
    """
    with conn.cursor() as cur:
        cur.execute(
            "select count(*) from nucleo.viajes "
            "where empresa_id = %s and created_by = 'demo'",
            (EMPRESA_ID,),
        )
        print(f"Reset: {cur.fetchone()[0]} viajes demo marcados para borrar")

        protegidos = {
            "clientes": _ids_protegidos(cur, "clientes", "cliente_id"),
            "choferes": _ids_protegidos(cur, "choferes", "chofer_id"),
        }

        for tabla, trigger in RESET_TRIGGERS:
            cur.execute(f"alter table nucleo.{tabla} disable trigger {trigger}")

        total = 0
        for tabla, condicion in RESET_ORDEN:
            params: dict[str, Any] = {"empresa": EMPRESA_ID}
            if "%(protegidos)s" in condicion:
                params["protegidos"] = protegidos.get(tabla, [])
            cur.execute(
                f"delete from nucleo.{tabla} "
                f"where empresa_id = %(empresa)s and ({condicion})",
                params,
            )
            borradas = cur.rowcount
            total += borradas
            if verbose and borradas:
                print(f"  {tabla:24s} {borradas}")

        for tabla, trigger in RESET_TRIGGERS:
            cur.execute(f"alter table nucleo.{tabla} enable trigger {trigger}")

        # Verificación: el libro de viajes demo debe quedar vacío.
        for tabla in ("viajes", "facturas_nucleo", "pod", "viaje_gastos"):
            cur.execute(
                f"select count(*) from nucleo.{tabla} "
                f"where empresa_id = %s and created_by = 'demo'",
                (EMPRESA_ID,),
            )
            if cur.fetchone()[0]:
                raise RuntimeError(f"Reset incompleto: quedan filas demo en {tabla}")
        print(
            f"Reset OK: {total} filas demo eliminadas. Conservadas por FK: "
            f"{len(protegidos['clientes'])} clientes, "
            f"{len(protegidos['choferes'])} choferes, "
            "3 reglas de tenant (tabla de supabase_admin)"
        )


# ---------------------------------------------------------------------------
# Verificación e informe
# ---------------------------------------------------------------------------
CONSULTAS_MUESTRA = [
    ("Viajes por estado (tenant TEI)", (EMPRESA_ID,), """
        select estado::text as estado, count(*) as viajes,
               to_char(sum(monto_total_neto), 'FM999G999G999G999') as neto_clp
          from nucleo.viajes
         where empresa_id = %s
         group by estado
         order by viajes desc
    """),
    ("Top 5 clientes por facturación", (EMPRESA_ID,), """
        select c.razon_social,
               count(distinct f.id) as facturas,
               to_char(sum(f.total), 'FM999G999G999G999') as total_clp
          from nucleo.facturas_nucleo f
          join nucleo.clientes c
            on c.empresa_id = f.empresa_id and c.id = f.cliente_id
         where f.empresa_id = %s and f.estado <> 'anulada'
         group by c.razon_social
         order by sum(f.total) desc
         limit 5
    """),
    ("Aging de cartera (facturas con saldo)", (EMPRESA_ID,), """
        with saldo as (
          select f.id, f.fecha_vencimiento,
                 f.total
                 - coalesce((select sum(p.monto) from nucleo.pagos_nucleo p
                              where p.factura_id = f.id), 0)
                 - coalesce((select sum(n.monto)
                               from nucleo.notas_credito_nucleo n
                              where n.factura_id = f.id and n.estado = 'aplicada'), 0)
                 as pendiente
            from nucleo.facturas_nucleo f
           where f.empresa_id = %s and f.estado in ('emitida','parcial','vencida')
        )
        select case
                 when fecha_vencimiento >= current_date then 'corriente'
                 when current_date - fecha_vencimiento <= 30 then '1-30 dias'
                 when current_date - fecha_vencimiento <= 60 then '31-60 dias'
                 when current_date - fecha_vencimiento <= 90 then '61-90 dias'
                 else 'mas de 90 dias'
               end as tramo,
               count(*) as facturas,
               to_char(sum(pendiente), 'FM999G999G999G999') as pendiente_clp
          from saldo
         where pendiente > 0
         group by tramo
         order by min(fecha_vencimiento)
    """),
    ("Disponibilidad de flota (tenant TEI)", (EMPRESA_ID, EMPRESA_ID, EMPRESA_ID), """
        select 'tracto' as recurso, estado::text as estado, count(*) as unidades
          from nucleo.tractos where empresa_id = %s and activo group by estado
        union all
        select 'rampla', estado::text, count(*)
          from nucleo.ramplas where empresa_id = %s and activo group by estado
        union all
        select 'chofer', estado::text, count(*)
          from nucleo.choferes where empresa_id = %s and activo group by estado
        order by recurso, estado
    """),
]


def consultar(cur: psycopg.Cursor, titulo: str, params: tuple, sql: str) -> None:
    cur.execute(sql, params)
    columnas = [d.name for d in cur.description or []]
    filas = cur.fetchall()
    print(f"\n-- {titulo}")
    print("   " + " | ".join(columnas))
    for fila in filas:
        print("   " + " | ".join(str(valor) for valor in fila))
    if not filas:
        print("   (sin filas)")


def verificar(cur: psycopg.Cursor) -> dict[str, Any]:
    def uno(sql: str, params: tuple = (EMPRESA_ID,)) -> Any:
        cur.execute(sql, params)
        return cur.fetchone()[0]

    return {
        "tractos": uno("select count(*) from nucleo.tractos where empresa_id=%s and patente like 'LJAA%%'"),
        "ramplas": uno("select count(*) from nucleo.ramplas where empresa_id=%s and patente like 'RPDA%%'"),
        "choferes": uno("select count(*) from nucleo.choferes where empresa_id=%s and rut like '12.5%%'"),
        "clientes": uno("select count(*) from nucleo.clientes where empresa_id=%s and razon_social not like 'Cliente %%'"),
        "viajes_demo": uno("select count(*) from nucleo.viajes where empresa_id=%s and created_by='demo'"),
        "viajes_total": uno("select count(*) from nucleo.viajes where empresa_id=%s"),
        "facturas": uno("select count(*) from nucleo.facturas_nucleo where empresa_id=%s and numero_factura like 'FAC-DEMO-%%'"),
        "anulados": uno("select count(*) from nucleo.viajes where empresa_id=%s and estado='anulado' and created_by='demo'"),
        "vencidas": uno("select count(*) from nucleo.facturas_nucleo where empresa_id=%s and estado='vencida' and numero_factura like 'FAC-DEMO-%%'"),
        "incidentes_abiertos": uno("select count(*) from nucleo.viaje_incidentes where empresa_id=%s and estado='abierto' and created_by='demo'"),
        "talleres": uno("select count(*) from nucleo.tractos where empresa_id=%s and estado='en_taller' and patente like 'LJAA%%'"),
        "mantenimientos": uno("select count(*) from nucleo.mantenimientos where empresa_id=%s and created_by='demo'"),
        "precios_diesel": uno("select count(*) from nucleo.precios_diesel where empresa_id=%s and fuente like 'Precio ficticio%%'"),
        "pod": uno("select count(*) from nucleo.pod where empresa_id=%s and created_by='demo'"),
        "gastos": uno("select count(*) from nucleo.viaje_gastos where empresa_id=%s and created_by='demo'"),
        "solicitud_pendiente": uno("select count(*) from nucleo.solicitudes where empresa_id=%s and clave_idempotencia='demo-chat-anulacion-001' and estado='pendiente'"),
        "solapes": uno("""
            select count(*) from (
              select 1
                from nucleo.reservas_recurso a
                join nucleo.reservas_recurso b
                  on a.empresa_id = b.empresa_id
                 and a.id < b.id
                 and a.activa and b.activa
                 and a.ventana && b.ventana
                 and a.recurso_tipo = b.recurso_tipo
                 and coalesce(a.tracto_id, a.rampla_id, a.chofer_id)
                   = coalesce(b.tracto_id, b.rampla_id, b.chofer_id)
               where a.empresa_id = %s
            ) x
        """),
        "tardes": uno("""
            select count(*) from nucleo.viajes
             where empresa_id=%s and created_by='demo' and fin_real is not null
               and fin_real > fin_planificado
        """),
        "prexistentes": uno("""
            select count(*) from nucleo.viajes
             where empresa_id=%s and numero_viaje in
                   ('VJ-2026-200001','VJ-2026-200002','VJ-2026-100001',
                    'VJ-2026-100002','VJ-2026-100003')
        """),
    }


def imprimir_informe(cur: psycopg.Cursor, datos: dict[str, Any]) -> bool:
    print("\n== Conteos del dataset demo ==")
    for clave in (
        "tractos", "ramplas", "choferes", "clientes", "viajes_demo",
        "viajes_total", "facturas", "anulados", "vencidas",
        "incidentes_abiertos", "talleres", "mantenimientos", "precios_diesel",
        "pod", "gastos", "tardes", "solicitud_pendiente",
    ):
        print(f"  {clave:22s} {datos[clave]}")
    print(f"  {'solapes_reservas':22s} {datos['solapes']}")
    print(f"  {'viajes_preexistentes':22s} {datos['prexistentes']} (de 5)")

    print("\n== Consultas de muestra ==")
    for titulo, params, sql in CONSULTAS_MUESTRA:
        consultar(cur, titulo, params, sql)

    print("\n== Criterios de aceptación ==")
    criterios = [
        ("viajes >= 700", datos["viajes_demo"] >= 700),
        ("40 tractos nuevos", datos["tractos"] >= 40),
        ("44 ramplas nuevas", datos["ramplas"] >= 44),
        ("45 choferes nuevos", datos["choferes"] >= 45),
        ("14 clientes nuevos", datos["clientes"] >= 14),
        ("facturas >= 100", datos["facturas"] >= 100),
        ("sin solapes de reservas", datos["solapes"] == 0),
        ("anulados >= 8", datos["anulados"] >= 8),
        ("facturas vencidas >= 8", datos["vencidas"] >= 8),
        ("incidentes abiertos >= 3", datos["incidentes_abiertos"] >= 3),
        ("2 tractos en taller", datos["talleres"] >= 2),
        ("5 viajes preexistentes intactos", datos["prexistentes"] == 5),
        ("solicitud de chat pendiente", datos["solicitud_pendiente"] == 1),
    ]
    ok = True
    for nombre, cumple in criterios:
        print(f"  [{'OK' if cumple else 'FALLA'}] {nombre}")
        ok = ok and cumple
    return ok


# ---------------------------------------------------------------------------
# Ejecución
# ---------------------------------------------------------------------------
def construir_dataset() -> dict[str, Any]:
    rng = random.Random(SEMILLA)
    tractos = construir_tractos()
    ramplas = construir_ramplas()
    choferes = construir_choferes()
    clientes = construir_clientes()
    equipos = construir_equipos(ramplas)
    viajes = planificar_viajes(tractos, ramplas, equipos, rng)
    asignar_estados(viajes, rng)

    # Un viaje con recargo por estadía (y su gasto asociado).
    for v in viajes:
        if v.estado_objetivo in ("cobrado", "facturado") and v.idx > 200:
            v.recargos = 85000
            v.observaciones = "Recargo por estadía en destino (2 días de espera)"
            break

    # 4 POD con daños declarados.
    con_danios = 0
    for v in viajes:
        if v.estado_objetivo in ("cobrado", "facturado") and con_danios < 4:
            if v.idx % 89 == 0:
                v.danios = ("Embalaje deformado en 2 pallets; se deja constancia "
                            "en el POD")
                con_danios += 1

    # 1 viaje cerrado sin POD.
    for v in viajes:
        if v.estado_objetivo == "cerrado":
            v.con_pod = False
            break

    ocs = construir_ocs(clientes)
    asignar_ordenes_compra(viajes, ocs)
    return {
        "tractos": tractos,
        "ramplas": ramplas,
        "choferes": choferes,
        "clientes": clientes,
        "viajes": viajes,
        "tarifas": TARIFAS,
        "ocs": ocs,
    }


def ejecutar(dry_run: bool = False, reset: bool = False) -> int:
    dataset = construir_dataset()
    rng = random.Random(SEMILLA + 3)
    viajes: list[ViajePlan] = dataset["viajes"]
    print(
        f"Plan: {len(viajes)} viajes | {len(dataset['tractos'])} tractos | "
        f"{len(dataset['ramplas'])} ramplas | {len(dataset['choferes'])} choferes | "
        f"{len(dataset['clientes'])} clientes | {len(dataset['ocs'])} OC"
    )
    if dry_run:
        print("Estados objetivo:", Counter(v.estado_objetivo for v in viajes))
        print("Sin OC:", sum(1 for v in viajes if v.oc_idx is None))
        print("Rango:", min(v.inicio for v in viajes), "→",
              max(v.inicio for v in viajes))
        return 0

    conn = psycopg.connect(URL_DEFAULT, autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute("select set_config('nucleo.auth_id', 'demo', true)")
            c = Cargador(cur)
            if reset:
                reset_demo(conn)
            precargar_todo(c)

            cargar_tractos_y_ramplas(c, dataset["tractos"], dataset["ramplas"])
            cargar_choferes_y_clientes(c, dataset["choferes"], dataset["clientes"])
            cargar_documentos(
                c, dataset["tractos"], dataset["ramplas"], dataset["choferes"]
            )
            ocs = cargar_tarifas_y_oc(
                c, dataset["tarifas"], dataset["clientes"], viajes, dataset["ocs"]
            )
            diesel = cargar_diesel(c)
            cargar_viajes(
                c, viajes, dataset["tractos"], dataset["ramplas"],
                dataset["clientes"], ocs, rng,
            )
            normalizar_llegadas(c)
            cargar_gastos(c, viajes, diesel, rng)
            cargar_pod(c, viajes, dataset["clientes"])
            cargar_incidentes(c, viajes)
            cargar_facturacion(c, viajes, dataset["clientes"], ocs)
            cargar_mantenimiento(c, dataset["tractos"], dataset["ramplas"])
            viaje_futuro = cargar_chat_y_config(
                c, dataset["clientes"], dataset["choferes"], viajes
            )

            # Las OC cuyo período ya terminó quedan vencidas (no se fuerza un
            # estado: es el resultado natural de su vigencia).
            cur.execute(
                """
                update nucleo.ordenes_compra
                   set estado = 'vencida'
                 where empresa_id = %s and estado <> 'anulada'
                   and vigencia_hasta < %s
                """,
                (EMPRESA_ID, FECHA_DEMO),
            )

            print("\n== Filas insertadas en este run ==")
            for tabla, cantidad in sorted(c.insertados.items()):
                print(f"  {tabla:24s} {cantidad}")

            datos = verificar(cur)
            if not imprimir_informe(cur, datos):
                raise RuntimeError(
                    "Criterios de aceptación incumplidos: ROLLBACK"
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print("\nCommit OK. Dataset demo cargado.")
    print(f"Solicitud pendiente en /agente/buzon sobre el viaje {viaje_futuro}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Dataset demo TEI (ficticio)")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="planifica y muestra el resumen sin escribir en la base",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="borra SOLO las filas del dataset demo (created_by='demo') y recarga",
    )
    args = parser.parse_args()
    try:
        return ejecutar(dry_run=args.dry_run, reset=args.reset)
    except Exception as exc:  # noqa: BLE001 - script de desarrollo
        print(f"\nERROR en seed demo: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
