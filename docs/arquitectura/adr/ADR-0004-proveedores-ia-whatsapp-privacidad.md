# ADR-0004: Proveedores de IA y de WhatsApp (AB-04) — malla multimodelo con DI como frontera, canal Cloud API directa y guardarraíles de Ley 21.719

- **Estado:** **Aceptado con condiciones** (fallo del dueño 2026-10-31: ratifica la malla multimodelo y deja puesta la asignación inicial de modelos — §3.1; ver §5). Condiciones restantes: **(a)** **CERRADA 2026-10-31** — confirmación explícita del canal por el dueño: **Meta Cloud API directa** (§4.1); **(b)** OK legal de P-07 (ZDR/DPA/transferencia internacional); **(c)** licitación-piloto del corpus de ADR-0003 §15 **antes** de activar la modalidad a usuarios reales, con los umbrales que fija el dueño. Todo lo demás (runtime premium, Núcleo F2.5/F2.6, ACL, solicitudes+buzón) queda **desbloqueado para implementación: ningún rol está a la espera del proveedor**. La decisión **no es irreversible**: la frontera del Documento de Intención (DI, ADR-0003 §3.4) hace que cambiar de proveedor sea una operación de runtime, no un cambio arquitectónico (§6 de este ADR).
- **Fecha:** 2026-10-30 — fallo del dueño registrado: 2026-10-31
- **Decide:** agente `arquitectura` (diseño). El fallo final es del **dueño + legal**: AB-04 (`docs/PLAN_DESARROLLO.md:64` — "Proveedor de LLM y de WhatsApp Business API; privacidad", destino "Módulo premium") y **P-07** (`docs/negocio/preguntas.md:67` — privacidad/residencia de audios, fotos, PDFs y transcripciones de terceros; abierta).
- **Fuente primaria de dominio:** **ADR-0003** (`ADR-0003-agente-multimodal-whatsapp.md`), citado con su numeración real vigente: pipeline y almacenamiento de media **§3.1**, agentes de modalidad **§3.2**, orquestador **§3.3**, DI **§3.4**, contexto de conversación **§3.5**, guardarraíles **§5**, fallos y degradación **§6**, costos y alternativas de proveedor **§7**, ACL por número **§13**, hoja de ruta sin carga automática **§14**, protocolo de evaluación ASR/OCR **§15**, ID de flete **§16**. Los protocolos y umbrales de ADR-0003 §15 **siguen siendo la única fuente de evaluación de calidad**; este ADR no los reemplaza ni duplica.
- **Fallo del dueño 2026-10-30 que este ADR respeta (ya no reabre):**
  - **D-13** (respondida 2026-10-30, `docs/negocio/preguntas.md:34`): el MVP integra **las 4 modalidades** y usa **los mejores modelos disponibles sin importar precio**; la optimización de costos es posterior. Consecuencia: elegir modelos premium **ya** es viable; el plan B con modelos ligeros queda como fase posterior (§3.2 regla 4 de este ADR).
  - **D-15** (respondida 2026-10-30, `preguntas.md:36`): "los precios de momento no nos preocupemos" — MVP **sin gate de costo**; la elección de proveedor y los costos siguen en AB-04.
  - **Fallo del dueño 2026-10-31 (este ADR lo registra y con él pasa a Aceptado con condiciones):** *"no me interesa el precio; me interesa que funcione de repo. Después vemos qué modelo usar realmente. Por ahora, dejo puesto el mejor modelo para cada tarea, orquestado por otro modelo que se conecta con el núcleo."* → (1) ratifica la malla multimodelo (alternativa C de §3) con el orquestador como núcleo de razonamiento; (2) deja puesta la **asignación inicial de modelos** (§3.1.1), que es la mejor estimada con los datos disponibles y re-comprobable con el corpus sin tocar código (regla 2 de §3.2); (3) reafirma D-13/D-15: el costo no decide; la re-optimización post-MVP es configuración + re-evaluación, no código.
  - **D-14** (`preguntas.md:35`): la aprobación se decide en el **buzón de la UI** (Confirmar/Rechazar/Modificar, ADR-0003 §14); queda abierta la subpregunta de **notificación por WhatsApp** — relevante para el diseño de plantillas (§4.2 de este ADR).
- **Relación con decisiones vigentes:** DEC-05 (`PLAN_DESARROLLO.md:43`, todo premium/manual), DEC-10 (`:48`, agente apagado por defecto, por tools), DEC-11 (`:49`, solicitud+aprobación), DEC-16 (`:54`, monolito modular), R-01 (`:723`, riesgo Alto → guardarraíles). Este ADR **no toca** el Núcleo ni introduce escrituras: completa la recomendación técnica de AB-04 que ADR-0003 §7 dejó abierta.
- **Estado del código:** no existe ninguna pieza de LLM/ASR/OCR/WhatsApp implementada (🟢 estados 🔴: D03 `capacidades-objetivo.md:92`, B06 `:103`, I01 `:109`). Este ADR no choca con código: toda su parte técnica es diseño del módulo premium.

**Nota de vigencia de la evidencia externa (obligatoria):** toda la evidencia de mercado/proveedores de este ADR fue **verificada por el orquestador el 2026-10-30 vía web** (sitios oficiales de Meta, OpenAI, Anthropic, Google y comparativas de mercado BSP) y es **no re-verificable en el repo**. Cada afirmación externa lleva la marca 🟡 y la nota **"dato externo a fecha 2026-10-30; re-validar al firmar contrato"**. Este ADR **no inventa precios de tokens ni tarifas exactas**: solo recoge las cifras referenciales de mercado entregadas por el orquestador; el precio firmado lo fija la negociación (§7 de este ADR).

---

## 0. Resumen ejecutivo

