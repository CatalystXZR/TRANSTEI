# ADR-0006: Identidad y alcance de las tools del agente — `ContextoAgente` sin impersonar roles del núcleo

- **Estado:** **Aceptado (2026-10-30)** — aceptado por delegación de criterio del
  dueño (misma delegación invocada en ADR-0005); revocable si el dueño objeta.
  Habilita O2.1/O2.2. No cambia el runtime ni el esquema.
- **Fecha:** 2026-10-30
- **Decide:** `arquitectura`. Lo ejecuta `backend` en O2.1/O2.2.
- **Relación:** concreta la frontera de ADR-0003 §4 ("el agente es lector y creador de
  Solicitudes") y §13.1 (ACL por número) para el punto que ambos dejaron abierto: **con
  qué identidad se ejecuta una tool**. No modifica ADR-0003, ADR-0004 ni ADR-0005.
- **Documento operativo:** [`conector-agente-whatsapp.md`](../conector-agente-whatsapp.md)
  (§4 registry/gate, §5 catálogo de tools).

---

## Contexto

Hechos verificados en esta sesión (lectura estática; sin base ni ejecución):

| # | Hecho | Nivel | Evidencia |
|---|---|---|---|
| 1 | La autenticación del núcleo exige JWT de Supabase **y** `X-Empresa-ID`; el rol sale de `nucleo.usuarios_empresa` | 🟢 | `backend/app/nucleo/deps.py:50-55,68-79` |
| 2 | `ContextoEmpresa` exige un `RolEmpresa` del enum del núcleo (`admin, gerente, despacho, contador, tesoreria, taller, conductor, auditor`) | 🟢 | `backend/app/nucleo/deps.py:30-35`; `backend/app/nucleo/permisos.py:58-139` |
| 3 | El contacto de WhatsApp tiene su **propio** enum de rol (`admin, cliente_final, conductor`) y **no siempre es miembro** (`cliente_final` no tiene fila en `usuarios_empresa`) | 🟢 | `supabase/migrations/0021_agente_whatsapp.sql:151`; `docs/datos/agente-esquema.md:225-228` |
| 4 | La PWA del conductor resuelve la ficha de chofer por `Chofer.auth_id` (usuario Supabase), no por identidad de contacto | 🟢 | `backend/app/nucleo/servicio_conductor.py:90-115` |
| 5 | Las escrituras del agente ya tienen camino propio y no necesitan rol del núcleo: crean filas en `nucleo.solicitudes` / `nucleo.hoja_ruta` (`propuesto`) | 🟢 | `0021:388-433,495-523`; ADR-0003 §14 |

Consecuencia: un contacto de WhatsApp **no es** un usuario del núcleo. No hay JWT, no hay
`auth_id` y `cliente_final` no existe en `RolEmpresa`.

---

## Problema

**En una frase verificable:** *cuando el runtime invoca una tool en nombre de un contacto
de WhatsApp, ¿con qué identidad y con qué alcance se ejecuta la consulta, de modo que la
autorización sea la ACL del número y no un rol del núcleo que el contacto no tiene?*

Hoy no existe respuesta en código: ni `ContextoAgente` ni tools ni gate (0 referencias a
las tablas del módulo en `backend/`, verificado con `rg`). Si `backend` resuelve esto por
su cuenta, el riesgo es que invente una de dos cosas malas: (a) fabricar un
`ContextoEmpresa` con un rol que el contacto no tiene, o (b) saltarse el filtro por
entidad y confiar en el `empresa_id`.

---

## Alternativas

| Alternativa | Ventajas | Costes/riesgos | Reversible | Impacto en legacy | Impacto en datos |
|---|---|---|---|---|---|
| **A. Fabricar un `ContextoEmpresa`** (rol sintético mapeado desde `rol_contacto_whatsapp`) | Cero código nuevo de contexto; se reutilizan servicios existentes | **Miente en el tipo**: `cliente_final` no es `RolEmpresa`; `ServicioConductor` seguiría resolviendo por `auth_id` (`servicio_conductor.py:96-104`) y fallaría; invita a que un `cliente_final` herede permisos de un rol del núcleo (`permisos.py:58-139`) y la ACL quede decorativa | Alta | Ninguno | Ninguno |
| **B (recomendada). `ContextoAgente` + adaptadores de lectura con filtro forzado** | Identidad honesta (contacto, empresa, rol, entidad); la ACL es la única autorización de tools; no toca servicios existentes ni el legacy; se puede probar por paridad | Duplica el **filtro** de ~15 consultas de lectura; riesgo de deriva entre la consulta humana y la del agente | Alta (paquete nuevo; se borra sin migración) | Ninguno | Ninguno: solo lee tablas existentes y escribe tablas del módulo |
| **C. Refactor: los servicios del núcleo dependen de un protocolo `Scope`** (empresa + actor + entidad) en vez de `ContextoEmpresa` | Una sola implementación de cada consulta; elimina la duplicación de B de raíz | Toca ~10 servicios y sus pruebas; riesgo Alto en un área ya auditada; no es reversible con un `revert` pequeño | Media | Ninguno, pero el diff es grande | Ninguno |

---

## Decisión

**B.** El runtime no impersona a nadie:

1. La identidad de ejecución es un **`ContextoAgente`** resuelto **desde la fila del
   contacto** (`nucleo.contactos_whatsapp`) y verificado contra el teléfono del mensaje:
   `{empresa_id, contacto_id, rol, entidad_id, conversacion_id, mensaje_id, request_id}`.
   `empresa_id` **nunca** se toma del DI ni del cuerpo del mensaje (ADR-0003 §3.4, §5 fila 2).
2. La tool fija el contexto de base con `app.empresa_id` (RLS de `0020`/`0021`) y **no**
   fija `nucleo.auth_id` con una identidad de tenant; `created_by` se escribe explícito
   (`'agente:<contacto_id>'`) en las filas del módulo.
3. **La única autorización de una tool es el gate**: rol del contacto + módulo activo por
   empresa + `nucleo.permisos_contacto` (ausencia = deny). `requiere_permiso` y la matriz
   `ROLES_PERMISOS` **no participan** en el camino del agente.
4. **Toda entidad se fuerza desde el contacto** (`cliente_id` o `chofer_id`). Los IDs que
   trae el DI se aceptan solo como *referencias ya devueltas por una tool en la misma
   conversación* y se **re-validan** contra el alcance antes de usarse (anti-IDOR).
5. El agente escribe **solo** tablas del módulo (`conversacion_mensajes`, `hoja_ruta` en
   `propuesto`, `solicitudes`, `auditoria_consultas_agente`); ninguna tabla de negocio.

---

## Consecuencias

**Positivas**

- La ACL por número queda como la garantía real de la aplicación, que es lo que exige
  ADR-0003 §13.5 mientras RLS solo aísla por empresa.
- No se introduce un segundo sistema de permisos: la ACL (contacto) y la matriz de roles
  (humanos) siguen separadas por diseño.
- El paquete es aditivo: si se retira el módulo, se borra sin tocar el núcleo.

**Negativas / deuda**

- Duplicación de filtros de lectura entre servicio humano y tool. **Se paga con pruebas de
  paridad** (misma entidad, mismo resultado) y con la regla de que la tool no reimplementa
  reglas de negocio, solo el filtro y la proyección.
- Si el catálogo de tools crece o aparece un segundo consumidor (p. ej. la PWA), la
  alternativa C pasa a ser la correcta. **Condición de pago:** más de ~20 tools o una
  tercera copia del mismo filtro.

---

## Plan de migración y rollback

1. `backend` crea `backend/app/nucleo/agente/` (contexto, descriptores, registry, gate,
   tools, servicio de solicitudes, router) sin tocar servicios existentes.
2. `backend` agrega los permisos de módulo (`agente:buzon`, `agente:aprobar`,
   `agente:contactos`) a `permisos.py` **solo para endpoints humanos del buzón**; no se
   usan en el camino del agente.
3. Rollback: `git revert` del paquete + apagar el módulo en el manifest/flag. No hay
   migración asociada a esta decisión.

---

## Criterios de aceptación

1. Un contacto `cliente_final` de la empresa A que pide un flete de la empresa B o de otro
   cliente recibe **denegación** y **cero filas** (prueba de integración con dos contactos
   y dos clientes).
2. Un contacto `conductor` no puede leer el viaje de otro chofer ni la hoja de ruta de otro
   contacto.
3. Quitar el filtro por entidad del adaptador hace **fallar** la prueba (mutación).
4. El camino del agente no importa `requiere_permiso` ni construye `ContextoEmpresa`
   (verificable con `rg` en el paquete y con una prueba que falla si aparece).
5. Para la misma entidad, la tool devuelve los mismos valores que el endpoint humano
   equivalente (prueba de paridad, al menos una por componente).

---

## Riesgos y preguntas abiertas

- **Deriva de consultas duplicadas:** mitigada por paridad, no eliminada. Se cierra con C.
- **Compatibilidad con el runtime:** el `ContextoAgente` debe poder construirse sin
  request HTTP (el runtime es un worker). Es una decisión de `backend`; este ADR solo fija
  los campos y la regla de resolución.
- **Contactos `admin` vinculados a una membresía** (`usuario_empresa_id`, `0021:189`): no
  se impersona su rol; su acceso sigue limitado por la ACL del número. Si el negocio
  quiere que un admin tenga "todo", se logra con filas de ACL explícitas, no con el rol.
