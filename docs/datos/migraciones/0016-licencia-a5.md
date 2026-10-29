# Migración 0016 — Solo A5 es asignable (R-02) y ventana de aviso por defecto de 14 días

> **Pregunta que responde:** ¿qué garantiza la migración 0016 y cómo se revierte?
> **Dueño:** `datos` · **Verificado:** 2026-10-29 · **Método:** lectura de DDL
> **Estado:** SQL escrito en `supabase/migrations/0016_licencia_a5_bloqueante.sql`; **aplicación en base 🔴 no verificada**.
> **Re-verificar con:** `grep -n "create trigger" supabase/migrations/0016_licencia_a5_bloqueante.sql`


> **Autor:** agente `datos` · **Fecha:** 2026-10-29 · **Riesgo:** Medio
> (regla operativa con efecto en asignación; sin dinero)
> **Estado:** SQL escrito en `supabase/migrations/0016_licencia_a5_bloqueante.sql`;
> **no aplicado, no ejecutado** (🔴).
> **Aprobación requerida para:** aplicar la migración. El backfill de
> `dias_alerta_documentos` (§6) **no** forma parte de esta migración y requiere
> autorización separada.

---

## 1. Propósito

Imponer en PostgreSQL la regla aprobada por el dueño:

> "Solo la clase A5 sirve, ninguna otra. Bloqueo de la asignación. Aviso cuando
> la licencia vence en 14 días o menos."

Hoy la clase de licencia se evalúa en Python, **como advertencia y solo si el
tracto tiene el array configurado**:

| Hecho | Evidencia |
|---|---|
| `licencias_permitidas` es un array configurable por tracto | `0004:207` |
| Si el array está vacío, **no se evalúa nada** | `backend/app/nucleo/politicas.py:297` |
| Clase faltante o no permitida se agrega como `Hallazgo(..., False)` = **no bloqueante** | `politicas.py:301-320` |
| La vigencia del documento sí es bloqueo duro en la base | `0004:1080-1102` (faltante 1091-1094, vencido 1097-1101) |
| `dias_alerta_documentos` por defecto 30 en la base y **30 en Python** | `0004:120-121`, `backend/app/nucleo/models.py:221` |

Consecuencia: un chofer con clase A3, o sin clase, podía quedar asignado si el
tracto no tenía el array o si el servicio solo advertía. La regla del dueño es
**global**, no por tracto, y debe ser bloqueo.

## 2. Invariantes

| ID | Enunciado | Mecanismo | SQLSTATE |
|---|---|---|---|
| INV-R02-01 | Si `nucleo.viajes.chofer_id` no es nulo y `estado <> 'anulado'`, entonces `upper(btrim(choferes.licencia_clase)) = 'A5'` (clase ausente ⇒ viola) | `trg_viajes_03_licencia_a5` → `nucleo.fn_viaje_licencia_a5()` | `23514` |
| INV-R02-02 | El documento `licencia_conducir` del chofer debe vencer en o después del fin efectivo del viaje (+ `dias_margen_documentos`) | `nucleo.validar_documentos_recurso` (`0004:1019-1104`), aplicado a todo viaje con 3 recursos por **0015** | `23514` |
| INV-R02-03 | Licencia que vence entre 14 y 1 días: **aviso**, no bloqueo | **Servicio**, no base. `empresas.dias_alerta_documentos` (default 14 desde 0016) | — |

Escritores cubiertos: cualquier `INSERT`/`UPDATE` sobre `nucleo.viajes` con
`chofer_id` (backend del núcleo, scripts, `psql`, seeds). No cubre `public.viajes`
(legacy no tiene clase de licencia: `0001`).

## 3. Dónde vive la regla y por qué

### 3.1 Trigger sobre el viaje, no `CHECK` en `choferes`

R-02 dice **"bloqueo de la asignación"**. Un `CHECK` en `nucleo.choferes`:

- impediría registrar un conductor con clase distinta, incluso como dato
  histórico o para otra función (A3/A4 existen en Chile y pueden ser legítimos
  para otros vehículos);
- obligaría a un backfill destructivo de la tabla de maestros;
- excedería lo pedido (la regla prohíbe asignar, no existir).

El trigger bloquea exactamente lo que la regla prohíbe y no toca maestros.

### 3.2 `tractos.licencias_permitidas` queda **deprecado**, no borrado

Decisión explícita (no olvido):

- **No se borra** (contiene datos) ni se reescribe.
- **No se le agrega `CHECK`**: rechazaría la edición de filas existentes desde la
  UI de maestros (`frontend/src/components/maestros/config.ts:76`) sin mejorar la
  garantía, que ya es global.
- Se marca con `COMMENT ... 'DEPRECADO (0016 / R-02) ...'`: ya no otorga ni
  restringe permisos.
