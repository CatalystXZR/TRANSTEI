# Fase 1, Ola 3 (backend) — SEC-023, SEC-021 y F-04

Fecha: 2026-10-30 · Agente: `backend` · Riesgo: **Medio**
Objetivo: tope de fotos del POD (SEC-023), evaluación del tope de transporte
multipart (SEC-021) y precisión decimal en el motor de KPIs (F-04).
Estado: **SEC-023 y F-04 implementados y verificados**; **SEC-021 reportado con
diseño, no implementado** (requiere `backend/app/main.py`, fuera de los archivos
autorizados).

---

## 1. Resultado

| Defecto | Estado | Qué se hizo |
|---|---|---|
| **SEC-023** (Media) — sin tope de cantidad de fotos del POD | **Cerrado** | `MAX_FOTOS = 10` validado en el router **antes de leer bytes** y revalidado en el servicio, incluido el acumulado entre actualizaciones |
| **SEC-021** (Media-Baja) — multipart sin tope de transporte | **Reportado con diseño** | Confirmado el orden `form()` → auth; el remedio correcto es un middleware ASGI en `app/main.py` (fuera de alcance). No se implementó a medias |
| **F-04** (Media) — dinero convertido a `float()` en KPIs | **Cerrado** | Aritmética en `Decimal` en `metricas_viaje` y `metricas_global`; `float` solo en `metricas_para_json` (borde de serialización) |

---

## 2. Cambios (archivo:línea)

| Archivo | Cambio |
|---|---|
| `backend/app/nucleo/servicio_pod.py:58` | `MAX_FOTOS = 10` (comentario SEC-023) |
| `backend/app/nucleo/servicio_pod.py:113-130` | `ServicioPOD._validar_cantidad_fotos(cantidad, existentes=0)`: límite por envío y límite acumulado del POD |
| `backend/app/nucleo/servicio_pod.py:223` | `crear()` valida `len(fotos)` antes de validar firma/subir nada |
| `backend/app/nucleo/servicio_pod.py:344` | `actualizar()` valida `len(fotos_nuevas) + len(pod.fotos) <= MAX_FOTOS` antes de subir archivos |
| `backend/app/nucleo/api_pod.py:17` | Importa `MAX_FOTOS` del servicio (una sola fuente de verdad) |
| `backend/app/nucleo/api_pod.py:30-41` | `_validar_cantidad_fotos(fotos)` del router: corta por **cantidad** antes de `leer_archivo_acotado` |
| `backend/app/nucleo/api_pod.py:83` (POST) y `:135` (PUT) | Primera sentencia del handler: valida cantidad → 422 de dominio |
| `backend/app/services/kpi_engine.py:109,129` | Tipos de `evaluar_formula`/`_evaluar` aceptan `Decimal` (ya usaban `_a_numero`) |
| `backend/app/services/kpi_engine.py:307,441-462` | `metricas_global` devuelve `Decimal` (ya calculaba en Decimal; se elimina el `float()` del valor de dominio) |
| `backend/app/services/kpi_engine.py:494-537` | `metricas_viaje` en `Decimal`; ya no hace `float(viaje.valor_flete_neto)` ni `flete * float(porcentaje)` |
| `backend/app/services/kpi_engine.py:540-547` | `metricas_para_json()`: único borde `Decimal → float` |
| `backend/app/api/routes/kpis.py:126` | `preview` serializa `metricas` con `metricas_para_json` (evaluar_formula recibe `Decimal`) |
| `backend/app/api/routes/viajes.py:307,346` | `rentabilidad` y `preview-rentabilidad`: `detalle` con `metricas_para_json` |

---

## 3. SEC-023 — tope de fotos del POD

### Regla
`MAX_FOTOS = 10` fotos **por envío** (el número recomendado por el hallazgo; el
frontend no define otro: `pod-panel.tsx:151-153` itera `archivos` sin tope, así
que 10 es la cota nueva y el frontend debe reflejarla). Además, el POD completo
queda acotado a 10 fotos: `actualizar()` solo **agrega** fotos, y sin tope
acumulado un conductor podía eludir el límite con N PUT de 10 fotos cada uno.

### Dónde se impone
1. **Router** (`api_pod.py:83,135`): primer statement del handler, antes de
   `leer_archivo_acotado` de la firma y de las fotos. Es lo que evita la
   materialización en RAM (10 fotos × 10 MB = 100 MB por request en lugar de
   ~1 GB con 100 fotos).
2. **Servicio** (`servicio_pod.py:223,344`): regla de dominio reutilizable,
   cubre también llamadas directas al servicio (`test_nucleo_pod.py` lo hace) y
   el acumulado del POD.

### Contrato de error
`HTTP 422` · `codigo: "DATOS_INVALIDOS"` · mensaje
`"El POD admite como máximo 10 fotos por envío; se recibieron 11."`
(acumulado: `"El POD ya tiene 10 fotos y el máximo es 10; no se pueden agregar más."`).
No se crea POD parcial ni se sube ningún archivo cuando se rechaza (verificado:
`count(nucleo.pod)=0` tras el 422).

