# Plan de desarrollo — Módulo Agente WhatsApp multimodal

> **Pregunta que responde:** ¿qué se construye, en qué orden, con qué dueños,
> pruebas y gates, para tener el agente WhatsApp (cliente/conductor/admin)
> funcionando de extremo a extremo?
> **Dueño:** `orquestador` · **Creado:** 2026-10-31 · **Método:** consolidación de
> decisiones vigentes (ADR-0003, ADR-0004, `docs/negocio/agente-whatsapp-roles.md`,
> `docs/negocio/preguntas.md`, estado F1-fase 1 de `docs/estado.md`)
> **Caduca si:** cambia una decisión D-*, un ADR o el estado de fases del plan maestro.
> **Re-verificar con:** `rg -n "Ola|Gate" docs/desarrollo/plan-modulo-agente-whatsapp.md`

**Fuentes de diseño (no se repiten aquí):**
- Arquitectura: [`ADR-0003`](../arquitectura/adr/ADR-0003-agente-multimodal-whatsapp.md)
  (pipeline, DI §3.4, contexto §3.5, guardarraíles §5, fallos §6, ACL §13, hoja de
  ruta §14, protocolo de evaluación §15, ID de flete §16).
- Proveedores y canal: [`ADR-0004`](../arquitectura/adr/ADR-0004-proveedores-ia-whatsapp-privacidad.md)
  (Aceptado con condiciones: Opus 4.7 + Whisper-3 + GPT-5.x; canal Meta directo por defecto).
- Reglas de rol/capacidad: [`docs/negocio/agente-whatsapp-roles.md`](../negocio/agente-whatsapp-roles.md).
- Decisión de aprobación: solicitudes con **Confirmar / Rechazar / Modificar**
  (D-10); invariante: nunca carga automática.

**Principios no negociables heredados:** agente opera **por tools, no SQL libre**
(DEC-10); escrituras = solicitud + aprobación (DEC-11); monolito modular, el runtime
es un *worker* que usa las interfaces del Núcleo (DEC-16); media = dato, nunca
instrucción; cada consulta auditada (D-17); Legacy (`public`) no se toca.

---

## 1. Situación de partida (verificado)

| Requisito del plan | Estado hoy | Evidencia |
|---|---|---|
| Fase 1 del núcleo operativa (facturación, gastos, disponibilidad, permisos) | 🟢 `make test` 219 passed (fase 1, 2026-10-30) | `docs/estado.md` §2 |
| Registry/gate/contactos/solicitudes/buzón | 🔴 pendiente — tareas F2.5/F2.6 | `PLAN_DESARROLLO.md:428-429` |
| Conector (F2.1/F2.2/F2.3) | 🔴 pendiente | `PLAN_DESARROLLO.md:424-427` |
| Aislamiento multiempresa (RA-03) | 🟡 diseñado + migrado en `tei_test` (`0020_rls_multiempresa.sql`), pendiente aceptación ADR-0005 y wiring del rol | `docs/estado.md` §5 RA-03 |
| Runtime WhatsApp/IA | 🔴 inexistente (D03/B06/I01) | `capacidades-objetivo.md:92,103,109` |
| Decisión de proveedores | 🟡 ADR-0004 Aceptado con condiciones | ADR-0004 Estado |
| Regla R-04 (ID de flete por cliente) | 🟡 propuesta, por numerar en catálogo | `agente-whatsapp-roles.md` §5 |

## 2. Olas

> Cada ola tiene: tarea → dueño → entregable → gate de salida → rollback.
> Las olas 1 y 2 van serializadas por contrato (mismo backend/datos); la Ola 3
> (runtime) y la Ola 4 (frontend) pueden avanzar en paralelo una vez fijado el
> contrato HTTP de la Ola 2.

### Ola 0 — Gates de decisión y materiales (no bloquea construcción)

| # | Tarea | Dueño | Gate |
|---|---|---|---|
| O0.1 | Confirmación explícita del canal (Meta Cloud API directa, §4.1 ADR-0004) | dueño | cierre condición (a) del ADR-0004 |
| O0.2 | OK base de legal: ZDR/DPA + no-entrenamiento (P-07) para Anthropic + OpenAI | dueño + legal | cierre condición (b) |
| O0.3 | Preparar corpus de piloto: 20-30 notas de voz reales de conductores, 20-30 fotos (boletas/POD), 10 PDFs reales | dueño (material), `qa` (procesamiento) | input de Ola 6 |
| O0.4 | Umbrales de aceptación §15 (WER, precisión de campo) definidos por el dueño | dueño | insumo de Ola 6 |
| O0.5 | Numerar regla R-04 en `catalogo-reglas.md` y ratificar formato SQM-00001 | `negocio-finanzas` | insumo de Ola 1 |
| O0.6 | Cerrar D-12 (política OTP/re-enrolamiento/revocación) y D-17 (qué se audita, retención) | dueño | insumos de Ola 1/O2 |

