from datetime import date
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.models import EstadoFactura, TipoFactura

MONEY = dict(max_digits=14, decimal_places=2)


class FacturaCreate(SQLModel):
    numero_sii: str
    cliente_id: str
    tipo: TipoFactura = TipoFactura.afecta
    fecha_emision: date | None = None
    fecha_vencimiento: date | None = None
    viaje_ids: list[str] = []
    notas: str | None = None


class FacturaUpdate(SQLModel):
    numero_sii: str | None = None
    tipo: TipoFactura | None = None
    fecha_emision: date | None = None
    fecha_vencimiento: date | None = None
    notas: str | None = None


class FacturaEstadoUpdate(SQLModel):
    estado: EstadoFactura


class ViajeFacturadoResumen(SQLModel):
    id: str
    origen: str
    destino: str
    valor_flete_neto: Decimal = Field(**MONEY)


class FacturaRead(SQLModel):
    id: str
    numero_sii: str
    cliente_id: str
    cliente_nombre: str
    tipo: TipoFactura
    monto_neto: Decimal
    iva: Decimal
    total: Decimal
    fecha_emision: date
    fecha_vencimiento: date | None
    fecha_pago: date | None
    estado: EstadoFactura
    notas: str | None
    viajes: list[ViajeFacturadoResumen] = []


class CobranzaItem(SQLModel):
    id: str
    numero_sii: str
    cliente: str
    total: Decimal
    fecha_emision: date
    fecha_vencimiento: date | None
    dias_restantes: int | None
    semaforo: str  # vencida | por_vencer | al_dia


class CobranzasResumen(SQLModel):
    total_vencidas: Decimal
    total_por_vencer: Decimal
    total_al_dia: Decimal
    items: list[CobranzaItem]


class IvaResumen(SQLModel):
    mes: str
    tasa: Decimal
    debito: Decimal
    credito: Decimal
    a_pagar: Decimal
    facturas: list[dict]
    gastos: list[dict]
