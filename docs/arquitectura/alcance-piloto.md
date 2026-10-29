# Alcance del piloto de 90 días — qué está construido, qué falta y cómo ejecutarlo

> **Pregunta que responde:** ¿qué entra en el piloto de 90 días y con qué criterio se acepta?
> **Dueño:** `arquitectura` · **Verificado:** 2026-10-29 · **Método:** lectura estática
> **Caduca si:** cambia el alcance acordado o se cierra un P0.
> **Re-verificar con:** `ls "frontend/src/app/(app)"`


- **Autor:** agente `arquitectura`
- **Fecha:** 2026-10-29
- **Base:** `docs/_archivo/planes/PLAN_MAESTRO_ERP_V2.md` §23.2 (Fases 0 y 1),
  `docs/arquitectura/matriz-plan-vs-codigo.md`,
  `docs/arquitectura/adr/ADR-0001-coexistencia-public-nucleo.md`
- **Método:** lectura estática. Base de datos apagada, servicios cerrados, sin
  permiso de shell. Todo lo que requiere ejecución está marcado 🔴.

---

## 1. Regla de lectura

| Marca | Significado |
|---|---|
| **Construido** 🟢 | Existe el mecanismo en código/DDL, con cita. No implica probado. |
| **Parcial** 🟡 | Existe una parte; falta la garantía o la cobertura. |
| **Ausente** 🔴 | No existe en el repositorio (búsqueda citada). |
| **No verificado** 🔴 | Existe, pero no se ejecutó ni se probó en esta sesión. |

**Advertencia central.** "Construido" no significa "en producción". Los 16
conceptos canónicos en `nucleo` (ver ADR-0001 §B.2) conviven con un legacy que
sigue aceptando escrituras (`0014:10,17-19`; `backend/app/main.py:36-61`). Un
piloto que use las pantallas del núcleo y, en paralelo, las legacy, **no tiene una
sola fuente de verdad** y sus números no son confiables. Por eso la Ola 1 no
agrega funcionalidad: hace exigible lo ya construido.

---

## 2. Fase 0 del plan ("Blindaje", 3 semanas)

Alcance declarado: multiempresa, auditoría, migraciones, seguridad, backups,
observabilidad, roles v2.

| Ítem del plan | Estado | Evidencia | Qué falta |
|---|---|---|---|
| Multiempresa | **Construido en esquema y backend** 🟢 | `nucleo.empresas`, `usuarios_empresa` `supabase/migrations/0004_nucleo_operacional.sql:102-157`; `empresa_id` en tablas de negocio y FKs compuestas `0004:720-728`; empresa desde `X-Empresa-ID` + membresía `backend/app/nucleo/deps.py:40-82` | RLS está **habilitado sin políticas** (`0004:1867-1881`; `create policy` en `nucleo` → 0 resultados). El aislamiento efectivo depende del backend y del rol de conexión, que **no se puede verificar** con la base apagada 🔴 |
| Auditoría | **Parcial** 🟡 | `nucleo.auditoria` append-only `0004:813-828`; inmutabilidad por trigger `0004:880-892`; triggers en viajes, reservas, documentos, OC, gastos, POD, expediente, facturación (`0004:1761-1862`, `0005:42`, `0007:58-211`, `0009:45`, `0011:24,81`, `0013:49-158`) | No cubre `cutover_control`, `transiciones_viaje` ni `folio_contador`. No cubre el legacy. No hay endpoint que exporte evidencia de auditoría para una investigación |
| Migraciones | **Parcial** 🟡 | 14 migraciones forward-only `0001..0014`; sin `create_all` (`backend/app/nucleo/models.py:4`); sin Alembic | Sin CI (`.github/workflows` → 0 archivos), sin chequeo de deriva modelo↔DDL, sin entorno staging declarado en el repo |
| Seguridad (authn/authz) | **Parcial** 🟡 | JWT Supabase validado por el backend; 8 roles `0004:35-37`; permisos deny-by-default con dependencia por endpoint `backend/app/nucleo/permisos.py:15-44,150-172`; error 403 explícito | Sin MFA, sin rate limiting, sin política de sesión (búsqueda `mfa|MFA|totp|rate_limit|slowapi` en `*.{py,ts,tsx,json}` → solo dependencias transitivas de Next en `package-lock.json`) |
| Roles v2 | **Construido** 🟢 | `nucleo.rol_empresa` con 8 roles `0004:35-37`; matriz de permisos `permisos.py:58-139`; pantalla `/permisos` sobre `frontend/src/lib/nucleo.ts`; test `backend/tests/test_nucleo_permisos.py` | Falta verificar que cada endpoint declare permiso (no auditado endpoint por endpoint en esta sesión) 🔴 |
| Backups | **Parcial** 🟡 | `scripts/restore_drill.sh` hace dump, restore en base temporal y 6 conteos `:26-54`; target `make restore-drill` (`Makefile:65-66`) | **Nunca ejecutado** con evidencia 🔴. No compara antes/después ni prueba que la aplicación funcione contra la base restaurada |
| Observabilidad | **Ausente** 🔴 | Sin Sentry/OpenTelemetry/Prometheus en código de aplicación; solo `/health` (`backend/app/main.py:83-85`) | Logs estructurados, trazas, métricas y alertas de error. No hay dependencia operativa nueva justificada todavía: para un piloto de 3 tractos alcanza log estructurado + `/health` + alerta de error 5xx |

