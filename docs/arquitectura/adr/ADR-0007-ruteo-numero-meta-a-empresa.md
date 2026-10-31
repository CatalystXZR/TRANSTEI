# ADR-0007: Ruteo `wa_phone_number_id → empresa_id` — cómo obtiene el runtime la empresa antes de leer el contacto

- **Estado:** **Propuesto (2026-10-31)** — la decisión es del **dueño**; este ADR no
  la toma por delegación. Bloquea el runtime O3 (webhook + resolución de contexto);
  el buzón humano de O2.4 no depende de este ruteo (usa JWT + `X-Empresa-ID`).
- **Fecha:** 2026-10-31
- **Decide:** `arquitectura` propone; **aprueba el dueño** (con `auditor-seguridad`
  como revisor de la opción elegida, por tratarse de tenant y PII).
- **Relación:** cierra el hueco que `docs/backend/informes/o2-1-registry-gate-tools.md:102-131`
  escaló y que el contrato `docs/arquitectura/conector-agente-whatsapp.md` (§4.1
  paso 2) describe como búsqueda **global**. No modifica ADR-0003, ADR-0005
  ni ADR-0006; los usa.
- **Documento operativo que actualiza:** `conector-agente-whatsapp.md` §4.1 (nota de
  ruteo y remisión a este ADR).

---

## Contexto

Hechos verificados por lectura de DDL/código en esta sesión. La única medición de
comportamiento es **heredada** del orquestador y se cita como tal.

| # | Hecho | Evidencia | Nivel |
|---|---|---|---|
| 1 | `nucleo.contactos_whatsapp` tiene `empresa_id NOT NULL` y `telefono NOT NULL`; la identidad `(empresa, rol, entidad)` sale de esa fila | `supabase/migrations/0021_agente_whatsapp.sql:179-216` | 🟢 |
| 2 | Un teléfono **activo** resuelve a **un solo** contacto en todo el sistema: `uq_contactos_telefono_activo (telefono) where activo`, **sin `empresa_id`** en la clave | `0021:218-223`; `docs/datos/agente-esquema.md:249-258` | 🟢 |
| 3 | RLS: `contactos_whatsapp` tiene política `tenant_empresa … using (empresa_id = nucleo.ctx_empresa())`; sin `app.empresa_id` válido, `ctx_empresa()` es `NULL` y la tabla devuelve 0 filas | `0021:799-814` (tabla en la lista de `:804`); `0020:178-195` | 🟢 |
| 4 | Medido con `tei_app` en `tei_test`: sin `app.empresa_id` → 0 filas; con la empresa dueña → 1; con empresa ajena → 0. **Medición del orquestador, no re-ejecutada en esta sesión** | `docs/backend/informes/o2-1-registry-gate-tools.md:108-113` | 🟢 (heredada) |
| 5 | El contrato §4.1 paso 2 describe una búsqueda **global** por `telefono` (`uq_contactos_telefono_activo`, `0021:222-223`), incompatible con el hecho 3 | `conector-agente-whatsapp.md` §4.1 paso 2 | 🟢 |
| 6 | **No existe** tabla ni columna `wa_phone_number_id` (ni equivalente) en `supabase/migrations/`; búsqueda `wa_phone\|phone_number\|waba\|numero_meta` = 0 coincidencias. La única columna cercana es `conversacion_mensajes.wa_message_id`, que es **por mensaje**, no por número de negocio | `0021:315-347`; búsqueda en migraciones | 🟢 |
| 7 | Mitigación provisional **implementada**: `resolver_contacto(empresa_id, telefono, request_id)` exige `empresa_id` (keyword-only), filtra por él en SQL y devuelve `None` si el teléfono no está en esa empresa | `backend/app/nucleo/agente/contexto.py:143-189`; SQL en `:65-79`; `None` en `:169-170` | 🟢 |
| 8 | El propio código declara que en producción `empresa_id` viene de `metadata.phone_number_id → una empresa`, no del cuerpo del mensaje | `contexto.py:14-24` | 🟢 |
| 9 | `empresa_id` **nunca** sale del DI ni del body; la empresa es del contacto | ADR-0006 `Decisión 1` (`ADR-0006-identidad-y-alcance-tools-agente.md:61-64`); ADR-0003 §3.4 | 🟢 |
| 10 | Precedente de resolución "antes de tener empresa": `nucleo.empresas_del_usuario()` es `SECURITY DEFINER` y deriva la identidad de un **GUC**, nunca de un parámetro, porque "un parámetro sería un enumerador de tenants" | `0020:216-238` (comentario en `:219`) | 🟢 |
| 11 | `nucleo.modulos_empresa` (0023) ya existe como migración en el repo; su aplicación en cada entorno no se verificó aquí | `supabase/migrations/0023_modulos_empresa.sql:183-202` | 🟢 (archivo) / 🔴 (aplicación) |

