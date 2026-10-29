---
name: vertical-slice
description: "Completa una funcionalidad del ERP TEI de extremo a extremo —persistencia, reglas, API, UI, permisos, pruebas y documentación— con criterios de aceptación y rollback, evitando capas a medias y terceras fuentes de verdad."
---

# Vertical slice — de la base a la pantalla

## 1. Objetivo y ámbito

Entregar una funcionalidad completa y usable, no una capa aislada. Un slice
incluye: modelo/migración si hace falta, servicio, endpoint, contrato, pantalla,
permisos, auditoría, pruebas y documentación.

## 2. Cuándo usarla

- Un módulo o capacidad nueva.
- Una funcionalidad que cruza backend y frontend.
- Un cambio que necesita migración + API + UI.
- Cuando el trabajo se está fragmentando en “primero la tabla, después vemos”.

## 3. Contexto y precondiciones

- `AGENTS.md`.
- Contrato de tarea con objetivo, alcance y no objetivos.
- Identificación de legacy vs núcleo.
- Contrato HTTP acordado antes de escribir UI.
- Datos de seed o fixtures.
- Riesgo clasificado.

## 4. Procedimiento

1. **Define el slice** en una frase: actor, acción, resultado.
2. **Criterios de aceptación**: observables, no “que funcione”.
3. **Diseña el dato**: tabla/columnas/constraints, tenant, estados, auditoría.
4. **Diseña la regla**: dónde se impone, qué error devuelve, qué es idempotente.
5. **Contrato HTTP**: método, ruta, request, response, códigos, permisos.
6. **Servicio**: transacción, locks, validaciones, errores de dominio.
7. **Frontend**: cliente correcto, estados de carga/vacío/error, accesibilidad,
   tipos.
8. **Pruebas**: unitaria, integración, HTTP, E2E; adversariales si el riesgo lo
   pide.
9. **Documentación**: regla, límites, decisión pendiente, cómo probar.
10. **Rollback**: qué se revierte y cómo; bandera si aplica.
11. **Regresión**: módulos vecinos y legacy.

## 5. Orden recomendado

```text
Contrato y criterios
  → migración/constraint
  → modelo/servicio
  → endpoint + permisos
  → pruebas backend
  → cliente/tipos
  → pantalla + estados
  → E2E
  → documentación
```

No empieces por la pantalla si aún no sabes qué devuelve el servidor.

## 6. Comprobaciones verificables

- [ ] La regla crítica está en DB/transacción, no solo en UI.
- [ ] El endpoint exige auth, permiso y empresa.
- [ ] El frontend usa el cliente correcto y envía `X-Empresa-ID` si es núcleo.
- [ ] Hay estados de carga, vacío, error y sin permiso.
- [ ] Los errores de dominio se muestran con un mensaje útil.
- [ ] La operación es idempotente si puede reintentarse.
- [ ] La auditoría registra el cambio crítico.
- [ ] Hay pruebas de camino feliz y negativo.
- [ ] El legacy sigue funcionando o se documentó el corte.
- [ ] El rollback está definido.

## 7. Errores frecuentes

- Implementar la UI primero y “acomodar” el backend después.
- Crear una tabla nueva sin revisar si ya existe una equivalente.
- Endpoint sin consumidor o pantalla con datos mock.
- Permisos solo en la navegación.
- Validación solo en el formulario.
- Migración sin rollback.
- Duplicar una regla en dos servicios.
- No probar el flujo completo.
- Romper una pantalla legacy por cambiar un contrato compartido.

## 8. Criterios de aceptación

- El flujo completo funciona con datos reales de seed.
- Las capas usan el mismo contrato.
- Las reglas críticas se imponen en la capa correcta.
- Hay evidencia de pruebas.
- La documentación y el rollback están actualizados.
- No se introdujo una tercera fuente de verdad.

## 9. Formato de entrega

```text
## Slice
<actor, acción, resultado>

## Cambios por capa
<DB, servicio, API, UI, pruebas, docs>

## Contrato
<request/response/errores>

## Permisos
<rol/permiso/empresa>

## Evidencia
<comandos y resultados>

## Rollback
<pasos>

## Pendientes
<decisiones y límites>
```

## 10. Referencias

- `docs/desarrollo/backlog.md` (Definition of Done original)
- `docs/qa/uat-piloto.md`
- `AGENTS.md`
- FastAPI: <https://fastapi.tiangolo.com/>
- Next.js App Router: <https://nextjs.org/docs/app>
