# F0 · WP6 — Línea base de seguridad (Due Diligence)

> Depositado por el orquestador (2026-10-29): el agente `auditor-seguridad` no tenía permiso `shell`/`edit` en su sesión; el contenido es íntegro de su respuesta. El Anexo A (herramientas ejecutadas) lo agregó el orquestador con permiso shell.

- **Rol:** `auditor-seguridad` (revisión independiente, solo lectura)
- **Fecha:** 2026-10-29
- **Alcance:** SAST, secretos, dependencias, configuración, auth/autorización, storage/POD, anon key, claves hardcodeadas — `backend/app/**`, `frontend/src/**`, `supabase/migrations/**`, `Makefile`
- **Método:** lectura estática con cita `archivo:línea` + verificación viva HTTP GET contra `127.0.0.1:8000` (solo lectura, sin tokens, sin escritura)
- **Limitación estructural 🔴:** permisos `shell` y `edit` denegados en la sesión del subagente. Por eso **bandit, semgrep, gitleaks, pip-audit y npm audit NO se ejecutaron por el subagente** (ver Anexo A: los ejecutó el orquestador). Ningún hallazgo de código fue reproducido en ejecución por el auditor; lo no observable se marca 🟡/🔴.
- **Regla de secretos:** este informe no reproduce ningún valor; solo ubicaciones.

## Resumen ejecutivo

El perímetro de autenticación está bien construido y sí se impone en cada router: las 12 rutas legacy declaran `get_current_user`/`require_roles` y los 13 módulos del núcleo declaran `requiere_permiso`/`get_contexto_empresa` con `X-Empresa-ID` obligatorio y membresía activa. Verificado en vivo: `GET /api/v1/viajes` sin token → **401**. El aislamiento multiempresa del núcleo funciona **solo en capa de servicio** (filtros `empresa_id` consistentes en 100+ consultas), sin respaldo en base: 47 tablas con RLS habilitado y **1 sola política en todo el repo**, y el backend no usa `SET ROLE`. Los defectos principales son de higiene de entorno y defensa en profundidad: `DEBUG=True` por defecto con eco de SQL, fail-open del congelamiento legacy, uploads sin validación de MIME real. **No encontró secretos hardcodeados en código de producto, ni rutas sin autenticación, ni IDOR evidente en los servicios muestreados.** Conteo: **0 críticas, 0 altas confirmadas, 4 medias, 6 bajas, 3 informativas**.

## Tabla de hallazgos

