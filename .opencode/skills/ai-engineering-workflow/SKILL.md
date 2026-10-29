---
name: ai-engineering-workflow
description: "Estructura el trabajo asistido por IA en el ERP TEI con contexto mínimo suficiente, contratos de tarea autocontenidos, descomposición por dependencias, propiedad de archivos, registro de supuestos y verificación de resultados antes de aceptar una entrega."
---

# AI engineering workflow — contexto, delegación y verificación

## 1. Objetivo y ámbito

Hacer que el trabajo multiagente sea más fiable y económico: menos contexto
irrelevante, menos duplicación, menos escrituras concurrentes y más evidencia.
Aplica al orquestador y a cualquier agente que delegue o prepare contexto.

## 2. Cuándo usarla

- Al planificar una tarea compleja.
- Antes de lanzar subagentes.
- Al preparar contexto para otro agente.
- Al revisar una entrega de otro agente.
- Cuando el coste de tokens o la confusión empieza a superar el valor.

## 3. Contexto y precondiciones

- `AGENTS.md`.
- Objetivo y criterios de aceptación, aunque sean provisionales.
- Acceso al repo y capacidad de verificar.
- Conocimiento de qué agentes/skills existen (`opencode debug agents`).
- No delegar secretos ni datos personales.

## 4. Procedimiento

### 4.1 Clasifica y decide

- ¿Es pregunta, diagnóstico, cambio, incidente o configuración?
- ¿Riesgo bajo, medio o alto?
- ¿Se resuelve directamente o necesita especialista?
- ¿El valor del subagente supera el coste de explicar el contexto?

### 4.2 Contexto mínimo suficiente

Incluye solo:

- hechos comprobados y su ubicación;
- archivos/módulos relevantes;
- contrato de API o esquema si aplica;
- restricciones (legacy/núcleo, no migraciones, no secretos);
- criterio de aceptación;
- formato de salida;
- qué debe escalar.

No incluyas el repositorio completo, conversaciones enteras ni conclusiones sin
evidencia.

### 4.3 Contrato de tarea

```text
Rol:
Objetivo:
Contexto mínimo:
Archivos/áreas (propiedad):
Restricciones:
Entregable:
Criterios de aceptación:
Pruebas requeridas:
Riesgos/preguntas:
```

Si no puedes llenar “criterios de aceptación” y “entregable”, la tarea aún no
está lista.

### 4.4 Dependencias y paralelismo

- Investigación de solo lectura: paraleliza.
- Escritura: un propietario por archivos.
- Contrato HTTP antes de frontend/backend en paralelo.
- Migración: un diseñador; revisión independiente después.
- No lances dos agentes a “mejorar” el mismo módulo sin límites.

### 4.5 Registro de supuestos

```text
Hechos confirmados:
Supuestos:
Contradicciones:
Decisiones pendientes:
Riesgos:
Evidencia faltante:
```

### 4.6 Verificación

1. Exige archivos/líneas/comandos, no adjetivos.
2. Verifica al menos una afirmación crítica.
3. Ejecuta las pruebas o revisa la salida real.
4. Revisa el diff completo.
5. Contrasta con la jerarquía de evidencia.
6. Si el subagente falló, corrige el contrato antes de reintentar.

### 4.7 Cierre

- Resume qué se hizo, qué se verificó y qué no.
- Actualiza el registro de riesgos si hay un hallazgo recurrente.
- No agregues una regla global por un incidente aislado.
- Convierte fallos recurrentes en prueba de regresión o skill, no en “memoria”.

## 5. Comprobaciones verificables

- [ ] Cada subagente tiene objetivo, archivos, restricciones y aceptación.
- [ ] No hay dos escritores sobre el mismo archivo.
- [ ] El contexto no incluye secretos ni volcados innecesarios.
- [ ] Hay una salida estructurada.
- [ ] La evidencia primaria fue verificada por el orquestador.
- [ ] El diff fue revisado.
- [ ] Las pruebas se ejecutaron o se declaró el bloqueo.
- [ ] El informe distingue verificado de no verificado.

## 6. Errores frecuentes

- Delegar “mejora el backend” sin alcance.
- Pegar todo el repo en cada prompt.
- Lanzar cinco agentes para una tarea de una línea.
- Paralelizar escrituras sobre el mismo archivo.
- Aceptar un resumen sin abrir el diff.
- Convertir un supuesto en hecho.
- Reintentar la misma instrucción sin cambiar el contexto.
- Duplicar una investigación ya concluida.
- Fijar modelos sin una razón medida.

## 7. Criterios de aceptación

- El trabajo se entiende y se puede reproducir.
- El contexto fue suficiente y no excesivo.
- Las dependencias y la propiedad de archivos están claras.
- La entrega incluye evidencia y limitaciones.
- El coste de coordinación está justificado.

## 8. Formato de entrega

```text
## Plan
## Delegaciones
<rol, objetivo, archivos, evidencia>

## Registro de supuestos
## Verificación
## Resultado
## No verificado
```

## 9. Referencias

- OpenCode agents: <https://opencode.ai/v2/docs/agents>
- OpenCode skills: <https://opencode.ai/v2/docs/skills>
- `AGENTS.md` del repo
- `docs/desarrollo/backlog.md`
