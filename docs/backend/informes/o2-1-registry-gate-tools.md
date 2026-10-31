# O2.1 — Registry, gate de cuatro llaves y tools de lectura de `despacho`

> Fecha: 2026-10-31 · Agente: `orquestador` (implementación directa; los subagentes
> `datos` y `backend` no estaban disponibles por límite de uso)
> Contrato vigente: `docs/arquitectura/conector-agente-whatsapp.md` (§2, §3, §4, §6.5, §7)
> Riesgo: **Alto** (autorización, aislamiento multiempresa, auditoría, exposición de datos)
> Estado: implementado, verificado y **revisado de forma independiente**
> (`docs/seguridad/hallazgos-o2-1.md`, SEC-030…SEC-040). 7 hallazgos corregidos y
> con prueba de regresión; SEC-033 escalado al contrato; SEC-038/039 preexistentes
> no atribuibles a este cambio.

## 1. Qué se implementó

Paquete nuevo `backend/app/nucleo/agente/`, sin tocar el legacy ni el esquema.

| Archivo | Contenido | Contrato |
|---|---|---|
| `contexto.py` (190 l.) | `RolContacto`, `EstadoOtp`, `ContextoAgente`, `normalizar_telefono`, `contexto_de_agente`, `resolver_contacto` (fail-closed) | §4.1, ADR-0006 |
| `tipos.py` (39 l.) | `ResultadoTool` (`datos`, `filas`, `total`, `truncado`, `ids`) | §3.4 |
| `manifest.py` (699 l.) | Modelos Pydantic `extra=forbid`/`strict`, V1–V16, validador JSON Schema subset fail-closed, `EntradaInvalida` | §2.4, §3.1, §3.3 |
| `ejecutores.py` (38 l.) | Allow-list `EJECUTORES` (`MappingProxyType`) | §3.4 |
| `tools/despacho.py` (318 l.) | C1 `mis_fletes`, K1 `mis_viajes_asignados`, A1 `viajes_del_dia`; SQL fijo parametrizado | §5.2–§5.4 |
| `gate.py` (238 l.) | `Decision`, `autorizar` pura, `FuenteGateBD`, 6 compuertas en orden §4.3, sin caché | §4.3–§4.4, §4.7–§4.8 |
| `auditoria.py` (114 l.) | INSERT append-only, `datos_tocados` (§7.3), nunca propaga | §7.2–§7.5 |
| `registry.py` (533 l.) | `Registry.invocar`: gate → entrada → timeout → salida → auditoría; `cargar_registry` fail-closed | §2.5, §4.5, §4.10 |
| `api.py` (119 l.) | `GET /nucleo/agente/estado` | §6.5 |

Wiring (aditivo):

| Archivo:línea | Cambio |
|---|---|
| `backend/app/nucleo/permisos.py:15-19,49,65-67` | `PERMISOS_AGENTE`; `admin` los hereda; **`gerente` excluido** (AB-02, deny-by-default) |
| `backend/app/main.py:277-303` | Handler `ProgrammingError` → 403 en `42501` (el `42501` no es `IntegrityError`) |
| `backend/app/api/router.py:18,46` | Inclusión del router del agente |
| `Makefile:66-67` | `test_agente_manifest.py` + `test_agente_gate.py` en `make unit` |

## 2. Evidencia de ejecución

```bash
# Unitarias del paquete nuevo
$ .venv/bin/python -m pytest tests/test_agente_manifest.py tests/test_agente_gate.py
57 passed

# Integración real contra tei_test (motor del núcleo como tei_app)
$ NUCLEO_TEST_DATABASE_URL=…/tei_test NUCLEO_DATABASE_URL=…tei_app…/tei_test \
    .venv/bin/python -m pytest tests/test_agente_o2_1_integracion.py -rs
17 passed

# Gate del proyecto (ahora sí incluye las unitarias nuevas)
$ make unit
124 passed

# Suite completa
$ make test
304 passed, 0 failed, 0 skipped
```

`ruff` sobre el paquete nuevo: solo 3 × `B008` (`Depends` en defaults de FastAPI),
patrón idéntico al de todos los `api_*.py` del repo (`api_gastos.py:30-38`). El
repo no tiene baseline limpio de `ruff` (579 hallazgos preexistentes en `app/`) y
no hay target de lint, así que no es un gate.

## 3. Defectos encontrados durante la verificación

