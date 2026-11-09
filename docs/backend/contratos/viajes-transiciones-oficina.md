# Contrato HTTP — Transiciones de estado de viaje desde la oficina y anulación

> **Pregunta que responde:** ¿qué puede hacer la mesa de despacho/supervisión
> con el estado de un viaje, con qué permiso, y qué garantiza la base?
> **Dueño:** `backend` · **Fecha:** 2026-11-02 · **Riesgo:** ALTO (cambio de
> estado operativo, disponibilidad de flota y consumo de OC).
> **Método:** lectura de `supabase/migrations/0004_nucleo_operacional.sql`
> (matriz, triggers), del código del núcleo y **pruebas ejecutadas**:
> `make unit` → 135 passed; `make test` → 423 passed, 0 skipped;
> `backend/tests/test_nucleo_transiciones.py` → 10 passed. Verificado contra
> `tei_test`: 29 aristas y 10 con `requiere_motivo` (todas hacia `anulado`);
> `anulado` es alcanzable desde `borrador, cotizado, confirmado, asignado,
> en_carga, cargado, en_ruta, en_descarga, descargado, pod_pendiente` y **no**
> desde `cerrado`, `facturado` ni `cobrado`.
> **Caduca si:** cambia la matriz `nucleo.transiciones_viaje`, el trigger
> `fn_viaje_transicion`/`fn_viaje_reservas`, la matriz de permisos
> (`backend/app/nucleo/permisos.py`) o la semántica de anulación.
> **Re-verificar con:** `make test`.

---

## 1. Reglas comunes

| Aspecto | Contrato |
|---|---|
| Prefijo | `/api/v1/nucleo` |
| Auth | `Authorization: Bearer <JWT>` validado contra JWKS |
| Tenant | `X-Empresa-ID: <uuid>` obligatorio; la empresa se resuelve en el servidor contra `nucleo.usuarios_empresa` y **nunca** desde el body |
| Correlación | `X-Request-ID` opcional (≤128, charset `[A-Za-z0-9._:-]`); se propaga a `nucleo.auditoria` |
| Fuente de la matriz | `nucleo.transiciones_viaje` (`0004:772-808`, 29 filas, catálogo **global**, sin `empresa_id`). No hay `dict` en Python con la matriz |
| Garantía en base | Trigger `fn_viaje_transicion` (`0004:1511-1547`) revalida la misma tabla y exige motivo; `fn_viaje_proteccion` impide reabrir un viaje anulado (`0004:1493-1495`) |
| Errores | `{"codigo","mensaje","contexto"{,"errores"}}` (`backend/app/nucleo/errores.py`) |
| Implementación | `backend/app/nucleo/servicio_transiciones.py`; rutas en `backend/app/nucleo/api.py` |

La matriz **solo se lee**: `tei_app` tiene `SELECT` y ningún `GRANT` de escritura
sobre `nucleo.transiciones_viaje` (`0020:270-271,363-370`).

---

## 2. `POST /api/v1/nucleo/viajes/{viaje_id}/transicion`

**Permiso:** `operacion:escribir` → `admin`, `gerente`, `despacho`
(`backend/app/nucleo/permisos.py:69-98`).

### Request

```json
{ "estado_destino": "asignado", "motivo": null }
```

| Campo | Tipo | Obligatorio | Límites |
|---|---|---|---|
| `estado_destino` | `EstadoViaje` (enum de `models.py:125-139`) | sí | debe existir la fila `(estado_actual, estado_destino)` en la matriz |
| `motivo` | `string \| null` | no (obligatorio si `requiere_motivo`) | ≤ 500; se recorta (`strip`) y `""` → `null` |

`extra="forbid"`: un campo desconocido es 422 de FastAPI. No se acepta
`version` en el body: la versión la lee el servidor bajo lock.

### Response 200

```json
{
  "viaje_id": "…",
  "numero_viaje": "VJ-2026-000123",
  "estado": "asignado",
  "estado_anterior": "confirmado",
  "version": 2,
  "reservas_liberadas": 0
}
```

