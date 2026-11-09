# Dataset demo — empresa de 40 camiones (tenant TEI)

> **Solo local. Datos 100 % ficticios. No ejecutar en producción.**
> Generado el 2026-11-02 en la base `postgres` de Supabase local, tenant
> `TEI` (`empresa_id = 11111111-1111-1111-1111-111111111111`).
> Nombres de personas, razones sociales, RUT, patentes, teléfonos y correos son
> **inventados**. Cualquier parecido con una persona o empresa real es
> coincidencia; no se usaron marcas reales.

## 1. Qué se cargó

| Entidad | Cantidad | Nota |
|---|---|---|
| Tractos | **40 nuevos** (43 con los 3 del seed) | Volvo/Scania/Mercedes/Kenworth, 2016–2024, 28–32 t |
| Ramplas | **44 nuevas** (47) | planas, sider, refrigeradas, portacontenedores, cisternas, graneleras, cama baja |
| Choferes | **45 nuevos** (48) | licencia A5; 2 en vacaciones |
| Clientes | **14 nuevos** (17) | retail, minería, salmón, cemento, agro, construcción, química, forestal |
| Tarifas | **18** | modalidades viaje, km y tonelada |
| Órdenes de compra | **28 nuevas** (31) | 1 anulada, 14 vencidas, 16 parciales |
| Viajes | **754 demo** (759 con los 5 preexistentes) | 2026-08-01 → 2026-11-16 |
| Facturas | **133** | 108 pagadas, 15 vencidas, 7 emitidas, 3 parciales |
| POD | **669** | receptor, firma y fotos ficticias; 4 con daños |
| Gastos | **1.995** | combustible, peajes, viáticos, estadías; 1 rechazado |
| Mantenimientos | **25** | 2 tractos en taller; 1 fuera de pauta y 1 anulado |
| Incidentes | **10** | 2 abiertos de severidad alta, 1 abierto medio, 7 cerrados/resueltos |
| Precios diésel | **13** | una fila semanal |
| Reglas de entidad | **3** | 2 clientes + 1 chofer |
| Directivas | **2** | `directiva_cobranza_recordatorio`, `directiva_prioridad_sobrepeso` |
| Solicitud de chat | **1 pendiente** | `anular_viaje` sobre `VJ-2026-203007` |

### Viajes por estado

| Estado | Viajes |
|---|---:|
| `cobrado` | 534 |
| `facturado` | 112 |
| `anulado` | 61 |
| `cerrado` | 25 |
| `confirmado` | 9 |
| `asignado` | 6 |
| `en_ruta` | 5 |
| `en_descarga` | 4 |
| `pod_pendiente` | 3 |

## 2. Imperfecciones deliberadas (para que no sea un demo “perfecto”)

| Imperfección | Dónde verla |
|---|---|
| **91 viajes con llegada tarde** (2–30 h sobre lo planificado) | `/expediente`, comparar `fin_real` vs `fin_planificado` |
| **15 facturas vencidas** (hasta 45 días) | `/cobranza`, aging |
| **3 facturas parciales** y **1 nota de crédito** | `/cobranza`, detalle de factura |
| **2 incidentes abiertos de severidad alta** + 1 medio | `/expediente/{id}`, panel de incidentes |
| **2 tractos en taller** y **2 choferes en vacaciones** | `/flota`, `/maestros` |
| **25 mantenimientos**, uno fuera de pauta y uno anulado | `/mantenimiento` |
| **1 gasto rechazado** con motivo | `/expediente/{id}`, panel de gastos |
| **1 OC anulada** y **1 vencida** | `/comercial`, órdenes de compra |
| **2 OC al ~99,5 % del límite** | `/comercial`, consumo de OC |
| **61 viajes anulados** con motivo | `/expediente`, filtro `anulado` |
| **4 POD con daños** declarados | detalle del viaje, POD |
| **1 viaje cerrado sin POD** | `/expediente`, estado `cerrado` |
| **1 viaje con recargo por estadía** | detalle del viaje |

## 3. Escenario para el chat

- La **solicitud pendiente** `demo-chat-anulacion-001` está en
  `/agente/buzon` y apunta al viaje **`VJ-2026-203007`** (estado `asignado`).
  Al aprobarla, el viaje pasa a `anulado` y se liberan sus reservas.
- El **Gerente** puede leer el contexto: “Dame el contexto de la empresa: viajes
  por estado, configuración vigente y reglas abiertas.”
- La **Secretaria** puede consultar viajes y crear nuevas solicitudes; no
  ejecuta nada hasta que el dueño apruebe.
- El **muro de pago** está activo para WhatsApp: no se creó
  `tenant_suscripciones`, así que una petición de WhatsApp debe responder con
  el flujo de **upsell**, no ejecutar.

## 4. Cómo ejecutar

```bash
cd /Users/pc/Desktop/Informatica/TRANSTEI/TRANSTEI

# 1) Ver el plan sin escribir nada
.venv/bin/python scripts/seed_demo_transporte.py --dry-run

# 2) Cargar (idempotente: un segundo run no duplica)
.venv/bin/python scripts/seed_demo_transporte.py

# 3) Borrar SOLO la data demo y volver a cargarla
.venv/bin/python scripts/seed_demo_transporte.py --reset
```

`DATABASE_URL` permite apuntar a otra base local; por defecto usa
`postgresql://postgres:postgres@127.0.0.1:54322/postgres`.

### Qué hace `--reset`

- Borra solo filas con `created_by = 'demo'` del tenant TEI.
- **No toca** los 3 tractos, 3 ramplas, 3 choferes, 3 clientes, 5 viajes, 3
  tarifas ni 3 OC del seed original.
- Conserva por FK **3 reglas de `tenant_reglas_entidad`** y los 2 clientes/1
  chofer que referencian. Esas reglas no se pueden borrar por el trigger de
  inmutabilidad (`INV-TEN05`); si necesitas un reset total, restaura un backup.
- Desactiva y reactiva los triggers append-only dentro de la misma transacción;
  si falla, el `rollback` los deja como estaban.

## 5. Verificación

```sql
-- Viajes por estado
select estado::text, count(*) from nucleo.viajes
 where empresa_id = '11111111-1111-1111-1111-111111111111'
 group by estado order by 2 desc;

-- Solapes en el libro de ocupación (debe ser 0)
select count(*)
  from nucleo.reservas_recurso a
  join nucleo.reservas_recurso b
    on a.empresa_id = b.empresa_id and a.id < b.id
   and a.activa and b.activa and a.recurso_tipo = b.recurso_tipo
   and a.ventana && b.ventana
   and ((a.tracto_id is not null and a.tracto_id = b.tracto_id)
     or (a.rampla_id is not null and a.rampla_id = b.rampla_id)
     or (a.chofer_id is not null and a.chofer_id = b.chofer_id));

-- Facturas vencidas
select count(*) from nucleo.facturas_nucleo
 where empresa_id = '11111111-1111-1111-1111-111111111111' and estado = 'vencida';
```

## 6. Límites y advertencias

- El seed corre como `postgres` (BYPASSRLS); no prueba RLS. La app usa
  `tei_app` y sigue sujeta a las políticas.
- El volumen y las fechas están fijados a `TEI_DEMO_HOY = 2026-11-02`. Si
  cambias la fecha del sistema, ajusta esa constante en el script.
- No se creó `tenant_suscripciones` a propósito (demo de upsell).
- No se usan nombres reales. Si agregas clientes/choferes, mantén la regla.
- El script no crea usuarios de login; usa el `admin@tei.local` existente.
