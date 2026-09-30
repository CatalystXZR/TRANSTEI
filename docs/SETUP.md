# Guía de Configuración y Ejecución (Fase 0)

## Requisitos

- Python 3.13+ (venv incluido en `backend/venv`)
- Node.js 22+ (instalado en `~/.local/node/bin`, ya agregado a `~/.profile`)
- Un proyecto [Supabase](https://supabase.com) gratuito (DB + Auth + Storage)

## 1. Crear el proyecto Supabase

1. Crear cuenta/proyecto en https://supabase.com/dashboard
2. En **SQL Editor**, ejecutar el contenido de `supabase/migrations/0001_esquema_base.sql` (crea tablas, enums, RLS, triggers y seed)
3. Crear un bucket de Storage llamado `respaldos` (privado) para boletas y PDFs
4. En **Authentication → Users**, crear los usuarios (dueño, secretaria, contador)
5. Asignar roles: en **Table Editor → usuarios**, cambiar `rol` del dueño a `admin` (los nuevos usuarios se crean con rol `operacion` automáticamente)

## 2. Configurar el backend

```bash
cd backend
cp .env.example .env   # completar con los datos de Supabase → Settings → API
```

| Variable | Dónde obtenerla |
|---|---|
| `SUPABASE_URL` | Settings → API → Project URL |
| `SUPABASE_ANON_KEY` | Settings → API → anon public |
| `SUPABASE_SERVICE_ROLE_KEY` | Settings → API → service_role (secreto) |
| `SUPABASE_JWT_SECRET` | Settings → API → JWT Settings |
| `DATABASE_URL` | Settings → Database → Connection string → Session pooler (cambiar `postgresql://` por `postgresql+psycopg://`) |

Ejecutar:

```bash
./venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Verificar: `http://localhost:8000/health` → `{"status":"ok",...}`

## 3. Configurar el frontend

```bash
cd frontend
cp .env.local.example .env.local  # completar con los datos de Supabase
npm run dev                        # http://localhost:3000
```

Variables: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1`

## 4. Verificación Fase 0 (hito)

- [ ] Login con email/contraseña de Supabase funciona
- [ ] El sistema muestra el rol correcto (admin/operación/contabilidad)
- [ ] El menú lateral filtra opciones según el rol
- [ ] Cerrar sesión y volver a entrar funciona

## Roles

| Rol | Acceso |
|---|---|
| admin (dueño) | Todo el sistema |
| operacion (secretaria) | Dashboard, Viajes, Clientes, Choferes, Flota, Mantenimiento, Facturación |
| contabilidad (contador) | Dashboard, Viajes, Facturación, Cobranzas, IVA, Liquidaciones |
