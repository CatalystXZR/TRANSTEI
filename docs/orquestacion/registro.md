# Registro de orquestación

> **Nota de lectura:** las entradas anteriores al 2026-10-29 15:00 citan rutas que
> después se reorganizaron. El mapa vigente es [`docs/INDEX.md`](../INDEX.md); los
> documentos movidos están en `docs/_archivo/`.

---

### [2026-10-29] Reorganización documental completa

**Riesgo:** Medio (no toca código de producción ni datos; sí mueve 30 archivos sin
versionar y cambia rutas que los agentes citan).

**Estado:** cerrada — olas 1 a 6 ejecutadas.

#### Qué se hizo

| Ola | Acción | Resultado |
|---|---|---|
| 0 | Notas personales del dueño sacadas del repo (integridad SHA-256 verificada) + respaldo `tar.gz` de todo el corpus | `_privado-tei/` fuera del repositorio |
| 1 | Creados `docs/INDEX.md`, `docs/mapa-sistema.md`, `docs/estado.md` | Punto de entrada único; el único documento con cifras volátiles es `estado.md` |
| 2 | 15 documentos históricos movidos a `docs/_archivo/{planes,mvp}/` con banner "NO CITAR COMO ESTADO" | `_archivo/README.md` con tabla de reemplazos |
| 3 | Corregidos los documentos que se citaban a diario | `AGENTS.md` §1/§2/§11/§14/§15, `README.md`, contrato R-01, `negocio/catalogo-reglas.md` R-02, `operacion/cutover.md` |
| 4 | Redactados los documentos faltantes por especialidad | `arquitectura/`, `datos/`, `negocio/`, `qa/`, `desarrollo/`, `operacion/` |
| 5 | Contratos de agentes y skills sincronizados con la taxonomía real | 0 referencias a rutas fantasma |
| 6 | Verificación | `opencode debug agents` descubre los 8 agentes; 0 enlaces rotos fuera de `_archivo` |

#### Hechos confirmados (evidencia primaria)

- `make unit` → **52 passed** (esta sesión).
- `supabase/migrations/` → **19 archivos**; `HEAD` solo contiene **0001–0003**.
- `frontend/e2e/tei.spec.ts` → **9** tests.
- El venv real es `.venv` en la raíz; `backend/venv` no existe.

#### Contradicciones resueltas

- `AGENTS.md` decía 14 migraciones y 50 unitarias → sustituido por punteros.
- `PENDIENTES_ERP.md` afirmaba 8/8 E2E y se autocontradecía → archivado.
- El contrato R-01 decía "mes del viaje" y el código imputa por fecha de emisión → corregido.
- `R-02` decía "ventana 30 / solo advierte" cuando ya es 14 y bloqueante → corregido.
- **El primer `cutover.md` de esta reorganización afirmaba que `0015` rompía el script.** Falso: `0015` describe una versión anterior; el script actual migra `confirmado` **sin recursos** (`cutover_legacy.py:6-13,378-401`) y el `23514` no se dispara. Corregido en `cutover.md`, `estado.md`, `garantias.md`, `catalogo-migraciones.md` y `matriz-trazabilidad.md` (deuda D-05). Lo detectó el agente `datos` y lo confirmó `arquitectura`.
- `RA-10` pasa de "sin verificar" a **confirmado**: `DEBUG: bool = True` en `config.py:11`.
- `RA-13` nuevo: los tests leen `settings.DATABASE_URL` (de `backend/.env`), no la URL de test.

#### Riesgos que quedan

- Los documentos siguen **sin commitear** (ver `docs/estado.md` §6).
- `docs/_archivo/` conserva enlaces internos con rutas antiguas: es histórico, no se corrige.

---

### [2026-10-29] PLAN_MAESTRO_ERP_V2 — reconciliación y arranque del piloto

**Riesgo:** Alto (toca dinero, multiempresa, disponibilidad de flota, migraciones y
cutover). Cualquier ola de escritura sobre estos dominios exige revisión
independiente y autorización explícita.

**Estado:** abierta — Ola 0 en curso (solo lectura).

#### Preflight (verificado en esta sesión)

| Ítem | Resultado |
|---|---|
| Rama | `main` |
| Árbol | 135 entradas en `git status --short`: núcleo v2 en staging (`backend/app/nucleo/**`, `supabase/migrations/0004`–`0014`, tests, páginas frontend) + `Makefile`, `README.md`, `router.py`, `config.py`, `main.py` modificados. **No es un árbol limpio; no revertir.** |
| PostgreSQL `127.0.0.1:54322` | Cerrado (`lsof` sin listener) |
| Backend `:8000` | Cerrado |
| Frontend `:3000` | Cerrado |
| `NUCLEO_TEST_DATABASE_URL` | No verificable (shell bloquea lectura de `.env`; variable no exportada en la sesión) |
| `opencode debug agents` | 🔴 No ejecutable: binario `opencode` no está en `PATH` de esta shell. Descubrimiento por filesystem: 8 agentes en `.opencode/agents/` (`orquestador`, `arquitectura`, `datos`, `backend`, `frontend`, `negocio-finanzas`, `qa`, `auditor-seguridad`) y 10 skills en `.opencode/skills/`. |
| `make unit` | 🟢 50 passed (2026-10-29, esta sesión) |
| Suite completa / E2E | 🔴 Imposible sin base: no se ejecutó, no se declara en verde |

Consecuencia: en esta sesión solo son verificables afirmaciones estáticas
(código, migraciones, tests unitarios). Integración PostgreSQL, HTTP, concurrencia
real y E2E quedan **🔴 no verificadas**.

#### Hechos confirmados (evidencia primaria)

1. El plan (§0.1) declara haber auditado "3 migraciones, 12 routers"; el repo tiene
   hoy 14 migraciones y 26 routers montados (`backend/app/api/router.py:32-56`).
   **El diagnóstico del plan es anterior al núcleo v2.**
2. Varios hallazgos del §2.4 ya están resueltos **en `nucleo`**, no en legacy:
   - `EXCLUDE USING gist` para tracto, rampla y chofer: `0004_nucleo_operacional.sql:746,751,756`.
   - Folio único por empresa: `0013_facturacion.sql:30` (`unique (empresa_id, numero_factura)`).
   - Bloqueo de facturación sin POD: `backend/app/nucleo/servicio_facturacion.py:495-500`.
   - Evaluación de documentos vencidos en disponibilidad: `backend/app/nucleo/servicio_disponibilidad.py:234+`.
   - RLS habilitado en tablas de `nucleo` **sin políticas**: `0004_nucleo_operacional.sql:1866-1881` (coincide con RA-03).
3. El legacy conserva los defectos: `public.facturas` con `unique (numero_sii, cliente_id)` (`0001_esquema_base.sql:142`) y validación de asignación solo por tracto y por estado (`backend/app/api/routes/viajes.py:99-113`).
4. 13 páginas del frontend ya consumen `frontend/src/lib/nucleo.ts` (despacho, agenda, expediente, comercial, cobranza, rentabilidad, tablero, maestros, auditoría, permisos, cutover, PWA conductor) — UI de núcleo existe, sin verificación de ejecución.

#### Supuestos provisionales

- 🟡 El trabajo del núcleo v2 está sin commitear y **nunca se aplicó** contra una base en esta sesión; se desconoce si las migraciones `0004`–`0014` corren limpias.
- 🟡 Las 13 páginas de núcleo funcionan; no se ejecutaron.
- 🟡 `public` sigue siendo la fuente operativa real del día a día.

#### Contradicciones abiertas

- C-1: el plan pide "corregir esta semana" cinco riesgos que en `nucleo` ya tienen
  mecanismo, pero el legacy sigue vivo y sin mecanismo → el riesgo real no es
  "falta construir" sino "coexisten dos verdades y la UI usa las dos".
- C-2: §0.6/§23 proponen 7 fases y 10–12 meses; §26 pide al dueño decidir alcance.
  Sin esa decisión, ejecutar fases es iniciativa no autorizada.
- C-3: RA-01/RA-08 de `AGENTS.md` (piloto "cerrado y probado", "8/8 E2E") no se
  sostienen: base apagada, E2E no ejecutado, spec con 9 escenarios.

#### Decisiones pendientes (usuario / dueño)

1. Alcance: ¿piloto de 90 días (Fase 0 + Fase 1) o las 7 fases?
2. Prioridad de dolor: disponibilidad, cobranza, costos, mantenimiento o nómina.
3. ¿Se autoriza aplicar `0004`–`0014` en la base local para verificar el núcleo v2?
4. Política de comisión: ¿devengado o cobrado? (dinero)
5. Fuente de verdad: ¿`nucleo` canónico y `public` congelado, o convivencia prolongada?
6. Datos reales, sistemas externos (GPS, combustible, banco, contabilidad) y asesoría
   tributaria/laboral: sin esto, Fases 3–4 no se pueden cerrar.

#### Delegaciones

| Agente | Entregable | Estado |
|---|---|---|
| `arquitectura` | Matriz plan↔código + ADR de coexistencia `public`/`nucleo` en `docs/arquitectura/` | en curso |
| `datos` | Matriz de garantías DB existentes vs faltantes (núcleo/legacy) en `docs/datos/` | en curso |
| `qa` | Línea base reproducible y matriz de cobertura | pendiente (bloqueada por base apagada) |
| `negocio-finanzas` | Catálogo de reglas que el plan asume (margen, comisión, estadía, diésel) | pendiente (Ola 1) |

#### Evidencia que falta

- Aplicación limpia de `0004`–`0014` en PostgreSQL local (autorización requerida).
- Rol efectivo de `DATABASE_URL` (sin imprimir la cadena) → RA-03.
- Ejecución de la suite completa y de los 9 escenarios E2E.
- `opencode debug agents` en una shell con el binario disponible.

---

#### Cierre de Ola 0 (2026-10-29) — artefactos y verificación del orquestador

Artefactos producidos (nuevos, untracked, solo documentación):

- `docs/arquitectura/matriz-plan-vs-codigo.md` (164 líneas)
- `docs/arquitectura/adr/ADR-0001-coexistencia-public-nucleo.md` (350 líneas)
- `docs/arquitectura/alcance-piloto.md` (227 líneas)
- `docs/datos/garantias.md` (338 líneas, 83 garantías en 12 dominios)
- `docs/datos/invariantes.md` (716 líneas, 31 invariantes `INV-*`)
- `docs/_archivo/planes/plan-migraciones-0015.md` (676 líneas, `0015`–`0021` en diseño)

**Verificación independiente del orquestador** (re-ejecutada, no aceptada por
autoridad). Todas las afirmaciones críticas de ambos subagentes se confirmaron:

| Afirmación del subagente | Verificación propia | Resultado |
|---|---|---|
| Los 3 `EXCLUDE` están en `nucleo.reservas_recurso`, no en `nucleo.viajes` | `sed -n '744,757p' 0004_nucleo_operacional.sql` | 🟢 confirmado |
| `confirmado` puede llevar recursos y **no** genera reserva | `0004:671-674` (`ck_viaje_recursos_por_estado`) + `0004:1632-1635` (`fn_viaje_reservas`) | 🟢 confirmado |
| `cutover_legacy.py` inserta `estado='confirmado'` con tracto/rampla/chofer | `scripts/cutover_legacy.py:361-371` | 🟢 confirmado → **INV-D04 real** |
| `registrar_pago` lee saldo y luego inserta, sin `FOR UPDATE` ni idempotencia | `backend/app/nucleo/servicio_facturacion.py:620-651` | 🟢 confirmado → **INV-F01 real** |
| `nucleo` tiene RLS sin políticas | `grep -c "create policy"` en `supabase/migrations/` → 1, y es en `public.usuarios` (`0001:284`) | 🟢 confirmado |
| `23514` → 409 y `23502` → 500 | `errores.py:165-168` + `class ReglaNegocioViolada` (`errores.py:106-108`); `23502` sin rama | 🟢 confirmado (desvía de `AGENTS.md` §8) |
| Legacy borra facturas físicamente | `backend/app/api/routes/facturas.py:241-263` | 🟢 confirmado |
| Comisión sobre viaje finalizado/facturado, no cobrado | `backend/app/api/routes/liquidaciones.py:45-59` | 🟢 confirmado |

**Contradicciones nuevas detectadas al consolidar** (no resueltas, requieren decisión):

- C-4: `AGENTS.md` §8 exige `23514`/`23502` → 422; el código devuelve 409 y 500. Es
  una desviación de contrato documentado, no un bug inventado por el subagente.
- C-5: el ADR-0001 concluye que **ninguna garantía del núcleo es exigible** mientras
  `nucleo.cutover_control.legacy_escritura_congelada = false` (`0014:10`), porque
  `public` sigue escribiendo. Eso reordena las olas: el blindaje del legacy deja de
  ser "deuda" y pasa a ser precondición del piloto.
- C-6: `docs/datos/invariantes.md` propone 31 invariantes nuevos; el plan maestro
  no los conoce. Adoptarlos exige ADR y aprobación, no iniciativa de implementación.
- C-7: el trabajo de núcleo v2 sigue **sin commitear y sin aplicar a ninguna base**;
  toda la matriz de `nucleo` es 🟢 estático, 🔴 en ejecución.

