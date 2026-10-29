> **ARCHIVADO 2026-10-29 — NO CITAR COMO ESTADO.**
> Documento histórico. Reemplazos y contexto: `docs/_archivo/README.md` · Estado real: `docs/estado.md`.
> Sus cifras y afirmaciones de "terminado" NO fueron re-verificadas en esta fecha.

# PLAN 90 DÍAS — PILOTO OPERATIVO TRANSTEI
## "Que el sistema sepa dónde está cada camión, qué carga lleva y cuándo queda libre"

**Versión:** 1.0  
**Fecha:** Octubre 2026  
**Objetivo:** poner en producción un piloto operativo usable, con datos reales, en 90 días.

---

## 1. Resultado esperado al día 90

Al terminar los 90 días, el dueño y el equipo deben poder hacer esto sin planillas paralelas:

1. Crear un viaje vinculado a una **OC del cliente** y a una **tarifa**.
2. Saber **qué tracto, rampla y chofer están disponibles** en una fecha/hora.
3. Ver **dónde está** cada unidad (GPS o check-in manual) y **cuándo queda libre**.
4. Registrar **carga, peso, documentos y checklist** del viaje.
5. Capturar **POD** desde el celular del conductor (foto, firma, geolocalización).
6. Registrar **gastos** con boleta/foto y **combustible/peajes**.
7. Calcular **costo real y margen** del viaje.
8. Ver **alertas críticas**: documentos vencidos, mantenimiento, viajes sin POD, viajes sin facturar, facturas vencidas.
9. Ver un **tablero diario** con caja, margen, flota y cobranza.
10. Medir **5 KPIs base** con datos confiables.

**Criterio de éxito:** el piloto se usa todos los días con al menos 3 tractos y 3 choferes reales, y el dueño confirma que la información es confiable.

---

## 2. Alcance del piloto (y lo que queda fuera)

### Incluido

- Multiempresa básica y auditoría.
- Rol conductor y rol despacho.
- Clientes, contactos, OC, tarifas simples.
- Tractos, ramplas, choferes y documentos.
- Viaje v2: carga, paradas, checklist, estados, POD.
- Disponibilidad y mesa de despacho.
- PWA del conductor (MVP).
- Gastos, combustible y peajes.
- Costo por viaje y margen de contribución.
- Precio del diésel y tarifa piso.
- Alertas críticas.
- Tablero del dueño.
- Facturación/cobranza existente mejorada.
- Migración de datos maestros y viajes abiertos.

### Fuera del piloto (fases siguientes)

- DTE integrado con SII.
- Nómina legal completa.
- Contabilidad de doble partida.
- Tesorería y conciliación bancaria completa.
- Mantenimiento predictivo con ML.
- Portal del cliente completo.
- Copiloto de IA.
- Optimización de rutas/backhaul.
- Multi-sucursal avanzada.
- Factoring.
- Integración profunda con GPS/combustible/peajes (en el piloto se permite CSV/manual).

---

## 3. Equipo y responsabilidades

| Rol | Persona | Responsabilidad |
|---|---|---|
| Product Owner | Dueño TEI | Prioriza, aprueba, decide |
| PM/BA | Por definir | Plan, requisitos, coordinación |
| Tech Lead | Por definir | Arquitectura, calidad |
| Backend | Por definir | API, datos, reglas |
| Frontend | Por definir | Web, PWA |
| UX/UI | Por definir | Flujos, usabilidad |
| QA | Por definir | Pruebas, UAT |
| Dueño del dato | Secretaria/operaciones | Limpieza y carga |
| Contador | Externo/interno | Validación de facturación/impuestos |
| Experto operación | Despachador | Reglas y adopción |

**Regla:** el dueño no puede ser el único que decide todo. Necesita un PM con autonomía y un dueño del dato con tiempo asignado.

---

## 4. Cronograma semanal

### Semana 1 — Descubrimiento y alineación

**Objetivo:** entender la operación real y congelar el alcance.

