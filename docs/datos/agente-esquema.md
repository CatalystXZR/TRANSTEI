# Esquema del módulo Agente WhatsApp — contrato documental de `0021`

> **Pregunta que responde:** ¿qué garantías impone la base para el módulo agente
> WhatsApp, con qué mecanismo exacto, qué SQLSTATE emiten, qué escritores cubren y
> qué pruebas existen?
> **Dueño:** agente `datos`.
> **Verificado:** 2026-10-30 contra el clon desechable `tei_test` (contenedor
> `supabase_db_TRANSTEI`), por **catálogo de PostgreSQL** + ejecución de
> `supabase/tests/0021_01_smoke.sql` (14/14 OK **antes** de `0022`; ver §8.1) +
> sondas `BEGIN … ROLLBACK`.
> **Migraciones:** `supabase/migrations/0021_agente_whatsapp.sql` (883 líneas) y
> `supabase/migrations/0022_agente_whatsapp_endurecimiento.sql` (endurecimiento;
> cierra D2/D3/D5/D9, §8.1). Ambas **untracked** en git.
> **Estado de aplicación:** 🟢 `0021` y `0022` aplicadas en `tei_test`; 🔴 **no
> verificadas** en la base de la app ni en ningún otro entorno.
> **Caduca si:** se aplica, edita o revierte `0021` o `0022`; cambia `0020`
> (`nucleo.ctx_empresa`, políticas, rol `tei_app`); se agrega una migración que
> toque estas tablas; o se ejecutan `0021_02`/`0021_03`/`0021_04` y aparece
> evidencia nueva de concurrencia, RLS o mutación.
> **Re-verificar con:** §6 de este documento + `ls supabase/tests/` +
> `docker exec -i supabase_db_TRANSTEI psql -U postgres -d tei_test -f supabase/tests/0021_01_smoke.sql`.

---

## 0. Alcance y cómo leer este documento

1. Cubre la **parte Núcleo** del módulo agente WhatsApp (ADR-0003, ADR-0004,
   `docs/negocio/agente-whatsapp-roles.md`, tarea O1.1). No cubre el runtime, el
   gate de permisos, el orquestador conversacional ni el webhook: eso es
   `backend`/O2 y no tiene DDL.
2. Los estados 🟢/🟡/🔴 siguen `AGENTS.md` §2. **"Existe" no es "funciona"**:
   cada mecanismo se cita por `archivo:línea` y se marca si fue probado.
3. `AW-NN` son los IDs que la migración ya cita (no se puede editar: está
   aplicada). Su equivalente canónico en el registro es `INV-AWNN`; la
   reconciliación completa está en §7 y en `docs/datos/invariantes.md` §11.
4. **El legacy `public` no interviene**: ninguna sentencia de `0021` referencia
   `public` y ninguna tabla nueva es leída por el backend actual (módulo apagado,
   DEC-10). Los invariantes de este documento no dicen nada sobre el legacy ni lo
   protegen.

---

## 1. Inventario aplicado

Todo lo de esta sección fue leído del catálogo de `tei_test` el 2026-10-30
(consultas y salidas en §6). Dueño de las 8 tablas: `supabase_admin`.

### 1.1 Objetos creados

| Objeto | Tipo | DDL (`0021:línea`) | Nota |
|---|---|---|---|
| `nucleo.contactos_whatsapp` | tabla | `179-216` | teléfono → empresa/rol/entidad + estado OTP |
| `nucleo.permisos_contacto` | tabla | `243-260` | ACL por (contacto, componente, variable) |
| `nucleo.conversaciones` | tabla | `275-293` | sesión activa por contacto + resumen |
| `nucleo.conversacion_mensajes` | tabla | `315-341` | mensajes multimodales, idempotentes |
| `nucleo.solicitudes` | tabla | `388-433` | buzón F2.6 (pendiente/aprobada/rechazada/cancelada) |
| `nucleo.hoja_ruta` | tabla | `495-523` | JSON propuesto → solicitud → carga |
| `nucleo.id_comercial_contador` | tabla | `572-586` | contador por (empresa, cliente) |
| `nucleo.auditoria_consultas_agente` | tabla | `678-702` | log append-only de consultas (D-17) |
| `nucleo.viajes.id_comercial_flete` | columna `text` nullable | `548-549` | R-04; `NULL` permitido (asignación diferida) |
| `nucleo.ck_viaje_id_comercial_flete` | CHECK | `551-553` | `^[A-Z0-9]{2,8}-[0-9]{5}$` |
| `nucleo.uq_viajes_id_comercial` | UNIQUE parcial | `555-557` | `(empresa_id, cliente_id, código) WHERE código IS NOT NULL` |
| `nucleo.uq_usuarios_empresa_empresa` | UNIQUE | `170-171` | habilita las FK compuestas hacia `usuarios_empresa` |
| 8 tipos `enum` | tipos | `151-162` | `rol_contacto_whatsapp`, `estado_otp`, `direccion_mensaje`, `modalidad_mensaje`, `estado_procesamiento_mensaje`, `tipo_solicitud`, `estado_solicitud`, `estado_hoja_ruta` |
| 5 funciones | funciones | `361-379`, `458-483`, `603-636`, `640-670`, `719-727` | `fn_mensaje_validar`, `fn_solicitud_transicion`, `obtener_siguiente_id_comercial_flete`, `registrar_id_comercial_flete`, `fn_consultas_agente_inmutable` |
| 25 triggers | triggers | `729-735`, `741-792` | 2 de inmutabilidad (append-only) + 2 de validación (`trg_mensajes_10_validar`, `trg_solicitudes_10_transicion`) + 21 de convención (`touch`, `version`, `audit` × 7 tablas) |
| 32 índices | índices | varios | 8 `pkey` (7 simples + 1 compuesta), 6 `UNIQUE (empresa_id, id)`, 6 únicos parciales/funcionales, 12 de consulta; **+3 fuera**: 2 en `viajes`, 1 en `usuarios_empresa` |
| 9 políticas RLS | políticas | `799-831` | 7 `tenant_empresa` (`FOR ALL`) + 2 en auditoría (`SELECT`, `INSERT`) |
| `ENABLE` + `FORCE` RLS | atributo de tabla | `833-850` | en las 8 tablas; medido `relrowsecurity=t`, `relforcerowsecurity=t` |
| GRANTs a `tei_app` | privilegios | `855-868` | `SELECT/INSERT/UPDATE` en 7 tablas; `SELECT/INSERT` en auditoría; `USAGE/SELECT` en secuencias; `EXECUTE` en funciones |

### 1.2 Índices que sostienen invariantes (no son solo rendimiento)

| Índice | Definición efectiva (medida) | Invariante |
|---|---|---|
| `uq_contactos_telefono_activo` | `UNIQUE (telefono) WHERE activo` | AW-02 |
| `uq_conversacion_activa` | `UNIQUE (contacto_id) WHERE activa` | AW-05 |
| `uq_mensaje_wa_message_id` | `UNIQUE (wa_message_id) WHERE wa_message_id IS NOT NULL` | AW-01 |
| `uq_permisos_contacto_valor` | `UNIQUE (contacto_id, componente, COALESCE(variable,''))` | AW-06 |
| `uq_solicitud_idempotencia` | `UNIQUE (empresa_id, clave_idempotencia) WHERE clave_idempotencia IS NOT NULL` | AW-12 |
| `uq_hoja_ruta_carga_por_solicitud` | `UNIQUE (solicitud_id) WHERE estado='cargado'` | AW-13 |
| `uq_viajes_id_comercial` | `UNIQUE (empresa_id, cliente_id, id_comercial_flete) WHERE … IS NOT NULL` | AW-14 |
| `contactos_whatsapp_empresa_id_id_key` y 5 similares | `UNIQUE (empresa_id, id)` | AW-08 (habilitan las FK compuestas) |

---

## 2. Precondiciones

Las cuatro precondiciones del encabezado (`0021:38-50`) están **defendidas dentro
de la transacción** (`0021:97-140`, `raise exception … errcode='23514'`), de modo
que si no se cumplen, la migración aborta completa en vez de romper objetos.

> **Cómo leer los resultados de hoy.** `0021` **ya está aplicada** en `tei_test`,
> así que P1–P3 dan distinto de cero. Eso **no** significa que las precondiciones
> fallen: significa que la migración ya corrió. La prueba de que se cumplieron al
> aplicar es estructural: el `DO` de precondiciones y el DDL están en la **misma
> transacción** (`begin` en `:92`, `commit` en `:870`); si P1–P3 hubieran dado >0,
> no habría ni tablas ni `commit`. Para aplicar `0021` a otra base hay que
> re-ejecutar estas consultas **antes** y exigir el valor de la columna
> "esperado pre-aplicación".

