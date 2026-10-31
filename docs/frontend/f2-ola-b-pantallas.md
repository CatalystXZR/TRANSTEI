# Fase 2 — Ola B del retiro legacy: pantallas del núcleo (mantenimiento, liquidaciones, IVA y configuración)

**Fecha:** 2026-10-31 · **Agente:** `frontend` · **Riesgo:** Alto (nómina,
IVA y configuración por empresa).
**Método:** lectura de contrato (`docs/backend/contratos/ola-b-modulos-nucleo.md`),
código de los servicios/routers de la Ola B, `openapi.json` del backend en
`:8000`, `tsc`, `eslint`, `next build`, smoke HTTP de las rutas de página y
`grep` de imports. **No se ejecutó un flujo autenticado** (sin credenciales ni
seed disponibles en la sesión); se declara en §7.

---

## 1. Resultado

Las cuatro rutas dejaron de consumir el cliente legacy `lib/api.ts` y ahora usan
`lib/nucleo.ts` (`/api/v1/nucleo`, JWT + `X-Empresa-ID`). Se mantienen las mismas
URLs de pantalla y cambia la fuente de datos, no la navegación del usuario.

| Ruta | Pantalla | Cliente | Endpoints usados |
|---|---|---|---|
| `/mantenimiento` | Pautas, estado/semáforo e historial | `lib/nucleo.ts` | `GET/POST /nucleo/mantenimiento/pautas`; `GET/POST /nucleo/mantenimiento/mantenimientos`; `POST /nucleo/mantenimiento/mantenimientos/{id}/anular`; `GET /nucleo/mantenimiento/estado`; `GET /nucleo/tractos`; `GET /nucleo/ramplas` |
| `/liquidaciones` | Borradores, emisión, anulación, anticipos y ajustes | `lib/nucleo.ts` | `GET/POST /nucleo/liquidaciones`; `POST /nucleo/liquidaciones/{id}/emitir`; `POST /nucleo/liquidaciones/{id}/anular`; `GET/POST /nucleo/anticipos`; `GET/POST /nucleo/ajustes`; `GET /nucleo/choferes`; `GET /nucleo/export/liquidaciones` |
| `/iva` | Resumen de IVA débito por rango | `lib/nucleo.ts` | `GET /nucleo/iva/resumen?desde=&hasta=` |
| `/configuracion` | Valores vigentes por empresa | `lib/nucleo.ts` | `GET /nucleo/configuracion`; `PUT /nucleo/configuracion/{clave}` |

La empresa y los permisos se resuelven con `useNucleoEmpresa()`
(`frontend/src/lib/use-nucleo-empresa.ts:20-65`): `GET /nucleo/mis-empresas` y
`GET /nucleo/permisos/mios`. Los permisos sólo guían la UI; cada endpoint vuelve
a autorizar en el backend.

Los tipos nuevos están en `frontend/src/types/nucleo.ts:1180-1360` (sin `any`).
La descarga CSV usa `descargarNucleo()` en `frontend/src/lib/nucleo.ts:113-160`,
que reutiliza el JWT y `X-Empresa-ID` del cliente del núcleo.

---

## 2. Contrato usado (resumen fiel al backend)

### 2.1 Mantenimiento

- Pautas: `PautaMantenimientoOut` con `recurso_tipo`, `item`, `intervalo_km`,
  `intervalo_meses`, `alerta_km`, `orden`, `activo`, `version`,
  `created_at`, `updated_at`. El alta usa `PautaMantenimientoCreate` con
  `extra="forbid"`. No hay `PUT` ni `DELETE`: la UI **no** ofrece editar ni borrar.
- Mantenimientos: alta con `pauta_id`, exactamente uno de `tracto_id`/`rampla_id`,
  `fecha`, `km`, `costo`, `observaciones`. La anulación es
  `POST …/{id}/anular` con `{motivo}` (3–500). El histórico no se borra.
- Estado: `EstadoMantenimientoOut[]` leído de `nucleo.v_mantenimiento_estado`,
  con `estado` ∈ `sin_registro|sin_odometro|pendiente|por_vencer|ok`,
  `proximo_km`, `restante_km`, snapshots de intervalo y alerta. El semáforo se
  muestra tal como lo entrega el servidor; el cliente no lo recalcula.
- Errores usados: 401/403, 404 recurso/pauta, 409 pauta inactiva o duplicada,
  422 validación (p. ej. `km < 0`, `respaldo_url` inválido).

### 2.2 Liquidaciones

- Listado `GET /nucleo/liquidaciones?mes=YYYY-MM&chofer_id=&estado=` devuelve
  `LiquidacionOut[]` con montos **almacenados** y `chofer_nombre`.
