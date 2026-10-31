# O2.2 — Buzón de solicitudes

> Fecha: 2026-10-31 · Agente: `orquestador` · Contrato: §6.1–§6.7
> Riesgo: **Alto** (aprobación con efecto real sobre datos, concurrencia, tenant)
> Estado: implementado y probado contra `tei_test`; **revisión independiente pendiente**.

## 1. Qué se implementó

| Archivo | Contenido |
|---|---|
| `backend/app/nucleo/agente/solicitudes.py` | servicio: `listar`, `obtener`, `decidir`; ejecutores por tipo; `diff` derivado |
| `backend/app/nucleo/agente/api_solicitudes.py` | `GET /solicitudes`, `GET /solicitudes/{id}`, `POST /solicitudes/{id}/decidir` |
| `backend/app/nucleo/errores.py` | `SolicitudYaDecidida` (409), `Autoaprobacion` (403), `TipoSinEjecutor` (501) |
| `backend/app/api/router.py` | inclusión del router |

## 2. Garantías y cómo se probaron

`backend/tests/test_agente_o2_2_buzon.py` — **14 passed**, con escritura como
`tei_app` y RLS activa.

| Garantía | Prueba |
|---|---|
| Una empresa no ve solicitudes de otra | `test_detalle_de_otra_empresa_es_404` (404, no 403: no se filtra existencia) |
| El listado solo trae su empresa | `test_listar_solo_devuelve_la_empresa` |
| Por defecto solo pendientes | `test_listar_por_defecto_solo_pendientes` |
| Rechazar deja estado, motivo, actor y versión | `test_rechazar_deja_estado_motivo_y_hoja_ruta` |
| Rechazar una hoja de ruta la deja `rechazado` | ídem |
| Modificar deja `pendiente` y calcula `diff` | `test_modificar_deja_pendiente_con_diff` |
| **El `payload` propuesto no se reescribe** | `test_confirmar_hoja_de_ruta_no_reescribe_el_payload` (ADR-0003 §14.2) |
| `confirmar` sin ejecutor devuelve 501 **y no aprueba** | `test_confirmar_tipo_sin_ejecutor_es_501` |
| Versión incorrecta → 409 | `test_version_incorrecta_es_409` |
| Segunda decisión → 409 | `test_ya_decidida_es_409` |
| Rechazar sin motivo → 422 | `test_rechazar_sin_motivo_es_422` |
| Autoaprobación → 403 | `test_autoaprobacion_es_403` |
| Otro aprobador sí puede | `test_otro_aprobador_si_puede` |
| **Dos aprobadores simultáneos: un solo efecto** | `test_dos_aprobadores_solo_uno_aplica` — **dos conexiones reales**: A toma el lock y retiene el `commit`; B queda bloqueado en `FOR UPDATE`; al reanudar ve el estado terminal. Se verifica `version=2`, no 3 |
| Permisos del buzón | `test_permisos_del_buzon_solo_para_admin` (unit) |

### 2.1 Capa HTTP con JWT real (`test_agente_o2_2_http.py`, 15 pruebas)

Lo que el servicio no puede probar: la resolución de membresía y la autoridad de
permisos del backend.

| Garantía | Prueba |
|---|---|
| Listado con JWT de Supabase Auth y `X-Empresa-ID` | `test_listar_con_jwt_real` |
| Sin token → 401/403 | `test_sin_token_es_401_o_403` |
| Sin `X-Empresa-ID` → 422 | `test_sin_empresa_es_422` |
| Rol sin `agente:buzon` (contabilidad) → 403 `ACCESO_DENEGADO` | `test_rol_sin_permiso_no_lee_el_buzon` |
| JWT válido pero sin membresía en esa empresa → 403 | `test_empresa_ajena_no_es_miembro` |
| Id de otra empresa con membresía correcta → 404 | `test_detalle_de_otra_empresa_es_404` |
| Rol sin `agente:aprobar` no decide → 403 | `test_decidir_sin_permiso_es_403` |
| `version` ausente → 422; acción desconocida → 422 | `test_body_incompleto_es_422`, `test_accion_desconocida_es_422` |
| Rechazo completo por HTTP | `test_rechazo_completo_por_http` |
| Reintento tras éxito → 409 `SOLICITUD_YA_DECIDIDA` | `test_reintento_tras_exito_es_409` |
| `version` vieja → 409 `CONFLICTO_CONCURRENCIA` | `test_version_vieja_es_409` |
| `confirmar` sin ejecutor → 501 y sin efecto | `test_confirmar_tipo_sin_ejecutor_es_501` |
| Autoaprobación → 403 `AUTOAPROBACION` | `test_autoaprobacion_es_403` |
| El detalle no expone teléfono, costos ni margen | `test_no_revela_datos_fuera_del_buzon` |

