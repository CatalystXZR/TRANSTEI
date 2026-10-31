# PLAN_DESARROLLO.md — Cierre del Núcleo del ERP Transportes TEI

> **Pregunta que responde:** ¿qué hay que construir, en qué orden, con qué criterios y qué pruebas, para dejar el **Núcleo** 100 % cerrado, seguro y estable?
> **Dueño:** `orquestador` · **Estado:** vigente (documento vivo) · **Creado:** 2026-10-29
> **Método:** consolidación de las decisiones del dueño + lectura de `docs/` + verificación de `git`
> **Regla:** este plan **no reemplaza** `AGENTS.md`; lo complementa. Si hay contradicción, manda `AGENTS.md` y se reporta.
> **F0 no está ejecutado.** Este documento solo transcribe el plan. La ejecución empieza cuando el dueño lo autorice.

---

## 0. Cómo usar este plan

1. **Se sigue al pie de la letra.** No se agregan tareas de último momento sin registrarlas aquí (con su ID y su impacto).
2. **Cada fase tiene:** objetivo, alcance, prerrequisitos, tareas, entregables, criterios de aceptación, **gate de pruebas**, rollback y criterio de salida.
3. **Ninguna fase se cierra sin su gate de pruebas aprobado.** Un `skip` no es un aprobado. "No ejecutado" no es "pasó".
4. **Toda afirmación se sostiene con evidencia:** comando exacto + salida + fecha + `archivo:línea`. Sin eso, es 🟡 o 🔴, nunca 🟢.
5. **Riesgo Alto** (dinero, permisos, tenant, disponibilidad, migraciones, backups, agente) exige **revisión independiente** (`auditor-seguridad`/`qa`) y prueba adversarial.
6. **No se borran datos ni se toca producción** sin autorización explícita del dueño y backup verificado.
7. **Al cerrar cada fase:** actualizar este documento (estado, evidencia, desvíos) y `docs/estado.md`.

### 0.1 Convención de estados de una fase

| Estado | Significado |
|---|---|
| `pendiente` | No iniciada |
| `en curso` | Tareas activas |
| `en gate` | Construcción terminada, gate de pruebas en ejecución |
| `cerrada` | Gate aprobado, evidencia registrada, dueño aceptó |
| `bloqueada` | Depende de una decisión del dueño o de un tercero |

---

## 1. Registro de decisiones (fuente de verdad del plan)

Estas decisiones fueron tomadas por el dueño en la conversación de diseño. **Mandan sobre cualquier suposición previa de la documentación antigua.**

| ID | Decisión | Efecto en el plan |
|---|---|---|
| **DEC-01** | **Un solo piso.** Se elimina `public` (legacy) y el cutover. Todo vive en un esquema único. | F1 elimina legacy y renombra el esquema. |
| **DEC-02** | **Multiempresa SaaS**: una base, un esquema, `empresa_id` en todo, **RLS** con rol sin bypass. Aislamiento lógico fuerte. | F3 implementa y prueba RLS con rol real. |
| **DEC-03** | **Plano plataforma**: el dueño (TRANSTEI) tiene **acceso total** a la data operativa de cada empresa, **auditado** y por un rol/consola separados. | F3 construye consola y rol de plataforma. |
| **DEC-04** | **Nomenclatura**: **Núcleo** = base irremovible, compuesta por **componentes**. **Módulos** = extras acoplables. | Glosario y todo el plan. |
| **DEC-05** | **Tributario**: el **Núcleo es 100 % manual** (registro + carga automática de documentos al storage). La **automatización SII/WhatsApp/OCR es un módulo premium**. | F1/F4 hacen el manual; el premium queda fuera de alcance. |
| **DEC-06** | **Tarifas, OC y documentación** (facturas, NC, guías de despacho, tickets de pesaje, etc.) son **Núcleo**. | F1/F4. |
| **DEC-07** | **Rentabilidad/Freight Score, Nómina/Compensaciones y Mantenimiento (pautas + registro)** son **Núcleo**. | F1/F4. |
| **DEC-08** | **Mantenimiento avanzado** (neumáticos por ID, repuestos, reparaciones) es **Módulo**. | Fuera de alcance del cierre; el conector lo soporta. |
| **DEC-09** | **Conectores**: cada componente del Núcleo expone hooks, interfaces, slots de UI y seams genéricos. Los módulos se construyen sobre esos enchufes; **no se modifica el Núcleo**. | F2. |
| **DEC-10** | **Agente** (LLM + WhatsApp): instalado en la plataforma, **apagado** por defecto; se activa por componente al conectar un módulo; opera por **tools** (no SQL libre). | F2 diseña; implementación premium fuera de alcance. |
| **DEC-11** | **Escrituras sensibles** vía **solicitud + aprobación humana**. Matriz de aprobación configurable; **buzón** con badge rojo, cerrable, alertas persistentes hasta aprobar/rechazar/cancelar. | F2/F4 construyen el genérico. |
| **DEC-12** | **Storage**: archivos en object storage, metadatos en la base; prefijo por empresa; URLs firmadas; versionado; ciclo de vida; cuotas. | F5. |
| **DEC-13** | **Backups/restore**: PITR + snapshots; restauración por empresa/módulo/fecha con **grupos de consistencia**; "backup del backup"; retención por plan. | F5. |
| **DEC-14** | **Archivo anual/offboarding**: paquete reproducible por meses, cifrado; verificación; **purga** de nuestros sistemas (con salvedad legal); **no re-carga**. | F5. |
| **DEC-15** | **Due diligence (F0)** aprobada: leer/correr sin cambiar código; veredicto refactor vs reconstrucción. | F0. |
| **DEC-16** | **Stack se mantiene** (FastAPI + PostgreSQL + Next.js). **Monolito modular**, no microservicios. | Todo el plan. |
| **DEC-17** | **Aprobaciones con matriz de permisos** configurable (roles + overrides por usuario). Se pueden agregar roles si el dueño lo pide. | F2/F4. |

