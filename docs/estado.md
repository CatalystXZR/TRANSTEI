# Estado del sistema — ERP Transportes TEI

> **Pregunta que responde:** ¿qué está construido, qué está verificado y qué no?
> **Dueño:** `orquestador` · **Verificado:** 2026-11-02 (Ola 3) · 2026-11-01 (Fase 2) · 2026-10-29 (F0) · **Método:** ejecución + lectura
> **Caduca si:** pasan 30 días, cambia el esquema o se agrega un módulo.
> **Re-verificar con:** los comandos de §2.

> ⚠️ **Este es el único documento autorizado a contener cifras volátiles.**
> Si otro documento cita un conteo, está desactualizado por definición.

---

## 1. Entorno de esta verificación

| Elemento | Estado |
|---|---|
| Rama | `main`, árbol con cambios sin commitear (seguridad + documentación, 2026-11-01) |
| Backend `:8000` | 🟡 listener presente |
| Frontend `:3000` | 🟡 listener presente |
| PostgreSQL `:54322` | 🟢 Supabase local confirmado: contenedor `supabase_db_TRANSTEI` healthy (el listener `ssh` es el port-forward de Colima/Lima, no un túnel externo) — F0 2026-10-29 |
| Suite de integración | 🟢 ejecutada: **468 passed, 0 skipped** (2026-11-02) |
| E2E | 🟢 ejecutados: **20/20 passed** (2026-11-01) |
| `make unit` | 🟢 ejecutado: **135 passed** (2026-11-01) |
| Plan de cierre | [`docs/PLAN_DESARROLLO.md`](PLAN_DESARROLLO.md) — F0 cerrada; Fase 2 cerrada; reconciliar numeración de fases |

---

## 2. Cifras clave y cómo re-verificarlas

| Dato | Valor | Comando |
|---|---|---|
| Migraciones en disco | **31** (`0001`–`0031`) | `ls supabase/migrations \| wc -l` |
| Migraciones en `HEAD` | **28** (`0029`–`0031` sin commitear) | `git ls-tree HEAD supabase/migrations/ \| wc -l` |
| Migraciones aplicadas en la base local | **31** (2026-11-02: `0001`–`0031`) | `docker exec supabase_db_TRANSTEI psql -U postgres -tA -c "select count(*) from supabase_migrations.schema_migrations"` |
| Tablas en `nucleo` | **50** (`46` + `tenant_reglas_entidad`/`tenant_suscripciones` + `agente_chat_*`) · tablas en `public`: **0** | `select count(*) from pg_tables where schemaname='nucleo'` |
| Routers montados | **18** `include_router` en `api/router.py` (+4 Ola B anidados en `/nucleo`); 0 de negocio legacy | `grep -c include_router backend/app/api/router.py` |
| Pantallas | **30** page.tsx (incluye `/agente/chat` y 9 redirecciones 308) | `find frontend/src/app -name page.tsx \| wc -l` |
| Roles del núcleo | **8** | `backend/app/nucleo/models.py` (`RolEmpresa`) |
| Unitarias | **135 passed** (2026-11-01, re-ejecutado) | `make unit` |
| Integración | **468 passed, 0 skipped** (2026-11-02, re-ejecutado) | `make test` |
| Tenants activos (local) | **2** (TEI + TES) | `select count(*) from nucleo.empresas` |
| E2E definidos | **20** | `grep -cE "^\s*test\(" frontend/e2e/tei.spec.ts` |
| E2E ejecutados | **20/20 passed** (2026-11-01, re-ejecutado) | `make e2e` |

> **Re-verificado 2026-11-02:** `make unit` 135 passed; `make test` 468 passed, 0 skipped; E2E **no re-ejecutado** desde 2026-11-01 (20/20). Migraciones 31 aplicadas en local; `0030` y `0031` con RLS+FORCE y pruebas SQL propias.

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
| Cutover (datos) | — | `servicio_cutover.py` | ⚪ gate retirado en Fase 2; el servicio/script se conserva para cutover de datos local |

---

## 4. Qué NO está verificado 🔴

