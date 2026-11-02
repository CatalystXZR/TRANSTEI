# Retiro físico del esquema legacy `public` (Ola E, ADR-0002 §6.7 E.5)

> **Pregunta que responde:** ¿qué se borró de `public`, con qué precondiciones, qué
> evidencia hay y cómo se vuelve atrás?
> **Dueño:** agente `datos` · **Fecha:** 2026-11-01 · **Migración:** `supabase/migrations/0028_retiro_public.sql`
> **Entorno:** Supabase local (PostgreSQL 17.11, contenedor `supabase_db_TRANSTEI`),
> datos ficticios. **Autorización:** el dueño autorizó la Ola E completa
> (incluido el `DROP`) el 2026-11-01; riesgo clasificado **Alto (destructivo)**.
> **Caduca si:** se aplica otra migración sobre `public`, se restaura el backup o
> se cambia el rol de aplicación.
> **Re-verificar con:** `supabase/tests/0028_01_retiro_public.sql` y
> `supabase/tests/0028_02_mutacion.sh`.

---

## 1. Resultado

Se borraron **todos los objetos propios de `public`**: 17 tablas, 8 `enum`,
2 funciones y el trigger de identidad `on_auth_user_created` de `auth.users`.
El esquema `public` **se conserva vacío** (PostgREST y `supabase/config.toml` lo
esperan) y la extensión `btree_gist` **se conserva** porque de ella dependen los
4 `EXCLUDE` del núcleo.

No es `DROP SCHEMA public`: eso habría arrastrado `btree_gist` y las garantías
`INV-D07`/`INV-CFG02`.

---

## 2. Alcance y autorización

| Fuente | Qué dice |
|---|---|
| `ADR-0002` §6.7 | E.5 = "`DROP SCHEMA public` (o archivo de solo lectura)"; exige ADR destructivo, backup verificado, restore drill, ventana y autorización dueño + contador |
| Instrucción del dueño (2026-11-01) | Autoriza **la Ola E completa** sobre base local con datos ficticios; backup existente declarado |
| `AGENTS.md` §8/§10 | Migraciones forward-only; operación destructiva solo con autorización explícita; `DROP` reportado con conteos |

**Decisión registrada:** se ejecuta el `DROP` de los **objetos** de `public` sin
borrar el esquema, porque `btree_gist` vive ahí (§6). El `DROP SCHEMA` del ADR no
se ejecuta: quedará como decisión de `arquitectura` si algún día se mueve la
extensión a `extensions`.

---

## 3. Inventario medido antes del `DROP`

Medido el 2026-11-01 con `psql` sobre `supabase_db_TRANSTEI` (nivel 🟢), antes de
aplicar `0028`.

### 3.1 Objetos

| Tipo | Cantidad | Detalle |
|---|---|---|
| Tablas | 17 | `_migraciones`, `ajustes_liquidacion`, `anticipos_chofer`, `choferes`, `clientes`, `configuracion`, `factura_viaje`, `facturas`, `gastos_viaje`, `kpis`, `liquidaciones`, `mantenimientos`, `pautas_mantenimiento`, `ramplas`, `tractos`, `usuarios`, `viajes` |
| Índices | 37 | 17 PK + 7 `UNIQUE` (`choferes_rut_key`, `clientes_rut_key`, `ramplas_patente_key`, `tractos_patente_key`, `liquidaciones_chofer_id_mes_key`, `facturas_numero_sii_cliente_id_key`, `usuarios_auth_id_key`) + 13 `idx_*` |
| FKs | 15 | 14 `public → public` + 1 `public.usuarios → auth.users` |
| Triggers | 11 | 10 `trg_*_updated` (uno por tabla con `updated_at`) + `on_auth_user_created` en `auth.users` |
| Políticas RLS | 1 | `usuarios: "leer propio perfil"` (SELECT) |
| `enum` | 8 | `categoria_gasto`, `estado_factura`, `estado_liquidacion`, `estado_viaje`, `rol_usuario`, `tipo_ajuste`, `tipo_factura`, `tipo_rampla` |
| Funciones | 2 | `public.handle_new_user()` (firma real: **sin argumentos**), `public.set_updated_at()` |
| Secuencias / vistas / dominios | 0 | — |
| Extensión en `public` | 1 | `btree_gist` 1.7 (se **conserva**) |
| Tamaño agregado | 600 kB | `sum(pg_total_relation_size)` de las 17 tablas |

