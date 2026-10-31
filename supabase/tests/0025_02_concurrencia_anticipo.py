#!/usr/bin/env python3
"""0025-2 — Concurrencia REAL de la nómina del núcleo (INV-LIQ02 / INV-LIQ03).

Invariantes probados (migración 0025)
    C1  INV-LIQ03: dos conexiones intentan descontar el MISMO anticipo a la vez
        con el patrón correcto (`... where liquidacion_id is null`). La fila se
        serializa por lock y, en READ COMMITTED, la segunda reevalúa el WHERE
        sobre la versión ya confirmada: exactamente una actualiza 1 fila y la
        otra 0. Resultado exigido: **una** imputación y `row_count` total = 1.
        (No hay dos destinos legales para el mismo anticipo: `UNIQUE (empresa_id,
        chofer_id, mes)` + "el mes debe coincidir" dejan una sola liquidación
        posible; el rechazo de un destino distinto es secuencial, 0025_01.)
    C2  INV-LIQ02: una conexión emite la liquidación mientras otra edita el
        monto. Son excluyentes: o la edición entra antes (la emisión congela el
        valor nuevo) o la emisión gana y la edición recibe 23514. Lo prohibido
        es un estado commiteado `emitida` con un monto que no es el emitido.

Por qué dos conexiones
    Una prueba secuencial no demuestra nada: el perdedor vería el estado ya
    confirmado. Cada hilo abre SU PROPIA conexión, esperan en una
    `threading.Barrier` y recién entonces ejecutan (AGENTS.md §7).

Rol
    Corre como `tei_app` (sin BYPASSRLS), el rol real de la aplicación: es el
    único con INSERT/UPDATE sobre las tablas de nómina (0025 no otorga escritura
    a `postgres`). Cada conexión fija `app.empresa_id`; si faltara, RLS daría 0
    filas y el test lo reporta como fallo de entorno, no como defecto.

Datos y limpieza
    Crea 1 liquidación y 1 anticipo de un chofer de TEI con mes `2099-01`
    (imposible de chocar con datos reales) y los elimina al final con TRUNCATE
    de las 3 tablas de nómina (los triggers de fila no disparan en TRUNCATE y
    la base de test es desechable). No toca `nucleo.auditoria` (append-only).

Uso
    export NUCLEO_TEST_DATABASE_URL='postgresql://...@127.0.0.1:54322/tei_test'
    # o DATABASE_URL; sin variable usa la credencial local del Makefile.
    .venv/bin/python supabase/tests/0025_02_concurrencia_anticipo.py
"""

from __future__ import annotations

import os
import sys
import threading
from typing import Any

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    print("FALLO 0025-2: falta psycopg (use el .venv del backend)", file=sys.stderr)
    raise SystemExit(2)

DSN_LOCAL = "postgresql://tei_app:tei_app@127.0.0.1:54322/tei_test"
EMPRESA_TEI = "11111111-1111-1111-1111-111111111111"
MES = "2099-01"


def dsn() -> str:
    url = (
        os.environ.get("NUCLEO_DATABASE_URL")
        or os.environ.get("NUCLEO_TEST_DATABASE_URL")
        or DSN_LOCAL
    )
    return url.replace("postgresql+psycopg://", "postgresql://")


def conectar() -> psycopg.Connection:
    """Conexión nueva con el tenant fijado a nivel de sesión (rol tei_app)."""
    conn = psycopg.connect(dsn(), autocommit=False)
    with conn.cursor() as cur:
        cur.execute("select set_config('app.empresa_id', %s, false)", (EMPRESA_TEI,))
    conn.commit()
    return conn


def fallo(mensaje: str) -> None:
    print(f"FALLO 0025-2: {mensaje}", file=sys.stderr)
    raise SystemExit(1)


