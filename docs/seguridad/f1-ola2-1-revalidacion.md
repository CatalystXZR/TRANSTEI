# Revalidación independiente — Ola 2.1 (correcciones SEC-016…020 + POD + idempotencia)

**Fecha:** 2026-10-30 · **Rol:** `auditor-seguridad` · **Alcance:** revalidar las
correcciones aplicadas por `backend` sobre los hallazgos de
`docs/seguridad/f1-ola2-revalidacion.md`.

**Método:** lectura estática del **código actual** con cita `archivo:línea`
(nivel 1 de `AGENTS.md` §2) + lectura de las migraciones de las que dependen las
garantías. **No se ejecutó nada**: `shell` está denegado en esta sesión (verificado
con dos intentos rechazados), no hay `.venv` en el repo, y no hay backend/base
levantados. Por tanto **ninguna prueba de regresión fue ejecutada por el auditor**:
los tests del autor se leen como *intención de cobertura*, no como evidencia de
verde. No se modificó código, configuración ni permisos. No se leyeron secretos.

**Criterio:** un punto solo es CONFORME si el control existe en la capa donde se
impone y no queda ninguna ruta alcanzable que lo eluda. Los residuos se clasifican
con severidad propia; una buena práctica ausente **no** se presenta como
vulnerabilidad.

---

## Resumen de veredictos

| # | Punto | Veredicto | Residuales |
|---|---|---|---|
| 1 | SEC-018 content-type del cliente | **CONFORME** (causa raíz eliminada) | SEC-022 `ftyp`≡imagen (Baja), SEC-028 ventana `%%EOF` (Info/Baja), SEC-029 legacy sin firma (Baja) |
| 2 | SEC-019 lectura sin cota | **CONFORME** en las 4 rutas listadas | SEC-021 multipart sin tope de transporte (🟡 Media-Baja), SEC-023 fotos sin tope de cantidad (Media) |
| 3 | SEC-017 `message_primary` 23514 | **CONFORME** (fuga eliminada) | SEC-026 `constraint` aún en el body (Baja); 409 vs 422 persiste (Baja); 23502 → 500 (Baja) |
| 4 | SEC-016 `rowcount` cutover | **CONFORME** | `estado()` sigue diciendo "legacy abierto" sin fila (Baja) |
| 5 | SEC-020 `DEBUG` | **CONFORME** | `echo` sigue acoplado a `DEBUG` (Info) |
| 6 | Firma POD solo-imagen | **CONFORME** para PDF/texto | SEC-022 (mismo `ftyp`); mensaje de error omite HEIC |
| 7 | Idempotencia de documentos | **CONFORME** el diseño | SEC-024 dedup ignora `observaciones` (Baja), SEC-025 expediente sin idempotencia (Baja), concurrencia real no probada 🔴 |

**Ningún hallazgo Crítico ni Alto.** Los puntos 1–7 quedan cerrados en su causa
raíz; lo que sigue son residuos de defensa en profundidad y dos vectores de abuso
que el arreglo no cubría (SEC-021, SEC-023).

---

## Punto 1 — SEC-018: content-type fijado por el servidor

**Veredicto: CONFORME 🟢 (causa raíz eliminada)**

### Verificado

- `nucleo/api_expediente.py:254-271`: `await leer_archivo_acotado(archivo)` →
  `detectar_content_type(contenido)` → 422 si `None` → el CT detectado viaja al
  servicio. **Ya no se lee `archivo.content_type`.** Grep de `.content_type` en
  `backend/app`: 0 usos sobre `UploadFile` (solo `Documento.content_type` y
  `foto.get("content_type")`, ambos valores ya persistidos por el servidor).
- `nucleo/api_gastos.py:113-126`: idéntico patrón.
- `nucleo/servicio_expediente.py:1180,1189,1198`: re-valida con `validar_archivo`
  (extensión + firma) **antes** de `subir_archivo` y persiste el CT recibido, que
  ahora es el detectado. `nucleo/servicio_gastos.py:324,333`: igual.
- `nucleo/servicio_maestros.py:519-521`: `content_type_para(ext)` tras validar
  firma; sin cambios y correcto.
- `nucleo/storage.py:53-57,86-102`: la firma PDF exige `%PDF-` **al inicio** y
  `%%EOF` en la cola; un polyglot que empiece con HTML ya no puede declararse PDF.
  Esto cierra el escenario exacto de SEC-018 (`%PDF-1.4 <img src=x onerror=…>`).
