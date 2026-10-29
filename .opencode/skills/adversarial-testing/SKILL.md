---
name: adversarial-testing
description: "Busca de forma sistemática escenarios que rompan las reglas de negocio y los controles de seguridad del ERP TEI: límites, estados ilegales, concurrencia, datos de otra empresa, idempotencia, archivos y abuso. Produce casos reproducibles con evidencia."
---

# Adversarial testing — romper antes de que rompan

## 1. Objetivo y ámbito

Encontrar los casos que el camino feliz no cubre: entradas límite, estados
ilegales, carreras, datos de otra empresa, reintentos, archivos maliciosos y
abuso de permisos. No es “probar más”; es atacar supuestos concretos.

## 2. Cuándo usarla

- Cambios de alto riesgo: dinero, permisos, disponibilidad, migraciones, auth.
- Antes de un cutover o una entrega.
- Al revisar un módulo nuevo.
- Cuando una prueba solo cubre el caso normal.
- Al investigar un incidente.

## 3. Contexto y precondiciones

- `AGENTS.md`, `testing`, `postgres-concurrency`, `finance-invariants`.
- Entorno local y datos de seed/fixtures.
- Autorización para las pruebas; nada contra producción.
- Modelo de amenaza o invariantes a atacar.
- Capacidad de observar respuestas, logs y estado de la base.

## 4. Procedimiento

1. **Elige el objetivo**: una regla, un control o un invariante.
2. **Enumera los límites**: 0, negativo, máximo, vacío, nulo, duplicado,
   fuera de rango, tipo incorrecto, encoding, zona horaria.
3. **Enumera los estados**: transiciones ilegales, recurso cerrado, factura
   pagada, viaje anulado.
4. **Enumera los actores**: sin token, rol mínimo, otra empresa, usuario
   inactivo, recurso ajeno.
5. **Enumera los tiempos**: doble clic, reintento, concurrencia, expiración,
   cambio de hora.
6. **Ejecuta** el caso mínimo reproducible.
7. **Observa**: código HTTP, cuerpo, estado en DB, auditoría, logs.
8. **Clasifica**: confirmado, potencial, no reproducible.
9. **Minimiza** y documenta pasos.
10. **Agrega regresión** si el defecto es real.

## 5. Catálogo de ataques

### Fechas y ventanas

- Fecha naive, ISO sin zona, DST de Chile, fin antes de inicio, ventana > 90 días.
- Borde exacto `[inicio, fin)`, buffer de 90 min, ETA retrasada.
- Recurso ocupado por mantención/descanso/bloqueo.

### Dinero

- 0, negativo, máximo, decimales, redondeo, moneda.
- Pago parcial, sobrepago, nota de crédito, anulación, reintento.
- Comisión sobre viaje anulado, costo duplicado al reasignar.

### Autorización y tenant

- Sin token, token expirado, token de otro usuario.
- Rol sin permiso, membresía inactiva, empresa inactiva.
- UUID de otra empresa, `empresa_id` en body, header manipulado.
- Recurso propio vs recurso ajeno.

### Estados

- Transición hacia atrás, salto de estado, cierre con incidente abierto.
- Facturar sin POD/OC, cobrar factura anulada, aprobar gasto propio.
- Reabrir viaje cerrado, borrar reserva/documento.

### Idempotencia y concurrencia

- Doble POST, reintento de pago/factura, doble aprobación.
- Dos conexiones reales sobre la misma ventana/recurso.
- Folio concurrente, consumo de OC concurrente.

### Archivos y entradas

- Archivo vacío, > 10 MB, extensión falsa, MIME incorrecto, path traversal.
- CSV con `=`, `+`, `-`, `@` (inyección de fórmulas), XSS en texto.
- SQL injection en filtros; comodines; paginación extrema.

### Abuso

- Enumeración de UUID, fuerza bruta, rate limit, logs con datos sensibles.
- URLs firmadas reutilizadas, bucket público, CORS amplio.

## 6. Comprobaciones verificables

- [ ] El caso tiene pasos mínimos y resultado esperado.
- [ ] El resultado real está registrado (código, cuerpo, DB).
- [ ] Se probó al menos un actor sin permiso.
- [ ] Se probó al menos un dato de otra empresa.
- [ ] La concurrencia usó conexiones reales.
- [ ] El caso no modifica datos reales.
- [ ] Si se encontró un defecto, hay regresión propuesta.

## 7. Errores frecuentes

- Probar solo la UI.
- Simular concurrencia con llamadas secuenciales.
- Usar datos de producción.
- Reportar un “posible” sin reproducir.
- Ignorar el estado de la base después del ataque.
- No probar el rol mínimo.
- Confundir un 400 esperado con un defecto.
- Atacar servicios externos o producción.

## 8. Criterios de aceptación

- Los casos son reproducibles por otra persona.
- Hay evidencia de resultado esperado vs actual.
- Los defectos están priorizados por impacto.
- Las pruebas destructivas se hicieron en local/fixtures.
- Se agregó o propuso regresión para lo confirmado.

## 9. Formato de entrega

```text
## Objetivo
## Casos
| # | Escenario | Esperado | Actual | Estado |
## Evidencia
## Defectos
<severidad, impacto, reproducción>
## Regresión propuesta
## No probado / límites
```

## 10. Referencias

- OWASP Top 10: <https://owasp.org/www-project-top-ten/>
- OWASP ASVS: <https://owasp.org/www-project-application-security-verification-standard/>
- OWASP Testing Guide: <https://owasp.org/www-project-web-security-testing-guide/>
- PostgreSQL concurrency: <https://www.postgresql.org/docs/current/transaction-iso.html>
