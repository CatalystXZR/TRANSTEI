# Contrato HTTP — Ola B del retiro legacy (mantenimiento, nómina, IVA, configuración, export)

> **Pregunta que responde:** ¿qué endpoints del núcleo reemplazan a los módulos
> legacy sin equivalente y con qué contrato exacto?
> **Dueño:** `backend` · **Fecha:** 2026-10-31 · **Riesgo:** ALTO (nómina,
> impuestos, configuración por empresa).
> **Método:** lectura de `supabase/migrations/0024–0026`, implementación en
> `backend/app/nucleo/servicio_*.py` / `api_*.py` y pruebas ejecutadas en
> `backend/tests/test_nucleo_ola_b_modulos.py`.
> **Caduca si:** cambia una migración 0024–0026, la matriz de permisos o la
> fórmula de comisión. **Re-verificar con** `make test`.
>
> **Alcance:** se portan con paridad funcional mínima mantenimiento, nómina,
> export CSV y configuración. El resumen de IVA es **solo débito**: el crédito
> fiscal, el monto a pagar y el arrastre de remanente dependen de `P-09` y no se
> implementan. El import CSV del legacy **no** se porta.

---

## 1. Reglas comunes

| Aspecto | Contrato |
|---|---|
| Prefijo | `/api/v1/nucleo` |
| Auth | `Authorization: Bearer <JWT>` validado contra JWKS |
| Tenant | `X-Empresa-ID: <uuid>` obligatorio; la empresa se resuelve en el servidor contra `nucleo.usuarios_empresa` y **nunca** desde el body |
| Correlación | `X-Request-ID` opcional (≤128, charset `[A-Za-z0-9._:-]`); se propaga a auditoría |
| Rol/permiso | Deny-by-default; cada endpoint declara su permiso (`requiere_permiso`) |
| Errores | `{"codigo": "...", "mensaje": "...", "contexto": {...}}`; violaciones PostgreSQL traducidas por `manejador_error_nucleo` (23505/23P01→409, 23514/23503→409/422) |
| 401 / 403 | Sin identidad válida / rol sin el permiso requerido (`ACCESO_DENEGADO`) |
| 404 | Recurso inexistente **o de otra empresa** (`RECURSO_NO_ENCONTRADO`) |
| 422 | Validación Pydantic o regla de dominio de entrada (`DATOS_INVALIDOS`) |
| Paginación | Listados con límite duro en servidor (200/500/5000) y orden estable con desempate por `id` |
| RLS | El backend usa el engine `tei_app` (sin `BYPASSRLS`); además de la política, toda consulta filtra por `empresa_id` |

### Matriz de permisos agregada

| Permiso | admin | gerente | despacho | contador | tesorería | taller | conductor | auditor |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `mantenimiento:leer` | ✔ | ✔ | ✔ | ✔ | — | ✔ | — | ✔ |
| `mantenimiento:escribir` | ✔ | ✔ | ✔ | — | — | ✔ | — | — |
| `liquidaciones:leer` | ✔ | ✔ | — | ✔ | — | — | — | — |
| `liquidaciones:escribir` | ✔ | ✔ | — | ✔ | — | — | — | — |
| `iva:leer` | ✔ | ✔ | — | ✔ | ✔ | — | — | ✔ |

Criterio: nómina sigue SEC-008 (solo admin/gerencia/contabilidad); mantenimiento
conserva el permiso de operación/taller del legacy; IVA queda para quien ya lee
documentos tributarios.

---

## 2. Mantenimiento (`0024`)

### 2.1 `GET /api/v1/nucleo/mantenimiento/pautas`

- Permiso: `mantenimiento:leer`.
- Query: `recurso_tipo` (`tracto|rampla`, opcional), `incluir_inactivas` (bool,
  default `false`).
- 200 → `PautaMantenimientoOut[]`:
  `{id, recurso_tipo, item, intervalo_km, intervalo_meses, alerta_km, orden,
  activo, version, created_at, updated_at}`.
- Errores: 401/403/422 (enum inválido).

