# ADR-0005: Tenancy real en `nucleo` — dos engines (legacy privilegiado / núcleo `tei_app`), contexto por transacción y legacy declarado no aislado

- **Estado:** **Aceptado** (2026-10-30) por el **dueño** vía delegación de criterio al orquestador ("haz lo que estimes conveniente"), con la condición de activación por pasos y rollback aquí descritos. Sustituye la numeración anterior ADR-0004 (colisión) → este es **ADR-0005**.
  toca aislamiento multiempresa y el camino de escritura del núcleo).
- **Fecha:** 2026-10-30
- **Decide:** agente `arquitectura`. La migración `0020` y su evidencia son del agente `datos`.
- **Nota de numeración (bloqueante editorial, no técnica):** el número `0004` ya está
  asignado a `ADR-0004-proveedores-ia-whatsapp-privacidad.md` (2026-10-30). Este
  documento se entrega en la ruta solicitada por el orquestador; **antes de citarlo
  desde otros documentos debe renumerarse a `ADR-0005`** (un solo propietario por
  archivo: no renombro el ADR ajeno). Mientras tanto, citarlo por nombre de archivo,
  no por número.
- **Documentos y artefactos de los que depende:**
  - `docs/datos/rls-multiempresa.md` (diseño, precondiciones, pruebas `0020_01…04`,
    rollback probado; agente `datos`, 2026-10-30).
  - `supabase/migrations/0020_rls_multiempresa.sql` (rol `tei_app`, 35 políticas,
    `FORCE`, GRANTs) — **aplicada solo en el clon desechable `tei_test`**, no en la
    base de la app.
  - `docs/qa/informes/F0-due-diligence.md` (estado del aislamiento: D-05, F0-02,
    RA-03; bypass del cutover: D-2).
  - `ADR-0001` (coexistencia `public`/`nucleo`), `ADR-0002` (retiro del legacy).
  - `docs/arquitectura/deuda.md` D-03; `docs/estado.md` RA-03/RA-04.
- **Relación con `ADR-0001`:** no lo reemplaza. `ADR-0001` decide **quién es canónico**;
  este ADR decide **con qué rol y con qué contexto se accede a cada esquema**. Ambas
  decisiones son independientes: se puede cerrar el legacy por módulo sin cambiar de
  rol, y se puede imponer RLS en el núcleo sin haber cerrado ningún módulo.

---

## 0. Resumen de la decisión

1. **Dos engines, dos DSN, dos roles.** El engine del **legacy** conserva el rol actual
   (`postgres`, `BYPASSRLS`) y atiende `public`. El engine del **núcleo** usa `tei_app`
   (`NOBYPASSRLS`) y atiende **solo** `nucleo`. No hay *fallback*: si
   `NUCLEO_DATABASE_URL` falta, los endpoints del núcleo responden 503; nunca se
   degradan en silencio al rol privilegiado.
2. **Contexto por transacción, no por request.** `app.empresa_id`, `nucleo.auth_id` y
   `nucleo.request_id` se fijan con `set_config(…, true)` (`SET LOCAL`) desde un
   listener `after_begin` del `Session` del núcleo, alimentado por `session.info` que
   llena **un único** punto (la dependencia de sesión). Así los 54 `commit()`
   intermedios no pierden el contexto ni la auditoría.
3. **Fail-closed explícito.** Sin GUC válido ⇒ 0 filas (probado), nunca "todas". La
   autorización sigue siendo membresía + estado de empresa en `deps.py`. El error de
   política (`42501`) se traduce a 403/404 sin revelar existencia; `42501` por falta de
   `GRANT` es bug de despliegue (500 + alerta).
4. **`public` sigue con el rol privilegiado hasta su retiro y se declara NO aislado.**
   No se le ponen políticas (no tiene `empresa_id`: sería teatro de seguridad) y no se
   le dan `GRANT` a `tei_app` (hoy daría 42501 o 0 filas). Es una limitación aceptada,
   con condición de pago: el retiro del legacy (`ADR-0002`).
5. **D-2 (bypass del cutover): recomendación, no decisión.** Mantener el bypass como
   **operación de plataforma** —no como escritura de tenant— con verificaciones
   compensatorias obligatorias y evidencia; **no** reescribirlo para pasar por los
   servicios en esta fase. Lo que falta para decidir está en §7.

---

## 1. Contexto verificado

Método: lectura de código, migraciones y documentos con salida registrada. **Esta sesión
no ejecutó comandos** (shell no disponible): las marcas 🟢 de comportamiento en base se
apoyan en salidas pegadas por `datos`/F0, no re-ejecutadas aquí.

