# Overrides de capacidades del chat in-app (`0032`)

Fecha: 2026-11-02 · Autor: agente `datos` · Método: DDL aplicado y pruebas
ejecutadas en **`tei_test` y `postgres`** (contenedor `supabase_db_TRANSTEI`,
rol `supabase_admin`), con el rol de aplicación `tei_app` para RLS.
Niveles de certeza: 🟢 verificado con salida real · 🟡 inferido · 🔴 no ejecutado.

---

## 1. Objeto y motivo

`nucleo.agente_capacidades` guarda **overrides** de las capacidades del chat
in-app: por `(empresa, agente, capacidad)` decide si una capacidad del catálogo
queda habilitada o deshabilitada.

- **Fila ausente** = se aplica el valor por defecto del código.
- **Fila presente** = el valor explícito (`habilitada`) manda sobre el defecto.

La tabla NO es:

| No es | Por qué |
|---|---|
| `nucleo.tenant_reglas_entidad` (`0030`) | Aquella exige entidad concreta y vigencia; aquí no hay entidad ni historial. |
| `nucleo.modulos_empresa` (`0023`) | Aquello es el gate de módulos por empresa; esto es permiso fino por agente. |
| `nucleo.agente_chat_conversaciones` (`0031`) | Aquello es memoria del chat; esto es configuración. |
| `nucleo.usuarios_empresa.rol` | Aquello es el rol del usuario humano; esto es el agente LLM. |

No se alteró ninguna tabla existente.

## 2. DDL y objetos

### 2.1 Tabla (`0032:158-170`)

```sql
create table nucleo.agente_capacidades (
  id uuid primary key default gen_random_uuid(),
  empresa_id uuid not null references nucleo.empresas(id) on delete restrict,
  agente text not null check (agente in ('gerente','secretaria')),
  capacidad text not null check (capacidad ~ '^[a-z][a-z0-9_.]{2,80}$'),
  habilitada boolean not null,
  created_at timestamptz not null default now(),
  created_by text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at timestamptz not null default now(),
  updated_by text,
  version integer not null default 1 check (version >= 1),
  constraint agente_capacidades_unica unique (empresa_id, agente, capacidad)
);
```

`empresa_id` usa FK **simple** a `nucleo.empresas`: la fila no referencia otra
entidad, así que no existe el cruce entre empresas que obliga a una FK compuesta
(comparar con `0031:178-179`). El aislamiento lo impone RLS.

### 2.2 Triggers (`0032:202-212`)

| Trigger | Momento | Función | Efecto |
|---|---|---|---|
| `trg_agente_capacidades_touch` | `BEFORE UPDATE` | `nucleo.fn_touch()` | `updated_at := now()`, `updated_by := auth_id \|\| previo \|\| 'sistema'` |
| `trg_agente_capacidades_version` | `BEFORE UPDATE` | `nucleo.fn_version()` | `version := old.version + 1` |
| `trg_agente_capacidades_audit` | `AFTER INSERT OR UPDATE OR DELETE` | `nucleo.fn_auditoria()` | fila en `nucleo.auditoria` (SECURITY DEFINER) |

### 2.3 RLS (`0032:218-229`)

```sql
alter table nucleo.agente_capacidades enable row level security;
alter table nucleo.agente_capacidades force row level security;

create policy tenant_empresa on nucleo.agente_capacidades
  for all to public
  using (empresa_id = nucleo.ctx_empresa())
  with check (empresa_id = nucleo.ctx_empresa());
```

`nucleo.ctx_empresa()` lee `app.empresa_id` y devuelve `NULL` si falta o es
basura (`0020:187-200`): sin contexto, 0 filas y `INSERT` rechazado
(fail-closed). `FORCE` aplica RLS incluso al dueño de la tabla; en la práctica
solo un rol con `BYPASSRLS`/superusuario la evita (`postgres` y
`supabase_admin` en local).

### 2.4 Grants (`0032:236-237`)

| Rol | Privilegios |
|---|---|
| `tei_app` | `SELECT`, `INSERT`, `UPDATE` — **sin `DELETE`** |
| `postgres` | `SELECT`, `INSERT`, `UPDATE`, `DELETE` |
| `anon`, `authenticated` | `REVOKE ALL` (si el rol existe) |

## 3. Invariantes

