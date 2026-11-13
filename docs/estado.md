# Estado del sistema — ERP Transportes TEI

> **Pregunta que responde:** ¿qué está construido, qué está verificado y qué no?
> **Dueño:** `orquestador` · **Verificado:** 2026-11-09 (re-verificación de suites y esquema) · 2026-11-02 (Ola 3) · 2026-11-01 (Fase 2) · 2026-10-29 (F0) · **Método:** ejecución + lectura
> **Caduca si:** pasan 30 días, cambia el esquema o se agrega un módulo.
> **Re-verificar con:** los comandos de §2.

> ⚠️ **Este es el único documento autorizado a contener cifras volátiles.**
> Si otro documento cita un conteo, está desactualizado por definición.

---

## 1. Entorno de esta verificación

| Elemento | Estado |
|---|---|
| Rama | `main`, árbol de trabajo con la entrega 2026-11-12 (retiro legacy) sin commitear |
| Backend `:8000` | 🟢 sirviendo; 18 `include_router`, 0 rutas de cutover — 2026-11-12 |
| Frontend `:3000` | 🟢 dev sirviendo; rutas legacy → 404; `tsc` y `lint` verdes — 2026-11-12 |
| PostgreSQL `:54322` | 🟢 Supabase local confirmado: contenedor `supabase_db_TRANSTEI` healthy — 2026-11-12 |
| Suite de integración | 🟢 ejecutada: **490 passed, 0 skipped** (2026-11-12) |
| E2E | 🟢 ejecutados: **20/20 passed** (2026-11-12, tras reescritura con 404 legacy; 2.ª corrida con servidores frescos) |
| `make unit` | 🟢 ejecutado: **135 passed** (2026-11-12) |
| Plan de cierre | [`docs/PLAN_DESARROLLO.md`](PLAN_DESARROLLO.md) — F0 cerrada; Fase 2 cerrada; reconciliar numeración de fases |

---

## 2. Cifras clave y cómo re-verificarlas

| Dato | Valor | Comando |
|---|---|---|
| Migraciones en disco | **35** (`0001`–`0035`) | `ls supabase/migrations \| wc -l` |
| Migraciones en `HEAD` | **34** (`0001`–`0034`; `0035` untracked) | `git ls-tree HEAD supabase/migrations/ \| wc -l` |
| Migraciones aplicadas en la base local | **35** (2026-11-12: `0001`–`0035`; también en `tei_test`) | `docker exec supabase_db_TRANSTEI psql -U postgres -tA -c "select count(*) from supabase_migrations.schema_migrations"` |
| Tablas en `nucleo` | **50** (`0035` retiró `cutover_control`: 51 → 50) · tablas en `public`: **0** | `select count(*) from pg_tables where schemaname='nucleo'` |
| Políticas RLS en `nucleo` | **54** | `select count(*) from pg_policies where schemaname='nucleo'` |
| Routers montados | **18** `include_router` en `api/router.py` (`auth` + núcleo + 4 agente + dominio); 0 legacy | `grep -c include_router backend/app/api/router.py` |
| Pantallas | **21** page.tsx (sin las 9 redirecciones 308, eliminadas; rutas legacy → 404) | `find frontend/src/app -name page.tsx \| wc -l` |
| Roles del núcleo | **8** | `backend/app/nucleo/models.py` (`RolEmpresa`) |
| Unitarias | **135 passed** (2026-11-12) | `make unit` |
| Integración | **490 passed, 0 skipped** (2026-11-12; −14 al retirar las pruebas de cutover) | `make test` |
| Tenants activos (local) | **2** (TEI + TES) | `select count(*) from nucleo.empresas` |
| E2E definidos | **20** | `grep -cE "^\s*test\(" frontend/e2e/tei.spec.ts` |

