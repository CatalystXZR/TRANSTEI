> ⚠️ **Aviso de vigencia (2026-11-01):** cita archivos/cifras anteriores al retiro del legacy (`public`, `lib/api.ts`, `backend/app/api/routes/*`, `kpi_engine.py`). No citar como estado actual; ver `docs/estado.md` §2–§6 y `docs/PLAN_DESARROLLO.md`.

# F1 — Ola 6: dependencias, CI E2E y UI del POD (2026-10-31)

> Ejecutado por el orquestador dentro del reparto acordado con la sesión paralela (dueña del módulo agente). Archivos tocados: `backend/requirements*.txt`, `.github/workflows/ci.yml`, `frontend/package.json` + lock, `frontend/src/components/expediente/pod-panel.tsx`.

## 1. Dependencias backend (50 CVEs → 0)

| Paquete | Antes | Después |
|---|---|---|
| fastapi | 0.115.12 | **0.162.0** |
| starlette | 0.46.2 | **1.10.0** (explícita) |
| pyjwt[crypto] | 2.10.1 | **2.15.1** |
| python-multipart | 0.0.20 | **0.0.32** |
| pytest (dev) | 8.3.5 | **9.0.3** |

Método: primero en venv aislado (`venv-upgrade`) → suite **347/347**; luego aplicado a `.venv` y repo → `make unit` 135 · `make test` 347, verdes. `pip-audit -r backend/requirements.txt -r backend/requirements-dev.txt` → **"No known vulnerabilities found"**. Backend reiniciado y verificado (`/health` 200, `/api/v1/viajes` 401).

## 2. CI: job E2E

`.github/workflows/ci.yml` gana `e2e`: Supabase CLI + `supabase db reset` + credencial `tei_app` + seed + backend con `NUCLEO_DATABASE_URL` (tei_app) + `npm ci` + Playwright chromium + `npm run build` + `npx playwright test`. **No validado aún en GitHub Actions** (requiere el primer push; queda declarado).

## 3. Frontend: shadcn a devDependencies

`shadcn` movido de `dependencies` a `devDependencies`. `npm install` → `npm audit --omit=dev` → **0 vulnerabilidades** (antes 3 low). `tsc --noEmit` 0, `npm run lint` 0, `npm run build` OK (29 rutas).

## 4. UI POD: tope de 10 fotos

`pod-panel.tsx`: contador `(n/10)`, bloqueo del input al llegar al máximo, recorte de selección con `toast.error` al exceder, y mensaje de límite. Alineado con `MAX_FOTOS` del backend (Ola 3).

## Nota de coordinación (sesión paralela)

El módulo agente de la otra sesión devuelve **500** en `GET /api/v1/nucleo/agente/solicitudes` por `42P01` (`nucleo.solicitudes` no existe en la base local). Es su migración pendiente; no se tocó.

## Pendiente

- Validar el job E2E en el primer push.
- Commit de la fase: en pausa por instrucción del dueño.

## 5. Refresco de seguridad (2026-10-31, post-upgrade)

| Herramienta | Resultado |
|---|---|
| `pip-audit -r requirements*.txt` | **No known vulnerabilities found** (0 CVEs) |
| `npm audit --omit=dev` | **0** vulnerabilidades |
| `bandit -r backend/app` | 0 High · 3 B608 (Medium/Low-confidence) → **falsos positivos**: `agente/tools/despacho.py` arma SQL con fragmentos estáticos de whitelist (`_FILTROS_C1`) y valores como parámetros bind; nada del usuario se interpola. 2 B110 (Low) → patrón documentado de limpieza de archivos huérfanos (`servicio_maestros.py:584`, `storage.py:246`) |
| `gitleaks dir` (backend/frontend/src/scripts/docs) | mismos 4 hits conocidos: 2 en `backend/.env` (gitignored) + 2 falsos positivos de `localStorage` en `offline-queue.ts`; **sin secretos nuevos** |
| `make e2e` | **9/9 passed** con el stack actualizado |
| Servidor local | RLS activa confirmada (0 warnings de "RLS inerte" en el arranque) |
