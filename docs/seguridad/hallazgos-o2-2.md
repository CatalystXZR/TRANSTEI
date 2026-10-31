# Auditoría de seguridad — O2.2: buzón de solicitudes del agente WhatsApp

- **Rol:** `auditor-seguridad` (revisión independiente; el informe del autor,
  `docs/backend/informes/o2-2-buzon-solicitudes.md`, se trata como **hipótesis**,
  no como conclusión).
- **Fecha:** 2026-10-31.
- **Alcance:** commit `233e380` y `5fd401c` en lo que toca al buzón:
  `backend/app/nucleo/agente/solicitudes.py`,
  `backend/app/nucleo/agente/api_solicitudes.py`,
  `backend/app/nucleo/errores.py` (3 clases),
  `backend/app/api/router.py` (registro),
  `backend/tests/test_agente_o2_2_buzon.py`,
  `backend/tests/test_agente_o2_2_http.py` (presente en el árbol y parte de la
  evidencia HTTP),
  `docs/backend/informes/o2-2-buzon-solicitudes.md` (informe del autor).
- **Contrato de referencia:** `docs/arquitectura/conector-agente-whatsapp.md`
  §6.1–§6.7 y §7; `AGENTS.md` §9 y §11.2; ADR-0003 §14.
- **Esquema real:** `supabase/migrations/0021_agente_whatsapp.sql` y
  `supabase/migrations/0022_agente_whatsapp_endurecimiento.sql`.
- **Naturaleza:** auditoría **estática**. **No se ejecutó código, SQL ni HTTP**:
  el permiso de `shell` fue rechazado en esta sesión (`permission.rejected`).
  Tampoco se pudo usar `git diff`; la atribución al cambio se hace por la lista
  de archivos del contrato de tarea y por el árbol de trabajo. Ver §0.2.
- **Veredicto corto:** a nivel HTTP no encontré bypass de autenticación, de
  tenant, de permisos ni inyección SQL. **Sí hay dos bloqueantes para desplegar
  el ejecutor `hoja_de_ruta`** (SEC-041 y SEC-042) y la evidencia HTTP del cambio
  no es ejecutable/consistente (SEC-044). Detalle en §8.

> **Actualización — revalidación 2026-10-31** (commits `b1f18c7` y `a864a39`):
> SEC-041 y SEC-043 quedaron **cerrados**; SEC-044 quedó **refutado** (el fixture
> actual usa un solicitante distinto del aprobador y la suite HTTP es consistente);
> SEC-042 **sigue abierto en parte** (media: la validación de tipos/`faltantes`
> no se implementó). El veredicto de §8 queda superado por §10.9.

---

## 0. Método y limitación

### 0.1 Archivos leídos

| Archivo | Tipo | Lectura |
|---|---|---|
| `backend/app/nucleo/agente/solicitudes.py` | nuevo | completo (584 líneas) |
| `backend/app/nucleo/agente/api_solicitudes.py` | nuevo | completo (178 líneas) |
| `backend/app/nucleo/errores.py` | modificado | completo (222 líneas) |
| `backend/app/nucleo/deps.py` | contexto | completo |
| `backend/app/nucleo/permisos.py` | contexto | completo |
| `backend/app/core/{security,contexto,database}.py` | contexto | secciones citadas |
| `backend/app/main.py` | contexto | límite de cuerpo, handlers de error |
| `backend/app/api/router.py` | modificado | completo |
| `backend/tests/test_agente_o2_2_buzon.py` | nuevo | completo (510 líneas) |
| `backend/tests/test_agente_o2_2_http.py` | nuevo (árbol) | completo (322 líneas) |
| `backend/tests/test_agente_gate.py` | contexto | 370–388 |
| `backend/tests/conftest.py` | contexto | 50–130 |
| `Makefile` | contexto | 68–87 (`test`) |
| `supabase/migrations/0020_rls_multiempresa.sql` | contexto | políticas y `ctx_empresa` |
| `supabase/migrations/0021_agente_whatsapp.sql` | DDL | tablas, triggers, RLS, grants |
| `supabase/migrations/0022_agente_whatsapp_endurecimiento.sql` | DDL | `fn_hoja_ruta_transicion` |
| `docs/arquitectura/conector-agente-whatsapp.md` | contrato | §6.1–§6.7 (y referencias de §7) |
| `docs/arquitectura/adr/ADR-0003-agente-multimodal-whatsapp.md` | decisión | §14 |
| `docs/seguridad/hallazgos-o2-1.md` | numeración | 1–135 y 520–619 (numeración y formato) |

No se leyó `backend/.env` ni ningún valor de secreto. No se modificó código,
migraciones, configuración ni permisos.

### 0.2 Limitación de método — leer antes que nada 🔴

**El permiso de `shell` fue rechazado** (`permission.rejected`) también en esta
sesión. Por lo tanto:

- **no se ejecutaron** las pruebas que pide el contrato de tarea:
  ```
  cd backend
  NUCLEO_TEST_DATABASE_URL="<DSN de tei_test con rol administrador>" \
  NUCLEO_DATABASE_URL="<DSN de tei_test con rol tei_app>" \
  ../.venv/bin/python -m pytest tests/test_agente_o2_2_buzon.py -v
  ```
  ni la suite HTTP:
  ```
  TEST_ADMIN_EMAIL=… TEST_ADMIN_PASSWORD=… \
  TEST_CONTABILIDAD_EMAIL=… TEST_CONTABILIDAD_PASSWORD=… \
  ../.venv/bin/python -m pytest tests/test_agente_o2_2_http.py -v
  ```
- no hubo reproducción en PostgreSQL, ni dos conexiones reales, ni respuesta
  HTTP real;
- no se pudo verificar el rol efectivo de `NUCLEO_DATABASE_URL` ni el estado de
  `tei_test`;
- `git diff` no se pudo usar. Lo que no está en la lista de archivos del
  contrato se marca **preexistente / no atribuible**.

Todo hallazgo se sostiene sobre **lectura de código con cita `archivo:línea`**
(nivel 🟢 de `AGENTS.md` §2 = "leído en código/DB con cita"), no sobre ejecución.
Donde la diferencia entre "el código dice" y "la ejecución lo confirma" importa,
se indica en la columna de confianza y en §6.

---

## 1. Modelo de amenaza de este cambio

| Elemento | Contenido |
|---|---|
| **Activos** | Valores de la hoja de ruta (km, litros, toneladas, combustible, peajes) que alimentan costo/margen/facturación; estado y decisión de la solicitud; `payload` propuesto (puede contener PII: teléfono, RUT, nombres); `aprobado_por`/`modificado_por` y el rastro de auditoría; aislamiento de tenant; permisos `agente:buzon`/`agente:aprobar`. |
| **Actores** | (a) no autenticado; (b) autenticado con rol bajo (`gerente`, `contador`, `tesoreria`, `auditor`, etc.); (c) usuario de **otra** empresa; (d) membresía inactiva o empresa inactiva; (e) `admin` (hoy el único rol con permisos del agente); (f) contacto de WhatsApp (sin JWT ni `agente:aprobar`); (g) el modelo/orquestador (contenido no confiable que produce el `payload`); (h) atacante con la anon key (sin ruta PostgREST a `nucleo`); (i) proceso/credencial con el DSN `tei_app`; (j) dependencia comprometida. |
| **Límites de confianza** | navegador ↔ API; API ↔ Supabase Auth/JWKS (`security.py:21-42`); API ↔ PostgreSQL (`tei_app` + RLS `app.empresa_id`); runtime del agente ↔ tablas `solicitudes`/`hoja_ruta` (el `payload` es dato, no instrucción); frontend ↔ API (JSON). |
| **STRIDE aplicable** | **S**poofing: `empresa`/`auth_id` salen de la membresía y del JWT, no del body (`deps.py:50-102`; `DecidirIn` `extra="forbid"`). **T**ampering: `estado`/`version` solo por `accion` y bloqueo; SQL fijo con parámetros. **R**epudiation: triggers de auditoría en `solicitudes`/`hoja_ruta`; las lecturas del buzón no se auditan. **I**nformation disclosure: 404 entre empresas; proyección sin teléfono ni contenido de archivos; `payload` completo en el detalle (previsto por §6.3). **D**oS: cuerpo global de 32 MB; `listar` trae `payload` completo de hasta 100 filas; `count(*)` sin tope. **E**levation: permisos deny-by-default; autoaprobación; rol `tei_app` con `UPDATE` directo. |
| **Fuera de alcance** | runtime WhatsApp (webhook, HMAC, ASR/visión), enrolamiento/OTP (O2.3), servicios dueños de O2.5, frontend O4.3, legacy `public`, producción/staging y cualquier ataque contra servicios externos. |

---

## 2. Resumen

La parte de **autorización y tenant** está bien resuelta en el código:

- la empresa sale **siempre** de `X-Empresa-ID` + membresía (`get_contexto_empresa`),
  nunca del body ni de un query param;
- todas las consultas del servicio llevan `empresa_id = :empresa_id` explícito, y
  RLS es una segunda barrera con `tei_app`;
- un `id` de otra empresa devuelve **404**, no 403 ni fila;
- `decidir` toma `FOR UPDATE`, verifica estado terminal y `version`, y el `UPDATE`
  vuelve a exigir `estado='pendiente' and version=:version`;
- el ejecutor y el cambio de estado están en la **misma transacción**: no hay
  `commit()` en el servicio ni en el ejecutor; el endpoint hace un único
  `commit()` y `rollback()` ante excepción;
- el 501 `TIPO_SIN_EJECUTOR` ocurre antes de cualquier escritura y deja la
  solicitud `pendiente`;
- los permisos son deny-by-default: `agente:buzon` para leer,
  `agente:aprobar` para decidir; hoy solo `admin` los tiene y `gerente` está
  excluido (AB-02);
- el body no puede fijar `estado`, `empresa_id`, `aprobado_por` ni `decidido_en`;
  `accion` es un `Literal` y `extra="forbid"`;
- no hay SQL construido con datos del usuario: los filtros son constantes y los
  valores van ligados;
- el detalle no tiene campo de teléfono ni devuelve el `payload` de la hoja de
  ruta; `evidencia` se reduce a `{tipo, ref}`. El `payload` libre de la solicitud
  sí se devuelve porque §6.3 lo incluye (ver §7, pregunta 8);
- el `payload` de la hoja de ruta es inmutable por trigger (`0022:354-359`).

