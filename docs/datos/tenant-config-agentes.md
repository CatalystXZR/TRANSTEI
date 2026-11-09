# Configuración de tenant por entidad y suscripciones (`0030`)

**Fecha:** 2026-11-02 · **Dueño:** `datos` · **Estado:** aplicado **solo en
`tei_test`**; **pendiente de autorización** para la base de la app (`postgres`).

**Contrato:** Apéndice A de
`docs/arquitectura/adr/ADR-0008-config-tenant-y-autoridad-estados.md`
(líneas 588-685). **No** se re-decidió el modelo.

---

## 1. Objeto y motivo

| Objeto | Para qué | Vigencia |
|---|---|---|
| `nucleo.tipo_entidad_regla` (enum) | Tipo de entidad destino de una regla | — |
| `nucleo.tenant_reglas_entidad` | Regla por empresa **y** entidad concreta, `valor jsonb` | `[vigente_desde, vigente_hasta)` |
| `nucleo.tenant_suscripciones` | Plan/estado comercial por empresa | `[vigente_desde, vigente_hasta)` |
| `nucleo.fn_regla_entidad_inmutable()` | Historial inmutable + bloqueo de DELETE | — |

**No se creó `tenant_config`.** El ADR-0008 §B.0 concluyó que una tabla
`tenant_config` duplicaría `nucleo.configuracion_empresa` (`0026`). Si un
consumidor exige ese nombre, corresponde una **vista** con
`security_invoker = true` (Apéndice B.0), que no forma parte de esta migración.

---

## 2. Esquema creado (`archivo:línea`)

`supabase/migrations/0030_tenant_config_agentes.sql`:

| Línea | Objeto |
|---|---|
| 126-208 | `do` de precondiciones P1–P7 |
| 210-225 | `nucleo.tipo_entidad_regla` (5 valores) |
| 231-289 | `nucleo.tenant_reglas_entidad` (columnas, FKs, CHECK, EXCLUDE) |
| 292-308 | `COMMENT`s de la tabla de reglas |
| 313-325 | `uq_regla_vigente` (UNIQUE parcial con centinelas) + índice de búsqueda |
| 330-356 | `nucleo.tenant_suscripciones` |
| 359-373 | `COMMENT`s de suscripciones |
| 376-381 | `uq_suscripcion_vigente` + índice |
| 389-427 | `nucleo.fn_regla_entidad_inmutable()` |
| 435-456 | 7 triggers (4 reglas + 3 suscripciones) |
| 459-476 | RLS `ENABLE`/`FORCE` + políticas `tenant_empresa` |
| 483-500 | GRANTs (`tei_app` sin DELETE; `postgres` con DELETE) y revocaciones |
| 503-596 | verificación dentro de la transacción |

### 2.1 Reglas por entidad

Columnas: `id`, `empresa_id`, `entidad`, `cliente_id`/`chofer_id`/`tracto_id`/
`rampla_id`/`contacto_id` (nullable), `clave`, `valor jsonb`,
`vigente_desde`/`vigente_hasta`, `created_at/by`, `updated_at/by`, `version`.

Constraints relevantes:

- `UNIQUE (empresa_id, id)` (`uq_reglas_entidad_empresa_id`).
- FK simple a `nucleo.empresas(id) ON DELETE RESTRICT`.
- 5 FKs compuestas `(empresa_id, <fk>_id) → nucleo.<tabla>(empresa_id, id)
  ON DELETE RESTRICT`. Requiere `UNIQUE (empresa_id, id)` en cada destino
  (verificado: `clientes`, `choferes`, `tractos`, `ramplas`,
  `contactos_whatsapp`).
- `ck_regla_una_entidad`: `num_nonnulls(...) = 1` y coherencia con `entidad`.
- `ck_regla_clave_formato`: `^[a-z][a-z0-9_]{2,63}$`.
- `ck_regla_vigencia`: `vigente_hasta IS NULL OR vigente_hasta > vigente_desde`.
- `ex_regla_vigencia`: `EXCLUDE USING gist` con `empresa_id`, `entidad`,
  `clave`, 5 expresiones `coalesce(<fk>, '00000000-…'::uuid)` y
  `tstzrange(vigente_desde, vigente_hasta, '[)')`. Las expresiones centinela son
  obligatorias: sobre columnas nullable el `EXCLUDE` no detectaría solapes.
- `uq_regla_vigente`: UNIQUE parcial por
  `(empresa_id, entidad, clave, <5 centinelas>) WHERE vigente_hasta IS NULL`.

### 2.2 Suscripciones

Columnas: `id`, `empresa_id`, `plan_codigo`, `estado` (default `activa`),
`referencia_externa` (nullable), `vigente_desde`/`vigente_hasta`, control.

Constraints: `UNIQUE (empresa_id, id)`, FK a `empresas` `RESTRICT`,
`ck_suscripcion_plan_formato` (`^[a-z][a-z0-9_-]{2,63}$`),
`ck_suscripcion_estado` (`activa|suspendida|cancelada`), `ck_suscripcion_vigencia`,
`ex_suscripcion_vigencia` y `uq_suscripcion_vigente`.

