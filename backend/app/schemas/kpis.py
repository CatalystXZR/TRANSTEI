from datetime import date

from sqlmodel import SQLModel


class ReglaColor(SQLModel):
    operador: str
    valor: float
    color: str


class KpiCreate(SQLModel):
    nombre: str
    descripcion: str | None = None
    ambito: str = "global"
    formula: str
    formato: str = "numero"
    periodo: str = "mes"
    reglas_color: list[dict] = []
    uso: str = "dashboard"
    activo: bool = True
    orden: int = 0


class KpiUpdate(SQLModel):
    nombre: str | None = None
    descripcion: str | None = None
    ambito: str | None = None
    formula: str | None = None
    formato: str | None = None
    periodo: str | None = None
    reglas_color: list[dict] | None = None
    uso: str | None = None
    activo: bool | None = None
    orden: int | None = None


class KpiPreviewRequest(SQLModel):
    formula: str
    ambito: str = "global"
    periodo: str | None = None
    viaje_id: str | None = None
    flete_viaje: float | None = None
    chofer_id: str | None = None
    gastos_viaje: float | None = None


class KpiValor(SQLModel):
    id: str
    nombre: str
    descripcion: str | None
    formato: str
    valor: float | None
    color: str
    error: str | None = None
    periodo: str | None = None