**Contradicciones documentales que este ADR deja explícitas:**

- `conector-agente-whatsapp.md` §2.7 y §9.1 (B1) siguen declarando
  `nucleo.modulos_empresa` como faltante; el archivo `0023` ya existe en el repo
  (hecho 11). §2.7 lleva ahora una nota fechada que separa "archivo en el repo" de
  "tabla aplicada en el entorno" (🔴, no verificado); no se reescribe la propuesta.
- `conector-agente-whatsapp.md` §4.1 paso 2 describe una lectura que el hecho 3
  hace imposible con el rol de la aplicación. Se corrige con una nota en §4.1 que
  apunta a este ADR (no se reescribe el paso como si la decisión estuviera tomada).

---

## Problema

**En una frase verificable:** *¿de dónde obtiene el runtime el `empresa_id` con el
que fija `app.empresa_id` para resolver un contacto por teléfono, sin tomarlo del
cuerpo del mensaje y sin una lectura global del teléfono que RLS bloquea?*

Hoy hay dos mitades que no se tocan: el contrato pedía buscar por teléfono en
global (hecho 5; §4.1 paso 2 ya deja anotado que no es ejecutable y remite acá), y
la base solo permite buscar **dentro** de una empresa (hechos 1-4). La mitigación
actual (hecho 7) es correcta pero mueve el problema al llamador: exige un
`empresa_id` que todavía nadie sabe de dónde sacar. O3 no puede encenderse hasta
que exista una fuente de ese valor.

---

## Alternativas

### A. Configuración de despliegue por número de Meta (allow-list `phone_number_id → empresa_id`)

El runtime lee de su configuración (entorno/gestor de secretos) el mapa
`wa_phone_number_id → empresa_id`, lo valida al arrancar y lo usa para fijar
`app.empresa_id` **antes** de llamar a `resolver_contacto`.

| Dimensión | Evaluación |
|---|---|
| Garantías | El valor no viene del mensaje: viene de un allow-list que solo el despliegue puede cambiar. Un `phone_number_id` desconocido **no produce empresa** (fail-closed). La garantía crítica sigue en la base: aun con un mapeo equivocado, la fila del contacto solo aparece si pertenece a esa empresa (hecho 3). |
| Qué se filtra si falla | Si el mapa apunta a la empresa equivocada, la búsqueda corre en la empresa equivocada y devuelve **0 filas** (hecho 7) → respuesta genérica, sin fila de auditoría (§7.6). Solo habría lectura cruzada si el mismo teléfono estuviera activo en ambas empresas, y hoy el índice global lo impide (hecho 2). |
| Coste de migración | **Cero** esquema, cero migración, cero permiso nuevo. Es configuración + una función de arranque y sus pruebas. |
| Mismo teléfono en dos empresas | Sin cambio: `uq_contactos_telefono_activo` lo impide (hecho 2). Ver §Riesgos. |
| Reversible | Alta: revertir el despliegue/valor. No hay datos que deshacer. |
| Cambio de mapa | Requiere redeploy; no queda registro consultable en base. |

### B. Tabla de ruteo `nucleo.wa_numeros_empresa` (propuesta, no existe) con política propia

Tabla nueva `(wa_phone_number_id text primary key, empresa_id uuid not null
references nucleo.empresas(id), activo boolean not null default true, …)`. El
runtime la lee **antes** de tener empresa.

El punto delicado: una política `empresa_id = nucleo.ctx_empresa()` **no sirve**
para esta tabla, porque el lector justamente no conoce la empresa todavía. Dos
diseños posibles, ambos propuestas:

- **B1 (recomendado dentro de B):** política `for select to public using
  (wa_phone_number_id = current_setting('app.wa_phone_number_id', true) and activo)`.
  El runtime fija ese GUC con el valor recibido del webhook y solo puede leer **su**
  fila; no puede enumerar el mapa. Sigue el precedente del hecho 10: la identidad
  sale del contexto, no de un parámetro de consulta.
- **B2:** política de directorio `using (activo)` para `tei_app`. Más simple, pero
  permite enumerar todo el mapa número→empresa. No recomendado.