### P1 — Sin tablas del módulo

```sql
select count(*) as tablas_modulo from pg_tables
 where schemaname='nucleo' and tablename in (
 'contactos_whatsapp','permisos_contacto','conversaciones','conversacion_mensajes',
 'solicitudes','hoja_ruta','id_comercial_contador','auditoria_consultas_agente');
```

- Esperado pre-aplicación: **0**. Medido hoy en `tei_test`: **8** (las 8 tablas
  de §1.1).
- Si da >0 en una base destino: **reportar, no sobreescribir** (`0021:106-109`).

### P2 — Sin la columna `nucleo.viajes.id_comercial_flete`

```sql
select count(*) as col_existe from pg_attribute a
  join pg_class c on c.oid=a.attrelid join pg_namespace n on n.oid=c.relnamespace
 where n.nspname='nucleo' and c.relname='viajes'
   and a.attname='id_comercial_flete' and a.attnum>0 and not a.attisdropped;
```

- Esperado pre-aplicación: **0**. Medido hoy: **1**.

### P3 — Sin tipos del módulo

```sql
select count(*) as tipos_modulo from pg_type t join pg_namespace n on n.oid=t.typnamespace
 where n.nspname='nucleo' and t.typname in (
 'rol_contacto_whatsapp','estado_otp','direccion_mensaje','modalidad_mensaje',
 'estado_procesamiento_mensaje','tipo_solicitud','estado_solicitud','estado_hoja_ruta');
```

- Esperado pre-aplicación: **0**. Medido hoy: **8**.

### P4 — Dependencia de `0020` (esta sí debe dar > 0)

```sql
select count(*) as politicas_nucleo from pg_policies where schemaname='nucleo';
```

- Esperado pre-aplicación: **>= 35** (`0021:132-138`). Medido hoy: **44**.
- Desglose medido: **35** políticas fuera de las tablas del módulo (= exactamente
  el umbral de `0020`) + **9** del módulo. La migración pasó el guard por el
  margen mínimo: si `0020` hubiera tenido 34 políticas, `0021` habría abortado.

### P5 (no es precondición de la migración, es medición de impacto) — filas existentes

| Medición | Valor medido (`tei_test`, 2026-10-30) | Por qué importa |
|---|---|---|
| `nucleo.viajes` filas | **218** | `ADD COLUMN` + `CHECK` recorren la tabla |
| filas con `id_comercial_flete` no nulo | **0** | el `CHECK` valida 218 filas, todas `NULL` |
| filas que violarían el `CHECK` de formato | **0** | por eso `convalidated = true` sin `NOT VALID` |
| `ck_viaje_id_comercial_flete.convalidated` | **`t`** | constraint validada, no diferida |
| tamaño `nucleo.viajes` | **664 kB** | el lock de validación es irrelevante a este volumen |
| `nucleo.clientes` / `empresas` / `usuarios_empresa` / `choferes` | 246 / 316 / 31 / 190 | fixtures disponibles para las pruebas |

En una base con millones de viajes, el `ALTER TABLE … ADD CONSTRAINT … CHECK`
**sí** recorre la tabla: usar `NOT VALID` + `VALIDATE CONSTRAINT` (patrón
expand/contract) y medir antes.

---

## 3. Invariantes `AW-01` … `AW-16`

**Leyenda de prueba:** ✅ = caso ejecutado y pasado en `0021_01` (corrida propia
2026-10-30, 14/14 OK) · **en curso** = previsto en `0021_02`/`0021_03`/`0021_04`,
que `qa` está escribiendo (O1.2); **no se afirma que existan hoy** · **sin
cobertura** = no hay prueba y no la hay prevista con nombre.
**Escritores:** salvo excepción, "todos" = cualquier `INSERT/UPDATE` sobre la
tabla (backend, scripts, seeds, `psql`, y `tei_app` cuando se cablee el rol). El
legacy `public` **no** escribe `nucleo`.

