# ADR-0008: Configuración por tenant para agentes y autoridad única de la máquina de estados del viaje

- **Estado:** **Propuesto** (2026-11-02). Requiere aceptación explícita del dueño para
  la Decisión 1; sin ella, `datos` **no** escribe la migración `0030`. La Decisión 2 no
  requiere migración nueva en esta ola (solo una prueba y, opcionalmente, `0031`).
- **Fecha:** 2026-11-02
- **Decide:** agente `arquitectura`. Las migraciones `0030`/`0031` (si se autorizan) y su
  evidencia son del agente `datos`; el catálogo de claves es de `backend`; las pruebas
  de la matriz, de `qa`.
- **Método de esta sesión:** lectura estática de migraciones, servicios, routers,
  esquemas, pruebas y frontend. **No** se ejecutó ningún comando de base, prueba ni
  migración (shell no disponible). Todo hecho que depende de comportamiento en ejecución
  se marca 🟡 con lo que lo cerraría.
- **Depende de:** `ADR-0005` (dos engines, `tei_app`, RLS por transacción), `ADR-0001`
  (`nucleo` canónico), migraciones `0020` (RLS), `0023` (`modulos_empresa`), `0026`
  (`configuracion_empresa`), `0004` (máquina de estados), `0009` (gate POD/OC), `0013`
  (facturación), `0028` (retiro de `public`).
- **Reemplaza a:** nada. No modifica ADR previos.
- **Nota de procedencia (corregida 2026-11-02 por `orquestador`):** el encargo de este
  ADR se redactó con el estado de la auditoría inicial: no había lector de
  `transiciones_viaje` en Python ni endpoint de transición para oficina. **Eso era
  cierto al auditar.** Los hechos 27–30 se refieren a archivos creados por la Ola 2
  (`servicio_transiciones.py`, endpoints en `api.py`, `test_nucleo_transiciones.py`)
  **durante esta misma sesión y en paralelo a la redacción del ADR**; al momento de la
  auditoría no existían. El ADR se construye sobre el estado final, pero no debe leerse
  como refutación retroactiva de la auditoría.
  **Error propio de la auditoría que sí se corrige aquí:** la auditoría afirmó que la
  matriz "no se aplicaba". Es falso: el trigger `fn_viaje_transicion`
  (`0004:1511-1547`, hecho 25) la aplica en PostgreSQL desde `0004`. La brecha real era
  la ausencia de vía para oficina, no la ausencia de garantía en base.
- **Numeración de preguntas:** los IDs `D-24…D-28` y `P-14…P-16` son **propuestos**; el
  prefijo `D-NN` pertenece al dueño y `negocio-finanzas` asigna el número final en
  `docs/negocio/preguntas.md` (`AGENTS.md` §11.2). Al 2026-11-02 esos números no
  aparecen en `docs/` (búsqueda propia).

---

## 0. Resumen de las decisiones

**Decisión 1 — Configuración por tenant.**

1. **`tenant_config` NO se crea como tabla.** La configuración por empresa ya existe:
   `nucleo.configuracion_empresa` (`0026:109-145`) con clave/valor `jsonb`, vigencia
   `[desde, hasta)`, `EXCLUDE` anti-solape (`0026:140-144`), historial inmutable
   (`0026:198-256`) y RLS `tenant_empresa` (`0026:270-277`). Lo que falta no es tablar:
   es **catálogo**. Se extiende el catálogo del servicio
   (`servicio_configuracion.py:38-43`), que es donde `0026:46-49` decidió que viviera.
2. **`tenant_reglas_entidad` NO se crea en la Ola 1.** El único caso verificado de
   "regla por entidad" para la capa de agentes ya existe y se llama
   `nucleo.permisos_contacto` (`0021:243-265`). Un EAV genérico por entidad duplicaría
   esa fuente y perdería las FKs. Su contrato exacto queda en el Apéndice B por si un
   ADR posterior lo autoriza: **no** `entidad_id uuid` polimórfico, sino el patrón ya
   usado por `nucleo.documentos` (`0004:326-360`).
3. **`tenant_suscripciones` NO se crea en la Ola 1.** Plan, precio, cupos y límites son
   decisión de dueño/negocio (`D-25`, `D-26`); la arquitectura solo fija el mecanismo.
   Además, "empresa activa/inactiva" ya existe (`nucleo.empresas.estado`, `0004:34,126`)
   y "módulo encendido" ya existe (`nucleo.modulos_empresa`, `0023:183-202`): una tabla
   de suscripción que reimplemente cualquiera de los dos crea una segunda verdad.
   Contrato condicional en el Apéndice C.
4. **Consecuencia operativa:** `0030_tenant_config_agentes.sql` **no debe escribirse para
   estos tres objetos** (§3.5). Si el dueño confirma las tablas contra esta
   recomendación, el contrato de ejecución completo —objetos, precondiciones,
   RLS+FORCE, `GRANT`s sin `DELETE`, triggers `fn_touch`/`fn_version`/`fn_auditoria`,
   verificación y rollback— está en el Apéndice A, para que `datos` no vuelva a decidir
   el modelo.

**Decisión 2 — Autoridad de la máquina de estados del viaje.**

5. **`nucleo.transiciones_viaje` es la autoridad única de la *legalidad*, y el código ya
   la trata así.** Dos capas la aplican: el trigger `trg_viajes_30_transicion` →
   `fn_viaje_transicion` (`0004:1840-1841`, `0004:1511-1547`) y el servicio de oficina,
   que **lee la tabla** en vez de duplicarla (`servicio_transiciones.py:109-117`,
   `:167-179`). No hay que crear autoridad: hay que **protegerla de la regresión**.
6. **`facturado` y `cobrado` no son transiciones operativas: son estados derivados de un
   hecho financiero.** La oficina ya los tiene prohibidos por política de servicio
   (`ESTADOS_SOLO_FACTURACION`, `servicio_transiciones.py:65-67`, `:156-165`), y
   `facturado` además está condicionado en la base (POD + OC, `0009:80-93`). **`cobrado`
   no tiene ninguna condición en la base**: cualquier `UPDATE` con derecho de escritura
   lo puede fijar.
7. **No se agrega columna `actor` a `transiciones_viaje`.** El repo ya distingue
   **legalidad (tabla)** de **política por flujo (servicio)**: oficina excluye 3 destinos
   (`:156-205`) y el conductor solo avanza en 6 aristas (`servicio_conductor.py:51-58`).
   Una sola columna no expresa "solo hacia adelante", y la garantía de "quién" en
   PostgreSQL no existe (un solo rol de aplicación, `tei_app`). Cambiar el esquema aquí
   sería complejidad sin problema que resolver.
8. **Deuda real y acotada:** `TRANSICIONES_CONDUCTOR` es la única copia en Python y no
   tiene prueba contra la matriz; los gates financieros `INV-EST05`/`INV-EST06` están
   declarados pero **no impuestos**. Ambas se pagan con una prueba (S) y, si el contador
   lo pide, con la migración `0031` (M).

---

## 1. Contexto verificado

### 1.1 Configuración por empresa

