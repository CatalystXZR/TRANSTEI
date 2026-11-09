> ⚠️ **Aviso de vigencia (2026-11-01):** cita archivos/cifras anteriores al retiro del legacy (`public`, `lib/api.ts`, `backend/app/api/routes/*`, `kpi_engine.py`). No citar como estado actual; ver `docs/estado.md` §2–§6 y `docs/PLAN_DESARROLLO.md`.

# F0 — WP-1 (inventario) y WP-2 (análisis estático) — Agente arquitectura

> Depositado por el orquestador (2026-10-29): el agente `arquitectura` no tiene permiso de escritura en `docs/qa/informes/`; el contenido es íntegro de su respuesta. F0 es solo lectura.

- Fecha: 2026-10-29
- Rol: arquitectura (misión solo lectura; no se modificó ningún archivo del repo)
- Método: exploración con read/grep/glob (sin shell; ver "No verificado" al final)
- Jerarquía de evidencia: código + migraciones > docs. Niveles 🟢 verificado / 🟡 inferido / 🔴 no determinable.

## 1. Inventario (WP-1)

### 1.1 Conteos

| Componente | Cantidad | Evidencia |
|---|---|---|
| Routers montados | 25 (12 legacy + 13 nucleo) | `backend/app/api/router.py:32-56` 🟢 |
| Prefijo global API | `/api/v1` | `backend/app/core/config.py:10`, `backend/app/main.py:33` 🟢 |
| Servicios | 15 (14 nucleo + 1 legacy `kpi_engine`) | `backend/app/nucleo/servicio_*.py` (14) + `backend/app/services/kpi_engine.py` 🟢 |
| Modelos `table=True` | 46 (16 public + 30 nucleo) | `backend/app/models/__init__.py:67-276` (16) + `backend/app/nucleo/models.py:198-1344` (30) 🟢 |
| Migraciones en disco | 19 (0001–0019) | `supabase/migrations/` 🟢 |
| Migraciones aplicadas en DB local | 14 (máx 0014) | verificado por el orquestador (2026-10-29) 🟢 |
| Pantallas (`page.tsx`) | 28 | `frontend/src/app/**/page.tsx` 🟢 |
| Tests backend | 22 archivos | `backend/tests/*.py` 🟢 |
| Tests Supabase SQL/Py | 10 archivos (7 `.sql`, 1 `.py`, fixtures, README, mutacion.md) | `supabase/tests/` 🟢 |
| Tests E2E | 1 spec | `frontend/e2e/tei.spec.ts` 🟢 |

### 1.2 Routers legacy (`backend/app/api/routes/`)

