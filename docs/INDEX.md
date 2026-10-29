# Índice de documentación — ERP Transportes TEI SpA

> **Punto de entrada único.** Si necesitás saber algo del sistema, empezá acá.
> El código, las migraciones y las pruebas ejecutadas siguen siendo la autoridad
> final; este índice dice **dónde mirar** y **cuánto vale** lo que vas a leer.

---

## 1. Cómo se usa

1. Buscá tu pregunta en la tabla §2.
2. Abrí el documento indicado.
3. Leé su cabecera: **fecha de verificación**, **método** y **caducidad**.
4. Si el documento tiene más de 30 días o el esquema cambió, re-verificá antes de citarlo.

---

## 2. Por intención

| Si necesitás saber… | Leé | Tipo |
|---|---|---|
| ¿Qué está listo hoy y qué no? | [`estado.md`](estado.md) | estado |
| ¿Cómo se conecta todo el sistema? | [`mapa-sistema.md`](mapa-sistema.md) | mapa |
| ¿Dónde se guarda un dato? ¿Qué tablas hay? | [`arquitectura/modelo-datos.md`](arquitectura/modelo-datos.md) | referencia |
| ¿Qué pantallas, endpoints y módulos existen? | [`arquitectura/modulos.md`](arquitectura/modulos.md) | referencia |
| ¿Cómo funciona la disponibilidad / reservas? | [`arquitectura/nucleo-diseno.md`](arquitectura/nucleo-diseno.md) | diseño |
| ¿Cómo viaja un dato de la pantalla a la tabla? | [`arquitectura/flujos.md`](arquitectura/flujos.md) | trazabilidad |
| ¿`public` o `nucleo` es la fuente de verdad de X? | [`arquitectura/fuentes-de-verdad.md`](arquitectura/fuentes-de-verdad.md) | decisión |
| ¿Qué falta respecto del ERP objetivo? | [`arquitectura/capacidades-objetivo.md`](arquitectura/capacidades-objetivo.md) | brecha |
| ¿Cuál es la regla de comisión, tarifa, OC, IVA? | [`negocio/catalogo-reglas.md`](negocio/catalogo-reglas.md) | regla |
| ¿Dónde se implementa esa regla en el código? | [`negocio/implementacion.md`](negocio/implementacion.md) | trazabilidad |
| ¿Cómo se calcula un KPI? | [`negocio/kpis.md`](negocio/kpis.md) | referencia |
| ¿Qué decisiones están pendientes y de quién? | [`negocio/preguntas.md`](negocio/preguntas.md) | bloqueo |
| ¿Cuál es el contexto real del negocio? | [`negocio/contexto.md`](negocio/contexto.md) | contexto |
| ¿Cómo levanto el entorno local? | [`operacion/setup-local.md`](operacion/setup-local.md) | guía |
| ¿Cómo se hace el cutover sin perder datos? | [`operacion/cutover.md`](operacion/cutover.md) | runbook |
| ¿Cómo respaldo y restauro? | [`operacion/backup-restore.md`](operacion/backup-restore.md) | runbook |
| ¿Cómo despliego a la nube? | [`operacion/deploy-cloud.md`](operacion/deploy-cloud.md) | contingencia |
| ¿Qué garantiza PostgreSQL? | [`datos/garantias.md`](datos/garantias.md) | garantía |
| ¿Qué invariantes NO tienen mecanismo en base? | [`datos/invariantes.md`](datos/invariantes.md) | deuda |
| ¿Qué hace la migración 00XX? ¿Está aplicada? | [`datos/catalogo-migraciones.md`](datos/catalogo-migraciones.md) | referencia |
| ¿Qué prueba cubre esta garantía? | [`desarrollo/pruebas.md`](desarrollo/pruebas.md) | cobertura |
| ¿Qué se está construyendo? ¿Qué sigue? | [`desarrollo/backlog.md`](desarrollo/backlog.md) | plan |
| ¿Qué deuda técnica hay y cuánto cuesta? | [`arquitectura/deuda.md`](arquitectura/deuda.md) | deuda |
| ¿Cómo se escribe código en este repo? | [`desarrollo/guia.md`](desarrollo/guia.md) | guía |
| ¿En qué estado está la suite? | [`qa/linea-base.md`](qa/linea-base.md) | evidencia |
| ¿Qué invariante tiene prueba y cuál no? | [`qa/matriz-trazabilidad.md`](qa/matriz-trazabilidad.md) | cobertura |
| ¿Qué escenarios de aceptación existen? | [`qa/uat-piloto.md`](qa/uat-piloto.md) | plan |
| ¿Hay hallazgos de seguridad abiertos? | [`seguridad/hallazgos.md`](seguridad/hallazgos.md) | hallazgo |
| ¿Qué se decidió y por qué? | [`arquitectura/adr/`](arquitectura/adr/) | decisión |
| ¿Qué se hizo, en qué orden y con qué evidencia? | [`orquestacion/registro.md`](orquestacion/registro.md) | bitácora |
| ¿Qué se intentó antes y por qué se descartó? | [`_archivo/README.md`](_archivo/README.md) | histórico |
| ¿Cuál es el alcance del piloto de 90 días? | [`arquitectura/alcance-piloto.md`](arquitectura/alcance-piloto.md) | alcance |
| ¿Cómo se retira el legacy? | [`arquitectura/retiro-legacy.md`](arquitectura/retiro-legacy.md) | borrador |
| ¿Cuál es el destino modular? | [`arquitectura/destino-modular.md`](arquitectura/destino-modular.md) | propuesta |
| ¿Qué contradicciones tenía el plan maestro? | [`arquitectura/matriz-plan-vs-codigo.md`](arquitectura/matriz-plan-vs-codigo.md) | análisis |

