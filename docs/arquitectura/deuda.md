> ⚠️ **Aviso de vigencia (2026-11-01):** cita archivos/cifras anteriores al retiro del legacy (`public`, `lib/api.ts`, `backend/app/api/routes/*`, `kpi_engine.py`). No citar como estado actual; ver `docs/estado.md` §2–§6 y `docs/PLAN_DESARROLLO.md`.

# Deuda arquitectónica — registro priorizado

> **Pregunta que responde:** ¿qué deuda estructural existe, cuánto cuesta y en qué condición se paga?
> **Dueño:** arquitectura · **Verificado:** 2026-10-29 (filas D-01…D-23) y 2026-10-31
> (filas DEU-24/DEU-25) · **Método:** consolidación de lectura de código/DDL y de
> `matriz-plan-vs-codigo.md`, `retiro-legacy.md`, `destino-modular.md`,
> `seguridad/hallazgos.md` y `estado.md` §5; sin ejecución.
> **Caduca si:** se cierra un ítem, cambia el esquema o se ejecuta el cutover.
> **Re-verificar con:** `grep -n` de la evidencia citada + `docs/estado.md` §5.
>
> **Prefijo canónico: `DEU-NN`.** Las 23 filas `D-01…D-23` de este archivo se conservan como alias histórico; **las nuevas deudas usan `DEU-NN`**. El prefijo `D-NN` pertenece a las decisiones del dueño en `docs/negocio/preguntas.md` (`AGENTS.md` §11.2): el `D-18` de este archivo (observabilidad) **no** es el `D-18` de `preguntas.md` (resolución de código de flete).
>
> ⚠️ **Aviso 2026-10-31 (Olas A–C ejecutadas).** Varias filas citan archivos que
> **ya no existen** (`routes/viajes.py`, `routes/facturas.py`,
> `routes/liquidaciones.py`, `routes/gastos.py`, `kpi_engine.py`) y describen una
> doble escritura que la aplicación ya no tiene. Siguen siendo válidas como
> **deuda de datos** (histórico sin migrar), no como deuda de código:
> `D-01`, `D-04`, `D-06`, `D-09`, `D-15`, `D-16`. Estado y compuertas vigentes:
> [`adr/ADR-0002-retiro-del-legacy.md`](adr/ADR-0002-retiro-del-legacy.md) rev. 3 y
> [`fuentes-de-verdad.md`](fuentes-de-verdad.md) rev. 2. La reescritura de estas
> filas queda pendiente de `arquitectura`.

---

## 0. Reglas

- **No se duplican los RA.** Se citan por ID (`RA-NN`) y se agrega la evidencia de código que falta en el registro vivo.
- **No se duplican los SEC.** Se citan por ID (`SEC-NNN`).
- Esfuerzo relativo: **S** ≤ 2 días-agente · **M** ≤ 1 semana · **L** > 1 semana.
- "Condición de pago" = hecho observable que convierte la deuda en trabajo obligatorio; no es una fecha inventada.
- Un ítem sin evidencia `archivo:línea` no entra en esta tabla.

---

## 1. Prioridad P0 — bloquea el piloto o el cutover