| # | Hecho | Evidencia | Certeza |
|---|---|---|---|
| 1 | `nucleo` tiene 31 tablas con RLS habilitado, **0 políticas**, 0 `FORCE`; el backend conecta como `postgres` (`rolbypassrls=t`) ⇒ RLS inerte | F0 §4 D-05 (`docs/qa/informes/F0-due-diligence.md:80`); `docs/datos/rls-multiempresa.md:50-53` | 🟢 |
| 2 | `0020` crea `tei_app` (LOGIN, NOINHERIT, NOSUPERUSER, **NOBYPASSRLS**), 35 políticas `USING`+`WITH CHECK`, `FORCE` en 31 tablas y los GRANT mínimos (sin `DELETE` en ninguna tabla) | `0020:21-25`, `:247-266`, `:283-295`, `:397` | 🟢 |
| 3 | `BYPASSRLS` gana sobre `FORCE`: con `postgres` el `FORCE` no protege (62 viajes con y sin GUC; 57 viajes de otras empresas visibles) | `0020:38-43`; `docs/datos/rls-multiempresa.md:449-463` (salida `0020_04`) | 🟢 (salida de `datos`) |
| 4 | Con `tei_app` y contexto: cada empresa ve solo lo suyo; sin contexto: 0 filas; INSERT ajeno ⇒ `42501`; `SET LOCAL` muere en el `COMMIT` (la conexión del pool no hereda la empresa) | `docs/datos/rls-multiempresa.md:381-404`, `:442-447` | 🟢 (salida de `datos`) |
| 5 | Dos conexiones simultáneas quedan aisladas (solape real 1,60 s); la mutación (BYPASSRLS o `USING(true)`) se detecta; rollback sin pérdida y re-aplicación idempotente | `docs/datos/rls-multiempresa.md:416-435`, `:465-476`, `:517-539`; scripts `supabase/tests/0020_01…04`, `0020_99_rollback.sql` | 🟢 (salida de `datos`) |
| 6 | El backend tiene **un solo** engine: `create_engine(settings.DATABASE_URL, pool_pre_ping=True)` y un `get_session()` global | `backend/app/core/database.py:7,10-29` | 🟢 |
| 7 | Ese `get_session` lo usan **11 archivos de rutas legacy** y `api/deps.py`; el núcleo lo usa vía `app/nucleo/deps.py:17,47` | grep `from app.core.database import` en `backend/app/api/**` + `deps.py:17` | 🟢 |
| 8 | El **único** acceso cruzado del núcleo a `public` es un conteo en `servicio_cutover.estado()` | `backend/app/nucleo/servicio_cutover.py:89-102` (grep `public\.` en `backend/app` = 1 resultado) | 🟢 |
| 9 | Los servicios del núcleo hacen `commit()` a mitad de request: **54 llamadas** en `backend/app/nucleo/**` (p. ej. `servicio_maestros.py:125,201,245,287,335,545`) | grep `.commit()` | 🟢 |
| 10 | Hoy el GUC de auditoría se fija **por método de escritura** y **antes** de su primer `commit`; tras el `COMMIT` se pierde (SET LOCAL) | `servicio_maestros.py:93-102` + `:125`; `0004:830-878` (`fn_auditoria` lee `nucleo.auth_id`/`request_id` en `:872-873`); `docs/datos/rls-multiempresa.md:216-219` | 🟢 |
| 11 | `get_contexto_empresa` consulta `usuarios_empresa` **antes** de fijar cualquier GUC; `X-Empresa-ID` es `Header(...)` obligatorio | `backend/app/nucleo/deps.py:43-61` (header en `:44`) | 🟢 |
| 12 | `GET /nucleo/mis-empresas` no recibe `X-Empresa-ID` y resuelve por `auth_id` | `backend/app/nucleo/api.py:69-76`; `0020:216-238` (`empresas_del_usuario()` derivado del GUC, nunca de un parámetro) | 🟢 |
| 13 | `public` tiene 17 tablas con RLS habilitado y **1** política (`public.usuarios`); no tiene `empresa_id` | `docs/datos/rls-multiempresa.md:57`; `ADR-0001:144` | 🟢 |
| 14 | `0020` **no** otorga nada en `public` y lo declara fuera de alcance | `0020:65-69` | 🟢 |
| 15 | El handler global solo traduce `IntegrityError` (23505/23P01/23514/23502/23503) y `ErrorNucleo`; `42501` no está mapeado en ninguno | `backend/app/main.py:19,69-113`; `backend/app/nucleo/errores.py:136-189` | 🟢 (mapeo) / 🟡 (`42501` llega como `ProgrammingError`, no `IntegrityError`: confirmar con prueba HTTP) |
| 16 | `scripts/cutover_legacy.py` escribe **9 tablas** de `nucleo` con SQL directo (`clientes`, `choferes`, `documentos` —3 inserts—, `tractos`, `ramplas`, `tarifas`, `ordenes_compra`, `viajes`), crea `MIG-*` sintéticas y hace un único `commit()` final; usa `DATABASE_URL` (el mismo DSN de la app) | `scripts/cutover_legacy.py:63-66`, `:124-378`, `:312,339`, `:407-420` | 🟢 |
| 17 | El pooler local está **deshabilitado**; si se habilita, el modo declarado es `transaction` | `supabase/config.toml:45-55` | 🟢 |
| 18 | `create_engine` no fija `pool_size`/`max_overflow`: usa los *defaults* de SQLAlchemy ⇒ dos engines = dos pools por proceso | `backend/app/core/database.py:21-23` | 🟢 |
| 19 | `fn_auditoria` es `SECURITY DEFINER` (dueño `postgres`): los triggers **no** pasan por RLS | `0004:830-834`; `0020:60-63` | 🟢 |
| 20 | `servicio_cutover.legacy_congelado()` es hoy **fail-closed** (si falla la lectura o no hay fila, congela) | `servicio_cutover.py:25-63` | 🟢 (código actual) |
| 21 | Los modelos del núcleo fijan `schema='nucleo'` y el SQL crudo del backend está cualificado por esquema (grep de `from/join/update <tabla>` sin esquema = 0) ⇒ el engine del núcleo no depende de `search_path` para llegar a `nucleo` | `backend/app/nucleo/models.py:5,49` (+ `{"schema": SCHEMA}` por tabla); grep | 🟢 |

**Contradicción documental detectada (no la corrijo aquí):** `docs/estado.md:78,103,127`
y `F0 §4` describen `legacy_congelado()` como **fail-open**; el código actual
(`servicio_cutover.py:47-63`) es **fail-closed**. El documento está desactualizado
respecto del código; lo reporto a `orquestador`/`qa`. No cambia ninguna decisión de este
ADR (RA-04 sigue abierto por la ventana de caché de 5 s y por `estado()` devolviendo
`legacy_abiertos=0` ante error, `:95-102`).