| # | Hecho | Evidencia | Certeza |
|---|---|---|---|
| 1 | `nucleo.configuracion_empresa` existe: `empresa_id`, `clave text`, `valor jsonb`, `vigente_desde`/`vigente_hasta` (`[desde, hasta)`), `version`; FK a `nucleo.empresas` con `on delete restrict` | `0026:109-145` (FK `:123-124`, formato de clave `:125`, `vigencia > desde` `:126-128`) | 🟢 |
| 2 | Una sola fila vigente por `(empresa_id, clave)` y vigencias sin solape | índice único parcial `0026:165-167`; `EXCLUDE USING gist` `0026:140-144` | 🟢 |
| 3 | El valor de una fila cerrada no se edita; la tabla no admite `DELETE` | `fn_config_empresa_inmutable` `0026:198-232`; `fn_config_empresa_no_borrar` `0026:234-246`; triggers `0026:251-256` | 🟢 |
| 4 | RLS habilitada **y** forzada, política `tenant_empresa` con `empresa_id = nucleo.ctx_empresa()` en `USING` y `WITH CHECK` | `0026:270-277` | 🟢 |
| 5 | `tei_app` tiene `SELECT/INSERT/UPDATE` y **no** `DELETE`; `anon`/`authenticated` quedan revocados | `0026:282-283`, `:285-296`; verificación `:344-353` | 🟢 |
| 6 | Lectura canónica única de la fila vigente vía `nucleo.config_vigente(uuid, text)`, `SECURITY INVOKER` (RLS aplica) | `0026:176-191` | 🟢 |
| 7 | El catálogo de claves es **cerrado y está en el servicio**: 4 claves (`iva_porcentaje`, `alerta_km_mantenimiento`, `dias_alerta_vencimientos`, `dias_alerta_cobranza`); clave desconocida ⇒ error de datos | `backend/app/nucleo/servicio_configuracion.py:38-43`, `:54-58`, `:208-212` | 🟢 |
| 8 | La migración `0026` declara que "qué claves existen y qué tipos tienen" **no** está en la base, sino en el servicio | `0026:46-49`; `COMMENT` de `clave` `0026:151-154` | 🟢 |
| 9 | El catálogo está **triplicado**: servicio (4 claves), pantalla de configuración (misma lista, con títulos/rangos) y `CHECK` de `iva_porcentaje` en la base | `servicio_configuracion.py:38-43`; `frontend/src/app/(app)/configuracion/page.tsx:38-82` (usado en `:135`); `0026:130-137` | 🟢 |
| 10 | `nucleo.empresas` guarda parámetros de tenant **como columnas tipadas con `CHECK`**: `zona_horaria`, `moneda`, `buffer_operacional_min`, `dias_margen_documentos`, `dias_alerta_documentos`, `exigir_soap`, `exigir_seguro_carga`, `exigir_curso_carga_peligrosa`, `exigir_oc` | `0004:114-125` | 🟢 |
| 11 | Esos parámetros **tienen lectores reales** salvo uno: `politicas.py:67,84,109` (`exigir_soap`/`exigir_seguro_carga`/`exigir_curso_carga_peligrosa`), `servicio_alertas.py:125` y `servicio_disponibilidad.py:245` (`dias_alerta_documentos`), `servicio_disponibilidad.py:134,623,944,1174,1442,1483` (`buffer_operacional_min`). **`exigir_oc` no lo lee ningún archivo de `backend/app`** | grep de `exigir_oc` en `backend/` = 1 sola aparición: `models.py:226` | 🟢 |
| 12 | `empresas.exigir_oc` (default `false`) contradice a la base: pasar a `facturado` **siempre** exige OC | `0004:125` vs `0009:89-93` (sin condición sobre `exigir_oc`) | 🟢 |
| 13 | Deriva de default en un parámetro de tenant: `dias_alerta_documentos` nace **30** por DDL y **14** por el modelo ORM | `0004:120` vs `backend/app/nucleo/models.py:222`; el propio test lo reconoce (`backend/tests/test_r02_licencia_nucleo.py:496`) | 🟢 |
| 14 | `nucleo.configuracion_costos` es una **tercera** superficie de configuración por empresa: una fila por empresa, columnas tipadas, sin vigencia | `0012:8-25` (`unique` en `empresa_id` `:10`) | 🟢 |
| 15 | `configuracion_costos` **sí** quedó cubierta por `0020`: `GRANT` y política se aplican por bucle a todas las tablas existentes con `empresa_id`, y el `FORCE` a todas las tablas de `nucleo` | `0020:258`, `:282-307`, `:395-409` | 🟢 |
| 16 | `nucleo.modulos_empresa`: flag booleano por `(empresa_id, modulo_id)`, PK natural, sin plan/límites/vigencia contractual; "sin fila o `habilitado=false` = apagado" | `0023:183-202`, `COMMENT` `:204-220`; RLS+política `:239-246`; `GRANT` `:253` | 🟢 |
| 17 | `nucleo.permisos_contacto` ya es una tabla clave/valor **por entidad** (contacto) para la capa de agentes: `componente`, `variable`, `permitido`, con FK compuesta `(empresa_id, contacto_id)` y unicidad por `(contacto_id, componente, coalesce(variable,''))`; ausencia = denegado | `0021:243-265`, `:262-263`, `COMMENT` `:267-270` | 🟢 |
| 18 | El patrón del repo para "entidad polimórfica sin FK polimórfica" es: enum de tipo + **una FK nullable por tipo** + `CHECK` de exclusividad, con FKs **compuestas por empresa** | `nucleo.documentos` `0004:326-360` (`ck_doc_un_solo_recurso` `:354-358`); replicado en `contactos_whatsapp` `0021:185-214` | 🟢 |
| 19 | Un parámetro por entidad hoy se guarda como **columna tipada en la propia entidad** (comisión del chofer), no en una tabla EAV | `choferes.porcentaje_comision` `0004:299-301`; default 10 % en `0017:47` (rollback documentado en `0017:38`) | 🟢 |
| 20 | `tenant_config`, `tenant_reglas_entidad` y `tenant_suscripciones` **no existen** en el repositorio: 0 coincidencias en `backend/`, `frontend/`, `supabase/` y `docs/` | grep propio sobre la raíz | 🟢 |
| 21 | Tabla nueva en `nucleo` ⇒ política + `GRANT` explícitos; `0020` no la alcanza (sus bucles corren sobre el catálogo del momento) | `0020:258,282-307`; `ADR-0005` R-6 | 🟢 |
| 22 | El engine del núcleo usa `NUCLEO_DATABASE_URL` **con fallback** al DSN privilegiado y solo emite `WARNING` ("RLS inerte"); el `503` que pedía `ADR-0005` §3.2.2 no es el comportamiento actual | `backend/app/core/database.py:28-32`, `:120-124`, `:170-195` | 🟢 (código) / 🔴 (rol efectivo desplegado) |

### 1.2 Máquina de estados del viaje

> **Procedencia de los hechos 27–30:** describen código creado en la Ola 2
> (2026-11-02) durante esta sesión. Antes de esa ola, ningún Python leía la matriz y no
> existía endpoint de oficina. Los hechos 23–26 (tabla + trigger en base) sí son
> preexistentes y son la garantía real.

| # | Hecho | Evidencia | Certeza |
|---|---|---|---|
| 23 | `nucleo.transiciones_viaje` es un catálogo global (sin `empresa_id`) con PK `(estado_origen, estado_destino)` y `requiere_motivo` | `0004:772-777` | 🟢 |
| 24 | Tiene **29 aristas**; **10** llevan `requiere_motivo = true` (todas las que terminan en `anulado`) | `0004:779-808` (conteo propio de las 29 filas y de los `true`) | 🟢 |
| 25 | La base **sí** la aplica: trigger `BEFORE UPDATE` que rechaza arista inexistente (`23514`), exige `motivo_anulacion` cuando `requiere_motivo`, y sella `anulado_por`/`anulado_en` | `fn_viaje_transicion` `0004:1511-1547` (`:1522-1534`, `:1536-1543`); trigger `trg_viajes_30_transicion` `0004:1840-1841` | 🟢 |
| 26 | El catálogo es de solo lectura para la aplicación: `tei_app` tiene `SELECT` y nada más; política `using(true)` | `0020:270-271`, `:364-367`; rechazo de escritura probado (`supabase/tests/0020_01_aislamiento.sql:378-386`) | 🟢 |
| 27 | **La aplicación SÍ lee la tabla**: el servicio de oficina consulta la matriz en vez de duplicarla | `servicio_transiciones.py:109-117` (`_matriz_desde` sobre `TransicionViaje`), uso en `:167-179` y `:291-302`; modelo `models.py:1331-1332` | 🟢 |
| 28 | **Existe endpoint de transición para oficina**: `POST /nucleo/viajes/{id}/transicion`, permiso `operacion:escribir`; el destino se valida contra la matriz leída de la base | `api.py:206-210` (dependencia), `:220-232` (endpoint); `servicio_transiciones.py:146-179` | 🟢 |
| 29 | **Existe endpoint de anulación**: `POST /nucleo/viajes/{id}/anular`, permiso `comercial:aprobar` (no `operacion:escribir`), motivo obligatorio (≥5 caracteres), lee la matriz y libera reservas **antes** de cambiar el estado, con motivo y actor | `api.py:213-217`, `:235-246`; `servicio_transiciones.py:282-323`; esquema `schemas.py:2099-2109` | 🟢 |
| 30 | La oficina tiene **prohibidos por política de servicio** tres destinos: `facturado`/`cobrado` (frozenset), `anulado` (flujo propio) y `asignado` sin tracto/rampla/chofer (debe usarse `/asignar`) | `servicio_transiciones.py:65-67`, `:156-165`, `:192-205`, `:211-224` | 🟢 |
| 31 | El flujo del conductor es **independiente** y no lee la tabla: usa un `dict` de 6 aristas, **más estricto** que la matriz (solo avanza; no permite volver, p. ej. `en_carga → asignado`) | `servicio_conductor.py:51-58`, uso en `:156` y `:190-200`; matriz permite retrocesos en `0004:783,788,791,794,797,800` | 🟢 |
| 32 | Escritores de `viajes.estado` en el núcleo: alta ⇒ `confirmado`; asignar ⇒ `asignado`; oficina ⇒ aristas de la matriz menos 3 políticas; conductor ⇒ 6 aristas; cierre de expediente ⇒ `cerrado`; facturación ⇒ `facturado`; trigger de pago ⇒ `cobrado` | `servicio_disponibilidad.py:951`, `:1487-1497`; `servicio_transiciones.py:234-242`; `servicio_conductor.py:209-217`; `servicio_expediente.py:1261-1277`; `servicio_facturacion.py:644-651`; `fn_factura_estado` `0013:202-209` | 🟢 |
| 33 | `facturado` exige POD **y** OC en la base | `fn_viaje_facturacion` `0009:65-93` (`POD` `:80-87`, `OC` `:89-93`) | 🟢 |
| 34 | `facturado` **no** exige que exista factura, y `cobrado` **no** exige pago: la matriz autoriza la arista y nada más la condiciona | `0004:807-808` + `0009:76-93` (único gate) + `0013:202-209` (único escritor de `cobrado`) | 🟢 (código) / 🟡 (que un `UPDATE` manual pase: lo confirmaría una prueba con rol real) |
| 35 | `anulado` es terminal, no se reabre, y borrar un viaje fuera de `borrador`/`cotizado` está bloqueado | `0004:1493-1495`, `:1457-1463` | 🟢 |
| 36 | Hay pruebas de integración de la transición de oficina y de la anulación: matriz (arista inválida), motivo, `facturado` rechazado, conflicto de versión, viaje de otra empresa, anulación con reservas y eventos, doble anulación, `cerrado → anulado`, permiso `comercial:aprobar` | `backend/tests/test_nucleo_transiciones.py:280,320,348,372,453,492,519,582,613,640`; módulo marcado `integracion` (`:76`) con `skip` explícito si falta `0004` (`:101`) | 🟢 |
| 37 | Huecos de prueba: `cobrado` por la vía de oficina no se prueba (solo `facturado`); no hay prueba de que el `dict` del conductor sea subconjunto de la matriz; no hay prueba de base que intente `UPDATE` directo a `cobrado` sin pago | `test_nucleo_transiciones.py:372` es el único caso de estado financiero; grep de `TRANSICIONES_CONDUCTOR` en `backend/tests` = 0 | 🟢 |
| 38 | El alta de viaje **no** acepta `estado`: no hay bypass en creación | `schemas.py:204-205` (`extra="forbid"`, sin campo `estado`) | 🟢 |
| 39 | El legacy no tiene ruta: `backend/app/api/routes/` solo contiene `auth.py`, y `public` fue retirado con inventario de 17 tablas | `glob` de `backend/app/api/**/*.py`; `0028:15-28` | 🟢 |
| 40 | Existe precedente de máquina de estados **en base** para el módulo de agentes (`hoja_ruta`): el grafo vive en una función de trigger, no en tabla | `fn_hoja_ruta_transicion` `0022:349-392`, trigger `:390-392` | 🟢 |