**Prohibido y ausente:** `precio`, `moneda`, `cupos`, `limites jsonb`,
`habilitado boolean` (Apéndice A.4). La prueba `0030_02` 2A falla si alguien
las agrega.

### 2.3 Seguridad

- `ENABLE` + `FORCE ROW LEVEL SECURITY` en ambas tablas.
- Política `tenant_empresa FOR ALL TO public USING/WITH CHECK
  (empresa_id = nucleo.ctx_empresa())`, con `DROP POLICY IF EXISTS` previo.
- `tei_app`: `SELECT, INSERT, UPDATE`; **nunca DELETE**.
- `anon`/`authenticated`: `REVOKE ALL` si existen.
- `postgres` (rol de plataforma): `SELECT, INSERT, UPDATE, DELETE` (patrón `0027`).
- Sin `SECURITY DEFINER` nuevo; los triggers usan las funciones compartidas
  (`fn_touch`, `fn_version`, `fn_auditoria`) y una función de inmutabilidad
  nueva con `search_path` fijo.

---

## 3. Invariantes impuestos

Ver `docs/datos/invariantes.md` §14 (`INV-TEN01`–`INV-TEN10`). Resumen:

| ID | Regla | Mecanismo | SQLSTATE |
|---|---|---|---|
| INV-TEN01 | Exactamente una entidad destino, coherente con `entidad` | `ck_regla_una_entidad` | 23514 |
| INV-TEN02 | El destino es de la misma empresa | FK compuesta | 23503 |
| INV-TEN03 | Sin solapes de vigencia por regla/destino | `ex_regla_vigencia` | 23P01 |
| INV-TEN04 | Una sola fila abierta por regla/destino | `uq_regla_vigente` | 23505/23P01 |
| INV-TEN05 | Fila cerrada inmutable; reglas no se borran | `fn_regla_entidad_inmutable` | 23514 |
| INV-TEN06 | Sin solapes por (empresa, plan) | `ex_suscripcion_vigencia` | 23P01 |
| INV-TEN07 | Una sola suscripción abierta por (empresa, plan) | `uq_suscripcion_vigente` | 23505/23P01 |
| INV-TEN08 | `estado` y `plan_codigo` acotados | CHECKs | 23514 |
| INV-TEN09 | Invisible/inescribible fuera de `app.empresa_id` | RLS + FORCE + política | 42501 / 0 filas |
| INV-TEN10 | `tei_app` no borra | GRANT sin DELETE | 42501 |

### Qué **no** impone la migración

- **Catálogo de claves y forma de `valor`**: es del servicio (`D-27`). La base
  solo exige jsonb y formato de `clave`.
- **Plan, precio, moneda, cupos, límites**: `D-25`/`D-26` abiertos. No existen
  columnas.
- **Gate de módulos**: la suscripción **no** se evalúa en autorización; el flag
  sigue en `nucleo.modulos_empresa` (ADR-0008 Ap. C.1).
- **Cierre automático de vigencia** de suscripciones y su inmutabilidad: no hay
  historial decidido; el contrato A.5 solo pide touch/version/audit.
- **Inmutabilidad de una regla abierta**: mientras `vigente_hasta IS NULL` se
  pueden editar `valor`, las 5 FKs y `clave`. El contrato A.3/A.5 solo congela la
  fila **cerrada**; exigir "cerrar + insertar" también para abiertas es una
  decisión de negocio posterior (`P-15`).
- **Concurrencia probada con dos conexiones**: no se ejecutó para el `EXCLUDE`
  (sí se probaron todos los bordes secuenciales). Pendiente de `qa`.

---

## 4. Precondiciones (ejecutadas)

Todas corren dentro de la transacción y abortan con `23514` **sin crear nada**:

| # | Detección | Resultado en `tei_test` |
|---|---|---|
| P1 | Estado parcial de las dos tablas | 0 filas (ninguna existía) |
| P2 | `ctx_empresa()`, rol `tei_app`, `USAGE` | OK |
| P3 | `btree_gist` | 1 fila |
| P4 | `empresas` y `configuracion_empresa` | existen |
| P5 | `modulos_empresa` | existe |
| P6 | Empresas no activas | `NOTICE` 0 (informativo) |
| P7 | `UNIQUE (empresa_id, id)` en 5 destinos | 5/5 |

---

## 5. Impacto y rollback

- **Datos:** no se siembra nada; conteo 0 en ambas tablas al aplicar.
- **Locks:** solo sobre objetos nuevos. Las FKs apuntan a tablas existentes sin
  reescribirlas. No hay `ALTER TABLE` sobre tablas calientes ni backfill.
- **Compatibilidad:** aditivo. Backend y frontend actuales no leen estas tablas;
  `make test` sigue en verde (423).
- **Rollback:** `supabase/tests/0030_99_rollback.sql` elimina triggers, tablas,
  función y enum, verifica 0 objetos y es idempotente. No toca `empresas`,
  `configuracion_empresa`, `modulos_empresa`, las tablas de entidades ni
  `nucleo.auditoria`. **Pérdida:** las reglas/suscripciones escritas (ninguna al
  aplicar).

---

