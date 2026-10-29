# ADR-0001: Coexistencia `public` (legacy) y `nucleo` (destino)

- **Estado:** Propuesto
- **Fecha:** 2026-10-29
- **Decide:** agente `arquitectura` (propuesta técnica). Requiere aceptación del
  dueño del negocio para las decisiones marcadas como **D-xx**.
- **Reemplaza a:** ninguna decisión previa registrada. `docs/_archivo/planes/PLAN_MAESTRO_ERP_V2.md`
  §6.5 propone una estrategia distinta (evolucionar `public` en sitio); este ADR
  la sustituye con evidencia.
- **Documentos relacionados:** `docs/arquitectura/matriz-plan-vs-codigo.md`,
  `docs/arquitectura/alcance-piloto.md`

---

## Contexto

Hechos verificados en esta sesión (2026-10-29), por lectura estática. La base
local estaba apagada: **ninguna afirmación de comportamiento en ejecución está
probada**.

1. **Hay dos esquemas con tablas de negocio propias y ningún puente.**
   `public` se crea en `supabase/migrations/0001_esquema_base.sql`–`0003`;
   `nucleo` en `0004`–`0014`. `nucleo` no escribe en `public` y `public` no
   escribe en `nucleo`: no existe vista, trigger cruzado ni job de
   reconciliación (búsqueda de `outbox|worker|job_queue` → 0 resultados). 🟢

2. **Los dos esquemas tienen conceptos duplicados con reglas distintas.**
   Ejemplo canónico: `public.facturas unique (numero_sii, cliente_id)`
   (`0001:142`) frente a `nucleo.facturas_nucleo unique (empresa_id, numero_factura)`
   (`0013:30`). Otro: `public.viajes` valida solo el tracto por estado
   (`backend/app/api/routes/viajes.py:99-115`); `nucleo` impone 3 `EXCLUDE USING gist`
   por ventana (`0004:744-757`). 🟢

3. **La garantía crítica vive en `nucleo` y solo en `nucleo`.**
   Documentos vencidos: trigger `0004:1281-1292`. Capacidad y sobrepeso:
   `0004:1198-1225`. Transiciones de viaje: `0004:1511-1547`. Congelamiento
   financiero y prohibición de borrado: `0004:1454-1503`. Factura sin POD:
   `backend/app/nucleo/servicio_facturacion.py:494-501`. Folio por empresa:
   `0004:498`. 🟢

4. **Ambos esquemas siguen aceptando escrituras.** El único control es
   `nucleo.cutover_control.legacy_escritura_congelada`, que nace en `false`
   (`0014:10,17-19`) y solo bloquea escrituras legacy cuando está en `true`
   (`backend/app/main.py:36-61`). Es decir: **hoy el flag está abierto y toda
   garantía del núcleo es evitable escribiendo por el legacy**. 🟢

5. **El corte no es atómico ni completo.**
   - La lectura del flag tiene caché de 5 s **por proceso**
     (`backend/app/nucleo/servicio_cutover.py:17-26,40`): con varios workers hay
     hasta 5 s de ventana en que un proceso cree que está abierto.
   - Ante excepción al leer el flag, el código asume **abierto**
     (`servicio_cutover.py:38-39`): **fail-open**.
   - `scripts/cutover_legacy.py` migra clientes, choferes, tractos, ramplas,
     documentos, tarifas, OC sintéticas y viajes (`:100-388`). **No migra
     gastos, facturas, pagos, liquidaciones ni mantenimientos** (búsqueda de
     `gastos|facturas|liquidaciones|mantenimientos|pagos` en el script → 0
     resultados).
   - Los viajes migrados se insertan siempre con `estado = 'confirmado'`
     (`cutover_legacy.py:368`), perdiendo el estado real, y por lo tanto **sin
     crear reservas** (el trigger solo reserva fuera de
     `borrador/cotizado/confirmado/anulado`, `0004:1632-1635`). Tras el corte,
     la agenda no refleja la ocupación real de los viajes migrados.
   - El script y el endpoint de congelar escriben el flag en la misma
     transacción (`cutover_legacy.py:390-403`), lo cual es correcto, pero no
     existe verificación posterior de que la migración cuadre. 🟢