| Dimensión | Evaluación |
|---|---|
| Garantías | Igual que A para la resolución del tenant (la base sigue siendo el árbitro del contacto). Suma: el mapa es dato gobernado, se puede cambiar sin redeploy y su escritura puede auditarse. |
| Qué se filtra si falla | Número desconocido o `activo=false` → 0 filas → sin empresa → respuesta genérica. Fila mal cargada → misma consecuencia que A. Si se elige B2, un compromiso de `tei_app` enumera el mapa (no datos de negocio). |
| Coste de migración | **M**: migración `0024` (tabla + política + GRANT sin `DELETE` + comentarios), backfill desde la configuración de A, pruebas con `tei_app` (número propio, número ajeno, sin GUC → 0 filas). Detalle: `fn_auditoria` extrae `new.id::uuid` (`0004:830-878`) y una PK textual no tiene `id`; o se agrega `id uuid` o la tabla se audita con función propia — el mismo hueco que 0023 declaró (`0023:67-72`). |
| Mismo teléfono en dos empresas | Sin cambio por sí sola: el índice global sigue decidiendo (hecho 2). Lo que habilita B es **varios números de Meta para varias empresas**, no el mismo cliente en dos. |
| Reversible | Alta: `drop table` (nace vacía) o dejar la tabla inerte volviendo al runtime de A. |

### C. Función `SECURITY DEFINER` acotada `nucleo.empresa_de_telefono(telefono)`

Resuelve la empresa leyendo `contactos_whatsapp` con los privilegios del dueño,
saltando RLS.

| Dimensión | Evaluación |
|---|---|
| Garantías | Restaura la letra del §4.1 paso 2. La función es el único camino privilegiado y puede auditarse. |
| Qué se filtra si falla | `NULL` → sin contexto → respuesta genérica. Pero el modo de fallo es peor que A/B: `EXECUTE` mal otorgado, `search_path` mal fijado o una futura variante que devuelva la fila convierten una función de resolución en un **enumerador de tenants indexado por PII**. El repo ya rechazó ese patrón para `usuarios_empresa` (hecho 10). Además la entrada es el teléfono del **cliente** (PII), cuando el webhook ya trae un identificador del número **de negocio**. |
| Coste de migración | **S/M**: función + `REVOKE`/`GRANT` + revisión de seguridad + pruebas de mutación. |
| Mismo teléfono en dos empresas | La función no lo resuelve: el índice global lo impide (hecho 2). |
| Reversible | Alta (`drop function`), pero deja un camino privilegiado que hay que recordar retirar. |

### Alternativas descartadas sin tabla

- **Agregar `wa_phone_number_id` a `nucleo.contactos_whatsapp`:** no resuelve nada,
  porque para leer la fila hace falta `empresa_id`; y un contacto puede recibir
  mensajes por más de un número de negocio. Sería una columna que no se puede
  consultar primero.
- **Reutilizar `conversaciones` o `conversacion_mensajes`:** `wa_message_id` es por
  mensaje y ya llega con el mensaje; no identifica el número de negocio ni la
  empresa antes de tener contexto (`0021:315-347`).
- **Un GUC `app.empresa_id` puesto por el BSP:** el BSP no es una autoridad del
  ERP; el valor seguiría siendo entrada no confiable.

### Comparación

| Alternativa | Garantía del tenant | Coste | Multiempresa real | Auditoría del mapa | Riesgo si falla |
|---|---|---|---|---|---|
| **A. Configuración de despliegue** | Base (contacto) + allow-list de código | **Nulo** | Sí, con el mapa en configuración; cambiarlo exige redeploy | Solo historial de despliegue | 0 filas (fail-closed) |
| **B. Tabla de ruteo (B1)** | Base + fila gobernada | **M** (migración) | Sí, sin redeploy | Posible, con el ajuste de `fn_auditoria` | 0 filas (fail-closed) |
| **C. `SECURITY DEFINER` por teléfono** | Función privilegiada | S/M + revisión | Sí | Sí | 0 filas, o enumeración si el `GRANT`/`search_path` se degrada |

---

## Decisión

**Recomendación: A para el piloto, con B1 como destino declarado y camino de
migración escrito; C queda descartada como mecanismo por defecto.**

Razón, en el orden del método:

1. **El problema es "obtener un valor de configuración de despliegue", no "modelar
   ruteo multiempresa".** El piloto declarado opera con una sola empresa (🟡: no
   verificado en base en esta sesión) y `public` no es multiempresa (ADR-0005,
   hecho 13). A resuelve exactamente eso, sin tabla, sin política nueva y sin
   ampliar privilegios.
2. **La garantía crítica no se mueve.** Aunque el mapa esté mal, el acceso al dato
   sigue cerrado por RLS y por el filtro explícito de `resolver_contacto`
   (hechos 3 y 7). La configuración elige el tenant; la base decide si el contacto
   existe en él. Eso es lo que el catálogo exige: garantía en PostgreSQL, no en el
   servicio.
