# TRANSTEI — ERP Transportes TEI SpA

ERP a la medida para la gestión operativa y financiera de Transportes TEI SpA,
empresa de transporte de carga terrestre en Chile.

El repositorio mantiene **dos capas que coexisten**:

| Capa | Schema PostgreSQL | API | Rol |
|---|---|---|---|
| Legacy (MVP) | `public` | `/api/v1/*` | En uso; **no** es multiempresa |
| Núcleo v2 | `nucleo` | `/api/v1/nucleo/*` | Destino del cutover |

La migración es progresiva (*strangler*): primero maestros, luego viajes abiertos y
finalmente el congelamiento de la escritura legacy. No se introduce una tercera
fuente de verdad ni se retira el legacy sin ventana de cutover autorizada
(ver [`docs/operacion/cutover.md`](docs/operacion/cutover.md)).

## Stack

Versiones verificadas en `backend/requirements.txt` y `frontend/package.json`
(2026-10-29):

| Capa | Tecnología |
|---|---|
| Frontend | Next.js 16.3.7 (App Router), React 19.2.8, TypeScript 5, Tailwind CSS 4 |
| Backend | Python 3.13, FastAPI 0.115.12, SQLModel 0.0.24, Pydantic 2.11.4, psycopg 3.2.6 |
| Base de datos | PostgreSQL de Supabase local (`127.0.0.1:54322`), extensiones `btree_gist` y `pgcrypto` |
| Auth / Storage | Supabase Auth (JWT) y Supabase Storage |
| E2E | Playwright 1.56 |

## Estructura

```text
frontend/    # Next.js: pantallas legacy y del núcleo, PWA del conductor
backend/     # FastAPI: app/api (legacy) + app/nucleo (modelos, servicios y routers)
supabase/    # Migraciones 0001–0019 y configuración local
scripts/     # seed, cutover legacy, backup y restore drill
docs/        # Documentación técnica, de negocio y de agentes
```

## Puesta en marcha

Requisitos: Python 3.13 en `.venv`, Node.js 22, Docker/Colima y Supabase CLI.

```bash
make help       # lista todos los comandos disponibles
make db-up      # levanta Supabase local (Colima + supabase start)
make seed       # carga datos del piloto y los 8 usuarios locales
make backend    # FastAPI en http://localhost:8000
make frontend   # Next.js en http://localhost:3000
```

- API: `http://localhost:8000/api/v1` (OpenAPI interactivo en `/docs`).
- Web: `http://localhost:3000`.
- Supabase Studio: `http://127.0.0.1:54323`.
- `make db-reset` borra y recrea la base local: **es destructivo**.

## Pruebas

```bash
make unit          # unitarias del núcleo, sin base de datos
make test          # suite completa contra Supabase local
make e2e           # Playwright (requiere frontend en :3000 y datos)
```

Al 2026-10-29, las unitarias de `make unit` ejecutaron **52 pruebas en verde**. La
integración PostgreSQL, las pruebas HTTP y el E2E requieren base local y frontend
levantados; no se ejecutaron en esa verificación. Un `skip` o un "no ejecutado" no
es un aprobado.

## Backup y cutover

```bash
make restore-drill   # backup + restore en base temporal + verificación
make cutover-dry     # dry-run de migración legacy → núcleo
make cutover         # migra y congela la escritura legacy
```

`make cutover` modifica datos y congela escrituras: requiere backup verificado,
ventana coordinada y autorización explícita. Ver
[`docs/operacion/cutover.md`](docs/operacion/cutover.md).

## Usuarios locales del seed

`admin@tei.local`, `gerente@tei.local`, `despacho@tei.local`, `contador@tei.local`,
`tesoreria@tei.local`, `taller@tei.local`, `conductor@tei.local`,
`auditor@tei.local`; clave `TEI2026!`. Solo aplican al entorno local.

## Estado del repositorio

| Área | Evidencia en el repo | Verificación |
|---|---|---|
| Migraciones | `supabase/migrations/0001`–`0019` | 🟢 listadas y leídas |
| API legacy | routers en `backend/app/api/routes/` | 🟢 montados en `backend/app/api/router.py` |
| API núcleo | 13 routers en `backend/app/nucleo/api*.py` | 🟢 montados en `backend/app/api/router.py` |
| Pantallas | legacy y núcleo en `frontend/src/app/(app)/`; PWA en `/conductor` | 🟢 rutas y manifest presentes |
| Unitarias | `make unit` | 🟢 52 passed (2026-10-29) |
| Integración/HTTP | requieren Supabase local | 🔴 no ejecutadas en esta actualización |
| E2E | 9 escenarios en `frontend/e2e/tei.spec.ts` | 🔴 no ejecutados |
| Cutover | `scripts/cutover_legacy.py` + checklist | 🔴 dry-run no ejecutado en esta verificación |

El estado declarado de fases y pendientes vive en [`docs/estado.md`](docs/estado.md);
la documentación histórica está en [`docs/_archivo/`](docs/_archivo/README.md) y **no
se cita como estado**.

## Límites conocidos

- `public` no tiene `empresa_id` y no filtra por empresa; **no debe presentarse como
  aislado por tenant**.
- En `nucleo`, varias tablas tienen RLS habilitado y las migraciones no definen
  políticas para el schema. El backend resuelve la empresa con `X-Empresa-ID` +
  membresía en `nucleo.usuarios_empresa`; el aislamiento no se declara como
  garantía impuesta por RLS.
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
| Ver módulos y pantallas | [`docs/arquitectura/modulos.md`](docs/arquitectura/modulos.md) |
| Entender disponibilidad y reservas | [`docs/arquitectura/nucleo-diseno.md`](docs/arquitectura/nucleo-diseno.md) |
| Consultar reglas de negocio | [`docs/negocio/catalogo-reglas.md`](docs/negocio/catalogo-reglas.md) |
| Levantar el entorno | [`docs/operacion/setup-local.md`](docs/operacion/setup-local.md) |
| Hacer el cutover | [`docs/operacion/cutover.md`](docs/operacion/cutover.md) |
| Ver escenarios de aceptación | [`docs/qa/uat-piloto.md`](docs/qa/uat-piloto.md) |
| Revisar lo que se intentó antes | [`docs/_archivo/README.md`](docs/_archivo/README.md) |

Reglas de trabajo y límites de autonomía: [`AGENTS.md`](AGENTS.md).