**Contradicción documental detectada (no se corrige aquí):**
`docs/arquitectura/matriz-plan-vs-codigo.md:55` y `docs/datos/garantias.md:71` citan
`viajes.py:36-41` con una constante `TRANSICIONES` del legacy como fuente de autoridad en
Python. Ese archivo **no existe** (hecho 39). Además, `docs/datos/garantias.md:71`
describe la autoridad como "Tabla + `TRANSICIONES` en Python", cuando la realidad es
"tabla + trigger + lectura de la tabla por el servicio de oficina". Se reporta a
`orquestador`; no cambia las decisiones de este ADR, pero sí su punto de partida.

---

## 2. Problema

**Dos preguntas verificables, cada una con un "sí/no" observable:**

1. *¿Dónde debe vivir un parámetro que varía por empresa, de modo que exista una sola
   fila de verdad, historial y aislamiento por tenant, sin crear una segunda tabla
   clave/valor?* — La respuesta ya está implementada (`configuracion_empresa`); lo que
   falta es el catálogo de claves, y la petición de tres tablas nuevas lo duplicaría.
2. *¿Qué garantiza que un viaje no pase a un estado ilegal, y qué impide que un flujo
   (oficina, conductor, facturación) escriba un estado que no le corresponde?* — La
   legalidad ya la impone la base (`0004:1840-1841`); la **política por flujo** la impone
   el servicio, y una de sus piezas (`cobrado`) no tiene condición en la base.

---

## 3. Decisión 1 — Configuración por tenant

### 3.1 `tenant_config`: alternativas

| Alternativa | Ventajas | Costes / riesgos | Reversible | Impacto en frontend | Impacto en datos |
|---|---|---|---|---|---|
| **A. Extender el catálogo de `configuracion_empresa`** *(recomendada)* | Cero DDL; hereda vigencia, `EXCLUDE`, inmutabilidad, RLS+`FORCE`, `GRANT` sin `DELETE` ya probados (`0026`); una sola fila de verdad; el catálogo sigue donde `0026:46-49` decidió que estuviera | Cada clave nueva exige tocar servicio **y** pantalla (hoy el catálogo está triplicado, hecho 9); la base no valida tipos salvo `iva_porcentaje` | **Alta**: retirar una clave es dejar de leerla; las filas quedan como historial | Añadir la clave a `CATALOGO` de la pantalla (o hacer la pantalla dirigida por el servidor) | Ninguno: sin `DROP`, sin migración |
| **B. Tabla nueva `nucleo.tenant_config`** | Nombre que pidió el dueño; libertad de esquema | Duplica tabla, triggers, política y `GRANT`; **dos** fuentes para "el parámetro de la empresa"; toda lectura nueva debe elegir una y las existentes seguirán leyendo la vieja; obliga a migrar/duplicar las 4 claves y su historial; viola `AGENTS.md` §3.1 | Media: revertir exige consolidar datos ya escritos en la tabla nueva | Ninguno si se mantiene la API; alto si se expone una segunda ruta | Alto: dos historiales que reconciliar |
| **C. Vista `nucleo.tenant_config` sobre `configuracion_empresa`** | Satisface el nombre sin segunda escritura | Una vista **no** añade garantía: si es escribible exige `INSTEAD OF` (segunda ruta de escritura); si corre con privilegios del dueño **salta RLS** salvo `security_invoker = true` (PG15+; el proyecto usa PG17, `supabase/config.toml:41`); superficie nueva que documentar y probar | Alta: `DROP VIEW` | Ninguno | Ninguno |
| **D. Tabla de **catálogo** de claves + `configuracion_empresa` para valores** | Resuelve el problema real (agregar claves sin desplegar) sin duplicar valores | Validación dinámica de tipos/rangos en el servicio; riesgo de desincronización con las columnas tipadas de `empresas`; **no** es lo que se pidió | Alta | Cambia la pantalla a dirigida por servidor | Bajo: tabla de metadatos |

**Decisión: A.** No se crea `tenant_config` (ni tabla ni vista) en esta ola. Si en el
futuro un consumidor externo exige ese nombre, la única forma admisible es una **vista
de solo lectura** con `WITH (security_invoker = true)` y **sin** `GRANT` de escritura
(Apéndice B.0); nunca una tabla paralela (B) ni una vista escribible (C).

**Descartadas:** B porque crea la segunda fuente de verdad que `AGENTS.md` §3.1 prohíbe y
obliga a reconciliar historiales; C porque una vista no agrega ninguna garantía y, mal
configurada, salta RLS; D **no se descarta por mala**, se **pospone**: ataca otro
problema (catálogo editable sin despliegue) y requiere ADR propio (`D-27`).

### 3.2 Reglas normativas (A)

1. **Un valor, una tabla.** Todo parámetro que varía por empresa y no es un atributo
   estable de identidad/operación vive en `nucleo.configuracion_empresa`. Los atributos
   estables con `CHECK` (`empresas.*`, `configuracion_costos.*`) **se quedan** donde
   están: moverlos no resuelve nada y rompe lectores (`politicas.py:67,84,109`).
2. **El catálogo es del servicio y es deny-by-default.** Clave fuera de `CATALOGO` ⇒
   rechazo (`servicio_configuracion.py:54-58`). La base solo garantiza forma
   (`0026:125`), vigencia y tenant.
3. **Ninguna clave nueva sin dueño, tipo, rango y lector.** Antes de agregar una clave se
   declara: tipo (`entero`/`numero`/`texto`/`booleano`), rango o enumeración, default o
   semántica de "sin valor", **quién la lee** y qué pasa si falta. Si no hay lector, no
   se crea (`INV-TC06`, que nace violado por `empresas.exigir_oc`).
4. **La pantalla no puede ser la segunda autoridad de tipos.** Mientras el catálogo siga
   duplicado en `frontend/src/app/(app)/configuracion/page.tsx:38-82`, toda clave nueva
   se agrega en los dos lugares y una prueba debe fallar si divergen (`INV-TC03`). La
   solución definitiva (pantalla dirigida por el servidor) es deuda de `frontend`, no de
   este ADR.
5. **Prohibido `UPDATE` del valor.** Cambiar un valor = cerrar la vigencia e insertar
   fila nueva en la **misma** transacción, con el mismo instante (patrón implementado en
   `servicio_configuracion.py:159-187`). El trigger lo impone (`0026:214-223`).

### 3.3 `tenant_reglas_entidad`: granularidad, constraints y validación de la entidad

**Decisión: no se crea en la Ola 1.** Dos razones verificadas:

- el único caso real de "regla por entidad" en la capa de agentes **ya existe**:
  `nucleo.permisos_contacto` (`0021:243-265`), con FK compuesta y unicidad por
  `(contacto, componente, variable)`. Crear un EAV al lado es una segunda fuente;
- el parámetro por entidad del dominio operativo (comisión del chofer) está como
  **columna tipada** (`0004:299-301`), que es la forma correcta cuando el conjunto de
  claves es pequeño y conocido.

**Si un ADR posterior lo autoriza**, el contrato (Apéndice B.2) se resume así:

| Aspecto | Regla |
|---|---|
| Discriminador | `entidad nucleo.tipo_entidad_regla` (enum dedicado), **no** `text` libre |
| Identidad de la entidad | **una columna FK nullable por tipo** + FKs **compuestas** `(empresa_id, X_id)`; **prohibido** `entidad_id uuid` sin FK |
| Exclusividad | `CHECK` que exige exactamente una FK no nula y coherente con `entidad` (patrón `0004:354-358`) |
| Clave/valor | `clave text` con formato `^[a-z][a-z0-9_]{2,63}$`, `valor jsonb`; catálogo en el servicio del dominio |
| Vigencia | `[vigente_desde, vigente_hasta)` con `EXCLUDE USING gist`; una sola fila vigente por entidad+clave |
| Tenant | FK `empresa_id`, RLS+`FORCE`, política `tenant_empresa` |
| Historial | cerrar vigencia, no editar valor; `DELETE` bloqueado por trigger y por ausencia de `GRANT` |

**Cómo se valida la entidad sin FK polimórfica:** *no se valida* — se evita el problema.
Con una FK compuesta por tipo, PostgreSQL garantiza existencia **y** pertenencia a la
misma empresa; el `CHECK` garantiza que la fila declare el tipo correcto. La alternativa
"`entidad_id` + trigger que consulte la tabla destino según el enum" es un trigger con SQL
dinámico: pierde integridad referencial (borrados, `on delete`), no es indexable y
duplica en código lo que la FK ya hace. **Descartada.**

Detalle técnico que `datos` no debe improvisar: un `EXCLUDE` sobre columnas nullable **no**
detecta solapes (las comparaciones con `NULL` no son verdaderas). Si se usa el patrón de
FKs por tipo, la restricción debe construirse sobre expresiones con centinela
(Apéndice B.2).

### 3.4 `tenant_suscripciones`: qué puede y qué no puede decidir la arquitectura

**Decisión: no se crea en la Ola 1.** La arquitectura **puede** decidir el mecanismo; el
contenido es del dueño.

**Puede decidir la arquitectura (y queda decidido aquí):**

- toda fila pertenece a **una** empresa (`empresa_id` FK), con RLS+`FORCE` y política
  `tenant_empresa`; sin `DELETE` para `tei_app` (se cierra la vigencia, no se borra);
- la historia contractual es **por vigencia** `[desde, hasta)` sin solape por empresa
  (mismo mecanismo que `0026`, no uno nuevo);
- la suscripción **no** crea un segundo "encendido/apagado": el gate operativo sigue
  siendo `nucleo.modulos_empresa.habilitado` (`0023:183-202`) y el estado de la empresa
  sigue siendo `nucleo.empresas.estado` (`0004:34,126`). Una suscripción puede
  *explicar* por qué un módulo está apagado; **no** puede ser la condición que el código
  evalúe para dejarlo operar, o habrá dos verdades;
- cualquier límite debe tener **un punto de cumplimiento declarado** antes de crear la
  columna. Un límite sin punto de cumplimiento es documentación disfrazada de esquema.

**No puede decidir la arquitectura (va a pregunta):**

- qué es un plan, cuántos hay y cómo se llaman (`D-25`);
- precio, moneda, periodicidad, prorrateo, impuestos y quién factura (`D-25`, `P-14`);
- qué límites son comerciales y qué pasa al excederlos (bloquear, avisar, cobrar);
- qué ocurre con el histórico al cambiar de plan (¿se reescribe? ¿se cierra vigencia?).

Con `D-25`/`D-26` respondidas, el contrato de ejecución está en el Apéndice C.

### 3.5 Contrato de la migración `0030_tenant_config_agentes.sql`

**Recomendado: no escribirla.** Para las tres tablas pedidas, `0030` tendría **0
objetos**; crearla vacía o con objetos no decididos solo agrega numeración y deuda.

**Precondiciones para cerrar el tema sin migración** (las ejecuta `datos` o `qa` cuando
haya base):

| # | Verificación | Resultado esperado |
|---|---|---|
| C1 | `select count(*) from nucleo.configuracion_empresa` | > 0 con `iva_porcentaje` vigente por empresa (`0026:355-362`) |
| C2 | Claves distintas en la tabla vs catálogo del servicio | diferencia 0 (`INV-TC03`) |
| C3 | `has_table_privilege('tei_app','nucleo.configuracion_empresa','DELETE')` | `false` |
| C4 | `select count(*) from pg_policies where tablename='configuracion_empresa' and policyname='tenant_empresa'` | 1 |
| C5 | Parámetros de configuración sin lector (lista curada) | 0; hoy falla con `exigir_oc` (`INV-TC06`) |
| C6 | `select count(*) from pg_class where relname in ('tenant_config','tenant_reglas_entidad','tenant_suscripciones')` dentro de `nucleo` | 0 (lo que este ADR decide) |

**Si el dueño confirma las tablas contra esta recomendación**, el contrato completo de
`0030` (objetos, columnas, precondiciones, RLS+`FORCE`, `GRANT`s, triggers, verificación
en transacción, rollback y orden) está en el **Apéndice A**. `datos` lo ejecuta sin
volver a decidir el modelo; no se escribe aquí.

---

## 4. Decisión 2 — Autoridad de la máquina de estados del viaje

### 4.1 Lo que la base garantiza y lo que garantiza el servicio

La tabla decide **qué aristas existen**. El servicio decide **qué flujo puede pedir
cuál**. Declararlo por estado evita vender una garantía que no existe.

| Estado destino | Escritores | ¿La oficina puede pedirlo? | Garantía en **base** | Garantía solo en **servicio** |
|---|---|---|---|---|
| `borrador`, `cotizado`, `confirmado` | alta (`confirmado`), oficina (cotización y retrocesos) | Sí, si la arista existe | grafo + validaciones de tarifa/OC (`0004:1310-1358`) | — |
| `asignado` | `/nucleo/viajes/{id}/asignar`; oficina solo si ya tiene recursos | Condicionado | `EXCLUDE` de disponibilidad (`0004:703-761`) + documentos (`0015`) + `fn_viaje_validar` | la oficina deriva a `/asignar` (`servicio_transiciones.py:211-224`) |
| `en_carga`…`pod_pendiente` (6 aristas) | conductor y oficina | Sí | grafo + `version` optimista | el conductor solo avanza (`servicio_conductor.py:51-58`) |
| `cerrado` | `/nucleo/expediente/viajes/{id}/cerrar`; oficina (>`descargado`/`pod_pendiente`) | Sí | grafo; `DELETE` y congelamiento financiero (`0004:1452-1508`) | checklist completo (`puede_cerrar`) |
| `facturado` | emisión de factura | **No**: frozenset de servicio (`:156-165`) | **POD + OC** (`0009:80-93`) | que el viaje esté `cerrado` (`servicio_facturacion.py:521-524`) |
| `cobrado` | trigger de pago (`0013:202-209`) | **No**: mismo frozenset | **ninguna** | — |
| `anulado` | `/nucleo/viajes/{id}/anular` (`comercial:aprobar`) | Sí, por su propio endpoint | grafo + `motivo_anulacion` (`0004:1531-1534`) + terminal (`:1493-1495`) | permiso propio y liberación de reservas con motivo/actor (`servicio_transiciones.py:304-323`) |

**Las 29 aristas tienen un manejador en código** (oficina, asignación, conductor, cierre
de expediente, facturación o anulación): no hay aristas huérfanas (`INV-EST08`). Matiz
verificado: **5 de ellas** parten de `borrador` o `cotizado`, estados que **ningún
endpoint produce** — el alta nace directamente en `confirmado`
(`servicio_disponibilidad.py:951`). La fase de cotización existe en el catálogo pero no
tiene alta por API; es una observación de producto, no un defecto de la máquina de
estados.

### 4.2 Alternativas evaluadas

