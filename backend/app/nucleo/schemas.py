"""Contratos Pydantic del núcleo operacional.

Los requests usan `extra="forbid"` para que un error de tipeo del frontend no
se convierta silenciosamente en un campo ignorado. Los datetimes deben ser
aware; la API rechaza naive con 422 antes de tocar la base.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.nucleo.models import (
    EstadoOC,
    EstadoRecurso,
    EstadoViaje,
    ModalidadTarifa,
    RolEmpresa,
    TipoCarga,
    TipoDocumento,
    TipoRampla,
    TipoRecurso,
    TipoReserva,
)

MAX_DURACION_VIAJE = timedelta(days=90)


def _exigir_aware(valor: datetime | None, campo: str) -> datetime | None:
    if valor is not None and (valor.tzinfo is None or valor.utcoffset() is None):
        raise ValueError(
            f"{campo} debe incluir zona horaria. Ejemplo: 2026-11-01T08:00:00-03:00"
        )
    return valor


class SolicitudAsignacion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracto_id: UUID
    rampla_id: UUID
    chofer_id: UUID
    inicio_planificado: datetime
    fin_planificado: datetime
    fin_estimado: datetime | None = None
    buffer_minutos: int | None = Field(default=None, ge=0, le=1440)
    minutos_traslado: int = Field(default=0, ge=0, le=1440)
    motivo_reasignacion: str | None = Field(default=None, max_length=500)

    @field_validator("inicio_planificado", "fin_planificado", "fin_estimado")
    @classmethod
    def validar_aware(cls, valor: datetime | None, info):
        return _exigir_aware(valor, info.field_name)

    @model_validator(mode="after")
    def validar_ventana(self):
        if self.fin_planificado <= self.inicio_planificado:
            raise ValueError("fin_planificado debe ser posterior a inicio_planificado")
        if self.fin_estimado is not None and self.fin_estimado <= self.inicio_planificado:
            raise ValueError("fin_estimado debe ser posterior a inicio_planificado")
        if self.fin_planificado - self.inicio_planificado > MAX_DURACION_VIAJE:
            raise ValueError("La ventana del viaje no puede superar 90 días")
        return self


class SolicitudValidacionAsignacion(SolicitudAsignacion):
    viaje_id: UUID


class VentanaOut(BaseModel):
    inicio: datetime
    fin: datetime
    incluye_buffer: bool = True


class IncidenciaOut(BaseModel):
    codigo: str
    mensaje: str
    bloqueante: bool = True
    recurso_tipo: TipoRecurso | None = None
    recurso_id: str | None = None


class DocumentoOut(BaseModel):
    recurso_tipo: TipoRecurso
    recurso_id: UUID
    tipo: str
    estado: str  # vigente | por_vencer | vencido | faltante | insuficiente
    requerido: bool = True
    bloqueante: bool = False
    vence_en: str | None = None
    dias_restantes: int | None = None
    motivo: str | None = None
    numero: str | None = None


class ConflictoOut(BaseModel):
    recurso_tipo: TipoRecurso
    recurso_id: UUID
    tipo_reserva: TipoReserva
    inicio: datetime
    fin: datetime
    motivo: str | None = None
    viaje_id: UUID | None = None


class ReservaOut(BaseModel):
    id: UUID
    tipo_reserva: TipoReserva
    inicio: datetime
    fin: datetime
    motivo: str | None = None
    viaje_id: UUID | None = None


class RecursoOut(BaseModel):
    id: UUID
    tipo: TipoRecurso
    etiqueta: str
    estado: EstadoRecurso
    activo: bool
    disponible: bool
    libre_desde: datetime | None
    inicio_operativo_posible: datetime | None = None
    documentos_ok: bool
    capacidad_carga_kg: Decimal | None = None
    volumen_m3: Decimal | None = None
    tipo_rampla: str | None = None
    licencia_clase: str | None = None
    incidencias: list[IncidenciaOut] = Field(default_factory=list)
    advertencias: list[IncidenciaOut] = Field(default_factory=list)
    documentos: list[DocumentoOut] = Field(default_factory=list)
    proximas_reservas: list[ReservaOut] = Field(default_factory=list)


class ResultadoValidacion(BaseModel):
    apto: bool
    viaje_id: UUID
    numero_viaje: str
    estado: EstadoViaje
    empresa_id: UUID
    zona_horaria: str
    ventana: VentanaOut
    recursos: list[RecursoOut]
    documentos: list[DocumentoOut]
    conflictos: list[ConflictoOut]
    incidencias: list[IncidenciaOut]
    advertencias: list[IncidenciaOut]
    libre_desde: datetime | None
    inicio_operativo_posible: datetime | None
    flete_total: Decimal
    oc_numero: str | None = None
    tarifa_codigo: str | None = None
    mensaje: str


class AsignacionConfirmada(BaseModel):
    viaje_id: UUID
    numero_viaje: str
    estado: EstadoViaje
    version: int
    empresa_id: UUID
    recursos: list[RecursoOut]
    ventana: VentanaOut
    reservas: list[ReservaOut]
    libre_desde: datetime | None
    inicio_operativo_posible: datetime | None
    audit_ok: bool = True


class TarifaOpcionOut(BaseModel):
    id: UUID
    cliente_id: UUID
    codigo: str
    nombre: str
    modalidad: ModalidadTarifa
    origen: str | None = None
    destino: str | None = None
    moneda: str
    precio_unitario: Decimal
    minimo_cobro: Decimal
    vigencia_desde: date
    vigencia_hasta: date | None = None
    activo: bool


class OrdenCompraOpcionOut(BaseModel):
    id: UUID
    cliente_id: UUID
    numero_oc: str
    monto_autorizado: Decimal
    monto_consumido: Decimal
    sobregiro_autorizado: Decimal
    moneda: str
    vigencia_desde: date
    vigencia_hasta: date
    estado: EstadoOC


class ViajeCreateNucleo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cliente_id: UUID
    orden_compra_id: UUID | None = None
    tarifa_id: UUID
    inicio_planificado: datetime
    fin_planificado: datetime
    buffer_minutos: int | None = Field(default=None, ge=0, le=1440)

    origen_nombre: str = Field(min_length=1, max_length=200)
    origen_direccion: str | None = Field(default=None, max_length=300)
    origen_comuna: str | None = Field(default=None, max_length=120)
    origen_ciudad: str | None = Field(default=None, max_length=120)
    origen_region: str | None = Field(default=None, max_length=120)
    origen_lat: Decimal | None = Field(default=None, max_digits=9, decimal_places=6)
    origen_lon: Decimal | None = Field(default=None, max_digits=9, decimal_places=6)
    destino_nombre: str = Field(min_length=1, max_length=200)
    destino_direccion: str | None = Field(default=None, max_length=300)
    destino_comuna: str | None = Field(default=None, max_length=120)
    destino_ciudad: str | None = Field(default=None, max_length=120)
    destino_region: str | None = Field(default=None, max_length=120)
    destino_lat: Decimal | None = Field(default=None, max_digits=9, decimal_places=6)
    destino_lon: Decimal | None = Field(default=None, max_digits=9, decimal_places=6)
    distancia_km: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    km_vacios: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    tiempo_estimado_h: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)

    tipo_carga: TipoCarga = TipoCarga.general
    descripcion_carga: str | None = None
    codigo_carga_cliente: str | None = Field(default=None, max_length=80)
    peso_bruto_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    peso_neto_kg: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    tara_kg: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=3)
    volumen_m3: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)
    bultos: int | None = Field(default=None, ge=0)
    largo_m: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=3)
    ancho_m: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=3)
    alto_m: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=3)
    valor_declarado: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=2)
    moneda_valor: str = Field(default="CLP", max_length=3)

    carga_peligrosa: bool = False
    numero_un: str | None = Field(default=None, max_length=20)
    clase_peligro: str | None = Field(default=None, max_length=20)
    msds_url: str | None = Field(default=None, max_length=1000)
    refrigerada: bool = False
    temperatura_min_c: Decimal | None = Field(default=None, max_digits=5, decimal_places=2)
    temperatura_max_c: Decimal | None = Field(default=None, max_digits=5, decimal_places=2)
    sobredimensionada: bool = False
    permiso_vialidad: str | None = Field(default=None, max_length=200)
    requiere_grua: bool = False
    requiere_montacargas: bool = False
    sellos: list[str] = Field(default_factory=list)
    instrucciones_especiales: str | None = None

    ventana_carga_desde: datetime | None = None
    ventana_carga_hasta: datetime | None = None
    ventana_descarga_desde: datetime | None = None
    ventana_descarga_hasta: datetime | None = None
    contacto_origen_nombre: str | None = Field(default=None, max_length=200)
    contacto_origen_telefono: str | None = Field(default=None, max_length=50)
    contacto_destino_nombre: str | None = Field(default=None, max_length=200)
    contacto_destino_telefono: str | None = Field(default=None, max_length=50)

    monto_recargos: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    condiciones_pago_dias: int | None = Field(default=None, ge=0, le=365)
    observaciones: str | None = None

    @field_validator(
        "inicio_planificado",
        "fin_planificado",
        "ventana_carga_desde",
        "ventana_carga_hasta",
        "ventana_descarga_desde",
        "ventana_descarga_hasta",
    )
    @classmethod
    def validar_aware(cls, valor: datetime | None, info):
        return _exigir_aware(valor, info.field_name)

    @model_validator(mode="after")
    def validar_viaje(self):
        if self.fin_planificado <= self.inicio_planificado:
            raise ValueError("fin_planificado debe ser posterior a inicio_planificado")
        if self.fin_planificado - self.inicio_planificado > MAX_DURACION_VIAJE:
            raise ValueError("La ventana del viaje no puede superar 90 días")
        if self.peso_neto_kg is not None and self.peso_neto_kg > self.peso_bruto_kg:
            raise ValueError("El peso neto no puede superar el peso bruto")
        if self.carga_peligrosa and not (self.numero_un or "").strip():
            raise ValueError("La carga peligrosa requiere número UN")
        if self.refrigerada:
            if self.temperatura_min_c is None or self.temperatura_max_c is None:
                raise ValueError("La carga refrigerada requiere temperatura mínima y máxima")
            if self.temperatura_min_c > self.temperatura_max_c:
                raise ValueError("La temperatura mínima no puede superar la máxima")
        return self


class ViajeResumenOut(BaseModel):
    id: UUID
    numero_viaje: str
    estado: EstadoViaje
    cliente_id: UUID
    cliente_nombre: str
    orden_compra_id: UUID | None = None
    oc_numero: str | None = None
    tarifa_id: UUID | None = None
    tarifa_codigo: str | None = None
    origen: str
    destino: str
    inicio_planificado: datetime
    fin_planificado: datetime
    buffer_minutos: int
    peso_bruto_kg: Decimal | None = None
    flete_total: Decimal
    tracto_id: UUID | None = None
    tracto_patente: str | None = None
    rampla_id: UUID | None = None
    rampla_patente: str | None = None
    chofer_id: UUID | None = None
    chofer_nombre: str | None = None
    carga_peligrosa: bool = False
    refrigerada: bool = False


class ListaViajesOut(BaseModel):
    items: list[ViajeResumenOut]
    total: int
    limit: int
    offset: int
    hay_mas: bool


class LibreDesdeOut(BaseModel):
    recurso_tipo: TipoRecurso
    recurso_id: UUID
    etiqueta: str
    consultado_desde: datetime
    libre_desde: datetime | None
    inicio_operativo_posible: datetime | None
    disponible: bool
    documentos_ok: bool
    documentos: list[DocumentoOut] = Field(default_factory=list)
    incidencias: list[IncidenciaOut] = Field(default_factory=list)
    advertencias: list[IncidenciaOut] = Field(default_factory=list)
    proximas_reservas: list[ReservaOut] = Field(default_factory=list)
    mensaje: str


class PaginacionOut(BaseModel):
    total: int
    limit: int
    offset: int
    hay_mas: bool


class ListaRecursosOut(BaseModel):
    items: list[RecursoOut]
    paginacion: PaginacionOut
    desde: datetime
    hasta: datetime
    zona_horaria: str


class EmpresaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    codigo: str
    razon_social: str
    rut: str
    zona_horaria: str
    moneda: str
    buffer_operacional_min: int


class EmpresaMembresiaOut(EmpresaOut):
    rol: RolEmpresa


class ClienteCreateNucleo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    razon_social: str = Field(min_length=1, max_length=250)
    rut: str = Field(min_length=1, max_length=20)
    giro: str | None = Field(default=None, max_length=250)
    direccion: str | None = Field(default=None, max_length=300)
    comuna: str | None = Field(default=None, max_length=120)
    ciudad: str | None = Field(default=None, max_length=120)
    contacto_nombre: str | None = Field(default=None, max_length=200)
    contacto_email: str | None = Field(default=None, max_length=200)
    contacto_telefono: str | None = Field(default=None, max_length=50)
    dias_pago: int = Field(default=30, ge=0, le=365)
    credito_autorizado: Decimal = Field(default=Decimal("0"), ge=0, max_digits=16, decimal_places=2)
    exige_oc: bool = False
    activo: bool = True
    observaciones: str | None = None


class TractoCreateNucleo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patente: str = Field(min_length=1, max_length=20)
    marca: str | None = Field(default=None, max_length=80)
    modelo: str | None = Field(default=None, max_length=80)
    ano: int | None = Field(default=None, ge=1950, le=2100)
    vin: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, max_length=40)
    configuracion_ejes: str | None = Field(default=None, max_length=40)
    peso_bruto_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    tara_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    capacidad_carga_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    volumen_m3: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)
    km_actual: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=1)
    horas_motor: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=1)
    licencias_permitidas: list[str] = Field(default_factory=list)
    estado: EstadoRecurso = EstadoRecurso.disponible
    activo: bool = True
    ubicacion_ciudad: str | None = Field(default=None, max_length=120)
    ubicacion_lat: Decimal | None = Field(default=None, max_digits=9, decimal_places=6)
    ubicacion_lon: Decimal | None = Field(default=None, max_digits=9, decimal_places=6)
    observaciones: str | None = None

    @model_validator(mode="after")
    def validar_pesos(self):
        if self.tara_kg >= self.peso_bruto_kg:
            raise ValueError("La tara debe ser menor que el peso bruto")
        if self.capacidad_carga_kg > self.peso_bruto_kg - self.tara_kg:
            raise ValueError("La capacidad de carga no puede superar el peso bruto menos la tara")
        return self


class RamplaCreateNucleo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patente: str = Field(min_length=1, max_length=20)
    tipo: TipoRampla = TipoRampla.plana
    marca: str | None = Field(default=None, max_length=80)
    modelo: str | None = Field(default=None, max_length=80)
    ano: int | None = Field(default=None, ge=1950, le=2100)
    vin: str | None = Field(default=None, max_length=40)
    capacidad_carga_kg: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    volumen_m3: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)
    largo_m: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=3)
    ancho_m: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=3)
    alto_m: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=3)
    peso_tara_kg: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    ejes: int | None = Field(default=None, ge=1, le=12)
    temperatura_min_c: Decimal | None = Field(default=None, max_digits=5, decimal_places=2)
    temperatura_max_c: Decimal | None = Field(default=None, max_digits=5, decimal_places=2)
    estado: EstadoRecurso = EstadoRecurso.disponible
    activo: bool = True
    ubicacion_ciudad: str | None = Field(default=None, max_length=120)
    ubicacion_lat: Decimal | None = Field(default=None, max_digits=9, decimal_places=6)
    ubicacion_lon: Decimal | None = Field(default=None, max_digits=9, decimal_places=6)
    observaciones: str | None = None

    @model_validator(mode="after")
    def validar_temperaturas(self):
        if (
            self.temperatura_min_c is not None
            and self.temperatura_max_c is not None
            and self.temperatura_min_c > self.temperatura_max_c
        ):
            raise ValueError("La temperatura mínima no puede superar la máxima")
        return self


class ChoferCreateNucleo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rut: str = Field(min_length=1, max_length=20)
    nombre: str = Field(min_length=1, max_length=150)
    apellido_paterno: str | None = Field(default=None, max_length=120)
    apellido_materno: str | None = Field(default=None, max_length=120)
    fecha_nacimiento: date | None = None
    telefono: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=200)
    direccion: str | None = Field(default=None, max_length=300)
    comuna: str | None = Field(default=None, max_length=120)
    ciudad: str | None = Field(default=None, max_length=120)
    numero_licencia: str | None = Field(default=None, max_length=60)
    licencia_clase: str | None = Field(default=None, max_length=10)
    licencia_restricciones: str | None = Field(default=None, max_length=250)
    autorizado_carga_peligrosa: bool = False
    sueldo_base: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    porcentaje_comision: Decimal = Field(
        default=Decimal("0"), ge=0, le=1, max_digits=5, decimal_places=4
    )
    contacto_emergencia_nombre: str | None = Field(default=None, max_length=200)
    contacto_emergencia_telefono: str | None = Field(default=None, max_length=50)
    estado: EstadoRecurso = EstadoRecurso.disponible
    activo: bool = True
    observaciones: str | None = None


class DocumentoOutNucleo(BaseModel):
    id: UUID
    recurso_tipo: TipoRecurso
    tracto_id: UUID | None = None
    rampla_id: UUID | None = None
    chofer_id: UUID | None = None
    tipo: TipoDocumento
    numero: str | None = None
    entidad_emisora: str | None = None
    emitido_en: date | None = None
    vence_en: date
    archivo_url: str | None = None
    hash_sha256: str | None = None
    es_vigente: bool
    observaciones: str | None = None
    created_at: datetime
    version: int


class DocumentoUrlOut(BaseModel):
    url: str
    expires_in: int = 3600


# ---------------------------------------------------------------------------
# P0-03 Comercial: centros de costo, tarifas y OC editables
# ---------------------------------------------------------------------------
class CentroCostoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str = Field(min_length=1, max_length=60)
    nombre: str = Field(min_length=1, max_length=200)
    descripcion: str | None = None
    activo: bool = True


class CentroCostoUpdate(CentroCostoCreate):
    version: int | None = Field(default=None, ge=1)


class CentroCostoOut(BaseModel):
    id: UUID
    codigo: str
    nombre: str
    descripcion: str | None = None
    activo: bool
    version: int


class TarifaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cliente_id: UUID
    codigo: str = Field(min_length=1, max_length=60)
    nombre: str = Field(min_length=1, max_length=200)
    descripcion: str | None = None
    modalidad: ModalidadTarifa
    origen: str | None = Field(default=None, max_length=200)
    destino: str | None = Field(default=None, max_length=200)
    tipo_rampla: TipoRampla | None = None
    tipo_carga: TipoCarga | None = None
    vigencia_desde: date = Field(default_factory=date.today)
    vigencia_hasta: date | None = None
    moneda: str = Field(default="CLP", min_length=3, max_length=3)
    precio_unitario: Decimal = Field(default=Decimal("0"), ge=0, max_digits=16, decimal_places=4)
    minimo_cobro: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    incluye_peajes: bool = False
    incluye_combustible: bool = False
    precio_diesel_base: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=4
    )
    rendimiento_km_l: Decimal | None = Field(
        default=None, gt=0, max_digits=6, decimal_places=3
    )
    participacion_combustible: Decimal | None = Field(
        default=None, ge=0, le=1, max_digits=5, decimal_places=4
    )
    recargos: dict[str, Any] = Field(default_factory=dict)
    condiciones: dict[str, Any] = Field(default_factory=dict)
    activo: bool = True

    @model_validator(mode="after")
    def validar_vigencia(self):
        if self.vigencia_hasta is not None and self.vigencia_hasta < self.vigencia_desde:
            raise ValueError("vigencia_hasta no puede ser anterior a vigencia_desde")
        return self


class TarifaUpdate(TarifaCreate):
    version: int | None = Field(default=None, ge=1)


class TarifaOut(BaseModel):
    id: UUID
    cliente_id: UUID
    cliente_nombre: str
    codigo: str
    nombre: str
    descripcion: str | None = None
    modalidad: ModalidadTarifa
    origen: str | None = None
    destino: str | None = None
    tipo_rampla: TipoRampla | None = None
    tipo_carga: TipoCarga | None = None
    vigencia_desde: date
    vigencia_hasta: date | None = None
    moneda: str
    precio_unitario: Decimal
    minimo_cobro: Decimal
    incluye_peajes: bool
    incluye_combustible: bool
    precio_diesel_base: Decimal | None = None
    rendimiento_km_l: Decimal | None = None
    participacion_combustible: Decimal | None = None
    recargos: dict[str, Any] = Field(default_factory=dict)
    condiciones: dict[str, Any] = Field(default_factory=dict)
    activo: bool
    vencida: bool = False
    viajes_activos: int = 0
    version: int
    created_at: datetime
    updated_at: datetime


class OrdenCompraLineaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    descripcion: str = Field(min_length=1)
    origen: str | None = Field(default=None, max_length=200)
    destino: str | None = Field(default=None, max_length=200)
    tarifa_id: UUID | None = None
    centro_costo_id: UUID | None = None
    cantidad_estimada: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=14, decimal_places=3
    )
    unidad: str = Field(default="viaje", min_length=1, max_length=40)
    precio_unitario: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=16, decimal_places=4
    )


class OrdenCompraLineaUpdate(OrdenCompraLineaCreate):
    activa: bool = True
    version: int | None = Field(default=None, ge=1)


class OrdenCompraLineaOut(BaseModel):
    id: UUID
    numero_linea: int
    descripcion: str
    origen: str | None = None
    destino: str | None = None
    tarifa_id: UUID | None = None
    centro_costo_id: UUID | None = None
    cantidad_estimada: Decimal
    unidad: str
    precio_unitario: Decimal
    monto_linea: Decimal
    activa: bool
    version: int


class OrdenCompraCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cliente_id: UUID
    numero_oc: str = Field(min_length=1, max_length=80)
    referencia_interna: str | None = Field(default=None, max_length=80)
    fecha_emision: date = Field(default_factory=date.today)
    vigencia_desde: date = Field(default_factory=date.today)
    vigencia_hasta: date
    monto_autorizado: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    sobregiro_autorizado: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=16, decimal_places=2
    )
    moneda: str = Field(default="CLP", min_length=3, max_length=3)
    centro_costo_id: UUID | None = None
    proyecto: str | None = Field(default=None, max_length=120)
    faena: str | None = Field(default=None, max_length=120)
    condiciones_pago_dias: int | None = Field(default=None, ge=0, le=365)
    observaciones: str | None = None
    lineas: list[OrdenCompraLineaCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validar_vigencia(self):
        if self.vigencia_hasta < self.vigencia_desde:
            raise ValueError("vigencia_hasta no puede ser anterior a vigencia_desde")
        if self.fecha_emision > self.vigencia_hasta:
            raise ValueError("fecha_emision no puede ser posterior a vigencia_hasta")
        total_lineas = sum(
            (linea.cantidad_estimada * linea.precio_unitario for linea in self.lineas),
            Decimal("0"),
        )
        if total_lineas > self.monto_autorizado:
            raise ValueError("La suma de las líneas no puede superar el monto autorizado")
        return self


class OrdenCompraUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    referencia_interna: str | None = Field(default=None, max_length=80)
    fecha_emision: date | None = None
    vigencia_desde: date | None = None
    vigencia_hasta: date | None = None
    monto_autorizado: Decimal | None = Field(
        default=None, gt=0, max_digits=16, decimal_places=2
    )
    moneda: str | None = Field(default=None, min_length=3, max_length=3)
    centro_costo_id: UUID | None = None
    proyecto: str | None = Field(default=None, max_length=120)
    faena: str | None = Field(default=None, max_length=120)
    condiciones_pago_dias: int | None = Field(default=None, ge=0, le=365)
    observaciones: str | None = None
    version: int | None = Field(default=None, ge=1)


class ConsumoViajeOut(BaseModel):
    id: UUID
    numero_viaje: str
    estado: EstadoViaje
    inicio_planificado: datetime
    monto: Decimal
    porcentaje_oc: Decimal


class OrdenCompraResumenOut(BaseModel):
    id: UUID
    cliente_id: UUID
    cliente_nombre: str
    numero_oc: str
    referencia_interna: str | None = None
    fecha_emision: date
    vigencia_desde: date
    vigencia_hasta: date
    monto_autorizado: Decimal
    sobregiro_autorizado: Decimal
    monto_consumido: Decimal
    saldo_disponible: Decimal
    porcentaje_consumo: Decimal
    alerta: str  # normal | 80 | 90 | 100 | sobregiro
    moneda: str
    centro_costo_id: UUID | None = None
    centro_costo_nombre: str | None = None
    estado: EstadoOC
    vencida: bool
    sobregiro_estado: str
    sobregiro_solicitado: Decimal
    lineas_count: int = 0
    viajes_count: int = 0
    version: int


class OrdenCompraOut(OrdenCompraResumenOut):
    proyecto: str | None = None
    faena: str | None = None
    condiciones_pago_dias: int | None = None
    observaciones: str | None = None
    sobregiro_motivo: str | None = None
    sobregiro_solicitado_por: str | None = None
    sobregiro_solicitado_en: datetime | None = None
    sobregiro_aprobado_por: str | None = None
    sobregiro_aprobado_en: datetime | None = None
    sobregiro_resolucion: str | None = None
    lineas: list[OrdenCompraLineaOut] = Field(default_factory=list)
    viajes: list[ConsumoViajeOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SolicitudSobregiro(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monto: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    motivo: str = Field(min_length=5, max_length=1000)


class AprobacionSobregiro(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monto: Decimal | None = Field(default=None, gt=0, max_digits=16, decimal_places=2)
    observacion: str | None = Field(default=None, max_length=1000)


class RechazoSobregiro(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: str = Field(min_length=5, max_length=1000)


class HistorialCambioOut(BaseModel):
    id: int
    tabla: str
    registro_id: UUID | None = None
    operacion: str
    ocurrido_en: datetime
    auth_id: str | None = None
    datos_antes: dict[str, Any] | None = None
    datos_despues: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# P0-04 Bloqueos de recursos y agenda
# ---------------------------------------------------------------------------
class BloqueoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recurso_tipo: TipoRecurso
    recurso_id: UUID
    inicio: datetime
    fin: datetime
    tipo_reserva: TipoReserva
    motivo: str = Field(min_length=5, max_length=500)

    @field_validator("inicio", "fin")
    @classmethod
    def validar_aware(cls, valor: datetime, info):
        return _exigir_aware(valor, info.field_name)

    @model_validator(mode="after")
    def validar_bloqueo(self):
        if self.fin <= self.inicio:
            raise ValueError("El fin del bloqueo debe ser posterior al inicio")
        if self.fin - self.inicio > timedelta(days=365):
            raise ValueError("El bloqueo no puede superar 365 días")
        if self.tipo_reserva == TipoReserva.viaje:
            raise ValueError("Use la asignación de viaje para reservas de tipo viaje")
        return self


class BloqueoUpdate(BloqueoCreate):
    version: int | None = Field(default=None, ge=1)


class CancelarBloqueo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: str = Field(min_length=3, max_length=500)


class BloqueoOut(BaseModel):
    id: UUID
    recurso_tipo: TipoRecurso
    recurso_id: UUID
    etiqueta: str
    inicio: datetime
    fin: datetime
    tipo_reserva: TipoReserva
    motivo: str | None = None
    activa: bool
    cancelado_motivo: str | None = None
    cancelado_por: str | None = None
    cancelado_en: datetime | None = None
    creado_por: str
    created_at: datetime
    version: int


class AgendaItemOut(BaseModel):
    id: UUID
    origen: str  # bloqueo | viaje
    recurso_tipo: TipoRecurso
    recurso_id: UUID
    inicio: datetime
    fin: datetime
    tipo_reserva: TipoReserva
    motivo: str | None = None
    viaje_id: UUID | None = None
    numero_viaje: str | None = None
    estado_viaje: EstadoViaje | None = None
    cancelable: bool = False


class AgendaRecursoOut(BaseModel):
    recurso_tipo: TipoRecurso
    recurso_id: UUID
    etiqueta: str
    estado: str
    activo: bool
    items: list[AgendaItemOut] = Field(default_factory=list)


class AgendaOut(BaseModel):
    desde: datetime
    hasta: datetime
    zona_horaria: str
    recursos: list[AgendaRecursoOut]
    total_bloqueos: int
    total_viajes: int
    mensaje: str


# ---------------------------------------------------------------------------
# P0-05 Expediente del viaje
# ---------------------------------------------------------------------------
class ParadaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orden: int | None = Field(default=None, ge=1)
    tipo: str = Field(default="intermedia", min_length=1, max_length=20)
    nombre: str = Field(min_length=1, max_length=200)
    direccion: str | None = Field(default=None, max_length=300)
    comuna: str | None = Field(default=None, max_length=120)
    ciudad: str | None = Field(default=None, max_length=120)
    contacto_nombre: str | None = Field(default=None, max_length=200)
    contacto_telefono: str | None = Field(default=None, max_length=50)
    ventana_desde: datetime | None = None
    ventana_hasta: datetime | None = None
    estado: str = Field(default="pendiente", max_length=20)
    notas: str | None = None

    @field_validator("ventana_desde", "ventana_hasta")
    @classmethod
    def validar_aware(cls, valor: datetime | None, info):
        return _exigir_aware(valor, info.field_name)

    @model_validator(mode="after")
    def validar_ventana(self):
        if self.ventana_desde and self.ventana_hasta and self.ventana_hasta < self.ventana_desde:
            raise ValueError("La ventana de la parada no es válida")
        return self


class ParadaUpdate(ParadaCreate):
    activo: bool = True
    version: int | None = Field(default=None, ge=1)


class ParadaOut(BaseModel):
    id: UUID
    orden: int
    tipo: str
    nombre: str
    direccion: str | None = None
    comuna: str | None = None
    ciudad: str | None = None
    contacto_nombre: str | None = None
    contacto_telefono: str | None = None
    ventana_desde: datetime | None = None
    ventana_hasta: datetime | None = None
    estado: str
    notas: str | None = None
    activo: bool
    version: int


class ChecklistItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categoria: str = Field(default="general", max_length=60)
    item: str = Field(min_length=1)
    requerido: bool = True
    orden: int | None = Field(default=None, ge=1)


class ChecklistItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completado: bool
    notas: str | None = None
    evidencia_url: str | None = Field(default=None, max_length=1000)
    version: int | None = Field(default=None, ge=1)


class ChecklistItemOut(BaseModel):
    id: UUID
    orden: int
    categoria: str
    item: str
    requerido: bool
    completado: bool
    completado_por: str | None = None
    completado_en: datetime | None = None
    evidencia_url: str | None = None
    notas: str | None = None
    version: int


class EventoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: str = Field(default="nota", min_length=1, max_length=60)
    descripcion: str = Field(min_length=1)
    ocurrido_en: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ocurrido_en")
    @classmethod
    def validar_aware(cls, valor: datetime | None, info):
        return _exigir_aware(valor, info.field_name)


class EventoOut(BaseModel):
    id: UUID
    tipo: str
    descripcion: str
    ocurrido_en: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    auth_id: str | None = None


class IncidenteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: str = Field(min_length=1, max_length=80)
    severidad: str = Field(default="media")
    descripcion: str = Field(min_length=1)
    ocurrido_en: datetime | None = None

    @field_validator("severidad")
    @classmethod
    def validar_severidad(cls, valor: str):
        if valor not in {"baja", "media", "alta", "critica"}:
            raise ValueError("severidad debe ser baja, media, alta o critica")
        return valor

    @field_validator("ocurrido_en")
    @classmethod
    def validar_aware(cls, valor: datetime | None, info):
        return _exigir_aware(valor, info.field_name)


class IncidenteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: str | None = None
    severidad: str | None = None
    resolucion: str | None = None
    version: int | None = Field(default=None, ge=1)

    @field_validator("estado")
    @classmethod
    def validar_estado(cls, valor: str | None):
        if valor is not None and valor not in {"abierto", "en_revision", "resuelto", "cerrado"}:
            raise ValueError("estado de incidente no válido")
        return valor

    @field_validator("severidad")
    @classmethod
    def validar_severidad(cls, valor: str | None):
        if valor is not None and valor not in {"baja", "media", "alta", "critica"}:
            raise ValueError("severidad debe ser baja, media, alta o critica")
        return valor


class IncidenteOut(BaseModel):
    id: UUID
    tipo: str
    severidad: str
    descripcion: str
    estado: str
    ocurrido_en: datetime
    reportado_por: str | None = None
    resolucion: str | None = None
    resuelto_por: str | None = None
    resuelto_en: datetime | None = None
    version: int


class ViajeDocumentoOut(BaseModel):
    id: UUID
    tipo: str
    nombre: str
    archivo_url: str
    hash_sha256: str | None = None
    content_type: str | None = None
    tamano_bytes: int | None = None
    observaciones: str | None = None
    activo: bool
    created_at: datetime
    url_firmada: str | None = None


class ResumenExpedienteOut(BaseModel):
    checklist_total: int
    checklist_completados: int
    checklist_requeridos_pendientes: int
    paradas_total: int
    paradas_completadas: int
    incidentes_abiertos: int
    documentos_count: int
    progreso_pct: Decimal
    puede_cerrar: bool
    motivos_cierre: list[str] = Field(default_factory=list)


class ViajeExpedienteOut(BaseModel):
    id: UUID
    numero_viaje: str
    estado: EstadoViaje
    cliente_id: UUID
    cliente_nombre: str
    cliente_rut: str | None = None
    orden_compra_id: UUID | None = None
    oc_numero: str | None = None
    tarifa_id: UUID | None = None
    tarifa_codigo: str | None = None
    tracto_id: UUID | None = None
    tracto_patente: str | None = None
    rampla_id: UUID | None = None
    rampla_patente: str | None = None
    chofer_id: UUID | None = None
    chofer_nombre: str | None = None
    inicio_planificado: datetime
    fin_planificado: datetime
    fin_estimado: datetime | None = None
    inicio_real: datetime | None = None
    fin_real: datetime | None = None
    buffer_minutos: int
    origen_nombre: str
    origen_direccion: str | None = None
    origen_comuna: str | None = None
    origen_ciudad: str | None = None
    origen_region: str | None = None
    destino_nombre: str
    destino_direccion: str | None = None
    destino_comuna: str | None = None
    destino_ciudad: str | None = None
    destino_region: str | None = None
    distancia_km: Decimal | None = None
    tiempo_estimado_h: Decimal | None = None
    tipo_carga: TipoCarga
    descripcion_carga: str | None = None
    peso_bruto_kg: Decimal | None = None
    peso_neto_kg: Decimal | None = None
    volumen_m3: Decimal | None = None
    bultos: int | None = None
    valor_declarado: Decimal | None = None
    moneda_valor: str | None = None
    carga_peligrosa: bool
    numero_un: str | None = None
    clase_peligro: str | None = None
    refrigerada: bool
    temperatura_min_c: Decimal | None = None
    temperatura_max_c: Decimal | None = None
    sobredimensionada: bool
    instrucciones_especiales: str | None = None
    valor_flete_neto: Decimal
    monto_recargos: Decimal
    monto_total_neto: Decimal | None = None
    moneda: str
    condiciones_pago_dias: int | None = None
    observaciones: str | None = None
    motivo_anulacion: str | None = None
    created_at: datetime
    updated_at: datetime
    version: int
    paradas: list[ParadaOut] = Field(default_factory=list)
    checklist: list[ChecklistItemOut] = Field(default_factory=list)
    eventos: list[EventoOut] = Field(default_factory=list)
    incidentes: list[IncidenteOut] = Field(default_factory=list)
    documentos: list[ViajeDocumentoOut] = Field(default_factory=list)
    historial: list[HistorialCambioOut] = Field(default_factory=list)
    gastos: list[dict[str, Any]] = Field(default_factory=list)
    factura: dict[str, Any] | None = None
    pod: dict[str, Any] | None = None
    costos: dict[str, Any] | None = None
    resumen: ResumenExpedienteOut
    qr_url: str


class CerrarViaje(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observaciones: str | None = Field(default=None, max_length=2000)


class ViajeExpedienteResumenOut(BaseModel):
    id: UUID
    numero_viaje: str
    estado: EstadoViaje
    cliente_id: UUID
    cliente_nombre: str
    origen: str
    destino: str
    inicio_planificado: datetime
    fin_planificado: datetime
    peso_bruto_kg: Decimal | None = None
    flete_total: Decimal
    oc_numero: str | None = None
    tarifa_codigo: str | None = None
    tracto_patente: str | None = None
    rampla_patente: str | None = None
    chofer_nombre: str | None = None
    checklist_pct: Decimal
    checklist_pendientes: int
    incidentes_abiertos: int
    documentos_count: int
    puede_cerrar: bool


class ListaExpedienteOut(BaseModel):
    items: list[ViajeExpedienteResumenOut]
    total: int
    limit: int
    offset: int
    hay_mas: bool


# ---------------------------------------------------------------------------
# P0-06 POD
# ---------------------------------------------------------------------------
class PODFotoOut(BaseModel):
    path: str
    nombre: str | None = None
    content_type: str | None = None
    url_firmada: str | None = None


class PODOut(BaseModel):
    id: UUID
    viaje_id: UUID
    receptor_nombre: str
    receptor_rut: str | None = None
    receptor_cargo: str | None = None
    fecha_hora: datetime
    lat: Decimal | None = None
    lon: Decimal | None = None
    firma_url: str
    firma_url_firmada: str | None = None
    firma_hash: str | None = None
    fotos: list[PODFotoOut] = Field(default_factory=list)
    danios: str | None = None
    observaciones: str | None = None
    created_at: datetime
    created_by: str
    version: int
    facturacion_habilitada: bool = True
    mensaje: str


class PODUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receptor_nombre: str = Field(min_length=1, max_length=200)
    receptor_rut: str | None = Field(default=None, max_length=20)
    receptor_cargo: str | None = Field(default=None, max_length=120)
    fecha_hora: datetime | None = None
    lat: Decimal | None = Field(default=None, ge=-90, le=90, max_digits=9, decimal_places=6)
    lon: Decimal | None = Field(default=None, ge=-180, le=180, max_digits=9, decimal_places=6)
    danios: str | None = None
    observaciones: str | None = None
    version: int | None = Field(default=None, ge=1)

    @field_validator("fecha_hora")
    @classmethod
    def validar_aware(cls, valor: datetime | None, info):
        return _exigir_aware(valor, info.field_name)


# ---------------------------------------------------------------------------
# P0-07 PWA del conductor
# ---------------------------------------------------------------------------
class ConductorPerfilOut(BaseModel):
    id: UUID
    nombre: str
    rut: str
    telefono: str | None = None
    licencia_clase: str | None = None
    numero_licencia: str | None = None
    estado: str


class TransicionConductor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado_destino: EstadoViaje
    motivo: str | None = Field(default=None, max_length=500)
    lat: Decimal | None = Field(default=None, ge=-90, le=90, max_digits=9, decimal_places=6)
    lon: Decimal | None = Field(default=None, ge=-180, le=180, max_digits=9, decimal_places=6)


class CheckInOutConductor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: Decimal | None = Field(default=None, ge=-90, le=90, max_digits=9, decimal_places=6)
    lon: Decimal | None = Field(default=None, ge=-180, le=180, max_digits=9, decimal_places=6)
    nota: str | None = Field(default=None, max_length=500)


class MiViajeOut(BaseModel):
    chofer: ConductorPerfilOut
    viaje: ViajeExpedienteOut | None = None
    mensaje: str
    siguiente_accion: str | None = None
    acciones_disponibles: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# P0-08 Gastos, combustible y costos
# ---------------------------------------------------------------------------
class PrecioDieselCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fecha: date = Field(default_factory=date.today)
    precio_litro: Decimal = Field(ge=0, max_digits=10, decimal_places=4)
    fuente: str | None = Field(default=None, max_length=120)


class PrecioDieselOut(BaseModel):
    id: UUID
    fecha: date
    precio_litro: Decimal
    fuente: str | None = None
    created_at: datetime


class GastoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: str = Field(default="otro", min_length=1, max_length=40)
    proveedor: str | None = Field(default=None, max_length=200)
    numero_documento: str | None = Field(default=None, max_length=80)
    fecha: date = Field(default_factory=date.today)
    monto_total: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    iva: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    moneda: str = Field(default="CLP", min_length=3, max_length=3)
    litros: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)
    precio_litro: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=4
    )
    km_odometro: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=1
    )
    estacion: str | None = Field(default=None, max_length=200)
    tag: str | None = Field(default=None, max_length=120)
    observaciones: str | None = None

    @model_validator(mode="after")
    def validar_gasto(self):
        if self.tipo not in {
            "combustible",
            "peaje",
            "estadia",
            "viatico",
            "mantenimiento",
            "lavado",
            "pesaje",
            "otro",
        }:
            raise ValueError("tipo de gasto no válido")
        if self.iva > self.monto_total:
            raise ValueError("El IVA no puede superar el monto total")
        if self.tipo == "combustible" and self.litros is None:
            raise ValueError("El gasto de combustible requiere litros")
        if self.litros is not None and self.precio_litro is not None:
            esperado = (self.litros * self.precio_litro).quantize(Decimal("0.01"))
            neto = self.monto_total - self.iva
            if abs(esperado - neto) > Decimal("1"):
                raise ValueError(
                    "El monto neto no coincide con litros × precio (tolerancia $1)"
                )
        return self


class GastoOut(BaseModel):
    id: UUID
    viaje_id: UUID
    tipo: str
    proveedor: str | None = None
    numero_documento: str | None = None
    fecha: date
    monto_total: Decimal
    iva: Decimal
    monto_neto: Decimal
    moneda: str
    litros: Decimal | None = None
    precio_litro: Decimal | None = None
    km_odometro: Decimal | None = None
    estacion: str | None = None
    tag: str | None = None
    comprobante_url: str | None = None
    comprobante_url_firmada: str | None = None
    estado: str
    motivo_rechazo: str | None = None
    aprobado_por: str | None = None
    aprobado_en: datetime | None = None
    observaciones: str | None = None
    activo: bool
    created_at: datetime
    created_by: str
    version: int


class AprobarGasto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observacion: str | None = Field(default=None, max_length=500)


class RechazarGasto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: str = Field(min_length=5, max_length=500)


class CostoPorTipoOut(BaseModel):
    tipo: str
    cantidad: int
    monto: Decimal


class CostosViajeOut(BaseModel):
    viaje_id: UUID
    flete_neto: Decimal
    recargos: Decimal
    ingreso_total: Decimal
    gastos_aprobados: Decimal
    gastos_pendientes: Decimal
    comision_estimada: Decimal
    costo_variable: Decimal
    costo_total: Decimal
    margen: Decimal
    margen_pct: Decimal
    litros: Decimal
    km_recorridos: Decimal | None = None
    rendimiento_km_l: Decimal | None = None
    costo_por_km: Decimal | None = None
    por_tipo: list[CostoPorTipoOut] = Field(default_factory=list)
    actualizado_en: datetime | None = None
    mensaje: str


# ---------------------------------------------------------------------------
# P0-09 Margen, tarifa piso y Freight Score
# ---------------------------------------------------------------------------
class ConfiguracionCostosBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    costo_fijo_mensual: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=14, decimal_places=2
    )
    viajes_estimados_mes: int = Field(default=60, ge=1, le=10000)
    margen_objetivo: Decimal = Field(
        default=Decimal("0.25"), ge=0, le=Decimal("0.95"), max_digits=5, decimal_places=4
    )
    benchmark_margen_km: Decimal = Field(
        default=Decimal("1200"), gt=0, max_digits=14, decimal_places=2
    )
    contribucion_minima: Decimal = Field(
        default=Decimal("100000"), ge=0, max_digits=14, decimal_places=2
    )
    costo_variable_km_estandar: Decimal = Field(
        default=Decimal("900"), ge=0, max_digits=14, decimal_places=2
    )
    rendimiento_km_l: Decimal = Field(
        default=Decimal("2.5"), gt=0, max_digits=6, decimal_places=3
    )
    precio_diesel: Decimal = Field(
        default=Decimal("1000"), ge=0, max_digits=10, decimal_places=4
    )


class ConfiguracionCostosUpdate(ConfiguracionCostosBase):
    version: int | None = Field(default=None, ge=1)


class ConfiguracionCostosOut(ConfiguracionCostosBase):
    id: UUID | None = None
    configurado: bool = False
    version: int = 0
    updated_at: datetime | None = None


class SimulacionFlete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    distancia_km: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    km_vacios: Decimal = Field(default=Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    peso_kg: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=3)
    capacidad_kg: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=3)
    flete_neto: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    costos_variables: Decimal | None = Field(
        default=None, ge=0, max_digits=14, decimal_places=2
    )
    dias_pago: int = Field(default=30, ge=0, le=365)
    retorno: str = Field(default="vacio_cercano")
    riesgo_puntos: int = Field(default=0, ge=0, le=10)

    @field_validator("retorno")
    @classmethod
    def validar_retorno(cls, valor: str):
        if valor not in {
            "cargado_completo",
            "parcial",
            "vacio_cercano",
            "vacio_sin_alternativa",
            "no_aplica",
        }:
            raise ValueError("retorno no válido")
        return valor


class ComponenteFreightScoreOut(BaseModel):
    codigo: str
    nombre: str
    score: Decimal
    peso: Decimal
    aporte: Decimal
    detalle: str


class ResultadoRentabilidadOut(BaseModel):
    ingreso_total: Decimal
    costo_variable: Decimal
    costo_fijo_asignado: Decimal
    costo_total: Decimal
    margen: Decimal
    margen_pct: Decimal
    margen_km: Decimal | None = None
    km_totales: Decimal
    tarifa_piso_estrategica: Decimal
    tarifa_piso_tactica: Decimal
    score: Decimal
    semaforo: str
    componentes: list[ComponenteFreightScoreOut]
    explicacion: list[str] = Field(default_factory=list)
    margen_objetivo: Decimal
    benchmark_margen_km: Decimal
    configurado: bool = False


class RentabilidadViajeOut(ResultadoRentabilidadOut):
    viaje_id: UUID
    numero_viaje: str
    fuente_costos: str  # real | estandar
    cliente_nombre: str
    distancia_km: Decimal | None = None
    km_vacios: Decimal | None = None


# ---------------------------------------------------------------------------
# P0-10 Facturación y cobranza
# ---------------------------------------------------------------------------
class FacturaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cliente_id: UUID
    orden_compra_id: UUID | None = None
    viaje_ids: list[UUID] = Field(min_length=1)
    fecha_emision: date = Field(default_factory=date.today)
    fecha_vencimiento: date
    tasa_iva: Decimal = Field(default=Decimal("0.19"), ge=0, le=1, max_digits=5, decimal_places=4)
    observaciones: str | None = None

    @model_validator(mode="after")
    def validar_fechas(self):
        if self.fecha_vencimiento < self.fecha_emision:
            raise ValueError("La fecha de vencimiento no puede ser anterior a la emisión")
        if len(set(self.viaje_ids)) != len(self.viaje_ids):
            raise ValueError("No se puede repetir un viaje en la misma factura")
        return self


class FacturaViajeOut(BaseModel):
    viaje_id: UUID
    numero_viaje: str
    estado: EstadoViaje
    monto: Decimal
    fecha_inicio: datetime | None = None


class ViajeFacturableOut(BaseModel):
    viaje_id: UUID
    numero_viaje: str
    cliente_id: UUID
    cliente_nombre: str
    orden_compra_id: UUID | None = None
    oc_numero: str | None = None
    fecha_inicio: datetime
    monto: Decimal
    tiene_pod: bool


class PagoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fecha: date = Field(default_factory=date.today)
    monto: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    metodo: str = Field(default="transferencia")
    referencia: str | None = Field(default=None, max_length=200)
    observaciones: str | None = None

    @field_validator("metodo")
    @classmethod
    def validar_metodo(cls, valor: str):
        if valor not in {
            "transferencia",
            "cheque",
            "efectivo",
            "tarjeta",
            "condonacion",
            "otro",
        }:
            raise ValueError("método de pago no válido")
        return valor


class PagoOut(BaseModel):
    id: UUID
    factura_id: UUID
    fecha: date
    monto: Decimal
    metodo: str
    referencia: str | None = None
    observaciones: str | None = None
    created_at: datetime
    created_by: str


class NotaCreditoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fecha: date = Field(default_factory=date.today)
    monto: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    motivo: str = Field(min_length=5, max_length=500)


class NotaCreditoOut(BaseModel):
    id: UUID
    factura_id: UUID
    numero: str
    fecha: date
    monto: Decimal
    motivo: str
    estado: str
    created_at: datetime


class PromesaPagoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fecha_prometida: date
    monto: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    notas: str | None = Field(default=None, max_length=500)


class PromesaPagoOut(BaseModel):
    id: UUID
    factura_id: UUID
    fecha_prometida: date
    monto: Decimal
    estado: str
    notas: str | None = None
    created_at: datetime


class FacturaResumenOut(BaseModel):
    id: UUID
    numero_factura: str
    cliente_id: UUID
    cliente_nombre: str
    orden_compra_id: UUID | None = None
    oc_numero: str | None = None
    fecha_emision: date
    fecha_vencimiento: date
    moneda: str
    neto: Decimal
    iva: Decimal
    total: Decimal
    pagado: Decimal
    notas_credito: Decimal
    saldo: Decimal
    estado: str
    dias_atraso: int
    aging: str
    viajes_count: int
    version: int


class FacturaOut(FacturaResumenOut):
    observaciones: str | None = None
    viajes: list[FacturaViajeOut] = Field(default_factory=list)
    pagos: list[PagoOut] = Field(default_factory=list)
    notas: list[NotaCreditoOut] = Field(default_factory=list)
    promesas: list[PromesaPagoOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AgingBucketOut(BaseModel):
    etiqueta: str
    facturas: int
    monto: Decimal


class AgingOut(BaseModel):
    total_cxc: Decimal
    total_vencido: Decimal
    facturas_abiertas: int
    buckets: list[AgingBucketOut]
    mensaje: str


# ---------------------------------------------------------------------------
# P0-11 Alertas y tablero del dueño
# ---------------------------------------------------------------------------
class AlertaOut(BaseModel):
    id: str
    categoria: str
    severidad: str
    titulo: str
    detalle: str
    accion: str
    link: str
    entidad_tipo: str | None = None
    entidad_id: str | None = None
    fecha_referencia: str | None = None


class TableroKpisOut(BaseModel):
    cxc_total: Decimal
    cxc_vencido: Decimal
    caja_operativa: Decimal
    viajes_activos: int
    tractos_activos: int
    tractos_disponibles: int
    oc_con_alerta: int
    documentos_por_vencer: int
    mantenciones_proximas: int
    viajes_sin_pod: int
    viajes_sin_facturar: int
    freight_score_promedio: Decimal | None = None
    alertas_criticas: int
    alertas_altas: int
    alertas_medias: int


class AccionTableroOut(BaseModel):
    titulo: str
    descripcion: str
    link: str
    prioridad: str


class TableroOut(BaseModel):
    generado_en: datetime
    zona_horaria: str
    kpis: TableroKpisOut
    salud: dict[str, int]
    alertas: list[AlertaOut]
    briefing: list[str]
    acciones: list[AccionTableroOut]
    aging: AgingOut


# ---------------------------------------------------------------------------
# P0-12 Roles, permisos y auditoría
# ---------------------------------------------------------------------------
class PermisoRolOut(BaseModel):
    rol: RolEmpresa
    permisos: list[str]


class MatrizPermisosOut(BaseModel):
    roles: list[PermisoRolOut]
    permisos: list[str]


class MisPermisosOut(BaseModel):
    rol: RolEmpresa
    permisos: list[str]
    empresa_id: UUID


class PaginaAuditoriaOut(BaseModel):
    items: list[HistorialCambioOut]
    total: int
    limit: int
    offset: int
    hay_mas: bool


class TablaAuditoriaOut(BaseModel):
    tabla: str
    total: int


# ---------------------------------------------------------------------------
# P0-13 Cutover
# ---------------------------------------------------------------------------
class CutoverEstadoOut(BaseModel):
    legacy_escritura_congelada: bool
    congelada_en: datetime | None = None
    congelada_por: str | None = None
    motivo: str | None = None
    updated_at: datetime | None = None
    legacy_viajes_abiertos: int = 0
    nucleo_viajes: int = 0
    mensaje: str


class CutoverAccion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo: str = Field(min_length=5, max_length=500)


class ErrorOut(BaseModel):
    codigo: str
    mensaje: str
    contexto: dict[str, Any] = Field(default_factory=dict)
    errores: list[dict[str, Any]] = Field(default_factory=list)
