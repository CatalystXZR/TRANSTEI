# Módulos y pantallas — qué existe y quién lo sirve

> **Pregunta que responde:** ¿qué pantallas, routers, servicios y permisos existen hoy, y cuáles están duplicados entre legacy y núcleo?
> **Dueño:** arquitectura · **Verificado:** 2026-10-29 · **Método:** lectura estática de `backend/app/api/router.py`, `backend/app/api/routes/*`, `backend/app/nucleo/api_*.py` y de los 28 `page.tsx`; sin ejecución.
> **Caduca si:** se agrega o retira un router, una pantalla o un permiso; o si cambia un prefijo HTTP.
> **Re-verificar con:** `grep -c include_router backend/app/api/router.py` y `find frontend/src/app -name page.tsx | wc -l`

---

## 1. Composición verificada

| Capa | Routers montados | Cliente HTTP | Pantallas |
|---|---|---|---|
| Legacy `public` | 12 (`router.py:32-43`) | `frontend/src/lib/api.ts` | 13 de negocio |
| Núcleo `nucleo` | 13 (`router.py:44-56`) | `frontend/src/lib/nucleo.ts` | 13 de negocio (incluye PWA) |
| Autenticación / navegación | — | Supabase Auth | 2 (`login`, raíz) |
| Total | **25** `include_router` | 2 clientes | **28** `page.tsx` |

Los clientes no declaran endpoints: `api` y `nucleo` son envoltorios genéricos (`api.ts:37-46`; `nucleo.ts:89-106`). Cada pantalla arma su ruta y su tipo. Los tipos del frontend viven en `frontend/src/types/`; no hay contrato compartido generado desde OpenAPI.

---

## 2. Legacy (`public`) — 12 routers

| # | Router | Endpoints principales | Lógica / servicio | Tablas que escribe | Permiso | Pantallas |
|---|---|---|---|---|---|---|
| L01 | `auth.py` (`/auth`) | `GET /me` (`:10`) | resolución de usuario en `api/deps.py:9-28` | lee `public.usuarios` | autenticado | bootstrap global (`auth-context.tsx:59`) |
| L02 | `catalogos.py` | CRUD `/clientes`, `/choferes`, `/tractos`, `/ramplas` (`:27-288`) | validaciones en el router | `clientes`, `choferes`, `tractos`, `ramplas` | lectura: autenticado; escritura: admin/operación (`:20-21`) | `/clientes`, `/choferes`, `/flota`, `/viajes` |
| L03 | `viajes.py` | `/viajes` CRUD, `PATCH /{id}/estado`, `GET /{id}/rentabilidad`, `POST /preview-rentabilidad` (`:118-348`) | reglas en router + `kpi_engine` (`:29`) | `viajes`; lee catálogos y gastos | lectura: autenticado; escritura: admin/operación (`:33-34`) | `/viajes`, `/viajes/[id]` |
| L04 | `gastos.py` | `GET/POST /viajes/{id}/gastos`, `DELETE /gastos/{id}`, `GET /gastos/{id}/respaldo` (`:42-122`) | router; Storage `respaldos` | `gastos_viaje` | lectura: autenticado; escritura: admin/operación (`:17-18`) | `/viajes/[id]` |
| L05 | `dashboard.py` (`/dashboard`) | `GET /resumen`, `GET /alertas` (`:42-178`) | router; lee viajes/facturas/gastos | ninguna (solo lectura) | autenticado (`:26`) | `/dashboard` |
| L06 | `facturas.py` | CRUD `/facturas`, `PATCH /{id}/estado` (`:73-263`) | router; asocia viajes y los marca facturados | `facturas`, `factura_viaje`, `viajes` | lectura: autenticado; escritura: admin/operación/contabilidad (`:31-32`) | `/facturacion` |
| L07 | `finanzas.py` | `GET /facturacion/fletes-por-facturar`, `/cobranzas`, `/iva/resumen` (`:27-185`) | router + `get_config` | ninguna (solo lectura) | autenticado (`:24`) | `/facturacion`, `/cobranzas`, `/iva` |
| L08 | `mantenimiento.py` | CRUD `/pautas`, `/mantenimientos`, `GET /mantenimiento/estado` (`:28-228`) | router | `pautas_mantenimiento`, `mantenimientos`, actualiza `tractos.km_actual` | lectura: autenticado; escritura: admin/operación (`:21-22`) | `/mantenimiento` |
| L09 | `liquidaciones.py` | `/anticipos`, `/ajustes`, `/liquidaciones/calcular`, `/emitir`, `GET /{id}/pdf` (`:102-533`) | `_comision_chofer` (`:51-96`) + reglas en router | `anticipos_chofer`, `ajustes_liquidacion`, `liquidaciones`; lee viajes/facturas | admin/contabilidad en lectura y escritura (`:33-34`) | `/liquidaciones` |
| L10 | `configuracion.py` (`/configuracion`) | `GET ""`, `PUT /{clave}` (`:14-40`) | router; claves permitidas en `:30` | `configuracion` | lectura: autenticado; escritura: admin (`:10-11`) | `/configuracion`, `/facturacion` |
| L11 | `export.py` (`/export`) | CSV de viajes/facturas/liquidaciones; `POST /import/clientes`, `/import/choferes` (`:49-272`) | router + `csv.DictWriter` | import escribe `clientes`/`choferes` | lectura: autenticado; escritura: admin/operación (`:25-26`) | `/viajes`, `/facturacion`, `/liquidaciones`, `/clientes`, `/choferes` |
| L12 | `kpis.py` | catálogo, valores, preview, CRUD de KPIs (`:38-204`) | `services/kpi_engine.py` | `kpis` | lectura: autenticado; escritura: solo admin (`:14-15`) | `/kpis`, `/dashboard` |

