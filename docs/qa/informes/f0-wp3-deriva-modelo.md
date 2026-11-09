> ⚠️ **Aviso de vigencia (2026-11-01):** cita archivos/cifras anteriores al retiro del legacy (`public`, `lib/api.ts`, `backend/app/api/routes/*`, `kpi_engine.py`). No citar como estado actual; ver `docs/estado.md` §2–§6 y `docs/PLAN_DESARROLLO.md`.

# F0-WP3 — Deriva modelo↔DDL y huecos de integridad/aislamiento

> Depositado por el orquestador (2026-10-29): el agente `datos` no tiene permiso de escritura en `docs/qa/informes/`; el contenido es íntegro de su respuesta. F0 es solo lectura.

> **Fecha:** 2026-10-29 · **Agente:** `datos` · **Misión:** F0 (due diligence, SOLO LECTURA)
> **Método:** lectura de `backend/app/nucleo/models.py` y `backend/app/models/__init__.py`;
> consultas `SELECT` de catálogo contra la base local (contenedor `supabase_db_TRANSTEI`,
> `docker exec … psql -U postgres`); lectura de `supabase/migrations/0001…0019` y
> `docs/datos/invariantes.md`.
> **No se ejecutó** nada destructivo, ninguna migración, ninguna escritura.
> **Certezas:** 🟢 verificado (salida pegada o `archivo:línea`) · 🟡 inferido · 🔴 no determinable.

---

## 0. Resumen ejecutivo

1. **Modelo↔DDL:** los 30 modelos SQLModel del núcleo existen en DDL y en la base; la tabla
   `nucleo.cutover_control` (0014) **no tiene modelo**. A nivel de **columnas** la deriva es
   mínima (tipos `char(n)` vs `varchar`, `smallint`/`bigint` vs `int`). La deriva real está en
   **constraints/índices/triggers**: el DDL impone ~90 CHECK, 3 EXCLUDE, 10+ índices únicos
   (parciales y funcionales) y ~90 triggers que **no están representados** en el modelo; y 4
   UNIQUE que el modelo declara sobre la columna pura existen en DDL como **índices únicos
   funcionales normalizados** (semántica distinta).
2. **Estado de migraciones:** `schema_migrations` registra 0001–0014, pero la base **contiene
   ya los objetos DDL de 0015, 0016 y 0017** (triggers, funciones, defaults) y 3 reservas con
   `creado_por='migracion_0015'` (backfill corrido). Evidencia física de 0018/0019: 🟡
   (consistente con datos TEI, no concluyente). El registro de migraciones está **desincronizado**
   del esquema físico.
3. **RLS:** 31/31 tablas `nucleo` con `rowsecurity=true`, **0 políticas**, **0 `FORCE`**. El
   backend conecta con rol `postgres` (dueño + `rolbypassrls=true`): RLS es inerte para la
   aplicación. `anon`/`authenticated` ni siquiera tienen `USAGE` sobre el schema `nucleo`
   (`0004:1886` solo a `service_role`). INV-T01 sigue **ausente**.
4. **Auditoría:** 28/31 tablas `nucleo` con trigger `_audit`; **sin** auditoría: `cutover_control`,
   `folio_contador`, `transiciones_viaje`. `public` no tiene auditoría (solo `set_updated_at`).
5. **Tipos:** 0 columnas `float`/`double`/`real` en ambos schemas; 100% de los timestamps son
   `timestamptz`; dinero en `numeric`; ventanas en `tstzrange`. Único `date` en eventos: el
   legacy `public.viajes` (INV-L01/L06).
6. **Invariantes:** los 8 con mecanismo del catálogo (`INV-D04/D07/DOC04/R02-01/R02-02/C03/T02/A01`)
   se verificaron presentes en la base viva 🟢; los 23+ ausentes siguen sin mecanismo 🟢.

---

## 1. Estado real de las migraciones

**Comando:** `docker exec supabase_db_TRANSTEI psql -U postgres -d postgres -tA -c "select version from supabase_migrations.schema_migrations order by version::int"`

**Salida 🟢:** `0001 0002 0003 0004 0005 0006 0007 0008 0009 0010 0011 0012 0013 0014` (14 filas).

**Objetos físicos presentes en la base (no registrados):**

