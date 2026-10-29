"""Pruebas P0-12: matriz de permisos, segregación y auditoría visible."""

from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine

from app.core.config import settings
from app.nucleo.deps import ContextoEmpresa, RolEmpresa
from app.nucleo.errores import AccesoDenegado
from app.nucleo.models import Empresa
from app.nucleo.permisos import ROLES_PERMISOS, permisos_de, requiere_permiso, tiene_permiso
from app.nucleo.schemas import ClienteCreateNucleo
from app.nucleo.servicio_auditoria import ServicioAuditoria
from app.nucleo.servicio_gastos import ServicioGastos
from app.nucleo.servicio_maestros import ServicioMaestros


def _url() -> str:
    url = os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL
    if not url:
        pytest.skip("Sin NUCLEO_TEST_DATABASE_URL; se omite integración de auditoría")
    return url


def test_matriz_de_permisos_y_segregacion():
    assert len(RolEmpresa) == 8
    assert set(ROLES_PERMISOS) == set(RolEmpresa)
    assert tiene_permiso(RolEmpresa.admin, "usuarios:administrar")
    assert not tiene_permiso(RolEmpresa.gerente, "usuarios:administrar")
    assert tiene_permiso(RolEmpresa.despacho, "agenda:escribir")
    assert not tiene_permiso(RolEmpresa.despacho, "gastos:aprobar")
    assert not tiene_permiso(RolEmpresa.despacho, "facturacion:emitir")
    assert tiene_permiso(RolEmpresa.contador, "facturacion:emitir")
    assert tiene_permiso(RolEmpresa.tesoreria, "cobranza:registrar")
    assert not tiene_permiso(RolEmpresa.tesoreria, "facturacion:emitir")
    assert tiene_permiso(RolEmpresa.auditor, "auditoria:leer")
    assert not tiene_permiso(RolEmpresa.auditor, "maestros:escribir")
    assert tiene_permiso(RolEmpresa.conductor, "pod:escribir")
    assert not tiene_permiso(RolEmpresa.conductor, "comercial:leer")

    contexto = ContextoEmpresa(
        auth_id=str(uuid4()),
        empresa=SimpleNamespace(id=uuid4()),  # type: ignore[arg-type]
        rol=RolEmpresa.despacho,
    )
    checker = requiere_permiso("gastos:aprobar")
    with pytest.raises(AccesoDenegado):
        checker(contexto)  # type: ignore[arg-type]

    contexto_contador = ContextoEmpresa(
        auth_id=str(uuid4()),
        empresa=SimpleNamespace(id=uuid4()),  # type: ignore[arg-type]
        rol=RolEmpresa.contador,
    )
    gasto = SimpleNamespace(created_by=contexto_contador.auth_id)
    servicio = ServicioGastos(
        session=SimpleNamespace(),  # type: ignore[arg-type]
        contexto=contexto_contador,
    )
    with pytest.raises(AccesoDenegado, match="segregación"):
        servicio._validar_aprobador(gasto)  # noqa: SLF001


def test_auditoria_visible_y_filtros():
    engine = create_engine(_url(), future=True)
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("select 1 from nucleo.auditoria limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover
                pytest.skip(f"Falta aplicar la migración 0004: {exc}")

        sufijo = uuid4().hex[:8]
        with Session(engine) as session:
            empresa = Empresa(
                codigo=f"AUD-{sufijo}",
                razon_social=f"Empresa Auditoría {sufijo}",
                rut=f"AUD-{sufijo}",
            )
            session.add(empresa)
            session.commit()
            session.refresh(empresa)

            admin = ContextoEmpresa(
                auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.admin
            )
            auditor = ContextoEmpresa(
                auth_id=str(uuid4()), empresa=empresa, rol=RolEmpresa.auditor
            )
            cliente = ServicioMaestros(session, admin).crear_cliente(
                ClienteCreateNucleo(
                    razon_social=f"Cliente Auditoría {sufijo}",
                    rut=f"CAU-{sufijo}",
                )
            )
            assert cliente.id is not None

            servicio = ServicioAuditoria(session, auditor)
            pagina = servicio.listar(tabla="nucleo.clientes", limit=10)
            assert pagina.total >= 1
            assert all(item.tabla == "nucleo.clientes" for item in pagina.items)
            assert any(item.operacion == "INSERT" for item in pagina.items)

            filtrada = servicio.listar(
                tabla="nucleo.clientes",
                registro_id=cliente.id,
                operacion="INSERT",
            )
            assert filtrada.total >= 1
            assert filtrada.items[0].registro_id == cliente.id
            assert filtrada.items[0].datos_despues is not None

            pagina_1 = servicio.listar(tabla="nucleo.clientes", limit=1, offset=0)
            assert pagina_1.limit == 1
            assert pagina_1.hay_mas == (pagina_1.total > 1)

            tablas = servicio.tablas()
            assert any(t.tabla == "nucleo.clientes" for t in tablas)
    finally:
        engine.dispose()