---

## 3. Núcleo (`nucleo`) — 13 routers

| # | Router | Endpoints principales | Servicio | Tablas que escribe | Permiso | Pantallas |
|---|---|---|---|---|---|---|
| N01 | `api.py` (`/nucleo`) | empresa, mis-empresas, opciones, `POST/GET /viajes`, disponibilidad, `POST /viajes/{id}/asignar` (`:61-189`) | `servicio_disponibilidad.py` | `viajes`, `reservas_recurso` (vía trigger), `auditoria` | `operacion:leer` / `operacion:escribir` (`:47-58`) | `/despacho` + diálogo nuevo viaje |
| N02 | `api_maestros.py` | CRUD clientes/tractos/ramplas/choferes; documentos y URL firmada (`:57-247`) | `servicio_maestros.py` | `clientes`, `tractos`, `ramplas`, `choferes`, `documentos` | `maestros:leer` / `maestros:escribir` (`:42-49`) | `/maestros` |
| N03 | `api_comercial.py` | centros de costo, tarifas e historial, OC y líneas, sobregiro (`:67-300`) | `servicio_comercial.py` | `centros_costo`, `tarifas`, `ordenes_compra`, `ordenes_compra_lineas` | `comercial:leer` / `escribir` / `aprobar` (`:45-59`) | `/comercial` |
| N04 | `api_bloqueos.py` | CRUD bloqueos y cancelación; `GET /agenda` (`:40-86`) | `servicio_bloqueos.py` | `reservas_recurso` (no-viaje) | `agenda:leer` / `agenda:escribir` (`:28-35`) | `/agenda` |
| N05 | `api_expediente.py` (`/nucleo/expediente`) | listado/detalle, QR, cierre, paradas, checklist, eventos, incidentes, documentos (`:50-263`) | `servicio_expediente.py` | `viaje_paradas`, `viaje_checklist`, `viaje_eventos`, `viaje_incidentes`, `viaje_documentos`; `viajes` al cerrar | `expediente:leer` / `expediente:escribir` (`:38-45`) | `/expediente`, `/expediente/[id]` |
| N06 | `api_pod.py` (`/nucleo/expediente/viajes`) | `GET/POST/PUT /{id}/pod` (`:35-87`) | `servicio_pod.py` | `pod` | `pod:leer` / `pod:escribir` (`:23-30`) | `/expediente/[id]` |
| N07 | `api_conductor.py` (`/nucleo/conductor`) | `mi-viaje`, transición, check-in/out (`:29-57`) | `servicio_conductor.py` | `viajes`, `viaje_eventos` | `conductor:usar` (`:24`) | `/conductor` |
| N08 | `api_gastos.py` | precios diésel, gastos del viaje, comprobante, aprobar/rechazar, costos (`:48-144`) | `servicio_gastos.py` | `precios_diesel`, `viaje_gastos`; `viajes.costo_*` vía trigger | `gastos:leer` / `escribir` / `aprobar`; precio con `comercial:escribir` (`:29-43,71`) | `/expediente/[id]` pestaña Gastos |
| N09 | `api_rentabilidad.py` | configuración, simulador, rentabilidad por viaje (`:38-61`) | `servicio_rentabilidad.py` | `configuracion_costos`; lee viajes/gastos/pagos | `rentabilidad:leer` / `configurar` (`:26-33`) | `/rentabilidad`, panel en `/expediente/[id]` |
| N10 | `api_facturacion.py` (`/nucleo/cobranza`) | viajes facturables, facturas, pagos, NC, promesas, aging (`:48-124`) | `servicio_facturacion.py` | `facturas_nucleo`, `factura_viajes`, `pagos_nucleo`, `notas_credito_nucleo`, `promesas_pago_nucleo`; `viajes.estado` | `facturacion:leer` / `emitir`, `cobranza:registrar` (`:29-43`) | `/cobranza` |
| N11 | `api_alertas.py` (`/nucleo/alertas`) | `GET /tablero` (`:24`) | `servicio_alertas.py` | ninguna (solo lectura) | `alertas:leer` (`:19`) | `/tablero` |
| N12 | `api_permisos.py` | permisos míos/matriz/verificar; auditoría (`:27-97`) | `permisos.py` + `servicio_auditoria.py` | ninguna (solo lectura) | `roles:leer`, `auditoria:leer` (`:40,68`) | `/permisos`, `/auditoria` |
| N13 | `api_cutover.py` (`/nucleo/cutover`) | estado, congelar, descongelar (`:31-46`) | `servicio_cutover.py` | `cutover_control` | `configuracion:leer` / `configuracion:escribir` (`:19-26`) | `/cutover` |

