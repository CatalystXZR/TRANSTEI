# `_archivo/` — Documentación histórica

> **Estos documentos NO son fuente de verdad.** Se conservan por trazabilidad:
> explican qué se intentó, qué se decidió y por qué. No se citan como estado
> actual del sistema.

## Regla de uso

- Si necesitás saber **qué es cierto hoy**, leé `docs/estado.md` y el código.
- Si necesitás saber **por qué se llegó hasta acá**, leé estos archivos.
- Nunca copies una cifra, un checklist o una afirmación de "terminado" desde
  `_archivo/` sin re-verificarla en código o en la base.

## Contenido

| Carpeta | Qué hay | Por qué se archivó |
|---|---|---|
| `planes/` | `PLAN_MAESTRO_ERP_V2.md`, `IMPLEMENTACION.MD`, `PLAN_90_DIAS.md`, `PLAN_DESARROLLO_AUTONOMO.md`, `PLAN_DESARROLLO.md`, `plan-migraciones-0015.md` | Planes de producto y de proyecto. Su diseño funcional sobrevive; sus cifras y su estado, no |
| `mvp/` | `ARQUITECTURA_SPECS.md`, `prompts.md`, `MODULOS.md`, `PENDIENTES_ERP.md`, `SETUP.md`, `DEPLOY.md`, `UPGRADE_SUPABASE_PRO.md`, `CATALOGO_KPIS_Y_FREIGHT_SCORE.md`, `KPIS.md` | Documentación del MVP legacy. Describen `public`, no el sistema completo |
| raíz | `modulos.md`, `cutover.md`, `cutover-ejecutado-2026-11-01.md`, `retiro-legacy-modulos.md` (archivados 2026-11-12) | Documentación del período de coexistencia y cutover, ejecutado y cerrado. Se conservan como historia de la transición |

## Reemplazos

| Documento archivado | Reemplazado por |
|---|---|
| `PENDIENTES_ERP.md` | `docs/estado.md` |
| `SETUP.md` | `docs/operacion/setup-local.md` |
| `CUTOVER_CHECKLIST` (movido, no archivado) | `docs/_archivo/cutover.md` (el cutover ya se ejecutó; no hay operación vigente) |
| `DEPLOY.md`, `UPGRADE_SUPABASE_PRO.md` | `docs/operacion/deploy-cloud.md` |
| `MODULOS.md`, `modulos.md` (de `arquitectura/`) | `docs/mapa-sistema.md` (vigente) + `docs/_archivo/modulos.md` (histórico) |
| `KPIS.md`, `CATALOGO_KPIS_Y_FREIGHT_SCORE.md` | `docs/negocio/kpis.md` |
| `cutover.md` (de `operacion/`) | — (operación ejecutada; el registro está en `docs/_archivo/cutover-ejecutado-2026-11-01.md`) |
| `cutover-ejecutado-2026-11-01.md` (de `operacion/`) | — (histórico de la Ola D; permanece archivado como evidencia) |
| `retiro-legacy-modulos.md` (de `negocio/`) | `docs/arquitectura/retiro-legacy.md` |
| `NUCLEO_V2_DISENO.md` (movido) | `docs/arquitectura/nucleo-diseno.md` |
| `UAT_PILOTO.md` (movido) | `docs/qa/uat-piloto.md` |
| `PLAN_MAESTRO` §4-21 | `docs/arquitectura/capacidades-objetivo.md` |
| `IMPLEMENTACION.MD` §1-4 | `docs/negocio/contexto.md` |
| `PLAN_DESARROLLO_AUTONOMO` §5 | `docs/desarrollo/backlog.md` |
| `plan-migraciones-0015.md` | `docs/datos/catalogo-migraciones.md` |
| `ARQUITECTURA_SPECS.md` | `docs/arquitectura/modelo-datos.md` |
| `prompts.md` | sin reemplazo: la paleta vive en `frontend/src/app/globals.css` |

Fecha de archivo: **2026-10-29**.
