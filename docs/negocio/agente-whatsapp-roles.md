# Mapa rol → intención → componente — Agente WhatsApp multimodal

> **Pregunta que responde:** ¿qué pueden pedir o hacer por WhatsApp los roles
> enrolados (cliente, conductor, administración), qué componente del Núcleo responde
> cada intención y qué falta para implementarla?
> **Dueño:** `negocio-finanzas` · **Verificado:** 2026-10-30 (añade las respuestas
> del dueño de 2026-10-30 en §1; el bloque 2026-10-29 se conserva) · **Método:** decisión del
> dueño transcrita como fuente (no editada en sustancia) + lectura de ADR-0003,
> `docs/PLAN_DESARROLLO.md`, catálogo de reglas y auditoría F0. Sin base arriba y sin
> runtime: ningún comportamiento del agente está ejecutado; todo lo del agente es diseño.
> **Caduca si:** cambia el mapa rol→capacidad del dueño, se responden las `D-NN`/`P-NN`
> citadas, o se implementa F2.5 / el módulo premium.
> **Re-verificar con:** `rg -n "AG-|CL-|CO-|AD-" docs/negocio/agente-whatsapp-roles.md`
> y contrastar con `docs/negocio/preguntas.md` y `docs/arquitectura/adr/ADR-0003-agente-multimodal-whatsapp.md`.

---

## 1. Fuente primaria — especificación del dueño (2026-10-29 y 2026-10-30)

**Dato fiel.** Respuesta del dueño a la pregunta de enrolamiento (ADR-0003 §11, fila
D-13). Transcrita tal cual; este documento la analiza, no la corrige.

> **Se enrolan por WhatsApp: clientes, conductores y administración.**
>
> **CLIENTE** (cliente final de TRANSTEI):
> - Todo tipo de información sobre SUS fletes: el sistema debe reconocer cuáles
>   fletes son suyos y cuáles no (aislamiento por cliente).
> - Monto de deuda.
> - Fletes pendientes de facturar (montos, IDs, lo que pida).
> - Qué camión está disponible (dónde y cuál).
> - Agendar un flete: el agente pregunta ¿Qué carga? ¿Desde dónde? ¿Hasta dónde?
>   ¿Qué tipo de camión necesita?; luego lanza alerta al UI y queda pendiente de
>   aprobación con desglose (tal cliente pidió tal flete, a tal monto). Si se
>   aprueba, el agente notifica al cliente qué camión, qué rampla y qué conductor van.
> - Enviar documentación (PDF): al recibirla, el agente pregunta automáticamente a
>   qué fletes corresponden, envía desglose de fletes pendientes de OC o pendientes
>   de facturar, el cliente responde cuáles son, el agente genera alerta al UI y
>   queda pendiente. Si se aprueba/recepciona, el agente avisa al cliente y se
>   actualiza la data del sistema.
>
> **CONDUCTOR**:
> - Llenar hojas de ruta por WhatsApp. El sistema lo identifica por el número
>   (triangula conductor, camión, rampla).
> - Si hay más de 1 flete pendiente para él: mini cuestionario en WhatsApp
>   (cliente + rutas) para seleccionar el flete; si dice "ninguno de esos", genera
>   alerta y le avisa que se comunique con administración.
> - Una vez triangulado el flete (cliente, camión, etc.), le pide la data de la
>   hoja de ruta: da igual el orden en que la entrega; el conductor puede enviar
>   6-7 fotos y el sistema debe reconocer a qué corresponde cada una e ir llenando
>   un JSON estricto. Si falta información, el agente lo detecta e informa qué
>   falta. Si no la entrega, genera alerta y entrega el desglose "a medias" para
>   que administración complete.
> - Si entrega todo: el sistema ingresa la información automáticamente y actualiza
>   los componentes (gastos, sueldos, ganancias, finanzas — todo lo que toque esas
>   variables), y notifica al admin: "X conductor realizó su hoja de ruta,
>   efectivamente guardada. ¿Deseas revisarla?" (el admin puede abrirla y
>   modificarla manualmente).
> - El sistema avisa al conductor "Hoja de ruta de X flete" con ID por cliente
>   (ej: Soquimich → SQM-001) y desglose de la data ingresada/reconocida, y
>   consulta "¿La información es correcta?". Si dice no: el agente pregunta qué
>   parte(s) están mal, se re-ingresa por texto, reacomoda al JSON, vuelve a
>   consultar. Si vuelve a fallar: el conductor puede reintentar o declarar
>   entrega presencial, y el sistema notifica a los roles correspondientes.
>
> **ADMINISTRADOR/DUEÑO**:
> - Acceso completo. Puede preguntar lo que sea, incluido lo no precomputado:
>   "¿Qué fletes hay planificados para hoy?", "¿Qué clientes solicitaron fletes?",
>   "¿Cómo va la facturación de este mes?", "¿Qué clientes están pendientes de
>   pago?", "¿Qué pasó con X camión?", "¿Se hizo la mantención de X camión?",
>   "¿Cuánto gastamos en aceite?" — incluso preguntas nuevas que no existen en
>   KPIs predefinidos: el agente debe construir la respuesta consultando la DB
>   (un "gerente digital").
> - "¿Qué fletes de este mes lleva X cliente?" → desglose completo. "¿Mándame la
>   factura de Y flete y qué otra documentación hay (OC, nota de crédito)?" →
>   respuesta + envío del documento si lo pide.
> - Si dice "algo anda mal con este flete, no me calza X": el agente genera alerta
>   en el buzón con desglose; al pincharla, el sistema redirige a los roles con
>   permiso al componente del núcleo correspondiente para revisar y modificar.

