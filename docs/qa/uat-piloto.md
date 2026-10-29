# UAT — Piloto 90 días (P0-01 a P0-13)

**Versión:** 1.0  
**Fecha:** Octubre 2026  
**Alcance:** validación funcional del núcleo operativo y comercial en local/Supabase.  
**Fuera de alcance:** DTE real SII, GPS, combustible, peajes, bancos, WhatsApp y firma electrónica externa.

> **Estado: PLAN NO EJECUTADO.** La tabla de evidencia (§4) está vacía: no hay fecha,
> ejecutor ni resultado por escenario. Este documento define **qué** hay que validar;
> no es una aprobación. Ver `docs/estado.md` para lo que sí está verificado.

---

## 1. Entorno y credenciales

| Elemento | Valor |
|---|---|
| Frontend | `http://localhost:3000` |
| API | `http://localhost:8000/api/v1` |
| Supabase Studio | `http://127.0.0.1:54323` |
| Seed | `.venv/bin/python scripts/seed_local.py` |
| E2E | `cd frontend && npm run test:e2e` |
| Backup/restore | `scripts/restore_drill.sh` |
| Cutover | `scripts/cutover_legacy.py --freeze` |

Todos los usuarios usan la clave **TEI2026!**:

`admin@tei.local`, `gerente@tei.local`, `despacho@tei.local`, `contador@tei.local`, `tesoreria@tei.local`, `taller@tei.local`, `conductor@tei.local`, `auditor@tei.local`.

---

## 2. Criterio de aceptación

Un escenario se acepta solo si:

1. La pantalla carga sin error de consola.
2. El backend rechaza datos inválidos con un mensaje legible.
3. La base impide el estado/duplicado/solapamiento aunque el servicio falle.
4. El cambio queda en auditoría.
5. El rol sin permiso recibe 403/409 y no ve la acción como disponible.
6. El flujo deja datos consistentes al recargar.

---

## 3. Escenarios por módulo

### P0-01 — Alta de viaje y despacho
- [ ] Crear viaje con cliente, tarifa, OC, ruta, ventana y carga.
- [ ] Ver el flete calculado y el folio `VJ-...`.
- [ ] Intentar crear viaje con fecha naive, fin anterior o ventana > 90 días.
- [ ] Intentar tarifa/OC de otro cliente; debe rechazar.
- [ ] Intentar peligrosa sin UN y refrigerada sin temperaturas; debe rechazar.
- [ ] Asignar tracto, rampla y chofer; validar disponibilidad.
- [ ] Intentar doble asignación concurrente; PostgreSQL debe impedirla.

### P0-02 — Maestros y documentos
- [ ] Crear/editar/desactivar cliente, tracto, rampla y chofer.
- [ ] Verificar que un cliente con viaje activo no se desactiva.
- [ ] Subir documento PDF/JPG, ver versión vigente y URL firmada.
- [ ] Reemplazar documento; la versión anterior queda histórica.
- [ ] Subir extensión no permitida o archivo > 10 MB; debe rechazar.
- [ ] Desactivar un recurso con reservas futuras; debe rechazar.

### P0-03 — Tarifas, OC y consumo
- [ ] Crear tarifa y editar precio/vigencia.
- [ ] Crear OC con líneas y centro de costo.
- [ ] Ver consumo por viaje, saldo y alerta 80/90/100 %.
- [ ] Solicitar sobregiro como despacho y aprobar como gerencia.
- [ ] Intentar aprobar sobregiro con despacho; debe dar 403.
- [ ] Reducir monto de OC bajo el consumo; debe rechazar.
- [ ] Anular OC con viaje activo; debe rechazar.
- [ ] Ver historial de cambios de tarifa/OC.

### P0-04 — Agenda y bloqueos
- [ ] Crear mantención, descanso y vacaciones.
- [ ] Ver el bloqueo en el calendario y en disponibilidad.
- [ ] Intentar solapar dos bloqueos o un bloqueo con viaje; debe rechazar.
- [ ] Cancelar bloqueo con motivo; la ventana queda libre.
- [ ] Verificar que el bloqueo cancelado no se borra.

### P0-05 — Expediente
- [ ] Abrir detalle con QR, ruta, carga, recursos y finanzas.
- [ ] Agregar/editar parada y marcar estado.
- [ ] Completar checklist obligatorio.
- [ ] Registrar evento y verificar que no se puede editar/borrar.
- [ ] Reportar incidente alto; debe bloquear cierre.
- [ ] Resolver incidente y cerrar viaje.
- [ ] Verificar que un viaje futuro no se puede cerrar.
- [ ] Adjuntar documento y abrirlo con URL firmada.

### P0-06 — POD
- [ ] Registrar POD con receptor, RUT, firma, foto y geolocalización.
- [ ] Verificar que sin POD no se puede facturar.
- [ ] Intentar segundo POD; debe exigir actualización versionada.
- [ ] Reemplazar POD y ver nueva versión/evento.
- [ ] Verificar que el POD no se borra.

