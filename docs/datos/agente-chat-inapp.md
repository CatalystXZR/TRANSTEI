# Chat in-app del agente — memoria persistida (`0031`)

Fecha: 2026-11-02 · Autor: agente `datos` · Método: DDL aplicado y pruebas
ejecutadas en la base local desechable `tei_test` (contenedor
`supabase_db_TRANSTEI`, rol `supabase_admin`). **La base de la app (`postgres`)
NO se tocó.** Niveles de certeza: 🟢 verificado con salida real · 🟡 inferido ·
🔴 no ejecutado.

---

## 1. Objeto y motivo

La Ola 3 construye un chat in-app para el dueño con dos agentes LLM (`gerente`,
`secretaria`). La memoria de ese chat se guarda en **dos tablas nuevas**:

| Tabla | Qué guarda |
|---|---|
| `nucleo.agente_chat_conversaciones` | Sesión por (empresa, usuario del núcleo, agente) con resumen compactado |
| `nucleo.agente_chat_mensajes` | Turnos con roles LLM (`user`/`assistant`/`tool`/`system`), `tool_calls`, idempotencia |

**Por qué no se reutilizan las tablas de WhatsApp** (verificado en
`supabase/migrations/0021_agente_whatsapp.sql`):

- `nucleo.conversaciones.contacto_id uuid NOT NULL` con FK a
  `contactos_whatsapp` (`0021:290-292`): un usuario del núcleo no es un contacto
  de WhatsApp y forzarlo exigiría un contacto ficticio por usuario.
- `nucleo.conversacion_mensajes.contacto_id NOT NULL` y
  `ck_mensaje_entrante_idempotente` exigen `wa_message_id` en entrantes
  (`0021:315-341`): el chat in-app no tiene webhook de WhatsApp.
- El chat necesita roles LLM y `tool_calls`/`tool_call_id`, ausentes en el
  modelo multimodal de WhatsApp.

No se alteran `conversaciones`, `conversacion_mensajes` ni `solicitudes`.

**Desviación declarada del contrato de tarea:** a `agente_chat_mensajes` se le
agregaron `updated_at`/`updated_by` además de `created_at`/`created_by`/`version`.
Motivo: el contrato exige el trigger `nucleo.fn_touch()` sobre esa tabla, y
`fn_touch()` asigna `NEW.updated_at`/`NEW.updated_by` (`0004:74-87`); sin esas
columnas todo `UPDATE` fallaría con `42703`. 🟢 verificado: la prueba `0031_01`
actualiza un mensaje y `version` pasa a 2.

---

## 2. DDL

Migración: `supabase/migrations/0031_agente_chat_inapp.sql` (transacción única,
`begin`/`commit`, re-ejecutable).

### 2.1 `nucleo.agente_chat_conversaciones` (`0031:159`)

| Columna | Tipo / constraint |
|---|---|
| `id` | `uuid not null default gen_random_uuid()` PK |
| `empresa_id` | `uuid not null` FK `nucleo.empresas(id)` `ON DELETE RESTRICT` |
| `usuario_empresa_id` | `uuid not null` |
| `agente` | `text not null` CHECK ∈ {`gerente`,`secretaria`} |
| `activa` | `boolean not null default true` |
| `abierta_en` / `cerrada_en` | `timestamptz not null default now()` / `timestamptz` |
| `resumen` / `resumen_en` | `text` / `timestamptz` |
| `created_at/created_by/updated_at/updated_by/version` | patrón `0021`/`0026` |

Constraints e índices:

- `uq_agente_chat_conv_empresa_id` UNIQUE `(empresa_id, id)`.
- `fk_agente_chat_conv_usuario` FK compuesta
  `(empresa_id, usuario_empresa_id)` → `nucleo.usuarios_empresa(empresa_id, id)`
  `ON DELETE RESTRICT`. Se apoya en el índice único
  `uq_usuarios_empresa_empresa` creado por `0021:170-171` (precondición P3).
- `ck_agente_chat_conv_cierre`: `activa OR cerrada_en IS NOT NULL`.
- `uq_agente_chat_conv_activa` UNIQUE parcial
  `(empresa_id, usuario_empresa_id, agente) WHERE activa` (`0031:203`).