### Respuestas del dueño — 2026-10-30 (D-09…D-16, transcripción fiel)

**Dato fiel.** Respuestas del dueño registradas el 2026-10-30 por la sesión
orquestadora del agente; transcritas tal cual lo reportado (no corregidas en
sustancia). Complementan el bloque 2026-10-29 anterior, que no se reemplaza.
Estos datos cierran **D-09…D-16** (D-12 y D-14 parciales) en
`docs/negocio/preguntas.md`.

> - **D-09 (gerente digital):** Responsable. El dueño quiere un agente realmente
>   inteligente, no respuestas preestablecidas; que comunique lo que sea y que, al
>   topar con un límite (ej: cliente pregunta por ganancias de la empresa, sueldos
>   de conductores, u otros clientes), responda naturalmente tipo "No estoy
>   autorizado a darte ese tipo de información" — límites reales pero respuesta
>   natural, no guionada. El gerente digital SOLO lo opera administrador o dueño.
>   El dueño registra desde la plataforma qué números telefónicos quedan
>   reconocidos como administrador, y puede generar limitaciones por número:
>   pinchando un botón desactiva el acceso de ese número a la data asociada a tal
>   módulo y sus variables. Los ÚNICOS roles predefinidos son clientes y
>   conductores (operan por los módulos de clientes y conductores); los números se
>   registran dentro de esos módulos asociando RUT de la empresa / nombre de la
>   empresa / teléfono / nombre del cliente, y solo tienen acceso a lo vinculado a
>   eso (NO acceso a métricas de ganancias, costos de flete, ni números de
>   camiones). El dueño pide auditoría de cada consulta. ("Hay que ingeniársela" =
>   el mecanismo técnico lo resuelve arquitectura, con estos requerimientos.)
> - **D-10 (hoja de ruta):** Responsable. NO se actualiza todo automáticamente. Se
>   genera una SOLICITUD que debe ser aprobada por un rol correspondiente (el dueño
>   mencionó "secretario" como ejemplo del aprobador). La solicitud muestra: tipo
>   de solicitud, qué se solicita, desglose de la información. Botones: **Confirmar**
>   (carga automática y se confirman los cambios), **Rechazar** (log, no se
>   efectúan cambios, el estado se mantiene como estaba), **Modificar** (abre la
>   plantilla correspondiente donde puede modificar manualmente cada valor; al
>   confirmar, se carga automáticamente y se actualiza el sistema). El núcleo del
>   dueño: "Tendremos que construir la hoja de ruta" — se construye el objeto.
> - **D-11 (disponibilidad de flota):** Responsable. No exponer la cantidad exacta
>   de camiones. Si el cliente "necesita camiones", el sistema le pregunta:
>   ¿cuántos necesita? ¿qué rampla? ¿qué desea cargar? y con eso se gestionan los
>   fletes para luego generar la solicitud que se aprueba en el sistema.
> - **D-12 (identidad por teléfono):** Parcial. El dueño describe el registro de
>   números por módulo (RUT empresa / nombre / teléfono / cliente) pero NO
>   respondió política de cambio de teléfono / compartición / OTP / revocación.
>   Queda ABIERTA la parte de política OTP / re-enrolamiento / revocación, con la
>   nueva información registrada.
> - **D-13 (fases por modalidad):** Responsable — el dueño pide tener TODO esto
>   integrado en el MVP, usar los mejores modelos disponibles sin importar precio
>   para presentar el proyecto, y luego optimizar/reducir costos.
> - **D-14 (aprobación por WhatsApp):** Responsable Parcial — el dueño describe la
>   aprobación en UI (buzón con 3 botones) y no menciona aprobación por WhatsApp;
>   cierra con la descripción de la aprobación en UI y deja abierta la subpregunta
>   de notificación.
> - **D-15 (límites de costo):** Responsable — "los precios de momento no nos
>   preocupemos": fase MVP sin gate de costo; se revisará después de la
>   presentación.
> - **D-16 (ID por cliente):** Responsable — regla formal en el sistema, orden
>   creciente; el dueño prefiere **5 dígitos** (SQM-00001, SQM-00002…). Regla
>   **R-04**, **numerada** en `catalogo-reglas.md:117` (2026-10-30); el texto de §5
>   de este documento queda como nota histórica del borrador (numeración verificada
>   2026-10-30: el catálogo tenía R-01…R-03 → siguiente ID libre **R-04**).
> - **ASR/OCR:** el dueño quiere ENFRENTAR el problema de calidad y resolverlo de
>   manera permanente (no acepta "ya lo vemos después"). Requerimiento del MVP con
>   **evaluación piloto obligatoria** (las subpreguntas de corpus se tratan en la
>   ADR — dueño `arquitectura`).
> - **Nota AB-02:** al describir D-10 el dueño menciona **"secretario"** como rol
>   aprobador — nueva evidencia de la intención del dueño (2026-10-30), anotada
>   también en `docs/negocio/preguntas.md`; NO cierra AB-02 (`PLAN_DESARROLLO.md:62`).

