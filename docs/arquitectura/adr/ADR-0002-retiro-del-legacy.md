# ADR-0002: Retiro del legacy `public` — definición operativa de "basura" y plan por módulo

- **Estado:** Propuesto
- **Fecha:** 2026-10-29
- **Decide:** agente `arquitectura` (propuesta técnica). Requiere aceptación del
  dueño para las decisiones marcadas **D-08…D-12**.
- **Relación con ADR-0001:** lo **continúa**. ADR-0001 fija cómo conviven hoy los
  dos esquemas (puerta única por módulo, matriz `módulo → esquema canónico`). Este
  ADR fija **el estado final** —`public` retirado— y **sustituye el §B.3 de
  ADR-0001** (cuatro condiciones de cierre) por las cuatro puertas de §"Decisión",
  que son más estrictas y observables. El "registro de módulos" que ADR-0001
  propone como mecanismo de transición **no sobrevive al final**: existe solo
  mientras quede al menos un módulo duplicado y muere con el último. No se
  convierte en una dependencia permanente.
- **Documentos relacionados:** `docs/arquitectura/retiro-legacy.md`
  (inventario por módulo), `docs/arquitectura/destino-modular.md` (estado
  final), `docs/arquitectura/matriz-plan-vs-codigo.md`,
  `docs/arquitectura/alcance-piloto.md`.

---

## Contexto

Hechos verificados en esta sesión (2026-10-29) **por lectura estática**. En esta
sesión no tuve permiso de ejecución de shell: **no ejecuté pruebas, consultas ni
comandos**. Todo lo que dependa de comportamiento en ejecución está marcado 🟡 o
🔴 y no se usa como prueba de nada. Los resultados de suite y E2E citados abajo
son **reportados por el orquestador**, no reproducidos por mí.

### 1. El legacy no es "una pantalla vieja": es una segunda implementación completa

`backend/app/api/router.py:32-43` monta 12 routers legacy (auth, catálogos,
viajes, gastos, dashboard, facturas, finanzas, mantenimiento, liquidaciones,
configuración, export, kpis). `:44-56` monta 13 routers del núcleo. Ambos viven
en el mismo proceso y comparten el mismo pool de conexiones. 🟢

Los dos esquemas están duplicados concepto por concepto: `public.clientes`
(`0001:47-58`) vs `nucleo.clientes` (`0004:158-186`), `public.viajes`
(`0001:97-112`) vs `nucleo.viajes` (`0004:542`), `public.facturas`
(`0001:127-143`) vs `nucleo.facturas_nucleo` (`0013:10-38`). No existe vista,
trigger cruzado ni job que los reconcilie. 🟢 (ADR-0001 §Contexto 1, sin cambios.)

### 2. Cuatro capacidades siguen existiendo **solo** en legacy

Verificado por routers, no por documentación:

| Capacidad | Rutas legacy | Equivalente en `nucleo` |
|---|---|---|
| Liquidaciones / comisiones / anticipos / ajustes | `liquidaciones.py:65-504` | **No existe**. `grep -i "liquidacion"` en `backend/app/nucleo/` → 0 resultados 🟢 |
| Mantenimiento por km (pautas + historial) | `mantenimiento.py:28-228` | **No existe**. `nucleo` solo bloquea agenda (`TipoReserva.mantenimiento`, `models.py:187`) y alerta bloqueos (`servicio_alertas.py:172`) 🟢 |
| IVA / F29 | `finanzas.py:116-185` | **No existe**. `nucleo` guarda `iva` por factura y por gasto, pero no hay módulo de IVA 🟢 |
| Export CSV / import de planillas | `export.py:49-272` | **No existe** 🟢 |

Consecuencia: un "borrar `public` hoy" no es un retiro, es apagar cuatro
funciones que la empresa usa. 🟢

### 3. Hay dependencias transversales que no son "módulos" y rompen todo si se borran

Esto no estaba en ADR-0001 y es la razón principal por la que el retiro no puede
planificarse como "lista de routers":

1. **`public.usuarios` es la identidad de toda la aplicación, no un dato legacy.**
   `backend/app/api/deps.py:15-17` resuelve el usuario autenticado leyendo
   `public.usuarios` por `auth_id`. `frontend/src/context/auth-context.tsx:59`
   llama `GET /auth/me` en **cada carga de la app**, incluidas las pantallas del
   núcleo. Además, el trigger `public.handle_new_user` (`0001:248-262`) inserta
   una fila en `public.usuarios` en **cada alta de Supabase Auth**. Borrar
   `public.usuarios` sin reemplazo deja el login sin perfil, `/auth/me` en 401 y
   el alta de usuarios rota. 🟢