| Alternativa | Ventajas | Costes / riesgos | Reversible | Impacto frontend | Impacto datos |
|---|---|---|---|---|---|
| **A. Tabla = legalidad (base); política por flujo en el servicio; gates financieros en base** *(recomendada)* | Es lo que ya existe y funciona (hechos 25–30); el grafo no se puede burlar con SQL; cada flujo expresa su política sin tocar el esquema; cero migración en esta ola | La política de oficina vive en Python: un refactor puede retirar el frozenset sin que falle nada (falta prueba, hecho 37); el rol único `tei_app` no distingue flujos | Alta | Ninguno | Ninguno (salvo `0031` opcional) |
| **B. Grafo en Python como autoridad** | Código explícito | `UPDATE` directo, scripts y el futuro agente **saltan** el grafo; viola `AGENTS.md` §3.11; habría que **apagar** `fn_viaje_transicion` (ya probado) | Baja | Ninguno | Alto: estados ilegales sin detector |
| **C. Mover el grafo a una función de trigger** (patrón `hoja_ruta`, `0022:349-392`) | Una sola definición en base; sin tabla que leer | Cambiar una arista exige migración; se pierde el catálogo consultable del que ya dependen `servicio_transiciones` y la UI (`_destinos`, `:119-125`); `requiere_motivo` pasaría a `if` dispersos | Media | Habría que reexponer "destinos permitidos" | Medio: se destruye el catálogo que funciona |
| **D. Columna `actor` en `transiciones_viaje` que declare el flujo** | Mueve la política de oficina/conductor a datos | No expresa "solo hacia adelante" (política del conductor, hecho 31); **no** es garantía: sin roles PG por flujo, `tei_app` puede escribir cualquier estado; añade migración y una tercera semántica que mantener | Alta | Cambia de dónde salen las acciones | Bajo (29 filas) |
| **E. GUC de flujo (`nucleo.flujo`) exigido por el trigger** | Permitiría bloquear `facturado` desde oficina en la base | El GUC lo fija la aplicación: un servicio con `UPDATE` y el GUC puesto lo salta; garantía aparente; un fallo del listener deja el trigger sin contexto (fail-open o fail-closed inesperado) | Media | Ninguno | Ninguno |

**Decisión: A.** **Descartadas:** B por violar la regla de la garantía crítica y
retroceder sobre algo ya impuesto y probado; C porque destruye el catálogo consultable
sin resolver nada que A no resuelva; D porque no expresa la política real (solo
avanzar) y no es garantía; E porque su modo de fallo es "parece que bloquea" sobre un
rol que puede escribir igual.

### 4.3 Reglas normativas

1. **La legalidad vive en la tabla y en el trigger; no se duplica en Python.** Ningún
   servicio declara una lista de aristas legales: consulta la tabla
   (`servicio_transiciones.py:109-117`) y, si necesita política, la aplica **después**
   como exclusión explícita y probada. La lista del conductor
   (`servicio_conductor.py:51-58`) es política más estricta, no legalidad, y debe seguir
   siendo subconjunto probado de la tabla (`INV-EST09`).
2. **La política por flujo es explícita, con nombre y prueba.** `ESTADOS_SOLO_FACTURACION`
   y el bloqueo de `anulado`/`asignado` en oficina son política, no legalidad: cada uno
   lleva su prueba (§6, paso 2) y una prueba de mutación que la retire debe romper la
   suite.
3. **La tabla no se toca desde la aplicación.** Sigue siendo catálogo de migraciones:
   `GRANT SELECT` únicamente (`0020:270-271`). Cambiar el grafo es una migración con
   precondiciones y rollback.
4. **`facturado` y `cobrado` son derivados, no comandos.** `facturado` solo se origina en
   la transacción de emisión (que exige `cerrado` en `servicio_facturacion.py:521-524` y
   POD+OC en la base); `cobrado` solo desde `fn_factura_estado` cuando el saldo llega a 0
   (`0013:190-210`). Si el negocio necesita corregir un estado financiero, se corrige el
   hecho (nota de crédito, anulación, re-emisión), no la etiqueta.
5. **Todo estado con impacto en dinero declara su autoridad.** Si la precondición está
   solo en el servicio, no se presenta como garantía (§4.1). Cuando el contador
   considere que el error es inaceptable, se mueve a la base con migración,
   precondición de 0 filas y mutación (`0031`, §4.4).
6. **El flujo del conductor mantiene su política en el servicio, pero como
   subconjunto probado.** No puede permitir una arista que la tabla no tenga; esa
   propiedad se prueba, no se supone (`INV-EST09`).

### 4.4 Qué evita que la oficina marque `facturado` (o `cobrado`) a mano

| Capa | Qué hace | ¿Garantía? | Evidencia |
|---|---|---|---|
| **Endpoint de oficina** | Rechaza `facturado` y `cobrado` con error de dominio, aunque la matriz los permita | Sí, **de código**: un refactor puede quitarlo si no hay prueba | `servicio_transiciones.py:65-67`, `:156-165`; prueba existente solo para `facturado` (`test_nucleo_transiciones.py:372`) |
| **Matriz** | Solo permite `cerrado → facturado` y `facturado → cobrado` | Sí, de base | `0004:807-808`; trigger `0004:1840-1841` |
| **Gate de facturación** | `facturado` exige POD **y** OC | Sí, de base | `0009:80-87`, `:89-93` |
| **Gate de pago** | `cobrado` exigiría factura pagada | **No existe** | `0004:808` + `0013:202-209` |
| **Gate de factura** | `facturado` exigiría una fila en `factura_viajes` | **No existe** | `0009:76-93` valida POD y OC, no factura |
| **Detector** | Consulta que detecte `facturado` sin factura o `cobrado` con saldo > 0 | **No existe** | — |

**Decisiones derivadas:**

- `INV-EST04` (facturado ⇒ POD + OC) ya está impuesto; se mantiene.
- `INV-EST05` (`cobrado` ⇒ factura pagada) e `INV-EST06` (`facturado` ⇒ existe
  `factura_viajes`) quedan **propuestos y no impuestos**. Mecanismo, en `0031` si `P-14`
  lo autoriza: trigger `BEFORE UPDATE` en `nucleo.viajes` (o ampliación de
  `fn_viaje_transicion`) que exija la fila correspondiente al entrar a
  `facturado`/`cobrado`. Precondición obligatoria antes de crearlo:

  ```sql
  select count(*) from nucleo.viajes v
   where v.estado in ('facturado','cobrado')
     and not exists (select 1 from nucleo.factura_viajes fv where fv.viaje_id = v.id);
  ```

  Debe devolver **0**; si devuelve filas, **se reportan, no se corrigen** (`AGENTS.md` §8).
- Mientras no exista el trigger, se exige el **detector** equivalente (misma consulta +
  `pagos_nucleo` vs saldo) con dueño `qa`/`datos` y periodicidad definida por operación:
  es la única evidencia de que no hay estados financieros inventados.

🟡 **No verificado:** que la transacción de `servicio_facturacion.py:630-668` deje la
fila de `factura_viajes` visible para un trigger `BEFORE UPDATE` sobre `viajes` en el
mismo statement (depende del *autoflush* de SQLAlchemy antes del `UPDATE`; no se ejecutó
aquí). Lo cierra la prueba de `INV-EST06` **antes** de escribir `0031`. Si no se cumple,
el gate va en un trigger `AFTER INSERT` sobre `factura_viajes` o en una restricción
`DEFERRABLE` verificada al `COMMIT`.

### 4.5 Deuda de `servicio_conductor.py` y orden de pago

`TRANSICIONES_CONDUCTOR` (`servicio_conductor.py:51-58`) **no es una copia de la
legalidad**: es una política **más estricta** (solo avanza) y hoy es un subconjunto
exacto de la matriz (hecho 31). El riesgo no es un viaje ilegal, es la **deriva
silenciosa**: si mañana cambia la matriz y el `dict` no, nadie lo detecta.

1. **Ahora (S, `qa`):** prueba que afirma `dict ⊆ matriz` (comparando contra
   `select estado_origen, estado_destino from nucleo.transiciones_viaje`). No cambia
   comportamiento; convierte la deriva en rojo. Cierra el hueco del hecho 37.
2. **Ahora (S, `qa`):** prueba de que el endpoint de oficina rechaza **`cobrado`**
   además de `facturado`, y de que rechaza `anulado` derivando al endpoint propio.
3. **Después (opcional, `backend`):** si se quiere que la política deje de estar en una
   constante, `servicio_conductor.py` puede leer la matriz y aplicar el filtro "solo
   aristas que avanzan en el orden del ciclo operativo". **No** se recomienda: agrega una
   regla de orden implícita; la constante probada es más honesta y más barata.
4. **Después (M, `datos` — solo si `P-14` lo pide):** `INV-EST05`/`INV-EST06` en `0031`
   con el gate financiero, su precondición de 0 filas y su prueba de mutación.

**No se hace:** mover el grafo a Python, mover el grafo a una función, agregar `actor`,
ni agregar un GUC de flujo.

---

## 5. Invariantes propuestos

Enunciados verificables. "Mecanismo" dice quién lo impone hoy; si dice *propuesto*, no
está impuesto y no puede citarse como garantía.

### 5.1 Configuración por tenant

