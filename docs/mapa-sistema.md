> **Pregunta que responde:** ¿cómo se conecta todo y dónde vive cada cosa?
> **Dueño:** `orquestador` · **Verificado:** 2026-11-12 · **Método:** lectura estática + conteos re-ejecutados (SQL `pg_tables`/`pg_policies`, `grep`, `find`)
> **Caduca si:** se agrega un router, una pantalla, una tabla o un cliente HTTP.
> **Re-verificar con:** `grep -c include_router backend/app/api/router.py && find frontend/src/app -name page.tsx | wc -l && docker exec supabase_db_TRANSTEI psql -U supabase_admin -d postgres -tA -c "select count(*) from pg_tables where schemaname='nucleo'"`

---

## 1. Vista de 30 segundos

```
Navegador / PWA
   │
   └── frontend (Next.js 16)  · 21 páginas (`page.tsx`)
         └── frontend/src/lib/nucleo.ts   → fetch('/api/v1/nucleo/*', { headers: Authorization + X-Empresa-ID })
                       │
         FastAPI (backend/app, Python 3.13, FastAPI 0.162)
                       │
         ├── app/api/routes/auth.py        → login/token (Supabase Auth, JWKS RS256/ES256)
         ├── app/nucleo/deps.py            → JWT + permisos + contexto de empresa (X-Empresa-ID + membresía)
         ├── app/nucleo/api_*.py           → 15 routers de dominio + 5 de agente/plataforma (18 include_router)
         ├── app/nucleo/servicio_*.py      → ~20 servicios (reglas, transacciones, idempotencia)
         └── app/nucleo/agente/            → agente conversacional (LLM + herramientas + WhatsApp)
                       │
         SQLModel → SQLAlchemy Core
                       │
         PostgreSQL 17 (Supabase local) — ÚNICO esquema de negocio: `nucleo`
           · 50 tablas · 54 políticas RLS · roles: tei_app (app), postgres (plataforma)
           · 35 migraciones forward-only en supabase/migrations/
           · auditoría append-only por trigger en nucleo.auditoria
```

🟢 Verificado 2026-11-12: 18 `include_router` (`backend/app/api/router.py:28-45`), 21 `page.tsx`,
1 solo cliente HTTP (`frontend/src/lib/nucleo.ts`; `lib/api.ts` eliminado), 50 tablas, 54
políticas RLS, 35 migraciones. **No hay segundo esquema de negocio** (`public` tiene 0 tablas).

---

## 2. Mapa de piezas por capa

| Capa | Dónde vive | Qué contiene |
|---|---|---|
| Frontend | `frontend/src/app/(app)/**` (21 `page.tsx`) | Tablero, despacho, agenda, expediente, conductor, comercial, rentabilidad, cobranza, IVA, liquidaciones, maestros, auditoría, permisos, configuración, agente (`/agente/chat`, `/agente/buzon`) — menú: 17 ítems (`frontend/src/lib/navigation.ts:41-82`) |
| Cliente HTTP | `frontend/src/lib/nucleo.ts` | Único cliente: agrega `Authorization` (JWT) + `X-Empresa-ID` y mapea errores |
| Auth | `backend/app/api/routes/auth.py` | Login contra Supabase Auth; el backend valida firma/audiencia contra JWKS (`backend/app/nucleo/deps.py`) |
| Autorización | `backend/app/nucleo/permisos.py`, `deps.py` | 8 roles (`models.py:79-88`), matriz `ROLES_PERMISOS`, deny-by-default; empresa resuelta en servidor desde `X-Empresa-ID` + `nucleo.usuarios_empresa` (nunca del body) |
| Routers de dominio | `backend/app/nucleo/api_*.py` | maestros, comercial, bloqueos, expediente, POD, conductor, gastos, rentabilidad, facturación, alertas, permisos, IVA, nómina, export, mantenimiento |
| Routers de agente | `backend/app/nucleo/` + `agente/` | `api_agente` (contactos, solicitudes, chat, configuración); herramientas con allow-list (`agente/`) |
| Servicios | `backend/app/nucleo/servicio_*.py` | Reglas de negocio, transacciones (`set_config` de contexto), disponibilidad, facturación, IVA, nómina, export |
| Modelos | `backend/app/nucleo/models.py` + `schemas.py` | SQLModel ↔ `nucleo`; Pydantic de entrada/salida |
| Migraciones | `supabase/migrations/0001`–`0035` | DDL forward-only; constraints críticas en PostgreSQL (`EXCLUDE USING gist`, `UNIQUE`, `CHECK`, triggers) |
| Pruebas de BD | `supabase/tests/` | Aislamiento RLS (`0020_01_aislamiento.sh`), rollback por migración (`*_99_rollback.sql`) |
| Pruebas de app | `backend/tests/**` (490), `frontend/e2e/tei.spec.ts` (20 Playwright) | Unitarias + integración PostgreSQL + HTTP + E2E |

---

## 3. Flujos canónicos