| Migración | Objeto | Evidencia en DB 🟢 |
|---|---|---|
| 0015 | `fn_viaje_documentos()` + `trg_viajes_05_documentos` | `pg_trigger`: `nucleo.viajes|trg_viajes_05_documentos|O` (habilitado) |
| 0015 | `fn_viaje_reservas()` versión 0015 | `obj_description('nucleo.fn_viaje_reservas'::regproc)` → *"0015: todo viaje con tracto, rampla y chofer ocupa el libro…"* (= `0015:240-242`) |
| 0015 | Backfill corrido | `select count(*) from nucleo.reservas_recurso where creado_por='migracion_0015'` → **3** |
| 0016 | `fn_viaje_licencia_a5()` + `trg_viajes_03_licencia_a5` | `pg_trigger`: `trg_viajes_03_licencia_a5|O`; `pg_proc.nucleo.fn_viaje_licencia_a5` existe |
| 0016 | `dias_alerta_documentos` default 14 | `information_schema.columns` → `14` (DDL `0004:120` dice 30; `0016:182-183` lo cambia) |
| 0017 | `porcentaje_comision` default 0.10 | `information_schema.columns` → `0.10` (`0017:47-48`) |
| 0018 | choferes TEI con `licencia_clase='A5'` | datos: `TEI|3|3|4` (3 de 4 choferes A5) — 🟡 también pudo venir del seed |
| 0019 | choferes TEI con comisión 0.10 | datos: `TEI` tiene 3 de 4 con 0.10 — 🟡 ídem |

**Impacto de la desincronización (la base está "5 archivos atrás" en el registro, no en el esquema):**
- `supabase db push`/`migration up` re-aplicaría 0015–0019 sobre un esquema que ya las tiene.
  Los cinco archivos declaran ser **re-ejecutables** (DROP IF EXISTS / CREATE OR REPLACE /
  backfill con `NOT EXISTS` / `UPDATE … WHERE`), por lo que la re-aplicación es idempotente por
  diseño (`0015:477-478`, `0016:273-274`, `0018:90-108`, `0019:55-63`). El único aborto posible
  es el backfill de 0015 si existieran solapes P1.2 (`0015:70-93`) — en esta base ya corrió y
  no dejó pendientes.
- **Causa no determinable 🔴:** no hay registro en el repo de *cómo* llegaron esos objetos a la
  base sin pasar por `schema_migrations` (posible `psql -f` directo o reset previo con otro
  mecanismo de tracking). El reset autorizado al final reconciliará el estado.
- **Ojo de cara al reset:** la base quedará en el estado 0015–0019 *completo* (hoy falta
  confirmar 0018/0019), y las pruebas escritas en `supabase/tests/` (0015_*, 0016_*) pasan a ser
  ejecutables con datos reales.

---

## 2. Tabla de deriva modelo ↔ DDL (núcleo)

Conteos: **30 tablas en modelo** (`models.py`) · **31 en DDL/DB**. Columnas comparadas contra el
volcado real de `information_schema.columns` (595 columnas `nucleo`): **ninguna columna del modelo
falta en el DDL y ninguna columna del DDL falta en el modelo** (salvo la tabla `cutover_control`
completa). Los 11 enums nativos (`pg_enum`) coinciden valor a valor con los `Enum` del modelo 🟢.

