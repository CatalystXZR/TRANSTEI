# Contrato — `GET /api/v1/auth/me` (F2 Ola E1, 2026-11-01)

Autoridad: código en `backend/app/api/routes/auth.py`, `backend/app/api/deps.py`
y `backend/app/schemas/__init__.py` (verificado en esta sesión). Este documento
describe el contrato **después** del retiro de `public.usuarios`; no es fuente de
verdad por sí mismo.

## Método y ruta

`GET /api/v1/auth/me`

- Sin parámetros, sin body, sin `X-Empresa-ID`.
- No exige `X-Request-ID` (si llega, se propaga al GUC de auditoría).
- Idempotente y de solo lectura: no hay clave de idempotencia.

## Autenticación

`Authorization: Bearer <JWT de Supabase Auth>`.

- El JWT se valida contra JWKS (`RS256`/`ES256`, audiencia `authenticated`) en
  `backend/app/core/security.py:20-67`.
- Sin token o token inválido/expirado → **401**.
- `sub` ausente o que no sea UUID → **401** `Token inválido`.
- La identidad **no** se busca en `public.usuarios` (tabla retirada en 0028).

## Request

Sin cuerpo.

## Response `200`

`application/json`, validado por `UsuarioOut`:

```json
{
  "id": "0f1d…-uuid-del-sub",
  "nombre": "Admin TEI",
  "email": "admin@tei.local",
  "rol": "admin"
}
```

| Campo | Tipo | Origen |
|---|---|---|
| `id` | `string` (UUID) | claim `sub` del JWT (`auth_id` de Supabase Auth) |
| `nombre` | `string` | `user_metadata.nombre`; si falta, `email`; si tampoco, `sub` |
| `email` | `string \| null` | claim `email` |
| `rol` | `"admin" \| "operacion" \| "contabilidad"` | membresía activa en `nucleo.usuarios_empresa` (empresa activa), mapeada al menú |

### Mapeo de rol (núcleo → menú)

| `nucleo.rol_empresa` | `rol` de menú |
|---|---|
| `admin`, `gerente` | `admin` |
| `despacho`, `taller`, `conductor` | `operacion` |
| `contador`, `tesoreria`, `auditor` | `contabilidad` |

Si el usuario tiene membresías en varias empresas con roles distintos, gana el
menú de mayor alcance con orden determinista `admin > operacion > contabilidad`
(`backend/app/api/deps.py:50-77`). Es solo navegación: la autorización real se
resuelve por empresa en cada request del núcleo.

**Cambio de contrato:** se elimina `es_legacy`. El frontend ya no lo consume
(`frontend/src/types/index.ts` define exactamente `{id, nombre, email, rol}`) y
Pydantic filtra cualquier campo extra.

## Errores

| HTTP | `detail` | Cuándo |
|---|---|---|
| 401 | `Se requiere autenticación` | sin `Authorization: Bearer` |
| 401 | `Token inválido` | firma/audiencia inválidas, `sub` ausente o no UUID |
| 401 | `Sesión expirada, vuelva a iniciar sesión` | JWT expirado |
| 403 | `El usuario no tiene una membresía activa.` | JWT válido sin membresía activa en una empresa activa |
| 503 | (mensaje de configuración) | engine del núcleo sin DSN y sin `DATABASE_URL` |

No hay códigos de dominio adicionales: `/auth/me` no crea estado ni toca dinero.

## Autorización y tenant

- El tenant **no** se toma del body ni de un header: la consulta de membresías se
  resuelve en el servidor por `auth_id` (RLS de `nucleo.usuarios_empresa`,
  política `usuarios_empresa_lectura` de `0020_rls_multiempresa.sql`).
- No requiere `X-Empresa-ID`: la política RLS resuelve por `nucleo.auth_id`, que
  se fija antes de la primera consulta (`app/api/deps.py:79-90`).
- Deny-by-default: sin membresía utilizable no hay perfil (403).

## Compatibilidad

- Consumidor único verificado: `frontend/src/context/auth-context.tsx:61`
  (`fetch /auth/me`) y `frontend/src/types/index.ts:3-12`.
- El frontend ya se actualizó (fuera del alcance de esta ola): no usa `es_legacy`
  y el menú usa `rol`.
- `id` cambia de valor (antes `public.usuarios.id`, ahora `sub` del JWT). Ningún
  consumidor del repo lo compara con otra tabla; el shell solo lo guarda como
  parte del perfil.
