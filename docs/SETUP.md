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