---

## 3. Documentos vivos

| Documento | Responde | Verificado | Método |
|---|---|---|---|
| `estado.md` | ¿qué está listo? | 2026-10-29 | ejecución + lectura |
| `mapa-sistema.md` | ¿cómo se conecta todo? | 2026-10-29 | lectura estática |
| `arquitectura/modelo-datos.md` | ¿dónde se guarda? | 2026-10-29 | lectura de DDL |
| `arquitectura/modulos.md` | ¿qué existe? | 2026-10-29 | lectura de routers/páginas |
| `arquitectura/nucleo-diseno.md` | ¿cómo funciona el núcleo? | 2026-10-29 | lectura de DDL + servicios |
| `arquitectura/flujos.md` | ¿cómo fluye un dato? | 2026-10-29 | lectura estática |
| `arquitectura/fuentes-de-verdad.md` | ¿qué esquema manda? | 2026-10-29 | lectura estática |
| `arquitectura/capacidades-objetivo.md` | ¿qué falta? | 2026-10-29 | lectura estática |
| `arquitectura/deuda.md` | ¿qué deuda hay? | 2026-10-29 | consolidación |
| `negocio/catalogo-reglas.md` | ¿cuál es la regla? | 2026-10-29 | lectura + auditoría |
| `negocio/implementacion.md` | ¿dónde se implementa? | 2026-10-29 | lectura de código |
| `negocio/kpis.md` | ¿cómo se calcula? | 2026-10-29 | lectura de código |
| `negocio/preguntas.md` | ¿qué está bloqueado? | 2026-10-29 | consolidación |
| `negocio/contexto.md` | ¿cuál es el negocio? | 2026-10-29 | fuente: dueño |
| `operacion/setup-local.md` | ¿cómo levanto? | 2026-10-29 | lectura + ejecución |
| `operacion/cutover.md` | ¿cómo migro? | 2026-10-29 | lectura de scripts |
| `operacion/backup-restore.md` | ¿cómo respaldo? | 2026-10-29 | lectura de scripts |
| `operacion/deploy-cloud.md` | ¿cómo despliego? | 2026-10-29 | lectura |
| `datos/garantias.md` | ¿qué garantiza la DB? | 2026-10-29 | lectura de DDL |
| `datos/invariantes.md` | ¿qué no está garantizado? | 2026-10-29 | lectura de DDL |
| `datos/catalogo-migraciones.md` | ¿qué hace cada migración? | 2026-10-29 | lectura de DDL |
| `desarrollo/guia.md` | ¿cómo codeo acá? | 2026-10-29 | lectura |
| `desarrollo/pruebas.md` | ¿qué prueba cubre qué? | 2026-10-29 | lectura |
| `desarrollo/backlog.md` | ¿qué sigue? | 2026-10-29 | consolidación |
| `qa/linea-base.md` | ¿estado de la suite? | 2026-10-29 | ejecución |
| `qa/matriz-trazabilidad.md` | ¿cobertura por invariante? | 2026-10-29 | consolidación |
| `qa/uat-piloto.md` | ¿escenarios de aceptación? | 2026-10-29 | lectura |
| `seguridad/hallazgos.md` | ¿qué hallazgos hay? | 2026-10-29 | auditoría |
| `arquitectura/adr/` | ¿qué se decidió? | 2026-10-29 | propuesta |
| `orquestacion/registro.md` | ¿qué se hizo? | 2026-10-29 | bitácora |