**Efectos de este bloque en la matriz §3:** cambian los estados de CL-04 (D-11),
CO-01 (D-12 parcial), CO-03/CO-04 (D-10), CO-05 (D-16), AD-01 (D-15), AD-02 (D-09),
AD-04 (D-14 parcial) y el refinamiento de AG-01. La acción de CO-03/CO-04 deja de
ser candidata a **EA?** y es **S+A** (solicitud con Confirmar / Rechazar /
Modificar). La auditoría de cada consulta (D-09) abre **D-17** en
`docs/negocio/preguntas.md`.

---

## 2. Marco vigente que acota este mapa

| Regla | Contenido | Ancla |
|---|---|---|
| DEC-05 | Núcleo 100 % manual; toda automatización WhatsApp/OCR es módulo premium | `docs/PLAN_DESARROLLO.md:43` |
| DEC-10 | Agente LLM+WhatsApp apagado por defecto, activado por componente, opera **por tools, no SQL libre** | `docs/PLAN_DESARROLLO.md:48` |
| DEC-11 | Escrituras sensibles = **solicitud + aprobación humana**, matriz configurable, buzón | `docs/PLAN_DESARROLLO.md:49` |
| C01–C15 | Componentes del Núcleo (mapa de cerebro por dominio) | `docs/PLAN_DESARROLLO.md:167-181` |
| F2.5 | Tool registry + gate de capacidades + registro de contactos con OTP (parte Núcleo, aún no implementada) | `docs/PLAN_DESARROLLO.md:428` |
| F2.6 | Solicitudes + buzón + matriz de aprobación (aún no implementada) | `docs/PLAN_DESARROLLO.md:429` |
| ADR-0003 | Pipeline de ingesta, DI, frontera "leer vía tools o crear Solicitud; nunca escribe directo" | `docs/arquitectura/adr/ADR-0003-agente-multimodal-whatsapp.md:24`, `:184` |
| Capacidades D03/B06/I01 | OCR, copiloto/IA e integraciones externas **ausentes** | `docs/arquitectura/capacidades-objetivo.md:92,103,109` |
| Red de seguridad en base | RLS en `nucleo` con 31 tablas protegidas, **0 políticas**, rol de conexión con BYPASSRLS → el filtrado vive hoy solo en servicios Python | `docs/qa/informes/f0-wp1-wp2-arquitectura.md:100` |
| Enrolamiento respondido | El dueño definió el mapa rol→capacidad (sección 1) | D-08 Respondida, `docs/negocio/preguntas.md` |

