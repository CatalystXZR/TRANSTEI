# ADR-0002: Retiro del legacy `public` — plan por olas A–E

- **Estado:** **Aceptado y ejecutado (local): olas A–E.** A/B/C el 2026-10-31;
  D/E el 2026-11-01 sobre datos ficticios. El `DROP` del **schema** se sustituyó
  por **`public` vacío** (se conserva por `btree_gist` y PostgREST); el `DROP` de
  los objetos legacy sí se ejecutó (`0028`).
- **Fecha:** 2026-10-29 · **Rev. 2:** 2026-10-31 · **Rev. 3:** 2026-10-31 ·
  **Rev. 4:** 2026-11-01 (D/E ejecutadas; ver §6.6/§6.7 y
  `docs/operacion/cutover-ejecutado-2026-11-01.md`).
- **Decide:** agente `arquitectura` (propuesta técnica y criterio). Ejecutan
  `datos`, `backend`, `frontend`, `qa` y `auditor-seguridad` según `AGENTS.md` §11.
- **Relación con ADR-0001:** lo continúa. ADR-0001 fija la convivencia; este ADR
  fija la trayectoria al estado final —`public` retirado— y registra lo ya
  ejecutado. Sustituye el §B.3 de ADR-0001 por las compuertas C1/C2/C3 + G0 de
  §4.2.
- **Relación con ADR-0005:** el retiro del legacy es requisito para escalar a más
  tenants; el gate `LEGACY_SOLO_TEI` es una frontera **de acceso**, no de datos
  (`ADR-0005`, fila P-1). La Ola C no relaja el gate.
- **Relación con las Olas A/B/C:** este ADR **registra** trabajo ejecutado y no lo
  revierte. Evidencia: `docs/frontend/f2-ola-a-retiro.md`,
  `docs/frontend/f2-ola-b-pantallas.md`,
  `docs/backend/informes/f2-ola-b-modulos-nucleo.md`,
  `docs/backend/informes/f2-ola-c-retiro-routers.md`,
  `docs/datos/retiro-legacy-modelo.md`.
- **Documentos relacionados:** `docs/arquitectura/retiro-legacy.md` (inventario
  por módulo, rev. 3), `docs/arquitectura/fuentes-de-verdad.md` (rev. 2),
  `docs/arquitectura/destino-modular.md`, `docs/arquitectura/deuda.md`,
  `docs/operacion/segundo-tenant.md`.

---

## Resumen ejecutivo

1. **El retiro de código terminó.** Tras las olas A, B y C: **0 routers legacy de
   negocio** (solo `/auth`), **0 pantallas legacy de negocio** (9 redirigen y 4
   fueron reescritas en el núcleo), **0 consumidores** de `lib/api.ts`,
   `lib/download.ts` o `importar-csv.tsx` (los tres archivos ya no existen).
2. **El retiro de datos no empezó.** `public` conserva **17 relaciones** con su
   histórico; ninguna migración borró tablas (`grep "drop table public"` → 0) y
   el cutover D-2 sigue bloqueado por `RET-01`.
3. **La identidad sigue en `public.usuarios`** y se escribe en cada alta de
   Supabase Auth por el trigger `public.handle_new_user`. Es la dependencia que
   impide cualquier `DROP` y el alcance real de la Ola E.
4. **Ningún módulo está "retirado" en el sentido de fuente de verdad**: C2
   (cero consumidores de código) está cerrada; **C1 está cerrada o parcial según
   el módulo y C3 sigue abierta en todos**. El avance depende de si la Ola B
   construyó destino y de si la función se conservó.
5. **Lo que no se retiró es deliberado y verificable**: tablas de `public`,
   `public.usuarios`, el trigger de identidad, el gate `LEGACY_SOLO_TEI`, el
   middleware de congelamiento, el flag `cutover_control`, los modelos legacy,
   `settings_db.py` (código muerto) y los scripts de seed/cutover.

---

## 0. Método y límites de esta revisión

- **Método:** lectura estática de `backend/app/api/router.py`,
  `backend/app/api/routes/`, `backend/app/nucleo/`, `backend/app/main.py`,
  `frontend/src/{app,lib,components}`, migraciones `0001`–`0026` y los informes
  fechados de las tres olas.
- **Sin shell en esta sesión:** no ejecuté `pytest`, `make`, `psql` ni `git`.
  Los conteos de suite y de base se citan con la fuente que los produjo y se
  marcan 🟡. Lo que leí directamente va 🟢.
- **Árbol en movimiento:** `0024`–`0026` están **untracked** según
  `docs/datos/catalogo-migraciones.md:205-207`. Un clon limpio de `HEAD` **no**
  reproduce el esquema de la Ola B. Riesgo R13.
- **Cifras volátiles:** las de `docs/estado.md` son de una verificación anterior
  y hoy están desactualizadas (§8.2). No se copian como estado.

| Marca | Significado |
|---|---|
| 🟢 | Leído en archivo, con `archivo:línea` |
| 🟡 | Deducido de código o dato de un informe fechado; se dice qué lo confirmaría |
| 🔴 | No determinable en esta sesión; se indica el comando/consulta |

---

## 1. Contexto verificado (2026-10-31, rev. 3)

### 1.1 Superficie de API

- **Un solo router legacy: `auth`.** `backend/app/api/router.py:24-39` monta
  **16** `include_router`: `auth` + 15 del núcleo. 🟢
- **Los 4 routers de la Ola B** (mantenimiento, nómina, IVA/configuración,
  export) se agregan en `backend/app/nucleo/router.py:14-23` y se montan bajo
  `/nucleo` en `backend/app/nucleo/api.py:25,47`. Total de routers de módulo:
  **20** (1 + 15 + 4). 🟢
- **Los 11 routers legacy de negocio fueron borrados del disco**, no solo
  desmontados: `backend/app/api/routes/` contiene únicamente `__init__.py` y
  `auth.py`. 🟢
- **Las rutas antiguas responden 404**: probado por
  `backend/tests/test_f2_ola_c_retiro_routers.py:43,53,71,81` (OpenAPI + HTTP) y
  por smoke real (`docs/backend/informes/f2-ola-c-retiro-routers.md:107-122`). 🟢
- **`/auth/me` sigue vivo** (`backend/app/api/routes/auth.py:12-28`) y exige
  token; es la última pieza legacy de negocio. 🟢
- **OpenAPI**: 101 paths, 1 legacy (`/health`, fuera de `/api/v1`)
  (`f2-ola-c-retiro-routers.md:89-92`). 🟡 (dato del informe, no re-ejecutado).

### 1.2 Superficie de frontend

- **9 pantallas retiradas** con `permanentRedirect` 308 en
  `frontend/src/app/(retiradas)/` (`dashboard`, `viajes`, `viajes/[id]`, `flota`,
  `clientes`, `choferes`, `facturacion`, `cobranzas`, `kpis`). 🟢
- **4 pantallas que eran legacy fueron reescritas** y siguen en `(app)`:
  `mantenimiento`, `liquidaciones`, `iva`, `configuracion` importan
  `@/lib/nucleo` (`frontend/src/app/(app)/{mantenimiento,iva,liquidaciones,configuracion}/page.tsx`). 🟢
- **Ningún archivo importa `@/lib/api`.** `frontend/src/lib/` solo contiene
  `nucleo.ts`, `navigation.ts`, `format.ts`, `utils.ts`, `agente.ts`,
  `offline-queue.ts`, `use-nucleo-empresa.ts`. `api.ts`, `download.ts` e
  `importar-csv.tsx` **no existen**. 🟢
- **La navegación ya no tiene flag `legacy`**: `navigation.ts:37-85` declara 17
  ítems, todos del núcleo. 🟢
