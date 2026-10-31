# Conector del agente WhatsApp — manifiesto, tools, gate y contrato del buzón

> **Dueño:** `arquitectura` · **Estado:** Propuesto (F2.1; habilita O2.1–O2.7) ·
> **Verificado:** 2026-10-30 · **Método:** lectura estática de DDL, servicios,
> routers y documentos; **sin base, sin ejecución y sin shell en esta sesión**.
> Las citas 🟢 son texto leído; lo que depende de estado de base o de ejecución
> queda 🟡/🔴 y se dice qué lo confirmaría.
>
> **Relación:** concreta la frontera de ADR-0003 §4 (el agente lee por tools y
> crea Solicitudes; nunca ejecuta un estado de negocio), §13 (ACL por número),
> §14 (aprobación de hoja de ruta) y §16 (ID comercial). Toma de ADR-0004 §3.1.1
> la asignación de modelos y de §6 las reglas de swap. La identidad de ejecución
> es la de **ADR-0006** (`ContextoAgente`), que este documento usa sin
> reemplazarla.
>
> **Alcance estricto:** módulo `agente-whatsapp`. **No** es la especificación de
> seams, slots y hooks de la plataforma (`docs/arquitectura/destino-modular.md`);
> esos contratos son de F2.2 y no se tocan acá.

---

## 0. Resumen ejecutivo

1. El módulo se declara en un **manifiesto** `agente-modulo/v1` con
   `habilitado_por_defecto: false` literal (DEC-10). Un manifiesto inválido no
   tumba la API: deja **0 tools** y el estado se ve en `GET /nucleo/agente/estado`.
2. La identidad de una tool es **`ContextoAgente`** (empresa, contacto, rol,
   entidad, conversación, mensaje, `request_id`), resuelta desde la fila del
   contacto. No se fabrica un `ContextoEmpresa` ni se impersona un rol del núcleo
   (ADR-0006).
3. El **gate** es una cadena de cuatro llaves en serie: módulo activo por empresa
   → rol del contacto → toggle de componente en `permisos_contacto` → toggle de
   variable. Ausencia de fila o `permitido=false` = denegación. La base impone
   estructura; el gate impone la ausencia (INV-AW07).
4. El catálogo inicial declara **20 tools** (8 cliente, 4 conductor, 8 admin) y una
   diferida (`gerente.consultar`, ADR-0003 §13.2 / D-09). De las 20, **19 son
   registrables hoy**: `A5 mantenimiento` queda fuera del manifiesto hasta que el
   objeto exista en `nucleo` (§5.7). El agente escribe solo tablas del módulo; las
   escrituras de negocio siguen siendo del componente dueño tras aprobación
   (DEC-11).
5. El **buzón** es HTTP humano (JWT + `X-Empresa-ID` + permiso) con tres acciones:
   Confirmar, Rechazar y Modificar. Rechazar **no ejecuta escritura de negocio**.
   Dos aprobadores concurrentes: uno gana, el otro recibe 409.
6. La **auditoría** es una fila por intento terminado en
   `nucleo.auditoria_consultas_agente`, append-only, escrita en su propia
   transacción. `acceso_otorgado` es el veredicto del gate, no el éxito de la tool.
   Un teléfono no registrado no puede auditarse ahí (FK `contacto_id` NOT NULL):
   va al log del runtime.

**Bloqueo único de F2.1:** no existe tabla de módulo activo por empresa. Sin
`nucleo.modulos_empresa` (migración `0023` propuesta en §2.7) el gate queda
cerrado y ninguna tool se ejecuta. Es un bloqueo de `datos`, no una decisión de
`backend`.

---

## 1. Alcance y no alcance

### 1.1 Qué resuelve F2.1

| Pieza | Contrato que fija | Consumidor |
|---|---|---|
| Manifiesto del módulo | esquema, validación, default OFF, kill-switch por manifiesto inválido | `backend` O2.1 |
| Descriptor de tool | campos, JSON Schema de entrada/salida, ejecutor permitido, idempotencia, límites | `backend` O2.1/O2.2 |
| Registry | carga inmutable, resolución por nombre, prohibición de import dinámico | `backend` O2.2 |
| Gate | cadena de autorización, denegación por defecto, códigos de error, auditoría del intento | `backend` O2.2 |
| Catálogo inicial | 20 tools declaradas (19 registrables hoy; `A5` bloqueada) con componente, variable, rol, alcance y datos de origen | `backend` O2.1–O2.7, `frontend` O4 |
| Contrato del buzón | endpoints, bodies, errores, concurrencia, autoaprobación | `backend` O2.4, `frontend` O4.3 |
| Auditoría | columnas, momento de escritura, mapeo D-17, casos denegados | `backend` O2.7, `frontend` O4.5 |
| Versión de modelos | bloque del manifiesto, `schema_di`, swap y rollback | `backend` O3.3/O3.7 |

### 1.2 Qué **no** resuelve (y no debe inventarse acá)

- **Seams/slots/hooks de la plataforma** (`destino-modular.md`): son F2.2, no
  F2.1. Este documento no define puntos de extensión genéricos.
- **Runtime premium (Ola 3):** webhook, firma HMAC, descarga de media, ASR,
  visión, orquestador, envío de mensajes. Acá solo se fija el contrato que el
  runtime consume: manifiesto, tools y envelope de resultado.
- **Enrolamiento/OTP (O2.3):** el gate exige `activo` y `otp_estado='verificado'`
  (INV-AW03), pero el flujo de emisión/verificación/revocación es O2.3 y D-12.
- **Ejecutores de negocio:** la tool de lectura puede implementarse con los
  servicios actuales; las escrituras de `agendamiento` y `documentos` no tienen
  ejecutor en F2.1. El buzón devuelve 501 `TIPO_SIN_EJECUTOR` hasta que exista
  (ver §6.7).
- **Frontend:** el contrato HTTP y los tipos; las pantallas son O4.
- **Matriz de aprobación (AB-02):** qué rol aprueba cada tipo es decisión de
  negocio, no de este documento (§9.5).
- **D4/D-18:** la unicidad del prefijo y la resolución por código es decisión del
  dueño; acá se fija la regla de trabajo que no requiere migración (§5.9).
- **D-17:** retención y acceso a la auditoría siguen abiertos (§9.6).
- **D8:** el índice global de `wa_message_id` no se cambia en F2.1 (§9.4).

### 1.3 Reglas que hereda y no puede contradecir

| Regla | Fuente | Consecuencia en este contrato |
|---|---|---|
| `public` es legacy; `nucleo` es destino; no hay tercera fuente | `AGENTS.md:116` | Ninguna tool lee ni escribe `public`; todo el módulo vive en `nucleo`. |
| El agente opera por tools, no SQL libre; apagado por defecto | `docs/PLAN_DESARROLLO.md:48` (DEC-10) | El manifiesto no acepta SQL, tabla ni ejecutor dinámico; `habilitado_por_defecto=false`. |
| Escrituras sensibles = solicitud + aprobación humana | `docs/PLAN_DESARROLLO.md:49` (DEC-11) | La tool de escritura solo inserta en `solicitudes`/`hoja_ruta`; nunca en tablas de negocio. |
| `timestamptz` UTC; `date` para vigencias; rangos `[inicio, fin)` | `AGENTS.md:124` | Entradas/salidas usan RFC 3339 con `Z`; las fechas de vencimiento son `date`. |
| Dinero en `numeric`, nunca `float` | `AGENTS.md:125` | Los montos viajan como **string decimal** en el JSON de la tool, con `moneda`. |
| Garantía crítica en PostgreSQL o transacción demostrada | `AGENTS.md:126` | Idempotencia, unicidad y transiciones se apoyan en constraints/triggers existentes; el gate no reemplaza la base. |
| Aislamiento multiempresa verificado en servidor y base | `AGENTS.md:127` (texto desactualizado: habla de “RLS sin políticas”); `docs/estado.md:103` (RA-03: `0020` aplicada, 35 políticas, app con `tei_app`) | Toda consulta fija `app.empresa_id`; el rol efectivo debe ser `tei_app` (sin `BYPASSRLS`). El fallback a `DATABASE_URL` deja RLS inerte (`backend/app/core/database.py:26-35`). |
| Todo endpoint declara permiso (deny-by-default) | `AGENTS.md:221` | Los endpoints del buzón usan `requiere_permiso`; el camino del agente **no**. |
| Auditoría append-only, cobertura parcial | `AGENTS.md:223` | `auditoria_consultas_agente` es append-only; el legacy no está cubierto. |

---

## 2. Manifiesto del módulo

### 2.1 Archivo y ubicación propuesta

| Objeto | Ruta propuesta | Dueño |
|---|---|---|
| Manifiesto | `backend/app/nucleo/agente/manifest.json` | `backend` |
| Descriptores de tools | `backend/app/nucleo/agente/tools/*.json` | `backend` |
| Schemas de entrada/salida | `backend/app/nucleo/agente/schemas/*.json` | `backend` |
| Registro de ejecutores | `backend/app/nucleo/agente/ejecutores.py` (dict cerrado) | `backend` |

La ruta es una propuesta de implementación, no una imposición de arquitectura: lo
que sí es contrato es el **contenido** y las **reglas de validación**. Si
`backend` elige empaquetar el manifiesto como constante Python, debe producir
exactamente el mismo documento validable y exponerlo en `GET /nucleo/agente/estado`.

### 2.2 Esquema `agente-modulo/v1`

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `schema` | string | sí | Literal `"agente-modulo/v1"`. Otro valor → manifiesto inválido. |
| `modulo_id` | string | sí | Literal `"agente-whatsapp"`. |
| `version` | string | sí | Semver del manifiesto (`0.1.0`); no es la versión de las tools. |
| `habilitado_por_defecto` | boolean | sí | **Debe ser `false`** (DEC-10). `true` → inválido, no se “corrige” en runtime. |
| `schema_di` | string | sí | Literal `"di/v1"` (ADR-0003 §3.4). Un DI con otro `schema` se rechaza. |
| `migraciones` | array[string] | sí | Nombres de archivo en `supabase/migrations/` que el módulo requiere. No se ejecutan: se verifican y se reportan faltantes. |
| `roles` | array[string] | sí | Subconjunto cerrado de `admin`, `cliente_final`, `conductor` (`0021:151`). |
| `componentes` | array[string] | sí | Lista cerrada de componentes que el manifiesto puede usar. Toda tool debe declarar uno de estos. |
| `permisos_modulo` | array[string] | sí | Subconjunto de `agente:buzon`, `agente:aprobar`, `agente:contactos`. Son permisos **humanos**; no se usan en el camino del agente. |
| `aprobacion` | object | sí | `{ "modo": "solicitud", "autoaprobacion": false }`. `autoaprobacion=true` → inválido (DEC-11). |
| `modalidades` | object | sí | `{ "texto": bool, "voz": bool, "imagen": bool, "pdf": bool }`. El default de todas es `false`; activar una exige evaluación ADR-0003 §15. |
| `modelos` | object | sí | Ver §8. Cuatro claves: `orquestador`, `asr`, `vision`, `pdf`; cada una con `proveedor`, `modelo`, `revision`, `prompt_version`. |
| `tools` | array[object] | sí | Lista de `{ "$ref": "tools/<archivo>.json" }`. No se aceptan descriptores inline ni rutas absolutas. |

### 2.3 Ejemplo (abreviado; el manifiesto real lista las tools registrables — 19 hoy)

```jsonc
{
  "schema": "agente-modulo/v1",
  "modulo_id": "agente-whatsapp",
  "version": "0.1.0",
  "habilitado_por_defecto": false,
  "schema_di": "di/v1",
  "migraciones": [
    "0021_agente_whatsapp.sql",
    "0022_agente_whatsapp_endurecimiento.sql",
    "0023_modulos_empresa.sql"
  ],
  "roles": ["admin", "cliente_final", "conductor"],
  "componentes": [
    "despacho", "facturacion", "cobranza", "flota",
    "mantenimiento", "gastos", "hoja_ruta", "solicitudes"
  ],
  "permisos_modulo": ["agente:buzon", "agente:aprobar", "agente:contactos"],
  "aprobacion": { "modo": "solicitud", "autoaprobacion": false },
  "modalidades": {
    "texto": true,
    "voz": false,
    "imagen": false,
    "pdf": false
  },
  "modelos": {
    "orquestador": {
      "proveedor": "anthropic",
      "modelo": "claude-opus-4.7",
      "revision": "configurada-en-deploy",
      "prompt_version": "sha256:…"
    },
    "asr": {
      "proveedor": "openai",
      "modelo": "whisper-3",
      "revision": "configurada-en-deploy",
      "prompt_version": "n/a"
    },
    "vision": {
      "proveedor": "openai",
      "modelo": "gpt-5.x",
      "revision": "configurada-en-deploy",
      "prompt_version": "sha256:…"
    },
    "pdf": {
      "proveedor": "anthropic",
      "modelo": "claude-opus-4.7",
      "revision": "configurada-en-deploy",
      "prompt_version": "sha256:…"
    }
  },
  "tools": [
    { "$ref": "tools/despacho.mis_fletes.json" },
    { "$ref": "tools/hoja_ruta.proponer.json" },
    { "$ref": "tools/solicitudes.bandeja.json" }
  ]
}
```