2. **El middleware de congelamiento define el perímetro de "legacy" por prefijo
   de ruta**, no por módulo: todo lo que no empiece con `/nucleo` ni `/auth` es
   legacy (`backend/app/main.py:45-50`). Al retirar routers, el flag
   `nucleo.cutover_control` (`0014:8-19`) pierde destinatario gradualmente y
   queda como configuración muerta. 🟢
3. **`nucleo` lee `public.viajes` en tiempo de ejecución.**
   `servicio_cutover.py:62-75` cuenta viajes abiertos legacy dentro de
   `ServicioCutover.estado()`. Es la única lectura cruzada del backend
   (`grep "public\." backend/` → 1 resultado) y es un bloqueo duro para borrar
   `public.viajes`. 🟢
4. **`public.configuracion` guarda un parámetro tributario.**
   `core/settings_db.py:5-16` lee `iva_porcentaje` de `public.configuracion`
   (`0001:290-293`), usado por `finanzas.py:133`, `facturas.py:36` y
   `kpi_engine.py:401`. `nucleo.configuracion_costos` (`0012:8-25`) **no tiene**
   columna de IVA. Borrar esa fila es borrar una regla tributaria, no "basura". 🟢
5. **El rol legacy es más grueso que el del núcleo y concede escritura de más.**
   `seed_local.py:101-110` mapea 8 roles del núcleo a 3 roles legacy
   (`auditor → operacion`, `conductor → operacion`, `taller → operacion`).
   Los routers legacy autorizan escritura con `require_roles(admin, operacion)`
   (`catalogos.py:21`, `viajes.py:34`, `mantenimiento.py:22`), mientras que en el
   núcleo `auditor` es solo lectura (`permisos.py:132-138`). **Hoy el legacy es
   una vía de escalada de privilegio** para auditor, conductor y taller. 🟢
   Retirarlo no es solo limpieza: cierra un defecto de autorización.

### 4. El cutover actual no puede sostener el retiro

- `scripts/cutover_legacy.py:268-288` migra **solo** viajes en estados abiertos;
  los `finalizado`/`facturado` se omiten por diseño (`ESTADOS_LEGACY_ABIERTOS`,
  `:30-40`). El histórico operativo y financiero **no se migra**. 🟢
- Los viajes migrados se insertan siempre `confirmado` (`:361-388`), perdiendo
  estado y sin crear reserva (`0004:1632-1635`). 🟢
- No migra gastos, facturas, pagos, liquidaciones ni mantenimientos (no hay
  referencia a esas tablas en el script). 🟢
- El flag de congelamiento es **fail-open** ante excepción
  (`servicio_cutover.py:38-39`) y tiene caché de 5 s por proceso (`:17-26`). 🟢
- El E2E de cutover **afirma el estado congelado** (`frontend/e2e/tei.spec.ts:96`,
  `getByText("Congelada")`): la prueba pasa porque el flag está en `true`, no
  porque el cutover funcione. Un cambio de flag la pone en rojo sin que haya
  regresión funcional. 🟢

### 5. Estado de verificación de esta sesión

| Afirmación | Nivel | Nota |
|---|---|---|
| Base local arriba, `0001`–`0014` aplicadas, 31 tablas `nucleo` / 17 `public` | 🟡 | Reportado por el orquestador; no ejecuté consultas |
| Suite 76 passed / 7 skipped; 82 passed / 1 failed con credenciales; E2E 9/9 | 🟡 | Reportado por el orquestador; no reproducido |
| Rutas, tablas, constraints, triggers y modelos citados | 🟢 | Leídos en archivo con línea |
| Volúmenes de datos por tabla | 🔴 | Prohibido ejecutar SQL; consultas exactas en `03-matriz-retiro-legacy.md` §5 |

---

## Problema

**No existe hoy ningún criterio objetivo que responda "¿este módulo legacy se
puede borrar?", y sin ese criterio el retiro se ejecuta por intuición o no se
ejecuta.**

En una frase verificable: *dado un artefacto legacy (router, pantalla, modelo,
test, fila de seed), ¿existe una comprobación reproducible que devuelva
"retirable" o "no retirable" sin consultar a una persona?* Hoy la respuesta es
no: la única regla escrita son las 4 condiciones de ADR-0001 §B.3, de las cuales
2 dependían de una base apagada y ninguna dice cómo se comprueba "sin
referencias vivas".

---

## Alternativas

