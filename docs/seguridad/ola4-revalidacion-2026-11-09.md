# Revalidación independiente — correcciones Ola 4 (2026-11-09)

- **Fecha:** 2026-11-09
- **Autor:** `auditor-seguridad` (revalidación independiente; no implementa ni corrige)
- **Alcance:** las correcciones declaradas para SEC-063, SEC-064, SEC-065, SEC-066,
  SEC-068, SEC-069 y SEC-056 (`0033`), más el estado de SEC-053, SEC-054, SEC-057,
  SEC-067, SEC-070 y SEC-071.
- **Método:** lectura del código actual y `git diff` de los archivos modificados.
  El entorno permitió `git` (diff/status) pero **denegó `pytest`, `psql` y
  `docker`**: no ejecuté la suite ni consulté una base viva. El **"495 passed"** es
  dato del orquestador; **no lo heredo como prueba mía**. Todo lo marcado 🟡/🔴
  refleja esa limitación.
- **Documentos actualizados:** este archivo y la sección 9 de
  `docs/seguridad/hallazgos.md`. No se tocó `docs/qa/**` ni el informe de QA.

---

## 0. Veredicto corto

Las correcciones **están en el código** y, leídas línea a línea, cierran los
hallazgos tal como se declararon. No encontré una regresión funcional evidente en
el diff. Quedan tres clases de residuo:

1. **Sin prueba de regresión específica** para SEC-063 (opt-in del catálogo),
   SEC-064 (`modificar` en `tipo='otra'`) y SEC-065 (topes de tools). La suite
   puede estar verde sin cubrir esos vectores.
2. **SEC-066** se cierra en HTTP, pero `tei_app` conserva `EXECUTE` sobre
   `nucleo.admin_set_modulo_empresa` (`0029:270`); `0033` no lo revoca. Sin
   endpoint, solo un runtime comprometido/SQLi puede llamarla.
3. **SEC-056/068** dependen de que `0033` esté aplicada en `postgres` y `tei_test`;
   el DDL y las pruebas SQL existen, pero no pude ejecutar `psql` para confirmarlo.
   La matriz de QA (`docs/qa/matriz-trazabilidad.md` §19) sigue diciendo que el
   panel no está montado; es un artefacto desactualizado, no lo edité.

---

## 1. Estado por hallazgo

| ID | Estado tras la corrección | Evidencia principal | ¿Cierra? |
|---|---|---|---|
| SEC-056 | 🟢 **cerrado en código** (🟡 aplicación en BD no verificada) | `0033:54-60,63-83`; `supabase/tests/0033_01:24-89`; `scripts/test_db_reset.sh` re-aplica | Sí, para `tei_app`; `postgres` conserva privilegios (plataforma) |
| SEC-063 | 🟢 **cerrado en código** (🟡 sin test específico) | `capacidades.py:176-186`; `api/router.py:12-14,35`; `api_configuracion.py:145-152`; contrato actualizado | Sí: la capacidad nace `False`; el admin la habilita |
| SEC-064 | 🟢 **cerrado en código** (🟡 sin test específico) | `solicitudes.py:459-485` | Sí: merge `valores`/`valores_modificados` y revalidación |
| SEC-065 | 🟢 **cerrado en código** (🟡 sin test específico; residual de tamaño) | `runtime.py:566-606`; `config.py:47-48`; `chat/api.py:157-169` | Sí para cantidad; el tamaño de argumentos sigue sin tope |
| SEC-066 | 🟡 **cerrado en HTTP; residual DB** | `api_contactos.py:172-174`; `backend/tests/test_agente_enrolamiento_http.py:100-108`; `0029:270` | Sí en la superficie del tenant; `tei_app` conserva EXECUTE |
| SEC-067 | 🔴 **abierto** (decisión ADR-0003) | `0021:218-223`; `0029:105-160` | No; no se tocó |
| SEC-068 | 🟢 **cerrado en código** (🟡 aplicación en BD no verificada) | `0033:58-80`; `supabase/tests/0033_01:39-87` | Sí, para `tei_app` |
| SEC-069 | 🟢 **cerrado en código** (🟡 test no ejecutado) | `api/router.py:12-14,35`; `api_configuracion.py:145-152`; `test_ola4_chat_capacidades.py:328-340` | Sí: la ruta queda montada y `_agente_out` existe |
| SEC-070 | 🟢 **cerrado** | `scripts/seed_local.py:47-61` | Sí: la demo solo se usa contra local |
| SEC-071 | 🔴 **abierto** (negocio/legal) | `runtime.py:416-463`; `herramientas.py:781-1081`; `llm.py:78-93` | No; no se tocó |
| SEC-053 | 🟡 **parcial / abierto** | `chat/api.py:46-67,148-170`; `runtime.py:579-654` | No; no se tocó |
| SEC-054 | 🔴 **abierto** | sin middleware de rate limit; `config.py:48-50` | No; no se tocó |
| SEC-057(a) | 🔴 **abierto** | `0031:264-266`; `runtime.py:383-411,527-555` | No; no se tocó |
| SEC-061 | 🟢 **cerrado** | `solicitudes.py:508-521` | Sí (ya estaba) |
| SEC-062 | 🟢 **cerrado** | `chat/api.py:78-80`; `runtime.py:572-619` | Sí, con residual SEC-065 |