- **El gate de UI desapareció**: `frontend/src/app/(app)/layout.tsx:9-35` solo
  exige sesión. `es_legacy` sobrevive únicamente para elegir la pantalla de
  inicio (`frontend/src/components/app-shell.tsx:40`). **Consecuencia:** un
  usuario de TES ya no es redirigido por la UI; el 403 real lo impone el backend. 🟢
- **E2E actualizado a Olas B/C**: `frontend/e2e/tei.spec.ts` contiene **20
  pruebas**: 11 del piloto, 3 de la Ola A, 2 de menús (TEI/TES con 17 ítems del
  núcleo), 4 de las pantallas reimplementadas y 1 de los 11 routers 404 con
  OpenAPI. 🟢 **La última pasada no está registrada en esta sesión** (🔴): el spec
  está alineado, el verde no está evidenciado.

### 1.3 Superficie de datos

- **`public` conserva sus 17 relaciones**: 15 de negocio de
  `0001_esquema_base.sql:36-215`, `kpis` (`0003_kpis.sql:5-20`) y `_migraciones`
  (`0002_config_cobranza.sql:6-9`). Ninguna migración las borra
  (`grep "drop table"` solo aparece en comentarios de rollback de `0023`–`0026`). 🟢
- **`nucleo` pasó de 40 a 46 tablas y de 45 a 51 políticas** con `0024`–`0026`
  (`docs/datos/retiro-legacy-modelo.md:25-32`; misma cifra en
  `docs/datos/catalogo-migraciones.md:205-213`). 🟡 (medido por `datos`; no
  re-ejecutado aquí).
- **Migraciones en disco: 26** (`0001`–`0026`), de las cuales `0024`–`0026` están
  **untracked** (`docs/datos/catalogo-migraciones.md:205-207`). 🟢 por listado de
  directorio; 🟡 el estado git.
- **Escritores de `public` que quedan:**
  - El **trigger de identidad** `public.handle_new_user`
    (`0001_esquema_base.sql:248-262`) inserta en `public.usuarios` en **cada**
    alta de Supabase Auth. Es escritura de producción, no de desarrollo. 🟢
  - `scripts/seed_local.py:198,235,270,305,337` y
    `scripts/seed_segundo_tenant.py:79` (solo local). 🟢
  - Ningún router, servicio ni tarea del backend escribe en `public.*`. 🟢
- **Lectores de `public` que quedan:**
  - `backend/app/api/deps.py:15-17` + `auth.py` → `public.usuarios` (identidad). 🟢
  - `backend/app/nucleo/servicio_cutover.py:97` → `count(*) from public.viajes`
    (única lectura `nucleo → public`, G0.2). 🟢
  - `scripts/cutover_legacy.py:110-351` (fuera del runtime). 🟢
  - `backend/app/core/settings_db.py:9-19` lee `public.configuracion`, pero
    **no tiene ningún consumidor en `backend/app/`**: solo lo usa
    `backend/tests/test_seguridad_ola2.py`. Es código muerto. 🟢
- **IVA**: el módulo lee `nucleo.config_vigente(empresa, 'iva_porcentaje')`
  (`backend/app/nucleo/servicio_iva.py:15-16,44-51`). **Pero** la creación de
  factura sigue aceptando `tasa_iva` desde el request
  (`backend/app/nucleo/schemas.py:1543`; `servicio_facturacion.py:544`). Son dos
  fuentes del mismo parámetro **dentro del núcleo**. 🟢

### 1.4 Identidad, gate y cutover (sin cambios)

- **Identidad:** `GET /auth/me` resuelve el perfil desde `public.usuarios` vía
  `deps.py:15-17`; el frontend lo llama en cada carga
  (`frontend/src/context/auth-context.tsx`). El trigger `handle_new_user`
  (`0001:248-262`) mantiene el espejo. **Dos identidades conviven**:
  `public.usuarios` (rol global) y `nucleo.usuarios_empresa` (rol por empresa). 🟢
- **Gate multiempresa:** `GateLegacyMiddleware` (`backend/app/main.py:217-302`)
  sigue activo y exige membresía en `LEGACY_EMPRESA_ID` para toda ruta bajo
  `/api/v1` salvo `/nucleo` y `/auth` (`main.py:157-175`). Sin membresía: 403
  `LEGACY_SOLO_TEI` (`main.py:191-214`). 🟢
- **Como ya no hay rutas legacy de negocio, el gate hoy solo se manifiesta sobre
  rutas inexistentes**: TES recibe 403 antes del 404 y TEI recibe 404. Es un
  oráculo de tenant menor, no una garantía de negocio. Ver R1/R15 y el handoff a
  `auditor-seguridad`.
- **Congelamiento:** `legacy_congelado()` fail-closed y
  `congelar/descongelar` con rowcount (`nucleo/servicio_cutover.py`); middleware
  activo (`main.py:326-351`). Residual: caché de 5 s por proceso. 🟢
- **`nucleo.cutover_control`** no se archivó ni se retiró: G0.4 abierta. 🟢

### 1.5 Qué cambió respecto de la revisión 2

| Cambio | Evidencia | Efecto |
|---|---|---|
| **Ola B ejecutada**: 4 módulos construidos en `nucleo` | `0024`–`0026`; `nucleo/router.py:14-23`; `docs/datos/retiro-legacy-modelo.md:25-32` | M08/M09/M11/M14 pasan de "sin equivalente" a "equivalente con datos sin migrar" |
| **Ola C ejecutada**: 11 routers borrados | `backend/app/api/routes/`; `test_f2_ola_c_retiro_routers.py:43,53,71` | C2 de API cerrada en los 11; el legacy deja de tener superficie de escritura |
| **Frontend sin cliente legacy** | ausencia de `lib/api.ts`, `download.ts`, `importar-csv.tsx`; `navigation.ts:37-85` | C2 de UI cerrada en las 13 pantallas |
| **IVA con parámetro en `nucleo`** | `servicio_iva.py:15-16,44-51`; `0026` | G0.3 avanza; queda la tasa del comprobante (`schemas.py:1543`) |
| **`kpi_engine` eliminado** | `backend/app/services/` no existe; informe Ola C §1.2 | RET-05 se resolvió **por retiro de código**, no por decisión del dueño |
| **E2E actualizado a B/C** | `frontend/e2e/tei.spec.ts` (20 pruebas: Olas A/B/C) | El spec está alineado; **falta la última pasada de `qa`** |
| **Migraciones de la Ola B untracked** | `docs/datos/catalogo-migraciones.md:205-207` | El esquema no está en `HEAD`; riesgo de despliegue (R13) |

---

## 2. Problema

**El retiro de código ya ocurrió; el riesgo se movió a los datos y a la
identidad, y el criterio de "retirado" debe impedir que se confunda con
"migrado".**

En una frase verificable: *dado un concepto de negocio, ¿el sistema puede
responder hoy, sin consultar a una persona, si su histórico vive en `nucleo`, si
`public` sigue siendo necesario para operar y qué falta para borrarlo?* Hoy la
respuesta es **no**: el código está retirado, los datos no, la identidad no y no
existe consulta de reconciliación (§4.2 C3).

La revisión 2 preguntaba si existía un criterio de retiro por módulo. **Ese
criterio existe y se aplicó a A–C.** Lo que falta es aplicarlo a D–E, que son de
naturaleza distinta: uno mueve dinero y documentos, el otro borra el esquema.

---

## 3. Alternativas (revisadas a la luz de A–C)

