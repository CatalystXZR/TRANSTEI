# TMS (producto sin nombre) — TEI Advisory

Sistema TMS (Transportation Management System) para la gestión operativa y
financiera de empresas de transporte de carga terrestre en Chile. El producto
**aún no tiene nombre comercial**: se comercializa bajo licencia B2B por
**TEI Advisory**. Su caso de uso original y piloto es Transportes TEI SpA; nada
del código asume una sola empresa — el sistema es multiempresa desde el esquema.

El repositorio opera sobre **un único esquema de negocio: `nucleo`**. El esquema
legacy `public` fue retirado físicamente (migración `0028`, 2026-11-01) y el
cutover está ejecutado; el código legacy remanente (API/UI de cutover, páginas
redirigidas, script y targets) fue eliminado el 2026-11-12. El historial de esa
transición vive en [`docs/_archivo/`](docs/_archivo/README.md) y **no se cita
como estado**.

## Stack

Versiones verificadas en `backend/requirements.txt` y `frontend/package.json`
(2026-11-12):

| Capa | Tecnología |
|---|---|
| Frontend | Next.js 16.4.3 (App Router), React 19.2.8, TypeScript 5, Tailwind CSS 4 |
| Backend | Python 3.13, FastAPI 0.162.0, SQLModel 0.0.24, Pydantic 2.11.4, psycopg 3.2.6 |
| Base de datos | PostgreSQL 17 de Supabase local (`127.0.0.1:54322`), extensiones `btree_gist` y `pgcrypto` |
| Auth / Storage | Supabase Auth (JWT, validado contra JWKS) y Supabase Storage |
| E2E | Playwright 1.56 |

## Estructura

```text
frontend/    # Next.js: pantallas del núcleo en src/app/(app)/, PWA del conductor,
             #   agente IA (chat in-app /agente/chat) y cliente HTTP único lib/nucleo.ts
backend/     # FastAPI: app/nucleo (modelos, servicios y routers); app/api solo conserva
             #   /auth/me (identidad desde JWT + nucleo.usuarios_empresa)
supabase/    # Migraciones 0001–0035 y configuración local
scripts/     # seed, roles de BD, backup y restore drill
docs/        # Documentación técnica, de negocio y de agentes (entrada: docs/INDEX.md)
```

## Puesta en marcha

Requisitos: Python 3.13 en `.venv`, Node.js 22, Docker/Colima y Supabase CLI.

```bash
make help            # lista todos los comandos disponibles
make db-up           # levanta Supabase local (Colima + supabase start)
make seed            # carga datos del piloto y los 8 usuarios locales
make seed-tenant2    # carga el segundo tenant local (TES)
make backend         # FastAPI en http://localhost:8000
make frontend        # Next.js en http://localhost:3000
```

- API: `http://localhost:8000/api/v1` (todo el negocio bajo `/nucleo/*`).
- Web: `http://localhost:3000`.
- Supabase Studio: `http://127.0.0.1:54323`.
- `make db-reset` borra y recrea la base local: **es destructivo**.

## Pruebas

```bash
make unit          # unitarias del núcleo, sin base de datos
make test          # suite completa contra Supabase local
make e2e           # Playwright (requiere frontend en :3000 y datos)
```

Cifras de la última re-verificación completa (2026-11-12): `make unit` **135
passed**, `make test` **490 passed, 0 skipped** y `make e2e` **20/20** (rutas
legacy → 404; la 1.ª corrida falló por servidores dev huérfanos de una sesión
anterior, no por código). El estado
vigente de las suites vive en [`docs/estado.md`](docs/estado.md) y se re-verifica
ahí; un `skip` o un "no ejecutado" no es un aprobado.

## Backup y restauración

```bash
make restore-drill   # backup + restore en base temporal + verificación
```

El cutover legacy → núcleo ya está ejecutado; el procedimiento quedó archivado en
[`docs/_archivo/cutover.md`](docs/_archivo/cutover.md).

