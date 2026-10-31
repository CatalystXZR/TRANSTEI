# Estado del sistema — ERP Transportes TEI

> **Pregunta que responde:** ¿qué está construido, qué está verificado y qué no?
> **Dueño:** `orquestador` · **Verificado:** 2026-10-29 · **Método:** ejecución + lectura
> **Caduca si:** pasan 30 días, cambia el esquema o se agrega un módulo.
> **Re-verificar con:** los comandos de §2.

> ⚠️ **Este es el único documento autorizado a contener cifras volátiles.**
> Si otro documento cita un conteo, está desactualizado por definición.

---

## 1. Entorno de esta verificación

| Elemento | Estado |
|---|---|
| Rama | `main`, árbol con trabajo sin commitear |
| Backend `:8000` | 🟡 listener presente |
| Frontend `:3000` | 🟡 listener presente |
| PostgreSQL `:54322` | 🟢 Supabase local confirmado: contenedor `supabase_db_TRANSTEI` healthy (el listener `ssh` es el port-forward de Colima/Lima, no un túnel externo) — F0 2026-10-29 |
| Suite de integración | 🟢 ejecutada: **100 passed, 0 skipped** (pre y post reset) — F0 |
| E2E | 🟢 ejecutados: **9/9 passed** (pre y post reset) — F0 |
| `make unit` | 🟢 ejecutado: **52 passed, 1 warning** |

---

## 2. Cifras clave y cómo re-verificarlas

| Dato | Valor | Comando |
|---|---|---|
| Migraciones en disco | **19** (`0001`–`0019`) | `ls supabase/migrations \| wc -l` |
| Migraciones en `HEAD` | **19** (corrección 2026-10-29: la cifra anterior "3" era una medición errónea de `git ls-tree` sin slash) | `git ls-tree HEAD supabase/migrations/ \| wc -l` |
| Migraciones aplicadas en la base local | **19** (tras reset F0 2026-10-29; antes del reset el ledger registraba 14 pero el esquema físico ya contenía objetos de 0015–0017, ver RA-14) | `docker exec supabase_db_TRANSTEI psql -U postgres -tA -c "select count(*) from supabase_migrations.schema_migrations"` |
| Tablas en `nucleo` | **31** | `grep -rh "create table nucleo" supabase/migrations \| wc -l` |
| Routers montados | **25** (12 legacy + 13 núcleo) | `grep -c include_router backend/app/api/router.py` |
| Pantallas | **28** | `find frontend/src/app -name page.tsx \| wc -l` |
| Roles del núcleo | **8** | `backend/app/nucleo/models.py` (`RolEmpresa`) |
| Unitarias | **67 passed** (fase 1, 2026-10-30) | `make unit` |
| Integración | **230 passed** (fase 1, 2026-10-30) | `make test` (tei_test) |
| E2E definidos | **9** | `grep -cE "^\s*test\(" frontend/e2e/tei.spec.ts` |
| E2E ejecutados | **9/9 passed** | `make e2e` (F0 2026-10-29) |

---

## 3. Estado por capa

### Legacy (`public`) — en uso

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
| POD | — | `servicio_pod.py` | 🟡 storage no verificado |
| PWA conductor | `/conductor` | `api_conductor.py` | 🟡 offline no verificado |
| Comercial (OC, tarifas) | `/comercial` | `servicio_comercial.py` | 🟢 |
| Gastos | — | `servicio_gastos.py` | 🟢 |
| Rentabilidad / Freight Score | `/rentabilidad` | `servicio_rentabilidad.py` | 🟢 6 componentes |
| Facturación núcleo | `/cobranza` | `servicio_facturacion.py` | 🟢 |
| Alertas | `/tablero` | `servicio_alertas.py` | 🟢 |
| Maestros | `/maestros` | `servicio_maestros.py` | 🟢 |
| Auditoría | `/auditoria` | `servicio_auditoria.py` | 🟢 append-only |
| Permisos | `/permisos` | `api_permisos.py` | 🟢 8 roles |
| Cutover | `/cutover` | `servicio_cutover.py` | 🔴 **fail-open** (RA-04) |

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
| Cutover ejecutable | No hay evidencia de `--dry-run` ejecutado; el script es compatible con `0015` pero deja los viajes sin recursos | `make cutover-dry` + ver `operacion/cutover.md` |

---

## 5. Riesgos abiertos