Lo que **no** cierra es la **integridad del efecto** del único ejecutor
(`hoja_de_ruta`) y la **evidencia de pruebas HTTP**:

1. **SEC-041 (alta):** `confirmar` después de `modificar` **ignora los valores
   corregidos persistidos** y carga el `payload` original. El registro dice que
   se aplicó una corrección que no se aplicó.
2. **SEC-042 (media):** `confirmar` acepta `valores_modificados` vacíos o
   arbitrarios y marca `hoja_ruta.estado='cargado'` sin validar campos ni
   `faltantes`.
3. **SEC-043 (baja):** `rechazar` de una hoja de ruta no verifica que la
   transición `solicitud_creada → rechazado` haya ocurrido; si no ocurre, la
   solicitud queda rechazada y la hoja de ruta intacta.
4. **SEC-044 (baja, evidencia):** el fixture HTTP crea solicitudes a nombre del
   propio `admin` y tres pruebas esperan éxito donde el servicio devuelve 403
   `AUTOAPROBACION`; la capa HTTP no está realmente verificada.
5. Residuales: autoaprobación con contacto sin vínculo (SEC-045, aceptado por
   contrato), servicio que confía en `ContextoEmpresa` (SEC-046), respuesta
   frágil a `payload` no-objeto (SEC-047), `listar` que trae payload completo
   (SEC-048) y el rol `tei_app` que puede escribir sin pasar por la app
   (SEC-049, preexistente).

**Conteo: 1 alta, 1 media, 2 bajas, 1 baja/potencial y 4 informativas.**
No hay crítica ni alta de autenticación/tenant.

---

## 3. Tabla de hallazgos

| ID | Sev. | Área | Evidencia (`archivo:línea`) | Impacto | Remediación | Estado |
|---|---|---|---|---|---|---|
| SEC-041 | **alta** | Integridad del efecto | `solicitudes.py:349`, `:481-483`, `:506-540`; `test_agente_o2_2_buzon.py:307-321,324-348`; ADR-0003 §14.1 (`:405`); contrato §6.4 (`:1028`) | `confirmar` tras `modificar` carga el payload original, no la corrección; el registro y el efecto se contradicen | Usar `valores_modificados` del body, si no el persistido, si no el payload de la hoja de ruta; nunca solo `solicitud.payload`; prueba de regresión | confirmado (código) |
| SEC-042 | **media** | Validación / integridad | `solicitudes.py:349-351,429-435`; `0021:522`; `0022:361-365`; contrato §6.4 (`:1028`); ADR-0003 §14.2 (`:417`) | `confirmar` con `{}` o tipos inválidos marca la hoja de ruta `cargado` sin datos; `faltantes` se ignora | Validar contra schema del tipo; rechazar `{}`/tipos inválidos; CHECK de respaldo; schema de `negocio-finanzas` | confirmado (código) |
| SEC-043 | **baja** | Integridad / fail-closed | `solicitudes.py:557-584` (sin `rowcount`); contraste `:373-378` | Un rechazo puede dejar la solicitud `rechazada` y la hoja de ruta `propuesto`/`cargado` | Verificar la fila actualizada y fallar cerrado; prueba | confirmado (comportamiento) |
| SEC-044 | **baja** | Evidencia de pruebas | `test_agente_o2_2_http.py:88,241-252,255-270,288-298`; `solicitudes.py:414-420,470`; `0004:89-96` | Tres pruebas HTTP reciben 403 `AUTOAPROBACION` donde esperan 200/501; la capa HTTP no está verificada | Fixture con solicitante distinto del aprobador; correr `make test`; pruebas HTTP faltantes | confirmado (lectura) |
| SEC-045 | informativa | Autoaprobación | `solicitudes.py:421-426`; `0021:189`; contrato §6.4 (`:1085-1088`) | Un contacto sin `usuario_empresa_id` permite que el aprobador sea el solicitante real | Exigir vínculo o registrar el usuario creador; O2.3; documentar el residual | confirmado (comportamiento) |
| SEC-046 | informativa | Defensa en profundidad | `solicitudes.py:438-470`; `api_solicitudes.py:157`; `deps.py:68-79` | El servicio no revalida membresía/rol; un llamador interno con `ContextoEmpresa` armado a mano podría decidir | Contexto verificado o chequeo de servicio; documentar el contrato | confirmado (código) |
| SEC-047 | **baja** (potencial) | Robustez / respuesta | `api_solicitudes.py:174-178`; `:92`; `0021:399`; `_evidencia` `:223-228` | Un `payload` no-objeto o `ref` no-str produce 500; si es `decidir`, la decisión ya se commiteó | CHECK `jsonb_typeof`/modelos tolerantes; serializar antes del commit; prueba | potencial |
| SEC-048 | informativa | Disponibilidad | `solicitudes.py:66,204,297-304`; `main.py:42` | `listar` trae `payload` completo de hasta 100 filas para calcular un resumen | Resumen en SQL o columna; cota de payload al crear | confirmado (código) |
| SEC-049 | informativa (preexistente) | Rol de BD | `0021:855-860`; `0021:458-483`; `core/database.py:185-217` | `tei_app` puede actualizar `solicitudes`/`hoja_ruta` sin permiso ni autoaprobación; el trigger solo valida estado/campos | Rol escritor separado o trigger de autoaprobación; decisión de arquitectura | confirmado (preexistente) |

---

## 4. Detalle de hallazgos

### SEC-041 [alta] `confirmar` después de `modificar` ignora la corrección persistida y carga el `payload` original

- **Estado:** confirmado · **Confianza:** alta (lectura de código) ·
  **Explotabilidad:** requiere condiciones (flujo documentado `modificar` →
  `confirmar` sin reenviar valores) · **Alcance:** una empresa ·
  **Esfuerzo:** S.
- **Evidencia:**
  - `solicitudes.py:349`:
    `cargados = valores if valores is not None else solicitud.payload`.
    `valores` es el `valores_modificados` **del body**; si el body no lo trae,
    usa `solicitud.payload` (el original).
  - `solicitudes.py:481-483`: el ejecutor recibe `valores_modificados` del body.
  - `solicitudes.py:506-540`: el `UPDATE` conserva
    `valores_modificados = coalesce(cast(:valores as jsonb), valores_modificados)`;
    si el body no trae valores, la corrección persistida **sigue** en
    `solicitudes.valores_modificados`.
  - `solicitudes.py:103-104`: `_SELECT_BLOQUEO` lee `payload` y
    `valores_modificados`, pero `_confirmar_hoja_ruta` solo usa el primero.
  - `test_agente_o2_2_buzon.py:307-321` prueba `modificar`; `:324-348` prueba
    `confirmar` **con** valores en el body. **No hay prueba del flujo combinado**
    `modificar` → `confirmar` sin reenviar valores.
  - ADR-0003 §14.1 (`:405`): "el aprobador corrige valores y **confirma** → la
    carga usa los valores corregidos". Contrato §6.4 (`:1028`): `confirmar`
    "usa `valores_modificados` si están presentes".
- **Escenario:**
  1. Solicitud `hoja_de_ruta` pendiente, `payload={"km":10,"litros":5}`,
     `version=1`.
  2. `POST /decidir {accion:"modificar", version:1, valores_modificados:{"km":12}}`
     → `solicitudes.valores_modificados={"km":12}`, `version=2`.
  3. `POST /decidir {accion:"confirmar", version:2}` (sin
     `valores_modificados`, que es válido para `confirmar`).
  4. `_confirmar_hoja_ruta` toma `cargados = solicitud.payload` →
     `hoja_ruta.valores_cargados={"km":10,"litros":5}`, `estado='cargado'`.
     `solicitudes.valores_modificados` sigue `{"km":12}`.
  5. El detalle muestra `diff: km 10→12`, pero la hoja de ruta cargada tiene
     `km=10`.
- **Impacto:** la corrección aprobada **no se aplica**; el registro dice que sí.
  Los km/litros cargados son los originales, y los consumidores de la hoja de
  ruta (costo/km, combustible, márgenes, facturación) reciben datos distintos de
  los que el aprobador vio y aprobó. Pérdida de trazabilidad financiera y
  contradicción entre `solicitudes.valores_modificados` y
  `hoja_ruta.valores_cargados`. Alcance: una empresa; requiere un aprobador que
  use el flujo documentado. No es un bypass de autorización.
- **Capas que fallan:** servicio (elección de la fuente de datos). La base no
  puede inferir la intención; no hay constraint que compare
  `hoja_ruta.valores_cargados` con `solicitudes.valores_modificados`.
- **Remediación:** en `decidir`/`_confirmar_hoja_ruta`, elegir la fuente en este
  orden: (1) `valores_modificados` del body si viene; (2) si no,
  `solicitud.valores_modificados` persistido; (3) si no, el `payload` de la
  **hoja de ruta** (no el de la solicitud). Añadir una prueba de regresión del
  flujo combinado. `backend`; prueba `qa`.
- **Prueba de verificación:**
  `test_confirmar_tras_modificar_sin_reenviar_usa_la_correccion`: tras
  `modificar(km=12)` y `confirmar` sin body, afirmar
  `hoja_ruta.valores_cargados == {"km":12}` y
  `solicitudes.payload == {"km":10,"litros":5}`. Antes de la corrección debe
  fallar (hoy obtiene `km=10`); después, pasar. Añadir también el caso
  "body tiene precedencia".
- **Esfuerzo:** S · **Depende de:** ninguno.

### SEC-042 [media] `confirmar` acepta valores vacíos o arbitrarios y marca la hoja de ruta `cargado` sin validar

- **Estado:** confirmado · **Confianza:** alta (lectura de código) ·
  **Explotabilidad:** requiere un aprobador autorizado (o un error de UI) ·
  **Alcance:** una empresa · **Esfuerzo:** M.
- **Evidencia:**
  - `solicitudes.py:349-351`: el ejecutor solo exige
    `isinstance(cargados, dict)`; `{}` pasa.
  - `solicitudes.py:429-435`: `_validar_cuerpo` exige valores no vacíos
    **solo** para `accion="modificar"`; para `confirmar` no exige nada.
  - `0021:522` (`ck_hr_carga_registrada`): `estado <> 'cargado' or
    valores_cargados is not null`; `{}` no es `NULL`, así que pasa.
  - `0022:361-365`: `solicitud_creada → cargado` es una transición permitida.
  - `_confirmar_hoja_ruta` no consulta `hoja_ruta.payload.faltantes` ni el
    schema del tipo; el `faltantes` del payload solo se **proyecta** en la lista
    (`solicitudes.py:153-155`) y en el detalle (`:244-250`), nunca se valida
    antes de cargar.
  - Contrato §6.4 (`:1028`): `confirmar` valida "datos completos"; ADR-0003
    §14.2 invariante 4 (`:417`): "ninguna carga se ejecuta con evidencia
    faltante".