1. **Modelos: malla multimodelo por tarea, no un único LLM.** Cada agente de modalidad de ADR-0003 §3.2 elige su proveedor de forma independiente, con el protocolo §15 de ADR-0003 como único juez. Un único proveedor para todo queda hoy en desventaja: ningún modelo lidera todas las modalidades, Claude no procesa audio nativo, y la calidad con audio real de conductores (ruido de cabina) la decide el corpus, no el benchmark.
2. **Canal WhatsApp: Meta Cloud API directa** como recomendación técnica primaria (mínima cadena de terceros, control del número y del dato); **360dialog (BSP)** como alternativa si el dueño prefiere un interlocutor comercial o residencia de datos UE; **Twilio** como segunda BSP referencial. El número debe ser del dueño; el canal es gratuito en la gran mayoría de los flujos previstos (mensajes dentro de la ventana de servicio de 24 h).
3. **Privacidad: la cadena de tratamiento se minimiza por diseño.** Media descargada a storage propio (patrón DEC-12) **dentro de la ventana de 14–30 días** en que Meta la retiene; las conversaciones y el contexto viven en el ERP (ADR-0003 §3.5), **nunca en objetos de sesión/archivos del proveedor** (los endpoints con estado no están cubiertos por ZDR); contratos exigidos: no-entrenamiento escrita, ZDR u opt-out, DPA, lista de subprocesadores, residencia UE cuando exista. Los campos de Ley 21.719 (consentimiento, retención, RC delegado, transferencia internacional) quedan en manos de legal (P-07).
4. **Lo que este ADR aporta es la recomendación técnica.** Con el fallo parcial del dueño (2026-10-31) el ADR pasó a **Aceptado con condiciones** (§5): la condición del fallo del dueño está dada en lo de modelos (malla ratificada y asignación inicial puesta, §3.1.1) y pendiente en la línea de canal (§4.1); restan además legal OK de P-07 con los proveedores elegidos, y pilotaje del corpus con los umbrales de ADR-0003 §15 fijados por el dueño. Pasar a **Aceptado total** exige cerrar las tres líneas.

---

## 1. Contexto

### 1.1 Hechos verificados en el repo (🟢, esta sesión 2026-10-30)

| # | Hecho | Evidencia |
|---|---|---|
| 1 | AB-04 está abierto: "Proveedor de LLM y de WhatsApp Business API; privacidad", dueño + legal, bloquea el módulo premium | `docs/PLAN_DESARROLLO.md:64` |
| 2 | ADR-0003 deja la recomendación de proveedor como técnica por defecto, sin decidir | ADR-0003 §7 (`:239-258`), §12 (`:344-350`) |
| 3 | No hay implementación de LLM/ASR/OCR/WhatsApp en el código | 🟢 `capacidades-objetivo.md:92,103,109` |
| 4 | Los bytes de media van a object storage con prefijo por empresa y ciclo de vida (DEC-12) | ADR-0003 §3.1 regla 3 (`:92-93`); `PLAN_DESARROLLO.md:126-133` |
| 5 | La evaluación de calidad (WER / precisión por campo) es el protocolo §15 de ADR-0003; los umbrales los fija el **dueño** en el pilotaje 🔴 | ADR-0003 §15.3 (`:443-448`) |
| 6 | La aprobación de solicitudes se decide en el buzón de la UI; la notificación por WhatsApp queda abierta (D-14) | `docs/negocio/preguntas.md:35`; ADR-0003 §14 |
| 7 | P-07 y P-08 (contrato de cada tenant con sus propios clientes sobre el canal) están abiertas | `docs/negocio/preguntas.md:67` (P-07); P-08 citada en ADR-0003 §11 |
| 8 | El runtime no existe; la ACL (§13 de ADR-0003) aplica hoy como capa de servicio (RLS de `nucleo` sin políticas, RA-03) | ADR-0003 §13.5 (`:386`), §9.1 (`:285`) |

### 1.2 Evidencia externa (🟡, verificada por el orquestador el 2026-10-30 vía web — no re-verificable en repo)

**Canal WhatsApp — modelo de cobro.** Meta dejó de cobrar por conversación (deprecado desde jul-2025) y cobra **por mensaje de plantilla entregado**, con precio por categoría (marketing / utility / authentication / service). Los mensajes **no-plantilla enviados dentro de la ventana de servicio de 24 h** (que se abre con cada mensaje del usuario) son gratis; los mensajes **usuario→negocio no se cobran**. Tarifario vigente desde 01-oct-2026.
→ Implicancia para los flujos del ERP: en ADR-0003 el flujo es **el cliente/conductor escribe primero** (texto, nota de voz, foto o PDF) y el agente responde en la conversación ⇒ la mayoría de los intercambios previstos es *no-plantilla dentro de ventana 24 h = gratuito*. Los mensajes **proactivos fuera de ventana** (p. ej. notificar el resultado de una aprobación resuelta en el buzón días después, §14 de ADR-0003) salen como **utility template (pagados)**. P-08 sigue vigente para el contrato del tenant con sus propios clientes.

**Canal WhatsApp — límites de media.** Cloud API: audio `.ogg`/`opus` hasta **16 MB** (nota de voz — responde la 🟡 que ADR-0003 §3.2 fila "voz" dejó abierta: "la cifra exacta queda en el proveedor"), imagen `jpeg`/`png` hasta **5 MB**, documento PDF hasta **100 MB**. Los media viven en servidores de Meta **14–30 días** ⇒ la descarga a object storage propio es **obligatoria e inmediata** (coincide con ADR-0003 §3.1 regla 3; regla de diseño R1 de §4.3.1).

**Canal — opciones.** *Cloud API directa* (sin intermediario, sin markup, control total del número y del dato; setup referencial ~2-4 h con equipo técnico; requiere verificación de negocio de Meta y gestión propia de firmas de webhook). *BSP*: Twilio (markup referencial **≈ +US$0.005/mensaje** sobre la tarifa de Meta), 360dialog (EUR 49–99/mes por número tier-1, sin markup declarado, **datos alojados en infraestructura UE**), Gupshup (fuerte en LATAM). Ninguna BSP retiene data en Chile. Los precios son **referenciales de mercado a la fecha**; la cifra firmada la fija la negociación.