### 2.2 `POST /api/v1/nucleo/mantenimiento/pautas`

- Permiso: `mantenimiento:escribir`.
- Request (`extra="forbid"`):
  `{recurso_tipo?, item (1..120), intervalo_km (>0), intervalo_meses? (>0),
  alerta_km? (>=0), orden? (>=0)}`.
- 201 → `PautaMantenimientoOut`.
- Errores: 409 `REGISTRO_DUPLICADO` si ya hay una pauta **activa** con el mismo
  `(recurso_tipo, lower(item))`; 422 si `recurso_tipo` no es tracto/rampla o
  `intervalo_km <= 0`.

### 2.3 `GET /api/v1/nucleo/mantenimiento/mantenimientos`

- Permiso: `mantenimiento:leer`.
- Query: `recurso_tipo`, `recurso_id`, `pauta_id`, `estado`
  (`realizado|anulado`), `desde`, `hasta` (fecha, inclusivo).
- 200 → `MantenimientoOut[]`, orden `fecha desc, created_at desc, id`.

### 2.4 `POST /api/v1/nucleo/mantenimiento/mantenimientos`

- Permiso: `mantenimiento:escribir`.
- Request: `{pauta_id, tracto_id xor rampla_id, fecha, km (>=0, 1 decimal),
  costo? (>=0), observaciones?, respaldo_url?}`.
- Reglas de servicio: la pauta debe existir en la empresa y estar activa; el
  recurso debe ser de la empresa y del mismo tipo que la pauta; `km` no puede
  ser menor al odómetro actual del tracto; `respaldo_url` es una ruta relativa
  (sin `..`, sin esquema, sin `/` inicial).
- 201 → `MantenimientoOut` (incluye `intervalo_km_snapshot`,
  `intervalo_meses_snapshot`, `alerta_km_snapshot`).
- Errores: 404 pauta/recurso; 409 regla de negocio (pauta inactiva); 422
  validación (xor, costo/km negativos, respaldo inválido).

### 2.5 `POST /api/v1/nucleo/mantenimiento/mantenimientos/{id}/anular`

- Permiso: `mantenimiento:escribir`.
- Request: `{motivo (3..500)}`.
- 200 → `MantenimientoOut` con `estado="anulado"`, sello de anulación.
- Reemplaza el `DELETE` del legacy: el histórico se conserva.
- Errores: 404; 409 si ya está anulado (terminal); 422 sin motivo.

### 2.6 `GET /api/v1/nucleo/mantenimiento/estado`

- Permiso: `mantenimiento:leer`.
- Query: `recurso_tipo`, `recurso_id`, `estado`
  (`sin_registro|sin_odometro|pendiente|por_vencer|ok`).
- 200 → `EstadoMantenimientoOut[]`, leído de `nucleo.v_mantenimiento_estado`
  (única definición del semáforo; no se almacena).
- `proximo_km = ultimo_km + intervalo_km` del snapshot; `restante_km =
  proximo_km − odómetro`; ver §5 del informe (CN-08).
- Errores: 422 estado no válido.

> **No implementado:** bloquear el despacho por mantención vencida (`RET-08`
> abierto) y prorratear el costo al viaje (`D-20`).

---

## 3. Nómina (`0025`)

### 3.1 `GET /api/v1/nucleo/liquidaciones`

- Permiso: `liquidaciones:leer`.
- Query: `mes` (`YYYY-MM`), `chofer_id`, `estado`
  (`borrador|emitida|anulada`).
- 200 → `LiquidacionOut[]` con montos **almacenados** (sin recálculo) y
  `chofer_nombre`.

### 3.2 `POST /api/v1/nucleo/liquidaciones`

- Permiso: `liquidaciones:escribir`.
- Request: `{chofer_id, mes (YYYY-MM), sueldo_base? (>=0), notas?}`.
- Cálculo del borrador:
  - `comision = redondear_half_up(Σ valor_flete_neto(viajes facturados del mes) ×
    porcentaje_comision, 2)`; el mes se atribuye por la **primera emisión de
    factura no anulada** (`R-01`/`R-05`).
  - `bonos`/`descuentos` = ajustes `vigente` del chofer y mes.
  - `anticipos` = anticipos `pendiente` del chofer y `mes_imputacion`.
  - `sueldo_base` = el del request o el del chofer (snapshot).
  - `total_liquido` lo calcula la **columna generada** de la base.