`version` es la que quedó en la base (`fn_version`, `0004:89-97`).

### Reglas y rechazos explícitos

1. Viaje inexistente **o de otra empresa** → `404 RECURSO_NO_ENCONTRADO`
   (se filtra por `empresa_id` del contexto; no se revela el viaje ajeno).
2. `estado_destino ∈ {facturado, cobrado}` → `409 ESTADO_VIAJE_INVALIDO`
   (`contexto.via = "facturacion"`). Ese paso lo controla facturación:
   `fn_viaje_facturacion` (`0004:1387-1449`) exige OC vigente y sin sobregiro,
   y `servicio_facturacion.py` exige POD. **Aunque la matriz tenga
   `cerrado → facturado`, este endpoint no es la vía.**
3. `estado_destino = "anulado"` → `409 ESTADO_VIAJE_INVALIDO`
   (`contexto.via = "anulacion"`). Anular exige `comercial:aprobar` y libera
   reservas con motivo; permitirlo aquí daría a despacho una vía para saltarse
   ese control. **Orden de validación:** si además falta el motivo que exige la
   matriz, la respuesta es `422 DATOS_INVALIDOS` (petición incompleta) antes que
   el 409 de "flujo equivocado".
4. `estado_destino = "asignado"` sin tracto/rampla/chofer → `409
   ESTADO_VIAJE_INVALIDO` (`contexto.via = "asignacion"`). `fn_viaje_validar`
   (`0004:1140-1144`) exige los tres recursos para ese estado; la vía correcta
   es `POST /viajes/{id}/asignar`, que además valida documentos, ventana y crea
   las reservas en la misma transacción.
5. Transición ausente en la matriz → `409 ESTADO_VIAJE_INVALIDO` con
   `contexto.destinos_permitidos` (lista ordenada, leída de la tabla).
6. `requiere_motivo = true` y `motivo` vacío → `422 DATOS_INVALIDOS`.

### Efectos

- `UPDATE nucleo.viajes` con `WHERE id AND empresa_id AND version` (control
  optimista). `rowcount != 1` → `409 CONFLICTO_CONCURRENCIA`, sin commit.
- `inicio_real = now()` si el destino es `en_carga` y estaba `NULL`.
- `fin_real = now()` si el destino es `descargado` y estaba `NULL`.
- `INSERT nucleo.viaje_eventos` con `tipo='transicion_oficina'` y payload
  `{estado_origen, estado_destino, motivo, origen: "oficina"}`.
- Triggers: `fn_viaje_reservas` (`0004:1621-1650`) recalcula el libro de
  reservas del viaje; `fn_oc_recalcular` (`0004:1550-1597`) recalcula
  `monto_consumido` de la OC. **El backend no reimplementa ninguno de los dos.**

---

## 3. `POST /api/v1/nucleo/viajes/{viaje_id}/anular`

**Permiso:** `comercial:aprobar` → `admin`, `gerente`
(`permisos.py:69-73`). `despacho` recibe `403 ACCESO_DENEGADO`.

### Request

```json
{ "motivo": "Cliente canceló el embarque" }
```

| Campo | Tipo | Obligatorio | Límites |
|---|---|---|---|
| `motivo` | `string` | **sí** | 5–500 caracteres útiles (se recorta; solo espacios → 422) |

`extra="forbid"`.

### Response 200

Igual que el endpoint anterior; `reservas_liberadas` es el número de filas de
`nucleo.reservas_recurso` desactivadas por esta llamada.

### Reglas

1. No existe `(estado_actual, 'anulado')` en la matriz → `409
   ESTADO_VIAJE_INVALIDO` con `contexto.estado_origen` y
   `contexto.destinos_permitidos`. Estados sin salida a `anulado`: `cerrado`,
   `facturado`, `cobrado` (la matriz no tiene esas filas; un viaje cerrado se
   corrige por el flujo de facturación, no anulándolo).