| ID | Tema | Estado | Dueño |
|---|---|---|---|
| RA-01 | "Piloto cerrado y probado" sin evidencia | 🟡 parcial | `qa` |
| RA-02 | Doble asignación legacy ↔ núcleo (legacy sin `EXCLUDE`) | 🟢 riesgo confirmado, carrera no reproducida | `datos` + `qa` |
| RA-03 | Aislamiento multiempresa | 🟢 **ACTIVO en `nucleo` (fase 1, 2026-10-30)**: ADR-0005 aceptado; `0020` aplicada (35 políticas, 31 FORCE); app con dos engines — núcleo `tei_app` (NOBYPASSRLS), legacy con el rol actual y **declarado no aislado** hasta su retiro. Pruebas: A no ve ni escribe de B, sin contexto 0 filas, mutación (núcleo→rol legacy) rompe 6 pruebas. Residual: legacy sin aislamiento; pooler real y concurrencia `tei_app` no probados | `datos` + `backend` |
| RA-04 | Cutover: flag abierto por defecto + `legacy_congelado()` **fail-open** | 🟢 **corregido (fase 1, Ola 2)**: fail-closed en `servicio_cutover.py:46-60` + `congelar`/`descongelar` con rowcount (SEC-016); revalidado por auditor-seguridad. Residual: caché TTL 5 s por proceso | `auditor-seguridad` |
| RA-05 | Restore drill no compara antes/después | 🟡 | `datos` |
| RA-06 | Duplicidad de fuentes (`/maestros` vs `/clientes`, `/dashboard` vs `/tablero`, `/cobranza` vs `/cobranzas`) | 🟢 confirmado | `arquitectura` |
| RA-07 | Auditoría cubre núcleo, no legacy | 🟡 | `datos` |
| RA-08 | Conteo E2E contradictorio en documentos históricos | 🟢 resuelto: son **9** | `qa` |
| RA-09 | Informe de auditoría original ausente del repo | 🔴 | usuario |
| RA-10 | `DEBUG` por defecto | 🟢 **confirmado**: `DEBUG: bool = True` (`backend/app/core/config.py:11`). Debe forzarse `false` por entorno antes de exponer la API | `auditor-seguridad` |
| RA-11 | Uploads POD: MIME real, path, visor | 🔴 sin verificar | `auditor-seguridad` |
| RA-12 | Anon key de Supabase en frontend | 🔴 sin verificar | `auditor-seguridad` |
| RA-13 | **Los tests pueden escribir en la base de la aplicación** | 🟢 **mitigado (fase 1, 2026-10-29)**: fixtures leen `settings.NUCLEO_TEST_DATABASE_URL` con guarda anti-RA-13 (`conftest.py:40-54`); `make test` apunta por defecto a `tei_test` (clon dedicado, `scripts/test_db_reset.sh`); `backend/.env` corregido. Prueba de aislamiento: 2 corridas completas con la base de la app idéntica. ⚠️ residual: los `test_nucleo_*.py` restantes tienen `_url()` propio sin guarda | `qa` + `backend` |
| RA-14 | Desincronización ledger↔esquema de migraciones | 🟢 confirmado por F0: `schema_migrations` registraba 0001–0014 pero el esquema físico ya contenía objetos de 0015/0016/0017 (triggers, defaults, backfill de 3 reservas `creado_por='migracion_0015'`). Reconciliado por `supabase db reset` (19 aplicadas). **Causa no determinada** | `datos` + dueño |

---

## 6. Bloqueos activos

0. **`make test` puede apuntar a la base de la aplicación.** El fixture `db` y
   `test_reglas_negocio` leen `settings.DATABASE_URL` (de `backend/.env`), no
   `NUCLEO_TEST_DATABASE_URL`. Si esa URL es la de la nube, **las pruebas escriben
   ahí**. No ejecutes `make test` hasta confirmar el destino (RA-13).
1. **El cutover deja viajes sin recursos.** El script migra los viajes `confirmado` con
   `tracto_id`, `rampla_id` y `chofer_id` en `NULL` (`scripts/cutover_legacy.py:6-13,378-401`).
   Es intencional (el legacy no tiene los documentos que exige `0015`), pero **exige
   reasignación manual** antes de operar. Ver `operacion/cutover.md`.
2. **El congelamiento legacy falla en abierto (RA-04).** Si la consulta del flag falla,
   `legacy_congelado()` devuelve `False` y las escrituras legacy se reanudan en silencio
   (`servicio_cutover.py:38-39`).
3. **SEC-002 abierto.** El PDF de liquidación recalcula la comisión en vivo
   (`liquidaciones.py:515`): un documento firmado no es reproducible.
4. ~~`HEAD` no tiene el esquema real~~ → **CERRADO (2026-10-29):** las 19 migraciones están commiteadas en `de0d6d3`; la cifra "3/19" era una medición errónea (ver §2). Un clon limpio sí reproduce el esquema.

---

*Historial de verificaciones: `orquestacion/registro.md`.*

*F0 — Due Diligence y Línea Base (2026-10-29): informe completo en [`docs/qa/informes/F0-due-diligence.md`](qa/informes/F0-due-diligence.md). **Veredicto: A (REFACTOR), ratificado por el dueño (2026-10-29). F0 cerrada.***

*Fase 1 (2026-10-30, en curso): infraestructura (tei_test + CI + aislamiento de tests), cutover fail-closed, SQLSTATE→HTTP, uploads con firma, idempotencia de documentos, límite de cuerpo y contexto por transacción, deps frontend 12→3. Baseline: 67 unit + 219 integración verdes. **Próxima decisión: aceptar ADR-0005 (tenancy con dos engines) para aplicar `0020` y cambiar el rol de la app.** Detalle por ola en `docs/orquestacion/registro.md`.*