### 1.1 Decisiones abiertas (no bloquean F0)

| ID | Pregunta | Destinatario | Bloquea |
|---|---|---|---|
| **AB-01** | Retención legal de documentos tributarios/laborales antes de purgar | Contador / abogado | Purga (F5) |
| **AB-02** | ¿Se agregan roles `secretaría` y `mantenimiento`, o se mapea `taller` = mantenimiento? | Dueño | Matriz de aprobación (F2). **Nota 2026-10-30:** al decidir D-10, el dueño citó al "secretario" como ejemplo de aprobador de solicitudes (transcripción en `docs/negocio/agente-whatsapp-roles.md` §1) — evidencia a favor del rol `secretaría`; sigue abierta. |
| **AB-03** | Formato exacto del paquete de archivo (SQLite+CSV+PDF+visor vs Excel+PDF) | Dueño | F5 |
| **AB-04** | Proveedor de LLM y de WhatsApp Business API; privacidad | Dueño + legal | Módulo premium (fuera de alcance) |
| **AB-05** | Umbrales de rendimiento (p95, throughput, RTO/RPO) | Dueño + arquitectura | F6 |
| **AB-06** | Retención de backups por plan (10 días free; tramos pagos) | Dueño | F5 |

---

## 2. Arquitectura objetivo

### 2.1 Los cuatro cerebros

| Cerebro | Tecnología | Qué guarda | Para qué |
|---|---|---|---|
| **Verdad (OLTP)** | PostgreSQL, un esquema | Datos transaccionales, `empresa_id` en todo, constraints, triggers | Consistencia fuerte (ACID) |
| **Análisis (OLAP)** | Réplica de lectura / warehouse | Métricas, tendencias, reportes | Cruce del dueño + auditorías de tenants |
| **Archivos** | Object storage (S3-compatible) | PDFs, imágenes, Excel, etc. | Evidencia y documentos |
| **Tiempo** | Auditoría append-only + WAL + snapshots | Cada cambio, versiones, copias | Recuperación y trazabilidad |

### 2.2 Monolito modular

- Un proceso backend, un despliegue, una base.
- **Un solo escritor por tabla.** Un módulo lee datos de otro por **interfaz**; nunca escribe sus tablas.
- **Orquestación = transacción del componente dueño.** Sin bus de eventos, sin colas, sin consistencia eventual en el camino crítico.
- Microservicios/colas: **solo con medición** y un módulo con perfil distinto (ej. OCR/LLM). Ese módulo será un *worker* que usa las interfaces del Núcleo, no una segunda fuente de verdad.

### 2.3 Multi-tenancy y planos

```
Tenant A ─┐
Tenant B ─┼─► app_tenant (rol SIN bypass) ─► RLS por empresa_id ─► PostgreSQL
Tenant C ─┘

Dueño ─────► app_platform (rol separado, BYPASSRLS) ─► consola /plataforma (auditada)
```

- **Tenant:** `empresa_id` en toda tabla, RLS + `FORCE ROW LEVEL SECURITY`, `SET LOCAL app.empresa_id` por request, FKs compuestas `(empresa_id, id)`.
- **Plataforma:** rol separado con acceso total, **solo** desde la consola de plataforma, con **MFA**, **auditoría de cada acceso** y modo soporte/impersonación registrado.
- **Regla:** el aislamiento tenant↔tenant no se toca; el acceso del dueño es un privilegio explícito y trazable.

### 2.4 Conectores (el corazón del plug & play)

Cada componente del Núcleo publica un **Conector** con:

| Pieza | Qué es |
|---|---|
| **Interfaces** | Operaciones estables con reglas (`facturacion.emitir`, `documentos.registrar`) |
| **Hooks** | Eventos que el componente emite (`viaje.cerrado`, `factura.emitida`) |
| **Slots de UI** | Lugares donde un módulo inyecta botones/paneles (`factura.detalle.acciones`) |
| **Seams genéricos** | Campos personalizados (JSONB), adjuntos, timeline, workflow, jobs, webhooks, permisos, configuración |

Un **módulo** trae su **manifest** (tablas, permisos, endpoints, hooks que escucha, slots que llena, tools de agente que desbloquea) + su **backend** + su **frontend**. El Núcleo **no se modifica**: solo pinta slots y emite hooks.

> Si un módulo necesita un seam que no existe, se agrega **ese seam** (cambio pequeño y versionado), no se reescribe el Núcleo.

### 2.5 Agente y aprobaciones

- **Agente central** (LLM + WhatsApp + voz + OCR), **instalado y apagado**.
- **Tool Registry:** cada componente declara sus tools (lectura/escritura/cálculo) con permiso y módulo que las desbloquea.
- **Gate de capacidades:** por empresa; por defecto **ninguna tool activa**; el módulo activa las suyas.
- **Registro de contactos:** teléfono → empresa + rol + entidad (`cliente_final`, `conductor`, `usuario_tenant`), con **OTP** de enrolamiento.
- **Escrituras sensibles = solicitud + aprobación** (matriz configurable, buzón con badge rojo, alertas persistentes).
- **El agente no ejecuta SQL libre**; solo tools aprobadas. Respuestas citan la fuente. Escrituras con confirmación y auditoría.

### 2.6 Storage

- Metadatos en PostgreSQL; bytes en object storage.
- Prefijo `tenant/<empresa_id>/<componente>/<entidad>/<año>/<mes>/<uuid>`.
- URLs firmadas de corta duración; nunca buckets públicos.
- Versionado; no borrado destructivo; `object lock` para documentos legales.
- Ciclo de vida: caliente → frío → retención → borrado.
- Cuotas por plan: límite blando (alerta), límite duro (bloquea subidas, **no** rompe la operación), buffer de gracia, archiving.

### 2.7 Backups, restauración y archivo

