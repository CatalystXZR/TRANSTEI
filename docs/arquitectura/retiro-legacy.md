# Matriz de retiro del legacy `public` — por módulo, con evidencia

> ## ⚠️ Aviso de vigencia — revisión 3, 2026-10-31
>
> **Este documento ya no describe "qué falta para retirar el código": eso se
> ejecutó.** Las olas A (pantallas), B (4 módulos en el núcleo) y C (11 routers
> borrados) están cerradas. Lo que queda es **retiro de datos (Ola D)** e
> **identidad + cierre de esquema (Ola E)**.
>
> - **Plan y decisiones:** [`adr/ADR-0002-retiro-del-legacy.md`](adr/ADR-0002-retiro-del-legacy.md)
>   **revisión 3**. Donde este documento discrepe, manda el ADR.
> - **Estado de los datos por concepto:** [`fuentes-de-verdad.md`](fuentes-de-verdad.md)
>   revisión 2.
> - **Lo que este documento conserva:** el inventario de las 17 relaciones de
>   `public`, las consultas de medición (aún **no ejecutadas**) y el detalle de
>   qué dato falta migrar por módulo.
>
> **Dueño:** `arquitectura` · **Verificado:** 2026-10-31 (código) / 2026-10-29
> (inventario de datos) · **Método:** lectura estática de routers, pantallas,
> migraciones, scripts y pruebas; informes fechados de las olas. **Sin shell:**
> no ejecuté SQL, `pytest`, `make` ni `git`.
> **Caduca si:** cambia `public`, el cutover, una pantalla del núcleo o se
> responde una `RET-*`.
> **Re-verificar con:**
> `grep -rn "public\." backend/app/` (debe ser 1: `servicio_cutover.py`),
> `ls backend/app/api/routes/` (debe ser solo `auth.py`) y
> `grep -rn "@/lib/api" frontend/src` (debe ser 0).

---

## 0. Cómo leer esta matriz (rev. 3)

| Marca | Significado |
|---|---|
| 🟢 | Leído en archivo, con `archivo:línea` |
| 🟡 | Deducido de código o dato de un informe fechado; se indica qué lo confirmaría |
| 🔴 | No determinable en esta sesión; se indica la consulta/comando exacto |
| **C1 / C2 / C3** | Compuertas del ADR-0002 §4.2 (paridad con prueba / cero consumidores / datos migrados) |
| **G0** | Precondición transversal del ADR-0002 §4.3 |
| **S/M/L** | Esfuerzo relativo: S ≤ 2 días-agente · M ≤ 1 semana · L > 1 semana |

> **Cambio respecto de la rev. 2:** las puertas `P1…P4` ya no existen; fueron
> reemplazadas por C1–C3 + G0 en el ADR rev. 2. Esta revisión alinea el
> vocabulario y elimina toda referencia a `P1…P4`.

**Regla de la columna "datos":** "volumen" nunca es una cifra inventada. Cuando
no hay medición, la celda dice 🔴 y remite a la consulta de §5.

---

## 1. Inventario de `public` (17 relaciones) y estado tras A–C

Ninguna migración borró tablas de `public` (`grep "drop table public"` → 0; los
`drop table` que aparecen están en comentarios de rollback de `0023`–`0026`). 🟢

