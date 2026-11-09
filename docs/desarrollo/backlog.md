# Backlog — qué se está construyendo y qué sigue

> **Pregunta que responde:** ¿en qué va el plan de trabajo y qué es lo próximo?
> **Dueño:** `orquestador` · **Verificado:** 2026-11-01 (Fase 2) / 2026-10-31 (§6, agente) · **Método:** lectura de código + planes archivados + suites ejecutadas
> **Caduca si:** se cierra un P0, cambia el alcance o se abre un frente nuevo.
> **Re-verificar con:** `ls frontend/src/app/\(app\)` y `ls backend/app/nucleo`
>
> ⚠️ **Plan vigente:** [`docs/PLAN_DESARROLLO.md`](../PLAN_DESARROLLO.md). Las §1–§3 son **históricas** (pre Fase 2); el estado real está en [`docs/estado.md`](../estado.md) §2–§6, y los pendientes operativos del agente en **§6** de este documento.

> El **estado verificado** está en [`docs/estado.md`](../estado.md). Este documento
> no repite cifras: describe el trabajo y dónde está cada pieza.

---

## 1. Origen del backlog

Los 13 bloques P0 vienen del plan de desarrollo autónomo
(`docs/_archivo/planes/PLAN_DESARROLLO_AUTONOMO.md` §5). El **código existe** para los
13; lo que no está verificado es que **funcionen de punta a punta** (suite completa y
E2E no se ejecutaron).

---

## 2. Estado por bloque

> **Histórico (pre Fase 2).** Varios P0 ya están cerrados (F0, F1, Fase 2). No citar esta tabla como estado; ver [`docs/estado.md`](../estado.md).

| P0 | Tema | Backend | Pantalla | Brecha principal |
|---|---|---|---|---|
| P0-01 | Alta de viaje del núcleo | `servicio_disponibilidad.py`, `api.py` | `/despacho` | Concurrencia real no probada (2 conexiones) |
| P0-02 | Maestros + documentos/Storage | `servicio_maestros.py`, `servicio_expediente.py` | `/maestros`, `/expediente` | Upload a Storage no verificado (RA-11) |
| P0-03 | OC / tarifas / centros de costo | `servicio_comercial.py` | `/comercial` | Requisito de OC es de facturación, no de despacho (decisión abierta) |
| P0-04 | Bloqueos de mantención/descanso | `servicio_bloqueos.py` | `/agenda` | Sin prueba de solapamiento contra viajes |
| P0-05 | Expediente del viaje | `servicio_expediente.py` | `/expediente/[id]` | Cierre con checklist parcial |
| P0-06 | POD | `servicio_pod.py` | — | Sin pantalla propia; storage sin verificar |
| P0-07 | PWA del conductor | `api_conductor.py` | `/conductor` | Modo offline no verificado |
| P0-08 | Gastos, combustible, peajes | `servicio_gastos.py` | — | Sin pantalla; combustible declarativo |
| P0-09 | Margen / tarifa piso / Freight Score | `servicio_rentabilidad.py` | `/rentabilidad` | Benchmark y volumen del catálogo no implementados |
| P0-10 | Facturación / cobranza | `servicio_facturacion.py` | `/cobranza` | Sin DTE; nota de crédito no implementada |
| P0-11 | Alertas y tablero | `servicio_alertas.py` | `/tablero` | "Caja" es proxy cobros−gastos, no saldo real |
| P0-12 | Roles / permisos / auditoría | `permisos.py`, `servicio_auditoria.py` | `/permisos`, `/auditoria` | Auditoría no cubre el legacy (RA-07) |
| P0-13 | Cutover / seed / E2E / backup / UAT | `servicio_cutover.py` | `/cutover` | **Bloqueado**: `0015` rompe `cutover_legacy.py` |

---

## 3. Pendientes reales (2026-11-01)

> Fuente: `docs/estado.md` §5–§6 y **§6** de este documento. El plan vigente es
> [`docs/PLAN_DESARROLLO.md`](../PLAN_DESARROLLO.md). La tabla §2 es histórica.

