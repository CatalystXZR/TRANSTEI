> **ARCHIVADO 2026-10-29 — NO CITAR COMO ESTADO.**
> Documento histórico. Reemplazos y contexto: `docs/_archivo/README.md` · Estado real: `docs/estado.md`.
> Sus cifras y afirmaciones de "terminado" NO fueron re-verificadas en esta fecha.

# Plan de migraciones forward-only 0015 → 0021 (diseño, no SQL final)

> **Autor:** agente `datos` · **Fecha:** 2026-10-29 · **Estado:** propuesta para
> aprobación. **Nada de esto está escrito ni aplicado.**
>
> **Reglas de este plan** (`AGENTS.md` §8, skill `database-safety` §4.3):
> - Forward-only. `0001`–`0014` no se editan.
> - Cada migración declara precondición de detección que **debe devolver 0
>   filas**. Si devuelve filas: **se reporta, no se borra**.
> - Sin `DROP` de columnas/tablas con datos. Los cambios destructivos aparecen
>   marcados **`[REQUIERE AUTORIZACIÓN EXPLÍCITA]`**.
> - Ninguna migración se aplica sin base local arriba y sin las pruebas de §8.
> - Las consultas de precondición de este documento **no se ejecutaron**: no hay
>   base (🔴). Se entregan listas para correr.

## 0. Orden, riesgo y dependencias

| Migración | Objetivo | Riesgo | Depende de | ¿Irreversible? |
|---|---|---|---|---|
| **0015** | Ocupación: todo viaje con recursos reserva; reserva coherente con el viaje | **Alto** (disponibilidad) | — | No |
| **0016** | Comercial: sobregiro aprobado, tarifa no borrable, gate de OC | Medio | — | No |
| **0017** | Gastos: inmutabilidad del aprobado, idempotencia, no borrado | **Alto** (dinero) | — | No |
| **0018** | Facturación: tope de saldo, idempotencia de pagos, inmutabilidad del documento emitido | **Alto** (dinero/tributario) | 0017 (mismo patrón de triggers) | No |
| **0019** | Legacy `public`: doble asignación, folio SII, `total`, no borrado, liquidación | **Alto** (dinero + cambio de comportamiento legacy) | ADR de convivencia (`arquitectura`) | No, pero **cambia comportamiento** |
| **0020** | Multiempresa real: FK compuestas + rol + políticas RLS + `FORCE RLS` | **Alto** (tenant) | Handoff `backend` (contexto por transacción) + provisión de rol | Sí, en el sentido de que volver atrás **desprotege** |
| **0021** | Cutover impuesto en DB + auditoría de cutover + `TRUNCATE` | Medio | 0014 | No |

> ### Renumeración (adenda 2026-10-29)
>
> La tabla anterior es el plan **original** y se conserva como historia. Al
> escribir el SQL cambió el reparto:
>
> | Número | Plan original | Contenido real (escrito, **no aplicado**) |
> |---|---|---|
> | **0015** | Ocupación (INV-D04, INV-D05, INV-D06) | **Ocupación + puerta documental** (INV-D04, INV-DOC04) y backfill. **No** incluye INV-D05 ni INV-D06: siguen abiertos. Ver `migraciones/0015-ocupacion-confirmado.md` |
> | **0016** | Comercial (INV-C03, INV-C04, INV-C05, INV-DOC03) | **Licencia A5 bloqueante (R-02)** + default `dias_alerta_documentos = 14`. Ver `migraciones/0016-licencia-a5.md` |
>
> Los invariantes comerciales **no se pierden**: pasan a la siguiente migración
> libre. La secuencia propuesta queda:
>
> | Número | Contenido |
> |---|---|
> | 0017 | Comercial: INV-C03, INV-C04, INV-C05, INV-DOC03 (lo que era 0016) |
> | 0018 | Gastos: INV-G04, INV-G05, INV-G06 (antes 0017) |
> | 0019 | Facturación: INV-F01…F07 (antes 0018) |
> | 0020 | Legacy `public`: INV-L01…L06 (antes 0019) |
> | 0021 | Multiempresa/RLS: INV-T01…T03 (antes 0020) |
> | 0022 | Cutover y auditoría: INV-T04, INV-X01, INV-A01, INV-A02 (antes 0021) |
> | por asignar | INV-D05 (reserva no desactivable), INV-D06 (reservas huérfanas) — quedaron fuera de 0015 |
>
> Consecuencias operativas de la renumeración:
>
> - Ninguna migración `0015`/`0016` anterior existe aplicada: no hay historia que
>   reescribir (`AGENTS.md` §8 prohíbe editar migraciones aplicadas; estas no lo
>   están).
> - Las referencias a "0016" en `docs/datos/02-invariantes.md` §1 (fila de
>   INV-C03/C04/C05/DOC03) apuntan al plan original: léalas con esta tabla.
> - El orden de riesgo no cambia: 0015 sigue siendo Alto (disponibilidad) y
>   0016 pasó de Medio a Medio (regla operativa, sin dinero).

