> ⚠️ **Aviso de vigencia (2026-11-01):** cita archivos/cifras anteriores al retiro del legacy (`public`, `lib/api.ts`, `backend/app/api/routes/*`, `kpi_engine.py`). No citar como estado actual; ver `docs/estado.md` §2–§6 y `docs/PLAN_DESARROLLO.md`.

# F0 — Due Diligence y Línea Base · ERP Transportes TEI SpA

> **Fecha:** 2026-10-29 · **Orquestador:** `orquestador` · **Misión:** F0 (solo lectura + ejecución de pruebas + documentación)
> **Autorización del dueño (2026-10-29):** F0 completo; levantar/resetear base local ficticia; instalar herramientas de análisis; sin restricciones de inspección; escritura solo en `docs/qa/` y `docs/estado.md` (no se tocaron `INDEX.md` ni `PLAN_DESARROLLO.md`, que tienen trabajo ajeno sin commitear).
> **Evidencia:** cada afirmación cita comando + salida o `archivo:línea`. Niveles 🟢 verificado / 🟡 inferido / 🔴 no determinable.
> **Artefactos de los WP:** `f0-wp1-wp2-arquitectura.md` (inventario + estático), `f0-wp1-frontend.md`, `f0-wp3-deriva-modelo.md`, `f0-wp4-wp5-suites.md`, `f0-wp6-seguridad-base.md` (+ Anexo A), `f0-wp7-acoplamiento.md` — todos en `docs/qa/informes/`.

---

## 1. Veredicto

# **A — REFACTOR** (mantener lo construido; imponer fronteras, RLS, contratos e invariantes; completar el retiro del legacy vía cutover)

Justificación con evidencia (refutable por un tercero repitiendo los comandos citados):

| Criterio (sección 7 de la misión) | Evidencia F0 | Cumple |
|---|---|---|
| A1. Modelo de datos y garantías duras sólidos | 3 `EXCLUDE` gist en `nucleo.reservas_recurso` (`0004:744-757`, verificados en `pg_constraint`); ~90 CHECK; 32 FKs compuestas `(empresa_id, col)`; dinero `numeric` (0 columnas float, verificado en `information_schema`); 100 % `timestamptz`; 28/31 tablas con auditoría append-only; concurrencia probada con 2 conexiones reales (23P01, `0015_02_concurrencia_rampla.py`) | ✅ |
| A2. Acoplamiento acotado y corregible con interfaces | 13/14 servicios del núcleo con 0 dependencias a otros servicios; 0 inversiones servicio→ruta; 0 imports nucleo→legacy; el único punto denso es `nucleo.viajes` (7 escritores) coordinado con optimistic lock `version` (`servicio_disponibilidad.py:1486-1509`) | ✅ |
| A3. Capa de servicios rescatable sin reescribir lógica | Matriz WP-7: disponibilidad/comercial/expediente/gastos/maestros/conductor/permisos **RESCATABLES**; ≤10–15 % del núcleo requiere cirugía no trivial; la lógica única legacy que vale trasladar es ≤20 % (comisión de liquidaciones, fórmulas kpi_engine, import CSV) | ✅ |
| A4. Suites reproducibles o casi | `make unit` 52 ✓ · `make test` 100 ✓ (pre y post reset) · E2E 9/9 ✓ · SQL 0015/0016 ✓ · reset+seed reproducido en 27 s con 19 migraciones | ✅ (brechas de CI aparte, §5) |
| B1. Solo 1–2 componentes sistémicamente entrelazados | No se cumple al revés: el entrelazamiento NO es sistémico; los candidatos a "rehacer" (facturación, alertas) son RESCATABLES CON CIRUGÍA (defectos puntuales F-01/F-03) — rehacerlos costaría más que arreglarlos | ❌ no aplica |
| C1. Deriva estructural generalizada o modelo que no soporta multiempresa/RLS | Refutado: `empresa_id` en todas las tablas tenant, FKs compuestas, RLS **habilitado** en 31/31 tablas (faltan políticas y un rol sin bypass — eso es una ADICIÓN, no una reconstrucción); deriva modelo↔DDL es de constraints/triggers (documental), no estructural | ❌ refutado |

**Por qué no B:** ningún componente del destino (núcleo) alcanza el umbral de "sistémicamente entrelazado" que haría más barato rehacerlo que refactorizarlo. Los defectos de facturación (`crear_promesa` sin traducción, ausencia de slot DTE) son cirugías acotadas. **Por qué no C:** el modelo de datos ya soporta multiempresa estructuralmente, las garantías duras existen y se probaron, y las suites se reproducen desde cero; reconstruir sería destruir valor demostrado para volver a pagarlo.

