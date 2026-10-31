# Fuentes de verdad — qué esquema manda por concepto

> **Pregunta que responde:** para cada concepto de negocio, ¿cuál es la fuente de
> verdad **de la aplicación** hoy, queda algún escritor en el otro esquema, y
> existe reconciliación del histórico?
> **Dueño:** `arquitectura` · **Verificado:** 2026-10-31 · **Método:** lectura
> estática de routers (solo queda `auth`), pantallas, servicios del núcleo,
> migraciones `0001`–`0026` y scripts; informes fechados de las Olas A/B/C.
> **Caduca si:** se agrega o retira un router/pantalla, se ejecuta la Ola D o se
> crea una sincronización.
> **Re-verificar con:**
> `grep -rn "public\\." backend/app/` (debe ser 1),
> `grep -rn "@/lib/api" frontend/src` (debe ser 0) y
> `grep -rn "insert into public" scripts/`.

> **Cambio de marco (2026-10-31).** Hasta la Ola C había **dos aplicaciones que
> escribían**: la legacy (`public`) y el núcleo (`nucleo`). Tras la Ola C **no
> queda ningún router, servicio ni pantalla que escriba en `public`**. El riesgo
> cambió de naturaleza: ya no es "dos escritores concurrentes", es **"un
> histórico duplicado sin migrar ni reconciliar"**. Este documento distingue
> ambas cosas en cada fila.

---

## 1. Regla de lectura

- **"Fuente de verdad de la aplicación"**: quién escribe hoy la operación. Si un
  concepto solo tiene escritores en `nucleo`, la aplicación manda ahí.
- **"Histórico"**: dónde viven las filas antiguas. Aunque la aplicación ya no
  escriba en `public`, **el dato sigue siendo la única copia** hasta la Ola D.
- **"Dos escrituras"** se refiere a **escritores de aplicación**, no a la
  existencia de filas históricas. Los scripts de seed/cutover se nombran aparte.
- 🟢 = leído en código/DDL con cita. 🟡 = inferido; se dice qué lo confirmaría.
  🔴 = no determinable sin base/ejecución.

---

## 2. Matriz por concepto (rev. 2, post Olas A/B/C)