def sqlstate(exc: BaseException) -> str | None:
    return getattr(exc, "sqlstate", None) or getattr(exc, "pgcode", None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def preparar(ctl: psycopg.Connection) -> tuple[str, str]:
    with ctl.cursor() as cur:
        cur.execute(
            "select current_user, rolbypassrls from pg_roles where rolname = current_user"
        )
        fila = cur.fetchone()
        if not fila or fila[0] != "tei_app" or fila[1]:
            fallo(
                "ENTORNO: se exige el rol tei_app sin BYPASSRLS (el único con "
                "escritura en la nómina). Use NUCLEO_DATABASE_URL del Makefile."
            )

        cur.execute(
            "select id from nucleo.choferes where empresa_id = %s order by rut limit 1",
            (EMPRESA_TEI,),
        )
        chofer = cur.fetchone()
        if not chofer:
            fallo("no hay choferes de TEI en la base de prueba")
        chofer_id = str(chofer[0])

        # La base es desechable, pero si quedó una corrida anterior (mes 2099-01)
        # el test no puede distinguirla de la nueva: se exige estado limpio.
        cur.execute(
            "select count(*) from nucleo.liquidaciones "
            " where empresa_id = %s and mes = %s",
            (EMPRESA_TEI, MES),
        )
        if cur.fetchone()[0] != 0:
            fallo(
                "ENTORNO: quedaron fixtures de una corrida anterior (mes 2099-01). "
                "Limpie con: docker exec supabase_db_TRANSTEI psql -U supabase_admin "
                "-d tei_test -c 'truncate nucleo.ajustes_liquidacion, "
                "nucleo.anticipos_chofer, nucleo.liquidaciones'"
            )

        cur.execute(
            """
            insert into nucleo.liquidaciones
              (empresa_id, chofer_id, mes, sueldo_base, comision)
            values (%s, %s, %s, 400000, 180000)
            returning id
            """,
            (EMPRESA_TEI, chofer_id, MES),
        )
        liq = str(cur.fetchone()[0])
        cur.execute(
            """
            insert into nucleo.anticipos_chofer
              (empresa_id, chofer_id, monto, mes_imputacion)
            values (%s, %s, 150000, %s)
            returning id
            """,
            (EMPRESA_TEI, chofer_id, MES),
        )
        ant = str(cur.fetchone()[0])
    ctl.commit()
    return liq, ant


def limpiar(ctl: psycopg.Connection) -> None:
    """Limpieza best-effort.

    `postgres` no es dueño de las tablas (las crea supabase_admin) y TRUNCATE
    exige ser dueño: si falla por privilegio no se considera un fallo del test,
    se imprime el comando a ejecutar. TRUNCATE no dispara los triggers de fila.
    """
    with ctl.cursor() as cur:
        for tabla in ("nucleo.ajustes_liquidacion", "nucleo.anticipos_chofer",
                      "nucleo.liquidaciones"):
            cur.execute(f"select count(*) from {tabla}")
            print(f"0025-2: filas en {tabla} antes de limpiar: {cur.fetchone()[0]}")
        try:
            cur.execute(
                "truncate nucleo.ajustes_liquidacion, nucleo.anticipos_chofer, "
                "nucleo.liquidaciones"
            )
        except psycopg.errors.InsufficientPrivilege:
            ctl.rollback()
            print(
                "AVISO 0025-2: sin privilegio TRUNCATE (el dueño es supabase_admin). "
                "Limpie con: docker exec supabase_db_TRANSTEI psql -U supabase_admin "
                "-d tei_test -c 'truncate nucleo.ajustes_liquidacion, "
                "nucleo.anticipos_chofer, nucleo.liquidaciones'"
            )
            return
    ctl.commit()
    print("0025-2: fixtures eliminadas (0 filas en las 3 tablas de nómina)")


# ---------------------------------------------------------------------------
# C1 — el mismo anticipo, dos escritores a la vez
# ---------------------------------------------------------------------------
def caso_c1(liq: str, ant: str) -> None:
    barrera = threading.Barrier(2)
    resultados: list[dict[str, Any]] = []
    candado = threading.Lock()

    def trabajador(nombre: str) -> None:
        info: dict[str, Any] = {"hilo": nombre, "error": None,
                                "sqlstate": None, "filas": 0}
        try:
            with conectar() as conn, conn.cursor() as cur:
                barrera.wait(timeout=10)
                cur.execute(
                    "update nucleo.anticipos_chofer "
                    "set liquidacion_id = %s, estado = 'descontado' "
                    "where id = %s and liquidacion_id is null",
                    (liq, ant),
                )
                info["filas"] = cur.rowcount
                conn.commit()
        except Exception as exc:  # noqa: BLE001 - se reporta el SQLSTATE
            info["error"] = str(exc).strip().splitlines()[0]
            info["sqlstate"] = sqlstate(exc)
        with candado:
            resultados.append(info)

    hilos = [threading.Thread(target=trabajador, args=(f"C1-{i}",)) for i in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)

    for r in resultados:
        print(f"0025-2 C1 {r['hilo']}: filas={r['filas']} error={r['error']}")

    total_filas = sum(r["filas"] for r in resultados)
    errores = [r for r in resultados if r["error"]]
    if errores:
        fallo(f"C1: la escritura idempotente no debe fallar ({errores})")
    if total_filas != 1:
        fallo(f"C1: se esperaba exactamente 1 fila imputada, hubo {total_filas}")
    if sorted(r["filas"] for r in resultados) != [0, 1]:
        fallo(f"C1: se esperaba un ganador (1) y un perdedor (0): {resultados}")

    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            "select liquidacion_id::text, estado "
            "  from nucleo.anticipos_chofer where id = %s",
            (ant,),
        )
        liq_final, estado = cur.fetchone()
    if str(liq_final) != liq or estado != "descontado":
        fallo(f"C1: estado final inesperado: liq={liq_final} estado={estado}")
    print("OK 0025-2 C1: dos conexiones, una sola imputación (row_count total = 1)")