**Matiz importante (no es B):** el **legacy** no se refactoriza ni se reconstruye: se **retira** vía el cutover ya diseñado (`scripts/cutover_legacy.py`, `docs/operacion/cutover.md`). Sus piezas únicas (comisión de liquidaciones, motor KPI, import CSV) se **reimplementan** en el núcleo como parte del cierre de plataforma — trabajo nuevo dentro de la opción A, no una reconstrucción del sistema.

### Esfuerzo / riesgo / impacto / reversibilidad por opción

| Opción | Alcance | Esfuerzo est. | Riesgo | Reversibilidad |
|---|---|---|---|---|
| **A (recomendada)** | RLS (políticas + rol de app sin `rolbypassrls`) · fail-closed cutover (F-01) · traducción SQLSTATE→HTTP completa (F-03) · idempotencia en dinero (promesas/anticipos) · magic bytes uploads (F0-05) · DEBUG=false · dependencias (starlette/pyjwt/undici/zod) · CI con PostgreSQL · completar cutover/retiro legacy · seams para conectores (DTE/pagos) cuando se necesiten | **6–10 semanas** (equipo con `datos`+`backend`+`qa`) | Bajo-medio; cada paso es aditivo o cirugía pequeña | Alta: cada cambio es independiente y reversible |
| B | A + reconstruir 1–2 módulos (facturación y/o alertas) | +4–6 semanas sin evidencia de beneficio | Medio: rehacer código verde y probado | Media |
| C | Reconstrucción total | 6+ meses | Alto: perdería EXCLUDE/triggers/auditoría ya probados y la suite verde | Baja |

**Condiciones del veredicto A:** (1) antes de sumar un segundo tenant: políticas RLS + rol de aplicación sujeto a RLS (INV-T01); (2) antes de cualquier ventana de cutover real: fail-closed (RA-04); (3) la decisión de "un escritor por tabla" como regla de frontera para `viajes` (hoy 7 escritores con locks, ver `f0-wp7-acoplamiento.md` §1.3); (4) CI con PostgreSQL antes de considerar "verde" cualquier rama.

---

## 2. Método, entorno y límites

- **Método:** WP-0 preflight propio; WP-1/2/7 por `arquitectura` (lectura estática); WP-1-FE por `frontend`; WP-3 por `datos` (catálogo DB + migraciones); WP-4/5 por `qa` (ejecución real de suites + reset autorizado); WP-6 por `auditor-seguridad` (lectura + HTTP vivo) con herramientas ejecutadas por el orquestador (Anexo A). El orquestador verificó personalmente las afirmaciones críticas: RA-13 (`conftest.py:63-65`, `test_reglas_negocio.py:114-120`), estado de migraciones (14 registradas / 19 en disco), RLS (31 tablas, 0 políticas, `rolbypassrls=t`), DEBUG (`config.py:11`).
- **Entorno real:** Supabase local healthy (`supabase_db_TRANSTEI` :54322; kong :54321; studio :54323); backend :8000; frontend :3000; macOS; `python3` 3.15.2 del sistema; `.venv` con python 3.13.16 (pip roto por renombre de carpeta, ver Anexo A.5); `psql`/`uv` no disponibles (usado `docker exec … psql`).
- **Límites:** sin cambios de código/migraciones/config; sin lectura de valores `.env`; reset local ejecutado 1 vez con autorización; staging/producción no tocados; pruebas de mutación de garantías **no ejecutadas** (fuera de alcance F0, ver §8).

---

## 3. Inventario y mapa (resumen; detalle en `f0-wp1-wp2-arquitectura.md`)

- **Backend:** 25 routers (12 legacy + 13 núcleo) montados en `backend/app/api/router.py:32-56`; prefijo `/api/v1`; 15 servicios (14 núcleo + `kpi_engine`); 46 modelos `table=True` (16 `public`, 30 `nucleo`).
- **Datos:** 19 migraciones en disco (`0001`–`0019`); 17 tablas `public`, 31 `nucleo`.
- **Frontend:** 28 pantallas `page.tsx`; 13 usan cliente legacy `lib/api.ts`, 13 `lib/nucleo.ts`, 2 sin cliente; 0 `fetch` directo; **0 `any`** en `src`; 100 tipos declarados; `tsc --noEmit` limpio.
- **Duplicidades de concepto (dos escrituras simultáneas):** clientes, choferes, tractos, ramplas, viajes, facturas, cobranza (tabla en `f0-wp1-wp2-arquitectura.md` §1.5). Sin mecanismo de sincronización ni reconciliación (grep = 0).
- **Tests:** 22 archivos backend; 10 en `supabase/tests` (7 SQL, 1 concurrencia py, README, mutacion.md); 1 spec E2E (9 tests).