3. **C es la opción con peor relación garantía/coste:** introduce una lectura
   privilegiada indexada por PII y un enumerador potencial, para resolver un valor
   que el webhook ya trae (el número de negocio). Si en el futuro se necesita
   resolver por teléfono sin número de negocio (p. ej. un mensaje que llega por un
   canal compartido), eso merece su propio ADR con revisión de seguridad, no una
   función "por si acaso".
4. **B no se descarta: se posterga con condición observable.** Se paga cuando
   aparezca cualquiera de estas: (i) una segunda empresa con números propios;
   (ii) necesidad de cambiar el ruteo sin redeploy; (iii) exigencia de auditar en
   base quién cambió el mapeo. Mientras no ocurra, la tabla sería una dependencia
   operativa sin problema que resuelva.

**Estado: Propuesto.** La aprobación del dueño debe responder, como mínimo:

| # | Pregunta al dueño | Consecuencia |
|---|---|---|
| P-1 | ¿Se autoriza A para el piloto (mapa `phone_number_id → empresa_id` en configuración, validado al arrancar)? | O3 puede implementar el webhook con el ruteo por configuración. |
| P-2 | ¿Habrá una segunda empresa **dentro del piloto**? | A sigue siendo viable con un mapa de varios números; si la segunda empresa es inminente, B1 pasa a ser preferible (cambio sin redeploy + auditoría) y se decide antes de O3.2. |
| P-3 | ¿Se acepta que el mapa no tenga historial consultable en base durante el piloto? | Si no, B1 desde el inicio. |
| P-4 | ¿Un mismo teléfono puede necesitar ser contacto de dos empresas (p. ej. un conductor que trabaja para dos transportistas)? | Si sí, hay que revisar `uq_contactos_telefono_activo` (hecho 2), que hoy lo impide; es otro ADR, no una variante de este. |

---

## Consecuencias

**Positivas**

- O3 desbloqueado con **cero** cambios de esquema.
- El error de ruteo es fail-closed y se detecta como "teléfono no registrado"
  (respuesta genérica), no como lectura de otro tenant.
- No se agrega una dependencia operativa nueva (ni tabla, ni worker, ni servicio).
- La decisión es reversible por configuración, sin migración inversa.

**Negativas / deuda que genera**

- El mapa vive fuera de la base: no es consultable por la plataforma ni queda
  auditado por trigger; la evidencia es el historial de despliegue. **Se paga con
  B1** cuando el ruteo deje de ser un detalle de despliegue.
- Cada número nuevo (o cambio de empresa) exige redeploy en el piloto.
- Si el runtime no valida el mapa al arrancar, un `phone_number_id` desconocido se
  convierte en "todos los mensajes genéricos" sin señal clara; por eso el criterio
  de aceptación 5 exige fallo ruidoso al arrancar con mapa vacío.

---

## Plan de migración y rollback

### Activación de A (piloto)

1. `backend` define el mapa en la configuración del runtime (nunca en el repo ni en
   `docs/`; `AGENTS.md` §4) y una validación de arranque: cada valor debe ser un
   UUID y cada `phone_number_id` no vacío; mapa vacío ⇒ el proceso **no arranca**
   (fail-closed ruidoso).
2. El runtime fija `app.empresa_id` con el valor resuelto y llama a
   `resolver_contacto(empresa_id=…, telefono=…, request_id=…)` (sin cambios en
   `contexto.py`).
3. Si el `phone_number_id` no está en el mapa: **no** se llama a
   `resolver_contacto`; respuesta genérica de enrolamiento, log con hash del
   teléfono y `request_id`, sin fila en `auditoria_consultas_agente` (§7.6).
4. Evidencia de cierre: prueba con dos empresas y dos números (criterios 1-3).

### Camino de migración A → B1 (cuando se cumpla la condición de pago)

1. `datos` crea la migración **`0024` (propuesta)**: tabla, PK
   `wa_phone_number_id`, FK a `nucleo.empresas`, `activo`, política B1, GRANT
   `select` a `tei_app` (sin `insert/update/delete`: la escribe la plataforma),
   comentarios. Precondiciones: tabla inexistente, 0 filas. Rollback: `drop table`.
2. **Backfill del mapa actual**: se carga desde la configuración vigente de A con
   el rol de plataforma; el conteo de filas debe coincidir con el número de
   entradas del mapa (evidencia registrada). No se inventan filas.
3. El runtime pasa a **leer la tabla primero** y, solo si no hay fila, usa la
   configuración (ventana de doble lectura declarada). Se registra en el log cuál
   fuente resolvió, para poder retirar la configuración con evidencia.