## 6. Pruebas ejecutadas (salida real en el informe de la sesión)

| Archivo | Qué cubre | Resultado |
|---|---|---|
| `supabase/tests/0030_01_reglas_entidad.sql` | Una FK/coherencia, formato de clave, vigencia, `EXCLUDE`, `UNIQUE` parcial, inmutabilidad, DELETE, FK cruzada, dos empresas | ✅ 23 `OK` + `ROLLBACK` |
| `supabase/tests/0030_02_suscripciones.sql` | Estado, plan, vigencia, solape, unicidad, columnas prohibidas, `version` | ✅ 15 `OK` + `ROLLBACK` |
| `supabase/tests/0030_03_rls_tei_app.sql` | `SET LOCAL ROLE tei_app`: sin contexto, contexto TEI/TES, cross-tenant, DELETE 42501 | ✅ 11 `OK` + `ROLLBACK` |
| `supabase/tests/0030_99_rollback.sql` | Drop ordenado, 0 objetos, tablas no tocadas | ✅ `COMMIT` |
| Ciclo | aplicar → rollback → 0 objetos → re-aplicar | ✅ |
| Mutación (transacción desechable) | Retirar `ck_regla_una_entidad`, `ex_regla_vigencia`, `trg_tenant_reglas_inmutable`, `uq_regla_vigente` y RLS: las 5 violaciones fueron **aceptadas**; `ROLLBACK` restauró todo (`ex=1`, `trg=1`, índice=1) | ✅ |
| `make test` | suite completa sobre `tei_test` | ✅ 423 passed |

---

## 7. Handoff

### 7.1 `backend` (SQLSTATE → HTTP)

| Situación | SQLSTATE | HTTP propuesto |
|---|---|---|
| Segunda regla/suscripción abierta o solape | `23505` / `23P01` | **409** con mensaje de vigencia vigente |
| Entidad destino de otra empresa | `23503` | **422** ("la entidad no pertenece a la empresa") |
| Entidad incoherente / sin entidad / formato de clave o plan / estado ilegal / vigencia invertida | `23514` | **422** |
| Escritura fuera de `app.empresa_id` (RLS) | `42501` | **403** |
| DELETE de regla/suscripción con `tei_app` | `42501` | **403** (no exponer DELETE) |

El servicio debe leer `entidad`, la FK correspondiente y `clave` del cuerpo, y
traducir los tres `SQLSTATE`; **nunca** devolver el mensaje crudo de PostgreSQL.

### 7.2 `qa`

- Repetir las 4 pruebas en CI con `tei_test`.
- Añadir concurrencia real (dos conexiones) para `EXCLUDE` si el riesgo se
  clasifica Alto.
- Verificar que el catálogo del servicio no inventa claves que la base acepte
  pero nadie lea (`INV-TC06`).

### 7.3 Preguntas abiertas para `negocio-finanzas` (no resueltas)

1. **D-25** — ¿Qué es un plan, qué se cobra, periodicidad, moneda, prorrateo y
   quién factura? La tabla solo admite `plan_codigo`/`estado`/vigencia.
2. **D-26** — ¿Qué límites son comerciales y en qué punto se cumplen (tabla,
   consulta, HTTP)? Sin eso no se agrega `limites jsonb` ni `cupos`.
3. **D-25 (historial)** — ¿La suscripción requiere historial con cierre manual o
   basta sobrescribir? Hoy no hay trigger de cierre automático.
4. **D-27** — ¿El catálogo de `clave` debe editarse sin desplegar? Hoy vive en el
   servicio; una tabla de catálogo requiere ADR propio.
5. **P-15** — ¿Las reglas por entidad requieren vigencia histórica? La base ya la
   soporta; confirmar la política de negocio.

---

## 8. Comando pendiente de autorización (base de la app)

**No ejecutado.** Aplicar `0030` a la base `postgres` (app) requiere autorización
explícita del dueño:

```bash
docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d postgres -v ON_ERROR_STOP=1 \
  < supabase/migrations/0030_tenant_config_agentes.sql
```

Después, con el rol de la app, ejecutar `0030_03_rls_tei_app.sql` y registrar la
salida. La migración es aditiva y re-ejecutable; aun así, **no** se aplicó a la
base de la app en esta sesión.

---

## 9. Riesgos y no verificado

- 🟢 Aplicación limpia, 4 pruebas SQL, ciclo rollback/re-aplicación y `make test`
  (423) verificados en `tei_test`.
- 🔴 No se probó concurrencia con dos conexiones para el `EXCLUDE` (las
  constraints son atómicas, pero no se ejecutó el escenario).
- 🔴 El rol efectivo del backend desplegado no se verificó (`R-10`); si conecta
  con `postgres`/`supabase_admin`, RLS es inerte para ese camino.
- 🟡 El `EXCLUDE` de reglas tiene 9 claves; se verificó que compila y detecta
  solapes en PG 17.11 con `btree_gist`, pero no se midió el costo de escritura a
  escala.
- 🟡 `contactos_whatsapp` tiene `UNIQUE (empresa_id, id)` y la FK compuesta
  funciona; cualquier cambio futuro de esa unicidad rompería la FK.
