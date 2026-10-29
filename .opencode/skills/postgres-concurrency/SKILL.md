---
name: postgres-concurrency
description: "Diseña y prueba garantías transaccionales del ERP TEI para reservas, disponibilidad, folios, pagos y transiciones de estado; cubre locks, EXCLUDE, aislamiento, condiciones de carrera y pruebas con conexiones reales."
---

# PostgreSQL concurrency — garantías, locks y carreras

## 1. Objetivo y ámbito

Impedir que dos operaciones concurrentes violen una regla de negocio: doble
asignación de tracto/rampla/chofer, doble pago, doble factura, folio duplicado,
transición ilegal o consumo de OC duplicado.

La pregunta correcta no es “¿el servicio consultó antes de escribir?”, sino
“¿qué impide que dos transacciones ganen a la vez?”.

## 2. Cuándo usarla

- Disponibilidad, reservas, bloqueos, mantenciones, descansos.
- Asignación/reasignación de viajes.
- Folios, pagos, facturas, notas de crédito.
- Aprobación de gastos y estados.
- Cualquier “primero consulto, luego inserto”.

## 3. Contexto y precondiciones

- `AGENTS.md` y `database-safety`.
- PostgreSQL local con las migraciones aplicadas.
- Dos conexiones reales para la prueba.
- Conocimiento del invariante exacto y de todos los escritores.
- No probar contra datos reales.

## 4. Procedimiento

1. **Escribe el invariante** en una frase:
   “Un tracto no puede tener dos reservas activas solapadas en `[inicio, fin)`”.
2. **Enumera todos los escritores**: legacy, núcleo, scripts, jobs, seeds.
3. **Elige el mecanismo**:
   - constraint (`EXCLUDE`, `UNIQUE` parcial, `CHECK`) para reglas estructurales;
   - lock (`FOR UPDATE`, advisory) para coordinar decisiones;
   - aislamiento/retry para conflictos de serialización;
   - idempotency key/unique para reintentos.
4. **Diseña el orden de locks** para evitar deadlocks (orden lexicográfico de
   recursos).
5. **Implementa la transacción** con el alcance mínimo.
6. **Traduce errores**: `23P01` (exclusion), `23505` (unique), `40001`
   (serialization) → `409` de dominio, no `500`.
7. **Prueba con dos conexiones**:
   - sesión A abre transacción y bloquea;
   - sesión B intenta la operación;
   - verifica que B espera o falla según el diseño;
   - libera A y comprueba el estado final.
8. **Agrega regresión** que falle si se elimina la garantía.

## 5. Comprobaciones verificables y patrones del repo

El núcleo usa:

```sql
exclude using gist (tracto_id with =, ventana with &&)
where (recurso_tipo = 'tracto' and activa);
```

y locks de asesoría por recurso:

```sql
select pg_advisory_xact_lock(hashtextextended(:clave, 0));
```

Además, `SELECT ... FOR UPDATE` sobre el viaje y `WHERE version = :version` para
concurrencia optimista.

Verifica que:

- la fila de reserva tenga exactamente un recurso tipado (sin `NULL` ambiguo);
- el `EXCLUDE` cubra tracto, rampla y chofer por separado;
- el buffer esté dentro de la ventana;
- el trigger mueva/desactive reservas en la misma transacción;
- el legacy no escriba fuera del libro (hoy no lo hace).

## 6. Prueba de concurrencia (esquema)

```python
# Dos conexiones/transacciones reales, no dos llamadas secuenciales.
with conn_a.transaction():
    conn_a.execute("select ... for update")
    # insertar/validar
    with conn_b.transaction():
        # debe bloquear o fallar con SQLSTATE 23P01
        ...
```

Comprueba:

- el segundo intento no “pasa” silenciosamente;
- el error es el esperado;
- no queda una reserva activa duplicada;
- la primera transacción puede commitear;
- el estado final es consistente tras rollback.

## 7. Errores frecuentes

- `SELECT` + `if` + `INSERT` sin lock ni constraint.
- `EXCLUDE` con columnas nulas.
- Lock solo en Python (`threading.Lock`) o en el proceso.
- Tomar locks en orden distinto según el recurso → deadlock.
- Probar concurrencia con dos requests secuenciales.
- Capturar `IntegrityError` y devolver 200.
- Reintentar sin idempotencia → duplicado.
- Asumir que el legacy respeta el libro del núcleo.
- Ignorar el buffer o los bordes `[inicio, fin)`.
- Usar `date` en vez de `timestamptz` para ventanas.

## 8. Criterios de aceptación

- La base rechaza la violación aunque el servicio falle.
- Hay una prueba con dos conexiones que lo demuestra.
- El error de dominio es estable y el HTTP es 409.
- No hay deadlocks en el orden normal.
- El legacy y el núcleo tienen una estrategia explícita de convivencia.
- La regresión falla si se quita la constraint/lock.

## 9. Formato de entrega

```text
## Invariante
## Escritores
## Mecanismo
## Transacción y orden de locks
## Prueba de concurrencia
## Errores y códigos
## Riesgos de convivencia legacy/núcleo
```

## 10. Referencias

- PostgreSQL explicit locking: <https://www.postgresql.org/docs/current/explicit-locking.html>
- PostgreSQL transaction isolation: <https://www.postgresql.org/docs/current/transaction-iso.html>
- PostgreSQL `CREATE TABLE ... EXCLUDE`: <https://www.postgresql.org/docs/current/sql-createtable.html>
- `nucleo.reservas_recurso` en `supabase/migrations/0004_nucleo_operacional.sql`