| ID | Enunciado verificable | Mecanismo | Estado |
|---|---|---|---|
| **INV-TC01** | Toda fila de configuración pertenece a una empresa existente y es invisible e inescribible fuera de `app.empresa_id`: sin contexto ⇒ 0 filas; `INSERT` con otra empresa ⇒ `42501` | FK `0026:123-124`; RLS+`FORCE` `0026:270-277`; patrón probado en `0020` | 🟢 impuesto |
| **INV-TC02** | A lo sumo una fila vigente por `(empresa, clave)` y dos vigencias de la misma clave nunca se solapan: `INSERT` solapado ⇒ `23P01`; segundo vigente ⇒ `23505` | `EXCLUDE` `0026:140-144`; índice parcial `0026:165-167` | 🟢 impuesto |
| **INV-TC03** | El conjunto de claves es **uno**: toda clave distinta en `nucleo.configuracion_empresa` está en el catálogo del servicio y en la pantalla, y viceversa; diferencia = 0 | Servicio `servicio_configuracion.py:38-43`; pantalla `configuracion/page.tsx:38-82`; **sin prueba que los compare** | 🟡 implementado, **sin detección** (§6 paso 1) |
| **INV-TC04** | El valor de una fila cerrada no se edita y el historial no se borra: `UPDATE valor` ⇒ `23514`; `DELETE` ⇒ `23514`; `tei_app` sin `DELETE` | `0026:198-232`, `:234-246`, `:282` | 🟢 impuesto |
| **INV-TC05** | Toda clave escrita pasa por el catálogo: clave desconocida ⇒ error de datos, nunca una fila nueva | Servicio `:54-58`, `:208-212`; **la base no lo impone** (`0026:46-49`) | 🟢 en servicio / 🔴 en base (por diseño) |
| **INV-TC06** | Ningún parámetro de configuración existe sin lector declarado, y su default es único: DDL y ORM no pueden diferir | Requiere prueba estática + corregir `empresas.exigir_oc` (sin lector) y `dias_alerta_documentos` (DDL 30 vs ORM 14) | 🔴 **nace violado hoy** |

### 5.2 Máquina de estados

| ID | Enunciado verificable | Mecanismo | Estado |
|---|---|---|---|
| **INV-EST01** | `viajes.estado` solo cambia por una arista de `nucleo.transiciones_viaje`: `UPDATE` a un destino no listado ⇒ `23514` | `fn_viaje_transicion` `0004:1511-1529`; trigger `0004:1840-1841` | 🟢 impuesto |
| **INV-EST02** | Toda arista con `requiere_motivo = true` exige `motivo_anulacion` no nulo (10 de 29, todas hacia `anulado`) | `0004:1531-1534`; catálogo `0004:781-806` | 🟢 impuesto |
| **INV-EST03** | `anulado` es terminal y sella autor y fecha: `anulado → X` ⇒ `23514`; `anulado_por` nunca queda nulo | `0004:1493-1495`; `0004:1536-1543` | 🟢 impuesto |
| **INV-EST04** | `facturado` sólo desde `cerrado` y sólo con POD y OC: sin POD o sin OC ⇒ `23514` | `0004:807`; `0009:80-93` | 🟢 impuesto |
| **INV-EST05** | `cobrado` sólo existe si la factura del viaje está pagada: `cobrado` sin factura pagada ⇒ rechazo | **No impuesto**: la arista `facturado→cobrado` (`0004:808`) no condiciona nada; `0013:202-209` es el único escritor, no el único permitido | 🔴 **propuesto** (`0031` + detector) |
| **INV-EST06** | `facturado` implica al menos una fila en `nucleo.factura_viajes` para ese viaje | **No impuesto**: `0009:76-93` valida POD y OC, no factura | 🔴 **propuesto** (`0031` + detector; 🟡 orden de *flush*, §4.4) |
| **INV-EST07** | La oficina no puede fijar estados financieros ni de anulación: `POST /viajes/{id}/transicion` con `facturado`, `cobrado` o `anulado` ⇒ error de dominio, aunque la matriz los permita | `servicio_transiciones.py:65-67`, `:156-165`, `:192-205`; prueba solo para `facturado` | 🟢 implementado / 🟡 **cobertura parcial** (§6 paso 2) |
| **INV-EST08** | Toda arista del catálogo tiene un manejador identificado en código; ninguna arista es inalcanzable por falta de escritor | Hoy 29/29 con manejador (hecho 32 + §4.1); 5 parten de `borrador`/`cotizado`, que la API no produce (no es falta de manejador, es falta de alta); sin prueba que lo afirme | 🟢 de hecho / 🟡 sin detección |
| **INV-EST09** | La política del conductor es un subconjunto de la matriz: ninguna arista del `dict` puede faltar en `nucleo.transiciones_viaje` | `servicio_conductor.py:51-58`; **sin prueba** (hecho 37) | 🟡 implementado, **sin detección** (§6 paso 1) |
| **INV-EST10** | El catálogo de estados es de solo lectura para la aplicación: `tei_app` no puede insertar ni actualizar aristas | `0020:270-271`; probado con rol real (`0020_01:378-386`) | 🟢 impuesto |

---

## 6. Plan de migración y rollback

| Paso | Acción | Dueño | Criterio de aceptación observable | Rollback |
|---|---|---|---|---|
| 1 | **Sin migración**: pruebas de detección — catálogo único (`INV-TC03`), `dict` del conductor ⊆ matriz (`INV-EST09`), aristas con escritor (`INV-EST08`) | `qa` | Las tres verdes; si se agrega una clave en un solo lugar, o una arista al `dict`, **rojo** | Revertir el commit de pruebas |
| 2 | **Sin migración**: ampliar la prueba de INV-EST07 a `cobrado` y a `anulado` (derivación al endpoint propio) | `qa` | `POST /transicion` con `cobrado` ⇒ error de dominio; con `anulado` ⇒ error que nombra el endpoint de anulación | Revertir el commit |
| 3 | **`0030` no se escribe** (`0` objetos). Se ejecutan C1–C6 de §3.5 como evidencia de cierre | `datos` | C1–C6 con el resultado esperado; C5 hoy **falla** (`exigir_oc`) y queda como deuda abierta, no se corrige aquí | Nada que revertir |
| 4 | *(Sólo si el dueño confirma las tablas)* `0030` según Apéndice A, primero en `tei_test` | `datos` | Apéndice A §A.6 | `supabase/tests/0030_99_rollback.sql` (§A.7) |
| 5 | *(Sólo si `P-14` lo autoriza)* `0031`: gates `INV-EST05`/`INV-EST06` + detector | `datos` → `qa` | Precondición de 0 filas; `UPDATE` a `cobrado` sin pago ⇒ `23514`; mutación: retirar el trigger ⇒ la prueba falla | `0031_99_rollback.sql` (retirar trigger y función; sin pérdida de datos) |
| 6 | Registrar deuda y preguntas | `arquitectura` / `negocio-finanzas` | `INV-TC06`, `INV-EST05/06`, R-10/R-11 en `docs/arquitectura/deuda.md`; `D-24…D-28`, `P-14…P-16` en `docs/negocio/preguntas.md` | — |

**Regla de orden:** el paso 1 va **antes** del 3 y del 4: sin detector, "cerramos el
tema" es una afirmación sin evidencia. El paso 5 no comparte ventana con el 4.

---

## 7. Consecuencias

**Positivas**

- La Ola 1 se desbloquea **sin** DDL de tenant: el modelo ya existe y está probado
  (`0026`); lo que faltaba era la decisión, no la tabla.
- Se evita una cuarta superficie de configuración por empresa: hoy ya hay tres
  (`empresas.*`, `configuracion_empresa`, `configuracion_costos`) y el ADR prohíbe la
  cuarta.
- Queda escrito, por estado, **qué garantiza la base y qué no** (§4.1), y se reconoce lo
  que el código ya hace bien: la oficina lee la matriz, no la duplica.
- No se agrega esquema donde la política de servicio basta (sin `actor`, sin GUC de
  flujo): menos superficie, menos migraciones, menos garantías aparentes.
- Cero dependencias operativas nuevas: sin colas, sin workers, sin servicios.

**Negativas / deuda que genera**

- Agregar una clave de configuración sigue exigiendo despliegue y tocar dos archivos
  (servicio y pantalla). Es el precio de no tener catálogo en base (`D-27`).
- `tenant_reglas_entidad` no existirá: si en la Ola 2 aparece una regla por entidad que
  no encaje como columna ni como ACL de contacto, habrá que abrir un ADR de dominio (el
  Apéndice B acorta ese trabajo, no lo evita).
- `INV-EST05/06` quedan **no impuestos** hasta que `P-14` se responda; mientras tanto, la
  única protección de `cobrado` es de código (el frozenset de la oficina y que el único
  escritor previsto sea `fn_factura_estado`), sin gate en la base, y depende de que
  alguien mire el detector.
- `INV-TC06` nace violado (`exigir_oc` muerto, `dias_alerta_documentos` con dos
  defaults). Corregirlo exige una decisión (`D-28`) y, si se cambia el default, una
  migración de bajo impacto; no es de este ADR.

**Queda prohibido**

- Crear `tenant_config`, `tenant_reglas_entidad` o `tenant_suscripciones` sin un ADR que
  reemplace a este.