6. **El interruptor de cutover no tiene dueño explícito ni historial.**
   Congelar/descongelar exige `configuracion:escribir`
   (`backend/app/nucleo/api_cutover.py:24-28`), permiso que tienen **admin y
   gerente de cualquier empresa** (`backend/app/nucleo/permisos.py:59-60`). La
   tabla es **global** (`id boolean primary key`, `0014:9`), no por empresa, y
   **no tiene trigger de auditoría** (no aparece en los `fn_auditoria` de
   `0004:1761-1862`). Solo guarda el último `congelada_por`/`motivo`, sin
   historial. 🟢

7. **Hay pantallas duplicadas con clientes HTTP distintos.** 13 páginas usan
   `frontend/src/lib/nucleo.ts` (tablero, comercial, despacho, agenda,
   expediente, cobranza, rentabilidad, maestros, auditoría, permisos, cutover,
   conductor, expediente/[id]) y 13 usan `frontend/src/lib/api.ts` (dashboard,
   viajes, flota, mantenimiento, facturación, cobranzas, IVA, liquidaciones,
   clientes, choferes, KPIs, configuración). Los pares
   `dashboard`/`tablero`, `clientes`+`choferes`/`maestros`,
   `facturacion`+`cobranzas`/`cobranza` cubren el mismo concepto con reglas
   distintas. 🟢

8. **Hay módulos sin equivalente en `nucleo`.** Liquidaciones/comisiones,
   mantenimiento preventivo por km, IVA/F29 y export CSV existen **solo** en
   legacy (`0001:151-209`; `backend/app/api/routes/liquidaciones.py`,
   `mantenimiento.py`, `export.py`). 🟢

---

## Problema

**Mientras `public` y `nucleo` acepten escrituras sobre el mismo concepto sin una
puerta única declarada, ninguna garantía del núcleo es exigible y no existe forma
de saber cuál de los dos registros es el verdadero.**

