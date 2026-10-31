# Revalidación independiente — Ola 2 de seguridad (Fase 1 post-F0)

**Fecha:** 2026-10-29 · **Rol:** auditor-seguridad · **Método:** revisión estática de
código con cita `archivo:línea`; sin ejecución (shell no disponible en esta sesión).
No se modificó código ni configuración.

**Jerarquía de evidencia aplicada:** código leído (nivel 1) > inferencia 🟡 >
no determinable 🔴. Los hallazgos nuevos se numeran `SEC-016` en adelante (continúan
la secuencia de `docs/seguridad/hallazgos.md`, que llega a SEC-015).

---

## Punto 1 — Fail-closed del cutover

**Veredicto: CONFORME** (con 2 observaciones Baja)

### Verificado 🟢

- `backend/app/nucleo/servicio_cutover.py:38-51`: la lectura del flag ocurre dentro
  de `try/except Exception`; cualquier fallo (DB caída, timeout) registra
  `logger.exception` y devuelve **`congelado = True`**. No hay camino de fallo que
  devuelva `False`.
- `servicio_cutover.py:53-58`: `scalar_one_or_none()` → `None` (fila ausente) se
  trata como **congelado**, con `logger.warning`. El supuesto previo "fila ausente =
  abierto" fue invertido correctamente.
- `servicio_cutover.py:20-21, 34-35`: caché de 5 s con TTL por `time.monotonic()`.
- `servicio_cutover.py:65-67, 146, 165`: `invalidar_cache()` se llama tras
  `congelar()` y `descongelar()` en el mismo proceso.
- `backend/app/main.py:41-66`: middleware `@app.middleware("http")` bloquea con 409
  (`CUTOVER_LEGACY_CONGELADO`) todo método no-GET/HEAD/OPTIONS cuyo path empiece por
  `/api/v1` y **no** empiece por `/api/v1/nucleo` ni `/api/v1/auth`.
- Cobertura de routers verificada por grep de `APIRouter(prefix=...)`: los 17 routers
  nucleo usan prefijos `/nucleo*` (`api.py:44`, `api_maestros.py:38`,
  `api_comercial.py:40`, `api_gastos.py:25`, `api_expediente.py:34`,
  `api_pod.py:20`, `api_cutover.py:14`, `api_conductor.py:20`, `api_alertas.py:14`,
  `api_bloqueos.py:24`, `api_facturacion.py:25`, `api_rentabilidad.py:22`,
  `api_permisos.py:24`); auth en `/auth` (`app/api/routes/auth.py:7`). No existe
  ruta legacy fuera de `/api/v1` sin prefijo nucleo/auth. El corte
  `/api/v1/nucleo/cutover` queda operativo, necesario para descongelar.
- El rol del middleware en la pila de Starlette es correcto: `add_middleware(CORS)`
  antes del decorador `@app.middleware("http")` no interfiere con la propagación de
  excepciones hacia los exception handlers.

### Observaciones (Baja)

- **SEC-016 (observación 1)** — **Ventana de 5 s con múltiples workers.** El caché es
  por proceso; `congelar()` solo invalida el caché del worker que atendió la
  request. Con `uvicorn --workers N`, los demás workers siguen permitiendo escrituras
  legacy hasta 5 s después de congelar (fail-open temporal acotado). El Makefile
  actual usa un solo proceso (`Makefile:51`, `uvicorn ... --reload` sin `--workers`),
  por lo que hoy no se materializa. Remediación: cache compartido (Redis/DB) o
  aceptar el TTL documentándolo. Esfuerzo S–M.
- **SEC-016 (observación 2)** — **Estados contradictorios si falta la fila de
  control.** `congelar()` ejecuta `update ... where id = true`
  (`servicio_cutover.py:130-147`) sin verificar `rowcount`; si la fila no existe, el
  commit no hace nada y `estado()` devuelve `legacy_escritura_congelada=False` con
  "No existe registro de cutover; se asume legacy abierto."
  (`servicio_cutover.py:108-114`), mientras el middleware **bloquea** las escrituras
  (fail-closed). La migración `supabase/migrations/0014_cutover.sql:17-19` inserta la
  fila (`insert ... on conflict do nothing`), así que solo ocurre si alguien la
  borra. Remediación: upsert en `congelar()` o validar rowcount y reportar.
  Esfuerzo S.