**Nota de alcance:** este mapa describe intenciones de negocio, no endpoints ni
tablas. Definir el registro declarado de tools (componente+intent+permiso) y el
design de las tablas es trabajo futuro de `datos`+`backend` (ADR-0003 §12,
`:324`). Aquí no se pregunta en qué tabla vive cada intención: se pregunta qué
dominio del Núcleo debe responder y con qué tipo de acción.

---

## 3. Matriz rol → intención → componente → acción

**Tipos de acción:**
- **L:** lectura vía tool (respuesta con cita de fuente; DEC-10).
- **S+A:** solicitud + aprobación humana en el buzón (DEC-11). El agente nunca
  ejecuta la escritura; la ejecuta el componente dueño tras aprobación.
- **EA?**: escritura automática al Núcleo — **desviación declarada de DEC-11**, que
  solo puede existir si el dueño la decide explícitamente (→ D-10). Ninguna EA?
  puede implementarse antes de esa respuesta.

**Leyenda de estado (columna "Estado"):**
- 🟢 = el **dato** que alimenta la intención existe en código/DB verificado.
- 🟡 = dato parcial o inferido de la lectura (se indica la breve).
- 🔴 = no existe el objeto ni la pieza del Núcleo que lo sostiene.
- Toda fila, aunque el dato exista, requiere el runtime (I01/B06/D03 🔴,
  `capacidades-objetivo.md:92,103,109`): "posible hoy" se refiere a la parte de
  datos, nunca al agente en sí.
- **D-XX / P-XX** en negro = decisión del dueño o validación externa que bloquea.

### Transversal

| ID | Intención | Componente | Acción | Dato hoy | Estado | Anclas |
|---|---|---|---|---|---|---|
| AG-01 | Enrolamiento por WhatsApp de clientes, conductores y administración (teléfono → empresa + rol + entidad, con OTP) | C01 Identidad (registro de contactos, F2.5) | Escritura del registro de contactos por el Núcleo (no por el agente); OTP de vigencia corta | 🔴 F2.5 no implementado | requiere objeto nuevo (F2.5) · decisión de flujo cerrada (D-08 Respondida) · refinada con D-09 (2026-10-30): números admin se registran en la plataforma y el dueño puede desactivar por número el acceso por módulo; registro de números de clientes/conductores dentro de sus módulos | `PLAN_DESARROLLO.md:122`; ADR `:110,177,203` |
| AG-02 | Aislamiento por cliente **dentro** de la empresa: un cliente no ve fletes de otro (transversal a CL-01..CL-04) | Filtrado impuesto por el tool registry: toda tool recibe empresa_id **y** entidad cliente resueltas del contacto | Restricción de lectura | 🟡 el filtro por empresa existe en servicios Python; el filtro por cliente existe en expediente (`api_expediente.py:53`) pero no hay garantía estructural | decisión estructural: hoy no hay red de seguridad en base (RLS sin políticas + BYPASSRLS, `f0-...:100`) → el guardrail es obligatorio, ver D-09 | ADR `:196`; `f0-wp1-wp2-arquitectura.md:100`; RA-03 `docs/estado.md` §5 |

### Rol: CLIENTE (cliente final de TRANSTEI)

