# RLS multiempresa real en `nucleo` — diseño, decisión y evidencia

> **Pregunta que responde:** ¿cómo se impone en PostgreSQL que la aplicación solo
> lea y escriba filas de la empresa del request, y qué falta para que eso esté en
> vigor?
> **Dueño:** agente `datos` · **Fecha:** 2026-10-30 · **Riesgo:** ALTO (aislamiento
> multiempresa)
> **Método:** lectura de `supabase/migrations/0001`–`0019`, `backend/app/**` y
> `docs/qa/informes/f0-wp3-deriva-modelo.md`; migración `0020` aplicada **solo** en
> el clon desechable `tei_test` y probada con `psql` como `tei_app`, `postgres`,
> `supabase_admin` (contenedor `supabase_db_TRANSTEI`). Salidas reales pegadas.
> **Caduca si:** se aplica `0020` en otra base, cambia el rol de conexión del
> backend, se agrega una tabla a `nucleo` o se edita una política.
> **Estado:** 🟢 diseñada y probada en `tei_test` · 🔴 **no aplicada** a la base de
> la app · 🔴 **no vigente** para la app mientras conecte como `postgres`.
>
> **Nota de entorno:** durante esta sesión `tei_test` fue **recreada** (los viajes
> pasaron de 553 a 42 y desaparecieron las políticas recién creadas). Causa
> identificada 🟢: `scripts/test_db_reset.sh` (artefacto de otro agente) hace
> `DROP DATABASE … WITH (FORCE)` + `pg_dump --no-privileges` desde la base de la
> app. Consecuencias: (i) **re-ejecutar ese script borra `0020` de `tei_test`** —
> hay que volver a aplicarla; (ii) el clon no trae los `GRANT` de `service_role`
> (§1). Se re-aplicó `0020` y se repitieron todas las pruebas; las cifras de §7 son
> una foto con hora y las pruebas no dependen de conteos absolutos. Ver §9.

---

## 0. Resumen

`nucleo` tenía RLS habilitado en 31/31 tablas con **0 políticas** y **0 `FORCE`**,
y el backend conecta como `postgres` (`rolbypassrls = t`): el RLS no hacía nada.
La migración `0020` agrega las tres piezas que faltaban:

1. **rol** `tei_app` (LOGIN, NOINHERIT, NOSUPERUSER, **NOBYPASSRLS**, sin dueño de
   nada, sin contraseña en el repo);
2. **contexto por transacción** `app.empresa_id` vía `set_config(…, true)`;
3. **35 políticas** `USING` + `WITH CHECK` sobre 31 tablas, con `FORCE RLS`.

Probado con dos conexiones reales y con mutación: sin contexto ⇒ 0 filas; con
contexto de A ⇒ solo A; INSERT con empresa ajena ⇒ `42501`; el aislamiento
desaparece si se le da `BYPASSRLS` al rol o `USING (true)` a la política.
**Nada de esto protege a la app hasta que el backend cambie de rol** (§8).

---

## 1. Contexto verificado en esta sesión (no heredado)

| Hecho | Evidencia | Certeza |
|---|---|---|
| 31 tablas en `nucleo`, 31 con `rowsecurity = true`, **0 con `FORCE`**, dueño `postgres` | `pg_class`/`pg_namespace` en `postgres` y `tei_test` | 🟢 |
| 0 políticas en `nucleo` (antes de 0020) | `select count(*) from pg_policies where schemaname='nucleo'` → `0` | 🟢 |
| `postgres`: `rolsuper=f`, `rolbypassrls=t`; `service_role`: `rolbypassrls=t`; `authenticated`/`anon` sin login | `pg_roles` | 🟢 |
| El backend conecta como el rol de `DATABASE_URL`; `create_engine(settings.DATABASE_URL, pool_pre_ping=True)` | `backend/app/core/database.py:21-22` | 🟢 |
| `nucleo` solo tiene `USAGE` para `postgres` y `service_role` | `pg_namespace.nspacl`; `0004:1886` | 🟢 |
| 28 tablas tienen `empresa_id`; **sin** `empresa_id`: `empresas`, `transiciones_viaje`, `cutover_control`; `auditoria.empresa_id` es **nullable** | `information_schema.columns` | 🟢 |
| Toda tabla con `empresa_id` tiene un índice cuyo primer campo es `empresa_id` | `pg_index` (precondición P3 → 0 filas) | 🟢 |
| `public` tiene 17 tablas con `RLS` habilitado y **1 sola política** (`public.usuarios`) | `pg_class`, `pg_policies` | 🟢 |
| Los servicios hacen `session.commit()` a mitad de request (p. ej. `servicio_maestros.py:125,201`, `servicio_facturacion.py:610`) | `grep` | 🟢 |
| `get_contexto_empresa` consulta `usuarios_empresa` **antes** de fijar cualquier contexto | `backend/app/nucleo/deps.py:55-61` | 🟢 |
| `GET /nucleo/mis-empresas` no recibe `X-Empresa-ID` | `backend/app/nucleo/api.py:69-76` | 🟢 |