> **Re-verificado 2026-11-12 (retiro del legacy y del cutover):** se eliminaron el
> grupo `(retiradas)` de la UI (404), el middleware/middleware flag de cutover de
> `main.py`, `api_cutover.py`, `servicio_cutover.py`, `scripts/cutover_legacy.py`,
> targets de Makefile y las pruebas de cutover; la tabla `nucleo.cutover_control`
> fue retirada por `0035` (51 → 50 tablas; backup previo en
> `backups/0035_pre_cutover_control_20261112.sql`). Suites: `make test-db` OK
> (clon con cadena de replay `0014 → 0020 → 0029 → 0033 → 0034 → 0035`);
> `make test` **490 passed**; `make unit` **135 passed**; `tsc`/`lint` verdes;
> `0035` verde en `postgres` y `tei_test`; RLS `0020_01_aislamiento.sh` verde
> (A–L, rol real `tei_app`); `make e2e` **20/20** (2.ª corrida del 2026-11-12;
> la 1.ª falló por servidores dev huérfanos de una sesión anterior, no por
> código). Previo (2026-11-09): **504 passed / 20 E2E**; ese
> cierre corrigió el orden del gate de módulos (SEC-052) y cerró
> SEC-056/063/064/065/066/068/069. Siguen abiertos SEC-067 (identidad),
> SEC-071 (DPA), SEC-053/054 y SEC-057(a).

---

## 3. Estado por capa

### Legacy (`public`) — RETIRADO (2026-11-01)

> **El esquema `public` fue retirado** (migración `0028`): 0 tablas, `auth.users` sin trigger
> legacy. La tabla de abajo es **histórica** (cómo era antes del retiro) y no describe el sistema
> actual. Los módulos viven hoy en `nucleo`; ver §3 Núcleo.

| Módulo | Pantalla | Backend | Estado |
|---|---|---|---|
| Viajes | `/viajes`, `/viajes/[id]` | `routes/viajes.py` | 🟢 construido, sin garantía de concurrencia |
| Flota | `/flota` | `routes/catalogos.py` | 🟢 |
| Mantenimiento | `/mantenimiento` | `routes/mantenimiento.py` | 🟢 |
| Facturación | `/facturacion` | `routes/facturas.py` | 🟢 sin DTE |
| Cobranzas | `/cobranzas` | `routes/finanzas.py` | 🟢 |
| IVA | `/iva` | `routes/finanzas.py` | 🟢 cálculo interno, no F29 |
| Liquidaciones | `/liquidaciones` | `routes/liquidaciones.py` | 🟢 R-01 corregida (SEC-001) |
| Clientes / Choferes | `/clientes`, `/choferes` | `routes/catalogos.py` | 🟢 |
| KPIs | `/kpis`, `/dashboard` | `routes/kpis.py`, `services/kpi_engine.py` | 🟢 22 métricas |
| Configuración | `/configuracion` | `routes/configuracion.py` | 🟢 |

### Núcleo (`nucleo`) — destino del cutover

| Módulo | Pantalla | Backend | Estado |
|---|---|---|---|
| Despacho / disponibilidad | `/despacho` | `servicio_disponibilidad.py` | 🟢 3 `EXCLUDE` en base |
| Agenda | `/agenda` | `api_bloqueos.py` | 🟢 |
| Expediente documental | `/expediente`, `/expediente/[id]` | `servicio_expediente.py` | 🟢 |
| POD | — | `servicio_pod.py` | 🟡 firma/tamaño validadas; visor/URLs firmadas sin verificar (RA-11) |
| PWA conductor | `/conductor` | `api_conductor.py` | 🟡 offline no verificado |
| Comercial (OC, tarifas) | `/comercial` | `servicio_comercial.py` | 🟢 |
| Gastos | — | `servicio_gastos.py` | 🟢 |
| Rentabilidad / Freight Score | `/rentabilidad` | `servicio_rentabilidad.py` | 🟢 6 componentes |
| Facturación núcleo | `/cobranza` | `servicio_facturacion.py` | 🟢 |
| Alertas | `/tablero` | `servicio_alertas.py` | 🟢 |
| Maestros | `/maestros` | `servicio_maestros.py` | 🟢 |
| Auditoría | `/auditoria` | `servicio_auditoria.py` | 🟢 append-only |
| Permisos | `/permisos` | `api_permisos.py` | 🟢 8 roles |
| Cutover (datos) | — | ~~`servicio_cutover.py`~~ | ⚪ **retirado por completo** (2026-11-12): servicio, API, script, targets de Makefile y tabla `cutover_control` (`0035`) eliminados |

---

## 4. Qué NO está verificado 🔴