| Alternativa | Ventajas | Costes / riesgos | Reversible | Impacto en legacy | Impacto en datos |
|---|---|---|---|---|---|
| **A. Big-bang**: construir los 4 módulos faltantes, migrar todo el histórico y borrar `public` en una sola entrega | Un solo corte; no queda convivencia | Requiere 4 módulos nuevos + migración de histórico + decisiones tributarias/laborales antes de tocar nada; un error de migración afecta dinero emitido; sin retiro parcial no hay forma de aprender del primer módulo; el cutover actual no migra el histórico (§Contexto 4) | Baja: revertir exige restaurar backup completo | Total: deja de existir de un día para otro | Alto: migración masiva de datos financieros cerrados |
| **B. Retiro por módulo con cuatro puertas verificables** | Cada borrado es pequeño y reversible; el criterio es observable por un tercero; permite medir el coste real del primer módulo antes de comprometer los demás; no crea infraestructura nueva | Más entregas; durante la transición conviven dos esquemas (igual que hoy); exige disciplina de evidencia por módulo | Alta: se puede parar en cualquier módulo sin haber perdido nada | Progresivo y explícito | Bajo por entrega: cada migración es de un concepto, con conteos antes/después |
| **C. Convivencia permanente**: `public` se queda como "archivo operativo" para liquidaciones, mantenimiento e IVA | Cero trabajo de migración de esos 3 módulos | Mantiene dos fuentes de verdad para siempre; mantiene la escalada de privilegio (§Contexto 3.5); mantiene `public.usuarios` como dependencia de identidad; cada módulo nuevo obliga a decidir "¿en cuál esquema?"; el dueño pidió lo contrario | — | Congela el estado actual | Ninguno, pero la divergencia se acumula sin detección |
| **D. Borrar solo el frontend legacy** y dejar los routers | Barato; quita pantallas duplicadas | No elimina escritores: los endpoints siguen abiertos y `test_flujos_criticos.py` los ejercita; la duplicación de verdad permanece; no cierra la escalada de privilegio | Alta | Parcial | Ninguno |

**Descartadas.** A: concentra todo el riesgo en una entrega y no tiene mecanismo
de aprendizaje; además depende de decisiones (D-08…D-12) que hoy no están tomadas.
C: es exactamente lo que el dueño ordenó evitar y deja el defecto de autorización
abierto. D: no cumple el objetivo (seguiría habiendo dos escritores) y confunde
"sin pantalla" con "sin escritura".

---

## Decisión

**Se adopta la alternativa B: retiro por módulo, con cuatro puertas verificables
y borrado únicamente de código y documentación. Los datos no se borran en este
ADR ni en ningún paso de este plan.**

### B.1 Definición operativa de "basura"

> **Basura** es un artefacto legacy cuyo concepto ya vive en `nucleo`, cuyos
> datos están migrados y conciliados, que no tiene ninguna referencia viva y cuya
> eliminación es reversible dentro de una ventana declarada.
>
> Un artefacto que cumple **tres** de las cuatro puertas **no es basura**: es
> deuda. Se registra como deuda, no se borra.

Un "artefacto" es cada una de estas cosas por separado: una ruta legacy, una
pantalla, un cliente HTTP, un modelo SQLModel legacy, un test, una fila de seed,
una sección de documentación. Un módulo es basura cuando **todos** sus artefactos
lo son.

### B.2 Las cuatro puertas

Cada puerta tiene un comando o una consulta que un tercero puede repetir. Sin esa
salida registrada, la puerta está cerrada.

#### P1 — Paridad funcional demostrada con prueba

**Qué exige.** Por cada **acción de escritura** de la pantalla legacy (alta,
edición, anulación/baja, y toda acción con efecto económico o de estado), existe
una acción equivalente en `nucleo` **y** una prueba que falla si se retira el
mecanismo que la garantiza.

**Cómo se verifica.**
1. Inventario de acciones cerrado: la lista de verbos del router legacy
   (`grep -n "@router\." <router>.py`) y la lista de llamadas de la pantalla
   (`grep -n "api\.\(get\|post\|put\|patch\|del\)" <page>.tsx`).
2. Cada verbo apunta a una ruta `/nucleo/...` o a "no aplica, se retira la
   función" con decisión del dueño.
3. Para cada regla crítica, una prueba de mutación: se retira el `EXCLUDE`, el
   `CHECK` o el trigger en una copia desechable y **la prueba debe fallar**.

**Estado actual (evidencia).** Ninguna pantalla legacy tiene E2E: el único spec
(`frontend/e2e/tei.spec.ts`) cubre 9 escenarios y **todos** son de `nucleo`
(`:14-98`), salvo `/dashboard` como destino post-login (`:16`). La cobertura de
las rutas legacy está en `backend/tests/test_flujos_criticos.py:16-250`, que es
una prueba de API, no de pantalla, y no prueba mutación. → **P1 abierta en todos
los módulos.** 🟢

#### P2 — Datos migrados y reconciliados con conteos antes/después

**Qué exige.**
1. Un script de migración **idempotente** por concepto (re-ejecutable sin
   duplicar), con clave natural declarada (RUT normalizado, patente normalizada,
   `numero_sii`/`numero_factura`, `(chofer_id, mes)`).