| # | Pendiente | Tipo | Dueño | Ref. |
|---|---|---|---|---|
| 1 | Revisión independiente de O2.2 (buzón de solicitudes) | Seguridad/QA | `auditor-seguridad` + `qa` | §6.5 |
| 2 | ~~Cerrar SEC-039~~ ✅ **cerrado 2026-11-01** (`0029`): `tei_admin` + `nucleo.admin_*`; `tei_app` solo lectura en identidad/ACL/flag | Seguridad | — | `0029` |
| 3 | Decidir ADR-0007 (ruteo `número Meta → empresa_id`) | Arquitectura | `arquitectura` + dueño | §6.3 |
| 4 | Corpus O0 (audios/fotos/PDFs reales para ASR/OCR) | Negocio | dueño | §6.4 |
| 5 | **D-12 (OTP)**: flujo admin→WhatsApp + verificación implementado (`0029`, `api_contactos`); falta proveedor WhatsApp real (AB-04) | Seguridad | dueño + `datos` | §6.2 |
| 6 | Restore drill con comparación antes/después | Datos | `datos` | RA-05 |
| 7 | Pooler real (`transaction`) + `SET LOCAL` + límites | Datos/operación | `datos` | RA-15 |
| 8 | Rol de plataforma formal (`tei_platform`) | Datos/seguridad | `datos` | RA-16 |
| 9 | Deudas RLS del ADR-0005 (R-1, R-5, R-9) | Datos | `datos` + `backend` | RA-17 |
| 10 | CI en GitHub Actions (Supabase + E2E) | Operación | operación | RA-18 |
| 11 | Decisiones tributarias/laborales (IVA/F29, nómina, comisiones, DTE) | Negocio/legal | contador | RA-19 |
| 12 | Documentos que citan archivos retirados (16) | Documentación | varios | RA-20 |
| 13 | Decisiones de producto (RET-06/12/13) | Producto | dueño | RA-21 |
| 14 | Deuda de seguridad operativa (rate limit, headers, `/docs`, issuer JWT) | Seguridad | `backend` + `auditor-seguridad` | estado §6.5 |
| 15 | POD: visor/URLs firmadas; anon key/bucket | Seguridad | `auditor-seguridad` | RA-11/RA-12 |
| 16 | UAT real (hoy vacía) | QA/negocio | `qa` + dueño | RA-01 |
| 17 | Reconciliar `PLAN_DESARROLLO.md` con el avance real (F0 y Fase 2 cerradas) | Planificación | `orquestador` | plan |

---

## 4. Fuera de alcance (decidido, no olvidado)

| Tema | Estado | Quién decide |
|---|---|---|
| DTE / SII real | No implementado; el sistema no emite DTE | dueño + contador |
| GPS / telemetría | Solo check-in manual | dueño |
| Conciliación bancaria | No existe | dueño + contador |
| Nómina legal (AFP, salud, gratificación) | No implementado | asesor laboral |
| SaaS multiempresa | Implementado en local con RLS y 2 tenants (TEI + TES); falta producción/pooler (RA-15/16) | dueño |
| Factoring / simulador de caja | Solo propuesta histórica | dueño |

---

## 5. Reglas del backlog

1. Un P0 no se marca cerrado sin prueba ejecutada y registrada.
2. "Existe el endpoint" no es "está terminado": falta UI, permiso y prueba.
3. Lo que requiere decisión de negocio se mueve a `docs/negocio/preguntas.md`.
4. Lo que requiere trabajo técnico se refleja en `docs/arquitectura/deuda.md`.

---

## 6. Módulo agente WhatsApp — pendientes

> Frente distinto del P0 legacy. Estado verificado 2026-10-31.
> Línea base 2026-11-01: `make test` → **413 passed, 0 failed, 0 skipped**;
> `make unit` → **135 passed**; `make e2e` → **20 passed**. Detalle en
> [`docs/backend/informes/o2-1-registry-gate-tools.md`](../backend/informes/o2-1-registry-gate-tools.md)
> y [`docs/seguridad/hallazgos-o2-1.md`](../seguridad/hallazgos-o2-1.md).

### 6.1 Lo urgente (riesgo de pérdida, no es código)

