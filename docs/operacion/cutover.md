# Cutover `public` → `nucleo` — runbook

> **Pregunta que responde:** ¿cómo se pasa el legacy a sólo lectura sin perder datos?
> **Dueño:** `orquestador` · **Verificado:** 2026-10-29 · **Método:** lectura de `scripts/` + `0014`/`0015`
> **Caduca si:** cambia `cutover_legacy.py`, una migración ≥ 0015 o el flag de congelamiento.
> **Re-verificar con:** `grep -n "add_argument" scripts/cutover_legacy.py`

---

## ⚠️ Estado real

| # | Hecho | Evidencia |
|---|---|---|
| 1 | **El script es compatible con `0015`.** Migra los viajes `confirmado` **sin recursos** (`tracto_id`, `rampla_id`, `chofer_id` en `NULL`), precisamente para no disparar el `23514` documental | `scripts/cutover_legacy.py:6-13,378-401` |
| 2 | El comentario de `0015` que declara "incompatible" al script describe una **versión anterior**; quedó obsoleto | `0015:130-143` vs `cutover_legacy.py:6-13` (deuda D-05) |
| 3 | Consecuencia operativa: **todo viaje migrado queda sin recursos** y debe reasignarse a mano con documentos reales | `cutover_legacy.py:294,398-401` |
| 4 | El congelamiento **falla en abierto**: si la consulta falla, `legacy_congelado()` devuelve `False` y las escrituras legacy se reanudan en silencio (RA-04) | `backend/app/nucleo/servicio_cutover.py:38-39` |
| 5 | `backup_pgdump.sh` es **cloud-only**: aborta si la URL no contiene el ref del proyecto en la nube — inservible para la base local | `scripts/backup_pgdump.sh:9,25-27` |

**Bloqueos reales antes de ejecutar:** resolver el fail-open (4) y usar el backup correcto (5).
La incompatibilidad con `0015` **no es un bloqueo**.

---

## 1. Antes del cutover (T-7 a T-1)

- [ ] Backup local con `scripts/restore_drill.sh` (**no** `backup_pgdump.sh`).
- [ ] Restore drill exitoso (`restore_ok`) y **comparación de conteos antes/después**.
- [ ] Suite backend completa en verde (`make test`) — hoy 🔴 no verificada.
- [ ] `tsc`, `eslint`, `next build` en verde.
- [ ] E2E Playwright en verde (`make e2e`) — 9 escenarios.
- [ ] UAT por rol firmada según `docs/qa/uat-piloto.md` (la tabla de evidencia está **vacía**).
- [ ] Los 8 roles creados y probados.
- [ ] Documentos de flota y choferes **vigentes y cargados en `nucleo.documentos`** (requisito de 0015).
- [ ] Licencias de conductor en clase **A5** (bloqueo de 0016).
- [ ] Tarifas y OC reales cargadas.
- [ ] Confirmado que no hay escrituras legacy en curso.
- [ ] Ventana comunicada a despacho, contabilidad y tesorería.

## 2. Dry-run

```bash
.venv/bin/python scripts/cutover_legacy.py --dry-run
```

- [ ] Revisar conteos de clientes, choferes, tractos, ramplas, documentos y viajes.
- [ ] **Los viajes abiertos se migran como `confirmado` y SIN recursos** (`tracto_id`, `rampla_id`, `chofer_id` en `NULL`) — decisión explícita del script: `scripts/cutover_legacy.py:6-7,294`.
- [ ] Confirmar que viajes facturados/cobrados/anulados no se migran.
- [ ] Revisar las tarifas/OC genéricas `MIG-*`.

## 3. Cutover

```bash
.venv/bin/python scripts/cutover_legacy.py --freeze
```

- [ ] Migración sin errores. **Si aparece `23514` por documentos faltantes, se está cumpliendo el bloqueo de §0** — no lo rodees.
- [ ] `nucleo.cutover_control.legacy_escritura_congelada = true`.
- [ ] `POST /api/v1/viajes` legacy devuelve **409 `CUTOVER_LEGACY_CONGELADO`**.
- [ ] `GET` legacy sigue disponible para consulta.
- [ ] Login y módulos `/nucleo` operan.
- [ ] **Reasignar recursos y documentos a cada viaje migrado** (§45 de la lista original): sin esto quedan viajes sin disponibilidad.

## 4. Validación posterior

- [ ] Crear un viaje nuevo en el núcleo.
- [ ] Asignar recursos y verificar que el `EXCLUDE` rechaza solapamientos.
- [ ] Completar checklist, registrar POD y cerrar.
- [ ] Emitir factura y registrar pago.
- [ ] Verificar alertas, tablero y auditoría.
- [ ] Confirmar que el legacy no recibe escrituras nuevas.
- [ ] Verificar el flag **consultando la base**, no el endpoint (por el fail-open).
- [ ] Backup posterior y restore drill posterior.

## 5. Rollback

1. Descongelar legacy — el campo `motivo` es obligatorio (5–500 caracteres):

   ```bash
   curl -X POST "$API/api/v1/nucleo/cutover/descongelar" \
     -H "Authorization: Bearer $TOKEN" \
     -H "X-Empresa-ID: $EMPRESA_ID" \
     -H "Content-Type: application/json" \
     -d '{"motivo":"Rollback del cutover: causa concreta y responsable"}'
   ```

   Contrato: `backend/app/nucleo/schemas.py:1793-1796` (sin `motivo` → **422**).

2. Alternativa directa en base: `update nucleo.cutover_control set legacy_escritura_congelada = false where id = true;`
3. Restaurar el backup previo en una base temporal y validar.
4. Reapuntar la aplicación al entorno anterior sólo con aprobación de gerencia/TI.
5. Registrar incidente y causa raíz en `docs/orquestacion/registro.md`.

**No** se borra ni el schema `nucleo` ni el legacy durante el rollback.

## 6. Después

- Actualizar `docs/estado.md`.
- Registrar la decisión en un ADR (`docs/arquitectura/adr/`).
- Abrir deuda: los viajes migrados sin recursos deben reasignarse.

## 7. Cómo desbloquear (decisión pendiente)

| Opción | Qué implica | Riesgo |
|---|---|---|
A | Cargar `nucleo.documentos` de tractos, ramplas y choferes **antes** del cutover | Alto si faltan documentos reales |
B | Migrar los viajes en `borrador`/`cotizado` **sin recursos** y asignar después | Medio: la operación queda a medio armar |
C | Agregar una vía de escape en la migración | **Rechazada**: sería fail-open, el mismo defecto que RA-04 |

Dueño de la decisión: **negocio + `datos`**. Registrada en `docs/negocio/preguntas.md`.

## 8. Responsables

| Rol | Nombre | Firma |
|---|---|---|
| Dueño / gerencia | | |
| TI / operador | | |
| Despacho | | |
| Contabilidad | | |
| Tesorería | | |