- Crear una segunda tabla clave/valor por empresa para cualquier concepto.
- Duplicar la matriz de transiciones en Python (el caso del conductor es **política**,
  no legalidad, y debe seguir siendo subconjunto probado).
- Presentar `INV-EST05`/`INV-EST06` como garantías mientras digan *propuesto*.

---

## 8. Criterios de aceptación

1. Este ADR existe, cita `archivo:línea` y permite a `datos` escribir —o decidir no
   escribir— `0030` sin re-decidir el modelo (§3.5 + Apéndice A).
2. Existe una prueba que falla si una clave del catálogo del servicio no está en la
   pantalla o en la base, o al revés (`INV-TC03`).
3. Existe una prueba que afirma `TRANSICIONES_CONDUCTOR ⊆ nucleo.transiciones_viaje` y
   falla si se agrega una arista ilegal al `dict` (`INV-EST09`).
4. `POST /nucleo/viajes/{id}/transicion` con `facturado`, `cobrado` y `anulado` devuelve
   error de dominio en los tres casos, sin escribir el estado (`INV-EST07`).
5. Con `tei_app` y contexto de empresa A: `configuracion_empresa` no devuelve filas de B;
   sin contexto devuelve 0; `DELETE` da `42501`; `INSERT` solapado da `23P01`.
6. `UPDATE nucleo.viajes SET estado='cobrado'` sin factura pagada: hoy **pasa**
   (documentado en §4.4); tras `0031` da `23514`, y la prueba de mutación al retirar el
   trigger lo demuestra.
7. Un `UPDATE` a una arista inexistente da `23514`; a `anulado` sin motivo, `23514`
   (regresión de `INV-EST01`/`INV-EST02` con SQL directo, no con el servicio).
8. La consulta de conciliación de §4.4 devuelve **0 filas** antes de intentar
   `INV-EST05/06`; si devuelve filas, se reportan y `0031` no se escribe.
9. `make unit` verde tras cada paso y `make test` verde cuando haya base; ningún `skip`
   nuevo (los existentes de `test_nucleo_transiciones.py:101` son por falta de `0004` y se
   reportan como tales, no como aprobados).

---

## 9. Lo que este ADR NO autoriza

- **No** crea, escribe ni aplica `0030` ni `0031`.
- **No** modifica `supabase/migrations/**`, `backend/**` ni `frontend/**`.
- **No** cambia `servicio_conductor.py`, ni retira `TRANSICIONES_CONDUCTOR`, ni toca
  `transiciones_viaje` ni `servicio_transiciones.py`.
- **No** agrega claves al `CATALOGO` de `servicio_configuracion.py` ni a la pantalla de
  configuración.
- **No** decide plan, precio, cupos, límites ni moneda (`D-25`, `D-26`, `P-14`).
- **No** decide si `cobrado`/`facturado` deben bloquearse en la base (`P-14`); solo
  especifica el mecanismo y la precondición si se decide.
- **No** corrige `empresas.exigir_oc`, el default de `dias_alerta_documentos`, ni el
  `fallback` del engine del núcleo (`database.py:120-124`): los registra como evidencia y
  deuda.
- **No** reabre `public` ni crea una segunda fuente de verdad para ningún concepto.
- **No** declara impuestos `INV-TC06`, `INV-EST05` ni `INV-EST06`: no lo están.

---

## 10. Preguntas abiertas y riesgos

| ID | Pregunta / riesgo | Evidencia | Destinatario | Estado |
|---|---|---|---|---|
| **D-24** | ¿La oficina debe poder **retroceder** estados operativos (p. ej. el chofer se equivocó de botón)? Hoy la matriz permite retrocesos (`0004:783,788,791,794,797,800`) y la oficina puede ejecutarlos con `operacion:escribir`; el conductor no. ¿Es el control deseado o falta una regla de "corrección con motivo"? | `servicio_transiciones.py:146-179`; `servicio_conductor.py:51-58`; `0004:779-808` | Dueño + despacho | **Abierta** |
| **D-25** | ¿Qué es un plan y qué se cobra por él? (nombre, periodicidad, moneda, prorrateo, quién factura) | No existe tabla ni documento con plan/precio; `0023:183-202` solo tiene el flag | Dueño + contador | **Abierta** — bloquea `tenant_suscripciones` |
| **D-26** | ¿Qué **límites** son comerciales y qué pasa al excederlos? Sin punto de cumplimiento declarado no se crea la columna | Hoy no hay ningún límite implementado; `modulos_empresa` es booleano | Dueño | **Abierta** |
| **D-27** | ¿El catálogo de claves debe poder editarse **sin desplegar**? Si sí, hace falta una tabla de catálogo (Apéndice B.1) y ADR propio | Catálogo triplicado (hecho 9) | Dueño + `arquitectura` | **Abierta** |
| **D-28** | `empresas.exigir_oc = false` por defecto, pero facturar **siempre** exige OC. ¿Cuál manda? | `0004:125` vs `0009:89-93`; `exigir_oc` sin lector | Dueño + `negocio-finanzas` | **Abierta** — hoy la base manda y el flag es letra muerta |
| **P-14** | ¿`facturado` sin factura y `cobrado` sin pago son errores que deben **bloquearse en base** o basta el control de servicio? Impacto en conciliación y cierre mensual | `INV-EST05/06`; `0009:76-93`; `0013:202-209` | Contador | **Abierta** — decide si hay `0031` |
| **P-15** | ¿Las reglas por entidad (p. ej. comisión del chofer) requieren **vigencia histórica** o el valor actual basta? Define si alguna vez hace falta el Apéndice B | `choferes.porcentaje_comision` `0004:299-301`; `0017:47` | Contador + dueño | **Abierta** |
| **P-16** | ¿Un viaje ya `facturado` puede anularse? Hoy la matriz **no tiene** `facturado → anulado` ni `cerrado → anulado` (solo hay salida hacia `cobrado`); el servicio lo explica al usuario y propone el flujo de facturación. Confirmar que es la política contable correcta y no un vacío | `0004:805-808`; `servicio_transiciones.py:292-302`; `test_nucleo_transiciones.py:613` | Contador | **Abierta** |
| — | **R-10:** el engine del núcleo cae al DSN privilegiado si falta `NUCLEO_DATABASE_URL`, con `WARNING` en lugar del `503` de `ADR-0005` §3.2.2. En ese modo toda garantía de este ADR (RLS de `configuracion_empresa`, políticas de `nucleo`) es inerte | `database.py:28-32`, `:120-124`, `:170-195` | `orquestador` + `operación` | **Abierto** (🔴 rol efectivo desplegado no verificado) |
| — | **R-11:** `UPDATE nucleo.viajes SET estado='cobrado'` pasa hoy la matriz sin comprobar pago (§4.4). No hay detector ni prueba | `0004:808`; `0013:202-209` | `datos` + `qa` | **Abierto hasta `0031`** |
| — | **R-12:** la exclusión de `facturado`/`cobrado` en la oficina es código, no base; solo `facturado` tiene prueba. Un refactor puede retirarla sin que nada falle | `servicio_transiciones.py:65-67`; `test_nucleo_transiciones.py:372` | `qa` | **Abierto hasta el paso 2 de §6** |

---

## Apéndice A — Contrato de `0030_tenant_config_agentes.sql`

> **Ejecutable sólo si el dueño confirma las tablas contra la recomendación (§0.1–0.3),
> mediante un ADR que reemplace a este.** `tenant_config` **no** está incluido en este
> contrato en ninguna variante: no tiene forma admisible como tabla (§B.0).

**A.1 Objetos (máximo)**

1. `nucleo.tipo_entidad_regla` (enum) y `nucleo.tenant_reglas_entidad` (tabla), con su
   función de inmutabilidad y 4 triggers (touch, version, audit, inmutable).
2. `nucleo.tenant_suscripciones` (tabla), con 3 triggers (touch, version, audit) y
   trigger de cierre de vigencia si `D-25` exige historial.
3. Funciones: `nucleo.fn_regla_entidad_inmutable()`,
   `nucleo.fn_suscripcion_vigencia()` (esta última solo si hay historial).
4. RLS + `FORCE`, política `tenant_empresa`, `GRANT`s, revocaciones a
   `anon`/`authenticated`, `COMMENT`s, verificación y rollback.

**A.2 Precondiciones (abortan con `23514`, no borran nada)**

| # | Consulta de detección | Esperado |
|---|---|---|
| P1 | `to_regclass('nucleo.tenant_reglas_entidad')`, `('nucleo.tenant_suscripciones')` | `NULL` |
| P2 | `nucleo.ctx_empresa()` existe; rol `tei_app` existe; `has_schema_privilege('tei_app','nucleo','USAGE')` | `true` |
| P3 | `pg_extension` contiene `btree_gist` | 1 fila |
| P4 | `to_regclass('nucleo.empresas')`, `('nucleo.configuracion_empresa')` | existen |
| P5 | `to_regclass('nucleo.modulos_empresa')` (para no reimplementar el flag) | existe |
| P6 | `select count(*) from nucleo.empresas where estado <> 'activa'` | informativo (`NOTICE`) |