---

## 4. Convenciones

### Marcas de evidencia (obligatorias)

| Marca | Significado |
|---|---|
| 🟢 | Verificado en código, DDL o salida de comando, con `archivo:línea` |
| 🟡 | Inferido; se indica qué lo confirmaría |
| 🔴 | No determinable; se indica qué falta |

### Cabecera mínima de cada documento

```
> **Pregunta que responde:** …
> **Dueño:** agente X · **Verificado:** AAAA-MM-DD · **Método:** lectura | ejecución | SQL
> **Caduca si:** …
> **Re-verificar con:** <comando>
```

### Identificadores

| Prefijo | Qué es | Vive en |
|---|---|---|
| `R-0XX` | regla de negocio | `negocio/catalogo-reglas.md` |
| `INV-XXX` | invariante | `datos/invariantes.md` |
| `SEC-NNN` | hallazgo de seguridad | `seguridad/hallazgos.md` |
| `ADR-NNNN` | decisión de arquitectura | `arquitectura/adr/` |
| `D-NN` | decisión pendiente del dueño | `negocio/preguntas.md` |
| `P-NN` | pregunta a contador/legal | `negocio/preguntas.md` |
| `RA-NN` | riesgo abierto | `estado.md` §riesgos |
| `P0-NN` | escenario de aceptación | `qa/uat-piloto.md` |

### Reglas

1. **Un documento = una pregunta.** Si un archivo crece >400 líneas, se divide.
2. **Ningún documento repite cifras volátiles** salvo `estado.md`. Los demás citan el archivo o el ID.
3. **Lo histórico no se borra:** se mueve a `_archivo/` con banner.
4. **Un dato sin `archivo:línea` no se cita.**
5. **Si dos documentos se contradicen, gana el código**; el documento se corrige o se archiva.

---

## 5. Artefactos por agente

Cada agente escribe solo en su carpeta. Esta tabla es el contrato vigente.

| Agente | Escribe en | No toca |
|---|---|---|
| `orquestador` | `docs/estado.md`, `docs/orquestacion/`, `docs/INDEX.md` | código |
| `arquitectura` | `docs/arquitectura/` | código, migraciones |
| `datos` | `docs/datos/` | código de aplicación |
| `backend` | `docs/backend/`, `backend/app/**`, `backend/tests/**` | frontend, migraciones |
| `frontend` | `docs/frontend/`, `frontend/src/**` | backend, E2E |
| `negocio-finanzas` | `docs/negocio/` | código, migraciones |
| `qa` | `docs/qa/`, `backend/tests/**`, `frontend/e2e/**` | código de producción |
| `auditor-seguridad` | `docs/seguridad/` | código |

---

*Última reorganización: 2026-10-29. Historial en `orquestacion/registro.md`.*