### Ola 1 — TDD rojo + diseño de persistencia (riesgo Alto: dinero y tenant)

| # | Tarea | Dueño | Entregable |
|---|---|---|---|
| O1.1 | Diseño de schema del módulo: `nucleo.contactos_whatsapp` (número→empresa/rol/entidad, estado OTP, activo), `nucleo.permisos_contacto` (ACL por módulo/variable por número), `nucleo.conversaciones`(+mensajes+resumen de contexto), `nucleo.hoja_ruta` (payload JSON estricto, estado, `solicitud_id`), extensión de `solicitudes` (F2.6, tipos: agendamiento/documentos/hoja_de_ruta), `id_comercial_flete` `(empresa, cliente, secuencial 5 dígitos)` **UNIQUE** + generación atómica, `auditoria` extendida (consultas del agente, append-only) | `datos` | `docs/datos/invariantes.md` + borrador de migración |
| O1.2 | Pruebas rojas de cada invariante: UNIQUE del ID comercial (dos generaciones concurrentes), solicitud rechazada no muta estado, auditoría inmanipulable, ACL deny-by-default | `qa` | suites `supabase/tests/` |
| O1.3 | Aprobación del dueño para crear migraciones → aplicación **solo en `tei_test`** primero | dueño + `datos` | migraciones `0021+` |

**Gate:** invariantes probados con 2 conexiones reales; precondiciones de migración
en 0 filas; error mapping `23505/23P01→409`, `23514/23502→422`.
**Rollback:** `DROP` de tablas nuevas (módulo aparte), sin tocar tablas existentes.

### Ola 2 — Backend del Núcleo (F2.2/F2.5/F2.6 con el módulo como driver)

| # | Tarea | Dueño | Entregable |
|---|---|---|---|
| O2.1 | Conector mínimo del módulo + manifest con la lista de tools (lectura y cálculo por componente; escrituras solo como solicitudes) | `arquitectura` + `backend` | F2.1/F2.2 |
| O2.2 | Tool Registry + gate por empresa **y** por contacto (`permisos_contacto`): deny-by-default | `backend` | F2.5 |
| O2.3 | Servicio de contactos/OTP (enrolamiento, revocación por número desde la plataforma) | `backend` | F2.5 |
| O2.4 | Solicitudes/buzón/matriz de aprobación (F2.6) con los **3 estados del dueño**: Confirmar (carga), Rechazar (log, estado intacto), Modificar (plantilla editable → Confirmar) | `backend` + `frontend` (Ola 4) | F2.6 |
| O2.5 | Servicio de hoja de ruta: validación del JSON estricto, detección de campos faltantes, estado "propuesto→solicitud→cargado", idempotencia por mensaje | `backend` | código + pruebas |
| O2.6 | Id comercial de flete: asignación atómica por secuencial, resolución código→flete como tool de lectura | `backend` | R-04 implementada |
| O2.7 | Auditoría de cada consulta del agente (quién, tool, data tocada, timestamp) | `backend` | D-17 |

**Gate:** suite completa + HTTP contract tests (403 sin permiso, 409 conflicto,
idempotencia) + legado intacto (`make test`, `make e2e`; el legacy sigue verde).
**Rollback:** `git revert`; módulo desactivable por manifest (gate a cero).

### Ola 3 — Runtime premium (worker del agente; no modifica el Núcleo)