- `idx_agente_chat_conv_usuario`
  `(empresa_id, usuario_empresa_id, agente, abierta_en DESC)` (`0031:207`).

### 2.2 `nucleo.agente_chat_mensajes` (`0031:218`)

| Columna | Tipo / constraint |
|---|---|
| `id` | `uuid not null default gen_random_uuid()` PK |
| `empresa_id` | `uuid not null` FK `nucleo.empresas(id)` `ON DELETE RESTRICT` |
| `conversacion_id` | `uuid not null` |
| `rol` | `text not null` CHECK ∈ {`user`,`assistant`,`tool`,`system`} |
| `contenido` / `tool_calls` / `tool_call_id` / `nombre_herramienta` | `text` / `jsonb` / `text` / `text` |
| `clave_idempotencia` | `text` |
| `metadata` | `jsonb not null default '{}'::jsonb` |
| `created_at/created_by/updated_at/updated_by/version` | patrón |

Constraints e índices:

- `uq_agente_chat_msg_empresa_id` UNIQUE `(empresa_id, id)`.
- `fk_agente_chat_msg_conversacion` FK compuesta
  `(empresa_id, conversacion_id)` → `agente_chat_conversaciones(empresa_id, id)`
  `ON DELETE RESTRICT`.
- `ck_agente_chat_msg_tool_call`: `rol <> 'tool' OR tool_call_id IS NOT NULL`.
- `ck_agente_chat_msg_contenido`:
  `contenido IS NOT NULL OR tool_calls IS NOT NULL OR rol IN ('tool','system')`.
- `uq_agente_chat_msg_idempotencia` UNIQUE parcial
  `(empresa_id, clave_idempotencia) WHERE clave_idempotencia IS NOT NULL`
  (`0031:264`).
- `idx_agente_chat_msg_conversacion` `(empresa_id, conversacion_id, created_at)`
  (`0031:268`).

### 2.3 Seguridad

| Elemento | Valor |
|---|---|
| RLS | `ENABLE` + `FORCE` en ambas tablas (`0031:294-297`) |
| Política | `tenant_empresa FOR ALL USING (empresa_id = nucleo.ctx_empresa()) WITH CHECK (...)`; `DROP POLICY IF EXISTS` previo (`0031:299-309`) |
| `tei_app` | `SELECT, INSERT, UPDATE`; **sin `DELETE`** (`0031:323-324`) |
| `postgres` | `SELECT, INSERT, UPDATE, DELETE` (`0031:326-327`) |
| `anon`/`authenticated` | `REVOKE ALL` si el rol existe (`0031:329-340`) |
| Triggers | `trg_agente_chat_conv_touch/version`, `trg_agente_chat_msg_touch/version` (`0031:276-288`). **Sin `fn_auditoria`**: el log de chat es append-only por diseño y auditar cada token inundaría `nucleo.auditoria` |
| COMMENT | Tablas y columnas no obvias (`0031:184-199` y `0031:247-262`) |

---

## 3. Invariantes impuestos y no impuestos

Registro completo en `docs/datos/invariantes.md` §15. Resumen:

| ID | Invariante | Mecanismo | SQLSTATE |
|---|---|---|---|
| INV-CHAT01 | Una conversación activa por (empresa, usuario, agente) | `uq_agente_chat_conv_activa` (UNIQUE parcial) | 23505 |
| INV-CHAT02 | `activa` exige coherencia con `cerrada_en` | `ck_agente_chat_conv_cierre` | 23514 |
| INV-CHAT03 | El usuario pertenece a la misma empresa | FK compuesta a `usuarios_empresa` | 23503 |
| INV-CHAT04 | El mensaje pertenece a una conversación de la misma empresa | FK compuesta a `agente_chat_conversaciones` | 23503 |
| INV-CHAT05 | Turno `tool` declara `tool_call_id` | `ck_agente_chat_msg_tool_call` | 23514 |
| INV-CHAT06 | Turno con contenido o `tool_calls` (tool/system exentos) | `ck_agente_chat_msg_contenido` | 23514 |
| INV-CHAT07 | `clave_idempotencia` única por empresa | `uq_agente_chat_msg_idempotencia` (UNIQUE parcial) | 23505 |
| INV-CHAT08 | Aislamiento por empresa con el rol real | RLS + FORCE + política `tenant_empresa` | 42501 / 0 filas |
| INV-CHAT09 | `tei_app` no borra conversaciones ni mensajes | GRANT sin `DELETE` | 42501 |

