# Mapa del sistema — ERP Transportes TEI

> **Pregunta que responde:** ¿cómo se conecta todo y dónde vive cada cosa?
> **Dueño:** `orquestador` · **Verificado:** 2026-10-29 · **Método:** lectura estática
> **Caduca si:** se agrega un router, una pantalla, una tabla o un cliente HTTP.
> **Re-verificar con:** `grep -c include_router backend/app/api/router.py && find frontend/src/app -name page.tsx | wc -l`

---

## 1. Vista de 30 segundos

```
Navegador
   │
   ├── frontend/src/lib/api.ts       → /api/v1/*          (LEGACY, schema public)
   └── frontend/src/lib/nucleo.ts    → /api/v1/nucleo/*   (NÚCLEO, schema nucleo)
                 │
        FastAPI (backend/app)
                 │
        ├── app/api/routes/          → 12 routers legacy
        └── app/nucleo/              → 13 routers núcleo
                 │
        PostgreSQL
                 ├── public   (legacy, sin empresa_id, en uso)
                 └── nucleo   (destino, multiempresa, 31 tablas)
```

🟢 Verificado: 25 `include_router` en `backend/app/api/router.py`; 28 `page.tsx`; 2 clientes HTTP; 2 schemas.

---

## 2. Las dos capas

| | `public` (legacy) | `nucleo` (destino) |
|---|---|---|
| Migraciones | `0001`–`0003` | `0004`–`0019` |
| Routers | `backend/app/api/routes/` | `backend/app/nucleo/api_*.py` |
| Cliente HTTP | `frontend/src/lib/api.ts` | `frontend/src/lib/nucleo.ts` |
| Multiempresa | **No** | Sí (`empresa_id` + `X-Empresa-ID`) |
| Auditoría | No | `nucleo.auditoria` (append-only por trigger) |
| Estado | En uso, no se retira sin cutover | En construcción, cubre el piloto |

**Regla:** no se introduce una tercera fuente de verdad. Cada concepto tiene un esquema canónico declarado en [`arquitectura/fuentes-de-verdad.md`](arquitectura/fuentes-de-verdad.md).

---

## 3. Dónde vive cada pieza

| Pieza | Ruta |
|---|---|
| Entrada del backend | `backend/app/main.py` |
| Agregador de routers | `backend/app/api/router.py` |
| Auth (JWT Supabase) | `backend/app/core/` |
| Reglas del legacy | `backend/app/api/routes/` |
| Reglas del núcleo | `backend/app/nucleo/servicio_*.py` + `politicas.py` |
| Permisos del núcleo | `backend/app/nucleo/permisos.py` (8 roles) |
| Motor de KPIs | `backend/app/services/kpi_engine.py` |
| Tarifas y Freight Score | `backend/app/nucleo/tarifas.py`, `servicio_rentabilidad.py` |
| Componentes UI | `frontend/src/app/(app)/` (25 pantallas) |
| PWA del conductor | `frontend/src/app/conductor/` |
| Navegación / menú | `frontend/src/lib/navigation.ts` |
| Migraciones | `supabase/migrations/0001`–`0019` |
| Scripts operativos | `scripts/` (seed, cutover, backup, restore) |
| Pruebas backend | `backend/tests/` (22 archivos: 21 módulos + `conftest.py`) |
| E2E | `frontend/e2e/tei.spec.ts` (9 tests) |

---

## 4. Flujo canónico: crear un viaje en el núcleo

```
/despacho (pantalla)
  → nucleo.ts (cliente tipado)
  → POST /api/v1/nucleo/viajes
  → deps.py  (empresa desde X-Empresa-ID + membresía)
  → permisos.py (rol autorizado)
  → servicio_disponibilidad.py
  → nucleo.viajes + nucleo.reservas_recurso
  → trigger fn_viaje_reservas → EXCLUDE USING gist (tracto/rampla/chofer)
  → trigger fn_viaje_documentos (0015) → documentos vigentes
  → trigger fn_viaje_licencia_a5 (0016) → licencia A5
  → nucleo.auditoria (append-only)
```

Cada eslabón puede fallar y **la base es la última línea**: las tres garantías
duras están en PostgreSQL, no en el servicio ni en la UI.

---

## 5. Autenticación y tenant

| Aspecto | Implementación |
|---|---|
| Emisor del token | Supabase Auth |
| Validación | Backend contra JWKS (`RS256`/`ES256`, audiencia `authenticated`) |
| Empresa | Cabecera `X-Empresa-ID` + membresía en `nucleo.usuarios_empresa` |
| **Nunca** | `empresa_id` del body |
| Roles | 8 roles de empresa (`nucleo/permisos.py`) |
| Legacy | 3 roles (`admin`, `operacion`, `contabilidad`), **sin** filtro por empresa |

⚠️ El legacy **no es multiempresa**. No lo presentes como aislado.

---

## 6. Convenciones del repo

- Migraciones **forward-only** con numeración consecutiva; nunca se edita una aplicada.
- Dinero en `numeric`, jamás `float`; eventos en `timestamptz` (UTC en BD).
- Rangos del núcleo **semiabiertos** `[inicio, fin)`.
- Errores PostgreSQL → HTTP: `23505`/`23P01` → 409; `23514`/`23502` → 422.
- Un solo dueño por archivo; sin escrituras concurrentes.

---

## 7. Dónde NO buscar

| Si buscás… | No está en |
|---|---|
| DTE / SII real | el sistema no emite DTE (`0013`) |
| GPS / telemetría | solo check-in manual del conductor |
| Banco / conciliación real | no existe; "caja" es un proxy de cobros − gastos |
| Nómina legal (AFP, salud) | no implementado; ver `negocio/preguntas.md` |
| Multiempresa en el legacy | no existe |
