# 0020 — RLS multiempresa (`supabase/migrations/0020_rls_multiempresa.sql`)

> **Nota de índice.** El diseño completo, las precondiciones, el impacto, el
> rollback, las pruebas ejecutadas y el handoff a `backend` viven en
> **[`docs/datos/rls-multiempresa.md`](../rls-multiempresa.md)**. Este archivo solo
> evita que el diseño quede fuera de esta carpeta.

| Campo | Valor |
|---|---|
| Archivo | `supabase/migrations/0020_rls_multiempresa.sql` |
| Invariante | `INV-T01` — aislamiento por empresa impuesto en PostgreSQL |
| Riesgo | **Alto** (aislamiento multiempresa) |
| Objetos | rol `tei_app`; `nucleo.ctx_empresa()`, `ctx_auth_id()`, `empresas_del_usuario()`; 35 políticas; `FORCE RLS` ×31; GRANTs |
| Contexto | GUC `app.empresa_id` por transacción (`set_config(…, true)`) |
| Aplicada en | **`tei_test` únicamente** (2026-10-30); 🔴 no aplicada a la base de la app |
| Precondiciones | P1–P6 del encabezado de la migración (deben dar 0 filas) |
| Rollback | `supabase/tests/0020_99_rollback.sql` (probado: sin pérdida de datos) |
| Pruebas | `supabase/tests/0020_01…04` (diseño §7) |
| Inerte mientras | el backend conecte como `postgres` (BYPASSRLS gana sobre FORCE) |
