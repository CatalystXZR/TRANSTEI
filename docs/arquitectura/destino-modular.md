# Destino modular del ERP TEI — fronteras, contratos, orquestación y escalabilidad

> **Pregunta que responde:** ¿cuál es el destino modular del sistema y qué lo justifica?
> **Dueño:** `arquitectura` · **Estado:** propuesta (requiere ratificación del dueño) · **Verificado:** 2026-10-29
> **Caduca si:** se acepta o rechaza una decisión de frontera de módulo.
> **Re-verificar con:** `ls backend/app/nucleo | wc -l`


- **Estado:** Propuesto (requiere ratificación del dueño en §9)
- **Fecha:** 2026-10-29
- **Autor:** `arquitectura`
- **Alcance:** define el destino *modular* del sistema actual (FastAPI + Next.js +
  PostgreSQL único). **No** autoriza migraciones, cutover ni cambios de código.
- **Relación con otros artefactos:** no repite ADR-0001 (coexistencia), ADR-0002 (retiro)
  ni `03-matriz-retiro-legacy.md` (inventario de `public`). Responde otra pregunta: cómo
  organizar el sistema cuando el legacy ya no sea la fuente de verdad, sin cambiar de estilo.

## 0. Cómo leer este documento

🟢 leído en código/migración con cita `archivo:línea` · 🟡 deducción razonable (se dice qué
la confirmaría) · 🔴 no determinable. Que un módulo exista **no** significa que esté terminado.

---

## 1. Principio rector: qué significa "modular" aquí

**Definición operativa.** Un módulo es un **dominio de negocio con cuatro cosas
propias**: (a) tablas que solo él escribe, (b) reglas y validaciones, (c) un contrato
HTTP estable, (d) pruebas que fallan si se rompe. Un módulo puede **leer** datos de
otro; no puede **escribir** sus tablas ni importar sus modelos para mutarlos.

**Qué NO significa:**

| No es | Por qué no |
|---|---|
| Microservicios | Un proceso, un despliegue, una base. No hay evidencia de necesidad de red entre dominios. |
| Un paquete Python por módulo | El repo ya usa `backend/app/nucleo/servicio_*.py` + `api_*.py` (`backend/app/api/router.py:17-29`). Reorganizar carpetas sin cambiar fronteras es cosmética. |
| Un schema PostgreSQL por módulo | `nucleo` ya es el destino (`supabase/migrations/0004_nucleo_operacional.sql:102-1881`). Multiplicar schemas multiplica migraciones y rompe FKs por empresa. |
| Una tabla por módulo | Hay tablas compartidas por diseño (§3.2). |
| Eventos / colas | Sin consumidor externo ni necesidad medida de desacoplar en el tiempo (§6.2). |

**La prueba de que una frontera es real** no es que exista un archivo con ese nombre: es
que exista **un solo escritor por tabla** y que el escritor ajeno esté prohibido por
contrato y detectable por revisión. Hoy se cumple a medias: `servicio_facturacion.py:586-609`
hace `update(Viaje)` e `insert(ViajeEvento)` — tablas de despacho y expediente — dentro de
su transacción. 🟢 Ese es exactamente el patrón que este documento prohíbe a futuro.

---

## 2. Fronteras de módulo propuestas (12 módulos)

Convención: "tablas que posee" = tablas cuyo **único escritor autorizado** es el módulo.
"Efectos" = qué cambia fuera de sus tablas. Cada encabezado cita la evidencia de
existencia.

### M01 — Identidad y empresa · `deps.py:43-82`, `permisos.py:15-172`

| | |
|---|---|
| **Responsabilidad** | Resolver quién es el usuario, a qué empresa pertenece y qué permisos tiene. |
| **Tablas** | `nucleo.empresas` (`0004:102`), `nucleo.usuarios_empresa` (`0004:139`) |
| **Endpoints** | `GET /nucleo/empresa` (`api.py:61`), `GET /nucleo/mis-empresas` (`api.py:69`), `/nucleo/permisos/mios` (`api_permisos.py:27`), `/permisos/matriz` (`:38`), `/permisos/verificar` (`:51`) |
| **Efectos** | Emite `ContextoEmpresa` (`deps.py:23-41`) que **todos** los módulos consumen como dependencia. Es el único módulo que puede afirmar `empresa_id`. |
| **Prohibido escribir** | Ningún módulo escribe `empresas` ni `usuarios_empresa`. Cambiar rol/permiso es operación sensible (AGENTS.md §9). |

### M02 — Maestros: flota, contrapartes, documentos · `servicio_maestros.py:83-500`

