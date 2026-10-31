"""Contexto de BD para pruebas que sustituyen `get_contexto_empresa`.

Varias pruebas reemplazan la dependencia `get_contexto_empresa` por un
`ContextoEmpresa` ya construido para aislar el objeto bajo prueba (validación de
archivos, POD, límites de cuerpo). Desde ADR-0005 el módulo núcleo corre con el
engine `tei_app` (sin `BYPASSRLS`), así que saltarse la dependencia real también
salta el `set_config` del request: sin `app.empresa_id` las políticas RLS
devuelven 0 filas y el endpoint responde 404 (fail-closed), que **no** es lo que
la prueba quiere medir.

`contexto_de_prueba()` fija los GUCs del contexto simulado (el `ContextoVar` del
request, que el middleware reinicia en cada petición) y devuelve el contexto, de
modo que la prueba sigue midiendo su regla y no el aislamiento.

Uso:

    app.dependency_overrides[get_contexto_empresa] = lambda: contexto_de_prueba(contexto)

No reintroduce autorización: la membresía ya la decidió el fixture; solo alinea
el contexto de base con el contexto simulado.
"""

from __future__ import annotations

from app.core.contexto import fijar_auth_id, fijar_empresa
from app.nucleo.deps import ContextoEmpresa


def contexto_de_prueba(contexto: ContextoEmpresa) -> ContextoEmpresa:
    fijar_auth_id(contexto.auth_id)
    fijar_empresa(contexto.empresa.id)
    return contexto