Contradicción con el clon: `tei_test` **no** trae los `GRANT` de `service_role`
(`relacl` de `nucleo.viajes` en `tei_test` = `{supabase_admin=…,postgres=…}`; en la
base de la app = `{postgres=…,service_role=arw/postgres}`). Explicado 🟢:
`scripts/test_db_reset.sh:29-31` copia con `pg_dump --no-owner --no-privileges`. Es
un clon parcial: sirve para RLS, no para verificar privilegios de `service_role`.

---

## 2. Decisión

**Se adopta (a): rol dedicado `tei_app` sin `BYPASSRLS` + GUC `app.empresa_id` por
transacción.** Es la única opción que (i) impone el aislamiento en la base,
(ii) no depende de la identidad de conexión que hoy usan seeds, scripts y cutover,
y (iii) se apoya en el mecanismo que el backend ya usa (`set_config(…, true)`).

Alternativa aceptada solo para el **legacy**: el rol actual (`postgres`) sigue
atendiendo `public` desde otro engine, porque `public` no tiene `empresa_id` y 17
de sus tablas devolverían 0 filas a un rol sin `BYPASSRLS` (§8.3).

### 2.1 Opciones evaluadas

| Criterio | (a) `tei_app` + GUC `app.empresa_id` | (b) seguir con `postgres` + `FORCE RLS` | (c) `tei_app` + claims JWT (`auth.jwt()`) |
|---|---|---|---|
| Impone aislamiento | Sí (probado §7) | **No** | Sí |
| Por qué no | — | `postgres` tiene `rolbypassrls=t`; **BYPASSRLS gana sobre FORCE** (probado §7.4). Las políticas quedarían decorativas | — |
| Requiere cambiar el rol de conexión | Sí (handoff) | No | Sí |
| Complejidad de propagación | Baja: un `set_config` por transacción, ya usado por el repo | Nula, pero no sirve | Alta: hay que llevar el JWT crudo hasta la conexión; el backend ya valida el token y **no** lo pasa a PostgreSQL |
| Multiempresa real | El claim no contiene la empresa: un usuario puede tener varias y el request la elige por `X-Empresa-ID` (validada contra `usuarios_empresa`) | — | El JWT de Supabase no dice qué empresa: habría que firmar un claim propio o consultar igual |
| Pooler en modo transacción | Seguro con `SET LOCAL` + re-aplicación por transacción (§8.2) | — | Igual de frágil; `auth.jwt()` lee `request.jwt.claims`, o sea otro GUC: mismo mecanismo con más piezas |
| Compatibilidad con el pool SQLAlchemy | Alta (`after_begin`, §8.2) | — | Media (token por request en el evento) |
| Riesgo de configuración | Medio: el GUC es controlable por quien pueda ejecutar SQL (ver §9.1) | Bajo | Medio |
| Verdicto | **Elegida** | Descartada | Descartada |

`ALTER ROLE postgres NOBYPASSRLS` (variante de (b)) también se descartó: `postgres`
es el rol de seeds, scripts, cutover, backups y del propio tooling de Supabase; un
solo rol para todo anula la separación de privilegios y un fallo de configuración
deja la base inoperable.

---

## 3. Diseño de `0020`

### 3.1 Rol

```
tei_app: LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE
         NOREPLICATION  ·  sin contraseña en la migración
```

- Sin contraseña a propósito: es un secreto de despliegue
  (`ALTER ROLE tei_app PASSWORD '…'` fuera del repo). En local se entra por
  socket/TCP con `trust`.
- `NOINHERIT` no cambia nada hoy (no tiene membresías) y evita que un `GRANT rolsuper TO tei_app` futuro herede privilegios en silencio.
- **No es dueño de ninguna tabla**: por eso las políticas le aplican sin depender
  de `FORCE`.

### 3.2 Contexto

| GUC | Quién lo fija | Para qué |
|---|---|---|
| `app.empresa_id` | backend, por request, `set_config(…, true)` | **nuevo**: empresa del request |
| `nucleo.auth_id` | backend (ya se usa en 9 servicios) | auditoría y `mis-empresas` |
| `nucleo.request_id` | backend | trazabilidad (sin uso en políticas) |

Funciones auxiliares (tolerantes: GUC ausente o basura ⇒ `NULL`, nunca `22P02`):

```sql
nucleo.ctx_empresa()   -- uuid | null  (lee app.empresa_id)
nucleo.ctx_auth_id()   -- uuid | null  (lee nucleo.auth_id)
nucleo.empresas_del_usuario() -- setof uuid, SECURITY DEFINER, EXECUTE solo tei_app
```

`empresas_del_usuario()` deriva el usuario **del GUC, nunca de un parámetro**:
aceptar un `auth_id` como argumento sería un enumerador de tenants.