| Tabla | Migración | Qué es | Estado tras A–C | Clase |
|---|---|---|---|---|
| `usuarios` | `0001:36-45` | Espejo de `auth.users` con rol global; **identidad del backend legacy** (`api/deps.py:15-17`) y destino del trigger `handle_new_user` (`0001:248-262`) | **VIVA y escrita en producción** por el trigger en cada alta | **Datos de runtime** — bloquea G0.1 |
| `clientes` | `0001:47-58` | Maestro duplicado de `nucleo.clientes` | Sin escritor de aplicación; seed local (`seed_local.py:235`) | Dato de negocio (histórico) |
| `choferes` | `0001:60-70` | Maestro duplicado; `sueldo_base` y `porcentaje_produccion` | Sin escritor de aplicación; seed (`seed_local.py:337`) | Dato de negocio |
| `tractos` | `0001:72-84` | Maestro duplicado; **sin** tara/peso/capacidad que `nucleo` exige `NOT NULL` | Sin escritor de aplicación; seed (`seed_local.py:270`) | Dato de negocio |
| `ramplas` | `0001:86-94` | Maestro duplicado; **sin** capacidad | Sin escritor de aplicación; seed (`seed_local.py:305`) | Dato de negocio |
| `viajes` | `0001:97-112` | Histórico operativo; estados `programado/en_ruta/finalizado/facturado` | Sin escritor de aplicación; **leído** por `servicio_cutover.py:97` y `cutover_legacy.py` | Dato de negocio |
| `gastos_viaje` | `0001:114-125` | Histórico de gastos + `respaldo_url` a Storage | Sin escritor de aplicación | Dato financiero |
| `facturas` | `0001:127-143` | Documentos emitidos; `unique (numero_sii, cliente_id)` | Sin escritor de aplicación | **Dato financiero/tributario** |
| `factura_viaje` | `0001:145-149` | Vínculo factura↔viaje | Sin escritor de aplicación | Dato financiero |
| `anticipos_chofer` | `0001:151-159` | Anticipos de sueldo | Sin escritor de aplicación | **Dato laboral** |
| `ajustes_liquidacion` | `0001:161-169` | Bonos/descuentos | Sin escritor de aplicación | **Dato laboral** |
| `liquidaciones` | `0001:171-186` | Liquidaciones; `unique (chofer_id, mes)` | Sin escritor de aplicación | **Dato laboral** |
| `pautas_mantenimiento` | `0001:189-196` | Pauta por km | Sin escritor de aplicación | Configuración operativa |
| `mantenimientos` | `0001:199-209` | Historial por tracto | Sin escritor de aplicación | Dato operativo |
| `configuracion` | `0001:212-215` | 4 claves, incluida **`iva_porcentaje`** | **Sin lector de producción**: `settings_db.py` no tiene consumidor; el IVA se lee de `nucleo` | **Configuración tributaria** (histórico) |
| `kpis` | `0003:5-20` | KPIs por fórmula | Sin lector: `kpi_engine.py` se eliminó | Configuración de producto (histórico) |
| `_migraciones` | `0002:6-9` | Trazabilidad de migraciones aplicadas | Metadato | **No se borra** |

**RLS:** todas las tablas tienen RLS habilitado y **una sola política** en todo el
esquema (`usuarios`, `0001:284-285`). No es aislamiento: es "solo `service_role`
pasa". 🟢

**Lectura correcta del inventario:** "sin escritor de aplicación" **no** significa
"sin datos" ni "sin uso". Significa que ningún router, servicio o tarea del
backend escribe esas tablas. El histórico sigue ahí y es la única copia hasta que
la Ola D lo migre.

---

## 2. Matriz por módulo — estado post Olas A/B/C

| # | Router legacy | Estado del router | Pantalla(s) original(es) | Estado de la pantalla | Destino en `nucleo` | Dato que falta migrar | Compuerta que queda | Esf. |
|---|---|---|---|---|---|---|---|---|
| **M01** | `auth` → `GET /auth/me` | **VIVO** (`auth.py:12-28`) | Todas (bootstrap) | shell sobre `/auth/me` | Membresía/rol en `nucleo.usuarios_empresa`; **sin endpoint de perfil** | `public.usuarios` · 🔴 §5.1 | C1, C2, C3, **G0.1** | M |
| **M02** | `catalogos` | **RETIRADO** (404) | `/clientes`, `/choferes`, `/flota` | 308 → `/maestros` | `api_maestros.py` (CRUD); **import CSV no** | `clientes`, `choferes`, `tractos`, `ramplas` · 🔴 §5.2 | C3 (tara/capacidad, import) | M |
| **M03** | `viajes` | **RETIRADO** | `/viajes`, `/viajes/[id]` | 308 → `/despacho`, `/expediente` | `api.py`, `api_expediente.py`, `api_conductor.py` | `viajes` abiertos y cerrados · 🔴 §5.3 | C3 (histórico) | L |
| **M04** | `gastos` | **RETIRADO** | `/viajes/[id]` | 308 → `/expediente` | `api_gastos.py` (superior: aprobación, storage) | `gastos_viaje` + objetos `respaldos` · 🔴 §5.4 | C3 (archivos) | M/L |
| **M05** | `dashboard` | **RETIRADO** | `/dashboard` | 308 → `/tablero` | `api_alertas.py` (`TableroOut`) | Sin tablas propias (lee viajes/facturas/gastos) · 🔴 §5.3/§5.5 | C1 (totales de dinero, **RET-06**), C3 | S/M |
| **M06** | `facturas` | **RETIRADO** | `/facturacion` | 308 → `/cobranza` | `api_facturacion.py` (pagos, NC, aging) | `facturas` + `factura_viaje` · 🔴 §5.5 | C3 (dinero) | L |
| **M07** | `finanzas` | **RETIRADO** | `/facturacion`, `/cobranzas`, `/iva` | 308 / reescrita | fletes→`viajes-facturables`; cobranzas→aging; IVA→`api_iva.py` | Sin tablas propias · 🔴 §5.5 | C3 (dinero) | S/L |
| **M08** | `mantenimiento` | **RETIRADO** | `/mantenimiento` | **Reescrita** contra `lib/nucleo.ts` | `0024` + `api_mantenimiento.py` | `pautas_mantenimiento`, `mantenimientos` · 🔴 §5.7 | C3 | M/L |
| **M09** | `liquidaciones` | **RETIRADO** | `/liquidaciones` | **Reescrita** contra `lib/nucleo.ts` | `0025` + `api_nomina.py` | `liquidaciones`, `anticipos_chofer`, `ajustes_liquidacion` · 🔴 §5.6 | C3, **RET-07** | L |
| **M10** | `configuracion` | **RETIRADO** | `/configuracion`, `/facturacion` | **Reescrita** contra `lib/nucleo.ts` | `0026` + `api_iva.py` | `public.configuracion` · 🔴 §5.8 | C3, **G0.3**, **RET-04** | S |
| **M11** | `export` | **RETIRADO** | viajes/facturación/liquidaciones/clientes/choferes | 308 o reescrita | `api_export.py` (export); **import no** | Sin tablas propias; el import escribía `public.clientes/choferes` | **RET-10** (import) | S/M |
| **M12** | `kpis` | **RETIRADO** | `/kpis`, `/dashboard` | 308 → `/rentabilidad`, `/tablero` | rentabilidad fija (`api_rentabilidad.py`, `servicio_rentabilidad.py`) | `public.kpis` (4 filas) · 🔴 §5.8 | **RET-05**, C3 | M |