---

## 2. Problema

**Hoy el aislamiento multiempresa del núcleo no lo impone PostgreSQL porque el único
engine de la aplicación conecta con un rol `BYPASSRLS`, y `0020` —que ya tiene el rol,
las políticas y las pruebas— no protege nada hasta que se decida con qué rol y con qué
contexto por transacción opera cada esquema, sin romper el legacy ni perder la
auditoría.** En una frase verificable: *¿qué rol ejecuta cada consulta del backend y
cómo sabe PostgreSQL, en cada transacción, a qué empresa pertenece el request?*

Tres hechos hacen que la respuesta no sea trivial:

- el legacy `public` **no es multiempresa** y 17 de sus tablas devolverían 42501 o 0
  filas a un rol sin `BYPASSRLS` (hechos 13-14);
- los servicios **commitean a mitad de request** (hecho 9), y `SET LOCAL` muere en cada
  `COMMIT` (hecho 4): un `set_config` único al inicio deja la segunda mitad sin contexto;
- el contexto de autorización (`usuarios_empresa`) se consulta **antes** de que exista
  contexto de base (hecho 11), y `mis-empresas` no trae `X-Empresa-ID` (hecho 12).

---

## 3. Decisión 1 — Rol y conexión

### 3.1 Alternativas reales

| Alternativa | Ventajas | Costes / riesgos | Reversible | Impacto en legacy | Impacto en datos |
|---|---|---|---|---|---|
| **A. Dos engines: `public` con `postgres` (actual) y `nucleo` con `tei_app`** *(recomendada)* | Impone RLS donde importa sin tocar 17 tablas legacy; cero migración de datos; el legacy queda exactamente igual; cada pool con su rol; el corte de rol es cambio de DSN (config), no de código | Dos pools por proceso (hecho 18): hay que fijar límites y verificar el límite del proveedor; dos DSN que administrar; el código del núcleo no puede leer `public` sin una excepción declarada (hoy: 1 sola, hecho 8) | **Alta**: volver a la versión anterior del backend restaura el estado actual; `0020` puede quedarse aplicada (inerte) o revertirse con `0020_99` | Ninguno (mismo rol, mismo DSN) | Ninguno (sin `DROP`/`DELETE`; rollback probado sin pérdida) |
| **B. Un solo rol `tei_app` para ambos esquemas** (+ `GRANT` en `public` y políticas) | Un pool, una credencial | `public` no tiene `empresa_id`: no hay nada que filtrar ⇒ políticas `USING(true)` = teatro de seguridad. Con `GRANT` y RLS sin políticas, el legacy devuelve **0 filas** (o 42501 sin `GRANT`). Rompe el negocio y no aísla | Baja (habría que revertir `GRANT`/políticas) | **Alto: legacy caído** | Ninguno, pero la app queda inoperante |
| **C. Un engine privilegiado + `SET LOCAL ROLE tei_app` por transacción** | Un solo pool; no hay segundo DSN | La sesión **conserva** la capacidad de ejecutar como `postgres`: si el listener falla o falta, la consulta corre **sin filtro** ⇒ fail-open por omisión. Exige `GRANT tei_app TO postgres` y que el rol de conexión pueda `SET ROLE` (no verificado en Supabase cloud: 🔴) | Alta | Ninguno | Ninguno |
| **D. `ALTER ROLE postgres NOBYPASSRLS` (un rol para todo, con `FORCE`)** | Sin cambios de código | `postgres` es el rol de seeds, scripts, cutover, backups y tooling de Supabase: quitarle `BYPASSRLS` deja inoperables las operaciones de plataforma y, si se revierte mal, la base; `FORCE` no aplica a dueños con `BYPASSRLS` (hecho 3) | Media: un `ALTER ROLE` afecta a todo el clúster | Alto: seeds/cutover/backup dejan de funcionar | Ninguno |
| **E. No cambiar (status quo)** | Cero trabajo | El aislamiento sigue viviendo en ~100 consultas de servicio; una consulta sin `empresa_id` es una fuga; `0020` queda como documentación muerta | — | Ninguno | Ninguno, y la deuda crece |

**Descartadas:** B porque rompe el legacy sin aislarlo; C porque su modo de fallo es
fail-open (viola el principio "la garantía crítica no depende de que alguien se acuerde");
D porque convierte el rol de plataforma en rol de aplicación y deja la operación sin
herramientas; E porque es la causa del problema.

### 3.2 Reglas de la alternativa A (normativas)

1. **Un engine por esquema, no por módulo.** `legacy_engine` (rol actual, `public`) y
   `nucleo_engine` (`tei_app`, `nucleo`). Nada de "elegir engine según el endpoint":
   la frontera es el **esquema**, que es estable y verificable. El engine del núcleo fija
   `search_path` explícito como defensa, aunque no depende de él: los modelos y el SQL
   están cualificados (hecho 21).
2. **Sin *fallback*.** `NUCLEO_DATABASE_URL` es obligatoria. Si falta o no conecta, los
   endpoints `/nucleo/*` responden **503** con mensaje explícito (no se reutiliza el
   `HTTPException` 503 genérico de `database.py:14-20` para otra cosa). Está prohibido
   que el engine del núcleo use `DATABASE_URL` "porque no estaba configurado".
