# Capacidades objetivo — matriz de brecha

> **Pregunta que responde:** ¿qué capacidades del ERP objetivo están construidas, parciales o ausentes hoy?
> **Dueño:** arquitectura · **Verificado:** 2026-10-29 · **Método:** lectura estática del código/DDL contra el diseño funcional de `PLAN_MAESTRO_ERP_V2.md` §4–21 y `CATALOGO_KPIS_Y_FREIGHT_SCORE.md`; sin ejecución.
> **Caduca si:** se implementa o retira una capacidad de esta lista, o cambia el alcance del piloto.
> **Re-verificar con:** `grep -rn` del mecanismo citado + `docs/estado.md` §3.

---

## 0. Cómo se clasifica

| Marca | Significado |
|---|---|
| 🟢 **Construido** | El mecanismo existe en código/DDL y tiene una ruta de uso identificable. No implica que esté probado en producción. |
| 🟡 **Parcial** | Existe una parte, o existe solo en una capa (legacy o núcleo), o falta la verificación de su garantía. |
| 🔴 **Ausente** | No se encontró mecanismo. Se cita la búsqueda o el archivo que lo evidencia. |

**Alcance:** 59 capacidades agrupadas por dominio. No se copia el plan: cada fila lo resume en una línea y la clasifica contra el repositorio. Una capacidad 🟢 no cierra la brecha de las demás.

---

## 1. Operación (14)

| # | Capacidad objetivo | Estado | Evidencia |
|---|---|---|---|
| O01 | Ciclo de vida del viaje con estados explícitos y transiciones permitidas | 🟢 | 14 estados en `0004:51-55`; tabla `transiciones_viaje` y 29 transiciones `0004:772-808`; trigger `fn_viaje_transicion` `0004:1511-1547` |
| O02 | Planificación por ventana `[inicio, fin)` con buffer operacional | 🟢 | `ventana tstzrange` `0004:561`; cálculo `fn_viaje_ventana` `0004:899-940`; check `0004:666-670` |
| O03 | Libro único de ocupación y exclusión de solape por tracto, rampla y chofer | 🟡 | `reservas_recurso` `0004:703-741`; 3 `EXCLUDE` `0004:744-757`; trigger `0015:183-238`. **Solo protege escrituras del núcleo**: el legacy no inserta reservas (RA-02) |
| O04 | "Libre desde" por recurso, con traslado | 🟢 | `libre_desde` `servicio_disponibilidad.py:687`; endpoint `api.py:150-166` |
| O05 | Mesa de despacho con previsualización y asignación atómica | 🟢 | pantalla `despacho/page.tsx:195-201,321-325`; validar `api.py:169-175`; asignar `api.py:178-189`; locks `servicio_disponibilidad.py:1397-1409` |
| O06 | Motor de asignación automática u optimización de rutas/recursos | 🔴 | Búsqueda `automatic\|optimiz\|sugerir\|asignacion_automatica` en `backend/app/nucleo` → 0 coincidencias; la asignación es manual |
| O07 | Bloqueos por mantención, descanso, vacaciones, siniestro o bloqueo manual | 🟢 | `tipo_reserva` `0004:67-69,711`; campos de cancelación `0006:9-18`; `servicio_bloqueos.py:62-444` |
| O08 | Expediente del viaje: paradas, checklist, eventos, incidentes y documentos | 🟢 | tablas `0007:17-211`; `servicio_expediente.py`; endpoints `api_expediente.py:50-263` |
| O09 | POD con firma, fotos, geo y no borrado | 🟡 | tabla `0009:8-58`; `api_pod.py:43-84`; `storage.py:34-77`. Storage y visor **no verificados** (`docs/estado.md` §4) |
| O10 | PWA del conductor con check-in/out y cola offline | 🟡 | endpoints `api_conductor.py:29-57`; `offline-queue.ts:20-30`. Comportamiento offline **no verificado** (`docs/estado.md` §4) |
| O11 | Cierre de viaje con checklist obligatorio | 🟢 | `servicio_expediente.py:1244-1292`; motivos de bloqueo `311-315` |
| O12 | Reapertura controlada de un viaje cerrado | 🔴 | `servicio_expediente.py:1294-1304` solo devuelve error; la máquina de estados no permite volver de `cerrado` (`0004:807-808`) |
| O13 | Mantenimiento preventivo por km, con pauta y alerta | 🔴 | En `nucleo` solo existe `tipo_reserva='mantenimiento'` (`servicio_alertas.py:172`); no hay tablas de pauta/mantención en `0004`–`0019` |
| O14 | GPS, telemetría, geocercas y ETA automática | 🔴 | Sin tablas ni endpoints; solo `ubicacion_*` manual en recursos (`0004:210-213`) y lat/lon de POD (`0009:16-17`) |