**Proveedores de IA — términos de privacidad comercial (API paga).** Todos: **no entrenan con datos de clientes por defecto** en sus términos comerciales.
- **OpenAI:** la API no entrena desde mar-2023 salvo opt-in explícito; retención ~30 días para abuso. **ZDR ("Zero Data Retention") por elegibilidad** vía equipo comercial, con *Private Safety Processing* (evalúa riesgos transversales de seguridad sin que personal humano vea el contenido). Endpoints cubiertos por ZDR (lista oficial del enterprise-privacy): completions/embeddings/moderations/audio transcription/realtime; **NO cubiertos: Files, vector stores, Assistants/Threads/Conversations, Batches** ⇒ no guardar estado de conversación ni archivos en sus objetos.
- **Anthropic:** Commercial Terms prohíben entrenar con customer content; borrado backend ≤30 días; contenido flaggeado por Trust & Safety puede retenerse hasta 2 años; **ZDR por organización** vía equipo comercial (cubre Messages/token-counting; NO elegible: Files API, Batch API, code execution, MCP). **Claude no procesa audio nativamente** ⇒ requiere transcripción previa de otro servicio (refuerza la malla de §2).
- **Google (Gemini API / Vertex):** la API pagada no entrena sin permiso; puntos de atención: prompt logging por abuso, Grounding con Search retiene queries 3 días (no desactivable), Implicit Caching 24 h, **Interactions `store=true` por defecto ⇒ setear `store=false`**; residencia por región disponible en Vertex.

**Mapa de modelos por tarea (benchmarks abr-2026, referencial).** Gemini 3 Pro: líder multimodal en audio/entendimiento de audio y vídeo, contexto largo (~1M–2M tokens); Whisper-3 (OpenAI) y Parakeet (NVIDIA): siguen ganando en **ASR puro** (transcripción); Claude Opus 4.x: líder en PDFs/producto documental largo (DocVQA), **sin audio nativo**; GPT-5.x: mejor lectura de texto denso en imágenes + voz en tiempo real. Hallazgo crítico (mar-2026): **todos los modelos caen ≥10 puntos (algunos >20) al pasar de audio limpio a audio con ruido** ⇒ los benchmarks de audio limpio **no predicen** el desempeño con notas de voz de conductores de campo; **el corpus de ADR-0003 §15 es la condición de decisión, no los benchmarks**.

---

## 2. Problema

**En una frase verificable:** *dadas las 4 modalidades de ingesta definidas en ADR-0003 y la apertura de AB-04 (`PLAN_DESARROLLO.md:64`), ¿qué combinación de (canal WhatsApp, modelos de ASR/visión/extracción/orquestador) satisface el requisito del dueño — mejores modelos en MVP (D-13), costo diferido (D-15), respuestas naturales (ADR-0003 §13.3) y evaluación permanente (§15) — con la menor cadena de terceros y las garantías de privacidad exigibles por contrato (P-07)?*

Hoy la respuesta está sin definir: ADR-0003 §7 dejó una recomendación de *forma* (SaaS, canal ≠ cerebro) pero no eligió canal ni modelos, y ninguna codificación de proveedor existe.

---

## 3. Por qué lo obvio (un único LLM) no sirve — alternativas y decisión

| Alternativa | Ventajas | Costes/riesgos | Reversible | Impacto en ADR-0003 |
|---|---|---|---|---|
| **A. Un único proveedor de IA para LLM+ASR+visión** | Un solo contrato, una factura, una negociación; menor esfuerzo de gestión | **No hay líder único por modalidad** (🟡 §1.2): el ASR puro lo lideran los especialistas de transcripción; los PDFs largos lo lidera Claude (que quedaría "ciego a la voz" como cerebro único); el audio multimodal lo lidera Gemini; la caída ≥10 pt con ruido impide decidir por ranking de benchmarks. Lock-in de datos: cada proveedor excluye endpoints distintos de su esquema ZDR ⇒ un solo proveedor deja capacidades completas sin cobertura de no-retención | Sí, detrás del DI | Choca con §3.2 (agentes de modalidad independientes ya diseñados) y con §15 (evaluación por `(proveedor, modelo, prompt)`) |
| **B. Un modelo por modalidad elegido solo por benchmarks** | Máximo puntaje "de papel" | Ignora el hallazgo de ruido: el benchmark de audio limpio no predice la nota de voz del conductor con ruido de cabina; la calidad real la fija **el corpus de §15 con los umbrales del dueño** 🔴 | Sí | Riesgo de pagar premium por capacidad que el problema real no ejercita |
| **C (recomendada). Malla multimodelo por tarea con DI como frontera** | Cada tarea toma el mejor candidato; swap por tarea sin rediseño (la frontera ya es el DI de ADR-0003 §3.4, campo `versiones`); mitigación de lock-in: ningún proveedor posee todo el pipeline; la cobertura despareja de ZDR se compensa eligiendo endpoints stateless (§4.3) | Más contratos que negociar (≤4); exige decidir por tarea, con criterio explícito y registrado | Alta por tarea | Consistente: los agentes de modalidad de §3.2 **ya** están diseñados como piezas intercambiables |

**Razón de la decisión:** lo más pequeño y reversible no es "un proveedor" ni "el mejor benchmark": es **mantener la frontera existente (DI)** y dejar que cada tarea elija su proveedor con un criterio declarado y el corpus como juez final. Se mantiene la recomendación técnica de ADR-0003 §7 ("canal ≠ cerebro"): el proveedor del canal es independiente del proveedor de la IA.

### 3.1 Tabla de la malla (tarea → candidatos → criterio → plan B)

> El **protocolo §15 de ADR-0003** es el único juez: ningún caso de uso se activa sin evaluación registrada de su modalidad con ese `(proveedor, modelo, prompt)`.