3. **Guarda de arranque (sin modo inerte).** Al crear el `nucleo_engine`, una
   verificación única (lazy, en el primer uso) comprueba `current_user` y
   `rolbypassrls` del rol efectivo. Si `rolbypassrls = true` (o el rol no es el
   declarado para el núcleo), se registra un **ERROR** con marcador estable propuesto
   (`nucleo_rls_inactivo`) y el módulo núcleo responde **503**: no se sirve tráfico
   creyendo que hay RLS. No se agrega una variable para "desactivar la guarda": un
   estado de RLS apagado tiene que ser imposible de alcanzar sin que el sistema lo
   grite. En local, `0020` deja `tei_app` disponible por `trust`
   (`docs/datos/rls-multiempresa.md:113`); si alguien no aplicó `0020`, el síntoma es
   503 con mensaje explícito, no datos sin filtrar.
4. **El código del núcleo no lee `public`.** Excepción declarada y única: el conteo de
   viajes legacy abiertos en `servicio_cutover.estado()` (`:89`), que debe ejecutarse
   con el `legacy_engine` (es una lectura de plataforma, no de tenant). Cualquier otra
   referencia a `public` desde `backend/app/nucleo/**` es un defecto. Prueba estática
   que lo hace fallar (ver §9, criterio 9).
5. **`tei_app` no recibe privilegios en `public`.** `GRANT` en `public` es una regresión
   de aislamiento aunque hoy "no filtre nada": convierte un error de conexión en una
   lectura silenciosa. Prueba que verifica `has_table_privilege('tei_app','public.viajes','SELECT') = false`.
6. **El rol de plataforma (seeds, cutover, backups) no es el rol de la aplicación.**
   Sigue siendo `postgres`/`supabase_admin`, se documenta quién lo usa y por qué
   (`docs/operacion/`), y no se expone a través de la API.

### 3.3 Por qué dos engines y no una abstracción mayor

No hace falta un router de conexiones, ni un proxy, ni roles por tenant, ni claims
firmados: el aislamiento ya está impuesto por RLS una vez que el rol no bypasea. La
segunda conexión es el precio mínimo para no reescribir el legacy, y es **reversible por
configuración** (o por *rollback* de la versión anterior). Añadir un tercer rol o un
servicio de conexión no resuelve ningún problema que A no resuelva ya (§3.1).

---

## 4. Decisión 2 — Propagación del contexto

### 4.1 Mecanismos evaluados

| Mecanismo | Cubre `commit()` intermedios | Cubre pool reutilizado | Riesgo de fail-open | Complejidad | Veredicto |
|---|---|---|---|---|---|
| `set_config` una vez en la dependencia FastAPI | **No**: muere en el primer `COMMIT` (hecho 4) ⇒ segunda mitad del request con 0 filas | Sí (`SET LOCAL`) | Medio (0 filas, no fuga) | Baja | Descartado |
| Middleware ASGI que abre su propia conexión | No: la sesión del request es otra conexión | Parcial | Alto: dos conexiones, una sin contexto | Media-alta | Descartado |
| **Listener `after_begin` sobre el `Session` del núcleo + `session.info`** | **Sí**: se re-aplica en cada transacción nueva (incluidas las que abren los `commit()`) | Sí: `SET LOCAL` muere en `COMMIT` y se re-fija al inicio de la siguiente | **No** (sin `empresa_id` ⇒ 0 filas) | Baja (≈15 líneas + 1 dependencia) | **Elegido** |
| `SET LOCAL ROLE` + `set_config` (variante de C) | Sí | Sí | Sí (si falta, corre como dueño) | Baja | Descartado (§3.1 C) |

### 4.2 Diseño normativo

1. **Un solo punto fija el contexto.** La dependencia de sesión del núcleo
   (`get_nucleo_session`) llena `session.info` **antes de la primera consulta**:
   - `empresa_id` ← `X-Empresa-ID` **si y solo si** es un UUID válido (si no, se rechaza
     la petición con 400 antes de tocar la base: el header no confiable no llega a SQL);
   - `auth_id` ← `sub` del JWT ya validado por `bearer_scheme`
     (`app/core/security.py`), que es la misma fuente que usa `deps.py:49`;
   - `request_id` ← `X-Request-ID` (opcional, solo trazabilidad).
   Esto resuelve el hecho 11: el GUC queda fijado **antes** de la consulta de membresía
   de `deps.py:55`, y resuelve el hecho 12 (`mis-empresas` obtiene `auth_id` sin
   `X-Empresa-ID`).
2. **El GUC se re-aplica por transacción**, no por request:

   ```python
   # backend/app/core/database.py — listener del engine del núcleo (boceto, handoff)
   @event.listens_for(Session, "after_begin")     # 🟡 ver nota de herencia abajo
   def _aplicar_contexto(session, transaction, connection):
       empresa = session.info.get("empresa_id")
       auth_id = session.info.get("auth_id")
       request_id = session.info.get("request_id")
       if not (empresa or auth_id or request_id):
           return                                  # sesiones legacy / plataforma: no-op
       # set_config(..., true) == SET LOCAL: muere en COMMIT (probado, 0020 §7.3)
       connection.exec_driver_sql(
           "select set_config('app.empresa_id', %s, true),"
           "       set_config('nucleo.auth_id', %s, true),"
           "       set_config('nucleo.request_id', %s, true)",
           (empresa or "", auth_id or "", request_id or ""),
       ).close()
   ```

   **Herencia del evento (🟡):** se asume que un listener de clase sobre
   `sqlalchemy.orm.Session` alcanza a `sqlmodel.Session` (subclase). No se verificó en
   esta sesión. Si no se cumple, la alternativa equivalente es registrar el listener
   sobre la clase concreta que produce el `sessionmaker` del núcleo (`propagate` no
   aplica a eventos de `Session`). Lo cierra la prueba del criterio 3: si el GUC no se
   re-aplica tras el primer `commit()`, la prueba falla.

   Notas de implementación (no negociables):
   - `set_config`, no `SET LOCAL ... = :param`: `SET` no acepta parámetros ligados.
   - Vacío (`''`) en lugar de `NULL`: `ctx_empresa()`/`ctx_auth_id()` normalizan `''`
     a `NULL` (`0020:178-210`), así que no hay `22P02` (probado `0020_01` bloque 1G).
   - El listener es **no-op** si `session.info` no trae claves: no afecta a las sesiones
     legacy ni a `legacy_congelado()` (`servicio_cutover.py:37-46`), que abre su propia
     sesión sin contexto.
   - `after_begin` también dispara en *savepoints*; re-fijar el GUC es idempotente.
     Confirmar en integración que no hay error de resultado abierto (🟡: es el único
     punto del diseño que depende del driver; lo cierran las pruebas de los criterios
     3 y 11).
