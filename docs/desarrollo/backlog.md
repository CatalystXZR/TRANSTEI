# Backlog — qué se está construyendo y qué sigue

> **Pregunta que responde:** ¿en qué va el plan de trabajo y qué es lo próximo?
> **Dueño:** `orquestador` · **Verificado:** 2026-10-29 · **Método:** lectura de código + planes archivados
> **Caduca si:** se cierra un P0, cambia el alcance o se abre un frente nuevo.
> **Re-verificar con:** `ls frontend/src/app/\(app\)` y `ls backend/app/nucleo`

> El **estado verificado** está en [`docs/estado.md`](../estado.md). Este documento
> no repite cifras: describe el trabajo y dónde está cada pieza.

---

## 1. Origen del backlog

Los 13 bloques P0 vienen del plan de desarrollo autónomo
(`docs/_archivo/planes/PLAN_DESARROLLO_AUTONOMO.md` §5). El **código existe** para los
13; lo que no está verificado es que **funcionen de punta a punta** (suite completa y
E2E no se ejecutaron).

---

## 2. Estado por bloque

| P0 | Tema | Backend | Pantalla | Brecha principal |
|---|---|---|---|---|
| P0-01 | Alta de viaje del núcleo | `servicio_disponibilidad.py`, `api.py` | `/despacho` | Concurrencia real no probada (2 conexiones) |
| P0-02 | Maestros + documentos/Storage | `servicio_maestros.py`, `servicio_expediente.py` | `/maestros`, `/expediente` | Upload a Storage no verificado (RA-11) |
| P0-03 | OC / tarifas / centros de costo | `servicio_comercial.py` | `/comercial` | Requisito de OC es de facturación, no de despacho (decisión abierta) |
| P0-04 | Bloqueos de mantención/descanso | `servicio_bloqueos.py` | `/agenda` | Sin prueba de solapamiento contra viajes |
| P0-05 | Expediente del viaje | `servicio_expediente.py` | `/expediente/[id]` | Cierre con checklist parcial |
| P0-06 | POD | `servicio_pod.py` | — | Sin pantalla propia; storage sin verificar |
| P0-07 | PWA del conductor | `api_conductor.py` | `/conductor` | Modo offline no verificado |
| P0-08 | Gastos, combustible, peajes | `servicio_gastos.py` | — | Sin pantalla; combustible declarativo |
| P0-09 | Margen / tarifa piso / Freight Score | `servicio_rentabilidad.py` | `/rentabilidad` | Benchmark y volumen del catálogo no implementados |
| P0-10 | Facturación / cobranza | `servicio_facturacion.py` | `/cobranza` | Sin DTE; nota de crédito no implementada |
| P0-11 | Alertas y tablero | `servicio_alertas.py` | `/tablero` | "Caja" es proxy cobros−gastos, no saldo real |
| P0-12 | Roles / permisos / auditoría | `permisos.py`, `servicio_auditoria.py` | `/permisos`, `/auditoria` | Auditoría no cubre el legacy (RA-07) |
| P0-13 | Cutover / seed / E2E / backup / UAT | `servicio_cutover.py` | `/cutover` | **Bloqueado**: `0015` rompe `cutover_legacy.py` |

---

## 3. Lo próximo, en orden

| # | Trabajo | Por qué primero | Dueño |
|---|---|---|---|
| 1 | **Ejecutar `make test` y `make e2e` con base real y registrar la salida** | Sin línea base, todo "terminado" es 🔴 | `qa` |
| 2 | **Resolver el cutover roto por `0015`** (cargar documentos antes, o migrar en `borrador`) | Es el paso que habilita retirar el legacy | `arquitectura` + `datos` |
| 3 | **Cerrar SEC-002**: snapshot de la liquidación al emitir | Documento firmado no reproducible | `backend` + `datos` |
| 4 | **Unificar comisión**: `kpi_engine.py:368-381` vs `liquidaciones.py:51-96` | El tablero sobreestima | `backend` |
| 5 | **Demostrar aislamiento de tenant** (rol efectivo + RLS con políticas) | RA-03; hoy no es garantía | `datos` + `auditor-seguridad` |
| 6 | **Prueba de concurrencia real** en disponibilidad (dos conexiones) | RA-02; el `EXCLUDE` es correcto pero no se probó | `qa` |
| 7 | **Llenar la matriz de trazabilidad** (invariante → prueba) | Hoy hay garantías sin cobertura | `qa` |
| 8 | **Backup con comparación antes/después** | RA-05: el drill no detecta pérdida | `datos` |

---

## 4. Fuera de alcance (decidido, no olvidado)

| Tema | Estado | Quién decide |
|---|---|---|
| DTE / SII real | No implementado; el sistema no emite DTE | dueño + contador |
| GPS / telemetría | Solo check-in manual | dueño |
| Conciliación bancaria | No existe | dueño + contador |
| Nómina legal (AFP, salud, gratificación) | No implementado | asesor laboral |
| SaaS multiempresa | `nucleo` preparado, no expuesto | dueño |
| Factoring / simulador de caja | Solo propuesta histórica | dueño |

---

## 5. Reglas del backlog

1. Un P0 no se marca cerrado sin prueba ejecutada y registrada.
2. "Existe el endpoint" no es "está terminado": falta UI, permiso y prueba.
3. Lo que requiere decisión de negocio se mueve a `docs/negocio/preguntas.md`.
4. Lo que requiere trabajo técnico se refleja en `docs/arquitectura/deuda.md`.