**Por qué este orden.** 0015 cierra la fuga que hoy permite despachar dos viajes
al mismo tracto sin que nadie lo note: es el riesgo operativo con impacto diario.
0017 y 0018 van después porque tocan dinero y exigen que `backend` ya traduzca
`23505`/`23514` (hoy `23502` cae en 500, `01` §14.2). 0019 es el único que puede
**rechazar operaciones hoy válidas** del legacy y por eso va tras el ADR. 0020 es
técnicamente independiente y **podría adelantarse**, pero sin el handoff de
`backend` (rol + `SET LOCAL`) sus políticas son decorativas y el riesgo de romper
la app es mayor que el beneficio inmediato.

---

## 0015 — Ocupación: cerrar la fuga `confirmado` y la desactivación libre

### Objetivo e invariantes
Impone **INV-D04** y **INV-D05** (`02-invariantes.md` §2). No crea tablas.

### Objetos afectados
- `nucleo.fn_viaje_reservas()` — `0004:1621-1650` (se reemplaza con
  `CREATE OR REPLACE`).
- `nucleo.fn_reserva_validar()` — `0004:1653-1690` (se reemplaza).
- `nucleo.viajes` — **sin cambio de columnas**; el `CHECK`
  `ck_viaje_recursos_por_estado` (`0004:671-674`) **no se toca** en la opción (A).
- Opcional: `nucleo.v_reservas_huerfanas` (vista de control, INV-D06).

### Precondiciones (deben dar 0 filas)

**P1.1 — viajes `confirmado` con recursos y sin reserva (los que la migración
debe adoptar o bloquear).**
```sql
select v.id, v.empresa_id, v.numero_viaje, v.estado, v.inicio_planificado, v.fin_planificado
  from nucleo.viajes v
 where v.estado = 'confirmado'
   and (v.tracto_id is not null or v.rampla_id is not null or v.chofer_id is not null)
   and not exists (
     select 1 from nucleo.reservas_recurso r
      where r.viaje_id = v.id and r.activa
   );
```
> Se espera **≠ 0** si el cutover o el seed corrieron (el propio
> `cutover_legacy.py:361-388` los crea). **No son datos a borrar:** son viajes
> reales. La migración debe **adoptarlos** (backfill de reservas) o **rechazar la
> asignación** con un mensaje claro. Decisión en §"Backfill".

**P1.2 — reservas de viaje activas que ya no coinciden con su viaje.**
```sql
select r.id, r.viaje_id, r.recurso_tipo, r.activa
  from nucleo.reservas_recurso r
  join nucleo.viajes v on v.id = r.viaje_id
 where r.activa
   and r.tipo_reserva = 'viaje'
   and not (
        (r.recurso_tipo = 'tracto' and v.tracto_id = r.tracto_id)
     or (r.recurso_tipo = 'rampla' and v.rampla_id = r.rampla_id)
     or (r.recurso_tipo = 'chofer' and v.chofer_id = r.chofer_id)
   );
```

**P1.3 — solapamientos que el nuevo criterio detectaría** (dos viajes
`confirmado` con recursos en la misma ventana y el mismo tracto). Se ejecuta
**antes** de activar la reserva en `confirmado`:
```sql
select a.id as viaje_a, b.id as viaje_b, a.tracto_id
  from nucleo.viajes a
  join nucleo.viajes b
    on a.tracto_id = b.tracto_id and a.id < b.id
 where a.tracto_id is not null
   and a.estado not in ('borrador','cotizado','anulado')
   and b.estado not in ('borrador','cotizado','anulado')
   and a.ventana && b.ventana;
```
> **Si devuelve filas, la opción (A) es inaplicable tal cual**: hay viajes
> legítimos ya solapados que el libro nunca vio. Esos casos **decide operación**,
> no `datos`.

**P1.4 — tamaño de las tablas** (para dimensionar locks; medir, no suponer):
```sql
select relname, n_live_tup,
       pg_size_pretty(pg_total_relation_size(relid)) as total
  from pg_stat_user_tables
 where schemaname = 'nucleo'
   and relname in ('viajes','reservas_recurso');
```

### Estrategia expand/contract
1. **Expand:** `CREATE OR REPLACE` de `fn_reserva_validar` con la nueva rama, en
   modo **aviso** (`RAISE NOTICE`) durante una ventana, para descubrir escritores
   que desactivan reservas.
2. **Backfill** de reservas para los viajes de P1.1 (idempotente, por lotes).
3. **Contract:** activar el rechazo (`RAISE EXCEPTION`).

No hay `NOT NULL` ni cambio de tipo ⇒ no aplica `NOT VALID`/`VALIDATE`.

### Backfill (si P1.1 ≠ 0 y operación aprueba la opción A)
- Por lotes de 500 viajes, ordenado por `inicio_planificado`.
- Idempotente: `WHERE NOT EXISTS (reserva activa para el viaje)`.
- Reanudable: cada lote en su propia transacción; registro en
  `nucleo.viaje_eventos` (`tipo='backfill_reserva'`).
- **Conteos antes/después**: `count(viajes confirmado con recursos)` vs
  `count(reservas activas de esos viajes) * 1` por recurso (3 por viaje).