| ID | Intención | Componente | Acción | Dato hoy | Estado | Anclas |
|---|---|---|---|---|---|---|
| CL-01 | Consultar todo tipo de información de SUS fletes (aislamiento por cliente) | C03 Despacho (viajes) / C04 Expediente | L | 🟢 consulta de expediente con filtro `cliente_id` (`api_expediente.py:53`) | posible hoy en datos · aislamiento AG-02 obligatorio | AG-02; ADR `:196` |
| CL-02 | Consultar monto de su deuda | C05 Facturación y cobranza | L | 🟢 `servicio_facturacion.py:133,171` (total − pagado − notas) y vencimiento `:172` | posible hoy en datos · decisión de alcance 🟡: ¿deuda total del cliente o por factura? (bloquea el diseño de la tool, no hay `D-NN` separada) | DEC-10 `:48` |
| CL-03 | Consultar fletes pendientes de facturar (montos, IDs) | C05 + C03 (viajes cerrados con POD pendientes de agruparse) | L | 🟡 la facturación del núcleo agrupa viajes cerrados con POD y OC (`servicio_facturacion.py:3-5`); "pendiente de facturar" como consulta declarada al agente no existe | requiere tool declarada (F2.5) | ADR `:113-115` |
| CL-04 | Consultar qué camión está disponible (dónde y cuál) | C03 Despacho (disponibilidad) | L | 🟢 `servicio_disponibilidad.py:1463-1474` (parcial: ventana y validaciones) | posible hoy en datos · **decidida (D-11, 2026-10-30):** NO se expone la cantidad exacta de camiones → el agente pregunta ¿cuántos necesita? ¿qué rampla? ¿qué desea cargar? → se gestionan los fletes y se genera la solicitud que se aprueba en el sistema (requiere el objeto solicitud; la consulta interna de disponibilidad sigue existiendo) | D-11; ADR `:121` |
| CL-05 | Agendar un flete por cuestionario (carga, origen, destino, tipo de camión) → alerta al UI → pendiente de aprobación con desglose → si se aprueba, notificar camión/rampla/conductor | C03 Despacho | S+A | 🔴 no existe el objeto "solicitud de flete del cliente" ni la reserva resultante automática; la asignación posterior sí existe en C03 | requiere objeto nuevo + flujo de aprobación (F2.6) | DEC-11 `:49`; F2.6 `:429`; R-02 (licencia A5, `catalogo-reglas.md` R-02) aplica igual a la asignación resultante |
| CL-06 | Enviar documentación (PDF) → agente pregunta a qué fletes corresponden → desglose de fletes pendientes de OC o de facturar → cliente responde → alerta al UI → al aprobarse se recepciona y se actualiza la data | C04 Expediente y POD (+ C07 OC) | S+A | 🟡 todo adjunto es dato, no instrucción (ADR `:198`); la recepción de documentos existe en expediente (legacy/nucleo) pero no el flujo conversacional de asignación | requiere objeto nuevo (asignación documento↔flete desde agente) + S+A | ADR `:78-81,198`; D-05 OC |

### Rol: CONDUCTOR

