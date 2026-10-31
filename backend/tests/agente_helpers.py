"""Utilidades compartidas de los tests del agente.

El clon `tei_test` trae una sola empresa (la del seed). Varias pruebas de
aislamiento necesitan una segunda: se crea de forma determinista aquí en vez de
saltar la prueba (un skip por orden de ejecución no es aprobado).
"""
from __future__ import annotations

import uuid


def asegurar_segunda_empresa(conn) -> str:
    """Devuelve el id de una empresa distinta de la del seed; la crea si falta."""
    base = conn.execute(
        "select id from nucleo.empresas order by created_at limit 1"
    ).fetchone()
    if base is None:
        raise RuntimeError("tei_test sin empresas; ejecute `make seed`")
    otra = conn.execute(
        "select id from nucleo.empresas where id <> %s limit 1", (base[0],)
    ).fetchone()
    if otra is not None:
        return str(otra[0])
    codigo = f"TEST-AIS-{uuid.uuid4().hex[:8]}"
    rut = str(uuid.uuid4().int % 10**12).zfill(12)
    creada = conn.execute(
        "insert into nucleo.empresas (codigo, razon_social, rut) "
        "values (%s, %s, %s) returning id",
        (codigo, "Empresa de prueba (aislamiento)", rut),
    ).fetchone()
    conn.commit()
    return str(creada[0])


def asegurar_segunda_empresa_con_membresia(conn, auth_excluido: str) -> tuple[str, str]:
    """Empresa distinta + membresía de OTRO usuario (nunca la del `auth_excluido`).

    La membresía ajena es necesaria para probar 404 con recurso de otra empresa
    sin convertir al usuario de la prueba en miembro (lo que rompería el 403).
    """
    empresa_id = asegurar_segunda_empresa(conn)
    fila = conn.execute(
        "select id from nucleo.usuarios_empresa "
        "where empresa_id = %s and auth_id <> %s and activo limit 1",
        (empresa_id, auth_excluido),
    ).fetchone()
    if fila is not None:
        return empresa_id, str(fila[0])
    otro = conn.execute(
        "select id from auth.users where id <> %s limit 1", (auth_excluido,)
    ).fetchone()
    if otro is None:
        raise RuntimeError("tei_test sin un segundo auth.users; ejecute `make seed`")
    rol = conn.execute("select rol from nucleo.usuarios_empresa limit 1").fetchone()
    rol = rol[0] if rol else "consulta"
    nueva = conn.execute(
        "insert into nucleo.usuarios_empresa (empresa_id, auth_id, rol, activo) "
        "values (%s, %s, cast(%s as nucleo.rol_empresa), true) returning id",
        (empresa_id, otro[0], str(rol)),
    ).fetchone()
    conn.commit()
    return empresa_id, str(nueva[0])