| ID | Severidad | Título | Evidencia (`archivo:línea`) | Impacto | Recomendación |
|---|---|---|---|---|---|
| F0-01 | Media | `DEBUG=True` por defecto + `echo=True` → toda consulta SQL queda en logs | `backend/app/core/config.py:11`; `backend/app/core/database.py:22` (`echo=settings.DEBUG`) | Sin `DEBUG=false` en el entorno, SQLAlchemy registra cada consulta con parámetros (RUT, montos, sueldos) en stdout/logs. RA-10 ampliado | `DEBUG: bool = False` en `config.py`; `echo` independiente |
| F0-02 | Media | Aislamiento multiempresa sin respaldo en base | `grep "enable row level security" → 47` (31 en `nucleo`: `0004:1867-1881`, `0005:94`, `0007:257-261`, `0009:141`, `0011:172-173`, `0012:34`, `0013:255-259`, `0014:21`); `grep "create policy" → 1` (`0001:284`, `public.usuarios`); `grep "set role" backend → 0`; `0004:1865` declara backend con service_role/postgres | Si una consulta olvida el filtro `empresa_id`, ninguna capa inferior bloquea lectura/escritura cruzada. Control real hoy: filtros de servicio consistentes (`servicio_maestros._get:103-107`, `servicio_pod.py:74`, `servicio_disponibilidad.py:788`). Es RA-03 (hueco de defensa en profundidad, no bypass demostrado) | Políticas RLS con rol de app sujeto a RLS o FKs compuestas; mientras, adversarial por endpoint contra datos de otra empresa (`datos` + `qa`) |
| F0-03 | Baja | Legacy (`public`) sin noción de empresa | `grep empresa backend/app/models/__init__.py → 0`; `0001_esquema_base.sql` sin `empresa_id`; rutas legacy sin filtro | Sin exposición activa (piloto monoempresa). Si se multiarrienda con el mismo backend, todos los datos legacy se comparten | ADR de tenancy antes de sumar un segundo tenant; no ofrecer legacy a otro tenant mientras tanto |
| F0-04 | Media | `legacy_congelado()` falla en abierto | `backend/app/nucleo/servicio_cutover.py:38-39` (`except Exception: congelado = False`); `backend/app/main.py:50` | Si la consulta del flag falla, las escrituras legacy se reanudan en silencio durante el cutover. RA-04 confirmado | Fallar cerrado (devolver `True` o error) ante fallo de consulta |
| F0-05 | Media | Uploads sin validación de MIME real y con carga completa en memoria | `backend/app/nucleo/storage.py:21-31`, `servicio_maestros.py:417-425` (solo extensión + 10 MB); content-type del cliente (`api_maestros.py:243`, `storage.py:55`); `await archivo.read()` previo a validar (`api_pod.py:60-68`, `api_maestros.py:231`) | Archivo con contenido distinto a su extensión servido con content-type del cliente; archivo gigante agota memoria del worker. Requiere cuenta con permiso de escritura. RA-11 cerrado parcialmente (tamaño/extensión sí en servidor; path con UUID en servidor, `storage.py:42-44`) | Magic bytes + content-type fijado en servidor + límite de body en capa HTTP |
| F0-06 | Baja | Anon key en el bundle del frontend | `frontend/src/lib/supabase/client.ts:6-7` (NEXT_PUBLIC_*, inlined por Next); supabase-js solo para Auth; `grep "\.from(" frontend/src → solo Array.from`; datos vía API propia | Diseño normal de Supabase. Residual: políticas de Storage del bucket `respaldos` (🔴) y endpoints de Auth. RA-12 cerrado parcialmente | Verificar políticas del bucket `respaldos` (anon no debe leer sin URL firmada) |
| F0-07 | Baja | JWT sin verificación de `issuer` | `backend/app/core/security.py:25-31` (firma por JWKS propio, RS256/ES256, aud, exp; sin `issuer=`) | Acotado: la clave viene del JWKS de este proyecto. Higiene de hardening | `issuer=settings.SUPABASE_URL` |
| F0-08 | Baja | Sin rate limiting en la API | `grep -i "rate.?limit\|slowapi\|throttle" backend → 0` | Abuso acotado a cuentas válidas; login va contra Supabase Auth | Rate limit en middleware o proxy antes de exponer a internet |
| F0-09 | Baja | Sin cabeceras de seguridad explícitas en Next | `frontend/next.config.ts` vacío; defaults de Next 16 no verificables 🔴 | CSP/HSTS/X-Frame-Options ausentes | `headers()` en `next.config.ts` + verificar runtime |
| F0-10 | Baja | CSV sin protección de fórmulas | `backend/app/api/routes/export.py:29-46` (QUOTE_MINIMAL, sin prefijo por celda) | Texto de catálogo que empiece con `=` ejecuta fórmula en Excel al abrir el CSV | Prefijar `'`/`\t` en celdas con `= + - @`, o validar en entrada |
| F0-11 | Baja | `/docs` y `/openapi.json` expuestos | `backend/app/main.py:12` (defaults de FastAPI). **Vivo:** `GET /openapi.json → 200`, `/health → 200` | Mapa completo de la API (rutas de dinero y permisos) en producción | `docs_url=None` fuera de local |
| F0-12 | Informativa | Traducción de errores DB engañosa | `backend/app/main.py:64-74` (todo IntegrityError → 400 "duplicado"); `nucleo/errores.py:165-169` (23514 devuelve mensaje PG) | No filtra SQL interno; confunde diagnóstico (un CHECK se presenta como duplicado) | Mapear por sqlstate (23505→409, 23503/23514→422) |
| F0-13 | Informativa | CORS con credenciales y comodines | `backend/app/main.py:25-31`; orígenes en `config.py:20` | Riesgo mínimo con origen único explícito | Restringir métodos/cabeceras al desplegar |