## 2. Comercial (7)

| # | Capacidad objetivo | Estado | Evidencia |
|---|---|---|---|
| C01 | Ficha de cliente con condiciones de pago, crédito y exigencia de OC | 🟢 | `nucleo.clientes` `0004:158-186`; `servicio_maestros.py:83-225`; `/maestros` |
| C02 | Tarifario multimodolidad con vigencia y recargos | 🟢 | `tarifas` `0004:377-416`; modalidades `0004:57-59`; `servicio_comercial.py:331-487`; `/comercial` |
| C03 | Orden de compra con líneas, consumo y sobregiro aprobado | 🟢 | `ordenes_compra` + líneas `0004:421-485`; `fn_oc_recalcular` `0004:1550-1597`; `servicio_comercial.py:589-1173` |
| C04 | Cotizador de fletes con registro de cotización | 🟡 | El estado `cotizado` existe (`0004:52`), pero no hay endpoint de cotización; el simulador (`api_rentabilidad.py:53`) no persiste una cotización |
| C05 | Freight Score de 6 componentes con pesos | 🟢 | `servicio_rentabilidad.py:239-247`; pesos y cálculo en `234-292`; persistencia en `viajes.freight_score_*` `0004:629-630` |
| C06 | Simulador de escenarios de flete/margen | 🟢 | `POST /nucleo/rentabilidad/simulador` `api_rentabilidad.py:53`; `servicio_rentabilidad.py:294-321` |
| C07 | Recargo automático por variación del diésel | 🟡 | Campos en tarifa (`precio_diesel_base`, `participacion_combustible`) `0004:396-398`, pero no se encontró recálculo automático en `tarifas.py`/`servicio_comercial.py` |

## 3. Finanzas (16)