- Alta `POST /nucleo/liquidaciones` con `{chofer_id, mes, sueldo_base?, notas?}`.
  El borrador calcula comisión, bonos/descuentos y anticipos en el servidor. La
  UI sólo envía los campos del contrato.
- Emisión `POST /nucleo/liquidaciones/{id}/emitir` es idempotente: el botón se
  bloquea durante la petición, pero reintentar no vuelve a imputar anticipos.
- Anulación `POST /nucleo/liquidaciones/{id}/anular` con `{motivo}` (3–500). El
  diálogo exige el motivo y muestra el error del servidor si el estado cambió.
- Anticipos: `GET/POST /nucleo/anticipos` (no hay `DELETE` en el contrato, la UI
  no lo ofrece). Ajustes: `GET/POST /nucleo/ajustes`.
- El documento emitido se muestra con aviso de que no se recalcula; los botones
  de anticipo/ajuste sólo se habilitan para borradores. Es una guía de UI, no una
  regla de autorización.
- Errores usados: 404 chofer, 409 `REGISTRO_DUPLICADO` (chofer+mes, incluida la
  limitación de `0025` tras anular), 409 de estado en carrera, 422 de mes/montos.

### 2.3 IVA

- `GET /nucleo/iva/resumen?desde=YYYY-MM-DD&hasta=YYYY-MM-DD` devuelve
  `{desde, hasta, tasa_iva, facturas, base_neta, iva_debito, advertencia}`.
- **Sólo débito.** La pantalla deja explícito que crédito fiscal, monto a pagar,
  remanente y notas de crédito dependen de `P-09` y no se muestran. Si
  `tasa_iva` es `null`, se muestra "no configurada"; no se hardcodea 19 %.
- `desde > hasta` se valida en el cliente como ayuda y también la valida el
  backend (422). No se usa `new Date("YYYY-MM-DD")` para la lógica de fechas.

### 2.4 Configuración

- `GET /nucleo/configuracion` devuelve `{items: ConfiguracionItemOut[], mensaje}`
  con las filas vigentes (`vigente_hasta IS NULL`).
- `PUT /nucleo/configuracion/{clave}` recibe `{valor}` en JSON. El catálogo y el
  rango se validan en el servidor:
  `iva_porcentaje` 0–100, alertas enteras ≥ 0.
- La UI valida `iva_porcentaje` entre 0 y 100 y los enteros; además muestra el
  mensaje del backend (422/409) sin perder lo digitado. El error de campo se
  asocia con `aria-describedby` y `aria-invalid`.
- Se muestra `vigente_desde`, `updated_at` y `version`; se advierte que el
  historial es append-only y que no hay endpoint de historial en esta ola.

---

## 3. Permisos y multiempresa

| Acción | Permiso comprobado en UI | Fuente |
|---|---|---|
| Ver mantenimiento | `mantenimiento:leer` (implícito al cargar) | `frontend/src/app/(app)/mantenimiento/page.tsx:145` |
| Crear pauta / registrar / anular mantención | `mantenimiento:escribir` | `…/mantenimiento/page.tsx:145,436,612,643,762` |
| Ver liquidaciones | `liquidaciones:leer` (implícito al cargar) | `…/liquidaciones/page.tsx:94` |
| Crear borrador / emitir / anular / anticipos / ajustes | `liquidaciones:escribir` | `…/liquidaciones/page.tsx:94,503,612,621,808` |
| Ver IVA | `iva:leer` (implícito al cargar) | `…/iva/page.tsx:73` |
| Editar configuración | `configuracion:escribir` | `…/configuracion/page.tsx:108,341,371` |

- `X-Empresa-ID` lo agrega `lib/nucleo.ts`; ninguna pantalla lo envía a mano.
- Un 403 se renderiza con `ErrorNucleo`
  (`frontend/src/components/nucleo/estado-error.tsx:11-27`) como **"Sin
  permiso"**; además, cuando hay error de carga se oculta el contenido para no
  confundirlo con un estado vacío (`bloqueado` en cada pantalla).
- La navegación sigue usando `usuario.rol` para decidir qué ítems mostrar
  (`frontend/src/lib/navigation.ts:115`). Ese rol es del legacy y no sustituye
  al rol de la empresa del núcleo; el backend es la autoridad.

---

## 4. Matriz de estados