**Lectura de la tabla:** **11 de 12** routers retirados; queda solo identidad. Las
13 pantallas están en el núcleo (9 redirigen, 4 reescritas). **Ningún módulo
cierra C3**: los datos siguen en `public`.

---

## 3. Dependencias entre módulos legacy — ya no describen el runtime

El grafo de la rev. 2 (`catalogos` → `viajes` → `gastos`/`finanzas`/`export`,
`configuracion` → `finanzas`/`mantenimiento`/`dashboard`/`kpi_engine`) describía
**cuando los routers legacy estaban montados**. Tras la Ola C:

- No hay routers legacy de negocio que se importen entre sí: los archivos no
  existen y `include_router` solo conserva `auth`.
- Las dependencias de datos entre tablas de `public` siguen existiendo **como
  histórico** (`factura_viaje` → `viajes`, `liquidaciones` → `choferes`), pero sin
  escritores de aplicación.
- El grafo **ya no sirve para ordenar retiros de código**; sirve para ordenar
  **importaciones de datos** en la Ola D, que deben respetar el orden de FKs
  lógicas: maestros → viajes → gastos/facturas → nómina/mantenimiento.

> **No se conserva el diagrama mermaid de la rev. 2 como estado vigente.** Un
> diagrama de routers que ya no existen induce a error. El orden de la Ola D está
> en §6 y en el ADR §6.6.

---

## 4. Dependencias transversales (las que sobreviven a A–C)

| # | Dependencia | Evidencia | Qué rompe si se borra hoy | Estado | Se cierra con |
|---|---|---|---|---|---|
| T1 | Identidad `public.usuarios` | `api/deps.py:15-17`; trigger `0001:248-262`; `auth-context` | Login sin perfil, `/auth/me` 401, alta de usuarios rota, **todas** las pantallas; el seed del segundo tenant escribe ahí (`seed_segundo_tenant.py:79`) | **ABIERTA** | G0.1 / Ola E |
| T2 | Gate `LEGACY_SOLO_TEI` | `main.py:157-175,217-302` | Ya no protege negocio (no hay rutas); sigue distinguiendo tenants sobre rutas inexistentes (403 vs 404) | **ABIERTA** | E.3 (retirar con el middleware) |
| T3 | Lectura cruzada `nucleo → public.viajes` | `servicio_cutover.py:97` | `GET /nucleo/cutover/estado` falla (500 o 0) | **ABIERTA** (1 lectura) | G0.2 (mover el conteo al núcleo) |
| T4 | Parámetro tributario | `servicio_iva.py:44-51` lee `nucleo.config_vigente`; **`schemas.py:1543` + `servicio_facturacion.py:544` aceptan `tasa_iva` del request** | Dos documentos pueden usar tasas distintas | **PARCIAL** | RET-04: la tasa debe venir del servidor |
| T5 | Escalada de rol legacy | Los roles globales de `public.usuarios` (`admin/operacion/contabilidad`) siguen en `/auth/me` y en `navigation.ts` | La UI sigue filtrando por rol legacy, no por rol de empresa del núcleo | **PARCIAL** | Ola E (G0.1) + `permisos` del núcleo |
| T6 | Flag de cutover sin dueño ni auditoría | `0014`; `servicio_cutover.py`; `main.py:326-351` | Un admin congela el sistema sin rastro; con rutas inexistentes solo altera el código de respuesta | **ABIERTA** | E.3 / D-05 de ADR-0001 |
| **T7** | **Migraciones `0024`–`0026` untracked** | `docs/datos/catalogo-migraciones.md:205-207` | Un clon de `HEAD` no tiene el esquema de la Ola B | **ABIERTA** (proceso) | `orquestador`: commit de las 26 migraciones |