- `api_pod.py:69-76,116-131` + `servicio_pod.py:94-106,184-199`: la firma usa
  `detectar_content_type_imagen` y `firma_content_type` se ignora en el servicio
  (`servicio_pod.py:185,295`).

### Residual (no reabre SEC-018)

- **SEC-022 [Baja] `ftyp` genérico ⇒ cualquier ISO-BMFF se acepta como imagen HEIC.**
  `storage.py:100-101` (`contenido[4:8] == b"ftyp"`) y `storage.py:75-77`
  (`.heic` en `firma_valida`) aceptan **MP4/MOV/AVIF** como `image/heic`.
  Consecuencia concreta: `validar_imagen` (`storage.py:189-199`) comprueba extensión
  ∈ {png,jpg,jpeg,webp} **y** CT detectado ∈ {jpeg,png,webp,heic}; un `video.mp4`
  renombrado `firma.png` → ext `.png` válida, CT detectado `image/heic` →
  **aceptado como firma del POD** (se guarda con extensión `.png` y CT `image/heic`).
  Impacto: no hay ejecución de código (se sirve `image/heic`, `<img>` no renderiza),
  pero se elude el control "la firma es una imagen" del hallazgo de `qa` y se debilita
  la evidencia del POD. Capas que fallan: servicio (`storage.py`), no DB.
  Remedio: validar el *brand* (`heic/heix/mif1/msf1/hevc`) en `storage.py:100-101`
  y `:75-77`, y añadir `EXTENSIONES_FIRMA` explícitas al mensaje. Prueba: subir
  `ftypisom` como `firma.png` → 422.
- **SEC-028 [Informativa→Baja] La ventana fija de 2048 B para `%%EOF` es un
  heurístico, con falso negativo y falso positivo.** (a) *Falso negativo:* un PDF
  válido con >2048 B de cola después del último `%%EOF` (firmas/appendices de
  terceros, padding de algunos pipelines) se rechaza — `storage.py:53-57`; es
  funcional, no de seguridad, y el test `test_seguridad_ola2.py:257-260` lo
  **fija como comportamiento esperado**, así que no es un accidente. (b) *Falso
  positivo:* `%%EOF` son 5 bytes que el atacante añade trivialmente, de modo que la
  marca **no acredita** que el PDF sea íntegro o válido, solo que "parece PDF".
  Esto basta para el objetivo real (canonicalizar el `Content-Type`, que es lo que
  evita la ejecución de SEC-018) pero **no debe** presentarse como validación de
  validez documental ante terceros. Recomendación: documentarlo como heurístico en
  `storage.py:24-32` y, si negocio exige validez, usar un parser PDF (dependencia
  nueva → requiere autorización).
- **SEC-029 [Baja] `POST /viajes/{id}/gastos` (legacy) sigue sin validar el
  contenido.** `api/routes/gastos.py:26-40`: valida solo la **extensión** y sube
  con `supabase.storage.upload(path, contenido)` **sin** `content-type` explícito
  ni comprobación de firma; SEC-019 se corrigió ahí (lectura acotada, `:75`), pero
  un `.pdf` con bytes arbitrarios se guarda y se entrega por URL firmada
  (`:107-124`). No hay XSS (el `Content-Type` lo infiere Storage de la extensión,
  nunca del header del cliente 🟡 — no pude leer la librería instalada), pero el
  contenido servido no está garantizado. Remedio: reutilizar `validar_archivo` +
  `content_type_para`. Esfuerzo S.

---

## Punto 2 — SEC-019: lectura acotada

**Veredicto: CONFORME 🟢 en las cuatro rutas señaladas**

- `storage.py:116-130` (`async`) y `:133-149` (`sync`): bucle de 64 KB con
  `max_bytes + 1 - total` y corte al exceder; el archivo nunca se materializa
  completo en RAM. Borde exacto correcto: `max_bytes` acepta, `max_bytes+1` corta.
- Reemplazos verificados: `api_expediente.py:255`, `api_gastos.py:114`,
  `api/export.py:202,240`, `api/routes/gastos.py:75` (usa la variante `_sync`).
- **Grep de `read()` en `backend/` → 0 `read()` de upload sin cota.** Los únicos
  `read(` restantes son los dos helpers y `conftest.py:81` (lectura de un
  `urlopen` de test).

### Residuales