| Router | include_router | Prefijo | Auth declarada | Servicio/logica | Endpoints principales |
|---|---|---|---|---|---|
| auth | `router.py:32` | `/auth` (`auth.py:7`) | `get_current_user` | — | GET `/me` (`auth.py:10`) |
| catalogos | `router.py:33` | — (`catalogos.py:18`) | lectura+escritura (`catalogos.py:20-21`) | lógica inline + `app.models` | `/clientes`, `/choferes`, `/tractos`, `/ramplas` CRUD |
| viajes | `router.py:34` | — (`viajes.py:31`) | lectura+escritura (`viajes.py:33-34`) | lógica inline + `app.models` + `kpi_engine` (`viajes.py:29`) | `/viajes` CRUD, `/viajes/{id}/rentabilidad`, `/viajes/preview-rentabilidad` |
| gastos | `router.py:35` | — (`gastos.py:15`) | lectura+escritura (`gastos.py:17-18`) | lógica inline | `/viajes/{id}/gastos`, `/gastos/{id}/respaldo` |
| dashboard | `router.py:36` | `/dashboard` (`dashboard.py:24`) | lectura (`dashboard.py:26`) | lógica inline | `/resumen`, `/alertas` |
| facturas | `router.py:37` | — (`facturas.py:29`) | lectura+escritura (`facturas.py:31-32`) | lógica inline | `/facturas` CRUD + `/facturas/{id}/estado` |
| finanzas | `router.py:38` | — (`finanzas.py:22`) | lectura (`finanzas.py:24`) | lógica inline | `/facturacion/fletes-por-facturar`, `/cobranzas`, `/iva/resumen` |
| mantenimiento | `router.py:39` | — (`mantenimiento.py:19`) | lectura+escritura (`mantenimiento.py:21-22`) | lógica inline | `/pautas`, `/mantenimientos`, `/mantenimiento/estado` |
| liquidaciones | `router.py:40` | — (`liquidaciones.py:28`) | lectura Y escritura = `require_roles(admin, contabilidad)` (`liquidaciones.py:33-34`) | lógica inline | `/anticipos`, `/ajustes`, `/liquidaciones/*` |
| configuracion | `router.py:41` | `/configuracion` (`configuracion.py:8`) | lectura + `solo_admin` (`configuracion.py:10-11`) | lógica inline | GET/PUT `""`, PUT `/{clave}` |
| export | `router.py:42` | `/export` (`export.py:23`) | lectura+escritura (`export.py:25-26`) | lógica inline | `/viajes`, `/facturas`, `/liquidaciones`, `/import/clientes`, `/import/choferes` |
| kpis | `router.py:43` | — (`kpis.py:12`) | lectura + `solo_admin` (`kpis.py:14-15`) | `kpi_engine` (`kpis.py:10`) | `/kpis/catalogo`, `/kpis/valores`, `/kpis/preview`, `/kpis` CRUD |

### 1.3 Routers núcleo (`backend/app/nucleo/api_*.py`)

| Router | include_router | Prefijo | Servicio | Permisos usados |
|---|---|---|---|---|
| api (operacional) | `router.py:44` | `/nucleo` (`api.py:44`) | `ServicioDisponibilidad` (`api.py:39-42`) | `operacion:leer/escribir` |
| maestros | `router.py:45` | `/nucleo` (`api_maestros.py:37`) | `ServicioMaestros` | `maestros:leer/escribir` |
| comercial | `router.py:46` | `/nucleo` (`api_comercial.py:40`) | `ServicioComercial` | `comercial:leer/escribir/aprobar` |
| bloqueos | `router.py:47` | `/nucleo` (`api_bloqueos.py:24`) | `ServicioBloqueos` | `agenda:leer/escribir` |
| expediente | `router.py:48` | `/nucleo/expediente` (`api_expediente.py:34`) | `ServicioExpediente` | `expediente:leer/escribir` |
| pod | `router.py:49` | `/nucleo/expediente/viajes` (`api_pod.py:18`) | `ServicioPOD` | `pod:leer/escribir` |
| conductor | `router.py:50` | `/nucleo/conductor` (`api_conductor.py:20`) | `ServicioConductor` | `conductor:usar` |
| gastos | `router.py:51` | `/nucleo` (`api_gastos.py:25`) | `ServicioGastos` | `gastos:leer/escribir/aprobar` (+ `comercial:escribir` en un endpoint, ver F-09) |
| rentabilidad | `router.py:52` | `/nucleo` (`api_rentabilidad.py:22`) | `ServicioRentabilidad` | `rentabilidad:leer/configurar` |
| facturacion/cobranza | `router.py:53` | `/nucleo/cobranza` (`api_facturacion.py:25`) | `ServicioFacturacion` | `facturacion:leer/emitir`, `cobranza:registrar` |
| alertas | `router.py:54` | `/nucleo/alertas` (`api_alertas.py:14`) | `ServicioAlertas` | `alertas:leer` |
| permisos | `router.py:55` | `/nucleo` (`api_permisos.py:24`) | `ServicioAuditoria` | `roles:leer`, `auditoria:leer`, `get_contexto_empresa` |
| cutover | `router.py:56` | `/nucleo/cutover` (`api_cutover.py:14`) | `ServicioCutover` | `configuracion:leer` + solo auth (`api_cutover.py:25`) |