| Tarea (ADR-0003 §3.2) | Candidatos (🟡 externos, abr-2026) | Criterio de elección (medible) | Tipo de plan B |
|---|---|---|---|
| **Orquestador / NLU** (texto, fusión, JSON del DI §3.4) | GPT-5.x · Gemini 3 · Claude Opus 4.x | Razonamiento con instrucciones estrictas + generación JSON conforme al schema del DI + español natural (registro en `docs/qa/`, §15.3). El mejor **con** schema rígido gana | Swap directo a la 2ª opción; sin cambios de código (§6) |
| **ASR (nota de voz)** | **Whisper-3 (API) por defecto** · (alternativa concurrente) Gemini 3 para audio de baja complejidad · **faster-whisper self-hosted** si P-07/legal exige residencia local de la voz | **WER sobre el corpus chileno real del §15** (con ruido de cabina), por muestra y distribución + vocabulario crítico (patentes, nombres) — no benchmarks genéricos | Self-hosted (alternativa B de ADR-0003 §7, que permanece; requiere medición + coste declarado + rollback por `destino-modular.md:341-353`) |
| **Visión: fotos (POD, boletas, fotos de campo)** | GPT-5.x (texto denso en imagen) · Gemini 3 vision | Precisión por campo del §15 sobre boletas/POD reales; no se asigna por "multimodalidad general" | OCR clásico + reglas (pipeline C de ADR-0003 §7) cuando el documento es nítido de texto |
| **PDF (largo/escaneado)** | Claude Opus 4.x · Gemini 3 | Evaluación de campo sobre PDFs reales (guías de despacho, manuscritos, multipágina) | Extracción de texto nativa primero + OCR de fallback (regla del detector de modalidad, ADR-0003 §3.1; costo casi cero en PDFs con texto) |

### 3.1.1 Asignación inicial dejada puesta (fallo del dueño 2026-10-31)

> Instancia la tabla anterior con nombres concretos, por el fallo del dueño: "dejo puesto el mejor modelo para cada tarea". Modelos 🟡 dato externo (snapshot de mercado oct-2026, verificado por el orquestador, §1.2); **caducan**: al cambiar de versión de cualquier modelo, re-evaluar por el protocolo ADR-0003 §15 antes de continuar.

| Tarea | Modelo asignado | Justificación |
|---|---|---|
| **Orquestador/NLU + procesamiento de PDFs largos** | **Anthropic Claude Opus 4.7** | Invocado y agentic + líder en OCR de PDFs largos (🟡 §1.2); **un mismo contrato cubre las dos tareas** |
| **ASR (notas de voz)** | **OpenAI Whisper-3 API** | ASR puro líder (🟡 §1.2); el razonamiento va después, en el orquestador, sobre la transcripción |
| **Visión de fotos (POD/boletas/fotos de campo)** | **OpenAI GPT-5.x** | Lectura de texto denso en imagen y conteo líder (🟡 §1.2) |
| *(Plan B por tarea, no activo)* | **Gemini 3** | Audio+razonamiento en un paso si Whisper+Opus no alcanza el umbral del corpus en el piloto §15; video no importa para el ERP |

- La malla colapsa a **2 contratos activos (Anthropic + OpenAI)** para el MVP — dentro del máximo de 4 de la regla 3 de §3.2, y con menos negociación.
- **El corpus manda** (regla 2 de §3.2): esta asignación es la mejor estimada con los datos disponibles hoy; el piloto §15 con corpus real re-comprueba y cualquier tarea puede swap sin código (§6).
- **Regla del dueño aplicada:** el costo no decide (D-13/D-15); se elige por desempeño esperado y la re-optimización post-MVP es **configuración + re-evaluación, no código**.

### 3.2 Reglas de la malla

1. **El orquestador es un único modelo multimodal fuerte**; las demás tareas son especialistas. No se exige que el orquestador sea el mismo modelo que el ASR ni que el de visión.
2. **El corpus manda sobre el benchmark** (hallazgo de ruido; 🔴 sin corpus ejecutado hoy: ADR-0003 §15.4). Cualquier candidato desmentido por la evaluación §15 se reemplaza **sin retocar código** (§6).
3. **Máximo 4 contratos de IA**, uno por tarea — no hay "segundos motores" operativos: el plan B entra en producción solo si se activa así la tarea (§15.3) o por degradación (ADR-0003 §6).
4. **La optimización de costos es posterior al MVP** (D-13/D-15): el plan B con modelos ligeros (Flash/Haiku) se reserva para esa fase; la frontera del DI hace que sea un cambio de configuración + re-evaluación, no de diseño.

---

## 4. Canal WhatsApp y privacidad

### 4.1 Canal: alternativas y recomendación

| Alternativa | Ventajas | Costes/riesgos | Residencia de la data / cadena de terceros | Recomendación |
|---|---|---|---|---|
| **Meta Cloud API directa** | Sin markup y sin intermediario; control del número, del webhook firmado y de la data; la firma del webhook y la desduplicación por `wa_message_id` son obligaciones del runtime ya diseñadas (ADR-0003 §3.1) | Exige equipo técnico (setup referencial ~2-4 h, 🟡) + verificación de negocio de Meta + gestión propia de firmas; el equipo asume la contingencia de un cambio de conducta de Meta | Data va directo a Meta; **ningún encargado de transmisión adicional** | **Primaria** |
| **360dialog (BSP)** | BSP especializada; sin markup declarado; **datos alojados en infraestructura UE** (🟡) ⇒ la transmisión internacional queda acotada y regulable, postura favorable bajo Ley 21.719; interlocutor comercial único | Costo mensual por número (referencial EUR 49–99/mes tier-1, 🟡); un encargado de tratamiento **más** en la cadena, junto a Meta | Data vía 360dialog (UE) → Meta | **Alternativa 1** si el dueño valora interlocutor / infra UE |
| **Twilio (BSP)** | Familiar para desarrolladores; API madura | Markup por mensaje (referencial ≈ +US$0.005/mensaje sobre Meta, 🟡) que en volumen se convierte en sobrecosto estructural | Data vía Twilio (EE. UU.) → Meta ⇒ cadena **más larga** de encargados, desfavorable a Ley 21.719 | Alternativa 2; sus ventajas la primaria las cubre con menos cadena |

