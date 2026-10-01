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
- [x] FASE 2: Viajes + Dashboard (estados, gastos con boleta, KPIs, alertas)
- [x] FASE 3: Facturación + Cobranzas + IVA
- [x] FASE 4: Sueldos + Mantenimiento + Alertas (+ PDF liquidación)
- [x] FASE 5: Export/Import CSV + Preparación cloud (docs + CI)
- [x] FASE 6: Blindaje — motor de KPIs configurables, tests pytest, validaciones duras, docs y backup

Ver `docs/PLAN_DESARROLLO.md` para el detalle completo.