## 4. Hallazgos principales (ID, severidad, evidencia, impacto)

### Código / arquitectura (WP-2, detalle en `f0-wp1-wp2-arquitectura.md`)

| ID | Sev. | Hallazgo | Evidencia | Impacto |
|---|---|---|---|---|
| F-01 | Alta | Cutover fail-open + caché TTL 5 s por instancia | `servicio_cutover.py:38-39`, `:17,24-26` | El congelamiento legacy cae en silencio ante error de DB |
| F-02 | Alta | Dos escritores por concepto sin reconciliación | `0019:40`, `0015:122`; grep reconciliación = 0 | Doble facturación / doble asignación posibles |
| F-03 | Media | `IntegrityError` global → 400 genérico; legacy y `crear_promesa` sin traducción | `main.py:64-74` vs `errores.py:135-186`; `servicio_facturacion.py:708-709` | Mensajes engañosos; viola AGENTS.md §8 |
| F-04 | Media | `float()` en dinero (KPIs legacy) | `kpi_engine.py:442-458,503-520` | Pérdida de centavos en KPIs/rentabilidad |
| F-05 | Media | `DEBUG=True` default + `echo=True` SQL | `config.py:11`, `database.py:22` | SQL con datos sensibles en logs si no se fuerza false |
| F-08 | Baja | 57 `except Exception` amplios, 3 con swallow silencioso | `kpis.py:62-63`, `servicio_cutover.py:73-75`, `settings_db.py:15` | Fallos invisibles (contador de viajes abiertos = 0) |
| F-09 | Baja | Permiso cruzado de dominio (diésel bajo `comercial:escribir`) | `api_gastos.py:71` | Acoplamiento de permisos |
| F-10 | Info | Legacy sin capa de servicio; lógica y commit en rutas | `catalogos.py:51-54`, `facturas.py:169` | Dificulta idempotencia y auditoría legacy |

### Datos (WP-3, detalle en `f0-wp3-deriva-modelo.md`)

| ID | Sev. | Hallazgo | Evidencia |
|---|---|---|---|
| D-01 | **Alta** | **Ledger de migraciones desincronizado del esquema físico**: registra 0001–0014, pero la base ya contiene objetos de 0015/0016/0017 (triggers, funciones, defaults) y el backfill de 0015 (3 reservas `creado_por='migracion_0015'`). Causa 🔴 no determinable. | `schema_migrations` = 14 filas; `pg_trigger` tiene `trg_viajes_05_documentos`, `trg_viajes_03_licencia_a5`; `dias_alerta_documentos`=14; `porcentaje_comision`=0.10 |
| D-02 | Alta | Constraints de disponibilidad invisibles en modelos (EXCLUDE, `ck_viaje_ventana`, `ck_reserva_*`) — deriva documental | `models.py` vs `0004:666,671,744-757` |
| D-03 | Media | `cutover_control` sin modelo y **sin auditoría** | `0014:8-15`; `pg_trigger` = 0 filas |
| D-04 | Media | UNIQUE de RUT/patente: semántica distinta modelo (columna pura) vs DDL (funcional normalizado) | `models.py:261` vs `0004:184` |
| D-05 | — | **RLS:** 31/31 tablas `nucleo` con `rowsecurity=true`, **0 políticas**, 0 FORCE; backend conecta como `postgres` (`rolbypassrls=t`) → RLS inerte; aislamiento vive solo en servicio | `pg_policies`=0; `pg_roles`; `Makefile:6` |
| D-06 | — | Auditoría: 28/31 tablas nucleo; sin `cutover_control`, `folio_contador`, `transiciones_viaje`; `public` sin auditoría | `0004:890`, `0007`; `0001:235-243` |
| D-07 | — | `fk_reserva_viaje` sin `empresa_id` (única FK no compuesta en tenant) | `0004:727-728` (INV-T02 parcial) |
| D-08 | — | Legacy: `public.viajes` guarda eventos en `date`; sin `UNIQUE(numero_sii)`; sin CHECK `total=neto+iva` | `information_schema`; `__init__.py` |