| # | Defecto | Causa | Corrección |
|---|---|---|---|
| D1 | `AttributeError: 'ResultadoTool' object has no attribute 'truncado'` | `_envelope_ok` (`registry.py:134`) leía un campo que `tipos.py` no declaraba; 4/16 pruebas de integración fallaban | Campo `truncado: bool` en `ResultadoTool` + helper `_resultado()` en `tools/despacho.py:38` que calcula `truncado` **una vez** y lo coloca en `datos` y en el envelope; imposible que discrepen |
| D2 | `InsufficientPrivilege: permission denied for table modulos_empresa` en el fixture | El fixture escribía con `postgres`, que tiene **solo SELECT** sobre las tablas del módulo (los GRANT de 0021/0023 son para `tei_app`) | Fixtures escriben con `tei_app` (`_dsn_app()` desde `NUCLEO_DATABASE_URL`), con `app.empresa_id` de sesión |
| D3 | `test_modulo_apagado_deniega` iba a fallar por D2 | Usaba `_conexion(escenario["dsn"])` (postgres) para el flag | Usa `_dsn_app()` + `_fijar_empresa` |
| D4 | `main.py` registraba `repr(exc)` en errores de BD | El repr de `StatementError` incluye SQL y **parámetros ligados** → riesgo de PII en logs (AGENTS.md §4) | Se registra `sqlstate` + nombre de la clase, nunca `repr` |
| D5 | `registry.py` usaba `logger.exception` en toda tool fallida | Mismo riesgo que D4 (traceback con parámetros) | `SQLAlchemyError` → log tipado sin traceback; error no-BD → traceback (es un bug de código, sin parámetros) |

Ningún defecto se cerró desactivando una prueba: no hay `skip`/`xfail` nuevos y las
16 pruebas de integración corren de verdad (`-rs` no reporta omisiones).

## 4. Decisiones de interpretación del contrato