---

## 2. Verificación de cada corrección

### 2.1 SEC-069 — panel de configuración montado

- **Diff:** `backend/app/api/router.py` importa
  `app.nucleo.agente.chat.api_configuracion` y lo incluye como
  `nucleo_agente_configuracion_router` (`api/router.py:12-14,35`). El helper
  `_agente_out` se agregó en `api_configuracion.py:145-152` y valida el dict de
  `capacidades.configuracion_agente` contra `AgenteConfigOut`.
- **Ruta y permisos:** `api_configuracion.py:27-29` (prefijo
  `/nucleo/agente/configuracion`), `:77-134` (`GET`/`PUT`/`POST restablecer` con
  `agente:configurar`; solo `admin`).
- **Prueba existente:** `test_ola4_chat_capacidades.py:328-340` exige `GET` 200 y
  `agentes` en el JSON. Antes fallaba con 404; con el `include_router` actual el
  router existe y `_agente_out` está definido. **No la ejecuté** (pytest denegado):
  la conclusión es estática.
- **Riesgo de regresión:** ninguno evidente. El orden de inclusión (después de
  `nucleo_agente_chat_router`) no colisiona: `/nucleo/agente/configuracion` no cae
  bajo el prefijo `/nucleo/agente/chat`.
- **Nota de consistencia:** `docs/qa/matriz-trazabilidad.md` §19 todavía marca la
  fila del panel como "falla: QA-O4-01 (404)" y cita `api/router.py:26-43` como
  "falta". Es un artefacto de QA desactualizado; no lo edité por la restricción de
  alcance. El `docs/estado.md` §6.9 sí lo declara corregido.

### 2.2 SEC-066 — retiro del endpoint de módulos del tenant

- **Diff:** `api_contactos.py:172-174` reemplaza `PUT /modulos/{modulo_id}` y
  `ModuloIn` por un comentario; `grep ModuloIn backend/` → 0 referencias.
- **Prueba actualizada:** `backend/tests/test_agente_enrolamiento_http.py:100-108`
  ahora espera **404** en `PUT /nucleo/agente/modulos/agente-whatsapp` (antes 204).
- **Cierre:** la superficie HTTP del tenant ya no puede encender el flag. El
  `admin_set_modulo_empresa` sigue existiendo (`0029:243-270`) y `tei_app` conserva
  `grant execute` (`0029:270`); `0033` no lo revoca. Sin endpoint, solo un runtime
  comprometido/SQLi podría llamarla. **Residual de defensa en profundidad**, no un
  bypass de tenant. Si se quiere cerrar del todo, `0033` (o una `0034`) debe
  revocar `EXECUTE` de `tei_app` sobre `nucleo.admin_set_modulo_empresa`, o
  moverlo a un rol de plataforma (RA-16).

### 2.3 SEC-064 — la corrección del aprobador ahora manda

- **Diff:** `solicitudes.py:459-485`:
  - parte de una copia del payload original (`datos = dict(originales)`);
  - `correccion = valores` (request actual); si es `None`, usa
    `solicitud.valores_modificados` (corrección persistida por un `modificar`
    previo);
  - si es dict, `datos.update(correccion)`;
  - para `anular_viaje`, vuelve a fijar `viaje_id` desde `solicitud.viaje_id` si
    existe (`:486-487`), para que una corrección no cambie el viaje objetivo;
  - `_ejecutar_crear_viaje` valida con `ViajeCreateNucleo(**datos)` y
    `_ejecutar_anular_viaje` usa `datos.get("motivo")`, ambos sobre el dict
    fusionado.
