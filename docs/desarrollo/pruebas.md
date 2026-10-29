# Pruebas — qué probar, cómo ejecutar y cómo saber que sirve

> **Pregunta que responde:** ¿qué prueba escribo para este cambio y cómo verifico que no es decorativa?
> **Dueño:** `qa` · **Verificado:** 2026-10-29 · **Método:** ejecución (`make unit`) + lectura
> **Caduca si:** cambia el `Makefile`, la estructura de pruebas o el entorno de base.
> **Re-verificar con:** `make unit` y `ls backend/tests/*.py | wc -l`

---

## 1. El riesgo define la prueba

| Riesgo | Alcance | Verificación mínima |
|---|---|---|
| **Bajo** | docs, textos, tests sin cambio de conducta | diff + `make unit` |
| **Medio** | endpoint, pantalla, consulta, validación no financiera | unitarias + integración/HTTP + regresión del área |
| **Alto** | dinero, permisos, tenant, persistencia, disponibilidad, migraciones, cutover | + adversariales + **concurrencia real** + revisión independiente + rollback |

Por área:

- **Dinero:** redondeo, IVA, pagos parciales, sobrepago, nota de crédito, anulación, doble clic, valores 0 y negativos.
- **Permisos:** 401/403/200, otra empresa, IDOR, `empresa_id` en el body, membresía inactiva.
- **Disponibilidad:** solape, borde `fin == inicio`, buffer, DST de Chile, reasignación, cancelación.
- **Estados:** transición ilegal o hacia atrás.
- **Entradas:** fecha naive, fin < inicio, ventana > 90 días, CSV/XSS.
- **Archivos:** vacío, MIME real, tamaño, path traversal.
- **Concurrencia:** dos conexiones reales, exactamente una gana.

---

## 2. Dónde vive cada prueba

| Tipo | Ubicación | Requisito | Comando |
|---|---|---|---|
| Unitaria | `backend/tests/test_nucleo_*.py` | — | `make unit` |
| Integración PostgreSQL | `backend/tests/test_nucleo_*.py` | base + `NUCLEO_TEST_DATABASE_URL` | `make test` |
| HTTP legacy | `backend/tests/test_flujos_criticos.py` | base + `TEST_*` | `make test` |
| Reglas R-01/R-02 | `backend/tests/test_reglas_negocio.py` | base + **`DATABASE_URL`** | `make test` |
| SQL | `supabase/tests/*.sql` | psql + fixtures | manual |
| Concurrencia | `supabase/tests/0015_02_concurrencia_rampla.py` | 2 conexiones | manual |
| E2E | `frontend/e2e/tei.spec.ts` | frontend + backend + base + seed | `make e2e` |

🟢 Medido: **22 archivos** en `backend/tests/` = 21 módulos + `conftest.py`.

---

## 3. Los módulos por dominio

**Unitarias puras (6):** `test_nucleo_tiempo` (DST y bordes), `test_nucleo_politicas` (A5, carga, OC), `test_nucleo_schemas` (entradas), `test_nucleo_modelos` (esquema), `test_nucleo_tarifas` (dinero), `test_kpi_engine` (**no lo corre `make unit`**).

**Integración del núcleo (13):** `integracion` (asignación), `bloqueos` (agenda), `comercial` (OC/sobregiro), `maestros`, `expediente`, `pod`, `gastos`, `rentabilidad`, `facturacion`, `alertas`, `conductor`, `cutover`, `permisos`.

**HTTP legacy (1):** `test_flujos_criticos`.

**Reglas (1):** `test_reglas_negocio` (usa `DATABASE_URL`).

**Infra:** `conftest.py` (login, fixture `db`, etiqueta; omite si faltan `TEST_*`).

---

## 4. Cómo se ejecuta

```bash
make unit      # 5 módulos, 52 passed (corte 2026-10-29). Deja fuera test_kpi_engine
make test      # hace db-up, exporta NUCLEO_TEST_DATABASE_URL + TEST_*, escribe datos locales
make e2e       # requiere :3000, :8000, base + seed
```

- SQL: `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/00XX_*.sql`
- Concurrencia: `.venv/bin/python supabase/tests/0015_02_concurrencia_rampla.py`

---

## 5. Concurrencia real

Dos conexiones simultáneas con barrera. Afirmar **exactamente una ganadora**, la otra con
`23P01`/`23505`, y el conteo final correcto. Dos llamadas seguidas **no** prueban
concurrencia.

🟢 En `backend/tests/` no hay ninguna prueba de este tipo: `conftest.py:66` abre una
conexión solo para verificar conectividad.

Para dinero, `SELECT … FOR UPDATE`; sin lock, dos transacciones leen el mismo saldo
(INV-F01). Sanidad: retirar el `EXCLUDE` o el lock en una copia desechable y confirmar
que la prueba falla.

---

## 6. Trampas conocidas

1. **`skip` ≠ aprobado.** `conftest.py:63-64` y `test_reglas_negocio.py:114-120` omiten
   el módulo si falta la variable: la suite puede verse verde sin haber ejecutado nada.
2. **`DATABASE_URL` ≠ `NUCLEO_TEST_DATABASE_URL`** (SEC-010). `make test` exporta la
   segunda; `test_reglas_negocio` y el fixture `db` leen la primera. Si `DATABASE_URL`
   apunta a staging, la prueba **escribe ahí**.
3. **`make test` arranca Supabase** (`test: db-up`): no es solo `pytest`.
4. **Mutación obligatoria** en garantías críticas. Único caso ejecutado: fixture A5
   (`docs/qa/informes/2026-10-29-r01-r02-suite-verde.md`).
5. **Fixtures A5:** `licencia_clase="A5"` + 9 documentos; si faltan, `23514`.
6. **E2E débil** (SEC-011): `tei.spec.ts:48-54` y `:96-100` pueden pasar sin probar el flujo.
7. **Fechas:** `date.today()`/UTC, nunca meses fijos. DST cubierto en `test_nucleo_tiempo.py`.
8. **Aislamiento** por etiqueta/UUID; `test_reglas_negocio` usa savepoint revertido.
9. **Nunca** `xfail`/`skip` para tapar defectos ni borrar pruebas.
10. **`make unit` no es toda la suite unitaria** (deja fuera `test_kpi_engine`).
11. **No repitas 52/9 sin re-ejecutar:** cifra viva en `docs/estado.md` §2; corte en
    `docs/qa/linea-base.md`.

---

## 7. Checklist antes de "prueba lista"

- [ ] Falla por la razón correcta antes del arreglo (o defecto ya confirmado por lectura).
- [ ] Nombre: escenario + resultado. Sin condicionales en el cuerpo.
- [ ] Datos aislados (dos empresas si es tenant), reloj controlado.
- [ ] Concurrencia = dos conexiones reales.
- [ ] Mutación: sin el mecanismo, la prueba falla.
- [ ] `make unit` verde + regresión del área.
- [ ] Salida real pegada; `skipped` contados aparte.
- [ ] Fila actualizada en `docs/qa/matriz-trazabilidad.md`; si no hay prueba, "sin cobertura".
- [ ] Sin `xfail`, sin `skip` nuevos, sin pruebas borradas.
