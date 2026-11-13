# Cutover legacy → núcleo — ejecución local 2026-11-01

> **Ámbito:** base **local** con datos **ficticios**. No es producción. No se tocó
> staging ni ningún entorno desplegado.
> **Decisión:** el dueño instruyó “continua con la ola D” (D-2).

## 1. Antes

- Backup: `backups/cutover_pre_20261101_115202.sql` (2,1 MB, `pg_dump` de la base local).
- Línea base: `make unit` 128 · `make test` 415 · `make e2e` 20/20.
- Dry-run: 0 maestros nuevos (ya consolidados por el seed), **6 pautas** de
  mantenimiento pendientes.

## 2. Procedimiento ejecutado (reproducible desde cero)

```bash
make db-reset                     # 0001–0027 + seed TEI + seed TES (config 19)
.venv/bin/python scripts/cutover_legacy.py --dry-run   # revisión
.venv/bin/python scripts/cutover_legacy.py --freeze    # migra y congela
make test-db && make unit && make test && make e2e
```

Resultado: `pautas_migradas: 6`, `legacy_escritura_congelada: true`.
Segunda ejecución: `pautas_migradas: 0` → **idempotente**.

## 3. Reconciliación `public` → `nucleo`

| Entidad | public | núcleo (TEI) | Δ |
|---|---|---|---|
| Pautas de mantenimiento | 6 | **6** | 0 |
| Clientes | 3 | 3 | 0 |
| Choferes | 3 | 3 | 0 |
| Tractos | 3 | 3 | 0 |
| Viajes | 0 | 5 (solo núcleo/seed) | 0 legacy pendientes |
| Liquidaciones / anticipos / ajustes | 0 | 0 | — |
| Mantenimientos | 0 | 0 | — |
| Facturas / gastos | 0 | 1 / 1 (solo núcleo) | — |

## 4. Verificaciones compensatorias (ADR-0005 §7)

| Condición | Resultado |
|---|---|
| 1. Legacy congelado | `nucleo.cutover_control.legacy_escritura_congelada = true`, motivo registrado |
| 2. DSN de plataforma explícito | `scripts/cutover_legacy.py` prioriza `PLATFORM_DATABASE_URL`; ejecutado con rol de plataforma (`postgres`, BYPASSRLS). Se añadió `0027` con los GRANTs que faltaban para los objetos 0024–0026 |
| 3. Verificación post-ejecución | 0 viajes `MIG-*` (no hubo viajes legacy abiertos); 0 reservas que reconciliar; constraints `EXCLUDE`/`CHECK` activos en tabla; diferencias de conteo 0 |
| 4. Auditoría declarada | 6 filas en `nucleo.auditoria` para `nucleo.pautas_mantenimiento` (trigger de auditoría de 0024) |
| 5. `MIG-*` | No se generaron (sin viajes migrados) |
| 6. Idempotencia y evidencia | 2.ª corrida 0 cambios; comando y salidas en este documento |

## 5. Rollback

1. Descongelar: `update nucleo.cutover_control set legacy_escritura_congelada = false where id = true;`
   (o `POST /api/v1/nucleo/cutover/descongelar` con motivo).
2. Restaurar el backup `backups/cutover_pre_20261101_115202.sql` si hace falta.
3. `make db-reset` deja el estado canónico (sin el cutover) y el cutover se puede
   re-ejecutar con `--freeze` (idempotente).

## 6. Límites y pendientes

- **No** se migraron datos de `public` que hoy están vacíos (liquidaciones,
  mantenimientos, facturas, gastos, anticipos, ajustes): no hay filas que trasladar.
  Si en otro entorno existen, requieren su propio mapeo (decisión de negocio).
- **Ola E pendiente:** retirar `public.usuarios` (el trigger `handle_new_user` sigue
  escribiendo ahí), el gate `LEGACY_SOLO_TEI`/`es_legacy` y el `DROP` físico de
  `public`. Requiere backup verificado + autorización explícita (destructivo).
- El rol de plataforma es hoy `postgres`; formalizar un rol `tei_platform` es deuda
  declarada (ADR-0005 R-3).
- El flag de congelamiento no tiene efecto sobre escritores porque ya no hay API
  legacy; se mantiene por el escritor de scripts y como registro del cutover.