---

## 4. Las 28 pantallas y su dependencia real

| # | Ruta | Cliente | Llamadas principales | Módulo |
|---|---|---|---|---|
| 1 | `/` | — | redirige a `/dashboard` (`app/page.tsx:1-5`) | navegación |
| 2 | `/login` | Supabase Auth | `signInWithPassword` vía `auth-context.tsx:77-86` | identidad |
| 3 | `/conductor` | `nucleo.ts` | `/nucleo/conductor/*` (`page.tsx:189`) | N07 |
| 4 | `/(app)/despacho` | `nucleo.ts` | viajes, disponibilidad ×3, validar, asignar (`:195-201,299,321`) | N01 |
| 5 | `/(app)/agenda` | `nucleo.ts` | `/nucleo/agenda`, `/nucleo/bloqueos` (`:123-161`) | N04 |
| 6 | `/(app)/expediente` | `nucleo.ts` | `/nucleo/expediente/viajes` (`:110`) | N05 |
| 7 | `/(app)/expediente/[id]` | `nucleo.ts` | expediente, POD, gastos, paradas, eventos, cerrar (`:178-364`) | N05/N06/N08 |
| 8 | `/(app)/maestros` | `nucleo.ts` | `/nucleo/{clientes,tractos,ramplas,choferes,documentos}` (`:100-128`) | N02 |
| 9 | `/(app)/comercial` | `nucleo.ts` | tarifas, OC, centros de costo (`:124-227`) | N03 |
| 10 | `/(app)/rentabilidad` | `nucleo.ts` | configuración, simulador (`:105-166`) | N09 |
| 11 | `/(app)/cobranza` | `nucleo.ts` | facturas, aging (`:118-122`) | N10 |
| 12 | `/(app)/tablero` | `nucleo.ts` | `/nucleo/alertas/tablero` (`:108`) | N11 |
| 13 | `/(app)/auditoria` | `nucleo.ts` | `/nucleo/auditoria`, `/auditoria/tablas` (`:104-108`) | N12 |
| 14 | `/(app)/permisos` | `nucleo.ts` | `/nucleo/permisos/mios`, `/matriz` (`:96-102`) | N12 |
| 15 | `/(app)/cutover` | `nucleo.ts` | estado, congelar, descongelar (`:58-101`) | N13 |
| 16 | `/(app)/viajes` | `api.ts` | `/viajes`, catálogos (`:104-108,165`) | L02/L03 |
| 17 | `/(app)/viajes/[id]` | `api.ts` | viaje, gastos, rentabilidad, estado (`:114-206`) | L03/L04 |
| 18 | `/(app)/clientes` | `api.ts` | CRUD `/clientes` (`:126-144`) | L02 |
| 19 | `/(app)/choferes` | `api.ts` | CRUD `/choferes` (`:127-145`) | L02 |
| 20 | `/(app)/flota` | `api.ts` | tractos y ramplas (`:77-212`) | L02 |
| 21 | `/(app)/mantenimiento` | `api.ts` | estado, pautas, mantenciones (`:111-223`) | L08 |
| 22 | `/(app)/facturacion` | `api.ts` | fletes por facturar, facturas, config (`:94-180`) | L06/L07/L10 |
| 23 | `/(app)/cobranzas` | `api.ts` | `PATCH /facturas/{id}/estado` (`:96`) | L06/L07 |
| 24 | `/(app)/iva` | `api.ts` | `/iva/resumen` (`:55`) | L07 |
| 25 | `/(app)/liquidaciones` | `api.ts` | anticipos, ajustes, calcular, emitir (`:139-225`) | L09 |
| 26 | `/(app)/dashboard` | `api.ts` | resumen, alertas, KPIs (`:52-54`) | L05/L12 |
| 27 | `/(app)/kpis` | `api.ts` | CRUD y preview de KPIs (`:98-247`) | L12 |
| 28 | `/(app)/configuracion` | `api.ts` | `PUT /configuracion/{clave}` (`:54`) | L10 |

