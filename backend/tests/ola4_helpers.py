"""Utilidades de las pruebas adversariales de la Ola 4 (2026-11-09).

No es un módulo de pruebas: no contiene `test_*`. Se separÓ de los archivos de
prueba para que las transiciones, el chat y la concurrencia compartan los mismos
constructores y no tres copias divergentes.

Dos modos de trabajo:

1. **Transacción revertida** (`sesion_aislada` + `http_con_sesion`): el cuerpo
   puede hacer `commit()` y solo libera un SAVEPOINT; al final se revierte. Es el
   patrón de `test_nucleo_transiciones.py` y no deja residuos.
2. **Datos confirmados** (`sesion_confirmada`): necesario para concurrencia real
   (dos conexiones distintas solo ven filas confirmadas). Las filas llevan una
   etiqueta única y no se borran: el núcleo es inmutable por triggers
   (`trg_reservas_no_delete`, auditoría append-only). `tei_test` se refresca con
   `make test-db`.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from contexto_helpers import contexto_de_prueba
from rut_helpers import rut_empresa
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from app.nucleo.deps import ContextoEmpresa
from app.nucleo.models import (
    Chofer,
    Cliente,
    Documento,
    Empresa,
    EstadoViaje,
    ModalidadTarifa,
    Rampla,
    RolEmpresa,
    Tarifa,
    TipoDocumento,
    TipoRampla,
    TipoRecurso,
    Tracto,
    TransicionViaje,
    Viaje,
    ViajeEvento,
)


# ---------------------------------------------------------------------------
# Conexiones
# ---------------------------------------------------------------------------
def url_test() -> str:
    from conftest import _base_url_test

    return _base_url_test()


def dsn_test() -> str:
    return url_test().replace("postgresql+psycopg://", "postgresql://")


@contextlib.contextmanager
def sesion_aislada():
    """Sesión sobre una transacción que siempre se revierte."""
    engine = create_engine(url_test(), future=True)
    try:
        with engine.connect() as conn_probe:
            try:
                conn_probe.execute(text("select 1 from nucleo.viajes limit 1"))
            except SQLAlchemyError as exc:  # pragma: no cover - entorno
                import pytest

                pytest.skip(f"Falta aplicar la migración 0004: {exc}")

        conn = engine.connect()
        transaccion = conn.begin()
        try:
            with Session(
                bind=conn, join_transaction_mode="create_savepoint"
            ) as session:
                yield session
        finally:
            transaccion.rollback()
            conn.close()
    finally:
        engine.dispose()


@contextlib.contextmanager
def sesion_confirmada():
    """Sesión que SÍ confirma: para datos que deben ver dos conexiones.

    Usa el rol `postgres` de `tei_test` (sin RLS) para simplificar el montaje;
    las garantías que se prueban aquí son constraints y locks de PostgreSQL, no
    políticas RLS (esas tienen sus propias suites).
    """
    engine = create_engine(url_test(), future=True)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


@contextlib.contextmanager
def http_con_sesion(session: Session, contexto: ContextoEmpresa):
    """`TestClient` sobre la sesión de la prueba (misma transacción revertida)."""
    from app.core.database import get_session_nucleo
    from app.main import app
    from app.nucleo.deps import get_contexto_empresa

    app.dependency_overrides[get_session_nucleo] = lambda: session
    app.dependency_overrides[get_contexto_empresa] = lambda: contexto_de_prueba(
        contexto
    )
    try:
        yield
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Constructores
# ---------------------------------------------------------------------------
def empresa(session: Session, etiqueta: str) -> Empresa:
    fila = Empresa(
        codigo=f"OLA4-{etiqueta}",
        razon_social=f"Empresa Ola4 {etiqueta}",
        rut=rut_empresa(),
        buffer_operacional_min=60,
    )
    session.add(fila)
    session.commit()
    session.refresh(fila)
    return fila


def cliente(session: Session, empresa: Empresa, etiqueta: str) -> Cliente:
    fila = Cliente(
        empresa_id=empresa.id,
        razon_social=f"Cliente Ola4 {etiqueta}",
        rut=f"CLI4-{etiqueta}",
    )
    session.add(fila)
    session.commit()
    session.refresh(fila)
    return fila


def recursos_documentados(
    session: Session, empresa: Empresa, cli: Cliente, etiqueta: str
) -> tuple[Tracto, Rampla, Chofer, Tarifa]:
    """Flota con documentos vigentes y tarifa (requisito de 'asignado')."""
    tracto = Tracto(
        empresa_id=empresa.id,
        patente=f"T{etiqueta[:5].upper()}",
        peso_bruto_kg=Decimal(39000),
        tara_kg=Decimal(9000),
        capacidad_carga_kg=Decimal(30000),
        licencias_permitidas=["A5"],
    )
    rampla = Rampla(
        empresa_id=empresa.id,
        patente=f"R{etiqueta[:5].upper()}",
        tipo=TipoRampla.plana,
        capacidad_carga_kg=Decimal(30000),
        volumen_m3=Decimal(80),
    )
    chofer = Chofer(
        empresa_id=empresa.id,
        rut=f"CHO4-{etiqueta}",
        nombre=f"Chofer Ola4 {etiqueta}",
        numero_licencia=f"LIC4-{etiqueta}",
        licencia_clase="A5",
    )
    session.add_all([tracto, rampla, chofer])
    session.commit()
    for recurso in (tracto, rampla, chofer):
        session.refresh(recurso)

    vence = date.today() + timedelta(days=400)
    session.add_all(
        [
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.tracto, tracto_id=tracto.id, tipo=TipoDocumento.revision_tecnica, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.tracto, tracto_id=tracto.id, tipo=TipoDocumento.permiso_circulacion, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.tracto, tracto_id=tracto.id, tipo=TipoDocumento.seguro_obligatorio, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.tracto, tracto_id=tracto.id, tipo=TipoDocumento.soap, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.rampla, rampla_id=rampla.id, tipo=TipoDocumento.revision_tecnica, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.rampla, rampla_id=rampla.id, tipo=TipoDocumento.permiso_circulacion, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.rampla, rampla_id=rampla.id, tipo=TipoDocumento.seguro_carga, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.chofer, chofer_id=chofer.id, tipo=TipoDocumento.licencia_conducir, vence_en=vence),
            Documento(empresa_id=empresa.id, recurso_tipo=TipoRecurso.chofer, chofer_id=chofer.id, tipo=TipoDocumento.examen_medico, vence_en=vence),
        ]
    )
    tarifa = Tarifa(
        empresa_id=empresa.id,
        cliente_id=cli.id,
        codigo=f"TAR4-{etiqueta}",
        nombre="Santiago - Concepción",
        modalidad=ModalidadTarifa.viaje,
        vigencia_desde=date.today(),
        vigencia_hasta=date.today() + timedelta(days=400),
        precio_unitario=Decimal(100000),
    )
    session.add(tarifa)
    session.commit()
    session.refresh(tarifa)
    return tracto, rampla, chofer, tarifa


def viaje(
    session: Session,
    empresa: Empresa,
    cli: Cliente,
    estado: EstadoViaje,
    *,
    recursos: tuple[Tracto, Rampla, Chofer, Tarifa] | None = None,
    dias_desde_hoy: int = 30,
    inicio: datetime | None = None,
) -> Viaje:
    inicio = inicio or (
        datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        + timedelta(days=dias_desde_hoy)
    )
    fila = Viaje(
        empresa_id=empresa.id,
        cliente_id=cli.id,
        estado=estado,
        inicio_planificado=inicio,
        fin_planificado=inicio + timedelta(hours=4),
        buffer_minutos=60,
        peso_bruto_kg=Decimal(25000),
        origen_nombre="Santiago",
        destino_nombre="Concepción",
        valor_flete_neto=Decimal(100000),
        tarifa_id=recursos[3].id if recursos else None,
        tracto_id=recursos[0].id if recursos else None,
        rampla_id=recursos[1].id if recursos else None,
        chofer_id=recursos[2].id if recursos else None,
    )
    session.add(fila)
    session.commit()
    session.refresh(fila)
    return fila


def contexto(
    empresa: Empresa, rol: RolEmpresa = RolEmpresa.admin
) -> ContextoEmpresa:
    return ContextoEmpresa(
        auth_id=str(uuid4()), empresa=empresa, rol=rol
    )


def eventos(session: Session, viaje_id: UUID, tipo: str) -> list[ViajeEvento]:
    return list(
        session.exec(
            select(ViajeEvento).where(
                ViajeEvento.viaje_id == viaje_id,
                ViajeEvento.tipo == tipo,
            )
        ).all()
    )


def destinos_en_matriz(session: Session, origen: EstadoViaje) -> list[str]:
    return sorted(
        fila.estado_destino.value
        for fila in session.exec(
            select(TransicionViaje).where(
                TransicionViaje.estado_origen == origen
            )
        ).all()
    )
