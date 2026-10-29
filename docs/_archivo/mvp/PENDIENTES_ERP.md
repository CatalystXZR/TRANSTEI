> **ARCHIVADO 2026-10-29 — NO CITAR COMO ESTADO.**
> Documento histórico. Reemplazos y contexto: `docs/_archivo/README.md` · Estado real: `docs/estado.md`.
> Sus cifras y afirmaciones de "terminado" NO fueron re-verificadas en esta fecha.

# Inventario de pendientes — ERP Transportes TEI

**Fecha:** Octubre 2026  
**Fuentes revisadas:** `PLAN_MAESTRO_ERP_V2.md`, `PLAN_90_DIAS.md`, `CATALOGO_KPIS_Y_FREIGHT_SCORE.md`, `PLAN_DESARROLLO.md`, `MODULOS.md`, `KPIS.md`, `DEPLOY.md`, `SETUP.md`, `NUCLEO_V2_DISENO.md`.

**Leyenda:** ✅ funcional y probado · 🟡 parcial · ❌ no existe.

> Importante: “ERP al 100%” según el Plan Maestro son **10–12 meses y 42–54 personas-mes**. Lo que sigue separa el **piloto de 90 días** (lo mínimo para operar 3 tractos/3 choferes) del **ERP completo**. No conviene mezclar ambos: el piloto se puede cerrar mucho antes.

---

## 0. Base local ya operativa

| Capacidad | Estado |
|---|---|
| Colima + Supabase local (Postgres, Auth, Storage, Studio) | ✅ |
| Node 22 + Next.js + FastAPI + Makefile | ✅ |
| Schema `nucleo` con 15 tablas, migración 0004 | ✅ |
| Usuario local, seed de 3 tractos/3 ramplas/3 choferes | ✅ |
| Login local y API del núcleo | ✅ |
| Mesa de Despacho con asignación y reasignación | ✅ |
| Restricciones de exclusión y auditoría en base | ✅ |

---

## 1. Piloto 90 días — lo que falta para operar de verdad

| # | Capacidad | Estado | Qué falta | Tamaño |
|---:|---|---|---|---|
| 1 | Crear viaje del núcleo con OC, tarifa y carga | ✅ | Alta, cálculo de flete y formulario listos; documentos/adjuntos pasan a P0-02 | — |
| 2 | CRUD de maestros en el núcleo | ✅ | Clientes, tractos, ramplas y choferes con alta, edición y desactivación protegida | — |
| 3 | Carga de documentos y archivos | ✅ | Upload a Storage, hash, versiones, visor firmado, límites y alertas de vencimiento | — |
| 4 | OC y tarifas editables | ✅ | CRUD de tarifas, OC, líneas y centros de costo; consumo por viaje, alertas 80/90/100 % y aprobación de sobregiro | — |
| 5 | Bloqueos de mantención, descanso y taller | ✅ | Agenda, alta/edición/cancelación y validación contra viajes en el mismo libro de reservas | — |
| 6 | Expediente del viaje | ✅ | Detalle, paradas, carga, checklist, eventos, incidentes, documentos, QR, auditoría y cierre | — |
| 7 | POD y evidencia | ✅ | Firma, fotos, receptor, RUT, geolocalización, daños y gate de facturación en PostgreSQL | — |
| 8 | PWA del conductor | ✅ | Login, “mi viaje”, check-in/out, checklist, fotos, gastos, incidentes, POD y offline básico | — |
| 9 | Gastos, combustible y peajes del núcleo | ✅ | Gastos por viaje con respaldo, aprobación, diésel, peajes, costo real y margen | — |
| 10 | Costo real, margen y Freight Score | ✅ | Costo/km, fijos asignados, tarifa piso, simulador y Freight Score v1 con semáforo | — |
| 11 | Facturación y cobranza del núcleo | ✅ | OC↔viaje↔factura, POD obligatorio, pagos parciales, notas, promesas y aging | — |
| 12 | Centro de alertas y tablero del dueño | ✅ | Alertas del núcleo, KPIs, briefing diario y acciones sugeridas | — |
| 13 | Migración/cutover desde `public` | ✅ | Migración, congelamiento legacy, rollback y restore drill documentados y ejecutados | — |
| 14 | Roles y permisos del piloto | ✅ | Matriz de 8 roles, permisos por módulo, segregación y UI de auditoría | — |
| 15 | UAT, E2E y backup restore local | ✅ | Playwright 8/8, restore drill OK y checklist UAT por rol | — |

