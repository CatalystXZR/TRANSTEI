# Entorno local — cómo levantarlo

> **Pregunta que responde:** ¿cómo arranco el ERP en mi máquina y qué rutas son las reales?
> **Dueño:** `orquestador` · **Verificado:** 2026-10-29 · **Método:** lectura de `Makefile` + ejecución de `make unit`
> **Caduca si:** cambia el `Makefile`, el runtime o la configuración de Supabase.
> **Re-verificar con:** `make help`

---

## 1. Requisitos

| Componente | Versión / nota |
|---|---|
| Python | 3.13 — el venv vive en **`.venv/` de la raíz** (no en `backend/venv`) |
| Node | 22 (el `Makefile` apunta a `/opt/homebrew/opt/node@22/bin`) |
| Docker | Colima o Docker Desktop |
| Supabase CLI | para `supabase start` |
| PostgreSQL | 17 (fijado en `supabase/config.toml:41`) |

🟢 El `Makefile` usa `PYTHON := .venv/bin/python` (`Makefile:3`). **No existe `backend/venv`.**

---

## 2. Arranque

```bash
make db-up      # Colima + Supabase local (imprime poco a propósito: log en $TMPDIR)
make seed       # datos del piloto
make backend    # FastAPI  -> http://localhost:8000
make frontend   # Next.js  -> http://localhost:3000
```

Otros comandos:

```bash
make unit            # unitarias del núcleo (no requiere base)
make test            # suite completa (requiere Supabase local)
make e2e             # Playwright (requiere :3000 + datos)
make restore-drill   # backup + restore en base temporal
make cutover-dry     # dry-run legacy -> nucleo
make help            # lista real de targets
```

⚠️ **`make db-reset` es destructivo**: borra la base local, reaplica migraciones y seed.
Requiere autorización explícita.

---

## 3. Direcciones y credenciales

| Elemento | Valor |
|---|---|
| API | `http://localhost:8000/api/v1` |
| Frontend | `http://localhost:3000` |
| PostgreSQL local | `127.0.0.1:54322` |
| Supabase Studio | `127.0.0.1:54323` |
| Login admin | `admin@tei.local` / `TEI2026!` |
| Roles del seed | gerente, despacho, contador, tesoreria, taller, conductor, auditor |

🔴 **`:54322` no está confirmado como el Postgres de Supabase** en la sesión del
2026-10-29: hay evidencia de un túnel `ssh` escuchando en ese puerto. Verificalo con
`docker ps --filter name=supabase_db` antes de confiar en `make test`.

Las credenciales viven en `backend/.env` y `frontend/.env.local` (ambos ignorados por git).
**Nunca** las leas, imprimas ni pegues en un informe.

---

## 4. Migraciones

```bash
supabase migration list --local
```

- El esquema real son **19 migraciones** (`0001`–`0019`), no 4.
- `supabase db push` **sin `--local` puede apuntar al proyecto en la nube**: el repo
  mantiene un proyecto vinculado en `supabase/.temp/linked-project.json`.
  🟡 Verificá el destino antes de usar ese comando.
- Para reconstruir desde cero: `make db-reset` (destructivo local).

---

## 5. Problemas conocidos

| Síntoma | Causa | Solución |
|---|---|---|
| `backend/venv/bin/python: no such file` | Ruta vieja de `SETUP.md` (archivado) | usar `.venv/bin/python` |
| `make test` falla con conexión rechazada | Supabase local apagado | `make db-up` |
| `supabase start` pide login | CLI sin sesión | `supabase login` (no commitees el token) |
| El backend arranca pero las tablas no existen | migraciones no aplicadas | `make db-reset` (destructivo) o `supabase migration up` |
| E2E falla en el primer test | datos del seed ausentes | `make seed` |

---

## 6. Orden recomendado para una sesión nueva

1. `git status --short` — no pises trabajo ajeno.
2. `make db-up` (si vas a probar integración).
3. `make unit` — línea base rápida.
4. `make backend` y `make frontend` en dos terminales.
5. Registrar el resultado real en `docs/qa/linea-base.md`.