**Estado de la tarea:** Ola 0 cerrada. Ola 1 (decisiones) bloqueada por el dueño:
alcance del piloto (D-01), política de comisión (D-02), documentos obligatorios por
recurso (D-06), mantenimiento por km en núcleo o legacy (D-07), dueño y granularidad
del interruptor de cutover (D-05).

---

#### Ola 0-bis — Verificación en ejecución (2026-10-29, base local arriba)

Autorización del usuario: levantar Supabase local e instalar `opencode` en el PATH.
`opencode` se enlazó desde la app de escritorio (`v2.2.0`) a `/opt/homebrew/bin`;
`opencode debug agents` ya corre y descubre los 8 agentes.

**Estado del entorno:** PostgreSQL `:54322` arriba; 31 tablas en `nucleo`, 17 en
`public`; backend `:8000` y frontend `:3000` arriba; migraciones `0001`–`0014`
aplicadas.

| Prueba | Comando | Resultado |
|---|---|---|
| Unitarias | `make unit` | 🟢 50 passed |
| Suite completa | `pytest tests` con `NUCLEO_TEST_DATABASE_URL` | 🟢 **76 passed, 7 skipped** (el snapshot decía 13 failed, 63 passed) |
| Suite completa con credenciales de admin y contador | `TEST_ADMIN_*` + `TEST_CONTABILIDAD_*` | 🟡 **82 passed, 1 failed** |
| E2E | `make e2e` | 🟢 **9 passed** (RA-08: el spec tiene 9, no 8) |

**Pruebas adversariales ejecutadas con dos conexiones reales:**

1. 🟢 `EXCLUDE` del núcleo funciona: dos sesiones simultáneas sobre la misma rampla
   en ventanas solapadas → `ERROR: conflicting key value violates exclusion constraint
   "ex_reserva_rampla"` (SQLSTATE 23P01).
2. 🟢 El legacy **no** protege: dos viajes con el mismo tracto, rampla y chofer, el
   mismo día, se insertaron sin error en `public.viajes` (solo tiene PK y FKs).
3. 🟢 **INV-D04 reproducido en ejecución:** viaje insertado en estado `confirmado`
   **con** tracto, rampla y chofer → **0 filas** en `nucleo.reservas_recurso`.
   Es exactamente lo que hace `scripts/cutover_legacy.py:361-371`.
4. 🟢 El mismo viaje en estado `asignado` y sin documentos → rechazado:
   `Documento revision_tecnica faltante para tracto ...` (`validar_documentos_recurso`).
5. 🟢 **Nuevo:** el viaje `confirmado` **sí** se insertó sin documentos. `confirmado`
   esquiva a la vez la reserva de disponibilidad y la validación documental.
6. 🟢 `delete from nucleo.viajes` → bloqueado por `fn_viaje_proteccion`
   ("use anulación auditada"); `confirmado → anulado` exige `motivo_anulacion`.
7. 🟢 RLS no es la frontera: `set role authenticated` → `permission denied for schema
   nucleo` (sin `USAGE`); el rol `postgres` tiene `rolbypassrls = true`. El aislamiento
   por empresa descansa solo en el backend (RA-03 confirmado en ejecución).

**Hallazgos nuevos de esta ola:**

- **H-1 (grave, estado dejado por una sesión previa):** la base estaba con
  `nucleo.cutover_control.legacy_escritura_congelada = true`. Con eso, **toda escritura
  del sistema viejo devuelve 409** (`select legacy_escritura_congelada` en cada request
  legacy). El E2E "cutover: estado congelado y runbook" pasa **porque** espera ver
  "Congelada": el test no prueba un comportamiento, fotografía un estado global.
  Restaurado a `false` por el orquestador; con eso los 5 tests legacy pasaron.
- **H-2 (test no determinista):** `test_liquidacion_calculo` espera comisión de
  septiembre 2026, pero `PATCH /viajes/{id}/estado` estampa `fecha_fin = date.today()`
  (`backend/app/api/routes/viajes.py:246`). Falla cualquier día fuera de 2026-09.
- **H-3 (regla de negocio real detrás de H-2):** el mes al que se imputa un viaje
  depende de **cuándo alguien aprieta "finalizar"**, no de cuándo ocurrió el viaje.
  Afecta comisión, margen mensual y cierre. Requiere decisión (¿se permite registrar
  la fecha real de término?).
- **H-4:** `nucleo.viajes` no se puede borrar nunca (ni anulado), por diseño. Queda un
  viaje de prueba `QA-CONF-1` **anulado** en la base local; no se puede eliminar sin
  desactivar el trigger, y no se desactiva un control para limpiar.

**Correcciones al informe anterior:**

- 🔴 → 🟢 "las migraciones aplican limpias": confirmado en base nueva.
- 🟡 → 🟢 "el núcleo impide doble asignación": confirmado con dos conexiones.
- 🔴 → 🟢 "suite completa": 76/7 con base; 82/1 con credenciales.
- 🔴 → 🟢 "E2E": 9/9.
- 🔴 sigue: rol efectivo de `DATABASE_URL` **en producción** (aquí es `postgres` con
  `bypassrls`).

---

#### Cierre de Ola 2 (2026-10-29) — reglas aprobadas aplicadas y verificadas

Autorización del dueño en esta sesión: levantar Supabase local, aplicar migraciones
`0015`–`0017` en la base local, escribir en `scripts/seed_local.py` y `Makefile`.
Nada de esto se commiteó ni se aplicó fuera de `127.0.0.1:54322`.

**Reglas aprobadas por el dueño (2026-10-29)**

| ID | Regla | Decisión del dueño |
|---|---|---|
| R-01 | Comisión del chofer | 10 % de la **facturación del mes**, configurable por chofer. Base = viajes `facturado`. |
| R-02 | Licencia de conducir | Única clase válida **A5**. Clase distinta/ausente → bloqueo. Vencida → bloqueo. Por vencer en 14–1 días → advertencia. Ventana por defecto 14 días. |
| R-03 | Imputación mensual del viaje | **Abierta.** `viajes.py:246` estampa `fecha_fin = date.today()` al finalizar. |

**Migraciones aplicadas (🟢 salida real, `psql -v ON_ERROR_STOP=1`)**

| Migración | Objetos | Evidencia de aplicación |
|---|---|---|
| `0015_viaje_con_recursos_ocupa_y_valida.sql` | `fn_viaje_reservas` reescrita (condición = "tiene los 3 recursos", no lista de estados), `fn_viaje_documentos`, `trg_viajes_05_documentos` | `NOTICE: 0015: viajes con 3 recursos=69, por adoptar=1, reservas insertadas=3, reservas activas de viaje: 210 -> 213` |
| `0016_licencia_a5_bloqueante.sql` | `fn_viaje_licencia_a5`, `trg_viajes_03_licencia_a5`, `dias_alerta_documentos` default 14, `COMMENT` de deprecación sobre `licencias_permitidas` | `EXIT=0`; `column_default = 14` |
| `0017_default_comision_chofer.sql` | `nucleo.choferes.porcentaje_comision` default 0.10 (sin backfill) | `column_default = 0.10` |

Orden de triggers verificado en `nucleo.viajes`: `trg_viajes_03_licencia_a5` corre
antes que `trg_viajes_05_documentos` (orden por prefijo numérico, no por creación).

**Precondiciones medidas antes de aplicar (🟢)**

| Consulta | Resultado | Lectura |
|---|---|---|
| P1.1 viajes con 3 recursos sin 3 reservas | 1 | el agujero era real y había 1 caso vivo |
| P1.2 solapes sobre el mismo recurso | **0** | seguro aplicar; si hubiera >0 se detenía |
| P1.3 reservas con ventana desviada | **0** | libro de ocupación consistente |
| P2.1 viajes vigentes con chofer no-A5 | **54** | deriva previa; no se corrigió |
| P2.2 choferes activos que no podrán asignarse | **43** | **bloqueo operativo real** (ver R-04) |
| P2.3 tractos con `licencias_permitidas` que contradicen R-02 | 0 | no hay que migrar el array |

**Pruebas de base ejecutadas (🟢 salida real)**

| Prueba | Resultado |
|---|---|
| `0015_01_confirmado_ocupa.sql` | OK: `confirmado` + 3 recursos ⇒ 3 reservas activas, misma ventana; anulado ⇒ 0 activas y 3 desactivadas sin borrar; recursos parciales **no** ocupan (frontera declarada) |
| `0015_02_concurrencia_rampla.py` (**dos conexiones**) | OK: B queda bloqueada por A; al commitear A, B recibe `23P01` / `ex_reserva_rampla`; 1 sola reserva activa, el perdedor no deja filas |
| `0015_03_confirmado_valida_documentos.sql` | OK: rechazo `23514` "Documento licencia_conducir faltante"; parciales no disparan validación |
| `0016_01_licencia_clase_no_a5.sql` | OK: A3 y clase ausente rechazadas `23514`; también por `UPDATE` de asignación |
| `0016_02_licencia_por_vencer_no_bloquea.sql` | OK: vence en 10 días ⇒ **no** bloquea (advertencia) |
| `0016_03_licencia_vencida_bloquea.sql` | OK: vencida ⇒ bloqueo |
| `99_limpieza_viajes_prueba.sql` | OK: limpieza de la empresa `TST15` bajo guardas (GUC + código de empresa + ausencia de documentos financieros) |

**Suite y E2E (🟢 re-ejecutados por el orquestador, no aceptados por autoridad)**

- `make unit` → **52 passed, 1 warning in 0.04s**.
- `make test` (suite completa, con credenciales del seed) → **97 passed, 2 warnings in 3.09s**
  (antes de R-01/R-02: 82 passed / 1 failed).
- `make e2e` → **9 passed (12.2 s)**. El test de cutover se reescribió para verificar
  que la pantalla muestre un estado **válido** (`Congelada|Abierta`), no un estado
  global concreto: antes pasaba solo con la base congelada (H-1).

**Higiene de evidencia (corregida en esta ola):** `make db-up` imprimía en stdout el
bloque JSON de `supabase start`, que incluye las claves locales (`SECRET_KEY`,
`ANON_KEY`, `SERVICE_ROLE_KEY`, `JWT_SECRET`). Son claves de demo de Supabase local,
pero quedaban escritas en cualquier log de `make test`. Ahora la salida se redirige a
`$TMPDIR/tei-supabase-start.log` y solo se imprime "Supabase local arriba"; si
`supabase start` falla, se muestra el log completo. Además se quitó el `-q` duplicado
(`addopts = -q` en `backend/pytest.ini` + `-q` en el recipe) que suprimía la línea
"NN passed" y dejaba la evidencia sin conteo.

**Correcciones aplicadas al código (🟢, diff revisado)**

| Archivo | Cambio | Motivo |
|---|---|---|
| `backend/app/api/routes/liquidaciones.py:45-61` | comisión cuenta solo `EstadoViaje.facturado` | R-01 |
| `backend/app/models/__init__.py:102-105` | `porcentaje_produccion` default 0.10 | R-01 |
| `backend/app/schemas/catalogos.py:32-35` | default 0.10 | R-01 |
| `backend/app/nucleo/models.py:221` | `dias_alerta_documentos` default 14 | R-02 |
| `backend/app/nucleo/models.py:583-586` | `porcentaje_comision` default 0.10 | R-01 |
| `backend/app/nucleo/politicas.py:297-322` | clase ≠ A5 y clase ausente pasan a **bloqueante** (`Hallazgo(..., True, ...)`); deja de depender de `tracto.licencias_permitidas` | R-02 |
| `scripts/seed_local.py` | comisión 0.10 con `on conflict do update`; ventana 14 días | R-01/R-02 |
| `Makefile` | `test` exporta credenciales del seed (sobrescribibles por entorno); `db-up` deja de imprimir claves; se quita `-q` duplicado | evidencia reproducible sin filtrar claves |
| `frontend/e2e/tei.spec.ts:90` | aserción de cutover independiente del estado global | H-1 |
| `backend/tests/test_reglas_negocio.py` (nuevo, 31 KB) | pruebas R-01 / R-02 con casos positivos y negativos | TDD selectivo |
| 6 fixtures `test_nucleo_*.py` | choferes con `licencia_clase="A5"` y documento vigente | la regla muerde; se corrigió el dato, no la aserción |

**Hallazgos nuevos de esta ola**

- **R-04 (bloqueo operativo, requiere decisión del dueño):** con R-02 activa,
  **43 de 54** choferes activos no pueden asignarse porque no tienen `licencia_clase='A5'`
  cargada (P2.2). No es un defecto del código: es un vacío de datos. Opciones: cargar
  la clase real desde las licencias físicas, o desactivar la regla hasta tener el dato
  (lo segundo no se recomienda y no se hará sin autorización).
- **R-05 (dinero silencioso):** **58 choferes** tienen `porcentaje_comision = 0`
  (P17.1). El default nuevo es 0.10, pero las filas existentes conservan 0 a propósito:
  un 0 puede ser intencional. Requiere revisión caso a caso por negocio.
- **R-03 sigue abierta:** la fecha de término del viaje se estampa al finalizar, así
  que comisión y margen mensual dependen de cuándo se aprieta el botón, no de cuándo
  ocurrió el viaje. Afecta R-01 directamente.