> Los nombres de modelo del ejemplo **copian** la asignación ratificada en
> ADR-0004 §3.1.1 (fechada 2026-10-31 en el repo); no son una elección nueva de
> este documento. El ID exacto de API lo fija el proveedor y se guarda en
> `modelo`/`revision`; cambiarlo es configuración + re-evaluación, no código
> (ADR-0004 §6).

### 2.4 Reglas de validación

| # | Regla | Si falla |
|---|---|---|
| V1 | JSON válido, sin claves duplicadas | Manifiesto inválido. |
| V2 | Validación estricta contra `agente-modulo/v1`; campos desconocidos → error (`extra=forbid`) | Manifiesto inválido. |
| V3 | `habilitado_por_defecto` es exactamente `false` | Manifiesto inválido (no se degrada a `false` en silencio). |
| V4 | `schema_di` es exactamente `di/v1` | Manifiesto inválido. |
| V5 | Cada `$ref` es relativo, empieza con `tools/`, no contiene `..`, no es absoluto y el archivo existe | Manifiesto inválido. |
| V6 | Cada descriptor valida contra el esquema de §3; `nombre` único | Manifiesto inválido. |
| V7 | `componente` de cada tool ∈ `componentes` | Manifiesto inválido. |
| V8 | `roles` de cada tool ⊆ `roles` del manifiesto y no vacío | Manifiesto inválido. |
| V9 | `permiso == componente + ":" + variable` | Manifiesto inválido. |
| V10 | `ejecutor` ∈ allow-list cerrada de `ejecutores.py` | Manifiesto inválido. |
| V11 | `timeout_ms` entero 100–5000; `max_filas` entero 1–200 en lectura; en escritura `max_filas` ausente/null | Manifiesto inválido. |
| V12 | `tipo=escritura_solicitud` ⇒ `idempotencia.modo="clave"` y campo `clave_idempotencia` declarado | Manifiesto inválido. |
| V13 | `entrada` y `salida` son JSON Schema draft 2020-12 válidos; raíz `type=object`; `additionalProperties=false` | Manifiesto inválido. |
| V14 | `alcance=propio` ⇒ el schema de entrada no declara `cliente_id`, `chofer_id`, `empresa_id`, `contacto_id` ni `rol` | Manifiesto inválido. |
| V15 | `permisos_modulo` ⊆ conjunto cerrado; `aprobacion.modo="solicitud"` y `autoaprobacion=false` | Manifiesto inválido. |
| V16 | `modalidades.voz/imagen/pdf=true` exige que el manifiesto declare `modelos.asr/vision/pdf` completos | Manifiesto inválido. |

**No hay corrección silenciosa.** Un valor fuera de rango no se “clampea”: invalida
el manifiesto. La razón es que un `timeout_ms` o un `max_filas` recortado en
silencio puede ocultar una tool mal declarada.

### 2.5 Comportamiento ante manifiesto inválido (fail-closed, API viva)

1. Al arrancar, el registry intenta cargar y validar. Si falla:
   - se registra `ERROR agente.manifest_invalido` con la ruta del campo y el
     motivo (sin volcar el archivo completo);
   - `tools_cargadas = 0`;
   - toda invocación de tool devuelve `MODULO_INACTIVO` (ver §4.6);
   - **la API no se cae**: legacy y núcleo siguen operando. El módulo es aditivo.
2. `GET /nucleo/agente/estado` responde **200** con
   `{ "manifest": { "valido": false, "motivo": "…" }, "tools": { "cargadas": 0 } }`.
   No es 500: es un estado diagnosticable.
3. El buzón sigue disponible: una solicitud pendiente debe poder drenarse aunque
   el manifiesto esté roto (§6.8). Lo que se detiene es la ejecución de tools, no
   la decisión humana.

### 2.6 Orden de carga y dependencia de migraciones

1. Cargar manifiesto y descriptores (sin tocar la base).
2. Verificar que las tablas requeridas existan (`to_regclass`), sin ejecutar
   migraciones. Si falta `nucleo.modulos_empresa`, el gate queda cerrado y
   `GET /nucleo/agente/estado` reporta `faltantes: ["nucleo.modulos_empresa"]`.
3. Construir el registry inmutable.
4. El runtime no debe registrar tools si `manifest.valido=false` o si falta la
   tabla del gate. La regla es: **sin flag verificable no hay tool**.

### 2.7 Flag por empresa: `nucleo.modulos_empresa` (faltante 🔴)

**Hecho verificado:** no existe tabla de módulos por empresa. `nucleo.empresas`
no tiene columna de configuración (`supabase/migrations/0004_nucleo_operacional.sql:102-134`);
`nucleo.cutover_control` es otra cosa — controla el congelamiento legacy→núcleo
(`supabase/migrations/0014_cutover.sql:8-31`) — y reutilizarlo acoplaría dos flags
sin relación. Una búsqueda en `supabase/migrations/` por
`modulos_empresa|habilitado` no devuelve la tabla (solo coincidencias de
`nucleo.empresas` y comentarios de RLS).

**Propuesta mínima para `datos` (migración `0023`, no se crea en F2.1):**

```sql
create table nucleo.modulos_empresa (
  empresa_id     uuid not null references nucleo.empresas(id) on delete restrict,
  modulo_id      text not null,
  habilitado     boolean not null default false,
  habilitado_en  timestamptz,
  habilitado_por text,
  created_at     timestamptz not null default now(),
  created_by     text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at     timestamptz not null default now(),
  updated_by     text,
  version        integer not null default 1 check (version >= 1),
  primary key (empresa_id, modulo_id),
  constraint ck_modulo_id_formato check (modulo_id ~ '^[a-z][a-z0-9-]{2,63}$')
);

alter table nucleo.modulos_empresa enable row level security;
alter table nucleo.modulos_empresa force row level security;
create policy tenant_empresa on nucleo.modulos_empresa
  for all to public
  using (empresa_id = nucleo.ctx_empresa())
  with check (empresa_id = nucleo.ctx_empresa());

grant select, insert, update on nucleo.modulos_empresa to tei_app;
-- Sin DELETE: desactivar es habilitado=false, no borrar el rastro.
```

Reglas de la propuesta:

- `habilitado` default `false`; la fila ausente también es `false`.
- El gate lee `(empresa_id, 'agente-whatsapp')`; no hay caché (§4.8).
- `habilitado_por` es texto (`nucleo.auth_id`), no FK: el actor puede ser humano o
  plataforma.
- Precondiciones de migración: tabla inexistente, 0 filas, sin objetos con ese
  nombre. Rollback: `drop table` (es un objeto nuevo, sin datos de negocio).
- `datos` decide si `tei_app` conserva `UPDATE`; la propuesta lo deja para que la
  plataforma pueda activar/desactivar sin un rol adicional. El `DELETE` se
  revoca para no perder el rastro de activación.

**Mientras no exista `0023`:** el gate trata la ausencia de tabla como módulo
apagado (fail-closed), no como error 500. `GET /nucleo/agente/estado` lo declara.
Esto permite construir y probar el registry sin encender nada.

---

## 3. Descriptor de tool

### 3.1 Campos

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `nombre` | string | sí | `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`; único en el manifiesto. Convención: `<componente>.<intent>`. |
| `componente` | string | sí | Uno de `componentes` del manifiesto; es la primera llave de ACL. |
| `variable` | string | sí | `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`; segunda llave de ACL. Codifica el **alcance** (`viajes.cliente`, `viajes.propios`, `viajes.empresa`). |
| `permiso` | string | sí | Derivado: `componente + ":" + variable`. No es un permiso de `ROLES_PERMISOS`; es la clave estable de ACL/log. |
| `tipo` | enum | sí | `lectura` \| `escritura_solicitud`. |
| `alcance` | enum | sí | `propio` (entidad forzada del contacto) \| `empresa` (sin entidad forzada; referencias revalidadas). |
| `roles` | array[string] | sí | Subconjunto no vacío de `admin`, `cliente_final`, `conductor`. |
| `descripcion` | string | sí | ≤ 240 caracteres; se usa para selección de tool por el orquestador, no para autorizar. |
| `entrada` | object | sí | `{ "$ref": "schemas/<archivo>.json" }`; JSON Schema draft 2020-12, raíz object, `additionalProperties=false`. |
| `salida` | object | sí | Igual que `entrada`; proyección explícita, sin `select *`. |
| `ejecutor` | string | sí | Clave de la allow-list cerrada de `backend/app/nucleo/agente/ejecutores.py`. **No** es un import path. |
| `idempotencia` | object | sí | `{ "modo": "clave" \| "ninguna", "campo": "clave_idempotencia" }`. `clave` obligatorio en escritura. |
| `timeout_ms` | integer | sí | 100–5000. El runtime lo aplica; el ejecutor no puede extenderlo. |
| `max_filas` | integer \| null | sí | 1–200 en lectura; `null` en escritura. Es el tope duro; si la entrada trae `limite`, se clampa a este valor. |
| `version` | integer | sí | ≥ 1. Se incrementa al cambiar entrada/salida de forma incompatible. |

### 3.2 Ejemplo

```jsonc
{
  "nombre": "despacho.mis_fletes",
  "componente": "despacho",
  "variable": "viajes.cliente",
  "permiso": "despacho:viajes.cliente",
  "tipo": "lectura",
  "alcance": "propio",
  "roles": ["cliente_final"],
  "descripcion": "Lista los fletes del cliente del contacto, con ID comercial y estado.",
  "entrada": { "$ref": "schemas/despacho.mis_fletes.entrada.json" },
  "salida": { "$ref": "schemas/despacho.mis_fletes.salida.json" },
  "ejecutor": "despacho_mis_fletes",
  "idempotencia": { "modo": "ninguna", "campo": null },
  "timeout_ms": 1500,
  "max_filas": 50,
  "version": 1
}
```

### 3.3 Reglas del schema de entrada/salida

1. **Cerrado:** raíz `type=object`, `additionalProperties=false` en todos los
   objetos. Un campo no declarado invalida la entrada (422).
2. **Sin autoridad en el body:** prohibidos `empresa_id`, `contacto_id`, `rol`,
   `usuario_empresa_id` y `version` como entrada. La empresa y el rol salen del
   `ContextoAgente`, nunca del DI ni de la tool.
3. **Sin SQL ni nombres de tabla:** prohibidos `sql`, `query`, `tabla`, `where`,
   `orden`, `join`, `select`. El ejecutor es una función fija; el modelo no elige
   la consulta.
4. **Entidades:** en `alcance=propio`, prohibidos `cliente_id`/`chofer_id`; se
   fuerzan del contacto. En `alcance=empresa`, se aceptan referencias
   (`cliente_id`, `cliente_rut`, `patente`) y el ejecutor las revalida contra la
   empresa antes de usarlas (anti-IDOR).
5. **Montos:** `type=string` con patrón decimal (`^-?[0-9]+(\.[0-9]{1,4})?$`) y
   campo `moneda` ISO 4217. Nunca `number`/`float` para dinero. El frontend ya
   tipa montos como `string` (`frontend/src/types/nucleo.ts:46-47`).
6. **Fechas:** `format=date-time` RFC 3339 con `Z` para eventos; `format=date`
   para vencimientos/vigencias. No se aceptan fechas locales sin zona.
7. **IDs:** `format=uuid`; el ID comercial usa
   `^[A-Z0-9]{2,8}-[0-9]{5}$` (mismo patrón del CHECK `0021:551-553`).
8. **Salida:** solo campos declarados; prohibido devolver la fila completa. Para
   cliente, la proyección excluye costo, margen, patentes y datos de otros
   clientes (§5.8).

### 3.4 `ejecutor`: allow-list, no import dinámico

El manifiesto **no** puede apuntar a un módulo, clase o función arbitraria. El
registry mantiene un diccionario cerrado:

```python
EJECUTORES: dict[str, EjecutorTool] = {
    "despacho_mis_fletes": ejecutar_despacho_mis_fletes,
    "hoja_ruta_proponer": ejecutar_hoja_ruta_proponer,
    # …
}
```

Reglas:

- Si `ejecutor` no está en el diccionario, el manifiesto es inválido (V10).
- El diccionario se define en código, no se carga de JSON ni de la base.
- Un ejecutor recibe `(contexto: ContextoAgente, entrada: dict) -> ResultadoTool`
  y **no** recibe una `Session` creada por el modelo: la sesión la abre el
  registry con `get_session_nucleo` y el contexto de empresa ya fijado.
