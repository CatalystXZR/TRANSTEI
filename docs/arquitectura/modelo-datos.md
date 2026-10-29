# Modelo de datos — qué tablas existen y qué garantizan

> **Pregunta que responde:** ¿dónde se guarda cada dato, con qué PK/FK y qué constraints duras lo protegen?
> **Dueño:** arquitectura · **Verificado:** 2026-10-29 · **Método:** lectura estática de DDL (`supabase/migrations/0001`–`0019`) y de `backend/app/nucleo/models.py`; sin base ni ejecución.
> **Caduca si:** se agrega, elimina o altera una tabla, constraint o trigger; o si una migración nueva cambia un tipo.
> **Re-verificar con:** `grep -rh "create table" supabase/migrations | wc -l` y `grep -n "class .*Base\\|__tablename__" backend/app/nucleo/models.py`

---

## 1. Reglas de lectura

- **`public` es el legacy** (17 tablas, `0001`–`0003`), **sin `empresa_id`** y sin libro de ocupación.
- **`nucleo` es el destino** (31 tablas creadas en `0004`–`0014`; `0015`–`0019` agregan reglas, no tablas), multiempresa por `empresa_id` y FKs compuestas `(empresa_id, id)`.
- La DDL es la fuente de verdad, no los modelos: `models.py` solo mapea (`backend/app/nucleo/models.py:1-14`) y `create_all` está prohibido.
- Dinero: `numeric`; eventos: `timestamptz`; rangos del núcleo: `tstzrange` semiabierto `[inicio, fin)` (`0004:14-16`).
- No se dibuja el ERD completo: se listan tablas por dominio y solo las relaciones que imponen garantías.

Conteo de tablas (🟢 verificado por DDL, no por base):
`0004`=15, `0005`=1, `0007`=5, `0009`=1, `0011`=2, `0012`=1, `0013`=5, `0014`=1 → **31**.

---

## 2. Legacy `public` — 17 tablas

| Tabla | PK | FKs / unicidad / checks relevantes | Migración |
|---|---|---|---|
| `usuarios` | `id` | `auth_id` único → `auth.users`; rol global `admin/operacion/contabilidad`; trigger `handle_new_user` | `0001:36-45,248-262` |
| `clientes` | `id` | `rut` único; sin `empresa_id` | `0001:47-58` |
| `choferes` | `id` | `rut` único; `porcentaje_produccion` 0–1; `vencimiento_licencia` como fecha | `0001:60-70` |
| `tractos` | `id` | `patente` única; **sin** peso/tara/capacidad | `0001:72-84` |
| `ramplas` | `id` | `patente` única; **sin** capacidad | `0001:86-94` |
| `viajes` | `id` | 4 FKs `NOT NULL` (cliente, chofer, tracto, rampla); estado `programado/en_ruta/finalizado/facturado`; **sin** exclusión de solape | `0001:97-112` |
| `gastos_viaje` | `id` | FK viaje `on delete cascade`; `monto >= 0` | `0001:114-125` |
| `facturas` | `id` | FK cliente; `unique (numero_sii, cliente_id)`; estados `pendiente/pagada/anulada` | `0001:127-143` |
| `factura_viaje` | `(factura_id, viaje_id)` | FKs; sin monto ni empresa | `0001:145-149` |
| `anticipos_chofer` | `id` | FK chofer; `monto > 0`; **sin** unique de idempotencia (SEC-007) | `0001:151-159` |
| `ajustes_liquidacion` | `id` | FK chofer; `monto >= 0` | `0001:161-169` |
| `liquidaciones` | `id` | FK chofer; `unique (chofer_id, mes)`; estados `borrador/emitida` | `0001:171-186` |
| `pautas_mantenimiento` | `id` | `intervalo_km > 0` | `0001:189-196` |
| `mantenimientos` | `id` | FKs tracto/pauta; `km` obligatorio | `0001:199-209` |
| `configuracion` | `clave` | pares clave/valor (IVA y alertas) | `0001:212-215` |
| `_migraciones` | `nombre` | metadato de migraciones aplicadas | `0002:6-9` |
| `kpis` | `id` | KPI por fórmula editable; 4 filas de seed | `0003:5-20,31-71` |