- **¿Usa el valor corregido?** Sí: el merge ocurre antes de elegir el ejecutor y
  antes de validar. `ViajeCreateNucleo`/`SolicitudAnulacionViaje` tienen
  `extra="forbid"`, así que una corrección con `empresa_id` u otra clave no
  permitida falla con 422 (fail-closed), y el servicio de viajes vuelve a filtrar
  `empresa_id` de cliente/tarifa/OC.
- **Borde detectado (bajo):** si el cliente envía `valores_modificados={}` en
  `confirmar` (dict vacío, no `None`), `correccion` es `{}` y `datos.update({})` es
  no-op; **no** se aplica la corrección persistida de un `modificar` anterior. El
  contrato no aclara ese caso y la UI probablemente omite el campo, pero conviene
  tratar `{}` como "sin corrección" y caer a `solicitud.valores_modificados`.
- **Cobertura:** no encontré una prueba que haga `modificar` + `confirmar` sobre
  una solicitud `tipo='otra'`; `test_ola4_chat_capacidades.py` no lo cubre. La
  verificación es estática. Se recomienda un test con un `crear_viaje` y un
  `monto_recargos` corregido.

### 2.4 SEC-063 — el catálogo nace apagado y el admin puede habilitarlo

- **Default:** `capacidades.py:176-186` agrega
  `por_defecto={"gerente": False}` a `configuracion.escribir_catalogo`. `_capacidad`
  (`:68-89`) respeta ese dict; `habilitadas` (`:278-306`) usa
  `capacidad.por_defecto.get(agente, False)`. Sin fila en `agente_capacidades`, la
  capacidad **no** está efectiva.
- **Caso "admin habilita":** `capacidades.actualizar` (`:368-450`) valida
  `tiene_permiso(admin, "configuracion:escribir")` (admin lo tiene), no hay módulo
  que bloquee, y hace el upsert `habilitada=true`; `configuracion_agente` la
  devuelve `habilitada: true` y `habilitadas` la incluye. La ruta
  `PUT /nucleo/agente/configuracion` está montada y exige `agente:configurar`
  (admin). **No hay test de este camino**, pero el código es consistente.
- **Runtime:** `especificaciones(persona.tools, habilitadas)` no ofrece la tool si
  no está en `habilitadas`; `_ejecutar_tool` vuelve a rechazarla (`runtime.py:738-742`).
  Al habilitarla, se ofrece y ejecuta; la escritura queda auditada por
  `trg_config_empresa_audit` (`0026`).
- **Contrato:** `docs/backend/agente-chat-inapp.md:170-181` documenta la tool como
  única vía del chat y el opt-in; la tabla de amenazas (`:304-310`) ya no afirma
  que el catálogo se rechaza sin excepción. **Cierra** la contradicción de
  SEC-060 en lo fiscal.
- **Residual:** sin test que verifique el default `False` ni el `PUT` de
  habilitación. Un cambio futuro en `_capacidad` podría volver a encenderla sin que
  la suite lo note.

### 2.5 SEC-065 — topes de tool_calls

- **Configuración:** `config.py:47-48` agrega `AGENTE_LLM_MAX_TOOL_CALLS=8` y
  `AGENTE_LLM_MAX_TOOL_CALLS_TURNO=16`. **No están en `backend/.env.example`**;
  los defaults aplican, pero un operador no ve la perilla. Es un detalle de
  configuración, no un defecto de seguridad.
- **Aplicación:** `runtime.py:566-606`:
  - calcula ambos topes;
  - por cada respuesta, **antes** de insertar el mensaje `assistant` y antes de
    ejecutar tools, rechaza si `len(respuesta.llamadas) > max_tools_respuesta`;
  - suma al contador y rechaza si `tools_ejecutadas > max_tools_turno`;
  - recién después entra a `if respuesta.llamadas` y ejecuta.
  Por tanto **no se ejecuta parcialmente la respuesta que excede el tope**.
- **¿Y las iteraciones anteriores?** Si el tope se excede en la iteración N, las
  tools de las iteraciones 1..N-1 ya se ejecutaron, pero el endpoint del turno
  hace `session.rollback()` ante cualquier excepción (`chat/api.py:157-169`), así
  que el efecto completo se revierte. **No hay commit parcial** en el camino HTTP.
  El contrato del runtime ya decía que el caller cierra la transacción.
