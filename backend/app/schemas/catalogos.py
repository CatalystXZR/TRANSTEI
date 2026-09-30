from datetime import date
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.models import TipoRampla

MONEY = dict(max_digits=14, decimal_places=2)


class ClienteCreate(SQLModel):
    razon_social: str
    rut: str
    giro: str | None = None
    dias_pago: int = 30
    telefono: str | None = None
    email: str | None = None


class ClienteUpdate(SQLModel):
    razon_social: str | None = None
    rut: str | None = None
    giro: str | None = None
    dias_pago: int | None = None
    telefono: str | None = None
    email: str | None = None


class ChoferCreate(SQLModel):
    nombre: str
    rut: str
    sueldo_base: Decimal = Field(default=Decimal("0"), **MONEY)
    porcentaje_produccion: Decimal = Field(
        default=Decimal("0"), max_digits=5, decimal_places=4, ge=0, le=1
    )
    vencimiento_licencia: date | None = None


class ChoferUpdate(SQLModel):
    nombre: str | None = None
    rut: str | None = None
    sueldo_base: Decimal | None = Field(default=None, **MONEY)
    porcentaje_produccion: Decimal | None = Field(
        default=None, max_digits=5, decimal_places=4, ge=0, le=1
    )
    vencimiento_licencia: date | None = None


class TractoCreate(SQLModel):
    patente: str
    marca: str | None = None
    modelo: str | None = None
    ano: int | None = None
    km_actual: int = 0
    vencimiento_revision_tecnica: date | None = None
    vencimiento_seguro: date | None = None


class TractoUpdate(SQLModel):
    patente: str | None = None
    marca: str | None = None
    modelo: str | None = None
    ano: int | None = None
    km_actual: int | None = None
    vencimiento_revision_tecnica: date | None = None
    vencimiento_seguro: date | None = None


class RamplaCreate(SQLModel):
    patente: str
    tipo: TipoRampla = TipoRampla.plana
    vencimiento_revision_tecnica: date | None = None


class RamplaUpdate(SQLModel):
    patente: str | None = None
    tipo: TipoRampla | None = None
    vencimiento_revision_tecnica: date | None = None