| | |
|---|---|
| **Responsabilidad** | Mantener la identidad operativa de clientes, tractos, ramplas y choferes, y la vigencia de sus documentos habilitantes. |
| **Tablas** | `nucleo.clientes` (`0004:158`), `tractos` (`:191`), `ramplas` (`:235`), `choferes` (`:282`), `documentos` (`:326`) |
| **Endpoints** | `/nucleo/clientes`, `/tractos`, `/ramplas`, `/choferes` (`api_maestros.py:57-194`), `GET/POST /nucleo/documentos` (`:205-247`) |
| **Efectos** | `documentos` alimenta `politicas.documentos_requeridos()` (`politicas.py:49-119`), que **bloquea despacho**; un documento nuevo desactiva el anterior (`fn_documento_vigente_unico`, `0004:1704`) y los documentos no se borran (`fn_documento_no_borrar`, `0004:1804`). |
| **Prohibido escribir** | Despacho y agenda **no** escriben `tractos`/`choferes`, solo leen. `tractos.km_actual` (`models.py:493`) **no se actualiza desde ningún servicio del núcleo** — ver D-05. |

### M03 — Comercial: tarifas, OC, centros de costo · `servicio_comercial.py:95-1217`

| | |
|---|---|
| **Responsabilidad** | Definir a qué precio se vende (tarifa) y contra qué autorización se factura (OC). |
| **Tablas** | `nucleo.tarifas` (`0004:377`), `ordenes_compra` (`:421`), `ordenes_compra_lineas` (`:459`), `centros_costo` (`0005:16`) |
| **Endpoints** | `/nucleo/tarifas` (`api_comercial.py:107-156`), `/nucleo/ordenes-compra` (`:167-300`), `/nucleo/centros-costo` (`:67-96`) |
| **Efectos** | El **consumo de OC** lo recalcula la base: `fn_oc_recalcular` (`0004:1550`) invocado por `trg_viajes_80_oc` (`0004:1850`). El sobregiro requiere aprobación explícita (`servicio_comercial.py:1083-1173`). |
| **Prohibido escribir** | Facturación **no** modifica `ordenes_compra`, solo lee saldo (`politicas.py:433-442`). Despacho no edita tarifas: las consume (`politicas.py:327-371`). |

### M04 — Despacho: viajes y máquina de estados · `servicio_disponibilidad.py:141-1511`

| | |
|---|---|
| **Responsabilidad** | Crear el viaje, asignarle recursos y gobernar su ciclo de vida. |
| **Tablas** | `nucleo.viajes` (`0004:542`), `nucleo.transiciones_viaje` (`0004:772`) |
| **Endpoints** | `POST /nucleo/viajes` (`api.py:95`), `GET /nucleo/viajes` (`:103`), `POST /nucleo/viajes/{id}/asignar` (`:178`), `POST /disponibilidad/validar-asignacion` (`:169`), `/nucleo/tarifas/opciones` (`:79`), `/ordenes-compra/opciones` (`:87`) |
| **Efectos** | Escribir `viajes` dispara seis triggers en orden (`0004:1832-1851`): ventana, validación, facturación, protección, transición, auditoría, reservas y OC. Un cambio de estado solo es válido si existe en `transiciones_viaje` (`fn_viaje_transicion`, `0004:1511-1547`). |
| **Prohibido escribir** | **Ningún módulo hace `UPDATE nucleo.viajes` directo.** Cambiar estado = pasar por la máquina de estados. Hoy facturación lo viola (`servicio_facturacion.py:586-594`). |

### M05 — Disponibilidad y agenda: libro único de ocupación · `servicio_bloqueos.py:62-444`

| | |
|---|---|
| **Responsabilidad** | Ser el único libro de verdad de "qué recurso está ocupado en qué ventana", sea por viaje, mantención, descanso o bloqueo. |
| **Tablas** | `nucleo.reservas_recurso` (`0004:703`) |
| **Endpoints** | `GET /nucleo/disponibilidad/recursos` (`api.py:122`), `.../libre-desde` (`:150`), `/nucleo/bloqueos` (`api_bloqueos.py:40-77`), `GET /nucleo/agenda` (`:86`) |
| **Efectos** | Tres `EXCLUDE` impiden solapamiento de tracto, rampla y chofer **en la base** (`0004:744-757`); `fn_reserva_no_borrar` (`0004:1692`) impide borrar reservas; `fn_reserva_validar` (`0004:1653`) exige coherencia con el viaje. |
| **Prohibido escribir** | Despacho **no inserta reservas de viaje**: las crea el trigger `fn_viaje_reservas` (`0004:1621-1650`). Agenda **sí** inserta reservas no-viaje (`servicio_bloqueos.py:233`). Nadie borra. |

### M06 — Expediente y POD: ejecución documental · `servicio_pod.py:54-373`

| | |
|---|---|
| **Responsabilidad** | Registrar lo que ocurre durante el viaje (paradas, checklist, eventos, incidentes, documentos) y su prueba de entrega. |
| **Tablas** | `nucleo.viaje_paradas` (`0007:17`), `viaje_checklist` (`:63`), `viaje_eventos` (`:102`), `viaje_incidentes` (`:139`), `viaje_documentos` (`:181`), `nucleo.pod` (`0009:8`) |
| **Endpoints** | `/nucleo/expediente/viajes` (`api_expediente.py:50-263`), `GET/POST/PUT /nucleo/expediente/viajes/{id}/pod` (`api_pod.py:35-87`) |
| **Efectos** | `POST /nucleo/expediente/viajes/{id}/cerrar` (`api_expediente.py:89`) mueve el viaje a `cerrado`, habilitando facturación. El POD es requisito de `pod_pendiente → cerrado` (`0004:805`). |
| **Prohibido escribir** | Otros módulos **no insertan `viaje_eventos`**. Hoy facturación lo hace (`servicio_facturacion.py:599-609`); el destino es que pida el evento a este módulo. |