---

## Punto 2 — Mapeo SQLSTATE→HTTP global

**Veredicto: CONFORME en el mapeo** (con 1 hallazgo de fuga leve)

### Verificado 🟢

- `backend/app/main.py:69-113`: handler global de `IntegrityError`. `23505`/`23P01` →
  `traducir_integrity_error` → 409 (RegistroDuplicado/ConflictoDisponibilidad,
  `errores.py:96-98, 71-74`); `23514`/`23502`/`23503` → **422 con mensaje genérico**
  (no usa el texto de PG); resto → 500 genérico con el detalle solo en el log
  (`main.py:102-113`). Sin mensajes crudos en este handler.
- `_sqlstate()` (`errores.py:118-120`) lee `orig.sqlstate` con fallback `pgcode`;
  `_constraint`/`_mensaje_primario` usan `diag` de forma defensiva (`getattr`).
- No existe `debug=True` en el backend (grep de `debug=True|reload=True`: 0
  resultados; `make backend` usa `uvicorn app.main:app --reload`, sin `--debug`).
  FastAPI queda con `debug=False` por defecto → sin trazas HTML en 500.
- `manejador_error_nucleo` (`errores.py:189-190`) serializa solo `codigo`,
  `mensaje`, `contexto`, `errores` — nunca `exc.__str__` de SQLAlchemy/PG.
- Orden de la pila verificado: `ExceptionMiddleware` envuelve al router; las
  excepciones de las rutas llegan a los handlers pese al middleware HTTP y a CORS.

### Hallazgo

- **SEC-017 [Baja] — `traducir_integrity_error` filtra `message_primary` de PG en
  23514 (vía servicio).**
  - Evidencia: `errores.py:165-169` usa `mensaje_db` (= `diag.message_primary`) en el
    mensaje de `ReglaNegocioViolada` para `state == "23514"`. PG emite ahí texto como
    `new row for relation "nucleo.maestros_tractos" violates check constraint "ck_..."`,
    que revela **nombres internos de schema/tabla/constraint** al cliente.
  - Ruta real: el handler global de `main.py` no llama a `traducir_integrity_error`
    para 23514 (usa mensaje genérico), pero **31 sitios de servicio** la llaman
    directamente al capturar `IntegrityError` (grep: servicio_gastos.py:215,305,384,428;
    servicio_comercial.py:237,283,452,486,820,903,996,1049; servicio_maestros.py:130,206,
    250,292,340,477; servicio_facturacion.py:614,647,687,713; servicio_expediente.py:837,
    903,1216; servicio_pod.py:271,379; servicio_bloqueos.py:277,353; servicio_rentabilidad.py:142,170;
    servicio_conductor.py:243; servicio_disponibilidad.py:978,1566). Cualquier CHECK
    violado en esos flujos llega al cliente con el texto crudo (parcial).
  - Inconsistencia adicional: vía servicio, 23514 sale como **409**
    (`ReglaNegocioViolada.status_code = 409`, `errores.py:106-108`), mientras el
    handler global lo emite como **422**. El mismo sqlstate produce dos códigos
    según la ruta. No es una fuga de datos (message_primary no incluye valores de
    fila; `message_detail` sí los tiene y **no** se usa), pero rompe la promesa de
    "sin mensaje crudo de PG".
  - Remediación (backend): en la rama 23514 de `traducir_integrity_error`, usar un
    mensaje genérico (como hace `main.py:90-101`) o mapear constraint→mensaje de
    dominio; no interpolar `mensaje_db`. Esfuerzo S.

---

## Punto 3 — `crear_promesa` (commit/rollback/traducción)

**Veredicto: CONFORME**

### Verificado 🟢

- `backend/app/nucleo/servicio_facturacion.py:708-717`: un único `session.commit()`
  dentro del `try`; `except IntegrityError` → `rollback()` + `raise
  traducir_integrity_error(exc) from exc`; `except Exception` → `rollback()` +
  `raise`. Sin doble commit ni commit parcial: `session.add` + commit atómico.
- La sesión queda usable tras el commit: SQLModel/SQLAlchemy hace autobegin, y el
  retorno llama a `self.obtener_factura(factura.id)` (`servicio_facturacion.py:717,
  383`) que re-consulta. En el camino de error no se reutiliza `factura` (objeto
  detachado) porque se re-lanza la excepción.