Mecanismo de tenant núcleo: `X-Empresa-ID` + membresía `nucleo.usuarios_empresa` (`backend/app/nucleo/deps.py:43-82`) 🟢. Contexto de auditoría vía `set_config('nucleo.auth_id'/'nucleo.request_id')` en cada servicio escritor (ej. `servicio_comercial.py:107-113`) 🟢.

### 1.4 Pantallas ↔ cliente HTTP (WP-1 punto 4)

**Legacy (`@/lib/api`)**: `configuracion`, `iva`, `flota`, `liquidaciones`, `choferes`, `cobranzas`, `clientes`, `kpis`, `facturacion`, `mantenimiento`, `dashboard`, `viajes`, `viajes/[id]` (13 pantallas; imports verificados en cada `page.tsx`).
**Núcleo (`@/lib/nucleo`)**: `conductor`, `permisos`, `despacho`, `tablero`, `cobranza`, `auditoria`, `maestros`, `comercial`, `cutover`, `rentabilidad`, `expediente`, `expediente/[id]`, `agenda` (13 pantallas).
**Sin cliente HTTP directo** (login/raíz): `login/page.tsx`, `page.tsx` (2).

### 1.5 Duplicidades de concepto (public vs nucleo)

| Concepto | Ruta legacy → tabla | Ruta nucleo → tabla | Dos escrituras |
|---|---|---|---|
| Clientes | `GET/POST /clientes` (`catalogos.py:27,45`) → `public.clientes` | `GET/POST /nucleo/clientes` (`api_maestros.py:57,66`) → `nucleo.clientes` | **SÍ** |
| Choferes | `/choferes` (`catalogos.py:93,111`) → `public.choferes` | `/nucleo/choferes` (`api_maestros.py:168,177`) → `nucleo.choferes` | **SÍ** (divergencia de comisión reconocida en `supabase/migrations/0019_comision_piloto_10.sql:40`) |
| Tractos/Ramplas | `/tractos`, `/ramplas` (`catalogos.py:159,230`) → `public.*` | `/nucleo/tractos`, `/nucleo/ramplas` (`api_maestros.py:94,131`) → `nucleo.*` | **SÍ** |
| Viajes | `POST /viajes` (`viajes.py:152`) → `public.viajes` | `POST /nucleo/viajes` (`api.py:95`) → `nucleo.viajes` | **SÍ** (legacy no escribe `nucleo.reservas_recurso`: `supabase/migrations/0015_viaje_con_recursos_ocupa_y_valida.sql:122`) |
| Facturas | `/facturas` (`facturas.py:73-263`) → `public.facturas` | `/nucleo/cobranza/facturas` (`api_facturacion.py:59-124`) → `nucleo.facturas_nucleo` (`models.py:1134`) | **SÍ** |
| Cobranza | `/cobranzas` (`finanzas.py:65`) → `public.facturas` | `/nucleo/cobranza/*` (`api_facturacion.py`) → `nucleo.pagos_nucleo`, etc. | **SÍ** (lectura distinta + pagos solo nucleo) |
| Dashboard | `/dashboard/resumen` (`dashboard.py:42`) → `public.*` | `/nucleo/alertas/tablero` (`api_alertas.py:24`) → `nucleo.*` | No (solo lectura) |
| Rentabilidad/KPIs | `/viajes/{id}/rentabilidad`, `/kpis/valores` → `public.*` + `kpi_engine` | `/nucleo/rentabilidad/*` (`api_rentabilidad.py`) → `nucleo.*` | No (solo lectura) |
| Sin duplicado | — | `nucleo` exclusivo: OC, tarifas, centros de costo, expediente, POD, bloqueos, conductor, permisos, auditoría | — |
| Sin duplicado | `public` exclusivo: liquidaciones, anticipos, ajustes, mantenimiento, iva, configuracion, kpis CRUD | — | — |

