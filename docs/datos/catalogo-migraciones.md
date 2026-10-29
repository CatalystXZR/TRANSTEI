# Catálogo de migraciones — `supabase/migrations/0001`–`0019`

> **Pregunta que responde:** ¿qué hace cada migración, cuánto riesgo tiene y está aplicada?
> **Dueño:** agente `datos` · **Verificado:** 2026-10-29 · **Método:** lectura de DDL + `git`
> **Caduca si:** se agrega, edita o reordena una migración, o se aplica alguna.
> **Re-verificar con:** `ls supabase/migrations/` · `git ls-tree HEAD supabase/migrations/` · `git status --short supabase/migrations/`

---

## 0. Cómo leer este catálogo

1. **"Aplicada en base" es 🔴 en las 19 filas.** No hubo acceso a PostgreSQL en esta
   sesión. Lo único que se afirma es que **el archivo existe en disco** y qué
   contiene. Que el DDL esté en el repo no significa que esté en vigor.
2. **El repo tiene dos registros posibles de aplicación y ninguno sirve hoy:**
   - `public._migraciones` se crea en `0002_config_cobranza.sql:6-10` y **ninguna
     migración la popula** (`grep -rn "_migraciones" supabase/migrations/` → solo
     esa línea). Está vacía por construcción.
   - `supabase_migrations.schema_migrations` lo mantiene la CLI de Supabase; el
     repo no lo consulta ni lo versiona.
   Verificación pendiente (no ejecutada): `select version from
   supabase_migrations.schema_migrations order by version;`
3. **Riesgo** = impacto si la migración se aplica mal o se revierte mal, no
   dificultad de escritura.
4. **Estado en git** (verificado el 2026-10-29, §2): `committed` = está en `HEAD`;
   `staged` = índice con `A`, aún sin commit; `untracked` = solo en el working tree.
5. Las migraciones son **forward-only**: ninguna de `0001`–`0019` se edita después
   de aplicada. Lo que sigue se corrige con una migración nueva.

---

## 1. Catálogo