**Conclusión Fase 0:** 2 de 7 ítems construidos, 4 parciales, 1 ausente. Lo
construido no está probado contra base real. La Fase 0 **no está cerrada**.

---

## 3. Fase 1 del plan ("Núcleo operacional", 8 semanas)

Alcance declarado: OC, tarifas, carga, viaje v2, disponibilidad, mesa de despacho,
documentos, POD, PWA conductor.

| Ítem del plan | Estado | Evidencia | Qué falta |
|---|---|---|---|
| OC del cliente | **Construido** 🟢 | `nucleo.ordenes_compra` + líneas `0004:421-489`; consumo recalculado en BD `fn_oc_recalcular` `0004:1550`; gate de facturación `0004:1386-1445`; pantalla `/comercial` + `orden-compra-dialog.tsx` | Nada bloqueante para el piloto. Alertas de OC al 80/90/100% existen en servicio `backend/app/nucleo/servicio_comercial.py:160-170` |
| Tarifas | **Construido** 🟢 | `nucleo.tarifas` `0004:377-420`; modalidades en `backend/app/nucleo/tarifas.py`; snapshot en el viaje `0004:1474-1483` | Falta validar con el dueño qué modalidades usa realmente (hoy hay catálogo técnico, no configuración comercial) → **D-06** |
| Carga del viaje | **Construido** 🟢 | Campos de carga en `nucleo.viajes` `0004:542-701` (peso, volumen, tipo, peligrosa, refrigerada, sobredimensionada); validación dura de capacidad y sobrepeso `0004:1198-1225`; paradas y checklist `0007:17-101` | Falta confirmar si el piloto necesita multi-parada real o basta origen/destino (decisión de operación) |
| Viaje v2 | **Construido** 🟢 | 14 estados `0004:53`; `transiciones_viaje` `0004:772-808`; triggers de ventana, validación, facturación, protección, transición, versión y auditoría `0004:1832-1850` | No existe reapertura controlada (decisión **D-03**). Los estados `en_taller`/`en_descanso` existen como estado de **recurso** (`0004:40`), no de viaje |
| Disponibilidad | **Construido** 🟢 | `nucleo.reservas_recurso` con 3 `EXCLUDE USING gist` `0004:744-757`; reservas creadas por trigger `0004:1621-1650`; `libre_desde` en `backend/app/nucleo/servicio_disponibilidad.py:687-778`; locks `FOR UPDATE` + asesoría `servicio_disponibilidad.py:785-791,1397-1411` | **No probado con dos conexiones simultáneas** 🔴 (ver `01-matriz` V2). Sin esa prueba la garantía es de diseño, no de hecho |
| Mesa de despacho | **Construido** 🟢 | `/despacho` sobre `nucleo.ts`; `validar_asignacion` y `confirmar_asignacion` `servicio_disponibilidad.py:1150-1470` | Falta el arrastrar-y-soltar y el Gantt que el plan describe (§7.3). Para el piloto, lista + conflicto detectado puede bastar (decisión de alcance) |
| Documentos | **Construido** 🟢 | `nucleo.documentos` `0004:326-375`; 12 tipos `0004:60-63`; requisitos por recurso y tipo de carga `0004:1041-1074`; bloqueo duro al asignar `0004:1281-1292`; pantalla `/expediente` + `documentos-dialog.tsx` | Falta definir qué documentos son obligatorios por empresa (**D-06**). La clase de licencia es advertencia, no bloqueo (`0004:1272-1274`) |
| POD | **Construido** 🟢 | `nucleo.pod` con firma, hash, fotos, lat/lon, daños, no borrable `0009:8-50`; API `backend/app/nucleo/api_pod.py`; pantalla `pod-panel.tsx`; bloqueo de factura sin POD `servicio_facturacion.py:494-501` | La geolocalización se guarda si el cliente la envía (`0009:16-17`), **no** hay captura GPS automática (búsqueda `gps|GPS|geocerca|telemetria` → 0). Para el piloto es aceptable si se documenta como "coordenada del dispositivo, no tracking" |
| PWA conductor | **Parcial** 🟡 | `/conductor` sobre `nucleo.ts`; `manifest.webmanifest`; service worker con caché de shell y cola en `localStorage` (`frontend/public/sw.js:1-65`) | Sin prueba de offline real 🔴; sin firma capturada en canvas verificada; sin push. No hay `gps` ni cámara nativa más allá de `input file` |

