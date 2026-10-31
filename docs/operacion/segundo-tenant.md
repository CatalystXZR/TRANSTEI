# Segundo tenant — onboarding local (2026-10-31)

> **Decisión:** D-3 resuelta por el dueño: el segundo tenant se habilita **ahora**.
> **Alcance:** entorno local/CI. En producción el alta de empresa y usuarios sigue siendo
> una operación de plataforma (no hay endpoint de alta de empresas; ver ADR-0005 R-4).

## Qué crea

`make seed-tenant2` (idempotente; equivale a `.venv/bin/python scripts/seed_segundo_tenant.py`):

| Objeto | Valor |
|---|---|
| Empresa | `22222222-2222-2222-2222-222222222222` · código **TES** · "Transportes del Sur SpA" |
| Usuarios | `admin2@tei.local` (admin) · `despacho2@tei.local` (despacho) · clave local `TEI2026!` |
| Membresías | activas en `nucleo.usuarios_empresa` para TES |
| Datos demo | 2 clientes de TES |

`make db-reset` ejecuta el seed de TEI **y** el del tenant 2, por lo que un reset deja el
sistema con dos empresas reales (ficticias) y aisladas.

## Qué queda aislado

- **Núcleo (`/api/v1/nucleo/*`):** RLS por `app.empresa_id` + `X-Empresa-ID` validado contra
  membresía. Un usuario de TES recibe **403** al pedir la empresa TEI; `mis-empresas` solo
  devuelve sus empresas.
- **Legacy (`/api/v1/<resto>`):** es monoempresa (sin `empresa_id`). Un usuario sin
  membresía en la empresa dueña del legacy (TEI) recibe **403 `LEGACY_SOLO_TEI`**
  (`main.py` · `GateLegacyMiddleware`). El legacy sigue disponible para TEI hasta su retiro
  (ADR-0002).
- **UI:** con `es_legacy=false` (campo de `GET /api/v1/auth/me`) se ocultan las 12 pantallas
  legacy y una URL directa a ellas muestra "Sin permiso" y redirige a `/despacho`.

## Verificación

```bash
make test-db && make test        # incluye las pruebas del gate y del aislamiento
make e2e                         # flujos TEI (no debe romperse)
# HTTP (backend :8000):
#   admin2@tei.local  GET /api/v1/clientes                  -> 403 LEGACY_SOLO_TEI
#   admin2@tei.local  GET /api/v1/nucleo/clientes (TES)     -> 200
#   admin@tei.local   GET /api/v1/clientes                  -> 200
```

## Rollback

- Local: `make db-reset` (vuelve al seed canónico, que ya incluye TES) o eliminar los datos
  de TES en orden de FKs (clientes → membresías → empresa).
- No hay migración asociada: el tenant es **dato**, no esquema.

## Límites declarados

- El gate legacy controla la **API**, no scripts con rol privilegiado (`postgres`).
- El pooler real y el límite de conexiones siguen sin probar (ADR-0005 R-2/R-3).
- Las credenciales de este documento son **locales** (misma convención que `postgres:postgres`
  del Makefile); nunca se usan en staging/producción.