| Estado | Mantenimiento | Liquidaciones | IVA | Configuración |
|---|---|---|---|---|
| Carga | skeletons de flota + `FilasCargando` | `FilasCargando` y contadores a cero | `StatTileSkeleton` | `Skeleton` por fila |
| Vacío | "Sin estado de mantenimiento" / pauta vacía / sin historial | "Sin liquidaciones en el período" | "No hay facturas no anuladas…" | Catálogo con "Sin valor vigente" |
| Error de red / 5xx | `ErrorNucleo` rojo | `ErrorNucleo` rojo | `ErrorNucleo` rojo | `ErrorNucleo` rojo |
| 403 | `ErrorNucleo` con **Sin permiso** y contenido oculto | ídem | ídem | ídem |
| 401 | Mensaje de sesión del cliente; `(app)/layout` redirige a login | ídem | ídem | ídem |
| Error de dominio | inline + toast (409 pauta, 422 km/motivo) | inline + toast (409 duplicado/estado, 422) | mensaje del backend | inline por campo + toast (422/409) |
| Éxito | toast + recarga silenciosa | toast + recarga + detalle actualizado | datos actualizados | valor y versión actualizados |
| Doble envío | botón `disabled` por `guardando*` | botón `disabled` por `procesando` | n/a | botón `disabled` por `guardando` |

---

## 5. Navegación

`frontend/src/lib/navigation.ts`:

- Los cuatro ítems quedaron con `legacy: false`
  (`:61,75,76,91`). No existía un grupo llamado "Legacy": el legacy estaba
  marcado por el flag `legacy` dentro de los grupos de dominio; se dejó todo el
  menú en el núcleo.
- `RUTAS_LEGACY` se deriva de los flags (`:103`) y ahora queda **vacía**;
  `esRutaLegacy()` (`:106-108`) sigue funcionando y devuelve `false`, por lo que
  el gate de `(app)/layout.tsx` no bloquea estas cuatro rutas. `gruposParaRol`
  (`:115-122`) sigue filtrando por `esLegacy` sin errores.
- No se borró `lib/api.ts` (Ola C). Tras el cambio, **ninguna pantalla** lo
  importa; sólo queda el import en
  `frontend/src/components/importar-csv.tsx:6`, un componente que no tiene
  consumidores (`grep -rn "importar-csv\\|ImportarCSV" src` → sin resultados).

---

## 6. Verificación ejecutada

```text
$ cd frontend && npx tsc --noEmit
(sin salida → 0 errores)

$ npm run lint
> frontend@0.1.0 lint
> eslint
(sin salida → 0 errores)

$ npm run build
▲ Next.js 16.4.3 (Turbopack)
✓ Compiled successfully in 366ms
✓ Running TypeScript ...
✓ Generating static pages using 7 workers (30/30)
Rutas presentes: /mantenimiento /liquidaciones /iva /configuracion
```

Contrato vivo en el backend local (`GET /openapi.json`, 2026-10-31):

```text
/api/v1/nucleo/mantenimiento/pautas ['GET','POST']
/api/v1/nucleo/mantenimiento/mantenimientos ['GET','POST']
/api/v1/nucleo/mantenimiento/mantenimientos/{mantenimiento_id}/anular ['POST']
/api/v1/nucleo/mantenimiento/estado ['GET']
/api/v1/nucleo/liquidaciones ['GET','POST']
/api/v1/nucleo/liquidaciones/{liquidacion_id}/emitir ['POST']
/api/v1/nucleo/liquidaciones/{liquidacion_id}/anular ['POST']
/api/v1/nucleo/anticipos ['GET','POST']
/api/v1/nucleo/ajustes ['GET','POST']
/api/v1/nucleo/iva/resumen ['GET']
/api/v1/nucleo/configuracion ['GET']
/api/v1/nucleo/configuracion/{clave} ['GET','PUT']
/api/v1/nucleo/export/liquidaciones ['GET']
```

Sin JWT, con `X-Empresa-ID` de prueba, los endpoints responden 401 (no 404):

```text
401 /api/v1/nucleo/mantenimiento/pautas
401 /api/v1/nucleo/liquidaciones?mes=2026-10
401 /api/v1/nucleo/iva/resumen?desde=2026-10-01&hasta=2026-10-31
401 /api/v1/nucleo/configuracion
```

Smoke de páginas contra `next dev` (`:3000`, sin sesión; el contenido se monta
tras el gate de auth):

```text
200 /mantenimiento   200 /liquidaciones   200 /iva   200 /configuracion
```

`grep` de imports legacy en `frontend/src`:

```text
$ grep -rn 'from "@/lib/api"' src
src/components/importar-csv.tsx:6:import { apiUpload } from "@/lib/api";
```

---

## 7. Accesibilidad

