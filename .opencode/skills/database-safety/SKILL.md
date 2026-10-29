---
name: database-safety
description: "Procedimiento seguro para inspeccionar el esquema PostgreSQL, diseñar migraciones, evaluar datos afectados, transacciones, rollback y restauración del ERP TEI sin perder trazabilidad ni romper public/nucleo."
---

# Database safety — esquema, migraciones y recuperación

## 1. Objetivo y ámbito

Cambiar la base de datos sin perder datos, trazabilidad ni capacidad de volver
atrás. Cubre DDL, constraints, índices, backfills, RLS, migraciones y restore.

## 2. Cuándo usarla

- Antes de crear o modificar una migración.
- Antes de un backfill, cambio de tipo o borrado lógico.
- Al investigar integridad, locks, RLS o rendimiento.
- Antes de un cutover o restore drill.
- Cuando un documento y el DDL no coinciden.

## 3. Contexto y precondiciones

- `AGENTS.md` leído.
- Repo en rama de trabajo; `git status` revisado.
- Base local disponible (`make db-up`) o autorización explícita para otro entorno.
- Backup reciente si hay datos que no se pueden reconstruir.
- Migraciones aplicadas identificadas (`supabase/migrations/`).
- Rol y permisos de conexión conocidos (no leas `.env`; usa el entorno).

## 4. Procedimiento

### 4.1 Inspección (solo lectura)

```bash
psql "$DATABASE_URL" -c "\dn"
psql "$DATABASE_URL" -c "\dt public.*"
psql "$DATABASE_URL" -c "\dt nucleo.*"
psql "$DATABASE_URL" -c "\d+ nucleo.reservas_recurso"
```

Si `psql` no está disponible o no hay autorización, usa el código/migraciones y
declara la limitación. Nunca imprimas la URL con credenciales.

Revisa:

- columnas, tipos, nulabilidad, defaults;
- FKs simples y compuestas;
- `CHECK`, `UNIQUE`, `EXCLUDE`, índices parciales;
- triggers y funciones;
- políticas RLS y rol efectivo;
- migraciones que crean cada objeto.

### 4.2 Impacto

1. ¿Qué datos existen y cuántos se afectan? Usa conteos, no suposiciones.
2. ¿Hay filas nulas, duplicadas, huérfanas o fuera de rango?
3. ¿El cambio bloquea tablas grandes? ¿Por cuánto?
4. ¿Afecta legacy, núcleo o ambos?
5. ¿Hay escritores concurrentes (API, scripts, jobs)?
6. ¿El cambio es reversible sin pérdida?

### 4.3 Diseño de migración

- Nueva migración numerada; no edites una aplicada.
- Transacción cuando el motor lo permita.
- Orden: crear objeto → backfill → validar → agregar constraint → limpiar.
- `NOT VALID` + `VALIDATE CONSTRAINT` para tablas grandes cuando aplique.
- Índices: `CREATE INDEX CONCURRENTLY` fuera de transacción si el volumen lo
  exige; documenta la excepción.
- Backfill por lotes, idempotente, con progreso y conteos.
- Rollback: DDL inverso y/o restauración; si no es posible, dilo antes.

### 4.4 Prueba

1. Aplica la migración en base local limpia o réplica.
2. Verifica objetos con `\d+` y una consulta funcional.
3. Prueba datos existentes y nuevos.
4. Prueba constraints con casos negativos.
5. Prueba concurrencia si hay locks/unicidad.
6. Ejecuta la suite de integración.
7. Registra comando y resultado.

### 4.5 Restore

- Un backup no verificado no es un backup.
- Restaura en base temporal, no sobre la original.
- Compara conteos y una consulta funcional antes/después.
- Verifica que la aplicación puede leer/escribir tras el restore.
- Documenta el tiempo y los pasos.

## 5. Comprobaciones verificables

- [ ] La constraint existe en PostgreSQL, no solo en SQLModel.
- [ ] La migración corre desde cero y sobre datos existentes.
- [ ] El rollback está escrito y probado, o la restauración está probada.
- [ ] No hay `NULL` que rompa un `EXCLUDE` o un `UNIQUE`.
- [ ] RLS tiene políticas y se probó con el rol real.
- [ ] El backfill es idempotente y tiene conteos.
- [ ] No se editó una migración aplicada.
- [ ] No se usó `create_all()` como migración.

## 6. Errores frecuentes

- `supabase db reset` contra datos que no son desechables.
- Editar una migración ya aplicada.
- Agregar `NOT NULL` sin backfill.
- `EXCLUDE` con columnas nulas.
- RLS habilitado sin políticas.
- Backfill sin transacción ni idempotencia.
- Índice que bloquea producción.
- Borrar filas en vez de desactivar/versionar.
- Restore que solo verifica que la base “abrió”.
- Declarar “rollback listo” sin ejecutarlo.

## 7. Criterios de aceptación

- DDL versionado y aplicado en local.
- Integridad impuesta en la base.
- Datos existentes compatibles.
- Rollback/restore documentado y probado.
- Pruebas de constraint y concurrencia ejecutadas.
- Impacto en `public`/`nucleo` explícito.

## 8. Formato de entrega

```text
## Objeto y motivo
## DDL/migración
## Datos afectados
## Rollback
## Pruebas ejecutadas
## Riesgos y límites
```

## 9. Referencias

- PostgreSQL DDL: <https://www.postgresql.org/docs/current/ddl.html>
- PostgreSQL constraints: <https://www.postgresql.org/docs/current/ddl-constraints.html>
- PostgreSQL `EXCLUDE`: <https://www.postgresql.org/docs/current/sql-createtable.html>
- Supabase migrations: <https://supabase.com/docs/guides/deployment/database-migrations>
- `supabase/migrations/` del repo.
