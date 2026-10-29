"""Modelos SQLModel del núcleo operacional v2.

La fuente de verdad DDL es `supabase/migrations/0004_nucleo_operacional.sql`.
Estos modelos no crean tablas (`create_all` está prohibido en producción); solo
mapean el schema `nucleo` para consultas y escrituras transaccionales.

Convenciones:
- Dinero: Decimal, nunca float.
- Fechas de evento: timestamptz en UTC (`DateTime(timezone=True)`).
- Fechas de calendario: date.
- Toda tabla transaccional lleva `empresa_id` y FKs compuestas por empresa.
- Los enums son tipos nativos PostgreSQL; `create_type=False` evita que
  SQLAlchemy intente recrearlos.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Computed,
    DateTime,
    ForeignKeyConstraint,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSTZRANGE
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlmodel import Field, SQLModel

SCHEMA = "nucleo"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def pg_enum(enum_cls: type[Enum], name: str) -> PGEnum:
    return PGEnum(
        enum_cls,
        name=name,
        schema=SCHEMA,
        create_type=False,
        values_callable=lambda e: [member.value for member in e],
    )


def dinero(max_digits: int = 14, decimal_places: int = 2) -> Any:
    return Field(default=Decimal("0"), max_digits=max_digits, decimal_places=decimal_places)


def dinero_opcional(max_digits: int = 14, decimal_places: int = 2) -> Any:
    return Field(default=None, max_digits=max_digits, decimal_places=decimal_places)


def timestamptz(default_factory=utcnow) -> Any:
    return Field(default_factory=default_factory, sa_type=DateTime(timezone=True))


def timestamptz_opcional() -> Any:
    return Field(default=None, sa_type=DateTime(timezone=True))


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class EstadoEmpresa(str, Enum):
    activa = "activa"
    inactiva = "inactiva"


class RolEmpresa(str, Enum):
    admin = "admin"
    gerente = "gerente"
    despacho = "despacho"
    contador = "contador"
    tesoreria = "tesoreria"
    taller = "taller"
    conductor = "conductor"
    auditor = "auditor"


class EstadoRecurso(str, Enum):
    disponible = "disponible"
    asignado = "asignado"
    en_ruta = "en_ruta"
    en_taller = "en_taller"
    en_descanso = "en_descanso"
    bloqueado = "bloqueado"
    vacaciones = "vacaciones"
    baja = "baja"


class TipoRampla(str, Enum):
    plana = "plana"
    sider = "sider"
    refrigerada = "refrigerada"
    portacontenedor = "portacontenedor"
    cisterna = "cisterna"
    cama_baja = "cama_baja"
    granelera = "granelera"
    otra = "otra"


class TipoCarga(str, Enum):
    general = "general"
    granel = "granel"
    pallets = "pallets"
    contenedor = "contenedor"
    maquinaria = "maquinaria"
    refrigerada = "refrigerada"
    peligrosa = "peligrosa"
    sobredimensionada = "sobredimensionada"
    ganado = "ganado"
    otra = "otra"


class EstadoViaje(str, Enum):
    borrador = "borrador"
    cotizado = "cotizado"
    confirmado = "confirmado"
    asignado = "asignado"
    en_carga = "en_carga"
    cargado = "cargado"
    en_ruta = "en_ruta"
    en_descarga = "en_descarga"
    descargado = "descargado"
    pod_pendiente = "pod_pendiente"
    cerrado = "cerrado"
    facturado = "facturado"
    cobrado = "cobrado"
    anulado = "anulado"


class EstadoOC(str, Enum):
    abierta = "abierta"
    parcial = "parcial"
    consumida = "consumida"
    vencida = "vencida"
    anulada = "anulada"


class ModalidadTarifa(str, Enum):
    viaje = "viaje"
    km = "km"
    tonelada = "tonelada"
    tonelada_km = "tonelada_km"
    hora = "hora"
    contenedor = "contenedor"
    estadia = "estadia"
    mixta = "mixta"


class TipoDocumento(str, Enum):
    revision_tecnica = "revision_tecnica"
    permiso_circulacion = "permiso_circulacion"
    seguro_obligatorio = "seguro_obligatorio"
    soap = "soap"
    seguro_carga = "seguro_carga"
    tachografo = "tachografo"
    limitador_velocidad = "limitador_velocidad"
    certificado_gases = "certificado_gases"
    permiso_carga_peligrosa = "permiso_carga_peligrosa"
    licencia_conducir = "licencia_conducir"
    examen_medico = "examen_medico"
    curso_carga_peligrosa = "curso_carga_peligrosa"
    curso_manejo_defensivo = "curso_manejo_defensivo"
    contrato_laboral = "contrato_laboral"
    otro = "otro"


class TipoRecurso(str, Enum):
    tracto = "tracto"
    rampla = "rampla"
    chofer = "chofer"


class TipoReserva(str, Enum):
    viaje = "viaje"
    mantenimiento = "mantenimiento"
    descanso = "descanso"
    vacaciones = "vacaciones"
    bloqueo_manual = "bloqueo_manual"
    siniestro = "siniestro"
    otro = "otro"


# ---------------------------------------------------------------------------
# Organización
# ---------------------------------------------------------------------------
class Empresa(SQLModel, table=True):
    __tablename__ = "empresas"
    __table_args__ = (
        CheckConstraint("moneda ~ '^[A-Z]{3}$'", name="ck_empresa_moneda"),
        CheckConstraint("buffer_operacional_min between 0 and 1440", name="ck_empresa_buffer"),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    codigo: str = Field(max_length=40)
    razon_social: str = Field(max_length=250)
    nombre_fantasia: str | None = Field(default=None, max_length=250)
    rut: str = Field(max_length=20)
    giro: str | None = Field(default=None, max_length=250)
    direccion: str | None = Field(default=None, max_length=300)
    comuna: str | None = Field(default=None, max_length=120)
    ciudad: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    pais: str = Field(default="CL", max_length=2)
    zona_horaria: str = Field(default="America/Santiago", max_length=80)
    moneda: str = Field(default="CLP", max_length=3)
    buffer_operacional_min: int = Field(default=90, ge=0, le=1440)
    dias_margen_documentos: int = Field(default=0, ge=0, le=90)
    # R-02: la ventana de aviso es de 14 días (el vencimiento bloquea, el aviso no).
    dias_alerta_documentos: int = Field(default=14, ge=0, le=365)
    exigir_soap: bool = Field(default=True)
    exigir_seguro_carga: bool = Field(default=True)
    exigir_curso_carga_peligrosa: bool = Field(default=True)
    exigir_oc: bool = Field(default=False)
    estado: EstadoEmpresa = Field(default=EstadoEmpresa.activa, sa_type=pg_enum(EstadoEmpresa, "estado_empresa"))
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


class UsuarioEmpresa(SQLModel, table=True):
    __tablename__ = "usuarios_empresa"
    __table_args__ = (
        UniqueConstraint("empresa_id", "auth_id", name="uq_usuario_empresa_auth"),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    auth_id: UUID
    rol: RolEmpresa = Field(default=RolEmpresa.despacho, sa_type=pg_enum(RolEmpresa, "rol_empresa"))
    activo: bool = Field(default=True)
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


# ---------------------------------------------------------------------------
# Comercial
# ---------------------------------------------------------------------------
class Cliente(SQLModel, table=True):
    __tablename__ = "clientes"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_clientes_empresa_id_id"),
        UniqueConstraint("empresa_id", "rut", name="uq_clientes_empresa_rut"),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    razon_social: str = Field(max_length=250)
    rut: str = Field(max_length=20)
    giro: str | None = Field(default=None, max_length=250)
    direccion: str | None = Field(default=None, max_length=300)
    comuna: str | None = Field(default=None, max_length=120)
    ciudad: str | None = Field(default=None, max_length=120)
    contacto_nombre: str | None = Field(default=None, max_length=200)
    contacto_email: str | None = Field(default=None, max_length=200)
    contacto_telefono: str | None = Field(default=None, max_length=50)
    dias_pago: int = Field(default=30, ge=0, le=365)
    credito_autorizado: Decimal = dinero(16)
    exige_oc: bool = Field(default=False)
    activo: bool = Field(default=True)
    observaciones: str | None = None
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


class Tarifa(SQLModel, table=True):
    __tablename__ = "tarifas"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_tarifas_empresa_id_id"),
        UniqueConstraint("empresa_id", "cliente_id", "codigo", name="uq_tarifas_cliente_codigo"),
        ForeignKeyConstraint(
            ["empresa_id", "cliente_id"],
            [f"{SCHEMA}.clientes.empresa_id", f"{SCHEMA}.clientes.id"],
            name="fk_tarifa_cliente",
        ),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    cliente_id: UUID = Field(index=True)
    codigo: str = Field(max_length=60)
    nombre: str = Field(max_length=200)
    descripcion: str | None = None
    modalidad: ModalidadTarifa = Field(sa_type=pg_enum(ModalidadTarifa, "modalidad_tarifa"))
    origen: str | None = Field(default=None, max_length=200)
    destino: str | None = Field(default=None, max_length=200)
    tipo_rampla: TipoRampla | None = Field(default=None, sa_type=pg_enum(TipoRampla, "tipo_rampla"))
    tipo_carga: TipoCarga | None = Field(default=None, sa_type=pg_enum(TipoCarga, "tipo_carga"))
    vigencia_desde: date = Field(default_factory=date.today)
    vigencia_hasta: date | None = Field(default=None)
    moneda: str = Field(default="CLP", max_length=3)
    precio_unitario: Decimal = dinero(16, 4)
    minimo_cobro: Decimal = dinero()
    incluye_peajes: bool = Field(default=False)
    incluye_combustible: bool = Field(default=False)
    precio_diesel_base: Decimal | None = Field(default=None, max_digits=10, decimal_places=4)
    rendimiento_km_l: Decimal | None = Field(default=None, max_digits=6, decimal_places=3)
    participacion_combustible: Decimal | None = Field(
        default=None, max_digits=5, decimal_places=4
    )
    recargos: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    condiciones: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    activo: bool = Field(default=True)
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


class CentroCosto(SQLModel, table=True):
    __tablename__ = "centros_costo"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_centros_costo_empresa_id_id"),
        UniqueConstraint("empresa_id", "codigo", name="uq_centros_costo_empresa_codigo"),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    codigo: str = Field(max_length=60)
    nombre: str = Field(max_length=200)
    descripcion: str | None = None
    activo: bool = Field(default=True)
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


class OrdenCompra(SQLModel, table=True):
    __tablename__ = "ordenes_compra"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_oc_empresa_id_id"),
        UniqueConstraint("empresa_id", "cliente_id", "numero_oc", name="uq_oc_cliente_numero"),
        ForeignKeyConstraint(
            ["empresa_id", "cliente_id"],
            [f"{SCHEMA}.clientes.empresa_id", f"{SCHEMA}.clientes.id"],
            name="fk_oc_cliente",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "centro_costo_id"],
            [f"{SCHEMA}.centros_costo.empresa_id", f"{SCHEMA}.centros_costo.id"],
            name="fk_oc_centro_costo",
        ),
        CheckConstraint(
            "monto_consumido <= monto_autorizado + sobregiro_autorizado",
            name="ck_oc_consumo",
        ),
        CheckConstraint(
            "sobregiro_estado in ('sin_solicitud', 'pendiente', 'aprobado', 'rechazado')",
            name="ck_oc_sobregiro_estado",
        ),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    cliente_id: UUID = Field(index=True)
    numero_oc: str = Field(max_length=80)
    referencia_interna: str | None = Field(default=None, max_length=80)
    fecha_emision: date = Field(default_factory=date.today)
    vigencia_desde: date = Field(default_factory=date.today)
    vigencia_hasta: date
    monto_autorizado: Decimal = Field(max_digits=16, decimal_places=2)
    sobregiro_autorizado: Decimal = dinero(16)
    monto_consumido: Decimal = dinero(16)
    moneda: str = Field(default="CLP", max_length=3)
    centro_costo: str | None = Field(default=None, max_length=120)
    centro_costo_id: UUID | None = Field(default=None)
    proyecto: str | None = Field(default=None, max_length=120)
    faena: str | None = Field(default=None, max_length=120)
    condiciones_pago_dias: int | None = Field(default=None, ge=0, le=365)
    estado: EstadoOC = Field(default=EstadoOC.abierta, sa_type=pg_enum(EstadoOC, "estado_oc"))
    aprobado_por: str | None = Field(default=None, max_length=200)
    aprobado_en: datetime | None = timestamptz_opcional()
    sobregiro_estado: str = Field(default="sin_solicitud", max_length=20)
    sobregiro_solicitado: Decimal = dinero(16)
    sobregiro_motivo: str | None = None
    sobregiro_solicitado_por: str | None = Field(default=None, max_length=200)
    sobregiro_solicitado_en: datetime | None = timestamptz_opcional()
    sobregiro_aprobado_por: str | None = Field(default=None, max_length=200)
    sobregiro_aprobado_en: datetime | None = timestamptz_opcional()
    sobregiro_resolucion: str | None = None
    observaciones: str | None = None
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


class OrdenCompraLinea(SQLModel, table=True):
    __tablename__ = "ordenes_compra_lineas"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_ocl_empresa_id_id"),
        UniqueConstraint("orden_compra_id", "numero_linea", name="uq_ocl_numero_linea"),
        ForeignKeyConstraint(
            ["empresa_id", "orden_compra_id"],
            [f"{SCHEMA}.ordenes_compra.empresa_id", f"{SCHEMA}.ordenes_compra.id"],
            name="fk_ocl_oc",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "tarifa_id"],
            [f"{SCHEMA}.tarifas.empresa_id", f"{SCHEMA}.tarifas.id"],
            name="fk_ocl_tarifa",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "centro_costo_id"],
            [f"{SCHEMA}.centros_costo.empresa_id", f"{SCHEMA}.centros_costo.id"],
            name="fk_ocl_centro_costo",
        ),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    orden_compra_id: UUID = Field(index=True)
    numero_linea: int = Field(ge=1)
    descripcion: str
    origen: str | None = Field(default=None, max_length=200)
    destino: str | None = Field(default=None, max_length=200)
    tarifa_id: UUID | None = Field(default=None)
    centro_costo_id: UUID | None = Field(default=None)
    cantidad_estimada: Decimal = Field(default=Decimal("0"), max_digits=14, decimal_places=3)
    unidad: str = Field(default="viaje", max_length=40)
    precio_unitario: Decimal = dinero(16, 4)
    monto_linea: Decimal = dinero(16)
    activa: bool = Field(default=True)
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


# ---------------------------------------------------------------------------
# Flota y personas
# ---------------------------------------------------------------------------
class Tracto(SQLModel, table=True):
    __tablename__ = "tractos"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_tractos_empresa_id_id"),
        UniqueConstraint("empresa_id", "patente", name="uq_tractos_empresa_patente"),
        CheckConstraint("peso_bruto_kg > 0", name="ck_tracto_peso"),
        CheckConstraint("capacidad_carga_kg > 0", name="ck_tracto_capacidad"),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    patente: str = Field(max_length=20)
    marca: str | None = Field(default=None, max_length=80)
    modelo: str | None = Field(default=None, max_length=80)
    ano: int | None = Field(default=None, ge=1950, le=2100)
    vin: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, max_length=40)
    configuracion_ejes: str | None = Field(default=None, max_length=40)
    peso_bruto_kg: Decimal = Field(max_digits=12, decimal_places=3)
    tara_kg: Decimal = Field(max_digits=12, decimal_places=3)
    capacidad_carga_kg: Decimal = Field(max_digits=12, decimal_places=3)
    volumen_m3: Decimal | None = Field(default=None, max_digits=10, decimal_places=3)
    km_actual: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=1)
    horas_motor: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=1)
    licencias_permitidas: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")),
    )
    estado: EstadoRecurso = Field(
        default=EstadoRecurso.disponible, sa_type=pg_enum(EstadoRecurso, "estado_recurso")
    )
    activo: bool = Field(default=True)
    ubicacion_ciudad: str | None = Field(default=None, max_length=120)
    ubicacion_lat: Decimal | None = Field(default=None, max_digits=9, decimal_places=6)
    ubicacion_lon: Decimal | None = Field(default=None, max_digits=9, decimal_places=6)
    ubicacion_actualizada_en: datetime | None = timestamptz_opcional()
    observaciones: str | None = None
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


class Rampla(SQLModel, table=True):
    __tablename__ = "ramplas"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_ramplas_empresa_id_id"),
        UniqueConstraint("empresa_id", "patente", name="uq_ramplas_empresa_patente"),
        CheckConstraint("capacidad_carga_kg > 0", name="ck_rampla_capacidad"),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    patente: str = Field(max_length=20)
    tipo: TipoRampla = Field(default=TipoRampla.plana, sa_type=pg_enum(TipoRampla, "tipo_rampla"))
    marca: str | None = Field(default=None, max_length=80)
    modelo: str | None = Field(default=None, max_length=80)
    ano: int | None = Field(default=None, ge=1950, le=2100)
    vin: str | None = Field(default=None, max_length=40)
    capacidad_carga_kg: Decimal = Field(max_digits=12, decimal_places=3)
    volumen_m3: Decimal | None = Field(default=None, max_digits=10, decimal_places=3)
    largo_m: Decimal | None = Field(default=None, max_digits=8, decimal_places=3)
    ancho_m: Decimal | None = Field(default=None, max_digits=8, decimal_places=3)
    alto_m: Decimal | None = Field(default=None, max_digits=8, decimal_places=3)
    peso_tara_kg: Decimal | None = Field(default=None, max_digits=12, decimal_places=3)
    ejes: int | None = Field(default=None, ge=1, le=12)
    temperatura_min_c: Decimal | None = Field(default=None, max_digits=5, decimal_places=2)
    temperatura_max_c: Decimal | None = Field(default=None, max_digits=5, decimal_places=2)
    estado: EstadoRecurso = Field(
        default=EstadoRecurso.disponible, sa_type=pg_enum(EstadoRecurso, "estado_recurso")
    )
    activo: bool = Field(default=True)
    ubicacion_ciudad: str | None = Field(default=None, max_length=120)
    ubicacion_lat: Decimal | None = Field(default=None, max_digits=9, decimal_places=6)
    ubicacion_lon: Decimal | None = Field(default=None, max_digits=9, decimal_places=6)
    ubicacion_actualizada_en: datetime | None = timestamptz_opcional()
    observaciones: str | None = None
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


class Chofer(SQLModel, table=True):
    __tablename__ = "choferes"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_choferes_empresa_id_id"),
        UniqueConstraint("empresa_id", "rut", name="uq_choferes_empresa_rut"),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    rut: str = Field(max_length=20)
    nombre: str = Field(max_length=150)
    apellido_paterno: str | None = Field(default=None, max_length=120)
    apellido_materno: str | None = Field(default=None, max_length=120)
    auth_id: UUID | None = Field(default=None)
    fecha_nacimiento: date | None = Field(default=None)
    telefono: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=200)
    direccion: str | None = Field(default=None, max_length=300)
    comuna: str | None = Field(default=None, max_length=120)
    ciudad: str | None = Field(default=None, max_length=120)
    numero_licencia: str | None = Field(default=None, max_length=60)
    licencia_clase: str | None = Field(default=None, max_length=10)
    licencia_restricciones: str | None = Field(default=None, max_length=250)
    autorizado_carga_peligrosa: bool = Field(default=False)
    sueldo_base: Decimal = dinero()
    # R-01: comisión por defecto 10 % de la facturación del mes.
    porcentaje_comision: Decimal = Field(
        default=Decimal("0.10"), max_digits=5, decimal_places=4
    )
    contacto_emergencia_nombre: str | None = Field(default=None, max_length=200)
    contacto_emergencia_telefono: str | None = Field(default=None, max_length=50)
    estado: EstadoRecurso = Field(
        default=EstadoRecurso.disponible, sa_type=pg_enum(EstadoRecurso, "estado_recurso")
    )
    activo: bool = Field(default=True)
    observaciones: str | None = None
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


class Documento(SQLModel, table=True):
    __tablename__ = "documentos"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_documentos_empresa_id_id"),
        ForeignKeyConstraint(
            ["empresa_id", "tracto_id"],
            [f"{SCHEMA}.tractos.empresa_id", f"{SCHEMA}.tractos.id"],
            name="fk_doc_tracto",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "rampla_id"],
            [f"{SCHEMA}.ramplas.empresa_id", f"{SCHEMA}.ramplas.id"],
            name="fk_doc_rampla",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "chofer_id"],
            [f"{SCHEMA}.choferes.empresa_id", f"{SCHEMA}.choferes.id"],
            name="fk_doc_chofer",
        ),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    recurso_tipo: TipoRecurso = Field(sa_type=pg_enum(TipoRecurso, "tipo_recurso"))
    tracto_id: UUID | None = Field(default=None)
    rampla_id: UUID | None = Field(default=None)
    chofer_id: UUID | None = Field(default=None)
    tipo: TipoDocumento = Field(sa_type=pg_enum(TipoDocumento, "tipo_documento"))
    numero: str | None = Field(default=None, max_length=80)
    entidad_emisora: str | None = Field(default=None, max_length=200)
    emitido_en: date | None = Field(default=None)
    vence_en: date
    archivo_url: str | None = Field(default=None, max_length=1000)
    hash_sha256: str | None = Field(default=None, max_length=64)
    es_vigente: bool = Field(default=True)
    observaciones: str | None = None
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


# ---------------------------------------------------------------------------
# Folios
# ---------------------------------------------------------------------------
class FolioContador(SQLModel, table=True):
    __tablename__ = "folio_contador"
    __table_args__ = ({"schema": SCHEMA},)

    empresa_id: UUID = Field(primary_key=True, foreign_key=f"{SCHEMA}.empresas.id")
    tipo: str = Field(primary_key=True, max_length=20)
    periodo: str = Field(primary_key=True, max_length=10)
    ultimo: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Viaje
# ---------------------------------------------------------------------------
class Viaje(SQLModel, table=True):
    __tablename__ = "viajes"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_viajes_empresa_id_id"),
        UniqueConstraint("empresa_id", "numero_viaje", name="uq_viajes_numero"),
        ForeignKeyConstraint(
            ["empresa_id", "cliente_id"],
            [f"{SCHEMA}.clientes.empresa_id", f"{SCHEMA}.clientes.id"],
            name="fk_viaje_cliente",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "orden_compra_id"],
            [f"{SCHEMA}.ordenes_compra.empresa_id", f"{SCHEMA}.ordenes_compra.id"],
            name="fk_viaje_oc",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "tarifa_id"],
            [f"{SCHEMA}.tarifas.empresa_id", f"{SCHEMA}.tarifas.id"],
            name="fk_viaje_tarifa",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "tracto_id"],
            [f"{SCHEMA}.tractos.empresa_id", f"{SCHEMA}.tractos.id"],
            name="fk_viaje_tracto",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "rampla_id"],
            [f"{SCHEMA}.ramplas.empresa_id", f"{SCHEMA}.ramplas.id"],
            name="fk_viaje_rampla",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "chofer_id"],
            [f"{SCHEMA}.choferes.empresa_id", f"{SCHEMA}.choferes.id"],
            name="fk_viaje_chofer",
        ),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    numero_viaje: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=False),
    )
    cliente_id: UUID = Field(index=True)
    orden_compra_id: UUID | None = Field(default=None, index=True)
    tarifa_id: UUID | None = Field(default=None)
    tracto_id: UUID | None = Field(default=None, index=True)
    rampla_id: UUID | None = Field(default=None, index=True)
    chofer_id: UUID | None = Field(default=None, index=True)
    estado: EstadoViaje = Field(
        default=EstadoViaje.borrador, sa_type=pg_enum(EstadoViaje, "estado_viaje")
    )

    inicio_planificado: datetime = Field(sa_type=DateTime(timezone=True))
    fin_planificado: datetime = Field(sa_type=DateTime(timezone=True))
    fin_estimado: datetime | None = timestamptz_opcional()
    inicio_real: datetime | None = timestamptz_opcional()
    fin_real: datetime | None = timestamptz_opcional()
    buffer_minutos: int = Field(default=90, ge=0, le=1440)
    ventana: Any = Field(
        default=None,
        sa_column=Column(TSTZRANGE, nullable=False),
        exclude=True,
    )
    prioridad: int = Field(default=3, ge=1, le=5)

    tipo_carga: TipoCarga = Field(
        default=TipoCarga.general, sa_type=pg_enum(TipoCarga, "tipo_carga")
    )
    descripcion_carga: str | None = None
    codigo_carga_cliente: str | None = Field(default=None, max_length=80)
    peso_bruto_kg: Decimal | None = Field(default=None, max_digits=12, decimal_places=3)
    peso_neto_kg: Decimal | None = Field(default=None, max_digits=12, decimal_places=3)
    tara_kg: Decimal | None = Field(default=None, max_digits=12, decimal_places=3)
    volumen_m3: Decimal | None = Field(default=None, max_digits=10, decimal_places=3)
    bultos: int | None = Field(default=None, ge=0)
    largo_m: Decimal | None = Field(default=None, max_digits=8, decimal_places=3)
    ancho_m: Decimal | None = Field(default=None, max_digits=8, decimal_places=3)
    alto_m: Decimal | None = Field(default=None, max_digits=8, decimal_places=3)
    valor_declarado: Decimal | None = Field(default=None, max_digits=16, decimal_places=2)
    moneda_valor: str | None = Field(default="CLP", max_length=3)
    carga_peligrosa: bool = Field(default=False)
    numero_un: str | None = Field(default=None, max_length=20)
    clase_peligro: str | None = Field(default=None, max_length=20)
    msds_url: str | None = Field(default=None, max_length=1000)
    refrigerada: bool = Field(default=False)
    temperatura_min_c: Decimal | None = Field(default=None, max_digits=5, decimal_places=2)
    temperatura_max_c: Decimal | None = Field(default=None, max_digits=5, decimal_places=2)
    sobredimensionada: bool = Field(default=False)
    permiso_vialidad: str | None = Field(default=None, max_length=200)
    requiere_grua: bool = Field(default=False)
    requiere_montacargas: bool = Field(default=False)
    sellos: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )
    instrucciones_especiales: str | None = None

    origen_nombre: str = Field(max_length=200)
    origen_direccion: str | None = Field(default=None, max_length=300)
    origen_comuna: str | None = Field(default=None, max_length=120)
    origen_ciudad: str | None = Field(default=None, max_length=120)
    origen_region: str | None = Field(default=None, max_length=120)
    origen_lat: Decimal | None = Field(default=None, max_digits=9, decimal_places=6)
    origen_lon: Decimal | None = Field(default=None, max_digits=9, decimal_places=6)
    destino_nombre: str = Field(max_length=200)
    destino_direccion: str | None = Field(default=None, max_length=300)
    destino_comuna: str | None = Field(default=None, max_length=120)
    destino_ciudad: str | None = Field(default=None, max_length=120)
    destino_region: str | None = Field(default=None, max_length=120)
    destino_lat: Decimal | None = Field(default=None, max_digits=9, decimal_places=6)
    destino_lon: Decimal | None = Field(default=None, max_digits=9, decimal_places=6)
    distancia_km: Decimal | None = Field(default=None, max_digits=10, decimal_places=2)
    km_vacios: Decimal | None = Field(default=None, max_digits=10, decimal_places=2)
    tiempo_estimado_h: Decimal | None = Field(default=None, max_digits=8, decimal_places=2)

    ventana_carga_desde: datetime | None = timestamptz_opcional()
    ventana_carga_hasta: datetime | None = timestamptz_opcional()
    ventana_descarga_desde: datetime | None = timestamptz_opcional()
    ventana_descarga_hasta: datetime | None = timestamptz_opcional()
    contacto_origen_nombre: str | None = Field(default=None, max_length=200)
    contacto_origen_telefono: str | None = Field(default=None, max_length=50)
    contacto_destino_nombre: str | None = Field(default=None, max_length=200)
    contacto_destino_telefono: str | None = Field(default=None, max_length=50)

    valor_flete_neto: Decimal = dinero()
    monto_recargos: Decimal = dinero()
    monto_total_neto: Decimal | None = Field(
        default=None,
        sa_column=Column(
            Numeric(14, 2),
            Computed("valor_flete_neto + monto_recargos", persisted=True),
            nullable=False,
        ),
    )
    moneda: str = Field(default="CLP", max_length=3)
    condiciones_pago_dias: int | None = Field(default=None, ge=0, le=365)
    tarifa_snapshot: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    oc_numero_snapshot: str | None = Field(default=None, max_length=80)
    costo_variable_estimado: Decimal | None = Field(
        default=None, max_digits=14, decimal_places=2
    )
    costo_variable_real: Decimal | None = Field(
        default=None, max_digits=14, decimal_places=2
    )
    costo_total_real: Decimal | None = Field(
        default=None, max_digits=14, decimal_places=2
    )
    costo_actualizado_en: datetime | None = timestamptz_opcional()
    freight_score_estimado: Decimal | None = Field(
        default=None, max_digits=5, decimal_places=2
    )
    freight_score_detalle: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )

    motivo_anulacion: str | None = None
    motivo_reasignacion: str | None = None
    anulado_por: str | None = Field(default=None, max_length=200)
    anulado_en: datetime | None = timestamptz_opcional()
    observaciones: str | None = None
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


# ---------------------------------------------------------------------------
# Expediente del viaje (P0-05)
# ---------------------------------------------------------------------------
class ViajeParada(SQLModel, table=True):
    __tablename__ = "viaje_paradas"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_paradas_empresa_id_id"),
        UniqueConstraint("viaje_id", "orden", name="uq_paradas_viaje_orden"),
        ForeignKeyConstraint(
            ["empresa_id", "viaje_id"],
            [f"{SCHEMA}.viajes.empresa_id", f"{SCHEMA}.viajes.id"],
            name="fk_parada_viaje",
        ),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    viaje_id: UUID = Field(index=True)
    orden: int = Field(ge=1)
    tipo: str = Field(default="intermedia", max_length=20)
    nombre: str = Field(max_length=200)
    direccion: str | None = Field(default=None, max_length=300)
    comuna: str | None = Field(default=None, max_length=120)
    ciudad: str | None = Field(default=None, max_length=120)
    contacto_nombre: str | None = Field(default=None, max_length=200)
    contacto_telefono: str | None = Field(default=None, max_length=50)
    ventana_desde: datetime | None = timestamptz_opcional()
    ventana_hasta: datetime | None = timestamptz_opcional()
    estado: str = Field(default="pendiente", max_length=20)
    notas: str | None = None
    activo: bool = Field(default=True)
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


class ViajeChecklist(SQLModel, table=True):
    __tablename__ = "viaje_checklist"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_checklist_empresa_id_id"),
        ForeignKeyConstraint(
            ["empresa_id", "viaje_id"],
            [f"{SCHEMA}.viajes.empresa_id", f"{SCHEMA}.viajes.id"],
            name="fk_checklist_viaje",
        ),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    viaje_id: UUID = Field(index=True)
    orden: int = Field(default=1, ge=1)
    categoria: str = Field(default="general", max_length=60)
    item: str
    requerido: bool = Field(default=True)
    completado: bool = Field(default=False)
    completado_por: str | None = Field(default=None, max_length=200)
    completado_en: datetime | None = timestamptz_opcional()
    evidencia_url: str | None = Field(default=None, max_length=1000)
    notas: str | None = None
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


class ViajeEvento(SQLModel, table=True):
    __tablename__ = "viaje_eventos"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_eventos_empresa_id_id"),
        ForeignKeyConstraint(
            ["empresa_id", "viaje_id"],
            [f"{SCHEMA}.viajes.empresa_id", f"{SCHEMA}.viajes.id"],
            name="fk_evento_viaje",
        ),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    viaje_id: UUID = Field(index=True)
    tipo: str = Field(default="nota", max_length=60)
    descripcion: str
    ocurrido_en: datetime = timestamptz()
    payload: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    auth_id: str | None = Field(default=None, max_length=200)
    created_at: datetime = timestamptz()


class ViajeIncidente(SQLModel, table=True):
    __tablename__ = "viaje_incidentes"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_incidentes_empresa_id_id"),
        ForeignKeyConstraint(
            ["empresa_id", "viaje_id"],
            [f"{SCHEMA}.viajes.empresa_id", f"{SCHEMA}.viajes.id"],
            name="fk_incidente_viaje",
        ),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    viaje_id: UUID = Field(index=True)
    tipo: str = Field(max_length=80)
    severidad: str = Field(default="media", max_length=20)
    descripcion: str
    estado: str = Field(default="abierto", max_length=20)
    ocurrido_en: datetime = timestamptz()
    reportado_por: str | None = Field(default=None, max_length=200)
    resolucion: str | None = None
    resuelto_por: str | None = Field(default=None, max_length=200)
    resuelto_en: datetime | None = timestamptz_opcional()
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


class POD(SQLModel, table=True):
    __tablename__ = "pod"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_pod_empresa_id_id"),
        UniqueConstraint("viaje_id", name="uq_pod_viaje"),
        ForeignKeyConstraint(
            ["empresa_id", "viaje_id"],
            [f"{SCHEMA}.viajes.empresa_id", f"{SCHEMA}.viajes.id"],
            name="fk_pod_viaje",
        ),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    viaje_id: UUID = Field(index=True)
    receptor_nombre: str = Field(max_length=200)
    receptor_rut: str | None = Field(default=None, max_length=20)
    receptor_cargo: str | None = Field(default=None, max_length=120)
    fecha_hora: datetime = timestamptz()
    lat: Decimal | None = Field(default=None, max_digits=9, decimal_places=6)
    lon: Decimal | None = Field(default=None, max_digits=9, decimal_places=6)
    firma_url: str = Field(max_length=1000)
    firma_hash: str | None = Field(default=None, max_length=64)
    fotos: list[Any] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )
    danios: str | None = None
    observaciones: str | None = None
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


class ViajeDocumento(SQLModel, table=True):
    __tablename__ = "viaje_documentos"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_docs_viaje_empresa_id_id"),
        ForeignKeyConstraint(
            ["empresa_id", "viaje_id"],
            [f"{SCHEMA}.viajes.empresa_id", f"{SCHEMA}.viajes.id"],
            name="fk_doc_viaje",
        ),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    viaje_id: UUID = Field(index=True)
    tipo: str = Field(default="otro", max_length=60)
    nombre: str = Field(max_length=300)
    archivo_url: str = Field(max_length=1000)
    hash_sha256: str | None = Field(default=None, max_length=64)
    content_type: str | None = Field(default=None, max_length=120)
    tamano_bytes: int | None = Field(default=None, ge=0)
    observaciones: str | None = None
    activo: bool = Field(default=True)
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


# ---------------------------------------------------------------------------
# Gastos y combustible (P0-08)
# ---------------------------------------------------------------------------
class PrecioDiesel(SQLModel, table=True):
    __tablename__ = "precios_diesel"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_precios_diesel_empresa_id_id"),
        UniqueConstraint("empresa_id", "fecha", name="uq_precios_diesel_empresa_fecha"),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    fecha: date
    precio_litro: Decimal = Field(max_digits=10, decimal_places=4, ge=0)
    fuente: str | None = Field(default=None, max_length=120)
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)


class ViajeGasto(SQLModel, table=True):
    __tablename__ = "viaje_gastos"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_gastos_empresa_id_id"),
        ForeignKeyConstraint(
            ["empresa_id", "viaje_id"],
            [f"{SCHEMA}.viajes.empresa_id", f"{SCHEMA}.viajes.id"],
            name="fk_gasto_viaje",
        ),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    viaje_id: UUID = Field(index=True)
    tipo: str = Field(default="otro", max_length=40)
    proveedor: str | None = Field(default=None, max_length=200)
    numero_documento: str | None = Field(default=None, max_length=80)
    fecha: date = Field(default_factory=date.today)
    monto_total: Decimal = Field(max_digits=14, decimal_places=2)
    iva: Decimal = Field(default=Decimal("0"), max_digits=14, decimal_places=2)
    monto_neto: Decimal | None = Field(
        default=None,
        sa_column=Column(
            Numeric(14, 2),
            Computed("monto_total - iva", persisted=True),
            nullable=False,
        ),
    )
    moneda: str = Field(default="CLP", max_length=3)
    litros: Decimal | None = Field(default=None, max_digits=10, decimal_places=3)
    precio_litro: Decimal | None = Field(default=None, max_digits=10, decimal_places=4)
    km_odometro: Decimal | None = Field(default=None, max_digits=12, decimal_places=1)
    estacion: str | None = Field(default=None, max_length=200)
    tag: str | None = Field(default=None, max_length=120)
    comprobante_url: str | None = Field(default=None, max_length=1000)
    estado: str = Field(default="pendiente", max_length=20)
    motivo_rechazo: str | None = None
    aprobado_por: str | None = Field(default=None, max_length=200)
    aprobado_en: datetime | None = timestamptz_opcional()
    observaciones: str | None = None
    activo: bool = Field(default=True)
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


# ---------------------------------------------------------------------------
# Configuración de costos y rentabilidad (P0-09)
# ---------------------------------------------------------------------------
class ConfiguracionCostos(SQLModel, table=True):
    __tablename__ = "configuracion_costos"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_config_costos_empresa_id_id"),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, unique=True, foreign_key=f"{SCHEMA}.empresas.id")
    costo_fijo_mensual: Decimal = dinero(14)
    viajes_estimados_mes: int = Field(default=60, ge=1)
    margen_objetivo: Decimal = Field(default=Decimal("0.25"), max_digits=5, decimal_places=4)
    benchmark_margen_km: Decimal = Field(
        default=Decimal("1200"), max_digits=14, decimal_places=2
    )
    contribucion_minima: Decimal = Field(
        default=Decimal("100000"), max_digits=14, decimal_places=2
    )
    costo_variable_km_estandar: Decimal = Field(
        default=Decimal("900"), max_digits=14, decimal_places=2
    )
    rendimiento_km_l: Decimal = Field(default=Decimal("2.5"), max_digits=6, decimal_places=3)
    precio_diesel: Decimal = Field(default=Decimal("1000"), max_digits=10, decimal_places=4)
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


# ---------------------------------------------------------------------------
# Facturación y cobranza (P0-10)
# ---------------------------------------------------------------------------
class FacturaNucleo(SQLModel, table=True):
    __tablename__ = "facturas_nucleo"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_facturas_empresa_id_id"),
        UniqueConstraint("empresa_id", "numero_factura", name="uq_facturas_numero"),
        ForeignKeyConstraint(
            ["empresa_id", "cliente_id"],
            [f"{SCHEMA}.clientes.empresa_id", f"{SCHEMA}.clientes.id"],
            name="fk_factura_cliente",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "orden_compra_id"],
            [f"{SCHEMA}.ordenes_compra.empresa_id", f"{SCHEMA}.ordenes_compra.id"],
            name="fk_factura_oc",
        ),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    numero_factura: str = Field(max_length=80)
    cliente_id: UUID = Field(index=True)
    orden_compra_id: UUID | None = Field(default=None, index=True)
    fecha_emision: date = Field(default_factory=date.today)
    fecha_vencimiento: date
    moneda: str = Field(default="CLP", max_length=3)
    neto: Decimal = Field(max_digits=14, decimal_places=2)
    iva: Decimal = dinero(14)
    total: Decimal | None = Field(
        default=None,
        sa_column=Column(
            Numeric(14, 2),
            Computed("neto + iva", persisted=True),
            nullable=False,
        ),
    )
    estado: str = Field(default="emitida", max_length=20)
    observaciones: str | None = None
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


class FacturaViaje(SQLModel, table=True):
    __tablename__ = "factura_viajes"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_factura_viajes_empresa_id_id"),
        UniqueConstraint("empresa_id", "viaje_id", name="uq_factura_viaje_unico"),
        ForeignKeyConstraint(
            ["empresa_id", "factura_id"],
            [f"{SCHEMA}.facturas_nucleo.empresa_id", f"{SCHEMA}.facturas_nucleo.id"],
            name="fk_fv_factura",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "viaje_id"],
            [f"{SCHEMA}.viajes.empresa_id", f"{SCHEMA}.viajes.id"],
            name="fk_fv_viaje",
        ),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    factura_id: UUID = Field(index=True)
    viaje_id: UUID = Field(index=True)
    monto: Decimal = Field(max_digits=14, decimal_places=2)
    created_at: datetime = timestamptz()


class PagoNucleo(SQLModel, table=True):
    __tablename__ = "pagos_nucleo"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_pagos_empresa_id_id"),
        ForeignKeyConstraint(
            ["empresa_id", "factura_id"],
            [f"{SCHEMA}.facturas_nucleo.empresa_id", f"{SCHEMA}.facturas_nucleo.id"],
            name="fk_pago_factura",
        ),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    factura_id: UUID = Field(index=True)
    fecha: date = Field(default_factory=date.today)
    monto: Decimal = Field(max_digits=14, decimal_places=2)
    metodo: str = Field(default="transferencia", max_length=20)
    referencia: str | None = Field(default=None, max_length=200)
    observaciones: str | None = None
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


class NotaCreditoNucleo(SQLModel, table=True):
    __tablename__ = "notas_credito_nucleo"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_nc_empresa_id_id"),
        UniqueConstraint("empresa_id", "numero", name="uq_nc_numero"),
        ForeignKeyConstraint(
            ["empresa_id", "factura_id"],
            [f"{SCHEMA}.facturas_nucleo.empresa_id", f"{SCHEMA}.facturas_nucleo.id"],
            name="fk_nc_factura",
        ),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    factura_id: UUID = Field(index=True)
    numero: str = Field(max_length=80)
    fecha: date = Field(default_factory=date.today)
    monto: Decimal = Field(max_digits=14, decimal_places=2)
    motivo: str
    estado: str = Field(default="aplicada", max_length=20)
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)


class PromesaPagoNucleo(SQLModel, table=True):
    __tablename__ = "promesas_pago_nucleo"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_promesas_empresa_id_id"),
        ForeignKeyConstraint(
            ["empresa_id", "factura_id"],
            [f"{SCHEMA}.facturas_nucleo.empresa_id", f"{SCHEMA}.facturas_nucleo.id"],
            name="fk_promesa_factura",
        ),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    factura_id: UUID = Field(index=True)
    fecha_prometida: date
    monto: Decimal = Field(max_digits=14, decimal_places=2)
    estado: str = Field(default="pendiente", max_length=20)
    notas: str | None = None
    created_at: datetime = timestamptz()
    created_by: str = Field(default="sistema", max_length=200)


# ---------------------------------------------------------------------------
# Libro de reservas
# ---------------------------------------------------------------------------
class ReservaRecurso(SQLModel, table=True):
    __tablename__ = "reservas_recurso"
    __table_args__ = (
        UniqueConstraint("empresa_id", "id", name="uq_reservas_empresa_id_id"),
        ForeignKeyConstraint(
            ["empresa_id", "tracto_id"],
            [f"{SCHEMA}.tractos.empresa_id", f"{SCHEMA}.tractos.id"],
            name="fk_reserva_tracto",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "rampla_id"],
            [f"{SCHEMA}.ramplas.empresa_id", f"{SCHEMA}.ramplas.id"],
            name="fk_reserva_rampla",
        ),
        ForeignKeyConstraint(
            ["empresa_id", "chofer_id"],
            [f"{SCHEMA}.choferes.empresa_id", f"{SCHEMA}.choferes.id"],
            name="fk_reserva_chofer",
        ),
        ForeignKeyConstraint(["viaje_id"], [f"{SCHEMA}.viajes.id"], name="fk_reserva_viaje"),
        {"schema": SCHEMA},
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    empresa_id: UUID = Field(index=True, foreign_key=f"{SCHEMA}.empresas.id")
    recurso_tipo: TipoRecurso = Field(sa_type=pg_enum(TipoRecurso, "tipo_recurso"))
    tracto_id: UUID | None = Field(default=None)
    rampla_id: UUID | None = Field(default=None)
    chofer_id: UUID | None = Field(default=None)
    ventana: Any = Field(sa_column=Column(TSTZRANGE, nullable=False))
    tipo_reserva: TipoReserva = Field(
        default=TipoReserva.viaje, sa_type=pg_enum(TipoReserva, "tipo_reserva")
    )
    viaje_id: UUID | None = Field(default=None, index=True)
    motivo: str | None = None
    activa: bool = Field(default=True)
    cancelado_motivo: str | None = None
    cancelado_por: str | None = Field(default=None, max_length=200)
    cancelado_en: datetime | None = timestamptz_opcional()
    creado_por: str = Field(default="sistema", max_length=200)
    created_at: datetime = timestamptz()
    updated_at: datetime = timestamptz()
    updated_by: str | None = Field(default=None, max_length=200)
    version: int = Field(default=1, ge=1)


# ---------------------------------------------------------------------------
# Estados y auditoría
# ---------------------------------------------------------------------------
class TransicionViaje(SQLModel, table=True):
    __tablename__ = "transiciones_viaje"
    __table_args__ = ({"schema": SCHEMA},)

    estado_origen: EstadoViaje = Field(
        primary_key=True, sa_type=pg_enum(EstadoViaje, "estado_viaje")
    )
    estado_destino: EstadoViaje = Field(
        primary_key=True, sa_type=pg_enum(EstadoViaje, "estado_viaje")
    )
    requiere_motivo: bool = Field(default=False)


class Auditoria(SQLModel, table=True):
    __tablename__ = "auditoria"
    __table_args__ = ({"schema": SCHEMA},)

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    empresa_id: UUID | None = Field(default=None, index=True)
    tabla: str = Field(max_length=200)
    registro_id: UUID | None = Field(default=None, index=True)
    operacion: str = Field(max_length=10)
    datos_antes: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    datos_despues: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    auth_id: str | None = Field(default=None, max_length=200)
    request_id: str | None = Field(default=None, max_length=200)
    ocurrido_en: datetime = timestamptz()