2. Conteo y **suma monetaria** por concepto antes y después, con la consulta
   pegada en el registro de la migración.
3. Una consulta de reconciliación que devuelve **0** diferencias, y su salida
   fechada.
4. Cero pérdida de estado: si un viaje legacy estaba `finalizado`, en `nucleo`
   debe quedar `finalizado` (no `confirmado`), y con su reserva creada.

**Cómo se verifica.** Las consultas están escritas en
`03-matriz-retiro-legacy.md` §5. Se ejecutan contra una **copia** de la base, no
contra producción, y se archiva la salida.

**Estado actual.** `cutover_legacy.py` no migra gastos, facturas, pagos,
liquidaciones ni mantenimientos; omite viajes cerrados (`:268-288`) y fuerza
`confirmado` (`:361-388`). No existe consulta de reconciliación en el repo
(`grep -rn "reconcilia" scripts/ backend/` → 0 resultados). → **P2 abierta en
todos los módulos con datos.** 🟢

#### P3 — Cero referencias vivas

**Qué exige.** Para el artefacto a borrar, estas seis búsquedas devuelven **0
resultados** (excluyendo el propio artefacto y este plan):

| # | Referencia | Comando |
|---|---|---|
| 1 | Ruta en el backend | `grep -rn "\"/<ruta>\"" backend/app/` |
| 2 | Montaje del router | `grep -rn "<router>" backend/app/api/router.py` |
| 3 | Llamada desde el frontend | `grep -rn "\"/<ruta>" frontend/src/` |
| 4 | Pantalla en la navegación | `grep -rn "href: \"/<pantalla>\"" frontend/src/lib/navigation.ts` |
| 5 | Test que la ejercita | `grep -rn "<ruta>" backend/tests/ frontend/e2e/` |
| 6 | Script, seed o SQL cruzado | `grep -rn "public\.<tabla>" scripts/ backend/ supabase/` |

**Corrección respecto de la propuesta inicial del contrato de tarea:** la puerta
P3 debe incluir **dependencias de runtime no obvias**, porque en este repo existen
y son las que más rompen. Son cuatro y se comprueban aparte:

- **Identidad:** `public.usuarios` + trigger `handle_new_user` (`0001:248-262`) +
  `GET /auth/me` (`auth.py:10-18`) + `auth-context.tsx:59`. **No se puede tratar
  como un módulo más**: se retira con un reemplazo de identidad en `nucleo`, no
  con un `grep` en cero.
- **Middleware de perímetro:** `main.py:45-50` clasifica "legacy" por prefijo. Al
  borrar la última ruta legacy, el middleware queda sin efecto y el flag
  `cutover_control` sin destinatario.
- **Lectura cruzada de esquema:** `servicio_cutover.py:67-71` lee
  `public.viajes`. Bloquea borrar `public.viajes` incluso si no queda ningún
  router legacy.
- **Parámetro tributario:** `public.configuracion.iva_porcentaje` alimenta
  `finanzas.py`, `facturas.py` y `kpi_engine.py` (`settings_db.py:5-16`).

**Estado actual.** Ejemplo canónico: `/clientes` legacy tiene referencias vivas en
`navigation.ts:85`, `clientes/page.tsx:126-129`, `viajes/page.tsx:105`,
`export.py:194-228` (import CSV) y `test_flujos_criticos.py:16`. → **P3 abierta.** 🟢

#### P4 — Reversibilidad con ventana declarada

**Qué exige.**
1. El borrado se hace en **dos entregas**: primero se retira el punto de entrada
   (pantalla, enlace de navegación, montaje del router) dejando el código en el
   repositorio y desplegable; después, transcurrida la ventana **N**, se borra el
   código.
2. **N se declara antes de empezar** y no se negocia a mitad de camino. Propuesta
   por defecto: **N = 30 días corridos** desde que la última escritura legacy del
   módulo quedó en cero. Justificación: cubre un ciclo mensual completo de
   facturación y liquidación, que es el período en que un módulo "que ya no se usa"
   reaparece. **D-08** ratifica o corrige N.
3. Durante la ventana, la reversión es un `git revert` del commit de retiro de
   entrada: sin migración inversa y sin pérdida de datos, porque no se movió nada.
4. Existe evidencia de que el restore funciona: `make restore-drill`
   (`Makefile:65-66`, `scripts/restore_drill.sh`) ejecutado y con salida
   registrada. Hoy **no hay evidencia de ejecución** en el repo. → **P4 abierta.**

**Por qué la ventana es de código y no de datos.** Reabrir una pantalla legacy no
devuelve a `public` lo que se escribió en `nucleo` mientras estuvo cerrada
(ADR-0001 §Rollback, advertencia vigente). La reversibilidad real solo existe si
el módulo se retira **cuando ya no recibe escrituras**, no como experimento.