## 2. Hallazgos estáticos (WP-2)

| ID | Severidad | Hallazgo | Evidencia (archivo:línea) | Impacto |
|---|---|---|---|---|
| F-01 | **Alta** | Cutover **fail-open**: si falla la lectura del flag, escrituras legacy quedan ABIERTAS. Además caché local con TTL 5 s sin invalidación entre workers | `servicio_cutover.py:38-39` (`except Exception: congelado = False`), `:17,24-26` (TTL), `:44-46` (invalidar solo proceso local); ausencia de fila → `scalar_one_or_none()` → abierto (`:31-37`) | El bloqueo de escrituras legacy se cae en silencio ante error de DB; ventana ≤5 s (por instancia) tras congelar/descongelar en que el middleware usa estado viejo. Verificado en código 🟢 |
| F-02 | **Alta** | Dos escritores por concepto (clientes/choferes/tractos/ramplas/viajes/facturas) sin **ningún** mecanismo de sincronización o detección de divergencia | grep `reconcil|sincroniz|sync_|cutover_legacy` en `backend/app` = 0 resultados; solo script manual `scripts/cutover_legacy.py`; divergencia reconocida en `0019_comision_piloto_10.sql:40` y `0015...sql:122` | Riesgo de doble facturación (public.facturas vs nucleo.facturas_nucleo) y de reserva legacy sin EXCLUDE (doble asignación de recurso). Verificado 🟢 |
| F-03 | **Media** | Handler global `IntegrityError` → **400** con mensaje genérico, para cualquier IntegrityError no traducido. El núcleo traduce bien (409/422), pero legacy y `crear_promesa` caen al handler | `main.py:64-74` (400 genérico); contraste `errores.py:135-186` (23505→409, 23514→409, 23P01→409, 23503→422); `servicio_facturacion.py:708-709` (commit sin try/except; los bloques previos sí traducen `:612,645,685`); rutas legacy commit sin manejo (ej. `catalogos.py:53`, `facturas.py:169`) | Violación de AGENTS.md §8 (23505/23P01→409; nunca mensajes genéricos). Un duplicado de promesa o RUT legacy devuelve 400 con texto "RUT o patente duplicada" aunque no sea el caso. Verificado 🟢 |
| F-04 | **Media** | Dinero convertido a `float` en el motor de KPIs legacy; usado en rutas vivas de rentabilidad por viaje | `services/kpi_engine.py:442-458, 503-520` (flete, gastos, comisión, margen, IVA a pagar → `float()`); consumido en `kpis.py:61` y `viajes.py:293-337` | Pérdida de precisión de centavos en KPIs y rentabilidad de viaje (solo lectura/pantalla, no persistencia). El resto del backend usa `Decimal` (nucleo: `servicio_comercial.py:92`, legacy: `facturas.py:42-43`). Verificado 🟢 |
| F-05 | **Media** | `DEBUG=True` por defecto en Settings; sin override forzado por entorno | `core/config.py:11`; efecto: `echo=True` del engine → log de SQL (`core/database.py:22`) | En producción, si `.env` no fija DEBUG=false, se loguea todo el SQL (datos sensibles en logs). Verificado 🟢 |
| F-06 | **Baja** | CORS con `allow_methods=["*"]`, `allow_headers=["*"]`, `allow_credentials=True`; sin headers de seguridad (X-Content-Type-Options, HSTS, etc.) | `main.py:25-31`; origins acotados por defecto a localhost:3000 (`config.py:20`) | Exposición limitada a origins configurados; hardening pendiente. Verificado 🟢 |
| F-07 | **Baja** | Legacy sin noción de empresa: 0 coincidencias de `empresa_id` en `api/routes`; cualquier usuario autenticado con rol ve toda la data | grep `empresa_id` en `backend/app/api/routes` = 0 resultados; modelos legacy sin `empresa_id` (`app/models/__init__.py:80-292`) | Coherente con AGENTS.md (legacy no es multiempresa) pero debe declararse: pantallas legacy exponen datos globales a todo usuario con sesión. 🟢 |
| F-08 | **Baja** | `except Exception` amplios, algunos con swallow silencioso: KPIs → `metricas={}` (pantalla vacía sin traza), cutover.estado → `legacy_abiertos=0`, `settings_db.py:15` | `kpis.py:62-63`, `servicio_cutover.py:73-75`, `core/settings_db.py:15`; total 57 ocurrencias en backend | Fallos invisibles en métricas y en el contador de viajes abiertos del estado de cutover (puede sub-reportar 0 y confundir la decisión de congelar). 🟢 |
| F-09 | **Baja** | Endpoint de precio diésel protegido con permiso de otro dominio (`comercial:escribir` en router de gastos) | `api_gastos.py:71` vs `gastos:escribir` en `:36` | Acoplamiento de permisos entre módulos; validar si es intención o error. 🟢 |
| F-10 | **Info** | Legacy sin capa de servicio: lógica de negocio y `session.commit()` viven en las rutas, sin manejo de excepciones ni traducción | `catalogos.py:51-54`, `facturas.py:169`, `viajes.py:176`, `liquidaciones.py:340-356` | Duplica a F-03; dificulta idempotencia y auditoría del legacy. 🟢 |