1. **V5 y los `$ref`.** El texto de V5 exige que todo `$ref` empiece con `tools/`,
   pero §3.1 define `entrada`/`salida` como `schemas/<archivo>.json`. Se interpreta
   V5 como aplicable a los `$ref` de `tools[]` del manifiesto; los de un descriptor
   deben empezar con `schemas/`. Misma función de resolución para ambos: rechaza
   rutas absolutas, `..`, `\`, fragmentos y archivos inexistentes, y verifica que el
   destino quede dentro del paquete (`manifest.py:_resolver_ref`).
2. **Validador JSON Schema propio.** `jsonschema` no está instalado y no se autorizó
   instalar dependencias. Se implementa el subconjunto realmente usado
   (`type`, `enum`, `const`, `format` date-time/date/uuid, `minimum`/`maximum`,
   `required`, `properties`, `additionalProperties=false`, `items`,
   `minItems`/`maxItems`, `minLength`/`maxLength`, `pattern`). **Cualquier keyword
   desconocida invalida el schema** (fail-closed): un portero que ignora lo que no
   entiende no es estricto.
3. **Reglas de §3.3 sin número V.** Se aplican y se reportan con la V más cercana:
   campos de autoridad en el body (`empresa_id`, `contacto_id`, `rol`,
   `usuario_empresa_id`, `version`) → V14; palabras de SQL (`sql`, `query`, `tabla`,
   `where`, `orden`, `join`, `select`) → V13.
4. **Sin corrección silenciosa.** Un valor fuera de rango no se recorta: el
   manifiesto completo se rechaza, el registry queda con 0 tools y la API sigue
   viva (§2.5), que es lo que exige el contrato.
5. **V3/V4/V15 conservan su número de regla.** Se validan explícitamente en
   `_validar_manifiesto` en vez de con `Literal`, para que el diagnóstico diga `V3`
   y no un `V2` genérico.

## 5. Hueco de contrato detectado (§4.1) — **requiere decisión, no se improvisó**

El contrato §4.1 paso 2 dice: *"se busca `nucleo.contactos_whatsapp` por `telefono`
con `activo=true`"*, es decir una búsqueda **global** por teléfono. Bajo RLS eso es
imposible con el rol de la aplicación:

```text
$ psql como tei_app …
tei_app sin app.empresa_id   -> 0 filas
tei_app con empresa_id       -> 1 filas
tei_app con empresa ajena    -> 0 filas
```

La política es `tenant_empresa … using (empresa_id = nucleo.ctx_empresa())`
(`0021_agente_whatsapp.sql:805-813`), aplicada a `contactos_whatsapp`. Sin
`app.empresa_id`, la fila existe pero es invisible. Y no hay tabla ni columna de
ruteo (`wa_phone_number_id` → `empresa_id`): la única columna relacionada es
`conversacion_mensajes.wa_message_id`, que es por mensaje, no por número.

**Mitigación aplicada (provisional, declarada):** `resolver_contacto(empresa_id,
telefono)` exige `empresa_id` explícito y es fail-closed. El runtime debe obtenerlo
del ruteo de Meta (cada número/WABA pertenece a una empresa).

**Lo que falta y de quién es la decisión:** cómo se obtiene `empresa_id` en el
runtime. Opciones (no decididas, no implementadas):
(a) configuración de despliegue por número de Meta — válido para el piloto, no
para multiempresa real;
(b) tabla de ruteo `wa_phone_number_id → empresa_id` con política propia;
(c) función `SECURITY DEFINER` de búsqueda acotada, con revisión de seguridad.
Escalar a `arquitectura` (ADR o actualización del contrato) **antes** de O2.2.

## 6. Garantías que sí quedaron demostradas

| Garantía | Cómo se probó |
|---|---|
| El cliente solo ve sus fletes | `test_c1_devuelve_solo_los_fletes_del_cliente` compara contra el `count(*)` de su `cliente_id`; el JSON no contiene `costo`, `margen`, `patente`, `chofer` ni `valor_flete` |
| El conductor solo ve sus viajes | `test_k1_filtra_por_chofer` compara el conjunto de IDs con el de la BD para ese `chofer_id` |
| A1 usa el día calendario de Chile, no UTC | `test_a1_usa_el_dia_de_chile` + `_rango_dia_chile(2026-09-06)` = 23 h (cambio de hora) |
| Rol equivocado no se salva con ACL | `test_rol_equivocado_no_usa_acl`: el chofer tiene ACL de `despacho` pero pide una tool de cliente → deniega en `rol` |
| ACL de componente ≠ ACL de variable | `test_sin_acl_deniega_componente` vs `test_variable_en_false_deniega_variable`, con `nivel` y `variable` en el error |
| Módulo apagado deniega aunque la ACL esté completa | `test_modulo_apagado_deniega` (flag escrito con `tei_app`) |
| Identidad no verificada deniega | `test_otp_pendiente_deniega_identidad` |
| Aislamiento entre empresas | `test_resolver_contacto_deniega_otra_empresa` → `None` |
| Entrada inválida se audita con `acceso_otorgado=true` | `test_entrada_invalida_audita_acceso_otorgado` (§7.5) |
| Cada intento deja una fila de auditoría | todas las pruebas de denegación leen la última fila y verifican `acceso_otorgado`, `variable`, `respuesta`, `request_id` |
| `42501` → 403 y no 500 | `test_42501_es_programming_error_y_se_traduce_a_403` (verifica `orig.sqlstate` real con `tei_app`) |

## 7. No verificado / limitaciones conocidas

- 🔴 **Timeout por tool** (`statement_timeout`): implementado (`registry.py:_ejecutar`),
  sin prueba dedicada que demuestre `57014` → `TIMEOUT_TOOL` con una consulta lenta
  real. `clasificar_error` sí está probado unitariamente.
- 🟡 **Higiene de `tei_test`**: las pruebas **dejan** contactos (`+56900000101…106`)
  y filas de auditoría, porque la tabla es append-only y `contacto_id` es FK NOT NULL.
  El teardown apaga ACL y flag (no borra: `tei_app` no tiene DELETE). `make test-db`
  refresca la base.
- 🟡 **`auditoria.py` usa `logger.exception`**: el traceback puede incluir la
  `pregunta_resumida` y los IDs de `datos_tocados` (no montos). Se dejó así a
  propósito para poder diagnosticar un fallo de auditoría; queda a criterio de
  `auditor-seguridad` si debe endurecerse igual que D4/D5.
- 🟡 **`resolver_contacto` no resuelve `conversacion_id`/`mensaje_id`**: los recibe
  el runtime y hoy quedan `None`; el contrato lo permite (§4.1 paso 5).
- 🟡 **Solo 3 de 20 tools**: el resto del catálogo es O2.2–O2.7. `GET /estado`
  reporta `cargadas: 3`, no 19.

## 8. Rollback

Todo es aditivo y no toca la base:

1. Revertir `backend/app/api/router.py` (2 líneas) → el endpoint desaparece.
2. Revertir `backend/app/nucleo/permisos.py` (`PERMISOS_AGENTE` y la exclusión de
   `gerente`) → nadie tiene `agente:*`.
3. Revertir `backend/app/main.py` (import + handler) → `42501` vuelve a 500.
4. Borrar `backend/app/nucleo/agente/` y los tres `tests/test_agente_*.py`;
   quitar las 2 líneas del `Makefile`.
5. No hay migración que revertir en O2.1: `0021`/`0022`/`0023` son de O1 y siguen
   aplicadas solo en `tei_test`.

Sin pérdida de datos: no se escribió ninguna tabla nueva desde este entregable más
allá de las filas de auditoría de las pruebas (append-only, en `tei_test`).

## 9. Siguiente paso

Revisión independiente (`auditor-seguridad`) con objetivo, diff y criterios —sin
esta conclusión— y, en paralelo, decisión de `arquitectura` sobre el hueco §4.1 antes
de empezar O2.2 (`solicitudes` + buzón).

## 10. Revisión independiente y correcciones (2026-10-31)

`auditor-seguridad` revisó el cambio con objetivo, diff y criterios, sin esta
conclusión. Informe: `docs/seguridad/hallazgos-o2-1.md` (SEC-030…SEC-040).

**Veredicto del auditor:** sin bloqueante de seguridad para desarrollar O2.2, con
una condición antes de encender el módulo (SEC-030). No encontró bypass de
autenticación, lectura cruzada entre empresas, lectura de otro cliente/chofer por
la entrada, inyección SQL, tools no declaradas ni fuga de PII en respuestas.

**Limitación del propio auditor (declarada):** su permiso de `shell` fue rechazado,
así que **no pudo ejecutar las suites**; todos sus hallazgos son estáticos y los que
dependen de ejecución quedaron marcados 🔴. La verificación de ejecución es la de
este informe (§2), hecha por el orquestador.

### Hallazgos corregidos en este entregable

| ID | Sev. | Defecto | Corrección | Prueba de regresión |
|---|---|---|---|---|
| SEC-030 | media | El paquete abría `Session(get_engine_nucleo())` en 5 sitios, saltando `_asegurar_rol_nucleo` (la guarda que convierte “RLS inerte” en 503). Con un DSN a un rol `BYPASSRLS`, `/nucleo/*` daba 503 pero las tools seguían operando con RLS inerte | `sesion_nucleo()` nuevo en `core/database.py` (misma guarda que `get_session_nucleo`) y los 5 sitios migrados | `test_sesion_nucleo_aplica_la_guarda_antes_de_abrir_sesion` + `test_el_paquete_agente_no_abre_sesiones_directas` (falla si vuelve el patrón) |
| SEC-031 | baja | Un `42501` al leer las llaves del gate escapaba de `invocar` **sin dejar fila de auditoría**, justo el caso que §7.4 exige registrar | `try/except` alrededor de `autorizar`: `HTTPException` se propaga (503 de despliegue); cualquier otro error deniega con `NO_AUTORIZADO:gate_error:<codigo>` y `acceso=false` | `test_gate_que_falla_deniega_y_audita` — **verificada por mutación**: al neutralizar el `except`, la prueba falla con el `ProgrammingError` crudo |
| SEC-032 | baja | `herramienta` (nombre elegido por el modelo al pedir una tool inexistente) se persistía y devolvía sin cota | `_nombre_seguro()`: solo imprimibles, máx. 120; se usa en envelope, auditoría y logs | `test_sec_032_nombre_de_tool_se_acota_y_sanea` |
| SEC-034 | info | `manifest.motivo` de `/estado` podía incluir la ruta absoluta del despliegue | `_motivo_publicable()` sustituye la raíz del paquete por `<paquete-agente>` | `test_sec_034_motivo_no_expone_la_ruta_absoluta` |
| SEC-035 | info | V13/V14 solo miraban propiedades de **primer nivel**: un `cliente_id` anidado pasaba | `_propiedades_recursivas()` recorre `properties` e `items` | `test_sec_035_cliente_id_anidado_tambien_se_rechaza` |
| SEC-036 | info | `cargar_registry` solo capturaba `ErrorManifiesto`; otra falla daba 500 en `/estado` | `except Exception` en la carga → registry cerrado (`valido=false`), detalle al log | `test_sec_036_registry_no_lanza_si_la_carga_falla_de_otra_forma` |
| SEC-037 | info | `auditoria.py` usaba `logger.exception`, que puede arrastrar el mensaje de PostgreSQL con parámetros | Registra tipo + `sqlstate`, nunca el mensaje | revisión de código (mismo patrón que D4/D5) |

### Escalado, no corregido por iniciativa

- **SEC-033 (baja, PII/auditoría):** `pregunta_resumida` se persiste tal como la
  entrega el llamador; la redacción se delega a un runtime que todavía no existe.
  Es una decisión de contrato, no un defecto de implementación: la asigna
  `arquitectura`/runtime antes de O2.4, cuando el agente empiece a manejar montos.
- **SEC-040 (info, contrato):** con el flag de empresa ausente el registry reporta 3
  tools “cargadas” aunque la ejecución quede cerrada (§2.6.4 vs §6.5). Es una
  discrepancia entre dos secciones del contrato: la resuelve `arquitectura`.
- **SEC-038 y SEC-039 (info, preexistentes):** `manejador_integrity_error` registra
  `repr(exc)` (`main.py:262-266`) y el rol `tei_app` puede escribir identidad, ACL y
  flag que el gate consume. No son de este cambio; quedan registrados para `backend`
  y `datos`/`arquitectura` respectivamente. **No se tocaron.**

### Efecto en los números

La suite completa pasó de 297 a **304** pruebas verdes (4 unitarias + 1 de
integración nuevas, más las 3 de SEC-030/031), sin `skip` y sin `xfail`. `ruff` sigue
con solo los 3 `B008` ambiente del patrón FastAPI del repo.