RLS legacy: habilitado en 15 tablas de `0001` y en `kpis`, con **una sola política** (`usuarios`, `0001:267-285`). No es aislamiento multiempresa: no existe `empresa_id` en ninguna tabla.

---

## 3. Núcleo `nucleo` — 31 tablas por dominio

### 3.1 Maestros y organización (6)

| Tabla | PK | FKs clave | Constraints duras | Migración |
|---|---|---|---|---|
| `empresas` | `id` | — | `codigo` único; RUT normalizado único; moneda ISO-4217; `buffer_operacional_min` 0–1440; `dias_margen_documentos` 0–90 | `0004:102-137` |
| `usuarios_empresa` | `id` | `empresa_id → empresas` | `unique (empresa_id, auth_id)`; rol enum de 8 valores; índice parcial por `auth_id` activo | `0004:139-153` |
| `clientes` | `id` | `empresa_id → empresas` | `unique (empresa_id, id)`; RUT normalizado único por empresa; `dias_pago` 0–365; crédito ≥ 0 | `0004:158-186` |
| `tractos` | `id` | `empresa_id → empresas` | patente y VIN únicos por empresa; `tara < peso_bruto`; `capacidad ≤ peso_bruto − tara`; estado enum | `0004:191-230` |
| `ramplas` | `id` | `empresa_id → empresas` | patente/VIN únicos por empresa; capacidad > 0; temperaturas coherentes | `0004:235-277` |
| `choferes` | `id` | `empresa_id → empresas` | RUT y licencia únicos por empresa; `sueldo_base ≥ 0`; `porcentaje_comision` 0–1 (default 0.10 desde `0017:47-48`; alineación piloto `0019:44-67`) | `0004:282-321` |

### 3.2 Operación (8)

| Tabla | PK | FKs clave | Constraints duras | Migración |
|---|---|---|---|---|
| `viajes` | `id` | `(empresa_id, cliente_id/orden_compra_id/tarifa_id/tracto_id/rampla_id/chofer_id)` compuestas | `unique (empresa_id, numero_viaje)`; `ventana` con `lower = inicio_planificado`; recursos completos fuera de borrador/cotizado/confirmado/anulado; peso, temperaturas, UN peligrosa, anulación con motivo | `0004:542-698` |
| `reservas_recurso` | `id` | `(empresa_id, tracto/rampla/chofer)` compuestas; `viaje_id → viajes` | **3 `EXCLUDE USING gist`** por recurso y ventana, parcial `activa`; un solo recurso por fila; ventana finita; no se borra | `0004:703-767` + `0006:9-18` |
| `transiciones_viaje` | `(estado_origen, estado_destino)` | — | máquina de estados explícita; 29 transiciones sembradas; sin reapertura de `cerrado`/`facturado` | `0004:772-808` |
| `folio_contador` | `(empresa_id, tipo, periodo)` | `empresa_id → empresas` | `ultimo ≥ 0`; `siguiente_folio()` con `insert … on conflict do update` (atómico) | `0004:490-517` |
| `viaje_paradas` | `id` | `(empresa_id, viaje_id)` | `unique (viaje_id, orden)`; `orden ≥ 1` | `0007:17-51` |
| `viaje_checklist` | `id` | `(empresa_id, viaje_id)` | ítem obligatorio/completado; evidencia URL | `0007:63-92` |
| `viaje_eventos` | `id` | `(empresa_id, viaje_id)` | **append-only**: trigger rechaza UPDATE/DELETE | `0007:102-133` |
| `viaje_incidentes` | `id` | `(empresa_id, viaje_id)` | severidad/estado libres (texto), sin catálogo en DB | `0007:139-175` |

### 3.3 Comercial (4)