Nota sobre RLS/tenancy: el orquestador verificó (base local) `nucleo` con 31 tablas `rowsecurity=true`, **0 políticas**, y rol de conexión con `rolbypassrls=t`. El aislamiento multiempresa descansa hoy en el filtrado por `empresa_id` en servicios Python + `set_config` para auditoría; cualquier query que omita el filtro expone datos entre empresas. Riesgo estructural abierto (RA-03 en `docs/estado.md`). 🟢 (verificado por orquestador).

## 3. Contradicciones docs vs código

1. AGENTS.md §8 exige `23505/23P01 → 409`, `23514/23502 → 422`, "nunca 500 por conflicto de negocio ni mensajes crudos". Código: núcleo cumple (`errores.py:135-186`); legacy y excepciones no traducidas → **400** genérico (`main.py:64-74`). La documentación describe el estándar del núcleo, no el comportamiento global. → F-03.
2. Migración `0019_comision_piloto_10.sql:40` reconoce textualmente divergencia de comisión entre `public.choferes` y `nucleo.choferes` y no define reconciliación → deuda documentada, no resuelta.
3. `docs/qa/linea-base.md` y `matriz-trazabilidad.md` no fueron contrastados aquí por alcance (F0 estático); pendiente para qa.

## 4. No verificado / bloqueos

- **Sin shell**: no pude re-ejecutar `psql`, `git status` ni tests. Conteos de DB son verificados por el orquestador (2026-10-29). Todo lo listado con archivo:línea es lectura de código en disco, 🟢.
- **Rol efectivo de `DATABASE_URL`**: no leído (regla de secretos). Solo ubicación: `backend/.env` (no impreso).
- **Comportamiento runtime** (fail-open real del cutover ante DB caída, ventana del caché con múltiples workers): inferido del código; requiere prueba de fallo (qa/datos).
- **Frontend deep-dive** (tipos de contrato en `api.ts`/`nucleo.ts`): fuera de alcance; corresponde al agente frontend (entregado aparte en `f0-wp1-frontend.md`).

## 5. Riesgo residual y siguiente paso

- Los hallazgos F-01, F-02, F-03 requieren decisión de arquitectura (ADR) y no se corrigen en esta misión (solo lectura).
- Sugerido: qa convierta F-01 (fail-open) y F-03 (promesa sin traducción) en pruebas rojas reproducibles; datos evalúe la restricción de compatibilidad public↔nucleo para F-02.