---

## 5. Módulos duplicados entre capas

No se decide aquí cuál se retira; se declara **qué hace cada uno y qué tiene de exclusivo**. La fuente canónica por concepto está en [`fuentes-de-verdad.md`](fuentes-de-verdad.md).

| Concepto | Legacy | Núcleo | Exclusivo del legacy | Exclusivo del núcleo | Riesgo |
|---|---|---|---|---|---|
| Viajes / despacho | `/viajes`, `viajes.py` | `/despacho`, `api.py` | histórico, estados `programado/en_ruta/finalizado/facturado`, rentabilidad por viaje, edición libre | disponibilidad, reservas, documentos, 14 estados, OC/tarifa, auditoría | **Dos libros de viajes**; un viaje legacy no existe para el núcleo (RA-02/RA-06) |
| Maestros | `/clientes`, `/choferes`, `/flota` | `/maestros` | importación CSV (`export.py:194-272`) y vencimientos planos | documentos versionados, capacidad/peso, 8 roles, baja lógica | CRUD duplicado; mismo RUT puede existir dos veces con distinto `id` |
| Facturación / cobranza | `/facturacion`, `/cobranzas` | `/cobranza` | IVA interno (`/iva`), factura asociada a viajes finalizados, pago por estado | OC obligatoria, POD, pagos parciales, NC, promesas, aging, folio | Dos tablas de factura y dos criterios de cobro |
| Tablero / KPIs | `/dashboard`, `/kpis` | `/tablero` | motor de KPIs editable y métricas de dinero | alertas operativas (docs, bloqueos, sin POD, sin facturar, OC, margen) | Números distintos con el mismo nombre |
| Mantenimiento | `/mantenimiento` | solo `reserva.tipo_reserva='mantenimiento'` | pauta por km e historial | bloqueo de agenda y alerta de 7 días | No hay preventivo en el núcleo |
| Liquidaciones | `/liquidaciones` | ninguno | comisión, anticipos, ajustes, PDF | solo costo estimado en rentabilidad | El núcleo no puede pagar ni reproducir un documento firmado |
| Rentabilidad | panel en `/viajes/[id]` | `/rentabilidad` + panel por viaje | fórmula KPI configurable | Freight Score, configuración de costos, simulador | Dos definiciones de margen (una resta comisión, la otra no) |

**Regla de convivencia:** una pantalla nueva no se agrega a la capa legacy; una pantalla legacy no se retira mientras tenga una función exclusiva sin equivalente probado (`docs/arquitectura/retiro-legacy.md`).