- **H-5 (deuda de diseño):** `tractos.licencias_permitidas` quedó deprecado por
  `COMMENT` pero sigue existiendo y editable en maestros; `frontend` debe dejar de
  ofrecerlo y `backend` ya no lo consulta. No se borra el campo en esta ola.
- **H-6 (higiene de datos de prueba):** `nucleo.viajes` no admite `DELETE` (trigger
  `fn_viaje_proteccion`), así que **cada corrida de la suite deja viajes que no se
  pueden borrar**. La base local pasó de 103 a **285 viajes** tras las corridas de
  esta sesión. Consecuencias: (a) los conteos de precondición (`P1.1`) ya no son
  estables, (b) la base local solo vuelve a una línea base limpia con
  `supabase db reset` + `make seed`, que es destructivo y requiere autorización.
  Medido ahora: 285 viajes, 651 reservas activas, **0 solapes** (P1.2 sigue en 0).

**Estado de la tarea:** Ola 2 cerrada en lo autorizado. Ola 3 (retiro del legacy) no
se ejecuta: depende de ADR-0002 y de las 4 puertas, y de decisión del dueño sobre el
orden de módulos.

---

#### Cierre de Ola 2-bis (2026-10-29) — destino modular y estado real del retiro

El tercer entregable de `arquitectura` no se había producido en la ola anterior
(el subagente devolvió respuesta vacía). Se re-encargó acotado y quedó escrito:

- `docs/arquitectura/destino-modular.md` (449 líneas): 12 módulos con frontera
  explícita, contrato entre módulos, tabla `dominio → tabla canónica → quién escribe`,
  orquestación por transacción de caso de uso, escalabilidad con criterio de
  diferimiento explícito (nada de microservicios/Kafka/event sourcing como destino) y
  11 deudas estructurales con condición de pago.

**Verificación propia de 3 afirmaciones críticas del documento (🟢):**

| Afirmación | Verificación | Resultado |
|---|---|---|
| Facturación escribe `nucleo.viajes` directamente (viola la frontera que el doc propone) | `servicio_facturacion.py:586-594` → `update(Viaje).values(estado=EstadoViaje.facturado)` | 🟢 confirmado |
| No existe transacción de caso de uso: cada servicio hace su `commit()` | `core/database.py:27-29` (`get_session` sin commit/rollback de unidad de trabajo) | 🟢 confirmado |
| `ContextoEmpresa` toma la empresa de `X-Empresa-ID` + membresía, nunca del body | `nucleo/deps.py:44,55-66` | 🟢 confirmado |

**Artefactos de arquitectura disponibles al cierre de la ola**

| Archivo | Líneas | Qué responde |
|---|---|---|
| `docs/arquitectura/matriz-plan-vs-codigo.md` | 164 | qué del plan maestro ya existe y qué no |
| `docs/arquitectura/alcance-piloto.md` | 227 | qué entra en el piloto y qué no |
| `docs/arquitectura/retiro-legacy.md` | 403 | por módulo legacy: uso, equivalente en núcleo, datos a migrar, puerta que falta |
| `docs/arquitectura/destino-modular.md` | 449 | fronteras, contratos, orquestación, escalabilidad |
| `docs/arquitectura/adr/ADR-0001-coexistencia-public-nucleo.md` | 350 | por qué coexisten y con qué reglas |
| `docs/arquitectura/adr/ADR-0002-retiro-del-legacy.md` | 521 | las 4 puertas de borrado y el orden de retiro |

**Lo que NO se hizo y por qué**

- No se borró ningún archivo legacy: ninguna de las 4 puertas de ADR-0002 está
  cerrada todavía, y borrar es irreversible.
- No se migró ningún módulo de `public` a `nucleo`: el orden de retiro depende de
  P-1 (¿liquidaciones, mantenimiento, IVA y export se migran o se retiran?).
- No se tocó `tractos.licencias_permitidas` en la base: quedó deprecado por
  `COMMENT`, sin `DROP COLUMN` (borrar una columna es destructivo y no estaba
  autorizado).

---

#### Ola 2-ter (2026-10-29) — revisión independiente de seguridad

Riesgo Alto exige que quien implementa no valide su propio trabajo. Se encargó a
`auditor-seguridad` una revisión del diff de la Ola 2, **sin entregarle la conclusión
del implementador**. Informe: `docs/seguridad/hallazgos.md` (594 líneas, 15
hallazgos: 2 altas, 8 medias, 3 bajas, 2 informativas).

El auditor no tuvo shell, así que su informe es estático. El orquestador verificó
personalmente los tres hallazgos graves **en ejecución**:

| Hallazgo | Verificación propia | Resultado |
|---|---|---|
| **SEC-001** la comisión se pierde si la facturación cae en un mes ya cerrado | `liquidaciones.py:49-56` atribuye por `coalesce(fecha_fin, fecha_inicio)` y exige `estado='facturado'`; `liquidaciones.py:291-295` devuelve 409 al recalcular una emitida; `viajes.py:245-246` estampa `fecha_fin` al finalizar | 🟢 confirmado. Viaje finalizado en octubre y facturado en noviembre: octubre ya emitido (409), noviembre no lo ve (`fecha_fin` en octubre) → **comisión no pagada, sin error** |
| **SEC-002** el PDF de una liquidación emitida se recalcula en vivo | `liquidaciones.py:467-500` recomputa `_comision_chofer` + bonos + descuentos; `:431` imprime `liquidacion.total_liquido` almacenado | 🟢 confirmado. Las líneas del PDF pueden no sumar su propio total |
| **SEC-009** `cutover_legacy.py` queda inoperante tras 0015 | Prueba en transacción con `ROLLBACK`: empresa + tracto + rampla + chofer A5 con **exactamente** los documentos que crea el cutover (`licencia_conducir`, `revision_tecnica`, `seguro_obligatorio`) → `INSERT` de viaje `confirmado` con 3 recursos rechazado con `23514 Documento permiso_circulacion faltante` | 🟢 confirmado en ejecución |

**Por qué SEC-009 no se "arregla" inventando documentos.** `public.tractos` solo tiene
`vencimiento_revision_tecnica` y `vencimiento_seguro`; `public.ramplas` solo
`vencimiento_revision_tecnica`; `public.choferes` solo `vencimiento_licencia`. Los
documentos que exige `validar_documentos_recurso` (`permiso_circulacion`, `soap`,
`seguro_carga`, `examen_medico`) **no existen en el legacy**. Fabricarlos con fechas
inventadas sería falsear cumplimiento documental. Las únicas salidas honestas son:
(a) migrar los viajes sin recursos y asignarlos después con documentos reales, o
(b) que el dueño decida otro criterio. Requiere decisión, no iniciativa.

**Hallazgo corregido en esta ola (🟢 verificado con HTTP real)**

- **SEC-008 [media, autorización/PII]:** `GET /liquidaciones/resumen`, `/anticipos`,
  `/ajustes` y `/liquidaciones/{id}/pdf` usaban `Depends(get_current_user)`: **cualquier
  usuario autenticado** (incluido `conductor`) leía sueldo, comisión y RUT de todos los
  choferes. Corregido en `liquidaciones.py:11,27-30` a
  `require_roles(admin, contabilidad)`.
  Evidencia: `conductor → 403`, `admin → 200` contra el backend en `:8000`.
  El único consumidor en frontend es `frontend/src/app/(app)/liquidaciones/page.tsx`,
  cuya entrada en `navigation.ts:78` ya estaba restringida a `["admin","contabilidad"]`.

**Hallazgos que quedan abiertos (no se tocaron)**

| ID | Sev. | Qué | Quién decide |
|---|---|---|---|
| SEC-001 | alta | mes de imputación de la comisión | `negocio-finanzas` + contador |
| SEC-002 | alta | snapshot inmutable de la liquidación emitida | `backend`/`datos` tras SEC-001 |
| SEC-003 | media | `nucleo.choferes.porcentaje_comision` (12 % de ejemplo) vs `public.choferes.porcentaje_produccion` (10 %): dos porcentajes para el mismo dinero | `arquitectura` (ADR) |
| SEC-004 | media | importador CSV de choferes deja `porcentaje_produccion=0` si falta la columna | `backend` + migración sobre `public` (no autorizada) |
| SEC-005 | media | degradar `licencia_clase` de un chofer ya asignado no revalida sus viajes | `datos` |
| SEC-006 | media | transición `borrador → confirmado` no revalida documentos | `datos` |
| SEC-007 | media | doble `POST /anticipos` duplica el descuento (sin idempotencia) | `backend`/`datos` |
| SEC-009 | media | cutover inoperante tras 0015 | dueño (ver arriba) |
| SEC-010 | media | `test_reglas_negocio.py` cae a `DATABASE_URL` si falta `NUCLEO_TEST_DATABASE_URL` | `qa` |
| SEC-012 | baja | P1.2 de 0015 no compara contra mantención/descanso | `datos` |
| SEC-013 | baja | dos `POST /liquidaciones/calcular` concurrentes → 500 | `backend` |
| SEC-011/014/015 | baja/inf. | E2E que pasa con solo el heading; credenciales de seed en el repo; tests SQL no están en `make test` | `qa` |

**Estado tras la revisión:** suite **97 passed**, `make unit` **52 passed**, E2E
**9 passed**, tras el cambio de SEC-008. Ruff sobre `liquidaciones.py`: 19 avisos, todos
preexistentes (B008 por `Depends` en defaults, FURB157, un F401); ninguno introducido
por este cambio.

---

#### Ola 3 (2026-10-29) — decisiones del dueño ejecutadas

El dueño respondió las tres preguntas abiertas y autorizó avanzar:

1. **Carga el dato** (licencia A5).
2. **Comisión = producción total del mes, opción (a)**: atribuir por fecha de
   emisión de la factura.
3. **Migrar los viajes sin asignación de recursos** y resolver la asignación después.

##### Corrección importante de una cifra que reporté mal

En la Ola 2 informé "43 de 54 choferes activos no pueden asignarse por falta de
A5". **Esa cifra estaba contaminada por datos de prueba**: al desglosar por
empresa, la empresa operativa `TEI` tiene **4** choferes activos, no 54. De ellos:

| RUT | Nombre | Clase | Comisión | Documento de licencia |
|---|---|---|---|---|
| 11.111.111-1 | Juan Pérez | A5 | 10 % | vigente |
| 22.222.222-2 | Luis Soto | A5 | 10 % | vigente |
| 33.333.333-3 | Pedro Rojas | A5 | 10 % | vigente |
| 78000222-2 | Chofer QA | — | 5 % | **no tiene** |

Los otros ~53 choferes "activos" pertenecen a empresas de fixtures (`TST15`,
`POD-*`, `ALT-*`, `AUD-*`) creadas por la suite. **El vacío real de A5 en la
empresa operativa es cero.** Lo que queda es un artefacto de pruebas ("Chofer QA")
dentro de la empresa real, sin documento de licencia; no se le asigna A5 porque
sería inventar un registro de cumplimiento.

Lección registrada: toda cifra de negocio debe medirse **por empresa**, no sobre
el total de la base, porque la suite escribe en `nucleo` y esos datos sobreviven.

##### Migraciones de carga

`0018_carga_licencia_clase_a5.sql` — carga A5 en choferes activos de `TEI` con
clase vacía **y** documento `licencia_conducir` vigente. Resultado real:
`choferes TEI actualizados a A5=0, omitidos sin documento=1`. Incorpora la
procedencia del dato en el `COMMENT` de la columna: *declarado por el dueño, no
contrastado con la licencia física*.

`0019_comision_piloto_10.sql` — alinea a 10 % la comisión de los choferes de
`TEI` que estaban en 0. Resultado real: `alineada a 10% = 0` (ya estaban en 10 %).
No toca `public.choferes`: SEC-003 sigue abierto.

Ambas son idempotentes y dejan los RUT afectados en el `NOTICE` para poder
revertirlas por lista explícita.

##### SEC-001 corregido: comisión por fecha de emisión de la factura

`_comision_chofer` (`backend/app/api/routes/liquidaciones.py:48-101`) ahora:

1. Toma los viajes del chofer.
2. Busca en `factura_viaje` → `facturas` la **primera** `fecha_emision` de factura
   **no anulada** de cada viaje.
3. Si hay factura: atribuye por esa fecha, sin importar `fecha_fin`.
4. Si el viaje está `facturado` **sin** factura (dato inconsistente): fallback a
   `coalesce(fecha_fin, fecha_inicio)` para no perder la comisión en silencio.
5. Un viaje `finalizado` sin factura no devenga.

Se implementó en dos consultas explícitas en vez de una subconsulta
correlacionada: la primera versión con `exists()` **no correlacionaba** y contaba
todos los viajes (270.000 en vez de 90.000). El error lo detectó la propia prueba.

Pruebas (todas en `backend/tests/test_reglas_negocio.py`):