- **PITR** (WAL) + snapshots diarios/semanales/mensuales + copia inmutable.
- **Restauración por empresa/módulo/fecha** con **grupos de consistencia** (Operación, Finanzas, Nómina, Mantención, Base). Sandbox → validación → diff → promoción transaccional → snapshot pre-restauración.
- **"Backup del backup"**: generaciones + copia inmutable.
- **Archivo anual/offboarding**: paquete por meses (SQLite + CSV + PDF + archivos + visor + manifiesto con checksums), cifrado, verificado; purga de la empresa (con salvedad legal); **no re-carga**.

---

## 3. Glosario

| Término | Significado |
|---|---|
| **Núcleo** | Sistema base irremovible. Sus partes son **componentes**. |
| **Módulo** | Extra acoplable (plug & play). No modifica el Núcleo. |
| **Componente** | Parte del Núcleo (ej. Facturación, Despacho, Nómina). |
| **Conector** | Contrato de un componente: interfaces + hooks + slots + seams. |
| **Solicitud** | Propuesta de escritura creada por el agente (o por un flujo), pendiente de aprobación. |
| **Buzón** | Bandeja de solicitudes pendientes; badge rojo; cerrable; alertas persistentes. |
| **Tool** | Operación que el agente puede invocar (lectura/escritura/cálculo). |
| **Gate de calidad** | Conjunto obligatorio de pruebas que una fase debe pasar para cerrarse. |
| **Paquete de archivo** | Export anual reproducible para offboarding/auditoría. |
| **Grupo de consistencia** | Conjunto de módulos que deben restaurarse juntos por dependencias. |

---

## 4. Alcance del Núcleo (cerrado) y fuera de alcance

### 4.1 Componentes del Núcleo (irremovibles)

| # | Componente | Qué hace | Hooks/interfaces/slots (mínimos) |
|---|---|---|---|
| C01 | Identidad y acceso | Usuarios, roles, permisos, empresas, login | interfaces de membresía/permisos; hooks de alta de usuario |
| C02 | Maestros y flota | Clientes, tractos, ramplas, choferes, documentos, odómetro | interfaces CRUD; hooks de cambio; slot de ficha |
| C03 | Despacho y agenda | Viajes, asignación, disponibilidad, estados, bloqueos | `viaje.*`; interfaces de consulta/asignación; slots de detalle |
| C04 | Expediente y POD | Evidencia de ejecución/entrega | `expediente.*`; interfaces; slots |
| C05 | Facturación y cobranza | Facturas, pagos, NC, saldos, aging | `factura.*`, `pago.*`, `nc.*`; interfaces; slots de acciones |
| C06 | Gastos y costos | Gastos, combustible, costo real | `gasto.*`; interfaces; slots |
| C07 | Tarifas y OC | Tarifas, órdenes de compra, consumo | `tarifa.*`, `oc.*`; interfaces; slots |
| C08 | Rentabilidad / Freight Score | Márgenes, simulador, score | interfaces de cálculo; hooks de recálculo |
| C09 | Nómina / Compensaciones | Sueldo base + % configurable + bonos | `nomina.*`; interfaces; slots; snapshot |
| C10 | Mantenimiento (pautas + registro) | Pautas por km + historial | `mantenimiento.*`; interfaces; slots |
| C11 | Tributario manual | Registro manual + storage de documentos (sin SII) | `documento.*`; interfaces; slots de acciones |
| C12 | Auditoría y trazabilidad | Log de todo, historial, correcciones | interfaces de consulta; sin escritura directa |
| C13 | Tablero | Home y alertas | agregación de solo lectura; slots de widgets |
| C14 | Plataforma (dueño) | Tenants, acceso total auditado, métricas cruzadas | interfaces de plataforma; consola |
| C15 | Backups y storage | Snapshots, PITR, object storage, cuotas, archivo | interfaces de backup/restore; consola |

### 4.2 Fuera de alcance del cierre (módulos premium/futuros)

- **Módulo tributario premium**: automatización SII, WhatsApp, OCR/LLM, botón de emisión.
- **Módulo de agente premium**: runtime LLM + WhatsApp + voz (el Núcleo deja el registry, gate, contactos, solicitudes y buzón).
- **Mantenimiento avanzado**: neumáticos por ID, repuestos, reparaciones.
- **Comercial avanzado**: cotizador, centros de costo, tarifas multimodales.
- **Integraciones** (email, mapas, bancos).
- **BI / auditorías avanzadas**.
- **Autorización como proveedor DTE ante el SII** (trámite legal).

> El Núcleo debe quedar **listo** para estos módulos, pero **no los construye** en este plan.

### 4.3 Qué significa "Núcleo cerrado"

1. Un solo esquema, sin `public`, sin cutover.
2. Multiempresa con RLS probado con el rol real.
3. Todos los invariantes críticos impuestos en PostgreSQL y probados con mutación.
4. Conectores publicados y un módulo de prueba acoplado sin tocar el Núcleo.
5. Storage, backups, restauración y archivo anual probados.
6. Gate de pruebas final aprobado: 0 hallazgos críticos/altos abiertos.
7. Staging operando con datos ficticios y checklist de producción completo.
8. Documentación viva actualizada.

---

## 5. Doctrina de calidad y pruebas

### 5.1 Principios

- **Seguridad y estabilidad > velocidad.**
- **La base es la última línea**: las garantías críticas viven en PostgreSQL, no en la UI.
- **Un solo escritor por tabla**; la escritura cruzada en Python está prohibida.
- **Mutación obligatoria**: para cada garantía crítica, retirar el mecanismo en una copia desechable y confirmar que la prueba falla.
- **Concurrencia real = dos conexiones simultáneas.** Dos llamadas seguidas no prueban concurrencia.
- **Nada de `skip`/`xfail`** para ocultar defectos.
- **Revisión independiente** en riesgo Alto.
- **Evidencia:** comando + salida + fecha + `archivo:línea`.