| ID | Invariante (una frase) | Mecanismo (`0021:línea`) | SQLSTATE | Prueba |
|---|---|---|---|---|
| **AW-01** | Un `wa_message_id` entra una sola vez en toda la base, y todo mensaje **entrante** lo trae. | `create unique index uq_mensaje_wa_message_id … where wa_message_id is not null` `:346-347`; `ck_mensaje_entrante_idempotente` `:338-340` | `23505` (duplicado) / `23514` (entrante sin id) | ✅ `0021_01` C7A, C7B, C7C, C7E. **Concurrencia real (dos webhooks simultáneos): en curso, `0021_02`** |
| **AW-02** | Un número **activo** resuelve a un solo contacto en todo el sistema; desactivarlo libera el número. | `uq_contactos_telefono_activo … where activo` `:222-223` (global, sin `empresa_id`) | `23505` | ✅ C3A–C3F, incluido rechazo entre tenants (C3F) y reactivación (C3E) |
| **AW-03** | El contacto es coherente: teléfono E.164, nombre no vacío, **exactamente una** entidad según rol, y `verificado` exige fecha. | `ck_contacto_telefono_e164` `:208`; `ck_contacto_nombre_no_vacio` `:209`; `ck_contacto_entidad` `:210-214`; `ck_contacto_otp_estado` `:215` | `23514` | ✅ C1, C2A–C2D, C3A, C4 |
| **AW-04** | Un mensaje solo pertenece a una conversación **de su contacto y de su empresa**. | `fn_mensaje_validar()` `:361-379` + `trg_mensajes_10_validar` `:762-763`; FK compuesta `fk_mensaje_conversacion` `:334-335` | `23514` (contacto distinto) / `23503` (otra empresa, lo dispara la FK) | ✅ C8A (`23514`). Sonda propia: empresa B en conversación de A ⇒ `23503` (§6, V8). `UPDATE` que cambie `contacto_id`: **sin cobertura** |
| **AW-05** | A lo sumo **una conversación activa** por contacto; toda conversación cerrada tiene `cerrada_en`. | `uq_conversacion_activa … where activa` `:298-299`; `ck_conversacion_cierre` `:292` | `23505` / `23514` | ✅ C6A–C6E. Dos cierres/aperturas concurrentes: **en curso, `0021_02`** |
| **AW-06** | La ACL tiene a lo sumo una fila por `(contacto, componente, variable)` —`NULL` = botón de módulo— y ni componente ni variable pueden ser blancos. | `uq_permisos_contacto_valor (contacto_id, componente, coalesce(variable,''))` `:262-263`; `ck_permiso_componente_no_vacio` / `ck_permiso_variable_no_vacia` `:258-259` | `23505` / `23514` | ✅ C5A–C5C, C5E. **Orden medido:** el clon exacto hacia otra empresa dispara `23505` antes que `23503` (C5F, documentado en el propio test) |
| **AW-07** | **Sin fila en `permisos_contacto` no hay acceso** (deny-by-default). | **Ninguno en la base.** La ausencia de fila no es un hecho que una constraint pueda imponer; la resuelve el gate del backend (O2.2) al leer `permitido`. El `COMMENT` lo declara: `:267-270` | n/a (HTTP 403/404, no SQLSTATE de negocio) | **sin cobertura de base** — por diseño. **Prueba prevista: O2.2 (backend)**. Riesgo declarado en §8 (D6) |
| **AW-08** | Ninguna fila del módulo referencia una entidad de **otra empresa**. | FK compuestas `(empresa_id, id)`: contactos `:202-207`; permisos `:256-257`; conversaciones `:290-291`; mensajes `:334-337`; solicitudes `:415-420`; hoja_ruta `:512-519`; contador `:582-585`; auditoría `:693-698`; + `uq_usuarios_empresa_empresa` `:170-171` | `23503` | **Parcial** ✅ C5D, C5F (permisos), C11B (función cliente↔empresa), sonda de §6 V8 (mensajes). **Sin caso:** solicitudes→viajes, hoja_ruta→solicitudes/mensajes, auditoría→contactos ⇒ **en curso, `0021_02`/`0021_04`** |
| **AW-09** | Toda solicitud tiene **exactamente un** solicitante humano: contacto de WhatsApp **xor** usuario del núcleo. | `ck_solicitud_solicitante` `:421-423` | `23514` | ✅ C9C, C9D |
| **AW-10** | Una solicitud en estado terminal está **documentada** (aprobada: aprobador+fecha; rechazada: motivo+fecha; cancelada: motivo) y **no se reabre ni reclasifica**. | CHECKs `ck_solicitud_aprobada/rechazada/cancelada` `:424-432`; `fn_solicitud_transicion()` `:458-483` + `trg_solicitudes_10_transicion` `:771-772` | `23514` | ✅ C9E, C9F, C9G, C9H, C9J. Dos aprobadores concurrentes: **en curso, `0021_02`** |
| **AW-11** | **Rechazar solo registra la decisión**: no muta el documento destino (viaje ni hoja de ruta). | **Parcial.** La base exige `motivo_rechazo` + `decidido_en` (`:427-429`) y **ningún** trigger del módulo escribe `nucleo.viajes` ni `nucleo.hoja_ruta`; el efecto sobre el destino lo impone el servicio (O2.5). La tabla no tiene columna que apunte al viaje salvo `viaje_id` (referencia, no escritura) | `23514` (rechazo sin motivo/fecha) | **sin cobertura del "no muta el destino"**. `0021_01` no tiene ningún caso que rechace una solicitud (C9G/C9H intentan reclasificar una aprobada). Previsto: `0021_02` + O2.5 |
| **AW-12** | La misma `clave_idempotencia` no produce dos solicitudes en una empresa. | `uq_solicitud_idempotencia … where clave_idempotencia is not null` `:437-438` | `23505` | ✅ C9B. Doble clic concurrente: **en curso, `0021_02`** |
| **AW-13** | La hoja de ruta declara un estado coherente con sus campos y existe **a lo sumo una carga confirmada por solicitud**. | `ck_hr_estado_solicitud` / `ck_hr_rechazo_con_motivo` / `ck_hr_carga_registrada` `:520-522`; `uq_hoja_ruta_carga_por_solicitud … where estado='cargado'` `:528-529` | `23514` / `23505` | ✅ C10A–C10F. **Límite medido:** no hay máquina de estados (§8, D5) |
| **AW-14** | Un código comercial cumple `PREFIJO-00000`, no se repite dentro de `(empresa, cliente)` y se genera **sin carrera**. | CHECK `:551-553`; `uq_viajes_id_comercial` `:555-557`; `obtener_siguiente_id_comercial_flete()` `:603-636` (INSERT … ON CONFLICT DO UPDATE que serializa por fila de contador); `registrar_id_comercial_flete()` `:640-670` (`greatest`, no retrocede); PK `(empresa_id, cliente_id)` `:581` | `23514` / `23505` | ✅ C11A–C11H (incluye consecutivos `SQM-00001`/`SQM-00002`, prefijo inválido, cliente ajeno, duplicado, `NULL`). Dos conexiones generando en paralelo: **en curso, `0021_02`**. Límites medidos: §8 (D2, D3, D4, D9) |
| **AW-15** | La auditoría de consultas es **append-only** para todos, incluido el dueño; `tei_app` no puede `UPDATE`/`DELETE`. | `fn_consultas_agente_inmutable()` `:719-727`; `trg_consultas_agente_no_update` (row, BEFORE UPDATE OR DELETE) `:729-731`; `trg_consultas_agente_no_truncate` (statement, BEFORE TRUNCATE) `:733-735`; `revoke all` + `grant select, insert` `:863-864` | `23514` (trigger) / `42501` (GRANT) | ✅ C12A–C12D; sonda propia: `DELETE` como `tei_app` ⇒ `42501` (§6, V7) |
| **AW-16** | Toda fila del módulo es **invisible e inescribible** fuera de la empresa del contexto `app.empresa_id`; **sin contexto no hay filas**. | `create policy tenant_empresa … for all to public using/with check (empresa_id = nucleo.ctx_empresa())` `:799-814`; auditoría `:817-825`; `ENABLE`+`FORCE ROW LEVEL SECURITY` `:833-850`; GRANT `:855-868`; `nucleo.ctx_empresa()` (devuelve `NULL` sin GUC) en `0020` | `42501` / 0 filas | **Parcial 🟢** sondas propias (§6, V7): sin contexto 0 filas y `INSERT` rechazado; con contexto A, `INSERT` con `empresa_id` de B rechazado; `SELECT`+`INSERT` en auditoría funcionan. **Matriz completa con el rol real: en curso, `0021_03` (qa O1.2)**. **Vigencia en la app 🟡:** el backend ya crea un engine `nucleo` con `tei_app` cuando `NUCLEO_DATABASE_URL` está configurada y cae a `DATABASE_URL` con el marcador `RLS inerte` si no (`backend/app/core/database.py:24-32,110-135`); qué variable está activa **no se verificó** (no se lee `.env`) — RA-03 |

### 3.1 Notas de cobertura

1. **Ningún invariante de esta tabla está probado con dos conexiones.** `0021_01`
   es secuencial y lo declara: corre con rol `BYPASSRLS` y prueba constraints,
   triggers y funciones, **no** concurrencia ni RLS. Las pruebas de concurrencia
   (`0021_02`), RLS con `tei_app` (`0021_03`) y mutación (`0021_04`) están
   previstas y **no existían** al levantar esta tabla (verificado entonces:
   `ls supabase/tests/` solo mostraba `0021_01_smoke.sql`).
   **Adenda 2026-10-30:** `0021_02`, `0021_03` y `0021_04` ya existen y
   corrieron en el cierre O1.3 (`0021_02` con 8+2+2 conexiones reales,
   `0021_03` con `tei_app`, `0021_04` M1–M9); ver
   `docs/qa/informes/2026-10-31-o1.3-rollback-reaplicacion.md:319-403`. La
   columna "Estado/Evidencia" de §3 conserva la foto previa a esas corridas.
2. **AW-07 y AW-11 no son garantías de base.** Se registran para que nadie las
   lea como cerradas: su cumplimiento depende del backend (O2.2 / O2.5).
3. `0021_01` corre **siempre** dentro de `BEGIN … ROLLBACK` por caso: no deja
   residuo. Verificado después de la corrida y de todas las sondas:
   `contactos=0`, `conversaciones=0`, `mensajes=0`, `solicitudes=0`,
   `hoja_ruta=0`, `contador=0`, `auditoria_consultas=0`,
   `viajes con id_comercial=0`.

---

## 4. Decisiones de diseño

### 4.1 Por qué `rol_contacto_whatsapp` no reutiliza `nucleo.rol_empresa`

Valores medidos en `tei_test` el 2026-10-30:

| Tipo | Valores |
|---|---|
| `nucleo.rol_empresa` (0004) | `admin, gerente, despacho, contador, tesoreria, taller, conductor, auditor` |
| `nucleo.rol_contacto_whatsapp` (0021) | `admin, cliente_final, conductor` |

Razones (el DDL las declara en `0021:143-149`):

1. **El contacto no siempre es miembro.** Un `cliente_final` escribe por WhatsApp
   sin fila en `nucleo.usuarios_empresa`; reutilizar `rol_empresa` habría obligado
   a inventar una membresía falsa o a permitir `conductor`/`cliente_final` en un
   enum cuyo consumidor (permisos del núcleo) no los conoce.
2. **D-09 trata "administrador o dueño" como una sola clase de operador.** Un
   único valor `admin` evita dos estados equivalentes que el gate tendría que
   acordar; si el dueño quisiera distinguir dueño vs empleado, se agrega con
   `alter type … add value` **sin migración de datos** (el enum es el mecanismo
   barato; partirlo después no reescribe filas).
3. **Costo de la decisión:** `conductor` existe en ambos enums con semántica
   distinta (membresía operativa vs entidad `choferes`). Quien una tablas por
   nombre de rol se equivoca; el vínculo real es la FK `chofer_id` (`:204-205`),
   no el texto del enum.
4. **Riesgo declarado:** con `admin` colapsado, la auditoría no distingue por sí
   sola entre dueño y administrador empleado. Mitigación disponible hoy:
   `usuario_empresa_id` opcional (`:189`, FK `:206-207`) permite saber qué
   membresía del núcleo está detrás. Si el negocio exige esa distinción en el
   gate, es decisión de `negocio-finanzas`/dueño, no de `datos`.

### 4.2 Por qué el teléfono activo es único **global** y cómo se compensa la revocación

DDL: `uq_contactos_telefono_activo on nucleo.contactos_whatsapp (telefono) where activo`
(`0021:222-223`), **sin `empresa_id`** en la clave.

