---
name: repo-forensics
description: "Determina el estado real del repositorio del ERP TEI, traza flujos UI→API→servicio→tabla y resuelve contradicciones entre documentos con una matriz de evidencia, sin reescribir la historia ni inventar reconciliaciones."
---

# Repo forensics — estado real y contradicciones

## 1. Objetivo y ámbito

Responder “¿qué existe, qué se usa y qué es cierto?” con evidencia primaria.
Sirve para onboarding, auditoría, diagnósticos y decisiones de migración.

No es una skill para arreglar el ERP. Es una skill para saber qué hay antes de
tocarlo.

## 2. Cuándo usarla

- Al empezar una tarea en un área desconocida.
- Cuando dos documentos se contradicen.
- Cuando alguien afirma “esto ya está terminado”.
- Antes de un cutover o una migración.
- Al investigar por qué una pantalla no refleja la base.

## 3. Contexto y precondiciones

- `AGENTS.md`.
- Acceso de lectura al repo.
- `git status` y `git log` para distinguir trabajo en curso.
- Capacidad de ejecutar búsquedas y, si es seguro, pruebas de solo lectura.
- No modificar nada durante el inventario.

## 4. Procedimiento

### 4.1 Inventario de fuentes

1. Lista documentos con fecha y propósito. No los trates como equivalentes.
2. Lista migraciones y el esquema que crean.
3. Lista routers montados y rutas declaradas.
4. Lista páginas y el cliente HTTP que usan.
5. Lista pruebas y qué cubren.
6. Revisa `git status`, `git diff --stat` y archivos sin seguimiento.
7. Identifica configuración de OpenCode, CI, scripts y seeds.

### 4.2 Trazabilidad

Para cada capacidad relevante:

```text
Pantalla → cliente HTTP → endpoint → dependencia auth → servicio → modelo → tabla/constraint → prueba
```

Marca dónde se corta la cadena. Un endpoint sin consumidor, una tabla sin
escritor o una prueba sin ejecución no son “implementación terminada”.

### 4.3 Matriz de evidencia

| Afirmación | Fuente | Evidencia | Ubicación | Clasificación | Confianza | Limitación |
|---|---|---|---|---|---|---|
| “POD implementado” | doc | tabla + endpoint + página | … | parcial | media | no se ejecutó E2E |

Clasificaciones: `confirmado`, `refutado`, `parcialmente confirmado`,
`sin verificar`.

### 4.4 Contradicciones

Para cada una:

1. Cita exacta de cada fuente.
2. Evidencia que la prueba o refuta.
3. Qué falta para decidir.
4. Impacto.
5. Pregunta concreta si requiere negocio/legal/datos.

No “armonices” los documentos. No edites el documento estratégico para que
coincida con el código.

### 4.5 Señales de duplicación

- Dos tablas para el mismo concepto (`public` vs `nucleo`).
- Dos endpoints para la misma acción.
- Dos pantallas para el mismo dato.
- Dos clientes HTTP.
- Dos validaciones con reglas distintas.
- Dos fuentes de numeración/folio.
- Escrituras simultáneas sin una garantía común.

## 5. Comandos seguros

```bash
git status --short
git log --oneline -10
find supabase/migrations -type f | sort
grep -rn "APIRouter" backend/app | head
grep -rn "nucleoFetch\|from \"@/lib/api\"" frontend/src/app | head
cd backend && ../.venv/bin/python -m pytest tests/test_nucleo_tiempo.py -q
```

No ejecutes migraciones, seeds, cutover, restore ni escrituras para “ver si
funciona”. Si necesitas la base, limita a `SELECT` y declara el alcance.

## 6. Comprobaciones verificables

- ¿La tabla existe en la migración aplicada?
- ¿El modelo SQLModel apunta al schema correcto?
- ¿El router está incluido en `api_router`?
- ¿La página usa el cliente correcto?
- ¿La prueba existe y se ejecuta?
- ¿Hay evidencia de ejecución o solo documentación?
- ¿El flujo tiene una sola fuente de verdad?
- ¿Hay escrituras concurrentes no cubiertas?

## 7. Errores frecuentes

- Leer solo `README.md`.
- Confundir “archivo existe” con “está montado”.
- Confundir “endpoint existe” con “la UI lo usa”.
- Ignorar archivos staged/untracked.
- Creer que un test que se omite pasó.
- Resolver una contradicción con una explicación plausible sin evidencia.
- Hacer un inventario y no registrar ubicaciones.

## 8. Criterios de aceptación

- Hay una matriz con evidencia y limitaciones.
- Las cadenas UI→DB están trazadas o se indica dónde se cortan.
- Las contradicciones están clasificadas.
- No se modificó el repositorio.
- Las afirmaciones “terminado” están respaldadas o marcadas como no verificadas.

## 9. Formato de entrega

```text
## Alcance
## Inventario
## Trazabilidad
## Matriz de evidencia
## Contradicciones
## Duplicaciones y riesgos
## No verificado
## Recomendación de siguiente paso
```

## 10. Referencias

- `docs/arquitectura/nucleo-diseno.md`
- `docs/estado.md`
- `docs/desarrollo/backlog.md`
- `supabase/migrations/`
- `backend/app/api/router.py`
- `frontend/src/lib/api.ts`, `frontend/src/lib/nucleo.ts`