| Prueba | Qué fija |
|---|---|
| `test_r01_comision_no_incluye_facturacion_de_otro_mes` (reescrita) | dos facturas, dos meses: 90.000 y 180.000 respectivamente |
| `test_r01_comision_se_atribuye_al_mes_de_emision_de_la_factura` (nueva) | viaje finalizado el mes anterior, facturado hoy: devenga hoy y **no** el mes anterior (caso SEC-001) |
| `test_r01_factura_anulada_no_genera_comision` (nueva) | factura anulada ⇒ 0, líquido = sueldo base |
| `test_r01_viaje_facturado_sin_factura_usa_fecha_del_viaje` (nueva) | fallback declarado para dato inconsistente |

##### SEC-009 corregido: cutover sin asignación de recursos

`scripts/cutover_legacy.py` inserta los viajes con `tracto_id = rampla_id =
chofer_id = NULL`, estado `confirmado`, y registra en `observaciones` los UUID
legacy de los tres recursos más el motivo. Nuevo contador
`viajes_sin_asignacion`. El cliente sigue siendo obligatorio.

Verificación en ejecución (transacción con `ROLLBACK`):
`OK: viaje confirmado SIN recursos aceptado` y `reservas creadas = 0`
(no asigna, no ocupa, no exige expediente).

**Hallazgo nuevo SEC-016 (cutover, media):** al re-ejecutar el cutover con un
viaje adicional, `fn_oc_recalcular` aborta con
`La OC ... no tiene saldo suficiente: consumido 570000.00, autorizado 320000.00`.
El control de OC funciona correctamente; el defecto es del cutover, que reutiliza
una OC existente sin ampliarla ni crear una nueva. En una primera migración sobre
`nucleo` vacío no se dispara (la OC se crea con 1,2× el total), pero rompe la
re-ejecutabilidad que exige ADR-0002 §P2. Opciones: (a) ampliar la OC
automáticamente —sube una autorización financiera sin humano—; (b) crear una OC
nueva por lote (`MIG-<cliente>-<fecha>`), que es la recomendada. **No se
implementó**: cambiar autorizaciones financieras no es decisión técnica.

##### Estado de verificación al cierre de la Ola 3

| Prueba | Resultado |
|---|---|
| `make unit` | verde |
| `make test` | **100 passed, 0 failed, 0 skipped** |
| SQL 0015/0016 (5 scripts) | OK |
| `0015_02_concurrencia_rampla.py` | OK (dos conexiones, `23P01`) |
| `cutover_legacy.py --dry-run` | OK, idempotente |
| `make e2e` | **9 passed (12.8 s)**, re-ejecutado tras reiniciar backend y frontend |

---

### [2026-10-29] Diseño ADR-0003 — agente multimodal WhatsApp (texto/voz/foto/PDF)

Riesgo: Medio (solo documento de diseño; la implementación futura será Alto por
tocar dinero vía escrituras de agente) | Estado: cerrada la fase de diseño,
abierta la decisión de activación.

Hechos confirmados:
- El requerimiento del dueño ya estaba anticipado en DEC-05/DEC-10/DEC-11 y §2.5
  de `docs/PLAN_DESARROLLO.md:43,48,49,117-124`; el runtime quedó fuera de F2.
- D03 (OCR), B06 (IA) e I01 (WhatsApp) siguen 🔴 sin implementación en código
  (`docs/arquitectura/capacidades-objetivo.md:92,103,109`; re-scan propio de
  `backend/` sin coincidencias reales).

Supuestos provisionales:
- Modalidad del mensaje declarada por el MIME del webhook (🟡: confirmar con la
  doc del BSP que elija AB-04); fiabilidad de `message_id` para idempotencia
  (🟡 ídem).

Contradicciones: ninguna detectada contra ADR-0001/ADR-0002 ni contra el plan.

Decisiones pendientes (y de quién):
- **AB-04** (dueño + legal): proveedor LLM y WhatsApp Business API, privacidad,
  residencia de datos, contrato de no-entrenamiento. Extensión propuesta P-07/P-08.
- **D-13…D-16** (dueño, a abrir en `docs/negocio/preguntas.md` por
  `negocio-finanzas`): mapa rol→intención, fases por modalidad, aprobación por
  WhatsApp vs buzón, límite de costo/volumen por empresa.
- Colisión de IDs `D-NN` reportada entre `deuda.md` y la serie del dueño — la
  resolveré al momento de numerar las preguntas.

Delegaciones: `arquitectura` → `docs/arquitectura/adr/ADR-0003-agente-multimodal-whatsapp.md` → entregado y verificado por el orquestador (cabecera, frontera DEC-10/DEC-11, pipeline por modalidad, citas archivo:línea re-checkeadas; único archivo nuevo en `git status`).
Evidencia que falta: precios reales de mensajería/ASR/visión, calidad de ASR en
español chileno y de OCR sobre POD/boletas reales → evaluación con corpus propio
antes de pasar el ADR de Propuesto a Aceptado.
Resultado final y enlaces a artefactos: ADR-0003 (Propuesto). Siguiente paso si
el dueño activa: negocio-finanzas abre D-13…D-16 y P-07/P-08; luego
`datos`+`backend` diseñan contactos/OTP/solicitudes del Núcleo (F2.5).

---

### [2026-10-29] Especificación rol→capacidad del agente WhatsApp (respuesta del dueño)

Riesgo: Medio (documentación de especificación; flujos referenciados son Alto) |
Estado: cerrada la especificación; abiertas D-09…D-16 y P-07/P-08.

Hechos confirmados:
- **D-08 respondida por el dueño (2026-10-29)**: se enrolan clientes finales,
  conductores y administración. Especificación completa transcrita fielmente en
  `docs/negocio/agente-whatsapp-roles.md` §1 (matriz AG/CL/CO/AD en §3).
- La numeración real de `docs/negocio/preguntas.md` era D-01…D-07 / P-01…P-06; el
  subagente usó D-08+ y P-07+ correctamente y anotó el mapeo vs lo sugerido por
  ADR-0003 (D-13…D-16). Verificado por orquestador con grep de filas.

Tensiones registradas (decisiones del dueño, NO resueltas):
- **D-09**: "gerente digital" del admin (preguntar lo que sea) vs DEC-10 (no SQL
  libre). Opciones (a) capa semántica / (b) SQL read-only con guardarraíles.
  Vulnerable mientras exista el gap de RLS (0 políticas, BYPASSRLS) — condición
  previa documentada en `docs/qa/informes/f0-wp1-wp2-arquitectura.md:100`.
- **D-10**: carga automática de hoja de ruta del conductor (toca nómina) = desviación
  declarada de DEC-11; requiere decisión (revisión posterior con corrección
  compensada vs aprobación previa). No existe el objeto hoja de ruta (0 resultados
  en `backend/`).
- **D-11** visibilidad de flota al cliente; **D-12** política OTP/cambio de número;
  **D-16** ID de flete por cliente (SQM-001), candidata a regla R-0XX.
- **P-07/P-08**: privacidad de audios/fotos/transcripciones que alimentan sueldos;
  envío de deuda/documentos a clientes por WhatsApp (consentimiento).

Delegaciones: `negocio-finanzas` → matriz `agente-whatsapp-roles.md` + cierre
D-08 + apertura D-09…D-16/P-07/P-08 → entregado, verificado (transcripción fiel
contrastada por orquestador; numeración única).
Evidencia que falta: ninguna implementación; todo flujo es diseño hasta AB-04 y
respuestas D-09…D-16.
Resultado final y enlaces a artefactos:
- `docs/negocio/agente-whatsapp-roles.md` (nuevo)
- `docs/negocio/preguntas.md` (D-08 Respondida; D-09…D-16, P-07, P-08 abiertas)
- Insumo directo de F2.5/F2.6 y del handoff a `datos`/`backend` cuando se autoricen.

---

### [2026-10-30] Respuestas del dueño a D-09…D-16 — actualización ADR-0003 y matriz de roles

Riesgo: Medio (solo documentación de decisión/diseño; implementación futura = Alto) |
Estado: closed el ciclo de decisiones; abiertas subpreguntas D-12/D-14, D-17 y AB-04.

Hechos confirmados:
- **D-09 Respondida**: gerente digital solo admin/dueño; ACL por número administrada
  por el dueño desde la plataforma (activar/desactivar acceso por módulo/variables);
  cliente y conductor predefinidos por su módulo, solo data vinculada a su registro
  (RUT/nombre/teléfono/cliente); respuestas naturales al límite (no preescritas);
  auditoría de cada consulta = nueva **D-17**.
- **D-10 Respondida**: SIN carga automática. Solicitud con Confirmar/Rechazar/
  Modificar (plantilla editable). Rechazar = log + estado intacto. Se construye el
  objeto hoja de ruta. "Secretario" citado como ejemplo de aprobador → evidencia AB-02
  (anotada por el orquestador en `PLAN_DESARROLLO.md`, AB-02 sigue abierta).
- **D-11 Respondida**: no exponer flota al cliente; captura por demanda (cuántos,
  rampla, carga) → solicitud.
- **D-13 Respondida**: todo en el MVP, mejores modelos sin importar costo ahora;
  optimización post-presentación.
- **D-15 Respondida**: sin gate de costo en fase MVP.
- **D-16 Respondida**: ID de flete por cliente regla formal, secuencial, 5 dígitos
  (SQM-00001). Borrador R-04 en `agente-whatsapp-roles.md` §5 (por numerar en
  `catalogo-reglas.md` — colisión de espacio R- con riesgos RA anotada).
- ASR/OCR: a resolver permanentemente → protocolo de evaluación §15 de ADR-0003.
- Parciales: **D-12** (OTP/cambio/revocación abierta), **D-14** (notificación de
  aprobación abierta).

Supuestos provisionales:
- Las 200k tokens/15 min del contexto son parámetros del dueño, revisables (ADR §3.5).
- Mecanismo técnico del gerente digital (a) capa semántica vs (b) SQL read-only
  guardado: lo decide `arquitectura` en ADR-0003 §13 con esos requerimientos.

Contradicciones: el subagente de arquitectura leyó `preguntas.md` antes del write de
negocio-finanzas; re-verificado por el orquestador al cierre: estados finales
consistentes (D-08…D-11,13,15,16 Respondida; 12,14 Parcial; 17 Abierta).

Delegaciones: `negocio-finanzas` → cierre D-09…D-17 en `preguntas.md` + estado en
matriz + R-04 propuesta → entregado. `arquitectura` → ADR-0003 §3.5, §13–§17 →
entregado. Ambos verificados por orquestador (grep de estados, lectura de cabeceras
nuevas del ADR).
Evidencia que falta: proveedor (AB-04), corpus real de piloto y umbrales ASR/OCR
(ADR §15, paramétricos), respuestas D-12/D-14/D-17, AB-02.
Resultado final y enlaces a artefactos:
- `docs/arquitectura/adr/ADR-0003*` (§3.5, §13–§17, Estado con nota de fallo)
- `docs/negocio/preguntas.md` (D-09…D-16 cerradas; D-17 abierta; nota AB-02)
- `docs/negocio/agente-whatsapp-roles.md` (subsección 30-oct en §1; estados fila;
  R-04 propuesta en §5)
- `docs/PLAN_DESARROLLO.md` (nota AB-02, editada por orquestador)

---

### [2026-10-31] Plan de desarrollo del módulo agente WhatsApp

Riesgo: Medio (planificación) | Estado: plan creado; construcción pendiente de
autorización de la fase O1 (migraciones) y de los inputs O0.

Hechos:
- Creado `docs/desarrollo/plan-modulo-agente-whatsapp.md` (dueño: orquestador):
  8 olas O0–O7 con tareas, dueños, gates, rollback; criterios de terminado;
  riesgos y paradas; inputs pendientes del dueño (canal, legal P-07, umbrales
  §15, R-04, D-12/D-17, orden de activación).
- Anclado al plan maestro: F2.1–F2.6 son el corazón de las Ola 1–2 (el módulo
  agent es el driver de esas tareas `pendiente` del `PLAN_DESARROLLO.md:424-429`).
- Revisado y corregido por el orquestador: 2 pasadas de diff, fragmentos
  corruptos eliminados (grep de verificación limpio).

Supuestos:
- El go de la Ola 1 (esquema + migraciones) requiere tu aprobación explícita
  (regla del repo); la aplicación va primero a `tei_test` (regla RA-13).
- Ola 3/Ola 4 en paralelo solo con el contrato HTTP de la Ola 2 fijado.

Resultado final y enlaces: `docs/desarrollo/plan-modulo-agente-whatsapp.md` —
insumo de trabajo desde hoy; a los subagentes solo se les entrega su tarea + ola.

---

### [2026-10-30] ADR-0004 — Proveedores de IA, canal WhatsApp y privacidad (AB-04)

Riesgo: Medio (documento de decisión externa verificado vía web; el fallo final y
la implementación posterior son del dueño / Alto) | Estado: cerrada la evaluación;
abierta la decisión final del dueño (5 preguntas §10 del ADR) y el OK legal (P-07).

Hechos confirmados (verificados por el orquestador vía web, 2026-10-30, marcados 🟡
en el ADR como "dato externo a fecha; re-validar al firmar"):
- Meta cobra por **plantilla entregada** (per-message desde jul-2025, tarifas vigentes
  01-oct-2026); mensajes no-plantilla dentro de ventana de servicio de 24 h = gratis;
  usuario→biz no se cobra → los flujos del ERP son casi todos gratis.