- Si el `INSERT` choca con un `EXCLUDE` (23P01) ⇒ **detener el lote y reportar**:
  significa que el viaje migrado ya choca con otro. No se resuelve borrando.

### Impacto y locks
| Sentencia | Lock | Duración esperada |
|---|---|---|
| `CREATE OR REPLACE FUNCTION` | `AccessExclusiveLock` sobre la función | milisegundos; no bloquea filas |
| Backfill `INSERT` en `reservas_recurso` | `RowExclusiveLock` + escritura de índices GIST | proporcional al lote; **compite con el `EXCLUDE`** ⇒ puede bloquear asignaciones concurrentes del mismo recurso |
| `ANALYZE` tras backfill | `ShareUpdateExclusive` | segundos |

Efecto sobre legacy: **ninguno** (no toca `public`).
Efecto sobre la app: los viajes `confirmado` con recursos pasan a bloquear el
recurso. **Es un cambio de comportamiento** y debe anunciarse a operación.

### Rollback
- `CREATE OR REPLACE FUNCTION` con la versión anterior (texto en
  `0004:1621-1690`).
- El backfill **no se revierte con `DELETE`**: las reservas creadas se
  **desactivan** (`activa=false`, `cancelado_motivo='rollback 0015'`) para
  conservar trazabilidad. Requiere que INV-D05 no esté aún activo o que el
  escape esté disponible en la misma transacción.
- Sin pérdida de datos: no se borra nada.

### Prueba de dos conexiones requerida
1. A: `BEGIN; UPDATE nucleo.viajes SET estado='confirmado', tracto_id=T WHERE id=V1;`
   (sin commit). B: `BEGIN; UPDATE nucleo.viajes SET estado='confirmado',
   tracto_id=T WHERE id=V2` con ventana solapada ⇒ B **espera** y al commitear A
   recibe `23P01`.
2. A: `BEGIN; UPDATE nucleo.viajes SET estado='asignado', …` (crea reservas).
   B: `UPDATE nucleo.reservas_recurso SET activa=false WHERE viaje_id=A` ⇒
   `23514`.
3. Mutación: `ALTER TABLE nucleo.reservas_recurso DROP CONSTRAINT
   ex_reserva_tracto` en copia desechable ⇒ la prueba 1 pasa a verde.

---

## 0016 — Comercial: sobregiro, tarifas y gate de OC

### Objetivo e invariantes
**INV-C03**, **INV-C04**, **INV-DOC03**; **INV-C05 bloqueado** (falta decisión de
negocio, `02` §9).

### Objetos afectados
- `nucleo.ordenes_compra` — trigger `fn_oc_sobregiro` (nuevo, BEFORE UPDATE).
- `nucleo.tarifas` — trigger `fn_tarifa_no_borrar` (nuevo, BEFORE DELETE).
- `nucleo.fn_viaje_facturacion()` — `0009:65-136` (se reemplaza para leer
  `exigir_oc`/`exige_oc`).

### Precondiciones (0 filas)

**P2.1 — sobregiros ya autorizados sin aprobación** (los que la migración
bloquearía retroactivamente):
```sql
select id, empresa_id, numero_oc, sobregiro_autorizado, sobregiro_estado
  from nucleo.ordenes_compra
 where sobregiro_autorizado > 0
   and (sobregiro_estado <> 'aprobado' or sobregiro_aprobado_por is null);
```
> Si hay filas: **no se corrigen a mano**. Se decide si se aprueban
> retroactivamente (con registro) o si el trigger solo aplica a `UPDATE`
> (no valida filas históricas). Recomendación: trigger **solo en UPDATE**, y
> esta consulta se entrega como informe de exposición.

**P2.2 — tarifas borradas que dejaron viajes sin origen** (no se puede detectar
lo ya borrado; se mide la exposición futura):
```sql
select count(*) as viajes_sin_tarifa
  from nucleo.viajes
 where tarifa_id is null and tarifa_snapshot = '{}'::jsonb;
```

**P2.3 — viajes sin OC que serían rechazados al facturar** con el nuevo gate:
```sql
select v.id, v.empresa_id, v.numero_viaje, v.estado
  from nucleo.viajes v
  join nucleo.empresas e on e.id = v.empresa_id
  join nucleo.clientes c on c.id = v.cliente_id
 where v.orden_compra_id is null
   and v.estado in ('cerrado','facturado','cobrado')
   and (e.exigir_oc or c.exige_oc);
```
> Se espera 0: si no, hay empresas con `exigir_oc=true` que hoy facturan sin OC.
> **Decisión de negocio** antes de activar.

### Expand/contract
- Expand: triggers creados pero con `RAISE NOTICE` (fase de observación).
- Contract: `RAISE EXCEPTION`.

### Impacto y locks
Solo `CREATE OR REPLACE FUNCTION` + `CREATE TRIGGER` (`ShareRowExclusiveLock`
breve sobre la tabla, sin reescritura). Sin backfill ⇒ sin locks largos.

