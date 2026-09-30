from datetime import date
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.models import CategoriaGasto, EstadoViaje

MONEY = dict(max_digits=14, decimal_places=2)


class ViajeCreate(SQLModel):
    fecha_inicio: date
    fecha_fin: date | None = None
    origen: str
    destino: str
    valor_flete_neto: Decimal = Field(default=Decimal("0"), **MONEY)
    cliente_id: str
    chofer_id: str
    tracto_id: str
    rampla_id: str
    notas: str | None = None


class ViajeUpdate(SQLModel):
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    origen: str | None = None
    destino: str | None = None
    valor_flete_neto: Decimal | None = Field(default=None, **MONEY)
    cliente_id: str | None = None
    chofer_id: str | None = None
    tracto_id: str | None = None
    rampla_id: str | None = None
    notas: str | None = None


class ViajeEstadoUpdate(SQLModel):
    estado: EstadoViaje


class ViajeRead(SQLModel):
    id: str
    fecha_inicio: date
    fecha_fin: date | None
    origen: str
    destino: str
    estado: EstadoViaje
    valor_flete_neto: Decimal
    cliente_id: str
    chofer_id: str
    tracto_id: str
    rampla_id: str
    notas: str | None
    cliente_nombre: str
    chofer_nombre: str
    tracto_patente: str
    rampla_patente: str
    total_gastos: Decimal = Decimal("0")


class GastoCreate(SQLModel):
    categoria: CategoriaGasto
    monto: Decimal = Field(ge=0, **MONEY)
    iva_recuperable: bool = False
    fecha: date | None = None
    notas: str | None = None


class ViajeDetalle(SQLModel):
    viaje: ViajeRead
    gastos: list