| ID | Deuda | Evidencia | Impacto | Esf. | Condición de pago | Ref. |
|---|---|---|---|---|---|---|
| D-01 | **Dos esquemas aceptan escrituras y no hay reconciliación.** No existe job, vista, mapeo de IDs ni consulta de divergencia entre `public` y `nucleo`. | `0004:703-757` (solo el núcleo reserva); `routes/viajes.py:152-178` (legacy crea sin reserva); `scripts/cutover_legacy.py:6-13` (copia one-way) | Crítico: doble asignación real, dos ciclos de viaje, dos facturaciones | **L** | Cuando el legacy esté congelado y una consulta de reconciliación devuelva 0 diferencias por concepto | RA-02, RA-06; `fuentes-de-verdad.md` |
| D-02 | **Cutover fail-open y sin evidencia de ejecución.** El flag nace en `false`; si la lectura falla, `legacy_congelado()` devuelve `false` y el legacy sigue escribiendo. | `0014:10,17-19`; `servicio_cutover.py:21-41` (excepto → `congelado = False` en `38-39`); `main.py:36-61` | Crítico: una migración puede correr con escrituras legacy concurrentes | **M** | Cuando `make cutover-dry` y un cutover completo en copia local tengan salida registrada y una prueba demuestre fallo cerrado | RA-04 |
| D-03 | **Aislamiento multiempresa no demostrado.** RLS habilitado sin políticas; el rol efectivo del backend no se verificó. `public` no tiene `empresa_id`. | `0004:1865-1892`; ausencia de `create policy` en `0004`–`0019`; `deps.py:43-82` resuelve empresa solo en aplicación | Crítico: fuga entre empresas si el rol no bypassa RLS o si una consulta omite el filtro | **M/L** | Cuando se identifique `current_user`, se pruebe con el rol real y existan políticas o se declare el rol como única frontera | RA-03 |
| D-04 | **Comisión con doble fuente y liquidación no reproducible.** Nómina legacy usa `porcentaje_produccion`; costo del núcleo usa `porcentaje_comision`; el PDF recalcula al emitir. | `liquidaciones.py:51-96,515-533`; `models.py:584-586`; `0019:17-18,37-41`; `0011:119-124` | Alto (dinero de trabajadores): pagar y costear distinto; documento firmado no reproducible | **M** | Cuando el dueño/contador declaren la fuente canónica (ADR) y exista snapshot inmutable al emitir | SEC-002, SEC-003 |

---

## 2. Prioridad P1 — integridad, datos y operación

