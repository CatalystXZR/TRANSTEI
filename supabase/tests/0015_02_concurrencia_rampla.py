#!/usr/bin/env python3
"""0015-2 — Concurrencia REAL: dos conexiones, la misma rampla, ventanas solapadas.

Invariante probado
    Ninguna rampla puede tener dos reservas activas solapadas en [inicio, fin).
    Mecanismo: EXCLUDE USING gist (rampla_id WITH =, ventana WITH &&)
    WHERE recurso_tipo = 'rampla' AND activa  (0004:749-752), alimentado por
    trg_viajes_70_reservas -> nucleo.fn_viaje_reservas (0015).

Por qué dos conexiones y no dos llamadas seguidas
    Una prueba secuencial no demuestra nada: el `SELECT` de disponibilidad del
    servicio ve el estado anterior. Aquí la sesión B queda BLOQUEADA por el
    índice de exclusión de la sesión A; al commitear A, B recibe 23P01.
    Ver AGENTS.md §7 y la skill postgres-concurrency §6.

Escenario
    Sesión A: inserta un viaje 'confirmado' con tracto A + rampla 1 + chofer A5 #1
              en la ventana [T, T+2h).  (crea 3 reservas; NO commitea)
    Sesión B: inserta otro viaje 'confirmado' con tracto B + rampla 1 + chofer A5 #4
              en la ventana [T+1h, T+3h).  Solo se solapa la rampla.
              => B se bloquea mientras A no commitea.
    A commitea => B debe fallar con SQLSTATE 23P01 y constraint ex_reserva_rampla.
    Estado final: exactamente 1 reserva activa de rampla en esa ventana.

Uso
    export DATABASE_URL='postgresql://...'   # base LOCAL 127.0.0.1:54322
    python supabase/tests/0015_02_concurrencia_rampla.py

    No se imprime la cadena de conexión. Requiere fixtures_0015_0016.sql.

Limpieza
    El viaje de la sesión A queda COMMITEADO (no se puede borrar: un viaje
    confirmado con recursos está protegido por fn_viaje_proteccion y por
    fk_reserva_viaje). Para limpiar la base local desechable:
        psql "$DATABASE_URL" -c "set nucleo.test_cleanup='si'" \
             -f supabase/tests/99_limpieza_viajes_prueba.sql
"""

from __future__ import annotations

import os
import random
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    print("FALLO: falta psycopg (use el .venv del backend)", file=sys.stderr)
    raise SystemExit(2)

EMPRESA = "00000015-0000-4000-8000-000000000001"
CLIENTE = "00000015-0000-4000-8000-000000000002"
TRACTO_A = "00000015-0000-4000-8000-000000000003"
TRACTO_B = "00000015-0000-4000-8000-000000000004"
RAMPLA = "00000015-0000-4000-8000-000000000005"
CHOFER_A = "00000015-0000-4000-8000-000000000007"
CHOFER_B = "00000015-0000-4000-8000-00000000000e"
TARIFA = "00000015-0000-4000-8000-00000000000b"

INSERT_VIAJE = """
insert into nucleo.viajes (
  id, empresa_id, numero_viaje, cliente_id, tarifa_id,
  tracto_id, rampla_id, chofer_id, estado,
  inicio_planificado, fin_planificado, buffer_minutos, peso_bruto_kg,
  origen_nombre, destino_nombre, valor_flete_neto
) values (
  %(id)s, %(empresa)s, %(numero)s, %(cliente)s, %(tarifa)s,
  %(tracto)s, %(rampla)s, %(chofer)s, 'confirmado',
  %(inicio)s, %(fin)s, 0, 20000,
  'Santiago', 'Los Andes', 90000
)
"""