- 201 → `LiquidacionOut`.
- Errores: 404 chofer; 409 `REGISTRO_DUPLICADO` si existe
  `(empresa, chofer, mes)`; 422 mes/montos inválidos.

### 3.3 `POST /api/v1/nucleo/liquidaciones/{id}/emitir`

- Permiso: `liquidaciones:escribir`.
- Efecto atómico: bloquea la fila (`SELECT … FOR UPDATE`), recalcula comisión y
  ajustes vigentes, imputa los anticipos pendientes del período
  (`estado='descontado'`, `liquidacion_id`), fija `estado='emitida'` y los
  sellos `emitida_en/por`. Todo en una transacción.
- **Idempotente:** si ya está `emitida`, devuelve el mismo documento sin volver
  a imputar.
- 200 → `LiquidacionOut`.
- Errores: 404; 409 si está `anulada` o si el estado cambió en carrera.
- Concurrencia: dos emisiones simultáneas se serializan por el lock; una sola
  imputa (prueba con dos conexiones reales).

### 3.4 `POST /api/v1/nucleo/liquidaciones/{id}/anular`

- Permiso: `liquidaciones:escribir`.
- Request: `{motivo (3..500)}`.
- 200 → `LiquidacionOut` anulada. Repetir con el mismo motivo es idempotente;
  con otro motivo → 409.
- Errores: 404; 409; 422.

> **Limitación conocida (0025):** `UNIQUE (empresa_id, chofer_id, mes)` no es
> parcial por estado, así que tras anular **no** se puede crear un documento
> nuevo para el mismo chofer y mes. Es una decisión pendiente de `datos`
> (índice parcial); el servicio responde 409 `REGISTRO_DUPLICADO` con mensaje
> explícito y no se modificó la migración.

### 3.5 `GET /api/v1/nucleo/anticipos`

- Permiso: `liquidaciones:leer`.
- Query: `chofer_id`, `mes` (sobre `mes_imputacion`), `estado`
  (`pendiente|descontado|anulado`).
- 200 → `AnticipoOut[]`.

### 3.6 `POST /api/v1/nucleo/anticipos`

- Permiso: `liquidaciones:escribir`.
- Request: `{chofer_id, fecha? (default hoy), monto (>0), mes_imputacion
  (YYYY-MM), notas?}`.
- 201 → `AnticipoOut` en `pendiente`.
- La imputación es única por fila y por período: la garantía vive en
  `fn_imputacion_validar` (no se reimputa ni se limpia).
- Errores: 404 chofer; 422.

### 3.7 `GET /api/v1/nucleo/ajustes`

- Permiso: `liquidaciones:leer`.
- Query: `chofer_id`, `mes`, `estado` (`vigente|anulado`).
- 200 → `AjusteOut[]`.

### 3.8 `POST /api/v1/nucleo/ajustes`

- Permiso: `liquidaciones:escribir`.
- Request: `{chofer_id, mes, tipo (bono|descuento), concepto (1..200), monto
  (>=0)}`.
- 201 → `AjusteOut`.
- Errores: 404 chofer; 422 (tipo, concepto vacío, monto negativo).

> **No implementado (documentado):** AFP/salud/cesantía/impuesto único (`P-02`),
> arrastre o rechazo de anticipos de meses cerrados (`D-19`/`P-10`), bloqueo de
> `total_liquido` negativo (`D-19`), reimputación al anular (`P-12`).

---

## 4. IVA (`0026`)

### `GET /api/v1/nucleo/iva/resumen?desde=YYYY-MM-DD&hasta=YYYY-MM-DD`

