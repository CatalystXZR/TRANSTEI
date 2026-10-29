---
name: code-review
description: "Revisión independiente de cambios del ERP TEI priorizando defectos funcionales, seguridad, datos, concurrencia y regresiones sobre estilo; produce hallazgos con severidad, evidencia archivo:línea y verificación."
---

# Code review — defectos antes que estilo

## 1. Objetivo y ámbito

Encontrar lo que puede romper el sistema antes de que llegue a producción.
Prioriza corrección funcional, seguridad, integridad de datos, concurrencia y
regresiones. El estilo solo importa si afecta mantenibilidad o consistencia real.

## 2. Cuándo usarla

- Antes de cerrar un cambio de riesgo medio/alto.
- Después de una implementación de otro agente.
- Al revisar una migración, un endpoint o una pantalla crítica.
- Cuando el autor pide “revisa esto” sin criterios claros.

## 3. Contexto y precondiciones

- `AGENTS.md` y el contrato de tarea.
- Diff completo (`git diff`, `git diff --staged`).
- Código circundante, no solo las líneas cambiadas.
- Pruebas ejecutadas por el autor y sus resultados.
- Si falta contexto, pídelo; no supongas.

## 4. Procedimiento

1. **Entiende el objetivo** y los criterios de aceptación.
2. **Lee el diff** y clasifica los archivos: producción, tests, migraciones,
   configuración, documentación.
3. **Traza el flujo** afectado: entrada → validación → auth → servicio →
   transacción → DB → respuesta → UI.
4. **Busca defectos** en este orden:
   - corrección funcional;
   - autorización/aislamiento;
   - integridad y concurrencia;
   - migraciones/compatibilidad;
   - errores y estados;
   - regresiones;
   - rendimiento;
   - mantenibilidad.
5. **Verifica** al menos una afirmación crítica con el código o una prueba.
6. **Clasifica** cada hallazgo y descarta los que no puedas sustentar.
7. **Revisa el diff completo** por secretos, artefactos y cambios accidentales.

## 5. Comprobaciones verificables (qué buscar en este repo)

- ¿Se usa el cliente HTTP correcto (legacy vs núcleo)?
- ¿La empresa se resuelve en el servidor o se acepta del body?
- ¿El endpoint tiene permiso y rol, no solo UI oculta?
- ¿La transacción cubre todos los efectos?
- ¿La constraint está en DB o solo en Python?
- ¿Hay TOCTOU, doble asignación, doble pago, doble factura?
- ¿Las fechas son aware y los rangos semiabiertos?
- ¿El dinero usa `Decimal`/`numeric`?
- ¿Se rompe un contrato existente del frontend?
- ¿La migración es forward-only y compatible?
- ¿Se agrega una tercera fuente de verdad?
- ¿Se desactiva una prueba, un control o un error?
- ¿Hay secretos, `.env`, logs sensibles o datos personales?
- ¿El cambio tiene pruebas y éstas prueban el comportamiento?

## 6. Severidad

| Nivel | Significado |
|---|---|
| Blocker | Pérdida de datos/dinero, bypass de auth, corrupción, caída |
| Alta | Regla crítica mal implementada, aislamiento roto, concurrencia |
| Media | Bug funcional acotado, error de estado, regresión probable |
| Baja | Mantenibilidad, mensaje, consistencia menor |
| Nit | Estilo o preferencia sin impacto demostrado |

No infles la severidad para llamar la atención. No la bajes para cerrar antes.

## 7. Errores frecuentes

- Revisar el plan del autor en vez del código.
- Confiar en el resumen sin abrir el diff.
- Comentar solo estilo.
- Reportar un “posible” problema sin evidencia.
- Ignorar tests, migraciones o configuración.
- No revisar el código circundante.
- Aceptar “funciona en mi máquina”.
- No verificar el caso negativo.

## 8. Criterios de aceptación

- Cada hallazgo tiene archivo:línea, escenario e impacto.
- Los hallazgos están priorizados y son accionables.
- No hay falsos positivos presentados como confirmados.
- Se indicó qué se verificó y qué no.
- El veredicto es claro: aprobar, aprobar con cambios o bloquear.

## 9. Formato de entrega

```text
## Veredicto
<aprobar | aprobar con cambios | bloquear>

## Hallazgos
### [Severidad] Título
- Ubicación: archivo:línea
- Escenario: ...
- Impacto: ...
- Evidencia: ...
- Remediación: ...

## Verificado
<qué se ejecutó/revisó>

## No verificado
<qué falta>

## Observaciones menores
<estilo/consistencia, separado>
```

## 10. Referencias

- OWASP ASVS: <https://owasp.org/www-project-application-security-verification-standard/>
- OWASP Top 10: <https://owasp.org/www-project-top-ten/>
- PostgreSQL constraints: <https://www.postgresql.org/docs/current/ddl-constraints.html>