- Entrevistas: dueño, secretaria, despacho, contador, 2 conductores.
- Inventario de planillas, correos, WhatsApp, carpetas y sistemas.
- Mapa de procesos: cotización → OC → asignación → viaje → POD → factura → cobro.
- Catálogo de documentos y vencimientos.
- Catálogo de clientes, rutas, tarifas y OC abiertas.
- Definición de KPIs base y metas.
- Validación del alcance del piloto.
- Riesgos y dependencias.

**Entregables:**

- Mapa de proceso actual y futuro.
- Inventario de datos.
- Alcance firmado.
- Backlog priorizado.
- Plan de comunicación.

---

### Semana 2 — Fundaciones técnicas

**Objetivo:** preparar la base para no rehacer después.

- `empresa_id` en tablas de negocio.
- Columnas de auditoría y soft delete.
- `audit_log`.
- Migraciones versionadas.
- Roles v2: admin, gerente, despacho, contador, tesorería, taller, conductor, auditor.
- Permisos backend por rol.
- Staging y producción.
- Backups y prueba de restauración.
- Monitoreo de errores.
- CI con tests.
- Seed de datos de prueba.

**Entregables:**

- Esquema actualizado.
- Roles y permisos.
- Ambientes.
- Backup verificado.
- Pipeline CI.

---

### Semana 3 — Maestros y documentos

**Objetivo:** datos limpios y confiables.

- Clientes: contactos, condiciones de pago, crédito.
- Choferes: licencia, clase, vencimiento, documentos.
- Tractos: capacidad, documentos, seguro, km.
- Ramplas: capacidad, documentos, tipo.
- Proveedores: talleres, combustible, peajes.
- Documentos: tipos, vencimientos, archivos.
- Validación de RUT, patente, fechas.
- Importación CSV con validación y reporte de errores.
- Limpieza de duplicados.

**Entregables:**

- Maestros cargados.
- Reporte de calidad de datos.
- Documentos críticos digitalizados.
- Checklist de vencimientos.

---

### Semana 4 — OC, tarifas y viaje v2

**Objetivo:** vincular el flete a la OC y a la tarifa.

- OC: número, cliente, monto, vigencia, centro de costo, líneas.
- Tarifas: por viaje, km, tonelada, recargos.
- Viaje: OC, tarifa, carga, peso, paradas, contactos.
- Estados v2.
- Checklist documental.
- Validaciones: cliente, OC, capacidad, documentos.
- IDs legibles y QR.
- Historial de cambios.

**Entregables:**

- Flujo OC → viaje.
- Ficha del viaje.
- Validaciones duras.
- Datos de prueba.

---

### Semana 5 — Disponibilidad y mesa de despacho

**Objetivo:** saber quién está libre y evitar dobles asignaciones.

- Calendario de tractos, ramplas y choferes.
- Estados: disponible, asignado, en ruta, taller, descanso, bloqueado.
- Cálculo de “libre desde”.
- Validación por rango de fechas.
- Restricciones de exclusión en PostgreSQL.
- Detección de conflictos.
- Asignación y reasignación con motivo.
- Filtros por fecha, origen, capacidad, documentos.
- Vista “¿quién está libre?”.

**Entregables:**

- Mesa de despacho funcional.
- Pruebas de doble asignación.
- Manual de despacho.

---

### Semana 6 — PWA del conductor (MVP)

**Objetivo:** que el conductor use el celular, no el papel.

- Login del conductor.
- “Mi viaje de hoy”.
- Check-in/check-out.
- Checklist de carga.
- Fotos de carga/descarga.
- POD: firma, foto, receptor, geolocalización.
- Gastos: combustible, peaje, viático (foto).
- Incidentes.
- Modo offline básico y sincronización.
- Botones grandes, español, bajo consumo de datos.

**Entregables:**

- PWA instalable.
- Prueba con 2 conductores.
- Manual de 1 página.

---

### Semana 7 — Gastos, combustible y peajes

**Objetivo:** costo real del viaje.

- Gastos por viaje con categoría, monto, fecha, respaldo.
- Combustible: litros, precio, km, estación.
- Peajes/TAG.
- Viáticos y rendición.
- Aprobación de gastos.
- OCR básico de boletas (si el proveedor está listo; si no, foto + digitación).
- Alertas de gasto sin respaldo.
- Bloqueo de edición después del cierre.

**Entregables:**