### M07 — Gastos y combustible · `servicio_gastos.py:64-437`

| | |
|---|---|
| **Responsabilidad** | Registrar y aprobar el costo real del viaje, con su respaldo y su precio de combustible. |
| **Tablas** | `nucleo.viaje_gastos` (`0011:29`), `nucleo.precios_diesel` (`0011:11`) |
| **Endpoints** | `/nucleo/combustible/precios` (`api_gastos.py:48`), `/combustible/precio-vigente` (`:55`), gastos del viaje (`:76-103`), `aprobar`/`rechazar` (`:120-129`) |
| **Efectos** | Solo gastos **aprobados** entran al costo (`servicio_alertas.py:374-378`); el comprobante va a Storage (§5.3). |
| **Prohibido escribir** | Rentabilidad **no** escribe gastos, solo los lee (`servicio_rentabilidad.py:179-294`). |

### M08 — Facturación y cobranza · `servicio_facturacion.py:62-712`

| | |
|---|---|
| **Responsabilidad** | Emitir la factura de viajes cerrados, aplicar pagos y notas de crédito, y medir la deuda. |
| **Tablas** | `nucleo.facturas_nucleo` (`0013:10`), `factura_viajes` (`:54`), `pagos_nucleo` (`:78`), `notas_credito_nucleo` (`:112`), `promesas_pago_nucleo` (`:139`) |
| **Endpoints** | `/nucleo/cobranza/viajes-facturables` (`api_facturacion.py:48`), `/facturas` (`:59,89`), `POST /facturas` (`:79`), `/pagos` (`:97`), `/notas-credito` (`:106`), `/promesas` (`:115`), `/aging` (`:124`) |
| **Efectos** | Consume folio de `nucleo.siguiente_folio(empresa,'FAC',periodo)` (`servicio_facturacion.py:548-556`), que escribe `nucleo.folio_contador` (`0004:490`). La nota de crédito es el mecanismo de corrección; **no hay borrado ni anulación destructiva** (AGENTS.md §3.16). |
| **Prohibido escribir** | No escribe `viajes` (debe pedir la transición a M04), ni `viaje_eventos` (M06), ni `ordenes_compra` (M03). |

### M09 — Rentabilidad y costos · `servicio_rentabilidad.py:81-416`

| | |
|---|---|
| **Responsabilidad** | Calcular margen por viaje y simular fletes con los parámetros de costo de la empresa. |
| **Tablas** | `nucleo.configuracion_costos` (`0012:8`) |
| **Endpoints** | `GET/PUT /nucleo/rentabilidad/configuracion` (`api_rentabilidad.py:38,45`), `POST /nucleo/rentabilidad/simulador` (`:53`), `GET /nucleo/rentabilidad/viajes/{id}` (`:61`) |
| **Efectos** | Ninguno sobre otros módulos: es **consumidor puro** de viajes, gastos y pagos. Persiste `freight_score` en `viajes.freight_score_estimado` (leído en `servicio_alertas.py:335`) — escritura que hoy hace vía despacho (D-06). |
| **Prohibido escribir** | No escribe tablas ajenas. Si necesita persistir un resultado, se lo pide a M04. |

### M10 — Auditoría y cumplimiento · `servicio_auditoria.py:25-95`

| | |
|---|---|
| **Responsabilidad** | Registrar de forma inmutable quién cambió qué, y exponer el rastro. |
| **Tablas** | `nucleo.auditoria` (`0004:813`) |
| **Endpoints** | `GET /nucleo/auditoria` (`api_permisos.py:73`), `GET /nucleo/auditoria/tablas` (`:97`) |
| **Efectos** | `fn_auditoria()` (`0004:830`) escribe en 29 puntos de trigger; `trg_auditoria_no_update` (`0004:890`) hace la tabla append-only. |
| **Prohibido escribir** | **Ningún módulo hace INSERT/UPDATE/DELETE en `auditoria`.** Solo la función `security definer` del trigger. Escribir auditoría "a mano" duplica el mecanismo. |

### M11 — Alertas y tablero · `servicio_alertas.py:56-482`

| | |
|---|---|
| **Responsabilidad** | Responder "¿qué requiere atención hoy?" agregando señales de los demás módulos. |
| **Tablas** | **Ninguna propia.** |
| **Endpoints** | `GET /nucleo/alertas/tablero` (`api_alertas.py:24`) |
| **Efectos** | Ninguno. Es lectura agregada. |
| **Prohibido escribir** | No escribe nada, en ninguna tabla. Si necesita un dato nuevo, se lo pide al módulo dueño. |
| **Riesgo actual** | Lee 9 tablas de 6 módulos e **importa `ServicioFacturacion`** (`:40`): es el módulo más acoplado y el primer candidato a interfaces de lectura (§3.3, D-10). |