- **Escenario:**
  1. `POST /decidir {accion:"confirmar", version:1, valores_modificados:{}}` →
     `hoja_ruta.valores_cargados={}`, `estado='cargado'`.
  2. o `valores_modificados={"km":"doce"}` → se persiste el tipo inválido.
  3. El `payload` de la hoja de ruta declaraba `faltantes=["litros"]`; el
     ejecutor lo ignora y marca `cargado`.
- **Impacto:** una hoja de ruta "cargada" sin los datos necesarios, o con tipos
  inválidos, se propaga a los servicios que la consumen; errores de costo,
  combustible o facturación. No hay cross-tenant ni escalamiento; el actor es
  un aprobador autorizado. La base solo valida "no nulo", no "completo".
- **Capas que fallan:** servicio (validación de dominio); base (CHECK débil).
- **Remediación:** definir el schema de campos de la hoja de ruta con
  `negocio-finanzas` y validar `valores_modificados` antes de ejecutar; rechazar
  `{}` y tipos inválidos; exigir `faltantes` vacío salvo una confirmación
  explícita de override; añadir un CHECK de respaldo
  (`jsonb_typeof(valores_cargados)='object'`, y evaluar `<> '{}'`). `backend`,
  `datos`, `negocio-finanzas`; prueba `qa`.
- **Prueba de verificación:** `confirmar` con `{}` → 422; con
  `{"km":"doce"}` → 422; con los campos válidos → 200 y
  `hoja_ruta.valores_cargados` correcto. Antes de la corrección, los dos
  primeros devuelven 200.
- **Esfuerzo:** M · **Depende de:** schema de campos de `negocio-finanzas`
  (D-10 / regla `R-0xx`).

### SEC-043 [baja] `rechazar` de una hoja de ruta no verifica que la transición haya ocurrido

- **Estado:** confirmado (comportamiento) · **Confianza:** alta ·
  **Explotabilidad:** requiere datos inconsistentes o un escritor futuro ·
  **Alcance:** una empresa · **Esfuerzo:** S.
- **Evidencia:**
  - `solicitudes.py:566-584`: `_rechazar_hoja_ruta` hace `UPDATE ... WHERE
    empresa_id=… AND solicitud_id=… AND estado='solicitud_creada'` y **no
    comprueba filas afectadas**; si son 0, retorna sin error.
  - Contraste: `_confirmar_hoja_ruta` sí comprueba (`solicitudes.py:373-378`) y
    lanza `ReglaNegocioViolada`.
  - Contrato §6.6 (`:1167-1169`): rechazar una `hoja_de_ruta` deja
    `hoja_ruta.estado='rechazado'` + motivo.
- **Escenario:** una solicitud `pendiente` de tipo `hoja_de_ruta` cuyo
  `hoja_ruta` está en `propuesto`, `cargado` o `rechazado` (por un escritor
  futuro, una reparación manual o una creación incompleta del agente). El
  aprobador rechaza: la solicitud queda `rechazada`; la hoja de ruta no cambia.
- **Impacto:** estado contradictorio; una hoja de ruta cargada/rechazada que no
  corresponde a la solicitud; el "rechazar no muta el núcleo" se cumple para la
  solicitud pero no para el objeto enlazado. En el flujo normal, una hoja de
  ruta `cargado` implica una solicitud `aprobada` (terminal), así que el rechazo
  se bloquea antes; por eso la severidad es baja.
- **Capas que fallan:** servicio; no hay constraint que ligue el estado de la
  solicitud con el de la hoja de ruta.
- **Remediación:** usar `RETURNING`/`rowcount` y, para `tipo='hoja_de_ruta'`,
  lanzar `ReglaNegocioViolada` si no hay fila en `solicitud_creada`; o registrar
  explícitamente el caso. `backend`; prueba `qa`.
- **Prueba de verificación:** crear una solicitud `pendiente` con una hoja de
  ruta en `propuesto`; `rechazar` debe devolver 409 y no cambiar la solicitud;
  antes de la corrección devuelve 200 y deja la solicitud rechazada.
- **Esfuerzo:** S · **Depende de:** ninguno.

### SEC-044 [baja] Las pruebas HTTP se contradicen con la autoaprobación y no prueban la capa HTTP

- **Estado:** confirmado (lectura; no ejecutado) · **Confianza:** alta ·
  **Explotabilidad:** N/A (evidencia de pruebas) · **Alcance:** verificación del
  cambio · **Esfuerzo:** S.
- **Evidencia:**
  - `test_agente_o2_2_http.py:88`: el fixture `solicitud` crea la solicitud con
    `usuario_empresa_id or admin["membresia_id"]`; por defecto el solicitante es
    **el propio admin**.
  - `solicitudes.py:414-420,470`: `_verificar_autoaprobacion` compara la
    membresía del aprobador con la del solicitante y lanza `Autoaprobacion`
    (403) antes de ejecutar y antes del `UPDATE`.
  - `test_agente_o2_2_http.py:241-252` (`test_rechazo_completo_por_http`) y
    `:255-270` (`test_reintento_tras_exito_es_409`) esperan **200** con
    `headers_admin`; el servicio devuelve **403 `AUTOAPROBACION`**.
  - `test_agente_o2_2_http.py:288-298`
    (`test_confirmar_tipo_sin_ejecutor_es_501`) espera **501**; la autoaprobación
    ocurre antes del lookup del ejecutor y devuelve **403**.
  - `test_agente_o2_2_http.py:275-278` hace
    `update nucleo.solicitudes set version = 5`; el trigger `fn_version`
    (`0004:89-96`) impone `new.version := old.version + 1`, así que la versión
    real es 2. La prueba pasa (409) pero no prueba "version=5".
  - `test_agente_o2_2_http.py:313-322` (`test_no_revela_datos_fuera_del_buzon`)
    solo busca literales (`telefono`, `+569`, `costo`, `margen`,
    `valor_flete`) en un payload sintético; no prueba campos reales ni el
    contenido libre de `payload`/`evidencia.ref`.
  - El informe del autor reconoce que la capa HTTP no está verificada
    (`o2-2-buzon-solicitudes.md:91-96`), pero el archivo existe y, si se ejecuta,
    falla.
- **Escenario:** `make test` define `TEST_ADMIN_*`/`TEST_CONTABILIDAD_*`
  (`Makefile:72-82`); al correr `test_agente_o2_2_http.py`, las tres pruebas
  anteriores reciben 403 y fallan. Si faltan las credenciales, el archivo entero
  se omite (`conftest.py:101-111`) y la capa HTTP queda sin evidencia.
- **Impacto:** no es una vulnerabilidad de runtime; es **evidencia falsa o
  ausente** para un cambio de riesgo Alto. El aislamiento/permisos HTTP no están
  demostrados por una suite verde; solo por lectura de código.
- **Capas que fallan:** pruebas / verificación.
- **Remediación:** el fixture por defecto debe usar un **contacto** o una segunda
  membresía como solicitante; reservar la solicitud a nombre del admin para
  `test_autoaprobacion`; para `test_confirmar_tipo_sin_ejecutor` usar una
  solicitud de un contacto; para la versión, subirla con un `modificar` real o
  con una segunda actualización; añadir pruebas HTTP de (a) `decidir` sobre una
  solicitud de otra empresa → 404, (b) contacto vinculado que intenta aprobar →
  403, (c) campos extra `estado`/`empresa_id` en el body → 422. `qa`.
- **Prueba de verificación:** `pytest tests/test_agente_o2_2_http.py -v` verde y
  `make test` verde; antes de la corrección, las tres pruebas citadas fallan.
- **Esfuerzo:** S · **Depende de:** ninguno.

### SEC-045 [informativa] La autoaprobación se puede eludir con un contacto sin vínculo

- **Estado:** confirmado (comportamiento) · **Confianza:** alta ·
  **Explotabilidad:** requiere condiciones (contacto sin `usuario_empresa_id`;
  O2.3 no implementado) · **Alcance:** una empresa · **Esfuerzo:** M.
- **Evidencia:** `solicitudes.py:421-426` solo compara si
  `contacto_usuario_empresa_id is not None`; `0021:189` declara la columna
  nullable; contrato §6.4 (`:1085-1088`) acepta explícitamente que "si el
  contacto no tiene vínculo, no hay autoaprobación posible por esa vía";
  ADR-0003 §14 (`:397`) exige que el conductor no apruebe su propia carga.
- **Escenario:** un `admin` enrola un contacto con su propio teléfono y
  `usuario_empresa_id=NULL`; el contacto origina una solicitud; el `admin` la
  aprueba. `_verificar_autoaprobacion` no ve vínculo y permite. El rastro muestra
  un contacto como solicitante y al admin como aprobador.
- **Impacto:** la regla de segregación no se impone para contactos sin vínculo.
  El actor ya es `admin` (no hay escalamiento de privilegios), pero se pierde la
  garantía de que "quien solicita no aprueba" y la trazabilidad de la identidad
  real. Es un residual **aceptado por el contrato**, no un bypass de un control
  que el contrato exija.
- **Capas que fallan:** servicio/identidad; el vínculo se define en O2.3.
- **Remediación:** en O2.3, exigir `usuario_empresa_id` para contactos de
  empleados/admin que puedan originar solicitudes, o registrar el usuario
  creador; documentar el residual en el contrato. `backend`, `datos`,
  `negocio-finanzas`.
- **Prueba de verificación:** contacto vinculado a la membresía X, aprobado por
  X → 403; contacto sin vínculo → decidir si se rechaza en el alta o se acepta
  documentadamente. `qa`.
- **Esfuerzo:** M · **Depende de:** O2.3.

### SEC-046 [informativa] El servicio confía en `ContextoEmpresa` y no revalida membresía ni rol

- **Estado:** confirmado · **Confianza:** alta · **Explotabilidad:** requiere un
  llamador interno/futuro que construya el contexto a mano · **Alcance:** todas
  las empresas · **Esfuerzo:** M.
