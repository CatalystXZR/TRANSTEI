---
name: erp-domain
description: "Verifica reglas de negocio del ERP TEI (viajes, tarifas, OC, POD, gastos, facturación, cobranza, comisiones) contra la implementación real, separa reglas de supuestos y produce una matriz de evidencia. Úsala antes de cambiar o auditar lógica de dominio."
---

# ERP domain — reglas, evidencia e invariantes

## 1. Objetivo y ámbito

Determinar qué reglas de negocio existen **realmente**, dónde se implementan, qué
las prueba y qué sigue siendo una decisión pendiente. Cubre viajes, tarifas, OC,
POD, gastos, costos, margen, facturación, cobranza, comisiones y liquidaciones.

No es una skill para “inventar” reglas faltantes. Es una skill para separar
hechos, implementación y decisiones.

## 2. Cuándo usarla

- Antes de modificar una regla de negocio.
- Al auditar un módulo o responder “¿esto está implementado?”.
- Al detectar documentos que se contradicen.
- Al diseñar pruebas de aceptación.
- Al incorporar un requisito nuevo de negocio.

## 3. Contexto y precondiciones

Lee `AGENTS.md` y, según el caso:

- `docs/arquitectura/nucleo-diseno.md` (reglas del núcleo).
- `docs/estado.md` (estado declarado; puede contradecirse).
- `docs/negocio/kpis.md` (fórmulas y ejemplos).
- `docs/qa/uat-piloto.md` (aceptación).
- `supabase/migrations/` (DDL real).
- `backend/app/nucleo/` y `backend/app/api/routes/` (servicios y rutas).
- `frontend/src/lib/api.ts`, `frontend/src/lib/nucleo.ts` y las páginas.

Identifica si el flujo es legacy, núcleo o ambos.

## 4. Procedimiento

1. **Enuncia la regla** en una frase verificable. Si no puedes, aún no la
   entiendes.
2. **Busca la fuente**: documento, decisión del usuario, código, constraint o
   prueba. Registra la cita exacta.
3. **Localiza la implementación**: UI, cliente HTTP, router, dependencia,
   servicio, trigger, constraint. Anota `archivo:línea`.
4. **Verifica uso**: ¿la pantalla llama al endpoint? ¿el endpoint escribe la
   tabla? ¿hay otra ruta que escriba lo mismo?
5. **Verifica corrección**: prueba el caso normal, el borde y el negativo. No
   confundas existencia con corrección.
6. **Construye la matriz**:

   | Regla | Fuente | Implementación | Prueba | Estado | Confianza |
   |---|---|---|---|---|---|
   | … | … | `archivo:línea` | comando/resultado | implementado/parcial/ausente/decisión | alta/media/baja |

7. **Identifica invariantes**: qué no puede ocurrir nunca y dónde se impide.
8. **Separa** reglas comerciales, decisiones pendientes y obligaciones
   legales/tributarias/laborales.
9. **Registra preguntas** concretas; no las respondas por intuición.

## 5. Comprobaciones verificables

- La regla está en el servidor, no solo en la UI.
- La constraint/trigger existe en la migración aplicada.
- El estado del viaje/factura/gasto permite la operación.
- El dinero usa `Decimal`/`numeric` y una regla de redondeo.
- Las fechas son `timestamptz` o `date` según el caso; no hay naive.
- La operación es idempotente si puede reintentarse.
- La empresa se resuelve en el servidor.
- La auditoría cubre el cambio crítico.
- Hay una prueba que falla si la regla se rompe.

## 6. Errores frecuentes

- Tomar `PENDIENTES_ERP.md` como prueba de implementación.
- Mezclar el comportamiento legacy con el del núcleo.
- Convertir una práctica observada en regla legal.
- Inventar IVA, comisión, recargo o plazo.
- Ignorar anulaciones, notas de crédito o pagos parciales.
- Validar solo el camino feliz.
- Confundir “facturado” con “cobrado”.
- Duplicar una regla en UI y backend con resultados distintos.

## 7. Criterios de aceptación

- Cada regla tiene fuente, implementación, prueba y estado.
- Las contradicciones están clasificadas, no “resueltas” por narrativa.
- Las decisiones pendientes tienen pregunta y responsable.
- Las reglas legales están marcadas para validación profesional.
- Los invariantes críticos tienen una prueba o una brecha explícita.

## 8. Formato de entrega

```text
## Reglas verificadas
| Regla | Fuente | Implementación | Prueba | Estado | Confianza |

## Invariantes
<regla → mecanismo → evidencia>

## Brechas y contradicciones
<qué no coincide, con ubicación>

## Decisiones pendientes
<pregunta exacta + a quién>

## Validación legal/tributaria/laboral
<qué requiere profesional y por qué>
```

## 9. Referencias

- `docs/arquitectura/nucleo-diseno.md`
- `docs/negocio/kpis.md`
- `docs/qa/uat-piloto.md`
- `supabase/migrations/0004_nucleo_operacional.sql` y siguientes
- `backend/app/nucleo/`
- PostgreSQL: <https://www.postgresql.org/docs/current/>