| Tabla | Modelo | DDL/DB | Diferencias | Severidad |
|---|---|---|---|---|
| `empresas` | ✅ `models.py:198` | ✅ `0004:102` | Modelo no declara `UNIQUE codigo` (`0004:104`); DDL extra: `ck_empresa_rut_no_vacio` (`0004:133`), índice `uq_empresas_rut_norm` (`0004:136`); `char(2)/char(3)` (pais/moneda) vs `varchar`; nombre del CHECK de buffer difiere (`ck_empresa_buffer` modelo vs auto `empresas_buffer_operacional_min_check`) | Baja |
| `usuarios_empresa` | ✅ `:235` | ✅ `0004:139` | Nombre UNIQUE distinto (`uq_usuario_empresa_auth` vs auto `usuarios_empresa_empresa_id_auth_id_key`); DDL extra `idx_usuarios_empresa_auth` parcial | Baja |
| `clientes` | ✅ `:257` | ✅ `0004:158` | Modelo `uq_clientes_empresa_rut` sobre columna pura (`:261`) vs DDL **índice funcional** `uq_clientes_empresa_rut_norm` normalizado (`0004:184`); DDL extra `ck_cliente_rut_no_vacio`, `credito_autorizado >= 0` | Media |
| `tarifas` | ✅ `:288` | ✅ `0004:377` | DDL extra `ck_tarifa_moneda`, `ck_tarifa_vigencia` (`0004:412`), `minimo_cobro>=0`, `precio_unitario>=0`, `precio_diesel_base>=0`, `rendimiento>0`, `participacion 0..1`; `char(3)` | Baja |
| `centros_costo` | ✅ `:340` | ✅ `0005:16` | DDL extra `ck_centro_costo_codigo`/`_nombre` | Baja |
| `ordenes_compra` | ✅ `:361` | ✅ `0004:421` | Modelo sí declara `ck_oc_consumo` y `ck_oc_sobregiro_estado` (`:376-383` = `0004:453`, `0005:61-68`) ✅; DDL extra: `ck_oc_moneda`, `ck_oc_vigencia` (`0004:452`), `ck_oc_sobregiro_pendiente`, `ck_oc_sobregiro_solicitado`, `monto_autorizado>0`, `monto_consumido>=0`, `sobregiro_autorizado>=0`; `char(3)` | Baja |
| `ordenes_compra_lineas` | ✅ `:423` | ✅ `0004:459` | **`fk_ocl_oc`: DB `ON DELETE CASCADE` vs modelo sin `ondelete`** (SQLAlchemy renderizaría NO ACTION si se usara `create_all`) | Media |
| `tractos` | ✅ `:470` | ✅ `0004:191` | `uq_tractos_empresa_patente` modelo columna pura (`:474`) vs DDL funcional normalizado (`0004:226`); DDL extra `uq_tractos_empresa_vin` (`0004:228`), `ck_tracto_patente_no_vacia`, `ck_tracto_peso_coherente`, `ck_tracto_capacidad_coherente`, `tara>0`, `km/horas>=0`, `volumen>0`; CHECK del modelo con nombre distinto (`ck_tracto_peso` vs auto) | Media |
| `ramplas` | ✅ `:515` | ✅ `0004:235` | Ídem patente (`0004:273`) + `uq_ramplas_empresa_vin` (`0004:275`), `ck_rampla_temperaturas`, `ck_rampla_patente_no_vacia` | Media |
| `choferes` | ✅ `:557` | ✅ `0004:282` | `uq_choferes_empresa_rut` modelo (`:561`) vs funcional normalizado (`0004:317`); DDL extra `uq_choferes_empresa_licencia` (`0004:319`), `uq_choferes_empresa_auth` (`0010:11-13`), `ck_chofer_nombre/rut_no_vacio`, `sueldo_base>=0`, `porcentaje_comision 0..1` (el modelo no declara `ge/le` aquí, `:584-586`) | Media |
| `documentos` | ✅ `:601` | ✅ `0004:326` | DDL extra `ck_doc_un_solo_recurso` (`0004:354`), `ck_doc_fechas` (`0004:359`), índices parciales `uq_doc_{tracto,rampla,chofer}_vigente` (`0004:362-368`), trigger `trg_documentos_vigente` (`0004:1802`); `char(64)` vs `varchar(64)` | Media |
| `folio_contador` | ✅ `:648` | ✅ `0004:490` | `ultimo`: DB `bigint` vs modelo `int` | Baja |
| `viajes` | ✅ `:661` | ✅ `0004:542` | DDL extra 12 CHECK nombrados: `ck_viaje_ventana` (`0004:666`), `ck_viaje_recursos_por_estado` (`0004:671`), `ck_viaje_peligrosa_un` (`0004:682`), `ck_viaje_anulacion` (`0004:685`), fechas/fin_estimado/fin_real/moneda/peso/temperaturas/buffer; `prioridad`: DB `smallint` vs modelo `int`; `char(3)` | **Alta** |
| `reservas_recurso` | ✅ `:1282` | ✅ `0004:703` | DDL extra: **3 `EXCLUDE` gist parciales** (`0004:744-757`), `ck_reserva_un_recurso` (`0004:729`), `ck_reserva_ventana` (`0004:734`), `ck_reserva_motivo`, `ck_reserva_viaje`, índice parcial `uq_reserva_viaje_recurso_activa` (`0004:759`) | **Alta** |
| `transiciones_viaje` | ✅ `:1331` | ✅ `0004:772` | Sin diferencias (sin `empresa_id` en ambos) | — |
| `auditoria` | ✅ `:1344` | ✅ `0004:813` | DDL extra `auditoria_operacion_check`; `tabla/operacion/auth_id/request_id`: DB `text` vs modelo `varchar(200/10)` | Baja |
| `viaje_paradas` | ✅ `:837` | ✅ `0007:17` | DDL extra `ck_parada_estado/tipo/nombre/ventana` | Baja |
| `viaje_checklist` | ✅ `:873` | ✅ `0007:63` | DDL extra `ck_checklist_completado/item` | Baja |
| `viaje_eventos` | ✅ `:904` | ✅ `0007:102` | DDL extra `ck_evento_descripcion` + trigger `trg_eventos_inmutable` (`0007:131`) | Baja |
| `viaje_incidentes` | ✅ `:930` | ✅ `0007:139` | DDL extra `ck_incidente_estado/severidad/resolucion/descripcion` | Baja |
| `viaje_documentos` | ✅ `:998` | ✅ `0007:181` | DDL extra `ck_doc_viaje_nombre`, `tamano_bytes>=0`; `bigint` vs `int`; `char(64)` | Baja |
| `pod` | ✅ `:961` | ✅ `0009:8` | DDL extra `ck_pod_receptor/firma/fotos/rut`, lat/lon; trigger `trg_pod_no_delete` (`0009:58`); `char(64)` | Baja |
| `precios_diesel` | ✅ `:1031` | ✅ `0011:11` | Sin diferencias (modelo `ge=0` = CHECK auto) | — |
| `viaje_gastos` | ✅ `:1048` | ✅ `0011:29` | DDL extra `ck_gasto_estado/tipo/aprobacion/rechazo/iva`; trigger `trg_gastos_costos` (`0011:154`); `char(3)` | Media |
| `configuracion_costos` | ✅ `:1100` | ✅ `0012:8` | DDL extra `margen_objetivo <= 0.95`, `benchmark>0`, `contribucion>=0`, `costo_variable>=0`, `rendimiento>0` | Baja |
| `facturas_nucleo` | ✅ `:1133` | ✅ `0013:10` | DDL extra `ck_factura_estado/fechas/moneda`, `neto>0`, `iva>=0`; `char(3)` | Media |
| `factura_viajes` | ✅ `:1178` | ✅ `0013:54` | DDL extra `UNIQUE (empresa_id, factura_id, viaje_id)` | Baja |
| `pagos_nucleo` | ✅ `:1204` | ✅ `0013:78` | DDL extra `ck_pago_metodo`, `monto>0` | Baja |
| `notas_credito_nucleo` | ✅ `:1231` | ✅ `0013:112` | DDL extra `ck_nc_estado/motivo`, `monto>0` | Baja |
| `promesas_pago_nucleo` | ✅ `:1256` | ✅ `0013:139` | DDL extra `ck_promesa_estado`, `monto>0` | Baja |
| `cutover_control` | ❌ **sin modelo** | ✅ `0014:8-15` | Tabla entera sin mapeo SQLModel; el backend la opera por SQL crudo (`servicio_cutover.py`) | **Media** |