### 3.2 Conteos de filas (P5) y comparación con el backup

| Tabla | Filas en base | Filas en el backup | Δ |
|---|---:|---:|---:|
| `_migraciones` | 0 | 0 | 0 |
| `ajustes_liquidacion` | 0 | 0 | 0 |
| `anticipos_chofer` | 0 | 0 | 0 |
| `choferes` | 3 | 3 | 0 |
| `clientes` | 3 | 3 | 0 |
| `configuracion` | 4 | 4 | 0 |
| `factura_viaje` | 0 | 0 | 0 |
| `facturas` | 0 | 0 | 0 |
| `gastos_viaje` | 0 | 0 | 0 |
| `kpis` | 4 | 4 | 0 |
| `liquidaciones` | 0 | 0 | 0 |
| `mantenimientos` | 0 | 0 | 0 |
| `pautas_mantenimiento` | 6 | 6 | 0 |
| `ramplas` | 3 | 3 | 0 |
| `tractos` | 3 | 3 | 0 |
| `usuarios` | 10 | 10 | 0 |
| `viajes` | 0 | 0 | 0 |
| **Total** | **36** | **36** | **0** |

Método del backup: `awk` sobre los bloques `COPY public.<tabla> … \.` de
`backups/cutover_pre_20261101_115202.sql` → 17 bloques `COPY`, 36 filas.
**Cero diferencia**: no hubo escrituras en `public` entre el backup y el `DROP`,
lo que satisface el criterio "backup verificado ⇒ restore reproduce el estado".

El `NOTICE` del bloque P5 quedó en el log de la aplicación (no se captura en la
salida de `supabase migration up`). La corrida en seco de la misma migración
(`commit` → `rollback`) sí los imprimió:

```text
NOTICE:  CONTE0 public.choferes = 3 filas
NOTICE:  CONTE0 public.clientes = 3 filas
NOTICE:  CONTE0 public.configuracion = 4 filas
NOTICE:  CONTE0 public.kpis = 4 filas
NOTICE:  CONTE0 public.pautas_mantenimiento = 6 filas
NOTICE:  CONTE0 public.ramplas = 3 filas
NOTICE:  CONTE0 public.tractos = 3 filas
NOTICE:  CONTE0 public.usuarios = 10 filas
NOTICE:  CONTE0 total: 36 filas en public, 600 kB
```

---

## 4. Precondiciones ejecutadas (deben dar 0)

Ejecutadas el 2026-11-01 antes de aplicar, y **re-ejecutadas dentro de la
migración** (abortan con `23514` si fallan).

| # | Detección | Resultado |
|---|---|---|
| **P0** | Backup declarado y verificado | `backups/cutover_pre_20261101_115202.sql`, 2.180.084 bytes, `sha256 fbdd07c9…d342c19f`, `^COPY public.` = **17** bloques, 36 filas |
| **P1** | FKs desde **fuera** de `public` hacia `public` | **0**. Las 15 FKs existentes son `public→public` (14) y `public→auth.users` (1); `nucleo` no tiene ninguna FK a `public` |
| **P2** | Vistas/materialized views fuera de `public` que dependan de `public` | **0** |
| **P3** | Columnas de otros esquemas con tipo **no-extension** de `public` | **0**. Las únicas columnas de `nucleo` con tipo de `public` son `gbtreekey32`/`gbtreekey_var` de las 4 relaciones de índice de `btree_gist` (extension, excluidas por diseño) |
| **P4** | Funciones de otros esquemas que dependan de funciones/tipos de `public` | **0** fuera de `realtime` (que solo menciona `public.` como cadena en SQL dinámico, sin dependencia registrada) |
| **P5** | Conteo por tabla antes del `DROP` | 36 filas (tabla §3.2) |