- Aislamiento: `_get_factura` exige `factura.empresa_id == self.empresa.id`
  (`servicio_facturacion.py:81-85`); el guard de estado (`pagada`/`anulada`) ocurre
  antes del commit (`:696-698`). `_fijar_contexto_bd()` (set_config de `auth_id`/
  `request_id`) se ejecuta antes del commit (`:699`, `:70-79`).
- El patrón es idéntico al ya revisado en `crear_nota_credito` (`:685-690`).

---

## Punto 4 — Firma mágica de uploads

**Veredicto: PARCIAL — el flujo maestros/POD es CONFORME; expediente y gastos tienen
2 hallazgos (uno potencial XSS almacenado, uno DoS de memoria).**

### Verificado 🟢 (lo que sí está bien)

- **Validación antes de cualquier escritura a Storage:** en los tres servicios la
  validación precede al upload — `servicio_expediente.py:1180` (`validar_archivo`)
  antes de `subir_archivo` en `:1189`; `servicio_gastos.py:324` antes de `:333`;
  `servicio_maestros.py:417-430` antes de `:442`; `servicio_pod.py:193-195`
  (firma y fotos) antes del bloque de subida (`:208+`). Ningún `subir_archivo` se
  ejecuta con contenido no validado.
- **Maestros:** content-type fijado por servidor `content_type_para(ext)`
  (`servicio_maestros.py:442-447`); lectura acotada por trozos
  (`api_maestros.py:232` → `storage.py:86-100`).
- **POD:** content-type derivado de `detectar_content_type` (magic bytes), nunca del
  cliente (`api_pod.py:65, 77`); firma rechazada si no es imagen (`api_pod.py:66-69`);
  las fotos además pasan `validar_archivo` en el servicio (`servicio_pod.py:194-195`).
  Si la detección devuelve `None`, se sube como `application/octet-stream`
  (`storage.py:142`) → sin render, seguro.
- **Path traversal:** cubierto. `ruta_archivo` genera `uuid4().hex + ext`
  (`storage.py:129-131`) con `ext` restringida a `ALLOWED_EXTENSIONS`
  (`storage.py:22, 108-112`); los componentes de path son UUIDs del servidor
  (`servicio_maestros.py:434-437`). No hay entrada de usuario libre en el path.
- `leer_archivo_acotado` respeta la cota: trozos de ≤64 KB con `max_bytes + 1 - total`
  y corte al exceder (`storage.py:90-99`); sin `read()` completo previo en los flujos
  que la usan (maestros y POD).

### Hallazgos