**Conclusión Fase 1:** 8 de 9 ítems construidos, 1 parcial. Funcionalmente el
piloto **está construido**; lo que falta no es alcance, es **exigibilidad y
prueba**.

---

## 4. Lo que falta de verdad (y bloquea el piloto)

Ordenado por impacto. Cada ítem es un bloqueo, no una mejora.

| # | Bloqueo | Evidencia | Tamaño relativo |
|---|---|---|---|
| B1 | El legacy sigue escribiendo los mismos conceptos | flag en `false` `0014:10,17-19`; middleware solo bloquea en `true` `main.py:50` | M |
| B2 | No hay reconciliación entre esquemas | no existe consulta/job; búsqueda `outbox|worker|job_queue` → 0 | S (consulta) |
| B3 | La exclusión del núcleo no está probada con concurrencia real | test existente es secuencial `test_nucleo_integracion.py:262-274` | S |
| B4 | El cutover pierde estado y no migra dinero | `cutover_legacy.py:368` (todo `confirmado`); sin gastos/facturas/pagos | L |
| B5 | El cutover falla abierto | `servicio_cutover.py:38-39` | S |
| B6 | El interruptor de cutover no tiene dueño ni historial | `permisos.py:59-60`; `0014:9`; sin trigger de auditoría | S |
| B7 | 4 módulos no tienen equivalente en el núcleo | liquidaciones, mantenimiento, IVA, export (`01-matriz` §4) | L (o se excluyen del piloto) |
| B8 | Restore drill no ejecutado | `scripts/restore_drill.sh` existe, sin evidencia | S |
| B9 | Sin CI ni verificación de deriva | `.github/workflows` → 0 | M |
| B10 | Sin observabilidad mínima | solo `/health` | S |

**B7 es la decisión que define el alcance.** Si el dueño acepta que
liquidaciones, mantenimiento e IVA queden fuera del piloto y se sigan operando en
legacy, el piloto puede cerrarse en 90 días. Si exige esos módulos dentro, el
piloto no cabe en 90 días con el equipo actual y hay que decirlo ahora, no en la
semana 10.

---

## 5. Propuesta de 3 olas

Cada ola tiene un resultado observable. No se avanza a la siguiente si la
anterior no cumple su criterio.

### Ola 1 — "Hacer exigible lo construido" (semanas 1–3)

**Objetivo:** que las garantías del núcleo no se puedan evitar. **No agrega
funcionalidad.**