- [x] **1. Poner el árbol en orden con commits por ola.** — hecho 2026-10-31: 6 commits (`9fb4f20`…`b69d9f3`). `make unit` falla en los commits 1–4 (ver registro); HEAD verde.
  Hay ~65 archivos modificados y ~3.000 líneas sin commitear que mezclan cuatro
  frentes: migraciones `0021`–`0023` (Ola 1), documentos de F2.1, el código de
  O2.1 y trabajo previo de F1 (`storage.py`, `servicio_pod.py`, `main.py`/SEC-021).
  Hoy no hay frontera entre olas: un `git checkout` mal puesto o un conflicto y no
  se puede reconstruir qué era de qué. **Todo el trabajo de riesgo Alto de estas
  semanas existe solo en el disco.**
  Propuesta: commits separados (migraciones · docs · O2.1), no uno solo.
  *Requiere autorización explícita del dueño* (`git commit` está en "pedir
  autorización", `AGENTS.md` §10).

### 6.2 No encender el módulo todavía

- [ ] **2. No habilitar `agente-whatsapp` en la base real.**
  La condición del auditor (SEC-030) ya está cerrada, pero encender exige: `0023`
  en la base de la app + fila en `nucleo.modulos_empresa` + enrolamiento de
  contactos + **OTP, que es `D-12` y sigue abierta**. Sin `otp_estado='verificado'`
  el gate deniega todo por diseño: encender ahora produce un módulo que no
  funciona.
  Además, **SEC-039** (el rol `tei_app` puede escribir identidad, ACL y flag que el
  gate consume) debería resolverse antes de que haya contactos reales.
  *Dueño: dueño del producto + `datos`.*

### 6.3 Decisión de arquitectura

- [ ] **3. ADR del ruteo `telefono → empresa_id` (hueco §4.1).**
  El contrato asume búsqueda global de `contactos_whatsapp` por teléfono; bajo RLS
  con `tei_app` devuelve 0 filas sin `app.empresa_id` (medido en O2.1). No existe
  tabla ni columna de ruteo `wa_phone_number_id → empresa_id`.
  Opciones: (a) configuración por número de Meta, (b) tabla de ruteo con política
  propia, (c) función `SECURITY DEFINER` acotada.
  Recomendación del orquestador: **(a) para el piloto, migrando a (b) antes del
  segundo cliente**. La decisión es de `arquitectura`, no del orquestador.
  *Dueño: `arquitectura` (ADR) → `datos` si implica migración.*
  **Estado 2026-10-31:** `ADR-0007` **Propuesto** (`docs/arquitectura/adr/`).
  Recomienda A para el piloto y B1 como destino; falta decisión del dueño (P-1…P-4).
  **Corrección registrada:** esto **no bloquea O2.2** (el buzón usa
  `agente:buzon`/`agente:aprobar` con `ContextoEmpresa`, §6.2–§6.4). Bloquea el
  runtime real (O3) y la resolución en producción.

### 6.4 Camino crítico que ningún agente puede hacer

- [ ] **4. Corpus de O0: 20–30 audios, 20–30 fotos, 10 PDFs reales.**
  Es la condición (c) de ADR-0004 y sin él no hay umbrales §15 para ASR ni OCR.
  Es lo que más tarda y lo único que no se acelera escribiendo código: si no
  arranca en paralelo, se convierte en el cuello de botella de todo el módulo.
  *Dueño: dueño del producto (material real); `negocio-finanzas`/`qa` lo procesan.*

### 6.5 Siguiente trabajo técnico

- [x] **5. O2.2 — buzón de solicitudes** — hecho 2026-10-31 (`233e380`): 14 pruebas de integración, concurrencia real con dos conexiones. **Falta revisión independiente.** Activa: revisión de O2.2 (`GET /nucleo/agente/solicitudes`,
  `GET …/{id}`, `POST …/{id}/decidir`, contrato §6.1–§6.4).
  No depende de §4.1 y es lo que el dueño ve. Riesgo **Alto** (aprobación con efecto
  real sobre datos): prueba roja antes, revisión independiente después.
  *Dueño: `backend` + `qa` + `auditor-seguridad`.*

### 6.6 Hallazgos de la revisión de O2.1 aún abiertos

| ID | Sev. | Qué | Dueño |
|---|---|---|---|
| ~~SEC-033~~ ✅ | baja | **Cerrado** (`5fd401c`): el registry valida la forma y descarta el texto libre; contrato §7.3.1. Verificado por mutación | — |
| ~~SEC-038~~ ✅ | info | **Cerrado** (`5fd401c`): registra sqlstate + tipo, nunca el `repr` | — |
| ~~SEC-039~~ ✅ | media | **Cerrado 2026-11-01** (`0029`): `tei_admin` + `nucleo.admin_*`; `tei_app` solo SELECT en identidad/ACL/flag | — |
| ~~SEC-040~~ ✅ | info | **Cerrado** (`c36791d`): lectura canónica "cargar no es habilitar" anotada en ambas secciones | — |
| ~~timeout~~ ✅ | — | **Cerrado** (`5fd401c`): `pg_sleep` real bajo `statement_timeout` produce 57014 → `TIMEOUT_TOOL` | — |

### 6.7 Decisión del dueño aún abierta (transversal)

- **`D-18` / D4** (prefijo `id_comercial_flete` colisionante vs. resolución siempre
  con `cliente_id`): regla operativa provisional vigente — resolver siempre con
  `cliente_id`. No bloquea O2.1/O2.2; sí la generación de IDs al crear viajes desde
  el agente. *Dueño: dueño del producto.*

### 6.8 Orden recomendado

1. ~~Commits por ola~~ ✅.
2. **Revisión independiente de O2.2** (`auditor-seguridad`) — riesgo Alto.
3. Arrancar el corpus en paralelo (lo más lento y lo único que no hace un agente).
4. SEC-039 antes de cualquier contacto real.
5. Decisión del dueño sobre ADR-0007 (P-1…P-4) para desbloquear O3.
6. Encender el módulo solo con `D-12` (OTP) cerrada y corpus disponible.