- Si algún tracto lo tiene con valores distintos de A5, la configuración
  **miente** (sugiere que A3/A4 sirven). Se detecta con P2.3 y se limpia con una
  sentencia separada y auditada.
- Handoff: `backend` debe dejar de validar contra el array (`politicas.py:297-320`)
  y `frontend` debe dejar de ofrecer el campo.

### 3.3 Orden de triggers: la clase se evalúa antes que los documentos

Orden alfabético real: `00_ventana` → `03_licencia_a5` → `05_documentos` (0015) →
`10_validar` → … Un chofer A3 con licencia vencida falla por **clase**, que es el
mensaje correcto para el operador. Verificado por diseño del nombre; la prueba
`0016_01` lo confirma con un A3 de documentos vigentes (el rechazo es por clase).

### 3.4 Misma excepción operativa que 0004 y 0015

`UPDATE` con `estado <> 'asignado'` y `chofer_id` sin cambio ⇒ no revalida. Un
viaje ya despachado no se congela porque después se corrija el maestro. El bloqueo
se aplica al **(re)asignar** (cambio de `chofer_id`) y en todo `asignado`.

### 3.5 Gap residual declarado (no garantizado)

> Un chofer **ya asignado** a un viaje vigente puede ser degradado de A5 a otra
> clase en `nucleo.choferes`; la base no lo impide.

No se agrega trigger en `choferes` porque excede R-02 ("la asignación") y podría
bloquear correcciones de datos. Detección: P2.1. Una vez degradado, la siguiente
reasignación o cualquier `UPDATE` con estado `asignado` falla con `23514`. Se
registra como riesgo R1, no se maquilla.

## 4. Precondiciones (ejecutar antes de aplicar)

Ninguna ejecutada (🔴). Todas son de **informe**: no se corrige ni se borra nada
desde la migración.

### P2.1 — Viajes vigentes con chofer de clase distinta de A5

```sql
select v.empresa_id, v.numero_viaje, v.estado, c.nombre, c.licencia_clase
  from nucleo.viajes v
  join nucleo.choferes c on c.id = v.chofer_id and c.empresa_id = v.empresa_id
 where v.estado <> 'anulado'
   and upper(btrim(coalesce(c.licencia_clase, ''))) <> 'A5'
 order by v.empresa_id, v.inicio_planificado;
```

**Se espera 0.** Si hay filas: son asignaciones que la regla considera inválidas.
**Acción:** operación decide reasignar o corregir la clase. **No** se corrige en la
migración. Nota: no bloquean la aplicación de 0016 (el trigger es `BEFORE INSERT
OR UPDATE`; las filas existentes no se revalidan), pero sí bloquean su próxima
modificación.

### P2.2 — Choferes activos que ya no podrán asignarse (universo del bloqueo)

```sql
select empresa_id, rut, nombre, licencia_clase, estado
  from nucleo.choferes
 where activo and estado <> 'baja'
   and upper(btrim(coalesce(licencia_clase, ''))) <> 'A5'
 order by empresa_id, nombre;
```

**Informe obligatorio.** Es la lista de conductores que la operación debe
regularizar (acreditar A5 o marcar baja). No es un error de la migración.

### P2.3 — Tractos cuya configuración contradice R-02

```sql
select empresa_id, patente, licencias_permitidas
  from nucleo.tractos
 where licencias_permitidas <> '{}'::text[]
   and not (licencias_permitidas <@ array['A5']::text[])
 order by empresa_id, patente;
```

**Informe.** El array deja de tener efecto; se limpia aparte si el dueño lo pide.

### P2.4 — Efecto del cambio de default (no cambia filas)

```sql
select id, codigo, dias_alerta_documentos from nucleo.empresas order by codigo;
```

**Esperado:** empresas existentes conservan su valor (típicamente 30). Después de
aplicar, este `SELECT` debe devolver **lo mismo**: si cambió, algo reescribió filas
y hay que investigarlo.

## 5. DDL

1. `alter table nucleo.empresas alter column dias_alerta_documentos set default 14;`
   — solo catálogo; no reescribe filas. El `CHECK 0..365` de `0004:121` no se toca.
2. `comment on column nucleo.empresas.dias_alerta_documentos` — documenta que es
   aviso, no bloqueo, y que el default cambió en 0016.
3. `create or replace function nucleo.fn_viaje_licencia_a5()` — nueva:
   - `chofer_id is null` ⇒ retorna (no hay asignación).
   - `estado = 'anulado'` ⇒ retorna (libera).
   - `UPDATE` con `estado <> 'asignado'` y `chofer_id` sin cambio ⇒ retorna
     (excepción operativa).
   - Lee `upper(btrim(coalesce(licencia_clase, '')))` de `nucleo.choferes`
     **con `empresa_id` del viaje** (no cruza empresas).
   - Si el chofer no existe, retorna: la FK compuesta (`0004:656-657`) o
     `fn_viaje_validar` dan el error correcto.
   - `v_clase <> 'A5'` ⇒ `raise exception 'Licencia A5 requerida (R-02): ...'`
     con `errcode = '23514'` y `hint`.