### 5.2 Herramientas (propuestas; se instalan en F0 si faltan)

| Capa | Herramienta |
|---|---|
| Backend lint/format | `ruff` |
| Backend tipos | `mypy` (opcional, incremental) |
| Frontend lint/tipos | `eslint`, `tsc` |
| Tests backend | `pytest`, `pytest-cov`, `hypothesis` |
| Tests frontend/E2E | `playwright` |
| Contrato API | OpenAPI + `schemathesis` |
| SAST | `semgrep`, `bandit` |
| Secretos | `gitleaks` |
| Dependencias | `pip-audit`, `npm audit`, `trivy` |
| DAST | OWASP ZAP |
| Carga | `k6` o `locust` |
| Caos | scripts propios (matar conexión/proceso, llenar disco, latencia) |
| Infra (si aplica) | `trivy`, escaneo de buckets/IAM |

### 5.3 Gate estándar (toda fase)

Antes de cerrar **cualquier** fase:

- [ ] `ruff` + `eslint` + `tsc` sin errores nuevos.
- [ ] Unitarias + integración + contrato en verde.
- [ ] Cobertura: rutas críticas 100 %; global ≥ 80 % en código tocado.
- [ ] Migraciones aplican limpias desde cero + chequeo de deriva.
- [ ] SAST + secret scan + dependency scan sin críticos/altos.
- [ ] Build backend + frontend.
- [ ] Sin `skip`/`xfail` nuevos.
- [ ] Mutación en garantías tocadas.
- [ ] Revisión independiente si riesgo Alto.
- [ ] Evidencia adjunta.

### 5.4 Pruebas adversariales (manual mínimo)

- **Autenticación/sesión:** JWT inválido/expirado, audiencia, alg, MFA, rate limit.
- **Autorización:** IDOR/BOLA, escalada de rol, empresa ajena, `empresa_id` en body, membresía inactiva.
- **Inyección:** SQLi, command, template, NoSQL (si aplica).
- **Web:** XSS, CSRF, SSRF, open redirect, CORS.
- **Archivos:** MIME real vs extensión, magic bytes, tamaño, path traversal, zip bomb, visor.
- **Lógica de negocio:** montos negativos/cero, sobrepago, doble pago, doble clic, replay, versión obsoleta, OC sobreconsumida, transición ilegal, estado imposible.
- **Concurrencia:** dos conexiones, deadlocks, folios, reservas, pagos.
- **Tenant:** fuga entre empresas, agregados, exportaciones.
- **Abuso:** paginación, mass assignment, enumeración, fuerza bruta, límites.
- **Infra:** secretos, headers, TLS, buckets, logs.

### 5.5 Bug bounty / red team

- **Interno (F6):** equipo rojo simulado con alcance definido (auth, tenant, dinero, archivos, agente).
- **Externo (opcional):** programa privado con reglas, recompensas, triage y SLA.
- **Regla:** un hallazgo crítico/alta **bloquea** el cierre; se corrige y se **revalida**.

### 5.6 Protocolo de evidencia

Cada tarea cerrada deja:
```
[FECHA] [FASE] [TAREA]
Comando: <comando exacto>
Salida: <cola relevante>
Archivos: <archivo:línea>
Resultado: PASS/FAIL
Riesgo residual: <si aplica>
```

### 5.7 Umbrales de salida (definición de "aprueba de balas")

No existe "100 % seguro"; se define un umbral objetivo:

- **0** hallazgos **críticos** y **altos** abiertos.
- **Medios:** mitigados o aceptados por el dueño con plan y fecha.
- **Bajos:** registrados en backlog.
- **Cobertura** de rutas críticas 100 %.
- **Concurrencia** probada en todos los invariantes de dinero/disponibilidad.
- **DR** probado: RTO/RPO definidos y medidos.
- **Restore** por empresa/módulo probado con datos ficticios.
- **Sin regresiones** en la suite completa.

---

## 6. Fases

> Plantilla de cada fase: Objetivo · Alcance · Prerrequisitos · Tareas · Entregables · Criterios de aceptación · **Gate de pruebas** · Rollback · Salida.

---

### F0 — Due diligence y línea base

**Estado:** `pendiente` (no ejecutada).

**Objetivo.** Decidir con evidencia entre **refactor**, **reconstrucción parcial** o **reconstrucción total**, y dejar una línea base reproducible. **No se cambia código de producto en F0.**

**Alcance.**
- Incluye: lectura de código, ejecución de suites, chequeo de deriva, mapa de acoplamiento, evaluación de cobertura y reproducibilidad, escaneo de seguridad base.
- No incluye: refactors, migraciones nuevas, cambios de esquema, despliegues.

**Prerrequisitos.**
- Autorización del dueño (DEC-15).
- Entorno local capaz de levantar PostgreSQL/Supabase.
- `git status` limpio o trabajo identificado.

**Tareas.**

| # | Tarea | Dueño | Entregable |
|---|---|---|---|
| F0.1 | Inventario de routers, servicios, modelos, tablas, pantallas y tests | `arquitectura` | Mapa actualizado |
| F0.2 | Leer servicios del núcleo y mapear escrituras cruzadas | `arquitectura` | Lista de acoplamientos |
| F0.3 | Ejecutar `make unit` y suite de integración con base limpia | `qa` | Salida real |
| F0.4 | Ejecutar E2E (si el entorno lo permite) | `qa` | Salida real |
| F0.5 | Chequeo de deriva esquema↔modelos | `datos` | Informe |
| F0.6 | Aplicar migraciones desde cero y comparar | `datos` | Informe |
| F0.7 | Escaneo base: SAST, secretos, dependencias | `auditor-seguridad` | Informe |
| F0.8 | Evaluar cobertura y reproducibilidad de pruebas | `qa` | Informe |
| F0.9 | Veredicto A/B/C con esfuerzo y riesgo | `orquestador` + `arquitectura` | Informe de decisión |
| F0.10 | Línea base limpia: reset + seed + CI con PostgreSQL; `DEBUG=false`; tests usan URL de test | `orquestador` + `qa` | Pipeline reproducible |