### 3.3 Políticas (35 sobre 31 tablas)

| Grupo | Tablas | Política |
|---|---|---|
| Tenant (25 tablas) | todo lo que tiene `empresa_id` salvo las 3 especiales | `tenant_empresa FOR ALL USING (empresa_id = ctx_empresa()) WITH CHECK (…)` |
| `empresas` | 1 | `empresas_lectura FOR SELECT USING (id = ctx OR id IN (empresas_del_usuario()))` + `empresas_escritura FOR ALL USING/WITH CHECK (id = ctx)` |
| `usuarios_empresa` | 1 | `…_lectura FOR SELECT USING (empresa_id = ctx OR auth_id = ctx_auth_id())` + `…_escritura FOR ALL (empresa_id = ctx)` |
| `auditoria` | 1 | `auditoria_lectura FOR SELECT (empresa_id = ctx)` + `auditoria_insercion FOR INSERT WITH CHECK (empresa_id = ctx)` |
| `transiciones_viaje` | 1 | `transiciones_lectura FOR SELECT USING (true)` — catálogo global |
| `cutover_control` | 1 | `cutover_lectura FOR SELECT (true)` + `cutover_actualizacion FOR UPDATE (true)` |
| `FORCE ROW LEVEL SECURITY` | 31 | activado (defensa en profundidad, §7.4) |

Todas las políticas son `TO PUBLIC`: cualquier rol futuro con `GRANT` sobre
`nucleo` queda filtrado automáticamente; un rol sin `GRANT` no ve nada. Los dos
caminos son fail-closed; `PUBLIC` evita el olvido al crear un rol nuevo.

### 3.4 Casos especiales y por qué

| Tabla | Situación | Decisión | Consecuencia declarada |
|---|---|---|---|
| `empresas` | sin `empresa_id`; PK `id` | lectura: empresa actual **o** empresas del usuario; escritura: solo la actual | **El alta de una empresa no es operación de la app** (`WITH CHECK id = ctx`). La hacen seed/cutover con rol privilegiado |
| `usuarios_empresa` | necesaria **antes** de tener empresa (`deps.py:55`) y en `mis-empresas` | lectura: empresa actual **o** `auth_id` propio | El usuario puede leer sus propias membresías (no las de otros). Escritura solo en la empresa actual |
| `auditoria` | `empresa_id` nullable, append-only | SELECT/INSERT con `empresa_id = ctx` | Las filas con `empresa_id IS NULL` (hoy 0) quedan visibles solo para el dueño. `UPDATE`/`DELETE` no se otorgan |
| `transiciones_viaje` | catálogo global, 3 columnas, sin empresa | solo `SELECT` | Las migraciones lo administran; la app no puede insertar estados |
| `cutover_control` | fila única de control global (`id boolean`) | `SELECT` + `UPDATE` | La app no puede crear ni borrar la fila. La autorización (rol admin) es del backend |
| `reservas_recurso` | FK simple `viaje_id` (INV-T02) | política por **su** `empresa_id` | No hay fuga: una reserva solo se ve desde su empresa. La FK simple sigue siendo deuda **de integridad**, no de aislamiento (§9.3) |

### 3.5 GRANTs

Se copia el conjunto que **hoy** tiene `service_role` en la base de la app
(`0004:1886-1893`, `0007:257-269`; contrastado con `pg_class.relacl` en la base de
la app —muestra `nucleo.viajes = {postgres=arwdDxtm, service_role=arw}`— y con
`grep` de `GRANT … DELETE` en `0001`–`0019`: **no hay ninguno**): `USAGE`
del esquema, `SELECT/INSERT/UPDATE` en todas las tablas, **sin `DELETE` en
ninguna**, y `SELECT/INSERT` solamente en `auditoria` y `viaje_eventos`. Encima:

- `transiciones_viaje`: solo `SELECT`; `cutover_control`: `SELECT` + `UPDATE`;
- `EXECUTE` en funciones del esquema; `empresas_del_usuario()` revocada de
  `PUBLIC` y otorgada solo a `tei_app`;
- `USAGE, SELECT` en secuencias (`nucleo.auditoria_id_seq`).
- Sin `ALTER DEFAULT PRIVILEGES`: una tabla nueva **no** queda accesible para
  `tei_app` hasta que una migración le dé `GRANT` + política. Es el defecto
  seguro; se documenta como tarea de cada migración futura.

---

## 4. Cómo se fija el contexto por request (diseño para `backend`)

**No implementado** (fuera de mi alcance). El diseño que satisface el pool y los
`commit()` intermedios:

```python
# backend/app/core/database.py  (boceto, handoff)
from sqlalchemy import event
from sqlalchemy.orm import Session

@event.listens_for(Session, "after_begin")
def _contexto_por_transaccion(session, transaction, connection):
    empresa = session.info.get("empresa_id")
    auth_id = session.info.get("auth_id")
    # set_config(..., true) = SET LOCAL: muere con la transacción
    if empresa:
        connection.exec_driver_sql(
            "select set_config('app.empresa_id', %s, true)", (empresa,))
    if auth_id:
        connection.exec_driver_sql(
            "select set_config('nucleo.auth_id', %s, true)", (auth_id,))
```

y en la dependencia, **antes** de la primera consulta (incluida la validación de
membresía) se llena `session.info`:

```python
def get_session(x_empresa_id: UUID | None = Header(None, alias="X-Empresa-ID")):
    with Session(get_engine()) as session:
        session.info["empresa_id"] = str(x_empresa_id) if x_empresa_id else None
        yield session
```

Por qué `after_begin` y no un `execute` suelto: el GUC `SET LOCAL` **muere en el
`COMMIT`** (probado, §7.3) y los servicios commitean a mitad de request
(`servicio_maestros.py:125`, `servicio_facturacion.py:610`, …). Un `set_config`
hecho una sola vez al inicio deja la segunda mitad del request con 0 filas.

**Qué pasa si falta `app.empresa_id`:** 0 filas en toda tabla de tenant, sin error
de sintaxis ni de permisos. Es fail-closed y es lo que se quiere: la ausencia de
contexto se comporta como "no hay empresa", no como "hay todas". El backend debe
traducirlo a 403/404 (nunca 500) y **no** filtrar si el registro existe.

**Orden dentro del request** (`deps.py`): hoy `get_contexto_empresa` valida la
membresía antes de fijar nada. Con RLS, `usuarios_empresa` solo se ve si
`app.empresa_id` (o `nucleo.auth_id`) ya está fijado ⇒ el GUC debe fijarse con el
`X-Empresa-ID` **antes** de esa consulta. Es seguro: el header es no confiable,
pero RLS solo lo usa para **acotar**; la autorización sigue siendo la membresía
activa + estado de la empresa.

---

## 5. Migración `0020_rls_multiempresa.sql`

Archivo: `supabase/migrations/0020_rls_multiempresa.sql` (nuevo, forward-only).
Estructura: rol → funciones de contexto → GRANTs → políticas de tenant (bucle
sobre catálogo) → políticas especiales → `FORCE` → `COMMENT`. Todo en **una
transacción**.

### 5.1 Precondiciones (ejecutadas en `tei_test`; salida real)

| # | Consulta | Resultado 2026-10-30 |
|---|---|---|
| P1 | `select count(*) from pg_policies where schemaname='nucleo'` | `0` 🟢 |
| P2 | `empresa_id IS NULL` en cada tabla de tenant (bucle `DO`) | `0 avisos` 🟢 |
| P3 | tablas con `empresa_id` sin índice de prefijo `empresa_id` | `0 filas` 🟢 |
| P4 | `select count(*) from nucleo.auditoria where empresa_id is null` | `0` 🟢 |
| P5 | reservas apuntando a un viaje de otra empresa (INV-T02) | `0` 🟢 |
| P6 | rol `tei_app` y sus membresías | `0` / `0` 🟢 |

En la base de la app **no se ejecutaron** (no se tocó): deben correrse antes de
aplicar. Si P2/P4 devuelven filas, **reportar, no borrar**; si P3 devuelve tablas,
crear el índice antes (con `CONCURRENTLY` fuera de la migración).

### 5.2 Impacto y locks

- `CREATE/DROP POLICY`, `ALTER TABLE … FORCE`, `GRANT`, `REVOKE`: cambios de
  catálogo, **sin reescritura ni escaneo**. Cada sentencia toma `ACCESS EXCLUSIVE`
  sobre su tabla; al ir en una transacción, los locks se retienen hasta el
  `COMMIT`. Medido en `tei_test` con `\timing` (re-aplicación en caliente):
  **19,1 ms de suma de sentencias, máximo 7,2 ms en una sola**; el costo depende
  del número de tablas del catálogo, **no del volumen de datos**.
- `public` (legacy): sin cambios.
- La app actual (rol `postgres`) no cambia de comportamiento (§7.4).
- El rol es de clúster: en la base de la app **no** tiene privilegios (verificado
  con una consulta de catálogo, sin escribir:
  `has_schema_privilege('tei_app','nucleo','USAGE')` → `f`).
- Puede aplicarla `postgres` (tiene `CREATEROLE` en este entorno) o
  `supabase_admin`; requiere ser dueño de las tablas para `CREATE POLICY` y
  `ALTER TABLE … FORCE`.
- Índice recomendado, **no** incluido para no mezclar locks (evaluar con
  `EXPLAIN` sobre volumen real):
  `create index concurrently idx_auditoria_empresa on nucleo.auditoria (empresa_id, ocurrido_en desc);`

### 5.3 Orden de despliegue