---

## 5. Consultas de medición (🔴 no ejecutadas en esta revisión)

Todas son `SELECT`. Se ejecutan contra una **copia**, nunca contra producción, y la
salida se archiva con fecha y hash. Mientras no se ejecuten, toda cifra de volumen
en este documento es 🔴.

### 5.0 Estado de la Ola 0 (línea base)

| Medición | Estado | Dónde |
|---|---|---|
| Conteo y suma por tabla de `public` | ⛔ No ejecutado | §5.1–§5.8 |
| Consulta de reconciliación `public` ↔ `nucleo` | ⛔ No existe | Debe crearse en D |
| `make restore-drill` con comparación | ⛔ No ejecutado | `RET-09` |
| Estado fechado de `nucleo.cutover_control` | ⛔ No registrado en esta fase | §5.9 |

### 5.1 Conteo total de `public`

```sql
select 'public.usuarios' t, count(*) n from public.usuarios
union all select 'public.clientes', count(*) from public.clientes
union all select 'public.choferes', count(*) from public.choferes
union all select 'public.tractos', count(*) from public.tractos
union all select 'public.ramplas', count(*) from public.ramplas
union all select 'public.viajes', count(*) from public.viajes
union all select 'public.gastos_viaje', count(*) from public.gastos_viaje
union all select 'public.facturas', count(*) from public.facturas
union all select 'public.factura_viaje', count(*) from public.factura_viaje
union all select 'public.liquidaciones', count(*) from public.liquidaciones
union all select 'public.anticipos_chofer', count(*) from public.anticipos_chofer
union all select 'public.ajustes_liquidacion', count(*) from public.ajustes_liquidacion
union all select 'public.pautas_mantenimiento', count(*) from public.pautas_mantenimiento
union all select 'public.mantenimientos', count(*) from public.mantenimientos
union all select 'public.configuracion', count(*) from public.configuracion
union all select 'public.kpis', count(*) from public.kpis
union all select 'public._migraciones', count(*) from public._migraciones
order by 1;
```

**Referencia local (no medición):** el seed inserta 8 usuarios
(`seed_local.py:91-100`), 3 clientes (`:214-218`), 3 tractos (`:245-249`),
3 ramplas (`:283-287`) y 3 choferes (`:314-318`). No inserta viajes, facturas,
gastos ni liquidaciones en `public`. Es decir: **en local esas tablas solo tienen
lo que dejaron las pruebas** y no sirven como estimación de producción. 🔴

### 5.2 Maestros (M02)

```sql
-- Duplicados entre esquemas (los que se perderían si se borra public)
select count(*) from public.clientes c
 where not exists (select 1 from nucleo.clientes n
                    where upper(regexp_replace(n.rut,'[^0-9K]','','g'))
                        = upper(regexp_replace(c.rut,'[^0-9K]','','g')));

select count(*) from public.choferes c
 where not exists (select 1 from nucleo.choferes n
                    where upper(regexp_replace(n.rut,'[^0-9K]','','g'))
                        = upper(regexp_replace(c.rut,'[^0-9K]','','g')));

select count(*) from public.tractos t
 where not exists (select 1 from nucleo.tractos n
                    where upper(regexp_replace(n.patente,'[^A-Z0-9]','','g'))
                        = upper(regexp_replace(t.patente,'[^A-Z0-9]','','g')));

select count(*) from public.ramplas r
 where not exists (select 1 from nucleo.ramplas n
                    where upper(regexp_replace(n.patente,'[^A-Z0-9]','','g'))
                        = upper(regexp_replace(r.patente,'[^A-Z0-9]','','g')));
```