### M12 — Cutover (**transitorio**) · `servicio_cutover.py:21-138`

| | |
|---|---|
| **Responsabilidad** | Congelar escrituras legacy mientras `public` siga existiendo. |
| **Tablas** | `nucleo.cutover_control` (`0014:8`) |
| **Endpoints** | `GET /nucleo/cutover/estado` (`api_cutover.py:31`), `POST /congelar` (`:38`), `POST /descongelar` (`:46`) |
| **Efectos** | `main.py:36-61` bloquea todo verbo no-GET fuera de `/nucleo` y `/auth` cuando el flag está activo. |
| **Prohibido escribir** | Nadie más escribe `cutover_control`. |
| **Ciclo de vida** | **Se elimina** al cerrar G0.4 de ADR-0002 (`ADR-0002:293`). No es un módulo permanente del destino. |

**Nota sobre el canal conductor.** La PWA del conductor (`api_conductor.py:20-57`,
`servicio_conductor.py:73-289`) **no es un módulo**: es una *fachada* de M04/M06/M07 para
el rol `conductor:usar` (`permisos.py:39`). Tratarla como módulo crearía una segunda
puerta de escritura a `viajes`.

---

## 3. Contrato entre módulos

### 3.1 Regla

Un módulo llama a otro **por su servicio Python, con interfaz explícita**, y solo para
*pedir una operación*, nunca para mutar su estado interno. Lo que se prohíbe:

| Prohibido | Por qué | Detección |
|---|---|---|
| Importar el **modelo** ajeno y hacer `session.add`/`update` | Salta reglas y auditoría del dueño | `grep -n "update(Viaje)\|Viaje(" backend/app/nucleo/servicio_facturacion.py` |
| Escribir tabla ajena desde el servicio | Rompe el "único escritor" | revisión de diff por tabla |
| Duplicar una validación que ya vive en el dueño | Dos reglas que divergen | dos `if` con el mismo nombre de regla |

### 3.2 Lo que **sí** se comparte (y por qué no es violación)

1. **`ContextoEmpresa`** (`deps.py:23`): el `empresa_id` se resuelve en M01 desde
   `X-Empresa-ID` + membresía (`deps.py:44,55-66`) y **nunca** desde el body. Es el
   contrato transversal de tenancy.
2. **`errores.py`** (`errores.py:135-190`): un solo lugar decide que `23P01 → 409` y
   `23505 → 409`. Si cada módulo traduce a su manera, el frontend recibe códigos
   inconsistentes.
3. **`auditoria`**: se comparte *el mecanismo* (trigger), no la tabla. Cada módulo obtiene
   auditoría por escribir sus propias tablas.
4. **`nucleo.folio_contador`** (`0004:490`): **primitiva compartida**, no propiedad de un
   módulo. La consumen despacho (`'VJ'`, `0004:943`) y facturación (`'FAC'`,
   `servicio_facturacion.py:550`). Pertenece a la infraestructura de datos, igual que
   `siguiente_folio` (`0004:498`). Ningún módulo la escribe directo.
5. **`reservas_recurso`**: excepción deliberada (§3.4).
6. **Lectura cruzada**: leer tablas ajenas para un listado o un KPI es legítimo. Se
   prohíbe **escribir**. M11 lo hace hoy sin interfaz; el destino es que use consultas
   nombradas y documentadas, no acceso libre a los modelos.

### 3.3 Interfaces de lectura

Cuando un módulo necesita datos de otro para *decidir*, no para *mostrar*, se expone una
función con nombre de dominio y firma estable:

- `M03.saldo_disponible_oc(oc_id) -> Decimal` — en vez de que M08 reimplemente parte de
  la regla (`servicio_facturacion.py:462-529`).
- `M04.viaje_por_id(...)` con `lock=True` — patrón ya existente
  (`servicio_disponibilidad.py:785`); evita que cada módulo haga su propio `SELECT`.
- `M07.costo_aprobado_viaje(viaje_id) -> Decimal` — en vez de que M09 y M11 consulten
  `viaje_gastos` por su cuenta (`servicio_alertas.py:374`, `servicio_gastos.py:437`).

### 3.4 La excepción: `reservas_recurso` y su trigger

`fn_viaje_reservas` (`0004:1621-1650`) hace que **escribir `viajes` mantenga el libro de
ocupación**. Es una escritura cruzada de M04 sobre una tabla de M05, y es **correcta**
porque: (1) ocurre **en la misma transacción** que el cambio de estado, sin ventana de
inconsistencia; (2) garantiza que *todo* viaje operativo tenga reserva, incluso si un
servicio nuevo lo olvida; (3) está auditada (`trg_reservas_audit`, `0004:1861`) y validada
(`fn_reserva_validar`, `0004:1653`).