4. Tras un período con 0 resoluciones por configuración (dato observable en el
   log), se retira el mapa de despliegue y la rama de fallback.
5. **Rollback en cualquier punto:** volver el runtime a A (la tabla puede quedar
   inerte o dropearse; no hay datos de negocio).

**Orden no invertible:** no se retira la configuración antes de que la tabla esté
poblada y probada; hacerlo deja todos los mensajes en respuesta genérica.

---

## Criterios de aceptación

Con `tei_app` (sin `BYPASSRLS`) y dos empresas de fixture A y B:

1. `phone_number_id` de A + teléfono enrolado en A ⇒ `resolver_contacto` devuelve
   el contacto y la tool ejecuta con `app.empresa_id = A`.
2. `phone_number_id` desconocido ⇒ **no** se resuelve contacto, respuesta genérica,
   **0 filas** nuevas en `auditoria_consultas_agente`.
3. `phone_number_id` de A + teléfono enrolado **solo** en B ⇒ `None` (0 filas) y
   respuesta genérica; la consulta no lee ni una fila de B (misma prueba que
   `test_resolver_contacto_deniega_otra_empresa`).
4. Prueba estática: ningún camino del runtime toma `empresa_id` del cuerpo del
   webhook, del DI ni de la entrada de la tool (grep del paquete + prueba que falla
   si aparece).
5. Mapa vacío o valor no-UUID al arrancar ⇒ el runtime falla al iniciar con
   mensaje explícito (no arranca "a medias").
6. Cambio de mapa documentado como cambio de despliegue (commit + registro de
   cambio), sin valores de secretos en `docs/`.
7. Si se implementa B1: número sin GUC `app.wa_phone_number_id` ⇒ 0 filas; número
   con GUC propio ⇒ 1; número con GUC ajeno ⇒ 0; `tei_app` sin `INSERT/UPDATE/
   DELETE` sobre la tabla.

---

## Riesgos y preguntas abiertas

| ID | Riesgo / pregunta | Evidencia | Destinatario | Estado |
|---|---|---|---|---|
| R-1 | **Mismo teléfono en dos empresas está prohibido hoy**: `uq_contactos_telefono_activo` es global (sin `empresa_id`). Un conductor que trabaje para dos transportistas no puede ser contacto activo de ambas. El índice existe a propósito (una identidad por número); cambiarlo es otro ADR y afecta la anti-enumeración | `0021:218-223`; `docs/datos/agente-esquema.md:249-274` | dueño + `negocio-finanzas` | 🔴 **No determinable**: depende de si ese caso existe en el negocio |
| R-2 | **Semántica y estabilidad de `phone_number_id`** (¿es único por número de negocio?, ¿cambia si se migra de WABA o de BSP?) no está verificada en el repo; `contexto.py:14-24` la asume | `contexto.py:14-24`; sin documentación de Meta en el repo | `backend` (con el BSP) | 🔴 **No verificado**; confirmarlo antes de congelar el mapa |
| R-3 | **El webhook debe estar autenticado** (firma HMAC) antes de confiar en `phone_number_id`; hoy O3.1 no existe | `conector-agente-whatsapp.md` §1.2 (runtime premium, Ola 3) | `backend` | Dependencia declarada: sin firma, cualquier llamador elige el número |
| R-4 | Si el dueño elige B1, la política debe fijarse con `current_setting(..., true)` y tratar vacío como `NULL` (patrón de `ctx_empresa`), o un GUC vacío podría coincidir con una fila de `wa_phone_number_id=''` | `0020:178-195` | `datos` | Abierto (solo si se aprueba B1) |
| R-5 | El mapa de A no tiene auditoría en base; una mala edición solo se detecta por síntoma (mensajes genéricos) | Este ADR, §Consecuencias | dueño / operación | Aceptado para el piloto; se paga con B1 |
| R-6 | `conector-agente-whatsapp.md` §2.7 y §9.1 siguen declarando `0023` como faltante, pero la migración existe en el repo. El estado de aplicación por entorno no se verificó; §2.7 ya lleva una nota del 2026-10-31 | `0023_modulos_empresa.sql:183-202`; `conector` §2.7, §9.1 | `arquitectura` / `orquestador` | 🟡 Documental; no cambia esta decisión |

**Lo que este ADR no decide:** no crea la tabla `nucleo.wa_numeros_empresa`, no
escribe la migración `0024`, no toca `resolver_contacto`, no define el contrato del
webhook (O3.1) ni la firma HMAC, y no cambia `uq_contactos_telefono_activo`.