**Severidad "Alta" (2):** `viajes` y `reservas_recurso` — las constraints que materializan los
invariantes de disponibilidad (`ck_viaje_ventana`, `ck_viaje_recursos_por_estado`, 3 EXCLUDE,
`ck_reserva_un_recurso`) son **invisibles para el modelo** y no hay ninguna barrera en
SQLModel/Python que las reemplace si alguien algún día usa `create_all()` (prohibido por
`AGENTS.md`, pero el riesgo de deriva de documentación es el que se mide aquí).

**Severidad "Media":** UNIQUE funcionales normalizados (RUT/patente) que el modelo declara con
semántica distinta; `fk_ocl_oc` CASCADE; índices parciales de documento vigente y de reserva
única activa; tabla `cutover_control`.

---

## 3. Constraints/triggers del DDL NO representados en el modelo

### 3.1 EXCLUDE (disponibilidad) — `0004:744-757` 🟢
```
exclude using gist (tracto_id with =, ventana with &&) where (recurso_tipo='tracto' and activa)   → ex_reserva_tracto
exclude using gist (rampla_id with =, ventana with &&)  where (recurso_tipo='rampla' and activa)   → ex_reserva_rampla
exclude using gist (chofer_id with =, ventana with &&)  where (recurso_tipo='chofer' and activa)   → ex_reserva_chofer
```
Verificados en `pg_constraint` (contype `x`) y en `pg_indexes` (gist). Extensión `btree_gist` instalada 🟢. INV-D07.

### 3.2 CHECKs relevantes solo en DDL (selección; ver §2 para la lista completa por tabla)