La regla, entonces: **la escritura cruzada entre módulos se permite únicamente si vive en
un trigger de PostgreSQL, en la misma transacción, y con auditoría.** En Python, no. La
asimetría es intencional: la base no se puede saltar con un `if` mal escrito.

---

## 4. Fuente de verdad por dominio

Criterio: **una tabla canónica por concepto**. "Legacy que la duplica" lista la tabla de
`public` que guarda el mismo concepto; si está vacía, no hay duplicado.

| Dominio | Tabla canónica (`nucleo`) | Quién escribe | Quién lee | Legacy que la duplica | ¿Dos fuentes vivas? |
|---|---|---|---|---|---|
| Empresa | `nucleo.empresas` | M01 | Todos | — (no existe en `public`) | No |
| Usuario | `nucleo.usuarios_empresa` | M01 | M01 | `public.usuarios` + `handle_new_user` | **Sí** 🔴 D-01 |
| Cliente | `nucleo.clientes` | M02 | M03, M04, M08 | `public.clientes` (`0001:47`) | **Sí** 🟢 |
| Chofer | `nucleo.choferes` | M02 | M04, M05, M07 | `public.choferes` (`0001:60`) | **Sí** 🟢 |
| Tracto | `nucleo.tractos` | M02 | M04, M05, M11 | `public.tractos` (`0001:72`) | **Sí** 🟢 |
| Rampla | `nucleo.ramplas` | M02 | M04, M05 | `public.ramplas` (`0001:86`) | **Sí** 🟢 |
| Documento | `nucleo.documentos` | M02 | M04, M11 | — | No |
| Tarifa | `nucleo.tarifas` | M03 | M04, M08 | — | No |
| OC | `nucleo.ordenes_compra` (+`_lineas`) | M03 | M04, M08, M11 | — | No |
| Viaje | `nucleo.viajes` | M04 (estado: máquina de estados) | M06, M07, M08, M09, M11 | `public.viajes` (`0001:97`) | **Sí** 🟢 |
| Reserva / bloqueo | `nucleo.reservas_recurso` | M05 + trigger `0004:1621` | M04, M11 | — (`public` no tiene libro) | No |
| Gasto | `nucleo.viaje_gastos` | M07 | M09, M11 | `public.gastos_viaje` (`0001:114`) | **Sí** 🟢 |
| Factura | `nucleo.facturas_nucleo` | M08 | M08, M11 | `public.facturas` (`0001:127`) | **Sí** 🟢 |
| Vínculo factura↔viaje | `nucleo.factura_viajes` | M08 | M11 | `public.factura_viaje` (`0001:145`) | **Sí** 🟢 |
| Pago | `nucleo.pagos_nucleo` | M08 | M08, M09, M11 | **Sin tabla**; legacy usa `facturas.fecha_pago`+`estado` (`0001:137-138`) | No (legacy no expresa pagos parciales) |
| Nota de crédito | `nucleo.notas_credito_nucleo` | M08 | M08 | — | No |
| POD | `nucleo.pod` | M06 | M11 | — | No |
| Evento de viaje | `nucleo.viaje_eventos` | M06 | M06, M11 | — | No (pero M08 escribe hoy) |
| Liquidación | **ninguna**: solo `public.liquidaciones` (`0001:171`) | legacy `liquidaciones.py:243-504` | legacy | — | No, pero **fuente única legacy** 🔴 |
| Mantención | **ninguna**: `public.pautas_mantenimiento` (`0001:189`) + `public.mantenimientos` (`0001:199`) | legacy `mantenimiento.py:28-158` | legacy | — | No, pero **dos conceptos homónimos**: `reservas_recurso.tipo_reserva='mantenimiento'` (`0004:68`) es *agenda*, no *historial* 🔴 |
| Configuración | `public.configuracion` (`0001:212`) | legacy `configuracion.py:23` | `settings_db.py:5-16` | `nucleo.configuracion_costos` (`0012:8`) = parámetros **de rentabilidad**, no globales | **Sí, por concepto partido** 🔴 D-07 |
| Parámetro IVA | `public.configuracion.iva_porcentaje` | legacy | `finanzas.py:133`, `facturas.py:36` | `nucleo.facturas_nucleo.iva` = **monto calculado**, no parámetro | No es duplicado; el **parámetro** vive en legacy 🔴 |
| KPI | `public.kpis` (`0003:5`) | legacy `kpis.py:141` | legacy | `nucleo.viajes.freight_score_estimado` = métrica distinta | No, pero dos "KPIs" con dueños distintos 🟡 |
| Auditoría | `nucleo.auditoria` | trigger | M10 | — (`public` sin equivalente) | No |

**Lectura de la tabla.** Los dominios con **dos fuentes vivas** son exactamente los
maestros, el viaje, el gasto y la factura: los cuatro que `03-matriz-retiro-legacy.md` §2
ya clasificó. **Ninguno** de los dos lados es "solo lectura": `public.viajes`,
`public.gastos_viaje` y `public.facturas` siguen recibiendo escrituras por sus routers
(`viajes.py:152-253`, `gastos.py:55`, `facturas.py:101-241`). Mientras el cutover no
congele, hay dos escritores reales. Eso **no lo resuelve este documento**: lo resuelve
ADR-0002 con sus cuatro puertas.

