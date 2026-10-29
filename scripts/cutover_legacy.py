#!/usr/bin/env python3
"""Cutover legacy `public` → `nucleo` para TRANSTEI.

Migra maestros y viajes abiertos sin tocar el legacy.

Los viajes se migran **sin asignación de recursos** (`tracto_id`, `rampla_id` y
`chofer_id` en NULL) y en estado `confirmado`. Motivo (2026-10-29): desde la
migración 0015, todo viaje con los tres recursos exige el expediente documental
completo en `nucleo`, y el legacy **no tiene** `permiso_circulacion`, `soap`,
`seguro_carga` ni `examen_medico`. Fabricarlos con fechas inventadas sería
falsear cumplimiento documental. La identidad legacy de cada recurso queda
registrada en `observaciones` para que despacho asigne y valide con documentos
reales.

Los viajes ya facturados/cobrados/anulados no se migran.

Uso:
    .venv/bin/python scripts/cutover_legacy.py --dry-run
    .venv/bin/python scripts/cutover_legacy.py --freeze
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from uuid import UUID, uuid4
from decimal import Decimal
from zoneinfo import ZoneInfo

import psycopg

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "backend" / ".env"
DEFAULT_DB = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
ZONA = ZoneInfo("America/Santiago")
ESTADOS_LEGACY_ABIERTOS = {
    "borrador",
    "programado",
    "cotizado",
    "confirmado",
    "asignado",
    "en_carga",
    "cargado",
    "en_ruta",
    "en_descarga",
}


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
    return os.environ.get("DATABASE_URL", DEFAULT_DB).replace(
        "postgresql+psycopg://", "postgresql://"
    )


def normalizar(valor: str) -> str:
    return "".join(c for c in valor.upper() if c.isalnum())


def buscar_id(cur, tabla: str, empresa_id: UUID, columna: str, valor: str) -> UUID | None:
    if columna == "rut":
        cur.execute(
            f"select id from nucleo.{tabla} where empresa_id = %s "
            f"and upper(regexp_replace(rut, '[^0-9K]', '', 'g')) = "
            f"upper(regexp_replace(%s, '[^0-9K]', '', 'g')) limit 1",
            (empresa_id, valor),
        )
    else:
        cur.execute(
            f"select id from nucleo.{tabla} where empresa_id = %s "
            f"and upper(regexp_replace({columna}, '[^A-Z0-9]', '', 'g')) = %s limit 1",
            (empresa_id, normalizar(valor)),
        )
    fila = cur.fetchone()
    return fila[0] if fila else None


def migrar(dry_run: bool, freeze: bool) -> None:
    resumen = {
        "clientes_nuevos": 0,
        "choferes_nuevos": 0,
        "tractos_nuevos": 0,
        "ramplas_nuevas": 0,
        "viajes_migrados": 0,
        "viajes_sin_asignacion": 0,
        "viajes_omitidos": 0,
        "documentos": 0,
    }
    with psycopg.connect(db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("select id from nucleo.empresas where codigo = 'TEI' limit 1")
            fila = cur.fetchone()
            if not fila:
                raise SystemExit("No existe la empresa TEI en nucleo. Ejecute el seed.")
            empresa_id = fila[0]

            cur.execute("select * from public.clientes order by razon_social")
            legacy_clientes = cur.fetchall()
            columnas = [d.name for d in cur.description]
            mapa_clientes: dict[UUID, UUID] = {}
            for fila in legacy_clientes:
                c = dict(zip(columnas, fila))
                existente = buscar_id(cur, "clientes", empresa_id, "rut", c["rut"])
                if existente:
                    mapa_clientes[c["id"]] = existente
                    continue
                nuevo = uuid4()
                if not dry_run:
                    cur.execute(
                        """
                        insert into nucleo.clientes
                          (id, empresa_id, razon_social, rut, giro, dias_pago,
                           contacto_email, contacto_telefono, activo)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            nuevo,
                            empresa_id,
                            c["razon_social"],
                            c["rut"],
                            c.get("giro"),
                            c.get("dias_pago") or 30,
                            c.get("email"),
                            c.get("telefono"),
                            c.get("activo", True),
                        ),
                    )
                    resumen["clientes_nuevos"] += 1
                mapa_clientes[c["id"]] = nuevo

            cur.execute("select * from public.choferes order by nombre")
            filas = cur.fetchall()
            columnas = [d.name for d in cur.description]
            mapa_choferes: dict[UUID, UUID] = {}
            for fila in filas:
                c = dict(zip(columnas, fila))
                existente = buscar_id(cur, "choferes", empresa_id, "rut", c["rut"])
                if existente:
                    mapa_choferes[c["id"]] = existente
                    continue
                nuevo = uuid4()
                if not dry_run:
                    cur.execute(
                        """
                        insert into nucleo.choferes
                          (id, empresa_id, rut, nombre, sueldo_base,
                           porcentaje_comision, activo)
                        values (%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            nuevo,
                            empresa_id,
                            c["rut"],
                            c["nombre"],
                            c.get("sueldo_base") or 0,
                            c.get("porcentaje_produccion") or 0,
                            c.get("activo", True),
                        ),
                    )
                    if c.get("vencimiento_licencia"):
                        cur.execute(
                            """
                            insert into nucleo.documentos
                              (empresa_id, recurso_tipo, chofer_id, tipo, vence_en, es_vigente)
                            values (%s, 'chofer', %s, 'licencia_conducir', %s, true)
                            """,
                            (empresa_id, nuevo, c["vencimiento_licencia"]),
                        )
                        resumen["documentos"] += 1
                    resumen["choferes_nuevos"] += 1
                mapa_choferes[c["id"]] = nuevo

            cur.execute("select * from public.tractos order by patente")
            filas = cur.fetchall()
            columnas = [d.name for d in cur.description]
            mapa_tractos: dict[UUID, UUID] = {}
            for fila in filas:
                c = dict(zip(columnas, fila))
                existente = buscar_id(cur, "tractos", empresa_id, "patente", c["patente"])
                if existente:
                    mapa_tractos[c["id"]] = existente
                    continue
                nuevo = uuid4()
                if not dry_run:
                    cur.execute(
                        """
                        insert into nucleo.tractos
                          (id, empresa_id, patente, marca, modelo, ano, km_actual,
                           peso_bruto_kg, tara_kg, capacidad_carga_kg, activo)
                        values (%s,%s,%s,%s,%s,%s,%s,39000,9000,30000,%s)
                        """,
                        (
                            nuevo,
                            empresa_id,
                            c["patente"],
                            c.get("marca"),
                            c.get("modelo"),
                            c.get("ano"),
                            c.get("km_actual") or 0,
                            c.get("activo", True),
                        ),
                    )
                    for tipo, columna in (
                        ("revision_tecnica", "vencimiento_revision_tecnica"),
                        ("seguro_obligatorio", "vencimiento_seguro"),
                    ):
                        if c.get(columna):
                            cur.execute(
                                """
                                insert into nucleo.documentos
                                  (empresa_id, recurso_tipo, tracto_id, tipo, vence_en, es_vigente)
                                values (%s, 'tracto', %s, %s, %s, true)
                                """,
                                (empresa_id, nuevo, tipo, c[columna]),
                            )
                            resumen["documentos"] += 1
                    resumen["tractos_nuevos"] += 1
                mapa_tractos[c["id"]] = nuevo

            cur.execute("select * from public.ramplas order by patente")
            filas = cur.fetchall()
            columnas = [d.name for d in cur.description]
            mapa_ramplas: dict[UUID, UUID] = {}
            for fila in filas:
                c = dict(zip(columnas, fila))
                existente = buscar_id(cur, "ramplas", empresa_id, "patente", c["patente"])
                if existente:
                    mapa_ramplas[c["id"]] = existente
                    continue
                nuevo = uuid4()
                tipo = c.get("tipo") or "plana"
                if tipo not in {
                    "plana",
                    "sider",
                    "refrigerada",
                    "portacontenedor",
                    "cisterna",
                    "cama_baja",
                    "granelera",
                    "otra",
                }:
                    tipo = "otra"
                if not dry_run:
                    cur.execute(
                        """
                        insert into nucleo.ramplas
                          (id, empresa_id, patente, tipo, capacidad_carga_kg, activo)
                        values (%s,%s,%s,%s,30000,%s)
                        """,
                        (nuevo, empresa_id, c["patente"], tipo, c.get("activo", True)),
                    )
                    if c.get("vencimiento_revision_tecnica"):
                        cur.execute(
                            """
                            insert into nucleo.documentos
                              (empresa_id, recurso_tipo, rampla_id, tipo, vence_en, es_vigente)
                            values (%s, 'rampla', %s, 'revision_tecnica', %s, true)
                            """,
                            (empresa_id, nuevo, c["vencimiento_revision_tecnica"]),
                        )
                        resumen["documentos"] += 1
                    resumen["ramplas_nuevas"] += 1
                mapa_ramplas[c["id"]] = nuevo

            cur.execute("select * from public.viajes order by fecha_inicio")
            filas = cur.fetchall()
            columnas = [d.name for d in cur.description]
            for fila in filas:
                v = dict(zip(columnas, fila))
                if v["estado"] not in ESTADOS_LEGACY_ABIERTOS:
                    continue
                cliente_id = mapa_clientes.get(v["cliente_id"])
                chofer_id = mapa_choferes.get(v["chofer_id"])
                tracto_id = mapa_tractos.get(v["tracto_id"])
                rampla_id = mapa_ramplas.get(v["rampla_id"])
                # Solo el cliente es imprescindible. Los recursos NO se asignan
                # aquí: el legacy no tiene los documentos que exige 0015.
                if not cliente_id:
                    resumen["viajes_omitidos"] += 1
                    continue
                sin_asignacion = not all([chofer_id, tracto_id, rampla_id])
                numero = f"VJ-LEG-{str(v['id'])[:8].upper()}"
                cur.execute(
                    "select 1 from nucleo.viajes where empresa_id=%s and numero_viaje=%s",
                    (empresa_id, numero),
                )
                if cur.fetchone():
                    continue
                inicio = datetime.combine(v["fecha_inicio"], time(8, 0), tzinfo=ZONA)
                fin_fecha = v.get("fecha_fin") or v["fecha_inicio"]
                fin = datetime.combine(fin_fecha, time(18, 0), tzinfo=ZONA)
                if fin <= inicio:
                    fin = inicio + timedelta(hours=8)
                if dry_run:
                    resumen["viajes_migrados"] += 1
                    if sin_asignacion:
                        resumen["viajes_sin_asignacion"] += 1
                    continue
                codigo_tarifa = f"MIG-{str(cliente_id)[:8].upper()}"
                cur.execute(
                    "select id from nucleo.tarifas where empresa_id=%s and cliente_id=%s and codigo=%s",
                    (empresa_id, cliente_id, codigo_tarifa),
                )
                fila_tarifa = cur.fetchone()
                if fila_tarifa:
                    tarifa_id = fila_tarifa[0]
                else:
                    tarifa_id = uuid4()
                    cur.execute(
                        """
                        insert into nucleo.tarifas
                          (id, empresa_id, cliente_id, codigo, nombre, modalidad,
                           vigencia_desde, vigencia_hasta, precio_unitario, activo)
                        values (%s,%s,%s,%s,'Tarifa migrada legacy','viaje',%s,%s,%s,true)
                        """,
                        (
                            tarifa_id,
                            empresa_id,
                            cliente_id,
                            codigo_tarifa,
                            date.today() - timedelta(days=3650),
                            date.today() + timedelta(days=730),
                            v.get("valor_flete_neto") or 0,
                        ),
                    )
                numero_oc = f"MIG-{str(cliente_id)[:8].upper()}"
                cur.execute(
                    "select id from nucleo.ordenes_compra where empresa_id=%s and cliente_id=%s and numero_oc=%s",
                    (empresa_id, cliente_id, numero_oc),
                )
                fila_oc = cur.fetchone()
                if fila_oc:
                    oc_id = fila_oc[0]
                else:
                    oc_id = uuid4()
                    cur.execute(
                        """
                        select coalesce(sum(valor_flete_neto), 0) from public.viajes
                         where cliente_id = %s and estado in
                           ('programado','cotizado','confirmado','asignado',
                            'en_carga','cargado','en_ruta','en_descarga')
                        """,
                        (v["cliente_id"],),
                    )
                    total_cliente = Decimal(str(cur.fetchone()[0] or 0))
                    cur.execute(
                        """
                        insert into nucleo.ordenes_compra
                          (id, empresa_id, cliente_id, numero_oc, vigencia_desde,
                           vigencia_hasta, monto_autorizado, estado)
                        values (%s,%s,%s,%s,%s,%s,%s,'abierta')
                        """,
                        (
                            oc_id,
                            empresa_id,
                            cliente_id,
                            numero_oc,
                            date.today() - timedelta(days=3650),
                            date.today() + timedelta(days=730),
                            max(total_cliente * Decimal("1.2"), Decimal("1000000")),
                        ),
                    )
                cur.execute(
                    """
                    insert into nucleo.viajes
                      (empresa_id, numero_viaje, cliente_id, orden_compra_id, tarifa_id,
                       tracto_id, rampla_id, chofer_id, estado, inicio_planificado,
                       fin_planificado, buffer_minutos, peso_bruto_kg, origen_nombre,
                       destino_nombre, valor_flete_neto, observaciones)
                    values (%s,%s,%s,%s,%s,null,null,null,'confirmado',%s,%s,60,20000,%s,%s,%s,%s)
                    """,
                    (
                        empresa_id,
                        numero,
                        cliente_id,
                        oc_id,
                        tarifa_id,
                        inicio,
                        fin,
                        v["origen"],
                        v["destino"],
                        v.get("valor_flete_neto") or 0,
                        f"Migrado desde legacy {v['id']} (estado {v['estado']}). "
                        f"Recursos legacy: tracto {v.get('tracto_id')}, "
                        f"rampla {v.get('rampla_id')}, chofer {v.get('chofer_id')}. "
                        "Asignación pendiente: el legacy no tiene permiso_circulacion, "
                        "soap, seguro_carga ni examen_medico.",
                    ),
                )
                resumen["viajes_migrados"] += 1
                if sin_asignacion:
                    resumen["viajes_sin_asignacion"] += 1

            if freeze and not dry_run:
                cur.execute(
                    """
                    update nucleo.cutover_control
                       set legacy_escritura_congelada = true,
                           congelada_en = now(),
                           congelada_por = 'cutover_legacy.py',
                           motivo = 'Cutover ejecutado: nucleo es la fuente de verdad',
                           updated_at = now()
                     where id = true
                    """
                )
            if not dry_run:
                conn.commit()

    print("Cutover" + (" (dry-run)" if dry_run else "") + " completado")
    for clave, valor in resumen.items():
        print(f"  {clave}: {valor}")
    if freeze:
        print("  legacy_escritura_congelada: true")
    else:
        print("  legacy_escritura_congelada: sin cambios (use --freeze)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrar legacy public a nucleo")
    parser.add_argument("--dry-run", action="store_true", help="No escribe cambios")
    parser.add_argument("--freeze", action="store_true", help="Congela escritura legacy")
    args = parser.parse_args()
    cargar_env()
    try:
        migrar(dry_run=args.dry_run, freeze=args.freeze)
    except Exception as exc:  # noqa: BLE001 - script operativo
        print(f"ERROR en cutover: {exc}", file=sys.stderr)
        raise
