from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


# ------------------------------------------------------------
# Enums (los nombres de los miembros coinciden con los valores
# y con los tipos nativos de PostgreSQL de la migración 0001)
# ------------------------------------------------------------
class RolUsuario(str, Enum):
    admin = "admin"
    operacion = "operacion"
    contabilidad = "contabilidad"


class EstadoViaje(str, Enum):
    programado = "programado"
    en_ruta = "en_ruta"
    finalizado = "finalizado"
    facturado = "facturado"


class EstadoFactura(str, Enum):
    pendiente = "pendiente"
    pagada = "pagada"
    anulada = "anulada"


class TipoFactura(str, Enum):
    afecta = "afecta"
    exenta = "exenta"


class CategoriaGasto(str, Enum):
    combustible = "combustible"
    peaje = "peaje"
    viatico = "viatico"
    mantenimiento_ruta = "mantenimiento_ruta"
    otros = "otros"


class TipoRampla(str, Enum):
    plana = "plana"
    sider = "sider"


class TipoAjuste(str, Enum):
    bono = "bono"
    descuento = "descuento"


class EstadoLiquidacion(str, Enum):
    borrador = "borrador"
    emitida = "emitida"


MONEY = dict(max_digits=14, decimal_places=2)


# ------------------------------------------------------------
# Modelos
# ------------------------------------------------------------
class Usuario(SQLModel, table=True):
    __tablename__ = "usuarios"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    auth_id: UUID = Field(foreign_key="auth.users.id", unique=True)
    nombre: str
    email: str | None = None
    rol: RolUsuario = Field(default=RolUsuario.operacion)
    activo: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Cliente(SQLModel, table=True):
    __tablename__ = "clientes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    razon_social: str
    rut: str = Field(unique=True)
    giro: str | None = None
    dias_pago: int = 30
    telefono: str | None = None
    email: str | None = None
    activo: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Chofer(SQLModel, table=True):
    __tablename__ = "choferes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    nombre: str
    rut: str = Field(unique=True)
    sueldo_base: Decimal = Field(default=Decimal("0"), **MONEY)
    porcentaje_produccion: Decimal = Field(
        default=Decimal("0"), max_digits=5, decimal_places=4, ge=0, le=1
    )
    vencimiento_licencia: date | None = None
    activo: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Tracto(SQLModel, table=True):
    __tablename__ = "tractos"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    patente: str = Field(unique=True)
    marca: str | None = None
    modelo: str | None = None
    ano: int | None = None
    km_actual: int = 0
    vencimiento_revision_tecnica: date | None = None
    vencimiento_seguro: date | None = None
    activo: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Rampla(SQLModel, table=True):
    __tablename__ = "ramplas"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    patente: str = Field(unique=True)
    tipo: TipoRampla = TipoRampla.plana
    vencimiento_revision_tecnica: date | None = None
    activo: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Viaje(SQLModel, table=True):
    __tablename__ = "viajes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    fecha_inicio: date
    fecha_fin: date | None = None
    origen: str
    destino: str
    estado: EstadoViaje = EstadoViaje.programado
    valor_flete_neto: Decimal = Field(default=Decimal("0"), **MONEY)
    cliente_id: UUID = Field(foreign_key="clientes.id")
    chofer_id: UUID = Field(foreign_key="choferes.id")
    tracto_id: UUID = Field(foreign_key="tractos.id")
    rampla_id: UUID = Field(foreign_key="ramplas.id")
    notas: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class GastoViaje(SQLModel, table=True):
    __tablename__ = "gastos_viaje"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    viaje_id: UUID = Field(foreign_key="viajes.id", ondelete="CASCADE")
    categoria: CategoriaGasto
    monto: Decimal = Field(ge=0, **MONEY)
    iva_recuperable: bool = False
    respaldo_url: str | None = None
    fecha: date = Field(default_factory=date.today)
    notas: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Factura(SQLModel, table=True):
    __tablename__ = "facturas"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    numero_sii: str
    cliente_id: UUID = Field(foreign_key="clientes.id")
    tipo: TipoFactura = TipoFactura.afecta
    monto_neto: Decimal = Field(default=Decimal("0"), **MONEY)
    iva: Decimal = Field(default=Decimal("0"), **MONEY)
    total: Decimal = Field(default=Decimal("0"), **MONEY)
    fecha_emision: date = Field(default_factory=date.today)
    fecha_vencimiento: date | None = None
    fecha_pago: date | None = None
    estado: EstadoFactura = EstadoFactura.pendiente
    notas: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class FacturaViaje(SQLModel, table=True):
    __tablename__ = "factura_viaje"

    factura_id: UUID = Field(
        foreign_key="facturas.id", ondelete="CASCADE", primary_key=True
    )
    viaje_id: UUID = Field(foreign_key="viajes.id", primary_key=True)


class AnticipoChofer(SQLModel, table=True):
    __tablename__ = "anticipos_chofer"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    chofer_id: UUID = Field(foreign_key="choferes.id", ondelete="CASCADE")
    fecha: date = Field(default_factory=date.today)
    monto: Decimal = Field(gt=0, **MONEY)
    mes_liquidacion: str  # YYYY-MM
    notas: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class AjusteLiquidacion(SQLModel, table=True):
    __tablename__ = "ajustes_liquidacion"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    chofer_id: UUID = Field(foreign_key="choferes.id", ondelete="CASCADE")
    mes: str  # YYYY-MM
    tipo: TipoAjuste
    concepto: str
    monto: Decimal = Field(ge=0, **MONEY)
    created_at: datetime = Field(default_factory=datetime.now)


class Liquidacion(SQLModel, table=True):
    __tablename__ = "liquidaciones"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    chofer_id: UUID = Field(foreign_key="choferes.id")
    mes: str  # YYYY-MM
    sueldo_base: Decimal = Field(default=Decimal("0"), **MONEY)
    comision: Decimal = Field(default=Decimal("0"), **MONEY)
    total_anticipos: Decimal = Field(default=Decimal("0"), **MONEY)
    total_ajustes: Decimal = Field(default=Decimal("0"), **MONEY)
    total_liquido: Decimal = Field(default=Decimal("0"), **MONEY)
    estado: EstadoLiquidacion = EstadoLiquidacion.borrador
    pdf_url: str | None = None
    notas: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class PautaMantenimiento(SQLModel, table=True):
    __tablename__ = "pautas_mantenimiento"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    item: str
    intervalo_km: int = Field(gt=0)
    orden: int = 0
    activo: bool = True
    created_at: datetime = Field(default_factory=datetime.now)


class Mantenimiento(SQLModel, table=True):
    __tablename__ = "mantenimientos"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tracto_id: UUID = Field(foreign_key="tractos.id", ondelete="CASCADE")
    pauta_id: UUID = Field(foreign_key="pautas_mantenimiento.id")
    fecha: date = Field(default_factory=date.today)
    km: int
    costo: Decimal = Field(default=Decimal("0"), **MONEY)
    notas: str | None = None
    respaldo_url: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class Configuracion(SQLModel, table=True):
    __tablename__ = "configuracion"

    clave: str = Field(primary_key=True)
    valor: str