Además, en la base: **0** dependencias registradas en `pg_depend` de `nucleo`
hacia relaciones de `public` (solo las TOAST propias de cada tabla).

---

## 5. Qué hace la migración

`supabase/migrations/0028_retiro_public.sql`, una sola transacción:

1. **P1–P4** en `do $$ … $$` que abortan con `23514` y listan el objeto culpable.
2. **P5**: `raise notice 'CONTE0 public.<tabla> = <n> filas'` + total.
3. `drop trigger if exists on_auth_user_created on auth.users;`
   (el nombre real del trigger **no** es `handle_new_user`; ver `0001:261-262`)
   y `drop function if exists public.handle_new_user();`.
4. 17 × `drop table if exists public.<tabla> cascade;` con `CASCADE` acotado por
   P1–P4 (no arrastra objetos de otro esquema).
5. `drop function public.set_updated_at()` + 8 × `drop type` **sin** `CASCADE`
   (si algo dependiera, la migración aborta en vez de arrastrarlo).
6. Defecto seguro del esquema: `revoke usage on schema public from public;` y
   `grant usage` explícito a `postgres`, `service_role`, `anon`, `authenticated`
   y `authenticator`. Consecuencia: `tei_app` (rol de la aplicación) queda **sin**
   `USAGE` en `public` ⇒ `42501`, no `42P01`.
7. Verificación **V1–V6** dentro de la transacción (aborta si el estado no es el
   buscado): 0 relaciones propias, 0 funciones propias, 0 `enum` propios,
   `auth.users` sin `on_auth_user_created`, esquema `public` presente,
   `btree_gist` instalada y los 4 `EXCLUDE` de `nucleo` intactos.

**Idempotente:** todo es `if exists`; los conteos se calculan sobre lo que haya.
Re-aplicar no cambia nada.

### 5.1 Desviación respecto de la instrucción literal (declarada)

La instrucción pedía `drop trigger if exists handle_new_user on auth.users`. El
trigger se llama **`on_auth_user_created`** (`0001:261`); `handle_new_user` es la
**función**. Se dropea el trigger por su nombre real y luego la función.

La instrucción no pedía tocar los privilegios del esquema. Se añadió el `REVOKE`
por dos razones verificadas:

1. **Mantiene una garantía existente:** `backend/tests/test_agente_o2_1_integracion.py:713`
   exige que `tei_app` reciba `42501` al tocar `public`. Con el `GRANT` implícito
   de PostgreSQL 15+ (`=U/pg_database_owner`), tras el `DROP` la respuesta habría
   pasado a `42P01` (probado: sin `USAGE`, incluso una tabla inexistente da
   `42501`; con `USAGE`, da `42P01`).
2. **Defecto seguro:** un esquema sin objetos no necesita `USAGE` para nadie; los
   roles de Supabase lo conservan explícitamente para que PostgREST siga
   funcionando igual.

Se probó que **no rompe** el uso de `btree_gist` por `tei_app`: los `EXCLUDE`
llaman a la `opclass` por OID, no por nombre (`0028_01` §E inserta en
`nucleo.configuracion_empresa` como `tei_app` y pasa).

---

## 6. Por qué `public` no queda literalmente vacío

`btree_gist` está instalada **en `public`** (`0004_nucleo_operacional.sql:28`,
`create extension if not exists btree_gist` sin `SCHEMA`), y de ella dependen:

| Constraint | Tabla | Invariante |
|---|---|---|
| `ex_reserva_tracto`, `ex_reserva_rampla`, `ex_reserva_chofer` | `nucleo.reservas_recurso` | `INV-D07` / libro de ocupación |
| `ex_config_vigencia` | `nucleo.configuracion_empresa` | `INV-CFG02` (vigencias no se solapan) |

Borrar o mover esa extensión es una decisión de `arquitectura`, no de este
retiro. **Consecuencia declarada:** `public` conserva ~190 funciones/operadores
de soporte de `btree_gist` (tipos `gbtreekey*`, `gbt_*`). Ninguna es del ERP.

---