### Seguridad (WP-6 + Anexo A, detalle en `f0-wp6-seguridad-base.md`)

| ID | Sev. | Hallazgo | Evidencia |
|---|---|---|---|
| F0-02 | Media | Aislamiento multiempresa sin respaldo en base (control real = filtros de servicio consistentes, 100+ consultas) | 0 políticas RLS; sin `SET ROLE`; `deps.py:43-82` |
| F0-04 | Media | `legacy_congelado()` fail-open (= F-01) | `servicio_cutover.py:38-39` |
| F0-05 | Media | Uploads sin magic bytes; `read()` completo en memoria; content-type del cliente | `storage.py:21-31`; `api_pod.py:60-68` |
| F0-01 | Media | DEBUG=True + echo SQL (= F-05) | `config.py:11` |
| F0-07..13 | Baja/Info | Sin `issuer` en JWT, sin rate limit, sin cabeceras Next, CSV sin protección de fórmulas, `/docs` expuesto, CORS con comodines | ver informe |
| A-A | 🟡 | **pip-audit: 50 CVEs en 4 paquetes** (starlette 0.46.2, pyjwt 2.10.1, python-multipart 0.0.20, pytest dev) | Anexo A.2 |
| A-B | 🟡 | **npm audit: 12 vuln (7 high undici, 1 critical `next@16.3.7`; zod high)** — corregido en Ola 3: **12→3** (0 critical/high/moderate; 3 low en CLI de desarrollo) | Anexo A.3 |
| A-C | — | SAST bandit: **0 high / 0 med / 2 low** (B110 justificados) | Anexo A.1 |
| A-D | — | Sin secretos hardcodeados en producto (grep = 0); anon key solo en `client.ts` (pública); sin claves de servicio en frontend | WP-6 controles 🟢 |
| — | 🟢 | Auth sólida: JWKS RS256/ES256, aud `authenticated`; 12/12 routers legacy y 13/13 módulos núcleo con dependencia de auth/permiso; `X-Empresa-ID` obligatorio + membresía; 401 real verificado en vivo | `security.py:13-42`; GET `/api/v1/viajes` sin token → 401 |

### Frontend (WP-1-FE, detalle en `f0-wp1-frontend.md`)

| ID | Sev. | Hallazgo | Evidencia |
|---|---|---|---|
| F0F-01 | Media | 5 pares de pantallas solapadas sin canónica ni deprecación; `facturacion` y `cobranzas` mutan el mismo endpoint | `navigation.ts:44-99`; `facturacion/page.tsx:169` vs `cobranzas/page.tsx:96` |
| F0F-02 | Media | 403 indistinguible de error genérico (ninguna página lee `status`/`codigo`) | grep `403` = 0 en páginas |
| F0F-03 | Media | 41 llamadas sin tipo explícito (`unknown` silencioso) | contadores §3 del informe |
| F0F-04..08 | Baja/Info | `API_URL` hardcodeado localhost, token en localStorage, sin Idempotency-Key, `/`→dashboard legacy, sin canónica | ver informe |

### Acoplamiento (WP-7, detalle en `f0-wp7-acoplamiento.md`)

- `nucleo.viajes`: **7 escritores** (5 servicios + 2 scripts), con optimistic lock salvo `servicio_rentabilidad.py:400-416` (update sin `version`).
- `viaje_eventos`: 4 escritores (append-only, acoplamiento de registro).
- `public.clientes`/`choferes`: 2 rutas legacy escriben sin coordinación.
- **0 hooks/interfaces/slots** para conectores (DTE/SII, pagos): integrar exige tocar el cuerpo del servicio; los únicos puntos de extensión son triggers de BD (probados).
- `scripts/cutover_legacy.py` escribe 9 tablas núcleo por SQL directo, **bypaseando permisos, triggers de validación y auditoría**; crea tarifas/OC sintéticas `MIG-*` (escalado al dueño, ver §7).
- Rescatabilidad: núcleo ≥85 % rescatable (≤10–15 % cirugía); legacy: solo ≤20 % de lógica única vale trasladar.

## 5. Suites: salida real (WP-4/5, detalle en `f0-wp4-wp5-suites.md`)