| # | Tarea | Dueño | Entregable |
|---|---|---|---|
| O3.1 | Webhook WhatsApp: verificación de firma HMAC, desduplicación por `wa_message_id`, descarga de media a object storage propio (prefijo por empresa, DEC-12) **dentro de la ventana de 14–30 días de Meta** | `backend` | endpoint + pruebas |
| O3.2 | Detector de modalidad por MIME (texto/voz/foto/PDF) — no por inferencia | `backend` | ADR-0003 §3.1 |
| O3.3 | Adapters por tarea con la malla ratificada: ASR (Whisper-3 API), Visión (GPT-5.x), PDF+Orquestador (Opus 4.7); contrato **DI** (JSON Schema versionado); salida estructurada validada | `backend` | ADR-0004 §3.1.1 |
| O3.4 | ACL + gate previo a cada tool; respuestas de negación **naturales** (no prefabricadas, pero con la regla real por debajo); auditoría de la consulta | `backend` | ADR-0003 §13 |
| O3.5 | Contexto de conversación: sesión activa, compresión a los 15 min de inactividad, límite ~200k tokens, "memoria reiniciada" natural; conversaciones viven en el ERP (nunca en objetos del proveedor) | `backend` | §3.5 |
| O3.6 | Plantillas mínimas: OTP (authentication), resultado de aprobación y aviso "pendiente" (utility); todo lo demás vía ventana 24 h | `backend` | §4.2 ADR-0004 |
| O3.7 | Fallos y degradación: confianza baja → re-pregunta; proveedor caído → mensaje honesto + expediente del mensaje; **nunca escritura parcial silenciosa** | `backend` | §6 ADR-0003 |
| O3.8 | Secretos de proveedores solo por env del backend (nunca frontend ni repo); `DEBUG=false` en el despliegue de staging | `backend` + `auditor-seguridad` | revisión |

**Gate:** integración con mocks + 1 llamada real por proveedor en staging con
datos de seed; adversariales (inyección por media/expediente) rojos y luego verdes;
rollout por debajo de flag (módulo apagado por defecto — DEC-10).
**Rollback:** flag del módulo a off = el sistema vuelve al operativo actual
(fletes, facturación y cobranza operan sin agente); sin pérdida de data (media ya en storage).

### Ola 4 — Frontend

| # | Tarea | Dueño | Entregable |
|---|---|---|---|
| O4.1 | Ajustes de plataforma: registrar números de admin/dueño; **ACL por número con toggles por módulo/variables** (botón desactiva acceso) | `frontend` | ADR-0003 §13 |
| O4.2 | Módulos clientes/conductores: alta de número (RUT empresa/nombre/teléfono/nombre cliente), estado OTP, revocar | `frontend` | F2.5 UI |
| O4.3 | Buzón: badge, desglose por solicitud, **3 botones (Confirmar/Rechazar/Modificar)**, plantilla editable por valor, log de rechazo | `frontend` | D-10 |
| O4.4 | Deep-link desde notificación/alerta del buzón → redirección al componente del núcleo correspondiente con permiso | `frontend` | flujo del dueño |
| O4.5 | Vista de auditoría de consultas del agente (filtro por contacto/fecha/tool) | `frontend` | D-17 |

**Gate:** `tsc`/`eslint` + E2E del bucle completo (mensaje WhatsApp simulado →
solicitud → aprobar → notificación → deep-link) + E2E regresión existente (9).
**Rollback:** rutas nuevas tras flag.

### Ola 5 — Pruebas adversariales e integración (contrato independiente)

| # | Tarea | Dueño | Entregable |
|---|---|---|---|
| O5.1 | Adversariales: inyección por PDF/foto/nota de voz ("instrucciones" dentro de media), intento de pregunta cruzada (cliente ve gastos de otra empresa/conductores), doble entrega del mismo webhook, doble aprobación concurrente de la misma solicitud, intento de bypass de ACL por re-enrolamiento | `qa` | `docs/qa/informes/` |
| O5.2 | Concurrencia real en PostgreSQL: dos generaciones simultáneas de ID comercial, dos aprobadores sobre la misma solicitud (uno gana, otro recibe 409), auditoría inmutable | `qa` + `datos` | suites con 2 conexiones |
| O5.3 | Independencia: revisión del diff por `auditor-seguridad` (ACL, webhook, secretos, inyección) y `code-review` del flujo Solicitud | `auditor-seguridad`(+`code-review`) | informe |

**Gate:** 0 rojos residuales; hallazgos SEC tratados; el módulo **apagado por
defecto** verificado (sin flag, nada existente responde a WhatsApp).

### Ola 6 — Pilotaje con corpus real (condición de activación, no de construcción)