1. **El invariante que se quiere es de identidad, no de tenant.** El webhook
   recibe un número y debe resolver **una** `(empresa, rol, entidad)`. Si dos
   empresas pudieran tener el mismo número activo, esa resolución sería ambigua:
   el mensaje de un cliente podría interpretarse con el rol y los datos de otra
   empresa. Eso es una fuga entre tenants, no un conflicto de negocio.
2. **La compensación es la revocación.** El índice es **parcial** (`WHERE activo`):
   al poner `activo=false` el número queda libre y puede re-enrolarse (`D-12`).
   Medido: C3D (desactivar y re-enrolar en la misma empresa) y C3E (reactivar el
   viejo mientras hay otro activo ⇒ `23505`). Se conservan **múltiples filas
   inactivas** con el mismo número; eso es deliberado: la historia no se borra.
3. **La traza sobrevive al reciclaje.** Cada `INSERT/UPDATE/DELETE` de
   `contactos_whatsapp` se copia a `nucleo.auditoria` por `trg_contactos_audit`
   (`:745-746`, `fn_auditoria` de `0004`). Verificado con una sonda: dos
   operaciones (INSERT + UPDATE) producen dos filas con
   `tabla='nucleo.contactos_whatsapp'`.
4. **Riesgo que la base no puede cerrar:** la unicidad global permite que quien
   registre primero un número **bloquee** su activación en otra empresa; y la
   liberación por `activo=false` permite que el número se re-enrole en **otra**
   empresa. La base no puede probar que el número pertenece a quien lo registra:
   eso es el OTP (D-12), que vive en el backend. Política de emisión/revocación:
   decisión abierta, declarada en el `COMMENT` de `otp_hash` (`:232-234`).
5. **No hay normalización canónica del teléfono** más allá del `CHECK` E.164
   (`^\+[1-9][0-9]{7,14}$`). `+56911111111` y `+56056911111111` son números
   distintos para la base; la canonicalización es del runtime.

### 4.3 Otras decisiones que conviene dejar escritas

- **`id_comercial_contador` + funciones, no `SEQUENCE`.** Una secuencia por
  `(empresa, cliente)` no existe en PostgreSQL; el contador con PK compuesta y
  `INSERT … ON CONFLICT DO UPDATE` (`:628-632`) toma el lock de fila y serializa;
  la `UNIQUE` de `viajes` es el árbitro final. Un `ROLLBACK` libera el número no
  publicado (mismo criterio que `folio_contador`, `0004:519-521`).
- **`NULL` en el ID comercial.** La columna nace nullable (`:549`) para no
  reescribir 218 viajes ni forzar un backfill en la migración; el `CHECK` y la
  `UNIQUE` son parciales sobre no nulos. Consecuencia: "todo viaje tiene ID
  comercial" **no** es un invariante de base (ver §8, D2/D4).
- **`solicitudes` no es una máquina de estados en `INSERT`.** El trigger de
  transición solo actúa en `UPDATE` (`:463`), así que insertar directamente una
  fila `aprobada` con sus campos completos es válido (medido, §6 V8). Es
  deliberado (`:485-487`): el ciclo `pendiente → terminal` lo gobierna el
  servicio; la base garantiza que un estado terminal esté documentado y no
  cambie después.
- **La auditoría de consultas no duplica datos de negocio.**
  `datos_tocados` guarda referencias (IDs), no el contenido (`:714-716`).

---

## 5. Impacto, locks y rollback

### 5.1 Impacto (ADD-only)

| Sentencia | Lock / costo | Medición en `tei_test` |
|---|---|---|
| `CREATE TABLE` ×8 | `ACCESS EXCLUSIVE` sobre tablas nuevas; sin efecto en tablas existentes | 8 tablas, 0 filas |
| `ALTER TABLE nucleo.viajes ADD COLUMN` | metadata-only (PG11+: `NULL` no reescribe) | 218 filas, sin reescritura |
| `ADD CONSTRAINT … CHECK` | recorre y valida la tabla (lock `SHARE ROW EXCLUSIVE`) | 218 filas, 0 violaciones, `convalidated=t` |
| `CREATE UNIQUE INDEX uq_usuarios_empresa_empresa` | construye índice; bloquea escrituras en `usuarios_empresa` mientras dura | 31 filas |
| `CREATE INDEX` ×13 + `CREATE UNIQUE INDEX` ×14 (además de las 8 `pkey`) | bloquean escrituras en cada tabla mientras se construyen | tablas nuevas vacías; `viajes` 218 filas |
| Políticas + `ENABLE/FORCE` + GRANTs | catálogo | 9 políticas, 8 tablas con `FORCE` |

**Legacy:** no se toca. **Backend actual:** nada lee ni escribe estas tablas
todavía — `grep -rn "contactos_whatsapp\|permisos_contacto\|conversacion_mensajes\|auditoria_consultas_agente\|hoja_ruta\|id_comercial_flete\|obtener_siguiente_id_comercial" backend/app backend/tests`
devuelve **0** (módulo apagado, DEC-10), así que el riesgo de regresión en la app
es nulo; el riesgo es de **despliegue** (encender el módulo sin pasar por el
engine `nucleo`, ver §8).

### 5.2 Rollback

- El encabezado describe el orden inverso y la pérdida prevista: **solo datos de
  las tablas del módulo**, cero erosión de datos de negocio (`0021:78-85`).
- **Defecto D1 (§8), estado 2026-10-30:** al documentar esta sección, el script
  `supabase/tests/0021_99_rollback.sql` citado en `:79` **no existía**. Hoy
  existe (`untracked`), junto con `0022_99_rollback.sql`, y el ciclo rollback →
  re-aplicación → 4 suites verdes está **ejecutado y probado en clon** (§8.2).
  Sigue pendiente probarlo con datos reales y versionar los scripts: `HEAD`
  todavía no los contiene.
- La migración es reversible en estructura (`DROP TABLE`… / `DROP TYPE`…), no en
  datos: los contactos y la auditoría de consultas se pierden. Retención
  (`P-07`/`D-17`) sigue abierta: decisión del dueño antes de revertir en
  producción.

---

## 6. Verificación post (catálogo)

Ejecutadas el 2026-10-30 en `tei_test` con
`docker exec -i supabase_db_TRANSTEI psql -U postgres -d tei_test` (y
`-U supabase_admin` para las sondas de RLS). Salidas resumidas; el detalle está
en el informe de la sesión.

### V1 — RLS activo y forzado en las 8 tablas

```sql
select c.relname, c.relrowsecurity as rls, c.relforcerowsecurity as force_rls,
       pg_get_userbyid(c.relowner) as dueno
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
 where n.nspname='nucleo' and c.relname in (
 'contactos_whatsapp','permisos_contacto','conversaciones','conversacion_mensajes',
 'solicitudes','hoja_ruta','id_comercial_contador','auditoria_consultas_agente')
 order by 1;
```

Resultado: las 8 con `rls=t`, `force_rls=t`, dueño `supabase_admin`.
**Esperado post:** 8 filas, todas `t/t`.

### V1b — Políticas por tabla (9)

```sql
select tablename, policyname, cmd, roles::text, coalesce(qual,'-'), coalesce(with_check,'-')
  from pg_policies
 where schemaname='nucleo' and tablename in (
 'contactos_whatsapp','permisos_contacto','conversaciones','conversacion_mensajes',
 'solicitudes','hoja_ruta','id_comercial_contador','auditoria_consultas_agente')
 order by 1,2;
```

Medido el 2026-10-30: **9 filas**, todas con `roles = {public}` (el pseudo-rol
`PUBLIC`: la política aplica a **cualquier** rol sujeto a RLS, no solo a `tei_app`)
y predicado `(empresa_id = nucleo.ctx_empresa())`.

| tabla | política | cmd | qual | with_check |
|---|---|---|---|---|
| `auditoria_consultas_agente` | `consultas_agente_insercion` | `INSERT` | — | `empresa_id = nucleo.ctx_empresa()` |
| `auditoria_consultas_agente` | `consultas_agente_lectura` | `SELECT` | `empresa_id = nucleo.ctx_empresa()` | — |
| `contactos_whatsapp` | `tenant_empresa` | `ALL` | idem | idem |
| `conversacion_mensajes` | `tenant_empresa` | `ALL` | idem | idem |
| `conversaciones` | `tenant_empresa` | `ALL` | idem | idem |
| `hoja_ruta` | `tenant_empresa` | `ALL` | idem | idem |
| `id_comercial_contador` | `tenant_empresa` | `ALL` | idem | idem |
| `permisos_contacto` | `tenant_empresa` | `ALL` | idem | idem |
| `solicitudes` | `tenant_empresa` | `ALL` | idem | idem |