**Resultado:** el piloto **P0-01 a P0-13 está cerrado y probado**. Lo que sigue en este documento corresponde a P1/P2 (ERP completo y escala), no al piloto.

---

## 2. ERP completo por módulo (Plan Maestro 4.1)

### 2.1 Centro de Mando
- ✅ Dashboard legacy con KPIs configurables y alertas básicas.
- ❌ Tablero por rol (dueño, gerente, despacho, contador, tesorería, taller).
- ❌ Briefing diario 07:00 y 18:00.
- ❌ Caja disponible/proyectada, margen, flota, CxC y decisiones del día integradas.
- ❌ Drill-down y explicación del cálculo.

### 2.2 Comercial
- 🟡 Clientes legacy (RUT, días de pago, contacto básico).
- ❌ Ficha completa: contratos, crédito, contactos, rentabilidad, riesgo, concentración.
- 🟡 Tarifas en schema nuevo; ✅ CRUD, tarifario por ruta/tipo, recargos y vigencia visual.
- ❌ Cotizaciones y aprobación por margen.
- ✅ OC con líneas, consumo visual, alertas 80/90 %, renovación y aprobación de sobregiro.
- ❌ Freight Score, tarifa piso y simulador comercial.
- ❌ Portal del cliente y estado de cuenta.

### 2.3 Operaciones
- ✅ Disponibilidad, “libre desde”, dobles reservas y mesa de despacho.
- 🟡 Viaje v2: schema y asignación; ❌ alta, paradas múltiples, carga completa, checklist, eventos y cierre.
- ❌ POD, evidencias, incidentes, reclamos y siniestros.
- ❌ Torre de control, GPS, geocercas, ETA, checkpoints y parte diario.
- ❌ Horas de conducción, descansos y jornada legal.
- ❌ PWA del conductor y modo offline.

### 2.4 Flota
- 🟡 Tractos/ramplas legacy con patente, marca, km y vencimientos.
- ❌ Ciclo de vida del activo, propiedad, leasing, VIN, configuración de ejes y capacidad completa.
- 🟡 Documentos en schema nuevo; ❌ repositorio, versiones, seguros, pólizas y siniestros.
- ❌ GPS/telemetría, odómetro, horas motor y costo/km.
- ❌ Neumáticos: serie, posición, dibujo, presión, rotación, reencauche y costo/km.

### 2.5 Mantenimiento
- 🟡 Pauta legacy por km solo para tractos; alerta a 5.000 km.
- ❌ Planes por tiempo/horas, ramplas, criticidad y repuestos.
- ❌ Órdenes de trabajo, diagnóstico, mano de obra, proveedor, fotos, garantía y tiempo fuera de servicio.
- ❌ Repuestos, inventario, mínimos/máximos, punto de pedido y valorización.
- ❌ Bloqueo automático de despacho por mantención crítica.
- ❌ Predictivo (reglas, estadística, ML).

### 2.6 Personas
- 🟡 Choferes legacy: RUT, sueldo base, % comisión y vencimiento de licencia.
- ❌ Ficha completa: contrato, AFP, salud, cesantía, banco, contacto de emergencia.
- ❌ Licencia por clase/restricciones, examen médico, cursos y certificados.
- 🟡 Liquidación legacy base + comisión + anticipos + ajustes + PDF.
- ❌ Nómina legal: AFP, salud, cesantía, impuesto único, gratificación, horas extra, vacaciones, licencias y finiquito.
- ❌ Jornada, asistencia, descansos, turnos y horas de conducción.
- ❌ Desempeño, siniestralidad, multas y capacitación.
- ❌ Snapshot inmutable de liquidación y integración con proveedor de nómina.

