---
name: testing
description: "Convierte requisitos y defectos del ERP TEI en pruebas reproducibles (unitarias, integración PostgreSQL, HTTP, E2E y regresión), registra evidencia real y evita aprobaciones falsas por tests omitidos o entornos incompletos."
---

# Testing — reproducir, probar, evidenciar

## 1. Objetivo y ámbito

Asegurar que un cambio se comporta como se espera y que otra persona puede
repetir la verificación. Cubre pruebas unitarias, integración, HTTP, E2E,
regresión y TDD selectivo.

## 2. Cuándo usarla

- Antes de declarar un cambio terminado.
- Al reproducir un bug.
- Al implementar una regla crítica.
- Al revisar una migración o un cambio de permisos.
- Cuando la suite falla o se omite.

## 3. Contexto y precondiciones

- `AGENTS.md` leído.
- Comando de pruebas identificado (`make unit`, `make test`, `make e2e`).
- Entorno: Python `.venv`, PostgreSQL local, frontend/seed si es E2E.
- Datos de prueba aislados; nunca datos reales.
- Si falta un servicio, se declara; no se inventa el resultado.

## 4. Procedimiento

1. **Baseline**: ejecuta la prueba o suite del área antes de cambiar. Registra el
   resultado.
2. **Reproduce**: reduce el caso al mínimo. Si no puedes, documenta qué falta.
3. **Define el nivel**:
   - unitaria: regla pura, cálculo, fecha, estado, contrato;
   - integración: constraint, trigger, transacción, concurrencia, RLS;
   - HTTP: endpoint, códigos, auth, roles, headers;
   - E2E: flujo visible;
   - regresión: área y suites relacionadas.
4. **Rojo**: escribe la prueba que falla por la razón correcta. Verifica el
   mensaje.
5. **Verde**: implementa o solicita la corrección; vuelve a ejecutar.
6. **Bordes**: agrega negativo, límite y adversarial si el riesgo lo justifica.
7. **Regresión**: ejecuta la suite del área y, si toca varios módulos, la
   completa.
8. **Evidencia**: guarda comando, entorno, salida y fecha.

## 5. Comandos del repo

```bash
make unit                 # unitarias sin base
make db-up                # Supabase local
make seed                 # datos del piloto
make test                 # suite completa con PostgreSQL
make e2e                  # Playwright
cd backend && ../.venv/bin/python -m pytest tests/test_x.py -q
cd frontend && npx tsc --noEmit
cd frontend && npm run lint
```

No ejecutes `make db-reset` ni `make cutover` para “arreglar” pruebas sin
autorización.

## 6. Comprobaciones verificables

- La prueba falla si se elimina la corrección.
- La prueba no depende del orden de ejecución.
- La prueba no usa la fecha/hora real sin control.
- La prueba no comparte estado con otras.
- La prueba de concurrencia usa conexiones reales.
- La prueba de permisos usa un rol sin permiso y otro con permiso.
- La prueba de tenant usa datos de dos empresas.
- El resultado incluye `passed/failed/skipped`, no solo “OK”.

## 7. Errores frecuentes

- Probar solo el camino feliz.
- Mockear la capa que se quiere verificar.
- Declarar verde con tests omitidos.
- Cambiar la expectativa para que pase.
- Desactivar un test o un hook.
- Prueba de concurrencia secuencial.
- Datos compartidos que hacen que el orden importe.
- Dependencia de la fecha actual, zona horaria o red.
- E2E que solo verifica que la página “carga”.

## 8. Criterios de aceptación

- Hay una prueba reproducible para el comportamiento.
- El comando y la salida están registrados.
- Los fallos y omisiones están explicados.
- La regresión del área pasa.
- Los casos negativos relevantes están cubiertos.
- No se modificó el código de producción desde QA (si aplica).

## 9. Formato de entrega

```text
## Escenario
## Comando
## Resultado real
## Cobertura
## Fallos/omisiones
## Evidencia
```

## 10. Referencias

- pytest: <https://docs.pytest.org/>
- Playwright: <https://playwright.dev/docs/intro>
- FastAPI testing: <https://fastapi.tiangolo.com/tutorial/testing/>