- **SEC-021 [Media-Baja · potencial 🟡] El límite es de aplicación, no de
  transporte: el multipart se bufferiza antes de que el endpoint lo lea.**
  No existe ningún tope de cuerpo en el repo (grep de
  `limit-max-request|client_max_body_size|MAX_BODY` → 0 resultados;
  `requirements.txt` no fija un servidor con límite por config y `Makefile` no lo
  pasa). Con `fastapi==0.115.12` (`requirements.txt:1`) el `request.form()` de
  Starlette se resuelve **antes** de `solve_dependencies`, y `UploadFile` rueda a
  `SpooledTemporaryFile` (disco) sobre 1 MB. Si eso se confirma, un atacante —muy
  probablemente **sin token**— puede llenar el disco temporal con un POST de
  gigabytes a cualquier endpoint con `File(...)`, antes de recibir el 401/403.
  **Falta para confirmarlo:** leer `fastapi/routing.py::get_request_handler` del
  venv desplegado (no hay `.venv` en el repo) o enviar 200 MB al endpoint sin
  `Authorization` y observar que el body se consume antes del 401.
  Remedio (infra/backend): `--limit-max-request-size`, límite en el proxy, o
  rechazo por `Content-Length` en un middleware. Esfuerzo S.
- **SEC-023 [Media] Sin tope de **cantidad** de fotos en el POD.**
  `api_pod.py:77-86` y `:132-141` recorren `fotos` sin límite y acumulan **todos**
  los bytes en `fotos_leidas` (lista de tuplas) antes de llamar al servicio;
  `MAX_BYTES` solo acota **cada** foto (`api_pod.py:79,134`). Un usuario con
  `pod:escribir` (rol bajo, PWA/chofer) que envíe 100 fotos de 10 MB obliga a
  ~1 GB de RAM en un solo request → OOM del worker. No hay `MAX_FOTOS` en
  `servicio_pod.py` (grep: solo `MAX_FIRMA_BYTES`, línea 53).
  Remedio: `MAX_FOTOS` (p. ej. 10) + tope agregado, validado en el router **antes**
  de leer el resto. Prueba: 11 fotos → 422. Esfuerzo S. Capa: router.

---

## Punto 3 — SEC-017: `message_primary` de PostgreSQL

**Veredicto: CONFORME 🟢 (la fuga señalada está eliminada)**

- `errores.py:165-172`: la rama `23514` devuelve un mensaje de dominio fijo; no
  interpola `_mensaje_primario`. `_mensaje_primario` (`:129-133`) queda declarado
  como "solo para logs" y **no tiene ningún llamador** (grep: solo su definición).
- El handler global (`main.py:90-101`) ya emitía un 422 genérico; sigue igual.

### Residuales (no son SEC-017, pero están en el mismo control)

- **SEC-026 [Baja] El nombre interno de constraint sigue viajando al cliente.**
  `errores.py:171` → `contexto={"constraint": constraint}` y `to_dict()`
  (`errores.py:34-43`) incluye `contexto` en el body. Lo mismo en `:146`, `:163`,
  `:184`, `:188`. El comentario de `:166-167` afirma que el texto "revela
  schema/tabla/constraint internos" y acto seguido se envía el nombre de la
  constraint (p. ej. `ck_nucleo_...`). Divulgación de bajo valor, pero contradice
  la intención declarada. Remedio: loguear `constraint` y devolver solo un código
  de dominio. Esfuerzo S.
- **Inconsistencia 409 vs 422 (Baja, ya anotada en la revalidación anterior y no
  corregida).** El mismo `23514` sale **409** por los ~31 sitios de servicio que
  llaman `traducir_integrity_error` (p. ej. `servicio_gastos.py:305,384`;
  `servicio_pod.py:280,389`) y **422** por el handler global (`main.py:90-101`).
  Rompe el contrato de `AGENTS.md` §8 y obliga al frontend a manejar dos códigos.
- **`23502` (NOT NULL) sin mapeo específico en el traductor (Baja).**
  `errores.py:174-189`: `23502` cae en el `default` → `ErrorPersistencia` (500),
  contra `AGENTS.md` §8 ("23502 → 422, nunca 500"). No es fuga de datos, es ruido
  operacional y un 500 por error de validación.

---

## Punto 4 — SEC-016: `congelar`/`descongelar` sin fila de control

**Veredicto: CONFORME 🟢**