---

## 5. Orquestación

### 5.1 Qué significa "orquestado" aquí

**Orquestado = un caso de uso transversal se ejecuta en una sola transacción, con un
responsable explícito y con efectos externos compensados.** No es coreografía de eventos:
no hay bus, no hay consumidor asíncrono, no hay estado eventual. Consecuencia práctica:
**cada caso de uso transversal tiene un módulo dueño** (el que tiene la regla principal)
que coordina a los demás **en su propia transacción**.

### 5.2 Casos de uso transversales y su dueño

| Caso de uso | Dueño | Módulos que toca | Mecanismo real hoy |
|---|---|---|---|
| Crear viaje con tarifa y OC | M04 | M03, M05 (reserva vía trigger), M10 | `servicio_disponibilidad.crear_viaje` (`:869`) + `trg_viajes_70_reservas` |
| Asignar tracto/rampla/chofer | M04 | M02 (documentos), M05 (EXCLUDE), M10 | `confirmar_asignacion` (`servicio_disponibilidad.py:1411`) con `SELECT ... FOR UPDATE` (`:1397`) y `EXCLUDE` como última defensa (`api.py:184-188`) |
| Cerrar viaje con POD | M06 | M04 (transición), M10 | `api_expediente.py:89` + `fn_viaje_transicion` |
| Aprobar gasto | M07 | M10 | `servicio_gastos.py:346-388` |
| Facturar viajes cerrados | **M08** | M03 (saldo OC), M04 (estado), M06 (evento), M10 | `crear_factura` (`servicio_facturacion.py:530-618`) — **una transacción**, hoy escribiendo tablas ajenas |
| Registrar pago | M08 | M10 | `registrar_pago` (`:620`) |
| Calcular rentabilidad | M09 | M04, M07, M08 (solo lectura) | `rentabilidad_viaje` (`:323`) |

### 5.3 Transacción y efectos externos

`get_session()` (`core/database.py:27-29`) entrega una `Session` sin gestor de
transacción: **cada método de servicio hace su propio `commit()`** (p. ej.
`servicio_disponibilidad.py:1511`, `servicio_facturacion.py:610`,
`servicio_gastos.py:301`). Dos consecuencias que el destino asume explícitamente:

1. **Un caso de uso = un método = un commit.** No se puede componer "dos servicios, un
   commit" sin refactor. Por eso la orquestación vive **dentro** del módulo dueño.
2. **Los archivos no son transaccionales.** `servicio_maestros.py:435-474` sube a Storage
   **antes** del commit y borra el archivo si la transacción falla (compensación en
   proceso). Es el patrón correcto mientras no haya cola: **efecto externo primero,
   compensación en el `except`**. Debe exigirse igual a POD y comprobantes (D-08).

**Regla:** ningún módulo abre una transacción que abarque a otro módulo *y* un efecto
externo. Si el efecto externo falla después del commit, se resuelve con una tarea de
limpieza, no con un rollback imposible.

---

## 6. Escalabilidad

### 6.1 Qué se puede escalar **hoy**, sin rediseño

| Técnica | Estado / condición |
|---|---|
| Índices por consulta real | Ya hay 8 índices en `viajes` y 3 en `reservas_recurso` (`0004:691-698`, `0004:763-767`) |
| Réplicas de lectura para M11 y M09 | Viable: son consumidores puros y toleran latencia (`servicio_alertas.py`, `servicio_rentabilidad.py` no escriben) |
| Partición por fecha de `nucleo.auditoria` | Viable: `ocurrido_en` es `timestamptz` indexado (`0004:828`) y la tabla es append-only (`0004:890`). Requiere migración `PARTITION BY RANGE` |
| Partición por fecha de `nucleo.viajes` | **No todavía**: hay FKs entrantes desde 5 tablas (`0004:721-728`, `0007:17-181`, `0013:54`) |
| Réplicas del proceso API | Viable: el estado está en PostgreSQL. Excepción: el caché de cutover (`servicio_cutover.py:17-41`) es por proceso, TTL 5 s |
| Connection pooling | Necesario antes de escalar réplicas; el engine se crea una vez (`database.py:21-24`) |

### 6.2 Qué se difiere, y **qué evidencia** lo justificaría

| Diferido | Evidencia que lo justificaría | Por qué no ahora |
|---|---|---|
| Cola de mensajes | Un efecto externo que deba reintentarse solo (p. ej. envío de DTE al SII) con volumen medido y fallos registrados | Hoy los efectos externos son de Storage y se compensan en proceso |
| Event sourcing | Requisito de reconstruir estado a una fecha arbitraria **que la auditoría no cubra** | `nucleo.auditoria` ya guarda `datos_antes`/`datos_despues` (`0004:819-820`) |
| CQRS con proyecciones | Latencia de lectura medida que una réplica + índice no resuelvan | No hay medición de latencia en el repo |
| Microservicios | Un módulo con **equipo, ciclo de despliegue y pico de carga** distintos, medido | Un solo equipo; un solo despliegue |
| Worker separado | Tarea > 30 s que hoy bloquee una request | Las operaciones actuales son interactivas |

