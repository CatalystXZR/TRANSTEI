> **ARCHIVADO 2026-10-29 — NO CITAR COMO ESTADO.**
> Documento histórico. Reemplazos y contexto: `docs/_archivo/README.md` · Estado real: `docs/estado.md`.
> Sus cifras y afirmaciones de "terminado" NO fueron re-verificadas en esta fecha.

# Guía de Despliegue a Cloud (Vercel + Render + Supabase)

> Estado actual: sistema corriendo 100% local. Esta guía permite migrar a cloud
> cuando se decida (Fase 5 del plan). Todo el código ya está preparado: las
> configuraciones se leen desde variables de entorno.

## Arquitectura objetivo

```
Cliente (navegador)
   │
   ├── Frontend Next.js en Vercel (dominio gratuito: *.vercel.app)
   │        └── llama API → NEXT_PUBLIC_API_URL
   │
   └── Backend FastAPI en Render (dominio gratuito: *.onrender.com)
            └── PostgreSQL en Supabase (ya operativo: luzxxhgozpqsxnwfookb)
```

## 1. Desplegar el Backend en Render

1. Crear cuenta en https://render.com
2. **New → Web Service → Connect GitHub → repo `CatalystXZR/TRANSTEI`**
3. Configuración:
   - **Root Directory**: `backend`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Variables de entorno (Settings → Environment):
   | Variable | Valor |
   |---|---|
   | `SUPABASE_URL` | `https://luzxxhgozpqsxnwfookb.supabase.co` |
   | `SUPABASE_SERVICE_ROLE_KEY` | (Settings → API del proyecto Supabase) |
   | `DATABASE_URL` | Connection string del pooler (Settings → Database) |
   | `CORS_ORIGINS` | `https://TU-PROYECTO.vercel.app` |
   | `DEBUG` | `false` |
5. **Deploy**. Verificar `https://TU-SERVICIO.onrender.com/health`

## 2. Desplegar el Frontend en Vercel

1. Crear cuenta en https://vercel.com (sign in con GitHub)
2. **Add New → Project → importar `CatalystXZR/TRANSTEI`**
3. Configuración:
   - **Root Directory**: `frontend`
   - **Framework Preset**: Next.js
4. Variables de entorno (Settings → Environment Variables):
   | Variable | Valor |
   |---|---|
   | `NEXT_PUBLIC_SUPABASE_URL` | `https://luzxxhgozpqsxnwfookb.supabase.co` |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | (Settings → API, clave `anon`) |
   | `NEXT_PUBLIC_API_URL` | `https://TU-SERVICIO.onrender.com/api/v1` |
5. **Deploy**. El dominio gratis será `https://TU-PROYECTO.vercel.app`

## 3. Dominio propio (opcional, después)

1. Comprar `transportestei.cl` (ej: en nic.cl)
2. Vercel: Settings → Domains → agregar dominio → configurar DNS
3. Render: Settings → Custom Domain para el backend (`api.transportestei.cl`)
4. Actualizar `NEXT_PUBLIC_API_URL` y `CORS_ORIGINS`

## 4. CORS entre frontend y backend

El backend ya tiene CORS configurado vía variable `CORS_ORIGINS` (lista separada por
comas). Al desplegar, agregar el dominio de Vercel.

## 5. Notas de Supabase (free tier)

- El proyecto se **pausa tras 7 días sin uso**; se reactiva con un clic en el dashboard
- Backups: activar en Supabase → Database → Backups (diario en plan pro; free tiene PITR limitado)
- Las migraciones se aplican con el script seguro (`docs/SETUP.md`)