**Hallazgo bloqueante para M02:** `public.tractos` (`0001:72-84`) y
`public.ramplas` (`0001:86-94`) **no tienen** peso bruto, tara ni capacidad;
`nucleo.tractos` los exige `NOT NULL` con `CHECK` de coherencia
(`0004:201-203,222-223`) y `nucleo.ramplas.capacidad_carga_kg` también
(`0004:244`). El cutover actual **inventa** esos valores: `39000 / 9000 / 30000`
para todo tracto (`cutover_legacy.py:193`) y `30000` para toda rampla (`:251`).
Esos números alimentan la validación de capacidad y sobrepeso
(`0004:1198-1225`). **Migrar maestros con capacidad inventada deja la garantía de
sobrepeso calculando contra datos falsos.** Cerrar C3 exige que el dueño/taller
entregue tara y capacidad reales (`RET-11`).

### 5.3 Viajes (M03, M05)

```sql
select estado, count(*) n, coalesce(sum(valor_flete_neto),0) flete
  from public.viajes group by 1 order by 1;

-- Viajes que el cutover actual NO migra (cerrados) y que sostienen el histórico
select count(*) from public.viajes where estado in ('finalizado','facturado');

-- Viajes abiertos (los únicos que el cutover sí migra)
select count(*) from public.viajes
 where estado in ('programado','en_ruta');
```

### 5.4 Gastos y archivos (M04)

```sql
select count(*) n, coalesce(sum(monto),0) total,
       count(*) filter (where respaldo_url is not null) con_respaldo
  from public.gastos_viaje;
```

Los archivos viven en el bucket `respaldos` (`0002:19`), con ruta histórica
`gastos/{viaje_id}/{uuid}{ext}` (construida por el router `gastos.py`, hoy
borrado). **Contar filas no cuenta archivos**: C3 exige listar el bucket y
comparar con `respaldo_url`.

### 5.5 Facturación y cobranza (M06, M07)

```sql
select estado, count(*) n, coalesce(sum(total),0) total
  from public.facturas group by 1 order by 1;

select count(*) from public.factura_viaje fv
 where not exists (select 1 from public.viajes v where v.id = fv.viaje_id);

-- Facturas "pagadas" sin registro de pago (defecto que el legacy tenía)
select count(*) from public.facturas where estado = 'pagada' and fecha_pago is null;
```

La última consulta mide el tamaño del defecto del `PATCH estado=pagada` legacy:
marcaba pagada sin exigir monto ni medio de pago, mientras el núcleo exige
`POST /nucleo/cobranza/facturas/{id}/pagos`. Ese endpoint **ya no existe en el
legacy**; la consulta sirve para decidir qué hacer con esos registros en D.2.

### 5.6 Liquidaciones (M09)

```sql
select mes, count(*) n, coalesce(sum(total_liquido),0) liquido
  from public.liquidaciones group by 1 order by 1;
select count(*) from public.liquidaciones where estado = 'emitida';
select count(*) n, coalesce(sum(monto),0) from public.anticipos_chofer;
select tipo, count(*) n, coalesce(sum(monto),0) from public.ajustes_liquidacion group by 1;
```

**Destino listo:** `nucleo.liquidaciones`, `nucleo.anticipos_chofer` y
`nucleo.ajustes_liquidacion` existen (`0025`). **Nota de regla:** la comisión
legacy se calculaba sobre viajes `finalizado`/`facturado`, es decir **sobre flete
no necesariamente cobrado**. La implementación del núcleo congela montos al
emitir, pero la base de comisión (devengado vs cobrado) sigue en `D-01`
(`docs/negocio/preguntas.md`). Migrar los números sin decidir la regla congela un
criterio posiblemente incorrecto.

### 5.7 Mantenimiento (M08)

```sql
select count(*) from public.pautas_mantenimiento where activo;
select count(*) n, coalesce(sum(costo),0) costo, max(km) from public.mantenimientos;
select count(*) from public.tractos where km_actual is null or km_actual = 0;
```

`nucleo.tractos.km_actual` es `numeric(12,1)` (`0004:205`) y
`public.tractos.km_actual` es `integer` (`0001:78`). La conversión es trivial; el
problema es que el `km_actual` legacy se actualizaba al registrar una mantención
y en el núcleo lo hace el trigger `odometro` (`0024`). La migración no debe
"re-ejecutar" el trigger: debe fijar el km final, no la secuencia histórica.

### 5.8 Configuración y KPIs (M10, M12)

```sql
select clave, valor from public.configuracion order by 1;
select id, nombre, uso, activo from public.kpis order by orden;
```

**Cambio respecto de la rev. 2:** `iva_porcentaje` **ya no se lee desde
`public.configuracion`**. El módulo de IVA lee
`nucleo.config_vigente(empresa, 'iva_porcentaje')`
(`backend/app/nucleo/servicio_iva.py:15-16,44-51`) y el seed de `0026` crea
`iva_porcentaje = 19` por empresa (`docs/datos/retiro-legacy-modelo.md:27,112`).
`settings_db.get_config*` (`core/settings_db.py:9-19`) quedó **sin consumidor de
producción**.