3. **La autorización no se mueve.** `get_contexto_empresa` (`deps.py:43-82`) sigue
   validando membresía activa y estado de empresa; el GUC **solo acota**. Que el header
   sea no confiable no importa: sirve para *reducir* el alcance, y PostgreSQL no lo usa
   para *conceder*. Si el usuario no es miembro, la consulta de membresía devuelve 0
   filas ⇒ 403; el GUC nunca amplía visibilidad fuera de la empresa indicada.
4. **Fail-closed se traduce, no se propaga.** Sin contexto válido, toda tabla de tenant
   devuelve 0 filas. El backend debe producir **403/404 de dominio**, nunca 500 ni un
   mensaje de PostgreSQL:
   - `42501` con `new row violates row-level security policy` ⇒ **403** (o 404 si revelar
     existencia es peor), sin detalle de tabla/columna;
   - `42501` con `permission denied for table` ⇒ **500** con alerta: es un `GRANT`
     faltante (bug de despliegue), no un problema del usuario (hoy cae en el 500 genérico
     porque no hay handler: hecho 15).
5. **La auditoría deja de depender del servicio.** Con `nucleo.auth_id` fijado por
   transacción, `fn_auditoria` (`0004:872-873`) registra el `auth_id` real también
   **después** del primer `commit()`. Los `_fijar_contexto_bd()` por servicio
   (`servicio_maestros.py:93-102` y 9 servicios más) quedan redundantes: se conservan
   como *no-op* en la primera entrega y se retiran cuando la prueba del criterio 3 esté
   verde (retirarlos antes no aporta y arriesga).
6. **Con el pooler en modo `transaction`** (`config.toml:51`) el `SET LOCAL` sigue siendo
   correcto: la transacción completa corre en una sola conexión de servidor. **No
   verificado contra PgBouncer/Supavisor real** (`docs/datos/rls-multiempresa.md:614-615`):
   🔴, criterio de aceptación en el entorno que se despliegue.
7. **Dos pools ⇒ límites explícitos.** Al crear los engines se fijan `pool_size` y
   `max_overflow` en función del límite del proveedor (no se fija un número aquí: **no
   hay cifra verificada**, 🔴). El total de conexiones del proceso es la suma de ambos
   pools; el despliegue debe declarar workers × (legacy + núcleo) ≤ límite del plan.

---

## 5. Decisión 3 — `public` legacy

**Se queda con el rol actual hasta su retiro, y se documenta que NO está aislado.**

- No se le añaden políticas: `public` no tiene `empresa_id` (hecho 13); una política
  `USING(true)` daría apariencia de control sin control.
- No se le dan `GRANT` a `tei_app` (hecho 14 y §3.2 regla 5). Dos consecuencias
  verificables: sin `GRANT` ⇒ `42501`; con `GRANT` y RLS sin políticas ⇒ 0 filas.
  Ambas son fallas del legacy, no aislamiento.
- **Declaración obligatoria** (texto a incorporar en `docs/operacion/` y en la ficha del
  legacy, por su dueño): *"`public` es single-tenant, no está aislado por empresa y no
  lo estará: su retiro es la condición de pago (`ADR-0002`). Todo endpoint legacy
  expone datos de la única empresa; no se ofrece a un segundo tenant."*
- **Consecuencia comercial, no técnica:** el día que exista un segundo tenant (D-3 de
  F0), el legacy **no puede** seguir expuesto. La fecha de ese día no está decidida
  (🔴). Este ADR no la requiere para imponer RLS en el núcleo, pero sí la señala como
  bloqueo de producto.
- **Excepción de lectura declarada:** solo `servicio_cutover.estado()` lee `public`
  (hecho 8), vía `legacy_engine`, con un `except` que hoy reporta 0
  (`servicio_cutover.py:95-102`). Ese `except` sigue siendo fail-open **informativo**
  (afecta una métrica, no una escritura); se registra como deuda, no se arregla aquí.

---

## 6. Plan de despliegue y rollback

Principio: **cada paso es observable y el anterior no se deshace para hacer el
siguiente**. La migración `0020` es inerte para el rol actual (probado, hecho 3), así que
puede aplicarse sin ventana de mantenimiento.