| Alternativa | Ventajas | Costes / riesgos | Reversible | Impacto en legacy | Impacto en datos |
|---|---|---|---|---|---|
| **A. Big-bang** | Un solo corte | Concentra el riesgo; exige D y E juntos; el cutover actual no migra cerrados (`scripts/cutover_legacy.py:15,283`) | Baja | Total | Alto |
| **B. Por olas con compuertas (elegida y en curso)** | A–C ya demostraron que funciona: cero consumidores, 404 probado, suites verdes | Más entregas; la Ola C se adelantó a D (ver §9.10) | Alta en A–C; baja en D–E | Progresivo | Bajo por concepto, con conteos |
| **C. Convivencia permanente** | Cero migración de datos | Mantiene `public.usuarios`, el gate y el histórico sin reconciliación; impide más tenants | — | Congela el estado | Divergencia sin detección |
| **D. Solo retirar el frontend** | Barato | **Refutada**: se ejecutó en A y no bastó; los routers y los datos seguían ahí | Alta | Parcial | Ninguno |

**Descartadas.** A: sin mecanismo de aprendizaje y con `RET-01/02/09` abiertas.
C: es lo que el dueño ordenó evitar. D: ya se ejecutó y quedó demostrado que no
cierra el problema.

---

## 4. Decisión

**Se mantiene la alternativa B. Las olas A, B y C se declaran EJECUTADAS. Las
olas D y E quedan PENDIENTES con compuertas explícitas. El retiro de código no
borra datos: `public` sigue siendo la única copia del histórico financiero,
laboral y tributario hasta que `RET-01`/`RET-02` lo resuelvan.**

### 4.1 Estado final: qué está cumplido

| # | Condición de §4.1 (rev. 2) | Estado | Evidencia |
|---|---|---|---|
| 1 | Ninguna ruta `/api/v1/*` fuera de `/nucleo` y `/auth` sirve negocio legacy | ✅ **Cumplida** | `router.py:24-39`; `test_f2_ola_c_retiro_routers.py:53` |
| 2 | Ninguna pantalla ni componente llama a `lib/api.ts` | ✅ **Cumplida** | `grep "@/lib/api"` → 0; `api.ts` inexistente; `navigation.ts:37-85` |
| 3 | Identidad y configuración tributaria viven en `nucleo` | ✅ **Cumplida** | `/auth/me` desde JWT + `nucleo.usuarios_empresa`; IVA en `nucleo.configuracion_empresa` |
| 4 | `public` deja de recibir escrituras | ✅ **Cumplida** | Trigger y `public.usuarios` retirados (`0028`); seeds solo escriben `nucleo` |
| 5 | `nucleo` es la única fuente de verdad de negocio | ✅ **Cumplida (local)** | Ola D ejecutada; `public` sin tablas. Entornos con datos reales requieren D-2 |

**Conclusión de lenguaje (rev. 4):** con D y E ejecutadas en local, el proyecto
**sí** puede decir que el legacy está retirado: no hay tablas de negocio, rutas ni
pantallas legacy, y `public` está vacío. En un entorno con datos reales, la
ratificación de D-2 (`RET-01`) y el destino del histórico (`RET-02`) siguen
abiertos antes de repetir el cutover.

### 4.2 Compuertas de retiro — estado por compuerta

#### C1 — Paridad funcional demostrada con prueba

| Bloque | Estado | Evidencia |
|---|---|---|
| 9 pantallas de la Ola A | ✅ **UI cerrada**: equivalente único + 308 probado. C1 de sus módulos se evalúa en §5.1 | `(retiradas)/*`; bloque "Ola A" de `frontend/e2e/tei.spec.ts` |
| 4 módulos de la Ola B | ⏳ **Paridad implementada y probada; falta prueba de mutación documentada** | `test_nucleo_ola_b_modulos.py` (25 pruebas); `f2-ola-b-modulos-nucleo.md:65-84` |
| Dashboard (M05) | ⏳ **Brecha de lectura** (no tiene acciones de escritura): los totales de dinero del legacy no se incorporaron | `TableroKpisOut` (`schemas.py:1711-1727`) no tiene `ingresos_mes`/`gastos_mes`; `grep` en frontend → 0; RET-06 |
| KPIs (M12) | ⏳ **No hay paridad**: el motor de fórmulas se eliminó y la rentabilidad fija ocupa parte del espacio. La decisión de producto sigue en RET-05 | `backend/app/services/` no existe; `api_rentabilidad.py` |
| Export/import | ⏳ **Parcial**: export reconstruido (CSV con neutralización de fórmulas); **import CSV desapareció** | `servicio_export.py`; `test_nucleo_ola_b_modulos.py:803`; RET-10 |

**Regla vigente:** una pantalla con 308 **no** cierra C1 de su módulo. C1 se
cierra por acción de escritura, no por URL.

#### C2 — Cero consumidores

| Artefacto | Estado | Evidencia |
|---|---|---|
| 11 routers legacy | ✅ **Cumplida** | no existen en `api/routes/`; `include_router` → 0; 404 probado |
| 13 pantallas legacy | ✅ **Cumplida** | 9 redirigen; 4 reescritas contra `lib/nucleo.ts` |
| `lib/api.ts`, `download.ts`, `importar-csv.tsx` | ✅ **Cumplida** (archivos borrados) | ausencia en `frontend/src` |
| Tests que ejercitaban el legacy | ✅ **Cumplida** (borrados/reescritos) | `test_flujos_criticos.py`, `test_reglas_negocio.py`, `test_kpi_engine.py` no existen; `test_r02_licencia_nucleo.py` conserva R-02 |
| Seeds y scripts | ⏳ **Parcial** | `seed_local.py:198,235,270,305,337`; `seed_segundo_tenant.py:79`; `cutover_legacy.py:110-351` |
| `public.usuarios` | ❌ **Abierta** | `deps.py:15-17`; trigger `0001:248-262` |

#### C3 — Datos migrados, archivados o declarados no migrables

**Estado: ABIERTA en todos los conceptos.** 🟢

- `cutover_legacy.py` migra maestros y viajes abiertos, omite cerrados
  (`:15,283`), fuerza `confirmado` (`:383`) y no toca gastos, facturas, pagos,
  liquidaciones, mantenimientos ni configuración.
- No existe consulta de reconciliación en el repo (ni job, ni vista, ni tabla de
  mapeo de identificadores).
- `RET-02` (destino del histórico y plazo) sigue sin respuesta.

### 4.3 Precondición transversal G0

| # | Condición | Estado | Evidencia / lo que falta |
|---|---|---|---|
| G0.1 | Identidad en `nucleo` que reemplace `public.usuarios`, `/auth/me` y el trigger | ❌ **Abierta** | `deps.py:15-17`; `0001:248-262`; alta de usuario desde `nucleo` no existe |
| G0.2 | Ningún código de `nucleo` lee `public.*` | ⏳ **Casi**: queda 1 lectura | `servicio_cutover.py:97` (`public.viajes`); el resto → 0 |
| G0.3 | `iva_porcentaje` y parámetros tributarios en `nucleo`, con dueño y auditoría | ⏳ **Parcial** | `0026` + `servicio_iva.py:44-51`; **pero** `schemas.py:1543` permite fijar la tasa en el request |
| G0.4 | `cutover_control` y middleware se retiran juntos | ❌ **Abierta** | `main.py:326-351`; `servicio_cutover.py` |
| G0.5 | Restore drill con comparación antes/después | ❌ **Abierta** | `make restore-drill` no ejecutado en esta fase |
| G0.6 | Backup verificado + autorización antes de cualquier `DROP` | ❌ **Abierta** | Requiere dueño + contador (`RET-09`) |

### 4.4 Qué se retiró (código y documentación)

- Los 11 routers legacy de negocio y su `include_router`; el `include_router` de
  `auth` se conserva hasta G0.1.
- Los modelos pueden quedarse: `backend/app/models/__init__.py` sigue siendo
  importado por `auth`, `deps`, `schemas` y `settings_db`. **No se retiraron** y
  no deben retirarse hasta la Ola E.