## 7. Verificación posterior (evidencia)

### 7.1 Estado de la base

```text
$ docker exec supabase_db_TRANSTEI psql -U postgres -d postgres -c "select count(*) from pg_tables where schemaname='public';"
 public_tablas
---------------
             0

$ … -c "select count(*) from supabase_migrations.schema_migrations;"
 28

$ … -c "select tgname from pg_trigger where tgrelid='auth.users'::regclass and not tgisinternal;"
 (0 rows)

$ … -c "select count(*) from pg_tables where schemaname='nucleo';"
 46

$ … -c "select count(*) from pg_constraint where contype='x' and connamespace='nucleo'::regnamespace;"
 4

$ … -c "select r, has_schema_privilege(r,'public','USAGE') from unnest(array['tei_app','postgres','anon','authenticated','service_role']) r;"
 tei_app       | f
 postgres      | t
 anon          | t
 authenticated | t
 service_role  | t
```

### 7.2 Prueba del mecanismo y prueba de mutación

```text
$ docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d postgres \
    -v ON_ERROR_STOP=1 < supabase/tests/0028_01_retiro_public.sql
NOTICE:  OK 0028-1A public sin relaciones, funciones ni tipos propios
NOTICE:  OK 0028-1B sin handle_new_user ni trigger en auth.users
NOTICE:  OK 0028-1C btree_gist + 4 EXCLUDE (3 de reservas_recurso) intactos
NOTICE:  OK 0028-1D tei_app => public.viajes da 42501
NOTICE:  OK 0028-1E tei_app insertó en nucleo.configuracion_empresa (EXCLUDE gist)
NOTICE:  OK 0028-1F esquema public conservado; bucket respaldos intacto
0028-1: OK (rollback; 0 filas residuales)

$ ./supabase/tests/0028_02_mutacion.sh
== [1/6] 0028_01 sin mutación: debe pasar
OK: 0028_01 pasa (base sin legacy)
== [3/6] 0028_01 con la tabla mutada: debe fallar
OK: 0028_01 falló como debía (exit 3)
ERROR:  FALLO 0028-1A: 1 relación(es) propias en public
== [5/6] 0028_01 con la función mutada: debe fallar
OK: 0028_01 falló como debía (exit 3)
ERROR:  FALLO 0028-1A: 1 función(es) propias en public
== [6/6] limpiando artefactos y repitiendo: debe pasar
OK: 0028_01 pasa de nuevo
0028-2: OK (la prueba detecta el legacy recreado y se recupera)
```

La mutación **prueba que la prueba prueba algo**: si alguien recrea una tabla o
una función en `public`, `0028_01` falla.

### 7.3 La única lectura `nucleo → public` del backend degrada bien

`backend/app/nucleo/servicio_cutover.py:97` cuenta `public.viajes` dentro de
`try/except`. Sonda de solo lectura
(`supabase/tests/0028_03_cutover_estado.py`, como `tei_app` en el engine del
núcleo y `postgres` en el engine legacy):

```text
sqlalchemy.exc.ProgrammingError: (psycopg.errors.UndefinedTable)
    relation "public.viajes" does not exist
legacy_escritura_congelada = False
legacy_viajes_abiertos     = 0
nucleo_viajes              = 0
mensaje                    = Escritura legacy ABIERTA: aún se puede escribir en el sistema anterior.
```

`estado()` responde igual; el conteo cae a 0 con `warning`. **No rompe** el
endpoint, pero **deja de informar** el número de viajes legacy abiertos: es una
lectura que ya no puede tener valor distinto de 0 y debería eliminarse del
servicio (handoff a `backend`, §10). El E2E lo confirma desde la UI real
(prueba 11, `cutover: estado actual y runbook`).

### 7.4 Idempotencia (re-aplicar no cambia nada)

La misma migración ejecutada otra vez sobre la base ya retirada (con `commit`
cambiado a `rollback` para no dejar rastro):