Lectura:

- Las 7 tablas operativas tienen **una** política `FOR ALL` (permisiva por
  defecto), o sea la misma expresión cubre `SELECT`, `INSERT`, `UPDATE` y
  `DELETE`. No hay política de `UPDATE`/`DELETE` separada; el control de "quién
  puede borrar" queda en el `GRANT` (§V4), no en RLS.
- `auditoria_consultas_agente` está partida a propósito (`INSERT` + `SELECT`) y
  **no tiene política de `UPDATE` ni `DELETE`**: con RLS habilitado y sin
  política, esas operaciones devuelven 0 filas / fallan, lo que es coherente con
  el `GRANT` `tei_app=ar` (sin `w`/`d`) y con el trigger append-only (AW-13).
- Ninguna política distingue rol ni exige `WITH CHECK` más estricto que `USING`:
  el aislamiento es puramente por `empresa_id`. La autorización por rol/permiso
  (`admin` vs `asesor`) **no** vive acá; ver §4.1 y AW-07 (no garantizada en DB).
- `{public}` implica que también aplica a `supabase_admin`, pero ese rol **es
  dueño** de las tablas y no tiene `BYPASSRLS`; el `FORCE ROW LEVEL SECURITY`
  (§V1) es lo que lo somete. Si en el futuro se agrega un rol con `BYPASSRLS`
  (p. ej. un rol de replicación o `service_role` de Supabase), **se salta estas
  políticas sin error**: verifícalo antes de asignarlo.

**Esperado post:** 9 filas exactamente como la tabla; si aparece una décima, o si
`consultas_agente_*` cambia de `cmd`, la superficie de escritura cambió y hay que
revisar el `GRANT` correspondiente.

### V2 — Conteo de triggers (25)

```sql
select c.relname as tabla, count(*) as n_triggers
  from pg_trigger t join pg_class c on c.oid=t.tgrelid
  join pg_namespace n on n.oid=c.relnamespace
 where n.nspname='nucleo' and not t.tgisinternal and c.relname in (
 'contactos_whatsapp','permisos_contacto','conversaciones','conversacion_mensajes',
 'solicitudes','hoja_ruta','id_comercial_contador','auditoria_consultas_agente')
 group by 1 order by 1;
```

Medido: auditoría 2; contactos 3; conversaciones 3; mensajes 4; hoja_ruta 3;
contador 3; permisos 3; solicitudes 4 → **25**.
**Esperado post:** exactamente estos números. Si falta `trg_solicitudes_10_transicion`
o `trg_mensajes_10_validar`, AW-10/AW-04 quedan sin mecanismo.

> **Adenda 2026-10-30 (`0022`, no reescribe la medición anterior).** Con los 3
> triggers de §8.1 el conteo vigente es: hoja_ruta **4**
> (`trg_hoja_ruta_10_transicion`), contador **4**
> (`trg_contador_10_no_retrocede`) y viajes **11**
> (`trg_viajes_10_id_comercial_inmutable`, fuera de la lista de tablas de arriba);
> el resto de la tabla no cambia. Total del módulo: **28**.

### V3 — Índices únicos (parciales, de invariantes y estructurales)

```sql
select indexname, indexdef from pg_indexes
 where schemaname='nucleo' and tablename in (
 'contactos_whatsapp','permisos_contacto','conversaciones','conversacion_mensajes',
 'solicitudes','hoja_ruta','id_comercial_contador','auditoria_consultas_agente')
   and indexdef ilike '%unique%'
 order by tablename, indexname;
select indexname, indexdef from pg_indexes
 where schemaname='nucleo' and tablename in ('viajes','usuarios_empresa')
   and indexname in ('uq_viajes_id_comercial','idx_viajes_id_comercial','uq_usuarios_empresa_empresa');
```

**Esperado post:** `uq_contactos_telefono_activo`, `uq_conversacion_activa`,
`uq_mensaje_wa_message_id`, `uq_permisos_contacto_valor`,
`uq_solicitud_idempotencia`, `uq_hoja_ruta_carga_por_solicitud`,
`uq_viajes_id_comercial`, `uq_usuarios_empresa_empresa`, con el `WHERE` del
predicado. Un `UNIQUE` sin el `WHERE` cambia el invariante (bloquearía filas
inactivas o no idempotentes).

### V4 — GRANTs reales de `tei_app`

> **Trampa medida:** `information_schema.role_table_grants` devuelve **0 filas**
> como `postgres`, porque el otorgante es `supabase_admin` y `postgres` no es
> miembro. No es un defecto del esquema: la consulta es la equivocada. Usar
> `relacl` o `has_table_privilege`.

```sql
select c.relname, c.relacl::text
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
 where n.nspname='nucleo' and c.relname in (
 'contactos_whatsapp','permisos_contacto','conversaciones','conversacion_mensajes',
 'solicitudes','hoja_ruta','id_comercial_contador','auditoria_consultas_agente')
 order by 1;

select t,
       has_table_privilege('tei_app','nucleo.'||t,'select') as sel,
       has_table_privilege('tei_app','nucleo.'||t,'insert') as ins,
       has_table_privilege('tei_app','nucleo.'||t,'update') as upd,
       has_table_privilege('tei_app','nucleo.'||t,'delete') as del
  from unnest(array['contactos_whatsapp','permisos_contacto','conversaciones',
   'conversacion_mensajes','solicitudes','hoja_ruta','id_comercial_contador',
   'auditoria_consultas_agente']) as t;
```

Medido: 7 tablas con `sel/ins/upd = t/t/t`, `del = f`; auditoría `t/t/f/f`.
**Esperado post:** idéntico; `UPDATE` en auditoría o `DELETE` en cualquiera de
las 8 ⇒ `42501`.

### V5 — Roles

```sql
select rolname, rolbypassrls, rolsuper, rolcanlogin from pg_roles where rolname='tei_app';
```

Medido: `tei_app | f | f | t`. **Esperado post:** `rolbypassrls=f`.

### V6 — Tipos, funciones y columna

```sql
select count(*) from pg_type t join pg_namespace n on n.oid=t.typnamespace
 where n.nspname='nucleo' and t.typname in (
 'rol_contacto_whatsapp','estado_otp','direccion_mensaje','modalidad_mensaje',
 'estado_procesamiento_mensaje','tipo_solicitud','estado_solicitud','estado_hoja_ruta');
-- esperado 8 (y typtype='e' en los 8)

select p.proname from pg_proc p join pg_namespace n on n.oid=p.pronamespace
 where n.nspname='nucleo' and p.proname in (
 'obtener_siguiente_id_comercial_flete','registrar_id_comercial_flete',
 'fn_mensaje_validar','fn_solicitud_transicion','fn_consultas_agente_inmutable');
-- esperado 5

select column_name, data_type, is_nullable from information_schema.columns
 where table_schema='nucleo' and table_name='viajes' and column_name='id_comercial_flete';
-- esperado text / YES
```

### V7 — Sondas de RLS (sustituyen parcialmente a `0021_03`)

`postgres` **no** puede `SET ROLE tei_app` (`42501 permission denied to set role`);
`supabase_admin` sí es miembro. Conexión como `tei_app` por peer auth falla
(`Peer authentication failed`), así que la prueba con el rol real requiere el
método de `supabase/tests/0020_01_aislamiento.sql` (`-U tei_app` con la URL de
aplicación). Sondas ejecutadas como `supabase_admin` + `SET LOCAL ROLE tei_app`:

| Sonda | Resultado medido |
|---|---|
| `SELECT count(*) FROM nucleo.viajes` sin `app.empresa_id` | **0** filas (fail-closed) |
| `SELECT count(*) FROM nucleo.viajes` con contexto empresa A | **5** filas (los viajes de A; no aparecen los 218) |
| `INSERT` en `contactos_whatsapp` sin contexto | **42501** (`new row violates row-level security policy`) |
| `INSERT` con `empresa_id = B` y contexto A | **42501** |
| `INSERT` con contexto A | OK; visible en la misma transacción |
| `DELETE` en `auditoria_consultas_agente` como `tei_app` | **42501** (`permission denied for table`) — lo corta el GRANT, antes del trigger |
| `INSERT` + `SELECT` en auditoría con contexto A | OK (1 fila) |