| ID | Invariante (una frase) | Mecanismo | Dónde | Escritores cubiertos | SQLSTATE | Prueba |
|---|---|---|---|---|---|---|
| INV-AGCAP01 | No hay dos filas para `(empresa, agente, capacidad)` | `UNIQUE agente_capacidades_unica` | `nucleo.agente_capacidades` (`0032:169`) | `tei_app`, `postgres`, seeds, scripts | 23505 | `0032_01` 1C ✅ + concurrencia 2 conexiones ✅ |
| INV-AGCAP02 | `agente` ∈ {gerente, secretaria} y `capacidad` cumple `^[a-z][a-z0-9_.]{2,80}$` | 2 `CHECK` | `0032:161-162` | todos los anteriores | 23514 | `0032_01` 1D ✅ (9 formatos inválidos) |
| INV-AGCAP03 | Toda fila es invisible/inescribible fuera de `app.empresa_id` | RLS `ENABLE`+`FORCE` + política `tenant_empresa` | `0032:218-224` | `tei_app` (probado); cualquier rol sin `BYPASSRLS` | 42501 / 0 filas | `0032_01` 1G ✅ con `tei_app` |
| INV-AGCAP04 | `tei_app` no puede borrar overrides | `GRANT` sin `DELETE` | `0032:236` | `tei_app` | 42501 | `0032_01` 1H ✅ |
| INV-AGCAP05 | `INSERT`/`UPDATE`/`DELETE` dejan rastro en `nucleo.auditoria` | `trg_agente_capacidades_audit` → `fn_auditoria()` | `0032:210-212` | todos los anteriores (el trigger es SECURITY DEFINER) | — | `0032_01` 1I ✅ |
| INV-AGCAP06 | Cada `UPDATE` refresca `updated_at` y sube `version` | `fn_touch()` + `fn_version()` | `0032:202-208` | todos los anteriores | — | `0032_01` 1F ✅ |

**Escritores cubiertos:** `tei_app` (probado con `SET LOCAL ROLE`, NOBYPASSRLS),
backend futuro y cualquier script que escriba con un rol sujeto a constraints y
RLS. **No cubre** a un superusuario/`BYPASSRLS` que deshabilite triggers o
escriba sin `app.empresa_id`.

**Nota de auditoría:** `fn_auditoria()` registra `tg_table_schema || '.' ||
tg_table_name`, así que el valor real de `tabla` es **`nucleo.agente_capacidades`**,
no `agente_capacidades`. La prueba usa el valor real.

## 4. Precondiciones y rollback

### 4.1 Precondiciones (`0032:107-149`)

| ID | Comprobación | Resultado esperado | Salida real |
|---|---|---|---|
| P1 | `to_regclass('nucleo.agente_capacidades') IS NULL` | tabla ausente | 🟢 OK en ambas bases |
| P2 | `nucleo.empresas` y `nucleo.auditoria` existen | presentes | 🟢 OK |
| P3 | `ctx_empresa`, `fn_touch`, `fn_version`, `fn_auditoria` existen | 4 de 4 | 🟢 OK |
| P4 | `tei_app` existe, **NOBYPASSRLS** y con `USAGE` en `nucleo` | cumple | 🟢 OK |

P1 es deliberadamente **no idempotente**: si la tabla existe, la migración
aborta con `23514` en vez de usar `if not exists`/`drop table`. Re-ejecutarla
exige el rollback documentado.

Salida real de la precondición:

```text
NOTICE:  PRECONDICIÓN OK 0032: tabla ausente; empresas/auditoria y 4 funciones presentes; tei_app NOBYPASSRLS con USAGE
```

### 4.2 Rollback

```sql
drop table if exists nucleo.agente_capacidades;
```

Con la tabla caen PK, `UNIQUE`, `CHECK`s, FK, triggers, política, RLS y GRANTs.
No hay funciones propias que borrar (se reutilizan las de `0004`). Pérdida:
**solo los overrides escritos** (ninguno al aplicar). `nucleo.empresas` y
`nucleo.auditoria` no se tocan; las filas de auditoría ya escritas son
append-only y **no se borran**.

Simulación no destructiva en `supabase/tests/0032_99_rollback.sql`
(`begin` → `drop` → verificaciones → `rollback`), ejecutada en ambas bases.

## 5. Índice: decisión y evidencia

No se creó un índice adicional `(empresa_id, agente)`: el índice que respalda
`agente_capacidades_unica (empresa_id, agente, capacidad)` ya sirve ese prefijo.
Un índice extra solo agregaría escrituras y espacio.