| # | Capacidad objetivo | Estado | Evidencia |
|---|---|---|---|
| F01 | Facturación con folio correlativo por empresa | 🟢 | `facturas_nucleo` `0013:10-38`; `siguiente_folio` `0004:498-517`; uso `servicio_facturacion.py:548-556` |
| F02 | Gate de facturación: viaje cerrado, POD y OC | 🟢 | `servicio_facturacion.py:485-501`; trigger `fn_viaje_facturacion` `0004:1387-1449` |
| F03 | Pagos parciales con saldo | 🟢 | `pagos_nucleo` `0013:78-98`; `registrar_pago` `servicio_facturacion.py:620-651` |
| F04 | Notas de crédito como mecanismo de corrección | 🟢 | `notas_credito_nucleo` `0013:112-129`; `crear_nota_credito` `servicio_facturacion.py:653-691` |
| F05 | Promesas de pago | 🟢 | `promesas_pago_nucleo` `0013:139-153`; `crear_promesa` `servicio_facturacion.py:693-710` |
| F06 | Aging de cartera | 🟢 | `GET /nucleo/cobranza/aging` `api_facturacion.py:124`; `servicio_facturacion.py:712` |
| F07 | DTE / SII real | 🔴 | Declarado fuera del piloto en `0013:4`; sin tablas, XML ni integración |
| F08 | IVA mensual y F29 | 🟡 | Solo legacy: `GET /iva/resumen` `finanzas.py:116-185`; cálculo interno, no F29 (`docs/estado.md` §3) |
| F09 | Cuentas por pagar, tesorería y conciliación bancaria | 🔴 | Sin tablas ni endpoints; `tesoreria` solo existe como rol (`permisos.py:99`) |
| F10 | Cierre contable mensual y estado de resultados | 🔴 | No hay período contable, asientos ni P&L; `configuracion_costos` solo alimenta margen por viaje (`0012:8-25`) |
| F11 | Gastos con aprobación y segregación de funciones | 🟢 | `servicio_gastos.py:346-435`; endpoint `api_gastos.py:120-134`; permiso `gastos:aprobar` |
| F12 | Costo real por viaje con gastos aprobados + comisión | 🟢 | `fn_viaje_costos` `0011:91-135`; trigger `0011:137-156` |
| F13 | Configuración de costos y margen objetivo por empresa | 🟢 | `configuracion_costos` `0012:8-32`; `servicio_rentabilidad.py:108-178` |
| F14 | Liquidación de comisión del chofer | 🟡 | Solo legacy: `liquidaciones.py:51-96,278-344`. El núcleo no tiene módulo de liquidaciones |
| F15 | Snapshot inmutable y PDF reproducible de la liquidación | 🔴 | El PDF recalcula la comisión al emitir (`liquidaciones.py:515-533`); SEC-002 abierto |
| F16 | Nómina legal (AFP, salud, cesantía, finiquito, gratificación) | 🔴 | Búsqueda `AFP\|cesantia\|finiquito\|gratificacion\|nomina` en `*.py,*.ts,*.sql` → 0 coincidencias |
| F17 | Combustible: precios, litros, rendimiento y costo | 🟢 | `precios_diesel` + `viaje_gastos` `0011:11-83`; `servicio_gastos.py:201-309` |

## 4. Personas (6)

| # | Capacidad objetivo | Estado | Evidencia |
|---|---|---|---|
| P01 | Ficha de conductor, licencia y documentos habilitantes | 🟢 | `nucleo.choferes` `0004:282-321`; documentos `0004:326-372`; regla A5 `0016:193-255` |
| P02 | Jornada, horas de conducción y descansos legales | 🔴 | Solo `estado='en_descanso'` (`0004:39-42`) y reserva `descanso` (`0004:67-69`); no hay jornada ni horas acumuladas |
| P03 | Roles y permisos por módulo | 🟢 | 8 roles `permisos.py:58-172`; 28 permisos `:15-44`; endpoints declaran permiso |
| P04 | Membresía multiempresa por usuario | 🟢 | `usuarios_empresa` `0004:139-153`; resolución `deps.py:43-82`; endpoint `api.py:69-76` |
| P05 | Selección y cambio de empresa en la UI | 🔴 | Cada pantalla toma la primera empresa (`despacho/page.tsx:162-167`); no existe selector ni persistencia |
| P06 | Autenticación con Supabase JWT (JWKS, RS256/ES256, audiencia) | 🟢 | `core/security.py:13-30`; `auth_id_from_credentials` `:45` |

## 5. Documentos (3)

| # | Capacidad objetivo | Estado | Evidencia |
|---|---|---|---|
| D01 | Expediente digital versionado por recurso, sin borrado | 🟢 | `documentos` `0004:326-372`; `fn_documento_vigente_unico` `0004:1704-1741`; `fn_documento_no_borrar` `0004:1743-1751` |
| D02 | Alertas de vencimiento documental | 🟢 | `servicio_alertas.py:124-133`; `dias_alerta_documentos` `0004:120-121` |
| D03 | OCR de documentos y extracción automática de datos | 🔴 | Búsqueda `ocr\|tesseract\|textract` → sin implementación (el único match es un folio de prueba) |