### B.3 Precondición transversal (G0)

No es una quinta puerta por módulo: es la condición que debe cumplirse **una vez**
para poder borrar el esquema. Mientras G0 no se cumpla, `public` puede quedar sin
routers pero **no puede dejar de existir**.

| # | Condición | Evidencia que la cierra |
|---|---|---|
| G0.1 | Existe identidad en `nucleo` que reemplace `public.usuarios` + `/auth/me`, y el trigger `handle_new_user` se retira en la misma migración que la tabla | Endpoint de perfil en `nucleo`, `auth-context` apuntando a él, prueba de alta de usuario nuevo, `grep` del trigger en 0 |
| G0.2 | Ningún código de `nucleo` lee `public.*` | `grep -rn "public\." backend/` → 0 |
| G0.3 | `iva_porcentaje` y el resto de parámetros tributarios viven en `nucleo` con dueño y auditoría | Migración + decisión D-10 + prueba de que el valor no lo fija el cliente |
| G0.4 | `nucleo.cutover_control` y el middleware se retiran juntos, con el histórico de congelamientos preservado | Migración que archiva el historial y elimina el flag; `main.py` sin el middleware |
| G0.5 | Restore drill ejecutado con evidencia, comparando conteos antes/después | Salida de `make restore-drill` archivada |
| G0.6 | Backup verificado + autorización explícita antes de cualquier `DROP SCHEMA` | Registro de autorización del dueño |

### B.4 Qué se puede borrar y qué **nunca** se borra

**Borrable (código y documentación) — solo con las cuatro puertas cerradas:**

- Routers legacy de `backend/app/api/routes/` y su `include_router`
  (`router.py:3-16,32-43`).
- Modelos SQLModel legacy de `backend/app/models/__init__.py:67-276` (los que
  solo usan routers retirados).
- Pantallas de `frontend/src/app/(app)/`, sus componentes exclusivos, sus entradas
  en `navigation.ts:44-99` y los métodos de `lib/api.ts` que solo ellas usan.
- `frontend/src/lib/api.ts` completo, cuando no quede ningún consumidor.
- Tests que solo ejercitan rutas retiradas (`test_flujos_criticos.py` se reescribe
  contra `nucleo`, no se "borra para que pase").
- Escrituras legacy en `scripts/seed_local.py:196-205,233-240,268-281,303-312,335-346`.
- Secciones de documentación que describen exclusivamente el módulo retirado, en
  el mismo cambio (AGENTS.md §11.3: un artefacto desactualizado se corrige o se
  elimina, no se deja como vigente).

**Nunca se borra sin backup verificado + autorización explícita (D-08):**

| Objeto | Por qué |
|---|---|
| Filas de las 17 tablas de `public` | Son el histórico operativo y financiero; parte de él no se migra (`cutover_legacy.py:268-288`) |
| `public.facturas`, `public.factura_viaje`, `public.liquidaciones`, `public.anticipos_chofer`, `public.ajustes_liquidacion` | Documentos con efecto tributario/laboral; se corrigen con documento compensatorio, no se borran (AGENTS.md §3.16) |
| `public.usuarios` | Identidad; ver G0.1 |
| `public.configuracion` | Parámetros vigentes (IVA, alertas); ver G0.3 |
| `public._migraciones` (`0002:6-9`) | Trazabilidad de migraciones aplicadas |
| Las migraciones `0001`–`0014` | Forward-only (AGENTS.md §8); no se editan ni se borran |
| Objetos del bucket `respaldos` (`0002:19`) | Comprobantes de gasto subidos por usuarios (`gastos.py:25-39`) |
| `auth.users` | Fuera de este repo y de este ADR |

**Regla de lenguaje, para evitar el error más caro:** "borrar el módulo" siempre
significa **borrar su código**. Nunca significa borrar sus datos. El día que se
borre una fila de `public`, eso es un ADR distinto, con backup, autorización y
ventana.

### B.5 Orden de retiro y qué desbloquea cada paso

El orden no es por tamaño ni por gusto: es por **dependencias reales** (quién
llama a quién) y por **lo que cada retiro libera**. El grafo está en
`03-matriz-retiro-legacy.md` §3.