def dsn() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        print(
            "FALLO: defina NUCLEO_TEST_DATABASE_URL o DATABASE_URL "
            "(base local 127.0.0.1:54322). No se imprime la cadena.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return url


def fallo(mensaje: str) -> None:
    print(f"FALLO 0015-2: {mensaje}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    sufijo = uuid.uuid4().hex[:8]
    # Ventana lejana y aleatoria: permite re-ejecutar sin limpiar entre corridas.
    base = datetime.now(timezone.utc) + timedelta(
        days=900, minutes=random.randint(0, 200_000)
    )
    inicio_a = base.replace(second=0, microsecond=0)
    fin_a = inicio_a + timedelta(hours=2)
    inicio_b = inicio_a + timedelta(hours=1)  # solape parcial [T+1h, T+3h)
    fin_b = inicio_a + timedelta(hours=3)

    viaje_a = str(uuid.uuid4())
    viaje_b = str(uuid.uuid4())

    resultado: dict[str, object] = {}

    conn_a = psycopg.connect(dsn(), autocommit=False)
    conn_b = psycopg.connect(dsn(), autocommit=False)
    try:
        # --- Sesión A: reserva la rampla y NO commitea ---------------------
        with conn_a.cursor() as cur:
            cur.execute(
                INSERT_VIAJE,
                {
                    "id": viaje_a,
                    "empresa": EMPRESA,
                    "numero": f"TST15-CONC-{sufijo}-A",
                    "cliente": CLIENTE,
                    "tarifa": TARIFA,
                    "tracto": TRACTO_A,
                    "rampla": RAMPLA,
                    "chofer": CHOFER_A,
                    "inicio": inicio_a,
                    "fin": fin_a,
                },
            )
            cur.execute(
                "select count(*) from nucleo.reservas_recurso "
                "where viaje_id = %s and activa",
                (viaje_a,),
            )
            n = cur.fetchone()[0]
        if n != 3:
            fallo(f"la sesión A debía crear 3 reservas, creó {n}")

        # --- Sesión B: mismo recurso, ventana solapada, en otro hilo -------
        empezado = threading.Event()

        def sesion_b() -> None:
            try:
                with conn_b.cursor() as cur:
                    empezado.set()
                    cur.execute(
                        INSERT_VIAJE,
                        {
                            "id": viaje_b,
                            "empresa": EMPRESA,
                            "numero": f"TST15-CONC-{sufijo}-B",
                            "cliente": CLIENTE,
                            "tarifa": TARIFA,
                            "tracto": TRACTO_B,
                            "rampla": RAMPLA,
                            "chofer": CHOFER_B,
                            "inicio": inicio_b,
                            "fin": fin_b,
                        },
                    )
                resultado["error"] = None
            except Exception as exc:  # noqa: BLE001 - se inspecciona el SQLSTATE
                resultado["error"] = exc

        hilo = threading.Thread(target=sesion_b, name="sesion-b", daemon=True)
        hilo.start()
        empezado.wait(timeout=5)

        time.sleep(1.5)
        if not hilo.is_alive():
            detalle = resultado.get("error")
            fallo(
                "la sesión B NO quedó bloqueada; terminó antes del commit de A. "
                f"Detalle: {detalle!r}"
            )
        print("OK 0015-2 paso 1: la sesión B quedó BLOQUEADA por la reserva de A")

        # --- A commitea: el libro queda ocupado ---------------------------
        conn_a.commit()
        hilo.join(timeout=15)
        if hilo.is_alive():
            fallo("la sesión B no terminó después del commit de A (posible deadlock)")

        error = resultado.get("error")
        if error is None:
            fallo("la sesión B fue ACEPTADA: dos viajes ocupan la misma rampla")

        sqlstate = getattr(error, "sqlstate", None) or getattr(error, "pgcode", None)
        diag = getattr(error, "diag", None)
        constraint = getattr(diag, "constraint_name", None)
        if sqlstate != "23P01":
            fallo(f"se esperaba SQLSTATE 23P01, llegó {sqlstate}: {error}")
        if constraint != "ex_reserva_rampla":
            fallo(
                "se esperaba la constraint ex_reserva_rampla, "
                f"llegó {constraint!r} (¿se solapó otro recurso?)"
            )
        print(f"OK 0015-2 paso 2: la sesión B fue rechazada con 23P01 ({constraint})")

        conn_b.rollback()

        # --- Estado final: una sola reserva activa de esa rampla ----------
        with conn_a.cursor() as cur:
            cur.execute(
                """
                select count(*)
                  from nucleo.reservas_recurso r
                 where r.activa
                   and r.recurso_tipo = 'rampla'
                   and r.rampla_id = %s
                   and r.ventana && tstzrange(%s, %s, '[)')
                """,
                (RAMPLA, inicio_a, fin_b),
            )
            activas = cur.fetchone()[0]
        if activas != 1:
            fallo(f"se esperaba 1 reserva activa de rampla en la ventana, hay {activas}")

        print("OK 0015-2 paso 3: 1 sola reserva activa; el perdedor no dejó filas")
        print(f"     viaje A commiteado: {viaje_a} (limpiar con 99_limpieza_viajes_prueba.sql)")
    finally:
        conn_a.close()
        conn_b.close()

    print("0015_02_concurrencia_rampla: OK")


if __name__ == "__main__":
    main()
