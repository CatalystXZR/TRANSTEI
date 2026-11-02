# Catálogo de migraciones — `supabase/migrations/0001`–`0028`

> **Pregunta que responde:** ¿qué hace cada migración, cuánto riesgo tiene y está aplicada?
> **Dueño:** agente `datos` · **Verificado:** 2026-10-29 (cuerpo) · 2026-10-30 (`0020`, `0021`, `0022` y `0023`, catálogo de `tei_test`) · **2026-11-01 (`0027`, `0028`: aplicadas en local y tras `make db-reset`)** · **Método:** lectura de DDL + `git` + `psql`
> **Caduca si:** se agrega, edita o reordena una migración, o se aplica alguna.
> **Re-verificar con:** `ls supabase/migrations/` · `git ls-tree HEAD supabase/migrations/` · `git status --short supabase/migrations/`

---

## 0. Cómo leer este catálogo

1. **"Aplicada en base" es 🔴 en 0001–0019.** No hubo acceso a PostgreSQL en esa
   sesión. Lo único que se afirma es que **el archivo existe en disco** y qué
   contiene. Que el DDL esté en el repo no significa que esté en vigor.
   **Excepción fechada:** `0020` se aplicó y probó en el clon desechable
   `tei_test` el 2026-10-30 (🟡, ver la fila y `docs/datos/rls-multiempresa.md`);
   en la base de la app sigue 🔴.
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
| `0020_rls_multiempresa.sql` | INV-T01: aislamiento por empresa impuesto en PostgreSQL | rol `tei_app` (NOBYPASSRLS, sin contraseña), `nucleo.ctx_empresa/ctx_auth_id/empresas_del_usuario`, 35 políticas en 31 tablas, `FORCE RLS`, GRANTs mínimos | **Alto** (aislamiento multiempresa; inerte hasta cambiar el rol de conexión) | untracked (`??`) | 🟡 solo `tei_test` (2026-10-30) |
| `0021_agente_whatsapp.sql` | Persistencia del módulo agente WhatsApp (F2.5/F2.6, ADR-0003/0004): contactos, ACL, conversaciones, mensajes, solicitudes, hoja de ruta, R-04 y auditoría de consultas | **ADD-only:** 8 tablas (`contactos_whatsapp`…`auditoria_consultas_agente`), columna `viajes.id_comercial_flete` + `CHECK` + `UNIQUE` parcial, 8 `enum`, 5 funciones, 25 triggers, 32 índices en las tablas nuevas, 9 políticas RLS con `ENABLE`+`FORCE`, GRANTs a `tei_app`; única excepción estructural: `UNIQUE (empresa_id, id)` en `usuarios_empresa` (habilita FKs compuestas) | **Alto** (identidad, aislamiento, idempotencia del webhook, numeración comercial; módulo apagado) | untracked (`??`) | 🟡 solo `tei_test` (2026-10-30, 14/14 smoke) |
| `0022_agente_whatsapp_endurecimiento.sql` | Cerrar en la base 4 defectos verificados de `0021` (D2, D3, D5, D9 de `docs/datos/agente-esquema.md` §8): ID comercial inmutable, contador monótono no decreciente, máquina de estados + `payload` inmutable de `hoja_ruta`, y tope de 5 dígitos fail-closed | 3 funciones de trigger + 3 triggers (`trg_contador_10_no_retrocede`, `trg_viajes_10_id_comercial_inmutable`, `trg_hoja_ruta_10_transicion`) y `create or replace` de `obtener_siguiente_id_comercial_flete` con el tope. **Cero cambios de tablas, columnas, índices, políticas o datos** | **Alto** (R-04: numeración comercial, identidad inmutable y estados; módulo apagado) | untracked (`??`) | 🟡 solo `tei_test` (2026-10-30); rollback probado con `0022_99` (2026-10-30) |
| `0023_modulos_empresa.sql` | Llave 1 del gate del conector: flag de módulo activo **por empresa** (`nucleo.modulos_empresa`), fail-closed | **ADD-only:** 1 tabla nueva (`modulos_empresa`), PK `(empresa_id, modulo_id)`, FK a `nucleo.empresas` `on delete restrict`, 3 `CHECK`, 2 triggers (`fn_touch`/`fn_version` de `0004`), RLS `ENABLE`+`FORCE`, 1 política `tenant_empresa`, GRANT `select, insert, update` a `tei_app` (sin `delete`). **0 filas: no siembra** | Bajo en datos (tabla vacía, sin reescritura) / a vigilar en comportamiento: escribir `habilitado=true` enciende la llave 1 del agente | untracked (`??`) | 🟡 solo `tei_test` (2026-10-30); rollback `0023_99` ejecutado + re-aplicación |
| `0024_mantenimiento_nucleo.sql` | Ola B.1: mantenimiento por km en el núcleo (pautas + registros + semáforo único) | **ADD-only:** 2 tablas (`pautas_mantenimiento`, `mantenimientos`), 1 vista (`v_mantenimiento_estado`, `security_invoker`), 3 funciones de trigger, 9 triggers, FKs compuestas, snapshot inmutable del intervalo, RLS `ENABLE`+`FORCE`, 2 políticas `tenant_empresa`, GRANT `select,insert,update` a `tei_app` + `select` a la vista. **0 filas** | **Alto**: `costo >= 0` (corrige defecto legacy) y el histórico de la flota. Sin backfill; el trigger de odómetro solo **sube** `tractos.km_actual` | untracked (`??`) | 🟡 `postgres` (local) y `tei_test`, 2026-10-31; rollback `0024_99` ejecutado + re-aplicación |
| `0025_liquidaciones_nucleo.sql` | Ola B.2: nómina (liquidaciones, anticipos, ajustes) con total generado y HALF_UP | **ADD-only:** 3 tablas (`liquidaciones`, `anticipos_chofer`, `ajustes_liquidacion`), 1 función de redondeo (`redondear_half_up`), 3 funciones de trigger, 15 triggers, `total_liquido` **generado**, UNIQUE `(empresa_id, chofer_id, mes)`, FKs compuestas, RLS `ENABLE`+`FORCE`, 3 políticas, GRANT `select,insert,update` (sin `delete`). **0 filas** | **Alto** (dinero y datos laborales): inmutabilidad de la emitida e imputación única del anticipo. No migra filas legacy | untracked (`??`) | 🟡 `postgres` y `tei_test`, 2026-10-31; rollback `0025_99` ejecutado + re-aplicación |
| `0026_configuracion_empresa.sql` | Ola B.4: configuración por empresa con vigencia e historial; reemplazo de `public.configuracion` | **ADD-only:** 1 tabla (`configuracion_empresa`), 3 funciones (lectura + 2 de trigger), 5 triggers, `UNIQUE` parcial de fila vigente, `EXCLUDE` gist de vigencias, `CHECK` de rango para `iva_porcentaje`, RLS `ENABLE`+`FORCE`, 1 política, GRANT `select,insert,update`. **Seed:** `iva_porcentaje=19` por empresa existente (2 en `postgres`, 130 en `tei_test`) | **Medio** (tributario): el 19 es paridad con `0001:291`, no una norma (`P-01`); no toca el legacy ni reajusta facturas | untracked (`??`) | 🟡 `postgres` y `tei_test`, 2026-10-31; rollback `0026_99` ejecutado + re-aplicación |
| `0027_grants_plataforma.sql` | Que el rol de plataforma (`postgres`, BYPASSRLS) usado por scripts y cutover tenga DML sobre los objetos de la Ola B | 6 `GRANT` (`select,insert,update,delete` en 6 tablas de `0024`–`0026`, `select` en `v_mantenimiento_estado`) + `usage,select` en secuencias de `nucleo`. **0 DDL, 0 filas** | Bajo: solo privilegios; idempotente (`grant` repetido es no-op) | committed | 🟢 `postgres` local, 2026-11-01 (`make db-reset`) |
| `0028_retiro_public.sql` | **Ola E (ADR-0002 §6.7 E.5): retiro físico del legacy `public`** | **DESTRUCTIVO:** `drop trigger on_auth_user_created on auth.users`; `drop function handle_new_user()`, `set_updated_at()`; **17 `drop table … cascade`** (`usuarios`…`_migraciones`); 8 `drop type` (`rol_usuario`, `estado_viaje`, …); `revoke usage on schema public from public` + `grant` a los roles de Supabase (defecto seguro). **Conserva** el esquema `public` y la extensión `btree_gist` (de la que dependen los 4 `EXCLUDE` del núcleo). Precondiciones P1–P4 abortan con `23514`; verificación V1–V6 dentro de la transacción | **Alto e irreversible por SQL** (pierde el histórico del legacy; solo se vuelve por backup) | untracked (`??`) — pendiente de commit | 🟢 `postgres` local, 2026-11-01 (aplicada con `supabase migration up --local`, y re-aplicada por `make db-reset`); **sin rollback SQL** (`docs/datos/retiro-public.md`) |

