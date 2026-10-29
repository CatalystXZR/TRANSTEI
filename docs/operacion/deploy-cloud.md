# Despliegue en la nube (contingencia)

> **Pregunta que responde:** ¿cómo se despliega si se decide salir del entorno local?
> **Dueño:** `orquestador` · **Verificado:** 2026-10-29 · **Método:** lectura de repo y configuración
> **Caduca si:** se decide el proveedor, se crea `render.yaml`/`vercel.json` o cambia el dominio.
> **Re-verificar con:** `ls render.yaml vercel.json 2>/dev/null`

---

## ⚠️ Esto NO es el estado actual

El sistema corre **100 % local**. Esta guía es un plan de contingencia, no un
procedimiento probado. No existe `render.yaml` ni `vercel.json` en el repo.

🟡 Estado del proyecto Supabase en la nube: **no verificado** en esta sesión
(puede estar pausado; el plan Free pausa tras 7 días sin uso).

---

## 1. Arquitectura objetivo

```
Navegador
   ├── Next.js  -> Vercel        (NEXT_PUBLIC_API_URL)
   └── FastAPI  -> Render        (DATABASE_URL, claves de Supabase)
                      └── PostgreSQL -> Supabase (nube)
```

---

## 2. Backend (Render)

1. New → Web Service → conectar el repo.
2. **Root Directory:** `backend`.
3. Runtime: Python 3.
4. Build: `pip install -r requirements.txt`.
5. Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
6. Variables de entorno (nunca en el repo):
   - `DATABASE_URL` (Supabase, con SSL)
   - Claves de Supabase (URL, anon key, JWT secret / JWKS)
   - `DEBUG=false` — **verificar**: hoy `config.py` podría traer un default permisivo (RA-10)

---

## 3. Frontend (Vercel)

1. Importar el repo; **Root Directory:** `frontend`.
2. Build: `npm run build`.
3. Variable: `NEXT_PUBLIC_API_URL` → URL pública del backend.
4. ⚠️ La *anon key* de Supabase queda expuesta en el bundle por diseño. Qué permite
   realmente vía PostgREST/Storage **no está verificado** (RA-12): revisar políticas
   antes de publicar.

---

## 4. Migraciones en la nube

```bash
supabase link --project-ref <ref>
supabase db push
```

Antes de ejecutar:

- [ ] Confirmar el `project-ref` correcto.
- [ ] Backup verificado (`scripts/backup_pgdump.sh`).
- [ ] Autorización explícita: `db push` escribe esquema en producción.
- [ ] Las 19 migraciones aplican en orden; `0015` exige documentos y puede bloquear datos existentes.

---

## 5. Checklist previo a publicar

- [ ] `DEBUG=false` confirmado en el entorno.
- [ ] Secretos solo en el panel del proveedor.
- [ ] CORS restringido al dominio real.
- [ ] Políticas de Storage revisadas (POD, boletas).
- [ ] RLS del núcleo con políticas explícitas y probado con el rol real (RA-03).
- [ ] Backup automático activo.
- [ ] Health check apuntando a un endpoint que no exponga datos.

---

## 6. Riesgos de este camino

| Riesgo | Por qué |
|---|---|
| Doble fuente de verdad de datos | La base local y la nube divergen en cuanto se prueba en ambas |
| `db push` al proyecto equivocado | El repo mantiene un proyecto vinculado en `supabase/.temp/` |
| Costos | Render Free duerme; Supabase Free pausa |
| RLS sin políticas | El backend usa conexión directa; RLS no protege si el rol la bypassa |
