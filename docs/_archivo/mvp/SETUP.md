> **ARCHIVADO 2026-10-29 — NO CITAR COMO ESTADO.**
> Documento histórico. Reemplazos y contexto: `docs/_archivo/README.md` · Estado real: `docs/estado.md`.
> Sus cifras y afirmaciones de "terminado" NO fueron re-verificadas en esta fecha.

# Guía de Configuración y Ejecución

## Estado actual

- **Repo GitHub**: `github.com/CatalystXZR/TRANSTEI` (privado, rama `main`)
- **Proyecto Supabase**: TRANSTEI — ref `luzxxhgozpqsxnwfookb` — región `sa-east-1` (São Paulo)
- **Migración aplicada**: `supabase/migrations/0001_esquema_base.sql` ✓
- **Bucket Storage**: `respaldos` (privado) ✓
- **Usuarios de prueba**: admin / operacion / contabilidad (roles asignados) ✓
- **Credenciales locales**: `backend/.env` y `frontend/.env.local` (gitignored) ✓

## Cómo levantar el entorno

```bash
# Backend (puerto 8000)
cd backend && ./venv/bin/python -m uvicorn app.main:app --reload --port 8000

# Frontend (puerto 3000)
cd frontend && npm run dev
```

## Cómo crear nuevos usuarios

1. En Supabase Dashboard → Authentication → Add user (con confirmación de email)
2. En Table Editor → `usuarios`, asignar el rol (`admin`, `operacion`, `contabilidad`)
   - El trigger `on_auth_user_created` crea el perfil automáticamente con rol `operacion`

## Roles

| Rol | Acceso |
|---|---|
| admin (dueño) | Todo el sistema |
| operacion (secretaria) | Dashboard, Viajes, Clientes, Choferes, Flota, Mantenimiento, Facturación |
| contabilidad (contador) | Dashboard, Viajes, Facturación, Cobranzas, IVA, Liquidaciones (catalogos en solo lectura) |

## Migraciones futuras

Cada cambio de esquema se agrega como `supabase/migrations/NNNN_descripcion.sql` y se aplica con:

```bash
cd backend
./venv/bin/python - << 'EOF'
import psycopg
# usar DATABASE_URL de backend/.env
EOF
```

## Núcleo operacional v2 (schema `nucleo`)

La migración `supabase/migrations/0004_nucleo_operacional.sql` crea el schema
`nucleo` con empresas, flota, documentos, OC, tarifas, viajes, reservas y
auditoría. Es independiente del esquema legacy `public`; ambos conviven durante
el cutover.

Aplicación:

```bash
supabase db push
# o:
psql "$DATABASE_URL" -f supabase/migrations/0004_nucleo_operacional.sql
```

Después hay que crear la membresía del usuario:

```sql
insert into nucleo.usuarios_empresa (empresa_id, auth_id, rol)
values ('<uuid-empresa>', '<auth_id-supabase>', 'admin');
```

La API del núcleo exige el header `X-Empresa-ID` y el JWT de Supabase.

## Entorno local recomendado (MacBook Air M3, 16 GB / 512 GB)

### Opción A — Supabase local + OrbStack (recomendada)

Da paridad con producción: PostgreSQL, Auth, Storage y Studio locales.

1. Instalar OrbStack (runtime Docker liviano para Apple Silicon) o Docker Desktop.
2. Instalar Supabase CLI:
   ```bash
   brew install supabase/tap/supabase
   ```
3. En la raíz del repo:
   ```bash
   supabase init          # crea supabase/config.toml si no existe
   supabase start         # levanta Postgres/Auth/Storage/Studio
   supabase db push       # aplica las migraciones
   supabase status        # muestra URL, anon key y service_role key
   ```
4. Copiar las claves locales a `backend/.env` y `frontend/.env.local`.
5. Ejecutar backend y frontend:
   ```bash
   cd backend && ./venv/bin/python -m uvicorn app.main:app --reload --port 8000
   cd frontend && npm run dev
   ```

Con 16 GB, asignar a OrbStack un límite de ~6 GB es suficiente. Las imágenes de
Supabase ocupan del orden de 10–15 GB; con 512 GB de SSD hay espacio de sobra.

### Opción B — PostgreSQL local + Supabase remoto para Auth/Storage

Más liviano, pero con dos entornos:

```bash
brew install postgresql@16
brew services start postgresql@16
createdb transtei
psql transtei -f supabase/migrations/0004_nucleo_operacional.sql
```

Luego `DATABASE_URL` apunta al PostgreSQL local y `SUPABASE_URL`/claves apuntan
al proyecto Supabase de desarrollo. Auth y Storage siguen siendo remotos.

### Prueba de integración

```bash
cd backend
export NUCLEO_TEST_DATABASE_URL="postgresql+psycopg://postgres@127.0.0.1:5432/transtei"
pytest tests/test_nucleo_integracion.py -q
```

## Entorno local ya configurado en esta máquina

Se instaló y dejó funcionando:

- **Colima** (runtime Docker local, 4 CPU / 6 GB / 60 GB).
- **Supabase CLI** con Supabase local en `http://127.0.0.1:54321`.
- **PostgreSQL local** en `127.0.0.1:54322`, con migraciones 0001–0004 aplicadas.
- **Node 22** y dependencias del frontend.
- **Backend y frontend** levantados en los puertos 8000 y 3000.
- **Seed local** con TEI, 3 tractos, 3 ramplas, 3 choferes, documentos, tarifas, OC y 3 viajes.

Comandos:

```bash
make db-up       # Colima + Supabase local
make seed        # datos de TEI + usuario admin
make backend     # FastAPI :8000
make frontend    # Next.js :3000
make db-down     # bajar Supabase
make db-reset    # borrar y rehacer base + seed (destructivo)
```

Credenciales locales:

```text
http://localhost:3000/login
http://localhost:3000/despacho   # Mesa de despacho del núcleo v2
admin@tei.local
TEI2026!
```

Supabase Studio: `http://127.0.0.1:54323`

> `backend/.env` y `frontend/.env.local` son locales y están gitignored. No
> contienen secretos de producción: usan las claves de demostración de Supabase
> CLI.
