# Guía de desarrollo

> **Pregunta que responde:** ¿dónde toco el código y con qué convenciones?
> **Dueño:** `orquestador` · **Verificado:** 2026-10-29 · **Método:** lectura de estructura y `AGENTS.md`
> **Caduca si:** cambia la estructura de carpetas o el stack.
> **Re-verificar con:** `ls backend/app backend/app/nucleo frontend/src/app`

---

## 1. Regla de oro: dos capas, no tres

| Capa | Schema | Backend | Cliente | ¿Multiempresa? |
|---|---|---|---|---|
| Legacy | `public` | `backend/app/api/routes/` | `frontend/src/lib/api.ts` | No |
| Núcleo | `nucleo` | `backend/app/nucleo/` | `frontend/src/lib/nucleo.ts` | Sí |

**Nunca** agregues una tercera fuente de verdad. Si un concepto ya existe en una capa,
extendé esa capa o documentá el cutover en un ADR. Ver `arquitectura/fuentes-de-verdad.md`.

---

## 2. Dónde va cada cosa

| Si vas a… | Escribí en |
|---|---|
| Regla de negocio del núcleo | `backend/app/nucleo/servicio_*.py` |
| Validación cruzada de dominio | `backend/app/nucleo/politicas.py` |
| Endpoint del núcleo | `backend/app/nucleo/api_*.py` + montar en `api/router.py` |
| Endpoint legacy | `backend/app/api/routes/*.py` |
| Modelo SQLModel | `backend/app/nucleo/models.py` (esquema `nucleo`) |
| Migración | `supabase/migrations/00NN_*.sql` (forward-only) |
| Pantalla | `frontend/src/app/(app)/<ruta>/page.tsx` |
| Cliente HTTP del núcleo | `frontend/src/lib/nucleo.ts` |
| Menú / navegación | `frontend/src/lib/navigation.ts` |
| Prueba backend | `backend/tests/test_nucleo_*.py` |
| E2E | `frontend/e2e/tei.spec.ts` |

---

## 3. Convenciones obligatorias

### Dinero y fechas
- Dinero en `numeric`, **nunca `float`**. Si calculás en Python, usá `Decimal`.
- Eventos en `timestamptz` (UTC en base); zona `America/Santiago` sola en presentación.
- `date` solo para vencimientos y vigencias.
- Rangos del núcleo **semiabiertos** `[inicio, fin)`.

### Base de datos
- Migraciones forward-only, numeración consecutiva; **no se edita una aplicada**.
- Garantías críticas en PostgreSQL (`EXCLUDE`, `CHECK`, `UNIQUE` parcial, trigger), no solo en el servicio.
- Errores → HTTP: `23505`/`23P01` → 409; `23514`/`23502` → 422. Nunca 500 por conflicto de negocio.

### Autorización
- La empresa sale de `X-Empresa-ID` + membresía, **nunca** del body.
- Todo endpoint nuevo declara permiso (deny-by-default), incluidos verbos secundarios.
- Ocultar un botón no es autorización.

### Dinero y estado
- Operaciones con dinero o transición de estado exigen **idempotencia**.
- Un doble clic no puede duplicar un pago ni una factura.

---

## 4. Flujo de trabajo

1. `git status --short` — no pises trabajo ajeno.
2. Trazá el flujo completo: pantalla → cliente → router → permiso → servicio → tabla → prueba.
3. Clasificá el riesgo (bajo / medio / alto). Alto = dinero, permisos, tenant, migraciones, cutover.
4. Cambio mínimo; sin refactors de paso.
5. Prueba del cambio + regresión del área.
6. `make unit` (y `make test` si tocaste base).
7. Revisá el diff: sin secretos, sin artefactos, sin `skip` nuevos.

---

## 5. Lo que no se hace

- `SQLModel.metadata.create_all()` como sustituto de migraciones.
- Borrar o desactivar pruebas para "cerrar en verde".
- `try/except` amplios que esconden fallos.
- Migrar el legacy por iniciativa propia.
- Presentar el legacy como multiempresa.
- Escribir secretos en código, commits o logs.

---

## 6. Antes de decir "terminado"

| Riesgo | Evidencia mínima |
|---|---|
| Bajo | Diff revisado + `make unit` |
| Medio | + integración/HTTP + regresión del área |
| Alto | + adversariales + concurrencia real (dos conexiones) + revisión independiente + rollback |

Ver `desarrollo/pruebas.md` y `docs/estado.md`.