- **Evidencia:** `solicitudes.py:438-470` no llama a `_membresia` para
  autorizar; solo lo hace `_verificar_autoaprobacion`; el permiso vive en
  `api_solicitudes.py:157` (`requiere_permiso("agente:aprobar")`) y la membresía
  en `deps.py:68-79`. Además, si `_membresia` devuelve `None`,
  `_verificar_autoaprobacion` **omite** la comparación (`actual is not None and
  …`, `solicitudes.py:414-419,421-426`): en el servicio, la autoaprobación falla
  abierto. Las pruebas construyen el contexto a mano
  (`test_agente_o2_2_buzon.py:79-85`), lo que demuestra que el servicio acepta
  cualquier `ContextoEmpresa`.
- **Escenario:** un job o endpoint futuro llama `servicio.decidir(session,
  contexto_armado, …)` con `app.empresa_id` fijado a una empresa y sin pasar por
  `get_contexto_empresa`; no hay revalidación de membresía/rol. Hoy no hay ruta
  HTTP que lo haga.
- **Impacto:** defensa en profundidad; un refactor podría saltarse la
  autorización. No es explotable por HTTP en este cambio.
- **Capas que fallan:** servicio; la base no conoce roles/permisos.
- **Remediación:** exigir un contexto verificado (tipo/flag) o un chequeo de
  membresía/permiso dentro del servicio; documentar que `decidir` es solo para
  el endpoint. `backend`, `arquitectura`.
- **Prueba de verificación:** un `ContextoEmpresa` sin membresía debe ser
  rechazado por el servicio; hoy el servicio no lo comprueba.
- **Esfuerzo:** M · **Depende de:** ninguno.

### SEC-047 [baja · potencial] Un `payload` no-objeto o una `evidencia` con `ref` no-str producen 500; en `decidir`, después del commit

- **Estado:** potencial · **Confianza:** media · **Explotabilidad:** requiere
  condiciones (payload no-objeto/`ref` no-str; el escritor del agente no está en
  el repo) · **Alcance:** una empresa · **Esfuerzo:** S/M.
- **Evidencia:** `api_solicitudes.py:92` declara `payload: dict[str, Any]` y
  `:96` `hoja_ruta: HojaRutaOut`; la base declara `payload jsonb` sin
  `jsonb_typeof` (`0021:399`) y `evidencia` es libre dentro del JSON. `_evidencia`
  (`solicitudes.py:223-228`) devuelve `elemento.get("ref")` sin validar tipo;
  `EvidenciaOut.ref: str | None` (`api_solicitudes.py:74-76`). El `commit()` está
  en `:174`, antes de construir `DecisionOut` (`:175-178`).
- **Escenario:** una solicitud con `payload=[]` o `"x"` (la base lo acepta) hace
  que `obtener`/`decidir` fallen en la validación de respuesta → 500. Si es
  `decidir`, el `commit()` ya ocurrió: la decisión quedó aplicada y el cliente
  recibe 500; el reintento devuelve 409. Un `evidencia: [{"ref": {"x":1}}]`
  produce el mismo efecto.
- **Impacto:** 500 en el detalle de un registro malformado; confusión de
  reintento; no hay doble efecto. Depende de que el runtime del agente escriba
  un payload no-objeto, hoy no implementado en este repo.
- **Capas que fallan:** modelo de respuesta; CHECK de base; escritor del agente.
- **Remediación:** añadir `CHECK (jsonb_typeof(payload) = 'object')` (y
  `valores_modificados` objeto/null), o hacer los modelos tolerantes y validar;
  construir/serializar la respuesta antes del `commit()` o asegurar que no pueda
  fallar después. `datos`, `backend`.
- **Prueba de verificación:** insertar un payload array y pedir el detalle → 422
  de dato (no 500) o respuesta controlada; `decidir` no debe commitear si la
  respuesta no se puede construir. `qa`.
- **Esfuerzo:** S/M · **Depende de:** ninguno.

### SEC-048 [informativa] `listar` trae el `payload` completo de hasta 100 filas para calcular un resumen

- **Estado:** confirmado · **Confianza:** alta · **Explotabilidad:** requiere
  condiciones (payloads grandes; admin o agente ruidoso) · **Alcance:** una
  empresa · **Esfuerzo:** M.
- **Evidencia:** `solicitudes.py:66` selecciona `s.payload`; `:204` llama a
  `_resumen`, que solo usa `len(payload)` (`:151`); `:297-304` limita a 100
  filas; el cuerpo global es 32 MB (`main.py:42`).
- **Escenario:** 100 solicitudes con payloads grandes; una llamada
  `GET /solicitudes?limit=100` transfiere y mantiene en memoria los JSONB
  completos para devolver un `resumen` de 200 caracteres.
- **Impacto:** latencia/memoria; DoS de baja intensidad por un usuario
  autorizado o por datos generados por el agente. No hay fuga: el payload no se
  devuelve en la lista.
- **Capas que fallan:** consulta/proyección; no hay cota de payload al crear.
- **Remediación:** calcular el resumen en SQL (`jsonb_object_keys`/`jsonb_array_length`)
  o guardar un resumen; acotar el payload al crear la solicitud. `backend`,
  `datos`.
- **Prueba de verificación:** medir la consulta con 100 payloads grandes; el
  listado no debe seleccionar el JSONB completo. `qa`.
- **Esfuerzo:** M · **Depende de:** ninguno.

### SEC-049 [informativa · preexistente, no atribuible] `tei_app` puede escribir `solicitudes`/`hoja_ruta` sin pasar por permiso ni autoaprobación

- **Estado:** confirmado (preexistente) · **Confianza:** alta ·
  **Explotabilidad:** requiere el rol `tei_app` o una inyección SQL (no
  encontrada en este cambio) · **Alcance:** todas las empresas · **Esfuerzo:** L.
- **Evidencia:** `0021:855-860` concede `select, insert, update` sobre
  `nucleo.solicitudes` y `nucleo.hoja_ruta` a `tei_app`;
  `fn_solicitud_transicion` (`0021:458-483`) solo valida estado terminal y
  campos obligatorios, no actor ni autoaprobación; la autorización y la
  autoaprobación viven en `solicitudes.py` y `api_solicitudes.py`.
- **Escenario:** una conexión `tei_app` comprometida (o un escritor futuro que
  no use el servicio) ejecuta
  `UPDATE nucleo.solicitudes SET estado='aprobada', aprobado_por='x', decidido_en=now()`
  sobre una solicitud `pendiente`; el trigger lo acepta. El GUC `nucleo.auth_id`
  puede fijarse a voluntad, así que el actor de auditoría también es spoofable
  por ese rol.
- **Impacto:** bypass de la autorización/autoaprobación de la aplicación a nivel
  de base; trazabilidad del actor dependiente del GUC. Es una propiedad
  **preexistente** de 0021, no introducida por O2.2, y coincide con el riesgo de
  rol ya anotado en SEC-039.
- **Capas que fallan:** privilegios de base / trigger.
- **Remediación:** decidir un rol escritor separado o restringir las columnas
  que `tei_app` puede actualizar; evaluar un trigger de autoaprobación (difícil
  porque `aprobado_por` es texto spoofable); documentar la aceptación.
  `datos`, `arquitectura`.
- **Prueba de verificación:** intentar el `UPDATE` directo con `tei_app` y
  confirmar que el trigger/rol lo rechaza, o registrar la aceptación. `qa`.
- **Esfuerzo:** L · **Depende de:** decisión de rol (SEC-039 / ADR-0005).

---

## 5. Controles verificados 🟢

