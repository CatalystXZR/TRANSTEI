> **ARCHIVADO 2026-10-29 — NO CITAR COMO ESTADO.**
> Documento histórico. Reemplazos y contexto: `docs/_archivo/README.md` · Estado real: `docs/estado.md`.
> Sus cifras y afirmaciones de "terminado" NO fueron re-verificadas en esta fecha.

# Plan de desarrollo autónomo — ERP Transportes TEI

**Versión:** 1.0  
**Fecha:** Octubre 2026  
**Modo:** local-first, un módulo a la vez, sin esperar instrucciones salvo bloqueos reales.

---

## 1. Regla de trabajo

No se encienden los 14 módulos a la vez. Se construye **un vertical slice completo** (base de datos → servicio → API → pantalla → pruebas) y solo se avanza cuando el módulo pasa:

1. Implementación completa, sin pseudocódigo ni `TODO`.
2. Pruebas unitarias y de integración en PostgreSQL local.
3. Prueba de API real.
4. Prueba de pantalla real.
5. Ataque deliberado: datos inválidos, fechas naive, solapamientos, permisos, otra empresa, montos límite, concurrencia, estados ilegales.
6. Corrección y re-prueba.
7. Regresión de todos los módulos anteriores.
8. Documentación y actualización de estado.

Si algo requiere una decisión del usuario (legal, datos reales, credenciales, precio, política comercial, UX, migración destructiva), el módulo se marca **BLOQUEADO** con la pregunta exacta y se continúa con el siguiente módulo que no dependa de esa respuesta.

---

## 2. Definición de “módulo terminado” (Definition of Done)

- [ ] Migración/esquema versionado si cambia datos.
- [ ] Modelos y contratos Pydantic estrictos.
- [ ] Servicio transaccional con errores de dominio.
- [ ] Endpoints con roles y `empresa_id` resuelto en backend.
- [ ] Pantalla usable, con estados de carga, vacío y error.
- [ ] Validaciones de negocio en backend y en base.
- [ ] Auditoría de cambios críticos.
- [ ] Pruebas unitarias.
- [ ] Prueba de integración contra PostgreSQL local.
- [ ] Prueba de API/HTTP.
- [ ] Prueba manual de UI.
- [ ] Casos adversariales ejecutados.
- [ ] `ruff`, `tsc`, `eslint`, `next build` sin errores nuevos.
- [ ] Documento del módulo y estado actualizado.

---

## 3. Cuándo se detiene y se pregunta

Solo se deja pendiente un módulo si necesita:

- Una definición legal/tributaria/laboral que no está en los documentos.
- Credenciales o sandbox de un proveedor externo (SII, banco, GPS, combustible, peajes, WhatsApp, firma).
- Datos reales que no se pueden inventar (RUT, patentes, tarifas, OC, contratos).
- Una decisión de negocio (margen objetivo, política de crédito, sobregiro, recargos).
- Una decisión de UX/branding que cambie el flujo.
- Una operación destructiva sobre datos reales.
- Un cambio de alcance o prioridad.

El bloqueo se registra en la tabla de estado con: qué falta, por qué, qué opciones hay y qué módulos se pueden seguir.

---

## 4. Secuencia de módulos

### P0 — Piloto 90 días (primero, en este orden)

| ID | Módulo | Depende de | Estado |
|---|---|---|---|
| P0-01 | Alta de viaje del núcleo + catálogos de apoyo | — | ✅ Terminado y probado |
| P0-02 | CRUD de maestros del núcleo + documentos/Storage | P0-01 | ✅ Terminado y probado |
| P0-03 | OC/tarifas editables y consumo visible | P0-01/02 | ✅ Terminado y probado |
| P0-04 | Bloqueos de mantención/descanso/taller | P0-02 | ✅ Terminado y probado |
| P0-05 | Expediente del viaje: detalle, paradas, checklist, eventos, incidentes | P0-01/02 | ✅ Terminado y probado |
| P0-06 | POD y evidencia | P0-05 | ✅ Terminado y probado |
| P0-07 | PWA del conductor (MVP, offline básico) | P0-06 | ✅ Terminado y probado |
| P0-08 | Gastos, combustible, peajes y costo real | P0-05 | ✅ Terminado y probado |
| P0-09 | Margen, tarifa piso, Freight Score v1 y simulador | P0-08 | ✅ Terminado y probado |
| P0-10 | Facturación/cobranza del núcleo (OC + POD + pagos parciales + aging) | P0-09 | ✅ Terminado y probado |
| P0-11 | Alertas y tablero del dueño del núcleo | P0-10 | ✅ Terminado y probado |
| P0-12 | Roles/permisos y auditoría visible | P0-02 | ✅ Terminado y probado |
| P0-13 | Cutover, seed completo, E2E, backup restore y UAT | P0-01..12 | ✅ Terminado y probado |