| ID | Deuda | Evidencia | Impacto | Esf. | Condición de pago | Ref. |
|---|---|---|---|---|---|---|
| D-05 | **Documentación de cutover desactualizada.** `0015` y `estado.md` §6.1 describen un cutover incompatible porque insertaba viajes con recursos; el script actual migra sin recursos y evita el `23514`. | `0015:130-143` vs `scripts/cutover_legacy.py:6-13,378-401` | Medio: un operador puede abortar un cutover que ya no falla por esa causa, o creer que los viajes migrados quedan asignados | **S** | En la próxima edición de `docs/estado.md` y `docs/datos/catalogo-migraciones.md` (no se edita la migración aplicada), con la salida de un `--dry-run` | SEC-009 (desactualizado) |
| D-06 | **Datos financieros borrables/editables en legacy.** Facturas pendientes se eliminan; gastos se borran con `cascade`; no hay auditoría. | `facturas.py:241-263`; `0001:116`; `gastos.py:92-102`; `0001:267-285` | Alto: pérdida de trazabilidad tributaria y de margen histórico | **M** | Cuando el legacy deje de aceptar escrituras o se bloqueen `DELETE` en tablas financieras | `matriz-plan-vs-codigo.md` #5/#6 |
| D-07 | **Huecos de validación documental.** Degradar la clase A5 de un chofer con viaje vigente no se bloquea; un viaje `borrador/confirmado` con recursos puede quedar con documentos vencidos al cambiar de estado. | `0016:56-62`; `0015:270-277`; `0004:1128-1138` | Alto: despacho con documento inválido | **M** | Cuando exista trigger en `nucleo.choferes` o revalidación en transiciones desde estados no despachados | SEC-005, SEC-006 |
| D-08 | **Idempotencia incompleta en dinero.** Anticipos legacy sin clave única; pagos/notas del núcleo sin `Idempotency-Key`. Un doble clic puede duplicar. | `0001:151-159`; `pagos_nucleo` `0013:78-98` (sin unique de idempotencia); `registrar_pago` `servicio_facturacion.py:620-651` | Alto: dinero duplicado | **M** | Cuando un reintento con la misma clave devuelva el mismo resultado (prueba con dos requests) | SEC-007 |
| D-09 | **Dos definiciones de margen y KPI de mantenimiento engañoso.** El legacy calcula `ingresos − gastos` sin comisión; el KPI ignora tractos sin registro de mantención. | `kpi_engine.py:440`; `kpi_engine.py:484-485`; `0011:115-127` | Alto: decisiones sobre margen sobreestimado; flota nueva sin alerta | **S** | Cuando el dueño/contador definan la fórmula canónica y el KPI trate "sin registro" explícitamente | `matriz-plan-vs-codigo.md` #11/#13 |
| D-10 | **Auditoría parcial.** No cubre `transiciones_viaje` ni `folio_contador` *(la parte de `cutover_control` dejó de aplicar: la tabla fue retirada por `0035`, 2026-11-12)*; el legacy no tiene auditoría. | `0004:813-892`; triggers de auditoría solo en tablas enumeradas en `0004:1756-1862` y migraciones posteriores | Alto: no se puede reconstruir quién cambió un folio | **M** | Cuando toda tabla de estado/financiera tenga trigger y exista una prueba de append-only | RA-07 |
| D-11 | **Pantallas y fuentes duplicadas.** Maestros, viajes, facturación, tablero y rentabilidad tienen dos implementaciones; la selección de empresa no se persiste ni se puede cambiar. | [`docs/_archivo/modulos.md`](../_archivo/modulos.md) §5 (inventario histórico 2026-10-29); `despacho/page.tsx:162-167`; `nucleo.ts:25-34` | Medio-alto: dos verdades para el usuario y decisiones distintas según pantalla | **M** | Cuando cada concepto tenga un esquema canónico declarado y una sola pantalla escriba | RA-06 |
| D-12 | **CI no prueba la base ni las migraciones.** Corre import, pytest sin PostgreSQL, lint y build; no aplica migraciones, no ejecuta integración/E2E. | `.github/workflows/ci.yml:27-50`; `docs/estado.md` §4 | Medio-alto: una migración rota o una garantía de DB puede llegar a `main` | **M** | Cuando el pipeline levante PostgreSQL y corra `supabase/tests/*.sql` + integración | `matriz-plan-vs-codigo.md` #19 (parcialmente desactualizado: el CI ya existe) |
| D-13 | **Riesgo de deriva modelo↔DDL y `HEAD` incompleto.** Solo 3 de 19 migraciones están en `HEAD` (dato heredado de `estado.md` §2, no re-ejecutado en esta sesión); no hay test de deriva ni `create_all`. | `docs/estado.md` §2 y §6.3; `models.py:1-14` | Medio: el esquema real puede diferir del versionado | **M** | Cuando `HEAD` contenga las 19 migraciones y un check compare `information_schema` con los modelos | `docs/estado.md` §6 |
| D-14 | **Uploads sin verificación de seguridad.** POD, comprobantes y documentos usan Storage; MIME real, path y visor no verificados. | `storage.py:34-77`; `servicio_pod.py:36`; `servicio_gastos.py:41` | Medio-alto: archivo malicioso o acceso indebido | **M** | Cuando exista prueba de MIME, límite, path y URL firmada con expiración | RA-11 |
| D-15 | **Export legacy vulnerable a inyección de fórmulas y sin paginación.** CSV con `QUOTE_MINIMAL` no neutraliza `= + - @`; listados sin `limit/offset`. | `export.py:29-46`; `viajes.py:118-137`; `facturas.py:73-87` | Medio: ejecución de fórmulas en Excel; lentitud con volumen | **S** | Cuando el export escape celdas y los listados tengan paginación | `matriz-plan-vs-codigo.md` #15/#16 |
| D-16 | **Export/import y nómina/IVA solo existen en legacy.** El núcleo no exporta ni importa; no tiene liquidaciones ni IVA. | `export.py:49-272`; `liquidaciones.py:278-533`; `finanzas.py:116-185` | Alto para el retiro: borrar el legacy rompe procesos usados | **L** | Cuando esas capacidades tengan equivalente en el núcleo o se declare su retiro | `retiro-legacy.md` M09/M10/M15 |
| D-17 | **Mantenimiento preventivo inexistente en el núcleo.** Solo hay bloqueo de agenda y alerta de 7 días; no hay pauta por km. | `servicio_alertas.py:165-198`; sin tablas `nucleo.*mantenimiento*` en `0004`–`0019` | Medio: flota sin control preventivo | **L** | Cuando el dueño priorice mantenimiento como módulo del núcleo | `matriz-plan-vs-codigo.md` #11 |
| DEU-24 | **Sin ruteo número de negocio Meta → empresa.** El runtime O3 no puede fijar `app.empresa_id` antes de leer `contactos_whatsapp`; la búsqueda global por teléfono del contrato §4.1 no es ejecutable bajo RLS (`tei_app` sin contexto → 0 filas). La mitigación actual exige un `empresa_id` que el llamador aún no tiene. | `0021:218-223,799-814`; `backend/app/nucleo/agente/contexto.py:143-189`; `conector-agente-whatsapp.md` §4.1 paso 2; `docs/backend/informes/o2-1-registry-gate-tools.md:102-131` | Alto: O3 bloqueado; una solución por función privilegiada indexada por teléfono sería un enumerador de tenants | **S** (config) / **M** (tabla) | Cuando el dueño apruebe **ADR-0007** y se implemente el webhook (O3.1) | ADR-0007 |