**Entregables.**
- `docs/qa/informes/F0-due-diligence.md` (evidencia + veredicto).
- Línea base: `reset + seed + CI` con PostgreSQL.
- Correcciones mínimas de entorno (no de lógica): `DEBUG=false`, tests aislados.

**Criterios de aceptación.**
- Existe un veredicto **justificado** con evidencia `archivo:línea`.
- La suite corre desde cero, sin datos previos, y se reproduce.
- Los tests **no** pueden escribir en la base de la aplicación.
- CI levanta PostgreSQL y aplica migraciones.

**Gate de pruebas.**
- `ruff`, `eslint`, `tsc` sin errores nuevos.
- `make unit` + integración + E2E con salida pegada.
- Deriva: 0 diferencias o lista exacta.
- SAST/secretos/dependencias: 0 críticos/altos.
- Evidencia fechada.

**Rollback.** No aplica (no hay cambios de producto). Si se tocó entorno, se revierte.

**Salida.** Veredicto A/B/C ratificado por el dueño + línea base reproducible. **Sin este veredicto no se inicia F1.**

---

### F1 — Consolidación a un solo piso

**Estado:** `pendiente`.

**Objetivo.** Eliminar `public` (legacy) y el cutover; dejar **un solo esquema** con todos los componentes del Núcleo.

**Alcance.**
- Incluye: absorber en el Núcleo las capacidades que hoy viven solo en legacy (nómina/liquidaciones, mantenimiento, tributario manual/IVA, export/import); borrar routers/pantallas/`api.ts` legacy; borrar `cutover_control` y middleware; renombrar el esquema (opcional); unificar el cliente HTTP.
- No incluye: módulos premium, agente operativo, DTE real.

**Prerrequisitos.** F0 cerrada.

**Tareas.**

| # | Tarea | Dueño | Entregable |
|---|---|---|---|
| F1.1 | Inventario legacy → componente del Núcleo | `arquitectura` | Matriz de absorción |
| F1.2 | Portar nómina/liquidaciones al componente C09 (con snapshot y bonos) | `backend` + `negocio-finanzas` | Servicio + pruebas |
| F1.3 | Portar mantenimiento (pautas + registro) al C10 | `backend` | Servicio + pruebas |
| F1.4 | Portar tributario manual + storage al C11 (sin SII) | `backend` | Servicio + pruebas |
| F1.5 | Portar export/import a utilidades del Núcleo | `backend` | Servicio + pruebas |
| F1.6 | Borrar routers, pantallas, modelos y `api.ts` legacy | `backend` + `frontend` | Diff limpio |
| F1.7 | Borrar `cutover_control`, middleware y servicio | `backend` + `datos` | Diff limpio |
| F1.8 | Renombrar esquema (decisión) y actualizar referencias | `datos` | Migración |
| F1.9 | Unificar cliente HTTP y navegación | `frontend` | Diff |
| F1.10 | Regresión completa | `qa` | Salida |

**Entregables.** Un esquema; 0 referencias a `public`; 0 referencias al cutover; suite verde.

**Criterios de aceptación.**
- `grep -rn "public\." backend/ frontend/ scripts/` → 0 (excluyendo documentación histórica).
- `grep -rn "cutover" backend/ frontend/` → 0 salvo histórico.
- Ninguna pantalla rota; navegación sin duplicados.
- Nómina, mantenimiento, tributario manual y export funcionan en el Núcleo.

**Gate de pruebas.**
- Regresión completa + E2E.
- Pruebas de nómina (casos numéricos), mantenimiento (km), tributario manual (documentos + storage), export.
- Integridad: no quedan FKs a `public`.
- SAST/secretos/dependencias.
- Revisión independiente del diff.

**Rollback.** Restaurar backup de la base local + `git revert` del commit de F1. No hay datos reales que perder.

**Salida.** Un solo piso; legacy eliminado; suite verde.

---

### F2 — Núcleo + conectores (plug & play)

**Estado:** `pendiente`.

**Objetivo.** Que cada componente del Núcleo publique su **Conector** y que un módulo se acople **sin modificar el Núcleo**.

**Alcance.**
- Incluye: especificación del conector; manifest + registry; hooks/interfaces/slots; seams genéricos; registro de tools del agente; gate de capacidades; registro de contactos; modelo de **solicitud** + **buzón** + **matriz de aprobación**; resolución de escrituras cruzadas; registro de UI (frontend); módulo de prueba.
- No incluye: runtime del agente (LLM/WhatsApp), módulos premium.

**Prerrequisitos.** F1 cerrada.

**Tareas.**

| # | Tarea | Dueño | Entregable |
|---|---|---|---|
| F2.1 | Especificar el **Conector** (interfaces/hooks/slots/seams) por componente | `arquitectura` | Documento de contrato |
| F2.2 | Implementar manifest + registry (backend) | `backend` | Código + pruebas |
| F2.3 | Implementar seams genéricos (custom fields, adjuntos, timeline, workflow, jobs, webhooks) | `backend` + `datos` | Código + migraciones |
| F2.4 | Implementar registry de slots + carga dinámica en frontend | `frontend` | Código + pruebas |
| F2.5 | Registrar tools del agente + gate de capacidades + contactos | `backend` + `datos` | Código + pruebas |
| F2.6 | Implementar **solicitudes** + **buzón** + **matriz de aprobación** | `backend` + `frontend` | Código + pruebas |
| F2.7 | Resolver escrituras cruzadas (facturación→viajes; alertas→facturación) | `backend` | Interfaces + diff |
| F2.8 | Módulo de prueba que se acopla sin tocar el Núcleo | `backend` + `frontend` | Módulo demo |
| F2.9 | Pruebas de contrato y de plug & play | `qa` | Salida |