2. Viaje ya `anulado` → `409 ESTADO_VIAJE_INVALIDO`: la matriz no tiene
   transición desde `anulado` y `fn_viaje_proteccion` impide reabrirlo.
   **No hay tabla de idempotencia**: la máquina de estados es el árbitro (misma
   clave natural; repetir la operación no duplica nada, devuelve 409).
3. Viaje de otra empresa → `404 RECURSO_NO_ENCONTRADO`.

### Efectos (orden determinista, una sola transacción)

1. `SELECT … FOR UPDATE` sobre `nucleo.viajes` (fila del viaje) — mismo orden de
   lock que el endpoint de transición.
2. `UPDATE nucleo.reservas_recurso SET activa=false, cancelado_motivo=:motivo,
   cancelado_por=:auth_id, cancelado_en=now()` para las reservas activas del
   viaje. **Las filas no se borran** (`trg_reservas_no_delete`, `0004:1692-1700`).
3. `UPDATE nucleo.viajes SET estado='anulado', motivo_anulacion=:motivo` con
   `WHERE … AND version`. `fn_viaje_transicion` completa `anulado_por`/
   `anulado_en` desde `nucleo.auth_id` (`0004:1536-1543`).
4. `INSERT nucleo.viaje_eventos` con `tipo='anulado'` y payload
   `{estado_origen, estado_destino:"anulado", motivo, origen:"oficina",
   reservas_liberadas}`.
5. Un único `commit()` al final; `IntegrityError` → `rollback` +
   `traducir_integrity_error`.

**Por qué las reservas se actualizan antes del viaje:** el trigger
`fn_viaje_reservas` desactiva todas las reservas activas en cada `UPDATE` de
`nucleo.viajes`, pero sin motivo ni actor. Si se actualizara primero el viaje,
las reservas quedarían inactivas sin trazabilidad de la cancelación.

---

## 4. Códigos de estado y SQLSTATE

| Situación | HTTP | `codigo` | Origen |
|---|---|---|---|
| Transición/anulación aplicada | 200 | — | servicio |
| Sin identidad / sin `X-Empresa-ID` válido | 401 / 403 | `ACCESO_DENEGADO` | `deps.py` / `permisos.py` |
| Viaje de otra empresa / inexistente | 404 | `RECURSO_NO_ENCONTRADO` | servicio |
| Transición fuera de la matriz, `facturado`/`cobrado`, `anulado` por esta vía, `asignado` sin recursos | 409 | `ESTADO_VIAJE_INVALIDO` | servicio |
| Versión cambiada entre lectura y update | 409 | `CONFLICTO_CONCURRENCIA` | servicio |
| `requiere_motivo` sin motivo, motivo inválido | 422 | `DATOS_INVALIDOS` | servicio / Pydantic |
| `23505` unique_violation | 409 | `REGISTRO_DUPLICADO` | `traducir_integrity_error` |
| `23P01` exclusion_violation | 409 | `CONFLICTO_DISPONIBILIDAD` | idem |
| `23514` check/raise del trigger (si el servicio no lo previó) | 409 | `REGLA_NEGOCIO_VIOLADA` | idem |
| `40001` / `40P01` serialización o deadlock | 409 | `CONFLICTO_CONCURRENCIA` | idem |
| `23503` FK inexistente/de otra empresa | 422 | `DATOS_INVALIDOS` | idem |
| `23502` not-null | 500 | `ERROR_PERSISTENCIA` | idem — **deuda**, ver §7 |

Nunca se devuelve el `message_primary` de PostgreSQL (SEC-017).

---

## 5. Idempotencia

- No se usa `Idempotency-Key`: no entra ni sale dinero de estas operaciones.
- La **clave natural** es la tupla `(viaje_id, estado_origen, estado_destino)`
  de la matriz y el `version` del viaje. Repetir la misma transición después de
  aplicada devuelve 409 (el origen ya cambió); dos ejecuciones concurrentes no
  pueden aplicarse dos veces por el `FOR UPDATE` + `WHERE version`.