### Rollback
`DROP TRIGGER` (los triggers son nuevos; retirarlos **no pierde datos**) y
`CREATE OR REPLACE` de la función de facturación en su versión de `0009`.

### Prueba de dos conexiones
Sobregiro: A `UPDATE ordenes_compra SET sobregiro_autorizado=+5.000.000` sin
aprobación, B lo mismo ⇒ ambos `23514`. Y prueba de que **no** hay carrera en el
consumo: dos viajes concurrentes contra el mismo saldo ⇒ `fn_oc_recalcular`
(`0004:1550-1597`) serializa por `FOR UPDATE`; solo uno gana.

---

## 0017 — Gastos: inmutabilidad, idempotencia y no borrado

### Objetivo e invariantes
**INV-G04**, **INV-G05**, **INV-G06**.

### Objetos afectados
- `nucleo.viaje_gastos` — columnas `idempotency_key text`,
  `anulado_motivo text`, `anulado_por text`, `anulado_en timestamptz`.
- Índice único parcial por documento + único de idempotencia.
- Triggers `fn_gasto_proteccion` (BEFORE UPDATE), `fn_gasto_no_borrar`
  (BEFORE DELETE).
- `REVOKE DELETE ON nucleo.viaje_gastos FROM service_role` (hoy no se revoca:
  `0011:175-182`).

### Precondiciones (0 filas)

**P3.1 — duplicados que el índice rechazaría:**
```sql
select empresa_id, viaje_id, upper(btrim(proveedor)) as prov,
       upper(btrim(numero_documento)) as doc, count(*)
  from nucleo.viaje_gastos
 where activo and numero_documento is not null and proveedor is not null
 group by 1,2,3,4
having count(*) > 1;
```
> Si hay filas: **reportar**. Son gastos posiblemente duplicados de verdad
> (dinero): decide `negocio-finanzas`. La migración **no** puede crear el índice
> hasta que estén resueltos, o debe crearse sin esos casos (no recomendado).

**P3.2 — gastos aprobados sin aprobador/fecha** (deberían ser 0 por
`ck_gasto_aprobacion`, `0011:68-70`; se verifica que el `CHECK` esté en vigor):
```sql
select count(*) from nucleo.viaje_gastos
 where estado = 'aprobado' and (aprobado_por is null or aprobado_en is null);
```

**P3.3 — tamaño:**
```sql
select n_live_tup, pg_size_pretty(pg_total_relation_size('nucleo.viaje_gastos'))
  from pg_stat_user_tables where relname = 'viaje_gastos';
```

### Expand/contract
1. **Expand:** agregar columnas nullable + `idempotency_key` nullable. Sin
   `NOT NULL` ⇒ sin backfill obligatorio.
2. **Backfill opcional:** `idempotency_key = 'legacy:' || id` para filas
   existentes (idempotente, `WHERE idempotency_key IS NULL`).
