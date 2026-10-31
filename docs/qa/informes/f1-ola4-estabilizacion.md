# F1 Ola 4 — Estabilización de flakiness y validación RLS (qa)

> Depositado por el orquestador (2026-10-30): el agente `qa` agotó pasos antes de escribir el archivo; contenido íntegro de su respuesta. Verificación del orquestador: `make unit` 67 · `make test` 219 passed (2026-10-30).

## Resultado

| Ítem | Estado |
|---|---|
| Tarea 1 — estabilizar RUT | 🟢 Hecho: helper único `backend/tests/rut_helpers.py` + 18 archivos migrados (23 sitios donde una `Empresa` nacía con RUT alfanumérico) |
| Tarea 2 — 3× `make test` | 🟢 **3/3 verdes**: 219 passed en tres corridas (00:56:32, 00:56:43, 00:56:57) |
| Tarea 3 — pruebas RLS 0020 | 🟢 **4/4 OK** en `tei_test`: 0020_01 (aislamiento), 0020_02 (dos conexiones, solape 1,60 s), 0020_03 (mutación), 0020_04 (compatibilidad) |
| Tarea 4 — `make unit` | 🟢 `67 passed` (incluye `test_kpi_engine.py` y `test_f1_ola3_recursos_decimal.py`) |

## Evidencia

```bash
make unit → 67 passed, 2 warnings
make test → 219 passed ×3 (00:56:32 / 00:56:43 / 00:56:57)

# RUT reproducido sin dejar datos
begin;
insert into nucleo.empresas(codigo,razon_social,rut) values ('QA-RUT-1','x','CON-a1b2c3d4');
insert into nucleo.empresas(codigo,razon_social,rut) values ('QA-RUT-2','x','CON-1a2b3c4d');
-- ERROR: duplicate key ... "uq_empresas_rut_norm"  DETAIL: Key=(1234) already exists.
rollback;

# 0020 en tei_test
psql -U tei_app … < supabase/tests/0020_01_aislamiento.sql   → OK (exit 0)
PSQL="docker exec -i supabase_db_TRANSTEI psql -h 127.0.0.1" bash supabase/tests/0020_02_dos_conexiones.sh
  → A|viajes|5 A|ajenos|0 · B|viajes|4 B|ajenos|0 · solape 1.60s · OK
PSQL_ADMIN="docker exec -i supabase_db_TRANSTEI psql -h 127.0.0.1 -U supabase_admin" bash supabase/tests/0020_03_mutacion.sh
  → M1 BYPASSRLS ve viajes ajenos; M2 USING(true) ve clientes ajenos; M3 sin FORCE tei_app sigue 0; restaurado OK
psql -U postgres … < supabase/tests/0020_04_compatibilidad_postgres.sql → OK
```

## Sanidad (mutación) de la corrección RUT

Con el helper forzado a RUT constante → la 2ª corrida falla con `UniqueViolation` (la prueba falla sin la garantía); sin el parche → verde. Ninguna aserción se debilitó.

## Defectos detectados

| # | Severidad | Descripción | Agente |
|---|---|---|---|
| D1 | Media (proceso) | Entre 00:54:06 y 00:56:19 `database.py` usó `event.listen(engine,"after_begin",…)` (evento inexistente) ⇒ 48 failed + 5 errors en la suite. Corregido a `"begin"`; md5 final `2f0f7dbfc2d334081404149a9fd2b641` (verificado por el orquestador). | backend |
| D2 | Baja (documentación) | El README de `supabase/tests/` usa `PSQL_ADMIN="… psql"` (rol root) y `-U postgres` para `ALTER POLICY`; correcto: `-h 127.0.0.1 -U supabase_admin`. | datos |
| D3 | Informativa | `0020_03` deja el aislamiento roto por segundos si se interrumpe; el `trap EXIT` funciona (post-estado verificado). | datos |

## Pendiente / inconcluso

1. Entregable (este archivo) — depositado por el orquestador.
2. Residuo de mutación: 1 fila `nucleo.empresas` con `rut='123456789012'` en `tei_test` (no afecta las 3 corridas verdes). Limpieza: `make test-db` + re-aplicar `0020` en el clon.
3. No se ejecutó `make test-db` (borraría las 35 políticas del clon).