## 6. Datos y BI (6)

| # | Capacidad objetivo | Estado | Evidencia |
|---|---|---|---|
| B01 | KPIs configurables por fórmula, con preview | 🟡 | Solo legacy: `kpis.py:38-204` y `kpi_engine.py`; el núcleo tiene indicadores fijos |
| B02 | Tablero operativo de alertas | 🟢 | `GET /nucleo/alertas/tablero` `api_alertas.py:24`; categorías docs/bloqueos/POD/facturación/OC/margen `servicio_alertas.py:115-198` |
| B03 | Exportación CSV/Excel | 🟡 | Solo legacy: `export.py:49-108`; el núcleo no exporta (`grep csv` en `backend/app/nucleo` → 0) |
| B04 | Importación CSV de maestros | 🟡 | Solo legacy: `export.py:194-272`; escribe `public.clientes/choferes` |
| B05 | BI, warehouse o reporting histórico | 🔴 | No hay réplica, esquema analítico, ETL ni herramienta de BI |
| B06 | Copiloto / IA sobre los datos | 🔴 | Búsqueda `copiloto\|openai\|llm\|embedding` → 0 coincidencias |

## 7. Integraciones (1)

| # | Capacidad objetivo | Estado | Evidencia |
|---|---|---|---|
| I01 | WhatsApp, email, mapas, bancos u otras integraciones externas | 🔴 | Búsqueda `whatsapp\|twilio\|smtp\|sendgrid\|mapbox\|google_maps` → 0 coincidencias; solo Supabase Storage (`storage.py:34-77`) |

## 8. Seguridad y operación (5)

| # | Capacidad objetivo | Estado | Evidencia |
|---|---|---|---|
| S01 | Aislamiento multiempresa efectivo en base (RLS con políticas) | 🟡 | RLS habilitado en todo `nucleo` (`0004:1867-1881` y migraciones posteriores), **sin `create policy`**; rol efectivo no verificado (RA-03) |
| S02 | Auditoría append-only de cambios | 🟡 | `auditoria` + triggers `0004:813-892`; cobertura parcial: no cubre `transiciones_viaje`, `folio_contador`, `cutover_control` (RA-07); legacy sin auditoría |
| S03 | Backup y restore probado con comparación antes/después | 🟡 | `scripts/restore_drill.sh:26-50` hace dump, restore y 6 conteos, pero no compara ni prueba la app (RA-05) |
| S04 | CI y observabilidad | 🟡 | CI existe: import + pytest + lint + build (`.github/workflows/ci.yml:27-50`), **sin PostgreSQL, migraciones, integración ni E2E**; no hay Sentry/OTel/métricas |
| S05 | API versionada y contrato verificable | 🟡 | Prefijo `/api/v1` (`main.py:33`); sin generación de cliente ni pruebas de contrato; tipos frontend escritos a mano |

---

## 9. Lectura de brecha

1. **Lo construido se concentra en el núcleo operativo**: viaje, disponibilidad, expediente, POD, comercial, facturación y costos. Es una base real, no un prototipo de pantallas.
2. **Las brechas que bloquean el piloto no son de UI**: RLS efectivo, cutover seguro, conciliación legacy↔núcleo, snapshot de liquidación y mantenimiento preventivo.
3. **Cinco capacidades viven solo en legacy** (F08, F14, B01, B03, B04). Retirar el legacy sin migrarlas rompe IVA, nómina, KPIs, export e import.
4. **15 capacidades están ausentes** (O06, O12, O13, O14, F07, F09, F10, F15, F16, P02, P05, D03, B05, B06, I01). No se proponen aquí: se registran como alcance futuro o decisión del dueño.
5. **Ninguna fila 🟢 acredita producción.** La verificación de ejecución (suite, E2E, restore, concurrencia) sigue pendiente en `docs/estado.md` §4.