**Criterios que el dueño debe decidir (el fallo 2026-10-31 los fijó en lo de modelos y dejó el canal por defecto — ver registro al final de esta subsección):**
1. **Control del número:** ¿el número queda en la cuenta del propio dueño (Meta Cloud API) o acepta un interlocutor que lo administre? Con Cloud API directa el número es **del dueño, sin ninguna app instalada ni acceso del BSP**, y la verificación de Meta se hace por **SMS/llamada** al propietario del número (🟡).
2. **Cadena de terceros (Ley 21.719):** Cloud API directa tiene el **mínimo número de encargados en la cadena** (⇒ mínimo registro de encargados de tratamiento y de DPAs en los que legal debe rendir cuentas, §4.3).
3. **Soporte operativo del webhook:** con Meta directa, firma, retry y desduplicación son 100 % responsabilidad del runtime (ADR-0003 §3.1/§5); con BSP el interlocutor asiste.
4. **Contratos en paralelo:** como de todas maneras hay que negociar contratos de IA (§4.3.3), un 4º contrato con un BSP solo se justifica si el dueño valora la interlocución (o la residencia UE de 360dialog) por encima del costo mensual y de la cadena diferida.

**Registro del fallo del dueño 2026-10-31 sobre el canal (⇐ pregunta 1 de §10):** el dueño **no respondió explícitamente**. Se registra: **Meta Cloud API directa aplica por defecto como recomendación técnica** — coincide con la preferencia del dueño en los otros dos criterios (control del número + sin encargados de transmisión extra) — ║🟡 pendiente de confirmación explícita del dueño║. El estado del ADR es **Aceptado con condiciones**, no Aceptado total, mientras falte esa línea (§5, condición a).

### 4.2 Plan mínimo de plantillas WhatsApp (mapa de costo del canal)

> Principio derivado del modelo de cobro 🟡 (§1.2): **el canal es gratuito para casi todo el tráfico previsto** (conversación iniciada por el contacto, respondida dentro de la ventana de 24 h). El costo aparece solo en mensajería **proactiva fuera de ventana**, y se minimiza a 3 plantillas:

| Plantilla | Categoría | Uso | Cobro según tarifario 01-oct-2026 (🟡) |
|---|---|---|---|
| OTP de enrolamiento | **authentication** | Registro de contactos con OTP (`PLAN_DESARROLLO.md:122`; ADR-0003 §3.1) | Cobrado por mensaje entregado; authentication es la categoría de plantilla más barata de las tres que se usan (🟡) |
| Resultado de aprobación | **utility** | **Notificar** (no decidir — D-14) que la solicitud del buzón fue Confirmada/Rechazada/Modificada, cuando la notificación llega fuera de ventana | Cobrado por mensaje entregado |
| Aviso "queda pendiente" | **utility** | Cuando el agente deriva una solicitud al buzón y la conversación se cierra antes de la respuesta | Cobrado por mensaje entregado |

- Toda otra comunicación va **sin plantilla dentro de la ventana de 24 h** ⇒ sin cobro de mensaje (🟡).
- La **subpregunta abierta de D-14** ("¿se notifica o se decide la aprobación por WhatsApp?", `preguntas.md:35`) afecta esta tabla: si se notifica por WhatsApp, es plantilla utility; si no se notifica, la fila desaparece y no hay costo adicional.
- **P-08** (contrato del tenant con sus clientes sobre el canal) sigue vigente: notificar a un cliente final puede exigir consentimiento adicional que legal declare por tenant (ADR-0003 §11).

### 4.3 Privacidad / Ley 21.719 — reglas de diseño que no dependen de legal + lo entregado a legal

**Marco:** la **Ley 21.719** (nueva ley chilena de protección de datos personales) tiene entrada en vigencia fijada en **01-dic-2026** (🟡 dato externo verificado por el orquestador; existe un **proyecto de postergación en trámite en el Senado a oct-2026**, 🟡). **No se espera la postergación** para diseñar: el diseño incorpora hoy lo que la ley exigirá; si se posterga, el diseño ya está; si no, no hay deuda de última hora. Las **etiquetas jurídicas exactas** (encargado de tratamiento / **tercero mandatario**, artículo de la ley, formato del DPA) las fija **legal vía P-07** — este ADR marca la frontera técnica y no decide derecho; la correspondencia del concepto con "tercero mandatario" es 🟡 y queda **a confirmar con el asesor legal**.

#### 4.3.1 Reglas de diseño que se imponen a la implementación (independientes de legal)

| # | Regla | Fundamento | Fuente |
|---|---|---|---|
| **R1** | **Descarga de media a storage propio (patrón DEC-12) inmediatamente al recibir el mensaje**, dentro de la ventana de 14–30 días (🟡) en que Meta la retiene en sus servidores | El ERP debe ser el custodio real del archivo con datos personales de terceros; la copia en Meta pasa residual e incontrolable si no se descarga a tiempo | ADR-0003 §3.1 regla 3 (`:92-93`); metadatos del runtime en el módulo premium, no en el Núcleo |
| **R2** | **Las conversaciones, el contexto de conversación (ADR-0003 §3.5) y el expediente del mensaje viven en el ERP**, no en objetos de estado del proveedor de IA | Los endpoints de estado del proveedor (Files / vector stores / Assistants / Threads / Conversations / `store=true`, 🟡 §1.2) **no están cubiertos por sus esquemas de ZDR** ⇒ mantener el estado en el ERP es condición para que el contrato de no-retención aplicable cubra de verdad el flujo | ADR-0003 §3.5 (`:168-181`): el contexto ya se persiste y comprime del lado ERP |
| **R3** | **Los endpoints de IA elegidos son stateless** (completions / messages / generations) — **prohibido** usar Files / vector stores / Assistants / Batch / code execution de los proveedores para datos del ERP | Es la línea de corte del swap (§6): solo entra al proveedor el contenido del mensaje en tránsito, nunca el histórico ni el storage | ADR-0003 §5 fila "fugas entre sesiones" (`:219`) |
| **R4** | **Parámetros de retención del proveedor al mínimo exigible**: `store=false` en Google; sin opt-in de entrenamiento en OpenAI; sin Files/Batch en Anthropic; desactivar logging de abuso donde el plan lo permita | Reduce el tiempo de vida del dato en el proveedor y hace auditable el compromiso más allá del marketing | §1.2 |
| **R5** | **El prompt del sistema declara el contenido del mensaje (texto, transcripción, OCR) como dato delimitado, no como instrucciones** | Refuerza P-07 (el tercero no decide sobre el dato) y la regla anti-inyección ya diseñada | ADR-0003 §5 (inyección adversarial) `:214-215` |
| **R6** | **El `wa_message_id` del webhook es la clave de idempotencia de la ingesta**; ningún ID interno del proveedor es fuente de verdad | Permite cambiar de canal (Cloud API ↔ BSP) sin duplicar mensajes ni depender del identificador interno del proveedor | ADR-0003 §3.1 regla 2 + §9.2 fila idempotencia |