# ---------------------------------------------------------------------------
# C2 — emisión vs edición del monto
# ---------------------------------------------------------------------------
def caso_c2(liq: str) -> None:
    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            "select total_liquido from nucleo.liquidaciones where id = %s", (liq,)
        )
        total_inicial = cur.fetchone()[0]

    barrera = threading.Barrier(2)
    resultados: list[dict[str, Any]] = []
    candado = threading.Lock()

    def emitir() -> None:
        info: dict[str, Any] = {"op": "emitir", "error": None, "sqlstate": None}
        try:
            with conectar() as conn, conn.cursor() as cur:
                barrera.wait(timeout=10)
                cur.execute(
                    "update nucleo.liquidaciones set estado = 'emitida' where id = %s",
                    (liq,),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            info["error"] = str(exc).strip().splitlines()[0]
            info["sqlstate"] = sqlstate(exc)
        with candado:
            resultados.append(info)

    def editar() -> None:
        info: dict[str, Any] = {"op": "editar", "error": None, "sqlstate": None}
        try:
            with conectar() as conn, conn.cursor() as cur:
                barrera.wait(timeout=10)
                cur.execute(
                    "update nucleo.liquidaciones set comision = comision + 1000 "
                    "where id = %s",
                    (liq,),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            info["error"] = str(exc).strip().splitlines()[0]
            info["sqlstate"] = sqlstate(exc)
        with candado:
            resultados.append(info)

    hilos = [threading.Thread(target=emitir), threading.Thread(target=editar)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)

    for r in resultados:
        print(f"0025-2 C2 {r['op']}: error={r['error']} sqlstate={r['sqlstate']}")

    with conectar() as conn, conn.cursor() as cur:
        cur.execute(
            "select estado, comision, total_liquido, emitida_en is not null "
            "  from nucleo.liquidaciones where id = %s",
            (liq,),
        )
        estado, comision, total, sellada = cur.fetchone()

    if estado != "emitida":
        fallo(f"C2: la liquidación no quedó emitida (estado={estado})")
    if not sellada:
        fallo("C2: emitida sin emitida_en")
    if total != total_inicial + (comision - 180000):
        fallo(f"C2: total_liquido {total} no cuadra con la comisión {comision}")
    if comision not in (180000, 181000):
        fallo(f"C2: comisión final inesperada {comision}")

    errores = [r for r in resultados if r["error"]]
    if len(errores) > 1:
        fallo(f"C2: no pueden fallar las dos operaciones ({errores})")
    if errores:
        if errores[0]["sqlstate"] != "23514":
            fallo(f"C2: el perdedor debe fallar con 23514, no {errores[0]['sqlstate']}")
        if comision != 180000:
            fallo("C2: la edición falló pero la comisión cambió")
        print("OK 0025-2 C2: emisión ganó; la edición posterior => 23514")
    else:
        print("OK 0025-2 C2: la edición entró antes; la emisión congeló el valor nuevo")


def main() -> int:
    with conectar() as ctl:
        liq, ant = preparar(ctl)
    print(f"0025-2: fixtures listas (liquidación {liq}, anticipo {ant})")

    caso_c1(liq, ant)
    caso_c2(liq)

    with conectar() as ctl:
        limpiar(ctl)
    print("0025_02: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
