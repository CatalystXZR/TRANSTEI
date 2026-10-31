#!/usr/bin/env python3
"""0021-2 — Concurrencia REAL del módulo agente (tarea O1.2).

Invariantes probados (migración 0021; plan O1.2)
    C1  R-04 / D-16: `nucleo.obtener_siguiente_id_comercial_flete` entrega un
        código DISTINTO y consecutivo a N transacciones concurrentes sobre el
        mismo (empresa, cliente). El lock de fila del `INSERT ... ON CONFLICT DO
        UPDATE` (0021:628-632) serializa; sin él dos transacciones leerían el
        mismo `ultimo`. Salida esperada: N códigos `PREFIJO-00001..N`, sin
        duplicados ni saltos, todos commiteados.
        C1b (control): un ROLLBACK no consume número (0021:599-601): la
        siguiente llamada repite el código no publicado. Si C1b fallara, "sin
        saltos en commits exitosos" no distinguiría rollback de hueco real.
    C2  D-10: dos aprobadores deciden la MISMA solicitud pendiente.
        C2a con filtro `and estado='pendiente'`: exactamente una fila actualizada;
            la otra conexión obtiene 0 filas (nunca dos aprobaciones).
        C2b sin filtro de estado: el trigger `trg_solicitudes_10_transicion`
            (fn_solicitud_transicion, 0021:458-483) rechaza al perdedor con
            23514 porque la decisión es definitiva.
    C3  Idempotencia del webhook (0021:346-347): dos conexiones insertan el mismo
        `wa_message_id`; una gana y la otra recibe 23505 por
        `uq_mensaje_wa_message_id`. Nunca entran dos mensajes con el mismo id.

Por qué dos conexiones y no dos llamadas seguidas
    Una prueba secuencial no demuestra nada: el perdedor vería el estado ya
    confirmado. Aquí cada hilo abre SU PROPIA conexión, todas esperan en una
    `threading.Barrier` y recién entonces ejecutan. En C1 las transacciones se
    bloquean en la fila del contador; en C2 en la fila de la solicitud; en C3 en
    la entrada del índice único. El commit del ganador libera al perdedor con el
    error esperado (AGENTS.md §7; skill postgres-concurrency §6).

Rol
    Corre como `postgres` local (BYPASSRLS) igual que 0015_02: aquí se prueba la
    mecánica de concurrencia, no RLS (eso es 0021_03). El script aborta si el rol
    no tiene BYPASSRLS para no confundir un 42501 de RLS con un defecto.

Datos y limpieza
    - C1 usa un (empresa, cliente) SIN contador previo ⇒ el primer código es
      necesariamente 00001. Al final borra la fila del contador (commit) para
      devolver la precondición "sin contador" a la base desechable.
    - C2/C3 crean contacto/conversación/solicitud con teléfonos aleatorios,
      commitean lo mínimo para que la otra conexión lo vea y lo BORRAN al final
      (orden de FKs). Se verifica 0 filas residuales de negocio.
    - Los triggers `fn_auditoria` dejan filas en `nucleo.auditoria`, append-only
      por diseño (0004:880-892): no se pueden borrar y NO se borran. El script
      informa el conteo. Mismo criterio que 0015_02 (viaje commiteado + auditoría).

Uso
    export NUCLEO_TEST_DATABASE_URL='postgresql://...@127.0.0.1:54322/tei_test'
    # o DATABASE_URL; sin variable usa la credencial local documentada en el
    # Makefile (base desechable tei_test). Nunca se imprime la cadena.
    .venv/bin/python supabase/tests/0021_02_concurrencia_id_comercial.py

    Salida: una línea 'OK 0021-2 ...' por aserción y '0021_02...: OK' al final.
    Código de salida 0 = todas pasaron; 1 = fallo; 2 = entorno.
"""

from __future__ import annotations

import os
import re
import sys
import threading
import time
import uuid
from typing import Any

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    print("FALLO 0021-2: falta psycopg (use el .venv del backend)", file=sys.stderr)
    raise SystemExit(2)

# Credencial local documentada en el Makefile (DB_URL_TEST). Base DESECHABLE.
DSN_LOCAL = "postgresql://postgres:postgres@127.0.0.1:54322/tei_test"

EMPRESA_A = "11111111-1111-1111-1111-111111111111"
CLIENTE_PREFERIDO = "22222222-2222-2222-2222-222222222221"  # cliente A1 del clon

PREFIJO = "SQM"
N_HILOS = 8