| Ola | Módulo | Por qué ahora | Qué desbloquea |
|---|---|---|---|
| **1** | **Cobranzas legacy** (`/cobranzas`, `GET /cobranzas`, `PATCH /facturas/{id}/estado`) | Es hoja (nadie más la llama). Su única escritura permite marcar una factura `pagada` **sin registrar un pago** (`facturas.py:212-217`), mientras el núcleo exige `POST /nucleo/cobranza/facturas/{id}/pagos` (`api_facturacion.py:97-103`). Retirarla **quita un defecto de integridad de dinero** en vez de crear trabajo | Elimina el último camino para "pagar" sin pago; deja `/facturacion` como único consumidor del PATCH y permite separar anulación (ver D-09) |
| **2** | **Dashboard legacy** (`/dashboard`, `GET /dashboard/resumen`, `GET /dashboard/alertas`) | Hoja y de solo lectura. `nucleo` ya tiene `/nucleo/alertas/tablero` (`api_alertas.py:24-28`) y `/nucleo/rentabilidad` (`api_rentabilidad.py:38-61`) | Deja de leer `public.viajes`/`public.facturas`/`public.gastos_viaje` para pintar la primera pantalla; obliga a mover el destino post-login a `/tablero` (`tei.spec.ts:16`) |
| **3** | **Maestros legacy — pantallas** (`/clientes`, `/choferes`, `/flota`) + `POST /export/import/{clientes,choferes}` | Las tres pantallas están duplicadas por `/maestros` (`maestros/page.tsx:6`, `navigation.ts:84-86`). El import CSV es un **escritor duplicado** de `public.clientes`/`public.choferes` (`export.py:194-272`) que sobrevive aunque se borren las pantallas | Elimina 3 escritores duplicados de maestros. **No** borra el router `catalogos`, porque `/viajes`, `/mantenimiento` y `/liquidaciones` lo consumen (`viajes/page.tsx:105-108`, `mantenimiento/page.tsx:113`) |
| **4** | **Operación legacy** (`/viajes`, `/viajes/[id]`, `viajes.py`, `gastos.py`) | Es el módulo con más datos y el que exige la migración de histórico (§P2) | Desbloquea el borrado del router `catalogos` y de `public.viajes` (salvo G0.2) |
| **5** | **Facturación legacy** (`/facturacion`, `facturas.py`, `finanzas.py:/facturacion/*`) | Requiere decidir anulación (D-09) y migrar facturas emitidas | Desbloquea borrar `public.facturas` (con backup) |
| **6** | **Configuración + KPIs** (`/configuracion`, `/kpis`) | Requiere decidir si los KPI configurables sobreviven (D-11) y mover `iva_porcentaje` a `nucleo` (G0.3) | Desbloquea G0.3 y el borrado de `public.configuracion`/`public.kpis` |
| **7** | **Liquidaciones** | Requiere construir el módulo en `nucleo` + D-02/D-03 (política de comisión y qué se congela al emitir) | Desbloquea `public.liquidaciones`, `anticipos_chofer`, `ajustes_liquidacion` |
| **8** | **Mantenimiento** | Requiere construir pautas por km en `nucleo` + D-07 | Desbloquea `public.pautas_mantenimiento`, `public.mantenimientos` |
| **9** | **IVA / F29** | Requiere D-10 (tasa y criterio de crédito fiscal) | Desbloquea el módulo de IVA y la última lectura de `public.configuracion` |
| **10** | **Identidad + cierre de esquema** (`auth`, `public.usuarios`, middleware, `cutover_control`) | Es G0 completa | Permite archivar `public` como histórico de solo lectura o retirarlo con backup (D-08) |

**Regla de secuencia:** un módulo de una ola no empieza hasta que el anterior
tenga **las cuatro puertas cerradas con salida registrada**. No se paralelizan dos
módulos que compartan tabla.

### B.6 Lo que este ADR **no** decide

- No migra ni borra datos.
- No congela ni descongela nada.
- No fija N (D-08), ni la política de comisión (D-02), ni la anulación de
  facturas (D-09), ni la tasa de IVA (D-10), ni el futuro de los KPI
  configurables (D-11), ni el destino del histórico (D-12).
- No modifica ADR-0001; declara qué parte suya queda sustituida.

---

## Consecuencias

### Positivas

- El retiro deja de ser una intención y pasa a ser una lista de comprobaciones
  que cualquiera puede ejecutar y refutar.
- Las olas 1 y 2 **eliminan defectos** (pago sin pago, lectura legacy en la
  primera pantalla) antes de tocar un solo dato.
- Cierra progresivamente la escalada de privilegio del §Contexto 3.5 sin escribir
  código de seguridad nuevo: basta con dejar de exponer las rutas legacy.
- No introduce ninguna dependencia operativa: ni cola, ni worker, ni servicio
  nuevo, ni registro permanente. El "registro de módulos" de ADR-0001 muere con
  el último módulo.
- La puerta P3, con las cuatro dependencias transversales explícitas, evita el
  error más probable de todo el plan: borrar `public.usuarios` y descubrir en
  producción que nadie puede entrar.

### Negativas

- Durante las olas 3–10 siguen existiendo dos esquemas y dos clientes HTTP. La
  deuda no desaparece hasta el final, solo se acota por módulo.
