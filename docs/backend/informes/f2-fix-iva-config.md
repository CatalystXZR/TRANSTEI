# F2 — La factura del núcleo usa el IVA de la configuración de la empresa (RET-04)

- **Fecha:** 2026-10-31
- **Agente / rol:** `backend`
- **Riesgo:** **Alto (tributario)** — dinero + impuesto
- **Origen:** hallazgo del ADR-0002 rev. 3 (`docs/arquitectura/adr/ADR-0002-retiro-del-legacy.md:149-153,286,500`;
  `docs/arquitectura/retiro-legacy.md:138,309-320`; `docs/arquitectura/fuentes-de-verdad.md:53,86`).
  Dos fuentes de la tasa de IVA dentro del núcleo.
- **Alcance tocado:** solo `backend/app/nucleo/schemas.py`,
  `backend/app/nucleo/servicio_facturacion.py`, `backend/tests/**` y este informe.
  Sin migraciones, sin frontend, sin `git commit`.

## Resultado

`POST /api/v1/nucleo/cobranza/facturas` ya **no puede fijar el impuesto desde el
request**. El IVA se calcula con la tasa **vigente de la empresa** leída de
`nucleo.configuracion_empresa.iva_porcentaje` (migración 0026). El campo
`tasa_iva` del request queda **deprecado y sin efecto**.

- `servicio_facturacion.py:602` — `iva = _d(neto * self._tasa_iva_vigente())`
  (antes `neto * data.tasa_iva`).
- `servicio_facturacion.py:566-580` — `_tasa_iva_vigente()`:
  `select nucleo.config_vigente(:empresa_id, 'iva_porcentaje')`.
  Sin fila vigente ⇒ `ReglaNegocioViolada` (409, `contexto.clave = "iva_porcentaje"`).
  **No hay 19 % implícito**: el valor es un parámetro tributario (`P-01`/`D-21`).
- `servicio_facturacion.py:74-99` — `tasa_desde_porcentaje()`: única conversión
  porcentaje (19) → fracción (0,1900). Precisión 4 decimales (la que declaraba el
  campo retirado). El rango 0–100 ya está impuesto en la base
  (`ck_config_iva_porcentaje`, 0026).
- `schemas.py:1551-1561` — `FacturaCreate.tasa_iva` pasa a
  `Decimal | None = None`, `deprecated=True`, sin `ge/le`.
  Se conserva **solo por compatibilidad** con el cliente actual
  (`frontend/src/components/cobranza/nueva-factura-dialog.tsx:114` envía
  `tasa_iva`); el backend lo ignora. Eliminarlo exige coordinar el retiro en el
  frontend.

## Contrato

`POST /api/v1/nucleo/cobranza/facturas` (sin cambios de forma en request/response)

| Aspecto | Antes | Ahora |
|---|---|---|
| `tasa_iva` (body) | obligatorio funcional, default `0.19`, `0<=x<=1` | **ignorado**; opcional, sin validación, marcado `deprecated` en OpenAPI |
| Origen del IVA | request | `nucleo.configuracion_empresa.iva_porcentaje` vigente (fracción = valor/100) |
| Empresa sin config | emitía al 19 % | **409** `REGLA_NEGOCIO_VIOLADA`, `contexto {"clave":"iva_porcentaje"}`; sin escrituras |
| Errores nuevos | — | 409 si falta la config o si el valor configurado no es numérico / sale de 0–100 |
| `neto`, `iva`, `total` en response | igual | igual (calculados con la tasa vigente) |
| Auth/permiso | `facturacion:emitir` | sin cambio |
| Idempotencia | `uq_factura_viaje_unico` + `siguiente_folio` | sin cambio |

Verificado en el OpenAPI generado: `tasa_iva` es opcional (`required` no la
incluye), aparece `deprecated: true` y una `description` que declara el ignorado;
`FacturaCreate(..., tasa_iva=10)` valida y el valor no influye en la factura.

## Autorización

Sin cambios: `crear_factura` sigue detrás de `requiere_permiso("facturacion:emitir")`
(`backend/app/nucleo/api_facturacion.py:34-38,79-86`). La empresa sale del
contexto del servidor (`X-Empresa-ID` → membresía), nunca del body; la lectura de
configuración usa `self.empresa.id` y `nucleo.config_vigente` (RLS aplica con
`tei_app`). La prueba nueva valida además la lectura **con el rol real `tei_app`**
y su GUC `app.empresa_id` (`test_nucleo_facturacion.py:513-524`).

## Transacción e idempotencia

La lectura de la tasa ocurre **antes** de `_fijar_contexto_bd()`, del folio y de
cualquier `INSERT/UPDATE`. Si falta configuración, el error se lanza sin escribir:
no hay factura, no cambia `viaje.estado` (probado explícitamente). La transacción
de emisión sigue siendo una sola: factura + `factura_viajes` + transición de viajes
+ `viaje_eventos`, con `commit` único y `rollback` en `IntegrityError`/excepción
(`servicio_facturacion.py:604-676`). No se agregaron efectos externos ni locks.