| Constraint | Línea | Invariante asociado |
|---|---|---|
| `ck_viaje_ventana` (rango no vacío, `lower=inicio_planificado`, `upper>=fin efectivo`) | `0004:666` | INV-D04 (libro coherente) |
| `ck_viaje_recursos_por_estado` (estados avanzados exigen los 3 recursos) | `0004:671` | asignación completa |
| `ck_viaje_anulacion` (anulado ⇒ motivo) | `0004:685` | transiciones |
| `ck_viaje_peligrosa_un` (carga peligrosa ⇒ nº UN) | `0004:682` | R-02 |
| `ck_reserva_un_recurso` (exactamente un recurso tipado) | `0004:729` | EXCLUDE sin NULL |
| `ck_reserva_ventana` (rango válido) | `0004:734` | EXCLUDE sin NULL |
| `ck_doc_un_solo_recurso` | `0004:354` | documentos |
| `ck_oc_consumo` (`monto_consumido <= monto_autorizado + sobregiro`) | `0004:453` | INV-C03 (sí está en el modelo) |
| `ck_oc_sobregiro_pendiente` | `0005:61-68` | INV-C03 (parcial) |
| `ck_gasto_estado/aprobacion/rechazo/iva` | `0011` | INV-G04/G05 (aún sin trigger de protección) |
| `ck_factura_estado` / `ck_factura_fechas` | `0013` | INV-F03/F06 (sin trigger de inmutabilidad) |
| `auditoria_operacion_check` | `0004:813+` | auditoría |

### 3.3 Triggers solo en DDL (SQLModel no los expresa) — selección crítica

| Trigger | Dónde | Línea | Función |
|---|---|---|---|
| `trg_viajes_00_ventana` … `80_oc` (10 triggers ordenados) | `nucleo.viajes` | `0004:1832-1850` | ventana, validación, facturación, protección, transición, touch, version, audit, reservas, OC |
| `trg_viajes_05_documentos` | `nucleo.viajes` | `0015:313` | INV-DOC04 |
| `trg_viajes_03_licencia_a5` | `nucleo.viajes` | `0016:255` | INV-R02-01 |
| `trg_reservas_validar` / `_no_delete` | `nucleo.reservas_recurso` | `0004:1857,1859` | validación + no borrar |
| `trg_auditoria_no_update` | `nucleo.auditoria` | `0004:890` | append-only (UPDATE/DELETE) |
| `trg_eventos_inmutable` | `nucleo.viaje_eventos` | `0007:131` | append-only |
| `trg_documentos_vigente` / `_no_delete` | `nucleo.documentos` | `0004:1802,1804` | vigencia + no borrar |
| `trg_pod_no_delete` | `nucleo.pod` | `0009:58` | no borrar |
| `trg_pagos_estado` / `trg_nc_estado` | `nucleo.pagos_nucleo`, `notas_credito_nucleo` | `0013:245,248` | recálculo de estado de factura |
| `trg_gastos_costos` | `nucleo.viaje_gastos` | `0011:154` | costo real del viaje |
| `trg_viajes_75_expediente` | `nucleo.viajes` | `0008:42` | checklist automático |

Patrón por tabla transaccional: `_touch` (updated_at/updated_by) + `_version` + `_audit`
(ver §5). **Ninguno de estos mecanismos puede reconstruirse desde `models.py`.**

### 3.4 Índices únicos parciales/funcionales solo en DDL

`uq_empresas_rut_norm` (`0004:136`) · `uq_clientes_empresa_rut_norm` (`0004:184`) ·
`uq_choferes_empresa_rut_norm` (`0004:317`) · `uq_choferes_empresa_licencia` (`0004:319`) ·
`uq_choferes_empresa_auth` (`0010:11-13`) · `uq_tractos_empresa_patente`/`_vin` (`0004:226,228`) ·
`uq_ramplas_empresa_patente`/`_vin` (`0004:273,275`) · `uq_doc_*_vigente` ×3 (`0004:362-368`) ·
`uq_reserva_viaje_recurso_activa` (`0004:759`) · `UNIQUE (empresa_id, factura_id, viaje_id)` en
`factura_viajes` (`0013`) · `UNIQUE (empresa_id)` en `configuracion_costos` (en modelo ✅).

---

## 4. FKs compuestas y tablas sin `empresa_id`

**Comando:** `select count(*) from pg_constraint where contype='f' and connamespace='nucleo'::regnamespace and pg_get_constraintdef(oid) like '%empresa_id%'` → **59** 🟢

Desglose verificado en `pg_constraint`:
- **27 FKs simples** `(empresa_id) → nucleo.empresas(id) ON DELETE RESTRICT` (una por tabla
  transaccional; `folio_contador` incluida).
- **32 FKs compuestas `(empresa_id, col)`**: `documentos` 3 (tracto/rampla/chofer) ·
  `tarifas` 1 (cliente) · `ordenes_compra` 2 (cliente, centro_costo) · `ordenes_compra_lineas` 3
  (oc, tarifa, centro_costo) · `viajes` 6 (cliente, oc, tarifa, tracto, rampla, chofer) ·
  `reservas_recurso` 3 (tracto, rampla, chofer) · 8 tablas con `fk_*_viaje` (paradas, checklist,
  eventos, incidentes, documentos, pod, gastos, factura_viajes→viaje) · `facturas_nucleo` 2
  (cliente, oc) · `factura_viajes` 2 (factura, viaje) · `pagos`/`notas_credito`/`promesas` 3
  (factura). Todas `RESTRICT` salvo `fk_ocl_oc` (**CASCADE**).