- `backend/app/services/kpi_engine.py` y el paquete `app/services/` (sin
  consumidores desde la Ola C).
- `frontend/src/lib/api.ts`, `lib/download.ts`, `components/importar-csv.tsx`.
- Las 9 pantallas de la Ola A (redirección 308) y las 4 pantallas legacy,
  reescritas contra el núcleo.
- Tests exclusivamente legacy: borrados o reescritos contra `nucleo`
  (`test_r02_licencia_nucleo.py` conserva la regla vigente).

### 4.5 Lo que **NO** se retiró (y por qué)

| Objeto | Por qué sigue | Condición para retirarlo |
|---|---|---|
| **Las 17 relaciones de `public`** | Contienen el histórico financiero, laboral y tributario que la Ola D no migró. Borrarlas sin backup es irreversible | Ola D cerrada + `RET-02` + backup verificado + autorización (`RET-09`) |
| **`public.usuarios`** | Es la identidad de **todos** los tenants: `/auth/me` y `deps.py` la leen; el trigger la escribe en cada alta; el seed del segundo tenant la usa (`seed_segundo_tenant.py:79`) | G0.1 + E.1/E.2: perfil y alta en `nucleo`, `auth-context` apuntando al nuevo endpoint, trigger retirado |
| **Trigger `public.handle_new_user`** | Mantiene el espejo de identidad; sin él, un alta nueva no puede entrar | Igual que la fila anterior; se retira **después** del dual-run de E.1 |
| **Gate `LEGACY_SOLO_TEI`** | Aunque ya no hay negocio legacy, sigue siendo la frontera de acceso y lo cubren pruebas del segundo tenant (`test_f2_tenant2_gate_legacy.py`) | G0.4 / E.3, junto con el middleware de congelamiento |
| **Middleware de congelamiento y `nucleo.cutover_control`** | El cutover D-2 lo necesita como interruptor de escrituras durante la ventana de migración | E.3: archivar historial y retirar flag + middleware juntos |
| **Modelos legacy (`app/models/`)** | Los usan `auth`, `deps`, `schemas` y `settings_db`; borrarlos antes de G0.1 rompe el login | E.4, cuando `grep` de modelos legacy → 0 |
| **`core/settings_db.py`** | Código muerto en producción, pero aún citado por una prueba y por documentación tributaria | E.4 (borrado o reemplazo por `servicio_configuracion`) |
| **Scripts `seed_local.py`, `seed_segundo_tenant.py`, `cutover_legacy.py`** | Escriben/leen `public` y son la herramienta de la Ola D; los seeds además reproducen el entorno local | Después de D/E, cuando `public` deje de existir y los seeds apunten solo a `nucleo` |
| **`public.configuracion`, `public.kpis`** | Sin lector de producción, pero con datos y valor de referencia histórica | `RET-02` (archivo o borrado con backup) |
| **Migraciones `0001`–`0026`** | Forward-only; son la trazabilidad del esquema | Nunca se borran (`AGENTS.md` §8) |
| **Bucket `respaldos` y `auth.users`** | Fuera del alcance de este ADR | `RET-02` / proveedor |

**Regla de lenguaje (vigente):** "retirar el módulo" significa **retirar su
código**. Nunca significa borrar sus datos. Un `DROP` es otro ADR.

---

## 5. Matriz de equivalencia por módulo (post Olas A/B/C)

### 5.1 Routers legacy → estado real

| # | Router legacy | Estado del código | Equivalente en `nucleo` | Datos | Compuerta que queda | Ola |
|---|---|---|---|---|---|---|
| M01 | `auth` (`/auth/me`) | **VIVO** (`auth.py:12-28`) | Membresía/rol en `nucleo.usuarios_empresa`; **no hay endpoint de perfil** | `public.usuarios` | C1, C2, C3, **G0.1** | E |
| M02 | `catalogos` | **RETIRADO** | CRUD `api_maestros.py`; import CSV **no** | maestros sin migrar | C3 (tara/capacidad, import) | B/D.1 |
| M03 | `viajes` | **RETIRADO** | `api.py`, `api_expediente.py`, `api_conductor.py` | viajes sin migrar | C3 (abiertos/cerrados) | C/D.1 |
| M04 | `gastos` | **RETIRADO** | `api_gastos.py` (superior: aprobación, storage) | gastos + archivos sin migrar | C3 (archivos) | C/D.1 |
| M05 | `dashboard` | **RETIRADO** | `api_alertas.py` (`TableroOut`) | sin tablas propias | C1 (totales de dinero, **RET-06**), C3 | C |
| M06 | `facturas` | **RETIRADO** | `api_facturacion.py` (pagos, NC, aging) | facturas sin migrar | C3 (dinero), **RET-03** | C/D.2 |
| M07 | `finanzas` | **RETIRADO** | fletes→`viajes-facturables`; cobranzas→aging; IVA→`api_iva.py` | sin tablas propias | C3 (dinero) | C/B/D.2 |
| M08 | `mantenimiento` | **RETIRADO** | `0024` + `api_mantenimiento.py` | pautas/mantenciones sin migrar | C3 | B/D.4 |
| M09 | `liquidaciones` | **RETIRADO** | `0025` + `api_nomina.py` | liquidaciones/anticipos/ajustes sin migrar | C3, **RET-07** (política) | B/D.3 |
| M10 | `configuracion` | **RETIRADO** | `0026` + `api_iva.py` (configuración por empresa) | `public.configuracion` sin migrar; `public.usuarios` vivo | C3, **G0.3**, **RET-04** | B/E |
| M11 | `export` | **RETIRADO** | `api_export.py` (solo export; import no) | sin tablas propias | **RET-10** (import) | B/D |
| M12 | `kpis` | **RETIRADO** | rentabilidad fija (`api_rentabilidad.py` + `servicio_rentabilidad.py`) | `public.kpis` sin migrar | **RET-05** (decisión), C3 | C |

**Lectura:** **11 de 12** routers retirados; queda solo identidad. **Ningún
módulo pasa C3**, y C1/C2 solo se cierran en el sentido de código.

### 5.2 Las 13 pantallas legacy originales

| Pantalla | Cliente actual | Estado 2026-10-31 | Equivalente | Ola |
|---|---|---|---|---|
| `/dashboard` | — | **Retirada** → 308 `/tablero` | `/tablero` | A ✅ |
| `/viajes` | — | **Retirada** → 308 `/despacho` | `/despacho` | A ✅ |
| `/viajes/[id]` | — | **Retirada** → 308 `/expediente` | `/expediente` | A ✅ |
| `/flota` | — | **Retirada** → 308 `/maestros` | `/maestros` | A ✅ |
| `/clientes` | — | **Retirada** → 308 `/maestros` | `/maestros` | A ✅ |
| `/choferes` | — | **Retirada** → 308 `/maestros` | `/maestros` | A ✅ |
| `/facturacion` | — | **Retirada** → 308 `/cobranza` | `/cobranza` | A ✅ |
| `/cobranzas` | — | **Retirada** → 308 `/cobranza` | `/cobranza` | A ✅ |
| `/kpis` | — | **Retirada** → 308 `/rentabilidad` | `/rentabilidad` | A ✅ |
| `/mantenimiento` | `lib/nucleo.ts` | **Reescrita en el núcleo** | `0024` + `api_mantenimiento.py` | B ✅ |
| `/liquidaciones` | `lib/nucleo.ts` | **Reescrita en el núcleo** | `0025` + `api_nomina.py` | B ✅ |
| `/iva` | `lib/nucleo.ts` | **Reescrita en el núcleo** | `api_iva.py` (solo débito) | B ✅ |
| `/configuracion` | `lib/nucleo.ts` | **Reescrita en el núcleo** | `0026` + `api_iva.py` | B ✅ |