- **SEC-018 [Media] — Content-type del cliente almacenado y servido en expediente y
  gastos (contradice la propia invariante; vector de XSS almacenado condicional).**
  - Estado: causa **confirmada** 🟢; ejecución de script 🟡 (depende de que Storage
    sirva sin `nosniff`, no verificable en esta sesión).
  - Evidencia: `api_expediente.py:252` y `api_gastos.py:111` leen el upload y pasan
    `archivo.content_type` (header del multipart, controlado por el atacante) al
    servicio; `servicio_expediente.py:1189, 1198` y `servicio_gastos.py:333` lo
    guardan como metadata de Storage **y** en la columna `content_type` del registro.
    Esto contradice la invariante declarada en `storage.py:30` ("Content-type
    canónico fijado por el servidor, nunca tomado del cliente") y la comentada en
    `servicio_maestros.py:445-446`.
  - Explotación: `firma_valida` es de prefijo débil — PDF solo exige empezar con
    `%PDF` (`storage.py:47-48`) y JPEG solo 3 bytes (`storage.py:43-44`). Un archivo
    `%PDF-1.4 <img src=x onerror=...>` con nombre `x.pdf` y Content-Type declarado
    `text/html` **pasa la validación** y queda servido como HTML. Al abrir la URL
    firmada, el navegador parsea los bytes como HTML y ejecuta el script (técnica
    clásica de polyglot). Requiere usuario con permiso de subida y víctima que abra
    el enlace; alcance: usuarios que reciban/abran enlaces de la misma empresa.
  - Remediación (backend): ignorar `archivo.content_type` en estos dos flujos y fijar
    `content_type_para(ext)` (o `detectar_content_type`), igual que maestros; persistir
    el canónico. Esfuerzo S. Prueba de verificación: subir PDF válido declarando
    `text/html` → el registro y el objeto deben quedar `application/pdf`.
- **SEC-019 [Media-Baja] — Lectura completa sin cota antes de validar (memoria).**
  - Evidencia: `api_expediente.py:252` y `api_gastos.py:111` usan `await
    archivo.read()` sin límite; la cota de 10 MB de `validar_archivo`
    (`storage.py:106`) se evalúa **después** de buffering completo en RAM. Un
    multipart de cientos de MB agota memoria del worker (DoS de un solo usuario
    autenticado). Los flujos maestros/POD ya usan `leer_archivo_acotado`; estos dos
    quedaron fuera.
  - Relacionado (fuera de Ola 2, legacy): `app/api/routes/export.py:200, 237` y
    `app/api/routes/gastos.py:73` también hacen `read()` completo sin cota ni
    validación de firma; quedan bloqueados solo cuando el cutover está congelado.
  - Remediación (backend): reemplazar `read()` por `leer_archivo_acotado` en los dos
    endpoints nucleo. Esfuerzo S. Prueba: subir archivo de 11 MB → 422
    `DATOS_INVALIDOS` sin exceder memoria.

---

## Punto 5 — DEBUG por defecto

**Veredicto: CONFORME el default, con hallazgo Baja en el template de entorno.**

### Verificado 🟢

- `backend/app/core/config.py:11`: `DEBUG: bool = False` — default falso.
- Ningún test ni código depende de `DEBUG=True` (grep de `DEBUG` en `backend/`:
  solo `config.py`, `database.py:22` y `.env.example:16`).
- Sin `debug=True`/`reload=True` en código (grep 0 resultados); el Makefile usa
  `uvicorn --reload` sin `--debug`.

### Hallazgo

- **SEC-020 [Baja] — `echo` acoplado a DEBUG y `.env.example` lo activa.**
  - Evidencia: `database.py:22` `echo=settings.DEBUG` (el echo de SQL **no** está
    separado de DEBUG) y `backend/.env.example:16` dice `DEBUG=true`. Quien copie el
    template (el camino documentado en `database.py:17-19`) activa el log de **todos
    los SQL con sus parámetros bindeados** (RUT, montos, fechas) en stdout de
    desarrollo. Riesgo acotado a dev; se vuelve real si el `.env` de un entorno se
    arma desde el ejemplo.
  - Remediación: cambiar `.env.example` a `DEBUG=false` y/o separar `SQL_ECHO`
    (default False) de DEBUG en `database.py`. Esfuerzo S.

---

## NO VERIFICADO 🔴 (requiere ejecución que no pude hacer)

1. **Comportamiento HTTP real** (409 del middleware, mapeos 409/422/500, contenido de
   respuestas con CHECK violado): requiere backend `:8000` y base local; **shell
   denegado en esta sesión**, no pude levantar ni hacer requests.
2. **Servido real de Storage** (`nosniff`, content-type del objeto en la URL firmada,
   bucket `respaldos` público/privado): requiere Supabase; determina si la rama de
   **ejecución** del XSS de SEC-018 se materializa (la causa raíz ya está confirmada).
3. **Concurrencia multi-worker** del caché del cutover: no pude inspeccionar el
   comando de deploy real (el Makefile local es single-worker).
4. **Estado del repo** (`git status`/rama) y ejecución de `make unit`: preflight
   bloqueado por el mismo permiso; los hallazgos son estáticos.
5. **Rol efectivo de `DATABASE_URL` frente a RLS**: fuera del alcance de esta
   revalidación (F0); no re-verificado acá.

---

## Resumen de veredictos

| Punto | Veredicto | Hallazgos |
|---|---|---|
| 1. Fail-closed cutover | CONFORME | 2 obs. Baja (cache multi-worker; upsert de `congelar`) — SEC-016 |
| 2. SQLSTATE→HTTP | CONFORME (mapeo) | SEC-017 Baja: `message_primary` 23514 vía servicios + 409/422 inconsistente |
| 3. `crear_promesa` | CONFORME | — |
| 4. Firma de uploads | PARCIAL | SEC-018 Media: content-type del cliente (XSS almacenado condicional); SEC-019 Media-Baja: `read()` sin cota |
| 5. DEBUG | CONFORME (default) | SEC-020 Baja: `DEBUG=true` en `.env.example` + echo acoplado |