Hallazgo durante la escritura: la primera versión del fixture usaba al aprobador
como solicitante y **todas** las decisiones devolvían 403 `AUTOAPROBACION`. No era
un defecto del código: era la regla funcionando por HTTP. El fixture se corrigió
para usar un solicitante distinto.

## 3. Contradicción del contrato y cómo se resolvió

§6.6 dice que el ejecutor de `hoja_de_ruta` "lo implementa O2.5"; §6.7 afirma que
`confirmar` sobre `hoja_de_ruta` **funciona** con el módulo apagado porque escribe
tablas del módulo. Ambas no pueden ser ciertas a la vez en O2.2.

Se resolvió a favor de §6.7 y de la frase "es el único ejecutor que F2.1 puede
declarar completo porque vive en tablas del módulo": **se implementó el ejecutor
`hoja_de_ruta`** (`solicitud_creada → cargado` + `valores_cargados`), que no llama
a ningún servicio ajeno. Los otros tres tipos (`agendamiento`, `documentos`,
`otra`) devuelven 501, como manda §6.6.

Esto es un **adelanto parcial de O2.5**, deliberado y acotado. Si el dueño prefiere
501 puro, se retira en un solo cambio: `EJECUTORES_SOLICITUD` vuelve a `{}`.

## 4. Decisiones de implementación

1. **`commit()` en el endpoint, no en el servicio.** `decidir` compone efecto y
   estado; el endpoint hace un único `commit()` y `rollback()` ante cualquier
   excepción. Si el servicio confirmara por su cuenta (patrón del resto de
   servicios del núcleo), un fallo del segundo paso dejaría medio efecto.
2. **`solicitante.nombre` puede ser `null`** cuando solicita un usuario:
   `nucleo.usuarios_empresa` no tiene columna de nombre (solo `auth_id` y `rol`).
   Se devuelve `null` en vez de inventar un identificador. Es una desviación del
   ejemplo de §6.2 y queda anotada.
3. **`resumen` no aplica reglas de negocio**: cuenta campos del payload y, si el
   payload declara `faltantes`, cuántos son.
4. **`evidencia` se proyecta a `{tipo, ref}`**: cualquier clave extra del payload
   se descarta para no romper el contrato cerrado de respuesta.

## 5. Otros pendientes cerrados en esta pasada

- **SEC-038** (`main.py:262-266` registraba `repr(exc)`): ahora registra
  `sqlstate` + tipo. El `repr` de SQLAlchemy incluye sentencia y parámetros.
- **Timeout por tool** (era 🔴 en O2.1): dos pruebas nuevas en
  `test_agente_o2_1_integracion.py`: `pg_sleep` real bajo
  `statement_timeout=100ms` produce `57014` y `clasificar_error` lo mapea a
  `TIMEOUT_TOOL`; y `current_setting('statement_timeout')` confirma que el
  mecanismo que usa el registry queda en `1500ms`.

## 6. Verificación

```text
pytest tests/test_agente_o2_2_buzon.py        -> 14 passed
pytest tests/test_agente_o2_1_integracion.py  -> 19 passed
make unit                                     -> 125 passed
pytest tests/test_agente_o2_2_http.py          -> 15 passed (JWT real)
make test                                     -> 347 passed, 0 failed, 0 skipped
ruff (paquete + pruebas)                      -> solo B008 (patrón FastAPI del repo)
```

## 7. No verificado

- 🔴 **Revisión independiente** de O2.2 en curso (`auditor-seguridad`).
- 🔴 **Frontend del buzón** (O4.3): no existe.
- 🟡 `resumen` y `diff` solo se probaron con payloads planos (un nivel).

## 8. Rollback

Revertir `api/router.py` (2 líneas), borrar `solicitudes.py` y
`api_solicitudes.py`, y quitar las 3 clases de `errores.py`. Sin migraciones y sin
datos de negocio: las únicas filas creadas son de prueba en `tei_test`.