- **Residual:** el tope es de **cantidad**, no de tamaño de `argumentos`/`valor`
  jsonb. Un proveedor comprometido puede enviar 8 tools con argumentos enormes
  (coste/tokens/DB) sin superar el tope. `AGENTE_LLM_MAX_TOOL_CALLS*` tampoco está
  en `.env.example`.
- **Cobertura:** no encontré un test que devuelva más de 8 tools en una respuesta
  ni que supere 16 en el turno. La verificación es estática.

### 2.6 SEC-056 y SEC-068 — `0033_privilegios_tei_app.sql`

- **DDL:** `0033:54-60`:
  - `revoke update, delete on nucleo.agente_chat_mensajes from tei_app`;
  - `grant select, insert on nucleo.agente_chat_mensajes to tei_app`;
  - `revoke insert, update, delete on nucleo.tenant_suscripciones from tei_app`;
  - `grant select on nucleo.tenant_suscripciones to tei_app`.
  La verificación interna (`:63-83`) aborta si `tei_app` conserva escritura o
  pierde `INSERT/SELECT` en mensajes / `SELECT` en suscripciones.
- **¿Rompe el runtime?** No, por lectura:
  - `runtime._insertar_mensaje` usa `INSERT ... ON CONFLICT DO NOTHING`; necesita
    `INSERT` (conservado). No hace `UPDATE` ni `DELETE` sobre mensajes.
  - `runtime.historial`/`_historial_llm` leen mensajes; necesitan `SELECT`
    (conservado).
  - `servicio_modulos.estado` lee `tenant_suscripciones`; necesita `SELECT`
    (conservado). No hay escritor en `backend/app` (`grep tenant_suscripciones` →
    solo `servicio_modulos.py`).
  - `fn_touch`/`fn_version` de `agente_chat_mensajes` son `BEFORE UPDATE`; como no
    hay UPDATE de la app, no se usan. No se requieren privilegios extra.
- **¿Deja `tenant_suscripciones` sin lectura?** No: `grant select` explícito
  (`:60`) y la verificación exige `SELECT` (`:79-81`).
- **Pruebas SQL:** `supabase/tests/0033_01:24-89` verifica catálogo y denegación
  real con `set local role tei_app` (UPDATE/DELETE/INSERT → `insufficient_privilege`)
  y `SELECT` permitido; termina en `ROLLBACK`. `0033_99_rollback.sql` simula la
  restauración de grants dentro de una transacción y revierte.
- **`scripts/test_db_reset.sh`:** re-aplica `0033` tras `0020` para que el clon
  `tei_test` tenga los mismos privilegios; correcto.
- **No verificado 🔴:** no pude ejecutar `psql`/`docker`; no confirmé que `0033`
  esté aplicada en `postgres` ni en `tei_test`, ni que `tei_app` no herede el
  privilegio por otra vía. El usuario dice que está aplicada; **no lo tomo como
  prueba mía**. El DDL y las pruebas SQL son coherentes.
- **Residual:** `0033` no añade trigger de inmutabilidad; `postgres`/plataforma
  conserva `UPDATE/DELETE`. Es la separación de roles esperada. `tei_app` conserva
  `UPDATE` sobre `agente_chat_conversaciones` (resumen/estado), que no es el
  historial de mensajes; si se quiere inmutabilidad total, hace falta una decisión
  aparte.

### 2.7 SEC-067 y SEC-071 — no corregidos

- **SEC-067:** `0021:218-223` sigue con el índice único global
  `(telefono) where activo`; `0029:105-160` sigue insertando el contacto
  `activo=true`/`otp_estado='pendiente'` antes de verificar. No hay endpoint de
  revocación. **Abierto**, requiere decisión de identidad (ADR-0003). El
  `docs/estado.md` lo registra como RA-22.
- **SEC-071:** el chat sigue enviando configuración, reglas, clientes con RUT,
  facturación y márgenes al proveedor LLM (`runtime.py:416-463`;
  `herramientas.py:781-1081`; `llm.py:78-93`). **Abierto**, requiere DPA/decisión
  de negocio (P-07). El `docs/estado.md` lo registra como RA-23.

### 2.8 SEC-053, SEC-054, SEC-057(a)

- **SEC-053:** sin cambios; la transacción sigue abierta durante el LLM y el cupo
  se adquiere antes de autenticar (`chat/api.py:46-67,148-170`;
  `runtime.py:579-654`). **Parcial.**
