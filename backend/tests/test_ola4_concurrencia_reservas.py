"""Concurrencia real del libro de ocupación (`EXCLUDE` de reservas).

La migración 0004 declara tres constraints `EXCLUDE USING gist` sobre
`nucleo.reservas_recurso` (tracto/rampla/chofer, ventana `[inicio, fin)`). La
prueba secuencial de `test_nucleo_integracion.py` valida el preview del
servicio, pero **no** prueba la carrera: dos INSERT simultáneos que se solapan
deben bloquearse en el índice GiST y terminar con exactamente una fila.

Aquí se usan dos conexiones psycopg reales y una barrera de eventos:

- A inserta 08:00–12:00 y espera a que B intente insertar;
- B intenta 10:00–14:00 (solapa) y queda bloqueado hasta el COMMIT de A;
- al confirmar A, B recibe SQLSTATE 23P01 y hace rollback.

Además se valida el borde semiabierto: 12:00–16:00 es válido (toca el fin de A
sin solapar) y 15:00–17:00 se rechaza. Las filas quedan con una etiqueta única;
el núcleo es inmutable por triggers y no se borran.
"""

from __future__ import annotations

import threading
from decimal import Decimal
from uuid import uuid4

import ola4_helpers as h
import psycopg
import pytest

from app.nucleo.models import Tracto

pytestmark = pytest.mark.integracion

APP_NAME = "ola4-reservas-concurrente"


def _insertar_reserva(conn, empresa_id, tracto_id, inicio: str, fin: str) -> None:
    conn.execute(
        "insert into nucleo.reservas_recurso "
        "  (empresa_id, recurso_tipo, tracto_id, ventana, tipo_reserva, motivo) "
        "values (%s, 'tracto'::nucleo.tipo_recurso, %s, "
        "        tstzrange(%s::timestamptz, %s::timestamptz, '[)'), "
        "        'bloqueo_manual'::nucleo.tipo_reserva, 'Prueba Ola4')",
        (empresa_id, tracto_id, inicio, fin),
    )


def test_dos_reservas_solapadas_concurrentes_una_gana():
    from ola4_helpers import sesion_confirmada

    with sesion_confirmada() as setup:
        etiqueta = uuid4().hex[:6]
        empresa = h.empresa(setup, etiqueta)
        tracto = Tracto(
            empresa_id=empresa.id,
            patente=f"T4{etiqueta[:5].upper()}",
            peso_bruto_kg=Decimal(39000),
            tara_kg=Decimal(9000),
            capacidad_carga_kg=Decimal(30000),
            licencias_permitidas=["A5"],
        )
        setup.add(tracto)
        setup.commit()
        setup.refresh(tracto)
        empresa_id, tracto_id = empresa.id, tracto.id

    inicio_a = "2027-03-10T08:00:00+00:00"
    fin_a = "2027-03-10T12:00:00+00:00"
    inicio_b = "2027-03-10T10:00:00+00:00"  # solapa 2 h
    fin_b = "2027-03-10T14:00:00+00:00"

    a_insertado = threading.Event()
    b_intentando = threading.Event()
    resultados: dict[str, str] = {}

    def hilo_a() -> None:
        with psycopg.connect(h.dsn_test(), connect_timeout=10) as conn:
            conn.execute(
                "select set_config('application_name', %s, false)", (APP_NAME,)
            )
            _insertar_reserva(conn, empresa_id, tracto_id, inicio_a, fin_a)
            a_insertado.set()
            assert b_intentando.wait(timeout=10), "B no llegó a intentar el INSERT"
            conn.commit()
            resultados["a"] = "commit"

    def hilo_b() -> None:
        assert a_insertado.wait(timeout=10), "A no insertó"
        with psycopg.connect(h.dsn_test(), connect_timeout=10) as conn:
            conn.execute(
                "select set_config('application_name', %s, false)", (APP_NAME,)
            )
            b_intentando.set()
            try:
                _insertar_reserva(conn, empresa_id, tracto_id, inicio_b, fin_b)
                conn.commit()
                resultados["b"] = "commit"
            except psycopg.Error as exc:
                resultados["b"] = f"error:{exc.sqlstate}"
                conn.rollback()

    hilo_a = threading.Thread(target=hilo_a)
    hilo_b = threading.Thread(target=hilo_b)
    hilo_a.start()
    hilo_b.start()
    hilo_a.join(timeout=20)
    hilo_b.join(timeout=20)
    assert not hilo_a.is_alive() and not hilo_b.is_alive()

    assert resultados.get("a") == "commit", resultados
    assert resultados.get("b") == "error:23P01", resultados

    with psycopg.connect(h.dsn_test(), connect_timeout=10) as conn:
        total = conn.execute(
            "select count(*) from nucleo.reservas_recurso "
            " where empresa_id = %s and tracto_id = %s and activa",
            (empresa_id, tracto_id),
        ).fetchone()[0]
    assert total == 1, "la EXCLUDE debe dejar exactamente una reserva activa"

    # Borde semiabierto: 12:00–16:00 toca el fin de A sin solapar ⇒ se acepta.
    with psycopg.connect(h.dsn_test(), connect_timeout=10) as conn:
        _insertar_reserva(
            conn,
            empresa_id,
            tracto_id,
            "2027-03-10T12:00:00+00:00",
            "2027-03-10T16:00:00+00:00",
        )
        conn.commit()

    # Solapamiento real contra la segunda reserva ⇒ 23P01.
    with psycopg.connect(h.dsn_test(), connect_timeout=10) as conn:
        with pytest.raises(psycopg.Error) as excinfo:
            _insertar_reserva(
                conn,
                empresa_id,
                tracto_id,
                "2027-03-10T15:00:00+00:00",
                "2027-03-10T17:00:00+00:00",
            )
        assert excinfo.value.sqlstate == "23P01"

    with psycopg.connect(h.dsn_test(), connect_timeout=10) as conn:
        total = conn.execute(
            "select count(*) from nucleo.reservas_recurso "
            " where empresa_id = %s and tracto_id = %s and activa",
            (empresa_id, tracto_id),
        ).fetchone()[0]
    assert total == 2, "las dos ventanas válidas deben coexistir"