- Todos los inputs de formulario tienen `label` (`Campo`/`htmlFor`); los errores
  visibles usan `role="alert"`. En configuración el error se enlaza con
  `aria-describedby` y `aria-invalid` (`configuracion/page.tsx:341-345,390`).
- Los diálogos usan el componente `Dialog` de base-ui (foco atrapado, cierre con
  Esc y `DialogTitle`).
- No hay `div` clicables: las acciones son `Button`; los paneles de estado son
  informativos y los botones "Registrar" son explícitos.
- Los estados no dependen sólo del color: `StatusBadge` incluye texto
  ("Vencido", "Por vencer", "Anulada", etc.).
- Las tablas conservan encabezados y `sr-only` para acciones; las cargas usan
  `FilasCargando`/skeletons con texto visible.
- No se agregó `dangerouslySetInnerHTML` ni `any` nuevo.

---

## 8. Handoff

### A `qa` (E2E, `frontend/e2e/` es de `qa`)

1. **Mantenimiento**: con rol `admin`/`gerente`/`despacho`/`taller`, crear pauta
   (tracto y rampla), registrar mantención con `km` igual al odómetro y verificar
   que el semáforo cambia; anular con motivo y comprobar que el registro sigue en
   el historial. Probar `km` menor al odómetro → error del servidor.
2. **Liquidaciones**: crear borrador de un chofer/mes libre, emitir, reintentar
   emitir (idempotente) y anular con motivo. Verificar 409 al repetir
   chofer+mes. Con rol `auditor`/`tesoreria`, confirmar que no aparecen acciones
   de escritura y que un 403 se muestra como "Sin permiso".
3. **IVA**: rango con facturas, rango sin facturas y `desde > hasta`. Verificar
   que no existe crédito/a pagar y que `tasa_iva` nula se muestra "no
   configurada". Cambiar `iva_porcentaje` en Configuración y comprobar el nuevo
   valor en el resumen.
4. **Configuración**: editar `iva_porcentaje` fuera de 0–100 (error de cliente),
   valor válido (200, nueva versión) y dos ediciones simultáneas (409
   `CONFLICTO_CONCURRENCIA`). Confirmar que se muestran `vigente_desde` y
   `version`.
5. **Navegación**: un admin TEI ya no ve ítems legacy; `es_legacy === false` no
   redirige estas cuatro rutas a `/despacho`. Regresión de `/permisos`,
   `/auditoria` y `/tablero`.
6. **Export**: `GET /nucleo/export/liquidaciones?mes=…` descarga CSV con BOM,
   separador `;` y sin recálculo.

### A `auditor-seguridad`

- Confirmar que ningún endpoint de las cuatro pantallas se llama sin
  `X-Empresa-ID` (el cliente lo agrega en `lib/nucleo.ts:25-35`).
- Revisar que los botones ocultos por rol no son la única defensa: los
  endpoints exigen `mantenimiento:escribir`, `liquidaciones:escribir`,
  `iva:leer` y `configuracion:escribir`.
- Verificar que el export CSV no construye URLs de storage y que no se expone
  ningún token en logs/consola.

---

## 9. Riesgos y no verificado

| Nivel | Punto |
|---|---|
| 🔴 | **No se ejecutó un flujo autenticado real** (sin credenciales ni seed en la sesión). La evidencia es `tsc`/lint/build, `openapi.json`, 401 de los endpoints y 200 de las páginas sin sesión. |
| 🟡 | No se probó visualmente el render con datos reales; los estados vacío/error están implementados pero no ejercitados en navegador. |
| 🟡 | `lib/api.ts` sigue existiendo y tiene un import en `components/importar-csv.tsx`, componente sin consumidores. No se borró por indicación de Ola C. |
| 🟡 | La navegación sigue filtrando por `usuario.rol` legacy, no por el rol de la empresa del núcleo. No se cambió porque el alcance era retirar el flag legacy; el backend sigue siendo la autoridad. |
| 🟡 | El contrato `0025` no permite crear un documento nuevo para un chofer+mes ya anulado (`UNIQUE` no parcial). La UI muestra el 409 del servidor; la corrección es de `datos`. |
| 🟡 | No hay `DELETE` de anticipos/ajustes en el contrato del núcleo; la UI no ofrece ese botón (el legacy sí lo tenía). |
| 🟡 | `POST /nucleo/liquidaciones/{id}/anular` repetido con el mismo motivo es idempotente; con otro motivo responde 409. La UI no compara motivos, sólo muestra el error. |
| 🟡 | El resumen de IVA es sólo débito y no descuenta notas de crédito (`P-09`); la pantalla lo declara explícitamente. |