| Suite | Entorno | passed | failed | skipped | Estado |
|---|---|---|---|---|---|
| `make unit` | sin BD | 52 | 0 | 0 | 🟢 ×2 corridas, estable |
| `make test` (pre-reset) | Supabase local, ledger 0014 | 100 | 0 | 0 | 🟢 (3,46 s) |
| SQL `supabase/tests` 0015/0016 | psql vía docker exec | 6 archivos OK | 0 | 0 | 🟢 |
| `0015_02_concurrencia_rampla.py` | **2 conexiones reales** | OK (EXCLUDE 23P01) | 0 | 0 | 🟢 |
| `make e2e` (pre-reset) | :3000 + :8000 | 9 | 0 | 0 | 🟢 (12,6 s) |
| `make db-reset` | autorizado 1 vez | 19 migraciones + seed | — | — | 🟢 (27 s) |
| `make test` (post-reset) | 19 migraciones | 100 | 0 | 0 | 🟢 (3,24 s) |
| SQL 0015/0016 (post-reset) | ídem | OK | 0 | 0 | 🟢 |
| `make e2e` (post-reset) | ídem | 9 | 0 | 0 | 🟢 (12,4 s) |

**Sin skips ocultos** (0 skipped en todas las suites). Fallos: ninguno.

**Aislamiento de tests (hallazgo Alto, confirmado con prueba de lock):** `make test` escribe en la base de la aplicación por doble vía — `NUCLEO_TEST_DATABASE_URL` (default `Makefile:6,65`) y `settings.DATABASE_URL` leído de `backend/.env` (`conftest.py:61-67`, `test_reglas_negocio.py:114-120`). El test R-01 se bloqueó 7,77 s contra `public.choferes` local. Cada `make test` deja **13 empresas TEST- + 16 viajes + reservas** sin limpieza (`test_nucleo_integracion.py:82-259` commitea; `:275-276` no borra); pre-reset había 393 empresas y 471 viajes acumulados. Hoy es seguro solo porque `.env` apunta a `127.0.0.1:54322` (verificado): **no ejecutar `make test` con un `.env` que apunte a la nube** (RA-13 sigue abierto).

## 6. Reproducibilidad y brechas de CI (WP-5/WP-10)

**Reproducible en local:** reset → 19 migraciones aplicadas → seed OK → suites verdes (27 s). Desde un clon limpio falta documentar la corrección del venv (Anexo A.5: el `.venv` tiene pip roto por renombre de carpeta).

**Brechas de CI (`.github/workflows/ci.yml`, leído):**
1. 🔴 **No levanta PostgreSQL**: el job backend corre `python -m pytest` sin servicio de base (`ci.yml:30`); todo lo no-unitario queda skip → un CI verde no cubre integración.
2. 🔴 **No aplica migraciones** (no hay Supabase CLI ni contenedor Postgres en el workflow).
3. 🔴 **No corre E2E** (job frontend solo `lint` + `build`, `ci.yml:47-50`).
4. ~~`HEAD` solo contiene 3 de 19 migraciones~~ → **CORREGIDO (2026-10-29):** las 19 migraciones **sí están commiteadas** (`git ls-tree HEAD supabase/migrations/` = 19; commit `de0d6d3`). La cifra "3 en HEAD" de `docs/estado.md` era una medición errónea (`git ls-tree` sin slash cuenta la línea del árbol, no los archivos). Un clon limpio sí reproduce el esquema.

**Cambios pendientes para cerrar el gate (NO ejecutados en F0 porque requieren tocar CI/config):** job CI con servicio `postgres:17` + aplicar `supabase/migrations/*` (o Supabase CLI) + `NUCLEO_TEST_DATABASE_URL` a base de test dedicada + pytest sin skip de integración; `DEBUG=false` por entorno; base de test separada para que los tests no escriban en la base de la app.

## 7. Decisiones pendientes y preguntas al dueño

| # | Pregunta / decisión | Destinatario | Bloquea |
|---|---|---|---|
| D-1 | ~~Ratificar el veredicto A (REFACTOR)~~ → **RATIFICADO por el dueño (2026-10-29)**; las condiciones de §1 quedan como obligaciones de fase 1 | Dueño | Cerrada |
| D-2 | ¿El bypass de `scripts/cutover_legacy.py` (escribe 9 tablas núcleo sin permisos/triggers/auditoría, crea tarifas/OC `MIG-*` sintéticas) está aprobado para el cutover real, o se exige rehacerlo pasando por los servicios? | Dueño / `arquitectura` | Cutover real |
| D-3 | ¿Cuándo habrá un segundo tenant? De eso depende la urgencia de RLS (INV-T01): políticas + rol de app sin `rolbypassrls` | Dueño | RLS |
| D-4 | ~~Autorizar commit de migraciones~~ → **CERRADA (2026-10-29):** las 19 migraciones ya están commiteadas (`de0d6d3`); la afirmación previa de "3/19 en HEAD" era una medición errónea | Dueño | Cerrada |
| D-5 | ¿Autorizas la fase siguiente (corrección de F-01, F-03, DEBUG, dependencias, CI con PostgreSQL)? | Dueño | Fase 1 |
| D-6 | Causa de la desincronización del ledger de migraciones (D-01): ¿hubo aplicación manual de 0015–0017 fuera de `schema_migrations`? | Dueño / quien operó la base | Higiene de migraciones |
| D-7 | Reglas tributarias pendientes ya registradas en `docs/negocio/preguntas.md` (IVA/DTE/SII): sin fuente, no se asumen | Contador | Facturación DTE |
| D-8 | `test_reglas_negocio.py:4` docstring obsoleto ("11 passed"; real 14) y README de `supabase/tests` desactualizado (superusuario `supabase_admin`, no `postgres`) | `qa` | Cosmético |