**Ya registrados, confirmados y no duplicados aquí:** SEC-007 (anticipos sin idempotencia), SEC-010/RA-13 (`backend/tests/conftest.py:63-65` y `test_reglas_negocio.py:114-120` usan `DATABASE_URL` de la app), SEC-014 (`Makefile:26,62-69` — credenciales de seed, solo local), RA-02 (legacy sin `EXCLUDE`), RA-07 (auditoría no cubre legacy). Estado vigente: `docs/seguridad/hallazgos.md`, `docs/estado.md` §5.

## Controles verificados 🟢

| Control | Evidencia |
|---|---|
| JWT: JWKS cacheado, RS256/ES256, aud `authenticated`, exp; fail-closed 401 | `core/security.py:13-42` |
| 12/12 routers legacy con auth; escritura con `require_roles` | grep `Depends(` en `api/routes/` (91 matches); `viajes.py:33-34`; `liquidaciones.py:33-34` (admin+contabilidad) |
| **Vivo:** `GET /api/v1/viajes` sin token → **401** | webfetch a `127.0.0.1:8000` (2026-10-29) |
| Núcleo: `X-Empresa-ID` obligatorio + membresía activa + empresa activa; rol desde membresía, nunca del body | `nucleo/deps.py:43-82`; `permisos.py:150-172` |
| Permiso declarado por endpoint en los 13 módulos núcleo | grep `requiere_permiso(` en `backend/app/nucleo/api*.py` |
| Conductor: identidad por `auth_id`; `chofer_id` de query solo para roles de supervisión; viaje propio verificado | `servicio_conductor.py:90-115,167-178` |
| Filtros `empresa_id` consistentes (100+ matches) | `servicio_maestros.py:103-107,183`; `servicio_pod.py:74,87`; `servicio_disponibilidad.py:788`; `servicio_facturacion.py:208,304` |
| `extra="forbid"` en 39 schemas (sin mass assignment) | `nucleo/schemas.py` |
| 10 MB + whitelist de extensiones en servidor; firma ≤5 MB; path con UUID (sin path traversal) | `storage.py:17-31,42-44`; `servicio_pod.py:91-99` |
| POD: sin DELETE físico, versionado con 409, compensación de subidas | `servicio_pod.py:187-189,293-297,348-384` |
| Config legacy: PUT whitelist de 4 claves + admin | `routes/configuracion.py:30-32` |
| Sin claves hardcodeadas en producto | grep `(api_key\|apikey\|secret\|password\|passwd\|token)\s*=\s*["'][^"']+["']` en `backend/app` y `frontend/src` → **0 matches** |
| `.env`/`.env.local` gitignored (existen; no leídos) | `.gitignore:9-11` |
| Frontend sin PostgREST directo; supabase-js solo Auth | `lib/supabase/client.ts`; grep `.from(` |
| Paginación con tope en núcleo | `nucleo/api.py:108,132` (`le=200`) |

## NO DISPONIBLE para el subagente 🔴 (motivo: permisos `shell`/`edit` denegados)