- Retirar una pantalla sin retirar su router deja rutas huérfanas que
  `test_flujos_criticos.py` seguirá ejercitando; si se olvida, la suite da una
  falsa sensación de cobertura.
- Cada ola exige trabajo de migración de datos que hoy no existe y que hay que
  escribir desde cero (el cutover actual no sirve como base: omite el histórico).
- La ventana N de 30 días retrasa el borrado de código aunque el módulo esté
  cerrado; es el precio de que la reversión sea real.

### Deuda que genera

- Una consulta de reconciliación por concepto que hay que mantener viva hasta la
  última ola.
- Un script de migración por concepto (no uno monolítico), idempotente.
- La obligación de actualizar `03-matriz-retiro-legacy.md` en cada ola: sus filas
  son el registro de qué falta. Una fila desactualizada es peor que ninguna.

---

## Plan de migración y rollback

### Paso 0 — Línea base (solo lectura, sin cambios)

1. Ejecutar las consultas de `03-matriz-retiro-legacy.md` §5 en una **copia** de la
   base y archivar la salida con fecha.
2. Registrar el resultado de `make unit` y `make test` **con la base arriba**, y
   de `make e2e`. Sin esto no hay línea base contra la cual comparar.
3. Verificar el estado real de `nucleo.cutover_control` y **dejarlo en un estado
   conocido y escrito** (hoy amaneció en `true` y bloqueó todas las escrituras
   legacy sin que nadie lo supiera).

**Criterio de aceptación:** existe un documento con la salida pegada de §5 y de
las tres suites, fechado, y el estado del flag declarado.

### Paso 1 — Ola 1 (cobranzas legacy)

1. Repuntar `/cobranzas` a `/cobranza` (o eliminar el ítem de navegación
   `navigation.ts:76`) en una entrega.
2. Separar `PATCH /facturas/{id}/estado` en dos responsabilidades: "marcar pagada"
   deja de existir en legacy (el pago se registra en el núcleo); la anulación
   queda pendiente de D-09 y **no se borra** hasta entonces.
3. Esperar N días con el punto de entrada retirado.
4. Borrar `GET /cobranzas` (`finanzas.py:65-113`) y su esquema de respuesta
   (`CobranzasResumen`), y actualizar `test_flujos_criticos.py` si lo usaba.

**Criterio de aceptación:** `grep -rn "/cobranzas" frontend/src/` → 0;
`grep -rn "def cobranzas" backend/` → 0; `make test` verde; E2E de `/cobranza`
verde.

### Paso 2 — Ola 2 (dashboard legacy)

1. Mover el destino post-login a `/tablero` y ajustar `tei.spec.ts:16`.
2. Decidir si los totales de dinero del dashboard (`ingresos_mes`,
   `cuentas_por_cobrar`, `gastos_mes`, `dashboard.py:57-96`) se agregan al tablero
   del núcleo o se aceptan desde `/cobranza` y `/rentabilidad`. **Si se aceptan
   sin reemplazo, es una decisión del dueño (D-12), no del agente.**
3. Esperar N días.
4. Borrar `dashboard.py` y su entrada en `router.py:36`.

### Paso 3 — Olas 3–9

Cada una repite el patrón: (a) cerrar pantalla/entrada, (b) migrar datos con P2,
(c) conciliar, (d) esperar N, (e) borrar código, (f) actualizar la matriz. Ninguna
ola avanza sin la salida de la anterior.

### Rollback

| Escenario | Acción | Efecto | Riesgo residual |
|---|---|---|---|
| Una pantalla retirada hace falta | `git revert` del commit de retiro de entrada | Vuelve la pantalla; el router legacy sigue montado durante la ventana N | Ninguno: no se movieron datos |
| Un módulo migrado resulta incorrecto | Restaurar desde backup verificado de la **copia** usada en la migración; la base productiva no se tocó en esa fase | Vuelve al estado previo a la migración de ese concepto | Se pierde lo escrito en `nucleo` desde la migración de ese concepto |
| Ya se borró el código y aparece un caso no cubierto | Reimplementar en `nucleo` (el legacy ya no existe) | Coste de reescritura | Alto: por eso N existe y por eso el borrado es el **último** paso, nunca el primero |
| G0 mal ejecutado (identidad) | Restaurar `public.usuarios` desde backup | El login vuelve a funcionar | Pérdida de las altas ocurridas entre el borrado y el restore |

**Advertencia explícita:** el rollback **no es sin pérdida** en el sentido de
datos. Reabrir el legacy no propaga a `public` lo escrito en `nucleo`. Por eso el
retiro de cada módulo se hace cuando ya no recibe escrituras, no para "probar".

---

## Criterios de aceptación

1. Existe, por módulo, un registro fechado con la salida de **las cuatro puertas**;
   sin esa salida el módulo no se declara basura.