3. **Índice:** `CREATE UNIQUE INDEX CONCURRENTLY` (fuera de transacción, §"Notas
   de ejecución").
4. **Contract:** triggers en modo rechazo + `REVOKE DELETE`.

### Impacto y locks
| Sentencia | Lock |
|---|---|
| `ALTER TABLE … ADD COLUMN` (nullable, sin default volátil) | `AccessExclusiveLock` **breve** (metadata only en PG ≥ 11) |
| `CREATE UNIQUE INDEX CONCURRENTLY` | **no** toma `AccessExclusiveLock`; puede tardar; **no puede ir en transacción** |
| `CREATE TRIGGER` | `ShareRowExclusiveLock` breve |

**Nota de ejecución:** `CONCURRENTLY` no puede ejecutarse dentro de un bloque
`BEGIN…COMMIT`. La migración debe separarse en dos pasos: (a) DDL transaccional,
(b) índice concurrente en su propia invocación. Si la tabla es pequeña (< 100k
filas), un `CREATE UNIQUE INDEX` normal dentro de la transacción es aceptable y
más simple: **decidir con la medición de P3.3**, no por intuición.

### Rollback
`DROP INDEX` + `DROP TRIGGER` + columnas se dejan (nullable, sin uso) o se
eliminan en una migración posterior **`[REQUIERE AUTORIZACIÓN EXPLÍCITA]`**
(`DROP COLUMN` pierde datos). Recomendación: dejar las columnas y solo retirar
los triggers.

### Prueba de dos conexiones
Dos conexiones insertan el mismo `(proveedor, numero_documento)` ⇒ una recibe
`23505`; el `costo_variable_real` del viaje suma **una** vez. Mutación: retirar
el índice ⇒ dos filas y el costo se duplica (`0011:107-113`).

---

## 0018 — Facturación: saldo, idempotencia e inmutabilidad del documento

### Objetivo e invariantes
**INV-F01**, **INV-F02**, **INV-F03**, **INV-F04**, **INV-F05**, **INV-F06**,
**INV-F07**.

### Objetos afectados
- `nucleo.pagos_nucleo` — `idempotency_key text` + único parcial; trigger
  `fn_pago_validar` (BEFORE INSERT/UPDATE), `fn_pago_no_borrar` (BEFORE DELETE).
- `nucleo.notas_credito_nucleo` — `fn_nc_validar`, `fn_nc_no_borrar`.
- `nucleo.facturas_nucleo` — `motivo_anulacion`, `anulado_por`, `anulado_en`;
  `CHECK` de anulación; trigger `fn_factura_proteccion` (BEFORE UPDATE/DELETE).
- `nucleo.factura_viajes` — trigger de protección (BEFORE DELETE/UPDATE).
- `REVOKE DELETE` en `pagos_nucleo`, `notas_credito_nucleo`, `factura_viajes`
  (hoy `0013:261-271` solo otorga `select, insert, update`, pero **no revoca**
  `delete` que el dueño conserva; el `REVOKE` aplica a `service_role`).

### Precondiciones (0 filas)

**P4.1 — facturas ya sobrepagadas** (dinero real; **reportar, no corregir**):
```sql
select f.id, f.empresa_id, f.numero_factura, f.total,
       coalesce(p.pagado,0) as pagado, coalesce(n.nc,0) as notas,
       coalesce(p.pagado,0) + coalesce(n.nc,0) - f.total as exceso
  from nucleo.facturas_nucleo f
  left join (select factura_id, sum(monto) pagado from nucleo.pagos_nucleo group by 1) p
         on p.factura_id = f.id
  left join (select factura_id, sum(monto) nc from nucleo.notas_credito_nucleo
              where estado='aplicada' group by 1) n
         on n.factura_id = f.id
 where coalesce(p.pagado,0) + coalesce(n.nc,0) > f.total;
```

**P4.2 — pagos duplicados por referencia** (candidatos a idempotencia):
```sql
select empresa_id, referencia, count(*), sum(monto)
  from nucleo.pagos_nucleo
 where referencia is not null
 group by 1,2 having count(*) > 1;
```
> Puede haber duplicados **legítimos** (dos transferencias con la misma glosa).
> Por eso `idempotency_key` es una columna nueva y **no** se hace único
> `referencia`: un único sobre `referencia` rechazaría datos válidos.

**P4.3 — facturas anuladas sin motivo** (para el `CHECK`):
```sql
select count(*) from nucleo.facturas_nucleo
 where estado = 'anulada' and coalesce(btrim(observaciones),'') = '';
```
> Si hay filas, el `CHECK` no puede crearse tal cual. Opción: crear el `CHECK`
> con `NOT VALID` y no validarlo hasta que se documenten los casos
> (`ALTER TABLE … ADD CONSTRAINT … NOT VALID`, luego `VALIDATE CONSTRAINT`).

**P4.4 — facturas con estado inconsistente con sus pagos** (deriva histórica):
```sql
select f.id, f.estado, coalesce(sum(p.monto),0) pagado
  from nucleo.facturas_nucleo f
  left join nucleo.pagos_nucleo p on p.factura_id = f.id
 group by f.id, f.estado, f.total
having (f.estado='pagada' and coalesce(sum(p.monto),0) < f.total)
    or (f.estado='emitida' and coalesce(sum(p.monto),0) > 0);
```

### Expand/contract
1. **Expand:** columnas nullable (`idempotency_key`, `motivo_anulacion`,
   `anulado_por`, `anulado_en`).
2. **Índice único** parcial sobre `idempotency_key` (`CONCURRENTLY` si el volumen
   lo exige; medir).
3. **`CHECK` de anulación** con `NOT VALID` → `VALIDATE CONSTRAINT` cuando P4.3
   esté en 0.
4. **Triggers** en modo aviso → rechazo.
5. **`REVOKE DELETE`** al final (es el paso que rompe más escritores; va último).

### Impacto y locks
- `ADD COLUMN` nullable: `AccessExclusiveLock` de metadata, milisegundos.
- `VALIDATE CONSTRAINT`: `ShareUpdateExclusiveLock`; **no bloquea** lecturas ni
  escrituras, pero recorre la tabla (proporcional al tamaño).
- Triggers: `ShareRowExclusiveLock` breve.
- **Riesgo de deadlock:** `fn_pago_validar` toma `FOR UPDATE` de la factura y
  `fn_factura_estado` (`0013:174`) también. Ambos deben tomarlo **en el mismo
  orden** (siempre la factura primero, nunca una NC y luego la factura). Se debe
  documentar el orden y probarlo con dos conexiones invirtiendo el orden de
  inserción.

### Rollback
`DROP TRIGGER` + `ALTER TABLE … DROP CONSTRAINT` (los `CHECK` se pueden quitar sin
pérdida) + `GRANT DELETE` de vuelta. **Las columnas se conservan.** El rollback
**degrada** la garantía a la situación actual: debe quedar registrado como
incidente, no como operación normal.

### Prueba de dos conexiones (la más importante del plan)
1. Factura total 1.000.000. A: `BEGIN; INSERT pago 600.000`. B: `BEGIN; INSERT
   pago 600.000` ⇒ B bloqueado; al commit de A, B recibe `23514`. Estado: 1 pago.
2. Misma `idempotency_key` en A y B ⇒ 1 fila; el segundo recibe `23505` y el
   servicio devuelve el pago existente (handoff `backend`).
3. A: `UPDATE facturas_nucleo SET neto=…` sobre factura pagada; B: `DELETE FROM
   pagos_nucleo` ⇒ `23514` en ambos.
4. Mutación: `DROP TRIGGER trg_pagos_validar` ⇒ la prueba 1 deja 2 pagos.

---

## 0019 — Legacy `public` (convivencia; el más delicado)

### Objetivo e invariantes
**INV-L01**, **INV-L02**, **INV-L03**, **INV-L04**, **INV-L05**, **INV-L06**.

### Precondición de gobierno, no solo técnica
Este bloque **cambia el comportamiento del sistema en operación**:
- `INV-L01` (EXCLUDE por día) puede rechazar viajes que hoy se aceptan (el legacy
  agenda por `date`, `0001:99-100`).
- `INV-L02` (folio SII único) puede chocar con folios repetidos entre clientes.

⇒ Requiere **ADR de `arquitectura`** + aprobación del dueño + ventana. Sin eso,
0019 no se escribe.

### Precondiciones (0 filas)

**L1 — solapamientos actuales en `public.viajes`** (los que el `EXCLUDE`
rechazaría). Se ejecuta **antes** de crear la constraint:
```sql
select a.id as viaje_a, b.id as viaje_b, 'tracto' as recurso, a.tracto_id as recurso_id,
       a.fecha_inicio, a.fecha_fin, a.estado, b.estado
  from public.viajes a
  join public.viajes b
    on a.tracto_id = b.tracto_id and a.id < b.id
 where a.estado in ('programado','en_ruta') and b.estado in ('programado','en_ruta')
   and daterange(a.fecha_inicio, coalesce(a.fecha_fin, a.fecha_inicio + 1), '[)')
    && daterange(b.fecha_inicio, coalesce(b.fecha_fin, b.fecha_inicio + 1), '[)')
union all
select a.id, b.id, 'rampla', a.rampla_id, a.fecha_inicio, a.fecha_fin, a.estado, b.estado
  from public.viajes a
  join public.viajes b on a.rampla_id = b.rampla_id and a.id < b.id
 where a.estado in ('programado','en_ruta') and b.estado in ('programado','en_ruta')
   and daterange(a.fecha_inicio, coalesce(a.fecha_fin, a.fecha_inicio + 1), '[)')
    && daterange(b.fecha_inicio, coalesce(b.fecha_fin, b.fecha_inicio + 1), '[)')
union all
select a.id, b.id, 'chofer', a.chofer_id, a.fecha_inicio, a.fecha_fin, a.estado, b.estado
  from public.viajes a
  join public.viajes b on a.chofer_id = b.chofer_id and a.id < b.id
 where a.estado in ('programado','en_ruta') and b.estado in ('programado','en_ruta')
   and daterange(a.fecha_inicio, coalesce(a.fecha_fin, a.fecha_inicio + 1), '[)')
    && daterange(b.fecha_inicio, coalesce(b.fecha_fin, b.fecha_inicio + 1), '[)');
```
> **Si devuelve filas: son datos reales de operación.** No se borran ni se
> reasignan desde una migración. Se entrega el listado a operación y se decide
> caso por caso **antes** de crear el `EXCLUDE`.

**L2 — folios SII duplicados:**
```sql
select numero_sii, count(*) as veces, array_agg(cliente_id) as clientes
  from public.facturas group by 1 having count(*) > 1;
```

**L3 — facturas con `total` inconsistente:**
```sql
select id, numero_sii, monto_neto, iva, total
  from public.facturas where total <> monto_neto + iva;
```

**L4 — fechas invertidas:**
```sql
select id, fecha_inicio, fecha_fin from public.viajes
 where fecha_fin is not null and fecha_fin < fecha_inicio;
```

**L5 — liquidaciones incoherentes:**
```sql
select id, chofer_id, mes, sueldo_base, comision, total_anticipos, total_ajustes,
       total_liquido,
       (sueldo_base + comision + total_ajustes - total_anticipos) as esperado
  from public.liquidaciones
 where total_liquido <> (sueldo_base + comision + total_ajustes - total_anticipos);
```

**L6 — tamaño (define si se puede crear el índice en transacción):**
```sql
select relname, n_live_tup, pg_size_pretty(pg_total_relation_size(relid))
  from pg_stat_user_tables
 where schemaname='public' and relname in ('viajes','facturas','liquidaciones');
```

### Expand/contract
1. `CHECK` de fechas (`INV-L06`) y `total` (`INV-L03`): `NOT VALID` →
   `VALIDATE CONSTRAINT` cuando L3/L4 estén en 0.
2. `UNIQUE (numero_sii)` (`INV-L02`): **requiere L2 = 0**. Si no, no se crea.
3. `EXCLUDE` (`INV-L01`): **requiere L1 = 0**. Es el paso que puede bloquear
   operación; va al final y en ventana.
4. Triggers `no_borrar` (`INV-L04`) y de liquidación (`INV-L05`): pueden ir
   primero (no cambian el resultado de operaciones válidas).

### Impacto y locks
- `CREATE INDEX` del `EXCLUDE` sobre `public.viajes`: **bloquea escrituras** de
  la tabla durante la construcción (`SHARE`). Con volumen realista, usar ventana.
  No existe `CREATE INDEX CONCURRENTLY` para constraints `EXCLUDE` ⇒ **no hay
  forma de crearlo sin lock**. Declararlo así en el diseño: es el costo real.
- `VALIDATE CONSTRAINT`: no bloquea escrituras.
- Efecto sobre el núcleo: **ninguno** (no escribe en `public`).

### Rollback
`ALTER TABLE public.viajes DROP CONSTRAINT …` (los `EXCLUDE` no guardan datos),
`DROP TRIGGER`, `DROP INDEX`. El rollback **vuelve a permitir** la doble
asignación: es un incidente, no una operación rutinaria.

### Prueba de dos conexiones
A y B insertan viajes `programado` con el mismo tracto y la misma fecha ⇒ uno
recibe `23P01`. Mutación: `DROP CONSTRAINT` ⇒ ambos pasan (reproduce RA-02).

---

## 0020 — Multiempresa real (RA-03)

### Objetivo e invariantes
**INV-T01**, **INV-T02**, **INV-T03**; habilita el cierre de RA-03.

### Objetos afectados
1. **Rol:** `nucleo_app` (`NOLOGIN`, sin `BYPASSRLS`, sin ser dueño de tablas),
   con `GRANT USAGE ON SCHEMA nucleo` y `SELECT/INSERT/UPDATE/DELETE` por tabla
   **excepto** `auditoria` (`select, insert`) y `viaje_eventos` (`select, insert`).
2. **Función de contexto:** `nucleo.empresas_del_usuario()` `STABLE SECURITY
   DEFINER` que lea `auth.uid()`/`current_setting('nucleo.auth_id')` y devuelva
   los `empresa_id` activos de `usuarios_empresa`.
3. **Políticas** `USING` + `WITH CHECK` en las 19 tablas de `nucleo` (y las que
   agregaron 0005–0014). Patrón: `empresa_id IN (select nucleo.empresas_del_usuario())`;
   para `nucleo.empresas`: `id IN (…)`; para `usuarios_empresa`: `empresa_id IN (…)`
   **usando la función**, nunca subconsulta directa (recursión).
4. **`ALTER TABLE … FORCE ROW LEVEL SECURITY`** en todas.
5. **FK compuesta** `reservas_recurso (empresa_id, viaje_id) → viajes
   (empresa_id, id)` (`INV-T02`).
6. **FK** `usuarios_empresa.auth_id → auth.users(id)` (`INV-T03`).

### Precondiciones (0 filas)

**T1 — reservas cruzadas entre empresas:**
```sql
select r.id, r.empresa_id as empresa_reserva, v.empresa_id as empresa_viaje
  from nucleo.reservas_recurso r
  join nucleo.viajes v on v.id = r.viaje_id
 where r.empresa_id <> v.empresa_id;
```

**T2 — membresías huérfanas** (romperían la FK nueva):
```sql
select ue.id, ue.empresa_id, ue.auth_id
  from nucleo.usuarios_empresa ue
  left join auth.users au on au.id = ue.auth_id
 where au.id is null;
```
> Se espera ≠ 0 en entornos con seed/tests que usan UUID sintéticos. **No se
> borran**: se decide si se crean los usuarios de Auth o si la FK se agrega
> `NOT VALID` y se valida cuando el entorno esté limpio.

**T3 — filas con `empresa_id` nulo en tablas donde la política lo asumiría no
nulo** (todas las de dominio lo tienen `NOT NULL`, pero `auditoria.empresa_id` es
nullable, `0004:815`; decisión: `auditoria` se filtra por `empresa_id` y las
filas con `NULL` solo las ve el rol de servicio).

**T4 — rol efectivo actual** (esto es el hallazgo ⚪ de RA-03; se ejecuta **antes**
de diseñar las políticas):
```sql
select current_user,
       (select rolbypassrls from pg_roles where rolname = current_user) as bypass_rls,
       (select rolsuper from pg_roles where rolname = current_user) as superuser;
```
> No se ejecutó (sin base). Si el resultado es `postgres`/`service_role`, las
> políticas de hoy no protegen **nada** y el orden de trabajo cambia: primero el
> rol, después las políticas.

### Expand/contract
1. **Crear el rol** y la función de contexto (no afecta nada todavía).
2. **Políticas en modo permisivo** (`USING (true)`) → validar que la app sigue
   funcionando con `nucleo_app` (esto prueba que los `GRANT` alcanzan).
3. **`SET LOCAL` en `backend`** (handoff): `nucleo.empresa_id` + `nucleo.auth_id`
   por transacción. Sin esto, las políticas reales devuelven 0 filas.
4. **Políticas reales** tabla por tabla, empezando por las de lectura.
5. **`FORCE ROW LEVEL SECURITY`** al final, tabla por tabla.
6. **FK compuesta y FK de auth** (independientes del resto; pueden ir antes).

### Impacto y locks
- `CREATE POLICY` / `ALTER TABLE … ENABLE/FORCE RLS`: `AccessExclusiveLock`
  breve sobre la tabla (metadata). Sin reescritura.
- **Riesgo real:** si el paso 3 no está desplegado, la app deja de ver filas.
  Es un cambio coordinado con `backend` (no un `datos` solo).
- Rendimiento: cada consulta agrega una subconsulta a `usuarios_empresa`; medir
  con `EXPLAIN (ANALYZE, BUFFERS)` antes/después sobre volumen realista (hoy
  imposible: sin base).

### Rollback
`DROP POLICY` + `ALTER TABLE … NO FORCE ROW LEVEL SECURITY` + `DROP ROLE`
(después de revocar). El rollback **elimina el aislamiento**: debe tratarse como
incidente de seguridad, no como operación normal.

### Prueba con rol real (obligatoria)
- Conectar como `nucleo_app`, contexto empresa A.
- `SELECT` de un viaje de B ⇒ **0 filas** (no error, no fila).
- `INSERT` con `empresa_id = B` ⇒ `42501` / violación de `WITH CHECK`.
- `UPDATE` de una fila de B ⇒ 0 filas afectadas.
- `SELECT` de `nucleo.auditoria` de B ⇒ 0 filas.
- Mutación: `NO FORCE ROW LEVEL SECURITY` ⇒ las filas de B aparecen.

---

## 0021 — Cutover impuesto en DB y auditoría del cutover

### Objetivo e invariantes
**INV-T04**, **INV-A01**, **INV-A02**; handoff de **INV-X01** a `backend`.

### Objetos afectados
- Función `public.fn_legacy_congelado()` (`STABLE`, lee
  `nucleo.cutover_control`) + trigger `BEFORE INSERT OR UPDATE OR DELETE` en las
  tablas legacy con escritura (`viajes`, `gastos_viaje`, `facturas`,
  `factura_viaje`, `anticipos_chofer`, `ajustes_liquidacion`, `liquidaciones`,
  `mantenimientos`, `clientes`, `choferes`, `tractos`, `ramplas`,
  `pautas_mantenimiento`, `configuracion`, `kpis`).
- `trg_cutover_control_audit` en `nucleo.cutover_control`.
- Trigger `BEFORE TRUNCATE … FOR EACH STATEMENT` en `nucleo.auditoria`.

### Precondiciones
**C1 — estado del flag:**
```sql
select legacy_escritura_congelada, congelada_en, congelada_por, motivo
  from nucleo.cutover_control;
```
> Si ya está congelado en el entorno donde se aplica, **todos** los triggers
> legacy empiezan a rechazar de inmediato. Verificar antes de aplicar.

**C2 — escritores legacy activos** (para saber a quién se bloquea):
```sql
select count(*) from public.viajes
 where estado in ('programado','en_ruta');
```

### Impacto y locks
- `CREATE TRIGGER` en 15 tablas: `ShareRowExclusiveLock` breve cada una. Sin
  reescritura.
- Cada escritura legacy pasa a hacer un `SELECT` sobre una tabla de una fila
  (`cutover_control`) ⇒ impacto despreciable.
- **Riesgo:** un trigger que falla cerrado puede detener operación si
  `nucleo.cutover_control` no existe o no es legible. La función debe tratar
  "no encontrado" como **congelado** (fail-closed, al revés que
  `servicio_cutover.py:38-39`).

### Rollback
`DROP TRIGGER` en las tablas legacy. El flag y sus columnas se conservan.

### Prueba
Congelar por `UPDATE` (sin pasar por el middleware) e intentar `INSERT` en
`public.viajes` desde `psql` ⇒ `23514`. Descongelar ⇒ inserta. Mutación: retirar
los triggers ⇒ inserta con el flag en `true` (demuestra que el middleware no era
la garantía).

---

## Notas transversales de ejecución

1. **Ninguna migración se aplica sin:** base local arriba, `git status` revisado,
   backup si hay datos que no se pueden reconstruir, y autorización explícita
   (`AGENTS.md` §10).
2. **Orden de aplicación en local:** `0015 → 0021`, cada una con su prueba. Si
   una precondición devuelve filas, **se detiene la cadena**: las migraciones
   siguientes asumen que la anterior se aplicó.
3. **`CONCURRENTLY` fuera de transacción** (`0017`, `0018`): si el índice va
   concurrente, la migración no puede ser un único script transaccional. Se
   documenta como excepción explícita.
4. **Medir antes de decidir** (`0017` P3.3, `0019` L6): la elección entre índice
   normal y `CONCURRENTLY` depende del tamaño real, que hoy **no se midió**.
5. **Cada migración actualiza `docs/datos/01-matriz-garantias.md`** en la misma
   entrega: una matriz que dice 🔴 cuando ya hay 🟢 es peor que no tener matriz.
6. **Ningún rollback de este plan borra datos.** Los backfills se revierten
   desactivando, no eliminando.