| Herramienta | Objetivo | Estado |
|---|---|---|
| bandit / semgrep | SAST `backend/` y `frontend/src/` | Ejecutado por el orquestador → Anexo A |
| gitleaks | `gitleaks dir` / `git log -p` (historial, docs/, no-ignorados) | Ejecutado por el orquestador → Anexo A |
| pip-audit | `backend/requirements.txt` | Ejecutado por el orquestador → Anexo A |
| npm audit | `frontend/package.json` | Ejecutado por el orquestador → Anexo A |
| Rol efectivo de `DATABASE_URL` | `backend/.env` (prohibido leer) | Verificado por el orquestador: host `127.0.0.1:54322`, rol `postgres` (`rolbypassrls=t`) |
| Políticas del bucket `respaldos` | Consola Supabase / SQL | No disponible |
| Headers runtime de Next 16 | Frontend + curl | No disponible |
| Escritura del entregable | `docs/qa/informes/f0-wp6-seguridad-base.md` | Denegada (`edit`); depositado por el orquestador |

## Prioridad recomendada

1. **F0-01** (S, quick win): `DEBUG=False` + `echo` separado. `backend`.
2. **F0-02** (L): adversarial por endpoint con datos de otra empresa (`qa`) + decisión de arquitectura sobre RLS/rol (`datos`/`arquitectura`).
3. **F0-04** (S): fail-closed del congelamiento antes de cualquier ventana de cutover. `backend`.
4. **F0-05** (M): magic bytes + content-type en servidor + límite de body HTTP. `backend`.
5. **F0-07 / F0-10 / F0-11 / F0-09** (S c/u): higiene. `backend`/`frontend`.
6. **Re-ejecutar §NO DISPONIBLE** en cuanto exista permiso `shell` (hecho por el orquestador, ver Anexo A).

## Autoverificación (del subagente)

1. Evidencia reproducible: sí (`archivo:línea` o respuesta HTTP viva). 2. Confirmado vs potencial: todo por lectura (🟢), inferido/heredado marcado 🟡/🔴. 3. Control real descrito (F0-02: el filtro de servicio es el control actual; §Controles 🟢 documenta lo que sí protege). 4. Variantes: revisión por router de ambos esquemas y deps por rol; sin requests autenticadas (declarado). 5. Sin secretos: solo ubicaciones. 6. Calibración honesta (F0-06/08/09/13 = baja/informativa). 7. No verificado listado. 8. Remediaciones con agente y prioridad.

---

## Anexo A — Herramientas ejecutadas por el orquestador (2026-10-29)

Ejecutadas con shell del orquestador (permisos que el subagente no tuvo). Comandos y resultados reales:

### A.1 Bandit (SAST, backend/app)

```bash
# venv temporal desechable (el .venv del repo tiene el shebang de pip roto por
# renombre de carpeta: INIFORMATICA → Informatica; su python 3.13.16 sí funciona)
python3 -m venv /private/var/folders/.../opencode/f0-tools
f0-tools/bin/pip install -q bandit pip-audit
f0-tools/bin/bandit -r backend/app -q
```

**Resultado (2026-10-29 23:05Z):** 16.351 líneas escaneadas · **0 High · 0 Medium · 2 Low** ·
0 #nosec · 0 archivos saltados. Los 2 Low son B110 (`try/except: pass`) en
`backend/app/nucleo/servicio_maestros.py:503-506` y `backend/app/nucleo/storage.py:78-81`,
ambos con comentario que justifica dejar el archivo huérfano antes que ocultar el error
original (limpieza por job). **SAST limpio** 🟢.

### A.2 pip-audit (dependencias backend)

```bash
# ejecutado con venv temporal Python 3.13 (3.15 no tiene wheel de psycopg-binary==3.2.6)
f0-tools313/bin/pip-audit -r backend/requirements.txt -r backend/requirements-dev.txt
```

**Resultado:** **50 vulnerabilidades conocidas en 4 paquetes** 🟡 (pendiente de confirmar
severidades individuales y relevancia de explotación):