**Regla de adopción:** una de estas técnicas se adopta solo con (a) una medición
reproducible del límite, (b) el coste de operación declarado, (c) plan de rollback. Sin
(a), la respuesta es índice o consulta, no infraestructura.

---

## 7. Reglas de evolución

### 7.1 Agregar un módulo nuevo

1. **Nombrar el dominio y su tabla canónica.** Si el concepto ya existe en otro módulo, no
   se crea tabla: se extiende el dueño.
2. **Declarar sus permisos** en `TODOS_LOS_PERMISOS` (`permisos.py:15-44`) y
   `ROLES_PERMISOS` (`:58-139`). Un endpoint sin permiso declarado no se acepta
   (deny-by-default, AGENTS.md §9).
3. **Declarar sus tablas con `empresa_id`**, FK compuesta por empresa, triggers `touch` +
   `version` + `audit` (patrón de `0004:1756-1862`).
4. **Exponer `servicio_<dominio>.py` + `api_<dominio>.py`** montado en `router.py`. No se
   importa el modelo de otro módulo para escribir.
5. **Escribir la prueba que falla si se retira el mecanismo** (mutación). Sin eso el
   módulo no está terminado, está escrito.

### 7.2 Retirar un módulo

No se decide aquí. Se rige por `adr/ADR-0002-retiro-del-legacy.md` §B.2: cuatro puertas
(P1 paridad con prueba, P2 datos reconciliados, P3 cero referencias vivas, P4
reversibilidad con ventana). Un módulo **no se borra por estar "viejo"**: se retira cuando
deja de recibir escrituras y las puertas están cerradas con salida registrada.

### 7.3 Evitar una tercera fuente de verdad

Tres controles, en orden de fuerza:

1. **Constraint en la base.** Si dos tablas pueden contradecirse, falta un `UNIQUE`, una
   FK compuesta o un `EXCLUDE`. Ejemplo correcto: `reservas_recurso` (`0004:744-757`).
2. **Un solo escritor por tabla**, verificable con `grep` del nombre de la tabla en
   `backend/app/`. Si aparece en dos servicios, se justifica o se unifica.
3. **Revisión de contrato.** Todo endpoint nuevo declara qué tabla escribe y qué módulo es
   su dueño. Sin esa declaración, no pasa revisión.

Un cuarto control, cuando el dato se duplica por rendimiento (snapshot): se declara
**inmutable y con fecha de origen**, como `oc_numero_snapshot` (`0004:1501-1504`), y nunca
se recalcula.

---

## 8. Deuda estructural reconocida

| ID | Deuda | Evidencia | Impacto | Se paga cuando |
|---|---|---|---|---|
| D-01 | **RLS sin políticas en `nucleo`**: el aislamiento por empresa vive solo en el backend | 44 `enable row level security` sin un `create policy` en `nucleo`; el único `create policy` es `public.usuarios` (`0001:284`). `0004:1865` declara el diseño: *"el backend entra con service_role/postgres; anon/authenticated no ven nada"* 🟢 | RLS es **perímetro**, no aislamiento multiempresa. Un bug de `empresa_id` en un servicio no lo detiene la base | Se decida si el rol de aplicación deja de ser `bypassrls` y se escriben políticas por `empresa_id`. **Dueño + `auditor-seguridad`** |
| D-02 | **Rol `postgres` con `bypassrls`** | Contexto verificado de la sesión; coherente con `0004:1865` 🟢 | Toda política futura sería inerte mientras el rol no cambie | Junto con D-01 |
| D-03 | **Legacy sin auditoría** | 29 triggers `fn_auditoria` en `nucleo`; **cero** en `public` | Escrituras legacy no dejan rastro; una divergencia no es investigable | Se paga con el retiro (ADR-0002), no antes |
| D-04 | **Doble cliente HTTP** | `api.ts:5-60` (sin `X-Empresa-ID`, sin `codigo` de error) vs `nucleo.ts:25-106` (con ambos). 12 páginas usan `api`, 11 usan `nucleo` | Dos manejadores de error; el legacy no reporta `codigo` de dominio | Se retira `api.ts` con el último módulo legacy (ADR-0002) |
| D-05 | **`tractos.km_actual`/`horas_motor` sin alimentador en el núcleo** | Campos existen (`models.py:493-494`); `grep km_actual` en `backend/app/nucleo/` → solo modelo y schema | Mantenimiento por km no puede migrar sin un origen de odómetro | Se decida cómo se captura el km (P-5) |
| D-06 | **Escrituras cruzadas desde facturación** | `servicio_facturacion.py:586-609` hace `update(Viaje)` + `insert(ViajeEvento)` | Viola §3.1; si M04 cambia su máquina de estados, facturación se rompe en silencio | Al implementar la interfaz de §3.3 |
| D-07 | **Configuración partida en dos lugares** | `public.configuracion` (global, `0001:212`) + `nucleo.configuracion_costos` (rentabilidad, `0012:8`) | Nadie sabe cuál es "la" configuración; un parámetro nuevo puede ir a cualquiera | Se decida el dueño de la configuración global (P-4) |
| D-08 | **POD y comprobantes: efecto externo antes del commit** | `servicio_maestros.py:435-474` compensa; el patrón debe replicarse en POD (`servicio_pod.py`) | Archivo huérfano si el proceso muere entre upload y commit | Se documente y pruebe la compensación en ambos |
| D-09 | **`licencias_permitidas` deprecado pero visible** | Vivo en `models.py:495` y expuesto en `schemas.py:420`; R-02 fija A5 como única clase válida (`politicas.py:297-322`; `test_nucleo_politicas.py:136-152`) | Un cliente podría creer que configura licencias; no tiene efecto | Se retire del contrato HTTP (expand/contract) |
| D-10 | **M11 acoplado a 6 módulos e importa un servicio ajeno** | `servicio_alertas.py:40` importa `ServicioFacturacion`; lee 9 tablas | Cambiar cualquier módulo puede romper el tablero | Al definir las interfaces de lectura (§3.3) |
| D-11 | **Estado `anulada` de factura sin transición** | `facturas_nucleo.estado` admite `anulada`; se lee en 5 guardas (`servicio_facturacion.py:215,622,657,697,714`) pero **ningún endpoint lo asigna** | Estado alcanzable solo por SQL manual: riesgo de inconsistencia | Se decida si existe anulación o solo nota de crédito (P-2) |