| Paso | Acción | Criterio de aceptación observable | Rollback del paso |
|---|---|---|---|
| **0. Precondiciones** | Ejecutar P1–P6 de `0020:74-110` **en la base destino** (no en `tei_test`) | P1 = 0 políticas previas (o solo las de `0020` en un re-run); P2 = 0 avisos de `empresa_id NULL`; P3 = 0 tablas sin índice de empresa; P4 = `auditoria` con `empresa_id NULL` contado y reportado; P5 = 0 reservas de otra empresa; P6 = `tei_app` sin membresías. **Si P2/P4/P5 devuelven filas: reportar, no borrar** | — |
| **1. `0020` inerte** | Aplicar `supabase/migrations/0020_rls_multiempresa.sql` con rol dueño de tablas | `pg_policies` = 35 en `nucleo`; `relforcerowsecurity` = 31; `pg_roles` de `tei_app`: `rolbypassrls=f, rolcanlogin=t`; `has_schema_privilege('tei_app','nucleo','USAGE')=t`; `0020_04` pasa (la app con `postgres` ve lo mismo con y sin GUC); `make test` 100 ✓ y `make e2e` 9/9 ✓ **sin cambios de código** | `supabase/tests/0020_99_rollback.sql` (probado sin pérdida: conteos idénticos). No hay `DROP TABLE`/`DELETE` |
| **2. Wiring del contexto (validación con `tei_app` en `tei_test`/staging)** | Desplegar el listener + `get_nucleo_session` contra el clon `tei_test` (donde `0020` ya está aplicada) y contra staging. **En producción no se despliega este paso por separado**: un estado "wiring con `postgres`" no prueba nada sobre RLS y crea la falsa creencia de que está vigente | Con `tei_app` en `tei_test`: una petición de escritura que commitea dos veces deja `nucleo.auditoria.auth_id` **distinto de `'sistema'` en ambas mitades** (criterio 3); sin `X-Empresa-ID` no hay 500; `mis-empresas` devuelve las empresas del usuario; `make test`/`make e2e` verdes | Revertir el despliegue en el entorno de prueba (el código anterior no lee `NUCLEO_DATABASE_URL`) |
| **3. Cambio de rol (release único que incluye el paso 2)** | Publicar en producción el release con `NUCLEO_DATABASE_URL` = DSN de `tei_app` (contraseña en el gestor de secretos, rotada; nunca en repo ni en `docs/`). Pasos 2 y 3 son **el mismo release** | `select current_user` desde una petición del núcleo = `tei_app` y `rolbypassrls=f`; empresa A no ve filas de B en viajes/clientes/facturas; `X-Empresa-ID` de B con token de A ⇒ **403**; escritura normal (crear viaje/maestro) ⇒ 201 + fila de auditoría con `auth_id` del usuario; `/nucleo/*` no devuelve 500; legacy intacto (`make e2e` 9/9) | **Revertir el release** a la versión anterior (mono-engine, `postgres`): RLS vuelve a ser inerte, sin cambio de datos. `0020` puede quedarse aplicada. Alternativa: `0020_99` si además se quiere retirar el rol |
| **4. Verificación y cierre** | 24–48 h con conteos por empresa, errores `42501` y latencia; recién entonces se actualiza RA-03/INV-T01 | 0 respuestas 500 con SQLSTATE `42501`; 0 filas de otra empresa en las consultas de control; latencia del módulo comparable a la línea base previa (medida con `EXPLAIN`/métricas, no supuesta); `nucleo.auditoria` del periodo sin filas con `auth_id='sistema'` atribuibles a requests de usuario (las de plataforma se enumeran) | Volver al paso 2/3 según la causa |

**Regla de orden (no invertir):** cambiar el rol sin el contexto fijado deja el módulo
núcleo con **0 filas en todas las tablas** (fail-closed, sin corrupción, pero caída
total). Por eso el paso 2 se prueba con `tei_app` en `tei_test` **antes** del release de
producción; en producción no existe una fase "wiring con postgres" que dé falsa
sensación de seguridad.

**Rollback de datos:** este ADR no mueve datos. `0020` solo cambia catálogo
(políticas/GRANT/rol) y su rollback está probado con conteos idénticos
(`docs/datos/rls-multiempresa.md:517-539`).

---

## 7. D-2 — Bypass del cutover (`scripts/cutover_legacy.py`)

**Recomendación (no decisión del dueño): mantener el bypass como operación de
plataforma, con verificaciones compensatorias obligatorias; no reescribirlo para pasar
por los servicios en esta fase.**

Razonamiento con evidencia:

- Lo que el script evita **no es solo RLS** (corre como `postgres`, que bypasea): evita
  los triggers de `0015` (expediente documental completo) y los de reserva/auditoría.
  Pasar por los servicios obligaría a fabricar `permiso_circulacion`, `soap`,
  `seguro_carga` y `examen_medico`, que el legacy no tiene: el propio script documenta
  que inventar fechas sería **falsear cumplimiento documental**
  (`scripts/cutover_legacy.py:6-13`). Eso es peor que el bypass.
- El bypass **no rompe el aislamiento**: las filas que inserta llevan `empresa_id` y
  quedan bajo las políticas de `0020` como cualquier otra. Lo que rompe son las
  **garantías de integridad/auditoría** del núcleo (triggers no ejecutados, sin filas de
  auditoría, tarifas/OC sintéticas `MIG-*`).

**Condiciones mínimas para que el bypass sea aceptable** (cada una observable):

1. Se ejecuta con el legacy **congelado** (fail-closed) y con un solo escritor; el flag
   se actualiza en la misma transacción que la migración (`cutover_legacy.py:407-420`).
2. El script usa un DSN de **plataforma explícito** (`PLATFORM_DATABASE_URL`), no
   `DATABASE_URL` de la app (`cutover_legacy.py:63-66`): hoy sus privilegios dependen de
   la configuración de la aplicación.
3. **Verificación compensatoria post-ejecución**, con salida registrada, que devuelva 0
   violaciones para cada mecanismo saltado:
   - viajes migrados con recursos ⇒ expediente documental completo (o 0, porque se
     migran sin asignación: contar y declarar);
   - `reservas_recurso` coherente con los viajes migrados (hoy no se crean: contar y
     declarar, `ADR-0001:58-62`);
   - `nucleo.viajes` sin violar `EXCLUDE`/`CHECK` (lo impone la tabla aunque el insert sea
     directo: los constraints sí corren);
   - suma y conteo por empresa legacy vs núcleo, con diferencia 0 o justificada.