**No impuesto por la base (declarado, no maquillado):**

- Reapertura de una conversación cerrada: `cerrada_en` es informativo; el ciclo
  de vida lo decide el servicio.
- Que `resumen` corresponda a los mensajes: texto libre del runtime.
- Forma de `tool_calls`/`metadata`: jsonb sin catálogo (contrato del runtime).
- Coherencia conversacional (`tool_call_id` referenciado por un `tool_calls`
  previo, orden de turnos): servicio.
- Inmutabilidad de mensajes: no hay trigger; `tei_app` conserva `UPDATE` por
  contrato. La intención append-only es de diseño, **no está impuesta**.
- Aislamiento frente a un rol `BYPASSRLS` o dueño de las tablas: RLS es inerte
  para ese rol (`FORCE` solo alcanza al dueño, no a un superusuario).
- Auditoría por fila del chat: decidido **no** implementar en esta migración.

---

## 4. Precondiciones ejecutadas y su resultado

| Precondición | Verificación | Resultado |
|---|---|---|
| P1 | `to_regclass` de ambas tablas: estado parcial ⇒ 23514; ambas ⇒ NOTICE | 🟢 La primera aplicación no las encontró; la re-aplicación emitió `NOTICE: PRECONDICIÓN P1: 0031 ya aplicada` y no duplicó nada |
| P2 | `nucleo.ctx_empresa()` existe; `tei_app` existe con USAGE en `nucleo` | 🟢 pasó (si falla, 23514) |
| P3 | Índice único `(empresa_id, id)` en `nucleo.usuarios_empresa` | 🟢 existe `uq_usuarios_empresa_empresa` (creado por `0021:170-171`) |

---

## 5. Impacto y locks

🟢 ADD-only sobre objetos nuevos:

- 2 tablas vacías + 4 índices + 4 triggers + 2 políticas + GRANTs.
- `CREATE TABLE`/`CREATE INDEX` bloquean solo los objetos nuevos; no reescriben
  `empresas` ni `usuarios_empresa` (solo se agregan FKs que apuntan a ellas).
- `ENABLE/FORCE RLS`, `CREATE POLICY` y `GRANT`: instantáneos.
- Ningún escritor actual conoce estas tablas ⇒ backend y frontend no cambian.
- Sin siembra de datos: la verificación reporta 0 filas en ambas tablas.

---

## 6. Pruebas ejecutadas (salida real)

Base: `tei_test` (desechable). Rol: `supabase_admin` (`BYPASSRLS`) más bloques
con `SET LOCAL ROLE tei_app` (NOBYPASSRLS). Comando:

```bash
docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
  -v ON_ERROR_STOP=1 < supabase/tests/0031_01_chat.sql
```

### 6.1 `0031_01_chat.sql` — constraints, roles LLM, idempotencia y tenant

```
NOTICE:  OK 0031-1A mecanismo: RLS+FORCE, 2 políticas, UNIQUE parciales, 4 triggers, 2 FKs compuestas
NOTICE:  OK 0031-1C segunda activa (empresa, usuario, agente) => 23505
NOTICE:  OK 0031-1D activa=false sin cerrada_en => 23514
NOTICE:  OK 0031-1D borde: sesión nueva tras cerrar la anterior permitida
NOTICE:  OK 0031-1E usuario de otra empresa => 23503
NOTICE:  OK 0031-1F turno tool sin tool_call_id => 23514
NOTICE:  OK 0031-1F assistant sin contenido ni tool_calls => 23514
NOTICE:  OK 0031-1F tool con tool_call_id y system sin contenido aceptados
NOTICE:  OK 0031-1G mensaje con conversación de otra empresa => 23503
NOTICE:  OK 0031-1H clave_idempotencia repetida en la empresa => 23505
NOTICE:  OK 0031-1H la misma clave en otra empresa convive (alcance por empresa)
NOTICE:  OK 0031-1I touch+version en mensajes: version = 2
NOTICE:  OK 0031-1K DELETE de conversación con tei_app => 42501
NOTICE:  OK 0031-1K DELETE de mensaje con tei_app => 42501
NOTICE:  OK 0031-1J dos empresas no se ven (set local role tei_app)
0031-1: OK (rollback; 0 filas residuales)
```