---

## 9. Decisiones: técnica vs. dueño

### 9.1 Decisiones **técnicas** de este documento (mías, reversibles)

| # | Decisión | Alternativa descartada | Por qué |
|---|---|---|---|
| T-1 | 12 módulos | Un módulo por archivo `servicio_*` (20) | `servicio_*` no es unidad de negocio: `servicio_disponibilidad` cubre viajes **y** disponibilidad, dos responsabilidades |
| T-2 | `viajes` es de M04; el estado solo cambia por la máquina de estados | Que cada módulo haga su `UPDATE` | Sin esto, D-06 se reproduce en cada módulo nuevo |
| T-3 | Facturación y cobranza son **un** módulo | Dos módulos (facturar / cobrar) | El saldo (`total - pagos - notas`) es un invariante único; partirlo crea dos fuentes de verdad para el mismo número |
| T-4 | `reservas_recurso` es de M05; el trigger de `viajes` es escritura sancionada | Que M04 inserte reservas desde Python | El trigger garantiza la reserva aunque un servicio nuevo lo olvide |
| T-5 | El conductor es una fachada, no un módulo | Un módulo "PWA" | Evita una segunda puerta de escritura a `viajes` |
| T-6 | Orquestación = transacción en el módulo dueño | Coreografía de eventos | No hay consumidor asíncrono ni necesidad medida |

### 9.2 Decisiones del **dueño** (no las puedo tomar yo)

| # | Pregunta | Por qué es del dueño | Bloquea |
|---|---|---|---|
| P-1 | ¿Se retiran liquidaciones, mantenimiento, IVA/F29 y export CSV, o se migran al núcleo? | Alcance de producto, no de arquitectura | 4 de las 12 fronteras |
| P-2 | ¿Existe anulación de factura, o solo nota de crédito? | Regla tributaria/comercial (validar con contador) | D-11 |
| P-3 | ¿El aislamiento multiempresa debe imponerse en la base (RLS con rol sin bypass)? | Coste operativo y riesgo de romper el backend actual | D-01, D-02 |
| P-4 | ¿Dónde vive la configuración global (IVA, parámetros) en el destino? | Define la fuente de verdad de un dato tributario | D-07 |
| P-5 | ¿Se captura odómetro/km para mantenimiento desde el núcleo? | Define si mantenimiento puede migrar | D-05 |

---

## 10. Lo que este documento **no** afirma

- **No** afirma que el legacy se pueda borrar: eso lo deciden las cuatro puertas de
  ADR-0002 con salida registrada.
- **No** afirma que los 12 módulos estén implementados o probados. Existencia de archivo ≠
  módulo terminado.
- **No** afirma que el sistema escale a un volumen dado: no hay medición de carga en el
  repo. Las técnicas de §6.1 son viables, no probadas.
- **No** resuelve la divergencia actual `public`/`nucleo`: la nombra en §4 y la deja donde
  corresponde (ADR-0002).
- **No** define reglas tributarias, laborales ni de comisión: las preguntas están en §9.2
  con su destinatario.
- 🔴 **No verificado en esta sesión:** rol efectivo de `DATABASE_URL` (no se leyó el
  valor), filas reales en `public` vs `nucleo`, latencia de consultas, comportamiento del
  pooler de Supabase, y si el frontend puede prescindir de `api.ts` hoy. Requiere `datos` +
  `qa` con base local arriba.