def dsn() -> str:
    """DSN de la base de test; acepta el formato SQLAlchemy del Makefile."""
    url = (
        os.environ.get("NUCLEO_TEST_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or DSN_LOCAL
    )
    return url.replace("postgresql+psycopg://", "postgresql://")


def conectar() -> psycopg.Connection:
    return psycopg.connect(dsn(), autocommit=False)


def fallo(mensaje: str) -> None:
    print(f"FALLO 0021-2: {mensaje}", file=sys.stderr)
    raise SystemExit(1)


def sqlstate(exc: BaseException) -> str | None:
    return getattr(exc, "sqlstate", None) or getattr(exc, "pgcode", None)


def telefono_aleatorio() -> str:
    """E.164 chileno válido y distinto en cada corrida (uq_contactos_telefono_activo)."""
    return "+569" + f"{int(uuid.uuid4().hex[:12], 16) % 100_000_000:08d}"


# ---------------------------------------------------------------------------
# C1 — N conexiones piden el siguiente ID comercial a la vez
# ---------------------------------------------------------------------------
def caso_c1(
    ctl: psycopg.Connection,
    reserva: dict[str, tuple[str, str]],
) -> tuple[str, str]:
    with ctl.cursor() as cur:
        cur.execute(
            """
            select c.empresa_id, c.id
              from nucleo.clientes c
              left join nucleo.id_comercial_contador k
                     on k.empresa_id = c.empresa_id and k.cliente_id = c.id
             where k.cliente_id is null
             order by (c.id = %s) desc, c.empresa_id, c.id
             limit 1
            """,
            (CLIENTE_PREFERIDO,),
        )
        fila = cur.fetchone()
        if fila is None:
            fallo(
                "no hay ningún (empresa, cliente) sin contador previo: no se puede "
                "afirmar 'consecutivo desde 00001' sin inventar el estado"
            )
        empresa, cliente = fila
        cur.execute(
            "select count(*) from nucleo.id_comercial_contador "
            "where empresa_id = %s and cliente_id = %s",
            (empresa, cliente),
        )
        if cur.fetchone()[0] != 0:
            fallo("el par elegido ya tenía contador: la precondición de 00001 no se cumple")

    # Se registra ANTES de la parte concurrente: si C1 falla, el finally de main
    # todavía puede borrar el contador que hayan dejado las transacciones.
    reserva["par"] = (str(empresa), str(cliente))

    barrera = threading.Barrier(N_HILOS, timeout=20)
    resultados: dict[int, Any] = {}
    entradas: dict[int, float] = {}
    salidas: dict[int, float] = {}

    def trabajador(i: int) -> None:
        try:
            conn = conectar()
        except Exception as exc:  # noqa: BLE001
            resultados[i] = exc
            barrera.abort()
            return
        try:
            with conn.cursor() as cur:
                # Todas las conexiones ya están abiertas y esperan juntas: ninguna
                # llamada a la función ocurre antes de que las N estén vivas.
                barrera.wait()
                entradas[i] = time.monotonic()
                cur.execute(
                    "select nucleo.obtener_siguiente_id_comercial_flete(%s, %s, %s)",
                    (empresa, cliente, PREFIJO),
                )
                resultados[i] = cur.fetchone()[0]
                salidas[i] = time.monotonic()
            conn.commit()
        except Exception as exc:  # noqa: BLE001 - se inspecciona el SQLSTATE
            resultados[i] = exc
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
        finally:
            conn.close()

    hilos = [
        threading.Thread(target=trabajador, args=(i,), name=f"c1-{i}", daemon=True)
        for i in range(N_HILOS)
    ]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=60)
    if any(h.is_alive() for h in hilos):
        fallo("C1: algún hilo no terminó (posible deadlock en el contador)")

    faltan = [i for i in range(N_HILOS) if i not in resultados]
    if faltan:
        fallo(f"C1: hilos sin resultado (¿barrera rota?): {faltan}")

    errores = {i: r for i, r in resultados.items() if isinstance(r, BaseException)}
    if errores:
        detalle = "; ".join(f"hilo {i}: {sqlstate(e)} {e}" for i, e in errores.items())
        fallo(f"C1: hubo transacciones fallidas y todas debían commitear: {detalle}")

    codigos = [resultados[i] for i in range(N_HILOS)]
    patron = re.compile(rf"^{PREFIJO}-[0-9]{{5}}$")
    malos = [c for c in codigos if not (isinstance(c, str) and patron.match(c))]
    if malos:
        fallo(f"C1: códigos con formato distinto de {PREFIJO}-00001: {malos!r}")

    numeros = sorted(int(c.split("-")[1]) for c in codigos)
    esperados = list(range(1, N_HILOS + 1))
    if numeros != esperados:
        fallo(f"C1: se esperaban consecutivos {esperados}, llegaron {numeros}")
    if len(set(codigos)) != N_HILOS:
        fallo(f"C1: códigos duplicados entre conexiones: {sorted(codigos)}")

    with ctl.cursor() as cur:
        cur.execute(
            "select ultimo from nucleo.id_comercial_contador "
            "where empresa_id = %s and cliente_id = %s",
            (empresa, cliente),
        )
        ultimo = cur.fetchone()[0]
    if ultimo != N_HILOS:
        fallo(f"C1: el contador quedó en {ultimo}, se esperaba {N_HILOS}")

    print(
        f"OK 0021-2 C1: {N_HILOS} conexiones simultáneas (barrera) obtuvieron "
        f"{PREFIJO}-00001..{PREFIJO}-{N_HILOS:05d}, sin duplicados ni saltos; "
        f"contador={ultimo}"
    )
    print(
        "     C1 evidencia de simultaneidad: "
        f"{len(entradas)} hilos entraron a la función entre "
        f"{min(entradas.values()):.3f}s y {max(entradas.values()):.3f}s "
        f"(reloj monotónico), salidas hasta {max(salidas.values()):.3f}s"
    )

    # --- C1b: ROLLBACK no consume número -----------------------------------
    conn = conectar()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select nucleo.obtener_siguiente_id_comercial_flete(%s, %s, %s)",
                (empresa, cliente, PREFIJO),
            )
            cod_rollback = cur.fetchone()[0]
        conn.rollback()  # número nunca publicado
        with conn.cursor() as cur:
            cur.execute(
                "select nucleo.obtener_siguiente_id_comercial_flete(%s, %s, %s)",
                (empresa, cliente, PREFIJO),
            )
            cod_siguiente = cur.fetchone()[0]
        conn.rollback()
    finally:
        conn.close()

    esperado_rollback = f"{PREFIJO}-{N_HILOS + 1:05d}"
    if cod_rollback != esperado_rollback:
        fallo(f"C1b: tras el rollback se esperaba {esperado_rollback}, llegó {cod_rollback}")
    if cod_siguiente != cod_rollback:
        fallo(
            "C1b: el ROLLBACK consumió número "
            f"({cod_rollback} no se repitió; la siguiente fue {cod_siguiente}): "
            "eso convierte cada reintento en un salto"
        )
    print(
        f"OK 0021-2 C1b: el número {cod_rollback} se repitió tras ROLLBACK "
        "(un rollback no deja hueco)"
    )
    return str(empresa), str(cliente)