- `servicio_cutover.py:149-154` y `:174-179`: `if resultado.rowcount != 1:` →
  `rollback()` + `ErrorPersistencia` **antes** del `commit()`. Ya no es posible un
  "commit exitoso sin efecto". El mensaje indica la migración faltante (0014).
- `legacy_congelado()` (`:39-63`) sigue fail-closed y cachea 5 s.
- Autorización del punto de control: `/nucleo/cutover/congelar|descongelar` exigen
  `configuracion:escribir` (`api_cutover.py:24-28`), y el path queda fuera del
  bloqueo del middleware (`main.py:50-54`), como debe ser para poder descongelar.

**Residual [Baja]** `estado()` (`servicio_cutover.py:109-115`) sigue devolviendo
`legacy_escritura_congelada=False` y "se asume legacy abierto" cuando no hay fila,
mientras el middleware **bloquea**. Hoy esa combinación solo se alcanza si alguien
borra la fila; pero es el estado que `SEC-016` describía como contradictorio y la
mitad de la corrección (`congelar`) no arregla la lectura. Remedio de una línea en
`:109-115` (`congelado=True` + mensaje). Esfuerzo S.

**No re-verificado:** la ventana de 5 s con múltiples workers (observación 1 de
SEC-016) no cambió y sigue dependiendo del comando de despliegue 🔴.

---

## Punto 5 — SEC-020: `DEBUG`

**Veredicto: CONFORME 🟢**

- `backend/.env.example:16-18`: `DEBUG=false` + comentario que explica el riesgo
  (registro de cada SQL con parámetros).
- `config.py:11`: `DEBUG: bool = False` (default seguro).
- `database.py:22`: `echo=settings.DEBUG` — sin cambios.

**Residual [Informativa]** `echo` sigue acoplado a `DEBUG`: activar depuración para
ver trazas vuelve a escribir RUT/montos en stdout. Separar `SQL_ECHO` (default
`False`) era la segunda mitad de la recomendación original; no bloquea el cierre.

---

## Punto 6 — Firma del POD solo-imagen

**Veredicto: CONFORME 🟢 para el caso reportado (PDF/documento renombrado)**

- `api_pod.py:69-76`: lectura acotada a 5 MB + `detectar_content_type_imagen`; PDF
  renombrado `.jpg` → `None` → 422. `api_pod.py:120-131` igual en el `PUT`.
- `servicio_pod.py:100-106` → `validar_imagen` (`storage.py:170-199`): extensión en
  `EXTENSIONES_FIRMA` **y** CT detectado de imagen; se revalida en el servicio
  (defensa en profundidad real, no solo en el router). `firma_content_type` del
  cliente se ignora (`:185`, `:295`).
- Servido: `subir_archivo(path, contenido, ct_firma)` (`servicio_pod.py:216`) con el
  CT **detectado**; el frontend lo consume en `<img src>` (`pod-panel.tsx:215-218`),
  no en un `iframe`/`innerHTML` (grep: 0 `dangerouslySetInnerHTML`).

**Residuales:** SEC-022 (un MP4 entra como firma, ver Punto 1) y el mensaje de error
de `api_pod.py:74-76,129-131` dice "PNG, JPG, JPEG o WEBP" aunque **HEIC es
aceptado** por `CONTENT_TYPES_IMAGEN` (`storage.py:47-49`) — inconsistencia de
mensaje, no de control.

---

## Punto 7 — Idempotencia de documentos (maestros)

**Veredicto: CONFORME 🟢 en el diseño; la garantía no está probada con
concurrencia real 🔴**

### Lo que sí está

- `servicio_maestros.py:365-381`: `_bloquear_recurso` hace
  `SELECT id ... FOR UPDATE` sobre la fila del recurso **dentro de la misma
  transacción**; el lock se libera en el `commit()` de `:545`. La secuencia
  `lock → re-consultar → insertar` está en el orden correcto (`:494-507`), y el
  lock se toma **antes** de subir a Storage (`:509+`), así que el perdedor de la
  carrera no deja objeto huérfano (retorna antes del `upload`, `:505-507`).
- Con READ COMMITTED (default), la re-lectura tras adquirir el lock ve el commit del
  ganador → el segundo request devuelve `creado=False` → `api_maestros.py:246-250`
  responde **200** con el registro existente. El `201` queda solo para creación real.