## Usuarios locales del seed

`admin@tei.local`, `gerente@tei.local`, `despacho@tei.local`, `contador@tei.local`,
`tesoreria@tei.local`, `taller@tei.local`, `conductor@tei.local`,
`auditor@tei.local`; clave `TEI2026!`. Segundo tenant (TES): `admin2@tei.local`.
Solo aplican al entorno local.

## Estado del repositorio

Las cifras volátiles (migraciones, tablas, routers, pantallas, suites) viven en
[`docs/estado.md`](docs/estado.md), el único documento autorizado a contenerlas.
Resumen a la fecha de esta actualización:

| Área | Evidencia en el repo | Verificación |
|---|---|---|
| Esquema | `nucleo` único (50 tablas); `public` retirado en `0028` (0 tablas) | 🟢 migración aplicada y documentada |
| Migraciones | `supabase/migrations/0001`–`0035` | 🟢 35 en disco y aplicadas en la base local; `0035` untracked |
| API núcleo | routers en `backend/app/nucleo/api*.py` (18 `include_router`) | 🟢 montados en `backend/app/api/router.py` |
| Identidad | `GET /api/v1/auth/me` (JWT + `nucleo.usuarios_empresa`) | 🟢 único endpoint fuera de `/nucleo` |
| Pantallas | `frontend/src/app/(app)/`; PWA en `/conductor`; agente en `/agente/chat` | 🟢 rutas y manifest presentes; rutas legacy → 404 |
| Cutover | ejecutado (Ola D, 2026-11-01) y luego **retirado por completo** (código + tabla, `0035`, 2026-11-12) | 🟢 histórico en `docs/_archivo/cutover.md` |
| Suites | `make unit` / `make test` / `make e2e` | ver `docs/estado.md` |

La documentación histórica está en [`docs/_archivo/`](docs/_archivo/README.md) y
**no se cita como estado**.

## Límites conocidos

- `nucleo` tiene RLS habilitado, pero el aislamiento no se declara como garantía
  impuesta por RLS: el backend resuelve la empresa con `X-Empresa-ID` + membresía
  en `nucleo.usuarios_empresa`, y el rol efectivo de la aplicación debe
  verificarse antes de afirmar aislamiento en base.
- La UI no es un control de seguridad; la autorización efectiva está en el backend.
- Reglas tributarias, laborales y comerciales sin fuente se registran como pregunta
  pendiente (contador/asesor), no se asumen.

## Documentación

> Los documentos describen intención o estado declarado. La fuente de verdad es el
> código, las migraciones y las pruebas ejecutadas.

**Punto de entrada: [`docs/INDEX.md`](docs/INDEX.md)** — responde "dónde está lo que
busco" y enlaza todo lo demás.

| Si necesitás… | Documento |
|---|---|
| Saber qué está listo hoy | [`docs/estado.md`](docs/estado.md) |
| Entender cómo se conecta todo | [`docs/mapa-sistema.md`](docs/mapa-sistema.md) |
| Entender disponibilidad y reservas | [`docs/arquitectura/nucleo-diseno.md`](docs/arquitectura/nucleo-diseno.md) |
| Consultar reglas de negocio | [`docs/negocio/catalogo-reglas.md`](docs/negocio/catalogo-reglas.md) |
| Levantar el entorno | [`docs/operacion/setup-local.md`](docs/operacion/setup-local.md) |
| Respaldar y restaurar | [`docs/operacion/backup-restore.md`](docs/operacion/backup-restore.md) |
| Ver escenarios de aceptación | [`docs/qa/uat-piloto.md`](docs/qa/uat-piloto.md) |
| Revisar lo que se intentó antes | [`docs/_archivo/README.md`](docs/_archivo/README.md) |

Reglas de trabajo y límites de autonomía: [`AGENTS.md`](AGENTS.md).