| # | Control | Evidencia | Cómo se comprobó |
|---|---|---|---|
| 1 | **Empresa solo desde la membresía** | `deps.py:50-102` (`X-Empresa-ID` + `usuarios_empresa`); `solicitudes.py:282,325,456-457,536-537`; `api_solicitudes.py:103-107` (`extra="forbid"`, sin `empresa_id`) | Lectura de las consultas y del schema de entrada; no hay `empresa_id` en body ni query. |
| 2 | **404 para recurso de otra empresa** | `solicitudes.py:323-328` (detalle), `:455-460` (decisión); `_SELECT_*` con `empresa_id`; `test_agente_o2_2_buzon.py:248-252`; `test_agente_o2_2_http.py:156-202` | Filtro explícito por empresa + RLS; el test de servicio y el HTTP esperan 404, no 403. |
| 3 | **Listado acotado a la empresa** | `_SELECT_LISTA` `solicitudes.py:59-82`; `_CONTEOS_LISTA` `:90-94`; `test_agente_o2_2_buzon.py:215-228` | `where s.empresa_id = :empresa_id` en lista y conteo. (Cobertura negativa incompleta; ver §6.) |
| 4 | **`FOR UPDATE` + estado terminal + `version`** | `solicitudes.py:98-115` (`for update of s`), `:455-468`, `:506-545`; `0021:458-483`; `test_agente_o2_2_buzon.py:442-510` | El `SELECT` bloquea; el `UPDATE` exige `estado='pendiente' and version=:version`; el trigger rechaza reabrir terminal. |
| 5 | **Atomicidad efecto + estado** | `solicitudes.py` no tiene `commit` (grep); `api_solicitudes.py:160-174` (un `commit`, `rollback` ante excepción); `test_agente_o2_2_buzon.py:351-362` | El ejecutor recibe la misma `Session`; no hay commit oculto; el 501 no deja estado. |
| 6 | **501 `TIPO_SIN_EJECUTOR` deja intacta la solicitud** | `solicitudes.py:475-480` (lookup antes de escribir); `api_solicitudes.py:170-173`; `test_agente_o2_2_buzon.py:351-362` | Si no hay ejecutor, lanza antes del `UPDATE`; el `rollback` cierra la transacción. |
| 7 | **Autoaprobación usuario y contacto vinculado** | `solicitudes.py:406-426`; `test_agente_o2_2_buzon.py:398-415`; `test_agente_o2_2_http.py:301-310` | Compara `usuarios_empresa.id` del aprobador con el solicitante usuario o con el `usuario_empresa_id` del contacto. |
| 8 | **Permisos de lectura vs decisión** | `api_solicitudes.py:128,147,157`; `permisos.py:15-18,63-67,157-177`; `test_agente_gate.py:377-388`; `test_agente_o2_2_http.py:132-141,210-218` | `agente:buzon` para GET; `agente:aprobar` para POST; solo `admin` los tiene; `gerente` excluido (AB-02). |
| 9 | **Body no fija estado/empresa/actor** | `api_solicitudes.py:103-107` (`Literal`, `extra="forbid"`); `solicitudes.py:475-504` (estado derivado de `accion`) | No hay campo `estado`, `empresa_id`, `aprobado_por` ni `decidido_en` en el schema. |
| 10 | **Sin inyección SQL** | `solicitudes.py:59-127` (SQL constante), `:273-304` (validación y parámetros ligados); `_FILTROS_LISTA` fijo | No hay f-strings con datos del usuario; `estado`/`tipo` se validan contra `frozenset`; `viaje_id` es UUID. |
| 11 | **Proyección del detalle sin teléfono/archivo; `payload` es contrato** | `_solicitante` `:159-176`; `_evidencia` `:212-229`; `_detalle` `:232-255`; contrato §6.3 (`:973-1007`) | No se devuelve `telefono`, ni `hoja_ruta.payload`, ni contenido de archivo; `evidencia` solo `{tipo, ref}`. El `payload` libre sí se devuelve porque §6.3 lo incluye; si contiene PII/costos, es responsabilidad del agente que lo creó. |
| 12 | **`payload` inmutable al confirmar** | `0022:349-359` (`fn_hoja_ruta_transicion` rechaza cambio de `payload`); `solicitudes.py:349-379` (no escribe `payload`); `test_agente_o2_2_buzon.py:324-348` | Trigger BEFORE UPDATE + el ejecutor solo escribe `valores_cargados`/`estado`/`updated_by`. |
| 13 | **RLS como segunda barrera** | `0021:799-814` (política `tenant_empresa`), `:833-850` (`ENABLE`+`FORCE`); `get_session_nucleo` `core/database.py:205-217`; `docs/estado.md:103` (RA-03) | Política y `FORCE` leídas; la guarda de `get_session_nucleo` rechaza `BYPASSRLS` con DSN explícito. El rol efectivo no se pudo verificar (§6 #3); si es `tei_app`, RLS filtra por `app.empresa_id`, y en todo caso el servicio filtra explícitamente. |
| 14 | **Auditoría de la decisión** | `0021:771-785` (triggers `trg_solicitudes_audit`, `trg_hoja_ruta_audit`); `0021:862-864` (append-only) | Cada `UPDATE`/`INSERT` de solicitud/hoja_ruta deja fila; el `aprobado_por`/`modificado_por` se derivan del contexto, no del body. |
| 15 | **Cota de cuerpo** | `main.py:42` (32 MB), `:91-132` (middleware ASGI) | El body se rechaza antes del parseo si excede 32 MB; no sustituye la validación de contenido, pero acota el DoS trivial. |
| 16 | **Errores de dominio sin SQL crudo** | `errores.py:196-222`; `main.py:179` (`ErrorNucleo` → JSON); `main.py:229-276` (mapeo sin `repr`) | 403/404/409/501 con `{codigo, mensaje}`; no se filtra el mensaje de PostgreSQL. |
| 17 | **Sin secretos en el cambio** | `grep` de `password`, `secret`, `token`, `apikey`, `api_key`, `service_role`, `anon_key`, `postgresql+psycopg` sobre `solicitudes.py`, `api_solicitudes.py` y `test_agente_o2_2_buzon.py` | 0 coincidencias de credenciales; solo aparecen dos reemplazos de esquema `postgresql+psycopg://` en el test, sin valor. No se leyó `.env`. |

---

## 6. Sin cobertura / no verificado 🔴

| # | Qué no está cubierto | Por qué | Qué lo cerraría |
|---|---|---|---|
| 1 | **Ejecución de las 14 pruebas del servicio** | `shell` denegado | Correr el comando del contrato y pegar la salida real. |
| 2 | **Ejecución de la suite HTTP** (`test_agente_o2_2_http.py`) | `shell` denegado; además SEC-044 la invalida | Corregir el fixture (SEC-044) y correr `pytest tests/test_agente_o2_2_http.py -v`. |
| 3 | **Rol efectivo de `NUCLEO_DATABASE_URL`** | requiere conectar; no se imprime el DSN | `select current_user, rolbypassrls from pg_roles where rolname=current_user;` con el engine del núcleo. Si `BYPASSRLS`, RLS es inerte y el aislamiento depende solo de los filtros del servicio (que están presentes). |
| 4 | **Dos conexiones reales para `rechazar` y `modificar`** | no ejecutado; el test solo cubre `confirmar` | Test de concurrencia con dos conexiones para cada acción. |
| 5 | **Autoaprobación con contacto vinculado** | no hay test; el servicio solo prueba el caso usuario | Contacto con `usuario_empresa_id` = membresía del aprobador → 403. |
| 6 | **Flujo `modificar` → `confirmar` sin reenviar valores** (SEC-041) | no hay test; el código lo permite | Test descrito en SEC-041; hoy falla. |
| 7 | **`confirmar` con `{}` o tipos inválidos** (SEC-042) | no hay test | Test descrito en SEC-042; hoy devuelve 200. |
| 8 | **`rechazar` con hoja_ruta fuera de `solicitud_creada`** (SEC-043) | no hay test; requiere datos inconsistentes | Test descrito en SEC-043. |
| 9 | **Bypass de la app con `tei_app`** (SEC-049) | no ejecutado; preexistente | `UPDATE` directo con `tei_app` y verificación de trigger/rol. |
| 10 | **Pooler en modo transacción / GUC `app.empresa_id`** | no hay entorno | Repetir las pruebas de aislamiento con pgbouncer en modo `transaction`; verificar `SET LOCAL`/listener `begin`. |
| 11 | **Frontend O4.3** | no existe | Al construirlo: escapar `payload`/`evidencia.ref`, no usar `dangerouslySetInnerHTML`, no aceptar `ref` como URL arbitraria. |
| 12 | **JWT `iss`/JWKS y expiración** | preexistente, fuera del cambio | Revisión de `core/security.py` en una auditoría de autenticación; aquí solo se verificó que el `sub` se usa y que el token se valida con RS256/ES256 y `aud`. |
| 13 | **`skip` silenciosos** | los tests HTTP se omiten sin `TEST_ADMIN_*`/`TEST_CONTABILIDAD_*` (`conftest.py:101-111`); los de servicio, sin seed | `make test` con credenciales y `tei_test`; registrar `-rs` para ver los `skip`. |
| 14 | **Atribución exacta a `233e380`/`5fd401c`** | `git diff` no disponible | Revisar el diff de los dos commits con shell; aquí se auditó el árbol de trabajo. |
| 15 | **Listado con una fila de otra empresa y listado no vacío** | `test_listar_solo_devuelve_la_empresa` no crea una fila ajena; `test_listar_por_defecto_solo_pendientes` puede pasar con `items=[]` | Crear una solicitud en otra empresa y afirmar que no aparece; afirmar que una solicitud pendiente propia sí aparece. |

---

## 7. Respuestas a las 10 preguntas del contrato de auditoría

| # | Pregunta | Respuesta | Evidencia | Nivel |
|---|---|---|---|---|
| 1 | ¿El `empresa_id` sale siempre de la membresía? ¿Hay body/query? | **Sí, siempre de `X-Empresa-ID` + membresía.** No hay `empresa_id` en body ni query; `DecidirIn` es `extra="forbid"` y `accion` es `Literal`. | `deps.py:50-102`; `solicitudes.py:282,325,456-457,536-537`; `api_solicitudes.py:103-107` | 🟢 |
| 2 | ¿Un `id` de otra empresa devuelve 404 y no 403/filtración? ¿Y el listado? | **Sí: 404.** El `SELECT`/`UPDATE` filtran por `empresa_id`; el listado solo devuelve filas de la empresa. | `solicitudes.py:323-328,455-460`; `_SELECT_LISTA` `:59-82`; `test_agente_o2_2_buzon.py:248-252`; `test_agente_o2_2_http.py:156-202` | 🟢 (código); 🔴 ejecución |
| 3 | ¿Se puede saltar `FOR UPDATE`, `version` o el estado terminal? ¿Dos transacciones? | **No por la API.** El `SELECT ... FOR UPDATE` bloquea; el estado terminal se comprueba antes; el `UPDATE` exige `estado='pendiente' and version=:version`; el segundo aprobador recibe 409. | `solicitudes.py:98-115,455-468,506-545`; `0021:458-483`; `test_agente_o2_2_buzon.py:442-510` | 🟢 (código); 🔴 dos conexiones reales |
| 4 | Atomicidad: ¿medio efecto? ¿`commit()` oculto? | **No hay medio efecto en el código.** El servicio y el ejecutor no hacen `commit`; el endpoint hace uno solo y `rollback` ante excepción. Matiz: el `commit` ocurre antes de serializar la respuesta (SEC-047). | `solicitudes.py` (sin `commit`); `api_solicitudes.py:160-174`; `test_agente_o2_2_buzon.py:351-362` | 🟢 (código) |
| 5 | Autoaprobación: ¿correcta para usuario y contacto? ¿Se elude con un contacto sin vínculo? | **Correcta para usuario y contacto vinculado.** **Sí se elude con un contacto sin vínculo**: el código no compara nada si `usuario_empresa_id` es NULL; el contrato lo acepta (SEC-045). | `solicitudes.py:406-426`; `0021:189`; contrato §6.4 (`:1085-1088`); `test_agente_o2_2_buzon.py:398-415` | 🟢 / residual |
| 6 | ¿El 501 deja la solicitud intacta o aprobada? | **Intacta (`pendiente`).** El lookup del ejecutor ocurre antes de cualquier escritura; el endpoint hace `rollback`. | `solicitudes.py:475-480`; `api_solicitudes.py:170-173`; `test_agente_o2_2_buzon.py:351-362` | 🟢 (código); 🔴 ejecución |
| 7 | ¿`agente:buzon`/`agente:aprobar`? ¿`gerente`? ¿Un rol de solo lectura decide? | **Sí, los endpoints exigen cada permiso.** `gerente` **no** los tiene (AB-02); hoy solo `admin`. No hay rol con `agente:buzon` sin `agente:aprobar`, así que un rol de solo lectura no existe ni puede decidir. | `api_solicitudes.py:128,147,157`; `permisos.py:15-18,63-67`; `test_agente_gate.py:377-388`; `test_agente_o2_2_http.py:132-141,210-218` | 🟢 (código/unit) |
| 8 | ¿El detalle expone algo prohibido por §6.3? | **A nivel de campos, no:** no hay teléfono, contenido de archivo ni `hoja_ruta.payload`; `evidencia` solo `{tipo, ref}`. **Matiz:** `payload` es JSON libre y puede contener PII/costos; §6.3 lo incluye explícitamente, así que el servidor depende de la disciplina del agente. | `_solicitante` `:159-176`; `_evidencia` `:212-229`; `_detalle` `:232-255`; contrato §6.3 (`:973-1007`) | 🟢 (campo) / 🟡 (contenido libre) |
| 9 | ¿El `payload` es inmutable al confirmar? | **Sí.** El trigger `fn_hoja_ruta_transicion` rechaza cualquier cambio de `payload` en `UPDATE`; el ejecutor no lo escribe; el test lo comprueba. | `0022:349-359`; `solicitudes.py:349-379`; `test_agente_o2_2_buzon.py:324-348` | 🟢 (código); 🔴 ejecución |
| 10 | ¿Hay `skip`/`xfail`/aserciones vacuas en las 14 pruebas? | **No hay `skip`/`xfail` en las 14** (solo `pytest.skip` de fixtures si falta seed/empresas/membresías). **Sí hay aserciones débiles:** listado sin fila ajena, lista que puede pasar vacía, autoaprobación solo usuario, no hay `modificar`→`confirmar`, y la suite HTTP tiene el defecto de SEC-044. | `test_agente_o2_2_buzon.py:215-245,398-415,307-348`; `test_agente_o2_2_http.py:88,241-298` | 🟢 (lectura); 🔴 ejecución |

---

## 8. Prioridad recomendada y veredicto

### 8.1 ¿Se puede encender el buzón en producción?

**No con el ejecutor `hoja_de_ruta` activo tal como está.** El buzón **no consulta
el flag del módulo** (contrato §6.7; `api_solicitudes.py` no lee
`modulos_empresa`): desplegar este código ya deja disponible
`POST /solicitudes/{id}/decidir` para `hoja_de_ruta`. Por lo tanto, el riesgo no
se controla con el flag del agente.

- **No hay bloqueante de autenticación, tenant ni permisos.** En esos ejes el
  cambio es sólido: empresa desde membresía, 404 entre empresas, `FOR UPDATE`,
  `version`, estado terminal, permisos deny-by-default, sin inyección SQL y sin
  estado por body.
- **Sí hay bloqueantes de integridad del efecto:**
  - **SEC-041 (alta):** `confirmar` tras `modificar` carga el valor original, no
    la corrección. Es el flujo que el ADR-0003 §14.1 describe; no debe
    desplegarse así.
  - **SEC-042 (media):** `confirmar` con `{}`/tipos inválidos marca la hoja de
    ruta `cargado` sin datos. La base solo exige "no nulo".
- **La evidencia HTTP no es aceptable todavía:** SEC-044 muestra que tres
  pruebas HTTP se contradicen con la autoaprobación; si se ejecutan, fallan; si
  se omiten, la capa HTTP queda sin probar. Un cambio de riesgo Alto no debería
  aceptarse con esa evidencia.
- **Interim seguro:** si el negocio necesita el buzón antes de corregir 041/042,
  dejar `EJECUTORES_SOLICITUD = MappingProxyType({})` (todo `confirmar` → 501
  `TIPO_SIN_EJECUTOR`, sin efecto) y habilitar solo lectura, `modificar` y
  `rechazar`; corregir SEC-043 para que el rechazo sea fail-closed. Esto no
  relaja ningún control: convierte el confirm en un 501 explícito, como el
  propio contrato §6.6 permite para los tipos sin ejecutor.
- **Condiciones de aceptación posteriores:** SEC-043 (baja), SEC-045/046
  documentadas, SEC-047 (robustez), SEC-048/049 (deuda/arquitectura).

### 8.2 Orden sugerido

1. **SEC-041** (alta, S): usar la corrección persistida; prueba de regresión.
2. **SEC-042** (media, M): schema de campos + rechazo de `{}`/tipos inválidos;
   depende de `negocio-finanzas`.
3. **SEC-044** (baja, S, evidencia): corregir el fixture HTTP y **ejecutar**
   `pytest tests/test_agente_o2_2_http.py -v` + `make test`.
4. **SEC-043** (baja, S): `RETURNING`/`rowcount` y fallo cerrado.
5. **SEC-047** (baja/potencial, S/M): CHECK `jsonb_typeof`/modelos tolerantes;
   serializar antes del commit o garantizar que no falle.
6. **SEC-045/046/048/049:** documentar/aceptar o planificar; SEC-049 depende de
   la decisión de rol (SEC-039 / ADR-0005).

**Quick wins (S, sin dependencias):** SEC-041, SEC-043, SEC-044.
**Dependencias:** SEC-042 → schema de `negocio-finanzas`; SEC-049 → decisión de
rol `datos`/`arquitectura`.

### 8.3 Agentes responsables

| Hallazgo | Agente |
|---|---|
| SEC-041, SEC-042, SEC-043, SEC-046, SEC-047 | `backend` |
| SEC-041/042/043/044/047 (pruebas) | `qa` |
| SEC-042 (CHECK de respaldo), SEC-047 (CHECK), SEC-049 | `datos` |
| SEC-042 (schema de campos), SEC-045 (vínculo) | `negocio-finanzas` |
| SEC-046, SEC-049 (rol) | `arquitectura` |
| SEC-044 (fixture HTTP) | `qa` |

---

## 9. Autoverificación

1. **¿Cada hallazgo confirmado tiene evidencia reproducible?** Sí: todos citan
   `archivo:línea`; los que dependen de ejecución están marcados `potencial` o
   en §6.
2. **¿Distinguí confirmado de potencial?** Sí: SEC-041/042/043/044/045/046/048/
   049 son confirmados por lectura de código; SEC-047 es `potencial` (requiere
   un payload no-objeto o `ref` no-str, y el escritor del agente no está en el
   repo).
3. **¿Describí el control real en vez de "no hay control"?** Sí: describí el
   filtro explícito por `empresa_id`, la RLS, el `FOR UPDATE`, el trigger de
   transición y el `commit` único; no declaré "no hay aislamiento" ni "no hay
   auditoría".
4. **¿Probé variantes (verbo, rol, endpoint legacy vs núcleo)?** Roles: admin,
   `gerente`, `contador`, otra empresa, membresía inactiva, contacto; verbos:
   solo GET/POST (no hay PUT/DELETE en el router); legacy vs núcleo: no hay ruta
   legacy equivalente para el buzón; body vs query vs header: el `empresa_id`
   solo sale del header/membresía. La ejecución de esas variantes quedó 🔴 por
   falta de shell, salvo la lectura de código y los tests existentes.
5. **¿Excluí secretos?** Sí: no se leyó `.env` ni se imprimió ningún valor; solo
   se citan ubicaciones (`NUCLEO_DATABASE_URL`, `X-Empresa-ID`) sin contenido.
6. **¿Evité presentar una buena práctica ausente como vulnerabilidad?** Sí:
   SEC-045 (autoaprobación de contacto sin vínculo) es aceptada por el contrato
   y se marca informativa; SEC-046/048/049 son defensa en profundidad/deuda;
   SEC-044 es evidencia de pruebas, no un fallo de runtime. SEC-041/042 son
   defectos de integridad del efecto, no estilo.
7. **¿Listé lo que no pude verificar?** Sí, §6 con 15 puntos y qué los cerraría.
8. **¿Cada remediación tiene prueba de verificación y agente responsable?** Sí,
   en el detalle de cada SEC y en §8.3.
9. **¿Respeté los límites?** No edité código, migraciones, configuración ni
   permisos; solo escribí este archivo en `docs/seguridad/`. No ejecuté pruebas
   destructivas ni contra producción (no pude ejecutar nada). No modifiqué
   `hallazgos.md`; este informe es un archivo aparte y continúa la numeración
   desde SEC-041 (el máximo registrado en `docs/seguridad/` es SEC-040).

---

## 10. Revalidación 2026-10-31

### 10.1 Método y límite

- **Objeto:** `b1f18c7` (correcciones SEC-041/042/043), `a864a39` (capa HTTP) y el
  árbol actual, contrastados con el informe original (`81b9ac7`).
- **Método:** lectura del código actual, `git show b1f18c7`, `git show a864a39`,
  `git diff a864a39`, `git log -S` y conteo estático de pruebas. **No se ejecutó
  pytest**: `shell` volvió a responder `permission.rejected` (solo quedó
  disponible `git`). Los resultados que aporta el orquestador —18 + 15 `passed`;
  `make test` → 351 `passed`, 0 `skipped`— se tratan como **nivel 3** y no se
  reproducen aquí.
- **Conteo estático:** 18 `def test_` en `test_agente_o2_2_buzon.py` y 15 en
  `test_agente_o2_2_http.py`, consistente con la cifra aportada. `b1f18c7` añade
  4 pruebas al servicio (14 → 18); eso explica el paso de 347 a 351 en `make test`
  respecto del informe del autor.
- **Sigue sin verificarse:** la ejecución real de las 33 pruebas, el rol efectivo
  de `NUCLEO_DATABASE_URL` y las dos conexiones reales de `rechazar`/`modificar`
  (§6 #1–#4). La revalidación es de código, no de ejecución.

### 10.2 Tabla de estados

| ID | Estado en la revalidación | Evidencia principal | ¿Bloquea el buzón? |
|---|---|---|---|
| SEC-041 | **cerrado** (código) | `solicitudes.py:355-366`; prueba `test_agente_o2_2_buzon.py:519-549` | No |
| SEC-042 | **sigue abierto (parcial)** — media | `solicitudes.py:355-366`, `:136-142`, `:244-250`; `0021:520-522` | **Sí, con el ejecutor** |
| SEC-043 | **cerrado** (defecto original) + efecto nuevo SEC-050 | `solicitudes.py:587-609`; prueba `test_agente_o2_2_buzon.py:593-627` | No (efecto nuevo, bajo) |
| SEC-044 | **refutado / obsoleto** | `test_agente_o2_2_http.py:83,65-67,298-307`; `git diff a864a39` vacío | No |
| SEC-045..049 | sin cambios en estos commits; no re-auditados | `git show --stat b1f18c7 a864a39` | No (informativa/baja) |
| SEC-050 | **nuevo, bajo · potencial** (efecto de SEC-043) | `solicitudes.py:587-609`; `0021:500,520`; `test_agente_o2_2_buzon.py:596-597` | No por sí solo |

### 10.3 SEC-041 — **cerrado** (código) · confianza alta

- **Prioridad actual** en `backend/app/nucleo/agente/solicitudes.py:355-366`:
  (1) `valores_modificados` del request si no es `None`; (2) el persistido en
  `solicitudes.valores_modificados`; (3) el `payload` de la solicitud. El
  `_SELECT_BLOQUEO` ya leía ambas columnas (`:98-115`, en particular `:103-104`) y
  `decidir` pasa el body al ejecutor (`:496-498`); el `UPDATE` conserva la
  corrección persistida cuando el body no trae valores
  (`valores_modificados = coalesce(cast(:valores as jsonb), valores_modificados)`,
  `:529`).
- **Traza `modificar` → `modificar` → `confirmar`:** cada `modificar` **reemplaza**
  el objeto persistido (el `coalesce` de `:529` no fusiona claves); el segundo
  `modificar` deja el último objeto y `confirmar` sin body usa ese último
  (`:357-358`). No hay un camino donde la corrección persistida se ignore y se
  cargue el `payload`. Matiz de diseño: si el segundo `modificar` envía un objeto
  **parcial**, el primero se pierde en el `modificar` (reemplazo de objeto
  completo, no merge), no en el `confirmar`; el cliente debe enviar el objeto
  completo, como describe el contrato §7 (`:1211-1213`).
- **Fallos cerrados, no pérdidas:** si el persistido fuese `{}` o un no-objeto
  (solo alcanzable por escritura directa a la tabla —SEC-049—, porque `modificar`
  exige un dict no vacío, `:449-450`), `confirmar` lanza `DatosInvalidos` en
  `:361-366` y **no** cae al `payload`. La solicitud queda `pendiente` y se
  resuelve con un `modificar` válido; es el comportamiento correcto.
- **Prueba de regresión:** `test_sec_041_confirmar_usa_la_correccion_persistida`
  (`test_agente_o2_2_buzon.py:519-549`) crea `payload={"km":10}`,
  `modificar({"km":12})`, `confirmar` sin body y afirma `valores_cargados=={"km":12}`
  y `payload=={"km":10}`. Cubre persistido > payload.
- **Cobertura que falta:** el caso **body > persistido** (modificar y luego
  confirmar con otro objeto) no tiene prueba. `test_confirmar_hoja_de_ruta_no_reescribe_el_payload`
  (`:325-349`) prueba body sin persistido; el test de SEC-041 prueba persistido
  sin body. Un mutante que intercambiara las ramas 1 y 2 pasaría ambas pruebas.
  Es una brecha de mutación, no un defecto actual.
- **Nivel:** 🟢 código; ejecución de la prueba 🔴 en esta sesión.

### 10.4 SEC-042 — **sigue abierto (parcial)** · media · confianza alta

- **Lo que sí se cerró:** `confirmar` ya no acepta `{}` ni un no-objeto. La guarda
  `if not isinstance(cargados, dict) or not cargados` (`solicitudes.py:361-366`)
  se ejecuta antes del `UPDATE` de `hoja_ruta`; el endpoint revierte
  (`api_solicitudes.py:160-174`). Pruebas:
  `test_sec_042_confirmar_sin_valores_no_carga` y
  `test_sec_042_confirmar_con_objeto_vacio_se_rechaza` (`:552-591`). El CHECK
  `ck_hr_carga_registrada` (`0021:522`) ya no es el único filtro.
- **Lo que sigue abierto:** la única condición es "dict no vacío". No hay schema
  de campos ni validación de tipos. Pasan `{"km":"doce"}`, `{"km":null}`,
  `{"foo":1}` y `{"faltantes":["litros"]}`. Además, el ejecutor sigue **sin leer**
  `hoja_ruta.payload`, que es donde vive `faltantes` (`:117-122` y `:244-250`);
  `_faltantes` solo se usa para el resumen y el detalle (`:136-142`, `:149-155`).
  Por tanto no se cumplen ADR-0003 §14.2 invariante 4 ("ninguna carga se ejecuta
  con evidencia faltante") ni contrato §6.4 ("datos completos", `:1028`).
- **Escenario concreto que sigue funcionando:** solicitud `hoja_de_ruta` con
  `payload={"faltantes":["litros"]}` (o `{"km":null}`) y hoja en
  `solicitud_creada`; `POST /decidir {accion:"confirmar", version:1}` sin body →
  `cargados` es ese objeto no vacío → `hoja_ruta.estado='cargado'` y
  `valores_cargados={...}`; el CHECK solo exige "no nulo" (`0021:522`), y el
  trigger de transición permite `solicitud_creada → cargado` (`0022:361-365`).
  El payload original queda inmutable, pero la carga se ejecutó con `faltantes`.
- **Efecto lateral del nuevo `not cargados`:** si `solicitudes.payload={}` y
  `hoja_ruta.payload={"km":10}` (dos fuentes que el esquema no obliga a
  coincidir), `confirmar` sin body devuelve 422 aunque la hoja tenga datos. Es
  fail-closed y se resuelve con `modificar`, pero confirma que el ejecutor usa
  una fuente distinta de la que muestra el detalle de la hoja.
- **Severidad:** media se mantiene. El abuso trivial (`{}`) está cerrado; lo que
  queda exige un aprobador autorizado (`agente:aprobar`, hoy solo `admin`) y un
  objeto no vacío con tipos/`faltantes` inválidos. El impacto sigue siendo datos
  financieros incorrectos en una empresa, sin cross-tenant ni escalamiento.
- **Para cerrar:** schema de campos acordado con `negocio-finanzas`, validación
  de tipos y de `faltantes` (vacío, o override explícito y auditado), CHECK de
  respaldo `jsonb_typeof(valores_cargados)='object'` y, si se decide, `<> '{}'`;
  pruebas 422 por HTTP para `{}`, `{"km":"doce"}` y `faltantes` no vacío.

### 10.5 SEC-043 — **cerrado** (defecto original) · efecto nuevo SEC-050

- **Corrección:** `_rechazar_hoja_ruta` comprueba `resultado.rowcount`
  (`solicitudes.py:587-609`); con 0 lanza `ReglaNegocioViolada` (409,
  `errores.py:106-107`) y el endpoint hace `rollback`
  (`api_solicitudes.py:160-174`). La prueba
  `test_sec_043_rechazo_fail_closed_si_la_hoja_no_transiciona`
  (`:593-627`) deja la solicitud en `pendiente` y la hoja en `propuesto`: el
  rechazo a medias ya no ocurre.
- **¿Es fiable `rowcount` con el driver?** El backend usa `psycopg[binary]==3.2.6`
  (`requirements.txt:9`) con SQLAlchemy; la sentencia es un `UPDATE` **sin**
  `RETURNING`, y psycopg informa las filas afectadas. Es fiable en este caso.
  Recomendación defensiva: usar `rowcount != 1` en vez de `== 0`; un driver que
  devolviera `-1` (no es el caso de psycopg aquí) no dispararía la guarda actual.
- **¿Falso positivo con un `UPDATE` que toca la fila sin cambiar de estado?** No:
  el `WHERE` exige `estado='solicitud_creada'` y el `SET` pone `'rechazado'`;
  toda fila que coincide cambia de estado. Los triggers
  `fn_hoja_ruta_transicion` (`0022:349-382`) y `fn_version` (`0004:89-96`) no
  revierten el estado. Si RLS ocultara la fila, `rowcount=0` → falla cerrado.
  Límite conocido: el esquema no garantiza una sola hoja por solicitud (la
  UNIQUE parcial `uq_hoja_ruta_carga_por_solicitud` solo cubre `cargado`,
  `0021:528-529`); `rowcount > 1` es posible y la guarda `== 0` no lo detecta.
  No es un fallo de seguridad, pero el contrato asume una hoja por solicitud.
- **Efecto nuevo (SEC-050, bajo · potencial):** `rowcount=0` también ocurre
  cuando **no existe** fila de `hoja_ruta` para una solicitud `tipo='hoja_de_ruta'`
  o cuando está en `propuesto`/`cargado`/`rechazado`. En esos casos:
  - `rechazar` → 409 (nuevo);
  - `confirmar` → `ReglaNegocioViolada` (el `WHERE` de `:375-377` exige
    `estado='solicitud_creada'`);
  - `modificar` no cambia el estado de la hoja.
  La solicitud queda sin camino de resolución por el buzón (no hay acción
  `cancelar`: `ACCIONES` en `:45`), es decir, potencialmente irresoluble.
  **Alcanzabilidad:** el esquema permite `propuesto` con `solicitud_id`
  (`ck_hr_estado_solicitud`, `0021:520`), el flujo de propuesta representado en
  las pruebas inserta la hoja sin `solicitud_id`
  (`0021_03_rls_tei_app.sql:151-154`) y el propio test comenta que es "un estado
  alcanzable por el alta" (`test...:596-597`). El escritor real (O2.5) no está en
  el repo, así que **no se puede confirmar** que el alta deje ese estado
  commiteado: 🟡 potencial, no confirmado.
  **Remediación:** distinguir "no hay fila" (quizá rechazar solo la solicitud,
  porque no hay nada que rechazar) de "fila en estado que no transiciona"
  (409); garantizar que el alta de O2.5 sea atómica (hoja + solicitud +
  transición a `solicitud_creada` en una transacción) y añadir una prueba del
  caso sin fila. `backend`/`datos`; prueba `qa`.

### 10.6 SEC-044 — **refutado / obsoleto**

- **Fixture actual:** `backend/tests/test_agente_o2_2_http.py:83` hace
  `solicitante = usuario_empresa_id or admin["otro_miembro_id"]`; `:65-67`
  obtiene la segunda membresía y `:84-85` omite la prueba si no existe. La
  solicitud se crea a nombre de **otra** membresía, no del aprobador. El único
  caso con la membresía del admin es `test_autoaprobacion_es_403`
  (`:298-307`), que la pasa explícitamente para probar el 403.
- **El árbol es idéntico al commit:** `git diff a864a39 -- backend/tests/test_agente_o2_2_http.py`
  no devuelve nada. `git log -S 'admin["membresia_id"]' -- backend/tests/test_agente_o2_2_http.py`
  solo encuentra `a864a39`, y la cadena se usa en la prueba de autoaprobación,
  no en el fixture.
- **La cita del informe no existe:** `usuario_empresa_id or admin["membresia_id"]`
  en `:88` no está en el archivo actual ni en el commit; en el archivo actual
  `:88` es el `insert into nucleo.solicitudes`. Las líneas citadas en §4
  (`:88`, `:241-252`, `:255-270`, `:288-298`) están desplazadas 3–5 líneas
  respecto de las actuales (`:83`, `:238-249`, `:252-267`, `:285-295`). Es
  consistente con haber leído la versión de trabajo **previa** al commit
  `a864a39`; el informe del autor (`o2-2-buzon-solicitudes.md` §2.1) documenta
  exactamente ese cambio de fixture.
- **Conclusión:** la afirmación "tres pruebas reciben 403 `AUTOAPROBACION` donde
  esperan 200/501 y la capa HTTP no está verificada" **no se sostiene** para
  `a864a39`+. Con `otro_miembro_id`, `_verificar_autoaprobacion`
  (`solicitudes.py:421-441`) compara la membresía del admin con la del otro
  miembro y no lanza; las expectativas 200/200/501 son coherentes.
- **Observaciones que sobreviven** (no son defectos de seguridad):
  `test_version_vieja_es_409` escribe `version=5` pero `fn_version` impone
  `old.version+1` (`0004:89-96`), así que prueba 1 vs 2 y no 5 (sigue siendo un
  409 válido); `test_no_revela_datos_fuera_del_buzon` busca literales sobre un
  payload sintético; no hay prueba HTTP de `decidir` cross-tenant → 404, de
  contacto vinculado al aprobador → 403 ni de campos extra en el body → 422.
  Son huecos de cobertura, no una suite que falle.
- **Ejecución:** 🔴 no ejecutada en esta sesión. La evidencia del autor/orquestador
  (15 `passed`) es nivel 3 y es consistente con la lectura del código.

### 10.7 SEC-045..049 — sin cambios

`b1f18c7` y `a864a39` solo tocan `solicitudes.py`, dos archivos de pruebas y un
informe; no hay cambios en los controles de SEC-045 (autoaprobación de contacto
sin vínculo), SEC-046 (servicio confía en el contexto), SEC-047 (payload
no-objeto), SEC-048 (payload completo en el listado) ni SEC-049 (rol `tei_app`).
Siguen como estaban: informativas o baja/potencial. SEC-047 no se re-auditó y su
condición (un escritor que inserte `payload` no-objeto) sigue sin estar en el
repo.

### 10.8 Respuestas a las preguntas de revalidación

| # | Pregunta | Respuesta | Nivel |
|---|---|---|---|
| 1 | ¿SEC-041 cerrado? ¿Se pierde la corrección persistida en algún camino? | **Cerrado.** Prioridad request > persistido > payload (`solicitudes.py:355-366`). `modificar`→`modificar`→`confirmar` carga el último persistido; el segundo `modificar` reemplaza el objeto (no fusiona), lo que puede perder campos si el cliente envía un objeto parcial, pero eso ocurre en el `modificar`, no en el `confirmar`. Un persistido `{}`/no-objeto falla cerrado, no cae al payload. Falta probar body > persistido. | 🟢 código / 🔴 ejecución |
| 2 | ¿SEC-042 cerrado? ¿Se puede marcar `cargado` sin datos por otra vía? | **No del todo.** `{}` y las listas/no-objetos se rechazan en el servicio (`:361-366`); una lista tampoco encaja con `dict[str, Any]` en el body (`api_solicitudes.py:107`). Pero cualquier dict no vacío pasa: `{"faltantes":["litros"]}`, `{"km":null}`, `{"km":"doce"}`. No hay schema ni chequeo de `faltantes`; el ejecutor no lee `hoja_ruta.payload`. | 🟢 código / 🔴 ejecución |
| 3 | ¿SEC-043 cerrado? ¿`rowcount` fiable? ¿Falso positivo? | **Cerrado** para el defecto original. `rowcount` es fiable con psycopg 3.2.6 y un `UPDATE` sin `RETURNING`; no hay falso positivo porque el `WHERE` exige `solicitud_creada` y el `SET` cambia a `rechazado`. Efecto nuevo SEC-050 (solicitud sin fila o en `propuesto` queda sin resolución). | 🟢 código / 🔴 ejecución |
| 4 | ¿SEC-044 es real u obsoleto? | **Refutado/obsoleto.** El fixture actual usa `admin["otro_miembro_id"]` (`:83`), no la membresía del aprobador; el árbol es idéntico a `a864a39`. La cita del informe no existe en el archivo. | 🟢 código |
| 5 | ¿Las correcciones introducen efectos nuevos? | **Sí, uno relevante (SEC-050, bajo/potencial):** el rechazo fail-closed deja sin resolución una solicitud `hoja_de_ruta` sin fila o con la hoja en `propuesto` (confirmar también falla y `modificar` no transiciona). Además, `confirmar` con `{}` tras un `modificar` válido devuelve 422 (fail-closed; el cliente debe omitir/null) y un `payload` de solicitud vacío con hoja con datos devuelve 422 (resoluble con `modificar`). | 🟡 código |
| 6 | ¿Queda algún alto/medio abierto que impida encender el buzón? | **Alto no; medio sí: SEC-042 en su parte de validación de tipos/`faltantes`.** SEC-041 y SEC-043 (original) cerrados; SEC-044 refutado. | 🟢 código |

### 10.9 Veredicto: ¿se puede habilitar el buzón?

- **Lectura, `modificar` y `rechazar`: sí.** Los controles de auth, tenant,
  permisos y concurrencia que el informe original verificó no cambiaron; no hay
  un bloqueante nuevo en esos ejes. La única reserva es SEC-050: si existen
  solicitudes `hoja_de_ruta` sin fila o con
  la hoja en `propuesto`, el rechazo devuelve 409 y la solicitud queda pendiente;
  conviene corregirlo o al menos detectarlo antes de O2.5.
- **`confirmar` con el ejecutor `hoja_de_ruta`: no lo certifico todavía.** SEC-042
  sigue siendo **media**: un aprobador autorizado puede marcar `cargado` con
  tipos inválidos o con `faltantes` declarados, y el ejecutor ignora la evidencia
  faltante. El caso trivial `{}` está cerrado, pero la validación de dominio que
  pedía el propio hallazgo (schema, tipos, `faltantes`) no está.
- **Opciones honestas:**
  1. Cerrar SEC-042 (schema + `faltantes` + CHECK de respaldo) y añadir las
     pruebas 422; luego habilitar el ejecutor.
  2. Habilitar solo lectura/`modificar`/`rechazar` y dejar
     `EJECUTORES_SOLICITUD = MappingProxyType({})` (todo `confirmar` → 501
     `TIPO_SIN_EJECUTOR`, sin efecto), como en el interim de §8.1.
  3. Habilitar el ejecutor con **aceptación explícita del riesgo** por el dueño,
     documentada y con la UI impidiendo confirmar si `faltantes` no está vacío.
     No es una aceptación que este auditor pueda firmar como "cerrado".
- **SEC-050** no bloquea por sí solo (bajo/potencial), pero debe corregirse o
  probarse antes de que O2.5 cree solicitudes de forma no atómica.

### 10.10 Pruebas que faltan (no ejecutadas 🔴)

- **Ejecución real** (bloqueada por `permission.rejected`):
  ```
  cd backend
  NUCLEO_TEST_DATABASE_URL="<DSN admin de tei_test>" \
  NUCLEO_DATABASE_URL="<DSN tei_app de tei_test>" \
  TEST_ADMIN_EMAIL=… TEST_ADMIN_PASSWORD=… \
  TEST_CONTABILIDAD_EMAIL=… TEST_CONTABILIDAD_PASSWORD=… \
  ../.venv/bin/python -m pytest tests/test_agente_o2_2_buzon.py tests/test_agente_o2_2_http.py -v
  ```
  y `make test` con la salida real. La cifra 18+15/351 no se reprodujo aquí.
- **Mutación de SEC-041:** `modificar({"km":12})` → `confirmar` con
  `{"km":13}` debe cargar 13 (body > persistido). Hoy no hay prueba que
  distinga el orden de las dos primeras ramas.
- **SEC-042 restante:** `confirmar` con `{"km":"doce"}`, `{"km":null}` y
  `{"faltantes":["litros"]}` → 422 (hoy 200); y un caso con
  `hoja_ruta.payload.faltantes` no vacío.
- **SEC-043/SEC-050:** rechazar una solicitud `hoja_de_ruta` **sin** fila de
  hoja y con la hoja en `propuesto`; definir el resultado esperado y probarlo.
  También el camino normal de rechazo con una sola fila en `solicitud_creada`
  (ya cubierto por `test_rechazar_deja_estado_motivo_y_hoja_ruta`, `:281-305`).
- **Cobertura HTTP que sigue faltando:** `POST /decidir` sobre un id de otra
  empresa → 404 (solo se prueba el GET), contacto vinculado al aprobador → 403,
  campos extra `estado`/`empresa_id` en el body → 422, y `confirmar` con `{}` →
  422 por HTTP.
- **Rol efectivo y concurrencia:** §6 #3 y #4 siguen 🔴; no se revalidaron.

### 10.11 Autoverificación de la revalidación

1. **¿Cada veredicto tiene evidencia?** Sí: `archivo:línea`, diff de git y
   conteo estático; lo que depende de ejecución está marcado 🔴.
2. **¿Distingo cerrado de parcial?** Sí: SEC-041 y SEC-043 (original) cerrados;
   SEC-042 marcado "sigue abierto (parcial)" porque la guarda de vacío no es la
   validación de dominio que el hallazgo pedía; SEC-044 refutado con cita del
   archivo actual.
3. **¿Contradigo al orquestador cuando la evidencia lo exige?** Sí: SEC-042 no
   está cerrado del todo y SEC-044 no es un defecto actual; se dice con la
   evidencia, no por coherencia con el mensaje.
4. **¿Introduzco hallazgos nuevos sin renumerar?** SEC-050 es nuevo y no altera
   SEC-041..049; el resto de la numeración queda intacta.
5. **¿Respeté los límites?** Solo se editó este archivo en `docs/seguridad/`; no
   se ejecutaron pruebas ni se tocó código, configuración o datos.