- El ejecutor no puede hacer `commit()` propio si la tool es de escritura; el
  registry controla la transacción (§4.10). Si el servicio dueño existente hace
  `commit()` interno, se envuelve con una variante que no commitea o no se
  registra la tool (ver §6.7 para la misma regla en el buzón).

### 3.5 Versionado de la tool

- `version` es un entero; se incrementa cuando cambia el schema de entrada o
  salida de forma incompatible, o cuando cambia la semántica del filtro.
- El runtime registra `version` en el envelope de resultado y en
  `datos_tocados._meta.tool_version` (§7.3), porque la tabla de auditoría no tiene
  columna de versión.
- Cambiar `version` no requiere migración; los DIs viejos siguen apuntando a la
  misma tool y el runtime valida el schema vigente. Si el cambio es incompatible,
  se declara una tool nueva (`nombre.v2` no: se usa `version=2` y se mantiene el
  nombre; el contrato de entrada es el que cambia). Para un cambio de nombre, se
  registra la nueva y se retira la vieja en el mismo manifiesto, nunca ambas.

### 3.6 Lo que una tool no puede hacer

- Leer o escribir `public`.
- Escribir `nucleo.viajes`, `nucleo.facturas`, `nucleo.pagos`, `nucleo.gastos`,
  `nucleo.hoja_ruta` en estado distinto de `propuesto`, ni ninguna tabla de
  negocio. La única escritura permitida es a las tablas del módulo:
  `conversacion_mensajes`, `hoja_ruta` (solo `propuesto → solicitud_creada`),
  `solicitudes` y `auditoria_consultas_agente`.
- Ejecutar SQL construido con texto del DI.
- Llamar a un proveedor externo (LLM, WhatsApp, storage) dentro de la
  transacción. Los efectos externos son del runtime, antes/después del commit
  (`destino-modular.md:308-324`).
- Aprobar su propia solicitud. La aprobación es humana y ocurre en el buzón.

---

## 4. Registry y gate

### 4.1 `ContextoAgente` (ADR-0006)

```python
@dataclass(frozen=True, slots=True)
class ContextoAgente:
    empresa_id: UUID
    contacto_id: UUID
    rol: RolContactoWhatsApp      # admin | cliente_final | conductor
    entidad_id: UUID | None       # cliente_id o chofer_id; None para admin
    conversacion_id: UUID | None
    mensaje_id: UUID | None
    request_id: str
```

Resolución, en orden:

1. El runtime entrega el teléfono E.164 del mensaje y `wa_message_id`.
2. Se busca `nucleo.contactos_whatsapp` por `telefono` con `activo=true`
   (`uq_contactos_telefono_activo`, `0021:222-223`). Si hay 0 filas → no hay
   contexto: respuesta genérica de enrolamiento, log del runtime, **sin fila de
   auditoría** (§7.6). Si hay >1 → integridad rota (el índice global lo impide);
   se deniega y se registra `ERROR`.
3. `empresa_id` sale de la fila del contacto, nunca del DI ni del body
   (ADR-0003 §3.4; ADR-0006 §Decisión 1).
4. `entidad_id`: `cliente_id` para `cliente_final`, `chofer_id` para `conductor`,
   `None` para `admin` (`ck_contacto_entidad`, `0021:210-214`).
5. `conversacion_id`/`mensaje_id`: los resuelve el runtime contra
   `nucleo.conversaciones`/`conversacion_mensajes`; si no existen, quedan `None`
   y la tool puede ejecutarse (la auditoría pierde el vínculo, no la fila).
6. Contexto de base: `fijar_empresa(empresa_id)`, `fijar_request_id(request_id)` y
   `nucleo.auth_id = "agente:<contacto_id>"`. Este último **no es un usuario**:
   es un marcador de actor para `created_by`/`fn_auditoria`
   (`AGENTS.md` §9; `nucleo/auth_id` es `text` en `nucleo.auditoria:821`). No se
   crea membresía ni se impersona un `RolEmpresa`.
7. `aplicar_contexto_sesion(session)` antes de la primera consulta, porque la
   transacción ya pudo haber empezado (`backend/app/core/contexto.py:149-155`).

**Prohibido:** construir `ContextoEmpresa`, llamar `get_contexto_empresa`, usar
`requiere_permiso` o resolver el chofer por `Chofer.auth_id`
(`servicio_conductor.py:90-115`). El camino del agente no tiene JWT.

### 4.2 Construcción del registry

1. Cargar el manifiesto y validar (§2.4). Si falla → registry vacío (§2.5).
2. Resolver cada `$ref` de tool; parsear y validar el descriptor.
3. Verificar `ejecutor` en `EJECUTORES`; verificar que el schema de entrada/salida
   exista y sea JSON Schema válido.
4. Construir un `MappingProxyType` inmutable `nombre → descriptor`.
5. Exponer:
   - `get(nombre) -> Descriptor | None`;
   - `tools_para_rol(rol) -> list[Descriptor]` (solo para armar el prompt; **no**
     autoriza);
   - `invocar(nombre, entrada, contexto) -> ResultadoTool` (revalida el gate en
     cada llamada).

El registry no consulta la base al construir; la base se consulta en el gate, por
invocación. Esto permite arrancar sin `0023` y reportar el faltante.

### 4.3 Algoritmo del gate

Cadena de cuatro llaves, en serie y con cortocircuito. La primera que falla
deniega y se audita.

```text
invocar(nombre, entrada, ctx):
  1. descriptor = registry.get(nombre)
     si no existe → DENY("TOOL_DESCONOCIDA", componente="agente", variable=None)
  2. si manifest.valido == false → DENY("MODULO_INACTIVO", descriptor)
  3. si contacto.activo == false u otp_estado != "verificado"
        → DENY("NO_AUTORIZADO", descriptor)          # INV-AW03 / D-12
  4. si modulo_habilitado(ctx.empresa_id) != true
        → DENY("MODULO_INACTIVO", descriptor)        # llave 1
  5. si ctx.rol no está en descriptor.roles
        → DENY("NO_AUTORIZADO", descriptor)          # llave 2
  6. acl_componente = leer_acl(ctx, descriptor.componente, variable=NULL)
     si no hay fila o permitido != true
        → DENY("NO_AUTORIZADO", componente, variable=None)  # llave 3
  7. acl_variable = leer_acl(ctx, descriptor.componente, descriptor.variable)
     si no hay fila o permitido != true
        → DENY("NO_AUTORIZADO", descriptor)          # llave 4
  8. validar entrada contra descriptor.entrada
     si inválida → AUDIT(acceso_otorgado=true, motivo="ENTRADA_INVALIDA")
                   → "DATOS_INVALIDOS"
  9. ejecutar con timeout_ms y max_filas
 10. auditar resultado (éxito o error) y devolver envelope
```

Notas:

- **Deny-by-default:** solo `permitido=true` autoriza. `false`, `NULL` y ausencia
  son lo mismo: denegación (INV-AW07, `docs/datos/invariantes.md:910`).
- **No hay atajo por rol:** un `admin` con ACL vacía no ve nada. El rol solo
  habilita la familia de tools; la ACL decide el dato.
- **No hay atajo por empresa:** el flag de empresa no reemplaza la ACL. Ambas
  deben estar activas.
- **El orden importa para la auditoría:** si falla el módulo, se registra con el
  descriptor (componente/variable/herramienta) y `acceso_otorgado=false`; no se
  revela si el problema es el módulo o la ACL.
- **`contacto.activo`/OTP:** se lee de la fila ya resuelta; no es una quinta llave
  de ACL, es una precondición de identidad. Si O2.3 aún no existe, los contactos
  de prueba se insertan con `otp_estado='verificado'`; en producción no se
  inventa un bypass.

### 4.4 SQL de las llaves

Todas las consultas se ejecutan con `app.empresa_id` fijado y con
`get_session_nucleo` (rol `tei_app`, sin `BYPASSRLS`; `docs/estado.md:103`).

```sql
-- Llave 1: módulo activo por empresa (tabla nueva 0023; ausencia = false)
select habilitado
  from nucleo.modulos_empresa
 where empresa_id = :empresa_id
   and modulo_id = 'agente-whatsapp';

-- Llave 3: toggle de componente (variable NULL)
select permitido
  from nucleo.permisos_contacto
 where empresa_id = :empresa_id
   and contacto_id = :contacto_id
   and componente = :componente
   and variable is null;

-- Llave 4: toggle de variable
select permitido
  from nucleo.permisos_contacto
 where empresa_id = :empresa_id
   and contacto_id = :contacto_id
   and componente = :componente
   and variable = :variable;
```

Reglas de implementación:

- Si `nucleo.modulos_empresa` no existe (`42P01`), el gate devuelve `false` y
  registra un `WARNING` una vez por proceso; no propaga 500.
- Si la consulta ACL devuelve más de una fila, es integridad rota: el índice
  `uq_permisos_contacto_valor` (`0021:262-263`) lo impide; se deniega y se
  registra `ERROR`.
- No se usa `count(*)`; se usa `first()` y se interpreta ausencia.
- No se cachea el resultado entre mensajes (§4.8).

### 4.5 Envelope de resultado

El runtime no recibe filas crudas ni excepciones de SQL. Recibe:

```jsonc
{
  "ok": true,
  "datos": { /* proyección declarada en salida */ },
  "meta": {
    "herramienta": "despacho.mis_fletes",
    "version": 1,
    "filas": 3,
    "truncado": false,
    "request_id": "…",
    "auditoria_id": 123
  }
}
```

Error:

```jsonc
{
  "ok": false,
  "error": {
    "codigo": "NO_AUTORIZADO",
    "reintentable": false
  },
  "meta": {
    "herramienta": "despacho.mis_fletes",
    "version": 1,
    "request_id": "…",
    "auditoria_id": 124
  }
}
```

- `datos` cumple el schema de salida; no se agregan campos “por si acaso”.
- `meta.filas` es el número devuelto; `truncado=true` si se alcanzó `max_filas`
  (se consulta `max_filas + 1` para saberlo, sin devolver la fila extra).
- `error.codigo` es un código estable; **no** incluye el mensaje de PostgreSQL ni
  el detalle de la ACL. El runtime lo usa para elegir la explicación natural
  (ADR-0003 §13.3), no para mostrar el código al contacto.

### 4.6 Códigos de error de tool

| Código | Cuándo | ¿Se audita? | ¿Reintentable? |
|---|---|---|---|
| `TOOL_DESCONOCIDA` | El nombre no está en el registry | Sí (`componente="agente"`) | No |
| `MODULO_INACTIVO` | Manifiesto inválido, tabla de gate ausente o empresa sin flag | Sí, si hay descriptor | No |
| `NO_AUTORIZADO` | Rol fuera de `roles`, ACL de componente/variable ausente o `false`, contacto inactivo/OTP no verificado | Sí | No |
| `DATOS_INVALIDOS` | Entrada no valida contra el schema | Sí (`acceso_otorgado=true`) | No (corregir entrada) |
| `CODIGO_AMBIGUO` | `id_comercial_flete` resuelve a >1 flete y falta cliente/viaje | Sí | Sí, con más contexto |
| `RECURSO_NO_ENCONTRADO` | 0 filas para una referencia válida | Sí | No |
| `TIMEOUT_TOOL` | Se superó `timeout_ms` | Sí | Sí, una vez |
| `AUDITORIA_FALLIDA` | No se pudo escribir la auditoría (solo lectura) | No aplica | Sí |
| `ERROR_INTERNO` | Falla no clasificada; el detalle va al log | Sí | Según el runtime |

Mapeo desde PostgreSQL (cuando la tool toca la base):

| SQLSTATE | Código de tool | Nota |
|---|---|---|
| `23505` | `CONFLICTO_IDEMPOTENCIA` (interno) | En escritura idempotente se absorbe y se devuelve la solicitud existente. |
| `23514` | `REGLA_NEGOCIO` | Transición/CHECK; no se muestra el `message_primary`. |
| `23503` | `REFERENCIA_INVALIDA` | FK compuesta; típicamente entidad de otra empresa. |
| `42501` | `NO_AUTORIZADO` | RLS/GRANT. **No es `IntegrityError`**: llega como `sqlalchemy.exc.ProgrammingError` (`InsufficientPrivilege`), así que no pasa por `traducir_integrity_error` (`errores.py:136-189`) ni por el handler `@app.exception_handler(IntegrityError)` (`main.py:229-273`); hoy queda **sin handler** → 500 por el manejador por defecto. El handler debe ser de `ProgrammingError`/`DBAPIError` y reutilizar `_sqlstate` (`errores.py:118-120`); se corrige antes de encender (§9.1). |
| `40001`/`40P01` | `CONFLICTO_CONCURRENCIA` | Reintento acotado por el runtime. |

**Por qué el mapeo no es uniforme:** `23505`, `23514` y `23503` **sí** llegan como
`sqlalchemy.exc.IntegrityError` y por eso tienen handler; `42501` no.

### 4.7 Denegación natural, no prefabricada