### Residual aceptado 🟡
El tope de bytes agregados queda en `10 × 10 MB = 100 MB` por request. No se
inventó un tope de bytes distinto de `MAX_BYTES` porque no hay regla de negocio
que lo fije; la cota de transporte es SEC-021 (§4).

---

## 4. SEC-021 — multipart sin tope de transporte (reportado, no implementado)

### Confirmación del orden (🟢 código instalado)
- `fastapi==0.115.12` (`backend/requirements.txt:1`), `starlette==0.46.2`.
- `.venv/lib/python3.13/site-packages/fastapi/routing.py:247` → `body = await request.form()`
  ocurre **antes** de `solve_dependencies` (`:291`). Por lo tanto las
  dependencias de auth/permiso (`get_contexto_empresa`, `requiere_permiso`) se
  resuelven **después** de consumir y parsear todo el cuerpo.
- `starlette/formparsers.py:135,208`: los `UploadFile` van a
  `SpooledTemporaryFile(max_size=1 MB)` (disco), con `max_files=1000`. El
  `max_part_size=1 MB` (`:137,160-163`) solo aplica a campos de texto, **no** a
  archivos.
- Endpoints afectados además del POD: `api_maestros.py:220` (`subir_documento`,
  `File(...)`), y los uploads de `api_expediente.py`, `api_gastos.py`,
  `api/export.py`.
- No hay límite de cuerpo en el repo ni en el arranque
  (`Makefile:51` usa `uvicorn` sin opción de tamaño; grep de
  `client_max_body_size|limit-max-request` → 0 coincidencias).

### Consecuencia
Un POST **sin token** a cualquier endpoint `File(...)` se bufferiza completo
(hasta 1000 × 10 MB ≈ 10 GB de disco temporal) antes de recibir 401/403.

### Diseño propuesto (requiere `backend/app/main.py`; NO aplicado)
1. Middleware ASGI `LimiteCuerpo(max_bytes)` registrado antes de `include_router`:
   - `content-length` declarado > cota → **413** sin leer el cuerpo;
   - `transfer-encoding: chunked` o sin `content-length` en POST/PUT/PATCH →
     envolver `receive` y contar bytes reales, abortando al superar la cota.
2. Cota global conservadora (p. ej. 25 MB) y cota explícita mayor **solo** para
   las rutas de upload del núcleo (POD: `MAX_FOTOS*MAX_BYTES + MAX_FIRMA_BYTES + 1 MB`).
3. Código de dominio estable `CUERPO_EXCESIVO` (413) + prueba: POST sin
   `Authorization` con `Content-Length` sobre la cota → 413 y sin archivo temporal.
4. En producción, además `client_max_body_size` en el proxy.

**Por qué no se implementó:** exige editar `backend/app/main.py` (fuera de los
archivos autorizados). Un control por router (clase `APIRoute` custom) cubriría
solo 2 de 5 routers de upload = arreglo a medias, y una dependencia `Depends`
corre **después** de `request.form()`, así que no sería un límite temprano real.

---

## 5. F-04 — precisión decimal en KPIs

### Causa
`metricas_viaje` (`kpi_engine.py:503-520` antes del cambio) hacía
`float(valor_flete_neto)` y luego `flete * float(porcentaje)`: el margen y la
comisión arrastraban error binario. `metricas_global` (`:442-458`) convertía a
`float` al construir el dict de dominio, que además alimenta `evaluar_formula`.

### Cambio
- Cálculo íntegro en `Decimal` (`_dec` normaliza floats de entrada por su
  representación decimal: `Decimal(str(0.1)) == Decimal("0.1")`).
- `evaluar_formula` **sigue devolviendo `float`**: es un motor numérico de
  fórmulas, no una fuente de dinero; `_a_numero` convierte en el punto de
  evaluación (comportamiento previo, sin cambio de contrato).
- `metricas_para_json` es el **único** punto `Decimal → float`, justificado
  porque el contrato del frontend (`frontend/src/types/nucleo.ts`) y el JSON
  existente usan `number`; se documenta en el docstring que no debe usarse para
  volver a calcular.

### Evidencia de la regla
`0.30 − 0.10 − 0.3×0.10`:
- antes: `0.16999999999999998` (float);
- ahora: `Decimal("0.17")` exacto, y el test compara contra
  `Decimal(str(0.3 - 0.1 - 0.3 * 0.1))` para fallar si alguien reintroduce float.

---

## 6. Pruebas (comandos y salidas reales)

```
$ make unit
52 passed, 1 warning in 0.05s

$ cd backend && NUCLEO_TEST_DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:54322/tei_test" \
    ../.venv/bin/python -m pytest tests/test_kpi_engine.py tests/test_f1_ola3_recursos_decimal.py
15 passed, 2 warnings in 0.49s

$ make test          # tei_test recién refrescada con make test-db
203 passed, 2 warnings in 4.91s
```

Pruebas nuevas:

| Prueba | Archivo:línea | Qué fija |
|---|---|---|
| `test_limite_fotos_por_envio` | `test_f1_ola3_recursos_decimal.py:67` | 10 acepta; 11 → `DatosInvalidos` 422 con código `DATOS_INVALIDOS` |
| `test_limite_fotos_acumuladas_del_pod` | `:76` | POD lleno no admite más; reemplazo dentro del tope sí |
| `test_pod_11_fotos_422` | `:214` | HTTP 11 fotos → 422, sin POD persistido |
| `test_pod_10_fotos_acepta` | `:234` | HTTP 10 fotos → 201 con 10 fotos |
| `test_metricas_viaje_no_pierde_centavos` | `test_kpi_engine.py:113` | Todo el dict es `Decimal`; margen `0.17` exacto |
| `test_metricas_para_json_convierte_solo_en_el_borde` | `test_kpi_engine.py:136` | El borde JSON devuelve `float` (`number`) |

**Sanidad por mutación (SEC-023)**: se retiraron temporalmente las dos llamadas
de validación en una copia local; `test_pod_11_fotos_422` **FAILED**. Restaurado
y verificado por `shasum` (`7d76755…`, `e1d1250…`) y suite verde de nuevo.

---

## 7. Verificado 🟢 / Inferido 🟡 / No verificado 🔴

🟢 `MAX_FOTOS` corta antes de leer bytes (orden del handler, línea 83/135);
la prueba HTTP 11 fotos responde 422 sin fila en `nucleo.pod`.
🟢 El servicio revalida el acumulado (prueba unitaria + `actualizar():344`).
🟢 `metricas_viaje` no usa `float` en el cálculo (inspección + prueba de centavos).
🟢 `form()` precede a `solve_dependencies` (fuente de FastAPI instalada, líneas citadas).
🟢 Suite completa verde: 203 passed / 0 skipped.

🟡 El frontend (`pod-panel.tsx`) no limita la cantidad de fotos: al elegir 11
recibirá 422 y el mensaje del backend. Requiere ajuste de UI (§8).
🟡 Valores no monetarios de `metricas_global` (conteos) pasaron de `float` a
`Decimal`: el JSON sigue siendo `number` y `evaluar_formula` los convierte; no
se encontró otro consumidor (grep de `metricas_global|metricas_viaje`).

🔴 No se probó la degradación real de memoria del worker (no se envió 1 GB).
🔴 No se probó SEC-021 con un POST grande sin token: la evidencia es de código
(FastAPI/Starlette instalados), no de ejecución HTTP.

---

## 8. Compatibilidad y handoff

- **Frontend**: mostrar/limitar a 10 fotos (`pod-panel.tsx:151`) y deshabilitar
  "agregar" cuando el POD ya tenga 10; mostrar el `mensaje` del 422. El JSON de
  KPIs no cambia de forma ni de tipo.
- **QA**: agregar `tests/test_kpi_engine.py` y
  `tests/test_f1_ola3_recursos_decimal.py` al target `make unit` (el `Makefile`
  lista archivos explícitos; hoy esas 6 pruebas nuevas solo corren en
  `make test`). No se editó el `Makefile` (fuera de alcance).
- **auditor-seguridad**: revisar SEC-021 con el diseño de §4 (decisión de
  incluir `app/main.py` y el código 413) y el residual de 100 MB por request del
  POD.

## 9. Riesgos y pendientes

1. **SEC-021 abierto** hasta que se autorice el middleware en `app/main.py`.
2. **Flake pre-existente detectado (no corregido, fuera de alcance):**
   `test_nucleo_conductor.py:148` y `test_f1_ola2_adversarial.py:149` crean
   `Empresa.rut` con texto (`"CON-<hex>"`, `"POD-<hex>"`); el índice
   `uq_empresas_rut_norm` normaliza a solo los dígitos del hex (3-6 dígitos) y
   colisiona entre corridas sobre la misma `tei_test`. Evidencia: una corrida
   `make test` falló con
   `UniqueViolation ... uq_empresas_rut_norm ... Key (...)=(654)`, y otra con
   `test_conductor_mi_viaje_y_transiciones` en verde aislado. Remedio para `qa`:
   usar RUT numérico único (`str(uuid4().int)[:12]`), como hace el nuevo archivo.
   La suite no es estable entre corridas sobre una `tei_test` acumulada; para una
   corrida de aceptación conviene `make test-db` (refresca solo `tei_test`).
3. El límite acumulado de 10 fotos es una decisión de dominio derivada del
   hallazgo (no de una regla `R-0XX`); si el negocio necesita más, se ajusta
   `MAX_FOTOS` en un solo lugar (`servicio_pod.py:58`).
4. **No hay garantía en la base para el conteo de fotos.** `nucleo.pod.fotos` es
   `jsonb`; un `CHECK (jsonb_array_length(fotos) <= 10)` cerraría el control
   incluso ante escrituras fuera del servicio, pero exige migración (fuera de
   alcance y no autorizada). Queda como propuesta para `datos`.

## 10. Rollback

Revertir los 6 archivos de §2 a su estado anterior. Sin migraciones ni cambios
de esquema. Las fotos ya subidas a Storage y los POD existentes no se ven
afectados; `MAX_FOTOS` solo aplica a envíos nuevos.