### P0-07 — PWA del conductor
- [ ] Login con `conductor@tei.local` y `next=/conductor`.
- [ ] Ver “mi viaje” o estado vacío.
- [ ] Check-in, cargar, iniciar ruta, descarga y check-out.
- [ ] Completar checklist desde el teléfono.
- [ ] Reportar incidente y subir foto.
- [ ] Registrar POD desde la PWA.
- [ ] Activar modo offline, tocar checklist y ver cola pendiente.
- [ ] Volver online y confirmar sincronización.

### P0-08 — Gastos y costo real
- [ ] Registrar combustible con litros, precio y comprobante.
- [ ] Registrar peaje/TAG y estadía.
- [ ] Aprobar gasto con otro usuario; intentar autoaprobación debe dar 403.
- [ ] Ver costo variable, comisión, margen, litros, rendimiento y costo/km.
- [ ] Rechazar gasto con motivo y verificar que no suma al costo.

### P0-09 — Margen y Freight Score
- [ ] Guardar parámetros de costo.
- [ ] Simular flete del catálogo (500 km, 25 t, $1.200.000, 45 días) → score ~92,9 verde.
- [ ] Simular flete malo → amarillo/rojo.
- [ ] Ver tarifa piso estratégica y táctica.
- [ ] Abrir rentabilidad de un viaje con gasto aprobado y ver fuente “real”.
- [ ] Verificar que el score quedó guardado en el viaje.

### P0-10 — Facturación y cobranza
- [ ] Emitir factura desde viaje cerrado con POD y OC.
- [ ] Intentar facturar viaje sin POD, sin OC, no cerrado o ya facturado; debe rechazar.
- [ ] Registrar pago parcial; estado `parcial` y saldo correcto.
- [ ] Aplicar nota de crédito; saldo disminuye.
- [ ] Registrar pago final; estado `pagada` y viaje `cobrado`.
- [ ] Intentar pago sobre saldo; debe rechazar.
- [ ] Verificar aging 0–30/31–60/61–90/>90.
- [ ] Registrar promesa de pago.

### P0-11 — Alertas y tablero
- [ ] Ver briefing diario y acciones sugeridas.
- [ ] Ver alertas de documentos, mantención, POD, sin facturar, OC, CxC, margen, incidentes y caja.
- [ ] Filtrar por severidad y categoría.
- [ ] Abrir la pantalla de resolución desde una alerta.

### P0-12 — Roles y auditoría
- [ ] Revisar matriz de 8 roles y permisos personales.
- [ ] Verificar 403 al intentar una acción sin permiso.
- [ ] Confirmar segregación: quien registra gasto no lo aprueba.
- [ ] Filtrar auditoría por tabla, operación, UUID y fecha.
- [ ] Ver diff antes/después de un cambio.

### P0-13 — Cutover y continuidad
- [ ] Ejecutar seed completo y validar 8 usuarios.
- [ ] Ejecutar `scripts/restore_drill.sh` y confirmar `restore_ok`.
- [ ] Ejecutar `npm run test:e2e` (9 escenarios).
- [ ] Ejecutar `scripts/cutover_legacy.py --dry-run` y luego `--freeze`.
- [ ] Verificar que POST legacy devuelve 409 y que el núcleo sigue operando.
- [ ] Confirmar backup final y checklist de cutover.

---

## 4. Evidencia

| Fecha | Módulo | Ejecutor | Resultado | Evidencia |
|---|---|---|---|---|
| | P0-01 | | | |
| | P0-02 | | | |
| | P0-03 | | | |
| | P0-04 | | | |
| | P0-05 | | | |
| | P0-06 | | | |
| | P0-07 | | | |
| | P0-08 | | | |
| | P0-09 | | | |
| | P0-10 | | | |
| | P0-11 | | | |
| | P0-12 | | | |
| | P0-13 | | | |

---

## 5. Limitaciones conocidas del piloto

- Facturación sin DTE real: el folio se simula y no se envía al SII.
- Storage local: las URLs firmadas expiran; el visor requiere Supabase local activo.
- Sin integraciones reales de GPS, combustible, peajes, banco, WhatsApp ni firma electrónica.
- La PWA cachea shell y encola acciones JSON; fotos y POD requieren conexión.
- Los datos de seed son ficticios; la UAT con datos reales requiere la lista de maestros y tarifas del negocio.
- La migración legacy asume pesos/capacidades estándar cuando el legacy no los tiene; debe revisarse antes de producción.

---

## 6. Aprobación

| Rol | Nombre | Fecha | Firma |
|---|---|---|---|
| Dueño / gerencia | | | |
| Despacho | | | |
| Contabilidad | | | |
| Tesorería | | | |
| TI / operador | | | |