| Archivo | Objetivo | Objetos que crea / altera | Riesgo | Estado (git) | Aplicada en base |
|---|---|---|---|---|---|
| `0001_esquema_base.sql` | Esquema legacy `public` del ERP | 8 `enum`; 15 tablas (`usuarios`…`configuracion`); 11 índices; `set_updated_at()`; 9 triggers `*_updated` + `on_auth_user_created`; policy `usuarios` | Alto (base del legacy en uso) | committed | 🔴 |
| `0002_config_cobranza.sql` | Config de cobranza y control de migraciones | tabla `_migraciones`; fila `dias_alerta_cobranza`; índice `factura_viaje(viaje_id)`; bucket `respaldos` | Bajo | committed | 🔴 |
| `0003_kpis.sql` | KPIs configurables | tabla `kpis` + RLS + trigger `updated`; **4 KPIs de ejemplo** sembrados | Bajo | committed | 🔴 |
| `0004_nucleo_operacional.sql` | Núcleo v2 multiempresa: el libro de ocupación y el viaje | 11 `enum`; 15 tablas (`empresas`…`auditoria`); 19 funciones; 48 triggers; 32 índices; **3 `EXCLUDE USING gist`**; RLS en 15 tablas; grants a `service_role` | **Alto** (disponibilidad, dinero, base de todo `nucleo`) | staged (`A`) | 🔴 |
| `0005_comercial.sql` | Comercial editable (centros de costo, sobregiro, líneas activas) | tabla `centros_costo`; `ALTER` en `ordenes_compra` y `ordenes_compra_lineas`; 4 índices; 3 triggers (touch/version/audit) | Medio | staged (`A`) | 🔴 |
| `0006_bloqueos.sql` | Cancelación trazable de bloqueos/mantenciones | columnas `cancelado_*` en `reservas_recurso`; índice de bloqueos | Bajo | staged (`A`) | 🔴 |
| `0007_expediente.sql` | Expediente del viaje | 5 tablas (`viaje_paradas`, `viaje_checklist`, `viaje_eventos`, `viaje_incidentes`, `viaje_documentos`); `fn_evento_inmutable`; 14 triggers; 5 índices | Medio | staged (`A`) | 🔴 |
| `0008_expediente_automatico.sql` | Todo viaje nace con expediente | `fn_viaje_expediente_inicial`; trigger `trg_viajes_75_expediente` | Medio (corre en todo `INSERT` de viaje) | staged (`A`) | 🔴 |
| `0009_pod.sql` | POD y bloqueo de facturación sin POD | tabla `pod`; `fn_pod_no_borrar`; `fn_viaje_facturacion` (reemplaza la de `0004`); 4 triggers | Medio (dinero: habilita facturar) | staged (`A`) | 🔴 |
| `0010_conductor.sql` | Vínculo `auth_id` ↔ chofer (PWA) | columna `choferes.auth_id`; índice único `(empresa_id, auth_id)` | Bajo | staged (`A`) | 🔴 |
| `0011_gastos.sql` | Gastos, combustible y costo real | tablas `precios_diesel`, `viaje_gastos`; `viajes.costo_variable_real`; `fn_viaje_costos`, `fn_gasto_costos`; 5 triggers | **Alto** (dinero: margen por viaje) | staged (`A`) | 🔴 |
| `0012_rentabilidad.sql` | Parámetros de costo y Freight Score | tabla `configuracion_costos` + RLS + 3 triggers | Bajo | staged (`A`) | 🔴 |
| `0013_facturacion.sql` | Facturación y cobranza del núcleo | 5 tablas (`facturas_nucleo`, `factura_viajes`, `pagos_nucleo`, `notas_credito_nucleo`, `promesas_pago_nucleo`); `fn_factura_estado`, `fn_pago_estado`, `fn_nota_estado`; 11 triggers; 6 índices | **Alto** (dinero y documento tributario) | staged (`A`) | 🔴 |
| `0014_cutover.sql` | Flag de congelamiento del legacy | tabla `cutover_control` + RLS; fila inicial | Medio (gobierna el cutover) | staged (`A`) | 🔴 |
| `0015_viaje_con_recursos_ocupa_y_valida.sql` | Todo viaje con los 3 recursos ocupa el libro y valida documentos | `fn_viaje_reservas` reescrita (`:183`); `fn_viaje_documentos` nueva (`:247`); trigger `trg_viajes_05_documentos` (`:313`); **backfill** de `reservas_recurso` (`:320-471`); aborta con `23514` si hay solapes (`:388`) | **Alto** (disponibilidad + backfill) | untracked (`??`) | 🔴 |
| `0016_licencia_a5_bloqueante.sql` | R-02: solo licencia A5 asignable; aviso de documentos a 14 días | `fn_viaje_licencia_a5` (`:193`); trigger `trg_viajes_03_licencia_a5` (`:255`); `empresas.dias_alerta_documentos` default 30→**14** (`:182`); `COMMENT` que deprecia `tractos.licencias_permitidas` (`:262`) | **Alto** (puede bloquear asignaciones en operación) | untracked (`??`) | 🔴 |
| `0017_default_comision_chofer.sql` | R-01: default de comisión 10 % | `choferes.porcentaje_comision` default 0→**0.10** (`:47`); sin backfill | Bajo en ejecución / **Alto en dinero** (define lo que gana un chofer nuevo) | untracked (`??`) | 🔴 |
| `0018_carga_licencia_clase_a5.sql` | Cargar `licencia_clase='A5'` en choferes TEI sin clase | `UPDATE` de filas en `nucleo.choferes` (`:67-113`), solo empresa `TEI`, solo con documento `licencia_conducir` vigente; imprime RUTs en `NOTICE` | **Alto** (dato declarado, no contrastado con licencia física) | untracked (`??`) | 🔴 |
| `0019_comision_piloto_10.sql` | R-01: alinear a 10 % los choferes TEI en 0 | `UPDATE` de filas en `nucleo.choferes` (`:44-66`), solo empresa `TEI`, activos y `porcentaje_comision = 0` | **Alto** (dinero: reescribe la base de pago) | untracked (`??`) | 🔴 |