| Concepto | Tabla(s) en `public` | Tabla(s) en `nucleo` | Fuente de verdad HOY | ¿Dos escrituras? | ¿Sincronización o detección de divergencia? | Riesgo |
|---|---|---|---|---|---|---|
| **Cliente** | `clientes` (`0001:47-58`) | `clientes` (`0004:158-186`) | **Aplicación: `nucleo`** (maestros/despacho). **Histórico: `public`**, sin migrar. | **No en la aplicación** 🟢. Residual: `seed_local.py:235` (solo local) | No hay job, vista ni tabla de mapeo. El cutover copia una vez y no sincroniza. | **Alto de datos**: mismo RUT con dos `id`; sin mapeo, D.1 no puede reconciliar |
| **Chofer** | `choferes` (`0001:60-70`) | `choferes` (`0004:282-321`) | **Aplicación: `nucleo`**. Histórico: `public`. | **No en la aplicación** 🟢. Residual: `seed_local.py:337` | Ninguna. `0017`/`0019` alinean el default del núcleo a 10 %, pero **no tocan `public`** | **Alto (dinero)**: el histórico conserva `porcentaje_produccion`; D.3 debe decidir qué porcentaje aplica a meses pasados |
| **Tracto** | `tractos` (`0001:72-84`) | `tractos` (`0004:191-230`) | **Aplicación: `nucleo`**. Histórico: `public`. | **No en la aplicación** 🟢. Residual: `seed_local.py:270` | Ninguna. El legacy no tiene tara/peso/capacidad; el cutover debe completarlos a mano | **Alto**: migrar sin `RET-11` deja la validación de sobrepeso con datos inventados |
| **Rampla** | `ramplas` (`0001:86-94`) | `ramplas` (`0004:235-277`) | **Aplicación: `nucleo`**. Histórico: `public`. | **No en la aplicación** 🟢. Residual: `seed_local.py:305` | Ninguna; el legacy no tiene capacidad ni tipo completo | **Alto**: ídem tracto (`RET-11`) |
| **Viaje** | `viajes` (`0001:97-112`) | `viajes` (`0004:542-698`) | **Aplicación: `nucleo`** (despacho/expediente/conductor). Histórico: `public`. | **No en la aplicación** 🟢 | Copia one-way en el cutover; migra `confirmado` y **sin recursos** (`cutover_legacy.py:6-13,378-401`); sin reconciliación. **`nucleo` aún lee `public.viajes` para un conteo** (`servicio_cutover.py:97`, G0.2) | **Crítico de datos**: los viajes cerrados no se migran; el histórico operativo queda en `public` |
| **Reserva / ocupación** | No existe | `reservas_recurso` (`0004:703-767`, `0006:9-18`) | `nucleo` es el único libro. | **No** 🟢: ya no hay API legacy que asigne recursos | No aplica para escrituras nuevas. Los viajes históricos de `public` **no tienen reserva** y no aparecerán en disponibilidad hasta D.1 | **Medio ahora** (antes Crítico, RA-02): el escritor legacy desapareció. Residual: el histórico importado debe generar reservas o declararse no ocupante |
| **Factura** | `facturas` (`0001:127-143`) | `facturas_nucleo` (`0013:10-49`) | **Aplicación: `nucleo`** (`/cobranza`). Histórico: `public`. | **No en la aplicación** 🟢 | Ninguna. Folios con reglas distintas en el histórico (`unique (numero_sii, cliente_id)` vs `unique (empresa_id, numero_factura)`) | **Crítico (tributario)**: D.2 debe mapear folios sin colisión y decidir anulación (`RET-03`) |
| **Pago** | Solo `facturas.estado` y `fecha_pago` (`0001:137-138`) | `pagos_nucleo` (`0013:78-98`) | **Aplicación: `nucleo`**. El estado "pagada" legacy es histórico. | **No en la aplicación** 🟢 | Ninguna. El legacy marcaba pagada sin monto ni medio; el núcleo exige pago | **Alto (dinero)**: hay facturas históricas "pagadas" sin registro de pago (§5.5 de `retiro-legacy.md`) |
| **Gasto** | `gastos_viaje` (`0001:114-125`) | `viaje_gastos` (`0011:29-83`) | **Aplicación: `nucleo`** (`/expediente`). Histórico: `public`. | **No en la aplicación** 🟢 | Ninguna. El legacy borraba en duro; el núcleo aprueba/rechaza y conserva | **Alto**: archivos en Storage (`respaldos`) deben migrarse con la fila, no solo el monto |
| **Usuario / identidad** | `usuarios` (`0001:36-45`) + `auth.users` | `usuarios_empresa` (`0004:139-153`) | **Dos fuentes vivas**: `public.usuarios` para `/auth/me` y rol global; `nucleo.usuarios_empresa` para rol por empresa | **Sí** 🟢: el trigger `handle_new_user` escribe `public.usuarios` en **cada alta**; la membresía del núcleo se crea aparte | `public.handle_new_user` (`0001:248-262`) mantiene el espejo; **no** crea membresía en `nucleo` | **Crítico**: un usuario puede existir en un esquema y no en el otro; permisos distintos; bloquea el `DROP` (G0.1) |
| **Empresa / tenant** | No existe `empresa_id` en ninguna tabla | `empresas` (`0004:102-137`) | `nucleo` es la única fuente. | **No** 🟢 | No aplica. El legacy es global por diseño y ya no tiene rutas de negocio | **Medio**: el gate sigue siendo la frontera de acceso; el aislamiento de datos es solo del núcleo |
| **Configuración** | `configuracion` (`0001:212-215`): IVA y alertas | `configuracion_empresa` (`0026`) + `empresas` (`0004:116-125`) + `configuracion_costos` (`0012:8-25`) | **Aplicación: `nucleo.configuracion_empresa`** (vigencia + historial). `public.configuracion` **no tiene lector de producción** (`settings_db` sin consumidor). | **No entre esquemas** 🟢. **Sí dentro del núcleo**: la factura acepta `tasa_iva` del request (`schemas.py:1543`; `servicio_facturacion.py:544`) | Ninguna. El seed de `0026` fija `iva_porcentaje = 19` por empresa; el histórico no se migra | **Alto (tributario)**: dos fuentes de la tasa dentro del núcleo; falta que el servidor imponga la configurada (`RET-04`) |
| **KPI** | `kpis` (`0003:5-20`) + `kpi_engine.py` (borrado) | Indicadores fijos: `servicio_alertas.py`, `servicio_rentabilidad.py` | **Aplicación: `nucleo`**. `public.kpis` quedó sin lector. | **No** 🟢 | No aplica para escrituras; el histórico de definiciones no se migra | **Medio**: el motor por fórmula se retiró con RET-05 abierta; si el dueño lo quiere, se recupera de git |
| **Orden de compra** | No existe | `ordenes_compra` + líneas (`0004:421-485`) | `nucleo` es la única fuente. | **No** 🟢 | No aplica. | **Bajo ahora**: el legacy ya no factura sin OC porque no factura |
| **Tarifa** | No existe (solo `valor_flete_neto` libre en `viajes`) | `tarifas` (`0004:377-416`) | `nucleo` es la única fuente. | **No** 🟢 | No aplica. | **Bajo ahora**; el histórico conserva fletes sin tarifa asociada |
| **Documento habilitante** | Fechas sueltas en `tractos`/`choferes` (`0001:66,79-80`) | `documentos` versionados (`0004:326-372`) | **Aplicación: `nucleo`**. El legacy ya no despacha. | **No en la aplicación** 🟢 | Ninguna; el histórico tiene fechas planas, no documentos | **Medio**: D.1 debe decidir si las fechas legacy se convierten en documentos o se descartan |
| **Liquidación** | `liquidaciones`, `anticipos_chofer`, `ajustes_liquidacion` (`0001:151-186`) | `liquidaciones`, `anticipos_chofer`, `ajustes_liquidacion` (`0025`) | **Aplicación: `nucleo`** (`/liquidaciones`). Histórico: `public`, sin migrar. | **No en la aplicación** 🟢 | Ninguna. La emisión del núcleo congela montos; la base de comisión sigue en `D-01` | **Alto (laboral)**: migrar números sin decidir la regla congela un criterio posiblemente incorrecto |
| **Mantenimiento** | `pautas_mantenimiento`, `mantenimientos` (`0001:189-209`) | `pautas_mantenimiento`, `mantenimientos`, `v_mantenimiento_estado` (`0024`) | **Aplicación: `nucleo`** (`/mantenimiento`). Histórico: `public`, sin migrar. | **No en la aplicación** 🟢 | Ninguna. El `km_actual` legacy se actualizaba en el router; el núcleo lo hace por trigger `odometro` | **Medio-alto**: D.4 no debe re-ejecutar el trigger; debe fijar el km final |