4. **Auditoría declarada:** o se insertan filas `auditoria` con `auth_id='cutover:<run>'`
   y `request_id` del run, o se declara por escrito que los registros migrados no tienen
   auditoría (hoy: no la tienen).
5. **`MIG-*` aceptadas o reemplazadas:** las tarifas y OC sintéticas
   (`cutover_legacy.py:312,339`) son datos comerciales provisionales; el dueño debe
   aceptarlas o el script debe excluirlas. **Validar con contador** si una OC sintética
   con monto `max(total*1.2, 1.000.000)` puede afectar facturación (no se asume).
6. **Idempotencia y evidencia de ejecución:** re-ejecutable sin duplicar; registro de
   quién, cuándo, commit del script y conteos.

**Lo que falta para que el dueño decida (bloqueo declarado):**

| # | Falta | Quién |
|---|---|---|
| D-2.a | ¿Se autoriza el bypass para el cutover **real** (no dry-run) con las condiciones 1–6? | Dueño |
| D-2.b | ¿Qué módulos entran? El script **no** migra gastos, facturas, pagos, liquidaciones ni mantenimientos (`ADR-0001:53-57`) | Dueño + `negocio-finanzas` |
| D-2.c | ¿Se aceptan tarifas/OC `MIG-*` como dato comercial provisional? | Dueño + contador |
| D-2.d | ¿Se aceptan viajes migrados en `confirmado`, sin recursos y sin reservas, con la asignación pendiente en `observaciones`? | Dueño + despacho |
| D-2.e | ¿Quién puede ejecutar el rol de plataforma y queda registrado? | Dueño + `auditor-seguridad` |

---

## 8. Consecuencias

**Positivas**

- El aislamiento deja de depender de las "100+ consultas" de servicio que hoy son el
  único control (F0 §4, F0-02): lo impone PostgreSQL, probado con dos conexiones reales
  y con mutación (hechos 4-5).
- Se corrige un defecto latente de auditoría (hecho 10): tras el primer `commit()` los
  registros dejaban de llevar `auth_id` real.
- El legacy no cambia de comportamiento: el riesgo de la migración se concentra en el
  núcleo, que es donde hay que concentrarlo.
- Reversible por despliegue, sin mover datos.
- No introduce colas, workers, proxies ni roles por tenant.

**Negativas / deuda que genera**

- Dos pools y dos DSN que mantener sincronizados; un DSN mal apuntado es un incidente de
  disponibilidad (fail-closed) o de seguridad (si se apunta al rol privilegiado).
- La excepción de lectura a `public` en `servicio_cutover` es deuda declarada hasta que
  el legacy se retire.
- Los `_fijar_contexto_bd()` por servicio quedan redundantes: deuda de limpieza (S).
- `fn_auditoria` y demás triggers son `SECURITY DEFINER` (hecho 19): **no** pasan por RLS.
  Su corrección es una garantía de código, no de base.
- `tei_app` puede insertar filas en `nucleo.auditoria` de su propia empresa: la
  auditoría es append-only pero no es prueba contra una aplicación comprometida.
- Las pruebas actuales corren con `postgres` (`NUCLEO_TEST_DATABASE_URL` y
  `settings.DATABASE_URL`, F0 §5): tras el cambio, los fixtures deben **sembrar** con el
  rol de plataforma y **consultar** con `tei_app`, o las pruebas verdes no probarán RLS.

---

## 9. Criterios de aceptación

1. `NUCLEO_DATABASE_URL` ausente ⇒ `/api/v1/nucleo/*` responde **503** y el legacy sigue
   operativo. No existe ningún camino por el que el engine del núcleo use el DSN del
   legacy "por defecto".
2. Con `tei_app`: `select current_user` desde una petición del núcleo = `tei_app` y
   `rolbypassrls = false`; con un rol `BYPASSRLS` el módulo núcleo responde 503 y registra
   ERROR (nunca sirve tráfico).
3. Una petición que ejecuta **dos** transacciones (dos `commit()` en el servicio) deja
   `app.empresa_id` y `nucleo.auth_id` vigentes en la segunda: la fila de auditoría de la
   segunda mitad tiene el `auth_id` del usuario, no `'sistema'`.
4. Empresa A no ve ni una fila de B en `viajes`, `clientes`, `facturas_nucleo` y
   `auditoria` (consulta de control con dos empresas de fixture, una por conexión).
5. `X-Empresa-ID` de B con token de A ⇒ **403** (nunca 200 con lista vacía, nunca 500).
6. `X-Empresa-ID` inválido ⇒ **400** antes de consultar la base (no `22P02`).
7. Con `tei_app`, `has_table_privilege('tei_app','public.viajes','SELECT') = false` y
   ninguna ruta del núcleo devuelve datos de `public` salvo el conteo declarado.
8. Escritura normal por el núcleo (crear viaje/maestro) ⇒ 201, filas de auditoría con
   `auth_id` real, y la respuesta no expone mensajes de PostgreSQL.
9. Prueba estática: solo `backend/app/nucleo/servicio_cutover.py` referencia `public.` y
   solo él importa el engine legacy; cualquier otra aparición hace fallar la prueba.
10. `42501` de política ⇒ 403/404; `42501` de `permission denied for table` ⇒ 500 con
    alerta. Prueba HTTP con ambos casos.
11. `make unit`, `make test` y `make e2e` verdes **después** del cambio de rol, con al
    menos una prueba de integración nueva que falle si se retira el `after_begin`
    (mutación: quitar el listener ⇒ la prueba del criterio 3 falla).