- Permiso: `iva:leer`.
- 200 → `{desde, hasta, tasa_iva, facturas, base_neta, iva_debito, advertencia}`.
- `iva_debito = Σ nucleo.facturas_nucleo.iva` de facturas `estado <> 'anulada'`
  emitidas en `[desde, hasta]` (fechas inclusivas).
- `tasa_iva` = `nucleo.config_vigente(empresa, 'iva_porcentaje')`; `null` si la
  empresa no tiene valor configurado (no se hardcodea).
- **No** devuelve crédito fiscal, `a_pagar` ni remanente: dependen de `P-09`.
  Tampoco descuenta notas de crédito (`P-06`/`P-09`).
- Errores: 422 si `desde > hasta`.

---

## 5. Configuración por empresa (`0026`)

### 5.1 `GET /api/v1/nucleo/configuracion`

- Permiso: `configuracion:leer`.
- 200 → `{items: [{clave, valor, vigente_desde, updated_at, version}], mensaje}`
  con las filas **vigentes** (`vigente_hasta IS NULL`).

### 5.2 `GET /api/v1/nucleo/configuracion/{clave}`

- Permiso: `configuracion:leer`.
- 200 → `ConfiguracionItemOut`.
- Errores: 404 si no hay valor vigente; 422 si la clave no pertenece al
  catálogo.

### 5.3 `PUT /api/v1/nucleo/configuracion/{clave}`

- Permiso: `configuracion:escribir` (solo admin/gerente).
- Request: `{valor: <json>}`.
- Catálogo y validación en servidor:
  | Clave | Tipo | Rango |
  |---|---|---|
  | `iva_porcentaje` | número | 0–100 |
  | `alerta_km_mantenimiento` | entero | ≥0 |
  | `dias_alerta_vencimientos` | entero | ≥0 |
  | `dias_alerta_cobranza` | entero | ≥0 |
- Efecto: cierra la vigencia actual (`vigente_hasta = now()`) e inserta una fila
  nueva con el **mismo `now()`** (evita solape del `EXCLUDE`). Historial
  append-only; nunca se edita el valor de una fila.
- **Idempotente:** si el valor normalizado es igual al vigente, no crea versión.
- 200 → `ConfiguracionItemOut`.
- Errores: 422 valor fuera de rango/tipo/clave desconocida; 409
  `CONFLICTO_CONCURRENCIA` si otra transacción cambió la vigencia al mismo
  tiempo (23P01/23505).

---

## 6. Export CSV (solo lectura)

| Endpoint | Permiso | Query | Filas |
|---|---|---|---|
| `GET /api/v1/nucleo/export/liquidaciones` | `liquidaciones:leer` | `mes?` | almacenadas, sin recálculo |
| `GET /api/v1/nucleo/export/viajes` | `operacion:leer` | `desde?`, `hasta?` | viajes del tenant |
| `GET /api/v1/nucleo/export/facturas` | `facturacion:leer` | — | facturas del tenant |

- `Content-Type: text/csv; charset=utf-8`, `Content-Disposition: attachment`.
- UTF-8 con BOM, separador `;`, decimal con coma (paridad legacy).
- **Sin recálculo:** exporta exactamente lo almacenado (corrige CN-09 del
  legacy, que recalculaba la comisión).
- **Anti-inyección de fórmulas:** toda celda que empieza con `=`, `+`, `-` o `@`
  se prefija con `'`.
- Límite duro: 5.000 filas por archivo.
- Errores: 422 `mes` inválido o `desde > hasta`.

---

## 7. Compatibilidad

- Las rutas legacy `/api/v1/{mantenimiento,liquidaciones,anticipos,ajustes,iva,
  configuracion,export}` **siguen existiendo** y no se modificaron (ADR-0002:
  retiro por olas). Los nuevos endpoints viven bajo `/api/v1/nucleo` y no
  colisionan.
- El frontend de la Ola A retiró las pantallas legacy; **ningún cliente consume
  todavía** estos endpoints. El handoff está en el informe
  `docs/backend/informes/f2-ola-b-modulos-nucleo.md`.
- No se tocó `public` ni se agregó una tercera fuente de verdad.