4. `drop trigger if exists` + `create trigger trg_viajes_03_licencia_a5 before
   insert or update on nucleo.viajes for each row`.
5. `comment on column nucleo.tractos.licencias_permitidas` (deprecado) y
   `comment on column nucleo.choferes.licencia_clase` (R-02).

Re-ejecutable: `ALTER ... SET DEFAULT` es idempotente; `CREATE OR REPLACE` y
`DROP TRIGGER IF EXISTS` también. No modifica datos.

## 6. Default 14: qué cambia y qué **no**

| Aspecto | Efecto |
|---|---|
| `INSERT` en `nucleo.empresas` sin la columna | pasa a 14 |
| Filas existentes | **conservan 30** (o lo que tengan). No hay backfill |
| `INSERT` desde el backend | **envía 30 explícito** (`models.py:221` `default=30`): el default de la base **no se aplica** |
| `scripts/seed_local.py` | inserta 30 literal (`seed_local.py:162-166`) |

Por eso el cambio de default **solo** es efectivo cuando el escritor omite la
columna. El handoff a `backend` (cambiar `default=30` → `14`, o no enviar el
campo) es requisito para que R-02 se cumpla de punta a punta.

Backfill de filas existentes: **fuera de esta migración**, autorizado y con
conteos. Si el dueño lo pide:

```sql
-- [REQUIERE AUTORIZACIÓN EXPLÍCITA] paso separado
select count(*) from nucleo.empresas where dias_alerta_documentos = 30;  -- antes

update nucleo.empresas
   set dias_alerta_documentos = 14,
       updated_by = 'migracion_0016_backfill'
 where dias_alerta_documentos = 30;

select count(*) from nucleo.empresas where dias_alerta_documentos = 30;  -- después: 0
-- queda registrado por trg_empresas_audit (0004:1760-1761)
```

## 7. La ventana de 14 días es aviso de servicio, no constraint

- Vive en `backend/app/nucleo/servicio_alertas.py` y
  `servicio_disponibilidad.py`, que leen `empresas.dias_alerta_documentos`.
- **No** se agrega constraint de "por vencer": sería convertir una notificación en
  una prohibición que el dueño no pidió.
- Interacción que debe quedar clara: el bloqueo duro de 0004 compara contra el
  **fin del viaje** (+ `dias_margen_documentos`), no contra "hoy + 14".
  Una licencia que vence en 10 días **no** bloquea un viaje que termina en 2 días;
  sí bloquea uno que termina después del vencimiento (correcto: está vencida
  durante el viaje).
- Si una empresa sube `dias_margen_documentos`, el bloqueo puede ocurrir antes de
  la ventana de aviso: son perillas distintas y así se documenta.
- La prueba `0016_02` fija este contrato: si alguien endurece el aviso a
  constraint, la prueba falla.

## 8. Impacto y locks

| Sentencia | Lock | Duración | Efecto |
|---|---|---|---|
| `ALTER TABLE ... SET DEFAULT` | `AccessExclusiveLock` en `nucleo.empresas` | ms (solo catálogo, sin reescritura) | Bloquea lecturas/escrituras de `empresas` por un instante |
| `CREATE OR REPLACE FUNCTION` | catálogo | ms | Ninguno |
| `CREATE TRIGGER` | `ShareRowExclusiveLock` en `nucleo.viajes` | ms | Bloquea escrituras de viajes mientras crea |
| `COMMENT` | catálogo | ms | Ninguno |

Sin backfill ⇒ sin locks largos, sin pérdida de datos. `public` no se toca.

## 9. Compatibilidad

| Consumidor | Efecto |
|---|---|
| Backend: `asignar`/`confirmar_asignacion` | Puede recibir `23514` con mensaje "Licencia A5 requerida" donde antes recibía una advertencia. **Comportamiento buscado**; `errores.py:164-168` lo traduce a `ReglaNegocioViolada` (HTTP 409, ver §10) |
| Backend: `politicas.py:297-320` | Sigue devolviendo `Hallazgo(..., False)`: advertencia redundante y, si el array está vacío, silencio. Handoff: convertirlo en bloqueante o eliminarlo (la base ya bloquea) |
| Backend: `models.py:221` | `default=30` anula el default 14. Handoff |
| Frontend maestros | El campo `licencias_permitidas` sigue existiendo; se muestra como editable pero ya no autoriza. Handoff: quitarlo de la UI |
| `scripts/seed_local.py` | Inserta 30 literal; no falla. Handoff |
| `public` legacy | Sin efecto: no tiene clase de licencia (`0001`) |