- **SEC-054:** sin rate limit/presupuesto; `grep` de `slowapi|RateLimit|...` no
  encuentra middleware (el único match de `quoting` es CSV). **Abierto.**
- **SEC-057(a):** la unicidad de `clave_idempotencia` sigue siendo
  `(empresa_id, clave)` (`0031:264-266`) y `_previa_por_clave` filtra por usuario
  (`runtime.py:383-411`); un usuario B con la clave de A recibe 502, no 409.
  **Abierto.**

---

## 3. Defectos nuevos o residuales introducidos por las correcciones

1. **`tei_app` conserva `EXECUTE` sobre `nucleo.admin_set_modulo_empresa`**
   (`0029:270`; `0033` no lo revoca). El endpoint HTTP se retiró (SEC-066), pero
   un runtime comprometido/SQLi puede seguir escribiendo el flag. **No es un
   bypass de tenant** (la función exige `p_empresa_id = ctx_empresa()` y el módulo
   no se activa sin suscripción), pero deja el control de plataforma a medias.
2. **`SEC-064` con `valores_modificados={}`:** un dict vacío en `confirmar` no
   cae a la corrección persistida. Es un borde de contrato, no un bypass; la UI
   probablemente omite el campo. Recomendación: `if not correccion: correccion =
   solicitud.valores_modificados`.
3. **`SEC-065` sin tope de tamaño de argumentos:** los topes son de cantidad. Un
   proveedor comprometido puede enviar 8 tools con `datos`/`valor` enormes. No se
   ejecuta N veces, pero sí puede inflar tokens/DB.
4. **`AGENTE_LLM_MAX_TOOL_CALLS*` no está en `backend/.env.example`:** el operador
   no ve las perillas. No es seguridad, es operación/configuración.
5. **Artefacto de QA desactualizado:** `docs/qa/matriz-trazabilidad.md` §19 sigue
   marcando el panel como fallo (QA-O4-01). No lo edité (fuera de alcance); debe
   actualizarlo `qa`.
6. **Docstring de `test_agente_enrolamiento_http.py:7`** sigue diciendo que el flag
   se enciende/apaga por la función; el test ahora espera 404. Menor.
7. **Sin tests de regresión para SEC-063/064/065:** el "495 passed" no prueba esos
   vectores. No es un defecto de producto, pero sí una brecha de aseguramiento.

---

## 4. Lo que no pude verificar 🔴

| Qué | Por qué | Qué lo confirmaría |
|---|---|---|
| `make unit` / `make test` / 495 passed | `pytest` denegado en esta sesión | salida real de `make test` y `pytest -q tests` |
| `0033` aplicada en `postgres`/`tei_test` y privilegios efectivos de `tei_app` | `psql`/`docker` denegados | `has_table_privilege('tei_app', ...)` y `set role tei_app` en ambas bases |
| Que el test del panel pase con `_agente_out` | no ejecuté pytest | `pytest tests/test_ola4_chat_capacidades.py::test_panel_configuracion_agente_esta_montado` |
| Que el admin pueda habilitar `configuracion.escribir_catalogo` por `PUT` | no ejecuté pytest/HTTP | test HTTP con `admin` y `PUT /nucleo/agente/configuracion` |
| Que `modificar` + `confirmar` aplique el valor corregido | no ejecuté pytest/HTTP | test de `crear_viaje` con `monto_recargos` corregido |
| Que los topes de tools rechacen sin ejecutar parcialmente | no ejecuté pytest | `FakeLLM` con >8 calls y assert de 0 efectos / rollback |
| Que `0033` no rompa los tests del chat (INSERT/SELECT) | no ejecuté pytest/psql | suite de chat contra `tei_test` con `tei_app` |
| Rol efectivo de `NUCLEO_DATABASE_URL` | no se puede leer `.env`/`pg_roles` | `select current_user` con la cadena de la app |

---

## 5. Conclusión

- **Cerrados en código:** SEC-056, SEC-063, SEC-064, SEC-065, SEC-068, SEC-069,
  SEC-070 (y SEC-051 por SEC-063; SEC-061/062 ya estaban).
- **Cerrado en HTTP con residual DB:** SEC-066.
- **Abiertos:** SEC-053 (parcial), SEC-054, SEC-057(a), SEC-067, SEC-071.
- **No verificado por mí:** la aplicación real de `0033` y la suite. No heredo el
  "495 passed". La matriz de QA sigue desactualizada en el panel; no la edité.