**Precisión:** "pantalla migrada" ≠ "dato migrado" ≠ "módulo retirado". Hoy la
UI y la API son del núcleo; los datos históricos siguen en `public`.

---

## 6. Secuencia en olas — estado

### 6.1 Vista de conjunto

| Ola | Tipo | Alcance | ¿Cutover de datos? | Estado |
|---|---|---|---|---|
| **0** | Preparación | Línea base, censo, backup/restore, consumidores | No | ⏳ **Parcial**: suites y consumidores medidos; censo de datos y restore drill no |
| **A** | UI pura | 9 pantallas duplicadas → 308 | No | ✅ **Ejecutada 2026-10-31** |
| **B** | UI + construcción | 4 módulos sin equivalente | No (construir primero) | ✅ **Ejecutada 2026-10-31** |
| **C** | API pura | Desmontar y borrar routers sin consumidor | No | ✅ **Ejecutada 2026-10-31** |
| **D** | Datos (D-2) | Maestros, viajes, gastos, facturas, nómina, mantenimiento, configuración | **Sí** | ✅ **Ejecutada (local) 2026-11-01**: solo D.4 tenía filas (6 pautas); D.1–D.3/D.5 con 0 filas; backup + reconciliación Δ=0; idempotente. Un entorno con datos reales requiere ratificar D-2 (`RET-01`) |
| **E** | Identidad + cierre | `/auth/me`, `public.usuarios`, trigger, middleware/flag, `DROP` | **Sí** (destructivo) | ✅ **Ejecutada (local) 2026-11-01**: identidad desde JWT + `nucleo`, trigger y `public.usuarios` retirados (`0028`), `public` vacío. `RET-02` (destino del histórico) sigue abierta para entornos con datos reales |

### 6.2 Ola 0 — Línea base (parcial)

Hecho: inventario de routers, pantallas y consumidores; suites registradas en los
informes de las olas. **Falta:** censo de filas y sumas por tabla de `public`
(`retiro-legacy.md` §5), `make restore-drill` con comparación, y estado fechado de
`nucleo.cutover_control` en la base local.

**Criterio de cierre:** documento fechado con las salidas de `make unit`,
`make test`, `make e2e`, censo y restore drill. Sin eso, D no avanza.

### 6.3 Ola A — UI duplicada. ✅ Ejecutada

**Evidencia:** 9 pantallas con `permanentRedirect` 308; navegación sin ítems
retirados; `docs/frontend/f2-ola-a-retiro.md`; E2E de redirecciones
(`tei.spec.ts:149-183`).

**Criterios de aceptación:** cumplidos en lo verificable. La Ola A se cerró con
**15/15** E2E según `qa` (🟡, no re-ejecutado aquí). El spec fue ampliado después
a **20 pruebas** para cubrir las Olas B y C; **la última pasada no está
registrada** (R6), por lo que el verde actual es 🟡, no 🟢.

**Rollback:** `git revert` del commit de Ola A. Residual: los 308 pueden quedar
cacheados en el navegador.

### 6.4 Ola B — Módulos sin equivalente. ✅ Ejecutada

| Sub-ola | Módulo | Entrega | Evidencia |
|---|---|---|---|
| B.1 | Mantenimiento | `nucleo.pautas_mantenimiento`, `nucleo.mantenimientos`, vista de estado, `api_mantenimiento.py`, pantalla reescrita | `0024`; `docs/datos/retiro-legacy-modelo.md:42-85`; `test_nucleo_ola_b_modulos.py` |
| B.2 | Nómina | `nucleo.liquidaciones`, `anticipos_chofer`, `ajustes_liquidacion`; emisión idempotente; export CSV | `0025`; `docs/datos/retiro-legacy-modelo.md:86-103` |
| B.3 | IVA | `api_iva.py` (solo débito; tasa desde `nucleo.configuracion_empresa`) | `servicio_iva.py:15-16,44-51` |
| B.4 | Configuración | `nucleo.configuracion_empresa` con vigencia e historial append-only | `0026`; `servicio_configuracion.py` |

**Lo que la Ola B no hizo:** migrar filas del legacy (`docs/datos/retiro-legacy-modelo.md:34-36`),
modelar crédito fiscal ni la composición legal de la remuneración. Por eso B
cierra C1/C2 **de código**, no C3.

### 6.5 Ola C — API legacy. ✅ Ejecutada

**Evidencia:** 11 routers borrados; `api/routes/` solo `auth.py`; 404 probado;
`make test` 405 passed / 0 skipped; `grep "@/lib/api"` → 0
(`f2-ola-c-retiro-routers.md:17-34,107-122,168-171,245-248`).

**Desviaciones registradas (y su criterio):**

1. **Se ejecutó C antes de D.** El ADR rev. 2 exigía B→C y dejaba C.2 diferido
   hasta que B cerrara. La UI ya había migrado y los routers no tenían
   consumidor; mantenerlos habría dejado superficie de escritura sin usuario. Se
   acepta como **desviación de secuencia**, con la consecuencia de que D
   importará datos en tablas que ya tienen escritores del núcleo: la migración de
   D debe ser **idempotente y con ventana congelada**.
2. **Las pruebas del gate cambiaron de 200/401 a 404** en 2 casos HTTP
   (`test_f2_tenant2_gate_legacy.py`). El **mecanismo** del gate no cambió. Se
   corrige el criterio §9.8: lo exigible es que el gate siga impidiendo el acceso
   de TES **antes** del enrutado, no que una ruta inexistente devuelva 200/401.
3. **`kpi_engine` se eliminó con RET-05 abierta.** Es reversible (`git show`) y
   no hay datos asociados. Se registra como decisión de código, no de producto.
4. **No se añadió un handler global de 404.** Un handler para `/api/v1/*`
   enmascararía 404 legítimos del núcleo (recurso de otra empresa, id
   inexistente). El 404 estándar no filtra estructura interna.

**Rollback:** `git revert` de los borrados y del `include_router`. Las rutas
vuelven; no se movió ningún dato.

### 6.6 Ola D — Datos (cutover D-2). ✅ Ejecutada (local 2026-11-01)

> **Ejecución local:** `make db-reset` (0001–0027 + seeds) → `cutover_legacy.py --freeze`.
> Solo D.4 tenía filas (**6 pautas**); D.1–D.3 y D.5 tenían **0 filas**. Backup
> `backups/cutover_pre_20261101_115202.sql`; reconciliación Δ=0; segunda corrida 0
> (idempotente). Las sub-olas de abajo quedan como guía para entornos con datos reales.

**Bloqueo duro:** `RET-01` (= **D-2**) sin resolver. El cutover bypassea tablas
del núcleo sin triggers/auditoría y crea tarifas/OC sintéticas `MIG-*`
(`docs/orquestacion/registro.md:824,842`). La recomendación es bypass como
operación de plataforma con 6 verificaciones compensatorias, pero faltan
`D-2.a…e` del dueño.

| Sub-ola | Concepto | Fuente → destino | Clave natural | Bloqueo |
|---|---|---|---|---|
| D.1 | Maestros + viajes abiertos + gastos/archivos | `public.clientes/choferes/tractos/ramplas/viajes/gastos_viaje` → `nucleo.*` | RUT, patente, `(cliente, fecha)` | `RET-11` (tara/capacidad); D-2 |
| D.2 | Facturación y cobranza | `public.facturas/factura_viaje` → `nucleo.facturas_nucleo/factura_viajes` | `numero_sii`/`numero_factura` | `RET-03`, `RET-04`; D-2 |
| D.3 | Nómina | `public.liquidaciones/anticipos_chofer/ajustes_liquidacion` → `nucleo.liquidaciones/anticipos_chofer/ajustes_liquidacion` (`0025`) | `(chofer_id, mes)` | `RET-07`; D-2 |
| D.4 | Mantenimiento | `public.pautas_mantenimiento/mantenimientos` → `nucleo.pautas_mantenimiento/mantenimientos` (`0024`) | `(tracto_id, km)` | `RET-08`; D-2 |
| D.5 | Configuración y KPIs | `public.configuracion` → `nucleo.configuracion_empresa`; `public.kpis` → **destino a decidir** | `clave`, `(nombre, uso)` | `RET-04`, `RET-05`; D-2 |