### P1 — ERP completo (después del piloto)

| ID | Módulo | Depende de |
|---|---|---|
| P1-01 | Comercial avanzado: contratos, cotizaciones, pricing, OC con líneas | P0-03 |
| P1-02 | Mantenimiento/taller: órdenes, repuestos, inventario, neumáticos | P0-04 |
| P1-03 | Personas: contratos, licencias, exámenes, jornada, pre-nómina | P0-12 |
| P1-04 | Finanzas: CxP, tesorería, caja 13 semanas, conciliación, contabilidad, cierre | P0-10 |
| P1-05 | Compras y proveedores | P1-02/04 |
| P1-06 | Documentos: OCR, firma, versiones, retención, checklist legal | P0-02 |
| P1-07 | BI/KPIs v2: catálogo 90 KPIs, snapshots, metas, reportes | P0-11 |
| P1-08 | Portales cliente/taller | P0-10/P1-06 |
| P1-09 | Integraciones: SII, GPS, combustible, peajes, bancos, WhatsApp, mapas | P1-04/P1-08 |
| P1-10 | Copiloto TEI: RAG, consultas, acciones con aprobación | P1-07 |
| P1-11 | Multiempresa/sucursales, RLS, MFA, outbox, observabilidad | P0-12 |
| P1-12 | Performance, carga, DR, seguridad y hardening | P1-11 |

### P2 — Escala

ML predictivo, optimización de rutas/backhaul, ESG, internacional/aduanas, SaaS multiempresa.

---

## 5. Backlog detallado P0

### P0-01 — Alta de viaje del núcleo + catálogos de apoyo

**Objetivo:** crear un viaje real desde la pantalla, con cliente, OC, tarifa, carga y ventana, y que aparezca en la Mesa de Despacho.

**Backend:**
- `GET /nucleo/clientes` (activos; búsqueda).
- `GET /nucleo/tarifas?cliente_id=` (activas).
- `GET /nucleo/ordenes-compra?cliente_id=` (no anuladas).
- `POST /nucleo/viajes` con estado `confirmado`.
- Cálculo de flete en backend según modalidad de tarifa y mínimo de cobro.
- Validaciones: cliente/tarifa/OC de la empresa; tarifa vigente; OC vigente/saldo; peso; peligrosa/UN; refrigerada/temperaturas; ventana aware y fin > inicio.
- Snapshot de tarifa y OC; folio generado por PostgreSQL; auditoría.

**Frontend:**
- Botón “Nuevo viaje” en `/despacho`.
- Formulario con cliente, OC, tarifa, origen/destino, ventana, peso, tipo de carga, descripción, valor declarado, peligrosa/refrigerada, instrucciones.
- Flete calculado visible; errores legibles.
- Al guardar, refresca la mesa y muestra el viaje.

**Pruebas adversariales:**
- Fecha naive, fin antes de inicio, ventana > 90 días.
- Cliente/tarifa/OC de otra empresa.
- Tarifa vencida, cliente inactivo, OC anulada/vencida/sin saldo.
- Peso 0 o negativo; peligrosa sin UN; refrigerada sin temperaturas.
- Crear con y sin OC; crear sin tarifa debe fallar.
- Folio duplicado/concurrente.
- Permisos de lectura vs escritura.

**Bloqueos:** ninguno. Se usan datos del seed.

---

### P0-02 — CRUD de maestros del núcleo + documentos/Storage

- Clientes, tractos, ramplas, choferes: listar, crear, editar, desactivar.
- Documentos: subir archivo, tipo, número, emisión, vencimiento, versión, hash, visor y alerta.
- Bucket `respaldos`, políticas, límites de tamaño y tipos permitidos.
- Checklist documental por recurso.
- Pruebas de vencimiento, reemplazo de versión, archivo faltante, borrado prohibido.

### P0-03 — OC/tarifas editables y consumo visible

- CRUD de tarifas y OC, líneas de OC, centros de costo.
- Consumo por viaje, saldo, alertas 80/90 %, aprobación de sobregiro.
- Historial de cambios.