| # | Tarea | Dueño | Entregable |
|---|---|---|---|
| O6.1 | Ejecutar protocolo §15 con el corpus (O0.3): WER por distribución para ASR, precisión por campo para visión/PDF, sobre `(proveedor, modelo, prompt)` ratificados de ADR-0004 §3.1.1 | `qa` | informe con resultados y plan B activado por tarea si no alcanza umbral |
| O6.2 | Iteración de prompts/schemas por tarea hasta el umbral (sin ensayar en producción); si una tarea no supera umbral → swap por plan B (Gemini o pipeline OCR clásico) sin tocar código | `backend` | registro de la decisión |
| O6.3 | Piloto end-to-end controlado: tu número + 1 conductor + 1 cliente real de seed, todos los flujos, incidencias anotadas | `orquestador` + dueño | acta de pilotaje |

### Ola 7 — Activación y go-live

| # | Tarea | Dueño | Gate |
|---|---|---|---|
| O7.1 | Cierre RA-03: aceptación de ADR-0005 + wiring del rol sin BYPASSRLS en la app (condición para producción con datos reales — hoy `postgres` bypasea RLS) | `backend` + `datos` + `arquitectura` | aislamiento probado con rol real |
| O7.2 | ORD de legal para go-live (P-07 completo) y confirmación final del canal | dueño + legal | condiciones (a)/(b) del ADR-0004 |
| O7.3 | Activación por orden de riesgo: 1) admin (gerente digital) → 2) conductores (hoja de ruta) → 3) clientes (agendamiento/documentos). Cada activación con su modalidad superando su umbral §15 | dueño + `orquestador` | cada rol activado con memoria de rollback (gate por módulo a off) |
| O7.4 | Operación: ruta de backup del media (storage), runbook de incidente del agente, verificación de restore-drill | `orquestador` | docs/operacion |

## 3. Criterios de terminado del módulo (go-live completo)

- [ ] Cliente pide lo suyo y recibe respuesta con fuente citada; cruzada → negación natural + registro.
- [ ] Cliente solicita agendar un flete → solicitud → aprobación en buzón → notificación por WhatsApp con unidades asignadas (D-10/D-14).
- [ ] Documento recibido → asociación a fletes → solicitud → carga tras Confirmar/Modificar.
- [ ] Conductor envía notas de voz y fotos desordenadas → JSON estricto llenado y faltantes detectados; falta → pregunta específica; carga solo tras Confirmar del rol apropiado; rechazo deja estado intacto y log.
- [ ] Admin pregunta lo que sea; ACL por número aplica en cada tool; cada consulta auditada (D-17).
- [ ] Si la herramienta no está autorizada → respuesta natural con la regla por debajo, nada preescrito, coherente entre modalidades (texto/voz).
- [ ] RA-03 con wiring: ACL impuesta en base+servicio ✔, firma del webhook ✔, media en storage propio ✔ (nunca "la UI valida").
- [ ] Revertibilidad: swap de modelo por tarea = config + §15; apagado del módulo = sistema normal.
- [ ] Revisión independiente firmada; suite completa en verde (unit+integration+E2E) y legacy intacto.

## 4. Riesgos mayores y condiciones de parada

| Riesgo | Mitigación | Parada si |
|---|---|---|
| ASR con audio chileno real bajo umbral | corpus §15 + plan B (Gemini / self-hosted) | dos iteraciones sin umbral → escala al dueño con evidencia |
| Inyección por media | media = dato; guardrails + adversarial O5.1 | patrón no contenable → modalidad desactivada; no hay go-live |
| ACL insuficiente (RA-03 sin wiring) | deny-by-default + revisión auditor | go sin RLS wiring = no se expone a datos reales |
| Solicitud con valor erróneo ya cargada | 3 estados + log + corrección compensada (espíritu DEC-11) | — (el flujo del dueño ya lo define) |
| Webhook duplicado / rechazo de Meta | idempotencia + reintentos con backoff | — |

## 5. Decisiones/inputs pendientes (listado honesto)

| Id | Qué es | Dueño |
|---|---|---|
| O0.1 | Confirmación del canal (Meta directo) | dueño |
| O0.2 | P-07 legal (ZDR/DPA/transferencia) | legal + dueño |
| O0.4 | Umbrales §15 (WER, precisión) | dueño |
| O0.5 | Numeración R-04 | `negocio-finanzas` |
| O0.6 | D-12 (OTP/revocación) y D-17 (alcance de auditoría/retención) | dueño |
| O7.3 | Orden de activación de roles | dueño |

**Rollback global:** en todo momento, el módulo apagado re-establece el estado
idéntico al actual (el agente ya está diseñado "instalado y apagado" — DEC-10);
los cambios de esquema se agregan y nunca destruyen; la data del módulo (media,
conversaciones, auditoría) puede purgarse sin tocar la data del negocio.