| Afirmación | Por qué no | Cómo se cierra |
|---|---|---|
| "Suite completa en verde" | Cerrado por F0 2026-10-29 | `make test` → **100 passed, 0 skipped** (pre y post reset) |
| "E2E 9/9" | Cerrado por F0 2026-10-29 | `make e2e` → **9/9 passed** |
| Migraciones 0015–0019 aplicadas | Cerrado por F0 2026-10-29: post-reset **19 aplicadas**. Pre-reset había desincronización ledger↔esquema (ver RA-14) | `select version from supabase_migrations.schema_migrations` |
| Aislamiento multiempresa (RA-03) | RLS habilitado sin políticas verificadas | `select current_user, rolbypassrls from pg_roles` |
| Restore drill real | Escribe en `backups/` y crea base temporal | `make restore-drill` (requiere autorización) |
| "CI en verde" | `.github/workflows/ci.yml` existe, pero ejecuta `pytest` **sin servicio PostgreSQL** y no corre E2E: un verde de CI no cubre integración ni navegador | leer `.github/workflows/ci.yml` |
| Cutover ejecutable | ⚪ superado: `public` fue retirado (0028) y la Ola D ejecutó el cutover local (2026-11-01). No aplica a producción. | `docs/operacion/cutover-ejecutado-2026-11-01.md` |

---

## 5. Riesgos abiertos

| ID | Tema | Estado | Dueño |
|---|---|---|---|
| RA-01 | "Piloto cerrado y probado" sin evidencia (UAT vacía) | 🟡 parcial | `qa` |
| RA-05 | Restore drill no compara antes/después | 🟡 | `datos` |
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

---

## 6. Bloqueos activos

No hay bloqueos **técnicos** para operar en local: identidad, aislamiento, suites y datos están verdes.
Los bloqueos son **decisiones** y **verificación en entorno real**:

1. **Producción/despliegue**: no hay servidor; faltan pooler probado (RA-15), límites de conexión y rol de plataforma (RA-16).
2. **Restore drill** (RA-05) y backup automatizado: el backup del cutover está verificado por conteos, no por restauración completa.
3. **CI real** (RA-18): validar el workflow en el primer push.
4. **Decisiones de negocio** (RA-19/RA-21): IVA/crédito/F29, nómina, comisiones, DTE, tablero, import CSV, ratificación formal de D-2.
5. **Deuda de seguridad operativa**: rate limiting, cabeceras del frontend, `/docs` en producción, `issuer` del JWT (F0-07/08/09/11).
6. **Plan de cierre y pendientes del agente**: el plan vigente es [`docs/PLAN_DESARROLLO.md`](PLAN_DESARROLLO.md); los pendientes operativos del agente están en [`docs/desarrollo/backlog.md`](../desarrollo/backlog.md) §6. Cifras re-verificadas el 2026-11-01 (135 unit / 413 integración / 20 E2E).
7. **SEC-039 cerrado (2026-11-01):** migración `0029` crea el rol `tei_admin` (privilegiado para identidad/ACL/flag) y revoca la escritura directa de `tei_app`; las escrituras de la app pasan por `nucleo.admin_*` (`SECURITY DEFINER`, con `empresa_id = ctx_empresa()`). El enrolamiento (OTP) lo inicia el admin; el envío usa el adaptador WhatsApp `fake` local hasta definir proveedor real (AB-04). Sigue pendiente `tei_platform` (RA-16) y el pooler (RA-15).
8. **Seguridad operativa cerrada en código (2026-11-01):** `iss` del JWT validado, `/docs`/`/openapi.json` deshabilitados por defecto (`ENABLE_DOCS=false`) y cabeceras de seguridad (`nosniff`, `DENY`, `no-referrer`, `permissions-policy`, `COOP`). Rate limiting queda para staging.

---

*Historial de verificaciones: `orquestacion/registro.md`.*

*F0 — Due Diligence y Línea Base (2026-10-29): informe completo en [`docs/qa/informes/F0-due-diligence.md`](qa/informes/F0-due-diligence.md). **Veredicto: A (REFACTOR), ratificado por el dueño (2026-10-29). F0 cerrada.***

*Fase 2 — retiro del legacy **COMPLETADO** (2026-11-01): **Olas A/B/C** (9 pantallas → 308; 4 módulos reconstruidos en el núcleo; 11 routers legacy retirados), **Ola D** (cutover local reproducible: 6 pautas, maestros 3/3, idempotente) y **Ola E** (identidad sin `public.usuarios`, gate retirado, **`public` retirado físicamente**: 0 tablas, `auth.users` sin trigger). Núcleo: 46 tablas, 51 políticas. Baseline: **128 unit + 404 integración (0 skipped) + 20 E2E**. ADR: `docs/arquitectura/adr/ADR-0002-retiro-del-legacy.md`; ejecución: `docs/operacion/cutover-ejecutado-2026-11-01.md`.*