**Lo que estas sondas no prueban:** aislamiento entre dos empresas con datos en
las tablas del módulo (hoy están vacías), `SET LOCAL` a través del pooler en modo
transacción, ni `USING`/`WITH CHECK` por operación en cada tabla. Eso es
`0021_03` (qa, O1.2).

### V8 — Sondas de límites (hallazgos D2/D3/D4/D5/D9)

Todas dentro de `BEGIN … ROLLBACK`; residuo verificado en 0.

| Sonda | Resultado medido | Sección |
|---|---|---|
| `UPDATE … id_comercial_flete` de `SQM-00001` a `OTR-00999` | **aceptado** | D2 |
| `UPDATE nucleo.id_comercial_contador SET ultimo = 0` (de 500) | **aceptado** | D3 |
| Dos clientes de A generan `SQM-00001`; `count(*) where empresa=A and código='SQM-00001'` | **2** | D4 |
| `hoja_ruta: rechazado → cargado` y `cargado → propuesto` | **ambos aceptados** | D5 |
| Contador en 99999 ⇒ `obtener_siguiente…` | devuelve **`SQM-10000`** (alias de un código ya emitido) | D9 |
| `INSERT` directo de una solicitud en `aprobada` con sus campos | **aceptado** (diseño, `0021:485-487`) | §4.3 |
| `INSERT` de mensaje de empresa B en conversación de A | **`23503`** | AW-04 |

> **Adenda 2026-10-30 (`0022`, no reescribe la medición anterior).** Las filas de
> D2, D3, D5 y D9 describen el estado **antes** de `0022`. Con `0022` aplicada,
> las cuatro sondas devuelven `23514` y dejan el dato intacto (§8.1). D4 sigue
> aceptando el código duplicado entre clientes: es decisión de negocio abierta.

### V9 — Residuo

```sql
select (select count(*) from nucleo.contactos_whatsapp) as contactos,
       (select count(*) from nucleo.conversaciones) as conversaciones,
       (select count(*) from nucleo.conversacion_mensajes) as mensajes,
       (select count(*) from nucleo.solicitudes) as solicitudes,
       (select count(*) from nucleo.hoja_ruta) as hoja_ruta,
       (select count(*) from nucleo.id_comercial_contador) as contador,
       (select count(*) from nucleo.auditoria_consultas_agente) as audit_consultas,
       (select count(*) from nucleo.viajes where id_comercial_flete is not null) as viajes_con_id;
```

Medido tras todas las pruebas y sondas: **todo 0**. `0021_01` y las sondas no
dejan datos.

---

## 7. Reconciliación de IDs: `AW-NN` ↔ `INV-*`

**Problema:** la migración aplicada referencia `AW-01..AW-16` (`0021:87-88`) y no
se puede editar; el registro del repo usa `INV-<categoría><NN>` (`invariantes.md`
§0). Si se registraran dos veces los mismos invariantes con dos IDs, el handoff a
`qa`/`backend` se rompe.

**Decisión (2026-10-30):**

1. **ID canónico:** `INV-AW01` … `INV-AW16`. La "categoría" es `AW` (módulo
   agente WhatsApp). Precedente en el propio registro: `INV-DOC04` (tres letras) e
   `INV-R02-NN` (atado a una regla de negocio) ya rompen la categoría de una letra.
2. **`AW-NN` queda como alias estable**, uno a uno (`AW-01 ↔ INV-AW01`). Se usa en
   el `.sql` aplicado y en los comentarios de las pruebas; **no se renombra nada
   en la base**.
3. **Sin duplicados:** no existía ningún otro `INV-AW*` en el registro
   (`git grep -o 'INV-AW[0-9]*' HEAD -- docs/` → 0); el bloque nuevo de
   `invariantes.md` §11 es la única fuente de esos 16 IDs.
4. **Regla de citación:** `datos` cita `INV-AWNN`; `qa`/`backend` pueden citar
   `AW-NN` en el código y debe entenderse como el mismo invariante. Si algún día
   se escribe un documento que use ambos, la forma larga es `INV-AWNN (AW-NN)`.
5. La tabla de §3 de este documento es la **ficha completa**; `invariantes.md` §11
   es el **registro** (estado + prueba + alias).

**Tabla de equivalencia (16/16, sin huecos):**

| Alias en `0021` | ID canónico | Origen del alias |
|---|---|---|
| `AW-01` | `INV-AW01` | `0021:87-88` (encabezado) y `0021_01` C7x |
| `AW-02` | `INV-AW02` | idem · C3x |
| `AW-03` | `INV-AW03` | idem · C1–C4 |
| `AW-04` | `INV-AW04` | idem · C8x |
| `AW-05` | `INV-AW05` | idem · C6x |
| `AW-06` | `INV-AW06` | idem · C5x |
| `AW-07` | `INV-AW07` | idem · gate O2.2 (sin prueba de base) |
| `AW-08` | `INV-AW08` | idem · C5D/C11B + sondas |
| `AW-09` | `INV-AW09` | idem · C9C/C9D |
| `AW-10` | `INV-AW10` | idem · C9E–C9J (fusiona "terminal documentado" y "terminal definitivo") |
| `AW-11` | `INV-AW11` | idem · O2.5 (parcial) |
| `AW-12` | `INV-AW12` | idem · C9B |
| `AW-13` | `INV-AW13` | idem · C10x |
| `AW-14` | `INV-AW14` | idem · C11x |
| `AW-15` | `INV-AW15` | idem · C12x |
| `AW-16` | `INV-AW16` | idem · sondas §6 V7 |

Regla mecánica: `INV-` + alias sin guion (`AW-07` → `INV-AW07`). No hay `AW-17`
ni saltos; el encabezado de `0021` enumera 16 y §3 cubre los 16.

---

## 8. Defectos, límites y riesgos encontrados (2026-10-30)

Este inventario se levantó **antes** de `0022`: en ese momento `0021` estaba
aplicada y era forward-only, así que ninguno se corrigió en ella. Se reportan
con evidencia medida. **Estado vigente: D2, D3, D5 y D9 quedaron cerrados por
`0022` (§8.1); D7 quedó probado en clon y D10 se registra como riesgo de
proceso local (§8.2); D4, D6 y D8 siguen abiertos.** Adenda 2026-10-30: el
script de rollback que D1 daba por inexistente ya está en `supabase/tests/`
(`0021_99_rollback.sql`, `0022_99_rollback.sql`; ambos **untracked**) y el
ciclo se ejecutó (§8.2).