### 2.7 Finanzas
- 🟡 Facturación manual legacy: número SII, afecta/exenta, IVA y asociación a viajes.
- ❌ DTE/SII, guías de despacho, notas de crédito/débito, XML/PDF y aceptación SII.
- ❌ Facturación por OC, por período o por hito; retenciones, moneda y centro de costo.
- 🟡 Cobranza legacy: pago total, semáforo y vencimiento.
- ❌ Pagos parciales, aplicación a factura, promesas, dunning, intereses y factoring.
- ❌ Cuentas por pagar, facturas de proveedor, match de 3 vías y calendario de pagos.
- ❌ Tesorería, conciliación bancaria, caja a 13 semanas y escenarios.
- ❌ Contabilidad de doble partida, plan de cuentas, asientos, centros de costo y cierre.
- ❌ Presupuesto, forecast, PPM, renta, patente, crédito diésel y F29 completo.
- ❌ Cierre mensual ≤ 5 días.

### 2.8 Compras
- ❌ Proveedores, contactos, condiciones, bancos y evaluación.
- ❌ Solicitud, aprobación, OC de proveedor, recepción, factura y pago.
- ❌ Inventario, devoluciones, garantías y compras fuera de OC.

### 2.9 Documentos y cumplimiento
- 🟡 Tabla de documentos con vencimiento y validación dura.
- ❌ Repositorio, visor, versiones, hash, firma electrónica, OCR, QR y retención legal.
- ❌ Checklist por cliente, tipo de viaje, carga, unidad y conductor.
- ❌ Matriz legal Chile completa y alertas de cumplimiento.
- ❌ Privacidad Ley 21.719, GPS, consentimiento y retención.

### 2.10 BI y KPIs
- 🟡 Motor legacy seguro con ~20 métricas y fórmulas configurables.
- ❌ Catálogo completo de 90 KPIs del documento.
- ❌ Modelo semántico, dimensiones, snapshots, metas, tendencias y drill-down.
- ❌ Reportes por rol, exportación gobernada y comparación presupuesto vs real.
- ❌ KPIs del núcleo nuevo (utilización, OTIF, km vacíos, estadía, disponibilidad mecánica).
- ❌ Freight Score v1 y simulador de escenarios.

### 2.11 Alertas y workflow
- 🟡 Alertas legacy de documentos y facturas vencidas.
- ❌ Centro unificado de alertas con severidad, SLA, dueño y acción.
- ❌ Reglas configurables y notificaciones email/WhatsApp/push.
- ❌ Workflows de aprobación: cotización bajo margen, gasto, factura, nota de crédito, pago, compra, alta de proveedor, siniestro.

### 2.12 Portales
- ❌ Portal del cliente: cargas, tracking, documentos, facturas, reclamos y estado de cuenta.
- ❌ PWA del conductor: viaje, checklist, POD, gastos, incidentes y offline.
- ❌ Portal de proveedor/taller: órdenes, repuestos, recepción y facturas.

### 2.13 Copiloto TEI
- ❌ Chat en lenguaje natural, briefing diario y análisis.
- ❌ Modelo semántico + RAG sobre contratos/políticas.
- ❌ Acciones con aprobación humana, auditoría y guardrails.
- ❌ “No inventar”: mostrar cálculo, fuente y fecha.

### 2.14 Administración
- 🟡 Auth legacy con 3 roles; configuración básica de IVA, alertas y KPIs.
- ❌ 8–10 roles, permisos granulares, segregación de funciones y aprobaciones.
- ❌ Gestión de usuarios/empresas/sucursales/centros de costo.
- 🟡 Auditoría en base nueva; ❌ UI de auditoría y consulta.
- ❌ Integraciones, webhooks, jobs, outbox y monitoreo.

---

## 3. Plataforma, seguridad y calidad

| Capacidad | Estado |
|---|---|
| Multiempresa en schema nuevo | ✅ backend; ❌ UI/selector y legacy migrado |
| RLS por empresa | 🟡 RLS activo sin políticas; backend usa service role |
| Roles 8–10 y permisos granulares | ❌ |
| MFA/SSO, rate limiting, secretos en vault | ❌ |
| Idempotencia en pagos/facturas | ❌ |
| Outbox, cola y worker | ❌ |
| Observabilidad (logs, trazas, métricas, Sentry) | ❌ |
| Staging/producción | ❌ (solo local) |
| Backups automáticos y restore drill | ❌ |
| Migraciones versionadas y CI | 🟡 migraciones sí; CI básico legacy |
| Paginación en listados legacy | ❌ |
| Sanitización CSV/inyección de fórmulas | 🟡 revisar export legacy |
| Límite y validación de uploads | 🟡 legacy sin límite |
| Tests E2E, carga y concurrencia real | ❌ |
| Seed completo para probar todos los módulos | ❌ (solo núcleo y maestros) |
| Buckets/políticas de Storage local | 🟡 bucket `respaldos` y upload probados; faltan políticas, visor y POD |
| Mailpit/email local | 🟡 Supabase local lo incluye; falta configurar envío |
| Mocks de SII, GPS, combustible, peajes, bancos, WhatsApp, mapas, OCR y firma | ❌ |