2. Ninguna fila de `public` se borra en ninguna ola; cualquier borrado de datos
   exige un ADR propio con backup verificado y autorización (D-08).
3. `grep -rn "public\." backend/` devuelve 0 antes de cualquier `DROP SCHEMA`.
4. Toda pantalla retirada tiene su redirección o su ítem de navegación eliminado
   en el mismo cambio; ninguna ruta retirada deja un 404 o un 409 visible al
   usuario.
5. `make unit`, `make test` y `make e2e` verdes **después** de cada ola, con
   salida registrada; un `skip` no cuenta como verde.
6. Ninguna prueba se modifica para que pase: `test_flujos_criticos.py` se
   **reescribe** contra `nucleo`, no se elimina.
7. El E2E deja de depender del estado del flag de cutover (`tei.spec.ts:96`).
8. Al cerrar la última ola, `03-matriz-retiro-legacy.md` no tiene filas con
   puertas abiertas, o las que quedan están marcadas como decisión pendiente del
   dueño con su ID.

---

## Riesgos y preguntas abiertas

| ID | Decisión que **no** toma este ADR | Destinatario | Por qué no la decido yo |
|---|---|---|---|
| **D-08** | Destino del histórico de `public`: ¿se conserva como esquema de solo lectura indefinidamente, se archiva fuera de la base, o se migra completo a `nucleo`? Y ratificar N (30 días) | Dueño + contador | Es política de retención documental con efecto tributario; no se infiere |
| **D-09** | Anulación de facturas: ¿se elimina el camino legacy `PATCH estado=anulada` (`facturas.py:218-228`, que además desasocia viajes) y se anula solo con nota de crédito (`api_facturacion.py:106-112`)? | Dueño + contador | Regla tributaria; el legacy hace algo que el núcleo no hace y no puedo decidir cuál es correcto |
| **D-10** | Tasa de IVA y criterio de crédito fiscal: hoy el núcleo acepta `tasa_iva` **desde el cliente** con default 0,19 (`schemas.py:1543`) y el legacy usa `public.configuracion.iva_porcentaje`; el crédito legacy es `monto * tasa/(100+tasa)` sobre un flag booleano (`finanzas.py:145-153`), el núcleo guarda `iva` por gasto (`0011:38`) | Contador | Obligación tributaria; AGENTS.md §3.15 prohíbe inventarla |
| **D-11** | ¿Los KPI configurables por fórmula (`0003:5-20`, `kpis.py`) sobreviven en `nucleo`, se congelan como configuración fija, o se retiran? | Dueño | Es alcance de producto; el núcleo tiene rentabilidad fija y no un motor de fórmulas |
| **D-12** | ¿Se acepta que el tablero del núcleo no muestre los totales de dinero del dashboard legacy (`ingresos_mes`, `cuentas_por_cobrar`, `gastos_mes`), o hay que agregarlos antes de retirarlo? | Dueño + contador | Define si la Ola 2 es "borrar" o "construir primero"; afecta el calendario |

**Riesgos residuales que este ADR no elimina:**

- **R1 (alto):** el retiro de maestros (Ola 3) deja `/viajes`, `/mantenimiento` y
  `/liquidaciones` consumiendo el router `catalogos`; si alguien borra el router
  junto con las pantallas, esas tres pantallas dejan de cargar. Mitigación: la
  matriz separa explícitamente "pantalla" de "router" en esa fila.
- **R2 (alto):** la suite actual no prueba las rutas legacy por pantalla; retirar
  una pantalla puede pasar desapercibido hasta que un usuario la busca.
  Mitigación: P1 exige inventario de acciones, no solo "existe el endpoint".
- **R3 (medio):** `test_nucleo_cutover.py:49-65` conmuta el flag global y lo
  restaura en un `finally`; si el proceso muere en medio, la base queda congelada.
  Es el mismo modo de fallo que ocurrió hoy. Mitigación: prueba sobre una fila
  aislada o transacción con rollback; no es parte de este ADR.
- **R4 (medio):** el orden propuesto asume que el dueño no exige liquidaciones
  antes de la Ola 7. Si exige liquidaciones primero, el orden cambia y la Ola 1
  sigue siendo válida, pero las olas 4–6 se posponen.
- **R5 (bajo):** la puerta P2 depende de una copia de la base; hoy no hay
  evidencia de que exista un procedimiento de copia probado (`restore_drill.sh`
  verifica 6 conteos y existencia, no comparación antes/después). Si no se prueba,
  P2 no se puede cerrar con honestidad.

**Riesgos heredados de ADR-0001 que siguen vigentes y no se repiten aquí:** R2
(exclusión del núcleo no probada con dos conexiones), R3 (RLS sin políticas),
R5 (registro de módulos desactualizado).