**Entregables.** Conectores publicados; manifest/registry; slots; solicitudes/buzón/matriz; módulo demo acoplado.

**Criterios de aceptación.**
- Un módulo demo agrega endpoint + tabla + pantalla + tool **sin cambios en el Núcleo**.
- Apagar el módulo no rompe el Núcleo.
- Una escritura cruzada detectada por el check falla el build.
- La matriz de aprobación se impone en backend (403 si no corresponde).
- El buzón muestra badge rojo, se cierra sin borrar, y resuelve solo por aprobar/rechazar/cancelar.

**Gate de pruebas.**
- Contract tests (OpenAPI) + frontend tipado.
- Plug & play del módulo demo (instalar/desinstalar).
- Slots de UI (render condicional).
- Hooks (orden, no-op si módulo off).
- Solicitudes: estados, idempotencia, permisos, auditoría.
- SAST/secretos/dependencias + revisión independiente.

**Rollback.** `git revert` de F2; el Núcleo sin conectores sigue operando (los módulos no existen aún).

**Salida.** Plug & play demostrado; Núcleo intacto.

---

### F3 — Tenancy, seguridad y plataforma

**Estado:** `pendiente`.

**Objetivo.** Aislamiento real entre empresas + acceso total auditado del dueño.

**Alcance.**
- Incluye: RLS + `FORCE RLS`; rol `app_tenant` sin bypass; `SET LOCAL app.empresa_id`; FKs compuestas; FK `auth_id`; plano plataforma (`app_platform`, consola, MFA, auditoría, impersonación); rate limiting; gestión de secretos; pruebas de fuga.
- No incluye: módulos premium.

**Prerrequisitos.** F2 cerrada.

**Tareas.**

| # | Tarea | Dueño | Entregable |
|---|---|---|---|
| F3.1 | Políticas RLS por tabla y operación | `datos` | Migración |
| F3.2 | Rol `app_tenant` sin `BYPASSRLS` + grants mínimos | `datos` | Migración + config |
| F3.3 | Contexto por transacción (`SET LOCAL`) en cada request | `backend` | Código |
| F3.4 | Cerrar huecos: FK compuesta reservas, FK `auth_id` | `datos` | Migración |
| F3.5 | Plano plataforma: rol, consola, acceso total auditado, impersonación | `backend` + `frontend` | Código + pruebas |
| F3.6 | MFA + rate limit + secretos | `backend` + `auditor-seguridad` | Código + config |
| F3.7 | Pruebas de aislamiento con rol real (2 empresas) | `qa` | Salida |
| F3.8 | Pentesting de auth/IDOR/tenant | `auditor-seguridad` | Informe |

**Entregables.** RLS efectivo; consola de plataforma; pruebas de aislamiento; informe de pentest.

**Criterios de aceptación.**
- Con `app_tenant` y contexto A, leer/escribir B → 0 filas / `42501`.
- El dueño accede desde la consola, con cada acceso auditado.
- Sin `BYPASSRLS` en el rol de tenant.
- 0 hallazgos críticos/altos en auth/tenant.

**Gate de pruebas.**
- Aislamiento 2 empresas (lectura/escritura/agregados).
- Pentest: JWT, sesión, IDOR, escalada, rate limit.
- DAST baseline (ZAP).
- SAST/secretos/dependencias.
- Revisión independiente.

**Rollback.** Revertir políticas/rol (con cuidado: puede dejar sin acceso) + restore de backup. Documentar.

**Salida.** Aislamiento probado; plataforma auditada.

---

### F4 — Integridad, dinero y trazabilidad

**Estado:** `pendiente`.

**Objetivo.** Que el Núcleo no permita estados inválidos ni duplique dinero, y que todo sea trazable.

**Alcance.**
- Incluye: invariantes de facturación/pagos/NC, gastos, OC/tarifas, auditoría completa, **odómetro** (registro multi-fuente, validación, alertas, corrección), nómina con snapshot, idempotencia, concurrencia.
- No incluye: módulos premium.

**Prerrequisitos.** F3 cerrada.

**Tareas.**

| # | Tarea | Dueño | Entregable |
|---|---|---|---|
| F4.1 | Factura emitida inmutable; pagos/NC no borrables; vínculo factura↔viaje inmutable | `datos` | Migración + pruebas |
| F4.2 | Tope de pagos/NC con `FOR UPDATE`; idempotencia | `datos` + `backend` | Migración + código |
| F4.3 | Gasto aprobado inmutable, no borrable, no duplicable | `datos` | Migración |
| F4.4 | OC: sobregiro solo aprobado; tarifa en uso no se borra | `datos` | Migración |
| F4.5 | Auditoría 100 % + partición + retención; `cutover` ya no existe | `datos` | Migración |
| F4.6 | **Odómetro**: log multi-fuente, validación km descendente, alertas, corrección, `km_actual` derivado | `datos` + `backend` + `frontend` | Código + pruebas |
| F4.7 | Nómina: motor de fórmulas (Decimal), snapshot al emitir, bonos | `backend` + `negocio-finanzas` | Código + pruebas |
| F4.8 | Pruebas de mutación + concurrencia (2 conexiones) | `qa` | Salida |
| F4.9 | Property-based tests (montos/fechas) | `qa` | Salida |

**Entregables.** Invariantes impuestos; odómetro; nómina con snapshot; pruebas de mutación y concurrencia.

**Criterios de aceptación.**
- Cada invariante crítico tiene mecanismo en DB + prueba que falla al retirarlo.
- Dos conexiones: exactamente una gana en solape/pago/folio.
- Odómetro: km menor → pendiente + alerta; corrección con rastro; `km_actual` reconstruible.
- Nómina: documento emitido reproducible; sin `float`.
- Auditoría: `UPDATE/DELETE/TRUNCATE` bloqueados; cobertura completa.