El gate devuelve un **motivo estructurado**, no una frase:

```jsonc
{
  "codigo": "NO_AUTORIZADO",
  "nivel": "variable",          // modulo | rol | componente | variable
  "componente": "facturacion",
  "variable": "facturacion.empresa"
}
```

El runtime genera la explicación en lenguaje natural (ADR-0003 §13.3) y **no
revela** el dato denegado, la configuración de otros números ni la existencia de
la fila ACL. La única respuesta pre-fijada es la de teléfono no registrado
(anti-enumeración, ADR-0003 §5). Este documento no escribe guiones.

### 4.8 Sin caché en v1; revocación inmediata

- El gate lee la ACL en **cada invocación**. No hay caché en proceso, ni TTL, ni
  memoización por conversación.
- Razón: una revocación desde la plataforma (O4.1) debe surtir efecto en el
  siguiente mensaje, no en el siguiente deploy. La lectura es una fila por índice
  único (`uq_permisos_contacto_valor`), coste despreciable.
- Si más adelante se agrega caché, debe invalidarse en la escritura de
  `permisos_contacto` y no sobrevivir al request; mientras no exista ese
  mecanismo, la regla es “sin caché”.

### 4.9 `tools_disponibles` no autoriza

El orquestador necesita saber qué tools ofrecer al modelo. `tools_para_rol(rol)`
devuelve la lista **declarativa** por rol; no consulta ACL ni empresa. Es una
ayuda de prompt, no una autorización. La autorización ocurre solo en `invocar`.
Si el modelo intenta una tool que no está en la lista, el gate la deniega igual
(no hay confianza en el prompt).

### 4.10 Transacción, timeout y límites

- **Lectura:** una transacción, sin `commit()` intermedio; se aplica
  `aplicar_contexto_sesion` antes de la primera consulta. `max_filas` se traduce a
  `LIMIT max_filas + 1`.
- **Escritura de solicitud:** una transacción que inserta la solicitud (y, si
  aplica, la hoja de ruta en `propuesto`) y confirma. No hay llamadas externas
  dentro. Si el ejecutor necesita un servicio que hace `commit()` propio, no se
  registra la tool hasta adaptarlo (§6.7).
- **Timeout:** el registry envuelve la ejecución con `timeout_ms`; al vencer,
  cancela la consulta y devuelve `TIMEOUT_TOOL`. No se deja la transacción abierta.
- **Auditoría:** se escribe después, en su propia transacción (§7.2). No forma
  parte de la transacción de la tool.

---

## 5. Catálogo inicial de tools

### 5.1 Convenciones

- **`variable` codifica el alcance**, no solo el dato:
  - `*.cliente` / `*.propia` / `*.propios`: entidad forzada del contacto.
  - `*.empresa`: alcance de empresa; el ejecutor revalida toda referencia.
- **`permiso = componente:variable`**. Es la clave que el frontend usa para el
  toggle y la que aparece en logs; la ACL se guarda en dos columnas.
- **Un componente puede tener varias variables** (p. ej. `facturacion.cliente` y
  `facturacion.empresa`). El dueño puede activar una y no la otra.
- **El rol no se deriva de la variable:** un `cliente_final` con una fila ACL de
  `viajes.empresa` sigue denegado por rol (llave 2 antes que ACL).
- **Registrable en O2.1** significa: existe el ejecutor y los datos en `nucleo`.
  Una tool no registrable queda en el catálogo objetivo, pero **no** entra al
  manifiesto hasta cumplir la condición.

### 5.2 Cliente (`cliente_final`, entidad `cliente_id` forzada)

| # | Tool | Permiso (ACL) | Tipo | Entrada (resumen) | Salida (resumen) | Dato hoy / paridad | ¿Registrable? |
|---|---|---|---|---|---|---|---|
| C1 | `despacho.mis_fletes` | `despacho:viajes.cliente` | lectura | `{estado?, desde?, hasta?, limite?}` | `{items:[{id_comercial_flete, fecha, origen, destino, estado, tipo_carga}], total, truncado}` | 🟢 `api_expediente.py:52-71` filtra por `cliente_id`; `ServicioExpediente.listar_viajes` | Sí |
| C2 | `despacho.mi_flete` | `despacho:viajes.cliente` | lectura | `{id_comercial_flete}` o `{viaje_id}` | detalle del flete, paradas y estado; sin costo/margen | 🟢 `api_expediente.py:74-79`; resolución por `(empresa, cliente, código)` | Sí (D4 resuelto por cliente forzado) |
| C3 | `facturacion.mi_deuda` | `facturacion:facturacion.cliente` | lectura | `{}` | `{total, vencido, por_vencer, facturas_abiertas, proximo_vencimiento, moneda}` | 🟢 saldos `servicio_facturacion.py:133-147,161-196`; aging `:719-754` | Sí |
| C4 | `facturacion.mis_fletes_pendientes` | `facturacion:facturacion.cliente` | lectura | `{limite?}` | `{items:[{id_comercial_flete, fecha_cierre, monto, moneda}], total}` | 🟡 agregación de viajes cerrados con POD y sin facturar; no hay servicio declarado | Sí (consulta nueva) |
| C5 | `facturacion.mis_documentos` | `facturacion:documentos.cliente` | lectura | `{tipo?, estado?, limite?}` | `{items:[{tipo, numero, fecha, estado, saldo, moneda}], total}` | 🟢 facturas `listar_facturas:198-227`; OC `listar_ocs:589`; NC | Sí (URL firmada se resuelve aparte) |
| C6 | `despacho.disponibilidad_para_carga` | `despacho:disponibilidad.cliente` | lectura | `{cantidad?, tipo_rampla?, carga_peligrosa?, refrigerada?, desde?, hasta?}` | `{hay_disponibilidad: bool, requisitos:[...], mensaje}`; **sin cantidad exacta, sin patentes** | 🟢 parcial `servicio_disponibilidad.listar_recursos:595`; regla D-11 | Sí, tras codificar D-11 |
| C7 | `solicitudes.agendar_flete` | `solicitudes:solicitudes.agendamiento` | escritura_solicitud | `{carga, origen, destino, tipo_camion, cantidad?, fecha_deseada?, observaciones?, clave_idempotencia}` | `{solicitud_id, estado, resumen}` | 🔴 tabla `solicitudes` existe (`0021:388-433`); servicio O2.4 | Sí (solo crea solicitud) |
| C8 | `solicitudes.enviar_documentos` | `solicitudes:solicitudes.documentos` | escritura_solicitud | `{storage_key, tipo_documento, id_comercial_flete[], observaciones?, clave_idempotencia}` | `{solicitud_id, estado, resumen}` | 🔴 tabla + storage; servicio O2.4 | Sí (solo crea solicitud) |

**Proyección cliente (deny-list):** las tools C1–C6 no devuelven `costo`,
`margen`, `freight_score`, `tracto_patente`, `rampla_patente`, `chofer_nombre`,
`chofer_rut`, datos de otros clientes ni la cantidad exacta de flota. La
notificación de asignación posterior a la aprobación (CL-05: “qué camión, qué
rampla y qué conductor”) es un mensaje del runtime, no una tool de lectura; si el
cliente debe poder consultarla después, se requiere decisión de negocio porque
choca con D-09 (“NO acceso a … números de camiones”)
(`docs/negocio/agente-whatsapp-roles.md:101-103` vs `:31-34`). Queda 🔴 como
pregunta (§9.8).

### 5.3 Conductor (`conductor`, entidad `chofer_id` forzada)

| # | Tool | Permiso (ACL) | Tipo | Entrada (resumen) | Salida (resumen) | Dato hoy / paridad | ¿Registrable? |
|---|---|---|---|---|---|---|---|
| K1 | `despacho.mis_viajes_asignados` | `despacho:viajes.propios` | lectura | `{estado?, desde?, hasta?, limite?}` | `{items:[{viaje_id, id_comercial_flete, cliente_nombre, origen, destino, fecha, estado}], total}` | 🟢 `api_conductor.py:29-34` (paridad; el agente filtra por `chofer_id`, no por `auth_id`) | Sí |
| K2 | `despacho.mi_viaje_asignado` | `despacho:viajes.propios` | lectura | `{viaje_id}` o `{id_comercial_flete}` | detalle del viaje asignado y estado | 🟢 mismo servicio; revalidar asignación | Sí (D4: entre los viajes del chofer; >1 → `CODIGO_AMBIGUO`) |
| K3 | `hoja_ruta.proponer` | `hoja_ruta:hoja_ruta.propia` | escritura_solicitud | `{wa_message_id, viaje_id, id_comercial_flete, payload, evidencia[], faltantes[], clave_idempotencia}` | `{hoja_ruta_id, solicitud_id, estado, faltantes}` | 🔴 tabla `hoja_ruta` (`0021:495-523`); servicio O2.5 | Sí (solo `propuesto` + solicitud) |
| K4 | `hoja_ruta.mi_hoja` | `hoja_ruta:hoja_ruta.propia` | lectura | `{solicitud_id}` o `{id_comercial_flete}` | `{estado, valores, faltantes, motivo_rechazo?}` | 🟡 tabla existe; servicio O2.5 | Sí |

**Regla de K3:** `payload` se valida contra un JSON Schema estricto versionado
(`hoja-ruta/v1`), con `additionalProperties=false`. La tool inserta
`hoja_ruta(estado='propuesto')` y `solicitudes(tipo='hoja_de_ruta')` en la misma
transacción, luego transiciona a `solicitud_creada` con `solicitud_id`
(`0022:349-392`). No escribe gastos, nómina ni viajes. La idempotencia es
`clave_idempotencia = "hoja_ruta:" + wa_message_id`; un reintento devuelve la
solicitud existente (`uq_solicitud_idempotencia`, `0021:437-438`).

**Regla de K2/K4:** un código puede repetirse entre clientes (D4), pero el
conjunto se acota a los viajes asignados al chofer. Si el código resuelve a más de
un viaje del mismo chofer, la tool devuelve `CODIGO_AMBIGUO` con las opciones
(viaje, cliente, origen/destino) para el mini-cuestionario CO-02; no elige sola.

### 5.4 Administración (`admin`, sin entidad forzada)

| # | Tool | Permiso (ACL) | Tipo | Entrada (resumen) | Salida (resumen) | Dato hoy / paridad | ¿Registrable? |
|---|---|---|---|---|---|---|---|
| A1 | `despacho.viajes_del_dia` | `despacho:viajes.empresa` | lectura | `{fecha?, estado?, limite?}` | `{items:[{viaje_id, id_comercial_flete, cliente_nombre, origen, destino, estado, recursos?}], total}` | 🟢 `api.py:109-125`; `listar_viajes:1022` | Sí |
| A2 | `facturacion.resumen_mes` | `facturacion:facturacion.empresa` | lectura | `{anio?, mes?}` | `{emitido, cobrado, pendiente, vencido, moneda}` | 🟢 facturas/pagos/NC (`servicio_facturacion.py`) | Sí (agregado nuevo) |
| A3 | `cobranza.clientes_pendientes` | `cobranza:cobranza.empresa` | lectura | `{min_dias_vencido?, limite?}` | `{items:[{cliente_id, cliente_nombre, saldo, vencido, dias_max}], total}` | 🟢 `aging:719-754` + `listar_facturas:198-227` | Sí |
| A4 | `flota.estado_vehiculo` | `flota:flota.empresa` | lectura | `{patente}` | `{tipo, patente, estado, ubicacion?, ultimo_viaje?, documentos_por_vencer[]}` | 🟢 `Tracto`, `Rampla`, `Documento`, `ReservaRecurso` (`models.py:470,515,601,1282`) | Sí (consulta nueva) |
| A5 | `mantenimiento.estado_vehiculo` | `mantenimiento:mantenimiento.empresa` | lectura | `{patente}` | `{pauta?, ultimo_service?, proximo_km?, historial[]}` | 🔴 no hay tabla de pautas/historial en `nucleo`; mantenimiento vive en legacy `public` y en `ReservaRecurso.tipo_reserva='mantenimiento'` (`servicio_alertas.py:172`) | **No** hasta crear el objeto en `nucleo` |
| A6 | `gastos.resumen_por_categoria` | `gastos:gastos.empresa` | lectura | `{desde, hasta, categoria?}` | `{items:[{categoria, monto, moneda, cantidad}], total}` | 🟡 `ViajeGasto` existe; `listar_gastos` es por viaje (`servicio_gastos.py:230-253`) | Sí (agregado nuevo) |
| A7 | `solicitudes.bandeja` | `solicitudes:solicitudes.bandeja` | lectura | `{estado?, tipo?, limite?}` | `{items:[...], total}` | 🟢 tabla `solicitudes` | Sí |
| A8 | `facturacion.documentos_cliente` | `facturacion:documentos.empresa` | lectura | `{cliente_id?/cliente_rut?, tipo?, estado?, limite?}` | `{items:[{tipo, numero, fecha, estado, saldo, moneda}], total}` | 🟢 facturas/OC/NC | Sí (D4: exigir cliente o `CODIGO_AMBIGUO`) |