---

## 3. Prioridad P2 — observabilidad, higiene y documentación

| ID | Deuda | Evidencia | Impacto | Esf. | Condición de pago | Ref. |
|---|---|---|---|---|---|---|
| D-18 | **Observabilidad ausente.** No hay trazas, métricas, alertas de error ni Sentry/OTel; solo logs de aplicación. | `config.py:4-28` no configura logging/métricas; búsqueda `sentry\|opentelemetry\|otel\|prometheus` en `backend/` → 0 coincidencias | Medio: incidentes detectados por el usuario | **M** | Cuando haya un incidente que no se pueda diagnosticar con logs | `destino-modular.md` §6 |
| D-19 | **`DEBUG` nace en `true`.** El default del código es `True`; el valor efectivo por entorno no se verificó. | `config.py:11`; RA-10 | Medio: trazas y comportamiento de desarrollo en un entorno mal configurado | **S** | Cuando `auditor-seguridad` verifique el valor efectivo en local/staging/producción y el default pase a `false` | RA-10 |
| D-20 | **Anon key de Supabase en frontend.** Qué expone PostgREST/Storage no está verificado. | `frontend/src/lib/supabase/client.ts`; RA-12 | Medio-alto: acceso anónimo a tablas/buckets | **S/M** | Cuando se pruebe el alcance real de la anon key contra PostgREST y Storage | RA-12 |
| D-21 | **Restore drill sin comparación.** Verifica existencia y 6 conteos; no compara antes/después ni prueba la app. | `scripts/restore_drill.sh:42-50` | Medio: un restore "exitoso" puede perder datos | **M** | Cuando el drill compare checksums/conteos y ejecute un smoke de la app | RA-05 |
| D-22 | **Documentación sin prueba de vigencia.** Los 6 artefactos de `docs/arquitectura/` y `estado.md` dependen de conteos y rutas que cambian sin CI documental. | `docs/INDEX.md:131-135`; este documento | Bajo-medio: decisiones sobre datos viejos | **S** | Cuando un cambio de esquema o de router obligue a actualizar la cabecera y falle un check de enlaces | `docs/INDEX.md` §4 |
| D-23 | **`matriz-plan-vs-codigo.md` desactualizada.** Afirma 26 routers, 14 migraciones y ausencia de CI; hoy hay 25, 19 y un workflow de CI. | `matriz-plan-vs-codigo.md:62,90,112` vs `router.py:32-56`, `ls supabase/migrations` y `.github/workflows/ci.yml:1-50` | Medio: conclusiones y prioridades apoyadas en cifras viejas | **S** | En la próxima revisión de esa matriz; no se reescribe la historia, se corrige la cabecera y las celdas refutadas | `docs/INDEX.md` §4 |
| DEU-25 | **`pregunta_resumida` sin control de forma (SEC-033).** El registry persiste el texto del llamador (hasta 500 chars) en una tabla append-only sin purga; la redacción se delega a un runtime que no existe. | `backend/app/nucleo/agente/registry.py:123-130`; `0021:687,729-735`; `docs/seguridad/hallazgos-o2-1.md:234-257` | Medio-alto: PII/financiero escrito en auditoría sin posibilidad de borrado | **S** | Antes de O2.4 si el agente empieza a manejar montos; en todo caso al implementar O3 | SEC-033; `conector-agente-whatsapp.md` §7.3.1 |