**Gate de pruebas.**
- Mutación en cada garantía.
- Concurrencia real (2 conexiones) en reservas, pagos, folio, OC.
- Property-based (Hypothesis) en dinero/fechas.
- Adversarial de dinero (negativos, sobrepago, doble clic, replay).
- Auditoría append-only.
- SAST/secretos/dependencias + revisión independiente.

**Rollback.** Migraciones con rollback documentado; backup verificado antes de aplicar.

**Salida.** Dinero y estado a prueba de fallos.

---

### F5 — Storage, backups y recuperación

**Estado:** `pendiente`.

**Objetivo.** Documentos seguros y recuperación por empresa/módulo/fecha, más archivo anual reproducible.

**Alcance.**
- Incluye: object storage + metadatos; prefijos por tenant; URLs firmadas; versionado; ciclo de vida; cuotas (blando/duro/gracia/archiving); PITR; snapshots; motor de restauración con grupos de consistencia; "backup del backup"; archivo anual/offboarding (paquete, verificación, purga, no re-carga).
- No incluye: módulos premium.

**Prerrequisitos.** F4 cerrada.

**Tareas.**

| # | Tarea | Dueño | Entregable |
|---|---|---|---|
| F5.1 | Object storage + metadatos + prefijos + URLs firmadas | `backend` + `datos` + `frontend` | Código + pruebas |
| F5.2 | Versionado, ciclo de vida, `object lock` | `datos` | Config + pruebas |
| F5.3 | Cuotas por plan + límites + archiving | `backend` | Código + pruebas |
| F5.4 | PITR + snapshots diarios/semanales/mensuales + copia inmutable | `datos` | Config + runbook |
| F5.5 | Motor de restauración (sandbox → validación → diff → promoción) + grupos de consistencia | `datos` + `backend` | Código + pruebas |
| F5.6 | Archivo anual/offboarding (paquete reproducible, cifrado, verificación, purga) | `backend` + `datos` | Código + pruebas |
| F5.7 | Restore drills + caos | `qa` + `datos` | Salida |
| F5.8 | Seguridad de storage (MIME, path, visor, expiración) | `auditor-seguridad` | Informe |

**Entregables.** Storage operativo; backups/PITR; restore por módulo/fecha; archivo anual.

**Criterios de aceptación.**
- Storage lleno: bloquea subidas, no rompe operación, no borra.
- Restore por empresa/módulo/fecha probado, con validación y promoción.
- Restauración de módulos acoplados respeta grupos de consistencia o bloquea.
- Archivo anual: paquete verificable + reproducible + purga auditada.
- "Backup del backup" probado.

**Gate de pruebas.**
- Restore drills con conteos/checksums antes/después.
- Caos: matar conexión/proceso durante restore; disco lleno; storage caído.
- Seguridad de URLs firmadas y uploads.
- Verificación de purga (no quedan filas/archivos/backups de la empresa).
- Prueba de "no re-carga" (el paquete no se puede importar).
- SAST/secretos/dependencias + revisión independiente.

**Rollback.** Restaurar desde el snapshot pre-operación; documentar.

**Salida.** Recuperación y archivo probados.

---

### F6 — Endurecimiento final (sistema completo)

**Estado:** `pendiente`.

**Objetivo.** Someter el Núcleo completo a pruebas de nivel **bug bounty / red team** antes de exponerlo a clientes.

**Alcance.**
- Incluye: threat modeling, bug bounty interno, red team, fuzzing, DAST full, carga, caos, DR, UAT por rol, revisión de código, SBOM, dependencias.
- No incluye: módulos premium.

**Prerrequisitos.** F5 cerrada.

**Tareas.**

| # | Tarea | Dueño | Entregable |
|---|---|---|---|
| F6.1 | Threat model + superficie de ataque | `auditor-seguridad` | Documento |
| F6.2 | Bug bounty interno / red team | `auditor-seguridad` + `qa` | Informe con hallazgos |
| F6.3 | Fuzzing API (Schemathesis) + inputs | `qa` | Salida |
| F6.4 | DAST full (ZAP) | `auditor-seguridad` | Informe |
| F6.5 | Carga y estrés (k6/Locust) | `qa` | Informe de performance |
| F6.6 | Caos (DB, worker, storage, red, disco) | `qa` + `datos` | Informe |
| F6.7 | DR: restore total + RTO/RPO | `datos` | Informe |
| F6.8 | UAT por rol (todos los componentes) | `qa` + dueño | Acta |
| F6.9 | Revisión de código + SBOM + dependencias | `orquestador` + `auditor-seguridad` | Informe |
| F6.10 | Corrección y **revalidación** de hallazgos | implementadores + auditor | Evidencia |

**Entregables.** Informe de bug bounty/red team; performance; DR; UAT; SBOM; 0 críticos/altos abiertos.

**Criterios de aceptación.**
- 0 hallazgos críticos/altos abiertos.
- Medios mitigados/aceptados con plan.
- Performance dentro de umbrales definidos (AB-05).
- DR probado con RTO/RPO.
- UAT firmada por rol.

**Gate de pruebas.** Es el gate completo: SAST+DAST+fuzzing+pentest+carga+caos+DR+UAT+revisión+SBOM. **Ningún hallazgo crítico/alta pasa a F7.**

**Rollback.** No aplica a la fase; cada corrección se revierte con `git revert` si rompe.

**Salida.** Núcleo endurecido y validado.

---

### F7 — Staging y salida a producción

**Estado:** `pendiente`.

**Objetivo.** Operar el Núcleo en un entorno real (staging) con datos ficticios, y dejar lista la salida a producción.

**Alcance.**
- Incluye: despliegue staging (Supabase Cloud + Render + Vercel, o VPS), seed, smoke, observabilidad, monitoreo, alertas, backups automáticos, runbooks, onboarding del primer tenant (si el dueño lo decide).
- No incluye: módulos premium.