- Costo real por viaje.
- Reporte de gastos.
- Conciliación básica.

---

### Semana 8 — Costo, margen y diésel

**Objetivo:** saber si el flete es bueno.

- Costo variable por km.
- Costo fijo asignado.
- Costo total del viaje.
- Margen de contribución y margen bruto.
- Precio del diésel diario.
- Consumo estándar por unidad/ruta.
- Tarifa piso.
- Simulador simple.
- Freight Score v1.
- Semáforo en la ficha del viaje.

**Entregables:**

- Ficha de rentabilidad.
- Simulador.
- Reporte de viajes bajo margen.
- Acta de validación con el dueño.

---

### Semana 9 — Facturación y cobranza

**Objetivo:** cerrar el ciclo del dinero.

- Facturación desde viaje con OC y POD.
- Validación: no facturar sin POD.
- Estados de factura.
- Pago total y parcial (si el alcance lo permite).
- Aging.
- Alertas de facturas vencidas.
- Registro de promesas de pago.
- Reporte de viajes entregados sin facturar.
- Enlace factura ↔ viaje ↔ OC.

**Entregables:**

- Flujo de facturación.
- Reporte de cobranza.
- Alertas.

---

### Semana 10 — Alertas y tablero del dueño

**Objetivo:** que el sistema diga qué hacer.

- Centro de alertas unificado.
- Documentos vencidos.
- Mantenimiento vencido (incluye “sin registro”).
- Viajes sin POD.
- Viajes sin facturar.
- Facturas vencidas.
- OC al 80/90%.
- Margen bajo.
- Gasto sin respaldo.
- Tablero del dueño: caja, margen, flota, CxC, alertas.
- Briefing diario.

**Entregables:**

- Centro de alertas.
- Tablero.
- Briefing automático.

---

### Semana 11 — Pruebas integrales y UAT

**Objetivo:** que no falle en la vida real.

- Casos de prueba por rol.
- Prueba de punta a punta: OC → viaje → POD → gasto → factura → cobro.
- Prueba de doble asignación.
- Prueba de documentos vencidos.
- Prueba de offline.
- Prueba de datos masivos.
- Prueba de permisos.
- Prueba de backup/restauración.
- Corrección de defectos críticos.
- UAT con usuarios reales.

**Entregables:**

- Reporte de UAT.
- Lista de defectos.
- Plan de corrección.

---

### Semana 12 — Capacitación, go-live y hypercare

**Objetivo:** poner en producción sin caos.

- Capacitación por rol.
- Manuales de 1 página.
- Videos cortos.
- Datos reales de 3 tractos/3 choferes.
- Go-live controlado.
- Soporte en terreno.
- Monitoreo diario.
- Ajustes rápidos.
- Retrospectiva.
- Plan de siguiente fase.

**Entregables:**

- Sistema en producción.
- Usuarios capacitados.
- Métricas de adopción.
- Retrospectiva.
- Backlog fase 2.

---

## 5. Quick wins de los primeros 30 días

Estos cambios se pueden hacer antes o en paralelo y reducen riesgo de inmediato:

1. **Bloquear rampla y chofer**, no solo tracto.
2. **Validar fechas** y solapamientos.
3. **Bloquear asignación** con documentos vencidos.
4. **Incluir “sin registro”** en mantenimiento y mostrar alerta.
5. **No facturar sin POD**.
6. **Folio único** por empresa/tipo.
7. **Auditoría** de cambios críticos.
8. **Alerta de viajes entregados sin facturar**.
9. **Alerta de gastos sin respaldo**.
10. **Sanitizar CSV**.
11. **Paginación** en listados.
12. **Etiqueta “pre-liquidación”** en el PDF actual y advertencia legal.
13. **Backup restore test**.
14. **Staging**.
15. **Tablero de 5 números** para el dueño.

---

## 6. Criterios de aceptación del piloto

### Operación

- [ ] Se puede crear un viaje con OC, tarifa, carga y documentos.
- [ ] El sistema impide asignar tracto/rampla/chofer ocupado.
- [ ] El sistema impide asignar documentos vencidos.
- [ ] El conductor ve su viaje en el celular.
- [ ] El conductor registra POD con foto/firma.
- [ ] El despacho ve el estado y la ubicación.
- [ ] El sistema calcula “libre desde”.