- Límites de media: audio ogg/opus 16 MB, imagen 5 MB, PDF 100 MB; media en servers
  de Meta 14–30 días → descarga a storage propio obligatoria.
- Ningún proveedor de IA entrena con datos API-pagos por defecto (OpenAI desde
  2023, Anthropic commercial, Google pagado); ZDR disponible con excepciones por
  endpoint (OpenAI: Files/Conversations/Assistants NO cubiertos; Anthropic: Files/
  Batch/code-exec NO elegibles; Google: `store=false`, grounding no desactivable).
- Benchmark multmodal 2026: sin líder único (Gemini 3 audio/video, Whisper-3 ASR
  puro, Claude Opus documentos largos y sin audio nativo, GPT-5.x texto denso en
  imágenes); **decaimiento ≥10 pt (algunos >20) de audio limpio→ruidoso** → el
  corpus con tus audios/fotos reales (ADR-0003 §15) es el juez de verdad.
- Ley 21.719: vigencia fijada 01-DIC-2026 (BCN); proyecto de postergación en trámite
  en el Senado (oct-2026) — el diseño no espera la postergación.

Decisión registrada en ADR-0004 (Propuesto):
- **Malla multimodelo por tarea** con el DI de ADR-0003 como frontera (máx 4
  contratos de IA): Orquestador (GPT-5.x/Gemini 3/Claude), ASR (Whisper-3 default;
  Gemini alternativa; faster-whisper self-hosted si legal exige residencia),
  Visión fotos (GPT-5.x/Gemini + OCR clásico fallback), PDF largo (Claude/Gemini +
  extracción nativa primero). El corpus §15 valida cada asignación; el swap es
  configuración + re-evaluación, nunca código.
- **Canal**: Meta Cloud API directa primaria (número del dueño, menos encargados en
  cadena, sin markup); 360dialog alternativa (residencia UE, EUR 49–99/mes ref.);
  Twilio descartada por markup y cadena más larga. 3 plantillas mínimas (OTP,
  resultado aprobación, aviso pendiente).
- 6 reglas de diseño de privacidad independientes del legal (storage propio, stateless,
  no endpoints con estado del proveedor, mínimo retención, media=dato, idempotencia
  por wa_message_id); 4 campos entregados a legal vía P-07.

Contradicciones: ninguna; el subagente corrigió la numeración que le sugerí por la
real de ADR-0003 (verificado por orquestador).

Delegaciones: `arquitectura` → `docs/arquitectura/adr/ADR-0004-proveedores-ia-whatsapp-privacidad.md` → entregado y verificado (leído §3–§4.3 por el orquestador).
Evidencia que falta: fallo del dueño (§10: canal, ratificación de malla, cuándo
exigir ZDR/DPA, plantillas de notificación, activación de plan self-hosted), OK
legal P-07, corpus de piloto con umbrales (§15), precios por token (diferidos).
Resultado final y enlaces a artefactos:
- `docs/arquitectura/adr/ADR-0004-proveedores-ia-whatsapp-privacidad.md` (Propuesto)
- En paralelo no bloqueado: F2.5/F2.6, ACL §13, solicitudes/buzón y hoja de ruta
  §14 de ADR-0003 avanzan sin depender del proveedor.

---

### [2026-10-31] Fallo del dueño sobre la malla de modelos — ADR-0004 a "Aceptado con condiciones"

Riesgo: Medio (registro de decisión; implementación posterior = Alto) |
Estado: cerrada la decisión de modelos; abiertas canal (por defecto aplicado,
pendiente confirmación), legal P-07 y licitación-piloto del corpus.

Hechos confirmados (verificados por el orquestador post-edición):
- Fallo del dueño 2026-10-31: "no me interesa el precio; que funcione; dejo puesto
  el mejor modelo para cada tarea, orquestado por otro modelo que se conecta con
  el núcleo" → ratifica la malla multimodelo (ADR-0004 §3) y la asignación inicial
  §3.1.1: **Orquestador/NLU + PDFs = Claude Opus 4.7; ASR = Whisper-3 API (OpenAI);
  Visión fotos = GPT-5.x (OpenAI); plan B por tarea = Gemini 3**. MVP con
  **2 contratos activos** (Anthropic + OpenAI). Swap post-piloto = configuración +
  re-evaluación §15, nunca código.
- Fallos tácitos aplicados por recomendación técnica: **ZDR+DPA+no-entrenamiento
  desde el primer contrato**; canal **Meta Cloud API directa por defecto** (🟡
  pendiente confirmación explícita del dueño); plan self-hosted solo si P-07 lo exige.
- **D-14 cerrada (2026-10-31)**: aprobación en buzón UI; notificación por WhatsApp
  al solicitante (según su especificación del 29-oct) → plantilla utility fuera de
  ventana. Preguntas §10 del ADR: 2, 3, 5 ✅; 1 parcial; 4 cerrada vía negocio.
- Cabecera de `preguntas.md` resincronizada + nota de fallo en D-13 (editadas por el
  orquestador — remanentes marcados por negocio-finanzas).

Supuestos provisionales:
- Los 4 modelos son snapshot de mercado oct-2026 🟡; re-validación por ADR-0003 §15
  (corpus del dueño) y al cambiar versión de proveedor.

Contradicciones: ninguna. Un propietario por archivo respetado (arquitectura:
ADR-0004; negocio: fila D-14; orquestador: cabecera/D-13/registro).

Delegaciones: `arquitectura` → ADR-0004 (Estado + §3.1.1 + §5 + §10) → verificado.
`negocio-finanzas` → fila D-14 → verificado con grep.
Evidencia que falta: confirmación del canal por el dueño; OK legal P-07 (ahora solo
2 DPAs: Anthropic + OpenAI); corpus de piloto con umbrales del dueño (condición para
activar modalidad a usuarios reales, no para construir).
Resultado final y enlaces: `ADR-0004` = **Aceptado con condiciones**; implementación
del runtime premium y del núcleo (F2.5/F2.6, ACL, solicitudes) desbloqueada en su
totalidad, sin nadie esperando proveedor. Siguiente ola natural: `datos`+`backend`.

---

### [2026-10-29] F0 Due Diligence + Fase 1 (infraestructura y aislamiento de tests)
Riesgo: Alto (auditoría + reset local autorizado) | Estado: F0 cerrada; fase 1 en curso
Hechos confirmados:
- F0 completa: veredicto A (REFACTOR) ratificado por el dueño; informe en `docs/qa/informes/F0-due-diligence.md`; suites 52 unit + 100 integración + 9 E2E en verde, reproducibles (reset 19 migraciones + seed, 27 s).
- Migraciones: 19/19 en disco, en HEAD (`de0d6d3`) y aplicadas en local; la cifra previa "3 en HEAD" era medición errónea de `git ls-tree` sin slash (corregida en estado.md y F0).
- RA-13 mitigado: fixtures (`conftest.py:40-54`, `test_reglas_negocio.py:104-118`, `test_nucleo_integracion.py:52-75`) leen `NUCLEO_TEST_DATABASE_URL` con guarda; base de test `tei_test` creada como clon (`scripts/test_db_reset.sh`); `Makefile test` apunta a tei_test; `backend/.env` corregido vía sed (sin lectura de valores). Prueba de aislamiento: base de la app idéntica tras 2 corridas.
- CI reescrito (`.github/workflows/ci.yml`): Supabase CLI en runner, migraciones + seed + base de test + pytest completo con credenciales. Pendiente de validación real en primer push.
Decisiones pendientes (y de quién):
- D-2 (dueño/arquitectura): bypass de `scripts/cutover_legacy.py` (9 tablas núcleo sin permisos/triggers/auditoría, tarifas/OC sintéticas MIG-*).
- D-3 (dueño): fecha del 2º tenant → urgencia de RLS (políticas + rol sin bypass).
- Residuo TEST-f246f6ad inmutable en ambas bases (triggers no permiten DELETE de reservas): limpiar con reset autorizado o intervención quirúrgica (baja prioridad, data ficticia).
Delegaciones: arquitectura→F0 WP-1/2/7 (docs/qa/informes/) · frontend→WP-1-FE · datos→WP-3 · qa→WP-4/5 · auditor-seguridad→WP-6 · backend→F1 aislamiento de tests (`docs/backend/informes/f1-tests-aislados.md`) — todas cerradas.
Evidencia que falta: CI real (primer push); E2E en CI; guarda RA-13 en los `test_nucleo_*.py` restantes.
Resultado final y enlaces: `docs/qa/informes/F0-due-diligence.md`, `docs/qa/informes/f0-wp*.md`, `docs/backend/informes/f1-tests-aislados.md`.

#### Fase 1 — progreso al 2026-10-30 (respuesta al "continúa con las fases" del dueño)
Riesgo: Alto (RLS/uploads/cutover) | Estado: olas 1–4 cerradas; Ola 5 bloqueada por aceptación del ADR-0005
Hechos confirmados (evidencia en docs/):
- Baseline actual: `make unit` 67 passed · `make test` 219 passed (tei_test) · E2E 9/9 (F0) · frontend `tsc`/lint/build verdes.
- Aislamiento de tests: fixtures con guarda RA-13 + `tei_test` (clon) + `make test-db`; 3 corridas limpias; base de la app intacta.
- CI: `.github/workflows/ci.yml` reescrito (Supabase CLI + migraciones + seed + base de test + pytest). Validación real pendiente del primer push.
- Ola 2/2.1: cutover fail-closed (RA-04), mapeo SQLSTATE→HTTP, DEBUG=false, uploads con firma mágica y content-type de servidor, POD solo-imagen, idempotencia de documentos (200), SEC-016/017/018/019/020. Revalidado por auditor-seguridad 7/7 CONFORME.
- Ola 3: SEC-023 (máx. 10 fotos POD, mutación), F-04 Decimal en kpi_engine, frontend deps 12→3 (0 critical/high; 3 low en CLI shadcn).
- Ola 4: SEC-021 middleware de cuerpo (32 MB / 106 MB POD), contexto `app.empresa_id`+`nucleo.auth_id` por transacción (sobrevive commits, fail-closed), flakiness RUT estabilizada (helper + 18 archivos, 3 corridas verdes), pruebas RLS 4/4 en tei_test.
Decisiones pendientes (y de quién):
- Aceptar ADR-0005 (tenancy: dos engines; legacy con rol actual, núcleo con tei_app). Dueño.
- D-2 (cutover): recomendación del ADR = bypass como operación de plataforma con 6 verificaciones compensatorias; faltan D-2.a…e del dueño.
- D-3: fecha del 2º tenant (urgencia de RLS en la app).
- pip-audit: 50 CVEs pendientes de actualización (starlette/pyjwt/python-multipart) — ola de dependencias backend.
- SEC-021 residual: tope equivalente en el proxy de despliegue (operación).
- Frontend: mover `shadcn` a devDependencies para 0 vulns en `--omit=dev`.
Evidencia que falta: CI real (push); E2E en CI; pooler real con SET LOCAL + tei_app; `INSERT` de viaje completo bajo RLS (fixtures de qa).
Resultado: `docs/qa/informes/F0-due-diligence.md`, `f0-wp*.md`, `f1-ola2*.md`, `f1-ola3-*.md`, `f1-ola4-*.md`, `docs/backend/informes/f1-*.md`, `docs/frontend/f1-ola3-dependencias.md`, `docs/datos/rls-multiempresa.md`, `docs/arquitectura/adr/ADR-0005-tenancy-rls-dos-engines.md`, `supabase/migrations/0020_rls_multiempresa.sql`.

#### Fase 1 — Ola 5: tenancy activa (2026-10-30)
Riesgo: ALTO | Estado: cerrada (código) | Decisión: ADR-0005 aceptado por delegación de criterio del dueño ("haz lo que estimes conveniente")
Hechos confirmados:
- `0020_rls_multiempresa.sql` APLICADA en la base local de la app (35 políticas, 31 FORCE) y en `tei_test`; rol `tei_app` sin BYPASSRLS.
- Dos engines: legacy `postgres` (intacto) / núcleo `tei_app`; con `NUCLEO_DATABASE_URL` explícita el arranque verifica que el rol no bypasee RLS (503 si bypasea). Fallback single-engine con warning si la variable falta (desviación declarada del ADR §3.2.2).
- `mis-empresas` corregido (no fijaba `nucleo.auth_id`).
- Pruebas: `make unit` 67 · `make test` **230 passed** (×2) · `test_f1_ola5_dos_engines.py` 11/11 · evidencia de roles: legacy `('postgres', True)`, núcleo `('tei_app', False)` · mutación (núcleo→legacy) rompe 6 pruebas de aislamiento.
- Backend local reiniciado con `make backend` (RLS activa en la app); `/health` 200 y `/api/v1/viajes` 401.
Pendientes: mapeo 42501→403/404 (hoy 500 genérico), pip-audit CVEs, E2E en CI, shadcn a devDependencies, frontend POD 10 fotos (UX), D-2 cutover, pooler real.

---

### [2026-10-30] Ola 1.1 — esquema del agente WhatsApp: estado real y corrección del registro

Riesgo: Alto (dinero/tenant/migración) | Estado: en curso — esquema aplicado y
smoke verde; falta contrato documental (`datos`) y pruebas de invariantes (`qa`),
ambos delegados y corriendo en paralelo.