| Afirmación | Por qué no | Cómo se cierra |
|---|---|---|
| "Suite completa en verde" | Cerrado por F0 2026-10-29 | `make test` → **100 passed, 0 skipped** (pre y post reset) |
| "E2E 9/9" | Cerrado por F0 2026-10-29 | `make e2e` → **9/9 passed** |
| Migraciones 0015–0019 aplicadas | Cerrado por F0 2026-10-29: post-reset **19 aplicadas**. Pre-reset había desincronización ledger↔esquema (ver RA-14) | `select version from supabase_migrations.schema_migrations` |
| Aislamiento multiempresa (RA-03) | 🟡 cerrado parcialmente (2026-11-12): **54 políticas + FORCE** aplicadas en la base de la app y prueba de aislamiento A–L verde con el rol real `tei_app` (bypass=f); queda verificar el rol efectivo de `DATABASE_URL` en el despliegue real | `select count(*) from pg_policies where schemaname='nucleo'`; `bash supabase/tests/0020_01_aislamiento.sh` |
| Restore drill real | Escribe en `backups/` y crea base temporal | `make restore-drill` (requiere autorización) |
| "CI en verde" | `.github/workflows/ci.yml` existe, pero ejecuta `pytest` **sin servicio PostgreSQL** y no corre E2E: un verde de CI no cubre integración ni navegador | leer `.github/workflows/ci.yml` |
| Cutover ejecutable | ⚪ superado y retirado: `public` fue eliminado (`0028`, 2026-11-01) y el mecanismo completo de cutover (código + tabla `cutover_control` por `0035`) se retiró el 2026-11-12 | `docs/_archivo/cutover-ejecutado-2026-11-01.md`; `docs/datos/catalogo-migraciones.md` (0035) |

---

## 5. Riesgos abiertos

| ID | Tema | Estado | Dueño |
|---|---|---|---|
| RA-01 | "Piloto cerrado y probado" sin evidencia (UAT vacía) | 🟡 parcial | `qa` |
| RA-05 | Restore drill: desde 2026-11-09 **verifica de verdad** (conteos + `restore_ok`, aborta si vacío); falta comparación automática antes/después | 🟡 | `datos` |
| RA-09 | Informe de auditoría original ausente del repo | 🔴 | usuario |
| RA-11 | POD: firma/tamaño/content-type ya validados (Ola 2); **visor/URLs firmadas** sin verificar | 🟡 | `auditor-seguridad` |
| RA-12 | Anon key en frontend (normal); **políticas del bucket `respaldos`** sin verificar | 🟡 | `auditor-seguridad` |
| RA-15 | Pooler real (transaction) con `SET LOCAL` + `tei_app` y límites de conexión | 🔴 no probado | `datos` + operación |
| RA-16 | Rol de plataforma formal (`tei_platform`); hoy el cutover usó `postgres` (BYPASSRLS) | 🔴 | `datos` |
| RA-17 | Deudas RLS del ADR-0005: R-1 (GUC antes de autorizar), R-5 (FK `reserva.viaje_id` sin empresa), R-9 (auditoría) | 🟡 | `datos` + `backend` |
| RA-18 | CI nunca ejecutado en GitHub Actions (workflow con Supabase + E2E) | 🔴 | operación |
| RA-19 | Decisiones tributarias/laborales pendientes (IVA crédito/F29, nómina, comisiones, DTE) | 🔴 | contador |
| RA-20 | Documentos que citan archivos retirados (16; lista en ADR-0002 §8.2) | 🟡 | varios |
| RA-21 | Decisiones de producto: RET-06 (tablero sin totales de dinero), RET-12 (secuencia), RET-13 (import CSV) | 🟡 | dueño |
| RA-22 | SEC-067: un contacto con OTP pendiente reserva el teléfono en el índice **global**; permite squatting/oráculo entre empresas. Requiere decisión de identidad (ADR-0003) | 🔴 abierto | `arquitectura` + `datos` |
| RA-23 | SEC-071: el chat envía RUT, facturación y márgenes al proveedor LLM externo sin DPA/redacción | 🔴 abierto | dueño + `negocio-finanzas` |
| RA-24 | SEC-053/054: transacción abierta durante el LLM y sin rate limit distribuido; el semáforo es por proceso | 🟡 parcial | `backend` + operación |
| RA-25 | SEC-057(a): la clave de idempotencia del chat es por empresa, no por usuario; B con la clave de A recibe 502, no 409 | 🟡 bajo | `backend` |

---

## 6. Bloqueos activos