---

## 3. Diagnóstico de conjunto (rev. 2)

1. **La aplicación ya tiene un solo escritor por concepto de negocio.** Los 11
   routers legacy de negocio fueron borrados y ningún servicio del núcleo escribe
   en `public.*`. Las excepciones son **identidad** (`public.usuarios`, escrita
   por trigger) y **scripts** (seed/cutover, fuera de runtime). 🟢
2. **"Un solo escritor" no es "una sola fuente de verdad".** El histórico
   financiero, laboral y tributario sigue en `public`, sin mapeo de
   identificadores y sin reconciliación. Eso es lo que bloquea D y E.
3. **No hay reconciliación automática.** No existe job, vista, tabla de mapeo ni
   consulta de divergencia. La única transferencia es el cutover, one-way, que
   migra viajes `confirmado` **sin recursos** (`cutover_legacy.py:6-13,378-401`).
4. **La ocupación dejó de ser el riesgo principal.** Antes de la Ola C, el legacy
   podía asignar un recurso sin insertar reserva (RA-02). Hoy no hay endpoint que
   lo haga; el riesgo residual es que los viajes históricos importados no generen
   reservas y queden invisibles para la disponibilidad.
5. **La identidad es el bloqueo del `DROP`.** `public.usuarios` es la puerta de
   entrada de `/auth/me` y `deps.py`, y el trigger la escribe en cada alta.
   `nucleo.usuarios_empresa` es la puerta del núcleo. Sin un mapeo
   `auth_id → membresía` y un endpoint de perfil en el núcleo, no se puede retirar
   el esquema sin dejar usuarios fuera (G0.1 / Ola E).
6. **La configuración tributaria ya no depende de `public`, pero tiene dos
   fuentes internas.** El módulo de IVA lee `nucleo.configuracion_empresa`; la
   creación de factura acepta `tasa_iva` del request. Es una regla sin dueño
   único (`RET-04`).

---

## 4. Regla operativa: un concepto, un esquema canónico

Antes de escribir una línea de código nueva:

1. **Declarar el dueño.** Todo concepto de la §2 debe tener un solo esquema
   canónico escrito en este documento y en el ADR correspondiente. Mientras no
   esté declarado, **no se agrega una tercera escritura**.
2. **Un solo escritor por operación.** La aplicación escribe en `nucleo`. Ningún
   endpoint, tarea o script de runtime debe escribir en `public` (los seeds y el
   cutover son herramientas de migración, no operación).
3. **El corte de datos se hace con el legacy congelado.** El flag
   `nucleo.cutover_control.legacy_escritura_congelada` debe estar en `true`
   durante la ventana de D-2; `legacy_congelado()` ya es fail-closed. Con las
   rutas legacy borradas, el flag protege contra escrituras residuales de scripts,
   no de la API.
4. **Toda divergencia se mide, no se supone.** Antes de declarar un concepto
   migrado: conteo por tabla, comparación de claves naturales (RUT, patente,
   número de factura, `(chofer, mes)`) y consulta de huérfanos. Sin esa evidencia,
   el concepto sigue en "histórico no migrado" 🔴.
5. **No se borra el legacy para "limpiar".** Se retira por módulo cuando exista
   paridad, datos migrados y reversibilidad (`docs/arquitectura/retiro-legacy.md`).

> **Criterio de éxito observable:** para cada concepto, una consulta de
> reconciliación devuelve 0 filas de diferencia y solo el núcleo recibe
> escrituras. Hoy se cumple la segunda mitad para los conceptos de negocio; la
> primera **no** se cumple en ninguno. La respuesta a "¿cuál manda?" es:
> **"la aplicación manda en `nucleo`; el histórico manda en `public` hasta que D
> lo migre"**.