Evidencia (`tei_test`, 2 000 filas sintéticas dentro de una transacción
revertida, `enable_seqscan = off` para forzar la comparación):

```text
Bitmap Heap Scan on agente_capacidades
  Recheck Cond: ((empresa_id = '1111…'::uuid) AND (agente = 'gerente'::text))
  ->  Bitmap Index Scan on agente_capacidades_unica
        Index Cond: ((empresa_id = '1111…'::uuid) AND (agente = 'gerente'::text))
```

🟡 A 2 000 filas el planner prefiere `Seq Scan` (0.10 ms); el índice existe y es
usable para el prefijo. Con el volumen real del piloto la decisión puede
cambiar, pero **no se justifica duplicar el índice hoy**.

## 6. Aplicación y registro

Comandos ejecutados (idénticos para `tei_test` y `postgres`):

```bash
docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d <base> \
  -v ON_ERROR_STOP=1 -f - < supabase/migrations/0032_agente_capacidades.sql

docker exec supabase_db_TRANSTEI psql -U supabase_admin -d <base> -v ON_ERROR_STOP=1 \
  -c "insert into supabase_migrations.schema_migrations (version, name, statements)
      values ('0032','agente_capacidades', array[]::text[])
      on conflict (version) do nothing;"
```

Salida real de la aplicación (misma en ambas bases):

```text
BEGIN
NOTICE:  PRECONDICIÓN OK 0032: tabla ausente; empresas/auditoria y 4 funciones presentes; tei_app NOBYPASSRLS con USAGE
CREATE TABLE
COMMENT × 6
CREATE TRIGGER × 3
ALTER TABLE × 2
CREATE POLICY
COMMENT
GRANT × 2
NOTICE:  OK 0032: 1 tabla, UNIQUE, 3 CHECK, FK RESTRICT, 3 triggers, RLS+FORCE, política tenant_empresa y GRANTs
COMMIT
```

Registro en `supabase_migrations.schema_migrations`:

```text
== tei_test
INSERT 0 1
 version |        name        | statements
---------+--------------------+------------
 0032    | agente_capacidades | {}

== postgres
INSERT 0 1
 version |        name        | statements
---------+--------------------+------------
 0032    | agente_capacidades | {}
```

### 6.1 Verificación de objetos (ambas bases)

```text
===== tei_test
filas | 0
rls | t | t
politica | tenant_empresa | ALL
trigger | trg_agente_capacidades_audit
trigger | trg_agente_capacidades_touch
trigger | trg_agente_capacidades_version
grant | postgres | DELETE,INSERT,SELECT,UPDATE
grant | tei_app | INSERT,SELECT,UPDATE
auditoria_prueba | 0
migracion | 0032 | agente_capacidades
===== postgres
filas | 0
rls | t | t
politica | tenant_empresa | ALL
trigger | trg_agente_capacidades_audit
trigger | trg_agente_capacidades_touch
trigger | trg_agente_capacidades_version
grant | postgres | DELETE,INSERT,SELECT,UPDATE
grant | tei_app | INSERT,SELECT,UPDATE
auditoria_prueba | 0
migracion | 0032 | agente_capacidades
```

`\d nucleo.agente_capacidades` (tei_test; idéntico en `postgres`):

```text
Indexes:
    "agente_capacidades_pkey" PRIMARY KEY, btree (id)
    "agente_capacidades_unica" UNIQUE CONSTRAINT, btree (empresa_id, agente, capacidad)
Check constraints:
    "agente_capacidades_agente_check" CHECK (agente = ANY (ARRAY['gerente'::text, 'secretaria'::text]))
    "agente_capacidades_capacidad_check" CHECK (capacidad ~ '^[a-z][a-z0-9_.]{2,80}$'::text)
    "agente_capacidades_version_check" CHECK (version >= 1)
Foreign-key constraints:
    "agente_capacidades_empresa_id_fkey" FOREIGN KEY (empresa_id) REFERENCES nucleo.empresas(id) ON DELETE RESTRICT
Policies (forced row security enabled):
    POLICY "tenant_empresa"
      USING ((empresa_id = nucleo.ctx_empresa()))
      WITH CHECK ((empresa_id = nucleo.ctx_empresa()))
Triggers:
    trg_agente_capacidades_audit AFTER INSERT OR DELETE OR UPDATE ... EXECUTE FUNCTION nucleo.fn_auditoria()
    trg_agente_capacidades_touch BEFORE UPDATE ... EXECUTE FUNCTION nucleo.fn_touch()
    trg_agente_capacidades_version BEFORE UPDATE ... EXECUTE FUNCTION nucleo.fn_version()
```