#### 4.3.2 Lo que queda en manos de legal (P-07) — 🔴 este ADR no lo decide

| Campo abierto | Qué debe declarar legal | Por qué el ADR no lo decide |
|---|---|---|
| **Consentimiento informado** de los terceros (conductor, cliente final) cuyo audio/foto/PDF pasa por Meta y por los proveedores de IA | Quién capta el consentimiento (TRANSTEI como plataforma vs. el tenant), con qué texto, en qué momento | Es derecho, no diseño; P-07 `preguntas.md:67` |
| **Retención mínima** de transcripciones, media y expedientes del mensaje; qué entra al ciclo de vida DEC-12 y qué se borra primero | Período por clase de dato (incluidos gastos/insumos de sueldos de D-10 y montos visibles al cliente final) | Requiere decisión jurídica (plazos, salvedades documentales) — no es diseño |
| **RC delegado** (representante/designado ante la autoridad de datos, a formalizar por la empresa) y qué acceso tiene al log de auditoría del agente (§13.4 de ADR-0003) | Asignar el RC y definir su acceso a la auditoría de consultas | Depende de la estructura jurídica del dueño |
| **Transferencia internacional** (Meta aloja donde tenga servidor; OpenAI/Anthropic/Google no tienen región Chile; la única residencia UE declarada en la cadena es 360dialog, 🟡) y el **contrato de encargado de tratamiento** con cada proveedor de la cadena | Lista definitiva de encargados/terceros mandatarios y DPAs firmados | Depende del fallo de canal + proveedor (fallo del dueño en AB-04) |

#### 4.3.3 Contratos exigidos por proveedor de IA (base de negociación del dueño con legal/P-07)

| Proveedor | Qué hace con input/output (🟡 términos comerciales API, 2026-10-30) | Retención declarada (🟡) | Contrato a exigir (mínimo) | Nota de diseño |
|---|---|---|---|---|
| **OpenAI** | No entrena con data de API por defecto (desde mar-2023); el opt-in explícito **no se acepta**; safety processing sin lectura humana del contenido (Private Safety Processing) | ~30 días para abuso | **ZDR por elegibilidad** vía equipo comercial + DPA + lista de subprocesadores + cláusula escrita de no-entrenamiento | ZDR cubre la lista oficial de endpoints (incl. transcripción de audio); **prohibido** guardar data en Files/vector stores/Assistants/Conversations/Batches (R3) |
| **Anthropic** | No entrena con customer content; Trust & Safety puede retener contenido flaggeado hasta 2 años; borrado backend ≤30 días | Borrado ≤30 días + flags T&S hasta 2 años (🟡) | **ZDR por organización** vía equipo comercial + DPA + no-elegibilidad declarada de Files API/Batch/MCP | Claude **sin audio nativo**: si se le asigna orquestador o PDF, la voz siempre entra ya transcrita (§3.1) |
| **Google (Gemini API / Vertex)** | La API pagada no entrena sin permiso; prompt logging por abuso; Grounding retiene 3 días (Search) / 30 días (Maps); **Interactions `store=true` por defecto** | 3–30 días según feature (🟡) | Contrato comercial + **residencia por región (Vertex UE)** + DPA + **`store=false` en producción** + desactivar grounding a fuentes externas donde el flujo no la use | El agente del ERP no necesita fuentes externas: el grounding queda fuera del flujo |

**Fallo tácito del dueño (2026-10-31) sobre el momento de exigirlos (⇐ pregunta 3 de §10):** con el costo fuera de la ecuación (D-13/D-15) y la Ley 21.719 con vigencia fijada al 01-dic-2026 (🟡, §4.3), se registra: **exigir ZDR + DPA + cláusula de no-entrenamiento desde el primer contrato** — no en el pase a producción, y antes de cualquier uso con datos reales (incluido el corpus del piloto §15). Ojo: la **elegibilidad real de ZDR por endpoint se verifica en la firma** — Files API / Batch / code-execution **NO elegibles** en Anthropic; los endpoints con estado (Files, vector stores, Assistants/Threads/Conversations, Batch) **NO cubiertos** en OpenAI — ya reflejado en R2/R3 (§4.3.1) y en las filas de esta tabla.

---

## 5. Condiciones del Aceptado con condiciones (estado a 2026-10-31)

> **Actualización 2026-10-31 (fallo del dueño):** el ADR pasa a **Aceptado con condiciones**. La condición 1 está dada **parcialmente**; quedan (a) la línea de canal y (b)/(c) como antes. Estado por condición:

1. **Fallo del dueño (canal + modelos) — ✅ dado, parcialmente (2026-10-31):** ratificada la malla multimodelo (alternativa C de §3) y dejada puesta la asignación inicial de modelos (§3.1.1). **Canal: sin respuesta explícita** — aplica por defecto Meta Cloud API directa (§4.1), ║🟡 pendiente de confirmación explícita del dueño║.
2. **Legal OK de P-07 (`preguntas.md:67`) con los proveedores elegidos: 🔴 abierta** — condición (b). Consentimiento, retención, RC delegado, transferencia internacional y DPAs firmados con la cadena del §4.3.3. Refuerzo del fallo tácito (§4.3.3): **ZDR/DPA/no-entrenamiento se exigen desde el primer contrato**, antes de cualquier uso con datos reales, incluido el propio piloto.
3. **Pilotaje del corpus según ADR-0003 §15: 🔴 no ejecutado** — condición (c). Corpus etiquetado (voz chilena real, POD/boletas/PDF reales), **WER y precisión por campo medidos con los umbrales que fija el dueño** (§15.3, 🔴), frente a las tareas de la malla asignada (§3.1.1); resultados registrados en `docs/qa/`. **Es requisito previo a la activación de la modalidad a usuarios reales.**