1. Aplicar `0020` (inerte para la app actual; §7.4 lo prueba).
2. `backend`: fijar `app.empresa_id` y `nucleo.auth_id` por transacción (§4).
   También es inocuo mientras el rol sea `postgres` (§7.4A).
3. `backend`: crear la contraseña del rol e **inyectarla en el gestor de
   secretos**; cambiar el usuario de `DATABASE_URL` del engine del núcleo a
   `tei_app` (y resolver el legacy, §8.3).
4. Verificar en producción-equivalente: conteos por empresa, `mis-empresas`,
   auditoría y una escritura por empresa. Recién entonces RA-03/INV-T01 cambian de
   estado.

**No invertir 2 y 3**: cambiar el rol sin fijar el GUC deja la app con 0 filas en
todo `nucleo` (fail-closed, sin corrupción, pero caída total del módulo).

### 5.4 Rollback (conserva datos)

```sql
begin;
-- 1) quitar FORCE
do $$ declare r record; begin
  for r in select c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace
            where n.nspname='nucleo' and c.relkind='r' loop
    execute format('alter table nucleo.%I no force row level security', r.relname);
  end loop; end $$;
-- 2) borrar TODAS las políticas del esquema (antes de 0020 no había ninguna)
do $$ declare r record; begin
  for r in select tablename, policyname from pg_policies where schemaname='nucleo' loop
    execute format('drop policy %I on nucleo.%I', r.policyname, r.tablename);
  end loop; end $$;
-- 3) revocar grants y borrar funciones/rol
revoke all on all tables in schema nucleo from tei_app;
revoke all on all sequences in schema nucleo from tei_app;
revoke all on all functions in schema nucleo from tei_app;
revoke usage on schema nucleo from tei_app;
drop function if exists nucleo.empresas_del_usuario();
drop function if exists nucleo.ctx_auth_id();
drop function if exists nucleo.ctx_empresa();
commit;
-- 4) por base donde se hayan dado grants (roles son de clúster):
--    drop owned by tei_app;  -- y luego, en cualquier base:
--    drop role tei_app;
```

Reversible sin pérdida **mientras el backend no dependa de `tei_app`** (probado en
`tei_test`: §7.8, conteos antes/después idénticos). Si ya se cambió el rol, el
rollback exige volver `DATABASE_URL` a `postgres` en el mismo despliegue (si no: 0
filas, no corrupción). No hay `DROP TABLE` ni `DELETE`.

---

## 6. Contenido aplicado (verificación de objetos)

```
$ select tablename, string_agg(policyname||':'||cmd, ', ') from pg_policies
    where schemaname='nucleo' group by 1 order by 1;
auditoria            | auditoria_insercion:INSERT, auditoria_lectura:SELECT
centros_costo        | tenant_empresa:ALL
choferes             | tenant_empresa:ALL
...
empresas             | empresas_escritura:ALL, empresas_lectura:SELECT
transiciones_viaje   | transiciones_lectura:SELECT
usuarios_empresa     | usuarios_empresa_escritura:ALL, usuarios_empresa_lectura:SELECT
viajes               | tenant_empresa:ALL
(31 tablas, 35 políticas)

$ select count(*) filter (where relrowsecurity), count(*) filter (where relforcerowsecurity), count(*)
    from pg_class ... where nspname='nucleo' and relkind='r';
31|31|31

$ select rolname, rolsuper, rolbypassrls, rolinherit, rolcanlogin from pg_roles where rolname='tei_app';
tei_app|f|f|f|t
```

---

## 7. Pruebas ejecutadas (salidas reales)

Comandos (prefijo `docker exec -i supabase_db_TRANSTEI` porque no hay `psql` en el
host; la app del contenedor usa `trust` para `127.0.0.1`):

```bash
# aplicar en el clon desechable
docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
  -v ON_ERROR_STOP=1 < supabase/migrations/0020_rls_multiempresa.sql

# 1) una sesión, rol tei_app
docker exec -i supabase_db_TRANSTEI psql -h 127.0.0.1 -U tei_app -d tei_test \
  -v ON_ERROR_STOP=1 < supabase/tests/0020_01_aislamiento.sql

# 2) dos conexiones simultáneas
PSQL="docker exec -i supabase_db_TRANSTEI psql -h 127.0.0.1" \
  ./supabase/tests/0020_02_dos_conexiones.sh

# 3) mutación (retira el mecanismo y la prueba debe fallar)
PSQL_ADMIN="docker exec -i supabase_db_TRANSTEI psql -U supabase_admin" \
PSQL="docker exec -i supabase_db_TRANSTEI psql -h 127.0.0.1" \
  ./supabase/tests/0020_03_mutacion.sh

# 4) compatibilidad con el rol actual de la app
docker exec -i supabase_db_TRANSTEI psql -h 127.0.0.1 -U postgres -d tei_test \
  -v ON_ERROR_STOP=1 < supabase/tests/0020_04_compatibilidad_postgres.sql
```