| ID | Intención | Componente | Acción | Dato hoy | Estado | Anclas |
|---|---|---|---|---|---|---|
| CO-01 | Identidad por número de teléfono → triangulación conductor/camión/rampla | C01 (contacto) + C02 (flota) + C03 (asignación vigente) | L (identidad) | 🟡 la asignación tracto/rampla/chofer existe como invariante operativo (AGENTS.md §3.7); la resolución por teléfono no existe | requiere objeto nuevo (contactos F2.5) · **parcial (D-12, 2026-10-30)**: registro de números por módulo decidido (RUT empresa / nombre empresa / teléfono / nombre del cliente); **ABIERTA** la política OTP / re-enrolamiento / revocación (cambio o uso compartido del número) | `PLAN_DESARROLLO.md:122`; ADR `:177` |
| CO-02 | Cuando hay > 1 flete pendiente: mini cuestionario para elegirlo; "ninguno de esos" → alerta + aviso de contactar administración | C03 Despacho | L | 🟡 listado de viajes asignados al chofer existe en legacy/nucleo; el cuestionario de desambiguación es diseño del DI (ADR `:113,148-149`) | requiere tool declarada + fallar con mensaje legible si no hay match (ADR §6) | ADR `:113` |
| CO-03 | Carga de hoja de ruta: 6-7 fotos en cualquier orden, reconocimiento a JSON estricto, detección de faltantes, desglose "a medias" si falta info | C06 Gastos + C09 Nómina + C04 (objeto nuevo "hoja de ruta") + C12 Auditoría | **EA?** (pendiente D-10) | 🔴 no existe el objeto hoja de ruta (grep `hoja_?de_?ruta` en `backend/` = 0 resultados) ni la extracción (D03 🔴, `capacidades-objetivo.md:92`) | **decidida (D-10, 2026-10-30):** NO hay actualización automática — se genera una SOLICITUD con **Confirmar / Rechazar / Modificar**; la acción pasa de candidata a EA? a **S+A**; el objeto hoja de ruta se construye ("tendremos que construir la hoja de ruta"); ASR/OCR = requerimiento del MVP con evaluación piloto obligatoria | DEC-11 `:49` vs flujo del dueño (§1); DI como JSON estricto, patrón ADR §3.4 |
| CO-04 | Si entregó todo: ingreso automático que actualiza gastos, sueldos, ganancias y finanzas + notificación al admin "¿deseas revisarla?" con modificación manual posterior | C06 + C09 + C08 (margen) | **EA?** (pendiente D-10) | 🔴 toca dinero: gasto y comisión son costo del viaje (`servicio_gastos.py:455-461`, R-01); nómina con snapshot (F1.2, `PLAN_DESARROLLO.md:377`) | **decidida (D-10, 2026-10-30):** la ejecución se hace tras aprobar la solicitud (aprobador = rol correspondiente; el dueño ejemplificó con "secretario" → evidencia AB-02) · escrituras deben ser idempotentes y con rastro (INV-G04/G05, INV-F, `PLAN_DESARROLLO.md:700-702`) y toda corrección del admin compensada, nunca borrado | `PLAN_DESARROLLO.md:695,700-702,535` |
| CO-05 | Confirmación del conductor: "Hoja de ruta de X flete" con ID por cliente (ej. Soquimich → SQM-001) + desglose de lo reconocido + "¿La información es correcta?" | C03/C04 (ID comercial) + runtime (conversación) | L (presentación) | 🔴 el núcleo usa IDs técnicos UUID/folios; no existe ID de entidad por cliente | **decidida (D-16, 2026-10-30):** regla formal en el sistema, orden creciente, 5 dígitos (SQM-00001…) · **R-04** numerada en `catalogo-reglas.md:117` | ADR `:137-156` (el DI cita solo IDs resueltas); D-16 |
| CO-06 | Si el conductor dice "no": re-ingreso por texto de la(s) parte(s) malas, reacomodo al JSON, re-consulta; si vuelve a fallar: reintento o declaración de entrega presencial + notificación a los roles | C04 + C12 + runtime | S+A (si toca escritura) | 🔴 no hay conversación ni estados de entrega presencial | requiere objeto nuevo (estados del expediente de hoja de ruta) + degradación con mensaje legible (ADR §6) | ADR `:211-218` |

### Rol: ADMINISTRACIÓN / DUEÑO

| ID | Intención | Componente | Acción | Dato hoy | Estado | Anclas |
|---|---|---|---|---|---|---|
| AD-01 | Preguntas precomputadas: fletes planificados hoy, clientes que solicitaron fletes, facturación del mes, clientes pendientes de pago, qué pasó con X camión, mantención de X camión, gasto en aceite | C03, C05, C10, C06, C13 | L | 🟡 hay datos y motores de lectura por dominio (aging CxC `servicio_alertas.py:308-313`; facturación `servicio_facturacion.py`; KPIs), pero **no** tools declaradas por intención | requiere tools declaradas (F2.5) · cada una activable por empresa (gate por defecto cero, `PLAN_DESARROLLO.md:121`) · **decidido (D-15, 2026-10-30):** MVP sin gate de costo ("los precios de momento no nos preocupemos"); se revisa tras la presentación | DEC-10 `:48`; ADR `:114`; D-15 |
| AD-02 | Preguntas NO precomputadas ("gerente digital"): el agente construye la respuesta consultando la DB | ¿? (forma de consulta flexible **por definir**) | L | 🔴 DEC-10 prohíbe SQL libre (`:48`); no existe capa semántica ni mecanismo alternativo | **decididos los requerimientos (D-09, 2026-10-30):** respuesta natural no guionada con límites reales ("No estoy autorizado a darte ese tipo de información"); opera SOLO admin/dueño; números admin registrados en la plataforma con desactivación por número del acceso por módulo; auditoría de cada consulta (→ detalle en **D-17**). El MECANISMO ((a) capa semántica/tools compuestas vs (b) SQL read-only con guardarraíles) lo resuelve arquitectura — abierto en la ADR · la escritura queda SIEMPRE en solicitud+aprobación (DEC-11, `:49`) | D-09; `f0-...:100` (no hay red de seguridad en base: el guardrail debe imponer empresa_id externamente) |
| AD-03 | Desglose completo por cliente; envío de documentos (factura, OC, nota de crédito) si lo pide | C05 + C07 + C11 | L + envío de documento (URL firmada, patrón DEC-12) | 🟢 existen facturas, OC con saldo (`servicio_comercial.py:560,574`) y storage con URLs firmadas (`capacidades-objetivo.md:109`; patrón `PLAN_DESARROLLO.md:128-133`) | posible hoy en datos · el envío por WhatsApp a terceros → validación P-08 | `PLAN_DESARROLLO.md:49-50`; P-08 |
| AD-04 | "Algo anda mal con este flete": alerta al buzón con desglose; al pincharla, redirige a los roles con permiso al componente del núcleo para revisar y modificar | C12 Auditoría + C13 buzón (F2.6) | S+A | 🔴 no existe el buzón (F2.6 no implementado); el patrón es exactamente el genérico de DEC-11 | requiere objeto nuevo (F2.6) · **precisado (D-10/D-14, 2026-10-30):** la aprobación es en UI — buzón con Confirmar / Rechazar / Modificar; NO se aprueba por WhatsApp → **ABIERTA** la notificación por WhatsApp (subpregunta de D-14) | DEC-11 `:49`; F2.6 `:429`; ADR `:84`; D-14 |

