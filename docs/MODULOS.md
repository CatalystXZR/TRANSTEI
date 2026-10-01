# Módulos del sistema

Resumen de cada módulo: qué hace, reglas de negocio y permisos.

## Roles

| Rol | Descripción |
|---|---|
| **admin** | Dueño. Acceso total, incluido Configuración y KPIs |
| **operacion** | Secretaría. Catálogos, Viajes, Gastos, Facturación, Mantenimiento |
| **contabilidad** | Contador. Facturación, Cobranzas, IVA, Liquidaciones y lectura de catálogos |

## Módulos

### Dashboard (`/dashboard`)
KPIs dinámicos (configurables en `/kpis`), centro de alertas (vencimientos y facturas
vencidas) y tabla de viajes activos.

### Viajes (`/viajes`, `/viajes/[id]`)
Registro de fletes. Máquina de estados: **Programado → En Ruta → Finalizado → Facturado**
("Facturado" solo se asigna al asociar una factura). Validaciones: recursos activos,
un tracto no puede estar en dos viajes activos, fecha fin ≥ inicio, solo se eliminan
viajes programados. En el detalle se registran **gastos** con foto de boleta (Supabase
Storage) y se muestra la **rentabilidad** del viaje (según el KPI configurable).

### Clientes (`/clientes`)
CRUD con validación de RUT, días de pago e importación CSV.

### Choferes (`/choferes`)
CRUD con sueldo base, % de comisión y vencimiento de licencia. Importación CSV.

### Flota (`/flota`)
Tractocamiones y ramplas por separado. Semáforo de vencimientos (rev. técnica, seguro).

### Mantenimiento (`/mantenimiento`)
Pauta de mantenimiento por flota (aceite, filtros, engrase, frenos…) con intervalos en km.
Registro de mantenciones que actualiza el kilometraje. Estado por camión/ítem:
OK / Por vencer (≤ 5.000 km) / **Pendiente permanente** al superar el umbral.

### Facturación (`/facturacion`)
Asocia viajes finalizados a una factura emitida en el SII (el sistema no emite DTE).
Calcula neto, IVA (afecta/exenta) y total. Marca los viajes como facturados.

### Cobranzas (`/cobranzas`)
Semáforo de facturas pendientes: rojo (vencidas), amarillo (≤ 5 días), verde (al día).
Permite registrar el pago.

### IVA (`/iva`)
Cuadratura mensual: débito (facturas afectas) − crédito (gastos con IVA recuperable) =
monto a pagar el día 20.

### Liquidaciones (`/liquidaciones`)
Sueldo = Base + (% comisión × fletes del mes) + Bonos − Descuentos − Anticipos.
Genera PDF de liquidación (documento legal, plantilla reemplazable).

### Indicadores (`/kpis`) — solo admin
Constructor de KPIs con fórmula editable, catálogo de métricas, vista previa y reglas
de color. Detalle en `docs/KPIS.md`.

### Configuración (`/configuracion`) — solo admin
Parámetros: IVA %, alerta de mantención (km), alerta de vencimientos (días),
alerta de cobranza (días).

## Cálculos clave

- **Comisión chofer**: Σ fletes finalizados/facturados del mes × % del chofer
- **Rentabilidad viaje**: flete − gastos − comisión del chofer
- **IVA a pagar**: débito fiscal − crédito fiscal (del mes)
- **Próximo mantenimiento**: km última mantención + intervalo del ítem

## Permisos de escritura

| Módulo | admin | operacion | contabilidad |
|---|---|---|---|
| Catálogos | ✅ | ✅ | lectura |
| Viajes / Gastos | ✅ | ✅ | lectura |
| Facturación | ✅ | ✅ | ✅ |
| Cobranzas / IVA | ✅ | — | ✅ |
| Liquidaciones | ✅ | — | ✅ |
| Mantenimiento | ✅ | ✅ | lectura |
| KPIs / Configuración | ✅ | — | — |