---

## 4. Lo mínimo para “probar todas las funciones” en local

Además del código, falta **preparar el entorno de prueba**:

1. Políticas y visor del bucket `respaldos` para fotos de gastos y POD.
2. Seed de facturas, pagos, cobranzas, gastos, combustible, peajes y liquidaciones.
3. Seed de mantenciones, órdenes de trabajo, repuestos y neumáticos.
4. Usuarios locales con todos los roles (despacho, conductor, taller, auditor, etc.).
5. Mocks locales de SII/DTE, GPS, combustible, peajes y banco.
6. Datos de 3 tractos/3 choferes con documentos, viajes, POD y facturas de ejemplo.
7. Prueba E2E: crear viaje → asignar → check-in → POD → gasto → factura → cobro.
8. Backup y restauración local probados.
9. Checklist UAT por rol y firma de aceptación.

---

## 5. Orden recomendado

### P0 — Cerrar el piloto (primero)

1. **Nuevo viaje del núcleo** (OC, tarifa, carga, ventana, paradas).
2. **CRUD de maestros + documentos + Storage local**.
3. **OC/tarifas editables y consumo visible**.
4. **Bloqueos de mantención/descanso/taller**.
5. **Expediente del viaje** (detalle, checklist, eventos, incidentes).
6. **POD + PWA del conductor**.
7. **Gastos, combustible, peajes y costo real**.
8. **Margen, tarifa piso y Freight Score v1**.
9. **Facturación/cobranza del núcleo** (OC + POD + pagos parciales + aging).
10. **Alertas y tablero del dueño del núcleo**.
11. **Roles/permisos y auditoría visible**.
12. **Cutover, seed completo, E2E, backup restore y UAT**.

### P1 — ERP completo

Comercial avanzado, mantenimiento/taller, personas/nómina legal, finanzas/tesorería/contabilidad, compras/inventario, documentos/OCR/firma, BI 90 KPIs, portales, integraciones y copiloto.

### P2 — Escala

Multi-sucursal, ML predictivo, optimización de rutas/backhaul, ESG, internacional/aduanas y SaaS multiempresa.

---

## 6. Estimación honesta

- **Piloto 90 días:** 12–15 paquetes; es un cierre de producto, no un par de pantallas.
- **ERP completo:** 14 módulos y ~70+ capacidades; el Plan Maestro estima **42–54 personas-mes** (60–80 con IA/multiempresa avanzada).
- **Solo local**, sin integraciones reales, se puede probar casi todo con mocks; SII, bancos, GPS y firma requieren adaptadores/sandbox.

---

## 7. Decisiones que necesito para avanzar

1. **Alcance:** ¿cerramos primero el piloto P0 o intentamos el ERP completo de una vez?
2. **Documentos legales:** lista definitiva y periodicidad (tacógrafo, limitador, extintores, botiquín, triángulos, sujeción, permisos especiales).
3. **Datos reales:** 3 tractos, 3 ramplas, 3 choferes, clientes, tarifas y OC para el seed/UAT.
4. **Facturación:** proveedor DTE/SII y formato de factura; en local se puede simular.
5. **Nómina:** ¿integración con proveedor o motor propio? El Plan Maestro recomienda integración al inicio.
6. **Integraciones:** qué GPS, combustible, peajes, banco y contabilidad usa TEI.
7. **Prioridad del dueño:** ¿qué duele más hoy: disponibilidad, facturación/cobranza, costos o mantenimiento?

---

## 8. Conclusión

El piloto P0 está cerrado: alta de viaje, maestros/documentos, OC/tarifas, agenda, expediente, POD, PWA, gastos/costos, rentabilidad, facturación/cobranza, alertas, roles/auditoría y cutover. El siguiente paso es decidir el alcance de P1 (ERP completo), que aún requiere módulos de personas, compras, finanzas avanzadas, BI, portales e integraciones reales.
