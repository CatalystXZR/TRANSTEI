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