> **Adenda 2026-11-01 (estado en git).** `git status --short supabase/` solo
> muestra `0028_retiro_public.sql` como `??`: las migraciones `0001`–`0027`
> están **en `HEAD`** y `0028` vive en el árbol de trabajo (la escribió `datos`
> con autorización del dueño; el commit es del `orquestador`). Las celdas
> `untracked (??)` de las filas `0015`–`0026` son el estado medido el
> 2026-10-29/30 y **no se reescriben** (§0.4 de este documento); a la fecha de
> esta adenda describen un estado superado. El riesgo R13 del ADR-0002
> ("un clon de `HEAD` no reproduce el esquema") quedó cerrado por el commit de
> `0001`–`0027`; se reabre solo si `0028` no se commitea.

**Nota (a) — única declaración de aplicación en el repo:** `docs/qa/informes/2026-10-29-r01-r02-suite-verde.md:1-45`
reporta PostgreSQL local arriba y el trigger de `0016` activo (los fixtures sin
`licencia_clase` fallan con `CheckViolation ... Licencia A5 requerida`). Eso
sugiere que `0015`/`0016` están aplicadas en **esa** base local (🟡), no en
producción, y no fue re-verificado por `datos`. Para `0017`, `0018` y `0019` no
hay ninguna declaración.