- La BD **sí** tiene una defensa propia, mayor que la que el docstring sugiere:
  índices únicos parciales `uq_doc_{tracto,rampla,chofer}_vigente` sobre
  `(recurso, tipo) where es_vigente` (`0004_nucleo_operacional.sql:362-370`) y el
  trigger `fn_documento_vigente_unico` que desactiva la versión anterior
  (`:1704-1741`). Aunque el lock fallara, no pueden coexistir dos vigentes del mismo
  tipo (el INSERT daría `23505` → 409, no idempotencia, pero sin corrupción).
  El docstring de `:371` ("`nucleo.documentos` no tiene unicidad por contenido") es
  exacto: lo que no hay es unicidad por **hash**.

### ¿Cubre el caso "mismo viaje / dos recursos"?

Respuesta explícita a la pregunta del orquestador:

| Escenario | Serializado por el lock | Veredicto |
|---|---|---|
| Mismo recurso, mismo contenido, concurrente | Sí (misma fila) | Cubierto 🟢 |
| Mismo contenido, **dos recursos distintos** (tracto A vs rampla B) | **No** (filas distintas) | **No es un defecto**: `nucleo.documentos` ata cada fila a un recurso (`ck_doc_un_solo_recurso`, `0004:354-358`). Son dos documentos lógicamente distintos. |
| Mismo recurso, distinto `tipo` | No | Correcto: dos documentos distintos (la unicidad es por `tipo`). |
| Mismo contenido, distinta vigencia | No aplica | Correcto: renovación, crea fila nueva y desactiva la anterior (trigger). |
| **Documentos del expediente (viaje)** | **No hay lock ni dedup** | **Gap real → SEC-025** |

### Residuales

- **SEC-024 [Baja] La clave de deduplicación excluye `observaciones`.**
  Campos comparados: `servicio_maestros.py:396-412`; `observaciones` se persiste
  (`:541`) pero no se compara. Un reenvío con la **misma** evidencia y
  observaciones nuevas devuelve 200 con el registro viejo: el operador cree que
  guardó la anotación y se perdió en silencio. En un documento probatorio (RT,
  licencia, permiso) esto es pérdida de trazabilidad silenciosa. Remedio: incluir
  `observaciones` en la comparación (o documentar que es "first write wins").
- **SEC-025 [Baja] `nucleo.viaje_documentos` no tiene idempotencia.** El alta del
  expediente (`servicio_expediente.py:1166-1221`) inserta siempre: sin dedup, sin
  lock y sin índice único por hash (`0007_expediente.sql:181-204`). Un doble clic
  crea dos filas y dos objetos de Storage (hasta 10 MB cada uno). No duplica dinero
  ni estado, pero sí expediente y costo. Mismo patrón en
  `servicio_gastos.py:311-344` (el doble envío sobrescribe `comprobante_url` y deja
  el objeto anterior huérfano en el bucket).
- **Lock mantenido durante I/O externo [Informativa].** `_bloquear_recurso` toma el
  lock del tracto/rampla/chofer y el `upload` a Storage ocurre dentro de esa
  transacción (`:509-527`): si Storage tarda, el recurso queda bloqueado para
  cualquier otra operación que use `FOR UPDATE` sobre esa fila. Sin impacto de
  seguridad; sí de contención. Alternativa: subir primero a una ruta temporal y
  tomar el lock solo alrededor de la verificación+INSERT.

### No verificado 🔴

La serialización **no está probada con dos conexiones simultáneas**. El test del
autor (`tests/test_f1_ola2_1_cierre.py:221-241`) es un reenvío **secuencial** y
además hace `pytest.skip` si falta `NUCLEO_TEST_DATABASE_URL` (`:57-60`, `:175-176`)
— un skip no es aprobado (`AGENTS.md` §2/§7). Para cerrar del todo hace falta un
test con dos `Session` en paralelo (o `asyncio.gather` de dos requests reales) que
demuestre: 1 fila, un 201 y un 200. Sin eso, la garantía es 🟡 por diseño y 🔴 por
ejecución.

---

## Hallazgo colateral (fuera de Ola 2.1, no corregido)

- **SEC-027 [Baja] Inyección de fórmulas en los CSV exportados (CWE-1236).**
  `api/export.py:40-41` escribe los valores crudos con `csv.QUOTE_MINIMAL`; citar un
  valor **no** impide que Excel interprete `=`, `+`, `-`, `@`. Cadena concreta:
  `POST /export/import/clientes` (`:195-230`) acepta `razon_social` desde un CSV del
  usuario → `GET /export/viajes` (`:66-77`) lo emite en la columna `cliente` → el
  contador abre `viajes.csv` en Excel. Impacto: fórmula/HYPERLINK de phishing, o
  ejecución si el entorno permite DDE. Requiere cuenta con rol `admin/operacion`
  para importar y una víctima que abra el archivo. Remedio: prefijar `'` (o espacio)
  a todo valor que empiece con `=`/`+`/`-`/`@`/tab/CR. Esfuerzo S. Responsable:
  `backend` + prueba de `qa`.

