"""Crea el SEGUNDO TENANT (empresa B) con usuarios y datos mínimos.

- Idempotente. No toca el tenant TEI.
- Requiere el stack Supabase local arriba (`make db-up`).
- Uso: `.venv/bin/python scripts/seed_segundo_tenant.py`

El objetivo es permitir el onboarding real de una segunda empresa y probar el
aislamiento (RLS + `X-Empresa-ID` + membresía) de extremo a extremo. Los
usuarios del tenant 2 NO tienen acceso a las pantallas legacy (monoempresa):
eso lo impone el backend (`LEGACY_SOLO_TEI`).
"""
from __future__ import annotations

import uuid

import psycopg

from seed_local import cargar_env, crear_o_obtener_usuario, db_url

EMPRESA_B = uuid.UUID("22222222-2222-2222-2222-222222222222")
PASSWORD = "TEI2026!"

USUARIOS = [
    # email, nombre, rol del núcleo, rol legacy (public.usuarios: admin|operacion|contabilidad)
    ("admin2@tei.local", "Admin Transportes del Sur", "admin", "admin"),
    ("despacho2@tei.local", "Despacho Transportes del Sur", "despacho", "operacion"),
]

CLIENTES = [
    (uuid.UUID("22222222-0000-0000-0000-000000000101"), "Minera del Sur SpA", "77.111.222-3"),
    (uuid.UUID("22222222-0000-0000-0000-000000000102"), "Agro Los Ríos Ltda", "77.222.333-4"),
]


def seed_segundo_tenant() -> None:
    cargar_env()
    auth_ids = {
        rol: crear_o_obtener_usuario(email, PASSWORD, nombre)
        for email, nombre, rol, _rol_legacy in USUARIOS
    }

    with psycopg.connect(db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into nucleo.empresas
                  (id, codigo, razon_social, rut, giro, ciudad, region,
                   buffer_operacional_min, dias_margen_documentos,
                   dias_alerta_documentos, exigir_soap, exigir_seguro_carga,
                   exigir_curso_carga_peligrosa, exigir_oc, estado)
                values
                  (%s, 'TES', 'Transportes del Sur SpA', '77.999.888-1',
                   'Transporte de carga por carretera', 'Puerto Montt', 'Los Lagos',
                   90, 0, 14, true, true, true, false, 'activa')
                on conflict (id) do update set
                  razon_social = excluded.razon_social,
                  estado = 'activa',
                  updated_at = now()
                """,
                (EMPRESA_B,),
            )
            # Configuración base por empresa (0026): IVA de la empresa.
            cur.execute(
                """
                insert into nucleo.configuracion_empresa
                  (empresa_id, clave, valor, vigente_desde)
                values (%s, 'iva_porcentaje', '19'::jsonb, now())
                on conflict (empresa_id, clave) where vigente_hasta is null
                do nothing
                """,
                (EMPRESA_B,),
            )

            for email, nombre, rol, rol_legacy in USUARIOS:
                uid = auth_ids[rol]
                cur.execute(
                    """
                    insert into nucleo.usuarios_empresa (empresa_id, auth_id, rol, activo)
                    values (%s, %s, %s, true)
                    on conflict (empresa_id, auth_id)
                    do update set rol = excluded.rol, activo = true
                    """,
                    (EMPRESA_B, uid, rol),
                )
                # (Sin espejo legacy: la identidad ya no vive en `public.usuarios`.)

            for cliente_id, razon_social, rut in CLIENTES:
                cur.execute(
                    """
                    insert into nucleo.clientes (id, empresa_id, razon_social, rut)
                    values (%s, %s, %s, %s)
                    on conflict (id) do nothing
                    """,
                    (cliente_id, EMPRESA_B, razon_social, rut),
                )

            cur.execute(
                "select count(*) from nucleo.clientes where empresa_id = %s",
                (EMPRESA_B,),
            )
            clientes = cur.fetchone()[0]
        conn.commit()

    print("Segundo tenant listo")
    print(f"  empresa_id:  {EMPRESA_B}  (codigo TES)")
    print(f"  usuarios:    {' / '.join(e for e, _, _, _ in USUARIOS)}  (clave {PASSWORD})")
    print(f"  clientes:    {clientes}")


if __name__ == "__main__":
    seed_segundo_tenant()