### P0-04 — Bloqueos de mantención/descanso/taller

- Crear reservas de mantención, descanso, vacaciones, siniestro o bloqueo manual.
- Calendario de recursos y validación contra viajes.
- Integración con la Mesa de Despacho.

### P0-05 — Expediente del viaje

- Detalle del viaje, paradas, carga, checklist, eventos, incidentes, documentos, gastos, factura y auditoría.
- IDs legibles y QR.
- Cierre con checklist.

### P0-06 — POD

- Firma, foto, receptor, RUT, geolocalización, fecha/hora, daños.
- Bloqueo de facturación sin POD.
- Almacenamiento y visor.

### P0-07 — PWA del conductor

- Login, “mi viaje”, check-in/out, checklist, fotos, gastos, incidentes, POD y offline básico.

### P0-08 — Gastos, combustible, peajes y costo real

- Gastos por viaje con respaldo y aprobación.
- Combustible transaccional, precio diésel, rendimiento, peajes/TAG.
- Costo variable y costo total del viaje.

### P0-09 — Margen, tarifa piso y Freight Score v1

- Costo/km, fijos asignados, tarifa piso estratégica/táctica, simulador.
- Freight Score con los 6 componentes del catálogo.
- Semáforo y explicación del cálculo.

### P0-10 — Facturación/cobranza del núcleo

- OC ↔ viaje ↔ factura, POD obligatorio, pagos parciales, notas de crédito, aging, promesas y alertas.
- Sin DTE real en el piloto; se simula el folio.

### P0-11 — Alertas y tablero del dueño

- Documentos, mantención, sin POD, sin facturar, OC, margen, caja, CxC.
- Briefing diario y acciones.

### P0-12 — Roles/permisos y auditoría visible

- Roles 8–10, permisos por módulo, segregación de funciones, UI de auditoría.

### P0-13 — Cutover, seed completo, E2E, backup restore y UAT

- Migrar maestros y viajes abiertos.
- Congelar escritura legacy.
- Seed de todos los módulos.
- Playwright/E2E, restauración local y checklist UAT.

---

## 6. Estrategia de pruebas

### Unitarias
- Reglas puras: fechas, tarifas, capacidad, documentos, OC, estados, cálculos.

### Integración
- PostgreSQL local con migraciones aplicadas.
- Transacciones, triggers, restricciones `EXCLUDE`, auditoría, folios.
- Empresa A vs empresa B.
- Concurrencia cuando aplique.

### API/HTTP
- 200/201, 400/409/422, permisos, headers, errores legibles.

### UI
- Navegación, formularios, estados de carga/vacío/error, responsive, accesibilidad básica.
- Prueba manual con el navegador y, cuando se instale, Playwright.

### Adversarial
- Valores límite, nulos, duplicados, fechas naive/DST, montos negativos, recursos ocupados, documentos vencidos, OC sin saldo, estados ilegales, doble clic, recarga.

### Regresión
- Toda la suite del núcleo + build del frontend + smoke test local antes de cerrar cada módulo.

---

## 7. Registro de estado

Cada módulo se actualiza en este documento y en `docs/PENDIENTES_ERP.md`:

- `⏸️ Pendiente`
- `🟡 En curso`
- `✅ Terminado y probado`
- `⛔ Bloqueado` + pregunta exacta
- `🔁 En corrección`

**Estado actual:** P0-01 a P0-13 terminados. Piloto cerrado y probado; sin bloqueos. Siguiente fase: P1 (ERP completo), sujeta a decisión de alcance del usuario.

### Bitácora P0-01

- Backend: `GET /nucleo/clientes`, `GET /nucleo/tarifas`, `GET /nucleo/ordenes-compra`, `POST /nucleo/viajes`.
- Cálculo de flete backend por modalidad (`viaje`, `km`, `tonelada`, `tonelada_km`, `hora`, `contenedor`) con mínimo de cobro.
- Formulario "Nuevo viaje" en `/despacho`: cliente, OC opcional, tarifa, ruta, ventana, peso, tipo de carga, peligrosa/refrigerada.
- Pruebas: 50 unitarias, integración PostgreSQL, API real y UI real.
- Casos adversariales: fecha naive, fin anterior, tarifa de otro cliente, cliente inexistente, peligrosa sin UN, refrigerada sin temperaturas, viaje sin OC.
- Creado `VJ-2026-100005` desde la UI y `VJ-2026-100006` sin OC desde API.
- Sin bloqueos para P0-02.

