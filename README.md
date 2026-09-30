# TRANSTEI — ERP Transportes TEI SpA

ERP a la medida para la gestión operativa y financiera de Transportes TEI SpA (transporte de carga terrestre, Chile).

## Stack

| Capa | Tecnología |
|---|---|
| Frontend | Next.js (App Router) + TypeScript + Tailwind CSS + Shadcn UI |
| Backend | FastAPI (Python) + SQLModel |
| Base de datos / Auth / Storage | PostgreSQL en Supabase |

## Estructura

```
frontend/    # Next.js
backend/     # FastAPI
supabase/    # Migraciones SQL + seed
docs/        # Plan de desarrollo y documentación
```

## Estado

- [x] FASE 0: Fundaciones (auth, roles, tema TEI)
- [x] FASE 1: Mantenedores (clientes, choferes, tractos, ramplas)
- [ ] FASE 2: Viajes + Dashboard
- [ ] FASE 3: Facturación + Cobranzas + IVA
- [ ] FASE 4: Sueldos + Mantenimiento + Alertas
- [ ] FASE 5: Reportes + Datos históricos + Preparación cloud

Ver `docs/PLAN_DESARROLLO.md` para el detalle completo.