| Paquete | Versión | CVEs relevantes | Fix |
|---|---|---|---|
| `starlette` | 0.46.2 | PYSEC-2026-161, -1941, -1942, -2280, -2281, -248, -249 (múltiples) | ≥0.47.2 / 1.x |
| `pyjwt` | 2.10.1 | PYSEC-2025-183, PYSEC-2026-120, -175..-179, -4145, -4149, -4152 | ≥2.12.0/2.13.0/2.14.0 |
| `python-multipart` | 0.0.20 | PYSEC-2026-3036, -3037, -3039, -3040 | ≥0.0.30/0.0.31 |
| `pytest` (dev) | 8.3.5 | PYSEC-2026-1845 | 9.0.3 |

Nota: la actualización de `starlette` puede requerir subir FastAPI; es trabajo de fase
siguiente (F0 no toca dependencias). Contraste: el auditor no pudo ejecutarlo (sin shell);
el orquestador lo ejecutó.

### A.3 npm audit (dependencias frontend)

```bash
cd frontend && npm audit --omit=dev
```

**Resultado:** **12 vulnerabilidades (1 low, 3 moderate, 7 high, 1 critical)**:
- `undici 7.0.0–7.30.0` (transitiva): 8 advisories **high** (DoS, TLS validation bypass,
  cache poisoning, SRI bypass). Fix vía `npm audit fix`.
- **`next@16.3.7`: 1 critical (RCE/SSRF)** — corrección 2026-10-30: el `critical` era `next`, no `zod`.
- `zod <4.6.6`: **high** (GHSA-mrhx-c7xc-m3w5, agotamiento de memoria en colecciones restringidas).
- **Corregido en Ola 3 (2026-10-30):** 12 → **3** vulnerabilidades (0 critical/high/moderate); los 3 `low` restantes son de `shadcn` (CLI de generación, no runtime).

### A.4 Gitleaks (escaneo de secretos) — ejecutado por el orquestador

```bash
gitleaks dir --redact=100 backend            # 2 hits
gitleaks dir --redact=100 frontend/src       # 2 hits
gitleaks dir --redact=100 supabase           # 4 hits
gitleaks dir --redact=100 scripts docs       # 0 hits
gitleaks git --log-opts="--all" --redact=100 .  # historial (15 commits): 2 hits
```

**Clasificación (verificada por el orquestador, no a ojo):**

| Ubicación | RuleID | Clasificación | Evidencia |
|---|---|---|---|
| `backend/.env` (2) | jwt | **No expuesto**: archivo no versionado y en `.gitignore` | `git ls-files` = ∅; `git check-ignore` OK |
| `frontend/src/lib/offline-queue.ts:5-6` (2) | generic-api-key | **Falso positivo**: nombres de claves de localStorage (`tei_conductor_cola_v1`, `..._ultimo_viaje_v1`) | lectura del archivo, líneas 5–6 |
| `supabase/.temp/start-secrets/...docker.env` (4) | jwt, generic-api-key | **No expuesto**: secretos locales generados por `supabase start`, ignorados por git | `git check-ignore` OK |
| Historial git (2) | generic-api-key | **Falsos positivos**: mismos `offline-queue.ts:5-6` en commit `de0d6d3` | reporte JSON |

**Conclusión: 0 secretos reales expuestos en el repositorio ni en su historial.** Los 8 hits
del árbol de trabajo se reducen a 2 falsos positivos + 6 en archivos locales gitignored. El
escaneo completo del repo (1,91 GB, 579 hits) es ruido de `node_modules`/`.venv`/`.next` y
**no debe usarse como métrica**: la métrica válida es el escaneo de fuentes versionadas.

### A.5 Hallazgo de entorno adicional (afecta reproducibilidad)

El `.venv` del repo tiene el **shebang de `pip` roto**: apunta a
`/Users/pc/Desktop/INIFORMATICA/TRANSTEI/TRANSTEI/.venv/bin/python3.13` (ruta con typo
"INIFORMATICA"; el repo hoy vive en `.../Informatica/...`). `make unit`/`make test` usan
`.venv/bin/python -m pytest` (funciona, python 3.13.16 vía symlink a homebrew), pero
cualquier `pip install` directo falla. La línea base reproducible (WP-10) debe recrear el
venv en la ruta actual.