**Nota (b) — migraciones de datos:** `0015` (backfill de reservas), `0018` y
`0019` escriben filas, no solo esquema. En un entorno con datos reales exigen
precondiciones ejecutadas y conteos antes/después, no solo `psql -f`.

**Nota (c) — `0020` (2026-10-30):** crea un rol **a nivel de clúster** (`tei_app`)
y políticas RLS. Es **inerte** mientras el backend conecte como `postgres`
(BYPASSRLS gana sobre FORCE: probado). Se aplicó y probó solo en `tei_test`. Antes
de aplicarla a otra base: ejecutar las precondiciones P1–P6 del encabezado
(0 filas) y leer `docs/datos/rls-multiempresa.md` §5.3 (orden de despliegue) y
§8 (handoff a `backend`). Rollback: borrar políticas + `NO FORCE` + revocar
GRANTs; no borra datos.

**Nota (d) — `0021` (2026-10-30):** contrato documental completo en
`docs/datos/agente-esquema.md`. **Requiere `0020` aplicada antes** (usa
`nucleo.ctx_empresa`, el rol `tei_app` y exige ≥35 políticas: si no, aborta con
`23514`, `0021:132-138`). Se aplicó **solo** en `tei_test`, donde se midió:
8 tablas vacías, 218 viajes existentes con `id_comercial_flete` nulo, `CHECK`
validado sin violaciones, 9 políticas nuevas (44 totales) y `FORCE RLS` en las 8
tablas. La aplicación fue **en una sola transacción** con las precondiciones
dentro (`0021:92-870`), así que P1–P3 valían 0 y P4 valía exactamente 35 al
aplicar. Rollback: descrito en `0021:78-85`, pero **el script
`supabase/tests/0021_99_rollback.sql` que cita no existía** al documentar esta
nota (defecto D1 del contrato). **Adenda 2026-10-30:** el script ya existe
(`supabase/tests/0021_99_rollback.sql`, **untracked**) junto con
`0022_99_rollback.sql`, y ambos se ejecutaron en el ciclo O1.3; D1 queda
resuelto en el árbol de trabajo, **no en `HEAD`**. En la base de la app sigue 🔴
no aplicada/no verificada.