| Tabla | PK | FKs clave | Constraints duras | Migración |
|---|---|---|---|---|
| `tarifas` | `id` | `(empresa_id, cliente_id)` | `unique (empresa_id, cliente_id, codigo)`; vigencia coherente; precio/mínimo ≥ 0; moneda ISO | `0004:377-416` |
| `ordenes_compra` | `id` | `(empresa_id, cliente_id)`; centro de costo | `unique (empresa_id, cliente_id, numero_oc)`; `monto_consumido ≤ autorizado + sobregiro`; vigencia | `0004:421-457` |
| `ordenes_compra_lineas` | `id` | `(empresa_id, orden_compra_id)`; tarifa/centro | `unique (orden_compra_id, numero_linea)`; montos ≥ 0; FK OC `on delete cascade` | `0004:459-485` |
| `centros_costo` | `id` | `empresa_id → empresas` | `unique (empresa_id, codigo)`; código/nombre no vacíos | `0005:16-42` |

### 3.4 Documentos (3)

| Tabla | PK | FKs clave | Constraints duras | Migración |
|---|---|---|---|---|
| `documentos` | `id` | `(empresa_id, tracto/rampla/chofer)` compuestas | un solo recurso por fila; `vence_en ≥ emitido_en`; **índice único parcial** `(recurso, tipo) where es_vigente`; no se borra; un documento nuevo desactiva el anterior | `0004:326-372,1704-1751` |
| `viaje_documentos` | `id` | `(empresa_id, viaje_id)` | archivo_url obligatoria; hash SHA-256 y tamaño opcionales | `0007:181-211` |
| `pod` | `id` | `(empresa_id, viaje_id)` | `unique (viaje_id)`; firma obligatoria; fotos JSON array; lat/lon acotadas; no se borra | `0009:8-58` |

### 3.5 Finanzas (8)

| Tabla | PK | FKs clave | Constraints duras | Migración |
|---|---|---|---|---|
| `viaje_gastos` | `id` | `(empresa_id, viaje_id)` | `monto_neto` generado (`monto_total − iva`); estado `pendiente/aprobado/rechazado`; no hay borrado lógico obligatorio | `0011:29-83` |
| `precios_diesel` | `id` | `empresa_id → empresas` | `unique (empresa_id, fecha)`; precio ≥ 0 | `0011:11-24` |
| `configuracion_costos` | `id` | `empresa_id` **único** | margen objetivo 0–0.95; rendimiento > 0; una fila por empresa | `0012:8-32` |
| `facturas_nucleo` | `id` | `(empresa_id, cliente_id/orden_compra_id)` | `unique (empresa_id, numero_factura)`; `total` generado (`neto + iva`); estados acotados; vencimiento ≥ emisión | `0013:10-49` |
| `factura_viajes` | `id` | `(empresa_id, factura_id/viaje_id)` | `unique (empresa_id, viaje_id)` → **un viaje en una sola factura**; monto ≥ 0 | `0013:54-73` |
| `pagos_nucleo` | `id` | `(empresa_id, factura_id)` | `monto > 0`; método en catálogo; pagos parciales permitidos | `0013:78-107` |
| `notas_credito_nucleo` | `id` | `(empresa_id, factura_id)` | `unique (empresa_id, numero)`; `monto > 0`; motivo no vacío; estado `aplicada/anulada` | `0013:112-134` |
| `promesas_pago_nucleo` | `id` | `(empresa_id, factura_id)` | `monto > 0`; estado `pendiente/cumplida/incumplida` | `0013:139-158` |

### 3.6 Auditoría y cutover (2)

| Tabla | PK | FKs clave | Constraints duras | Migración |
|---|---|---|---|---|
| `auditoria` | `id` bigint identity | sin FKs (histórico) | `operacion in (INSERT, UPDATE, DELETE)`; triggers de inmutabilidad rechazan UPDATE/DELETE; `service_role` solo `select/insert` | `0004:813-892,1889-1891` |
| `cutover_control` | `id` boolean (`check (id)`) | — | fila singleton sembrada en `false`; `legacy_escritura_congelada` default `false` | `0014:8-19` |

---

## 4. Relaciones críticas (no es un ERD)

