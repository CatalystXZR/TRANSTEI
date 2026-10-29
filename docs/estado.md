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
| PostgreSQL `:54322` | 🔴 **no confirmado como Supabase local** — hay evidencia de un túnel `ssh`, no el contenedor |
| Suite de integración | 🔴 no ejecutada (requiere base real) |
| `make unit` | 🟢 ejecutado: **52 passed, 1 warning** |

---

## 2. Cifras clave y cómo re-verificarlas

| Dato | Valor | Comando |
|---|---|---|
| Migraciones en disco | **19** (`0001`–`0019`) | `ls supabase/migrations \| wc -l` |
| Migraciones en `HEAD` | **3** (`0001`–`0003`) | `git ls-tree HEAD supabase/migrations/ \| wc -l` |
| Tablas en `nucleo` | **31** | `grep -rh "create table nucleo" supabase/migrations \| wc -l` |
| Routers montados | **25** (12 legacy + 13 núcleo) | `grep -c include_router backend/app/api/router.py` |
| Pantallas | **28** | `find frontend/src/app -name page.tsx \| wc -l` |
| Roles del núcleo | **8** | `backend/app/nucleo/models.py` (`RolEmpresa`) |
| Unitarias | **52 passed** | `make unit` |
| E2E definidos | **9** | `grep -cE "^\s*test\(" frontend/e2e/tei.spec.ts` |
| E2E ejecutados | **0 en esta sesión** | `make e2e` (requiere base + seed) |

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
| "Suite completa en verde" | Requiere base; no ejecutada | `make test` |
| "E2E 9/9" | No ejecutados | `make e2e` |
| Migraciones 0015–0019 aplicadas | Sin acceso a la base | `select version from supabase_migrations.schema_migrations` |
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
| RA-03 | Aislamiento multiempresa | 🟢 **47 tablas con RLS habilitado y 0 políticas en `nucleo`** (única `create policy` del repo: `0001:284`, sobre `public.usuarios`). El backend usa conexión directa: si el rol es owner/superusuario, RLS no aplica. Aislamiento **no demostrado** | `datos` + `auditor-seguridad` |
| RA-04 | Cutover: flag abierto por defecto + `legacy_congelado()` **fail-open** | 🟢 confirmado en código | `arquitectura` + `auditor-seguridad` |
| RA-05 | Restore drill no compara antes/después | 🟡 | `datos` |
| RA-06 | Duplicidad de fuentes (`/maestros` vs `/clientes`, `/dashboard` vs `/tablero`, `/cobranza` vs `/cobranzas`) | 🟢 confirmado | `arquitectura` |
| RA-07 | Auditoría cubre núcleo, no legacy | 🟡 | `datos` |
| RA-08 | Conteo E2E contradictorio en documentos históricos | 🟢 resuelto: son **9** | `qa` |
| RA-09 | Informe de auditoría original ausente del repo | 🔴 | usuario |
| RA-10 | `DEBUG` por defecto | 🟢 **confirmado**: `DEBUG: bool = True` (`backend/app/core/config.py:11`). Debe forzarse `false` por entorno antes de exponer la API | `auditor-seguridad` |
| RA-11 | Uploads POD: MIME real, path, visor | 🔴 sin verificar | `auditor-seguridad` |
| RA-12 | Anon key de Supabase en frontend | 🔴 sin verificar | `auditor-seguridad` |
| RA-13 | **Los tests pueden escribir en la base de la aplicación** | 🟢 confirmado en código: `test_reglas_negocio.py:114-120` y `conftest.py:63` leen `settings.DATABASE_URL` (de `backend/.env`, que existe), mientras `make test` exporta `NUCLEO_TEST_DATABASE_URL` | `qa` + `backend` |

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
4. **`HEAD` no tiene el esquema real.** Solo 3 de 19 migraciones están commiteadas;
   reconstruir el entorno desde un clon no reproduce el sistema.

---

*Historial de verificaciones: `orquestacion/registro.md`.*