**Residual tributario:** la creación de factura sigue aceptando `tasa_iva` desde
el request (`schemas.py:1543`; `servicio_facturacion.py:544`). Es una segunda
fuente dentro del núcleo. **No es basura: es una regla tributaria sin fuente
única** (`RET-04` / `P-09`, `AGENTS.md` §3.15).

### 5.9 Flag de cutover

```sql
select legacy_escritura_congelada, actualizado_en, actualizado_por
  from nucleo.cutover_control;
```

Registrar la salida con fecha antes de cualquier ventana de D.

### 5.10 Destinos de la Ola B (para reconciliar en D.3/D.4/D.5)

```sql
select count(*) from nucleo.pautas_mantenimiento;
select count(*) from nucleo.mantenimientos;
select count(*) from nucleo.liquidaciones;
select count(*) from nucleo.anticipos_chofer;
select count(*) from nucleo.ajustes_liquidacion;
select clave, valor, vigente_desde, vigente_hasta from nucleo.configuracion_empresa;
```

---

## 6. Orden de retiro — estado real

La numeración de 10 olas de la rev. 2 quedó obsoleta. El plan vigente es A–E
(ADR §6).

| Ola | Qué | Estado | Evidencia |
|---|---|---|---|
| **A** | 9 pantallas duplicadas → 308 | ✅ **Ejecutada 2026-10-31** | `frontend/src/app/(retiradas)/`; `docs/frontend/f2-ola-a-retiro.md` |
| **B** | 4 módulos sin equivalente construidos en `nucleo` | ✅ **Ejecutada 2026-10-31** | `0024`–`0026`; `api_mantenimiento.py`, `api_nomina.py`, `api_iva.py`, `api_export.py`; pantallas reescritas |
| **C** | 11 routers legacy borrados | ✅ **Ejecutada 2026-10-31** | `api/routes/` solo `auth.py`; 404 probado; `f2-ola-c-retiro-routers.md` |
| **D** | Migración de datos (D-2) | ⛔ **Pendiente** | Bloqueada por `RET-01` |
| **E** | Identidad y `DROP` | ⛔ **Pendiente** | Bloqueada por D + `RET-02` + `RET-09` |

**Orden dentro de D (por FKs lógicas):**

1. **D.1** maestros → viajes → gastos/archivos (con `RET-11` resuelta para
   tractos/ramplas).
2. **D.2** facturas → `factura_viaje` → pagos.
3. **D.3** nómina (`0025`).
4. **D.4** mantenimiento (`0024`).
5. **D.5** configuración (`0026`) y KPIs (destino a decidir, `RET-05`).

**Regla de secuencia vigente:** D no empieza hasta que la Ola 0 tenga el censo y
el restore drill. Cada sub-ola termina con una consulta de reconciliación que
devuelve 0 filas y una salida fechada.

---

## 7. Preguntas abiertas que esta matriz no responde

| ID | Pregunta | Destinatario | Estado |
|---|---|---|---|
| Q1 | ¿Cuántas filas y cuánto dinero hay realmente en cada tabla de `public`? (consultas §5) | `datos` (solo lectura, sobre copia) | ⛔ Abierta |
| Q2 | Tara, peso bruto y capacidad reales por tracto y rampla, para no migrar maestros con `39000/9000/30000` inventados | Dueño + taller (`RET-11`) | ⛔ Abierta |
| Q3 | ¿Cuántos archivos hay en el bucket `respaldos` y cuántos `respaldo_url` apuntan a objetos existentes? | `datos` + `auditor-seguridad` | ⛔ Abierta |
| Q4 | ¿El histórico de viajes cerrados se migra a `nucleo` o se conserva en `public` como archivo? | Dueño + contador (`RET-02`) | ⛔ Abierta |
| Q5 | ¿Se acepta que el tablero no muestre los totales de dinero del dashboard legacy? | Dueño (`RET-06`) | ⛔ Abierta |
| **Q6** | ¿Se ratifica el retiro del import CSV y del motor de KPIs por fórmula? | Dueño (`RET-10`, `RET-05`) | ⛔ Abierta |
| **Q7** | ¿Se acepta la desviación de secuencia C→D y la migración idempotente con ventana congelada? | Dueño + `datos` (`RET-12`) | ⛔ Abierta |

---

## 8. Lo que esta matriz **no** afirma