---

## 4. Lecturas del mapa (🟡 inferido, con lo que lo confirmaría)

1. **El único flujo que toca escritura automática es CO-03/CO-04**:
   todo lo demás encaja en L (DEC-10) o S+A (DEC-11), tal como el ADR lo exige.
   Lo confirma el dueño al responder **D-10**.
2. **El "aislamiento por cliente" (AG-02) es una regla nueva**, no la que ya existe:
   la empresa se filtra hoy en servicios Python (sin garantía en base,
   `f0-wp1-wp2-arquitectura.md:100`); además el cliente final no es una entidad con
   identidad en el núcleo hoy (contacto = 🔴, AG-01/D-12). Lo confirma `datos` al
   cerrar la pieza de guardrails de D-09.
3. **CL-04 es el único flujo de lectura que expone operación interna a un tercero**
   (disponibilidad de flota). Técnica y comercialmente es posible; la autorización
   depende del dueño (D-11). Lo confirma el dueño.
4. **El ID por cliente (CO-05, "SQM-001") es una regla de presentación candidata**
   con efecto fuerte: exige un identificador comercial por cliente en el Núcleo.
   No se escribe en el catálogo `R-0XX` hasta que el dueño responda (D-16).
   Lo confirma el dueño.

---

## 5. Regla R-04 — ID comercial de flete por cliente

> **Numerada como R-04 en `catalogo-reglas.md` (2026-10-30); implementación en `0021`+`0022` (solo `tei_test`).** El bloque de verificación siguiente describe el estado previo a la numeración.

> **Verificación de numeración (2026-10-30):** `docs/negocio/catalogo-reglas.md`
> tiene **R-01, R-02 y R-03** (lectura directa del archivo); el siguiente ID libre
> en el espacio `R-0XX` de **reglas** es **R-04**. Ojo: `docs/orquestacion/registro.md`
> usó "R-04/R-05" como **riesgos** de una sesión de 2026-10-29 — espacio distinto;
> evitar colisión es del `orquestador` (AGENTS.md §11.2). Este documento **no la
> numera definitivamente**: pasa a `catalogo-reglas.md` como R-04 en una tarea con
> alcance de catálogo, o con el siguiente ID libre si el orquestador reasigna.

- **Enunciado propuesto (R-04):** todo flete lleva un **ID comercial por cliente**
  con formato `<PREFIJO>-NNNNN` — prefijo derivado del cliente y 5 dígitos con
  relleno de ceros (SQM-00001, SQM-00002, …) —, estable, asignado en **orden
  creciente** y sin reutilización, que se usa en las comunicaciones (hojas de ruta,
  desgloses) en lugar del UUID/folio técnico.
- **Fuente:** dueño, 2026-10-29 (§1) y confirmación 2026-10-30 (**D-16 Respondida**,
  "regla formal en el sistema, orden creciente; 5 dígitos").
- **Fórmula:** `siguiente = máximo(dígitos ya asignados para (empresa_id, cliente_id)) + 1`,
  con relleno a 5 dígitos; asignación **atómica y única** por (empresa, cliente).