### 6.2 `0031_02_rls_tei_app.sql` — RLS con el rol real

```
NOTICE:  OK 0031-2A rol: current_user=tei_app bypass=f (session_user conserva admin)
NOTICE:  OK 0031-2B INSERT de conversación sin contexto => 42501
NOTICE:  OK 0031-2B INSERT de mensaje sin contexto => 42501
NOTICE:  OK 0031-2C TEI: filas propias visibles y escribibles
NOTICE:  OK 0031-2C INSERT de conversación con empresa de TES => 42501
NOTICE:  OK 0031-2C INSERT de mensaje con empresa de TES => 42501
NOTICE:  OK 0031-2C UPDATE de otra empresa: 0 filas
NOTICE:  OK 0031-2D DELETE de conversación => 42501
NOTICE:  OK 0031-2D DELETE de mensaje => 42501
NOTICE:  OK 0031-2E contexto TES: 0 filas de TEI, solo las propias
0031-2: OK (rollback; 0 filas residuales)
```

### 6.3 `0031_99_rollback.sql` — ciclo de rollback

```
NOTICE:  0031-99: agente_chat_mensajes eliminada; 0 fila(s) perdidas
NOTICE:  0031-99: agente_chat_conversaciones eliminada; 0 fila(s) perdidas
NOTICE:  0031-99: OK; 0 objetos de 0031; empresas/usuarios/WhatsApp/solicitudes intactos
0031-99: OK (rollback aplicado; re-aplicar 0031 para volver al estado anterior)
```

Verificación posterior (0 objetos) y re-aplicación:

```
NULL|NULL|0|0          -- to_regclass conversaciones, to_regclass mensajes, políticas, índices
COMMIT                 -- re-aplicación limpia
NOTICE:  PRECONDICIÓN P1: 0031 ya aplicada; se re-verifica sin duplicar objetos
COMMIT                 -- segunda re-aplicación idempotente
```

### 6.4 Concurrencia REAL (dos conexiones, `tei_test`)

Dos procesos `psql` simultáneos. La transacción A inserta una conversación
activa y duerme 4 s antes del `commit`; B intenta insertar el mismo
`(empresa_id, usuario_empresa_id, agente)` mientras A sigue abierta:

```
--- B arranca con A abierta: 16:16:07 ---
Time: 3000.789 ms (00:03.001)
ERROR:  duplicate key value violates unique constraint "uq_agente_chat_conv_activa"
DETAIL:  Key (empresa_id, usuario_empresa_id, agente)=(11111111-…, 17efc277-…, secretaria) already exists.
--- B termina: 16:16:10 ---
```

B quedó **bloqueada ~3 s** (esperando el fin de A) y perdió con `23505`: una
sola ganadora. Limpieza posterior: `DELETE 1`, `count(*) = 0`.

### 6.5 Mutación (la prueba prueba algo)

En una transacción con `rollback`: se retira `uq_agente_chat_conv_activa` y se
insertan dos conversaciones activas idénticas:

```
INSERT 0 2
 activas_duplicadas_sin_indice
-------------------------------
                             2
ROLLBACK
 indice_restaurado_por_rollback
--------------------------------
 nucleo.uq_agente_chat_conv_activa
```

Sin el índice, `INV-CHAT01` deja de existir y la prueba `0031_01` fallaría.

### 6.6 Suite completa

```bash
make test
# 423 passed, 2 warnings in 7.57s
```

🟢 Sigue en verde (423), igual que antes de la migración.

---

## 7. Rollback

`supabase/tests/0031_99_rollback.sql` (ejecutado 🟢):

1. `DROP TRIGGER` de los 4 triggers si las tablas existen.
2. `DROP TABLE nucleo.agente_chat_mensajes` (primero, por la FK RESTRICT).
3. `DROP TABLE nucleo.agente_chat_conversaciones`.
4. Verifica: 0 tablas, 0 triggers, 0 políticas, 0 índices de 0031; y que
   `empresas`, `usuarios_empresa`, `conversaciones`, `conversacion_mensajes` y
   `solicitudes` siguen existiendo.

**Pérdida:** solo el historial de chat escrito (ninguno al aplicar). No toca
`nucleo.auditoria` (append-only). Re-aplicar `0031` tras el rollback deja el
mismo estado.