| ID | Hallazgo | Evidencia | Impacto | Acción sugerida |
|---|---|---|---|---|
| **D1** | La migración remite a `supabase/tests/0021_99_rollback.sql` (`:79-85`) y **ese archivo no existía** al levantar este inventario (`ls supabase/tests/` solo tenía `0021_01_smoke.sql`; `find . -name '*0021_99*'` → vacío) | lectura + `ls` | El rollback estaba descrito, **no probado**. Bloquea aplicar `0021` fuera de un clon | Escribir y ejecutar el script en `tei_test` antes de cualquier aplicación real. **[Adenda 2026-10-30: `0021_99` y `0022_99` existen (untracked), se ejecutaron y el ciclo cerró con 4 suites verdes — §8.2.]** |
| **D2** | `nucleo.viajes.id_comercial_flete` **se puede reasignar** después de asignado, contra el `COMMENT` que dice "No editable después de asignado" (`:566-570`) | sonda: `UPDATE … 'SQM-00001'` → `UPDATE … 'OTR-00999'` **aceptado**; ninguna función menciona la columna (solo las dos de generación) | R-04: un código puede cambiar de viaje; el histórico queda solo en `nucleo.auditoria` | Trigger `BEFORE UPDATE` que rechace cambio de valor no nulo (o corregir el comentario y aceptar la reasignación como decisión) |
| **D3** | El "contador nunca retrocede" (`:591-593`) **no está impuesto**: `tei_app` tiene `UPDATE` sobre `id_comercial_contador` y un `UPDATE` directo baja `ultimo` | sonda: `ultimo 500 → 0` aceptado; `relacl` de la tabla = `tei_app=arw` | Un bug del servicio puede emitir códigos ya usados; la `UNIQUE` de `viajes` lo convierte en `23505` (no en duplicado silencioso) | Trigger que impida disminuir `ultimo`, o `REVOKE UPDATE` y escritura solo por función |
| **D4** | La resolución `(empresa, código)` **no es única**: la `UNIQUE` es `(empresa, cliente, código)` y dos clientes pueden usar el mismo prefijo | sonda: dos clientes de A generan ambos `SQM-00001`; `count(*) where empresa=A and código='SQM-00001'` = **2** | La tool de lectura de §16.2 puede recibir 2 fletes para un código; el comentario de `:559-561` sugiere resolución por `(empresa, código)` | Decisión de negocio: prefijo único por cliente (constraint/tabla de prefijos) o resolución que exija cliente |
| **D5** | `nucleo.hoja_ruta` **no tiene máquina de estados**: solo CHECK de campos por estado | sonda: `rechazado → cargado` **aceptado**; `cargado → propuesto` **aceptado** (libera el slot único) | La única garantía es "a lo sumo un `cargado` **vigente** por solicitud"; el histórico no impide reciclar el estado | Trigger de transición análogo a `fn_solicitud_transicion`, si D-10 exige que `rechazado`/`cargado` sean terminales |
| **D6** | **Rechazo solo-logra** (AW-11) no es garantía de base: nada impide que un servicio, al rechazar, escriba además en `viajes` u `hoja_ruta` | lectura del DDL: no hay trigger que lo impida; el módulo no tiene writers aún | Si el backend lo implementa mal, la base no lo detecta | Prueba de integración O2.5 + revisión de `backend` |
| **D7** | `0021` fue **editada después de una primera aplicación** en `tei_test` (lo dice el propio archivo: `:844-845`, "defecto detectado en la primera aplicación … y corregido aquí") | comentario en el DDL | En una base desechable es aceptable; **en cualquier otra viola forward-only** | No repetir: si aparece un defecto al aplicar, migración nueva. **[Adenda 2026-10-30: probado en clon — ciclo rollback/re-aplicación con 4 suites verdes (§8.2); la edición fue anterior a ese cierre.]** |
| **D8** | `wa_message_id` es único **global** (AW-01): un tenant podría "reservar" un id ajeno y bloquear su inserción | lectura de `:346-347`; `wa_message_id` no lleva `empresa_id` | DoS entre tenants de baja probabilidad (los `wamid` del BSP son opacos y largos) | Aceptar y documentar; si preocupa, índice por `(empresa_id, wa_message_id)` requiere migración |
| **D9** | **R-04 tiene un tope duro de 99.999 códigos por `(empresa, cliente)`** y al llegar a 100.000 **reutiliza un código anterior**: `lpad(v_numero::text, 5, '0')` **trunca** si el número tiene 6 dígitos | sonda: contador en `99999` ⇒ `obtener_siguiente…` devuelve **`SQM-10000`** (9 caracteres): `lpad(…,5,'0')` trunca `100000` y repite el código que se emitió con contador `10000` (o el que corresponda si el contador saltó por cutover). La asignación al viaje fue **aceptada** en la sonda porque ese código no estaba asignado; si el original sigue asignado, la `UNIQUE` la rechaza con `23505` | A partir de 100.000 fletes del mismo cliente, la numeración deja de ser creciente y "sin reutilización": o falla la asignación (`23505`) o se reutiliza un código si el original perdió el valor | Decisión de formato (6+ dígitos, prefijo + año, o `raise` explícito al superar 99999) en una migración nueva; hasta entonces, documentar el tope y monitorear el contador |
| **D10** | La re-aplicación limpia de `0021` como `supabase_admin` **no reproduce el ACL de `postgres`** en las 8 tablas del módulo: queda solo `SELECT` (`pg_read_all_data`); el `GRANT ALL` previo no alcanza a tablas nuevas | `has_table_privilege('postgres', …, 'INSERT') = false` en las 8; `0021_01` como `postgres` aborta con `42501` (`docs/qa/informes/2026-10-31-o1.3-rollback-reaplicacion.md:266-297,424-441`) | Suites `0021_01`/`0021_02` (documentadas para `postgres`) no reproducibles solo con `0021`+`0022` en un clon; **local, no producción** | Restaurar el ACL de `postgres` tras aplicar, o correr las suites con `supabase_admin`; el rol que aplica migraciones debe ser el mismo en todos los entornos; no editar `0021` (§8.2) |

**Riesgo de despliegue (no es defecto del esquema):** el módulo está apagado
(DEC-10) y ningún código lo lee (grep en 0). El backend ya tiene dos motores: el
del núcleo usa `tei_app` si `NUCLEO_DATABASE_URL` existe y, si no, cae a
`DATABASE_URL` con el WARNING `RLS inerte: configure NUCLEO_DATABASE_URL`
(`backend/app/core/database.py:24-32,110-135`). **Cuál de los dos está activo no
se verificó** (🟡: no se lee `.env`). Si el módulo se enciende sobre el fallback,
AW-16 queda solo en el servicio (RA-03). Ver `rls-multiempresa.md` §5.3 y usar
`get_session_nucleo` en los endpoints nuevos.

### 8.1 Cierre de D2, D3, D5 y D9 por `0022` (2026-10-30)

`supabase/migrations/0022_agente_whatsapp_endurecimiento.sql` (untracked,
aplicada **solo** en `tei_test`) impone los cuatro mecanismos. Cero cambios de
esquema o de datos: 4 funciones y 3 triggers (`0022:183-446`), con
precondiciones defendidas P1-P4 dentro de la transacción (`0022:186-274`).

| Defecto | Mecanismo que lo cierra | `0022:línea` | SQLSTATE | Evidencia real (2026-10-30, `tei_test`) |
|---|---|---|---|---|
| **D3** | trigger `trg_contador_10_no_retrocede` sobre `nucleo.id_comercial_contador`: rechaza `new.ultimo < old.ultimo`. Corre antes de `touch`/`version` (orden alfabético: `10` < `audit`/`touch`/`version`) | función `284-297`, comment `299-303`, trigger `305-307` | `23514` | sonda `UPDATE ultimo 500 → 0` ⇒ 23514; `500 → 600` sigue permitido. Repetida con **`tei_app`** (sin BYPASSRLS, contexto A): 23514. `registrar_id_comercial_flete` usa `greatest` (`0021:668`) y no se rompe |
| **D9** | `obtener_siguiente_id_comercial_flete` rechaza `v_numero > 99999` **después** del upsert: el `raise` revierte el incremento (no quema el número). Formato y `lpad` intactos: nunca emite 6 dígitos | función `401-444`, guarda `434-440` | `23514` | contador 99999 ⇒ 23514 y el contador sigue en **99999**; 99998 ⇒ `SQM-99999`; con el tope retirado (mutación) vuelve a emitir `SQM-10000` (9 caracteres) |
| **D2** | trigger `trg_viajes_10_id_comercial_inmutable`: `old.id_comercial_flete is not null and new.id_comercial_flete is distinct from old.id_comercial_flete` ⇒ 23514. Incluye el paso a `NULL`: liberaría el código para reasignarlo, porque `uq_viajes_id_comercial` solo cubre valores no nulos | función `315-330`, comment `332-336`, trigger `339-341` | `23514` | `NULL → SQM-00001` permitido (cutover/backfill); `SQM-00001 → SQM-09999` y `SQM-00001 → NULL` ⇒ 23514; con el trigger retirado la reasignación se acepta |
| **D5** | trigger `trg_hoja_ruta_10_transicion`: solo `propuesto → solicitud_creada` y `solicitud_creada → cargado` o `rechazado`; `cargado` y `rechazado` terminales; `payload` inmutable en UPDATE (`valores_cargados` libre, ADR-0003 §14.2) | función `349-382`, comment `384-388`, trigger `390-392` | `23514` | `propuesto → cargado`, `propuesto → rechazado`, `cargado → rechazado`, `cargado → propuesto`, `rechazado → cargado` y cambio de `payload` ⇒ 23514; la ruta legal y el cambio de `valores_cargados` en `cargado` pasan. Repetida con `tei_app`: 23514 |

Sondas ejecutadas con `postgres` (BYPASSRLS) y con `tei_app` por TCP
(`app.empresa_id` = empresa A), todas en `BEGIN … ROLLBACK`: sin residuo. La
mutación de los 4 mecanismos (retirarlos dentro de una transacción) confirmó que
sin ellos el caso ilegal vuelve a aceptarse y que el `ROLLBACK` los restaura.

**Riesgo residual que `0022` no cierra (por alcance):**

- `tei_app` conserva `UPDATE` sobre `id_comercial_contador`. Ya no puede bajar el
  contador, pero **sí puede adelantarlo** (`ultimo = 99999` desde 5). Eso no
  reutiliza códigos: agota el rango y la función falla cerrada. No es una fuga.