- **Detalles de diseño que D-16 no fijó** (no bloquean el enunciado; van al
  quarantine de diseño en el handoff): cómo se genera y se garantiza la unicidad
  del prefijo (derivación del nombre corto: dos clientes distintos que producirían
  el mismo prefijo);
  si el ID es editable después de asignado (recomendación conservadora: **no
  editable**; una corrección se documentaría con el cambio de relación flete↔ID,
  nunca renumerando los fletes ya citados en comunicaciones — propuesta, no
  decisión del dueño).
- **Ejemplo numérico (borrador):** Soquimich ya tiene asignados SQM-00001,
  SQM-00002 y SQM-00003. Llega un flete nuevo de Soquimich → siguiente = 3 + 1 →
  **SQM-00004**. Un segundo flete de Soquimich el mismo día → **SQM-00005** (la
  secuencia es por cliente, no por fecha). Un cliente distinto (p. ej. Cervera) en
  la misma empresa arranca en su propia secuencia → CER-00001. La secuencia se
  lleva por (empresa, cliente): dos empresas distintas no comparten contadores.
- **Invariantes asociadas (prospección para `datos`):** unicidad `UNIQUE (empresa_id,
  cliente_id, id_comercial_flete)`; creciente sin salto reutilizado; auditada
  append-only (la asignación no se reescribe).
- **Handoff si se numera:** `datos` → columna `id_comercial_flete` + constraint
  `UNIQUE (empresa_id, cliente_id, id_comercial_flete)` con asignación atómica/
  idempotente; `backend` → usarlo en el DI (ADR `:137-156`) y en las comunicaciones
  del agente (CO-05); `qa` → casos de unicidad, caso de reasignación de flete (no
  duplicar consumo de ID), y caso de prefijo colisionante entre clientes.
  Mientras esté solo como propuesta, **ninguna pieza está implementada**.

---

## 6. Tensiones registradas → `docs/negocio/preguntas.md`

| Tensión | ID de decisión | Resumen |
|---|---|---|
| 1. Lectura libre del admin vs DEC-10 ("por tools, no SQL libre", `PLAN_DESARROLLO.md:48`) | **D-09** | El admin demanda "gerente digital" (respuesta libre); se necesitan opciones (a) capa semántica/tools compuestas o (b) SQL read-only con guardarraíles. Hoy NO hay red de seguridad en base (RLS sin políticas + BYPASSRLS, `f0-wp1-wp2-arquitectura.md:100`): el filtro `empresa_id` debe imponerse externamente. Escritura = SIEMPRE solicitud+aprobación (DEC-11). |
| 2. Hoja de ruta automática vs DEC-11 (escrituras sensibles = aprobación previa) | **D-10** | El flujo del dueño es carga automática + revisión posterior del admin + confirmación previa del conductor: desviación declarada de DEC-11 porque toca nómina y finanzas. Opciones (a)/(b) en la pregunta. |
| 3. Visibilidad de flota disponible al cliente | **D-11** | Dato operativo interno (dónde y cuál hay camión disponible) expuesto a un tercero. |
| 4. Identidad por número de teléfono | **D-12** | Cambio de teléfono, número compartido, OTP y re-enrolamiento; cross-ref con registro de contactos OTP (ADR §3.3) y revocación (R5 del ADR, `:317`). |

## 7. Riesgos que este mapa no elimina

1. **Riesgo Alto heredado (R1 del ADR, `:313`):** si el agente se activa antes de
   cerrar el aislamiento del piloto, los flujos de cliente (CL-01/CL-03) heredan el
   mismo filtrado débil; con `BYPASSRLS` vigente, la garantía es el guardrail
   externo decidido en D-09, no la base.
2. **Doble conteo en CO-04:** si el admin corrige manualmente una hoja de ruta ya
   escrita, gastos/sueldos/margen deben recalcularse compensando, no duplicando
   (INV-G04/G05 sin prueba hoy, `PLAN_DESARROLLO.md:700-702`). Se resuelve con el
   diseño de D-10 y handoff a `datos`/`backend` después.
3. **Adjuntos adversarios (CL-06, CO-03):** un PDF/foto "que pide facturar" es
   dato, no instrucción (ADR `:198`); las escrituras que nacen de ellos siguen siendo
   Solicitud, nunca ejecución.
4. **Canal y privacidad:** cualquier envío de deudas/facturas/hojas de ruta por
   WhatsApp a terceros arrastra validación legal externa (P-07, P-08). Este mapa no
   la resuelve.