**Mientras tanto, NADA de lo demás depende del proveedor:** la construcción del Núcleo (F2.5/F2.6: tool registry, gate, contactos+OTP, solicitudes+buzón — `PLAN_DESARROLLO.md:428-429`) y del runtime premium (ingesta, storage de media con regla R1, ACL de §13 de ADR-0003, hoja de ruta de §14, buzón, auditoría) **puede avanzar sin proveedor elegido** — coincide con ADR-0003 §15.4 ("no bloquea la construcción del Núcleo ni la implementación del pipeline, sí su activación"). Con el fallo de 2026-10-31, todo eso queda **desbloqueado para implementación: ningún rol está a la espera del proveedor**. Lo único que depende de las tres condiciones restantes es la **activación de casos de uso interpretativos** (§15.3 de ADR-0003) y la inversión concreta con los contratos del §4.3.3.

---

## 6. Rollback del proveedor (reglas operativas, no arquitectónicas)

1. **Cambio de modelo por tarea = configuración + re-evaluación, no código.** La frontera es el DI de ADR-0003 §3.4 (el campo `versiones`, `:155`, lo posibilita); las secciones del DI (`transcripcion`, `documento`, `interpretacion`) no contienen el nombre del proveedor como lógica. Cambiar un modelo actualiza `versiones` y exige re-correr el protocolo §15 (`:447`).
2. **Cambio de canal WhatsApp:** webhook, firma, desduplicación por `wa_message_id` (R6) y descarga de media son obligaciones del runtime idénticas en Meta directa y en BSP ⇒ cambiar de canal toca configuración y credenciales, no el pipeline ni el Núcleo.
3. **Advertencia estructural (es el propósito de R3):** los endpoints con estado de los proveedores (Files / vector stores / Assistants / Conversations / Threads, `store=true`, Batch) **no deben usarse precisamente para que el rollback no dependa del proveedor**. Si nadie guardó estado en el proveedor, cambiar de proveedor no deja datos retenidos bajo una política de retención ajena ni importa/exporta nada.
4. **El swap se aplica por caso de uso activado:** cada caso de uso se activó tras su evaluación §15 ⇒ se puede cambiar de proveedor por tarea sin tocar casos ya activados, cuyo `(proveedor, modelo)` queda acreditado en su registro.
5. **Si legal (P-07) exige residencia local de la voz:** entra la alternativa B de ADR-0003 §7 (faster-whisper self-hosted); en la malla (§3.1), el ASR ya tiene plan B self-hosted designado — el swap apunta a un sitio definido, no requiere nuevo diseño.

---

## 7. Registro de lo no verificable y cifras referenciales

| Dato | Estado | Nota |
|---|---|---|
| Precio exacto por plantilla entregada (Meta, 01-oct-2026) | 🟡 externo, referencial | La cifra firmada la fija la negociación; el diseño no depende del monto exacto, sino del **patrón de cobro** (plantilla fuera de ventana) |
| Markup BSP Twilio / precio mensual 360dialog / Gupshup | 🟡 externo, referencial | Referencia de mercado; no cifra contractual |
| Setup Cloud API directa ~2-4 h | 🟡 externo, referencial | Solo dimensiona la complejidad con equipo técnico |
| Residencia UE de 360dialog; residencia por región de Vertex | 🟡 externo | Confirmar en el DPA firmado, no en el material comercial del proveedor |
| Retención de media de Meta (14–30 días) y límites (16 MB audio / 5 MB imagen / 100 MB PDF) | 🟡 externo | Confirmar con la doc del proveedor al firmar; la desduplicación y fiabilidad del `message_id` por proveedor se confirma junto al webhook (ADR-0003 §3.1 regla 2, 🟡) |
| Precios por token de los modelos | 🔴 **este ADR no los mide ni los cita** | El costo queda diferido por el dueño (D-13/D-15, `preguntas.md:34,36`); restan para la fase de optimización |
| WER del español chileno con ruido de cabina, por candidato | 🔴 | Exige el corpus de ADR-0003 §15; es la condición #3 del §5 |
| Vigencia efectiva de Ley 21.719 (01-dic-2026 vs. proyecto de postergación en Senado) | 🟡 externo | Legal confirma al firmar; el diseño no cambia en ninguno de los dos escenarios |
| Correspondencia exacta "encargado/tercero mandatario" con los artículos de Ley 21.719 | 🔴 | Es materia legal (P-07); este ADR no cita artículos |

---

## 8. Consecuencias y deuda que genera este ADR

**Positivas**
- AB-04 pasa de "sin recomendación" a "recomendación técnica completa con tabla de contratos exigibles"; el dueño puede decidir canal+modelos leyendo este documento, sin nueva investigación.
- La cadena de tratamiento queda explícita y minimizada **antes** de firmar cualquier DPA — es la forma más barata de aproximar el cumplimiento de Ley 21.719.
- La reversibilidad no se promete: ya existe por diseño (DI de ADR-0003 §3.4 + protocolo §15).

**Deuda que genera o hereda:**

| Deuda | Evidencia | Se paga cuando | Esfuerzo |
|---|---|---|---|
| Corpus etiquetado y pilotaje no ejecutados (ningún WER medido) | ADR-0003 §15.4 (`:452`) | Pilotaje con el dueño; es la condición #3 del §5 de este ADR | M |
| Contratos ZDR/DPA sin negociar | §4.3.3 | **Desde el primer contrato** (fallo tácito del dueño 2026-10-31); la negociación incorpora ZDR+DPA+no-entrenamiento antes de cualquier uso con datos reales, incluido el corpus del piloto | M |
| Subpregunta de notificación por WhatsApp (D-14) afecta la tabla de plantillas de §4.2 | `preguntas.md:35` | Cuando la cierre el dueño; si no se notifica, la tabla queda válida igual (una fila menos) | S |
| P-08 sin respuesta (contrato de cada tenant con el canal) | ADR-0003 §11 | Antes de notificar a clientes finales de un tenant | S |
| Prueba real de swap de proveedor en staging (que el rollback sea demostrado, no solo diseñado) | §6 de este ADR | Primera fase de staging del runtime premium | S |
| ¿Qué se envía al proveedor: solo el contenido del mensaje o también el contexto de conversación (§3.5)? — decisión de integración que afecta la exposición del dato al proveedor | §4.3.1 R2 | Fase de implementación del runtime | S |