**Prerrequisitos.** F6 cerrada + decisiones AB resueltas.

**Tareas.**

| # | Tarea | Dueño | Entregable |
|---|---|---|---|
| F7.1 | Definir proveedor y arquitectura de despliegue | `arquitectura` + dueño | ADR de despliegue |
| F7.2 | Staging: backend, frontend, base, storage | `orquestador` | Entorno arriba |
| F7.3 | Migraciones + seed + smoke | `datos` + `qa` | Salida |
| F7.4 | Observabilidad (logs, métricas, trazas, alertas 5xx) | `backend` | Config |
| F7.5 | Backups automáticos + restore drill en staging | `datos` | Salida |
| F7.6 | Seguridad de despliegue (secretos, CORS, TLS, buckets, anon key) | `auditor-seguridad` | Informe |
| F7.7 | Runbooks (incidente, rollback, restore) | `orquestador` | Documentos |
| F7.8 | Checklist de producción + onboarding del primer tenant | `orquestador` + dueño | Acta |

**Entregables.** Staging operando; monitoreo; backups; runbooks; checklist; acta.

**Criterios de aceptación.**
- Staging reproducible desde cero.
- `make test` + E2E verdes contra staging.
- Backup automático + restore probado.
- 0 secretos expuestos; CORS/TLS/buckets correctos.
- Runbooks probados.

**Gate de pruebas.**
- Smoke + E2E en staging.
- Restore drill en staging.
- Escaneo de configuración/secretos.
- Revisión independiente.
- Aprobación del dueño para producción.

**Rollback.** Volver a la versión anterior + restore; documentar.

**Salida.** Núcleo listo para el primer cliente real.

---

## 7. Matriz de trazabilidad (se llena durante la ejecución)

| Regla/Invariante | Componente | Mecanismo (DB/servicio) | Prueba | Estado |
|---|---|---|---|---|
| R-01 comisión | C09 | Servicio + snapshot | `test_*` | pendiente |
| R-02 licencia A5 | C02/C03 | Trigger | `test_*` | pendiente |
| INV-D04 ocupación | C03 | Trigger + `EXCLUDE` | concurrencia | pendiente |
| INV-F01 pagos ≤ total | C05 | Trigger + `FOR UPDATE` | concurrencia | pendiente |
| INV-F02 pago idempotente | C05 | `idempotency_key` | doble envío | pendiente |
| INV-F03 factura inmutable | C05 | Trigger | mutación | pendiente |
| INV-G04 gasto inmutable | C06 | Trigger | mutación | pendiente |
| INV-G05 gasto no duplicable | C06 | `UNIQUE` | concurrencia | pendiente |
| INV-T01 aislamiento | C01/C14 | RLS | 2 empresas | pendiente |
| Odómetro descendente | C02 | Trigger + alerta | funcional | pendiente |
| Auditoría append-only | C12 | Trigger | mutación | pendiente |
| Restore por módulo | C15 | Motor restore | drill | pendiente |
| Archivo anual | C15 | Pipeline | verificación | pendiente |

> Se completa por fase; una fila sin prueba se marca **"sin cobertura"**, no se omite.

---

## 8. Riesgos y decisiones abiertas

| ID | Riesgo/decisión | Impacto | Mitigación |
|---|---|---|---|
| AB-01 | Retención legal antes de purgar | Alto | Validar con contador/abogado; purga bloqueada por defecto |
| AB-02 | Roles `secretaría`/`mantenimiento` | Medio | Matriz de permisos + rol configurable |
| AB-03 | Formato del paquete de archivo | Medio | Propuesta SQLite+CSV+PDF+visor; validar |
| AB-04 | LLM/WhatsApp y privacidad | Alto | Contrato, sin entrenamiento, opción self-hosted |
| AB-05 | Umbrales de performance/RTO/RPO | Medio | Definir antes de F6 |
| AB-06 | Retención de backups | Medio | 10 días free; tramos pagos |
| R-01 | Complejidad del agente/LLM | Alto | Fuera de alcance; diseño con guardarraíles |
| R-02 | RLS mal configurado filtra | Crítico | Pruebas con rol real + pentest |
| R-03 | Restore de módulos acoplados | Alto | Grupos de consistencia + validación |
| R-04 | Purga vs backups | Alto | Purga explícita, verificada, auditada |
| R-05 | Deuda de la documentación | Medio | F0 sincroniza; actualizar por fase |

---

## 9. Anexos

### 9.1 Checklist de cierre de fase

- [ ] Objetivo y alcance cumplidos.
- [ ] Tareas con evidencia.
- [ ] Criterios de aceptación verificados.
- [ ] Gate de pruebas aprobado.
- [ ] Riesgos residuales documentados.
- [ ] Rollback probado o documentado.
- [ ] Documentación actualizada (`docs/estado.md`, este plan).
- [ ] Revisión independiente (si riesgo Alto).
- [ ] Aprobación del dueño.

### 9.2 Comandos de referencia (adaptar al repo)

```bash
make unit
make test
make e2e
ruff check backend
npx tsc --noEmit
npm run lint
pytest --cov
npx playwright test
# herramientas propuestas (instalar en F0 si faltan)
semgrep --config auto
bandit -r backend
gitleaks detect
pip-audit
npm audit
trivy fs .
schemathesis run <openapi>
zap-baseline.py -t <url>
k6 run <script>
```

### 9.3 Plantilla de evidencia

```
[FECHA] [FASE] [TAREA]
Comando:
Salida:
Archivos:
Resultado: PASS/FAIL
Riesgo residual:
```

### 9.4 Regla final

> **Una fase no se cierra porque el código "parece" listo. Se cierra cuando el gate de pruebas lo demuestra con evidencia, y un tercero puede repetirlo.**

---

*Fin del plan. Documento vivo: se actualiza al cerrar cada fase, sin reescribir la historia.*