- **Única FK sin `empresa_id` en tablas tenant:** `fk_reserva_viaje` (`reservas_recurso.viaje_id
  → nucleo.viajes.id`, `0004:727-728`) — es el hueco documentado como INV-T02 (parcial: lo cubre
  `fn_reserva_validar` solo si `activa`, `0004:1669-1676`).

**Tablas `nucleo` sin columna `empresa_id` 🟢:** `transiciones_viaje`, `cutover_control`
(catálogo/control global, razonable). `auditoria` la tiene **nullable** (registra cambios de
empresas con `empresa_id` nulo cuando no hay contexto).

---

## 5. RLS — clasificación con evidencia

**Comandos y salidas 🟢:**

```
$ docker exec supabase_db_TRANSTEI psql -U postgres -d postgres -tA -c "select n.nspname, c.relname, c.relrowsecurity, c.relforcerowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace where c.relkind='r' and n.nspname in ('nucleo','public') order by 1,2"
  → nucleo: 31 filas, todas relrowsecurity=t, relforcerowsecurity=f
  → public: 16 filas relrowsecurity=t (usuarios, clientes, choferes, tractos, ramplas, viajes,
    gastos_viaje, facturas, factura_viaje, anticipos_chofer, ajustes_liquidacion, liquidaciones,
    pautas_mantenimiento, mantenimientos, configuracion, kpis), 1 fila relrowsecurity=f (_migraciones)

$ … -c "select n.nspname, c.relname, count(p.oid) from pg_class c join pg_namespace n on n.oid=c.relnamespace left join pg_policy p on p.polrelid=c.oid where c.relkind='r' and n.nspname in ('nucleo','public') group by n.nspname, c.relname having count(p.oid)>0"
  → public|usuarios|1   (política: "leer propio perfil", FOR SELECT, qual = (auth.uid() = auth_id))
  → nucleo: 0 filas

$ … -c "select rolname||'|'||rolsuper||'|'||rolbypassrls from pg_roles where rolname in ('postgres','anon','authenticated','service_role','authenticator')"
  → postgres: super=f, bypassrls=t · service_role: super=f, bypassrls=t
  → anon/authenticated/authenticator: super=f, bypassrls=f
```

**Rol efectivo del backend:** `backend/app/core/config.py:17` lee `DATABASE_URL` del entorno;
el `Makefile:6` define la URL local con usuario `postgres` (`DB_URL_LOCAL :=
postgresql+psycopg://postgres:…@127.0.0.1:54322/postgres`; no se imprime la credencial). El rol
`postgres` es **dueño de las tablas** y tiene `rolbypassrls=true` ⇒ **RLS es inerte para la
aplicación**. `service_role` también lo tiene. Además, `grant usage on schema nucleo` se otorga
**solo** a `service_role` (`0004:1886`): `anon`/`authenticated` ni acceden al schema (42501),
independientemente de RLS.

**Clasificación final 🟢:**
| Afirmación | Estado |
|---|---|
| 31/31 tablas `nucleo` con RLS habilitado | 🟢 verificado (comando arriba) |
| Cero políticas RLS en `nucleo` | 🟢 verificado (`pg_policy` 0 filas; `grep create policy` en migraciones → solo `0001:284` en `public.usuarios`) |
| Ninguna tabla con `FORCE ROW LEVEL SECURITY` | 🟢 verificado (`relforcerowsecurity=f` en las 31) |
| RLS como frontera de aislamiento multiempresa | **INEXISTENTE** — el backend corre como dueño/bypass; el aislamiento efectivo vive solo en `X-Empresa-ID` + servicio (INV-T01 ausente, `invariantes.md:73`) |
| Comportamiento para roles `anon`/`authenticated` | cero filas en `public` (salvo `usuarios`) y 42501 en `nucleo` (sin USAGE) — 🟡 inferido del catálogo, no ejecutado con esos roles en esta misión |

---

## 6. Cobertura de auditoría

**Con auditoría `_audit` (AFTER INSERT/UPDATE/DELETE) — 28 tablas 🟢:**
`empresas, usuarios_empresa, clientes, tarifas, centros_costo, ordenes_compra,
ordenes_compra_lineas, tractos, ramplas, choferes, documentos, viajes, reservas_recurso,
viaje_paradas, viaje_checklist, viaje_incidentes, viaje_documentos, pod, precios_diesel,
viaje_gastos, configuracion_costos, facturas_nucleo, factura_viajes, pagos_nucleo,
notas_credito_nucleo, promesas_pago_nucleo, viaje_eventos`