```text
NOTICE:  P1-P4 OK: 0 FKs, 0 vistas, 0 columnas y 0 funciones de otros esquemas dependen de public
NOTICE:  CONTE0 total: 0 filas en public, 0 kB
NOTICE:  trigger "on_auth_user_created" for relation "auth.users" does not exist, skipping
NOTICE:  table "viajes" does not exist, skipping
   … (las 17 tablas, 2 funciones y 8 tipos: "does not exist, skipping")
NOTICE:  V1-V6 OK: public sin objetos propios, auth.users sin trigger, nucleo con sus 4 EXCLUDE
ROLLBACK
```

### 7.5 Backend vivo después del retiro

```text
$ curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health
200
$ curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/openapi.json
200
```

Login y núcleo: cubiertos por `make test` (`test_f2_ola_e1_identidad.py`: `/auth/me`
200 para TEI y TES desde el JWT) y por 19 de las 20 pruebas E2E.

---

## 8. Pruebas y estado de las suites

| Comando | Antes de `0028` | Después de `0028` |
|---|---|---|
| `make unit` | 128 passed, exit 0 | **128 passed, exit 0** |
| `make test` | 404 passed, 2 warnings, **0 skipped**, exit 0 | **404 passed, 2 warnings, 0 skipped, exit 0** |
| `make test-db` | exit 0 (`migraciones=27`, `public_tablas=17`) | **exit 0** (`migraciones=28`, `nucleo_tablas=46`, `public_tablas=0`) |
| `make db-reset` | — | **exit 0**: aplica `0001`–`0028`, `Seed local OK`, `Segundo tenant listo` |
| `make e2e` | no ejecutado en esta sesión | **20 passed (25.9 s), exit 0** |

`make db-reset` reproduce el estado de punta a punta: 28 migraciones, 0 tablas en
`public`, 46 en `nucleo`, 4 `EXCLUDE`, `auth.users` sin trigger, `tei_app` sin
`USAGE` en `public`. No imprimió ningún error ni aviso de dependencia oculta a
`public`.

### 8.1 E2E (`make e2e`, tras `make db-reset`)

```text
Running 20 tests using 1 worker
  ✓   1 … login cae en tablero del dueño y briefing
  ✓   2 … comercial: tarifas, OC y centros de costo
  ✓   3 … despacho: mesa y disponibilidad
  ✓   4 … expediente: lista y detalle con QR
  ✓   5 … maestros: reemplaza flota, clientes y choferes retirados
  ✓   6 … rentabilidad: reemplaza los KPIs retirados
  ✓   7 … cobranza: factura del seed y aging
  ✓   8 … auditoría: filtros y registros
  ✓   9 … permisos: matriz de 8 roles
  ✓  10 … PWA del conductor: login y mi viaje
  ✓  11 … cutover: estado actual y runbook      ← ejercita servicio_cutover.estado()
  ✓  12 … las 9 rutas retiradas responden 308
  ✓  13 … la raíz redirige 307 al tablero
  ✓  14 … TEI: menú con 17 ítems del núcleo
  ✓  15 … TES: login y menú del núcleo
  ✓  16 … mantenimiento: estado y pauta del servidor
  ✓  17 … iva: resumen de IVA débito del mes
  ✓  18 … liquidaciones: mes en curso desde el núcleo
  ✓  19 … configuración: valores vigentes del servidor
  ✓  20 … los 11 routers legacy responden 404 y el núcleo sigue montado
  20 passed (25.9s)
e2e exit=0
```

La prueba 11 es la que más importa aquí: recorre el endpoint de cutover con
`public` ya borrado y pasa (confirma §7.3 desde la UI/API real).

---

## 9. Rollback

**No hay rollback SQL.** Los datos se destruyen; `DROP TABLE` no se deshace.

| Paso | Acción |
|---|---|
| 1 | **No** ejecutar `supabase db reset`: re-aplicaría `0028`. |
| 2 | Crear base vacía y restaurar `backups/cutover_pre_20261101_115202.sql` (contiene `public` completo + `nucleo` + `auth` + `storage`). |
| 3 | Si la restauración es parcial: re-aplicar `0001`–`0027` antes de cargar `public`. |
| 4 | Re-crear `tei_app` / credenciales si la base es nueva (`scripts/bootstrap_db_roles.sh`). |