## 8. Lo que NO se pudo verificar 🔴 y por qué

| Ítem | Motivo | Cómo se cierra |
|---|---|---|
| Mutación de garantías 0015/0016 (retirar el mecanismo y ver la prueba fallar) | Fuera del alcance F0 (solo ejecutar suites; no tocar mecanismos) | Fase 1 con copia desechable |
| Políticas del bucket `respaldos` de Storage | Requiere consola Supabase/SQL específico | `auditor-seguridad` en fase 1 |
| Headers de seguridad en runtime de Next 16 | `next.config.ts` vacío; defaults no verificables sin deploy | curl al frontend desplegado |
| Comportamiento runtime del fail-open (F-01) | Inferido del código; requiere prueba de fallo con DB caída | `qa` (prueba roja) en fase 1 |
| Rol efectivo de conexión en producción | `backend/.env` local apunta a localhost; el rol de nube no se lee | Operación al desplegar |
| CI real en GitHub Actions | No ejecutado; inferido del `ci.yml` | Push de una rama de prueba (requiere autorización) |
| Severidad individual de los 50 CVEs de pip-audit y los 12 de npm | Reporte agregado; requiere desglose por advisory | Fase 1 con `pip-audit --format json` / `npm audit --json` |
| Causa raíz de D-01 (ledger desincronizado) | Sin registro en el repo | Pregunta D-6 |

## 9. Estado del gate de aceptación de F0

- [x] Informe con evidencia y veredicto justificado (este documento + 6 artefactos).
- [x] La suite corre desde cero y se reproduce (reset + seed + verdes, §5).
- [ ] Los tests **no** escriben en la base de la aplicación → **NO CUMPLIDO**: escriben (RA-13 demostrado con lock de 7,77 s). Corrección pendiente (base de test dedicada).
- [ ] CI levanta PostgreSQL y aplica migraciones → **NO CUMPLIDO**: `ci.yml` no tiene PostgreSQL. Corrección pendiente.
- [x] No hay secretos expuestos en el informe.
- [x] 0 hallazgos críticos/altos sin declarar (todos los altos están declarados: F-01, F-02, D-01, D-02, aislamiento de tests; los 1 critical + 7 high de dependencias declarados).
- [x] El dueño ratificó el veredicto → **RATIFICADO (2026-10-29)** (D-1 cerrada).

**F0 CERRADA (2026-10-29, con ratificación del dueño).** Dos ítems del gate no eran ejecutables dentro de F0 (F0 prohíbe modificar tests y CI) y quedan **transferidos a fase 1 como obligaciones vinculantes del veredicto A**, con trazabilidad:
1. **Base de test dedicada** (hoy los tests escriben en la base de la app) → RA-13 en `docs/estado.md` §5.
2. **CI con PostgreSQL + migraciones + integración** → brecha registrada en §5 de este informe y `docs/estado.md` §4.
Ambos deben cerrarse antes de declarar "verde" la primera rama de fase 1. El resto de los ítems del gate está cumplido.

## 10. Rollback de F0

F0 no modificó código ni datos productivos. Únicos efectos: base local reseteada con seed (estado: 19 migraciones + datos ficticios de `scripts/seed_local.py`; reversión: volver a `make db-reset`, o restaurar backup si existía uno previo al reset — no había), y 7 archivos nuevos bajo `docs/qa/informes/` + edición de `docs/estado.md` (reversión: `git rm` de los informes / revertir el diff de `docs/estado.md`). No se tocaron `docs/INDEX.md` ni `docs/PLAN_DESARROLLO.md` (trabajo ajeno sin commitear).