- `viaje_eventos`: audit **solo INSERT** + `trg_eventos_inmutable` (BEFORE UPDATE/DELETE, `0007:131`) — append-only.
- `nucleo.auditoria` se protege a sí misma con `trg_auditoria_no_update` (BEFORE UPDATE/DELETE, `0004:890`); **sin** trigger `BEFORE TRUNCATE` por sentencia (INV-A01 parcial) y `service_role` no tiene `TRUNCATE` (`0004:1887` concede solo select/insert/update).

**Sin auditoría — 3 tablas 🟢:** `cutover_control` (INV-A02 ausente: congelar/descongelar no queda
en `auditoria`), `folio_contador` (incrementos de folio no auditados), `transiciones_viaje`
(catálogo de transiciones).

**`public`:** **cero triggers de auditoría** 🟢 — solo `set_updated_at()` (`0001:235-243`). El
legacy no deja rastro de quién/cuándo cambió qué.

---

## 7. Tipos: dinero y tiempo

**Comandos 🟢:**
```
$ select table_schema,table_name,column_name,data_type from information_schema.columns
  where table_schema in ('nucleo','public') and data_type in ('double precision','real')
  → 0 filas
$ … data_type like 'timestamp%'
  → 100% "timestamp with time zone" (nucleo 72 columnas, public 24). 0 sin time zone.
```
- **Dinero:** todo `numeric` (`numeric(14,2)`/`numeric(16,2)`/`numeric(16,4)`); modelos usan
  `Decimal` (`models.py:55-60`, `backend/app/models/__init__.py:61`). ✅ conforme AGENTS.md §3.10.
- **Eventos:** `timestamptz` en `viajes` (inicio/fin/ventanas de carga y descarga), `pod.fecha_hora`,
  `viaje_eventos.ocurrido_en`, `viaje_paradas.ventana_*`, etc. ✅ AGENTS.md §3.9.
- **Rangos:** `tstzrange` en `viajes.ventana` y `reservas_recurso.ventana`; CHECKs de validez en
  ambos (`ck_viaje_ventana` `0004:666`, `ck_reserva_ventana` `0004:734`). ✅ semiabierto.
- **`date`:** solo vigencias/emisión (`documentos.vence_en`, `tarifas.vigencia_*`,
  `facturas.fecha_emision/vencimiento`, `pagos.fecha`, `viaje_gastos.fecha`, `precios_diesel.fecha`)
  — aceptable según AGENTS.md.
- **Excepción legacy 🔴:** `public.viajes.fecha_inicio/fecha_fin` son `date` para **eventos**
  (granularidad día) — es la raíz de INV-L01/L06 (`invariantes.md:510-528, 608-620`).

---

## 8. Invariantes del catálogo verificados contra el DDL vivo

Re-verificación de `docs/datos/invariantes.md` §1 (35 invariantes) contra la base local:

| ID | Estado en catálogo | Verificación en base viva | Certeza |
|---|---|---|---|
| INV-D04 (3 recursos ⇒ 3 reservas) | impuesto (DDL) | `fn_viaje_reservas` versión 0015 activa (comentario = `0015:240-242`), `trg_viajes_70_reservas` presente, 3 reservas `creado_por='migracion_0015'` | 🟢 |
| INV-D07 (bloqueo no solapa) | impuesto (DDL) | 3 `EXCLUDE` en `pg_constraint` (`0004:744-757`) | 🟢 |
| INV-DOC04 (documentos por viaje) | impuesto (DDL) | `trg_viajes_05_documentos` + `fn_viaje_documentos` presentes | 🟢 |
| INV-R02-01 (solo A5) | impuesto (DDL) | `trg_viajes_03_licencia_a5` + `fn_viaje_licencia_a5` presentes | 🟢 |
| INV-R02-02 (licencia vigente) | impuesto (DDL) | `nucleo.validar_documentos_recurso` presente | 🟢 |
| INV-C03 (sobregiro aprobado) | parcial (DDL) | `ck_oc_sobregiro_*` presentes; **no** hay trigger `fn_oc_sobregiro` (triggers de `ordenes_compra`: solo touch/version/audit) | 🟢 |
| INV-T02 (reserva ↔ viaje misma empresa) | parcial (DDL) | FK `fk_reserva_viaje` simple (`viaje_id` solo) presente; compuesta ausente | 🟢 |
| INV-A01 (auditoría no truncable) | parcial (DDL) | `trg_auditoria_no_update` presente; sin trigger por sentencia; `service_role` sin TRUNCATE (`0004:1887`) | 🟢 |
| INV-D05, INV-D06, INV-C04, INV-C05, INV-DOC03, INV-G04, INV-G05, INV-G06, INV-F01…F07, INV-L01…L06, INV-T01, INV-T03, INV-T04, INV-X01, INV-A02 | ausente / solo servicio | Verificado **sin mecanismo en DB**: 0 políticas RLS; `viaje_gastos` sin trigger de protección ni `no_delete` ni UNIQUE de idempotencia (solo touch/version/audit/costos); `pagos_nucleo`/`notas_credito` sin `_no_delete` ni trigger de saldo con `FOR UPDATE` (solo touch/version/audit/estado); `facturas_nucleo` sin trigger de inmutabilidad; `cutover_control` **sin ningún trigger** (`pg_trigger` → 0 filas); `public` sin triggers de integridad (solo `set_updated_at`) | 🟢 |