### 7.1 Aislamiento en una sesión (rol `tei_app`)

```
OK 0020-1 rol: current_user=tei_app bypass=f
OK 0020-1A sin contexto: 0 filas en tablas de tenant, catálogos globales legibles
OK 0020-1B/C contexto: cada empresa ve solo sus filas y no ve la fila concreta de la otra
OK 0020-1D INSERT ajeno rechazado: SQLSTATE=42501 (new row violates row-level security policy for table "clientes")
OK 0020-1E INSERT propio aceptado, visible y auditado por el trigger
OK 0020-1E alta de empresa rechazada (por diseño: la hace seed/cutover)
OK 0020-1F UPDATE ajeno: 0 filas afectadas, sin error (no filtra existencia)
OK 0020-1G contexto inválido/vacío: 0 filas sin excepción 22P02
OK 0020-1H empresas/usuarios_empresa: solo la empresa actual y las membresías propias
OK 0020-1I auditoria: INSERT con empresa ajena rechazado
OK 0020-1I auditoria: INSERT con la empresa del contexto aceptado
OK 0020-1I auditoria: UPDATE denegado (append-only)
OK 0020-1J transiciones_viaje: escritura denegada
OK 0020-1J cutover_control: INSERT denegado
OK 0020-1J cutover_control: UPDATE permitido (control global)
OK 0020-1J viaje_eventos: UPDATE denegado (append-only)
OK 0020-1K siguiente_folio propio: rls_test-2026-000001
OK 0020-1K siguiente_folio ajeno: rechazado por WITH CHECK
OK 0020-1L tras COMMIT: 0 filas — una conexión del pool no hereda la empresa anterior
0020_01_aislamiento: OK
```

Snapshot de conteos (2026-10-30T03:47:20Z, misma base, misma hora; las cifras se
mueven porque el clon es compartido, por eso las pruebas no dependen de ellas):

```
tei_app ctx A (1111…): viajes=5   clientes=3   auditoria=135   viajes de otra empresa=0
tei_app ctx B (b078…): viajes=4   clientes=1   auditoria=64    viajes de otra empresa=0
tei_app sin contexto:  viajes=0   clientes=0   auditoria=0
postgres (rol actual): viajes=67  clientes=67  auditoria=2336
```

### 7.2 Dos conexiones simultáneas (`0020_02`)

```
  viaje de A: 26baa17d-2fbd-44af-a321-e1ab0c9614c5
  viaje de B: 49f2d33e-7791-4fcd-88be-cef5bd366a43
  A|inicio|1793331801.495138
  A|viajes|5
  A|ajenos|0
  A|viaje_b_visible|0
  A|cliente_propio|1
  A|fin|1793331803.501676
  B|inicio|1793331801.904980
  B|viajes|4
  B|ajenos|0
  B|viaje_a_visible|0
  B|cliente_de_a|0
  B|cliente_de_a_tras_commit_aparente|0
  B|fin|1793331804.424161
  solape de las dos transacciones: 1.60s
OK 0020-2: dos conexiones simultáneas, cada empresa aislada; A no ve B, B no ve A
```

Las dos transacciones estuvieron abiertas a la vez 1,60 s. A insertó un cliente
**sin commitear**: A lo ve (1), B no lo ve (0) ni antes ni después; B no ve el
viaje concreto de A y A no ve el de B.

### 7.3 El contexto muere con el `COMMIT` (caso pool)

En `0020_01`, bloque L: `begin; set_config('app.empresa_id', A, true); commit;`
seguido de un `select` nuevo en la **misma** conexión ⇒ `0 filas`. Es la prueba de
que `SET LOCAL` (y no `SET`) es lo que impide que una conexión reutilizada del pool
herede la empresa del request anterior.

### 7.4 Compatibilidad con el rol actual (`postgres`) — `0020_04`

Totales de esa corrida (el clon es compartido y cambia entre corridas; el punto es
que `postgres` ve lo mismo con y sin GUC, no la cifra exacta):

```
OK 0020-4 rol: current_user=postgres bypass=t
OK 0020-4A postgres ve 62 viajes con y sin app.empresa_id (BYPASSRLS gana sobre FORCE)
OK 0020-4B postgres inserta sin contexto y el trigger de auditoría registra
OK 0020-4C postgres ve 57 viajes de otras empresas (así se comporta la app HOY)
```

Conclusión honesta: `FORCE` **no** protege de `postgres`/`service_role`. La
migración es inerte para la app actual (no la rompe) y solo empieza a proteger
cuando el rol de conexión cambia.

### 7.5 Mutación (`0020_03`) — la prueba prueba algo

```
OK 0020-3 base: 0 filas ajenas con tei_app
OK 0020-3 M1: con tei_app BYPASSRLS se ven 41 viajes ajenos ⇒ el ROL es el mecanismo
OK 0020-3 M2: con USING(true) se ven 41 clientes ajenos ⇒ la POLÍTICA es el mecanismo
OK 0020-3 M3: sin FORCE tei_app sigue viendo 0 (FORCE no es el mecanismo para un rol no-dueño)
OK 0020-3 restaurado: 0 filas ajenas, tei_app.rolbypassrls=f
```