**Regla de A1–A8:** son de empresa, no de contacto. El `admin` ve todo dentro de
su empresa, pero la ACL del número puede apagar cualquier variable. No hay tools
de plataforma (cross-empresa); esas son de C14 y no se exponen al agente.

### 5.5 Diferida: `gerente.consultar` (AD-02)

| Tool | Permiso | Estado | Por qué no se registra |
|---|---|---|---|
| `gerente.consultar` | `gerente:gerente.consulta` | 🔴 diferida | DEC-10 prohíbe SQL libre (`docs/PLAN_DESARROLLO.md:48`); el mecanismo (capa semántica/tools compuestas vs SQL read-only con guardarraíles) sigue abierto en D-09 (`docs/negocio/preguntas.md:34`). Sin decisión no hay ejecutor ni schema que declarar. |

Si alguien la agrega al manifiesto antes de esa decisión, V10 la rechaza (no hay
`ejecutor` en la allow-list). Es intencional: no se puede “colar” el gerente
digital por configuración.

### 5.6 Matriz ACL resumen (lo que el dueño enciende por número)

| Rol | Componente | Variables que debe activar | Tools |
|---|---|---|---|
| `cliente_final` | `despacho` | `viajes.cliente`, `disponibilidad.cliente` | C1, C2, C6 |
| `cliente_final` | `facturacion` | `facturacion.cliente`, `documentos.cliente` | C3, C4, C5 |
| `cliente_final` | `solicitudes` | `solicitudes.agendamiento`, `solicitudes.documentos` | C7, C8 |
| `conductor` | `despacho` | `viajes.propios` | K1, K2 |
| `conductor` | `hoja_ruta` | `hoja_ruta.propia` | K3, K4 |
| `admin` | `despacho` | `viajes.empresa` | A1 |
| `admin` | `facturacion` | `facturacion.empresa`, `documentos.empresa` | A2, A8 |
| `admin` | `cobranza` | `cobranza.empresa` | A3 |
| `admin` | `flota` | `flota.empresa` | A4 |
| `admin` | `mantenimiento` | `mantenimiento.empresa` | A5 (cuando exista) |
| `admin` | `gastos` | `gastos.empresa` | A6 |
| `admin` | `solicitudes` | `solicitudes.bandeja` | A7 |

**Dos filas por componente:** el gate exige el toggle de componente
(`variable=NULL`) **y** el de variable. El frontend O4.1, al activar un módulo
para un número, debe escribir ambos; si solo escribe el de variable, el gate
deniega por la llave 3. Esto es deliberado: el toggle de componente es el
“interruptor maestro” que el dueño apaga de un clic.

### 5.7 Estado de implementabilidad

| Estado | Tools | Significado |
|---|---|---|
| 🟢 datos y paridad existen | C1, C2, C3, C5, K1, K2, A1, A2, A3, A4, A7, A8 | Se puede implementar el ejecutor con servicios/consultas actuales; falta el adaptador de filtro forzado (ADR-0006). |
| 🟡 requiere consulta/agregado nuevo | C4, C6, K4, A6 | El dato existe, pero no hay método declarado con esa proyección. |
| 🔴 requiere servicio del módulo | C7, C8, K3 | La tabla existe; el servicio de solicitudes/hoja de ruta es O2.4/O2.5. |
| 🔴 bloqueada por pieza de dominio | A5 | Mantenimiento no está en `nucleo`; no se lee `public`. |
| 🔴 diferida por decisión | `gerente.consultar` | D-09 abierta. |

**Conteo honesto:** el catálogo declara 20 tools, pero el registry carga **19**:
`A5` se mantiene como diseño y **no** se declara en el manifiesto (sin `ejecutor`
en la allow-list, V10 la rechaza). Cuando exista el objeto de mantenimiento en
`nucleo` y su ejecutor, pasa a 20 sin cambiar el contrato.

### 5.8 Proyección y minimización

- **Cliente:** nunca costo, margen, score, patentes, chofer, otros clientes,
  cantidad exacta de flota. La salida se declara campo por campo; no se reutiliza
  un `Out` que traiga de más.
- **Conductor:** solo sus viajes/hojas; no ve tarifas de otros clientes ni gastos
  de la empresa.
- **Admin:** ve la empresa, no otras empresas. La consulta lleva `empresa_id`
  explícito además de RLS; no se confía solo en el GUC.
- **Todos:** `datos_tocados` en auditoría guarda IDs, no el contenido (§7).

### 5.9 D4 / D-18 en las tools (regla de trabajo, no ratificada)

La `UNIQUE` real es `(empresa_id, cliente_id, id_comercial_flete)`
(`0021:555-557`), no `(empresa, código)`; el índice de resolución por
`(empresa, código)` puede devolver N filas (`0021:559-564`;
`docs/datos/agente-esquema.md:637`; D-18 en `docs/negocio/preguntas.md:43`).

Regla de F2.1, alineada con la recomendación (b) de D-18:

| Rol | Resolución |
|---|---|
| `cliente_final` | `cliente_id` forzado; `(empresa, cliente, código)` es único → 0 o 1 fila. Si hay >1, integridad rota → `ERROR_INTERNO`. |
| `conductor` | `chofer_id` forzado; se resuelve entre los viajes asignados. Si >1 → `CODIGO_AMBIGUO` con opciones (CO-02). |
| `admin` | Si viene `cliente_id`/`cliente_rut`, se usa; si solo viene el código, se resuelve por `(empresa, código)`. Si >1 → `CODIGO_AMBIGUO` 409 con candidatos (cliente, viaje). Si 0 → `RECURSO_NO_ENCONTRADO`. |

Esto **no cierra D4**: la decisión de negocio (prefijo único vs exigir cliente)
sigue siendo del dueño (D-18). Cierra el caso de uso sin migración y sin inventar
una unicidad que la base no tiene.

---

## 6. Contrato HTTP del buzón y solicitudes

### 6.1 Convenciones

- **Autenticación:** Supabase JWT validado por el backend; `X-Empresa-ID`
  obligatorio. La empresa se resuelve por membresía (`get_contexto_empresa`,
  `backend/app/nucleo/deps.py:50-102`), nunca por el body.
- **Permisos:** `agente:buzon` para leer/estado; `agente:aprobar` para decidir;
  `agente:contactos` para O2.3. Se agregan a `TODOS_LOS_PERMISOS`
  (`backend/app/nucleo/permisos.py:15-44`) y a los roles que el negocio ratifique
  (AB-02, §9.5). **Ojo:** `admin` y `gerente` usan `set(TODOS_LOS_PERMISOS)`
  (`permisos.py:59-60`), así que agregar un permiso al conjunto se lo concede a
  ambos; si no se quiere ese efecto, se excluye explícitamente.
- **Formato:** JSON `snake_case` (Pydantic). Errores con el sobre existente
  `{codigo, mensaje, contexto?, errores?}` (`backend/app/nucleo/errores.py:34-43`),
  que el cliente `nucleo.ts` ya sabe leer (`frontend/src/lib/nucleo.ts:60-79`).
- **Rutas:** relativas al prefijo de la API (`settings.API_V1_PREFIX`, hoy
  `/api/v1`); el cliente concatena `NEXT_PUBLIC_API_URL`
  (`frontend/src/lib/nucleo.ts:4`). El router nuevo se registra en
  `backend/app/api/router.py:44-56`.
- **Aislamiento:** toda consulta lleva `empresa_id` explícito y RLS; un recurso de
  otra empresa devuelve **404**, no 403, para no filtrar existencia.

### 6.2 `GET /nucleo/agente/solicitudes`

Lista el buzón de la empresa.

**Permiso:** `agente:buzon`.

**Query:**

| Parámetro | Tipo | Default | Regla |
|---|---|---|---|
| `estado` | enum | `pendiente` | `pendiente\|aprobada\|rechazada\|cancelada\|todas` |
| `tipo` | enum | — | `agendamiento\|documentos\|hoja_de_ruta\|otra` |
| `viaje_id` | uuid | — | Filtro por flete |
| `limit` | int | 50 | 1–100 |
| `offset` | int | 0 | ≥ 0 |

**200:**

