---
name: finance-invariants
description: "Protege cálculos económicos del ERP TEI (tarifas, gastos, combustible, costo/km, margen, facturación, pagos, comisiones, liquidaciones) mediante invariantes, redondeo, idempotencia, snapshots, anulaciones y trazabilidad auditables."
---

# Finance invariants — dinero, costos y trazabilidad

## 1. Objetivo y ámbito

Evitar errores que cuestan dinero o destruyen la confianza en el ERP: doble
contabilización, ingresos incorrectos, comisiones mal calculadas, facturación sin
respaldo, pagos duplicados, costos que no cuadran y pérdida de trazabilidad.

No define la política comercial ni la normativa tributaria. Verifica y protege la
regla que TEI/contador hayan decidido.

## 2. Cuándo usarla

- Tarifas, OC, gastos, combustible, peajes, costos fijos, margen, Freight Score.
- Facturación, notas de crédito, pagos, cobranza, aging.
- Comisiones, liquidaciones, anticipos, ajustes.
- Cualquier cambio que sume, reste, redondee o congele un importe.

## 3. Contexto y precondiciones

- `AGENTS.md` y `erp-domain`.
- Fórmula o decisión fuente; si no existe, es una pregunta, no una regla.
- Modelo de datos y estados.
- Moneda, unidad, base de cálculo y momento de aplicación.
- Decisión de redondeo.
- Datos de seed o fixtures; nunca datos reales.

## 4. Procedimiento

1. **Define la magnitud**: flete neto, costo, margen, comisión, IVA, saldo, pago,
   aging. Una frase cada una.
2. **Define la fórmula** con unidades y signo:
   `margen = ingreso_neto − costo_variable − costo_fijo_asignado`.
3. **Define la base**: ¿neto o bruto? ¿facturado, cobrado o finalizado? ¿por
   viaje, por mes, por cliente?
4. **Define el redondeo**: por línea o por total; decimales; cuándo se aplica.
5. **Identifica periodos**: fecha de viaje, emisión, vencimiento, pago, cierre.
6. **Identifica estados**: borrador, confirmado, en ruta, cerrado, facturado,
   cobrado, anulado, rechazado.
7. **Busca doble conteo**: reasignación, recálculo, reintento, reproceso.
8. **Exige idempotencia** en pagos, facturas, notas, aprobaciones y consumo de OC.
9. **Congela snapshots**: tarifa, OC, costo, comisión; un cambio posterior no
   reescribe la historia.
10. **Prueba** el caso normal, el borde, el negativo y la anulación.

## 5. Invariantes típicos (verificar, no asumir)

- Un viaje no se factura dos veces.
- Un pago no supera el saldo; una nota no deja saldo negativo.
- Un gasto rechazado no suma al costo; uno aprobado no se aprueba dos veces.
- El consumo de OC es idempotente al reasignar.
- La comisión usa la base definida y no incluye viajes anulados si así se decidió.
- El margen no mezcla costos de otra empresa/viaje.
- Un cambio de tarifa no altera viajes históricos.
- Un anticipo de cliente no es ingreso.
- Un gasto pagado no es automáticamente costo del viaje.
- La anulación conserva rastro y evidencia.

## 6. Comprobaciones verificables

- [ ] `Decimal`/`numeric`, no `float`.
- [ ] Redondeo documentado y probado.
- [ ] IVA afecta/exenta según la fuente, no inventado.
- [ ] Fechas de corte y zona horaria explícitas.
- [ ] Pagos parciales y notas probados.
- [ ] Reintento no duplica.
- [ ] Snapshot histórico intacto.
- [ ] Costo y ingreso no se confunden.
- [ ] La comisión no se calcula sobre datos incompletos.
- [ ] La auditoría permite reconstruir el cálculo.

## 7. Errores frecuentes

- `float` o `toFixed` para dinero.
- Redondear cada línea y luego sumar, sin conciliar con el total.
- Recalcular historia con la tarifa actual.
- Duplicar consumo al reasignar.
- Pagar comisión sobre viaje anulado/no cobrado sin regla.
- Facturar sin POD/OC si el gate existe.
- Ignorar notas de crédito en aging.
- Tratar una tasa tributaria como constante de código.
- No registrar quién cambió un importe.
- Probar solo el caso exacto.

## 8. Criterios de aceptación

- Cada invariante tiene fórmula, fuente y prueba.
- Los bordes y anulaciones están cubiertos.
- La idempotencia está probada.
- Los snapshots son inmutables o versionados.
- Las reglas legales están marcadas para validación profesional.
- El cálculo se puede explicar con datos y fecha.

## 9. Formato de entrega

```text
## Magnitud y fórmula
## Fuente y decisión
## Implementación
## Invariantes y pruebas
## Bordes/redondeo/IVA
## Riesgos de doble conteo o pérdida
## Validación pendiente (contador/abogado)
```

## 10. Referencias

- `docs/negocio/kpis.md`
- `docs/arquitectura/nucleo-diseno.md` (OC, tarifa, facturación)
- `docs/qa/uat-piloto.md`
- `supabase/migrations/0011_gastos.sql`, `0012_rentabilidad.sql`, `0013_facturacion.sql`
- PostgreSQL numeric: <https://www.postgresql.org/docs/current/datatype-numeric.html>