- **No** afirma que `public` esté retirado: el esquema, las tablas y el histórico
  siguen existiendo. Lo retirado es el **código de negocio**.
- **No** afirma que ningún módulo esté "migrado": **C3 está abierta en los 12**.
  Lo verificado es que la aplicación ya no escribe ni lee `public` (salvo
  identidad y el conteo del cutover).
- **No** afirma volúmenes: §5 sigue sin ejecutar.
- **No** afirma que las pantallas del núcleo sean equivalentes en todos los
  detalles: la Ola B implementó paridad de acciones y el informe de `frontend`
  declara 🔴 que no se ejecutó un flujo autenticado real
  (`docs/frontend/f2-ola-b-pantallas.md:276`).
- **No** propone una tercera fuente de verdad: no hay tabla de reconciliación,
  solo consultas (§5) y scripts de migración por concepto.

---

## 9. Lo que **no** se retiró y por qué (resumen operativo)

| Objeto | Por qué sigue | Quién lo retira |
|---|---|---|
| 17 relaciones de `public` | Histórico no migrado; borrar sin backup es irreversible | Ola D + `RET-02` + `RET-09` |
| `public.usuarios` + trigger `handle_new_user` | Identidad de todos los tenants; `/auth/me` y `deps.py` la leen; el trigger escribe en cada alta | Ola E (G0.1) |
| Gate `LEGACY_SOLO_TEI` | Frontera de acceso y pruebas del segundo tenant; hoy solo actúa sobre rutas inexistentes | E.3 |
| Middleware de congelamiento + `cutover_control` | Interruptor de escrituras para la ventana de D | E.3 |
| Modelos legacy (`app/models/`) | Los usan `auth`, `deps`, `schemas`, `settings_db` | E.4 |
| `core/settings_db.py` | Código muerto en producción, aún citado por una prueba | E.4 |
| Seeds y `cutover_legacy.py` | Son la herramienta de D; los seeds reproducen el entorno local | Después de D/E |
| `public.configuracion`, `public.kpis` | Sin lector, con datos históricos | `RET-02` |
| Migraciones `0001`–`0026` | Forward-only; trazabilidad del esquema | Nunca |

---

## 10. Documentos que citan archivos borrados (a corregir por su dueño)

| Documento | Cita inválida | Dueño | Acción |
|---|---|---|---|
| `docs/estado.md` | 23 migraciones, 40 tablas, 27 routers (12 legacy), módulos legacy "en uso", `routes/*`, `kpi_engine` | `orquestador` | Reescribir; es el único autorizado a cifras volátiles |
| `docs/seguridad/hallazgos.md` | `routes/liquidaciones.py`, `routes/viajes.py`, `routes/facturas.py`, `routes/export.py`, `test_reglas_negocio.py` | `auditor-seguridad` | Aviso de archivo retirado + revalidar SEC-002/SEC-010 |
| `docs/seguridad/f1-ola2-*.md` | `routes/export.py`, `routes/gastos.py` | `auditor-seguridad` | Aviso de informe histórico |
| `docs/qa/matriz-trazabilidad.md` | R-01 en `liquidaciones.py`; `test_reglas_negocio.py`, `test_flujos_criticos.py` | `qa` | Re-mapear R-01 a `0025`/`servicio_nomina.py` |
| `docs/qa/linea-base.md` | `test_kpi_engine.py`, `test_reglas_negocio.py`, conteos 52/67 | `qa` | Nueva línea base 128/405 |
| `docs/qa/informes/f0-*.md`, `f1-*.md` | `routes/*`, `kpi_engine.py` | `qa` | Aviso histórico; no reescribir |
| `docs/negocio/catalogo-reglas.md` | R-01 y reglas con fuente en `routes/liquidaciones.py`, `mantenimiento.py`, `configuracion.py`, `export.py` | `negocio-finanzas` | Re-apuntar a `servicio_*` del núcleo |
| `docs/negocio/{implementacion,contexto,kpis,preguntas}.md` | `routes/liquidaciones.py`, `viajes.py`, `facturas.py`, `dashboard.py` | `negocio-finanzas` | Re-apuntar; marcar `D-01`/`P-09` abiertas |
| `docs/backend/contratos/liquidaciones-comision-r01.md` | `routes/liquidaciones.py` (ya tiene aviso) | `backend` | Completar re-mapeo a `servicio_nomina.py` |
| `docs/datos/invariantes.md` | `api/routes/gastos.py` | `datos` | Re-apuntar a `servicio_gastos.py`/`api_gastos.py` |
| `docs/mapa-sistema.md` | `lib/api.ts` vigente | `arquitectura` | Reescritura lista 2026-11-12 (`docs/arquitectura/handoff-mapa-sistema-2026-11-12.md`); aplicación sobre `docs/mapa-sistema.md` pendiente de permiso de edición (ver §11) |
| `docs/arquitectura/modulos.md` | 12 routers legacy, 13 pantallas legacy | `arquitectura` | Archivado 2026-11-12 a `docs/_archivo/modulos.md`; el `git mv` físico requiere shell, denegado a esta sesión (ver §11) |
| `docs/arquitectura/deuda.md` | D-01/D-04/D-06/D-09/D-15/D-16 con `routes/*` | `arquitectura` | Aviso + revisión de filas |
| `docs/arquitectura/matriz-plan-vs-codigo.md` | `routes/viajes.py`, `gastos.py`, `facturas.py`, `liquidaciones.py`, `mantenimiento.py` | `arquitectura` | Re-apuntar a servicios del núcleo |
| `docs/arquitectura/destino-modular.md` | `viajes.py`, `gastos.py`, `facturas.py` como escritores | `arquitectura` | Actualizar reparto de escrituras |
| `docs/desarrollo/guia.md` | `lib/api.ts` vigente | `orquestador` | Actualizar tabla de capas |
| `docs/orquestacion/registro.md` | `routes/*` en fases previas | `orquestador` | Añadir entrada de Olas B/C; no reescribir pasado |
| `docs/frontend/f2-tenant2-navegacion.md` | `lib/api.ts`, 12 pantallas legacy | `frontend` | Aviso de superado |
| `docs/PLAN_DESARROLLO.md`, `docs/_archivo/**` | `api.ts`, routers legacy | — | Histórico: no citar como estado |