| Trabajo | Entregable | Dueño sugerido |
|---|---|---|
| Registro `módulo → esquema canónico` y bloqueo de escritura legacy por módulo | Middleware + lista declarada; 409 con `codigo = MODULO_EN_NUCLEO` | `backend` |
| Consulta de reconciliación por concepto (conteo y suma) | Script de solo lectura + salida fechada | `datos` |
| Prueba de concurrencia real de los 3 `EXCLUDE` | Test con dos conexiones que espera `23P01` y 409 HTTP | `qa` + `datos` |
| Cutover fail-closed para escrituras | Excepción de lectura ⇒ congelado, no abierto | `backend` |
| Auditoría del interruptor de cutover | Historial append-only de congelar/descongelar | `datos` |
| Cierre de escritura legacy de **maestros** y **operación** | `/clientes`, `/choferes`, `/flota`, `/viajes` redirigidas o de solo lectura | `frontend` + `backend` |

**Criterio de aceptación (observable):**
1. `POST` a `/api/v1/viajes` y a `/api/v1/clientes` devuelve 409 con código
   explícito, no 500 ni error de base.
2. Existe una prueba que abre dos conexiones simultáneas, intenta reservar el
   mismo tracto en la misma ventana y verifica que **una** falla con `23P01` y que
   el endpoint responde 409.
3. La consulta de reconciliación devuelve 0 diferencias en maestros y viajes, o
   la lista exacta de diferencias con dueño asignado.
4. Con la lectura del flag forzada a fallar, una escritura legacy **no** pasa.
5. Las pantallas redirigidas no muestran errores al usuario.

**Rollback:** revertir el registro de módulos (deploy). No hay cambio de datos.

---

### Ola 2 — "Cerrar el ciclo del piloto" (semanas 4–7)

**Objetivo:** un viaje completo, de la OC al cobro, sin tocar el legacy.

| Trabajo | Entregable | Dueño sugerido |
|---|---|---|
| Cierre de escritura legacy de **facturación** y **cobranza** | `/facturas`, `/cobranzas` redirigidas a `/cobranza` | `backend` + `frontend` |
| Migración del histórico financiero mínimo | Gastos, facturas y pagos migrados con conciliación de montos | `datos` |
| Flujo POD de punta a punta desde el celular | Viaje `descargado` → POD → `cerrado` → factura, con evidencia | `qa` |
| Alertas del piloto en el tablero | Documentos, mantención agendada, viajes sin POD, facturas vencidas, OC al 90% | `backend` |
| Redirección de `/dashboard` a `/tablero` | Una sola pantalla de inicio | `frontend` |
| Definición de documentos obligatorios por empresa | Configuración cargada y verificada | **D-06** |

**Criterio de aceptación (observable):**
1. Un viaje creado en `/despacho` recorre todos sus estados hasta `cobrado` con
   POD y pago parcial, **sin una sola escritura a `public`** (verificable por log
   de auditoría de `nucleo` y por la ausencia de filas nuevas en `public`).
2. Los 9 escenarios de `frontend/e2e/tei.spec.ts` pasan en verde, ejecutados.
3. La conciliación de facturas y pagos migrados cuadra al centavo contra
   `public` (suma por cliente y por mes).
4. La pantalla `/dashboard` ya no existe en la navegación o redirige a
   `/tablero`.

**Rollback:** reabrir el módulo en el registro. **Advertencia:** lo facturado o
cobrado en `nucleo` durante la ola no existe en `public`; el rollback de datos
exige restaurar backup, no solo reabrir.

---

### Ola 3 — "Operar con evidencia" (semanas 8–12)

**Objetivo:** que el piloto sea auditable y que el corte sea reversible de verdad.

| Trabajo | Entregable | Dueño sugerido |
|---|---|---|
| Restore drill ejecutado y documentado | Salida real con conteos antes/después y prueba de la app contra la base restaurada | `datos` |
| Observabilidad mínima | Logs estructurados con `request_id`, `/health` con dependencias, alerta de 5xx | `backend` |
| CI mínimo | lint + unitarias + migraciones aplicadas en base efímera | `orquestador` + `qa` |
| UAT con operación real | 3 tractos y 3 choferes reales durante 2 semanas | `qa` + dueño |
| Cierre del piloto o decisión de alcance para los 4 módulos legacy | Acta firmada | **D-01** |

**Criterio de aceptación (observable):**
1. `make restore-drill` ejecutado con salida registrada; los 6 conteos coinciden
   con la base origen; la aplicación responde contra la base restaurada.
2. 5 días hábiles consecutivos con **cero** escrituras legacy (flag en `true`) y
   reconciliación diaria en 0.