**Nota (e) — `0022` (2026-10-30):** migración **correctiva** de `0021`, no
estructural. Cierra D2 (ID comercial inmutable: trigger `BEFORE UPDATE` que
también rechaza el paso a `NULL`), D3 (contador no retrocede: trigger), D5
(`propuesto → solicitud_creada → cargado|rechazado`, terminales, `payload`
inmutable) y D9 (tope `> 99999` ⇒ `23514` sin quemar el número, formato
intacto). Aplicada **solo** en `tei_test`; precondiciones P1-P4 dentro de la
transacción (`0022:186-274`); no toca filas. **Regresión (al aplicar):**
`0021_02`, `0021_03` y `0021_04` verdes; `0021_01_smoke.sql` **no** daba 14/14
porque sus aserciones C10E (`:566-578`) y C11H (`:669-670`) describían el
comportamiento anterior a D5/D2 — es de `qa` y no se editó en ese momento
(detalle en `docs/datos/agente-esquema.md` §8.1). D4, D6 y D8 siguen abiertos.
Rollback: drop de 3 triggers + 3 funciones y restaurar la función de
`0021:603-636`; completo en `0022:133-168`. No pierde datos y reabre los 4
defectos.

> **Adenda 2026-10-30 (O1.3 — rollback probado).** `qa` ejecutó el ciclo
> `0022_99_rollback.sql` → `0021_99_rollback.sql` → cero objetos →
> re-aplicación de `0021`/`0022` como `supabase_admin` → **4 suites verdes**,
> incluido `0021_01` **14/14 (63 `NOTICE OK`)** con C10E/C11H ya adaptadas y
> `0021_04` M1–M9 (`docs/qa/informes/2026-10-31-o1.3-rollback-reaplicacion.md:94-403`;
> `supabase/tests/README.md:145-170`). Con eso **D7 queda probado en clon** y
> el rollback de `0022` deja de ser teórico: el script existe y revierte sin
> pérdida de datos. D1 queda resuelto en el árbol de trabajo (no en `HEAD`).
> **Cautela medida (D10):** la re-aplicación no reproduce el ACL de `postgres`
> (ver §2, adenda O1.3 y `agente-esquema.md` §8.2).

> **Nota 2026-10-30 (`0023`).** `nucleo.modulos_empresa` **no** forma parte del
> módulo de `0021`: es la **llave 1 del gate** del conector
> (`docs/arquitectura/conector-agente-whatsapp.md` §2.7, `:260-311`), la tabla
> que desbloquea F2.1/O2.1. Nace **vacía**: aplicar `0023` no enciende nada y la
> ausencia de fila = módulo apagado (fail-closed). El rollback
> (`supabase/tests/0023_99_rollback.sql`) es `drop table` y se **ejecutó** en
> `tei_test` seguido de re-aplicación; pérdida = 0 filas (no hay semilla).
> Evidencia: catálogo + sonda con `tei_app` + las 4 suites de `0021` en verde
> (2026-10-30). Invariante: `INV-AW17` (`docs/datos/invariantes.md` §12);
> inventario: `docs/datos/agente-esquema.md` §10.

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