### 3.1 Identidad y multiempresa (todo request)

```
UI: Authorization: Bearer <jwt Supabase> + X-Empresa-ID: <uuid empresa>
  → deps.py: valida JWT (JWKS, audiencia authenticated)
  → get_contexto_empresa: consulta nucleo.usuarios_empresa (membresía) ANTES de fijar contexto
  → set_config('nucleo.empresa_id'/'auth_id') por transacción
  → requiere_permiso(rol) en cada endpoint (deny-by-default)
```

Garantía en DB: políticas RLS `tenant_empresa` `TO PUBLIC` + `FORCE` (54 políticas,
`0020_rls_multiempresa.sql`). Prueba: `supabase/tests/0020_01_aislamiento.sh` (rol real
`tei_app`, bypass=f, 12 veredictos OK). Único punto abierto: el rol efectivo de
`DATABASE_URL` en producción (RA-03).

### 3.2 Ciclo de viaje y ocupación (el libro único)

```
UI despacho → POST /nucleo/viajes        → servicio (borrador)
            → asignar tracto/rampla/chofer → servicio_disponibilidad consulta
              nucleo.reservas_recurso (ÚNICO libro de ocupación; EXCLUDE USING gist
              evita doble asignación activa del mismo recurso)
            → confirmar → despachar → POD → facturar → cierre
```

- Cada transición valida documentos (`0015`/`0016`); los eventos del expediente son
  inmutables (trigger `fn_evento_inmutable`, `0007`).
- Rangos de ocupación semiabiertos `[inicio, fin)`; `timestamptz` en UTC.

### 3.3 Facturación (dinero)

```
POD presente → emitir factura (folio por empresa: nucleo.siguiente_folio)
  → factura + factura_viajes + pagos/notas de crédito (0028-bloque: 0013)
  → triggers de estado + auditoría append-only en cada tabla financiera
```

- `numeric` para dinero; sin `float`. Documento emitido no se edita: corrección por
  nota de crédito (regla tributaria pendiente de confirmar con contador, D-08/P-…).
- Deuda declarada: idempotencia `Idempotency-Key` en pagos (D-08).

### 3.4 Agente conversacional (Ola 3)

```
UI /agente/chat  ┐
WhatsApp (Meta)  ┴→ api_agente (chat/solicitudes/contactos/config)
   → agente/: proveedor LLM (deepseek), loop con herramientas allow-list
   → herramientas = servicios del núcleo (mismas reglas, mismo tenant)
   → módulos por empresa: nucleo.modulos_empresa (fail-closed: sin fila = apagado)
```

Env vars del canal: `AGENTE_LLM_*`, `WHATSAPP_*` (`backend/app/core/config.py:33-48`).
Migraciones `0021`–`0023` (esquema del agente + gate).

---

## 4. Convenciones obligatorias

| Convención | Dónde se impone |
|---|---|
| `timestamptz` (UTC en BD) para eventos; `date` solo vigencias | migraciones; presentación en `America/Santiago` |
| Rangos semiabiertos `[inicio, fin)` | `reservas_recurso`, disponibilidad |
| `numeric` para dinero; redondeo con regla documentada | `0013`, servicios de facturación |
| Garantía crítica = constraint/trigger en PostgreSQL | `0004:813-892` (auditoría), `EXCLUDE` (0004), folios (`siguiente_folio`) |
| Errores PG → HTTP: `23505`/`23P01`→409, `23514`/`23502`→422, nunca 500 por negocio | `backend/app/nucleo/errores.py` |
| Auditoría append-only con usuario real (`nucleo.auth_id`) | triggers `_audit`; set_config por transacción |
| Empresa desde `X-Empresa-ID` + membresía; nunca del body | `deps.py:40-82` |

---

## 5. Dónde NO buscar

| Concepto | Estado | Dónde está el rastro |
|---|---|---|
| Esquema `public` (legacy) | **Retirado físicamente** (`0028`, 2026-11-01: 0 tablas) | `docs/_archivo/cutover-ejecutado-2026-11-01.md`; `backups/cutover_pre_20261101_115202.sql` |
| Código legacy (`lib/api.ts`, `backend/app/api/routes/*`, `kpi_engine.py`) | **Eliminado del repo** (2026-11-12) | `docs/arquitectura/retiro-legacy.md` §11; `docs/orquestacion/registro.md` |
| Cutover (flag, middleware, script, tabla `cutover_control`) | **Eliminado**: código 2026-11-12, tabla por `0035` (2026-11-12) | `docs/arquitectura/destino-modular.md` M12; `docs/datos/catalogo-migraciones.md` (0035) |
| Rutas legacy en UI | **404** (grupo `(retiradas)` eliminado) | `frontend/e2e/tei.spec.ts` (pruebas 404) |

> Regla de lectura: si un documento menciona `public`, `lib/api.ts` o "cutover" sin
> marcarlo como histórico, está desactualizado — corrígelo o archívalo, no lo cites
> como estado.