3. UAT firmada por el dueño con el criterio de `docs/_archivo/planes/PLAN_90_DIAS.md:25`: uso
   diario con al menos 3 tractos y 3 choferes reales.
4. Los 5 KPIs base del piloto muestran el mismo número en la pantalla y en una
   consulta SQL directa.

**Rollback:** `POST /nucleo/cutover/descongelar` (`api_cutover.py:46-51`) y
restauración desde el backup del drill si hubo migración de datos.

---

## 6. Lo que depende del dueño (no lo decide este documento)

| ID | Decisión | Impacto en el alcance | Sin decidir… |
|---|---|---|---|
| **D-01** | ¿Los 4 módulos sin equivalente (liquidaciones, mantenimiento, IVA, export) quedan **fuera** del piloto y se siguen operando en legacy? | Define si el piloto cabe en 90 días o no | No se puede cerrar el legacy ni declarar una sola fuente de verdad |
| **D-02** | Política de comisión: devengada al finalizar, al facturar o al cobrar | Define si liquidaciones entra a la Ola 2 o queda fuera | El legacy seguirá pagando comisión sobre flete no cobrado (`liquidaciones.py:45-59`) |
| **D-06** | Documentos obligatorios por empresa y si la clase de licencia bloquea | Define la configuración de la Ola 2 | El bloqueo de asignación puede ser laxo o excesivo |
| **D-07** | ¿El mantenimiento preventivo por km se construye en el núcleo o se queda en legacy? | Define el tamaño de la Ola 2/3 | El KPI seguirá ignorando unidades sin registro (`kpi_engine.py:484-485`) |
| **D-05** | ¿Quién es dueño del interruptor de cutover y es global o por empresa? | Define el control de la Ola 3 | Cualquier admin/gerente de cualquier empresa puede congelar el sistema completo (`permisos.py:59-60`) |
| **D-04** | Criterio de devengo del margen mensual | Define qué KPI se muestra en el tablero | Habrá dos "margen" distintos y el dueño no sabrá cuál creer (`kpi_engine.py:440` vs `servicio_rentabilidad.py:192`) |
| **D-03** | Qué se congela al emitir liquidación y quién reabre un viaje cerrado | Solo si D-01 incluye liquidaciones | El PDF seguirá recalculándose (`liquidaciones.py:465-502`) |

---

## 7. Riesgos del plan de olas

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Se cierra un módulo legacy sin redirigir su pantalla y el usuario ve 409 | Alta | Medio | Cerrar pantalla y endpoint en el mismo cambio; prueba E2E de la redirección |
| Se declara el piloto "listo" con la suite sin ejecutar | Media | Alto | Ningún criterio de aceptación se marca sin salida real de comando |
| El cutover se ejecuta sin migrar gastos/facturas/pagos | Media | Alto | B4 es bloqueante de la Ola 2, no de la Ola 3 |
| El dueño exige los 4 módulos dentro del piloto | Media | Alto | Decidir D-01 en la semana 1; si la respuesta es "sí", replanificar el plazo, no comprimir la calidad |
| Se agrega una tercera fuente de verdad "para reconciliar" | Baja | Alto | La reconciliación es una **consulta**, nunca una tabla de espejo |
| La observabilidad se convierte en un proyecto (OTel, stack, dashboards) | Media | Medio | Ola 3: log estructurado + `/health` + alerta 5xx. Nada más hasta que duela |

---

## 8. Resumen ejecutivo

- **El piloto funcional ya está construido** en `nucleo`: OC, tarifas, carga,
  viaje v2, disponibilidad con `EXCLUDE`, expediente, POD y PWA del conductor.
- **Lo que falta no es funcionalidad, es exigibilidad**: el legacy sigue abriendo
  la puerta (`0014:10`), no hay reconciliación, la concurrencia no está probada y
  el cutover pierde estado y dinero.
- **3 olas**: hacer exigible (semanas 1–3), cerrar el ciclo (4–7), operar con
  evidencia (8–12).
- **Una decisión manda sobre todas**: qué pasa con liquidaciones, mantenimiento,
  IVA y export (**D-01**). Sin esa respuesta, el alcance del piloto no puede
  fijarse, y cualquier fecha es una promesa sin base.