**Nota (a) — única declaración de aplicación en el repo:** `docs/qa/informes/2026-10-29-r01-r02-suite-verde.md:1-45`
reporta PostgreSQL local arriba y el trigger de `0016` activo (los fixtures sin
`licencia_clase` fallan con `CheckViolation ... Licencia A5 requerida`). Eso
sugiere que `0015`/`0016` están aplicadas en **esa** base local (🟡), no en
producción, y no fue re-verificado por `datos`. Para `0017`, `0018` y `0019` no
hay ninguna declaración.

**Nota (b) — migraciones de datos:** `0015` (backfill de reservas), `0018` y
`0019` escriben filas, no solo esquema. En un entorno con datos reales exigen
precondiciones ejecutadas y conteos antes/después, no solo `psql -f`.

---

## 2. Estado real en git (verificado)

```text
$ ls supabase/migrations/ | wc -l
19

$ git ls-tree HEAD supabase/migrations/ | awk '{print $4}'
supabase/migrations/0001_esquema_base.sql
supabase/migrations/0002_config_cobranza.sql
supabase/migrations/0003_kpis.sql

$ git status --short supabase/migrations/
A  supabase/migrations/0004_nucleo_operacional.sql
A  supabase/migrations/0005_comercial.sql
A  supabase/migrations/0006_bloqueos.sql
A  supabase/migrations/0007_expediente.sql
A  supabase/migrations/0008_expediente_automatico.sql
A  supabase/migrations/0009_pod.sql
A  supabase/migrations/0010_conductor.sql
A  supabase/migrations/0011_gastos.sql
A  supabase/migrations/0012_rentabilidad.sql
A  supabase/migrations/0013_facturacion.sql
A  supabase/migrations/0014_cutover.sql
?? supabase/migrations/0015_viaje_con_recursos_ocupa_y_valida.sql
?? supabase/migrations/0016_licencia_a5_bloqueante.sql
?? supabase/migrations/0017_default_comision_chofer.sql
?? supabase/migrations/0018_carga_licencia_clase_a5.sql
?? supabase/migrations/0019_comision_piloto_10.sql
```

Consecuencia operativa: **`HEAD` no reproduce el esquema.** Un clon del
repositorio aplica 3 migraciones y obtiene solo el legacy `public`; las 16
restantes no están versionadas en ningún commit. Esto no es un detalle de
higiene: cualquier `supabase db reset` sobre `HEAD` deja un sistema sin `nucleo`.

---

## 3. Migraciones de alto riesgo

Criterio: si se aplican mal, se revierten mal o escriben datos que no se pueden
reconstruir. El rollback de cada una cabe en una línea; el detalle vive en el
encabezado del propio `.sql`.

### `0015` — ocupación + documentos (`untracked`)

- **Ojo — comentario obsoleto:** el encabezado de `0015:130-143` declara
  "incompatible" a `scripts/cutover_legacy.py`, pero describe una **versión anterior**.
  El script actual migra los viajes `confirmado` **sin recursos**
  (`cutover_legacy.py:6-13,378-401`), de modo que el `23514` documental **no se dispara**.
  Deuda D-05: corregir este catálogo, no la migración aplicada.
- **Rollback:** `drop trigger trg_viajes_05_documentos; drop function
  fn_viaje_documentos();` restaurar `fn_viaje_reservas` con el cuerpo de
  `0004:1621-1650`; **desactivar** (no borrar) las reservas con
  `creado_por='migracion_0015'` (`0015:145-164`).
- **Irreversible en la práctica:** volver atrás reabre el agujero de INV-D04; se
  documenta como incidente, no como operación rutinaria.