---

## NO VERIFICADO 🔴

1. **Ejecución de cualquier prueba.** `shell` denegado (dos intentos rechazados),
   sin `.venv`, sin `:8000`/`:54322`/`:3000`. `make unit`, los tests de
   `test_f1_ola2_1_cierre.py` y las pruebas de integración **no** fueron ejecutados
   por el auditor; no afirmo que estén en verde.
2. **Comportamiento HTTP real** de los mapeos 409/422/500 y del 200 idempotente
   (requiere backend + base).
3. **Cabeceras de Storage** (`Content-Type` del objeto en la URL firmada,
   `X-Content-Type-Options`, bucket `respaldos` público/privado, duración real del
   enlace). Es lo único que falta para descartar del todo la **ejecución** del XSS
   de SEC-018; la causa raíz sí está cerrada.
4. **SEC-021** (multipart antes de auth): requiere leer el `fastapi/routing.py`
   instalado o un POST grande sin token.
5. **Concurrencia real** del `FOR UPDATE` (Punto 7) y de `congelar`/`descongelar`.
6. **`NUCLEO_TEST_DATABASE_URL`** presente o no: no se inspeccionó el entorno
   (no se debe imprimir su valor).
7. **`git status`/rama**: no verificable sin `shell`; no se tocó el árbol salvo este
   documento.

---

## Prioridad recomendada

**Quick wins (S, severidad Media/Baja) — responsable `backend`, prueba `qa`:**

1. **SEC-023** tope de fotos en POD (Media, router). *Hoy es el único vector de DoS
   barato con cuenta de chofer.*
2. **SEC-021** límite de cuerpo en el borde (Media-Baja): primero confirmar el orden
   `form()` vs auth; luego proxy/`--limit-max-request-size`.
3. **SEC-022** validar *brand* HEIC (Baja): cierra la elusión de "firma solo imagen".
4. **SEC-026** dejar de devolver `constraint` (Baja).
5. **SEC-016 residual**: `estado()` fail-closed coherente (Baja, 2 líneas).
6. **SEC-024** incluir `observaciones` en la clave de dedup (Baja).
7. **SEC-029** `validar_archivo` + `content_type_para` en el alta legacy de gastos
   (Baja) y **SEC-028** documentar la ventana `%%EOF` como heurístico (Info).

**Con prueba obligatoria antes de cerrar (M):**

7. Test de concurrencia real de `subir_documento` (2 conexiones) — sin esto la
   idempotencia queda 🟡.
8. **SEC-025** idempotencia del expediente de viaje (o decisión documentada de
   aceptar duplicados).
9. **SEC-027** saneo de CSV al exportar.

**Dependencias:** SEC-022 → prueba de `qa` sobre POD; SEC-023 y SEC-021 se pueden
hacer en paralelo (router vs infraestructura); el resto es independiente.

---

## Autoverificación

1. ¿Cada veredicto tiene `archivo:línea`? Sí.
2. ¿Distingo 🟢 confirmado de 🟡 potencial? Sí: SEC-021 es explícitamente 🟡 con lo
   que falta; el resto es lectura directa de código.
3. ¿Describí el control real? Sí, incluida la defensa de BD (`0004:362-370`,
   `:1704-1741`) que hace que la idempotencia no dependa solo del servicio.
4. ¿Probé variantes? Sí: verbo (`PUT /pod`, `:104-141`), rol (`pod:escribir`,
   `gastos:escribir`, `configuracion:escribir`), legacy vs núcleo (`routes/gastos.py`,
   `export.py`), y el caso dos-recursos del lock.
5. ¿Sin secretos? Sí: solo ubicaciones.
6. ¿No inflé? SEC-018/019/016/017/020 y POD se cierran como CONFORME; los residuos
   llevan severidad Baja/Informativa salvo donde hay impacto demostrable
   (SEC-023 Media).
7. ¿Listé lo no verificado? Sí, 7 puntos.
8. ¿Cada remediación tiene prueba y responsable? Sí (backend/qa/infra).
