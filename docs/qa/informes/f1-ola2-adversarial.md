# F1 Ola 2 — Pruebas adversariales (2026-10-29/30)

> Depositado por el orquestador: el agente `qa` agotó pasos antes de escribir el archivo y de correr la última pasada; contenido íntegro de su respuesta + **Anexo A (verificación del orquestador, 2026-10-30)** con los resultados reales de la re-ejecución.

## Entorno
🟢 backend:8000 UP · 🟢 frontend:3000 UP · 🟢 Supabase local 54322 UP · tei_test disponible
🟢 Línea base: make test → 139 passed (3.13s)
🟡 Estado del artefacto: tests creados; última corrida completa NO ejecutada por el subagente (límite de pasos) → completada por el orquestador (Anexo A).

## Casos

| # | Escenario | Esperado | Veredicto (Anexo A) |
|---|---|---|---|
| A1-A9 | Firma manipulada doc (JPEG como .pdf, PNG como .jpg, texto, whitespace, vacío, .exe, sin ext) | 422 DATOS_INVALIDOS | ver Anexo A |
| A10 | PDF+bytes extra, CT cliente text/html | 201 + CT application/pdf | ver Anexo A |
| A11 | Ext MAYÚSCULAS | 201 (lower) | ver Anexo A |
| A12 | Políglota PDF+HTML | 201 + CT pdf | ver Anexo A |
| A13-A14 | 10MB exacto / +1B | 201 / 422 | ver Anexo A |
| A15 | Doble envío concurrente | 201,201 | ver Anexo A |
| A16-A21 | POD firma/fotos manipuladas, 5MB+1, 10MB+1 | según caso | ver Anexo A |
| A22 | POD doble envío concurrente | 201+409, 1 fila | ver Anexo A |
| B1-B2 | legacy_congelado fila false/true | False/True | ver Anexo A |
| B3 | Middleware congelado (sin token) | 409 CUTOVER | ver Anexo A |
| B4 | Middleware congelado (admin real) | 409 CUTOVER | ver Anexo A |
| B5 | Mutación: legacy_congelado=False fijo (sanidad) | sin 409 | ver Anexo A |
| C1 | 23505 RUT chofer duplicado | 409 REGISTRO_DUPLICADO | ver Anexo A |
| C2 | 23514 gasto negativo | 422 DATOS_INVALIDOS | ver Anexo A |
| C3 | Liquidación concurrente (unicidad chofer+mes) | 1 fila | ver Anexo A |
| C4 | Promesa monto 0 / 1 | 422 / 200 | ver Anexo A |
| D | test_upload_invalido_http.py ×10 | todos passed | ver Anexo A |

## Hallazgos (del subagente qa)

1. **MEDIA** — la validación de firma de POD no exige "imagen": PDF renombrado `.jpg` aceptado como firma; path/.ext incoherente (`storage.py:67-83` detecta PDF/HEIC; `servicio_pod.py:91-99` solo mira nombre; `api_pod.py:65-69`). Sugerido: restringir EXTENSIONES_FIRMA + usar `firma_valida` en el servicio.
2. **BAJA** — fotos del POD aceptan PDF/HEIC (`ALLOWED_EXTENSIONS` incluye .pdf/.heic).
3. **MEDIA-BAJA** — `nucleo.documentos` sin unicidad/idempotencia; doble envío crea 2 filas.
4. **BAJA** — magic bytes no detectan HTML embebido tras `%PDF` (deuda documentada).
5. **Positivo** — triggers append-only `fn_documento_no_borrar` / `fn_pod_no_borrar` bloquean DELETE (verificado con CheckViolation capturada).
6. **Positivo** — DEBUG=False por defecto (`config.py:11`).
7. Ruta corregida en test: promesas viven en `/nucleo/cobranza`.

## No verificado por el subagente
- Suite adversarial completa verde (última corrida pendiente) → completada en Anexo A.
- D (×10 flaky del upload) no corrido → completado en Anexo A.
- Algunos asserts finales de B/C pendientes → completados en Anexo A.

## Próximo paso (del subagente)
Re-ejecutar `test_f1_ola2_adversarial.py` + `make test`; correr D ×10.

---

## Anexo A — Verificación del orquestador (2026-10-30)

Ejecutado por el orquestador con shell real (el subagente qa no alcanzó la última pasada).

| Verificación | Comando | Resultado |
|---|---|---|
| Suite adversarial completa (tras Ola 2.1) | `pytest tests/test_f1_ola2_adversarial.py -q` | **33 passed** 🟢 |
| Cierre Ola 2.1 | `pytest tests/test_f1_ola2_1_cierre.py -q` | **18 passed** 🟢 |
| Seguridad Ola 2 | `pytest tests/test_seguridad_ola2.py -q` | **44 passed** 🟢 |
| Regresión unitaria | `make unit` | **52 passed** 🟢 |
| Regresión completa | `make test` (tei_test) | **197 passed** 🟢 (1 corrida previa: 196+1 error transitorio, no reproducido) |
| D — flaky upload ×10 | `pytest tests/test_upload_invalido_http.py` ×10 | **10/10 passed** 🟢 (el fallo transitorio no reapareció) |

**Estado de los hallazgos de este informe:**
1. Firma POD acepta PDF renombrado → **CORREGIDO** en Ola 2.1 (solo imagen; PDF `.jpg` → 422; `test_f1_ola2_1_cierre.py`).
2. Fotos POD aceptan PDF/HEIC → **CORREGIDO** (whitelist de imágenes).
3. Doble envío sin unicidad en `nucleo.documentos` → **CORREGIDO** (idempotencia 200 con `SELECT … FOR UPDATE` + hash; 1 fila bajo concurrencia).
4. Políglota PDF+HTML → **reforzado** (`%PDF-` + `%%EOF` en ventana final); políglota válido sigue pasando (deuda documentada).
5. Fallo "10 MB exactos" → **causa raíz: test construía 10 MiB + 1 B**; corregido con helper de tamaño exacto.
6. Positivos (triggers append-only, DEBUG=false) → confirmados.

**Pendiente:** revalidación de `auditor-seguridad` sobre SEC-018/019 (Ola 2.1) y estabilización de flakiness de RUT (fuera de esta ola).