Se restauró todo con `trap EXIT` y se verificó el estado final; el script aborta si
`tei_app` queda con `BYPASSRLS`.

### 7.6 Plan de ejecución (la política usa el índice)

```
-- tei_app, ctx A: select count(*) from nucleo.viajes where estado='confirmado'
Bitmap Heap Scan on viajes
  Recheck Cond: (empresa_id = nucleo.ctx_empresa())
  Filter: (estado = 'confirmado'::nucleo.estado_viaje)
  -> Bitmap Index Scan on idx_viajes_empresa_estado_ini
       Index Cond: (empresa_id = nucleo.ctx_empresa())
Execution Time: 0.065 ms
```

El predicado de la política se empuja al índice de empresa: no hay `Seq Scan`
forzado ni filtro posterior sobre toda la tabla.

### 7.7 Camino de escritura completo bajo RLS (smoke del núcleo)

Un `UPDATE` real de la app (no una tabla aislada) con `tei_app` y contexto A:
dispara `fn_touch`, `fn_version`, `fn_auditoria`, `fn_viaje_reservas` (0015) y
`fn_viaje_oc` — todos invocadores, todos sujetos a RLS. Resultado real:

```
update nucleo.viajes set observaciones = 'smoke rls 0020'
 where empresa_id = '11111111-1111-1111-1111-111111111111';
UPDATE 5
 26baa17d-… | smoke rls 0020 | version=2
 81d70fa3-… | smoke rls 0020 | version=2
 dddddddd-…-ddddddddddd1 | smoke rls 0020 | version=4
 dddddddd-…-ddddddddddd2 | smoke rls 0020 | version=2
 e525ebd2-… | smoke rls 0020 | version=2
auditoria_del_cambio = 7      (filas de auditoría de la empresa A)
ROLLBACK
```

Conclusión: la cadena de triggers **no** se rompe por RLS (las filas que toca son
de la misma empresa del contexto) y la auditoría sigue registrando. No se probó el
`INSERT` de un viaje completo con recursos y documentos: eso requiere el fixture de
`fixtures_0015_0016.sql` y queda como pendiente para `qa` (🔴).

### 7.8 Rollback probado e idempotencia de la migración

```bash
docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
  -v ON_ERROR_STOP=1 < supabase/tests/0020_99_rollback.sql
```

```
NOTICE:  rollback 0020: 35 políticas eliminadas
DROP FUNCTION   (x3)
COMMIT
0020_99_rollback: OK (datos intactos)

antes:  viajes=67 clientes=67 empresas=75 auditoria=2336
después: viajes=67 clientes=67 empresas=75 auditoria=2336   ← sin pérdida
estado: políticas=0  FORCE=0  USAGE(tei_app)=f  funciones ctx=0
```

Después se **re-aplicó** `0020` (`APPLY_EXIT=0`, 35 políticas otra vez) y se
repitieron las cuatro pruebas con `EXIT=0`: la migración es re-ejecutable
(`DROP POLICY IF EXISTS`, `CREATE OR REPLACE FUNCTION`, `ALTER ROLE` idempotente).
El rol quedó `rolbypassrls=f`, `rolcanlogin=t`, **sin contraseña**
(`pg_authid.rolpassword IS NULL`).

---

## 8. Handoff a `backend` (no implementado aquí)

### 8.1 Cambios requeridos

1. **Fijar el contexto por transacción** con `after_begin` + `session.info`
   (§4). Cubre los `commit()` intermedios.
2. **Fijar `app.empresa_id` antes de `get_contexto_empresa`** (`deps.py:43-80`), y
   `nucleo.auth_id` en el mismo punto (hoy solo lo ponen 9 servicios, y **después**
   de su primer `commit()` se pierde: los registros de auditoría de la segunda
   mitad de un request quedan con `auth_id = 'sistema'`). Es un defecto latente que
   0020 hace visible.
3. **Rol de conexión**: engine del núcleo con usuario `tei_app` (contraseña en el
   gestor de secretos, nunca en el repo ni en `docs/`).
4. **`mis-empresas`** (`api.py:69-76`): funciona con `nucleo.auth_id` fijado (lo
   cubre §4) y las políticas de `empresas`/`usuarios_empresa` (§3.4). Probado con
   dos membresías: 2 empresas visibles, 0 ajenas. No requiere endpoint nuevo.
5. **Traducción de errores**: `42501` por política ⇒ **403/404 sin revelar
   existencia**; no es un conflicto de negocio. `42501` por falta de `GRANT` es un
   bug de despliegue (500 con alerta): la causa está en el mensaje
   (`permission denied for table …` vs `new row violates row-level security policy`).