> **Adenda 2026-10-30 (no reescribe la salida anterior).** Hoy hay **21**
> archivos en `supabase/migrations/` (medido con `ls | wc -l`). Se agregaron
> `0020_rls_multiempresa.sql` y `0021_agente_whatsapp.sql`, ambos **untracked**
> (`??`), verificado con `git status --short supabase/migrations/`. Los conteos
> `19` de arriba corresponden a la corrida del 2026-10-29 y se conservan como
> registro.

> **Adenda 2026-10-30 (0022).** `ls supabase/migrations/ | wc -l` = **22**;
> `0022_agente_whatsapp_endurecimiento.sql` es **untracked** (`??`). Las 3
> nuevas (`0020`, `0021`, `0022`) siguen fuera de `HEAD`: el esquema del núcleo
> y del módulo no se reproduce desde un clon.

> **Adenda 2026-10-30 (O1.3 — reproducibilidad medida y D10).** El ciclo
> `0022_99` → `0021_99` → re-aplicación de `0021`/`0022` como `supabase_admin`
> → 4 suites verdes demuestra que las migraciones reconstruyen el esquema en
> un clon (`docs/qa/informes/2026-10-31-o1.3-rollback-reaplicacion.md:94-403`).
> **Límite medido (D10):** la re-aplicación **no** reproduce el ACL de
> `postgres` en las 8 tablas del módulo (solo `SELECT` vía
> `pg_read_all_data`), porque `0021:855-868` otorga únicamente a `tei_app`.
> En un clon local hay que restaurar ese ACL o correr las suites con
> `supabase_admin`; **el rol que aplica migraciones debe ser el mismo en todos
> los entornos**. Clasificación: riesgo de proceso local (clon), no de
> producción por este mecanismo — el rol previsto del núcleo es `tei_app` y el
> ACL real de la base de la app no se verificó (🟡) (`agente-esquema.md` §8.2).

> **Adenda 2026-10-30 (`0023`).** `ls supabase/migrations/ | wc -l` = **23**;
> `0023_modulos_empresa.sql` es **untracked** (`??`). `HEAD` sigue teniendo solo
> `0001`–`0003`: 20 de los 23 archivos están fuera del commit (11 `A` + 9 `??`).
> Aplicada **solo** en `tei_test` (clon desechable).

> **Adenda 2026-10-31 (Ola B: `0024`–`0026`).** `ls supabase/migrations/ |
> wc -l` = **26**; los tres archivos nuevos son **untracked** (`??`). `HEAD`
> sigue teniendo solo `0001`–`0003`: 23 de los 26 están fuera del commit.
>
> Las tres se aplicaron **y** probaron en la base local `postgres` (datos
> ficticios) y en el clon `tei_test`: `nucleo` pasa de **40 a 46 tablas** y de
> **45 a 51 políticas**; 6 tablas nuevas con `ENABLE`+`FORCE` y política
> `tenant_empresa`; 29 triggers nuevos; `tei_app` con
> `select,insert,update` (sin `delete`) en las 6 y `select` en la vista.
> Rollback probado en ciclo completo: `0026_99` → `0025_99` → `0024_99` deja
> 40 tablas/45 políticas y cero objetos de la Ola B; la re-aplicación vuelve a
> 46/51 sin residuos.
>
> **Particularidad de `0026`:** es la única de las tres que **escribe datos**
> (seed `iva_porcentaje = 19` por empresa: 2 filas en `postgres`, 130 en
> `tei_test`). No es backfill ni migración de datos del legacy: es el valor por
> defecto del parámetro, con el mismo 19 de `0001:291`, pendiente de `P-01`.
>
> Diseño, precondiciones ejecutadas, impacto/locks y salidas reales:
> `docs/datos/retiro-legacy-modelo.md`; invariantes: `invariantes.md` §12.

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