## Pruebas (salidas reales)

Entorno: Supabase local `127.0.0.1:54322`, base de test `tei_test`, migraciones
incluida `0026`. Fecha 2026-10-31.

```text
$ make unit
128 passed, 2 warnings in 0.69s

$ make test
415 passed, 2 warnings in 7.76s
```

```text
$ cd backend && NUCLEO_TEST_DATABASE_URL=... NUCLEO_DATABASE_URL=... \
    ../.venv/bin/python -m pytest tests/test_nucleo_facturacion.py -q
............                                                     [100%]
```

Casos nuevos (`backend/tests/test_nucleo_facturacion.py`):

1. `test_tasa_desde_porcentaje_convierte_la_configuracion` (4 casos) y
   `test_tasa_desde_porcentaje_rechaza_valores_invalidos` (4 casos) — regla pura,
   sin base.
2. `test_factura_usa_la_config_e_ignora_tasa_iva_del_request` (línea 475):
   config de la empresa = **21 %**; factura A con `tasa_iva=10` y factura B sin el
   campo ⇒ ambas `iva = 21000.00` sobre `neto = 100000.00`, `total = 121000.00`.
   Demuestra que manda la config y no el request **ni** el default histórico 19 %.
3. `test_factura_sin_iva_configurado_falla_409_sin_efectos` (línea 569):
   empresa sin `iva_porcentaje` ⇒ 409 `REGLA_NEGOCIO_VIOLADA`,
   `contexto["clave"]=="iva_porcentaje"`, cero facturas y viaje aún `cerrado`.

**Sanidad (mutación):** se reemplazó temporalmente la línea 602 por
`iva = _d(neto * (data.tasa_iva or Decimal("0.19")))` y el caso 2 falló:

```text
FAILED tests/test_nucleo_facturacion.py::test_factura_usa_la_config_e_ignora_tasa_iva_del_request
```

Restaurado el código correcto; la prueba vuelve a pasar. La prueba falla si se
retira el mecanismo.

Regresión adicional: `test_nucleo_alertas.py` emite una factura en su fixture; se le
agregó la configuración de IVA (0026 solo sembró las empresas existentes). Verde.

## Compatibilidad

- **Frontend:** `nueva-factura-dialog.tsx:114` sigue enviando `tasa_iva`; el
  request no rompe (campo aceptado e ignorado). **Pendiente de frontend:** el
  diálogo calcula la vista previa con el valor que escribe el usuario
  (`nueva-factura-dialog.tsx:81`), que ya no determina la factura. Debe mostrar la
  tasa de `GET /nucleo/configuracion` (o `iva_porcentaje`) y dejar de enviar el
  campo.
- **Legacy:** sin cambios; no se tocó `public`.
- **Contrato previo:** todo cliente que enviaba `tasa_iva` sigue recibiendo 201;
  solo cambia el número de IVA, que ahora es el configurado. Ningún endpoint se
  eliminó ni cambió de forma.

## Riesgos y no verificado

1. 🟡 **Empresas creadas después de aplicar 0026 no tienen `iva_porcentaje`.** La
   migración sembró solo las existentes (`0026:302-314`; en `postgres` 2/2, en
   `tei_test` 187/658 al 2026-10-31, el resto son empresas de prueba). Con este
   cambio, facturar en una empresa nueva devuelve **409 claro** hasta que un
   admin configure el IVA (`PUT /nucleo/configuracion/iva_porcentaje`). Es
   fail-closed y correcto tributariamente, pero exige dueño: `datos`/`orquestador`
   deben decidir si la creación de empresa (seed/cutover) siembra la clave o si es
   un paso obligatorio del alta. **No se creó migración** (fuera de alcance).
2. 🟡 **La garantía es de servicio, no de base.** `facturas_nucleo.iva` es un
   `numeric` calculado por el servicio; no hay CHECK que lo ate a
   `neto × config`. Agregarlo requeriría función/trigger y migración (`datos`).
   La prueba de sanidad cubre el servicio.
3. 🔴 **No se ejecutó HTTP/E2E para el 409 nuevo** (`make e2e` no se corrió: exige
   frontend y datos; el flujo E2E actual no emite facturas, solo lee el seed). El
   mapeo 409 de `ReglaNegocioViolada` ya está cubierto por la suite, pero el caso
   HTTP exacto de facturación no tiene prueba propia.
4. 🟡 `docs/negocio/implementacion.md:75` y `docs/arquitectura/retiro-legacy.md:317`
   siguen describiendo el residual. Deben actualizarse por sus dueños
   (`negocio-finanzas`, `arquitectura`); este agente no escribe en esas carpetas.
5. 🟡 No se tocó el IVA del **legacy** (ya retirado) ni el resumen de IVA débito
   (`servicio_iva.py`), que ya leía la config.