12. Rollback ejecutado una vez en un entorno equivalente: volver la versión anterior
    restaura el comportamiento y no pierde datos (conteos antes/después idénticos).

---

## 10. Riesgos y preguntas abiertas

| ID | Riesgo / pregunta | Evidencia | Destinatario | Estado |
|---|---|---|---|---|
| R-1 | El GUC es fijado desde un header **no validado** antes de la autorización. Las políticas que incluyen `empresa_id = ctx` (p. ej. `usuarios_empresa_lectura`, `0020:323-330`) confían en ese contexto: un endpoint que consulte `usuarios_empresa` **antes** de validar membresía podría exponer membresías (auth_id/rol) de una empresa ajena. Hoy ningún endpoint lo hace (el orden de dependencias lo impide) | `0020:323-330`; `deps.py:43-82`; `api.py:69-76` | `datos` + `backend` | **Abierto (bajo, latente).** Mitigación: prueba que falle si un endpoint lee `usuarios_empresa` antes de `get_contexto_empresa`; política futura más estricta (`auth_id = ctx_auth_id() OR es_admin(ctx)`) |
| R-2 | Pooler real (PgBouncer/Supavisor) en modo `transaction` no probado con `SET LOCAL` + rol nuevo | `docs/datos/rls-multiempresa.md:614-615`; `config.toml:45-55` | `datos` + operación | 🔴 **No verificado.** Cierra con una prueba en el entorno desplegado |
| R-3 | Límite de conexiones del proveedor vs dos pools × workers | `database.py:21-23` (sin límites) | operación | 🔴 **No determinable aquí** (no hay cifra verificada del plan) |
| R-4 | Alta de empresa no es operación de la app (`WITH CHECK id = ctx`) | `docs/datos/rls-multiempresa.md:157`; `0020:305-317` | dueño / producto | **Abierto**: si el producto necesita alta por API, requiere `SECURITY DEFINER` acotado o procedimiento de plataforma |
| R-5 | `reservas_recurso.viaje_id` sigue siendo FK simple (INV-T02): no hay fuga bajo RLS, pero una reserva puede apuntar a un viaje de otra empresa y el `EXCLUDE` no lo nota | `docs/datos/rls-multiempresa.md:162`; `0004:727-728` | `datos` | Deuda, no la crea este ADR |
| R-6 | `0020` no crea tablas: una tabla nueva en `nucleo` **no** queda accesible a `tei_app` hasta que su migración dé `GRANT` + política. El defecto es seguro (0 filas/42501) pero se descubre en producción si se olvida | `docs/datos/rls-multiempresa.md:177-179` | `datos` | **Abierto como regla de migración**: checklist obligatorio en cada migración futura |
| R-7 | Las pruebas escriben en la base de la app con el rol privilegiado (RA-13): un verde no prueba RLS | F0 §5 (`:134`); `docs/estado.md` RA-13 | `qa` | **Abierto**: base de test dedicada + `tei_app` para las sesiones de prueba |
| R-8 | `docs/estado.md` y F0 describen `legacy_congelado()` como fail-open, pero el código es fail-closed | `estado.md:78,103,127` vs `servicio_cutover.py:47-63` | `orquestador` / `qa` | **Contradicción documental**: corregir el documento, no el código |
| R-9 | Auditoría: `tei_app` puede insertar filas de auditoría de su empresa; los triggers son `SECURITY DEFINER` y no pasan por RLS | `0004:830-834`; `0020:60-63`; `docs/datos/rls-multiempresa.md:159` | `auditor-seguridad` | Deuda declarada |
| P-1 | ¿Cuándo habrá un segundo tenant? Sin fecha, la urgencia de RLS es de producto, no de código | F0 D-3 (`:154`) | dueño | **Abierta** (no bloquea este ADR) |

**Lo que este ADR NO decide:** no aplica `0020`, no cambia el rol en ninguna base, no
crea el `NUCLEO_DATABASE_URL`, no modifica `scripts/cutover_legacy.py`, no arregla
`42501`→HTTP (lo especifica), no decide D-2 (§7), no decide el retiro del legacy
(`ADR-0002`) ni el canónico por módulo (`ADR-0001`).

---

## 11. Referencias mínimas para ejecutar el handoff

| Pieza | Archivo / símbolo | Cambio esperado |
|---|---|---|
| Engine y sesión | `backend/app/core/database.py` | `legacy_engine` (actual) + `nucleo_engine` (`NUCLEO_DATABASE_URL`), `get_nucleo_session`, listener `after_begin`, guarda de rol |
| Contexto | `backend/app/nucleo/deps.py` | pasar a `get_nucleo_session`; el contexto se llena en la dependencia de sesión (un solo punto); mantener autorización |
| `mis-empresas` | `backend/app/nucleo/api.py:69-76` | usar la sesión del núcleo (el `auth_id` llega por el GUC) |
| Excepción `public` | `backend/app/nucleo/servicio_cutover.py:85-102` | el conteo legacy se ejecuta con `legacy_engine` |
| Errores | `backend/app/main.py`, `backend/app/nucleo/errores.py` | handler de `42501` con dos causas distinguibles (política vs GRANT) |
| Pruebas | `backend/tests/**`, `supabase/tests/**` | fixtures con rol de plataforma; consultas con `tei_app`; mutación del listener |
| Configuración | `backend/.env.example` (sin valores) | `NUCLEO_DATABASE_URL` documentada como obligatoria y sin *fallback* |
| Operación | `docs/operacion/` (dueño: `orquestador`) | declaración de `public` no aislado; quién usa el rol de plataforma; rollback por versión |