- Si en el futuro se expone un botón que pueda reintentarse automáticamente, el
  cliente debe tratar 409 como "ya aplicado/no aplicable" y refrescar el viaje.

---

## 6. Compatibilidad

- **Endpoints nuevos**: no existían; no rompen consumidores.
- `frontend/src/lib/nucleo.ts` **no** tiene todavía un método para estas rutas;
  la pantalla debe implementarse contra este contrato (handoff a `frontend`).
- La PWA del conductor (`api_conductor.py`, `servicio_conductor.py`) **no se
  tocó**: sigue con su propio endpoint y su propia matriz.
- `nucleo.viaje_eventos` ya existía (`models.py:905+`): se usan tipos nuevos
  (`transicion_oficina`, `anulado`) sin cambiar el esquema. Un consumidor de
  expediente que liste eventos verá los nuevos tipos.

---

## 7. Deuda declarada (no corregida aquí)

1. **Copia de la matriz en el flujo del conductor.**
   `backend/app/nucleo/servicio_conductor.py:51-58` define
   `TRANSICIONES_CONDUCTOR` como `dict` en Python, y `:64-74` fija
   `SIGUIENTE_ACCION` con los mismos estados. Hoy **coincide** con la tabla
   (`asignado→en_carga`, `en_carga→cargado`, `cargado→en_ruta`,
   `en_ruta→en_descarga`, `en_descarga→descargado`, `descargado→pod_pendiente`,
   todas presentes en `0004:779-808`), pero es una segunda fuente de verdad:
   un cambio en la matriz no se propaga al conductor. Debe migrarse a leer
   `nucleo.transiciones_viaje` (permitiendo además solo el avance hacia
   adelante que el conductor necesita).
2. **`23502` (not-null) se traduce a 500.** `traducir_integrity_error`
   (`errores.py:136-189`) no tiene rama para `23502`; según `AGENTS.md` §8
   debería ser 422. No se modificó `errores.py` (fuera del alcance de esta
   tarea); no es alcanzable por estos dos endpoints porque los schemas
   completan todo campo obligatorio.
3. **Anulación de factura: decisión pendiente, sin código.** No se implementa
   porque es materia tributaria (`AGENTS.md` §3.15/§3.16). El mecanismo
   existente para compensar un documento emitido es la nota de crédito:
   `POST /api/v1/nucleo/facturacion/facturas/{factura_id}/notas-credito`
   (`backend/app/nucleo/api_facturacion.py:106-112`,
   `servicio_facturacion.py:711-749`). Falta que el dueño/contador confirme si
   "anular factura" significa emitir nota de crédito total, y si el viaje
   asociado debe volver de `facturado` a `cerrado` (hoy la matriz no lo permite).
4. **Sin cobertura de concurrencia real para la anulación.** El conflicto de
   versión se prueba con una sesión simulada; dos conexiones simultáneas sobre
   el mismo viaje no se probaron (el `FOR UPDATE` serializa, así que el segundo
   request debería ver el estado `anulado` y recibir 409). Pendiente para `qa`
   con dos conexiones reales.
5. **Tensión con `ADR-0008` (propuesto, `arquitectura`, 2026-11-02).** Su §0
   (punto 6) "prohíbe cualquier endpoint genérico 'cambiar estado'". Este
   endpoint lo es en la forma (`{estado_destino}`), pero acotado: la legalidad
   la decide la matriz de la base, `facturado`/`cobrado` se rechazan
   explícitamente y `anulado` tiene ruta y permiso propios. La ratificación (o
   el reemplazo por un endpoint por transición) es del dueño/`arquitectura`;
   mientras tanto este contrato es el que está implementado y probado.
6. **`ADR-0008` §1.2 #27 quedará desactualizado** con este cambio: afirmaba que
   ningún código Python lee `nucleo.transiciones_viaje`. Ahora la lee
   `servicio_transiciones.py`. Corregir ese ADR es de `arquitectura`.