**Criterios de aceptación por concepto (sin cambios):** conteo y suma
antes/después; 0 huérfanos y 0 duplicados; idempotencia; consulta de
reconciliación con 0 diferencias y salida fechada; `public` congelado durante la
ventana; dry-run en copia.

**Consecuencia de haber hecho C antes que D:** las tablas destino ya reciben
escrituras del núcleo. La importación debe usar claves naturales y `ON CONFLICT`
controlado, y la reconciliación debe correr **después** de la ventana, no antes.

### 6.7 Ola E — Identidad y cierre de esquema. ✅ Ejecutada (local 2026-11-01)

> **Ejecución local:** identidad desde JWT + `nucleo.usuarios_empresa`; trigger
> `on_auth_user_created` y `public.usuarios` retirados (`0028`); gate/middleware y
> `es_legacy` eliminados; `lib/api.ts` borrado; `public` **vacío** (0 tablas). Se
> conservó el schema por `btree_gist`/PostgREST (desviación de E.5 documentada).

| Paso | Qué | Evidencia de cierre | Estado |
|---|---|---|---|
| E.1 | Endpoint de perfil y alta de usuario en `nucleo`; membresía como fuente de rol | Prueba de alta + login sin `public.usuarios` | ⛔ |
| E.2 | Retirar `GET /auth/me`, `deps.py` sobre `public.usuarios` y el trigger `handle_new_user` | `grep` del trigger → 0; `auth-context` apunta al nuevo endpoint | ⛔ |
| E.3 | Archivar historial de `cutover_control` y retirar flag + middleware | Migración de archivo + `main.py` sin middleware | ⛔ |
| E.4 | `grep "public\." backend/app/` → 0; modelos legacy → 0; `api.ts` eliminado | Salida fechada | ⛔ (hoy queda `servicio_cutover.py:97`) |
| E.5 | `DROP SCHEMA public` (o archivo de solo lectura) | **ADR destructivo propio**, backup verificado, restore drill, ventana, autorización dueño+contador | ⛔ |

**Compuerta de entrada a E:** D cerrada, `RET-02` respondida, `RET-09`
autorizada, backup verificado y restore drill archivado.

**Rollback:** restaurar `public` desde backup. Riesgo residual: las altas
ocurridas entre el `DROP` y el restore se pierden; por eso E.1–E.4 se ejecutan en
dual-run antes de E.5.

---

## 7. Bloqueos y autorizaciones (estado rev. 3)

| ID | Decisión / autorización | Estado | Destinatario | Evidencia |
|---|---|---|---|---|
| **RET-01** | **D-2**: aprobar el bypass del cutover con 6 verificaciones y plan de migración | ✅ **Ejecutada de facto en local (2026-11-01)**; pendiente ratificación formal para entornos con datos reales | Dueño + `datos` | `docs/operacion/cutover-ejecutado-2026-11-01.md` |
| **RET-02** | Destino del histórico: archivo de solo lectura, migración completa o `DROP`; plazo N | ⏳ **Abierta para datos reales**: en local el histórico era ficticio y se descartó con backup verificado (Δ=0) | Dueño + contador | `retiro-legacy.md` §7 Q4 |
| **RET-03** | Anulación de facturas: ¿solo NC o se conserva `PATCH estado=anulada`? | 🟡 **Resuelta de facto**: el legacy se retiró, solo queda NC en el núcleo. Falta ratificación del contador | Dueño + contador | `api_facturacion.py`; `f2-ola-c-retiro-routers.md` |
| **RET-04** | Tasa de IVA, crédito fiscal y dueño del parámetro | 🟡 **Parcial**: la tasa vive en `nucleo.configuracion_empresa` y el request ya no la fija (fix 2026-11-01); el crédito fiscal sigue sin modelar (`P-09`) | Contador | `servicio_iva.py`; `f2-fix-iva-config` |
| **RET-05** | ¿El motor de KPIs sobrevive? | 🟡 **Resuelta por retiro de código**: `kpi_engine` se eliminó. Falta que el dueño confirme que no lo quiere de vuelta | Dueño | `f2-ola-c-retiro-routers.md:297` |
| **RET-06** | ¿El tablero debe mostrar `ingresos_mes`/`gastos_mes`? | ⏳ **Abierta**: el tablero no los muestra; si se quieren, es alcance nuevo | Dueño + contador | `schemas.py:1711-1727` |
| **RET-07** | Política de comisión y qué se congela al emitir | ⏳ **Parcial**: la emisión congela montos almacenados (`0025`); la base de comisión (devengado vs cobrado) sigue en `D-01` | Dueño + contador/asesor laboral | `0025`; `docs/negocio/preguntas.md` D-01 |
| **RET-08** | Prioridad y regla de mantenimiento por km | ⏳ **Parcial**: módulo construido; falta validación del taller | Dueño + taller | `0024` |
| **RET-09** | Backup, restore drill, ventana y responsable del `DROP` | ⛔ **ABIERTA** | Dueño + `datos` | `AGENTS.md` §8 |
| **RET-10** | ¿Export/import se reconstruye o se acepta su desaparición? | ⏳ **Parcial**: export reconstruido; **import CSV desapareció** y no está ratificado | Dueño | `api_export.py`; `f2-ola-c-retiro-routers.md:21-31` |
| **RET-11** | Tara, peso bruto y capacidad reales por tracto/rampla | ⛔ **ABIERTA** — bloquea D.1 | Dueño + taller | `0001:72-94` vs `0004:201-203,244` |
| **RET-12** | ¿Se acepta la desviación de secuencia C→D, con migración idempotente y ventana congelada? | ⛔ **ABIERTA** — condiciona D | Dueño + `datos` | §6.5 y §9.10 de este ADR |
| **RET-13** | ¿Se ratifica que el import CSV desaparece y el export se limita a viajes/facturas/liquidaciones? | ⛔ **ABIERTA** | Dueño | `api_export.py`; RET-10 |

**Checklist de operación destructiva (solo E.5):** sin cambios respecto de la
rev. 2 — backup verificado, restore drill, ventana, escrituras legacy en 0,
autorización dueño + contador, revisión independiente, rollback probado, y
prohibición de borrar `_migraciones`, migraciones aplicadas, `auth.users` o el
bucket `respaldos`.

---

## 8. Riesgos estructurales (rev. 3)

### 8.1 Tabla de riesgos