1. **Tenant por FK compuesta.** Todo dato de negocio referencia `empresas(id)` y, cuando apunta a otra tabla, lo hace con `(empresa_id, id)`. Ejemplo: `viajes` → cliente/OC/tarifa/tracto/rampla/chofer (`0004:646-657`). Una FK simple permitiría cruzar empresas; la compuesta no.
2. **Viaje ↔ reservas.** El viaje no inserta reservas: lo hace el trigger `fn_viaje_reservas` al tener los tres recursos (`0015:183-238`), con una fila por recurso y la misma `ventana`. La FK `viaje_id → viajes(id)` es simple (`0004:727-728`); la coherencia de empresa la valida `fn_reserva_validar` (`0004:1653-1690`).
3. **Ocupación única.** Tres `EXCLUDE` cubren tracto, rampla y chofer por separado (`0004:744-757`). Una mantención o un descanso compiten en el mismo libro (`0006:9-16`).
4. **Documento vigente único.** El índice parcial impide dos versiones vigentes del mismo tipo para el mismo recurso (`0004:362-370`); el trigger desactiva la anterior (`0004:1704-1741`).
5. **Factura ↔ viaje.** `factura_viajes` tiene `unique (empresa_id, viaje_id)` (`0013:63`): un viaje no puede facturarse dos veces. `facturas_nucleo.total` es columna generada (`0013:21`).
6. **Folio atómico.** `siguiente_folio` usa `insert … on conflict … do update … returning` (`0004:498-517`); no hay `max()+1` en Python.
7. **Auditoría inmutable.** `fn_auditoria` escribe `datos_antes/después` y `fn_auditoria_inmutable` rechaza cualquier UPDATE/DELETE (`0004:830-892`). Cobertura: tablas con trigger explícito; **no** cubre `transiciones_viaje`, `folio_contador` ni `cutover_control` (RA-07).

---

## 5. Garantías duras que no dependen del servicio

| Garantía | Mecanismo | Evidencia |
|---|---|---|
| No solapar tracto/rampla/chofer | `EXCLUDE USING gist` × 3 | `0004:744-757` |
| No asignar sin documentos vigentes | trigger `trg_viajes_05_documentos` → `validar_documentos_recurso` | `0015:247-313`; `0004:1019-1104` |
| Solo licencia A5 asignable | trigger `trg_viajes_03_licencia_a5` | `0016:193-255` |
| No reabrir un viaje anulado/cerrado | `fn_viaje_transicion` + tabla de transiciones | `0004:1511-1547,779-808` |
| Congelar dinero al iniciar ejecución | `fn_viaje_proteccion` | `0004:1452-1509` |
| No facturar sin OC vigente y del mismo cliente | `fn_viaje_facturacion` | `0004:1387-1449` |
| Consumo de OC recalculado y serializado | `fn_oc_recalcular` con `for update` | `0004:1550-1597` |
| Folio sin colisión concurrente | `folio_contador` + `on conflict` | `0004:490-517` |
| Auditoría no editable | triggers `before update or delete` | `0004:880-892` |
| Una factura por viaje | índice único parcial | `0013:63` |

---

## 6. Lo que NO se pudo verificar 🔴

| Afirmación | Por qué no | Cómo se cierra |
|---|---|---|
| Que las 19 migraciones están aplicadas y el esquema real coincide con el DDL | Sin acceso a PostgreSQL (`127.0.0.1:54322` no confirmado) y sin shell | `select version from supabase_migrations.schema_migrations order by version;` |
| Que `models.py` no tiene deriva respecto de la DDL | Solo lectura comparativa; no hay test de deriva | `alembic check` no aplica; consulta `information_schema.columns` vs modelos, o `supabase db reset` en copia local |
| Que los `EXCLUDE` rechazan dos transacciones simultáneas | Requiere dos conexiones reales | Prueba concurrente que espere SQLSTATE `23P01` |
| Rol efectivo del backend y su relación con RLS | `DATABASE_URL` no verificada (no se lee) | `select current_user, rolbypassrls from pg_roles where rolname = current_user;` |

---

*Fuentes de apoyo (no autoridad): `docs/_archivo/planes/PLAN_DESARROLLO.md:40-61` lista las 15 tablas legacy y coincide con `0001`; `docs/_archivo/mvp/ARQUITECTURA_SPECS.md` es especificación de UI y no define esquema. Toda afirmación de este documento se contrastó contra la DDL real.*