**Corrección de dos afirmaciones previas (evidencia primaria, no memoria):**
1. El resumen de sesión decía "nada de Ola 1 se ejecutó; el esquema no existe".
   **Falso**: `supabase/migrations/0021_agente_whatsapp.sql` existe (883 líneas,
   untracked, mtime 30-oct 01:22) y **está aplicada en `tei_test`**. La sesión de
   `datos` se interrumpió después de aplicar, antes de escribir su documento.
2. El mismo resumen decía "RA-03 pendiente: ADR-0005 sin aceptar y app conecta
   como `postgres` con BYPASSRLS". **Desactualizado**: ADR-0005 está **Aceptado**
   (`ADR-0005…md:3`), `tei_app` existe con `rolbypassrls=false` y hay 44 políticas
   en `nucleo` (35 de 0020 + 9 de 0021). El wiring existe en
   `backend/app/core/database.py:113-122`; que el proceso en ejecución use
   `NUCLEO_DATABASE_URL` queda 🟡 (no se lee `.env`).

**Verificado por el orquestador hoy (comandos reales):**
- Catálogo en `tei_test`: 8/8 tablas del módulo, columna
  `nucleo.viajes.id_comercial_flete`, 8/8 enums, 5/5 funciones, 13 triggers,
  9 políticas del módulo, RLS+FORCE en las 8 tablas.
- `docker exec -i supabase_db_TRANSTEI psql -U postgres -d tei_test
  -v ON_ERROR_STOP=1 < supabase/tests/0021_01_smoke.sql` → **14/14 OK**:
  `SQM-00001`/`SQM-00002` consecutivos, prefijo inválido y cliente de otra
  empresa rechazados (23514), código repetido (23505), auditoría append-only
  con DELETE/UPDATE/TRUNCATE bloqueados, touch/version, catálogo.
- `psql` no está instalado en el host; la verificación se hizo con
  `.venv/bin/python` + psycopg usando la URL de test documentada en `Makefile`
  (no se leyó `.env`).

**Delegaciones lanzadas (background, sin solape de archivos):**
- `datos` → `docs/datos/agente-esquema.md` (§2 precondiciones, §3 invariantes
  AW-01..AW-16, §4.1/§4.2 decisiones, §6 verificación) + entradas en
  `catalogo-migraciones.md` e `invariantes.md`. Prohibido editar 0021 o
  `supabase/tests/**`.
- `qa` → `supabase/tests/0021_02_concurrencia_id_comercial.py` (2 conexiones
  reales: IDs concurrentes, doble aprobación, `wa_message_id` duplicado),
  `0021_03_rls_tei_app.sql` (fail-closed y cruce de empresa con rol real),
  `0021_04_mutacion.sql` (retirar mecanismo → la prueba debe fallar) e informe
  en `docs/qa/informes/`.

**Evidencia que falta:** resultado de ambos entregables; prueba de RLS con el
rol `tei_app` (0021_03); prueba de mutación; y que la migración esté aplicada
también en la base de la app (hoy 🟡: no verificado).

**Entregable de `datos` recibido y verificado (parcial):** `agente-esquema.md`
(666 líneas, §0–§9), `invariantes.md` §11 y `catalogo-migraciones.md` con la fila
`0021`. Reportó 9 defectos (D1–D9); verifiqué personalmente los tres más graves
con el rol real `tei_app` en `tei_test`, en transacción con `ROLLBACK` y sin
residuo (contador en 0 tras revertir):

| Defecto | Prueba del orquestador (real) | Veredicto |
|---|---|---|
| **D3** contador retrocedible | `UPDATE id_comercial_contador SET ultimo=0` → 1 fila; siguiente llamada devuelve **`SQM-00001`** otra vez | 🟢 confirmado — viola R-04 "sin reutilización" |
| **D2** ID comercial reasignable | `UPDATE viajes SET id_comercial_flete='SQM-00001'` → 1; luego `'SQM-09999'` → 1 | 🟢 confirmado — contradice el `COMMENT` de `0021:566-570` |
| **D4** resolución por código ambigua | dos clientes de la misma empresa generan **`SQM-00001`** ambos | 🟢 confirmado — detalle que D-16 **no fijó** (R-04 §5); no se corrige por iniciativa |

**Decisión de corrección (Ola 1, solo `tei_test`):** D3, D5 (máquina de estados de
`hoja_ruta`), D9 (tope 99.999: `lpad` trunca y reutiliza) y D2 (alinear la base con
el comentario, criterio conservador de R-04) van a una **migración correctiva
`0022`** con `datos`, tras cerrar `qa`. **D4 no**: requiere decisión de negocio
(¿prefijo único por cliente/empresa o resolución que exija cliente?) → se registra
como pregunta; mientras tanto la regla operativa es resolver **siempre con
`cliente_id`** (el contacto lo conoce), nunca por código solo.

**Entregable de `qa` recibido y verificado por re-ejecución propia (O1.2):**
creados `0021_02_concurrencia_id_comercial.py`, `0021_03_rls_tei_app.sql`,
`0021_04_mutacion.sql`, informe `docs/qa/informes/2026-10-31-o1.2-invariantes-agente.md`
y sección 13 en `docs/qa/matriz-trazabilidad.md`. Yo re-ejecuté las tres suites:
- `0021_02`: 🟢 8 conexiones con barrera obtuvieron `SQM-00001..00008` sin duplicados
  ni saltos; doble aprobación → 1 gana y el perdedor recibe `23514`; mismo
  `wa_message_id` → `23505`.
- `0021_03` (rol real `tei_app`, sin BYPASSRLS): 🟢 sin contexto 0 filas e INSERT
  `42501`; contexto A/B aislados; cruce de empresa `42501`; auditoría sin
  UPDATE/DELETE (`42501`).
- `0021_04` (supabase_admin): 🟢 M1–M5: al retirar índice/trigger/política la
  aserción se rompe y `ROLLBACK` restaura.
- `make unit`: 🟢 67 passed.

**Defecto de configuración detectado (no corregido: requiere autorización):**
`.opencode/agents/qa.md` no incluye `edit supabase/tests/**` en `permissions`,
aunque `AGENTS.md` §11 asigna esa ruta a `qa`. Los tests se crearon por `shell`
bajo autorización explícita del orquestador. Corrección propuesta: una regla
`edit supabase/tests/** → allow` en el frontmatter de `qa`.

**Corrección `0022` aplicada y verificada por el orquestador (solo `tei_test`):**
`0022_agente_whatsapp_endurecimiento.sql` (462 líneas; 4 funciones + 3 triggers;
cero cambios de tablas/datos). Sondas propias con el rol real `tei_app`:
- **D3**: `UPDATE ultimo=0` → `23514` "El contador ... no retrocede".
- **D2**: `NULL → SQM-00001` permitido; `SQM-00001 → SQM-09999` → `23514`
  "El ID comercial ... es inmutable una vez asignado".
- **D5**: observado en el smoke: `propuesto → cargado` → `23514` (transición ilegal).
- **D9**: reportado por `datos` (100000 → `23514` sin quemar el número; 99998 →
  `SQM-99999`); pendiente de mi re-ejecución en el ciclo de `qa`.

**Efecto colateral esperado y en corrección:** `0021_01_smoke.sql` queda rojo en
C10E y C11H porque esas dos aserciones describían el comportamiento defectuoso
(salto ilegal a `cargado`; desasignar el ID). `qa` las adapta preservando la
intención (probar el índice parcial por ruta legal; afirmar el invariante nuevo)
y escribe los rollback `0021_99`/`0022_99` (D1). Ciclo encargado: rollback de
0022 → rollback de 0021 → verificar cero objetos → re-aplicar 0021+0022 →
verificar → 4 suites verdes. Eso cierra además **D7** (reproducibilidad).

**Cierre O1 (2026-10-30) — rollback probado y reproducibilidad:** `qa` escribió
`supabase/tests/0022_99_rollback.sql` y `0021_99_rollback.sql`, adaptó C10E/C11H
del smoke preservando su intención y ejecutó el ciclo completo en `tei_test`:
rollback 0022 → rollback 0021 (cero objetos del módulo; `nucleo` vuelve a 35
políticas) → **re-aplicación de 0021+0022** → 4 suites verdes. Yo re-ejecuté las
cuatro: `0021_01` **63 NOTICE OK** (14 casos), `0021_02` OK (8 conexiones
simultáneas), `0021_03` OK (8 aserciones, exit 0), `0021_04` **M1–M9** OK (exit 0;
M9 demuestra el tope y que el ROLLBACK restaura). Estado final medido: 44
políticas, 8 tablas con 0 filas, tope D9 presente, 3 triggers de 0022.

**Estado de defectos:** D1 cerrado (rollback scripts), D2/D3/D5/D9 cerrados por
`0022` con mutación, D7 probado en clon (documentación en curso por `datos`),
D8 documentado (aceptado), D10 documentado como artefacto local de ACL (todas las
tablas de `nucleo` son de `supabase_admin`; la app usa `tei_app`), D4 **abierto**
(decisión de negocio), D6 es del backend O2.5.

**Ola 1 cerrada.** Siguiente: F2.1 (contrato del Conector, `arquitectura`) como
prerrequisito de O2; luego `backend` implementa Tool Registry + gate + contactos
+ solicitudes/buzón (O2.1–O2.7), con el módulo apagado por defecto (DEC-10).

**D4 queda como decisión pendiente de negocio** (¿prefijo único por
cliente/empresa o resolución que exija cliente?); mientras tanto la regla
operativa es resolver siempre con `cliente_id`.

---

### [2026-10-30] R-04 numerada y D-18 registrada (O0.5)

Riesgo: Bajo (documentación de negocio) | Estado: cerrada la numeración; D-18
abierta por decisión del dueño.

- `docs/negocio/catalogo-reglas.md:117` — **R-04 "ID comercial de flete por
  cliente"** numerada con fórmula, ejemplo `CN-02`, invariantes y estado real de
  implementación (`0021:548-557,572-636`; `0022:284-341,401-444`), aclarando que
  está solo en `tei_test` 🟡 y que no hay consumo desde `backend/**` 🔴.
- `docs/negocio/preguntas.md:43` — **D-18** registrada (prefijo colisionante vs.
  resolución siempre con `cliente_id`), con opciones (a)/(b) y recomendación (b);
  **no decidida** por instrucción.
- **Colisión de namespace detectada:** `docs/arquitectura/deuda.md:55` ya usa
  `D-18` para una deuda técnica. El espacio `D-NN` de `preguntas.md` es de
  decisiones del dueño; la deuda debería renombrarse (`DEU-NN` u otro). Archivo
  de `arquitectura` → se resuelve con ese agente, no se edita por iniciativa.
- Referencias obsoletas "aún no numerada" en `agente-whatsapp-roles.md:135-136,222`
  → corregidas en seguimiento por `negocio-finanzas`.

---

### [2026-10-30] F2.1 revisado y aceptado con una corrección; apertura de O2.1/O2.2

Riesgo: Alto (identidad, ACL, tenant) | Estado: en curso.

**F2.1 (`docs/arquitectura/conector-agente-whatsapp.md`, 1617 líneas + ADR-0006)
revisado por el orquestador en las secciones que fijan el contrato para código:**
§2.7 (tabla `modulos_empresa`), §3.1–§3.6 (descriptor y límites de una tool),
§4.3/§4.4 (algoritmo y SQL de las cuatro llaves), §4.5–§4.10 (envelope, errores,
sin caché, transacción), §5.1–§5.9 (catálogo 20 declaradas / 19 registrables,
proyección cliente, D4 por rol), §6.1–§6.7 (contrato HTTP del buzón) y §7.

- 🟢 Citas verificadas: CHECK del ID `^[A-Z0-9]{2,8}-[0-9]{5}$` (`0021:551-553`);
  `UNIQUE (empresa_id, cliente_id, id_comercial_flete)` (`0021:555-557`);
  `deps.py:50-102` (empresa por membresía, nunca por body).
- 🟢 Decisión correcta: el **buzón no depende del flag del módulo** (§6.7), así
  una solicitud pendiente se puede resolver aunque el agente esté apagado.
- 🟢 El gate es **fail-closed si falta la tabla** (`42P01` → módulo apagado), por
  lo que O2 puede construirse antes de aplicar `0023`.

**Defecto material encontrado y verificado empíricamente (corregido por
`arquitectura` en seguimiento):** el contrato decía que `42501` "cae en 500
(`errores.py:186-189`)" citando `main.py:262-273`. Prueba real con el engine y
`tei_app` en `tei_test`:

```text
InsufficientPrivilege MRO: InsufficientPrivilege -> ProgrammingError -> DatabaseError
SQLAlchemy raises: sqlalchemy.exc.ProgrammingError
  .orig: InsufficientPrivilege | sqlstate: 42501 | is IntegrityError: False
```

Es decir: `42501` **no pasa** por `traducir_integrity_error` ni por el handler de
`IntegrityError`; hoy queda sin handler (500 por defecto). Una rama en
`errores.py` habría sido código muerto. `grep -rn "42501" backend/app/` → 0.