---

## 9. Relación con documentos vigentes

| Documento | Relación |
|---|---|
| ADR-0003 §7 | Este ADR es la recomendación técnica que §7 dejó "sujeta a ratificación en AB-04"; mantiene el criterio "canal ≠ cerebro" que este ADR desarrolla |
| ADR-0003 §15 | El protocolo de evaluación **sigue vigente sin modificación**; este ADR solo completa la lista de candidatos y su criterio; no inventa umbrales ni toca el protocolo |
| ADR-0003 §3.1 / §3.5 | R1 y R2 refuerzan el diseño sin modificarlo: la descarga de media ya estaba; "no usar objetos de estado del proveedor" es la consecuencia operacional del §3.5 |
| ADR-0003 §3.4 / §6 | El rollback de proveedor (§6 de este ADR) es posible porque el DI es el contrato; prohibir endpoints con estado (R3) es garantía transversal |
| `docs/PLAN_DESARROLLO.md:64` | AB-04, el objeto de este ADR (proveedor LLM + WhatsApp Business API + privacidad), dueño + legal |
| `docs/negocio/preguntas.md` (P-07/P-08, D-13/D-14/D-15) | Con el fallo parcial del dueño (2026-10-31) este ADR es **Aceptado con condiciones** y sigue condicionado a: confirmación explícita del canal, P-07 abierta y pilotaje §15 pendiente; respeta D-13 (modelos premium ya) y D-15 (costo diferido), y registra su fallo 2026-10-31 (malla ratificada, modelos puestos). Este ADR **no escribe** en esa carpeta |
| `agente-whatsapp-roles.md` (referencia de negocio, transcripciones D-08…D-16) | No es fuente de diseño técnico; el ADR respeta lo decidido ahí (matriz rol→intent, fallo 2026-10-30) sin duplicarla |
| DEC-05 (`:43`), DEC-10 (`:48`), DEC-11 (`:49`), DEC-16 (`:54`) | No cambia nada: módulo premium apagado por defecto; ninguna escritura del agente al Núcleo; monolito modular |
| R-01 (`:723`, riesgo Alto del agente) | La cadena de proveedores **amplía** la superficie expuesta (Meta + proveedores de IA); los guardarraíles de ADR-0003 §5 la cubren; riesgo Alto ⇒ revisión independiente antes de activar |

---

## 10. Preguntas concretas para el fallo del dueño

> **Registro de respuestas (fallo del dueño, 2026-10-31).** Respondidas: **2, 3 y 5** — y la **1 parcialmente** (por defecto, pendiente confirmación explícita del dueño). Queda **abierta la 4** para `docs/negocio/preguntas.md` (la está cerrando negocio-finanzas con la especificación del dueño; este ADR no escribe en esa carpeta).

1. **Canal:** ¿Cloud API directa (recomendación primaria de este ADR) o BSP 360dialog (alternativa por residencia UE e interlocutor)? Si BSP: ¿quién registra y mantiene la propiedad del número — el número no puede quedar del BSP, y la verificación de Meta por SMS/llamada es al dueño?
   **→ Parcialmente respondida (2026-10-31):** el dueño **no respondió explícitamente**. Registra **Meta Cloud API directa por defecto** como recomendación técnica (coincide con su preferencia: control del número + sin encargados extra), ║🟡 pendiente de confirmación explícita║ — §4.1, condición (a) de §5.
2. **Modelos:** ¿ratificar la malla de §3.1 (candidatos por tarea) o dejarla abierta hasta el piloto §15? Recomendación técnica: **ratificar los nombres ahora** y condicionar la **activación** al pilotaje §15 — es la única forma de cumplir a la vez "los mejores modelos" (D-13) y "calidad chilena real" (protocolo §15).
   **→ ✅ Respondida (2026-10-31):** el dueño ratificó la malla (alternativa C de §3) y dejó puesta la asignación inicial de modelos (§3.1.1); la activación sigue condicionada al piloto §15.
3. **ZDR/DPA:** ¿se exigen los contratos ZDR (OpenAI/Anthropic vía equipos comerciales) y el DPA de Google **antes** del pilotaje (que usa datos reales de terceros: la recomendación es exigirlos antes), o quedan dentro de la negociación posterior al MVP?
   **→ ✅ Respondida (fallo tácito, 2026-10-31):** se exigen **desde el primer contrato** (ZDR + DPA + no-entrenamiento), antes de cualquier uso con datos reales — con la Ley 21.719 inminente (vigencia fijada 01-dic-2026, 🟡) y el costo fuera de la ecuación. La elegibilidad real de ZDR por endpoint se verifica en la firma (§4.3.3).
4. **Notificación por WhatsApp (subpregunta D-14):** si el resultado de una aprobación se notifica por WhatsApp, la plantilla utility se asume como costo del canal — ¿se notifica desde el MVP o se difiere a la fase de optimización?
   **→ 🔴 Sigue abierta** para `docs/negocio/preguntas.md` (negocio-finanzas la cierra con la especificación del dueño). La tabla de plantillas de §4.2 queda válida en cualquiera de los dos escenarios (con o sin esa fila). No duplica aquí la respuesta.
5. **Plan B ASR self-hosted:** si legal considera inaceptable que la voz salga fuera de Chile/UE (OpenAI/Anthropic/Google no tienen región local), ¿exige ya el plan self-hosted o queda solo como rollback? (ADR-0003 §7 y fila ASR de §3.1 de este ADR).
   **→ ✅ Respondida (2026-10-31):** queda condicionada a **P-07/legal**, sin rebaja — con el costo fuera de la ecuación no hay presión por self-hosted por precio; solo por **propiedad de la data** (residencia de la voz). Se mantiene como plan B designado en §3.1 (fila ASR) y §6, regla 5.