# ---------------------------------------------------------------------------
# C2 — dos conexiones deciden la misma solicitud
# ---------------------------------------------------------------------------
def _nueva_solicitud(conn: psycopg.Connection, contacto: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into nucleo.solicitudes (empresa_id, tipo, solicitante_contacto_id, payload)
            values (%s, 'documentos', %s, '{"qa":"o1.2"}'::jsonb)
            returning id
            """,
            (EMPRESA_A, contacto),
        )
        return str(cur.fetchone()[0])


def _decidir(
    solicitud: str,
    marcador: str,
    filtrar_estado: bool,
    barrera: threading.Barrier,
) -> dict[str, Any]:
    """Una conexión propia: espera en la barrera y aprueba la solicitud."""
    salida: dict[str, Any] = {"marcador": marcador}
    conn = conectar()
    try:
        with conn.cursor() as cur:
            sql = (
                "update nucleo.solicitudes "
                "set estado = 'aprobada', aprobado_por = %s, decidido_en = now() "
                "where id = %s"
            )
            if filtrar_estado:
                sql += " and estado = 'pendiente'"
            barrera.wait()
            cur.execute(sql, (marcador, solicitud))
            salida["filas"] = cur.rowcount
        conn.commit()
    except Exception as exc:  # noqa: BLE001 - se inspecciona el SQLSTATE
        salida["error"] = exc
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
    finally:
        conn.close()
    return salida


def caso_c2(conn: psycopg.Connection, contacto: str, reserva: list[str]) -> None:
    """Añade a `reserva` los ids creados para que el finally los borre."""
    solicitud_a = _nueva_solicitud(conn, contacto)
    reserva.append(solicitud_a)
    solicitud_b = _nueva_solicitud(conn, contacto)
    reserva.append(solicitud_b)
    conn.commit()

    # --- C2a: ambos filtran por estado ------------------------------------
    barrera = threading.Barrier(2, timeout=20)
    salidas: list[dict[str, Any]] = []
    hilos = [
        threading.Thread(
            target=lambda m, s=solicitud_a: salidas.append(_decidir(s, m, True, barrera)),
            args=(f"qa-c2a-{i}",),
            daemon=True,
        )
        for i in (1, 2)
    ]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)
    if any(h.is_alive() for h in hilos):
        fallo("C2a: un hilo no terminó (¿deadlock en la fila de la solicitud?)")

    errores = [s for s in salidas if "error" in s]
    filas = sorted(s.get("filas", 0) for s in salidas if "error" not in s)
    if errores:
        fallo(f"C2a: el UPDATE filtrado no debía fallar: {[str(s['error']) for s in errores]}")
    if filas != [0, 1]:
        fallo(f"C2a: se esperaba exactamente un ganador (filas [0,1]), llegó {filas}")

    with conn.cursor() as cur:
        cur.execute(
            "select estado, aprobado_por from nucleo.solicitudes where id = %s",
            (solicitud_a,),
        )
        estado, aprobado_por = cur.fetchone()
    if estado != "aprobada" or aprobado_por is None:
        fallo(f"C2a: estado final inesperado ({estado}, aprobado_por={aprobado_por})")
    print(
        "OK 0021-2 C2a: dos conexiones filtrando por estado ⇒ exactamente 1 "
        f"aprobación (filas [0,1]); aprobado_por={aprobado_por}"
    )

    # --- C2b: ninguno filtra por estado ⇒ el trigger arbitra ---------------
    barrera = threading.Barrier(2, timeout=20)
    salidas = []
    hilos = [
        threading.Thread(
            target=lambda m, s=solicitud_b: salidas.append(_decidir(s, m, False, barrera)),
            args=(f"qa-c2b-{i}",),
            daemon=True,
        )
        for i in (1, 2)
    ]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)
    if any(h.is_alive() for h in hilos):
        fallo("C2b: un hilo no terminó (¿deadlock en la fila de la solicitud?)")

    ganadores = [s for s in salidas if "error" not in s and s.get("filas") == 1]
    perdedores = [s for s in salidas if "error" in s]
    if len(ganadores) != 1:
        fallo(
            "C2b: se esperaba exactamente una aprobación; "
            f"ganadores={[(s['marcador'], s.get('filas')) for s in salidas]} "
            f"errores={[str(s['error']) for s in perdedores]}"
        )
    if len(perdedores) != 1:
        fallo(f"C2b: el perdedor debía fallar; salidas={salidas!r}")
    exc = perdedores[0]["error"]
    if sqlstate(exc) != "23514":
        fallo(f"C2b: el perdedor debía recibir 23514 del trigger, recibió {sqlstate(exc)}: {exc}")

    with conn.cursor() as cur:
        cur.execute(
            "select estado, aprobado_por from nucleo.solicitudes where id = %s",
            (solicitud_b,),
        )
        estado, aprobado_por = cur.fetchone()
    if estado != "aprobada":
        fallo(f"C2b: estado final {estado}, se esperaba aprobada")
    if aprobado_por != ganadores[0]["marcador"]:
        fallo(
            f"C2b: aprobado_por={aprobado_por} no coincide con el ganador "
            f"{ganadores[0]['marcador']} (¿dos aprobaciones?)"
        )
    print(
        "OK 0021-2 C2b: sin filtro de estado ⇒ 1 aprobación y el perdedor recibe "
        f"23514 del trigger (aprobado_por={aprobado_por})"
    )


# ---------------------------------------------------------------------------
# C3 — el mismo wa_message_id desde dos conexiones
# ---------------------------------------------------------------------------
def caso_c3(conn: psycopg.Connection, contacto: str, conversacion: str, wa_id: str) -> None:
    resultados: list[dict[str, Any]] = []
    barrera = threading.Barrier(2, timeout=20)

    def insertar(i: int) -> None:
        salida: dict[str, Any] = {"hilo": i}
        c = conectar()
        try:
            with c.cursor() as cur:
                barrera.wait()
                cur.execute(
                    """
                    insert into nucleo.conversacion_mensajes
                      (empresa_id, conversacion_id, contacto_id, wa_message_id,
                       direccion, modalidad, cuerpo)
                    values (%s, %s, %s, %s, 'entrante', 'texto', %s)
                    returning id
                    """,
                    (EMPRESA_A, conversacion, contacto, wa_id, f"duplicado {i}"),
                )
                salida["id"] = cur.fetchone()[0]
            c.commit()
        except Exception as exc:  # noqa: BLE001 - se inspecciona el SQLSTATE
            salida["error"] = exc
            try:
                c.rollback()
            except Exception:  # noqa: BLE001
                pass
        finally:
            c.close()
        resultados.append(salida)

    hilos = [threading.Thread(target=insertar, args=(i,), daemon=True) for i in (1, 2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)
    if any(h.is_alive() for h in hilos):
        fallo("C3: un hilo no terminó (¿el índice único no liberó la espera?)")

    ganadores = [r for r in resultados if "error" not in r]
    perdedores = [r for r in resultados if "error" in r]
    if len(ganadores) != 1:
        fallo(
            "C3: se esperaba exactamente una inserción ganadora; "
            f"salidas={[(r.get('hilo'), r.get('id'), str(r.get('error'))) for r in resultados]}"
        )
    if len(perdedores) != 1:
        fallo(f"C3: el perdedor debía fallar; salidas={resultados!r}")
    exc = perdedores[0]["error"]
    if sqlstate(exc) != "23505":
        fallo(f"C3: el perdedor debía recibir 23505, recibió {sqlstate(exc)}: {exc}")
    diag = getattr(exc, "diag", None)
    constraint = getattr(diag, "constraint_name", None)
    if constraint != "uq_mensaje_wa_message_id":
        fallo(f"C3: se esperaba uq_mensaje_wa_message_id, llegó {constraint!r}")

    with conn.cursor() as cur:
        cur.execute(
            "select count(*) from nucleo.conversacion_mensajes where wa_message_id = %s",
            (wa_id,),
        )
        n = cur.fetchone()[0]
    if n != 1:
        fallo(f"C3: hay {n} mensajes con el mismo wa_message_id (se esperaba 1)")
    print(
        "OK 0021-2 C3: mismo wa_message_id en 2 conexiones ⇒ 1 fila; "
        "el perdedor recibe 23505 (uq_mensaje_wa_message_id)"
    )


# ---------------------------------------------------------------------------
# Limpieza
# ---------------------------------------------------------------------------
def limpiar(
    ids: dict[str, list[str]],
    par_contador: tuple[str, str] | None,
    telefonos: list[str],
    wa_ids: list[str],
) -> None:
    """Borra SOLO lo creado por esta prueba, en orden de FKs; verifica 0 filas."""
    with psycopg.connect(dsn(), autocommit=True) as conn:
        with conn.cursor() as cur:
            if wa_ids:
                cur.execute(
                    "delete from nucleo.conversacion_mensajes where wa_message_id = any(%s)",
                    (wa_ids,),
                )
            if ids["conversaciones"]:
                cur.execute(
                    "delete from nucleo.conversacion_mensajes "
                    "where conversacion_id = any(%s::uuid[])",
                    (ids["conversaciones"],),
                )
            if ids["solicitudes"]:
                cur.execute(
                    "delete from nucleo.hoja_ruta where solicitud_id = any(%s::uuid[])",
                    (ids["solicitudes"],),
                )
                cur.execute(
                    "delete from nucleo.solicitudes where id = any(%s::uuid[])",
                    (ids["solicitudes"],),
                )
            if ids["conversaciones"]:
                cur.execute(
                    "delete from nucleo.conversaciones where id = any(%s::uuid[])",
                    (ids["conversaciones"],),
                )
            if ids["permisos"]:
                cur.execute(
                    "delete from nucleo.permisos_contacto where id = any(%s::uuid[])",
                    (ids["permisos"],),
                )
            if ids["contactos"]:
                cur.execute(
                    "delete from nucleo.contactos_whatsapp where id = any(%s::uuid[])",
                    (ids["contactos"],),
                )
            if par_contador is not None:
                cur.execute(
                    "delete from nucleo.id_comercial_contador "
                    "where empresa_id = %s and cliente_id = %s",
                    par_contador,
                )

            chequeos: list[tuple[str, tuple[Any, ...]]] = []
            if wa_ids:
                chequeos.append(
                    (
                        "select count(*) from nucleo.conversacion_mensajes "
                        "where wa_message_id = any(%s)",
                        (wa_ids,),
                    )
                )
            if ids["solicitudes"]:
                chequeos.append(
                    (
                        "select count(*) from nucleo.solicitudes where id = any(%s::uuid[])",
                        (ids["solicitudes"],),
                    )
                )
            if ids["conversaciones"]:
                chequeos.append(
                    (
                        "select count(*) from nucleo.conversaciones where id = any(%s::uuid[])",
                        (ids["conversaciones"],),
                    )
                )
            if ids["contactos"]:
                chequeos.append(
                    (
                        "select count(*) from nucleo.contactos_whatsapp "
                        "where id = any(%s::uuid[])",
                        (ids["contactos"],),
                    )
                )
            if telefonos:
                chequeos.append(
                    (
                        "select count(*) from nucleo.contactos_whatsapp "
                        "where telefono = any(%s)",
                        (telefonos,),
                    )
                )
            if par_contador is not None:
                chequeos.append(
                    (
                        "select count(*) from nucleo.id_comercial_contador "
                        "where empresa_id = %s and cliente_id = %s",
                        par_contador,
                    )
                )
            for sql, params in chequeos:
                cur.execute(sql, params)
                n = cur.fetchone()[0]
                if n != 0:
                    fallo(f"limpieza: quedaron {n} filas para {sql!r}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> None:
    ids: dict[str, list[str]] = {
        "contactos": [],
        "permisos": [],
        "conversaciones": [],
        "solicitudes": [],
    }
    telefonos: list[str] = []
    wa_ids: list[str] = []
    par_contador: tuple[str, str] | None = None
    reserva_contador: dict[str, tuple[str, str]] = {}
    auditoria_antes: int | None = None

    ctl = conectar()
    try:
        with ctl.cursor() as cur:
            cur.execute(
                "select current_user, coalesce((select rolbypassrls from pg_roles "
                "where rolname = current_user), false), current_database()"
            )
            usuario, bypass, base = cur.fetchone()
        if not bypass:
            fallo(
                f"corre como {usuario} sin BYPASSRLS: use el rol postgres local "
                "(esta prueba mide concurrencia, no RLS)"
            )
        print(f"OK 0021-2 entorno: rol={usuario} bypassrls={bypass} base={base}")

        with ctl.cursor() as cur:
            cur.execute("select count(*) from nucleo.auditoria")
            auditoria_antes = cur.fetchone()[0]

        # C1 (commits reales para demostrar que no hay saltos)
        par_contador = caso_c1(ctl, reserva_contador)

        # Fixtures C2/C3 (commit mínimo para que la otra conexión los vea)
        telefono = telefono_aleatorio()
        telefonos.append(telefono)
        with ctl.cursor() as cur:
            cur.execute(
                """
                insert into nucleo.contactos_whatsapp (empresa_id, telefono, nombre, rol)
                values (%s, %s, 'QA O1.2 concurrencia', 'admin')
                returning id
                """,
                (EMPRESA_A, telefono),
            )
            contacto = str(cur.fetchone()[0])
            ids["contactos"].append(contacto)

            cur.execute(
                "insert into nucleo.conversaciones (empresa_id, contacto_id) "
                "values (%s, %s) returning id",
                (EMPRESA_A, contacto),
            )
            conversacion = str(cur.fetchone()[0])
            ids["conversaciones"].append(conversacion)
        ctl.commit()

        caso_c2(ctl, contacto, ids["solicitudes"])

        wa_id = f"wamid.qa.o12.{uuid.uuid4().hex}"
        wa_ids.append(wa_id)
        caso_c3(ctl, contacto, conversacion, wa_id)
    finally:
        if par_contador is None:
            par_contador = reserva_contador.get("par")
        try:
            limpiar(ids, par_contador, telefonos, wa_ids)
            print("OK 0021-2 limpieza: 0 filas de negocio residuales (verificado)")
        finally:
            if auditoria_antes is not None:
                with ctl.cursor() as cur:
                    cur.execute("select count(*) from nucleo.auditoria")
                    auditoria_despues = cur.fetchone()[0]
                print(
                    "     nota: nucleo.auditoria (append-only) pasó de "
                    f"{auditoria_antes} a {auditoria_despues} filas por las operaciones "
                    "commiteadas de C1/C2/C3; no se borran por diseño (0004:880-892)"
                )
            ctl.close()

    print("0021_02_concurrencia_id_comercial: OK")


if __name__ == "__main__":
    main()
