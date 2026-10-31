"""RUT de prueba para filas de `nucleo.empresas` (estabilización de flakiness).

Contexto del defecto (2026-10-30)
--------------------------------
`supabase/migrations/0004_nucleo_operacional.sql:136` define:

    create unique index uq_empresas_rut_norm
      on nucleo.empresas (upper(regexp_replace(rut, '[^0-9K]', '', 'g')));

Es decir, el índice **normaliza** el RUT dejando solo dígitos y `K`. Un RUT de
prueba alfanumérico como `CON-a1b2c3d4` queda indexado como `1234`, y dos
sufijos distintos (`CON-a1b2c3d4` y `CON-1a2b3c4d`) producen la misma clave.
Como `nucleo.empresas` es global (no lleva `empresa_id`) y la base de test
`tei_test` persiste entre corridas, esos RUT se acumulan y la corrida N choca
con la N-1: `UniqueViolation` / SQLSTATE `23505` sobre `uq_empresas_rut_norm`.

Reproducción mínima (sin dejar datos, `ROLLBACK`):

    begin;
    insert into nucleo.empresas(codigo, razon_social, rut)
      values ('QA-RUT-1','QA RUT uno','CON-a1b2c3d4');
    insert into nucleo.empresas(codigo, razon_social, rut)
      values ('QA-RUT-2','QA RUT dos','CON-1a2b3c4d');
    -- ERROR: duplicate key value violates unique constraint
    --        "uq_empresas_rut_norm"
    -- DETAIL: Key (...)=(1234) already exists.
    rollback;

Uso
---
Solo para empresas **de prueba**; no cambia la semántica de la prueba (ninguna
prueba afirma nada sobre el RUT de la empresa creada). Para `nucleo.clientes` y
`nucleo.choferes` no se necesita: sus índices de RUT normalizado están
particionados por `empresa_id` y cada prueba crea una empresa nueva.
"""

from __future__ import annotations

import random
import time

#: Arranque aleatorio dentro de la corrida: evita que dos procesos pytest que
#: empiezan en el mismo microsegundo generen la misma secuencia.
_secuencia = random.randrange(0, 1_000_000)


def rut_empresa() -> str:
    """RUT numérico de 12 dígitos, único para las empresas de prueba.

    Composición: 6 dígitos de reloj en microsegundos (cambia en cada llamada
    salvo llamadas dentro del mismo microsegundo) + 6 dígitos de secuencia del
    proceso. Sin letras ⇒ `regexp_replace(rut, '[^0-9K]', '')` devuelve el
    propio valor, de 12 dígitos, sin colisión con los RUT cortos que dejaron las
    corridas anteriores sobre la misma base.
    """

    global _secuencia
    _secuencia += 1
    microsegundos = time.time_ns() // 1_000
    return f"{microsegundos % 10**6:06d}{_secuencia % 10**6:06d}"