## 10. SQLSTATE → HTTP

`23514` es el SQLSTATE del bloqueo. El mapeo **real** hoy
(`backend/app/nucleo/errores.py:164-168`) es `23514 → ReglaNegocioViolada`, que
`backend` expone como **409**. `AGENTS.md` §8 pide `23514 → 422`. Es una
discrepancia preexistente que esta migración **no** cambia: se entrega como
handoff (`backend` decide si unifica a 422). El mensaje de la excepción incluye el
nombre del chofer y su clase, y un `hint`.

## 11. Rollback (exacto, sin pérdida de datos)

```sql
drop trigger if exists trg_viajes_03_licencia_a5 on nucleo.viajes;
drop function if exists nucleo.fn_viaje_licencia_a5();

alter table nucleo.empresas
  alter column dias_alerta_documentos set default 30;

comment on column nucleo.tractos.licencias_permitidas is null;
comment on column nucleo.choferes.licencia_clase is null;
```

No hay datos que revertir: la migración no escribió filas. El rollback vuelve a
permitir asignar cualquier clase de licencia (y a callar la advertencia del
servicio): **es un incidente**, no una operación rutinaria.

## 12. Verificación posterior

```sql
-- V1: trigger presente
select tgname from pg_trigger
 where tgrelid = 'nucleo.viajes'::regclass and not tgisinternal
   and tgname = 'trg_viajes_03_licencia_a5';           -- 1 fila

-- V2: default 14 (solo afecta INSERT futuros)
select column_default from information_schema.columns
 where table_schema = 'nucleo' and table_name = 'empresas'
   and column_name = 'dias_alerta_documentos';         -- '14'

-- V3: ninguna fila existente cambió (comparar con P2.4)
select id, codigo, dias_alerta_documentos from nucleo.empresas order by codigo;

-- V4: deprecación documentada
select col_description('nucleo.tractos'::regclass,
                       (select attnum from pg_attribute
                         where attrelid = 'nucleo.tractos'::regclass
                           and attname = 'licencias_permitidas'));
```

## 13. Pruebas

| Archivo | Qué demuestra | Estado |
|---|---|---|
| `0016_01_licencia_clase_no_a5.sql` | A3 ⇒ `23514` "Licencia A5 requerida" (con documentos vigentes, así que el rechazo es por clase); clase NULL ⇒ `23514` "sin registrar"; `UPDATE` que asigna un A3 a un borrador ⇒ `23514` | 🔴 |
| `0016_02_licencia_por_vencer_no_bloquea.sql` | A5 con licencia a 10 días y viaje que termina en 2 días ⇒ **aceptado** y ocupa 3 reservas | 🔴 |
| `0016_03_licencia_vencida_bloquea.sql` | A5 con licencia vencida ⇒ `23514` "licencia_conducir … vencido o insuficiente"; control con licencia vigente ⇒ aceptado | 🔴 |
| `mutacion.md` (M3, M5) | Retirar el trigger hace fallar `0016_01`; el default cambia de 14 a 30 | 🔴 |

Faltantes declarados: no hay prueba de dos conexiones para la clase A5 (no hay
carrera posible: es una lectura dentro del mismo trigger `BEFORE`); no hay prueba
de degradación de un chofer ya asignado (gap residual §3.5).

## 14. Riesgos y no verificado

| ID | Riesgo | Nivel | Mitigación / dueño |
|---|---|---|---|
| R1 | Chofer asignado degradado de A5 a otra clase: la base no lo impide | Medio | P2.1 para detectar; decidir si se agrega trigger en `choferes` (excede R-02) |
| R2 | `models.py:221` envía 30 explícito: el default 14 no aplica a los INSERT del backend | Medio | Handoff `backend` |
| R3 | `politicas.py` sigue tratando la clase como advertencia (y la ignora si el array está vacío) | Bajo (la base bloquea) | Handoff `backend`: eliminar o volver bloqueante para mensaje temprano |
| R4 | `tractos.licencias_permitidas` visible en maestros sugiere una regla que ya no existe | Bajo | Handoff `frontend`; `COMMENT` ya lo advierte en la base |
| R5 | `23514 → 409` en lugar de `422` | Bajo | Handoff `backend`; discrepancia preexistente |
| R6 | Operación con choferes A3 activos: no podrán asignarse hasta regularizar | Medio operativo | P2.2 como informe previo; es el efecto buscado de R-02 |
| — | **Nada ejecutado**: sin base local, ni precondiciones ni pruebas ni mutación | 🔴 | Orquestador/`qa` |