**Conclusión:** el catálogo coincide con la base viva. Ningún invariante "impuesto" está
sobre-declarado; ninguno de los ausentes apareció silenciosamente. La única novedad respecto del
catálogo es que **0015/0016/0017 sí están aplicados físicamente** en la base local aunque
`schema_migrations` no los registre.

---

## 9. `public` (legacy) — deriva breve

- **Modelos:** 16 tablas en `backend/app/models/__init__.py` (`Usuario` … `Kpi`); la DB tiene 17
  (`_migraciones` extra, sin modelo). Coinciden las 16 🟢.
- **Drift detectado:** `liquidaciones` tiene `UNIQUE (chofer_id, mes)` en DB que el modelo no
  declara (`__init__.py:226-241`); `kpis` tiene CHECKs `ambito/uso/formato` en DB que el modelo no
  declara (`:276-292`); modelo `FacturaViaje` declara `ondelete="CASCADE"` en `viaje_id` (`:199`)
  pero la DB no tiene cascada en esa FK (solo en `factura_id`); `kpis.reglas_color` usa
  `Column(JSON)` genérico (`:286`) vs `jsonb` en DB; los modelos legacy mapean `datetime` naive
  (`Field(default_factory=datetime.now)`) contra columnas `timestamptz`; `public.viajes` guarda
  eventos en `date`.
- **Integridad/aislamiento:** `public` no tiene `empresa_id` (single-tenant por construcción,
  `invariantes.md:506-508`); 16/17 tablas con RLS habilitado y 0 políticas (salvo
  `public.usuarios` con SELECT `auth.uid()=auth_id`); sin auditoría; `facturas` con
  `UNIQUE (numero_sii, cliente_id)` en vez de `UNIQUE (numero_sii)` (INV-L02); sin CHECK
  `total = neto + iva` (INV-L03).

---

## 10. Riesgos y no verificado

- 🔴 **Causa de la desincronización `schema_migrations` ↔ objetos físicos** no determinable con
  el repo (sin registro de cómo se aplicaron 0015–0017).
- 🟡 No se probó el comportamiento efectivo de los roles `anon`/`authenticated`/`service_role`
  con sentencias reales (solo catálogo): inferido, no ejecutado.
- 🟡 Evidencia de 0018/0019 es solo de datos (podría ser seed); no hay log de aplicación.
- 🔴 No se ejecutó ninguna prueba de los invariantes (misión solo lectura); la deuda de prueba de
  `invariantes.md` §8 sigue vigente.
- La deriva de severidad Alta (viajes/reservas_recurso) es **documental**, no funcional: los
  modelos no crean tablas (`models.py:3-5`), pero quien lea solo `models.py` no ve los EXCLUDE ni
  los CHECK críticos; cualquier `create_all()` accidental los perdería.
- No se leyeron archivos `.env` (permiso denegado correctamente); la evidencia del rol de conexión
  es `Makefile:6` + `config.py:17` + `pg_roles`.

## 11. Autoverificación (AGENTS.md §11)

- [x] Cada invariante citado con mecanismo y estado verificado contra la base viva.
- [x] RLS clasificado con salida de comandos pegada y rol efectivo evidenciado.
- [x] Cada afirmación con `archivo:línea` y marca 🟢/🟡/🔴.
- [x] Solo lectura: sin DDL, sin escrituras, sin `db reset`, sin lectura de `.env`.
- [x] Único archivo tocado: ninguno (sin permiso de escritura en `docs/qa/`; contenido entregado
  por esta vía).
