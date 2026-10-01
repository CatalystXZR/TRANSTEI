# Motor de KPIs — Guía de uso y extensión

## ¿Qué es?

Un motor que permite **crear indicadores (KPIs) desde la plataforma**, con una
fórmula editable, que el backend valida y calcula de forma segura. Los KPIs activos
con uso "Panel de control" aparecen como tarjetas en el Dashboard, con color según
sus umbrales. El KPI marcado como "Semáforo de rentabilidad de viaje" define el
color del formulario de Nuevo Viaje.

## Seguridad

- Las fórmulas **nunca** se convierten en SQL ni ejecutan código.
- Se evalúan con un intérprete propio (`app/services/kpi_engine.py`) que solo admite:
  números, métricas del catálogo, `+ - * / % **`, paréntesis, comparaciones
  (`< <= > >= =`), lógica (`Y`, `O`) y las funciones `SI`, `REDONDEAR`, `MIN`, `MAX`, `ABS`.
- Cualquier métrica o función fuera del catálogo produce un error claro; no se ejecuta.

## Sintaxis

```
SI(condicion, valor_si, valor_no)
REDONDEAR(x, decimales)
MIN(a, b, ...)   MAX(a, b, ...)   ABS(x)
```

Ejemplos:
- `margen_bruto / ingresos_mes * 100`
- `SI(ingresos_mes = 0, 0, margen_bruto / ingresos_mes * 100)`
- `cuentas_atrasadas > 0 Y cuentas_por_cobrar > 1000000` (devuelve 1 o 0)

`SI` evalúa **solo la rama elegida** (no hay divisiones por cero en la rama descartada).

## Catálogo de métricas

### Ámbito global (por período)
`ingresos_mes, gastos_mes, margen_bruto, margen_pct, cuentas_por_cobrar,
cuentas_atrasadas, iva_a_pagar, facturacion_mes, viajes_mes, viajes_activos,
flete_promedio, costo_mantenimiento_mes, mantenimientos_pendientes, vencimientos_30d,
comision_total_mes, costo_choferes_mes, choferes_activos`

### Ámbito viaje
`flete_viaje, gastos_viaje, comision_viaje, margen_viaje, margen_viaje_pct`

## Reglas de color

Cada KPI puede tener reglas `{operador, valor, color}`. Se aplica la **primera** regla
que se cumpla, en orden. Si ninguna aplica, el color es gris. Ejemplo:

```
<  10  → rojo
<  20  → amarillo
>= 20  → verde
```

## Cómo agregar una nueva métrica (desarrollador)

1. Editar `backend/app/services/kpi_engine.py`:
   - Agregar la métrica a `CATALOGO_GLOBAL` o `CATALOGO_VIAJE` (nombre + descripción).
   - Calcular su valor dentro de `metricas_global()` (o `metricas_viaje()`) y agregarla
     al diccionario de retorno, usando consultas parametrizadas (nunca SQL de texto).
2. Actualizar los tests en `backend/tests/test_kpi_engine.py` si aplica.
3. Listo: el editor mostrará la métrica automáticamente y las fórmulas podrán usarla.

> Esta es la única forma de "incorporar un dato nuevo al backend": se agrega la métrica
> en código (con su consulta segura). Las fórmulas se editan en la plataforma.

## Endpoints

| Método | Ruta | Acceso |
|---|---|---|
| GET | `/api/v1/kpis` | Todos |
| GET | `/api/v1/kpis/catalogo?ambito=` | Todos |
| GET | `/api/v1/kpis/valores?periodo=` | Todos |
| POST | `/api/v1/kpis/preview` | Admin |
| POST / PUT | `/api/v1/kpis` · `/kpis/{id}` | Admin |
| DELETE | `/api/v1/kpis/{id}` | Admin |
| GET | `/api/v1/viajes/{id}/rentabilidad` | Todos |
| POST | `/api/v1/viajes/preview-rentabilidad` | Todos |