### Bitácora P0-02

- Backend: CRUD de clientes, tractos, ramplas y choferes; desactivación con guardas por viajes/reservas; bloqueo optimista por versión.
- Documentos: upload multipart a `respaldos`, hash SHA-256, versión vigente/histórica, URL firmada, límite 10 MB y extensiones permitidas.
- Frontend `/maestros`: tabs, búsqueda, alta/edición, desactivación y gestor documental con historial y visor.
- Pruebas: 50 unitarias, 2 integraciones PostgreSQL, `tsc`, ESLint y `next build`.
- Adversarial: desactivación por formulario sin guardas (corregido), RUT duplicado (409 `REGISTRO_DUPLICADO`), extensión inválida (422), recurso con reservas (422), cliente con viajes (422), versión de documento (histórico).
- Sin bloqueos para P0-03.

### Bitácora P0-03

- Migración `0005_comercial.sql`: centros de costo, centro de costo en OC/líneas, líneas activas/inactivas y flujo de sobregiro.
- Backend: CRUD de tarifas (vigencia, modalidad, recargos), CRUD de OC y líneas, anulación lógica, catálogo de centros de costo, consumo por viaje, alertas 80/90/100 %, solicitud/aprobación/rechazo de sobregiro e historial desde auditoría.
- Reglas: solo admin/gerente aprueba sobregiro; no se desactiva una tarifa usada por un viaje activo; no se reduce el monto de una OC bajo su consumo; las líneas y centros se desactivan, nunca se borran.
- Frontend `/comercial`: tarifario, OC con barra de consumo, detalle con líneas, viajes, sobregiro e historial, y centros de costo.
- Pruebas: unitarias de contratos, integración PostgreSQL del flujo completo (tarifa → OC → viaje → alerta → sobregiro → línea → anulación), API real (201/200) y UI real con sesión.
- Adversarial: suma de líneas > autorizado, OC duplicada, versión obsoleta, tarifa de otro cliente, aprobación por despacho (403), reducción bajo consumo, anulación con viaje activo.
- Sin bloqueos para P0-04.

### Bitácora P0-04

- Migración `0006_bloqueos.sql`: trazabilidad de cancelación sobre `nucleo.reservas_recurso`; el bloqueo no se borra.
- Backend: listar, crear, editar y cancelar bloqueos de mantención, descanso, vacaciones, siniestro, bloqueo manual y otros; agenda por recurso y ventana.
- Validaciones: fin > inicio, máximo 365 días, recurso activo de la empresa, conflicto contra viajes y otros bloqueos mediante la restricción EXCLUDE.
- Integración con Mesa de Despacho: la disponibilidad existente ya considera el mismo libro de reservas y muestra `CONFLICTO_RESERVA`.
- Frontend `/agenda`: calendario de 7 días por tracto/rampla/chofer, alta/edición y cancelación con motivo.
- Pruebas: unitarias de contrato, integración PostgreSQL (conflicto bloqueo-bloqueo, conflicto con viaje, versión obsoleta, cancelación y reutilización de ventana), API real y UI real.
- Sin bloqueos para P0-05.

### Bitácora P0-05

- Migración `0007_expediente.sql`: paradas, checklist, eventos inmutables, incidentes y documentos del viaje; backfill de viajes existentes.
- Migración `0008_expediente_automatico.sql`: todo viaje nuevo nace con paradas origen/descarga, checklist estándar y evento inicial.
- Backend: detalle completo, listado con progreso, paradas CRUD, checklist con bloqueo optimista, eventos append-only, incidentes con resolución, documentos a Storage y auditoría.
- Cierre: exige viaje descargado/POD pendiente, checklist obligatorio completo y sin incidentes alta/crítica abiertos; registra evento y `fin_real`.
- Frontend `/expediente` y `/expediente/[id]`: resumen, QR, carga, finanzas, paradas, checklist, eventos, incidentes, documentos y auditoría.
- Pruebas: integración PostgreSQL del flujo completo, cierre bloqueado/desbloqueado, bitácora inmutable, API real y UI real con toggles.
- Sin bloqueos para P0-06.

### Bitácora P0-06