## 7. Pruebas ejecutadas

### 7.1 `0032_01_agente_capacidades.sql` (constraints, RLS, auditoría, versión)

Ejecutada en `tei_test` y `postgres`; salida idéntica. Se pega la de `tei_test`:

```text
BEGIN
NOTICE:  OK 0032-1A mecanismo: RLS+FORCE, política, UNIQUE, 3 triggers y privilegios
NOTICE:  OK 0032-1B INSERT válido: version=1, created_by=sistema, created_at=updated_at
NOTICE:  OK 0032-1C duplicado (empresa, agente, capacidad) => 23505
NOTICE:  OK 0032-1D agente fuera de {gerente,secretaria} => 23514
NOTICE:  OK 0032-1D 9 formatos de capacidad inválidos => 23514
NOTICE:  OK 0032-1D borde permitido: capacidad de 3 caracteres (a.b) aceptada
NOTICE:  OK 0032-1E misma capacidad en otro agente y en otra empresa convive
NOTICE:  OK 0032-1F touch+version: version=2, updated_at=now() (sobrescribió 2000-01-01)
NOTICE:  OK 0032-1G sin contexto: 0 filas y INSERT => 42501
NOTICE:  OK 0032-1G INSERT con empresa ajena => 42501
NOTICE:  OK 0032-1H DELETE con tei_app => 42501
NOTICE:  OK 0032-1G aislamiento: TEI y TES solo ven lo propio; INSERT cruzado rechazado
NOTICE:  OK 0032-1I auditoría: INSERT y UPDATE con empresa, registro y auth_id
NOTICE:  OK 0032-1I auditoría: DELETE registrado
NOTICE:  OK 0032-1J mutación: sin agente_capacidades_unica el duplicado pasa (la prueba depende del mecanismo)
NOTICE:  OK 0032-1: unicidad, formato, RLS, no-delete, auditoría y versionado
DO
ROLLBACK
OK 0032-1: rollback sin residuo (conteo igual antes/después)
```

Bordes cubiertos: capacidad de 3 caracteres permitida; 9 formatos inválidos
(mayúsculas, espacios, barra, `ñ`, guion bajo inicial, longitudes); misma
capacidad en otro agente y en otra empresa; contexto ausente; empresa ajena en
`INSERT` y en `UPDATE`; `DELETE` denegado.

**Nota sobre `updated_at`:** `fn_touch()` usa `now()`, que es el timestamp de la
**transacción**. Dentro de una sola transacción `updated_at` no avanza; la
prueba demuestra que el trigger dispara porque un valor explícito
(`2000-01-01`) es sobrescrito por `now()`. Entre transacciones reales sí avanza.

### 7.2 Mutación (la prueba prueba algo)

Al final de `0032_01` se ejecuta, **dentro de la misma transacción**:

```sql
alter table nucleo.agente_capacidades drop constraint agente_capacidades_unica;
insert into nucleo.agente_capacidades (...) values (..., 'facturacion.ver', true);  -- duplicado
```

El duplicado pasa, lo que confirma que la prueba de `INV-AGCAP01` depende del
`UNIQUE` y no de una coincidencia de datos. El `ROLLBACK` restaura la
constraint. 🟡 La mutación cubre solo el `UNIQUE`; no se mutaron RLS ni GRANTs.

### 7.3 Rollback simulado (`0032_99_rollback.sql`)

```text
BEGIN
NOTICE:  0032-99: drop simulado OK; 0 fila(s) se perderían; empresas/auditoria intactas
DO
ROLLBACK
NOTICE:  0032-99: ROLLBACK restauró nucleo.agente_capacidades (la tabla real sigue viva)
DO
0032-99: OK (rollback simulado; tabla real intacta)
```

### 7.4 Concurrencia real (dos conexiones)

Dos sesiones `psql` sobre la misma base. A inserta `(TEI, gerente, conc.prueba)`
y duerme 3 s antes de `ROLLBACK`; B intenta el mismo `INSERT` 1 s después:

```text
===== tei_test
A: insertado, durmiendo
B: insertó tras esperar        real 2.05
filas_residuales=0
===== postgres
A: insertado, durmiendo
B: insertó tras esperar        real 2.02
filas_residuales=0
```

B quedó **bloqueada ~2 s** hasta que A terminó: el índice único serializa a los
escritores, no hay ventana TOCTOU. 🟡 No se observó el rechazo `23505` con A
confirmando, porque ambas transacciones se revirtieron para no dejar residuo; el
rechazo en el caso secuencial sí está probado (`0032-1C`).

## 8. Limitaciones

- **El catálogo de capacidades no vive en la base.** Un `capacidad` con formato
  válido pero inexistente en el código es aceptado por PostgreSQL. El servicio
  debe ignorarlo o rechazarlo.
- **El valor por defecto no vive en la base.** Fila ausente = defecto del
  código; cambiar el defecto no requiere migración.
- **Los límites duros por agente viven en el código.** Esta tabla solo expresa
  el override; no impide que un agente ejecute algo que el servicio no filtre.
- **No hay borrado lógico ni historial.** Deshabilitar es
  `habilitada = false`; el `DELETE` queda reservado a `postgres`.
- **`tei_app` puede cambiar `empresa_id` de una fila propia** (el `WITH CHECK`
  valida el valor nuevo). Mover una fila a otra empresa requiere que el contexto
  sea el de esa otra empresa, así que no cruza el límite; aun así, el servicio
  no debería exponer esa edición.
- **La auditoría es append-only y no se purga.** Cada `UPDATE` deja una fila;
  un panel que escriba en bucle puede inflar `nucleo.auditoria`.
- **No hay prueba con el rol real del backend** (no existe un rol distinto de
  `tei_app` en local); se probó con `tei_app`, que es el rol de aplicación
  declarado.

## 9. Handoff

### 9.1 SQLSTATE → HTTP (`backend`)

| SQLSTATE | Origen | HTTP | Mensaje sugerido |
|---|---|---|---|
| `23505` | `agente_capacidades_unica` | 409 | "Esa capacidad ya está configurada para el agente" |
| `23514` | `CHECK` de `agente`, `capacidad` o `version` | 422 | "Agente o capacidad inválidos" |
| `42501` | RLS (`WITH CHECK`) o `DELETE` sin privilegio | 403 | "No autorizado para esta empresa / operación" |
| `23503` | FK a `empresas` (empresa inexistente) | 422 | "Empresa inválida" |

Regla del repo: nunca devolver 500 por un conflicto de negocio ni el mensaje
crudo de PostgreSQL.

### 9.2 Casos para `qa`

1. Panel de configuración: habilitar/deshabilitar una capacidad y recargar;
   el override persiste y `version` sube.
2. Dos pestañas que guardan el mismo `(agente, capacidad)` a la vez: una gana
   con 200, la otra recibe 409 (no duplicado silencioso).
3. Usuario de la empresa A no puede leer ni escribir overrides de la empresa B
   (probar con `X-Empresa-ID` de B y membresía solo de A).
4. Capacidad con nombre inventado pero formato válido: definir el
   comportamiento esperado (ignorar vs 422) y fijarlo en el contrato.
5. `DELETE` desde la API: debe responder 403/405, nunca borrar.

## 10. Riesgos y no verificado

- 🟡 **`tei_test` tenía `0030`/`0031` aplicadas pero no registradas** en
  `supabase_migrations.schema_migrations` (el registro llegaba hasta `0029`).
  Esta migración registra solo `0032`, como se pidió; **no se backfillearon**
  `0030`/`0031` porque no estaban autorizadas. `postgres` sí registraba hasta
  `0031`.
- 🔴 **No se probó con un volumen realista** (solo 2 000 filas sintéticas) ni se
  midió el impacto del `UNIQUE` en escritura a escala.
- 🔴 **No se probó el rechazo `23505` con dos conexiones y la primera
  confirmando**; se probó el bloqueo y el rechazo secuencial.
- 🔴 **No hay prueba de mutación para RLS ni para los GRANTs**; solo para el
  `UNIQUE`.
- 🟡 **`nucleo.auditoria` no se purga**; el crecimiento queda como riesgo
  operativo, no de esta migración.
- 🔴 **No se ejecutó la suite completa** (`make test`) en esta sesión; el cambio
  es aditivo y no toca código de aplicación.