| ID | Riesgo | Evidencia | Impacto | Mitigación / compuerta |
|---|---|---|---|---|
| R1 | **El gate no es retiro.** Hoy no hay negocio legacy, pero el gate sigue siendo la única frontera de acceso y distingue tenants sobre rutas inexistentes (403 vs 404) | `main.py:157-175,217-302`; `test_f2_ola_c_retiro_routers.py` | Medio: un 403/404 puede revelar pertenencia a TEI; no protege datos | E.3; revisión de `auditor-seguridad` |
| R2 | **Identidad global en `public.usuarios`.** `/auth/me`, `deps.py`, el trigger y el seed del segundo tenant | `auth.py:12-28`; `deps.py:15-17`; `0001:248-262`; `seed_segundo_tenant.py:79` | **Crítico**: borrar `public` deja a todos sin login | G0.1; Ola E dual-run |
| R3 | **Lectura cruzada `nucleo → public.viajes`.** Única lectura del backend, vigilada por prueba | `servicio_cutover.py:97`; `test_f1_ola5_dos_engines.py` | Alto: `DROP public.viajes` rompe `/nucleo/cutover/estado` | Mover el conteo a `nucleo` o archivar; G0.2 |
| R4 | **IVA con dos fuentes dentro del núcleo.** El módulo lee la config; el comprobante acepta la tasa del request | `servicio_iva.py:44-51`; `schemas.py:1543`; `servicio_facturacion.py:544` | **Crítico (tributario)**: dos documentos pueden usar tasas distintas | RET-04: la tasa debe venir del servidor, no del JSON |
| R5 | **Escritores residuales en scripts.** Seeds y cutover siguen tocando `public` | `seed_local.py:198,235,270,305,337`; `seed_segundo_tenant.py:79`; `cutover_legacy.py:110-351` | Medio: un seed mal apuntado escribe histórico | D/E: seeds solo a `nucleo`; cutover con ventana y dry-run |
| R6 | **E2E actualizado pero sin última pasada registrada.** El spec ya cubre Olas A/B/C (20 pruebas), pero no hay salida fechada posterior a B/C | `frontend/e2e/tei.spec.ts` (20 `test()`); tarea de `qa` pendiente | Medio: verde no evidenciado; el riesgo de regresión queda abierto | `qa`: ejecutar `make e2e` y archivar la salida |
| R7 | **308 permanentes.** Un navegador que cacheó la redirección no vuelve a consultar la URL legacy | `docs/frontend/f2-ola-a-retiro.md` | Medio: rollback de UI no inmediato | Documentado; no revertir salvo incidente |
| R8 | **`public` no está aislado por RLS.** Una política (`usuarios`) y rol legacy con bypass | `0001_esquema_base.sql`; `database.py` | Alto si se evade el gate | No confiar en RLS para `public`; retirar el esquema en E |
| R9 | **Volúmenes desconocidos.** No hay conteo/suma de `public`; el seed no representa producción | `retiro-legacy.md` §5 | Alto: C3 no se cierra con honestidad | Ola 0: censo en copia |
| R10 | **El cutover no migra el histórico.** Solo abiertos, forzados `confirmado`, sin gastos/facturas/nómina/mantenimiento | `cutover_legacy.py:15,283,383` | **Crítico**: pérdida de estado y de dinero emitido | Ola D por concepto; RET-01/02 |
| R11 | **Deriva documental.** `estado.md`, `modulos.md`, `deuda.md`, `catalogo-reglas.md`, `seguridad/**` y `qa/**` citan archivos borrados o cifras previas | §8.2 | Medio: decisiones sobre datos falsos | Cada dueño corrige su carpeta; este ADR no reescribe historia ajena |
| R12 | **`modulos_empresa` no gobierna el legacy.** No hay kill-switch por módulo; el corte real fue borrar routers | `0023_modulos_empresa.sql` | Bajo ahora: ya no hay rutas legacy | No introducirlo sin problema demostrado |
| **R13** | **Migraciones `0024`–`0026` untracked.** Un clon de `HEAD` no reproduce el esquema de la Ola B | `docs/datos/catalogo-migraciones.md:205-207` | **Crítico de despliegue**: CI/entorno nuevo falla o queda sin tablas | `orquestador`: commit de las 26 migraciones; verificar `git ls-tree HEAD` |
| **R14** | **Totales de dinero del dashboard retirados sin reemplazo.** `TableroKpisOut` no tiene ingresos/gastos del mes | `schemas.py:1711-1727`; `grep` frontend → 0 | Medio: el dueño perdió una vista que usaba | RET-06: decisión de producto, no regresión silenciosa |
| **R15** | **Oráculo del congelamiento.** Con el flag activo, TEI recibe 409 y TES 403 sobre una ruta inexistente; sin el flag, 404 | `main.py:326-351` | Bajo: revela estado global | Revisión de `auditor-seguridad`; E.3 lo elimina |

### 8.2 Documentos que citan archivos borrados (handoff de corrección)

Ninguno de estos documentos es una fuente de verdad; se listan para que su dueño
los corrija o les ponga aviso de vigencia. **No se reescribe la historia de los
informes fechados**: se les añade cabecera de "archivo citado retirado".

| Documento | Qué cita (borrado o inválido) | Dueño que debe corregirlo | Acción |
|---|---|---|---|
| `docs/estado.md` | 23 migraciones, 40 tablas, 27 routers (12 legacy), 9 E2E, 100/388/135 pruebas, módulos legacy "en uso", `routes/*` y `kpi_engine` | `orquestador` | Reescribir §1–§3 y §6; es el único autorizado a cifras volátiles |
| `docs/seguridad/hallazgos.md` | `routes/liquidaciones.py`, `routes/viajes.py`, `routes/facturas.py`, `routes/export.py`, `test_reglas_negocio.py` | `auditor-seguridad` | Aviso de archivo retirado + revalidar SEC-002/SEC-010 contra el núcleo |
| `docs/seguridad/f1-ola2-revalidacion.md`, `f1-ola2-1-revalidacion.md` | `routes/export.py`, `routes/gastos.py` | `auditor-seguridad` | Aviso de informe histórico; no reescribir |
| `docs/qa/matriz-trazabilidad.md` | R-01 sobre `liquidaciones.py`; `test_reglas_negocio.py`; `test_flujos_criticos.py` (borrados) | `qa` | Re-mapear R-01 a `0025`/`servicio_nomina.py`; R-02 ya está en `test_r02_licencia_nucleo.py` |
| `docs/qa/linea-base.md` | `test_kpi_engine.py`, `test_reglas_negocio.py`, conteos 52/67 | `qa` | Aviso + nueva línea base 128/405 |
| `docs/qa/informes/f0-*.md`, `f1-*.md` | `routes/*`, `kpi_engine.py`, `test_reglas_negocio.py` | `qa` | Aviso "informe histórico: archivos citados ya no existen"; no reescribir |
| `docs/negocio/catalogo-reglas.md` | R-01 y demás reglas con fuente en `routes/liquidaciones.py`, `routes/mantenimiento.py`, `routes/configuracion.py`, `routes/export.py` | `negocio-finanzas` | Re-apuntar la fuente a `servicio_nomina.py`, `servicio_mantenimiento.py`, `servicio_configuracion.py`, `servicio_export.py`; declarar qué reglas cambiaron de base |
| `docs/negocio/implementacion.md`, `contexto.md`, `kpis.md`, `preguntas.md` | `routes/liquidaciones.py`, `routes/viajes.py`, `routes/facturas.py`, `routes/dashboard.py` | `negocio-finanzas` | Re-apuntar y marcar `D-01`/`P-09` como abiertas |
| `docs/backend/contratos/liquidaciones-comision-r01.md` | `routes/liquidaciones.py` (ya tiene aviso) | `backend` | Completar el re-mapeo a `servicio_nomina.py` |
| `docs/datos/invariantes.md` | `api/routes/gastos.py` (borrado) | `datos` | Re-apuntar a `servicio_gastos.py`/`api_gastos.py` |
| `docs/mapa-sistema.md` | `lib/api.ts` como cliente vigente; esquema legacy | `arquitectura` | Actualizar §1 y la tabla de clientes |
| `docs/arquitectura/modulos.md` | 12 routers legacy, 13 pantallas legacy, `api.ts` (rev. 2026-10-29) | `arquitectura` | Aviso de superado por este ADR + `retiro-legacy.md` rev. 3 |
| `docs/arquitectura/deuda.md` | D-01/D-04/D-06/D-09/D-15/D-16 citan `routes/*` y `kpi_engine` | `arquitectura` | Aviso + revisión de las filas que ya no aplican |
| `docs/arquitectura/matriz-plan-vs-codigo.md` | `routes/viajes.py`, `routes/gastos.py`, `routes/facturas.py`, `routes/liquidaciones.py`, `routes/mantenimiento.py` | `arquitectura` | Re-apuntar a los servicios del núcleo; las filas "solo legacy" ya no tienen escritor |
| `docs/arquitectura/destino-modular.md` | `viajes.py:152-253`, `gastos.py:55`, `facturas.py:101-241` como escritores | `arquitectura` | Actualizar el reparto de escrituras (hoy todas en `nucleo`) |
| `docs/arquitectura/alcance-piloto.md` | D-01 "los 4 módulos sin equivalente siguen en legacy" | `arquitectura` | Aviso de superado (ya aplicado en la cabecera); revisar P0 |
| `docs/desarrollo/guia.md` | `lib/api.ts` como cliente legacy vigente | `orquestador` | Actualizar tabla de capas |
| `docs/orquestacion/registro.md` | `routes/*` en hechos de fases anteriores | `orquestador` | No reescribir; añadir entrada de Olas B/C con enlaces |
| `docs/frontend/f2-tenant2-navegacion.md` | `lib/api.ts`, 12 pantallas legacy, 13 del núcleo | `frontend` | Aviso de superado por Olas A/B |
| `docs/PLAN_DESARROLLO.md`, `docs/_archivo/**` | `api.ts`, routers legacy | — | Histórico: no citar como estado |