No hay bloqueos **técnicos** para operar en local: identidad, aislamiento, suites y datos están verdes.
Los bloqueos son **decisiones** y **verificación en entorno real**:

1. **Producción/despliegue**: no hay servidor; faltan pooler probado (RA-15), límites de conexión y rol de plataforma (RA-16).
2. **Restore drill** (RA-05) y backup automatizado: el backup del cutover está verificado por conteos, no por restauración completa.
3. **CI real** (RA-18): validar el workflow en el primer push.
4. **Decisiones de negocio** (RA-19/RA-21): IVA/crédito/F29, nómina, comisiones, DTE, tablero, import CSV, ratificación formal de D-2.
5. **Deuda de seguridad operativa**: rate limiting, cabeceras del frontend, `/docs` en producción, `issuer` del JWT (F0-07/08/09/11).
6. **Plan de cierre y pendientes del agente**: el plan vigente es [`docs/PLAN_DESARROLLO.md`](PLAN_DESARROLLO.md); los pendientes operativos del agente están en [`docs/desarrollo/backlog.md`](../desarrollo/backlog.md) §6. Cifras re-verificadas el 2026-11-12 (135 unit / 490 integración / 20 E2E definidos).
7. **SEC-039 cerrado (2026-11-01):** migración `0029` crea el rol `tei_admin` (privilegiado para identidad/ACL/flag) y revoca la escritura directa de `tei_app`; las escrituras de la app pasan por `nucleo.admin_*` (`SECURITY DEFINER`, con `empresa_id = ctx_empresa()`). El enrolamiento (OTP) lo inicia el admin; el envío usa el adaptador WhatsApp `fake` local hasta definir proveedor real (AB-04). Sigue pendiente `tei_platform` (RA-16) y el pooler (RA-15).
8. **Seguridad operativa cerrada en código (2026-11-01):** `iss` del JWT validado, `/docs`/`/openapi.json` deshabilitados por defecto (`ENABLE_DOCS=false`) y cabeceras de seguridad (`nosniff`, `DENY`, `no-referrer`, `permissions-policy`, `COOP`). Rate limiting queda para staging.
9. **Revisión Ola 4 (2026-11-09):** SEC-056/063/064/065/066/068/069 corregidos y con prueba; `0033` revoca escritura de `tei_app` sobre historial y suscripciones. Siguen abiertos SEC-067 (identidad, RA-22), SEC-071 (DPA, RA-23), SEC-053/054 (RA-24) y SEC-057(a) (RA-25). Informe: `docs/seguridad/ola4-revision-2026-11-09.md`.

---

*Historial de verificaciones: `orquestacion/registro.md`.*

*F0 — Due Diligence y Línea Base (2026-10-29): informe completo en [`docs/qa/informes/F0-due-diligence.md`](qa/informes/F0-due-diligence.md). **Veredicto: A (REFACTOR), ratificado por el dueño (2026-10-29). F0 cerrada.***

*Fase 2 — retiro del legacy **COMPLETADO** (2026-11-01): **Olas A/B/C** (9 pantallas → 308; 4 módulos reconstruidos en el núcleo; 11 routers legacy retirados), **Ola D** (cutover local reproducible: 6 pautas, maestros 3/3, idempotente) y **Ola E** (identidad sin `public.usuarios`, gate retirado, **`public` retirado físicamente**: 0 tablas, `auth.users` sin trigger). Núcleo: 46 tablas, 51 políticas. Baseline: **128 unit + 404 integración (0 skipped) + 20 E2E**. ADR: `docs/arquitectura/adr/ADR-0002-retiro-del-legacy.md`; ejecución: `docs/operacion/cutover-ejecutado-2026-11-01.md` (hoy en `docs/_archivo/`).*

*Erradicación final del legacy (2026-11-12): código (API/servicio/script/middleware/targets de Makefile), UI (grupo `(retiradas)` y página `/cutover` → 404), pruebas y tabla `nucleo.cutover_control` (migración `0035`; `nucleo` 51 → 50 tablas; backup previo en `backups/0035_pre_cutover_control_20261112.sql`). `grep -rni cutover backend/app backend/tests frontend/src scripts Makefile` → 0. Suites: **135 unit / 490 integración / 0 skip / 20 E2E**; RLS A–L verde; `0035` verde en `postgres` y `tei_test`; `tsc`/`lint` verdes.*
