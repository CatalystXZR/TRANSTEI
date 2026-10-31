# Fase 1, Ola 2 — Cierre de defectos de seguridad/higiene (backend)

> Depositado por el orquestador (2026-10-29): el agente `backend` agotó pasos antes de escribir el archivo; contenido íntegro de su respuesta. Verificaciones independientes del orquestador: F-01 fail-closed (`servicio_cutover.py:46-60`) y mapeo SQLSTATE (`main.py:84-111`) confirmados por lectura directa.

Fecha: 2026-10-29 · Agente: backend · Riesgo: ALTO · Estado: implementado, pendiente revalidación independiente (qa / auditor-seguridad)

## 1. Cambios (archivo:línea)

| Defecto | Archivo:línea | Cambio |
|---|---|---|
| F-01 | `backend/app/nucleo/servicio_cutover.py:28-57` | `legacy_congelado()` fail-closed: excepción de lectura → `logger.exception` + `True`; fila ausente → `logger.warning` + `True`. Decisión documentada en docstring (RA-04). Caché TTL 5 s sin tocar. |
| F-08#2 | `backend/app/nucleo/servicio_cutover.py:94-100` | `legacy_abiertos=0` ahora loguea `logger.warning(exc_info=True)`; retorno conservado. |
| F-03 | `backend/app/main.py:8-12,69-111` | Handler global `manejador_integrity_error` por sqlstate: 23505/23P01→409 (código+mensaje de dominio vía `traducir_integrity_error`), 23514/23502/23503→422 genérico, resto→500 genérico con log; nunca mensaje crudo de PG. |
| F-03b | `backend/app/nucleo/servicio_facturacion.py:708-719` | `crear_promesa` envuelve add+commit en try/except con rollback y `traducir_integrity_error` (patrón :612,645,685). |
| F-05 | `backend/app/core/config.py:11` | `DEBUG: bool = False` (default seguro). |
| F-08#1 | `backend/app/api/routes/kpis.py:13,66-71` | `metricas={}` ahora loguea; comportamiento visible sin cambios. |
| F-08#3 | `backend/app/core/settings_db.py:1-4,21-25` | `get_config_decimal` loguea fallo de parseo y devuelve default. |
| F0-05 | `backend/app/nucleo/storage.py:24-104` | `firma_valida` (PDF/JPEG/PNG/WEBP/HEIC), `content_type_para`, `detectar_content_type`, `leer_archivo_acotado` (trozos, cota); `validar_archivo:107-127` exige firma. |
| F0-05 | `backend/app/nucleo/api_pod.py:15-21,64-90,113-146` | Lectura acotada (firma 5 MB, fotos 10 MB); content-type por detección, rechazo 422 si no detiene. |
| F0-05 | `backend/app/nucleo/api_maestros.py:36,231-244` | Lectura acotada; no pasa content-type del cliente. |
| F0-05 | `backend/app/nucleo/servicio_maestros.py:412-447` | Valida firma y sube con `content_type_para(ext)`. |

## 2. Contrato

- `POST/PUT /api/v1/nucleo/expediente/viajes/{viaje_id}/pod`: multipart; la firma exige firma PNG/JPEG/WEBP y ≤5 MB; fotos ≤10 MB y firma de la whitelist (PDF/JPG/JPEG/PNG/WEBP/HEIC). Content-type declarado por el cliente **ignorado**; el servidor lo detecta. Rechazo: 422 `DATOS_INVALIDOS`.
- `POST /api/v1/nucleo/documentos`: ídem, ≤10 MB; 422 si la firma no corresponde a la extensión.
- IntegrityError no traducido por servicio: 409/422/500 según sqlstate (antes 400 genérico). Body `{codigo, detail}` (compatibilidad con formato legacy).
- `legacy_congelado()` consultado por el middleware (sin cambio de contrato HTTP); ahora bloquea escrituras legacy ante fallo de lectura (409 `CUTOVER_LEGACY_CONGELADO`).

## 3. Autorización
Sin cambios de permisos. Endpoints tocados ya declaran `requiere_permiso("pod:escribir")` / `"maestros:escribir"` (`api_pod.py:28-33`, `api_maestros.py:48-52`).

## 4. Transacción e idempotencia
`crear_promesa` ahora hace rollback ante IntegrityError y propaga error de dominio (sin commit parcial; la sesión queda usable). La idempotencia de promesas no cambia (no hay clave natural; fuera de alcance).

## 5. Pruebas nuevas
- `backend/tests/test_seguridad_ola2.py` — 37 unitarias: F-01 (error de lectura / fila ausente / caché), F-03 handler por sqlstate (parametrizado 23505/23P01/23514/23502/23503/40001/desconocido/None), F-08 (settings_db, kpi valores), F0-05 (firmas válidas/inválidas, PDF con bytes extra, content-types canónicos, lectura acotada).
- `backend/tests/test_upload_invalido_http.py` — 1 HTTP: upload de documento .pdf con bytes inválidos → 422 `DATOS_INVALIDOS` (override de `get_contexto_empresa`, sin tocar Storage).
- `backend/tests/test_nucleo_facturacion.py::test_crear_promesa_rechazo_db_traducido_409` — integración: defensa de BD (ck `monto > 0`, 23514) → `ReglaNegocioViolada` 409 + rollback probado con promesa posterior válida.
- `backend/tests/test_flujos_criticos.py:100` — ajuste legítimo: RUT duplicado legacy espera 409 (antes 400) según AGENTS.md §8.

## 6. Salidas reales
- `../.venv/bin/python -m pytest tests/test_seguridad_ola2.py`: `37 passed, 1 warning in 0.02s`
- `make unit`: `52 passed`
- `make test` (tei_test + TEST_* creds): `139 passed` ×3 (una ejecución previa arrojó 1 fallo transitorio en `test_upload_invalido_http.py` que no se reprodujo en las 3 ejecuciones posteriores ni en pytest directo).
- Sanidad F-01 (mutación temporal → `congelado=False` en ambas ramas): `2 failed` con el mecanismo retirado; restaurado → `37 passed`.

## 7. Compatibilidad
- La respuesta 409 en duplicados legacy cambió de 400: revisar clientes frontend que lean códigos legacy de duplicados (`frontend/src/lib/api.ts`).
- Archivos con extensión válida pero contenido falso ahora se rechazan en todos los flujos que usan `validar_archivo` (expediente, gastos, POD fotos, maestros); es el comportamiento pretendido.
- `make test` sin credenciales Supabase sigue omitiendo 8 tests (condicional previo, no es un skip nuevo oculto).

## 8. Riesgos residuales
- 🔴 Fallo transitorio no reproducido del test HTTP de upload (pendiente de confirmación por qa, recomendado aislar runner).
- 🔴 `subir_archivo()` recibe `content_type` aún desde otros servicios (`servicio_pod`, `servicio_expediente`, `servicio_gastos`); en POD ya viene detectado por la API; expediente/gastos siguen por API — verificar su capa HTTP en otra ola.
- 🟡 Ruff: persisten violaciones `B008/BLE001` *preexistentes* del patrón del proyecto; no introduje clases nuevas (LOG014/F401 corregidos).
- PEP8: `Configuracion` importado pero no referido en `settings_db.py` es preexistente; no se tocó para no alterar el runtime de la instancia global.

## 9. Handoff
- **qa**: adversariales sobre uploads (firma manipulada en los 3 puntos de entrada, archivos >10 MB, firma POD >5 MB, content-type falso del cliente) y confirmación del fallo transitorio.
- **auditor-seguridad**: revalidación independiente del handler global, fail-closed del cutover y fijación de content-type.