**Colisión de namespace documental (no bloquea):** `docs/arquitectura/deuda.md`
usa `D-01…D-23` (deuda técnica) y `docs/negocio/preguntas.md` usa `D-01…D-18`
(decisiones del dueño); `AGENTS.md` §11.2 asigna `D-NN` a decisiones. No se
renombran 23 filas por iniciativa: `arquitectura` agrega nota de prefijo canónico
`DEU-NN` para las nuevas.

**Delegaciones lanzadas en paralelo (sin solape de archivos):**
- `datos` → `0023_modulos_empresa.sql` (llave 1 del gate), RLS+FORCE, GRANTs a
  `tei_app` sin `DELETE`, trigger de versión, fail-closed sin fila semilla;
  `supabase/tests/0023_99_rollback.sql`; sondas con `tei_app`; 4 regresiones.
- `arquitectura` → corrige el mecanismo del `42501`, marca ADR-0006 **Aceptado**
  por delegación de criterio y agrega la nota `DEU-NN`.
- `backend` → O2.1/O2.2: `ContextoAgente` por teléfono, manifiesto v1 con solo
  tools ejecutables, registry con allow-list, gate de 4 llaves con auditoría de
  cada denegación, **tres tools de lectura** (C1/K1/A1) con entidad forzada,
  `GET /nucleo/agente/estado`, handler `ProgrammingError` 42501→403/404 y
  permisos `agente:*` con `gerente` excluido hasta AB-02.

**Evidencia que falta:** resultados de las tres delegaciones; prueba con el rol
`tei_app` de que el flag por empresa apaga/enciende; revisión independiente de
`auditor-seguridad` cuando O2.1 esté implementado (riesgo Alto).

**Siguiente:** consolidar ambos informes (verificar personalmente al menos una
afirmación crítica de cada uno), corregir defectos si aparecen con evidencia, y
pasar a Ola 2 (backend: Tool Registry + gate + solicitudes/buzón).

### [2026-10-31] O2.1 — registry, gate de cuatro llaves y tools de lectura implementados

Riesgo: **Alto** (autorización, aislamiento multiempresa, auditoría) | Estado: **cerrada con revisión independiente pendiente**.
Informe: `docs/backend/informes/o2-1-registry-gate-tools.md`

**Contexto de ejecución:** los subagentes `datos` y `backend` no estaban
disponibles ("Free usage limit reached"), así que O2.1 se implementó directamente
por el orquestador. Esto **agrava** la necesidad de revisión independiente: quien
implementó no puede calificarse a sí mismo un cambio de riesgo Alto.

**Hechos confirmados (🟢, con salida real):**

- Paquete `backend/app/nucleo/agente/` (9 archivos, ~1.800 líneas): `contexto`,
  `tipos`, `manifest`, `ejecutores`, `tools/despacho`, `gate`, `auditoria`,
  `registry`, `api`. Wiring aditivo en `permisos.py`, `main.py`, `api/router.py`,
  `Makefile`.
- `pytest tests/test_agente_manifest.py tests/test_agente_gate.py` → **51 passed**.
- `pytest tests/test_agente_o2_1_integracion.py` contra `tei_test` con el motor
  del núcleo como `tei_app` → **16 passed**, 0 skip.
- `make unit` → **118 passed** (67 previas + 51 nuevas: se agregaron al target para
  que el gate no dé verde sin correr lo nuevo).
- `make test` → **297 passed, 0 failed, 0 skipped**.
- `ruff` en el paquete nuevo → solo 3 × `B008` (`Depends` en default de FastAPI),
  idéntico al patrón de todos los `api_*.py`; el repo no tiene baseline limpio
  (579 hallazgos previos) ni target de lint.

**Defectos encontrados durante la verificación y corregidos (con su prueba):**

| # | Defecto | Corrección |
|---|---|---|
| D1 | `AttributeError: 'ResultadoTool' object has no attribute 'truncado'` en `registry.py:134` → 4/16 pruebas fallaban | Campo `truncado` en `ResultadoTool` + helper `_resultado()` (`tools/despacho.py:38`) que lo calcula una sola vez para `datos` y para el envelope |
| D2 | `permission denied for table modulos_empresa`: el fixture escribía con `postgres`, que solo tiene SELECT | Fixtures escriben con `tei_app` (`_dsn_app()`) + `app.empresa_id` de sesión |
| D3 | `test_modulo_apagado_deniega` escribía el flag con el rol equivocado | Usa `_dsn_app()` |
| D4 | `main.py` registraba `repr(exc)` en errores de BD (incluye SQL y parámetros ligados → riesgo de PII) | Registra `sqlstate` + clase, nunca `repr` |
| D5 | `registry.py` usaba `logger.exception` para toda tool fallida (mismo riesgo) | `SQLAlchemyError` → log tipado sin traceback; error no-BD → traceback |

**Hueco de contrato detectado y NO resuelto por iniciativa (§4.1):**
el contrato asume búsqueda **global** de `contactos_whatsapp` por teléfono; bajo RLS
con `tei_app` eso devuelve 0 filas sin `app.empresa_id`. Medido:

```text
tei_app sin app.empresa_id   -> 0 filas
tei_app con empresa_id       -> 1 filas
tei_app con empresa ajena    -> 0 filas
```

No existe tabla ni columna de ruteo `wa_phone_number_id → empresa_id` (la única
columna relacionada es `conversacion_mensajes.wa_message_id`, por mensaje).
Mitigación provisional declarada: `resolver_contacto(empresa_id, telefono)` exige
`empresa_id` y es fail-closed. **Decisión pendiente de `arquitectura`** (ADR o
actualización del contrato) entre: (a) configuración de despliegue por número de
Meta —válido para el piloto—, (b) tabla de ruteo con política propia, (c) función
`SECURITY DEFINER` acotada. Bloquea O2.2, no O2.1.

**Decisiones de interpretación documentadas en el informe:** V5 aplica a `tools[]`
y los `$ref` de descriptores usan `schemas/`; validador JSON Schema propio subset
fail-closed porque `jsonschema` no está instalado ni se autorizó instalarlo; reglas
de §3.3 sin número V se reportan con la V más cercana; V3/V4/V15 conservan su
número de regla validándose explícitamente.

**Contradicciones:** ninguna entre subagentes (no hubo subagentes). La colisión de
namespace `D-NN` (deuda vs. decisiones del dueño) sigue abierta y asignada a
`arquitectura` con prefijo canónico `DEU-NN`.

**Evidencia que falta:**
- 🔴 Revisión independiente de `auditor-seguridad` (autorización, aislamiento,
  auditoría). Pendiente y **no sustituible** por este registro.
- 🔴 Prueba de `statement_timeout` real → `57014` → `TIMEOUT_TOOL` (la
  clasificación está probada unitariamente; el timeout efectivo no).
- 🟡 Higiene de `tei_test`: las pruebas dejan contactos `+56900000101…106` y filas
  de auditoría (tabla append-only, FK NOT NULL); `make test-db` refresca.

**Delegaciones:** ninguna activa (los agentes `datos`/`backend` no estaban
disponibles). Siguiente delegación propuesta: `auditor-seguridad` con objetivo,
diff y criterios, **sin** esta conclusión.

**Siguiente:** lanzar la revisión independiente; pedir a `arquitectura` la decisión
del hueco §4.1; después O2.2 (`solicitudes` + buzón) sobre contrato HTTP ya fijado.

### [2026-10-31] O2.1 — revisión independiente cerrada: 7 hallazgos corregidos, 3 escalados

Riesgo: **Alto** | Estado: **cerrada** (condición de encendido cumplida).
Informes: `docs/backend/informes/o2-1-registry-gate-tools.md` §10 y
`docs/seguridad/hallazgos-o2-1.md` (SEC-030…SEC-040).

**Revisión independiente:** `auditor-seguridad` revisó con objetivo, diff y
criterios, sin la conclusión del autor. Veredicto: **sin bloqueante para O2.2, con
una condición antes de encender el módulo** (SEC-030). No encontró bypass de
autenticación, lectura cruzada entre empresas, lectura de otro cliente/chofer por
la entrada, inyección SQL, tools no declaradas ni fuga de PII en respuestas.

**Limitación del revisor (declarada por él):** su permiso de `shell` fue rechazado,
por lo que **no ejecutó ninguna suite**; todo su informe es estático y lo que
depende de ejecución quedó 🔴. La verificación de ejecución es la del orquestador
(abajo). Esto se registra porque un informe estático no sustituye una prueba.

**Hallazgos corregidos en este entregable (con prueba de regresión):**

| ID | Sev. | Corrección |
|---|---|---|
| SEC-030 | media | Nuevo `sesion_nucleo()` en `core/database.py` con la misma guarda de rol que `get_session_nucleo`; los 5 sitios del paquete migrados. El paquete ya no puede operar con RLS inerte |
| SEC-031 | baja | `try/except` en `autorizar`: un `42501` al leer llaves ahora deniega (`NO_AUTORIZADO:gate_error`) **y deja fila de auditoría** |
| SEC-032 | baja | `_nombre_seguro()` acota y sanea el nombre de tool elegido por el modelo |
| SEC-034 | info | `_motivo_publicable()` quita la ruta absoluta del despliegue de `/estado` |
| SEC-035 | info | V13/V14 recorren el schema **recursivamente** (un `cliente_id` anidado ya no pasa) |
| SEC-036 | info | `cargar_registry` no lanza: registry cerrado ante cualquier fallo de carga |
| SEC-037 | info | `auditoria.py` registra tipo + `sqlstate`, nunca el mensaje de PostgreSQL |

**Sanidad por mutación (SEC-031):** al neutralizar el `except`, la prueba
`test_gate_que_falla_deniega_y_audita` **falla** con el `ProgrammingError` crudo. La
prueba guarda el arreglo, no lo decora. (Un primer intento de mutación fue inválido
—dejaba el `except Exception` intacto— y se repitió; se registra para no presentar
un falso positivo.)

**Escalado, no corregido por iniciativa:**
- **SEC-033** (PII): `pregunta_resumida` sin redacción propia → decisión de contrato
  y del runtime, antes de O2.4 (primera tool con montos).
- **SEC-040**: discrepancia §2.6.4 vs §6.5 del contrato → `arquitectura`.
- **SEC-038** (`main.py:262-266` registra `repr`) y **SEC-039** (`tei_app` puede
  escribir las llaves que consume el gate): **preexistentes, no atribuibles**;
  registrados para `backend` y `datos`/`arquitectura`. **No se tocaron.**

**Evidencia de ejecución (post-corrección):**

```text
make unit                                        -> 124 passed
pytest tests/test_agente_o2_1_integracion.py -rs -> 17 passed, 0 skipped
make test                                        -> 304 passed, 0 failed, 0 skipped
ruff (paquete nuevo + pruebas)                   -> solo 3 × B008 (patrón FastAPI del repo)
```

**Evidencia que falta:**
- 🔴 `statement_timeout` efectivo → `57014` → `TIMEOUT_TOOL` con una consulta lenta
  real (la clasificación está probada unitariamente; el corte no).
- 🟡 Matriz adversarial A1–A15 del auditor (§ del informe de seguridad) diseñada
  pero no ejecutada: la ejecuta `qa` cuando exista el runtime.
- 🟡 Higiene de `tei_test`: quedan contactos `+56900000101…106` y filas de
  auditoría (append-only); `make test-db` refresca.

**Decisiones pendientes:** hueco §4.1 (cómo obtiene el runtime `empresa_id` para
resolver el contacto) sigue **abierto** y bloquea O2.2. Es de `arquitectura`;
opciones (a) config por número de Meta, (b) tabla de ruteo, (c) función
`SECURITY DEFINER` acotada.

### [2026-10-31] Árbol de trabajo ordenado en 5 commits

Riesgo: Medio (historia, no código) | Estado: **cerrada**.
Autorización: explícita del dueño ("ataquemos el primer punto"). **Sin push.**

**Situación de partida:** 150 archivos sin commitear (84 nuevos, 66 modificados)
que mezclaban cuatro frentes: F1 olas 2–5, Ola 1 del agente (0020–0023), F2.1
(contrato/ADR) y O2.1 (código). Todo el trabajo de riesgo Alto de varias sesiones
existía solo en el disco.

**Resultado:**

| Commit | Contenido | Archivos |
|---|---|---|
| `9fb4f20` | `feat(db)`: RLS multiempresa y motor dual (0020) + infra de tests aislados | 23 |
| `3638c7f` | `feat(agente)`: esquema WhatsApp 0021–0023 + pruebas SQL | 17 |
| `2932f39` | `docs(agente)`: contrato del conector y ADRs 0003–0006 | 13 |
| `51b6797` | `fix(f1)`: olas 2–5 (storage/POD, Decimal, handlers, suites) | 66 |
| `f2cd2f0` | `feat(agente)`: O2.1 registry, gate y tools de lectura | 30 |

**Verificación de HEAD (la única que se hizo):**

```text
make unit  -> 124 passed
make test  -> 304 passed, 0 failed, 0 skipped
git status -> solo frontend/AGENTS.md (no commiteado a propósito)
```

**Defecto conocido de este split (verificado, no supuesto):** el `Makefile` del
commit `9fb4f20` referencia `tests/test_agente_manifest.py` y
`tests/test_agente_gate.py`, que no existen hasta `f2cd2f0`:

```text
git show 9fb4f20:Makefile | grep -c test_agente      -> 2
git ls-tree 9fb4f20 backend/tests/ | grep -c test_agente -> 0
```

Por lo tanto **`make unit` falla en los commits 1 a 4**. No afecta a HEAD ni a
ningún despliegue (rama local, sin publicar), pero rompe un `bisect` limpio. La
causa es estructural: el `Makefile` sirve a dos frentes (infra de `tei_test` en el
commit 1, lista de `unit` en el 5) y partirlo exigía cortar hunks a mano, algo que
se descartó por riesgo. Si se quiere historia perfecta, el arreglo es mover esas 2
líneas del commit 1 al 5 con un rebase; queda a decisión del dueño.

**Hunks mezclados, documentados en cada mensaje de commit:**
- `Makefile`: `test-db`/`DB_URL_TEST` (F1) + lista de `unit` (O2.1).
- `core/database.py`: motor dual (F1) + `sesion_nucleo()` (O2.1).
- `main.py`: handlers de F1 + `manejador_programming_error` (O2.1).
- `docs/datos/{invariantes,catalogo-migraciones,garantias}.md`,
  `docs/qa/matriz-trazabilidad.md`, `registro.md`: documentos acumulativos.

**Exclusiones deliberadas:**
- `frontend/AGENTS.md` **no** se commitea: lo regenera `next dev` (`AGENTS.md` §5).
  Tampoco se revierte: no se descarta trabajo ajeno.
- `backend/.env.example`: se commiteó por ser el archivo de ejemplo (+3/−1, solo
  placeholders), pero **su contenido no fue inspeccionado** — el guard de
  herramientas bloquea rutas `.env*`. 🟡 Verificar a mano que solo tenga
  placeholders.

**Evidencia que falta:**
- 🔴 Los commits intermedios no se verificaron individualmente (y los 1–4 no
  pasan `make unit`, ver arriba).
- 🔴 `frontend/package-lock.json`: no se ejecutó `npm install`; el bump
  `next 16.3.7 → 16.4.3` es real pero la consistencia del lock no está verificada.
- 🟡 `docs/PLAN_DESARROLLO.md` quedó en `docs/` aunque `AGENTS.md` indica que los
  planes históricos van a `docs/_archivo/`. No se movió por iniciativa.

**Pendiente inmediato:** los 5 puntos de `docs/desarrollo/backlog.md` §6. El
primero (este) queda cerrado; sigue el corpus de O0 y la decisión de §4.1.

### [2026-10-31] O2.2 — buzón de solicitudes implementado; SEC-038 y timeout cerrados

Riesgo: **Alto** (aprobación con efecto real, concurrencia, tenant) | Estado: **implementado y probado; revisión independiente pendiente**.
Informe: `docs/backend/informes/o2-2-buzon-solicitudes.md`

**Hechos confirmados (🟢):**

- `backend/tests/test_agente_o2_2_buzon.py` → **14 passed**.
- `make test` → **321 passed, 0 failed, 0 skipped**; `make unit` → 125 passed.
- **Concurrencia real con dos conexiones**: `test_dos_aprobadores_solo_uno_aplica`
  hace que A tome `FOR UPDATE` y retenga el `commit`; B queda bloqueado y, al
  reanudar, ve el estado terminal. Se verifica `version=2` (una transición, no dos
  efectos) — no es una prueba secuencial disfrazada.
- El `payload` propuesto de la hoja de ruta **no** se reescribe al confirmar; la
  corrección va a `valores_cargados` (ADR-0003 §14.2, lo impone el trigger).

**Contradicción del contrato resuelta y declarada:** §6.6 asigna el ejecutor de
`hoja_de_ruta` a O2.5; §6.7 afirma que `confirmar` sobre ese tipo funciona. Se
implementó el ejecutor (adelanto parcial y acotado de O2.5, no llama servicios
ajenos) y los otros tres tipos devuelven 501. Si el dueño prefiere 501 puro, se
retira revirtiendo `EJECUTORES_SOLICITUD` a `{}`.

**Desviación anotada:** `solicitante.nombre` es `null` cuando solicita un usuario,
porque `nucleo.usuarios_empresa` no tiene columna de nombre.

**Pendientes cerrados en esta pasada:**
- **SEC-038** (`main.py` registraba `repr(exc)`): ahora `sqlstate` + tipo.
- **Timeout por tool** (antes 🔴): `pg_sleep` real bajo `statement_timeout=100ms`
  produce `57014` y se clasifica como `TIMEOUT_TOOL`; `current_setting` confirma
  que el mecanismo del registry queda en `1500ms`.

**Evidencia que falta:**
- 🔴 Revisión independiente de O2.2 (`auditor-seguridad`), riesgo Alto.
- 🔴 Capa HTTP real: no se probó `POST /decidir` con JWT, `X-Empresa-ID` y un
  usuario sin `agente:aprobar`; el permiso está cubierto solo a nivel unitario.
- 🔴 Frontend del buzón (O4.3) no existe.
- 🟡 `resumen` y `diff` probados solo con payloads planos.

**Siguiente:** revisión independiente de O2.2; ADR de §4.1 (delegado a
`arquitectura`); corpus de O0 y `D-12` siguen en manos del dueño.

### [2026-10-31] O2.2 — capa HTTP verificada con JWT real

Riesgo: Alto | Estado: **cerrada la verificación de transporte; revisión independiente en curso**.

`backend/tests/test_agente_o2_2_http.py` → **15 passed** con Supabase Auth real y
`X-Empresa-ID`. Cubre lo que el servicio no podía: membresía por empresa (403 si no
lo es), autoridad de permisos (403 sin `agente:buzon`/`agente:aprobar`), 422 sin
`X-Empresa-ID`, 404 para id de otra empresa, 409 en reintento y versión vieja, 501
sin efecto y 403 de autoaprobación.

**Hallazgo durante la escritura (no era defecto):** la primera versión del fixture
usaba al aprobador como solicitante, así que **todas** las decisiones devolvían 403
`AUTOAPROBACION`. Era la regla funcionando por HTTP. Se corrigió el fixture, no el
código.

Suite completa: **347 passed, 0 failed, 0 skipped**.

**En curso (delegado, no consolidado):** `auditor-seguridad` revisando O2.2 sin la
conclusión del autor; `frontend` construyendo la pantalla del buzón sobre el
contrato HTTP real. Nada de eso se da por bueno hasta verificarlo.

### [2026-10-31] O2.2 — revisión independiente revalidada y pantalla construida

Riesgo: Alto | Estado: **cerrada con una condición documentada**.
Informes: `docs/seguridad/hallazgos-o2-2.md` (§10 revalidación),
`docs/backend/informes/o2-2-buzon-solicitudes.md`.

**Revisión independiente (2 pasadas).** El auditor trabaja **sin shell** (permiso
denegado en ambas sesiones): todo su informe es estático y lo marcó 🔴. La
ejecución la aporta el orquestador.

| ID | Sev. | Estado | Evidencia |
|---|---|---|---|
| SEC-041 | alta | **cerrado** | `confirmar` usaba el `payload` original tras un `modificar`. Ahora: request > `valores_modificados` persistidos > payload. 2 pruebas; **mutación probada en ambas direcciones** |
| SEC-042 | media | **parcial** | `{}` y no-objetos rechazados. La validación de tipos y de `faltantes` exige un schema de payload de `hoja_de_ruta` que **no existe** en el contrato: no se inventa |
| SEC-043 | baja | **cerrado** | El rechazo ahora es fail-closed si la fila existe y no transicionó |
| SEC-044 | baja | **refutado** | El auditor leyó el fixture HTTP mientras se corregía. La versión commiteada usa un solicitante distinto; 15 pruebas HTTP pasan |
| SEC-050 | baja | **acotado** | Sin fila de hoja de ruta el rechazo procede; solo falla cerrado si la fila existe y no pudo transicionar |
| SEC-045…049 | info | abiertos | Aceptados o preexistentes; SEC-049 (`tei_app` con UPDATE directo) sigue siendo el único bloqueante antes de contactos reales (SEC-039 en backlog) |

**Condición documentada (SEC-042 parcial).** El ejecutor `hoja_de_ruta` puede
marcar `cargado` con valores de tipo incorrecto (`{"km":"doce"}`). Hoy el daño es
cero porque **nadie consume** `valores_cargados` todavía; pasa a ser bloqueante de
O2.5 (costo/consumo), donde se define el schema de payload. Opciones si el dueño
quiere cerrarlo antes: (a) `EJECUTORES_SOLICITUD = {}` → todo `confirmar` da 501,
(b) encargar el schema a `negocio-finanzas` + `arquitectura`. **No se relajó
ningún control y no se inventó la regla.**

**Prueba HTTP real (antes era 🔴).** `test_agente_o2_2_http.py` → **15 passed** con
Supabase Auth y `X-Empresa-ID`: 403 sin membresía, 403 sin `agente:buzon`/
`agente:aprobar`, 404 cross-tenant, 409 (reintento y versión vieja), 501 sin
efecto, 403 de autoaprobación, y sin fuga de teléfono/costo/margen.

**Pantalla (O4.3).** `/agente/buzon` con el sistema de diseño existente
(`PageHeader`, `Panel`, `StatusBadge`, `Dialog`, `Table`, `FilasCargando`), reusa
el cliente `nucleo`. Verificado por el orquestador: `npx tsc --noEmit` limpio,
`npm run lint` sin errores, ruta incluida en el build. **El flujo real de datos no
se pudo ejercitar**: la base de la app no tiene 0021–0023 (comprobado:
`to_regclass('nucleo.solicitudes')` → `null` en `postgres`, existe en `tei_test`).
El 500 que vio el subagente es ambiental, no un defecto del buzón.

**Trabajo ajeno detectado en el árbol y NO commiteado:** `.github/workflows/ci.yml`,
`backend/requirements{,-dev}.txt`, `frontend/package{,-lock}.json`,
`frontend/src/components/expediente/pod-panel.tsx`,
`docs/qa/informes/f1-ola6-deps-ci-ui.md` y `frontend/AGENTS.md`. Otro actor los
modificó durante esta pasada; no se tocaron ni se incluyeron en ningún commit.

**Evidencia ejecutada:** `make unit` 135; `make test` **353 passed, 0 failed, 0
skipped**; O2.2 20 + 15 pruebas.

#### Fase 1 — cierre y consolidación (2026-10-31)
Riesgo: Alto | Estado: cerrada (código) | Commit: pendiente de este cierre
Hechos confirmados:
- Otra sesión terminó y commiteó su trabajo (agente WhatsApp: 0021–0023, pantalla, tests). Árbol reconciliado.
- `make db-reset` reproducible: 23 migraciones aplicadas y registradas; 40 tablas nucleo; 45 políticas RLS; 40 FORCE; `tei_app` sin BYPASSRLS. Corregido: `0020` ya no fija NOSUPERUSER desde `postgres` (bootstrap de rol como supabase_admin); `scripts/bootstrap_db_roles.sh`; `test_db_reset.sh` conserva GRANTs.
- Suites: `make unit` 135 · `make test` **353 passed, 0 skipped ×3** (desde clon limpio, sin re-clonar entre corridas) · `make e2e` 9/9.
- Pruebas RLS 0020_01–04 OK sobre clon limpio (0020_01/02 autocontenidos: fixture empresa B + cliente; ya no dependen de datos acumulados).
- Dependencias: pip-audit 0 CVEs; npm audit (prod) 0. CI: job E2E agregado.
- Servidor local: backend :8000 con dos engines (RLS activa), frontend :3000.
Pendientes: commit (este cierre); validación del CI en el primer push; pooler real con SET LOCAL + tei_app; decisiones D-2/D-3 del dueño.

#### Fase 2 — onboarding del segundo tenant (2026-10-31)
Riesgo: ALTO | Estado: cerrada (código) | Decisión: D-3 resuelta por el dueño ("segundo tenant altiro")
Hechos confirmados:
- Tenant TES (`22222222-…`): usuarios `admin2@tei.local` / `despacho2@tei.local` (clave local), membresías, 2 clientes; `scripts/seed_segundo_tenant.py` idempotente; `make db-reset` y CI lo incluyen.
- Núcleo aislado: TES ve lo suyo (200); pedir TEI con sesión TES → 403. `mis-empresas` solo devuelve sus empresas.
- Hueco legacy cerrado: `GateLegacyMiddleware` (main.py) exige membresía en la empresa dueña del legacy (TEI) → `403 LEGACY_SOLO_TEI`; sin token sigue 401. Prueba de mutación: sin middleware, la prueba HTTP falla.
- UI: `es_legacy` en `/auth/me`; se ocultan las 12 pantallas legacy y la URL directa muestra "Sin permiso" (redirect a /despacho).
- Verificación: `make unit` 135 · `make test` **388 (0 skipped)** · `make e2e` 9/9 · 4 pruebas HTTP reales (403 legacy tenant2, 200 núcleo TES, 200 legacy TEI, es_legacy true/false).
Pendientes: CI real en el primer push; pooler real (R-2/R-3); retiro del legacy (ADR-0002) para más tenants; D-2 (cutover) sigue abierta.