En una frase verificable: *dado un concepto de negocio (p. ej. "la factura
F-123"), ¿en qué tabla vive su verdad y qué escritura puede cambiarla?* Hoy la
respuesta es "en las dos, y cualquiera".

---

## Alternativas

| Alternativa | Ventajas | Costes / riesgos | Reversible | Impacto en legacy | Impacto en datos |
|---|---|---|---|---|---|
| **A. Cutover global inmediato** — congelar todo `public` ahora y operar solo en `nucleo` | Una sola fuente de verdad de inmediato; máxima garantía | Liquidaciones, mantenimiento e IVA **no existen** en `nucleo`: la operación se detiene. Además el script no migra gastos/facturas/pagos y los viajes migrados pierden estado y reservas | Sí, con `descongelar`, pero el trabajo hecho en `nucleo` durante el corte no existe en `public` → divergencia al volver | Alto: deja de funcionar | Alto: pérdida de estado en viajes migrados; histórico financiero fuera del núcleo |
| **B. Coexistencia declarada con puerta única por módulo** — un registro explícito `módulo → esquema canónico`; el legacy queda cerrado a escritura **solo** en los módulos cuyo canónico es `nucleo`; los módulos sin equivalente siguen canónicos en `public` | Resuelve el problema sin detener la operación; no crea tercera fuente de verdad; cada módulo se cierra cuando su equivalente existe y está probado; reversible módulo a módulo | Requiere tocar código (registro + middleware) y decidir el orden; convive con dos esquemas un tiempo más; el flag actual es global y debe resolverse por módulo | Alta: revertir el registro devuelve el comportamiento actual sin tocar datos | Medio: pantallas legacy de módulos cerrados dejan de escribir (deben redirigirse a las del núcleo) | Bajo: no mueve datos; solo restringe escrituras |
| **C. Evolucionar `public` en sitio** (lo que propone el plan §6.5: añadir `empresa_id`, `EXCLUDE`, auditoría a las tablas existentes) | Un solo esquema; sin duplicación | Duplica el trabajo ya hecho en `nucleo` (14 migraciones); migrar tablas con datos vivos y constraints nuevas es el cambio de mayor riesgo del repo; contradice el diseño ya implementado | Baja: las migraciones de esquema con datos son difíciles de revertir | Alto: toca todas las tablas en uso | Alto: backfill de `empresa_id`, reconstrucción de rangos desde `date` |
| **D. No decidir** (dejar ambos abiertos y "ya veremos") | Ningún coste inmediato | Es el estado actual: el riesgo RA-02 sigue abierto y crece con cada pantalla nueva del núcleo | — | Ninguno | Ninguno, pero la divergencia se acumula sin detección |

**Descartadas:** A por impacto operativo y por datos incompletos (no hay
equivalente de 4 módulos y el script no migra el histórico financiero). C por
duplicar trabajo ya hecho y por ser el cambio de mayor riesgo sobre datos vivos.
D por ser la causa del problema, no una opción.

---

## Decisión

**Se adopta la alternativa B: coexistencia declarada con puerta única de
escritura por módulo.**

### B.1 Principio normativo

> Para cada concepto de negocio existe **exactamente un esquema canónico**. Las
> escrituras al otro esquema para ese concepto se rechazan. Un concepto no puede
> tener dos escritores.

Corolario: **no se crea una tercera fuente de verdad**. El registro de
enrutamiento es **configuración de arquitectura**, no un dato de negocio, y no
duplica ninguna entidad.

### B.2 Matriz módulo → esquema canónico → estado

Estados: **N** = canónico en `nucleo` (implementado) · **N-p** = canónico en
`nucleo`, implementación parcial · **P** = canónico en `public` (sin equivalente
en `nucleo`) · **D** = duplicado sin declarar (hoy).

| Módulo / concepto | Tabla(s) `public` | Tabla(s) `nucleo` | Canónico propuesto | Estado | Evidencia |
|---|---|---|---|---|---|
| Empresa, membresía, roles | — (`public.usuarios` solo auth+rol) `0001:36-45` | `nucleo.empresas`, `usuarios_empresa` `0004:102-157` | **nucleo** | N | `deps.py:40-82` |
| Clientes | `public.clientes` `0001:47-58` | `nucleo.clientes` `0004:158-190` | **nucleo** | N | pantalla `maestros`; `api_maestros.py` |
| Choferes | `public.choferes` `0001:60-70` | `nucleo.choferes` `0004:282-325` | **nucleo** | N | idem |
| Tractos / ramplas | `public.tractos`, `ramplas` `0001:72-94` | `nucleo.tractos`, `ramplas` `0004:191-281` | **nucleo** | N | idem |
| Documentos de recurso | solo 3 campos de vencimiento en `0001` | `nucleo.documentos` `0004:326-375` | **nucleo** | N | `0004:1041-1074` |
| Tarifas, OC, centros de costo | — | `nucleo.tarifas`, `ordenes_compra`, `centros_costo` `0004:377-489`, `0005:16` | **nucleo** | N | `api_comercial.py` |
| Viajes | `public.viajes` `0001:97-112` | `nucleo.viajes` `0004:542-701` | **nucleo** | N | 8 triggers `0004:1832-1850` |
| Disponibilidad / agenda / bloqueos | — | `nucleo.reservas_recurso` `0004:703-767`, `0006` | **nucleo** | N | 3 `EXCLUDE` `0004:744-757` |
| Expediente (paradas, checklist, eventos, incidentes, documentos) | — | `nucleo.viaje_*` `0007` | **nucleo** | N | `api_expediente.py` |
| POD | — | `nucleo.pod` `0009:8-36` | **nucleo** | N | `api_pod.py` |
| Gastos de viaje | `public.gastos_viaje` `0001:114-125` | `nucleo.viaje_gastos` `0011:29` | **nucleo** | N | `servicio_gastos.py:255-259` |
| Precio diésel | — | `nucleo.precios_diesel` `0011:11` | **nucleo** | N | `servicio_gastos.py:166-228` |
| Costos / rentabilidad / Freight Score | cálculo en `kpi_engine.py` | `nucleo.configuracion_costos` `0012:8` + servicio | **nucleo** | N | `servicio_rentabilidad.py` |
| Facturación | `public.facturas`, `factura_viaje` `0001:127-149` | `nucleo.facturas_nucleo`, `factura_viajes` `0013:10-73` | **nucleo** | N | `api_facturacion.py:48-124` |
| Cobranza (pagos, notas de crédito, promesas, aging) | solo `estado` en `0001:138` | `pagos_nucleo`, `notas_credito_nucleo`, `promesas_pago_nucleo` `0013:78-158` | **nucleo** | N | `servicio_facturacion.py:620-712` |
| Auditoría | — | `nucleo.auditoria` `0004:813-828` | **nucleo** | N-p (cobertura parcial: sin trigger en `cutover_control`, `transiciones_viaje`, `folio_contador`) | `0004:1761-1862` |
| Control de cutover | — | `nucleo.cutover_control` `0014` | **nucleo** | N-p (sin auditoría; global, no por empresa) | `0014:9` |
| **Liquidaciones / comisiones** | `public.liquidaciones`, `anticipos_chofer`, `ajustes_liquidacion` `0001:151-186` | **no existe** | **public** (temporal, explícito) | P | `liquidaciones.py` |
| **Mantenimiento preventivo** | `public.pautas_mantenimiento`, `mantenimientos` `0001:189-209` | **no existe** (solo bloqueos de agenda) | **public** (temporal, explícito) | P | `mantenimiento.py`; `0006` |
| **IVA / F29** | cálculo en `kpi_engine.py:400-421` + `0002` | **no existe** | **public** (temporal, explícito) | P | `iva/page.tsx` |
| **Export CSV** | `export.py` | **no existe** | **public** (temporal, explícito) | P | `export.py:29-45` |
| KPIs globales | `kpi_engine.py` sobre `public` | rentabilidad y tablero propios | **duplicado**: KPIs de gestión → `nucleo`; IVA/margen mensual → `public` hasta D-04 | D | ver `01-matriz` §1 #13/#14 |

**Consecuencia de la matriz:** 16 de 21 conceptos son canónicos en `nucleo`
hoy. 4 son canónicos en `public` **por ausencia de equivalente**, no por
decisión. 1 queda duplicado y debe resolverse con la decisión **D-04**.

### B.3 Regla de cierre por módulo

Un módulo pasa de `D` a `N` (y se cierra su escritura legacy) solo cuando se
cumplen **las cuatro** condiciones:

1. Existe el mecanismo en `nucleo` **y** una prueba que falla si se retira
   (prueba de mutación sobre la constraint o el trigger).
2. La pantalla del núcleo cubre la funcionalidad exclusiva de la pantalla legacy
   (no solo el listado: el alta, la edición y la anulación).
3. Los datos existentes del módulo en `public` están migrados y conciliados
   (conteo y suma por empresa antes/después).
4. Existe una consulta de reconciliación que devuelve 0 diferencias y queda
   registrada.

Ninguna de las cuatro se cumple hoy para ningún módulo con datos reales: las
condiciones 3 y 4 dependen de una base que estaba apagada. 🔴

### B.4 Lo que este ADR **no** decide

- No migra datos.
- No congela el legacy.
- No elimina pantallas legacy.
- No decide el orden de cierre por módulo (depende de D-01).
- No define reglas tributarias, laborales ni comerciales (D-02, D-03, D-04, D-06).

---

## Consecuencias

### Positivas

- Elimina la ambigüedad "¿dónde vive la verdad?" sin mover datos ni detener la
  operación.
- Hace explícito que 4 módulos siguen en legacy: deja de ser una deuda invisible
  y pasa a ser alcance declarado.
- Permite cerrar módulos de uno en uno, con criterio observable, en vez de un
  big bang que hoy rompería liquidaciones, mantenimiento e IVA.
- No introduce cola, worker, bus ni servicio nuevo: no hay dependencia
  operativa adicional.

### Negativas

- Durante la transición siguen existiendo dos esquemas y dos clientes HTTP. La
  deuda no desaparece, se acota.
- Cerrar un módulo en legacy **rompe pantallas legacy** que aún están en la
  navegación (`clientes`, `choferes`, `flota`, `viajes`, `facturacion`,
  `cobranzas`, `dashboard`). Requiere redirigir o retirar esas pantallas en el
  mismo cambio, o el usuario ve errores 409.
- El registro de módulos es política de arquitectura que debe mantenerse: si
  alguien agrega un endpoint legacy nuevo para un módulo cerrado, la garantía se
  pierde en silencio. Mitigación: prueba que enumere las rutas legacy y falle si
  aparece una escritura no declarada.

### Deuda que genera

- Un registro de enrutamiento más que mantener mientras dure la convivencia.
- La obligación de migrar los 4 módulos pendientes para poder retirar `public`.
- La reconciliación de datos entre esquemas, que hoy **no existe** y este ADR no
  crea (sería una tercera fuente de verdad si se implementara como tabla; debe
  ser una **consulta** de verificación, no un almacén).

---

## Plan de migración y rollback

### Fase 0 — Declarar (sin cambiar comportamiento)

1. Publicar esta matriz como referencia vigente.
2. Añadir la consulta de reconciliación por concepto (conteo y suma por
   `empresa_id`/equivalente legacy) y registrar su salida como línea base.
   **Solo lectura.**
3. Congelar por escrito la lista de módulos `P` (liquidaciones, mantenimiento,
   IVA, export): no se construyen en `nucleo` durante el piloto salvo decisión
   contraria (D-01).

**Criterio de aceptación:** existe una línea base numérica fechada por módulo, y
la lista `P` está aprobada por el dueño.

### Fase 1 — Cerrar escritura legacy módulo a módulo

Orden recomendado (menor a mayor impacto operativo), sujeto a D-01:

1. **Maestros** (`clientes`, `choferes`, `tractos`, `ramplas`, `documentos`):
   la pantalla `/maestros` ya los cubre y es la que usan despacho y taller.
2. **Comercial** (tarifas, OC): solo existe en `nucleo`; no hay nada que cerrar,
   solo impedir que se cree un duplicado en legacy.
3. **Operación** (`viajes`): cerrar escritura legacy de `POST/PUT/PATCH/DELETE
   /viajes` y redirigir `/viajes` a `/despacho` + `/expediente`.
4. **Facturación y cobranza**: cerrar `/facturas` y `/cobranzas` legacy;
   redirigir a `/cobranza`.

Cada cierre es un cambio independiente, con su propia prueba y su propio
rollback. **No se cierra un módulo cuyo equivalente no cubra alta, edición y
anulación.**

**Criterio de aceptación por módulo:**
- `POST/PUT/PATCH/DELETE` al endpoint legacy devuelve un código explícito
  (409 con `codigo = MODULO_EN_NUCLEO`), no 500 ni un error de base.
- La pantalla del núcleo ejecuta el mismo caso de uso con datos reales.
- La consulta de reconciliación del módulo devuelve 0 diferencias nuevas
  posteriores al cierre.
- La prueba de regresión del área pasa.

### Fase 2 — Cutover completo (solo cuando los 21 conceptos sean `N`)

Requisitos previos, todos verificables:

- [ ] Los 4 módulos `P` tienen equivalente en `nucleo` **o** el dueño acepta
      explícitamente que se retiran del alcance del piloto (D-01).
- [ ] `scripts/cutover_legacy.py` migra **gastos, facturas, pagos y
      liquidaciones**, no solo maestros y viajes (`cutover_legacy.py:100-388`).
- [ ] Los viajes migrados conservan su estado real y crean sus reservas, o se
      documenta que se reasignan a mano (`cutover_legacy.py:368`;
      `0004:1632-1635`).
- [ ] El flag de cutover es **fail-closed** para escrituras: hoy una excepción
      de lectura lo deja abierto (`servicio_cutover.py:38-39`).
- [ ] El flag se propaga a todos los procesos sin ventana de 5 s, o se opera con
      un solo worker durante el corte (`servicio_cutover.py:17-26`).
- [ ] `cutover_control` tiene auditoría append-only y un dueño definido (D-05).
- [ ] `make restore-drill` ejecutado con evidencia (hoy no ejecutado, 🔴).
- [ ] Reconciliación final: 0 diferencias en conteos y montos por módulo.

**Criterio de aceptación del cutover:** durante 5 días hábiles consecutivos,
cero escrituras legacy (el flag permanece en `true`), cero incidentes de
duplicación y reconciliación diaria en 0.

### Rollback

| Escenario | Acción | Efecto | Riesgo residual |
|---|---|---|---|
| Un módulo cerrado causa un bloqueo operativo | Revertir el registro de ese módulo (deploy) | El legacy vuelve a aceptar escrituras para ese concepto | Los registros creados en `nucleo` mientras estuvo cerrado **no existen en `public`**; las pantallas legacy no los verán |
| Cutover completo falla | `POST /nucleo/cutover/descongelar` (`api_cutover.py:46-51`) | Reabre escrituras legacy en ≤5 s por proceso | Mismo problema: divergencia de lo escrito en `nucleo` durante el corte; no hay sincronización inversa |
| Migración de datos incorrecta | Restaurar desde backup verificado (`scripts/restore_drill.sh`) | Vuelve al estado previo | Pérdida de lo escrito después del backup; el drill no está probado 🔴 |

**Advertencia explícita:** el rollback **no es sin pérdida** en el sentido de
datos. Reabrir el legacy no propaga a `public` lo creado en `nucleo`. Por eso el
cierre por módulo debe hacerse cuando el módulo esté completo, no para "probar".

---

## Criterios de aceptación de este ADR

1. Existe una matriz `módulo → esquema canónico` aprobada, sin conceptos
   marcados `D` salvo el explícitamente diferido (KPIs, D-04).
2. Todo endpoint de escritura legacy pertenece a un módulo declarado; una prueba
   automatizada falla si aparece uno no declarado.
3. Toda escritura a un módulo canónico en `nucleo` rechazada en legacy devuelve
   un código de error explícito y documentado, no un 500.
4. Existe una consulta de reconciliación por módulo, ejecutable y con salida
   registrada.
5. Ningún módulo se cierra sin las cuatro condiciones de §B.3.

---

## Riesgos y preguntas abiertas

| ID | Decisión que **no** toma este ADR | Destinatario | Por qué no la decido yo |
|---|---|---|---|
| **D-01** | Qué módulos entran al piloto de 90 días y en qué orden se cierra el legacy | Dueño del negocio | Es alcance y prioridad de negocio, no arquitectura |
| **D-02** | Política de comisión: ¿se devenga al finalizar, al facturar o al cobrar? | Dueño + contador | Regla comercial/laboral; el plan la deja abierta (§2.3 "Hay que definir política") y hoy legacy paga sobre `finalizado/facturado` (`liquidaciones.py:45-59`) |
| **D-03** | Qué se congela al emitir una liquidación y quién puede reabrir un viaje cerrado | Dueño + contador | Define un documento con efecto laboral; no se puede inferir |
| **D-04** | Criterio de devengo del margen mensual (ingreso por viaje vs. gasto por fecha) | Contador | Regla contable; el plan pide "política de devengo y matching" sin definirla (§2.4 #14) |
| **D-05** | Quién es dueño del interruptor de cutover y si debe ser global o por empresa | Dueño + `auditor-seguridad` | Hoy cualquier admin/gerente de cualquier empresa puede congelar el sistema completo (`permisos.py:59-60`, `0014:9`) |
| **D-06** | Documentos obligatorios por empresa (SOAP, seguro de carga, curso de carga peligrosa) y si la clase de licencia debe bloquear | Dueño + experto en prevención | Requisito legal/operativo; el DDL ya lo hace configurable (`0004:123,1047-1074`) y el código lo deja como advertencia (`0004:1272-1274`) |
| **D-07** | Si el mantenimiento preventivo se construye en `nucleo` durante el piloto o se queda en legacy | Dueño + taller | Alcance; hoy no hay pauta por km en `nucleo` |

**Riesgos residuales que este ADR no elimina:**

- **R1 (alto):** durante la convivencia, un usuario que use la pantalla legacy de
  un módulo aún abierto puede crear un registro que el núcleo no verá. Mitigado
  módulo a módulo, no de golpe.
- **R2 (alto):** la garantía de exclusión del núcleo no está probada con dos
  conexiones reales (ver `01-matriz` V2). El ADR la asume como mecanismo de
  diseño, no como hecho verificado.
- **R3 (medio):** RLS habilitado sin políticas no es aislamiento; el rol efectivo
  de conexión no es verificable sin base (RA-03).
- **R4 (medio):** el cierre de un módulo sin redirigir su pantalla produce 409
  visibles al usuario.
- **R5 (bajo):** el registro de módulos puede quedar desactualizado si se agregan
  endpoints sin actualizarlo.
