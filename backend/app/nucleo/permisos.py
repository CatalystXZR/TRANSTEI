"""Matriz de permisos del núcleo y dependencias FastAPI.

Los permisos se declaran por módulo y acción. El backend es la autoridad: la UI
puede ocultar botones, pero cada endpoint vuelve a verificar el permiso.
"""

from __future__ import annotations

from fastapi import Depends

from app.nucleo.deps import ContextoEmpresa, get_contexto_empresa
from app.nucleo.errores import AccesoDenegado
from app.nucleo.models import RolEmpresa

# AB-02 (docs/estado.md §5): permisos del módulo agente. `admin` los hereda de
# `TODOS_LOS_PERMISOS`; `gerente` queda **excluido** hasta que el dueño ratifique
# AB-02. Deny-by-default: no se conceden por conveniencia.
PERMISOS_AGENTE = {"agente:buzon", "agente:aprobar", "agente:contactos"}

TODOS_LOS_PERMISOS = {
    "maestros:leer",
    "maestros:escribir",
    "operacion:leer",
    "operacion:escribir",
    "comercial:leer",
    "comercial:escribir",
    "comercial:aprobar",
    "agenda:leer",
    "agenda:escribir",
    "expediente:leer",
    "expediente:escribir",
    "pod:leer",
    "pod:escribir",
    "gastos:leer",
    "gastos:escribir",
    "gastos:aprobar",
    "rentabilidad:leer",
    "rentabilidad:configurar",
    "facturacion:leer",
    "facturacion:emitir",
    "cobranza:registrar",
    "alertas:leer",
    "auditoria:leer",
    "conductor:usar",
    "configuracion:leer",
    "configuracion:escribir",
    # Ola B del retiro legacy (0024–0026): mantenimiento, nómina e IVA.
    "mantenimiento:leer",
    "mantenimiento:escribir",
    "liquidaciones:leer",
    "liquidaciones:escribir",
    "iva:leer",
    "roles:leer",
    "usuarios:administrar",
} | PERMISOS_AGENTE

LECTURA_OPERATIVA = {
    "maestros:leer",
    "operacion:leer",
    "comercial:leer",
    "agenda:leer",
    "expediente:leer",
    "pod:leer",
    "gastos:leer",
    "rentabilidad:leer",
    "alertas:leer",
}

ROLES_PERMISOS: dict[RolEmpresa, set[str]] = {
    RolEmpresa.admin: set(TODOS_LOS_PERMISOS),
    RolEmpresa.gerente: set(TODOS_LOS_PERMISOS)
    - {"usuarios:administrar"}
    - PERMISOS_AGENTE,
    RolEmpresa.despacho: {
        "maestros:leer",
        "maestros:escribir",
        "operacion:leer",
        "operacion:escribir",
        "comercial:leer",
        "comercial:escribir",
        "agenda:leer",
        "agenda:escribir",
        "expediente:leer",
        "expediente:escribir",
        "pod:leer",
        "pod:escribir",
        "gastos:leer",
        "gastos:escribir",
        "rentabilidad:leer",
        "facturacion:leer",
        "alertas:leer",
        "conductor:usar",
        "auditoria:leer",
        # El legacy permitía a operación registrar mantenciones
        # (`routes/mantenimiento.py:18`): se conserva con permiso explícito.
        "mantenimiento:leer",
        "mantenimiento:escribir",
    },
    RolEmpresa.contador: {
        "maestros:leer",
        "operacion:leer",
        "comercial:leer",
        "agenda:leer",
        "expediente:leer",
        "pod:leer",
        "gastos:leer",
        "gastos:aprobar",
        "rentabilidad:leer",
        "facturacion:leer",
        "facturacion:emitir",
        "cobranza:registrar",
        "alertas:leer",
        "auditoria:leer",
        "configuracion:leer",
        # Nómina y su control tributario: mismo criterio que SEC-008 (solo
        # admin/gerente/contabilidad). No se concede a tesorería ni auditor.
        "liquidaciones:leer",
        "liquidaciones:escribir",
        "iva:leer",
        # El costo de mantención es un gasto de flota: contabilidad lo lee.
        "mantenimiento:leer",
    },
    RolEmpresa.tesoreria: {
        "maestros:leer",
        "operacion:leer",
        "comercial:leer",
        "expediente:leer",
        "gastos:leer",
        "gastos:aprobar",
        "rentabilidad:leer",
        "facturacion:leer",
        "cobranza:registrar",
        "alertas:leer",
        "auditoria:leer",
        # El resumen de IVA resume documentos que tesorería ya puede leer.
        "iva:leer",
    },
    RolEmpresa.taller: {
        "maestros:leer",
        "operacion:leer",
        "agenda:leer",
        "agenda:escribir",
        "expediente:leer",
        "expediente:escribir",
        "pod:leer",
        "gastos:leer",
        "alertas:leer",
        "mantenimiento:leer",
        "mantenimiento:escribir",
    },
    RolEmpresa.conductor: {
        "expediente:leer",
        "expediente:escribir",
        "pod:leer",
        "pod:escribir",
        "gastos:leer",
        "gastos:escribir",
        "conductor:usar",
    },
    RolEmpresa.auditor: {
        *LECTURA_OPERATIVA,
        "facturacion:leer",
        "auditoria:leer",
        "configuracion:leer",
        "roles:leer",
        # Auditoría de flota y de documentos tributarios: lectura, sin escritura.
        "mantenimiento:leer",
        "iva:leer",
    },
}


def permisos_de(rol: RolEmpresa) -> set[str]:
    return set(ROLES_PERMISOS.get(rol, set()))


def tiene_permiso(rol: RolEmpresa, permiso: str) -> bool:
    return permiso in permisos_de(rol)


def requiere_permiso(*permisos: str, requiere_todos: bool = True):
    """Dependencia FastAPI que exige uno o varios permisos."""
    requeridos = tuple(permisos)

    def checker(
        contexto: ContextoEmpresa = Depends(get_contexto_empresa),
    ) -> ContextoEmpresa:
        disponibles = permisos_de(contexto.rol)
        if requiere_todos:
            permitido = all(p in disponibles for p in requeridos)
        else:
            permitido = any(p in disponibles for p in requeridos)
        if not permitido:
            raise AccesoDenegado(
                "Su rol no permite realizar esta operación.",
                contexto={
                    "rol": contexto.rol.value,
                    "permisos_requeridos": list(requeridos),
                },
            )
        return contexto

    return checker