### `0016` — licencia A5 (`untracked`)

- **Riesgo:** un chofer sin clase o con clase distinta de A5 no puede asignarse.
  En una flota con licencias sin cargar, la operación se detiene con `23514`.
- **Rollback:** `drop trigger trg_viajes_03_licencia_a5; drop function
  fn_viaje_licencia_a5(); alter table nucleo.empresas alter column
  dias_alerta_documentos set default 30;` (`0016:182-186`; el 30 original está en
  `0004:120`).
- **No revierte datos:** no escribe filas.

### `0017` — default de comisión 10 % (`untracked`)

- **Riesgo:** cambio de catálogo, instantáneo, **no reescribe filas**
  (`0017:47-49`). El riesgo es económico, no técnico: todo chofer nuevo sin
  porcentaje explícito devenga 10 % en vez de 0 %.
- **Rollback:** `alter table nucleo.choferes alter column porcentaje_comision
  set default 0;` (`0017:37-39`). No hay datos que restaurar.

### `0019` — comisión 10 % en choferes TEI (`untracked`)

- **Riesgo:** reescribe la base de pago de los choferes activos de `TEI` que
  estaban en 0. No toca otras empresas ni choferes inactivos (`0019:56-60`).
- **Rollback:** `update nucleo.choferes set porcentaje_comision = 0 where id =
  any (array[...]::uuid[]);` (`0019:31-35`). **Advertencia:** la lista de RUT/ids
  solo existe en el `NOTICE` de la migración (`0019:65-66`). Si ese log no se
  captura al aplicar, **el rollback exacto no es posible**; se vuelve por lista
  de RUT reconstruida a mano. Registrar el `NOTICE` es parte del procedimiento.
- **Irreversible sin log.**

> `0018` no está en la lista anterior porque no impone una garantía: es una carga
> de datos. Aun así es de riesgo alto por su procedencia (el propio archivo la
> marca 🚩): asigna `A5` a choferes **sin contrastar la licencia física**
> (`0018:16-19`). Su rollback también depende del `NOTICE`: `update
> nucleo.choferes set licencia_clase = null where id = any (...)` (`0018:50-60`).

---

## 4. Qué reemplaza este catálogo

Este documento sustituye como **referencia de estado** al histórico
`docs/_archivo/planes/plan-migraciones-0015.md`. Ese plan describía la secuencia
`0015` ocupación → `0016` comercial → `0017` gastos → `0018` facturación →
`0019` legacy → `0020` RLS → `0021` cutover, y **esa numeración quedó muerta**:

| Número | Plan histórico | Contenido real en disco |
|---|---|---|
| `0015` | Ocupación (INV-D04, D05, D06) | Ocupación **+ puerta documental** (INV-D04, INV-DOC04) + backfill. **No** incluye D05 ni D06 |
| `0016` | Comercial (INV-C03…C05, INV-DOC03) | **Licencia A5** (R-02) + default de aviso a 14 días |
| `0017` | Gastos (INV-G04…G06) | **Default de comisión 10 %** |
| `0018` | Facturación (INV-F01…F07) | **Carga de `licencia_clase='A5'`** (datos) |
| `0019` | Legacy `public` (INV-L01…L06) | **Comisión 10 % en choferes TEI** (datos) |

Ninguno de los invariantes de gastos, facturación, legacy, RLS ni cutover que el
plan asignaba a `0017`–`0021` tiene hoy migración. Quedan registrados en
`docs/datos/invariantes.md` como ausentes o parciales; **no citar el plan
archivado como estado**.

Los diseños de `0015` y `0016` sí existen y se conservan:
`docs/datos/migraciones/0015-ocupacion-confirmado.md` y
`docs/datos/migraciones/0016-licencia-a5.md`. Para `0017`–`0019` el único diseño
es el encabezado del `.sql`.

---

*Histórico: `docs/_archivo/planes/plan-migraciones-0015.md` (archivado 2026-10-29,
no citar como estado).*