- Migración `0009_pod.sql`: tabla `nucleo.pod`, firma/hash, fotos JSONB, receptor, RUT, geolocalización, fecha/hora y daños; POD inmutable (solo se versiona).
- Gate de facturación reemplazado: PostgreSQL rechaza pasar a `facturado` si el viaje no tiene POD, además de las validaciones de OC.
- Backend: obtener/crear/actualizar POD con Storage (firma + fotos), URLs firmadas, eventos en la bitácora y bloqueo optimista.
- Frontend: pestaña POD del expediente con formulario de receptor, geolocalización, daños, pad de firma y carga de firma escaneada/fotos; visor de evidencia.
- Pruebas: integración PostgreSQL con Storage local, rechazo de firma inválida, POD duplicado, versión obsoleta, actualización con nueva foto y gate de facturación sin POD. UI real con carga de firma y confirmación.
- Sin bloqueos para P0-07.

### Bitácora P0-07

- Migración `0010_conductor.sql`: vínculo `auth_id` en `nucleo.choferes`, único por empresa.
- Backend: `GET /nucleo/conductor/mi-viaje`, check-in/out y transiciones hacia adelante; el viaje se resuelve por usuario autenticado, no por id del navegador. Despacho/gerencia puede previsualizar con `chofer_id`.
- PWA `/conductor`: login con `next`, estado online/offline, tarjeta de viaje, progreso, checklist, incidentes, fotos, POD embebido y contacto/instrucciones.
- Offline básico: service worker para shell, manifiesto e íconos; cola local para transiciones y checklist con replay automático al volver la señal; último viaje guardado en localStorage.
- Pruebas: integración PostgreSQL de mi viaje, check-in/out, transiciones ilegales y acceso de otro conductor; UI real con check-in, cola offline y sincronización.
- Sin bloqueos para P0-08.

### Bitácora P0-08

- Migración `0011_gastos.sql`: gastos por viaje con respaldo, estados pendiente/aprobado/rechazado, precio diésel diario y costo real persistido en el viaje.
- Trigger `fn_viaje_costos`: costo variable real = gastos aprobados + comisión del chofer; se recalcula al insertar, aprobar, rechazar o modificar un gasto.
- Backend: CRUD de gastos, carga de comprobante a Storage, aprobación/rechazo con segregación básica, precios de diésel y reporte de costos con litros, rendimiento, costo/km, margen y desglose por tipo.
- Frontend: pestaña "Gastos y costos" en el expediente y formulario de gastos en la PWA del conductor; lista de estados, comprobantes y aprobación.
- Pruebas: integración PostgreSQL de combustible, peajes, autollenado de precio, aprobación/rechazo, comisión, costo real persistido, rendimiento y costo/km; UI real de registro y aprobación.
- Sin bloqueos para P0-09.

### Bitácora P0-09

- Migración `0012_rentabilidad.sql`: configuración de costos por empresa (fijos, viajes/mes, margen objetivo, benchmark, contribución mínima, costo/km, diésel).
- Backend: cálculo de costo total, margen, tarifa piso estratégica/táctica, Freight Score con los 6 componentes y semáforo; simulador sin escritura; rentabilidad por viaje con costos reales si hay gastos aprobados.
- Persistencia de `freight_score_estimado` y detalle en el viaje; explicación componente por componente.
- Frontend `/rentabilidad`: parámetros editables, simulador y resultado; pestaña "Rentabilidad" en el expediente.
- Pruebas: integración PostgreSQL con los dos ejemplos del catálogo (92,9 verde y ~65 amarillo), configuración, piso estratégico/táctico, costos reales, comisión y persistencia del score; UI real del simulador.
- Sin bloqueos para P0-10.

### Bitácora P0-10

- Migración `0013_facturacion.sql`: facturas simuladas, vínculo factura↔viaje, pagos, notas de crédito y promesas; trigger de estado/saldo y paso de viajes a `cobrado`.
- Backend: emisión de factura desde viajes cerrados con POD y misma OC, folio con `nucleo.siguiente_folio`, pagos parciales, notas de crédito, promesas y aging 0–30/31–60/61–90/>90.
- Reglas: sin POD o sin OC no se factura; un viaje no se factura dos veces; pagos/notas no pueden superar el saldo; la factura pagada marca los viajes como cobrados.
- Frontend `/cobranza`: tablero de CxC, aging, filtros, emisión multi-viaje, detalle con pagos/notas/promesas y registro de cobranza. El expediente muestra la factura del viaje.
- Pruebas: integración PostgreSQL con POD, cierre, factura, pago parcial, nota de crédito, pago final, viaje cobrado y aging; UI real de emisión y pago.
- Sin bloqueos para P0-11.