---

## 8. Handoff

### 8.1 SQLSTATE → HTTP (`backend`)

| SQLSTATE | Causa típica | HTTP propuesto |
|---|---|---|
| `23505` `uq_agente_chat_conv_activa` | Ya hay una conversación activa de ese usuario+agente | `409` con la conversación existente en el body (no crear otra) |
| `23505` `uq_agente_chat_msg_idempotencia` | Reintento del cliente con la misma `clave_idempotencia` | `200/409` idempotente (devolver el turno ya guardado) |
| `23503` FK compuesta | `conversacion_id`/`usuario_empresa_id` de otra empresa o inexistente | `422` (o `404` si no se filtra) |
| `23514` CHECK | `tool` sin `tool_call_id`, turno vacío, `activa=false` sin cierre | `422` |
| `42501` | `tei_app` intentando `DELETE` o escribir fuera de `app.empresa_id` | `403` |
| `0 filas` en `UPDATE`/`SELECT` | Fila de otra empresa (RLS) | `404` sin filtrar existencia |

Recordatorio: la empresa sale de `X-Empresa-ID` + membresía, **nunca** del body;
el runtime debe hacer `SET LOCAL app.empresa_id` en cada transacción para que
RLS no devuelva 0 filas.

### 8.2 Casos para `qa`

- `P0`: abrir chat `gerente`, cerrarlo y abrir otro; el segundo debe pasar y el
  primero quedar como historial.
- `P0`: doble clic de envío con la misma `clave_idempotencia` ⇒ un solo turno.
- `P0`: `tool` sin `tool_call_id` ⇒ 422, no 500.
- `P0`: usuario de otra empresa (UUID adivinado) ⇒ 404/422.
- `P0`: `DELETE` de un turno desde la API ⇒ 403.
- `P1`: dos pestañas simultáneas abriendo el chat del mismo agente ⇒ una sola
  conversación activa (409 en la segunda).

---

## 9. Comando pendiente para `postgres` (NO ejecutado)

🔴 **No aplicado en la base de la app.** Requiere autorización explícita del
dueño/orquestador. Cuando se autorice, el comando es:

```bash
# 1) Aplicar (base de la app, local)
docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d postgres \
  -v ON_ERROR_STOP=1 < supabase/migrations/0031_agente_chat_inapp.sql

# 2) Verificar (debe devolver las 2 tablas y 2 políticas)
docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d postgres -c \
  "select to_regclass('nucleo.agente_chat_conversaciones'),
          to_regclass('nucleo.agente_chat_mensajes'),
          (select count(*) from pg_policies
            where schemaname='nucleo' and tablename like 'agente_chat%');"

# 3) Pruebas (deben terminar en ROLLBACK; no dejan filas)
docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d postgres \
  -v ON_ERROR_STOP=1 < supabase/tests/0031_01_chat.sql
docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d postgres \
  -v ON_ERROR_STOP=1 < supabase/tests/0031_02_rls_tei_app.sql
```

No ejecutar `0031_99_rollback.sql` contra `postgres` sin backup verificado.

---

## 10. Riesgos y no verificado

- 🔴 **`postgres` no tiene la migración**: el chat in-app no puede persistir ahí
  hasta que se autorice el comando §9.
- 🟡 **Rol efectivo del backend**: `tei_app` es `NOBYPASSRLS` (verificado) y las
  políticas se probaron con ese rol. Si el runtime conecta con `postgres`
  (`BYPASSRLS`), RLS es inerte y el aislamiento depende solo del filtro del
  servicio (`R-10`, `docs/estado.md`).
- 🟡 **Inmutabilidad de mensajes**: no impuesta. Un `UPDATE` con `tei_app` puede
  reescribir `contenido`; el contrato no pidió trigger de inmutabilidad. Si el
  negocio exige historial inmutable, se diseña en una migración posterior.
- 🟡 **Crecimiento**: `agente_chat_mensajes` no tiene retención ni partición. El
  volumen real del chat del dueño no se midió (no hay datos). Sin impacto hoy
  porque la tabla está vacía.
- 🔴 **Sin prueba E2E ni HTTP**: el backend del chat no existe todavía; esta
  entrega es solo el esquema y sus garantías.