**Riesgo residual:** toda fila escrita en `public` después del backup se pierde.
Medido: Δ = 0 filas entre backup y `DROP` (§3.2). Además, restorear el backup
devuelve **también** `public.usuarios` y el trigger de identidad: el estado
vuelve a la Ola D, no a la Ola E.

---

## 10. Riesgos, residuos y handoff

| ID | Riesgo / residuo | Evidencia | Destinatario |
|---|---|---|---|
| RET-E2-01 | `nucleo/servicio_cutover.py:97` sigue leyendo `public.viajes` (fail-soft: cae a 0 con `warning`). Queda una lectura muerta que miente si alguien la lee como dato | §7.3 | `backend` (quitar el conteo legacy) |
| RET-E2-02 | `scripts/cutover_legacy.py` conserva lecturas de `public.*`; solo tiene guard en `:142` (`to_regclass('public.clientes')`). Con `public` vacío el script sale por el guard, pero las demás consultas (`:104,152,186,228,275,320,393`) quedan como código muerto | `scripts/cutover_legacy.py` | `orquestador`/`backend` (retirar el script o archivarlo) |
| RET-E2-03 | `supabase/tests/0024_99_rollback.sql:101`, `0025_99_rollback.sql:115` y `0026_99_rollback.sql:86` **afirman que las tablas legacy siguen existiendo** ("no debía tocarse"). Ya no son ejecutables: son verificaciones de rollback de las migraciones de la Ola B y quedan como registro histórico fechado. **No se reescribieron** | `grep -n "public\." supabase/tests/002[456]_99_rollback.sql` | `qa`/`datos` (renombrar o marcar obsoletos) |
| RET-E2-04 | El middleware de congelamiento y `nucleo.cutover_control` siguen en pie (E.3). Tras `make db-reset` el flag vuelve a **abierto** (`legacy_escritura_congelada=false`), lo que ya es inerte: no hay tablas ni rutas legacy | §7.3 | `backend`/`arquitectura` |
| RET-E2-05 | `public` conserva los objetos de `btree_gist`. Un `DROP SCHEMA public` (E.5 del ADR) rompería `INV-D07` e `INV-CFG02` | §6 | `arquitectura` (ADR si se quiere mover la extensión) |
| RET-E2-06 | El bucket `respaldos` de Storage y su contenido no se tocaron; sigue siendo la copia fuera de la base | `0028_01` §F | — |
| RET-E2-07 | `tei_app` ya no tiene `USAGE` en `public`: si algún día se crea un objeto ahí sin `GRANT`, el backend recibirá `42501` (defecto seguro por diseño) | §5.1 | `datos` |

### 10.1 Lo que **no** se verificó

- **Restore drill completo** del backup sobre una base vacía (no ejecutado en esta
  sesión: `make restore-drill` usa otra ruta y no estaba en el alcance). Queda 🔴.
- **Restauración del backup como prueba de rollback real**: se verificó su
  contenido (17 bloques `COPY`), no se restauró.
- **E2E** antes de esta migración no se ejecutó; el verde posterior no se compara
  contra una línea base previa en esta sesión.
- **Producción/staging**: nada de esto se ejecutó fuera de la base local.

---

## 11. Artefactos creados

| Archivo | Qué es |
|---|---|
| `supabase/migrations/0028_retiro_public.sql` | la migración (forward-only, idempotente) |
| `supabase/tests/0028_01_retiro_public.sql` | prueba del mecanismo (A–F, con `ROLLBACK`) |
| `supabase/tests/0028_02_mutacion.sh` | prueba de mutación (recrea legacy ⇒ debe fallar) |
| `supabase/tests/0028_03_cutover_estado.py` | sonda: `ServicioCutover.estado()` sin `public.viajes` |
| `docs/datos/retiro-public.md` | este documento |
| `docs/datos/catalogo-migraciones.md` | filas `0027` y `0028` + adenda de estado git |
| `docs/datos/invariantes.md` | §13: `INV-LEG01`–`INV-LEG03` |