```jsonc
{
  "items": [
    {
      "id": "…",
      "tipo": "hoja_de_ruta",
      "estado": "pendiente",
      "solicitante": { "tipo": "contacto", "id": "…", "nombre": "…" },
      "viaje_id": null,
      "id_comercial_flete": "SQM-00001",
      "resumen": "Hoja de ruta con 7 campos; faltan 2",
      "creada_en": "2026-10-30T12:00:00Z",
      "decidida_en": null,
      "tiene_modificaciones": false,
      "version": 1
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

- `solicitante` se resuelve a contacto o usuario; nunca expone el teléfono
  completo (se enmascara) ni datos de otra empresa.
- `resumen` es una síntesis del payload, no el payload completo; el detalle va en
  el endpoint siguiente.
- `total` es `count(*)` con los mismos filtros; si el volumen crece, se puede
  sustituir por un contador aproximado, pero el contrato no cambia.
- Sin permiso → 403 `ACCESO_DENEGADO`. Empresa sin solicitudes → 200 con
  `items=[]`, no 404.

### 6.3 `GET /nucleo/agente/solicitudes/{id}`

**Permiso:** `agente:buzon`.

**200:**

```jsonc
{
  "id": "…",
  "tipo": "hoja_de_ruta",
  "estado": "pendiente",
  "solicitante": { "tipo": "contacto", "id": "…", "nombre": "…" },
  "viaje_id": "…",
  "id_comercial_flete": "SQM-00001",
  "payload": { /* JSON propuesto, inmutable */ },
  "valores_modificados": null,
  "diff": [],
  "evidencia": [
    { "tipo": "mensaje", "ref": "…" },
    { "tipo": "documento", "ref": "storage/key" }
  ],
  "hoja_ruta": { "id": "…", "estado": "solicitud_creada", "faltantes": ["km_final", "litros"] },
  "creada_en": "2026-10-30T12:00:00Z",
  "decidida_en": null,
  "aprobado_por": null,
  "version": 1
}
```

- `payload` es el original; `valores_modificados` es la corrección; `diff` se
  calcula campo a campo (`campo`, `propuesto`, `modificado`) y no se persiste
  (se deriva al leer).
- `evidencia` solo contiene referencias; el aprobador que necesite el archivo usa
  el endpoint de storage con su propio permiso, no el buzón.
- Un `id` de otra empresa → 404 `RECURSO_NO_ENCONTRADO`.

### 6.4 `POST /nucleo/agente/solicitudes/{id}/decidir`

**Permiso:** `agente:aprobar`.

**Body:**

```jsonc
{
  "accion": "confirmar",              // confirmar | rechazar | modificar
  "version": 1,                       // obligatorio: bloqueo optimista
  "motivo_rechazo": null,             // obligatorio si accion=rechazar
  "valores_modificados": null         // obligatorio si accion=modificar
}
```

**Reglas por acción:**

| Acción | Efecto | Valida | Estado resultante |
|---|---|---|---|
| `confirmar` | Ejecuta el ejecutor registrado para el `tipo` (si existe), en la misma transacción; usa `valores_modificados` si están presentes | Estado `pendiente`, `version` coincide, datos completos | `aprobada` |
| `rechazar` | Registra `motivo_rechazo`, `aprobado_por` y `decidido_en`; **no llama a ningún ejecutor** | Estado `pendiente`, `version` coincide, motivo no vacío | `rechazada` |
| `modificar` | Guarda `valores_modificados`, `modificado_por` y `modificado_en`; **no ejecuta** | Estado `pendiente`, `version` coincide, valores válidos contra el schema del tipo | `pendiente` |

**200 (confirmar/rechazar):**

```jsonc
{
  "solicitud": { /* mismo shape que 6.3, con estado y decisión */ },
  "resultado": {
    "tipo": "hoja_ruta",
    "ref": "…",
    "estado": "cargado"
  }
}
```

**200 (modificar):**

```jsonc
{
  "solicitud": { /* estado pendiente, con valores_modificados y diff */ },
  "resultado": null
}
```

**Errores:**

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 403 | `ACCESO_DENEGADO` | Sin `agente:aprobar`, empresa inactiva o usuario sin membresía. |
| 403 | `AUTOAPROBACION` | El aprobador es el solicitante (§6.4). |
| 404 | `RECURSO_NO_ENCONTRADO` | Solicitud inexistente o de otra empresa. |
| 409 | `SOLICITUD_YA_DECIDIDA` | Estado terminal; dos aprobadores; reintento tras éxito. |
| 409 | `CONFLICTO_CONCURRENCIA` | `version` no coincide. |
| 422 | `DATOS_INVALIDOS` | Falta motivo, valores inválidos, acción desconocida. |
| 501 | `TIPO_SIN_EJECUTOR` | `confirmar` sobre un tipo sin ejecutor registrado. |

**Concurrencia (dos aprobadores):**

1. `select ... from nucleo.solicitudes where id=:id and empresa_id=:empresa for update`.
2. Verificar `estado='pendiente'` y `version=:version`.
3. Ejecutar (o no, según acción).
4. `update ... set estado=..., aprobado_por=..., decidido_en=..., version=version+1 where id=:id and estado='pendiente'`.
5. `commit`.

El segundo aprobador espera el lock; al reanudar, ve `estado` terminal y recibe
409 `SOLICITUD_YA_DECIDIDA` (o `version` distinta → 409
`CONFLICTO_CONCURRENCIA`). La garantía de que una solicitud terminal no se reabre
está en el trigger `fn_solicitud_transicion` (`0021:458-483`), que lanza `23514`;
el filtro por estado es la primera defensa, no la única.

**Idempotencia de la decisión:** no hay `Idempotency-Key` en decisiones. Un
reintento de red después de un 200 devuelve 409, no un segundo efecto. El
frontend debe tratar 409 `SOLICITUD_YA_DECIDIDA` como “ya decidida” y refrescar,
no como error fatal.

**Autoaprobación:** se prohíbe si el aprobador es la misma persona que el
solicitante. Para solicitudes de contacto, se compara el `usuario_empresa_id`
vinculado al contacto (`0021:189`) con la membresía del aprobador; si el contacto
no tiene vínculo, no hay autoaprobación posible por esa vía. Para solicitudes de
usuario, se compara `solicitante_usuario_empresa_id` con la membresía. Si
coinciden → 403 `AUTOAPROBACION`. El contacto nunca aprueba: no tiene JWT ni
permiso `agente:aprobar`.

### 6.5 `GET /nucleo/agente/estado`

**Permiso:** `agente:buzon`.

**200:**

```jsonc
{
  "modulo_id": "agente-whatsapp",
  "manifest": {
    "valido": true,
    "version": "0.1.0",
    "schema_di": "di/v1",
    "motivo": null
  },
  "empresa": {
    "habilitado": false,
    "fuente": "defecto"          // defecto | fila
  },
  "tools": {
    "cargadas": 19,
    "por_componente": { "despacho": 3, "facturacion": 3 }
  },
  "migraciones_requeridas": [
    "0021_agente_whatsapp.sql",
    "0022_agente_whatsapp_endurecimiento.sql",
    "0023_modulos_empresa.sql"
  ],
  "faltantes": ["nucleo.modulos_empresa"]
}
```

- Es un endpoint de diagnóstico, no de operación. No expone secretos ni la lista
  de contactos.
- `tools.cargadas` cuenta las tools **efectivamente cargadas** desde el
  manifiesto, no el tamaño del catálogo: hoy 19, porque `A5 mantenimiento` no se
  declara mientras no exista su ejecutor (§5.7).
- Si el manifiesto es inválido, `valido=false`, `tools.cargadas=0`, `motivo` con
  el campo; la respuesta sigue siendo 200.
- `faltantes` se calcula con `to_regclass`; no ejecuta migraciones.

### 6.6 Ejecutores por tipo (dispatch) y el 501

El endpoint de decisión no conoce reglas de negocio. Despacha a un ejecutor
registrado por `tipo`:

| `tipo` | Ejecutor | Estado F2.1 |
|---|---|---|
| `hoja_de_ruta` | Transición `solicitud_creada → cargado` + `valores_cargados` en `nucleo.hoja_ruta` | 🟡 O2.5 lo implementa; es el único ejecutor que F2.1 puede declarar completo porque vive en tablas del módulo. |
| `agendamiento` | Crear viaje en C03 con tarifa/OC (servicio dueño) | 🔴 sin ejecutor; 501 `TIPO_SIN_EJECUTOR`. |
| `documentos` | Asociar documento a viaje/OC en C04/C07 | 🔴 sin ejecutor; 501. |
| `otra` | — | 🔴 501. |

**Regla de transacción para futuros ejecutores:** el ejecutor recibe la `Session`
del endpoint y **no hace `commit()` propio**. La razón es verificada: los
servicios actuales hacen `commit()` por método (`destino-modular.md:308-316`), y
componer “servicio + estado de solicitud” en dos commits abre una ventana de
estado parcial (solicitud aprobada sin efecto, o efecto sin solicitud aprobada).
Mientras un servicio no acepte participar en la transacción del endpoint, no se
registra su ejecutor; se devuelve 501. Esto es más honesto que un “confirmar”
que a veces deja el sistema a medias.

**Rechazar no necesita ejecutor:** solo toca `solicitudes` y, para
`hoja_de_ruta`, `hoja_ruta.estado='rechazado'` + motivo. Es la garantía D6 que se
prueba en §9.3.

### 6.7 Módulo apagado vs buzón disponible

- El **flag de empresa** y el **manifiesto** gobiernan las **tools**.
- Los endpoints del buzón (`GET`, `GET/{id}`, `POST decidir`, `GET estado`) **no**
  consultan el flag del módulo. Una solicitud pendiente debe poder confirmarse o
  rechazarse aunque el agente esté apagado; de lo contrario, apagar el módulo
  dejaría basura irresoluble.
- `POST decidir` con `confirmar` sobre `hoja_de_ruta` funciona con el módulo
  apagado porque escribe tablas del módulo, no ejecuta una tool. Si el negocio
  quiere que el apagado también congele el buzón, es una decisión distinta y
  requiere un flag propio; no se confunde con el gate de tools.

### 6.8 Reservado O2.3 y O4.5 (no se implementa en F2.1)

| Ruta | Permiso | Ola | Nota |
|---|---|---|---|
| `GET /nucleo/agente/contactos` | `agente:contactos` | O2.3 | Lista enrolados, estado OTP, entidad, activo. |
| `POST /nucleo/agente/contactos` | `agente:contactos` | O2.3 | Alta de número; `rol` y entidad; nunca acepta `empresa_id` del body. |
| `POST /nucleo/agente/contactos/{id}/revocar` | `agente:contactos` | O2.3 | `activo=false`; no borra. |
| `GET /nucleo/agente/auditoria` | `auditoria:leer` | O4.5 | Filtros `contacto_id`, `desde`, `hasta`, `herramienta`, `acceso_otorgado`; solo lectura. |

Estas rutas se documentan para que `frontend` y `backend` no inventen formas
distintas; su contrato detallado es de O2.3/O4.5, no de F2.1.

### 6.9 Contrato de frontend (O4.3)

- Usar `nucleo` de `frontend/src/lib/nucleo.ts:89-106`; no crear un tercer cliente
  HTTP.
- Tipos nuevos en `frontend/src/types/nucleo.ts`:
  `SolicitudResumenNucleo`, `SolicitudDetalleNucleo`, `DecisionSolicitudNucleo`.
- Llamadas:
  - `nucleo.get<SolicitudLista>("/nucleo/agente/solicitudes?estado=pendiente", empresaId)`
  - `nucleo.get<SolicitudDetalle>(`/nucleo/agente/solicitudes/${id}`, empresaId)`
  - `nucleo.post<DecisionResponse>(`/nucleo/agente/solicitudes/${id}/decidir`, empresaId, body)`
- Badge: `GET ...?estado=pendiente&limit=1` y usar `total`. No hacer polling
  agresivo; el contrato no fija intervalo (decisión de UI/operación).
- En 409 `SOLICITUD_YA_DECIDIDA`, refrescar el detalle y mostrar “ya fue decidida
  por otro usuario”; no reintentar el POST.
- En 501 `TIPO_SIN_EJECUTOR`, deshabilitar “Confirmar” para ese tipo y mostrar el
  motivo; “Rechazar” sigue disponible.
- La edición de “Modificar” usa `payload` como base y envía `valores_modificados`;
  el `diff` se muestra con los valores propuestos y modificados. Al confirmar
  después de modificar, el backend usa `valores_modificados`.

---

## 7. Auditoría

### 7.1 Tabla y columnas (existentes)

`nucleo.auditoria_consultas_agente` (`0021:678-735`):

| Columna | Tipo | Uso |
|---|---|---|
| `id` | bigint identity | PK. |
| `empresa_id` | uuid not null | Empresa del contacto; RLS. |
| `contacto_id` | uuid not null | Quién; FK compuesta a contactos. |
| `conversacion_id` | uuid | Contexto de conversación. |
| `mensaje_id` | uuid | Expediente del mensaje. |
| `componente` | text | Componente consultado. |
| `variable` | text | Variable ACL; `NULL` en denegación de componente. |
| `herramienta` | text | Nombre de la tool. |
| `pregunta_resumida` | text | Intención + extracto redactado. |
| `datos_tocados` | jsonb | IDs devueltos, no contenido. |
| `respuesta_resumida` | text | Síntesis o código de error. |
| `acceso_otorgado` | boolean not null | Veredicto del gate. |
| `request_id` | text | Correlación con el runtime. |
| `ocurrido_en` | timestamptz | `now()` UTC. |

Restricciones: `ck_consulta_compuesto` exige `componente` o `herramienta`
(`0021:699-701`); el trigger `fn_consultas_agente_inmutable` bloquea UPDATE,
DELETE y TRUNCATE (`0021:719-735`); `tei_app` solo tiene SELECT/INSERT
(`0021:862-864`). Es **append-only** (INV-AW15).

### 7.2 Protocolo de escritura

1. El gate termina (autorizado o denegado) y produce un `ResultadoTool` o un
   error de gate.
2. El registry abre **una transacción separada** y inserta **una fila** por
   intento terminado. No se actualiza después: si hay que corregir, se inserta
   otra fila (append-only).
3. `empresa_id` y `contacto_id` salen del `ContextoAgente`; `request_id` del
   runtime; `ocurrido_en` lo pone la base.
4. Para lecturas: si la inserción de auditoría falla, **no se devuelven datos**
   (`AUDITORIA_FALLIDA`); el runtime reintenta una vez. Para escrituras de
   solicitud: la solicitud ya está comprometida; la auditoría se reintenta y, si
   persiste el fallo, se registra en el log del runtime con el `solicitud_id`.
   Esta asimetría es deliberada: no se puede “desescribir” una solicitud por un
   fallo de log, pero tampoco se entrega dato sin rastro.
5. La transacción de auditoría no incluye llamadas externas ni la transacción de
   la tool. `fn_auditoria` de las tablas del módulo registra además el cambio en
   `nucleo.auditoria` (INSERT/UPDATE), pero eso es auditoría de datos, no de
   consultas; no se duplica en `auditoria_consultas_agente`.

### 7.3 Mapeo D-17

| Requisito D-17 (`docs/negocio/preguntas.md:42`) | Columna / convención |
|---|---|
| Quién | `empresa_id`, `contacto_id` |
| Qué preguntó | `pregunta_resumida` (intención + extracto redactado; nunca el audio/foto) |
| Qué tool/módulo | `componente`, `variable`, `herramienta` |
| Qué datos tocó | `datos_tocados` = `{ "ids": [...], "total": n, "_meta": { "tool_version": 1, "schema_di": "di/v1" } }` |
| Respuesta resumida | `respuesta_resumida` (síntesis; no el payload completo) |
| Timestamp | `ocurrido_en` |
| Autorización | `acceso_otorgado` |
| Correlación | `request_id` |
| Conversación/mensaje | `conversacion_id`, `mensaje_id` |

`datos_tocados` no guarda el contenido íntegro (el comentario de la tabla lo
prohíbe, `0021:714-716`). Se limita a 50 IDs; si hay más, `total` y los primeros
50. El `_meta` es la única forma de guardar la versión de tool/DI sin una columna
nueva; no se usa para datos de negocio.

### 7.4 Casos de denegación (una fila cada uno)

| Caso | `componente` | `variable` | `herramienta` | `acceso_otorgado` | `respuesta_resumida` |
|---|---|---|---|---|---|
| Manifiesto inválido | tool.componente | tool.variable | tool.nombre | false | `MODULO_INACTIVO` |
| Empresa sin flag | tool.componente | tool.variable | tool.nombre | false | `MODULO_INACTIVO` |
| Rol no permitido | tool.componente | tool.variable | tool.nombre | false | `NO_AUTORIZADO:rol` |
| ACL de componente ausente/false | tool.componente | `NULL` | tool.nombre | false | `NO_AUTORIZADO:componente` |
| ACL de variable ausente/false | tool.componente | tool.variable | tool.nombre | false | `NO_AUTORIZADO:variable` |
| Contacto inactivo/OTP pendiente | tool.componente | tool.variable | tool.nombre | false | `NO_AUTORIZADO:identidad` |
| Tool desconocida | `agente` | `NULL` | nombre solicitado | false | `TOOL_DESCONOCIDA` |
| Entrada inválida | tool.componente | tool.variable | tool.nombre | **true** | `DATOS_INVALIDOS` |
| Error de base tras el gate | tool.componente | tool.variable | tool.nombre | **true** | `ERROR_INTERNO` / `REGLA_NEGOCIO` |
| Éxito | tool.componente | tool.variable | tool.nombre | **true** | síntesis |

La fila de denegación no revela el dato denegado; el `respuesta_resumida` es un
código, no la frase que ve el contacto. La frase la genera el runtime.

### 7.5 `acceso_otorgado` no es “éxito”

- `true` = el gate autorizó (módulo, rol y ACL pasaron). La tool pudo fallar
  después (timeout, 0 filas, error de base).
- `false` = el gate denegó. No se ejecutó el ejecutor.
- Un `DATOS_INVALIDOS` tiene `acceso_otorgado=true` porque la autorización pasó;
  el problema fue la entrada. Esto es lo que permite distinguir “no autorizado”
  de “autorizado pero mal formado” en la vista de auditoría.

### 7.6 Teléfono no registrado: no hay fila posible

`contacto_id` es `NOT NULL` con FK compuesta (`0021:681,693-694`). Un teléfono
que no resuelve a un contacto **no puede** insertar en
`auditoria_consultas_agente` sin inventar un contacto. Por lo tanto:

- el intento se registra en el **log del runtime** con `request_id`, un hash del
  teléfono (nunca el número completo) y el motivo `TELEFONO_NO_REGISTRADO`;
- no se crea fila en la tabla de auditoría;
- la respuesta al contacto es la genérica anti-enumeración (ADR-0003 §5).

Esto es una limitación declarada, no un olvido. Si el dueño exige auditoría de
intentos no registrados en la base, se necesita una tabla nueva o un
`contacto_id` nullable; ambas son migraciones y no se hacen en F2.1. Queda como
🔴 en §9.8.

### 7.7 Retención (D-17 abierta)

No hay purga ni partición en F2.1. La tabla crece linealmente con las consultas.
La retención, el archivado y quién puede leerla son D-17
(`docs/negocio/preguntas.md:42`), **no** una decisión de este documento. Hasta que
se ratifique:

- no se borra nada (el trigger lo impide);
- la vista O4.5 solo lee;
- el costo de almacenamiento y la latencia de consultas históricas se monitorean;
- si la tabla se vuelve un problema operativo, la salida es una migración de
  particionado/archivo, no un `DELETE` (que el trigger rechaza).

### 7.8 Lectura de auditoría (O4.5, reservada)

`GET /nucleo/agente/auditoria` con permiso `auditoria:leer` (no `agente:buzon`,
para no dar auditoría a todo el que ve el buzón). Filtros: `contacto_id`,
`desde`, `hasta`, `herramienta`, `acceso_otorgado`, `limit` 1–200, `offset`.
Devuelve las columnas de §7.1, sin `datos_tocados` completos si el payload es
grande (se resume). Es solo lectura; no hay endpoint de escritura.

---

## 8. Versión de modelos y swap

### 8.1 Bloque `modelos` del manifiesto

```jsonc
"modelos": {
  "orquestador": {
    "proveedor": "anthropic",
    "modelo": "claude-opus-4.7",
    "revision": "configurada-en-deploy",
    "prompt_version": "sha256:…"
  },
  "asr":    { "proveedor": "openai", "modelo": "whisper-3", "revision": "…", "prompt_version": "n/a" },
  "vision": { "proveedor": "openai", "modelo": "gpt-5.x",   "revision": "…", "prompt_version": "sha256:…" },
  "pdf":    { "proveedor": "anthropic", "modelo": "claude-opus-4.7", "revision": "…", "prompt_version": "sha256:…" }
}
```

- Los nombres copian la asignación ratificada en ADR-0004 §3.1.1; **no** son una
  elección de F2.1. El ID exacto de API y la revisión los fija el proveedor en el
  deploy.
- `prompt_version` es un hash del prompt versionado en el repo; no un número
  inventado. Si el prompt no aplica (ASR), `"n/a"`.
- `modalidades` y `modelos` se validan juntos (V16): no se puede activar voz sin
  ASR declarado.
- El manifiesto no guarda claves ni endpoints; los secretos viven en el entorno
  del backend (O3.8). El manifiesto solo declara identificadores.

### 8.2 `schema_di` y versionado del contrato

- El DI es `di/v1` (ADR-0003 §3.4). El runtime rechaza un DI con otro `schema`
  antes de invocar una tool.
- Un cambio incompatible del DI es `di/v2`: nuevo `schema_di` en el manifiesto,
  nuevo validador y nuevo bloque de evaluación. Los DIs `v1` ya persistidos en
  `conversacion_mensajes.metadata` se conservan y se leen como `v1`; no se
  reescriben (el DI es inmutable, ADR-0003 §3.4).
- No se migran conversaciones históricas. La convivencia es por versión declarada
  en el propio DI; el runtime no “adivina” la versión.

### 8.3 Procedimiento de swap (modelo o proveedor)

1. **Cambio de configuración:** editar `modelos.<tarea>` en el manifiesto
   (proveedor/modelo/revisión/prompt_version). No se toca código de tools ni de
   negocio.
2. **Re-evaluación obligatoria:** correr el protocolo ADR-0003 §15 contra el
   corpus versionado con el nuevo `(proveedor, modelo, prompt)`; registrar el
   resultado en `docs/qa/`. Sin evaluación, no se activa la modalidad/tarea.
3. **Despliegue con el módulo apagado:** el flag por empresa sigue en `false`;
   se enciende primero en una empresa piloto.
4. **Observación:** errores por modalidad, tasa de re-pregunta, costo. Si el
   umbral no se cumple, se revierte el manifiesto.
5. **Rollback:** `git revert` del manifiesto + redeploy; los DIs ya emitidos
   conservan su `versiones` y siguen auditables. No hay migración ni reescritura
   de datos.
6. **Swap por tarea, no global:** ASR, visión, PDF y orquestador se cambian por
   separado (ADR-0004 §6.4). Cambiar uno no obliga a cambiar los otros.

### 8.4 Lo que el swap no puede hacer

- Usar endpoints con estado del proveedor (Files, vector stores, Assistants,
  Threads, `store=true`, Batch) para datos del ERP. La razón es de rollback y
  privacidad: si el estado vive en el proveedor, cambiar de proveedor deja datos
  retenidos o exige import/export (ADR-0004 §6.3, R3).
- Cambiar el modelo sin re-evaluar el corpus. La evaluación es condición de
  activación, no un trámite.
- Cambiar `schema_di` sin declararlo en el manifiesto y sin validador.
- Poner el nombre del proveedor dentro de una tool o de una regla de negocio. El
  DI y el manifiesto son la frontera; el ejecutor no sabe qué modelo lo llamó.

### 8.5 Trazabilidad de la versión

| Dato | Dónde vive | Cómo se consulta |
|---|---|---|
| `(proveedor, modelo, revision, prompt_version)` | Manifiesto + registro de despliegue | `GET /nucleo/agente/estado` (resumen) y el repo (histórico git) |
| `schema_di` del mensaje | `conversacion_mensajes.metadata` (DI) | Por `mensaje_id` |
| Versión de la tool | `datos_tocados._meta.tool_version` en la auditoría | Vista O4.5 |
| Evaluación del corpus | `docs/qa/` | Documento de informe |

No hay una tabla de “versiones de modelo” en la base. Si el negocio quiere
consultar históricamente qué modelo respondió cada mensaje, el DI ya lo guarda en
`metadata`; no se agrega una tabla nueva sin necesidad demostrada.

---

## 9. Riesgos, deuda y preguntas abiertas

### 9.1 Bloqueos de F2.1 (deben cerrarse antes de encender)

| # | Bloqueo | Evidencia | Dueño | Criterio de cierre |
|---|---|---|---|---|
| B1 | No existe `nucleo.modulos_empresa` | Búsqueda en `supabase/migrations/` sin la tabla; `nucleo.empresas` sin config (`0004:102-134`) | `datos` | Migración `0023` aplicada en clon; gate lee la fila; ausencia = false probada. |
| B2 | `42501` cae en 500 | `backend/app/nucleo/errores.py:118-120,136-189` (solo `IntegrityError`); `backend/app/main.py:229-273` (handler de `IntegrityError`). `42501` llega como `sqlalchemy.exc.ProgrammingError` (MRO `InsufficientPrivilege → ProgrammingError → DatabaseError`; `is IntegrityError = False`), nunca entra a esos dos caminos; `grep -rn "42501" backend/app/` = 0 | `backend` | Handler para `ProgrammingError`/`DBAPIError` con `_sqlstate`: política → 403/404, `permission denied for table` → 500 con alerta (ADR-0005 `:245-247`); prueba HTTP real con `tei_app` sin GRANT/RLS. |
| B3 | No hay modelos SQLModel de las tablas del módulo ni `id_comercial_flete` en `Viaje` | `backend/app/nucleo/models.py:661` (clase `Viaje`, sin la columna); búsqueda en `backend/app/` de `contactos_whatsapp|solicitudes|hoja_ruta|auditoria_consultas_agente` = 0 | `backend` | Modelos + migración de lectura; prueba de round-trip. |
| B4 | El rol efectivo del núcleo no está verificado en este entorno | `docs/estado.md:103`; `backend/app/core/database.py:26-35,146-176` (con `NUCLEO_DATABASE_URL` explícito la guarda falla cerrada con 503 si el rol tiene `BYPASSRLS`; en fallback RLS queda inerte con `WARNING`) | `orquestador`/`backend` | `NUCLEO_DATABASE_URL` apunta a `tei_app` (sin `BYPASSRLS`) y `get_session_nucleo` se usa en el módulo; verificado en el entorno de ejecución, no solo en el código. |
| B5 | No hay tabla/columna de versión de tool en auditoría | `0021:678-702` | `backend` (convención `_meta`) | `datos_tocados._meta.tool_version` escrito y probado; no se agrega columna. |

### 9.2 D4 / D-18 — resolución por código

- **Hecho:** `UNIQUE (empresa_id, cliente_id, id_comercial_flete)`
  (`0021:555-557`); el índice por `(empresa, código)` puede devolver N
  (`0021:559-564`). Sonda: dos clientes de A generan `SQM-00001`, `count=2`
  (`docs/datos/agente-esquema.md:542,637`).
- **Decisión de F2.1:** regla de trabajo (b) de D-18: cliente forzado en tools de
  cliente; conductor acotado a sus viajes; admin exige cliente o devuelve
  `CODIGO_AMBIGUO` 409 con candidatos (§5.9). No se crea constraint ni tabla de
  prefijos.
- **Riesgo residual:** el admin que consulta solo por código recibe 409 y debe
  elegir; es UX, no fuga. El cliente no puede ambigüar porque su `cliente_id` es
  forzado.
- **Cierre:** D-18 ratificada por el dueño; si elige prefijo único, migración
  nueva y ajuste del resolvedor. Hasta entonces, la regla (b) es la única que no
  inventa unicidad.

### 9.3 D6 — rechazo solo-logra

- **Hecho:** nada en la base impide que un servicio, al rechazar, escriba además
  en `viajes`/`hoja_ruta`; `fn_solicitud_transicion` solo valida estado/motivo
  (`0021:458-483`; `docs/datos/agente-esquema.md:639`).
- **Contrato F2.1:** `rechazar` no llama a ningún ejecutor; solo actualiza
  `solicitudes` y, para `hoja_de_ruta`, `hoja_ruta.estado='rechazado'` + motivo
  (§6.4). No hay `INSERT` en `viajes`, `gastos`, `facturas` ni
  `hoja_ruta.valores_cargados`.
- **Prueba obligatoria (`qa`):** contar filas de `nucleo.viajes`,
  `nucleo.hoja_ruta` con `valores_cargados is not null` y `nucleo.viajes` del
  viaje antes/después; deben ser iguales. Mutación: si se agrega un
  `session.add(Viaje(...))` en el camino de rechazo, la prueba debe fallar.
- **Cierre:** prueba de integración + revisión de `backend`; no se agrega trigger
  en F2.1 porque el rechazo es un camino del servicio y el trigger de solicitud ya
  protege el estado.

### 9.4 D8 — `wa_message_id` único global

- **Hecho:** `uq_mensaje_wa_message_id` es global (`0021:343-347`); la columna no
  lleva `empresa_id` (`0021:320`). Un tenant podría insertar un `wamid` ajeno y
  bloquear su inserción (`docs/datos/agente-esquema.md:641`).
- **Decisión F2.1:** aceptar y documentar; **no** cambiar el índice. El runtime,
  ante `23505`, debe:
  1. buscar la fila existente por `wa_message_id`;
  2. si es de la misma empresa/conversación → responder 200 idempotente, no
     reprocesar;
  3. si es de otra empresa → registrar un evento `SEC` (sin datos del otro
     tenant), responder 200 al BSP y **no** procesar; no se revela la existencia.
- **Riesgo residual:** DoS entre tenants de baja probabilidad (los `wamid` son
  opacos y largos), aceptado. Cambiar a `(empresa_id, wa_message_id)` permitiría
  el mismo `wamid` en dos empresas, lo que también habilita un replay cruzado; es
  un trade-off, no una mejora automática. Si el BSP expone IDs por tenant o
  `auditor-seguridad` lo exige, se decide con migración.
- **Prueba:** dos empresas, mismo `wa_message_id`: la segunda no inserta, no
  procesa, responde 200; la primera queda intacta.

### 9.5 AB-02 — quién aprueba qué

- **Hecho:** el dueño mencionó “secretario” como aprobador
  (`docs/negocio/agente-whatsapp-roles.md:141-143`); el rol `secretaría` no existe
  en `RolEmpresa` (`backend/app/nucleo/models.py`; `permisos.py:58-139`); AB-02
  sigue abierta (`docs/PLAN_DESARROLLO.md:62`).
- **Contrato F2.1:** el endpoint exige `agente:aprobar`; **no** hardcodea un rol.
  La asignación de ese permiso a `admin`, `gerente`, `despacho` o un rol nuevo es
  decisión de negocio.
- **Riesgo:** si se agrega `agente:aprobar` a `TODOS_LOS_PERMISOS`, `admin` y
  `gerente` lo heredan por `set(TODOS_LOS_PERMISOS)` (`permisos.py:59-60`). Es un
  default razonable para O2.4, pero **no ratificado**. Se debe excluir
  explícitamente si el dueño decide que solo “secretaría” aprueba.
- **Cierre:** AB-02 ratificada y matriz de aprobación por `tipo` en
  `docs/negocio/`; prueba HTTP con el rol elegido y con un rol sin permiso.

### 9.6 D-17 — retención y acceso a la auditoría

- **Hecho:** D-17 abierta (`docs/negocio/preguntas.md:42`); no hay purga ni
  política de retención; la tabla es append-only (`0021:719-735`).
- **Contrato F2.1:** se escribe todo intento auditable; no se borra; la lectura es
  `auditoria:leer` (O4.5). No se inventa un período legal.
- **Riesgo:** crecimiento lineal y costo de almacenamiento; consultas históricas
  lentas si no se indexa por fecha (ya hay `idx_consultas_agente_empresa_fecha`,
  `0021:706-707`).
- **Cierre:** el dueño/legal fija retención y acceso; si hay que archivar, se hace
  con migración de particionado/archivo, nunca con `DELETE`.

### 9.7 D-09 — gerente digital

- **Hecho:** el mecanismo (a) capa semántica/tools compuestas vs (b) SQL
  read-only con guardarraíles sigue abierto (`docs/negocio/preguntas.md:34`).
- **Contrato F2.1:** `gerente.consultar` **no** se registra (§5.5). No hay SQL
  libre en el manifiesto ni en el descriptor. Si se elige (b), el executor debe
  ser un rol read-only real, con `empresa_id` impuesto externamente, límites de
  filas/tiempo y auditoría; eso es un ADR nuevo, no una tool más.
- **Riesgo:** si se “cuela” una tool de SQL libre, se rompe DEC-10 y la auditoría
  deja de ser verificable. V10 lo impide por configuración.

### 9.8 Otros riesgos y preguntas

| # | Riesgo/pregunta | Evidencia | Impacto | Mitigación F2.1 |
|---|---|---|---|---|
| R1 | Contradicción D-09 vs CL-05: el cliente “no ve números de camiones” pero la aprobación notifica camión/rampla/conductor | `agente-whatsapp-roles.md:101-103` vs `:31-34` | El alcance de la tool C2/C6 y la notificación no están claros | Se excluyen patentes de las tools; la notificación es un mensaje del runtime; decisión de negocio 🔴 |
| R2 | `A5 mantenimiento` no tiene objeto en `nucleo` | `models.py` sin pauta/mantenimiento; `servicio_alertas.py:172` solo reserva | No se puede responder “¿se hizo la mantención?” con datos del núcleo | No se registra A5; no se lee `public`; se crea el objeto en `nucleo` primero |
| R3 | Tool de lectura duplica el filtro del servicio humano (ADR-0006) | ADR-0006 §Consecuencias | Deriva entre consulta humana y del agente | Pruebas de paridad por componente; no reimplementar reglas, solo filtro/proyección |
| R4 | El runtime puede llamar a la tool con un `request_id` falso | No hay firma interna en F2.1 | Auditoría correlacionada pero no autenticada | El runtime es el único que llama; si se separa en worker, se exige autenticación de servicio (decisión de `backend`) |
| R5 | `auditoria_consultas_agente` no registra teléfonos no enrolados | `contacto_id NOT NULL` (`0021:681`) | Intento no auditado en base | Log del runtime con hash; si se exige base, tabla nueva (migración) |
| R6 | El módulo apagado no congela el buzón | Decisión de §6.7 | Un humano puede confirmar una solicitud con el agente apagado | Es deliberado para drenar; si el negocio quiere congelar, flag propio |
| R7 | `nucleo.empresas` no tiene config para el flag | `0004:102-134` | No hay lugar “natural” para el flag | Tabla `modulos_empresa` (0023), no una columna JSON informal |
| R8 | La aprobación de `agendamiento`/`documentos` no tiene ejecutor | §6.6 | El buzón no puede confirmar esos tipos | 501 `TIPO_SIN_EJECUTOR`; no se finge una escritura |
| R9 | Los servicios actuales hacen `commit()` por método | `destino-modular.md:308-316` | Componer ejecutor + estado en una transacción requiere adaptación | El ejecutor recibe la sesión y no commitea; si no, no se registra |
| R10 | El manifiesto con 20 tools puede ser difícil de mantener | Este documento | Deriva entre catálogo y código | Un archivo por tool + validación estricta + `GET estado` con conteo |

### 9.9 Handoffs

#### A `datos`

1. Migración `0023_modulos_empresa.sql` con el DDL de §2.7, RLS/FORCE, policy
   `tenant_empresa`, GRANT a `tei_app`, sin DELETE. Precondiciones: tabla
   inexistente, 0 filas. Rollback: `drop table`.
2. Revisar si el flag debe tener `habilitado_por` FK o texto; la propuesta usa
   texto por consistencia con `nucleo.auth_id`.
3. No tocar `0021`/`0022`; D4/D8 no se corrigen acá.
4. Criterio de aceptación: `select * from nucleo.modulos_empresa` con
   `app.empresa_id` de A no ve B; sin contexto, 0 filas; `INSERT` de B con
   contexto A → `42501`.

#### A `backend`

1. Paquete `backend/app/nucleo/agente/` con `contexto.py`, `manifest.py`,
   `registry.py`, `gate.py`, `ejecutores.py`, `solicitudes.py`, `api_agente.py`,
   `manifest.json`, `tools/`, `schemas/`.
2. Implementar `ContextoAgente` según ADR-0006; no importar `requiere_permiso` en
   el camino del agente.
3. Agregar `agente:buzon`, `agente:aprobar`, `agente:contactos` a
   `TODOS_LOS_PERMISOS`; decidir explícitamente qué roles los reciben (AB-02).
4. Implementar los endpoints de §6 y registrarlos en `backend/app/api/router.py`.
5. Mapear `42501` a 403/404 (B2) antes de encender **con un handler de
   `ProgrammingError`/`DBAPIError`**, no de `IntegrityError`: `42501` no es
   `IntegrityError` y hoy queda sin handler. Reutilizar `_sqlstate`
   (`errores.py:118-120`).
6. Agregar modelos SQLModel de lectura para las tablas del módulo y
   `id_comercial_flete` en `Viaje` (B3).
7. Implementar el envelope de §4.5, los códigos de §4.6 y la auditoría de §7.
8. Pruebas: unitarias de gate (4 llaves), integración con dos conexiones
   (aprobadores), HTTP (403/404/409/422/501), idempotencia de solicitud,
   `rechazar` sin escritura de negocio, paridad de al menos una tool por
   componente.

#### A `frontend`

1. O4.3: buzón con lista, detalle, tres acciones y diff; usar `nucleo.ts`.
2. O4.1: al activar un componente para un número, escribir el toggle de
   componente (`variable=NULL`) **y** los de variable; si no, el gate deniega.
3. O4.5: vista de auditoría con `auditoria:leer`; filtros de §7.8.
4. Manejar 409/501 según §6.9; no reintentar decisiones.
5. No crear un tercer cliente HTTP ni tipos `any` para montos: usar `string`.

#### A `qa`

1. Gate: matriz rol × componente × variable × `permitido` (true/false/ausente) ×
   módulo on/off; mutación: quitar una llave debe hacer fallar la prueba.
2. Dos conexiones reales: dos aprobadores sobre la misma solicitud (uno 200, uno
   409); dos `hoja_ruta.proponer` con el mismo `wa_message_id` (una solicitud).
3. D6: rechazar no cambia `viajes`, `gastos`, `hoja_ruta.valores_cargados`.
4. D4/D-18: dos clientes con `SQM-00001`; cliente ve solo el suyo; admin con solo
   código → 409; admin con cliente → 1.
5. D8: mismo `wa_message_id` en dos empresas; la segunda no procesa.
6. Auditoría: append-only (UPDATE/DELETE/TRUNCATE → 23514/42501), una fila por
   intento, `acceso_otorgado` correcto en denegación y en entrada inválida.
7. Paridad: al menos una tool de cliente, una de conductor y una de admin contra
   el endpoint humano equivalente.
8. Modelo: DI con `schema` distinto → rechazo; swap de manifiesto no rompe DIs
   viejos.

#### A `negocio-finanzas`

1. Ratificar AB-02: qué rol aprueba cada `tipo`; ¿se crea `secretaría`?
2. Ratificar D-18: prefijo único vs exigir cliente; la regla (b) de F2.1 es
   provisoria.
3. Ratificar D-17: retención, acceso y qué se audita exactamente.
4. Resolver R1: alcance de la notificación de asignación al cliente.
5. Confirmar que las variables de §5.6 son la granularidad que el dueño quiere
   togglear (no una por tool).

#### A `auditor-seguridad`

1. Revisar el gate: ausencia de fila, `permitido=false`, rol, módulo, OTP.
2. Revisar IDOR: `cliente_id`/`chofer_id` forzados; referencias de admin
   revalidadas; `CODIGO_AMBIGUO` no filtra datos de otro cliente.
3. Revisar D8: replay cross-tenant y respuesta 200 sin procesar.
4. Revisar que el agente no pueda escribir tablas de negocio ni leer `public`.
5. Revisar que la auditoría no guarde contenido sensible y que sea append-only.

### 9.10 Autoverificación

1. **¿Cada afirmación estructural tiene cita y nivel?** Sí: las de código/DDL van
   con `archivo:línea`; las propuestas van 🟡; las ausencias van 🔴 con el método
   de búsqueda.
2. **¿Distinguí documentado de verificado?** Sí: el manifiesto, el catálogo y el
   contrato son propuestas; el DDL, los servicios y los permisos son lecturas.
3. **¿Cada recomendación es la más pequeña y reversible?** Sí: no hay tabla nueva
   salvo `modulos_empresa` (necesaria para el flag); no hay cola, bus, caché,
   microservicio ni tercera fuente. El rechazo no ejecuta; el 501 evita fingir
   escrituras.
4. **¿Evité complejidad sin evidencia?** Sí: `gerente.consultar` queda fuera; el
   swap es configuración + evaluación, no código; la auditoría usa la tabla
   existente.
5. **¿Hay contradicciones entre mis artefactos?** No: ADR-0006 dice
   `ContextoAgente` y este documento lo usa; ADR-0003 §14 dice solicitud +
   aprobación y el buzón lo implementa; ADR-0004 §6 dice swap por configuración y
   §8 lo respeta. La única tensión es R1 (D-09 vs CL-05), declarada como pregunta,
   no resuelta por conveniencia.
6. **¿Cada decisión tiene criterios de aceptación y rollback?** Sí: §6.4, §8.3,
   §9.1–§9.9. El rollback del módulo es apagar el flag + `git revert`; no hay
   migración de datos asociada salvo `0023`, que se revierte con `drop table`.
7. **¿Listé lo que no pude verificar?** Sí: estado de base, rol efectivo, OTP,
   corpus/modelos, retención, aprobación AB-02, R1. Van en §9 y en el informe.
8. **¿Alguna cifra, SLA o norma legal salió de memoria?** No: no hay SLAs,
   retención legal ni volúmenes inventados. Los modelos se citan de ADR-0004; las
   fechas y montos son reglas del repo, no cifras nuevas.

---

*Documento creado 2026-10-30 por `arquitectura`. No reescribe ADR-0003, ADR-0004
ni ADR-0006. Si cambia el esquema del módulo, el catálogo de tools o la decisión
D-18, se actualiza este contrato o se reemplaza por uno nuevo; no se edita la
historia.*