---

## 4. Orden de pago recomendado

1. **D-01 + D-02 + D-03** antes de cualquier cutover real. Sin ellos, el cutover no es reversible ni seguro.
2. **D-04 + D-08** antes de emitir liquidaciones o cobrar en el núcleo. Es dinero de terceros.
3. **D-06 + D-10 + D-12** antes de declarar el legacy "congelado": sin auditoría ni CI, no hay evidencia de que el congelamiento se respete.
4. **D-05 + D-13 + D-22** en la misma entrega documental: corregir lo que hoy dice el repo y dejar el rastro.
5. **D-16 + D-17** son de alcance, no de corrección: se pagan cuando el dueño decida retirar el legacy o ampliar el piloto.

> **Regla:** una deuda no se cierra por haber escrito el documento que la describe. Se cierra con el mecanismo, la prueba y la evidencia fechada; hasta entonces sigue en esta tabla.

---

## 5. Cierre por retiro del legacy (2026-11-12)

El retiro del legacy (`0028`, cutover Ola D 2026-11-01, código legacy/cutover
eliminado del repo 2026-11-12) **no cierra** estas deudas: las elimina de la
misma forma que se elimina una habitación al demoler la casa. Estado:

| Ítem | Qué pasó | Evidencia |
|---|---|---|
| D-01 (dos esquemas sin reconciliación) | ⚪ **Superado**: `public` no existe; la Ola D reconcilió maestros y pautas con Δ 0 en local | `docs/estado.md` §3–§4; `docs/_archivo/cutover-ejecutado-2026-11-01.md` §3–§4 |
| D-02 (cutover fail-open) | ⚪ **Superado**: el flag y el middleware ya no existen en runtime; el cutover está ejecutado e idempotente | `cutover-ejecutado-2026-11-01.md` §2,§6; `main.py` sin `congelar_escritura_legacy` (2026-11-12) |
| D-06 (financiero borrable en legacy) | ⚪ **Superado**: las tablas y los `DELETE` legacy desaparecieron con `public` | `0028_retiro_public.sql:6-27` |
| D-15 (export legacy con inyección de fórmulas) | ⚪ **Superado** para el código legacy (eliminado). El export actual es `api_export.py` del núcleo (Ola B); revalidar su neutralización de fórmulas si se reutilizó el patrón CSV | `backend/app/nucleo/api_export.py` |
| D-16 (nómina/IVA/export solo en legacy) | ⚪ **Superado** en lo portado (Ola B: `0024`–`0026`, `api_nomina.py`, `api_iva.py`, `api_export.py`). Sigue **abierto** el import CSV, retirado sin reemplazo (`RET-10`) | `retiro-legacy.md` §6; `docs/negocio/preguntas.md` |
| D-05 (documentación de cutover desactualizada) | ⚪ **Superado por extinción**: el cutover se ejecutó y su documentación operativa (`cutover.md`, `cutover-ejecutado-2026-11-01.md`) fue archivada en `docs/_archivo/`; el estado vigente lo llevan `docs/estado.md` y `docs/datos/catalogo-migraciones.md` | `docs/_archivo/cutover.md`; `docs/orquestacion/registro.md` (2026-11-12) |

**Sigue vigente** (no lo cierra el retiro): D-03 (RLS efectivo, RA-03), D-04/D-08
(dinero de terceros: base de comisión `D-01` y idempotencia de pagos/anticipos),
D-10 (cobertura de auditoría: `transiciones_viaje`, `folio_contador`; la parte
de `cutover_control` dejó de aplicar con la migración `0035`) y D-11 (la
selección de empresa no se persiste).