**A.3 `tenant_reglas_entidad` — columnas y constraints mínimos**

```
id uuid pk default gen_random_uuid()
empresa_id uuid not null → nucleo.empresas(id) on delete restrict
entidad nucleo.tipo_entidad_regla not null
cliente_id uuid null, chofer_id uuid null, tracto_id uuid null, rampla_id uuid null,
contacto_id uuid null
clave text not null        -- ^[a-z][a-z0-9_]{2,63}$
valor jsonb not null
vigente_desde timestamptz not null default now()
vigente_hasta timestamptz null
created_at / created_by / updated_at / updated_by / version   (patrón 0026:116-120)
unique (empresa_id, id)
FKs compuestas (empresa_id, X_id) → tabla destino (empresa_id, id) on delete restrict
ck_regla_una_entidad: exactamente una FK no nula y coherente con `entidad`
ck_regla_vigencia: vigente_hasta is null or vigente_hasta > vigente_desde
ck_regla_clave_formato
exclude using gist (empresa_id with =, entidad with =, clave with =,
  (coalesce(cliente_id,'00000000-0000-0000-0000-000000000000'::uuid)) with =,
  (coalesce(chofer_id,  '…')) with =, (coalesce(tracto_id,'…')) with =,
  (coalesce(rampla_id,'…')) with =, (coalesce(contacto_id,'…')) with =,
  tstzrange(vigente_desde, vigente_hasta, '[)') with &&)
unique index uq_regla_vigente on (empresa_id, entidad, clave, <expresiones>)
  where vigente_hasta is null
```

Nota obligatoria: el `EXCLUDE` **debe** usar las expresiones con centinela; sobre
columnas nullable no detecta solapes (§3.3).

**A.4 `tenant_suscripciones` — columnas mínimas y prohibiciones**

Solo columnas cuyo contenido decida `D-25`/`D-26`: `empresa_id`, `plan_codigo text`
(catálogo en código, con `CHECK` de formato), `estado text` con `CHECK` acotado,
`vigente_desde`/`vigente_hasta`, control (`created/updated/version`),
`referencia_externa text` opcional. **Prohibido**: precio, moneda, cupos o `limites jsonb`
mientras `D-26` no fije el punto de cumplimiento; y **prohibido** `habilitado boolean`
(duplicaría `modulos_empresa`).

**A.5 RLS, `GRANT`s y triggers (iguales para ambas tablas)**

1. `enable` + `force row level security`.
2. Política `tenant_empresa` (`for all to public using (empresa_id = nucleo.ctx_empresa())
   with check (...)`), con `drop policy if exists` antes.
3. `grant select, insert, update` a `tei_app`; **`DELETE` nunca**; `revoke all` a
   `anon`/`authenticated` si existen (patrón `0026:285-296`).
4. Triggers: `trg_<tabla>_touch` → `nucleo.fn_touch()`; `trg_<tabla>_version` →
   `nucleo.fn_version()`; `trg_<tabla>_audit` → `nucleo.fn_auditoria()`. En
   `tenant_reglas_entidad`, además `trg_..._inmutable` → función nueva (no reutilizar
   `fn_config_empresa_inmutable`: no conoce `entidad` ni los ids).
5. `COMMENT` en tabla y en columnas no obvias (patrón `0026:147-161`).

**A.6 Verificación dentro de la transacción** (falla con `23514`)

- `relrowsecurity` y `relforcerowsecurity` = `true` en ambas tablas;
- 1 política `tenant_empresa` con `ctx_empresa` en `qual` y `with_check` por tabla;
- `has_table_privilege('tei_app', …, 'SELECT'|'INSERT'|'UPDATE')` = `true` y `'DELETE'`
  = `false`;
- `pg_constraint` con `contype='x'` = 1 en `tenant_reglas_entidad`;
- 3 (o 4) triggers por tabla, por nombre;
- `NOTICE` con el conteo de filas (0 esperado: la migración no siembra datos de negocio).

**A.7 Rollback**

`supabase/tests/0030_99_rollback.sql`: `drop table` de ambas, `drop function` de las
funciones nuevas y `drop type nucleo.tipo_entidad_regla`. Pérdida: los datos de tenant que
se hubieran escrito (ninguno al aplicar). `configuracion_empresa`, `empresas` y
`modulos_empresa` **no se tocan**. Probar ciclo aplicar → rollback → verificar 0 objetos →
re-aplicar (patrón `0021_99`/`0022_99`).

---

## Apéndice B — Contrato condicional de `tenant_config` (vista) y del catálogo de claves

**B.0 `tenant_config`: sin variante de tabla.** Si un consumidor exige el nombre:

```sql
create view nucleo.tenant_config with (security_invoker = true) as
select empresa_id, clave, valor, vigente_desde, vigente_hasta
  from nucleo.configuracion_empresa;
grant select on nucleo.tenant_config to tei_app;  -- sólo lectura
```

`security_invoker = true` es obligatorio: sin él la vista corre con los privilegios de su
dueño y **salta** RLS. Prohibido `INSTEAD OF` (sería una segunda ruta de escritura).

**B.1 Catálogo de claves (si `D-27` responde "sí, editable sin desplegar").** Tabla
`nucleo.catalogo_configuracion` (`clave` PK, `tipo`, `minimo`, `maximo`, `valores jsonb`,
`descripcion`, `activo`), global (sin `empresa_id`), `SELECT` para `tei_app`, escritura
solo por migración o rol de plataforma. El servicio valida contra esta tabla **en vez de**
`CATALOGO`; `INV-TC05` pasa de servicio a base. Requiere ADR propio por la validación
dinámica y por el riesgo de desincronización con `empresas.*`.

**B.2 Especificación de `tenant_reglas_entidad`.** Ver A.3. Enum inicial propuesto:
`('cliente','chofer','tracto','rampla','contacto')`. Agregar un valor exige migración
**y** una columna FK nueva: es intencional (evita el polimorfismo sin integridad).

---

## Apéndice C — Contrato condicional de `tenant_suscripciones`

Se ejecuta solo con `D-25` y `D-26` respondidas. Columnas, constraints, RLS, `GRANT`s y
triggers: A.4–A.6. Reglas adicionales:

1. **Un solo gate.** El código sigue leyendo `modulos_empresa.habilitado` y
   `empresas.estado`. La suscripción puede alimentar la decisión comercial de apagar un
   módulo, pero el apagado se escribe en `modulos_empresa`; no se evalúa la suscripción en
   el camino de autorización.
2. **Cumplimiento de límites:** cada límite aprobado en `D-26` debe declarar su punto de
   cumplimiento (tabla, consulta y código HTTP) **antes** de crearse la columna; el ADR de
   ese límite cita su `INV-`.
3. **Historial:** si hay historial, la fila se cierra (`vigente_hasta`) y se inserta una
   nueva; `DELETE` bloqueado. Si no hay historial, se documenta que el cambio sobrescribe
   y que queda en `fn_auditoria`.

---

## 11. Referencias para el handoff

| Pieza | Archivo / símbolo | Cambio esperado | Dueño |
|---|---|---|---|
| Catálogo de claves | `backend/app/nucleo/servicio_configuracion.py:38-43` | agregar claves solo con tipo/rango/lector declarados (`INV-TC06`) | `backend` |
| Prueba de catálogo único | `backend/tests/`, `frontend/**` | comparar servicio ↔ pantalla ↔ base (`INV-TC03`) | `qa` |
| Pantalla de configuración | `frontend/src/app/(app)/configuracion/page.tsx:38-82` | reflejar cada clave del catálogo; idealmente dirigida por servidor | `frontend` |
| Pruebas de matriz y política | `backend/tests/test_nucleo_transiciones.py` | `dict` del conductor ⊆ matriz; `cobrado`/`anulado` rechazados por oficina | `qa` |
| Evidencia de cierre de `0030` | `supabase/tests/` | C1–C6 de §3.5 | `datos` |
| `0031` (opcional) | `supabase/migrations/0031_*.sql` | gates `INV-EST05/06`; precondición de 0 filas; mutación | `datos` |
| Detector financiero | consulta de conciliación §4.4 | 0 filas antes de `0031`; después, alerta | `qa` + `operación` |
| Conductor | `backend/app/nucleo/servicio_conductor.py:51-58` | sólo prueba de subconjunto; **no** se cambia el `dict` en esta ola | `qa` |
| Registro de deuda | `docs/arquitectura/deuda.md` (dueño: `arquitectura`) | `INV-TC06`, `INV-EST05/06`, R-10/R-11/R-12 | `arquitectura` |
| Preguntas | `docs/negocio/preguntas.md` | `D-24…D-28`, `P-14…P-16` (numeración final de `negocio-finanzas`) | `negocio-finanzas` |