### Bitácora P0-11

- Backend: tablero calculado desde fuentes de verdad, sin tabla de alertas que se desactualice.
- Alertas: documentos por vencer/vencidos, mantenciones próximas, viajes sin POD, viajes cerrados sin facturar, OC 80/90/100/sobregiro, CxC vencida, Freight Score rojo, incidentes altos/críticos y caja operativa negativa.
- KPIs: CxC, caja 30 días, viajes activos, tractos disponibles, OC en alerta, documentos, mantenciones, viajes sin POD/sin facturar y score promedio.
- Briefing diario y acciones sugeridas con enlace directo a la pantalla de resolución.
- Frontend `/tablero`: salud, KPIs, briefing, acciones y centro de alertas filtrable por severidad/categoría.
- Pruebas: integración PostgreSQL con todas las fuentes de alerta activas y UI real con datos del seed.
- Sin bloqueos para P0-12.

### Bitácora P0-12

- Backend: matriz central de 8 roles × 28 permisos por módulo/acción; dependencia `requiere_permiso` aplicada a los endpoints del núcleo.
- Segregación: quien registra un gasto no puede aprobarlo, sin excepción de rol; contabilidad emite facturas y tesorería registra cobranza, con admin/gerencia como override.
- API: `GET /nucleo/permisos/mios`, `GET /nucleo/permisos/matriz`, `GET /nucleo/permisos/verificar`, `GET /nucleo/auditoria` y `/auditoria/tablas`.
- Frontend `/auditoria`: filtros por tabla, operación, UUID y fechas, paginación y diff antes/después. `/permisos`: rol actual, permisos personales y matriz completa.
- Pruebas: matriz de roles/permisos, rechazo por permiso, segregación de gastos, auditoría con filtros y paginación, UI real de auditoría y matriz.
- Sin bloqueos para P0-13.

### Bitácora P0-13

- Migración `0014_cutover.sql`: control `nucleo.cutover_control` para congelar escritura legacy.
- `scripts/cutover_legacy.py`: migra clientes, choferes, tractos, ramplas, documentos y viajes abiertos; crea tarifa/OC `MIG-*` cuando el legacy no las tiene; `--dry-run` y `--freeze`.
- Middleware: con el cutover congelado, POST/PUT/PATCH/DELETE legacy responde 409 `CUTOVER_LEGACY_CONGELADO`; lecturas legacy y todo `/nucleo` siguen operando.
- `scripts/seed_local.py`: 8 usuarios (admin, gerente, despacho, contador, tesorería, taller, conductor, auditor), centros de costo, configuración de costos, diésel, líneas de OC, bloqueos, viajes cerrados, POD, gasto aprobado, factura, pago y promesa.
- `scripts/restore_drill.sh`: pg_dump de `nucleo/public/auth`, restore en base temporal con extensiones, verificación de conteos y limpieza. Ejecutado con resultado OK.
- Playwright: 9 escenarios E2E (tablero, comercial, despacho, expediente/QR, cobranza, auditoría, permisos, PWA del conductor y cutover); 9/9 en verde.
- Documentación: `docs/UAT_PILOTO.md` (por rol) y `docs/CUTOVER_CHECKLIST.md` (pre/durante/post y rollback).
- Cutover ejecutado con `--freeze`; legacy bloqueado y núcleo operativo. Probado además con un viaje legacy `programado` migrado como `VJ-LEG-12345678` en estado `confirmado`.
- Clean-room: `supabase db reset` + `scripts/seed_local.py` + suite + E2E + restore drill + cutover, todo en verde.
- Sin bloqueos. El piloto P0 queda cerrado.

---

## 8. Orden de arranque

1. P0-01 Alta de viaje del núcleo.
2. P0-02 Maestros + documentos.
3. P0-03 OC/tarifas.
4. P0-04 Bloqueos.
5. P0-05 Expediente.
6. P0-06 POD.
7. P0-07 PWA conductor.
8. P0-08 Gastos/costos.
9. P0-09 Margen/Freight Score.
10. P0-10 Facturación/cobranza.
11. P0-11 Alertas/tablero.
12. P0-12 Roles/auditoría.
13. P0-13 Cutover/UAT.

No se avanza al siguiente hasta que el anterior pase la regresión y el ataque adversarial.