---

## 9. Criterios de aceptación globales

1. Por módulo, registro fechado con la salida de **C1, C2 y C3**; sin esa salida
   no se declara retirable. **Hoy: C2 cerrada en los 11 routers y 13 pantallas;
   C1 parcial; C3 abierta.**
2. Ninguna fila de `public` se borra en las olas A–C. ✅ Cumplido.
3. `grep -rn "public\." backend/app/` → 0 **antes** de cualquier `DROP`.
   **Hoy: 1** (`servicio_cutover.py:97`).
4. Toda pantalla retirada tiene redirección o ítem eliminado; ninguna deja
   404/500. ✅ Cumplido (9 × 308).
5. `make unit`, `make test` y `make e2e` verdes después de cada ola, con salida
   registrada; un `skip` no cuenta. **Parcial:** unit 128 y test 405 reportados
   (🟡); **E2E actualizado a 20 pruebas pero sin última pasada registrada**.
6. Los tests legacy se reescribieron contra `nucleo`; no se borraron para que
   pasaran. ✅ Cumplido (R-02 conservada).
7. El E2E deja de depender de `/dashboard` y del flag. ⏳ Parcial: `/dashboard`
   corregido; la dependencia del menú legacy sigue (R6).
8. Las pruebas del gate siguen pasando sin cambios. **Corregido:** el mecanismo
   no cambió; 2 pruebas HTTP se adaptaron a 404 porque la ruta dejó de existir.
   Lo exigible es que TES reciba 403 **antes** del enrutado.
9. Al cerrar la última ola, no queda ninguna fila con compuertas abiertas o cada
   una está marcada con su `RET-*`.
10. **Nuevo:** la secuencia C→D se declara desviación aceptada, con la obligación
    de que la migración de D sea idempotente y con ventana congelada.

---

## 10. Rollback

| Escenario | Acción | Efecto | Riesgo residual |
|---|---|---|---|
| Una pantalla de la Ola A hace falta | `git revert` del commit de Ola A | Vuelve la pantalla | 308 cacheado |
| Una pantalla de la Ola B no alcanza paridad | Revertir la pantalla y usar el legacy... **que ya no existe** | Obliga a corregir el núcleo | Alto: la Ola C eliminó la red de seguridad; por eso D es la prioridad |
| Un router desmontado hace falta | `git revert` de los borrados y del `include_router` | La ruta vuelve | Ninguno: no se movieron datos |
| La importación de D resulta incorrecta | Restaurar la copia usada en la migración; la base productiva no se tocó en el ensayo | Vuelve el estado previo | Se pierde lo escrito en `nucleo` desde la migración |
| G0 mal ejecutado (identidad) | Restaurar `public.usuarios` desde backup | El login vuelve | Altas de la ventana se pierden |
| `DROP` ejecutado por error | Restaurar backup completo + restore drill | Vuelve `public` | Pérdida de escrituras posteriores; incidente |

**Advertencia nueva:** la Ola C eliminó el legacy **antes** de que D migrara los
datos. Si aparece un caso de negocio que solo el legacy resolvía, ya no hay
pantalla ni API a la que volver; solo queda el código en git y los datos en
`public`. Esto eleva la prioridad de D y de la consulta de reconciliación.

---

## 11. Preguntas abiertas

| ID | Pregunta | Destinatario | Estado |
|---|---|---|---|
| RET-01 | ¿Se aprueba el bypass del cutover con las 6 verificaciones (D-2.a…e)? | Dueño + `datos` | ⛔ Abierta |
| RET-02 | ¿El histórico se conserva como archivo, se migra completo o se destruye? ¿Plazo? | Dueño + contador | ⛔ Abierta |
| RET-03 | ¿La anulación de facturas se hace solo con nota de crédito? | Dueño + contador | 🟡 De facto (NC); ratificar |
| RET-04 | ¿Tasa de IVA, crédito fiscal y dueño del parámetro? | Contador | ⏳ Parcial |
| RET-05 | ¿El motor de KPIs por fórmula sobrevive? | Dueño | 🟡 Retirado; ratificar |
| RET-06 | ¿El tablero debe mostrar los totales de dinero del dashboard legacy? | Dueño + contador | ⏳ Abierta (hoy no los muestra) |
| RET-07 | ¿Comisión devengada al finalizar, facturar o cobrar? ¿Qué se congela al emitir? | Dueño + contador/asesor laboral | ⏳ Parcial |
| RET-08 | ¿Se valida la regla de mantenimiento por km con el taller? | Dueño + taller | ⏳ Parcial |
| RET-09 | ¿Quién autoriza el `DROP`, con qué backup y en qué ventana? | Dueño + `datos` | ⛔ Abierta |
| RET-10 | ¿El import CSV se reconstruye o se acepta su desaparición? | Dueño | ⏳ Parcial |
| RET-11 | ¿Tara, peso bruto y capacidad reales por tracto/rampla? | Dueño + taller | ⛔ Abierta |

**Preguntas nuevas de cierre:**

- **RET-12:** ¿Se acepta que la Ola C se ejecutara antes de la Ola D, con la
  obligación de migración idempotente y ventana congelada? (Dueño + `datos`.)
- **RET-13:** ¿Se ratifica que el import CSV legacy desaparece y que el export se
  limita a viajes, facturas y liquidaciones? (Dueño.)

---

## 12. Historial de revisiones

| Rev. | Fecha | Cambio | Evidencia |
|---|---|---|---|
| 1 | 2026-10-29 | Plan inicial por 10 olas y 4 puertas (P1–P4) | Lectura estática |
| 2 | 2026-10-31 | Se registra la Ola A ejecutada; se reemplazan P1–P4 por C1–C3 + G0; se separa código (A–C) de datos (D) y cierre (E); se renombran las decisiones a `RET-*` | Este documento |
| 3 | 2026-10-31 | **Cierre de la transición de código:** A, B y C ejecutadas y verificadas; se actualiza la superficie (1 router legacy, 0 pantallas legacy, 20 routers de módulo, 46 tablas/51 políticas); se declara lo que **no** se retiró y por qué; se actualizan compuertas, riesgos (R13–R15), secuencia (desviación C→D) y estado de `RET-*`; se añade §8.2 con documentos que citan archivos borrados | `router.py:24-39`; `api/routes/`; `nucleo/router.py:14-23`; `navigation.ts:37-85`; `0024`–`0026`; informes de las olas |