---

## 11. Cierre (2026-11-12)

La matriz de arriba (rev. 3, 2026-10-31) describe el estado **anterior** al cierre.
Lo que pasó después, con evidencia fechada:

- **Ola D ejecutada (2026-11-01, base local):** cutover idempotente
  (`pautas_migradas: 6`; segunda corrida 0), maestros 3/3, 0 viajes legacy
  pendientes. Evidencia: `docs/_archivo/cutover-ejecutado-2026-11-01.md`;
  `docs/estado.md` §4 ("Cutover ejecutable ⚪ superado: `public` fue retirado
  (0028) y la Ola D ejecutó el cutover local").
- **`public` retirado físicamente (2026-11-01):** `supabase/migrations/0028_retiro_public.sql`
  borró las 17 tablas, los 8 enums, las 2 funciones y el trigger
  `on_auth_user_created` de `auth.users` (`0028:6-27`). El esquema se conserva
  **vacío** (sin `DROP SCHEMA`; `0028:75-78`). `docs/estado.md` §3: 0 tablas.
- **Identidad cerrada (Ola E):** `/auth/me` resuelve desde el JWT de Supabase y
  `nucleo.usuarios_empresa`, sin leer `public.usuarios`
  (`backend/app/api/routes/auth.py:13-14`; `backend/app/api/deps.py:4-8,96`).
- **Código legacy/cutover eliminado del repo (2026-11-12):** las 9 páginas
  `(retiradas)` y `(app)/cutover` borradas; el middleware
  `congelar_escritura_legacy` retirado de `main.py`; `api_cutover` desmontado de
  `router.py` (comentario "Retiro legacy completado (Ola E, 2026-11)",
  `router.py:3-5`); `scripts/cutover_legacy.py` eliminado.
  **Residual en retiro:** `backend/app/nucleo/servicio_cutover.py` y
  `api_cutover.py` siguen en disco sin importadores de aplicación (solo tests
  los referencian); su borrado está en curso.
- **Los comandos de re-verificación del encabezado quedaron obsoletos:**
  - `grep -rn "public\." backend/app/`: ya no aplica — `public` no existe; el
    único lector era `servicio_cutover.py` (en retiro).
  - `ls backend/app/api/routes/`: sigue siendo solo `auth.py` (🟢 2026-11-12).
  - `grep -rn "@/lib/api" frontend/src`: obsoleto — `api.ts` no existe
    (🟢 0 coincidencias, 2026-11-12).
  - Las consultas §5 contra `public.*` fallan con `42P01`: el histórico vive hoy
    en `nucleo` (lo que migró la Ola D) o en el backup P0 de `0028`
    (`backups/cutover_pre_20261101_115202.sql`).
- **Estado vigente:** `docs/estado.md` (único autorizado a cifras volátiles).
  Este documento queda como **registro histórico** de la matriz de retiro: su
  inventario §1–§2 describe `public` tal como era **antes** de `0028`, no como
  existe hoy.
