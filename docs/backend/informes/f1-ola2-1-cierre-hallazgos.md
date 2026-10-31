# Fase 1, Ola 2.1 — Cierre de hallazgos de la revisión independiente

> Depositado por el orquestador (2026-10-30): el agente `backend` agotó pasos antes de escribir el archivo; contenido íntegro de su respuesta + verificaciones del orquestador. Riesgo: Medio-Alto → revalidación de `auditor-seguridad` pendiente.

Fecha: 2026-10-30 · Agente: backend · Estado: implementado; verificado por el orquestador (números reales abajo)

## Cambios (archivo:línea)

| Archivo | Cambio |
|---|---|
| `backend/app/nucleo/storage.py` | `_FIRMA_PDF = b"%PDF-"` + `%%EOF` obligatorio en los últimos `VENTANA_FIN_PDF=2048` bytes (`firma_pdf_valida`); `detectar_content_type` usa la firma reforzada; nuevos `CONTENT_TYPES_IMAGEN`, `EXTENSIONES_IMAGEN`, `es_imagen`, `detectar_content_type_imagen`, `validar_imagen` (ext, CT), `leer_archivo_acotado_sync` |
| `backend/app/nucleo/api_expediente.py` | `read()` sin cota → `leer_archivo_acotado`; CT del cliente → `detectar_content_type(contenido)`; 422 si `None` |
| `backend/app/nucleo/api_gastos.py` | Ídem para el comprobante de gasto |
| `backend/app/nucleo/api_pod.py` | Firma: `detectar_content_type_imagen` (solo imagen) en POST y PUT; CT de fotos detectado |
| `backend/app/nucleo/servicio_pod.py` | `_validar_firma` devuelve `(ext, content_type)` vía `validar_imagen` (SOLO imagen, 5 MB, PNG/JPG/JPEG/WEBP); el CT de firma y fotos ya no viene del cliente |
| `backend/app/nucleo/servicio_maestros.py` | `subir_documento` devuelve `(doc, creado: bool)`; `_bloquear_recurso` (`SELECT … FOR UPDATE` sobre la fila del recurso) + `_documento_identico` (empresa+recurso+tipo+numero+entidad+emitido+vence+hash+vigente) |
| `backend/app/nucleo/api_maestros.py` | `Response` inyectado: reenvío idéntico → **200**; creación → 201 |
| `backend/app/nucleo/errores.py` | 23514: mensaje de dominio fijo; sin `message_primary` al cliente; status 409 intacto |
| `backend/app/nucleo/servicio_cutover.py` | `congelar`/`descongelar` verifican `rowcount == 1`; si no, `rollback` + `ErrorPersistencia` |
| `backend/app/api/routes/export.py` | `await archivo.read()` → `leer_archivo_acotado` (2 sitios) |
| `backend/app/api/routes/gastos.py` | `archivo.file.read()` → `leer_archivo_acotado_sync` |
| `backend/tests/test_f1_ola2_adversarial.py` | Fixtures PDF con `%%EOF`; 10 MiB y 10.000.000 B exactos con helper `_pdf_de_tamano`; doble envío espera `[200,201]` + 1 fila por hash; firma PDF `.jpg` → 422 |
| `backend/tests/test_seguridad_ola2.py` | PDF con `%PDF-`…`%%EOF`; nuevas pruebas: sin `%%EOF` rechazado, marca fuera de ventana, `validar_imagen`, lectura acotada exacta/±1 y sync, 23514 sin texto de PG |
| `backend/tests/test_f1_ola2_1_cierre.py` (nuevo) | SEC-016 (rowcount 0/1), firma POD solo-imagen, idempotencia 201→200 + 1 fila, renovación con otra vigencia crea registro, CT servido `application/pdf` con cliente `text/html`; SEC-018/019 a nivel endpoint |
| `backend/.env.example` | SEC-020: `DEBUG=false` + comentario (aplicado por el orquestador; el subagente no tenía permiso de edición) |

## Causa raíz del fallo "10 MB exactos" (Fallo #7)

🟢 **El test estaba mal, no el código:** `test_f1_ola2_adversarial.py:362` construía `b"%PDF-1.4\n"` (9 B) + `b"x" * (_10MB - 8)` = **10 MiB + 1 byte** y esperaba 201. El servidor aplicó correctamente el borde cerrado (`> MAX_BYTES`). Se corrigió el test con un helper de tamaño exacto y se agregó el caso 10.000.000 B (criterio del dueño; 10.000.000 < 10 MiB).

## Decisión de idempotencia: 200 (no 409)

Reenvío idéntico (doble clic/reintento) no es conflicto: devuelve el mismo recurso con la misma identidad. 201 reservado a creación real. Determinismo sin migración: `SELECT … FOR UPDATE` sobre la fila del recurso serializa dos POST concurrentes; el segundo re-consulta tras el lock y ve el commit del primero.

## Verificación del orquestador (2026-10-30, salidas reales)

| Comando | Resultado |
|---|---|
| `pytest tests/test_f1_ola2_adversarial.py -q` | **33 passed** |
| `pytest tests/test_f1_ola2_1_cierre.py -q` | **18 passed** |
| `pytest tests/test_seguridad_ola2.py -q` | **44 passed** |
| `make unit` | **52 passed** |
| `make test` (tei_test) | **197 passed** (una corrida previa: 196 passed + 1 error transitorio del stack; no reproducido) |

## Pendiente / no verificado 🔴

1. **Revalidación independiente de SEC-018/019** por `auditor-seguridad` (en curso).
2. **Flakiness preexistente de RUT**: colisiones en empresas pre-sembradas (`MAE-…`/`QA-…` normalizadas a dígitos) hacen fallar esporádicamente `test_nucleo_maestros.py`/`test_reglas_negocio.py`; fuera del alcance de esta ola → asignar a `qa` (estabilizar con RUT único por corrida).
3. **1 error transitorio** en una corrida de `make test` (196+1) no reproducido en la siguiente (197); vigilar con 3 corridas limpias.
4. Test "PDF políglota aceptado" sigue afirmando 201: con la firma reforzada el políglota **válido** (con `%%EOF`) pasa; un `%PDF` sin `%%EOF` ahora se rechaza.
5. No hay `ruff` configurado en `backend/` (lint no ejecutado).

## Rollback

Revertir los archivos de la tabla; sin migraciones ni cambios de esquema. Cambios de contrato: `POST /nucleo/documentos` (200 vs 201 en reenvío idéntico) y firma POD (PDF renombrado → 422).