- `INSERT` en `hoja_ruta` con `estado='cargado'`/`'rechazado'` directo sigue
  permitido si los `CHECK` de `0021:520-522` se cumplen: la guarda de `0022` es
  `BEFORE UPDATE`. El alta la controla el servicio (O2.5).
- `hoja_ruta.solicitud_id` no es inmutable tras `solicitud_creada` (fuera de
  alcance). Cambiarlo en `cargado` podría mover la unicidad
  `uq_hoja_ruta_carga_por_solicitud`; no se restringió porque no estaba pedido.

**Efecto en las pruebas de `qa` (no corregido aquí).** El smoke
`supabase/tests/0021_01_smoke.sql` tiene dos aserciones que describen el
comportamiento **anterior**; con `ON_ERROR_STOP` el script aborta en la primera:

- `0021_01_smoke.sql:566-578` (C10E) usa `propuesto → cargado` directo para
  provocar el `23505` de `uq_hoja_ruta_carga_por_solicitud`; con D5 la
  transición se rechaza antes con `23514`.
- `0021_01_smoke.sql:669-670` (C11H) afirma que se puede volver a `NULL` un ID
  ya asignado; D2 lo prohíbe por diseño.

Con las dos aserciones adaptadas (pasar por `solicitud_creada`; esperar `23514`
al desasignar), una **copia fuera del repo** corre los casos 1-14 sin errores
(62 `NOTICE OK`, 0 `FAIL`). `supabase/tests/` es de `qa`: **no se editó**. Las
otras tres suites siguen verdes: `0021_02` (C1, C1b, C2a, C2b, C3), `0021_03`
(RLS y append-only con `tei_app`) y `0021_04` (5 mutaciones).

> **Adenda 2026-10-30 (cierre O1.3).** `qa` adaptó C10E y C11H en
> `supabase/tests/0021_01_smoke.sql` y el smoke volvió a **14/14 (63 `NOTICE
> OK`)**; `0021_04` se extendió a M1–M9. Ya no hace falta el parche fuera del
> repo (`docs/qa/informes/2026-10-31-o1.3-rollback-reaplicacion.md:300-403`).

### 8.2 D7 probado en clon y D10 registrado (adenda 2026-10-30)

**D7 — reproducibilidad: probado en clon.** `qa` ejecutó el ciclo completo en
`tei_test`: `supabase/tests/0022_99_rollback.sql` →
`supabase/tests/0021_99_rollback.sql` → verificación de cero objetos →
re-aplicación de `0021` y `0022` como `supabase_admin` → las 4 suites verdes
(`0021_01` 14/14 con 63 `OK`; `0021_02` con 8+2+2 conexiones reales; `0021_03`
con el rol `tei_app`; `0021_04` M1–M9)
(`docs/qa/informes/2026-10-31-o1.3-rollback-reaplicacion.md:94-403`;
`supabase/tests/README.md:145-170`). La edición de `0021` que motivó D7 fue
**anterior** a este cierre: el ciclo no restauró un dump, revirtió y re-aplicó
las migraciones del repo, y el catálogo final quedó en 8 tablas, 8 tipos, 44
políticas y las 3 funciones + 3 triggers de `0022`
(`docs/qa/informes/2026-10-31-o1.3-rollback-reaplicacion.md:226-258`). Eso
demuestra que el esquema es reproducible desde `supabase/migrations/`. **Estado:
"probado en clon (2026-10-30)"**, no probado con datos reales ni en otra base.
Queda como **regla de proceso**: nunca editar una migración aplicada; todo
defecto nuevo se corrige con migración nueva (`0022` es el ejemplo).

**D10 (nuevo, severidad media) — la re-aplicación no reproduce el ACL de
`postgres`. Clasificación: riesgo de proceso local (clon), no de producción por
este mecanismo.** Re-aplicar `0021` como `supabase_admin` deja a `postgres`
**sin INSERT/UPDATE** en las 8 tablas del módulo: `0021:855-868` otorga solo a
`tei_app`; el `GRANT ALL … TO postgres` que el clon tenía era previo a las
tablas y no está en ninguna migración, y `pg_read_all_data` le deja solo
`SELECT`. Verificado con `has_table_privilege('postgres', …, 'INSERT') = false`
en las 8 tablas y con `0021_01` abortando con `42501` bajo `postgres`
(`docs/qa/informes/2026-10-31-o1.3-rollback-reaplicacion.md:266-297,424-441`;
`supabase/tests/README.md:163-168`). Según la verificación de `qa`, **todas** las
tablas de `nucleo` en `tei_test` son de `supabase_admin`, no solo las del
módulo. En producción el rol previsto del núcleo es `tei_app` (GRANT explícito
en `0021:855-868`) y el legacy usa `postgres` solo sobre `public`; el ACL real
de la base de la app **no se verificó** (🟡, no se lee `.env`), y el fallback a
`DATABASE_URL` con `postgres` sigue siendo el riesgo RA-03, distinto de D10.
**Regla operativa:** en un clon local, después de aplicar `0021`/`0022`,
restaurar el ACL de `postgres` (el `GRANT ALL` de §4.6 del informe) **o** correr
las suites con `supabase_admin`; y **el rol que aplica migraciones debe ser el
mismo en todos los entornos**. No se corrige editando `0021` (forward-only): la
salida es un script de setup o cambiar el rol de las suites; decisión pendiente
de `orquestador`.

---

## 9. Handoff

### 9.1 A `backend` (O2)

| SQLSTATE / caso | Origen típico | HTTP esperado | Nota |
|---|---|---|---|
| `23505` | AW-01 (`wa_message_id` repetido), AW-02 (teléfono activo), AW-06, AW-12, AW-13, AW-14 | **409** (`RegistroDuplicado`) | Un webhook repetido debe ser **idempotente**, no un 409 visible al usuario final: el runtime debe absorberlo y responder 200 |
| `23514` | AW-03, AW-04, AW-05, AW-09, AW-10, AW-11, AW-13, AW-14 | **hoy 409** (`ReglaNegocioViolada`, `errores.py:106-107`); `AGENTS.md` §8 pide **422** | Deuda de mapeo ya registrada en `garantias.md` §15.2; `backend` decide y actualiza |
| `23503` | AW-08 (FK compuesta) | **422** (`DatosInvalidos`) | Nunca 500; no exponer `message_primary` de PostgreSQL |
| `42501` | AW-15/AW-16 (GRANT o RLS) | **403/404 sin filtrar existencia** | `nucleo.errores` no tiene rama para `42501` hoy: cae en `ErrorPersistencia` ⇒ **500**. Handoff concreto |
| AW-07 (sin fila ACL) | gate O2.2 | **403** con mensaje neutro | Decisión del gate, no de la base |
| AW-11 (rechazo) | O2.5 | 200/204 | Verificar que **no** escribe en `viajes`/`hoja_ruta` |

Pendiente explícito de `backend`: absorber `23505` de `uq_mensaje_wa_message_id`
como éxito idempotente y registrar `request_id` en
`auditoria_consultas_agente` (la columna existe, nadie la escribe todavía).

### 9.2 A `qa` (O1.2)

- `0021_02` — concurrencia real con **dos conexiones**: dos `obtener_siguiente…`
  en paralelo (códigos distintos), dos webhooks con el mismo `wa_message_id`
  (uno gana), dos aprobaciones de la misma solicitud (una gana), dos aperturas de
  conversación (una gana).
- `0021_03` — RLS con el **rol real** `tei_app`: matriz `SELECT/INSERT/UPDATE/
  DELETE` × 8 tablas × (sin contexto / empresa A / empresa B), `SET LOCAL` por
  transacción, y el caso del pooler en modo transacción.
- `0021_04` — **mutación**: retirar el índice/trigger/CHECK en una copia y
  confirmar que el caso de `0021_01` falla. Cubre al menos AW-01, AW-02, AW-06,
  AW-10, AW-13, AW-14, AW-15.
- Casos que `0021_01` **no** cubre y conviene agregar: rechazo de una solicitud
  (AW-11), FK compuesta de `solicitudes`→`viajes` y `hoja_ruta`→`solicitudes`
  (AW-08), `UPDATE` de `contacto_id` en un mensaje (AW-04), reasignación del ID
  comercial (D2), transición `rechazado → cargado` (D5).

---

*Documento creado 2026-10-30 por el agente `datos`. Reemplaza el contrato que la
migración `0021` referenciaba y que no existía. No reescribe historia: el DDL
aplicado no se toca; los defectos se reportan en §8 para una migración futura.*