6. **`servicio_cutover`**: `cutover_control` es legible y actualizable por
   `tei_app`; el `except` que devuelve `legacy_abiertos = 0`
   (`servicio_cutover.py:96-102`) sigue siendo fail-open (INV-X01) y **no** lo
   arregla esta migración.

### 8.2 Qué **no** cubre 0020

- **El legacy `public`.** 17 tablas con RLS y una sola política: un rol sin
  `BYPASSRLS` vería 0 filas. Opciones (decisión de `arquitectura`, ADR):
  (i) dos engines — núcleo con `tei_app`, legacy con el rol actual (recomendada:
  no cambia nada del legacy y no hay que tocar 17 tablas); (ii) políticas en
  `public` (no hay `empresa_id` que filtrar: sería teatro de seguridad);
  (iii) `GRANT` masivo a `tei_app` en `public` **con** RLS sin políticas ⇒ legacy
  caído. La (iii) no debe hacerse.
- **Trabajo de plataforma** (seeds, `scripts/cutover_legacy.py`, jobs,
  `psql`): siguen como rol privilegiado. Es deliberado: son operaciones de
  plataforma, no de tenant. Debe quedar escrito quién puede usar ese rol.
- **La disponibilidad entre esquemas** (RA-02): el legacy sigue sin escribir en
  `nucleo.reservas_recurso`.
- **INV-T02** (FK simple `reservas_recurso.viaje_id`): no se toca aquí.

---

## 9. Riesgos y límites

1. **El GUC es controlable por quien pueda ejecutar SQL en la conexión.** Un
   `set_config('app.empresa_id', otra, true)` cambia de tenant. Por lo tanto RLS
   con GUC protege contra **errores de alcance** (una consulta que olvidó el
   `WHERE empresa_id`), no contra ejecución arbitraria de SQL (inyección). La
   defensa contra inyección sigue siendo el código; esto es la última línea, no la
   única. Alternativas (roles por tenant, claims firmados) tienen otro costo; se
   registran como decisión futura si el modelo de amenaza cambia.
2. **`empresas` no se puede crear desde la app** (§3.4). Si el producto necesita
   alta de empresas por API, requiere un `SECURITY DEFINER` acotado o un
   procedimiento de plataforma. **Decisión de producto, no de datos.**
3. **`reservas_recurso.viaje_id`** sigue siendo FK simple (INV-T02). Bajo RLS no
   hay fuga, pero una reserva inactiva puede apuntar a un viaje de otra empresa y
   el `EXCLUDE` no lo nota. Migración futura (FK compuesta) con precondición P5.
4. **`auditoria` con `empresa_id NULL`** quedaría invisible para la app (hoy 0
   filas). Si aparecen, son de plataforma: revisar antes de decidir.
5. **Índice de `auditoria`** no creado (§5.2). Medir con `EXPLAIN` sobre volumen
   real; a 2.3k filas no se justifica.
6. **Roles son de clúster:** `tei_app` existe en todo el contenedor, pero sin
   privilegios fuera de la base donde se aplicó `0020`. En Supabase cloud hay que
   crearlo en el proyecto correcto y cuidar que el pooler (`pgbouncer`/supavisor)
   permita el login del rol nuevo (no probado aquí: 🔴).
7. **`tei_test` es un clon parcial** (sin `GRANT` de `service_role`, ver §1) y fue
   recreado durante la sesión por `scripts/test_db_reset.sh` (`DROP DATABASE …
   WITH (FORCE)` + `pg_dump --no-privileges`). La evidencia es válida para RLS, no
   para ACLs ni para volumen; y **volver a correr ese script elimina `0020` del
   clon** (hay que re-aplicarla).
8. **No probado:** pooler en modo transacción real (PgBouncer/Supavisor), RLS bajo
   `COPY`/`TRUNCATE`, rendimiento con volumen de producción, y `service_role` en
   `tei_test` (sin grants en el clon).

---

## 10. Registro de invariantes (fila actualizada)

| ID | Invariante | Mecanismo | Dónde se impone | Escritores cubiertos | SQLSTATE | Prueba |
|---|---|---|---|---|---|---|
| INV-T01 | Ningún rol de aplicación lee o escribe filas de otra empresa | RLS + 35 políticas + rol `tei_app` sin `BYPASSRLS` + `app.empresa_id` por transacción (`0020`) | `nucleo.*` (31 tablas) | núcleo con `tei_app` ✔ / legacy `public` ✘ (otro esquema) / seeds-cutover-jobs como rol privilegiado ✘ (declarado) | 42501 (o 0 filas) | `supabase/tests/0020_01…04` |

Estado: **diseñado y probado en `tei_test` (2026-10-30)**; 🔴 **no aplicado** a la
base de la app y 🔴 **inerte** mientras el backend conecte como `postgres`. RA-03
sigue abierto hasta completar §5.3.
