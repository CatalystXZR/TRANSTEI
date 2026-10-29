#!/usr/bin/env python3
"""Seed local de TEI: Supabase local + schema nucleo + datos legacy mínimos.

Uso:
    .venv/bin/python scripts/seed_local.py

Credenciales locales:
    admin@tei.local / TEI2026!

No usar en producción. Las claves son las de Supabase CLI local.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID

import httpx
import psycopg

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "backend" / ".env"

DEFAULT_SUPABASE_URL = "http://127.0.0.1:54321"
DEFAULT_SERVICE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0."
    "EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"
)
DEFAULT_DB = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


def cargar_env() -> None:
    if not ENV_FILE.exists():
        return
    for linea in ENV_FILE.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip())


def db_url() -> str:
    url = os.environ.get("DATABASE_URL", DEFAULT_DB)
    return url.replace("postgresql+psycopg://", "postgresql://")


def crear_o_obtener_usuario(
    email: str = "admin@tei.local",
    password: str = "TEI2026!",
    nombre: str = "Admin TEI",
) -> UUID:
    supabase_url = os.environ.get("SUPABASE_URL", DEFAULT_SUPABASE_URL).rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", DEFAULT_SERVICE_KEY)
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }
    body = {
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": {"nombre": nombre},
    }

    with httpx.Client(timeout=20.0) as client:
        response = client.post(
            f"{supabase_url}/auth/v1/admin/users", headers=headers, json=body
        )
        if response.status_code in (200, 201):
            return UUID(response.json()["id"])
        if response.status_code not in (409, 422):
            response.raise_for_status()

    with psycopg.connect(db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("select id from auth.users where email = %s", (email,))
            fila = cur.fetchone()
            if not fila:
                raise SystemExit(
                    f"No se pudo crear {email} y no existe en auth.users."
                )
            return fila[0]


USUARIOS = [
    ("admin@tei.local", "Admin TEI", "admin"),
    ("gerente@tei.local", "Gerente TEI", "gerente"),
    ("despacho@tei.local", "Despacho TEI", "despacho"),
    ("contador@tei.local", "Contador TEI", "contador"),
    ("tesoreria@tei.local", "Tesorería TEI", "tesoreria"),
    ("taller@tei.local", "Taller TEI", "taller"),
    ("conductor@tei.local", "Conductor TEI", "conductor"),
    ("auditor@tei.local", "Auditor TEI", "auditor"),
]
ROL_LEGACY = {
    "admin": "admin",
    "gerente": "operacion",
    "despacho": "operacion",
    "contador": "contabilidad",
    "tesoreria": "contabilidad",
    "taller": "operacion",
    "conductor": "operacion",
    "auditor": "operacion",
}


def seed() -> None:
    auth_ids: dict[str, UUID] = {}
    for email, nombre, rol in USUARIOS:
        auth_ids[rol] = crear_o_obtener_usuario(email, "TEI2026!", nombre)
    auth_id = auth_ids["admin"]
    hoy = date.today()
    vence = hoy + timedelta(days=365)
    empresa_id = UUID("11111111-1111-1111-1111-111111111111")
    cliente_ids = [
        UUID("22222222-2222-2222-2222-222222222221"),
        UUID("22222222-2222-2222-2222-222222222222"),
        UUID("22222222-2222-2222-2222-222222222223"),
    ]
    tracto_ids = [
        UUID("33333333-3333-3333-3333-333333333331"),
        UUID("33333333-3333-3333-3333-333333333332"),
        UUID("33333333-3333-3333-3333-333333333333"),
    ]
    rampla_ids = [
        UUID("44444444-4444-4444-4444-444444444441"),
        UUID("44444444-4444-4444-4444-444444444442"),
        UUID("44444444-4444-4444-4444-444444444443"),
    ]
    chofer_ids = [
        UUID("55555555-5555-5555-5555-555555555551"),
        UUID("55555555-5555-5555-5555-555555555552"),
        UUID("55555555-5555-5555-5555-555555555553"),
    ]
    tarifa_ids = [
        UUID("88888888-8888-8888-8888-888888888881"),
        UUID("88888888-8888-8888-8888-888888888882"),
        UUID("88888888-8888-8888-8888-888888888883"),
    ]
    oc_ids = [
        UUID("66666666-6666-6666-6666-666666666661"),
        UUID("66666666-6666-6666-6666-666666666662"),
        UUID("66666666-6666-6666-6666-666666666663"),
    ]

    with psycopg.connect(db_url()) as conn:
        with conn.cursor() as cur:
            # ------------------------------------------------------------------
            # Empresa y usuario
            # ------------------------------------------------------------------
            cur.execute(
                """
                insert into nucleo.empresas
                  (id, codigo, razon_social, rut, giro, ciudad, region,
                   buffer_operacional_min, dias_margen_documentos,
                   dias_alerta_documentos, exigir_soap, exigir_seguro_carga,
                   exigir_curso_carga_peligrosa, exigir_oc, estado)
                values
                  (%s, 'TEI', 'Transportes TEI SpA', '76.123.456-7',
                   'Transporte de carga por carretera', 'Santiago', 'Metropolitana',
                   90, 0, 14, true, true, true, false, 'activa')
                on conflict (id) do update set
                  razon_social = excluded.razon_social,
                  buffer_operacional_min = excluded.buffer_operacional_min,
                  exigir_soap = excluded.exigir_soap,
                  exigir_seguro_carga = excluded.exigir_seguro_carga,
                  updated_at = now()
                """,
                (empresa_id,),
            )
            cur.execute(
                """
                insert into nucleo.usuarios_empresa (empresa_id, auth_id, rol, activo)
                values (%s, %s, 'admin', true)
                on conflict (empresa_id, auth_id) do update set rol = 'admin', activo = true
                """,
                (empresa_id, auth_id),
            )
            for email, nombre, rol in USUARIOS:
                uid = auth_ids[rol]
                cur.execute(
                    """
                    insert into nucleo.usuarios_empresa (empresa_id, auth_id, rol, activo)
                    values (%s, %s, %s, true)
                    on conflict (empresa_id, auth_id)
                    do update set rol = excluded.rol, activo = true
                    """,
                    (empresa_id, uid, rol),
                )
                cur.execute(
                    """
                    insert into public.usuarios (auth_id, nombre, email, rol, activo)
                    values (%s, %s, %s, %s, true)
                    on conflict (auth_id)
                    do update set nombre = excluded.nombre, email = excluded.email,
                                  rol = excluded.rol, activo = true
                    """,
                    (uid, nombre, email, ROL_LEGACY[rol]),
                )
            cur.execute(
                "update nucleo.choferes set auth_id = %s where id = %s",
                (auth_ids["conductor"], chofer_ids[0]),
            )

            # ------------------------------------------------------------------
            # Clientes
            # ------------------------------------------------------------------
            clientes = [
                ("Cliente Norte SpA", "96.111.222-1", True),
                ("Cliente Sur SpA", "96.111.222-2", True),
                ("Cliente Spot Ltda", "96.111.222-3", False),
            ]
            for cid, (nombre, rut, exige_oc) in zip(cliente_ids, clientes):
                cur.execute(
                    """
                    insert into nucleo.clientes
                      (id, empresa_id, razon_social, rut, giro, ciudad,
                       dias_pago, exige_oc, activo)
                    values (%s, %s, %s, %s, 'Comercio', 'Santiago', 30, %s, true)
                    on conflict (id) do update set
                      razon_social = excluded.razon_social,
                      exige_oc = excluded.exige_oc,
                      activo = true
                    """,
                    (cid, empresa_id, nombre, rut, exige_oc),
                )
                cur.execute(
                    """
                    insert into public.clientes (razon_social, rut, giro, dias_pago, activo)
                    values (%s, %s, 'Comercio', 30, true)
                    on conflict (rut) do update set razon_social = excluded.razon_social
                    """,
                    (nombre, rut),
                )

            # ------------------------------------------------------------------
            # Flota y choferes
            # ------------------------------------------------------------------
            tractos = [
                ("BJXY12", "Volvo", "FH 460", 2022),
                ("CKLM34", "Scania", "R 450", 2021),
                ("DRST56", "Mercedes-Benz", "Actros 2645", 2023),
            ]
            for tid, (patente, marca, modelo, ano) in zip(tracto_ids, tractos):
                cur.execute(
                    """
                    insert into nucleo.tractos
                      (id, empresa_id, patente, marca, modelo, ano,
                       peso_bruto_kg, tara_kg, capacidad_carga_kg,
                       licencias_permitidas, estado, activo)
                    values (%s, %s, %s, %s, %s, %s, 39000, 9000, 30000,
                            array['A5'], 'disponible', true)
                    on conflict (id) do update set
                      patente = excluded.patente,
                      marca = excluded.marca,
                      modelo = excluded.modelo,
                      ano = excluded.ano,
                      activo = true
                    """,
                    (tid, empresa_id, patente, marca, modelo, ano),
                )
                cur.execute(
                    """
                    insert into public.tractos
                      (patente, marca, modelo, ano, km_actual,
                       vencimiento_revision_tecnica, vencimiento_seguro, activo)
                    values (%s, %s, %s, %s, 120000, %s, %s, true)
                    on conflict (patente) do update set
                      marca = excluded.marca,
                      modelo = excluded.modelo,
                      vencimiento_revision_tecnica = excluded.vencimiento_revision_tecnica,
                      vencimiento_seguro = excluded.vencimiento_seguro
                    """,
                    (patente, marca, modelo, ano, vence, vence),
                )

            ramplas = [
                ("RPLA01", "plana"),
                ("RPLA02", "sider"),
                ("RPLA03", "plana"),
            ]
            for rid, (patente, tipo) in zip(rampla_ids, ramplas):
                cur.execute(
                    """
                    insert into nucleo.ramplas
                      (id, empresa_id, patente, tipo, capacidad_carga_kg,
                       volumen_m3, estado, activo)
                    values (%s, %s, %s, %s::nucleo.tipo_rampla, 30000, 80,
                            'disponible', true)
                    on conflict (id) do update set
                      patente = excluded.patente,
                      tipo = excluded.tipo,
                      activo = true
                    """,
                    (rid, empresa_id, patente, tipo),
                )
                cur.execute(
                    """
                    insert into public.ramplas
                      (patente, tipo, vencimiento_revision_tecnica, activo)
                    values (%s, %s::tipo_rampla, %s, true)
                    on conflict (patente) do update set
                      vencimiento_revision_tecnica = excluded.vencimiento_revision_tecnica
                    """,
                    (patente, tipo, vence),
                )

            choferes = [
                ("11.111.111-1", "Juan", "Pérez", "A5"),
                ("22.222.222-2", "Luis", "Soto", "A5"),
                ("33.333.333-3", "Pedro", "Rojas", "A5"),
            ]
            for did, (rut, nombre, apellido, clase) in zip(chofer_ids, choferes):
                cur.execute(
                    """
                    insert into nucleo.choferes
                      (id, empresa_id, rut, nombre, apellido_paterno,
                       numero_licencia, licencia_clase, autorizado_carga_peligrosa,
                       estado, activo)
                    values (%s, %s, %s, %s, %s, %s, %s, false, 'disponible', true)
                    on conflict (id) do update set
                      nombre = excluded.nombre,
                      apellido_paterno = excluded.apellido_paterno,
                      licencia_clase = excluded.licencia_clase,
                      activo = true
                    """,
                    (did, empresa_id, rut, nombre, apellido, f"LIC-{rut}", clase),
                )
                cur.execute(
                    """
                    insert into public.choferes
                      (nombre, rut, sueldo_base, porcentaje_produccion,
                       vencimiento_licencia, activo)
                    values (%s, %s, 800000, 0.10, %s, true)
                    on conflict (rut) do update set
                      nombre = excluded.nombre,
                      porcentaje_produccion = excluded.porcentaje_produccion,
                      vencimiento_licencia = excluded.vencimiento_licencia
                    """,
                    (f"{nombre} {apellido}", rut, vence),
                )

            # ------------------------------------------------------------------
            # Documentos (se desactivan los anteriores y se cargan frescos)
            # ------------------------------------------------------------------
            cur.execute(
                """
                update nucleo.documentos set es_vigente = false
                where empresa_id = %s
                  and (tracto_id = any(%s) or rampla_id = any(%s) or chofer_id = any(%s))
                """,
                (empresa_id, tracto_ids, rampla_ids, chofer_ids),
            )
            for tid in tracto_ids:
                for tipo in (
                    "revision_tecnica",
                    "permiso_circulacion",
                    "seguro_obligatorio",
                    "soap",
                ):
                    cur.execute(
                        """
                        insert into nucleo.documentos
                          (empresa_id, recurso_tipo, tracto_id, tipo, vence_en, es_vigente)
                        values (%s, 'tracto', %s, %s::nucleo.tipo_documento, %s, true)
                        """,
                        (empresa_id, tid, tipo, vence),
                    )
            for rid in rampla_ids:
                for tipo in ("revision_tecnica", "permiso_circulacion", "seguro_carga"):
                    cur.execute(
                        """
                        insert into nucleo.documentos
                          (empresa_id, recurso_tipo, rampla_id, tipo, vence_en, es_vigente)
                        values (%s, 'rampla', %s, %s::nucleo.tipo_documento, %s, true)
                        """,
                        (empresa_id, rid, tipo, vence),
                    )
            for did in chofer_ids:
                for tipo in ("licencia_conducir", "examen_medico"):
                    cur.execute(
                        """
                        insert into nucleo.documentos
                          (empresa_id, recurso_tipo, chofer_id, tipo, vence_en, es_vigente)
                        values (%s, 'chofer', %s, %s::nucleo.tipo_documento, %s, true)
                        """,
                        (empresa_id, did, tipo, vence),
                    )

            # ------------------------------------------------------------------
            # Tarifas, OC y viajes de prueba
            # ------------------------------------------------------------------
            rutas = [
                ("T-SCL-CCP", "Santiago", "Concepción", 450000, 0),
                ("T-SCL-TAL", "Santiago", "Talca", 280000, 1),
                ("T-CCP-SCL", "Concepción", "Santiago", 450000, 2),
            ]
            for tfid, (codigo, origen, destino, precio, idx) in zip(
                tarifa_ids, rutas
            ):
                cur.execute(
                    """
                    insert into nucleo.tarifas
                      (id, empresa_id, cliente_id, codigo, nombre, modalidad,
                       origen, destino, vigencia_desde, vigencia_hasta,
                       precio_unitario, activo)
                    values (%s, %s, %s, %s, %s, 'viaje', %s, %s, %s, %s, %s, true)
                    on conflict (id) do update set
                      precio_unitario = excluded.precio_unitario,
                      vigencia_hasta = excluded.vigencia_hasta,
                      activo = true
                    """,
                    (
                        tfid,
                        empresa_id,
                        cliente_ids[idx],
                        codigo,
                        f"{origen} - {destino}",
                        origen,
                        destino,
                        hoy,
                        vence,
                        precio,
                    ),
                )
                cur.execute(
                    """
                    insert into nucleo.ordenes_compra
                      (id, empresa_id, cliente_id, numero_oc, vigencia_desde,
                       vigencia_hasta, monto_autorizado, estado)
                    values (%s, %s, %s, %s, %s, %s, 5000000, 'abierta')
                    on conflict (id) do update set
                      vigencia_hasta = excluded.vigencia_hasta,
                      monto_autorizado = excluded.monto_autorizado
                    """,
                    (
                        oc_ids[idx],
                        empresa_id,
                        cliente_ids[idx],
                        f"OC-{idx + 1:04d}",
                        hoy,
                        vence,
                    ),
                )

            for idx, (origen, destino, precio) in enumerate(
                [
                    ("Santiago", "Concepción", 450000),
                    ("Santiago", "Talca", 280000),
                    ("Concepción", "Santiago", 450000),
                ]
            ):
                cur.execute(
                    """
                    insert into nucleo.viajes
                      (empresa_id, numero_viaje, cliente_id, orden_compra_id,
                       tarifa_id, estado, inicio_planificado, fin_planificado,
                       buffer_minutos, peso_bruto_kg, origen_nombre, destino_nombre,
                       valor_flete_neto, distancia_km)
                    values (%s, %s, %s, %s, %s, 'confirmado', %s, %s, 90, 25000,
                            %s, %s, %s, 500)
                    on conflict (empresa_id, numero_viaje) do nothing
                    """,
                    (
                        empresa_id,
                        f"VJ-2026-10{idx + 1:04d}",
                        cliente_ids[idx],
                        oc_ids[idx],
                        tarifa_ids[idx],
                        f"{hoy + timedelta(days=2 + idx)} 08:00:00-03",
                        f"{hoy + timedelta(days=2 + idx)} 12:00:00-03",
                        origen,
                        destino,
                        precio,
                    ),
                )

            # ------------------------------------------------------------------
            # P0-03 / P0-08 / P0-09: comercial, costos y configuración
            # ------------------------------------------------------------------
            centro_ids = [
                UUID("77777777-7777-7777-7777-777777777771"),
                UUID("77777777-7777-7777-7777-777777777772"),
            ]
            for cid, codigo, nombre in zip(
                centro_ids,
                ["CC-NORTE", "CC-SUR"],
                ["Operaciones norte", "Operaciones sur"],
            ):
                cur.execute(
                    """
                    insert into nucleo.centros_costo (id, empresa_id, codigo, nombre, activo)
                    values (%s, %s, %s, %s, true)
                    on conflict (id) do nothing
                    """,
                    (cid, empresa_id, codigo, nombre),
                )
            cur.execute(
                """
                update nucleo.ordenes_compra
                   set centro_costo_id = %s
                 where empresa_id = %s and centro_costo_id is null
                """,
                (centro_ids[0], empresa_id),
            )

            cur.execute(
                """
                insert into nucleo.configuracion_costos
                  (id, empresa_id, costo_fijo_mensual, viajes_estimados_mes,
                   margen_objetivo, benchmark_margen_km, contribucion_minima,
                   costo_variable_km_estandar, rendimiento_km_l, precio_diesel)
                values (%s, %s, 30000000, 60, 0.25, 1200, 100000, 900, 2.5, 1000)
                on conflict (empresa_id) do nothing
                """,
                (UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1"), empresa_id),
            )
            cur.execute(
                """
                insert into nucleo.precios_diesel
                  (id, empresa_id, fecha, precio_litro, fuente)
                values (%s, %s, %s, 1000, 'Seed local')
                on conflict (empresa_id, fecha) do nothing
                """,
                (UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2"), empresa_id, hoy),
            )

            for idx, (oc_id, precio, origen, destino) in enumerate(
                zip(oc_ids, [450000, 280000, 450000], ["Santiago", "Santiago", "Concepción"], ["Concepción", "Talca", "Santiago"])
            ):
                cur.execute(
                    """
                    insert into nucleo.ordenes_compra_lineas
                      (id, empresa_id, orden_compra_id, numero_linea, descripcion,
                       origen, destino, tarifa_id, centro_costo_id,
                       cantidad_estimada, unidad, precio_unitario, monto_linea)
                    values (%s, %s, %s, 1, %s, %s, %s, %s, %s, 1, 'viaje', %s, %s)
                    on conflict (id) do nothing
                    """,
                    (
                        UUID(f"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb{idx + 1}"),
                        empresa_id,
                        oc_id,
                        f"Flete {origen} - {destino}",
                        origen,
                        destino,
                        tarifa_ids[idx],
                        centro_ids[0],
                        precio,
                        precio,
                    ),
                )

            # ------------------------------------------------------------------
            # P0-04: bloqueos de mantención y descanso
            # ------------------------------------------------------------------
            cur.execute(
                """
                insert into nucleo.reservas_recurso
                  (id, empresa_id, recurso_tipo, tracto_id, ventana, tipo_reserva,
                   motivo, activa, creado_por)
                values (%s, %s, 'tracto', %s,
                        tstzrange(%s::timestamptz, %s::timestamptz, '[)'),
                        'mantenimiento', 'Mantención preventiva 40.000 km', true, 'seed')
                on conflict (id) do nothing
                """,
                (
                    UUID("cccccccc-cccc-cccc-cccc-ccccccccccc1"),
                    empresa_id,
                    tracto_ids[2],
                    f"{hoy + timedelta(days=45)} 08:00:00-03",
                    f"{hoy + timedelta(days=45)} 18:00:00-03",
                ),
            )
            cur.execute(
                """
                insert into nucleo.reservas_recurso
                  (id, empresa_id, recurso_tipo, chofer_id, ventana, tipo_reserva,
                   motivo, activa, creado_por)
                values (%s, %s, 'chofer', %s,
                        tstzrange(%s::timestamptz, %s::timestamptz, '[)'),
                        'descanso', 'Descanso programado', true, 'seed')
                on conflict (id) do nothing
                """,
                (
                    UUID("cccccccc-cccc-cccc-cccc-ccccccccccc2"),
                    empresa_id,
                    chofer_ids[2],
                    f"{hoy + timedelta(days=46)} 00:00:00-03",
                    f"{hoy + timedelta(days=47)} 00:00:00-03",
                ),
            )

            # ------------------------------------------------------------------
            # P0-06 / P0-10: viajes cerrados, POD, gasto, factura y pago
            # ------------------------------------------------------------------
            viaje_cerrado_1 = UUID("dddddddd-dddd-dddd-dddd-ddddddddddd1")
            viaje_cerrado_2 = UUID("dddddddd-dddd-dddd-dddd-ddddddddddd2")
            for vid, numero, hora in (
                (viaje_cerrado_1, "VJ-2026-200001", "08:00:00"),
                (viaje_cerrado_2, "VJ-2026-200002", "13:00:00"),
            ):
                cur.execute(
                    """
                    insert into nucleo.viajes
                      (id, empresa_id, numero_viaje, cliente_id, orden_compra_id, tarifa_id,
                       tracto_id, rampla_id, chofer_id, estado, inicio_planificado,
                       fin_planificado, buffer_minutos, peso_bruto_kg, origen_nombre,
                       destino_nombre, valor_flete_neto, distancia_km, observaciones)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'cerrado',
                            %s::timestamptz, %s::timestamptz, 60, 20000,
                            'Santiago', 'Concepción', 450000, 500,
                            'Viaje histórico del seed para UAT')
                    on conflict (empresa_id, numero_viaje) do nothing
                    """,
                    (
                        vid,
                        empresa_id,
                        numero,
                        cliente_ids[0],
                        oc_ids[0],
                        tarifa_ids[0],
                        tracto_ids[0],
                        rampla_ids[0],
                        chofer_ids[0],
                        f"{hoy} {hora}-03",
                        f"{hoy} {int(hora[:2]) + 4:02d}:00:00-03",
                    ),
                )

            cur.execute(
                """
                insert into nucleo.pod
                  (empresa_id, viaje_id, receptor_nombre, receptor_rut, fecha_hora,
                   firma_url, fotos, observaciones, created_by)
                select %s, id, 'Receptor UAT', '12.345.678-9', now(),
                       'nucleo/seed/firma-demo.png', '[]'::jsonb,
                       'POD de ejemplo del seed', 'seed'
                  from nucleo.viajes where id = %s
                on conflict (viaje_id) do nothing
                """,
                (empresa_id, viaje_cerrado_1),
            )

            cur.execute(
                """
                insert into nucleo.viaje_gastos
                  (id, empresa_id, viaje_id, tipo, proveedor, fecha, monto_total, iva,
                   litros, precio_litro, estado, aprobado_por, aprobado_en, created_by)
                values (%s, %s, %s, 'combustible', 'Copec', %s, 119000, 19000,
                        100, 1000, 'aprobado', 'seed', now(), 'seed')
                on conflict (id) do nothing
                """,
                (
                    UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeee1"),
                    empresa_id,
                    viaje_cerrado_1,
                    hoy,
                ),
            )

            factura_seed = UUID("ffffffff-ffff-ffff-ffff-fffffffffff1")
            cur.execute(
                """
                insert into nucleo.facturas_nucleo
                  (id, empresa_id, numero_factura, cliente_id, orden_compra_id,
                   fecha_emision, fecha_vencimiento, moneda, neto, iva, estado,
                   observaciones, created_by)
                values (%s, %s, 'FAC-2026-900001', %s, %s, %s, %s, 'CLP',
                        450000, 85500, 'emitida', 'Factura de ejemplo del seed', 'seed')
                on conflict (empresa_id, numero_factura) do nothing
                """,
                (
                    factura_seed,
                    empresa_id,
                    cliente_ids[0],
                    oc_ids[0],
                    hoy - timedelta(days=20),
                    hoy + timedelta(days=10),
                ),
            )
            cur.execute(
                """
                insert into nucleo.factura_viajes (empresa_id, factura_id, viaje_id, monto)
                select %s, id, %s, 450000 from nucleo.facturas_nucleo
                 where empresa_id = %s and numero_factura = 'FAC-2026-900001'
                on conflict (empresa_id, viaje_id) do nothing
                """,
                (empresa_id, viaje_cerrado_1, empresa_id),
            )
            cur.execute(
                """
                update nucleo.viajes set estado = 'facturado'
                 where id = %s and estado = 'cerrado'
                """,
                (viaje_cerrado_1,),
            )
            cur.execute(
                """
                insert into nucleo.pagos_nucleo
                  (id, empresa_id, factura_id, fecha, monto, metodo, referencia, created_by)
                values (%s, %s, %s, %s, 100000, 'transferencia', 'SEED-001', 'seed')
                on conflict (id) do nothing
                """,
                (
                    UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeee2"),
                    empresa_id,
                    factura_seed,
                    hoy - timedelta(days=5),
                ),
            )
            cur.execute(
                """
                insert into nucleo.promesas_pago_nucleo
                  (id, empresa_id, factura_id, fecha_prometida, monto, estado, notas, created_by)
                values (%s, %s, %s, %s, 50000, 'pendiente',
                        'Promesa de ejemplo del seed', 'seed')
                on conflict (id) do nothing
                """,
                (
                    UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeee3"),
                    empresa_id,
                    factura_seed,
                    hoy + timedelta(days=5),
                ),
            )
            cur.execute(
                """
                insert into nucleo.viaje_incidentes
                  (empresa_id, viaje_id, tipo, severidad, descripcion, estado,
                   ocurrido_en, reportado_por, resolucion, resuelto_por, resuelto_en)
                select %s, id, 'retraso', 'media', 'Espera en planta de origen',
                       'resuelto', now() - interval '1 day', 'seed',
                       'Se reprogramó la ventana de carga', 'seed', now()
                  from nucleo.viajes where id = %s
                 and not exists (
                   select 1 from nucleo.viaje_incidentes i where i.viaje_id = %s
                 )
                """,
                (empresa_id, viaje_cerrado_2, viaje_cerrado_2),
            )

        conn.commit()

    print("Seed local OK")
    print("  URL frontend: http://localhost:3000")
    print("  API backend:  http://localhost:8000")
    print("  Supabase:     http://127.0.0.1:54321")
    print("  Studio:       http://127.0.0.1:54323")
    print("  Usuarios:     admin@tei.local / gerente@tei.local / despacho@tei.local")
    print("                contador@tei.local / tesoreria@tei.local / taller@tei.local")
    print("                conductor@tei.local / auditor@tei.local")
    print("  Clave:        TEI2026!")
    print(f"  auth_id:      {auth_id}")
    print(f"  empresa_id:   {empresa_id}")


if __name__ == "__main__":
    cargar_env()
    try:
        seed()
    except Exception as exc:  # noqa: BLE001 - script de desarrollo
        print(f"ERROR en seed: {exc}", file=sys.stderr)
        raise