### Dinero

- [ ] El viaje tiene costo real y margen.
- [ ] El sistema muestra tarifa piso y Freight Score.
- [ ] No se factura sin POD.
- [ ] La factura se vincula a OC y viaje.
- [ ] La cobranza muestra aging y alertas.
- [ ] El dueño ve caja/margen/CxC.

### Datos

- [ ] 95% de los maestros críticos están completos.
- [ ] 95% de los viajes del piloto tienen documentos.
- [ ] 95% de los gastos tienen respaldo.
- [ ] 100% de los documentos críticos están digitalizados.
- [ ] El backup se restauró exitosamente.

### Adopción

- [ ] 3 tractos y 3 choferes usan el sistema a diario.
- [ ] El despacho no usa planilla paralela para el piloto.
- [ ] El dueño revisa el tablero al menos 4 veces por semana.
- [ ] Los usuarios califican la utilidad ≥ 4/5.
- [ ] Se midió tiempo ahorrado en al menos 3 procesos.

---

## 7. Métricas del piloto

| Métrica | Línea base | Meta 90 días |
|---|---|---:|
| Viajes con OC | Por medir | ≥ 90% |
| Viajes con POD | 0% | 100% |
| Gastos con respaldo | Por medir | ≥ 95% |
| Documentos críticos digitalizados | Por medir | ≥ 95% |
| Días entrega-factura | Por medir | ≤ 5 |
| Viajes sin facturar > 7 días | Por medir | 0 |
| Doble asignación | Desconocida | 0 |
| Tiempo de despacho | Por medir | −30% |
| Tiempo de cierre de viaje | Por medir | −50% |
| Adopción diaria | 0 | ≥ 90% |
| Satisfacción usuario | Por medir | ≥ 4/5 |

---

## 8. Riesgos del piloto

| Riesgo | Mitigación |
|---|---|
| Datos sucios | Dueño del dato, limpieza por olas, validaciones |
| Conductores no usan la app | Prueba con 2 conductores, botones grandes, offline, incentivo |
| El dueño cambia prioridades | Comité semanal, alcance congelado, cambio formal |
| Integración GPS/combustible no lista | CSV/manual en el piloto, API después |
| Contador no valida | Involucrarlo desde semana 1 |
| Poca capacidad del equipo | Priorizar, no prometer todo |
| Problemas de seguridad | MFA, roles, auditoría, backups |
| Pérdida de datos | Migración con respaldo, validación, rollback |

---

## 9. Decisiones que se necesitan antes de empezar

1. ¿Quién es el Product Owner?
2. ¿Quién es el dueño del dato?
3. ¿Qué 3 tractos y 3 choferes participan del piloto?
4. ¿Qué clientes/rutas entran?
5. ¿Qué OC están abiertas?
6. ¿Qué documentos críticos faltan?
7. ¿Qué GPS/tarjetas/peajes se usan?
8. ¿Qué proveedor de facturación electrónica?
9. ¿Qué política de comisión se aplica?
10. ¿Qué presupuesto y fecha de inicio?

---

## 10. Lo que NO se debe hacer en los 90 días

- No intentar implementar todo el ERP.
- No construir IA antes de tener datos.
- No migrar 10 años de historia.
- No cambiar el frontend completo.
- No prometer nómina legal sin asesoría.
- No dejar el piloto sin soporte en terreno.
- No medir solo “si el software funciona”; medir si **el negocio funciona mejor**.

---

## 11. Después del día 90

Si el piloto cumple los criterios:

1. Extender a toda la flota.
2. Iniciar Fase 2: costos, mantenimiento y precios.
3. Iniciar Fase 3: DTE, tesorería y caja.
4. Incorporar portal del cliente y copiloto.
5. Medir ROI y ajustar el plan.

Si no cumple:

1. No escalar.
2. Identificar la causa: datos, usabilidad, proceso, integración o adopción.
3. Corregir.
4. Repetir el piloto con alcance más pequeño.

**La regla es simple:** primero se demuestra en 3 camiones; después se escala a 30. No al revés.
