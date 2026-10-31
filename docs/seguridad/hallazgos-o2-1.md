# Auditoría de seguridad — O2.1: manifiesto, gate y tools de lectura del agente

- **Rol:** `auditor-seguridad` (revisión independiente; no se recibió la conclusión
  del autor como hecho).
- **Fecha:** 2026-10-31.
- **Alcance:** el diff descrito en el contrato de tarea (paquete nuevo
  `backend/app/nucleo/agente/**`, las 3 pruebas nuevas y los 4 hunks de
  `permisos.py`, `main.py`, `api/router.py`, `Makefile`).
- **Contrato de referencia:** `docs/arquitectura/conector-agente-whatsapp.md`
  (§2.4, §2.5, §3, §3.3, §4.1–§4.10, §5.2–§5.4, §6.5, §7) y `AGENTS.md` §4, §7,
  §8, §9.
- **Naturaleza:** auditoría **estática**. No se ejecutó código ni SQL (ver §0.2).
- **Veredicto:** **no hay bloqueante de seguridad para desarrollar O2.2, pero sí
  una condición antes de encender el módulo** (SEC-030). No encontré bypass de
  autenticación, de tenant ni inyección SQL. Detalle en §8.

---

## 0. Método y limitación

### 0.1 Archivos leídos

| Archivo | Tipo | Lectura |
|---|---|---|
| `backend/app/nucleo/agente/{__init__,contexto,tipos,manifest,ejecutores,gate,auditoria,registry,api}.py` | nuevos | completos |
| `backend/app/nucleo/agente/tools/{__init__,despacho}.py` | nuevos | completos |
| `backend/app/nucleo/agente/manifest.json`, `tools/*.json` (3), `schemas/*.json` (6) | nuevos | completos |
| `backend/tests/test_agente_{manifest,gate}.py`, `test_agente_o2_1_integracion.py` | nuevos | completos |
| `backend/app/nucleo/permisos.py` | modificado | completo |
| `backend/app/main.py` | modificado | 210–325 (handler nuevo) + `grep` de `ProgrammingError` |
| `backend/app/api/router.py`, `Makefile` | modificados | `grep` dirigido |
| `backend/app/core/{database,contexto}.py`, `backend/app/nucleo/errores.py`, `backend/tests/conftest.py`, `backend/pytest.ini` | contexto | secciones citadas |
| `supabase/migrations/{0020,0021,0023}` | contexto (DDL del gate y RLS) | secciones citadas |

No se leyó `backend/.env` ni ningún valor de secreto. En el paquete nuevo no hay
secretos, `eval`/`exec`, import dinámico (`import_module`, `__import__`,
`pickle`), `subprocess` ni referencias a `public.` (búsqueda por patrón sobre
`backend/app/nucleo/agente/**`).

### 0.2 Limitación de método — leer antes que nada 🔴

**El permiso de `shell` fue rechazado en esta sesión** (`permission.rejected` en
`pwd`, `git status --short` y `ls`). Por lo tanto:

- **no se ejecutaron** las pruebas que pide el contrato de tarea:
  ```
  cd backend && ../.venv/bin/python -m pytest tests/test_agente_manifest.py tests/test_agente_gate.py
  NUCLEO_TEST_DATABASE_URL=… NUCLEO_DATABASE_URL=… \
    ../.venv/bin/python -m pytest tests/test_agente_o2_1_integracion.py -rs
  ```
  **Resultado: no ejecutado, no aprobado** (`AGENTS.md` §2: "un `skip` no es un
  aprobado; 'no ejecutado' no es 'pasó'").
- no hubo reproducción en PostgreSQL ni respuesta HTTP real;
- `git diff` no se pudo usar: la atribución al diff se hace contra la lista de
  archivos del contrato de tarea, y lo que no está en esa lista se marca como
  **preexistente / no atribuible**.

Todo hallazgo se sostiene sobre **lectura de código con cita `archivo:línea`**
(nivel 🟢 de `AGENTS.md` §2 = "leído en código/DB con cita"), no sobre ejecución.
Donde la diferencia entre "el código dice" y "la ejecución lo confirma" importa,
se indica en la columna de confianza.

### 0.3 Regla de atribución

Los hunks de `permisos.py`, `main.py`, `api/router.py` y `Makefile` se evalúan como
parte del cambio. `supabase/migrations/0021`, `0023` y `0020` **no** están en el
alcance entregado: se citan solo para describir el control real (qué protege la
base hoy). Los hallazgos marcados *preexistente* no se atribuyen a este diff.

---

## 1. Modelo de amenaza de este cambio

| Elemento | Contenido |
|---|---|
| **Activos** | datos de viajes de un cliente (origen/destino/fecha/estado), nombre de cliente (para el chofer y para el admin), IDs comerciales (`SQM-00001`), IDs internos (UUID), la propia ACL del contacto y el flag de módulo por empresa, y el rastro de auditoría (`acceso_otorgado`, `datos_tocados`). |
| **Actores** | (a) contacto `cliente_final` válido que intenta ver fletes de otro cliente; (b) contacto `conductor` que intenta ver viajes ajenos; (c) contacto inactivo o con OTP pendiente; (d) contacto sin ACL; (e) **el modelo/orquestador** (entrada no confiable: elige nombre de tool y parámetros, y puede ser inducido por terceros); (f) atacante con la anon key (fuera de este módulo: no hay ruta PostgREST —`anon`/`authenticated` no tienen `USAGE` sobre `nucleo` ni GRANT en las tablas del módulo, `0023:84-86`); (g) quien pueda escribir el repositorio o el sistema de archivos del contenedor; (h) proceso con el DSN `tei_app`. |
| **Límites de confianza** | runtime ↔ `Registry.invocar` (aquí sí hay validación); `Registry` ↔ PostgreSQL (`tei_app` + `app.empresa_id`); manifiesto/schemas (archivos del repo) ↔ código; envelope ↔ runtime ↔ contacto. |
| **STRIDE aplicable** | **S**poofing: el `ContextoAgente` lo construye el runtime desde la fila del contacto (fuera de este diff), el gate no acepta identidad del body. **T**ampering: el modelo intenta alterar `WHERE`/`LIMIT`/entidad → V13/V14 + SQL fijo. **R**epudiation: auditoría append-only por intento. **I**nformation disclosure: fuga de otro cliente/empresa, PII en logs/auditoría, texto crudo de PG. **E**levation: rol que sustituye ACL, flag que sustituye ACL, tool no declarada, `ejecutor` arbitrario. **D**oS: `count(*)` sin tope, nombre de tool sin cota, timeout por statement. |
| **Fuera de alcance** | runtime WhatsApp (webhook, HMAC, ASR/visión), buzón de solicitudes (O2.4) y enrolamiento/OTP (O2.3): no existen en el árbol. Los evalúo solo como consumidores del contrato que este módulo fija. |

---

## 2. Resumen

El diseño del gate es correcto en lo esencial: seis compuertas **en serie**, cada
una con cortocircuito y código propio, **deny-by-default** (`solo True autoriza`),
sin caché de ACL, sin atajo por rol y sin atajo por flag de empresa. El SQL de las
tres tools es constante y la entidad (`cliente_id` / `chofer_id`) sale del
`ContextoAgente`, nunca de la entrada; el modelo no tiene ningún parámetro que
mueva el `WHERE`. La validación de entrada es cerrada (`additionalProperties=false`
en todos los objetos) y rechaza campos de autoridad y vocabulario SQL. La
auditoría deja fila con `acceso_otorgado=false` en las denegaciones y con
`true`+`DATOS_INVALIDOS` en la entrada mal formada, y `datos_tocados` guarda IDs,
no contenido. El mapeo `42501 → 403` existe y no devuelve texto de PostgreSQL.

Lo que no cierra es **de defensa en profundidad**, no de bypass:

1. el camino de las tools abre sesiones con `get_engine_nucleo()` y **nunca pasa
   por `get_session_nucleo()`**, que es donde vive la guarda fail-closed del rol
   (`verificar_rol_nucleo`); con un DSN que apunte a un rol con `BYPASSRLS` el
   módulo del agente no devuelve 503 como el resto del núcleo (SEC-030);
2. un fallo al leer las llaves del gate (GRANT/RLS) **no se traduce en denegación
   auditada**: propaga excepción y no deja fila (SEC-031);
3. quedan dos bordes de higiene con datos controlados por el modelo o por el
   llamador (`herramienta` sin cota; `pregunta_resumida` sin redacción) y varios
   residuales informativos (SEC-032…SEC-040).

**Conteo: 1 media, 3 bajas, 7 informativas. Ninguna crítica ni alta.**

---

## 3. Tabla de hallazgos

| ID | Sev. | Área | Evidencia (`archivo:línea`) | Impacto | Remediación | Estado |
|---|---|---|---|---|---|---|
| SEC-030 | **media** | Fail-closed / rol de BD | `registry.py:449`, `gate.py:192,223`, `auditoria.py:98`, `contexto.py:159` vs `core/database.py:203-215` | La guarda que convierte "RLS inerte" en 503 no se aplica al camino de tools | `sesion_nucleo()` que ejecute la guarda; usarla en los 5 sitios (`backend`) | confirmado (código) |
| SEC-031 | **baja** | Trazabilidad | `gate.py:189-238` (sin `try/except`), `registry.py:308-321` | Un 42501 al leer llaves del gate no deja fila de auditoría y sale como excepción, no como código estable | Envolver las llaves en `_invocar` → `NO_AUTORIZADO` + `acceso=false` (`backend`) | confirmado |
| SEC-032 | **baja** | Entrada no confiable | `registry.py:282-306,491-499`; `auditoria.py:88` | `herramienta` (nombre elegido por el modelo) sin cota: se persiste y se devuelve tal cual | Validar el patrón de §3.1 y recortar a ~120 (`backend`) | confirmado |
| SEC-033 | **baja** | PII / auditoría | `registry.py:111-118`; `auditoria.py:89` | `pregunta_resumida` se guarda tal como la entrega el llamador; la redacción se delega a un runtime que no existe | Contrato de redacción + límites del parámetro (`backend`/`arquitectura`) | potencial |
| SEC-034 | informativa | Info disclosure | `manifest.py:461,466`; `registry.py:529-530`; `api.py:109-111` | `motivo` de `/estado` puede incluir la ruta absoluta del despliegue | Guardar la ruta relativa al paquete (`backend`) | confirmado |
| SEC-035 | informativa | Validación de schema | `manifest.py:619-638` | V13/V14 solo revisan propiedades de **primer nivel**; un `cliente_id` anidado pasaría | Recorrer el schema recursivamente (`backend`) | confirmado (sin impacto hoy) |
| SEC-036 | informativa | Fail-closed | `registry.py:526-530` | `cargar_registry` solo captura `ErrorManifiesto`; otra falla da 500 en `/estado` | `except Exception` acotado a la carga → `valido=false` (`backend`) | potencial |
| SEC-037 | informativa | Logs | `auditoria.py:103-113` | `logger.exception` bajo `except Exception` puede arrastrar el mensaje de PG | Loguear `tipo` + `sqlstate` como en `main.py:303-307` (`backend`) | potencial |
| SEC-038 | informativa | Logs (preexistente) | `main.py:262-266` | `%r` registra SQL y parámetros ligados, contra la regla del handler nuevo | Misma política que `main.py:303-307` (`backend`) | confirmado, no atribuible |
| SEC-039 | informativa | Arquitectura (preexistente) | `0021:855-860`, `0023:253`; `core/database.py:183-200` | El rol `tei_app` puede escribir identidad, ACL y flag que el gate consume | Decidir rol del runtime antes de O2.4 (`datos`/`arquitectura`) | confirmado, no atribuible |
| SEC-040 | informativa | Contrato §2.6.4 | `registry.py:214-215`; `gate.py:198-209` | Sin `modulos_empresa` el registry reporta 3 tools "cargadas" (la ejecución sí queda cerrada) | Alinear §2.6.4 con §6.5 o condicionar el conteo (`backend`) | confirmado |

---

## 4. Detalle de hallazgos

### SEC-030 [media] El camino de las tools evita `get_session_nucleo()` y, con él, la guarda fail-closed del rol
- **Estado:** confirmado · **Confianza:** alta (lectura de código) · **Explotabilidad:** requiere condiciones (DSN mal configurado) · **Alcance:** todas las empresas · **Esfuerzo:** S
- **Evidencia:**
  - `backend/app/core/database.py:210-215`: `get_session_nucleo()` es el **único**
    lugar que llama `_asegurar_rol_nucleo(engine)` → `verificar_rol_nucleo(...)`,
    la guarda que devuelve 503 cuando el DSN explícito conecta con un rol
    `BYPASSRLS` (`database.py:146-180`).
  - El módulo nuevo abre sesiones con `Session(get_engine_nucleo())` en **cinco**
    sitios y en ninguno usa `get_session_nucleo`:
    `agente/gate.py:192`, `agente/gate.py:223`, `agente/registry.py:449`,
    `agente/auditoria.py:98`, `agente/contexto.py:159`.
  - `grep -rn "get_engine_nucleo()" backend/app` devuelve exactamente esas cinco
    apariciones más la definición y `get_session_nucleo` en `core/database.py`
    (`:183`, `:212`): fuera de `core/database.py`, **solo** el paquete nuevo abre
    el engine directamente. El resto de `app/nucleo/*` usa la dependencia
    `get_session_nucleo` (p. ej. `api.py:49`, `deps.py:54`).
  - El contrato lo pide explícitamente: §4.4 "todas las consultas se ejecutan con
    `get_session_nucleo` (rol `tei_app`, sin `BYPASSRLS`)"; §9.1 B4 exige
    verificar el rol efectivo del entorno de ejecución.
- **Escenario:** un despliegue con `NUCLEO_DATABASE_URL` **explícito** apuntando a
  un rol con `rolbypassrls=true` (en el Supabase local, `postgres`; ver
  `test_agente_o2_1_integracion.py:632-633`, que asume que `postgres` tiene
  `BYPASSRLS`). Con DSN explícito `fallback=False` y `verificar_rol_nucleo` lanza
  503 (`database.py:167-180`): cualquier endpoint `/nucleo/*` queda fuera de
  servicio. Pero el runtime del agente sigue invocando tools, porque nunca pasa
  por esa guarda: RLS queda inerte y el aislamiento depende **solo** del
  `where empresa_id = :empresa_id` explícito de cada consulta
  (`tools/despacho.py:69,151,238`, `gate.py:47,57,68`). Hoy esos filtros están en
  las seis consultas, así que **no hay fuga demostrable**; el hallazgo es que la
  capa que debía fallar cerrado no se ejecuta en este camino (el caso *fallback*,
  `NUCLEO_DATABASE_URL` ausente, ya es una desviación declarada y avisada en
  `database.py:26-35,159-166`).
- **Impacto:** la primera consulta futura que olvide el filtro explícito (o que
  confíe en RLS) fuga entre empresas sin ninguna alarma; además el módulo opera
  en un estado que el resto del núcleo rechaza, lo que rompe la expectativa de que
  "si el núcleo arrancó, RLS está vigente".
- **Capas que fallan:** servicio (apertura de sesión) y arranque (guarda de rol).
  No falla la base: RLS está bien definida (`0020:293`, `0023:239-246`).
- **Remediación (`backend`):** añadir un context manager `sesion_nucleo()` en
  `core/database.py` que ejecute `_asegurar_rol_nucleo(...)` y abra la `Session`, y
  usarlo en los cinco sitios (o exponer una verificación pública e invocarla al
  construir el registry, una vez por proceso).
- **Prueba de verificación:** con `NUCLEO_DATABASE_URL` **explícito** apuntando a
  un rol `rolbypassrls=true`, `Registry.invocar(...)` debe devolver error y **no**
  datos, igual que `/nucleo/*` responde 503. Hoy `invocar` no consulta el rol, así
  que la prueba falla antes del arreglo y pasa después. Residual de cobertura: la
  prueba actual `test_42501_es_programming_error_y_se_traduce_a_403:697-702` se
  **salta** si el rol no es `tei_app`, de modo que la suite no toca este caso.
- **Depende de:** nada.

### SEC-031 [baja] Un fallo al leer las llaves del gate no produce denegación auditada
- **Estado:** confirmado · **Confianza:** alta · **Explotabilidad:** requiere condiciones (GRANT/RLS roto) · **Alcance:** una empresa / todas · **Esfuerzo:** S
- **Evidencia:** `gate.py:189-210` y `gate.py:212-238` capturan **solo** `42P01`
  (`modulos_empresa` ausente). Cualquier otro `ProgrammingError` (típicamente
  `42501` por GRANT revocado o `FORCE ROW LEVEL SECURITY` sin política) sale de
  `autorizar` → sale de `registry._invocar` (la llamada al gate en
  `registry.py:308-313` **no** está dentro del `try` de `registry.py:349`) → el
  runtime recibe una excepción, **sin envelope** y **sin fila** en
  `auditoria_consultas_agente`.
- **Escenario:** tras una migración que olvide el `GRANT SELECT` a `tei_app` sobre
  `nucleo.permisos_contacto`, cada intento de tool revienta con 42501: no hay
  fila de auditoría (ni otorgada ni denegada) y no hay `NO_AUTORIZADO` estable.
  Falla cerrado (no se entrega dato), pero **se pierde la trazabilidad**, que es
  justo lo que §7.4 exige ("una fila cada uno").
- **Impacto:** un incidente de configuración deja de ser visible en la vista de
  auditoría y aparece como error interno del runtime. Contradice §4.6 (`42501 →
  NO_AUTORIZADO`) y §7.2.
- **Capas que fallan:** servicio (manejo de error del gate).
- **Remediación (`backend`):** envolver la lectura de llaves en `_invocar` y
  mapear con `clasificar_error` a `NO_AUTORIZADO` + `_denegar(acceso=False)`
  (nunca reintentable). Mantener `42P01 → MODULO_INACTIVO`.
- **Prueba de verificación:** revocar `SELECT` a `tei_app` sobre
  `permisos_contacto` en `tei_test` (y restaurarlo en el `finally`) y afirmar
  `error.codigo == "NO_AUTORIZADO"` **y** una fila nueva con
  `acceso_otorgado=false` para el `contacto_id`. Antes del arreglo el test falla
  con excepción/no-fila.
- **Depende de:** nada.

### SEC-032 [baja] `herramienta` (nombre elegido por el modelo) no tiene cota de longitud
- **Estado:** confirmado · **Confianza:** alta · **Explotabilidad:** requiere que el modelo emita un nombre anómalo · **Alcance:** una empresa · **Esfuerzo:** S
- **Evidencia:** `registry.py:282-306` usa el `nombre` recibido **sin validarlo ni
  recortarlo**; `_denegar` lo pasa a `_auditar(herramienta=herramienta)`
  (`registry.py:491-499`), `auditoria.registrar_consulta` lo escribe tal cual
  (`auditoria.py:88`, columna `text` sin CHECK, `0021:686`) y `_envelope_error` lo
  devuelve en `meta.herramienta` (`registry.py:165`). Lo único acotado es
  `pregunta_resumida` (`_recortar`, 500 caracteres, `auditoria.py:33,51-54`).
- **Escenario:** un nombre de tool de 1 MB (DI manipulado, prompt injection que
  haga al modelo emitir un nombre basura) genera una fila de auditoría enorme y
  un envelope enorme. Repetido, infla la tabla append-only (que **no se puede
  borrar**: `0021:719-735`) y el log de respuestas.
- **Impacto:** DoS de almacenamiento de bajo impacto sobre una tabla que por
  diseño no admite `DELETE`; ruido en la vista O4.5.
- **Capas que fallan:** servicio (validación de entrada del registry).
- **Remediación (`backend`):** validar `nombre` contra el patrón de §3.1
  (`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`) antes de auditarlo; si no cumple, usar
  `"desconocida"` truncado. Recortar `herramienta` a ~120 caracteres en
  `registrar_consulta` como segunda capa.
- **Prueba de verificación:** `invocar("X"*10000, {}, ctx)` → error y fila con
  `length(herramienta) <= 120`.
- **Depende de:** nada.

### SEC-033 [baja] `pregunta_resumida` se persiste sin redacción; la única redacción es la del llamador
- **Estado:** potencial · **Confianza:** media · **Explotabilidad:** requiere un runtime que pase texto libre · **Alcance:** una empresa · **Esfuerzo:** S
- **Evidencia:** `registry.py:111-118`: si el llamador pasa `explicita`, se guarda
  `explicita[:500]` sin más filtro; si no, se guardan solo las **claves** de la
  entrada (correcto, sin valores). `auditoria.py:89` la persiste en
  `pregunta_resumida`. El contrato §7.3 exige "intención + extracto **redactado**;
  nunca el audio/foto", pero esa redacción se asigna al runtime (O3), que **no
  existe en el árbol**; hoy no hay ningún control que la imponga.
- **Escenario:** el runtime pasa el texto crudo del mensaje ("mi RUT es…, la
  factura por $4.500.000…") a `invocar(..., pregunta_resumida=texto)`; queda
  escrito en una tabla append-only que no se puede purgar (D-17 abierta, §9.6) y
  que leerá O4.5.
- **Impacto:** PII/financiero persistido en el log de auditoría, sin posibilidad de
  borrado por diseño. No es explotable por el contacto (el contacto no controla
  este parámetro directamente), pero sí acumulable por uso normal.
- **Capas que fallan:** servicio (contrato del parámetro) y contrato del runtime.
- **Remediación (`backend` + `arquitectura`):** (a) que `invocar` **no** acepte
  texto libre: reciba una intención enumerada y un extracto ya redactado con
  longitud y charset acotados; (b) documentar en el contrato del runtime que la
  redacción es obligatoria y con qué regla; (c) prueba de regresión con un texto
  que contenga dígitos de RUT/teléfono y afirme que no aparecen en la fila.
- **Prueba de verificación:** invocar con `pregunta_resumida="+56912345678"` y
  afirmar que la fila no contiene el número.
- **Depende de:** O3 (contrato del runtime).

### SEC-034 [informativa] `/nucleo/agente/estado` puede exponer la ruta absoluta del despliegue
- **Estado:** confirmado · **Confianza:** alta · **Evidencia:** `manifest.py:457-467`
  construye `ErrorManifiesto("V1", str(ruta), …)` con la ruta **absoluta**;
  `registry.py:529-530` la guarda en `motivo` y `api.py:109-111` la devuelve en
  `manifest.motivo`.
- **Impacto:** un `admin` de la empresa ve `…/app/app/nucleo/agente/manifest.json`
  cuando el manifiesto está roto. Sin secretos ni contactos (lo verifiqué: el
  endpoint solo devuelve versión, `schema_di`, motivo, flag de **su** empresa,
  conteo por componente, nombres de migración y tablas faltantes). Informativa por
  ser información de despliegue a un rol ya privilegiado.

### SEC-035 [informativa] V13/V14 solo inspeccionan el primer nivel del schema de entrada
- **Estado:** confirmado (sin impacto con los 3 descriptores actuales) · **Evidencia:**
  `manifest.py:619-638` (`propiedades = set(schema_entrada.get("properties", {}))`)
  frente a `manifest.py:160-161`, que sí recorre los objetos anidados para V13.
- **Impacto:** un schema futuro con `properties.items.items.properties.cliente_id`
  (o `sql`) pasaría V14/V13 aunque §3.3.2/§3.3.3 lo prohíben. Hoy no hay objetos
  anidados en ninguna entrada y los ejecutores usan `contexto.entidad_id`
  (`tools/despacho.py:81-89,163-172`), así que no hay ruta de explotación.
- **Remediación (`backend`):** recorrer recursivamente el schema en
  `_prohibidos_en_entrada` (o aplicar la prohibición dentro de `_validar_nodo`).

### SEC-036 [informativa] `cargar_registry` solo captura `ErrorManifiesto`
- **Estado:** potencial · **Evidencia:** `registry.py:526-530`. `cargar_modulo`
  envuelve la mayoría de las fallas (OSError/JSONDecodeError → `manifest.py:457-467`;
  `ValidationError` → `:650-667`; schemas → `:610-616`), pero no todas: un
  `RecursionError` por un schema anidado en exceso o cualquier `TypeError`
  inesperado **no** se convierte en `Registry(valido=False)`.
- **Impacto:** `/nucleo/agente/estado` devolvería 500 (no 200 con `valido=false`
  como exige §2.5) y `invocar` propagaría excepción en vez de `MODULO_INACTIVO`.
  Requiere editar archivos del repositorio/paquete, es decir, una capacidad que ya
  implica compromiso; por eso es informativa.
- **Remediación:** `except Exception` **acotado a la carga** con log estructurado y
  `valido=False` (no en el camino de ejecución).

### SEC-037 [informativa] `logger.exception` bajo `except Exception` en auditoría
- **Estado:** potencial · **Evidencia:** `auditoria.py:103-113`.
- **Impacto:** el mensaje de una excepción de psycopg puede incluir valores de la
  clave (`Key (empresa_id, contacto_id)=(…) is not present in table …`) o el valor
  de un cast fallido. Hoy los parámetros son UUIDs y textos de configuración —sin
  contenido de negocio ni teléfono—, así que el residuo es identificadores de
  tenant en el log. Contradice la regla que el propio cambio aplica en
  `registry.py:358-367` y `main.py:300-302` ("nunca `repr(exc)`").
- **Remediación:** loggear `type(exc.orig).__name__` + `sqlstate` (mismo patrón que
  `main.py:303-307`).

### SEC-038 [informativa · preexistente, no atribuible] `manejador_integrity_error` registra el `repr` del error
- **Estado:** confirmado · **Evidencia:** `main.py:262-266`
  (`logger.error("IntegrityError sin traducción específica (sqlstate=%s): %r", state, exc)`).
- **Impacto:** en SQLAlchemy el `repr` de un `StatementError` incluye el SQL y los
  parámetros ligados (`registry.py:358-360` lo dice explícitamente). Es
  exactamente lo que el handler nuevo evita (`main.py:300-302`). No es de este
  diff (el hunk nuevo es el import de `ProgrammingError` y el handler de
  `main.py:276-314`), pero vive en el mismo archivo y en el mismo tipo de ruta.
- **Remediación (`backend`):** misma política que el handler nuevo
  (`tipo(exc.orig).__name__` + `sqlstate`).

### SEC-039 [informativa · preexistente, no atribuible] El rol del agente puede escribir las tres llaves del gate y la identidad
- **Estado:** confirmado · **Evidencia:** `supabase/migrations/0021:855-860`
  (`grant select, insert, update` sobre `contactos_whatsapp` y
  `permisos_contacto` a `tei_app`) y `0023:253` (`select, insert, update` sobre
  `modulos_empresa`). El runtime del agente usa ese mismo rol
  (`core/database.py:183-200`). La propia prueba de integración demuestra la
  capacidad: crea/edita contactos con `rol`, `cliente_id` y
  `otp_estado='verificado'` y escribe ACL y flag como `tei_app`
  (`test_agente_o2_1_integracion.py:88-192,279-346`).
- **Impacto:** hoy **ninguno explotable**: no hay tool de escritura, el SQL es fijo
  y V13/V14 impiden que el modelo aporte fragmentos. El riesgo aparece en O2.2+:
  si una tool de escritura, o una inyección en un ejecutor, corre con este rol,
  puede autoconcederse ACL, marcarse OTP verificado o encender el módulo. El gate
  "impone la ausencia" (`0021:236-241`) pero lee datos que su propio rol puede
  cambiar.
- **Remediación (`datos` + `arquitectura`):** decidir si el runtime del agente usa
  un rol distinto (solo `select` sobre las llaves y `insert` en auditoría) cuando
  existan tools de escritura; o separar el proceso. No es un cambio de este diff.

### SEC-040 [informativa] Con el flag de empresa ausente, el registry reporta 3 tools "cargadas"
- **Estado:** confirmado · **Evidencia:** `registry.py:214-215` (`tools_cargadas =
  len(self._descriptores)`) no consulta la base; `gate.py:198-209` cierra la
  ejecución devolviendo `None` → `MODULO_INACTIVO` (`gate.py:147-154`).
- **Impacto:** ninguno de seguridad (no se ejecuta nada), pero §2.6.4 dice "el
  runtime no debe registrar tools si falta la tabla del gate". La lectura literal
  se cumple en la ejecución, no en el conteo. `GET /estado` es coherente con §6.5
  (que separa `tools.cargadas` de `faltantes`). Se registra para que la
  discrepancia sea explícita y no se "arregle" cambiando el contrato después.

---

## 5. Respuestas a las preguntas del contrato

**Q1. ¿Puede un `cliente_final` obtener viajes de otro `cliente_id` de la misma
empresa?** 🟢 **No, por la entrada.** El `WHERE` de C1 fija
`v.empresa_id = :empresa_id and v.cliente_id = :cliente_id`
(`tools/despacho.py:69-70`) y `:cliente_id` se toma de `contexto.entidad_id`
(`tools/despacho.py:86-89`), no de `entrada`. Los únicos filtros opcionales son
`estado`, `desde` y `hasta`, elegidos por **clave** de un diccionario cerrado
(`despacho.py:73-77,83-85`); ningún iterador de la entrada llega al SQL. Además:
(a) si un cambio futuro declarara `cliente_id` en el schema de entrada de una tool
`alcance=propio`, V14 invalida el manifiesto (`manifest.py:633-638`), es decir, el
módulo se queda sin tools; (b) con el schema actual (cerrado), enviarlo produce
`DATOS_INVALIDOS` por `additionalProperties=false` (`manifest.py:296-299`), que es
exactamente lo que prueba `test_entrada_invalida_audita_acceso_otorgado`
(`test_agente_o2_1_integracion.py:572-581`); (c) `_where_c1` falla cerrado si el
rol no es `cliente_final` o falta la entidad (`despacho.py:81-82`). K1 fuerza
`v.chofer_id` (`despacho.py:151-152`); A1 es de empresa y solo para `admin`
(`despacho.py:264-265`). Confianza alta. **Limitación:** no lo reproduje en base
(shell denegado); la prueba de integración que lo verifica
(`test_c1_devuelve_solo_los_fletes_del_cliente:486-511`) **no se ejecutó**.

**Q2. ¿Puede el modelo introducir SQL o alterar `WHERE`/`LIMIT`?** 🟢 **No.** El
texto SQL es constante (`despacho.py:60-71,139-153,226-241`) y se compone con
fragmentos de un `dict` cerrado indexado por clave presente (`despacho.py:73-77`);
todos los valores viajan como parámetros ligados. `LIMIT` sale de
`_limite()` = `max(1, min(int(pedido), max_filas))` (`registry.py:101-108`) y el
schema acota `limite` a `1..max_filas` (`schemas/despacho.mis_fletes.entrada.json:28`,
`schemas/despacho.mis_viajes_asignados.entrada.json:28`,
`schemas/despacho.viajes_del_dia.entrada.json:27`).
`estado` se valida contra un `enum` de 14 valores antes de llegar al `cast`
(`manifest.py:283-285`), así que un valor fuera del enum de PG es inalcanzable.
V13 rechaza vocabulario SQL en el schema de entrada (`manifest.py:628-632`) y
`_validar_nodo` rechaza cualquier *keyword* no soportada —incluido `$ref` anidado—
(`manifest.py:143-149`). `ejecutor` está en una allow-list de código
(`ejecutores.py:32-38`), no es un import path (`manifest.py:578-581`). Confianza
alta, verificado por lectura.

**Q3. Orden del gate: ¿alguna llave se puede saltar? ¿rol sustituye ACL? ¿flag
sustituye ACL? ¿caché que sobreviva al request?** 🟢 El orden es
manifiesto → identidad → módulo → rol → ACL componente → ACL variable
(`gate.py:128-183`), en serie, con `return` en cada fallo: no hay forma de llegar
a la llave 5 sin pasar la 4. `solo True autoriza` (`is not True` en
`gate.py:147,165,174`), así que `None`/`False`/ausente son lo mismo. El rol se
evalúa **antes** que la ACL (`gate.py:156`) y no hay rama por rol; el flag de
empresa (`gate.py:147`) no exime de la ACL. No hay caché: `autorizar` recibe una
`FuenteGate` y consulta en cada invocación; `FuenteGateBD` abre sesión nueva cada
vez (`gate.py:189-238`). Lo único cacheado por proceso es el **manifiesto**
(`registry.py:514-533`), que no es autorización. `tools_para_rol` es declarativo y
no se usa para autorizar (`registry.py:224-229`, §4.9). Verificado además por
`test_agente_gate.py:136-202` (rol antes que ACL, admin sin ACL denegado).

**Q4. `42501` → 403 y sin texto crudo de PG.** 🟢 En HTTP: `main.py:276-299`
responde 403 `ACCESO_DENEGADO` con mensaje fijo; el resto de `ProgrammingError`
→ 500 genérico sin `repr` (`main.py:300-314`). En el camino de tool:
`clasificar_error` mapea `ProgrammingError`+`42501` a `NO_AUTORIZADO`
(`registry.py:92-93`) y el envelope no incluye mensajes de PG (`registry.py:142-169`).
Coincide con §4.6/B2. ⚠️ Dos matices: (a) ese mapeo solo cubre el **ejecutor**, no
las lecturas del gate (SEC-031); (b) la fila de auditoría de ese caso queda con
`acceso_otorgado=true` (`registry.py:368-376`), coherente con §7.5 ("el gate
autorizó, la tool falló") pero fácil de malinterpretar en O4.5.

**Q5. ¿Alguna ruta escribe en log parámetros ligados, SQL o datos personales?** 🟢
En el módulo nuevo, no encontré ninguna: `registry.py:328-330` registra solo el
campo; `registry.py:356` (bug no-SQL) usa `logger.exception` sin `locals` y sin
`repr` del error; para errores de base registra `codigo`, `sqlstate` y el **tipo**
(`registry.py:361-367`), con el comentario explícito de no usar `repr`;
`registry.py:388-390` registra el `str` de `EntradaInvalida`, que solo contiene
nombres de campo y constantes del schema; `gate.py:229-234` registra
`contacto_id`/`componente`/`variable` (identificadores internos, ya presentes en la
tabla de auditoría); `contexto.py:110` devuelve un mensaje de error que **no**
incluye el teléfono. El handler nuevo también es limpio. Residuales: SEC-037
(`auditoria.py`) y SEC-038 (preexistente, `main.py`).

**Q6. Auditoría: ¿denegación con `acceso_otorgado=false`? ¿entrada inválida con
`true`? ¿`datos_tocados` con IDs?** 🟢 Las tres. `_denegar` audita con
`acceso=False` y `respuesta=decision.respuesta` (`registry.py:482-507`); el camino
de entrada inválida audita con `acceso=True` y `respuesta="DATOS_INVALIDOS"`
(`registry.py:325-346`), igual que §7.5. `datos_tocados` = `{ids[:50], total,
_meta{tool_version, schema_di}}` (`auditoria.py:57-66`) y en C1/K1/A1 los `ids`
son `id_comercial_flete` o UUID (`despacho.py:129-131,219,311`): identificadores,
no contenido. La tabla es append-only por trigger (`0021:719-735`) y `tei_app` no
tiene `UPDATE`/`DELETE` (`0021:863-864`). Si la auditoría falla en una **lectura**,
no se entrega dato (`AUDITORIA_FALLIDA`, `registry.py:423-431`) — control
verificado y bien pensado.

**Q7. Fail-closed con manifiesto inválido o sin `nucleo.modulos_empresa`.** 🟢/🟡
Manifiesto inválido: `cargar_registry` no propaga (`registry.py:526-530`),
`_invocar` devuelve `MODULO_INACTIVO` para **cualquier** nombre
(`registry.py:273-288`) y `/estado` responde 200 con `valido=false`
(`api.py:106-118`). Tabla ausente: `42P01` → `None` → `MODULO_INACTIVO`
(`gate.py:198-209,147`); `/estado` la declara en `faltantes` (`api.py:75-98`). 🟡
El borde es SEC-036 (solo se captura `ErrorManifiesto`) y la letra de §2.6.4
(SEC-040). **No ejecutado**: no verifiqué el 200 real ni el log
`agente.manifest_invalido`.

**Q8. `GET /nucleo/agente/estado`: ¿requiere permiso? ¿expone secretos, teléfonos
o contactos?** 🟢 Requiere `agente:buzon` vía `requiere_permiso`
(`api.py:101-105`), y ese permiso solo lo tiene `admin` hoy
(`permisos.py:18,49,63-67`; `gerente` está excluido, más estricto que el default
del contrato). No expone secretos, teléfonos ni la lista de contactos: devuelve
`modulo_id`, versión/`schema_di`/motivo del manifiesto, el flag de **su** empresa
(consulta con `empresa_id` explícito + RLS, `api.py:86-98`), conteo de tools por
componente, nombres de migración requerida y tablas faltantes. Único residuo:
SEC-034 (ruta absoluta en `motivo`). **No verificado por HTTP** (sin shell).

**Q9. ¿`skip`/`xfail`/`except` amplio/pruebas desactivadas/aserciones vacuas?** 🟢
En las tres pruebas nuevas no hay `xfail`, ni `skipif`, ni `pytest.mark.skip`
incondicional, ni aserciones que no puedan fallar. Los cuatro `pytest.skip` del
archivo son **explícitos y con motivo** (falta `NUCLEO_DATABASE_URL`
`:66-72`; seed sin viajes `:222-223`; menos de dos empresas `:229-230`; rol
distinto de `tei_app` `:697-702`), igual que el de `conftest.py:63-71`. El fixture
`escenario` aborta si el teléfono fijo pertenece a otra empresa (falla ruidosa, no
silenciosa, `:104-109`). Las mutaciones de `test_agente_manifest.py` hacen
`pytest.raises(ErrorManifiesto)` y además comparan el número de regla, así que un
manifiesto que "no se mutó" hace fallar la prueba en vez de pasar vacía. Riesgo
real: **cobertura**, no aserción falsa — ver §7.

---

### 5.1 Matriz de casos adversariales (diseñados; ejecución 🔴)

Complementa las respuestas Q1–Q9 con el catálogo de `adversarial-testing` (límites, estados, actores, tiempo).
La columna "estático" es lo que se puede afirmar leyendo el código; **ninguno se
ejecutó** (§0.2), así que la columna de ejecución queda 🔴 y el caso sirve como
guion para `qa`.

| # | Escenario | Esperado | Estático | Ejecución |
|---|---|---|---|---|
| A1 | `cliente_final` de A envía `{"cliente_id": <B>}` a `despacho.mis_fletes` | `DATOS_INVALIDOS`, `acceso_otorgado=true` | 🟢 `manifest.py:296-299`, `registry.py:325-346` | 🔴 |
| A2 | `limite=1000000` / `limite=0` / `limite="50;…"` | `DATOS_INVALIDOS` (máx. 50) | 🟢 `schemas/…mis_fletes.entrada.json:28`, `registry.py:101-108` | 🔴 |
| A3 | `desde="2026-10-31T10:00:00"` (sin zona) | `DATOS_INVALIDOS` | 🟢 `manifest.py:256-263` | 🔴 |
| A4 | `conductor` con ACL de `despacho` pide la tool de cliente | `NO_AUTORIZADO:rol` (la ACL no se consulta) | 🟢 `gate.py:156-163` | 🔴 |
| A5 | `admin` con ACL vacía | `NO_AUTORIZADO:componente` | 🟢 `gate.py:165-172`; `test_agente_gate.py:194-202` | 🔴 |
| A6 | contacto con `otp_estado='pendiente'` y ACL completa | `NO_AUTORIZADO:identidad` | 🟢 `gate.py:137-145` | 🔴 |
| A7 | contacto de A resuelto con `empresa_id` de B | 0 filas → `None` (mensaje genérico) | 🟢 `contexto.py:66-80,170-171` | 🔴 |
| A8 | `invocar("despacho.inventada")` | `TOOL_DESCONOCIDA` + fila con `componente=agente` | 🟢 `registry.py:290-306` | 🔴 |
| A9 | manifiesto con `"ejecutor": "os_system"` | manifiesto inválido → 0 tools → `MODULO_INACTIVO` | 🟢 `manifest.py:578-581`, `registry.py:273-288` | 🔴 |
| A10 | schema de entrada con `"sql"` o `"where"` | manifiesto inválido (V13) | 🟢 `manifest.py:628-632`; `test_agente_manifest.py:265-271` | 🔴 |
| A11 | manifiesto con `"$ref": "../../etc/passwd"` | manifiesto inválido (V5), sin leer el archivo | 🟢 `manifest.py:478-496` | 🔴 |
| A12 | revocar `permitido` entre dos invocaciones | la segunda deniega (sin caché) | 🟢 `gate.py:212-238` (sesión nueva por llamada) | 🔴 |
| A13 | `42501` al leer `permisos_contacto` | hoy: excepción, sin fila (SEC-031) | 🟢/🟡 `gate.py:212-238` | 🔴 |
| A14 | nombre de tool de 1 MB | fila de auditoría y envelope gigantes (SEC-032) | 🟢 `registry.py:282-306` | 🔴 |
| A15 | `NUCLEO_DATABASE_URL` explícito a rol `BYPASSRLS` | `/nucleo/*` 503 y las tools sin datos (hoy: las tools siguen) | 🟢/🟡 SEC-030 | 🔴 |

---

## 6. Controles verificados 🟢

1. **Deny-by-default de punta a punta.** `is not True` en las tres llaves
   (`gate.py:147,165,174`) + `descriptor.roles` obligatorio y no vacío
   (`manifest.py:423,568-572`). Una fila `permitido=false` y la ausencia de fila
   producen la misma denegación (probado en `test_agente_gate.py:160-191`).
2. **Sin atajo por rol ni por empresa.** `test_admin_sin_acl_no_ve_nada`
   (`test_agente_gate.py:194-202`) y `test_rol_equivocado_no_usa_acl`
   (`test_agente_o2_1_integracion.py:661-668`).
3. **Entidad forzada desde el contexto.** C1 usa `contexto.entidad_id`
   (`despacho.py:81-89`), K1 ídem (`:163-172`); si falta, lanza antes de consultar.
4. **SQL constante y parametrizado** en las tres tools y en las tres consultas del
   gate (`gate.py:43-72`); sin `f-string`, `text()` dinámico, `ORDER BY` de entrada
   ni `LIKE`.
5. **Manifiesto cerrado y fail-closed.** `extra=forbid` + `strict`
   (`manifest.py:351-354`), V1–V16 implementadas (`manifest.py:499-607`), y
   `$ref` resuelto con rechazo de `..`, rutas absolutas y salida del paquete
   (`manifest.py:478-496`).
6. **Proyección exacta.** La salida se valida contra el schema antes de devolverla
   (`registry.py:385-406`); C1 no devuelve costo, margen, patentes ni chofer
   (`despacho.py:60-71,118-128`), y la prueba lo afirma sobre el JSON serializado
   (`test_agente_o2_1_integracion.py:509-511`).
7. **Timeout por statement.** `set_config('statement_timeout', …, true)` con el
   `timeout_ms` validado 100–5000 (`registry.py:62,451`; `manifest.py:582-585`), y
   `57014 → TIMEOUT_TOOL` (`registry.py:94-95`).
8. **`max_filas` como tope duro**, nunca ampliable desde la entrada
   (`registry.py:101-108`; `test_agente_gate.py:249-256`).
9. **Auditoría append-only, una fila por intento, con `datos_tocados` = IDs**
   (`auditoria.py:57-66`; `0021:714-716,863-864`) y **sin datos si la auditoría
   falla** en lectura (`registry.py:423-431`).
10. **`42501` ya no es 500** en HTTP (`main.py:276-299`), y no filtra el mensaje de
    PostgreSQL (contraste con SEC-017 ya corregido en `errores.py:165-172`).
11. **`gerente` excluido de `PERMISOS_AGENTE`** (`permisos.py:63-67`): más
    restrictivo que heredar por `set(TODOS_LOS_PERMISOS)`; coherente con AB-02
    abierta.
12. **Sin secretos ni rutas de ejecución en el paquete nuevo**: `grep` de
    `secret|password|apikey|api_key|token|anon_key|service_role|sk-` → **1**
    coincidencia, el docstring de `api.py:9` ("No expone secretos…"); ningún
    valor. `grep` de `public.|open(|subprocess|eval(|exec(|import_module|
    __import__|pickle` → 0 coincidencias.

---

## 7. Sin cobertura / no verificado 🔴

| # | Qué no está cubierto | Por qué | Qué lo cerraría |
|---|---|---|---|
| 1 | **Ejecución de las 3 suites** (unitaria y de integración) | `shell` denegado en esta sesión | correr los dos comandos del contrato y pegar la salida |
| 2 | **Rol efectivo de `NUCLEO_DATABASE_URL` en el entorno** (B4 del contrato) | requiere conectar; no se imprime el DSN | `select current_user, rolbypassrls from pg_roles where rolname=current_user` con el engine del núcleo |
| 3 | **`42501` real en el gate** (SEC-031) | requiere revocar un GRANT en `tei_test` | prueba de integración descrita en SEC-031 |
| 4 | **Permiso del endpoint `/estado` por HTTP** (403 a rol no-admin) | la prueba llama la función `estado()` directo con un `SimpleNamespace` (`test_agente_o2_1_integracion.py:676-683`), saltándose `requiere_permiso`; no hay ningún test que afirme el 403 | `TestClient` con JWT de un rol sin `agente:buzon` → 403 `ACCESO_DENEGADO` |
| 5 | **`invocar` con manifiesto inválido** (retorno `MODULO_INACTIVO` + fila) | solo se prueba `estado()`/`tools_cargadas` con `Registry(modulo=None)` (`test_agente_gate.py:232-241`); el camino `registry.py:273-288` no tiene prueba | test unitario con `FuenteFalsa` y `Registry(modulo=None, valido=False)` invocando una tool |
| 6 | **`AUDITORIA_FALLIDA`** | `registrar_consulta` nunca falla en las pruebas | inyectar una fuente/engine que falle en el insert y afirmar que **no** hay `datos` |
| 7 | **IDOR contra otro cliente del seed** | la prueba compara `total` con el conteo del propio cliente (`:491-498`), lo que cubre el caso, pero no hay aserción negativa explícita; el fixture calcula `otro_cliente_id` (`:213-216`) y no lo usa | afirmar `set(items) ∩ viajes(otro_cliente) == ∅` |
| 8 | **Concurrencia / revocación inmediata de ACL** | el cambio no escribe; §4.8 exige "sin caché" y el código lo cumple, pero no hay prueba de que una revocación surta efecto en la invocación siguiente | prueba con dos invocaciones y un `UPDATE permitido=false` entre ambas |
| 9 | **Pooler en modo transacción** | no hay entorno | `SET LOCAL` ya se usa; verificar con pgbouncer en `transaction` |
| 10 | **Runtime del agente (O3)** | no existe | al construirlo, verificar `ContextoAgente`, `request_id` y la redacción de `pregunta_resumida` (SEC-033) |

Además: `test_agente_o2_1_integracion.py` **deja filas** en
`contactos_whatsapp` y `auditoria_consultas_agente` (documentado en su cabecera
`:8-11`) porque la tabla es append-only y `contacto_id` es FK NOT NULL. Es
coherente con el diseño, pero implica que `tei_test` acumula contactos de prueba
entre corridas.

---

## 8. Prioridad recomendada y veredicto

**¿Puede pasar a O2.2? Sí, con condiciones.**

- **No hay bloqueante de seguridad para O2.2 (lectura).** No encontré: bypass de
  autenticación, lectura cruzada entre empresas, lectura de otro cliente/chofer
  por la entrada, inyección SQL, ejecución de tools no declaradas ni fuga de
  PII/financiero en respuestas. Las tres tools devuelven solo la proyección
  declarada y dejan rastro.
- **Condición 1 (antes de encender el módulo en una empresa):** cerrar **SEC-030**
  o registrar por escrito la aceptación de que el camino de tools no aplica la
  guarda de rol. Es la única media y su coste es S.
- **Condición 2 (antes de O2.4/O2.5, es decir, antes de la primera tool de
  escritura):** SEC-031 (denegación auditada), SEC-032 (`herramienta` acotada),
  SEC-033 (contrato de redacción de `pregunta_resumida`) y revisar **SEC-039**
  (el rol del agente puede escribir ACL/identidad/flag) — con escritura en juego,
  esa propiedad deja de ser teórica.
- **Quick wins (S, sin dependencias):** SEC-030, SEC-031, SEC-032, SEC-034,
  SEC-036, SEC-037, SEC-038. Todos son cambios de pocas líneas.
- **Antes de cerrar el hito:** ejecutar las 3 suites (§7.1) y las pruebas de §7.3,
  §7.4 y §7.5; hoy el veredicto de esas pruebas es 🔴 "no ejecutado".
- **Agentes responsables:** `backend` (SEC-030…033, 035, 036, 037, 038);
  `datos`/`arquitectura` (SEC-039, junto con la decisión de rol del runtime);
  `qa` (cobertura §7.3–§7.8); `orquestador` (aceptación formal si no se corrige
  SEC-030 antes de encender).

### Orden sugerido
1. SEC-030 (media, S) → 2. SEC-031 (S) → 3. SEC-032 (S) → 4. cobertura §7.4/§7.5
(qa) → 5. SEC-033 + contrato del runtime → 6. SEC-039 antes de O2.4.

---

## 9. Autoverificación

1. **¿Cada hallazgo confirmado tiene evidencia reproducible?** Sí: `archivo:línea`
   en todos. Los que dependen de ejecución están marcados `potencial` o en §7.
2. **¿Distinguí confirmado de potencial?** Sí: SEC-033/036/037 son `potencial`;
   el resto `confirmado` por lectura.
3. **¿Describí el control real en vez de "no hay control"?** Sí: no declaré "no hay
   RLS" ni "no hay auditoría"; describí qué capa protege y hasta dónde (p. ej.
   SEC-030: el filtro explícito por `empresa_id` **sí** está en todas las
   consultas; lo que falta es la guarda de arranque).
4. **¿Probé variantes (verbo, rol, endpoint legacy vs núcleo)?** Roles: cliente,
   conductor, admin, contacto inactivo, OTP pendiente, sin ACL, ACL `false`
   (Q3/Q9). Verbos: el módulo solo expone `GET /estado`; no hay rutas de escritura
   que probar. Legacy vs núcleo: el módulo no toca `public` (verificado por
   búsqueda) y no duplica rutas existentes.
5. **¿Excluí secretos?** Sí: no se leyó `.env`, no se imprime ningún valor; el
   único secreto del ecosistema que se menciona es por **ubicación**
   (`API_V1_PREFIX`, `NUCLEO_DATABASE_URL`), nunca por valor.
6. **¿Evité presentar una buena práctica ausente como vulnerabilidad?** Sí: las
   siete informativas no tienen ruta de explotación y lo dicen; SEC-030 es media
   precisamente porque el filtro explícito evita la fuga hoy.
7. **¿Listé lo que no pude verificar?** Sí, §7 con 10 puntos y qué los cerraría.
8. **¿Cada remediación tiene prueba de verificación y agente?** Sí, en el detalle
   de cada SEC y en §8.
9. **¿Respeté los límites?** No edité código ni configuración; solo escribí este
   archivo en `docs/seguridad/`. No ejecuté pruebas destructivas ni contra
   producción (no pude ejecutar nada). No modifiqué `hallazgos.md`: este informe
   es un archivo aparte y continúa la numeración desde SEC-030 (el máximo
   registrado en `docs/seguridad/` es SEC-029).
