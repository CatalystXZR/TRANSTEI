"""Reglas de negocio aprobadas R-01 (comisión) y R-02 (licencia) — TDD selectivo.

Estas pruebas describen el comportamiento aprobado por el dueño. Ambas reglas
están implementadas y la suite se ejecutó contra PostgreSQL local el 2026-10-29
(11 passed, `qa`); el docstring de cada prueba registra qué se verificó.

R-01 — comisión del chofer
    La comisión es el **10 % de la producción facturada del mes** del chofer. El
    porcentaje es configurable por chofer y vale 10 % por defecto. El mes se
    atribuye por la **fecha de emisión de la primera factura no anulada** del
    viaje (decisión del dueño, 2026-10-29, opción (a) del hallazgo SEC-001), no
    por la fecha del viaje. Un viaje solo `finalizado` no genera comisión.
    Fallback declarado: un viaje marcado `facturado` **sin** factura asociada
    (dato inconsistente) se atribuye por `coalesce(fecha_fin, fecha_inicio)`.

R-02 — licencia de conducir
    Única clase válida **A5**; clase distinta o ausente → **bloqueo**. Licencia
    **vencida → bloqueo**. Licencia que vence **entre 14 y 1 días → advertencia**
    (no bloquea). Ventana de aviso por defecto **14 días**.

Estado verificado (2026-10-29, ejecutado por `qa` contra PostgreSQL local):

* R-01 — `backend/app/api/routes/liquidaciones.py:51-96` (`_comision_chofer`)
  atribuye cada viaje a la primera `facturas.fecha_emision` **no anulada**
  (`:66-75`) y solo entonces acota al rango `[inicio, fin)` del mes (`:82`); el
  fallback por fecha del viaje aplica únicamente a viajes `facturado` sin
  factura asociada (`:85-91`). El default del porcentaje es 10 %
  (`backend/app/models/__init__.py:103`).
* R-02 — `backend/app/nucleo/politicas.py:297-322` emite
  `LICENCIA_NO_AUTORIZADA` / `LICENCIA_FALTANTE` con `bloqueante=True`, y
  `Empresa.dias_alerta_documentos` tiene default 14
  (`backend/app/nucleo/models.py:222`). La migración
  `supabase/migrations/0016_licencia_a5_bloqueante.sql` está aplicada: la base
  rechaza con 23514 ("Licencia A5 requerida (R-02)") todo viaje con chofer de
  clase distinta o ausente (observado al ejecutar fixtures sin clase).

Aislamiento y determinismo
--------------------------
Cada prueba abre su propia conexión, escribe dentro de una transacción y la
**revierte siempre** al terminar (`join_transaction_mode="create_savepoint"`).
No deja datos en la base, no usa datos de seed ni de otras pruebas y no depende
del orden de ejecución. Las fechas se derivan del reloj del sistema
(`date.today()` para el esquema legacy) o del reloj del núcleo
(`ahora_utc()` + zona de la empresa): no hay meses, años ni vencimientos fijos.

Nivel: integración con PostgreSQL real (no hay `mock` de la capa bajo prueba).
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlmodel import Session, create_engine, select

from app.api.routes.facturas import cambiar_estado_factura, crear_factura
from app.api.routes.liquidaciones import calcular_liquidacion
from app.core.config import settings
from app.models import (
    Chofer as ChoferLegacy,
    Cliente as ClienteLegacy,
    EstadoFactura,
    EstadoViaje as EstadoViajeLegacy,
    Factura,
    FacturaViaje,
    Rampla as RamplaLegacy,
    Tracto as TractoLegacy,
    Viaje as ViajeLegacy,
)
from app.nucleo.deps import ContextoEmpresa, RolEmpresa
from app.nucleo.errores import ConflictoDisponibilidad
from app.nucleo.models import (
    Chofer as ChoferNucleo,
    Cliente as ClienteNucleo,
    Documento,
    Empresa,
    EstadoViaje as EstadoViajeNucleo,
    ModalidadTarifa,
    OrdenCompra,
    Rampla as RamplaNucleo,
    Tarifa,
    TipoDocumento,
    TipoRampla,
    TipoRecurso,
    Tracto as TractoNucleo,
    Viaje as ViajeNucleo,
)
from app.nucleo.schemas import SolicitudAsignacion
from app.nucleo.servicio_disponibilidad import ServicioDisponibilidad
from app.nucleo.tiempo import ahora_utc, fecha_local
from app.schemas.facturas import FacturaCreate, FacturaEstadoUpdate

pytestmark = pytest.mark.integracion

MES_ACTUAL = "%Y-%m"


# ---------------------------------------------------------------------------
# Infraestructura de aislamiento
# ---------------------------------------------------------------------------
@pytest.fixture
def sesion_aislada():
    """Sesión sobre una transacción que **siempre** se revierte.

    `join_transaction_mode="create_savepoint"` hace que los `commit()` de la
    capa de producción liberen solo un SAVEPOINT: nada llega a la base. Un
    `rollback()` interno (por ejemplo el que ejecuta `confirmar_asignacion`
    cuando bloquea) tampoco destruye los datos de la prueba.
    """
    if not settings.DATABASE_URL:
        pytest.skip(
            "Sin DATABASE_URL: R-01 y R-02 requieren PostgreSQL. "
            "No se aprueban: quedan como no verificadas."
        )

    motor = create_engine(settings.DATABASE_URL, future=True)
    conexion = motor.connect()
    transaccion = conexion.begin()
    sesion = Session(bind=conexion, join_transaction_mode="create_savepoint")
    try:
        yield sesion
    finally:
        # La reversión de la transacción externa es la limpieza: no se borra
        # nada con DELETE (los triggers append-only lo impedirían) ni se dejan
        # filas de prueba.
        with contextlib.suppress(Exception):
            sesion.close()
        with contextlib.suppress(Exception):
            transaccion.rollback()
        with contextlib.suppress(Exception):
            conexion.close()
        motor.dispose()


def _mes_de(dia: date) -> str:
    return dia.strftime(MES_ACTUAL)


# ---------------------------------------------------------------------------
# Datos de prueba — legacy (`public`)
# ---------------------------------------------------------------------------
def _entorno_legacy(
    sesion: Session,
    etiqueta: str,
    *,
    porcentaje: Decimal | None = Decimal("0.10"),
) -> dict:
    """Cliente/chofer/tracto/rampla de prueba con identificadores únicos."""
    sufijo = uuid.uuid4().hex[:8].upper()
    cliente = ClienteLegacy(
        razon_social=f"Cliente QA {etiqueta}", rut=f"{etiqueta}-CLI-{sufijo}"
    )
    datos_chofer = {
        "nombre": f"Chofer QA {etiqueta}",
        "rut": f"{etiqueta}-CHO-{sufijo}",
        "sueldo_base": Decimal("400000"),
    }
    if porcentaje is not None:
        datos_chofer["porcentaje_produccion"] = porcentaje
    chofer = ChoferLegacy(**datos_chofer)
    tracto = TractoLegacy(patente=f"{etiqueta}-T{sufijo}")
    rampla = RamplaLegacy(patente=f"{etiqueta}-R{sufijo}")

    sesion.add_all([cliente, chofer, tracto, rampla])
    sesion.commit()
    for objeto in (cliente, chofer, tracto, rampla):
        sesion.refresh(objeto)

    return {
        "cliente": cliente,
        "chofer": chofer,
        "tracto": tracto,
        "rampla": rampla,
    }


def _viaje_legacy(
    sesion: Session,
    entorno: dict,
    *,
    valor: Decimal,
    estado: EstadoViajeLegacy,
    hoy: date,
) -> ViajeLegacy:
    """Viaje legacy con `fecha_fin` en el mes de `hoy`.

    `fecha_fin` se fija a `hoy` (una sola lectura del reloj por prueba). Ojo: la
    fecha del viaje **no** decide el mes de la comisión cuando el viaje tiene
    factura; la atribución es por `facturas.fecha_emision` (R-01/SEC-001). Solo
    se usa como fallback cuando el viaje está `facturado` sin factura asociada.
    """
    viaje = ViajeLegacy(
        fecha_inicio=hoy,
        fecha_fin=hoy,
        origen="Santiago",
        destino="Concepción",
        valor_flete_neto=valor,
        estado=estado,
        cliente_id=entorno["cliente"].id,
        chofer_id=entorno["chofer"].id,
        tracto_id=entorno["tracto"].id,
        rampla_id=entorno["rampla"].id,
    )
    sesion.add(viaje)
    sesion.commit()
    sesion.refresh(viaje)
    return viaje


def _liquidar(sesion: Session, entorno: dict, mes: str):
    """Ejecuta el cálculo real de liquidación para el mes indicado."""
    return calcular_liquidacion(
        chofer_id=entorno["chofer"].id,
        mes=mes,
        notas=None,
        session=sesion,
        _=None,
    )


def _facturar(sesion: Session, entorno: dict, viajes: list[ViajeLegacy], etiqueta: str):
    """Factura los viajes por la vía real: la factura los marca `facturado`."""
    return crear_factura(
        FacturaCreate(
            numero_sii=f"{etiqueta}-{uuid.uuid4().hex[:6].upper()}",
            cliente_id=str(entorno["cliente"].id),
            viaje_ids=[str(v.id) for v in viajes],
        ),
        session=sesion,
        _=None,
    )


def _fijar_fecha_emision(sesion: Session, factura_id: str, fecha: date) -> None:
    """Mueve la `fecha_emision` de una factura ya creada por `_facturar`.

    `crear_factura` estampa `date.today()` cuando el cuerpo no la indica
    (`backend/app/api/routes/facturas.py:144`). La regla R-01 atribuye el mes por
    esa fecha (SEC-001), así que la prueba necesita controlarla. Se ajusta por
    ORM **después** del alta para no alterar el camino de producción que se está
    midiendo.
    """
    factura = sesion.get(Factura, UUID(factura_id))
    assert factura is not None, (
        f"La factura {factura_id} debería existir después de facturar."
    )
    factura.fecha_emision = fecha
    sesion.add(factura)
    sesion.commit()
    sesion.refresh(factura)


# ---------------------------------------------------------------------------
# Datos de prueba — núcleo (`nucleo`)
# ---------------------------------------------------------------------------
def _entorno_nucleo(
    sesion: Session,
    etiqueta: str,
    *,
    licencia_clase: str | None = "A5",
    dias_para_vencer_licencia: int = 365,
    dias_alerta_documentos: int | None = None,
) -> dict:
    """Empresa completa del núcleo, aislada y con un viaje `confirmado` listo.

    Todos los documentos quedan vigentes salvo la licencia del chofer, que se
    vence según `dias_para_vencer_licencia` (negativo = ya vencida). El viaje se
    planifica a 3 días para que `dias_margen_documentos = 0` no convierta un
    documento "por vencer" en "insuficiente".
    """
    sufijo = uuid.uuid4().hex[:8].upper()

    datos_empresa = {
        "codigo": f"QA-{sufijo}",
        "razon_social": f"Empresa QA {etiqueta}",
        "rut": f"QA-{sufijo}",
    }
    if dias_alerta_documentos is not None:
        datos_empresa["dias_alerta_documentos"] = dias_alerta_documentos
    empresa = Empresa(**datos_empresa)
    sesion.add(empresa)
    sesion.commit()

    cliente = ClienteNucleo(
        empresa_id=empresa.id,
        razon_social=f"Cliente QA {etiqueta}",
        rut=f"CLI-{sufijo}",
    )
    tracto = TractoNucleo(
        empresa_id=empresa.id,
        patente=f"T{sufijo[:6]}",
        peso_bruto_kg=Decimal("39000"),
        tara_kg=Decimal("9000"),
        capacidad_carga_kg=Decimal("30000"),
        # La clase permitida del tracto es A5: la regla R-02 no debe depender
        # de que este arreglo venga vacío.
        licencias_permitidas=["A5"],
    )
    rampla = RamplaNucleo(
        empresa_id=empresa.id,
        patente=f"R{sufijo[:6]}",
        tipo=TipoRampla.plana,
        capacidad_carga_kg=Decimal("30000"),
        volumen_m3=Decimal("80"),
    )
    chofer = ChoferNucleo(
        empresa_id=empresa.id,
        rut=f"CHO-{sufijo}",
        nombre=f"Chofer QA {etiqueta}",
        numero_licencia=f"LIC-{sufijo}",
        licencia_clase=licencia_clase,
    )
    sesion.add_all([cliente, tracto, rampla, chofer])
    sesion.commit()

    # Se usa el mismo reloj y la misma zona que el servicio (`ahora_utc` +
    # `zona_horaria` de la empresa) para que `dias_restantes` no dependa de la
    # zona horaria del proceso que ejecuta la prueba.
    hoy = fecha_local(ahora_utc(), empresa.zona_horaria)
    vence_lejos = hoy + timedelta(days=365)
    docs = [
        Documento(
            empresa_id=empresa.id,
            recurso_tipo=TipoRecurso.tracto,
            tracto_id=tracto.id,
            tipo=TipoDocumento.revision_tecnica,
            vence_en=vence_lejos,
        ),
        Documento(
            empresa_id=empresa.id,
            recurso_tipo=TipoRecurso.tracto,
            tracto_id=tracto.id,
            tipo=TipoDocumento.permiso_circulacion,
            vence_en=vence_lejos,
        ),
        Documento(
            empresa_id=empresa.id,
            recurso_tipo=TipoRecurso.tracto,
            tracto_id=tracto.id,
            tipo=TipoDocumento.seguro_obligatorio,
            vence_en=vence_lejos,
        ),
        Documento(
            empresa_id=empresa.id,
            recurso_tipo=TipoRecurso.tracto,
            tracto_id=tracto.id,
            tipo=TipoDocumento.soap,
            vence_en=vence_lejos,
        ),
        Documento(
            empresa_id=empresa.id,
            recurso_tipo=TipoRecurso.rampla,
            rampla_id=rampla.id,
            tipo=TipoDocumento.revision_tecnica,
            vence_en=vence_lejos,
        ),
        Documento(
            empresa_id=empresa.id,
            recurso_tipo=TipoRecurso.rampla,
            rampla_id=rampla.id,
            tipo=TipoDocumento.permiso_circulacion,
            vence_en=vence_lejos,
        ),
        Documento(
            empresa_id=empresa.id,
            recurso_tipo=TipoRecurso.rampla,
            rampla_id=rampla.id,
            tipo=TipoDocumento.seguro_carga,
            vence_en=vence_lejos,
        ),
        Documento(
            empresa_id=empresa.id,
            recurso_tipo=TipoRecurso.chofer,
            chofer_id=chofer.id,
            tipo=TipoDocumento.licencia_conducir,
            vence_en=hoy + timedelta(days=dias_para_vencer_licencia),
        ),
        Documento(
            empresa_id=empresa.id,
            recurso_tipo=TipoRecurso.chofer,
            chofer_id=chofer.id,
            tipo=TipoDocumento.examen_medico,
            vence_en=vence_lejos,
        ),
    ]
    tarifa = Tarifa(
        empresa_id=empresa.id,
        cliente_id=cliente.id,
        codigo=f"T-{sufijo}",
        nombre="Ruta QA",
        modalidad=ModalidadTarifa.viaje,
        vigencia_desde=hoy,
        vigencia_hasta=hoy + timedelta(days=365),
        precio_unitario=Decimal("100000"),
    )
    oc = OrdenCompra(
        empresa_id=empresa.id,
        cliente_id=cliente.id,
        numero_oc=f"OC-{sufijo}",
        vigencia_desde=hoy,
        vigencia_hasta=hoy + timedelta(days=365),
        monto_autorizado=Decimal("1000000"),
    )
    sesion.add_all(docs + [tarifa, oc])
    sesion.commit()

    inicio = ahora_utc().replace(microsecond=0) + timedelta(days=3)
    fin = inicio + timedelta(hours=4)
    viaje = ViajeNucleo(
        empresa_id=empresa.id,
        numero_viaje=f"QA-{sufijo}",
        cliente_id=cliente.id,
        orden_compra_id=oc.id,
        tarifa_id=tarifa.id,
        estado=EstadoViajeNucleo.confirmado,
        inicio_planificado=inicio,
        fin_planificado=fin,
        buffer_minutos=60,
        peso_bruto_kg=Decimal("25000"),
        origen_nombre="Santiago",
        destino_nombre="Concepción",
        valor_flete_neto=Decimal("100000"),
    )
    sesion.add(viaje)
    sesion.commit()
    sesion.refresh(viaje)

    contexto = ContextoEmpresa(
        auth_id=str(uuid.uuid4()), empresa=empresa, rol=RolEmpresa.admin
    )
    servicio = ServicioDisponibilidad(sesion, contexto)
    propuesta = SolicitudAsignacion(
        tracto_id=tracto.id,
        rampla_id=rampla.id,
        chofer_id=chofer.id,
        inicio_planificado=inicio,
        fin_planificado=fin,
    )
    return {
        "empresa": empresa,
        "cliente": cliente,
        "tracto": tracto,
        "rampla": rampla,
        "chofer": chofer,
        "viaje": viaje,
        "servicio": servicio,
        "propuesta": propuesta,
    }


def _licencia_de(preview, recurso_id) -> object:
    """Extrae el `DocumentoOut` de la licencia de conducir del chofer."""
    for documento in preview.documentos:
        if (
            documento.recurso_tipo == TipoRecurso.chofer
            and documento.recurso_id == recurso_id
            and documento.tipo == TipoDocumento.licencia_conducir.value
        ):
            return documento
    raise AssertionError(
        "La validación no devolvió el documento de licencia del chofer: "
        f"{[d.model_dump() for d in preview.documentos]}"
    )


def _codigos(items) -> list[str]:
    return [getattr(item, "codigo", None) or item.get("codigo") for item in items]


# ===========================================================================
# R-01 — comisión = 10 % de la facturación del mes
# ===========================================================================
def test_r01_viaje_finalizado_no_facturado_no_genera_comision(
    sesion_aislada, etiqueta
):
    """R-01: un viaje solo `finalizado` NO genera comisión.

    Verde al escribir la prueba (2026-10-29): `_comision_chofer` ya filtra
    `EstadoViaje.facturado` en el árbol de trabajo
    (`backend/app/api/routes/liquidaciones.py:45-61`). Queda como guarda de
    regresión frente a la implementación heredada que sumaba `finalizado`.
    """
    entorno = _entorno_legacy(sesion_aislada, etiqueta)
    hoy = date.today()
    _viaje_legacy(
        sesion_aislada,
        entorno,
        valor=Decimal("1800000"),
        estado=EstadoViajeLegacy.finalizado,
        hoy=hoy,
    )

    liquidacion = _liquidar(sesion_aislada, entorno, _mes_de(hoy))

    assert liquidacion.comision == Decimal("0"), (
        "Un viaje solo finalizado (no facturado) no puede generar comisión. "
        f"Esperado 0, obtenido {liquidacion.comision} sobre un viaje de 1.800.000."
    )
    assert liquidacion.total_liquido == Decimal("400000"), (
        "El total líquido debe ser solo el sueldo base (400.000) cuando no hay "
        f"facturación; obtenido {liquidacion.total_liquido}."
    )


def test_r01_viaje_facturado_genera_comision_del_10_por_ciento(
    sesion_aislada, etiqueta
):
    """R-01: el mismo viaje, ya facturado, suma 10 % de 1.800.000 = 180.000.

    Hoy pasa (la implementación vigente también suma facturados); queda como
    guarda de regresión: si alguien excluye `facturado` de la base, esta prueba
    se rompe.
    """
    entorno = _entorno_legacy(sesion_aislada, etiqueta)
    hoy = date.today()
    viaje = _viaje_legacy(
        sesion_aislada,
        entorno,
        valor=Decimal("1800000"),
        estado=EstadoViajeLegacy.finalizado,
        hoy=hoy,
    )

    _facturar(sesion_aislada, entorno, [viaje], etiqueta)
    sesion_aislada.refresh(viaje)
    assert viaje.estado == EstadoViajeLegacy.facturado, (
        "La facturación debe marcar el viaje como facturado; "
        f"estado obtenido: {viaje.estado}"
    )

    liquidacion = _liquidar(sesion_aislada, entorno, _mes_de(hoy))

    # Aritmética: 1.800.000 × 0,10 = 180.000.
    assert liquidacion.comision == Decimal("180000"), (
        "10 % sobre 1.800.000 facturados debe ser 180.000; "
        f"obtenido {liquidacion.comision}."
    )
    assert liquidacion.total_liquido == Decimal("580000"), (
        "400.000 de sueldo base + 180.000 de comisión = 580.000; "
        f"obtenido {liquidacion.total_liquido}."
    )


def test_r01_comision_suma_solo_viajes_facturados_del_mes(
    sesion_aislada, etiqueta
):
    """R-01: con facturación parcial, la comisión solo cuenta lo facturado.

    1.000.000 facturado + 800.000 solo finalizado → 10 % de 1.000.000 =
    100.000 (no 180.000).

    Verde al escribir la prueba (2026-10-29) porque `_comision_chofer` ya
    filtra `EstadoViaje.facturado`; si vuelve a sumar `finalizado`, esta
    prueba lo detecta con una diferencia exacta de 80.000.
    """
    entorno = _entorno_legacy(sesion_aislada, etiqueta)
    hoy = date.today()
    facturado = _viaje_legacy(
        sesion_aislada,
        entorno,
        valor=Decimal("1000000"),
        estado=EstadoViajeLegacy.finalizado,
        hoy=hoy,
    )
    solo_finalizado = _viaje_legacy(
        sesion_aislada,
        entorno,
        valor=Decimal("800000"),
        estado=EstadoViajeLegacy.finalizado,
        hoy=hoy,
    )

    _facturar(sesion_aislada, entorno, [facturado], etiqueta)
    sesion_aislada.refresh(facturado)
    sesion_aislada.refresh(solo_finalizado)
    assert facturado.estado == EstadoViajeLegacy.facturado
    assert solo_finalizado.estado == EstadoViajeLegacy.finalizado

    liquidacion = _liquidar(sesion_aislada, entorno, _mes_de(hoy))

    assert liquidacion.comision == Decimal("100000"), (
        "Solo el viaje facturado (1.000.000) entra a la base: 10 % = 100.000. "
        f"Obtenido {liquidacion.comision} (¿se está sumando el viaje solo "
        "finalizado de 800.000?)."
    )


def test_r01_comision_no_incluye_facturacion_de_otro_mes(
    sesion_aislada, etiqueta
):
    """R-01: la base es la facturación **del mes**, atribuida por emisión.

    Dos viajes, cada uno con su factura: la del mes anterior se emitió el mes
    anterior y la del mes corriente, hoy. Aritmética: mes anterior 1.800.000
    (fuera) + mes corriente 900.000 → 10 % de 900.000 = 90.000, no 270.000.

    Guarda de regresión: si se quita el acotado `[inicio, fin)` sobre
    `facturas.fecha_emision`, la historia de meses anteriores se suma.
    """
    entorno = _entorno_legacy(sesion_aislada, etiqueta)
    hoy = date.today()
    # Mes anterior derivado del reloj: primer día del mes actual menos 1 día.
    mes_anterior = hoy.replace(day=1) - timedelta(days=1)
    assert _mes_de(mes_anterior) != _mes_de(hoy), (
        "La fecha derivada debe caer en un mes distinto al corriente; "
        f"mes_anterior={_mes_de(mes_anterior)}, actual={_mes_de(hoy)}."
    )

    viaje_mes_anterior = _viaje_legacy(
        sesion_aislada,
        entorno,
        valor=Decimal("1800000"),
        estado=EstadoViajeLegacy.finalizado,
        hoy=mes_anterior,
    )
    viaje_mes_actual = _viaje_legacy(
        sesion_aislada,
        entorno,
        valor=Decimal("900000"),
        estado=EstadoViajeLegacy.finalizado,
        hoy=hoy,
    )

    # Cada factura en su mes: la fecha de emisión es lo que atribuye el período.
    factura_anterior = _facturar(
        sesion_aislada, entorno, [viaje_mes_anterior], etiqueta
    )
    _fijar_fecha_emision(sesion_aislada, factura_anterior.id, mes_anterior)
    factura_actual = _facturar(sesion_aislada, entorno, [viaje_mes_actual], etiqueta)
    _fijar_fecha_emision(sesion_aislada, factura_actual.id, hoy)

    sesion_aislada.refresh(viaje_mes_anterior)
    sesion_aislada.refresh(viaje_mes_actual)
    assert viaje_mes_anterior.estado == EstadoViajeLegacy.facturado
    assert viaje_mes_actual.estado == EstadoViajeLegacy.facturado

    liquidacion = _liquidar(sesion_aislada, entorno, _mes_de(hoy))

    assert liquidacion.comision == Decimal("90000"), (
        "Solo la facturación emitida en el mes corriente (900.000) entra a la "
        f"base: 10 % = 90.000. Obtenido {liquidacion.comision} "
        "(¿se está sumando la factura emitida el mes anterior?)."
    )

    liquidacion_anterior = _liquidar(
        sesion_aislada, entorno, _mes_de(mes_anterior)
    )
    assert liquidacion_anterior.comision == Decimal("180000"), (
        "La factura emitida el mes anterior debe devengar en ese mes: "
        f"10 % de 1.800.000 = 180.000. Obtenido {liquidacion_anterior.comision}."
    )


def test_r01_comision_se_atribuye_al_mes_de_emision_de_la_factura(
    sesion_aislada, etiqueta
):
    """R-01/SEC-001: un viaje finalizado en el mes anterior pero facturado hoy
    devenga en el mes de la **factura**, no en el del viaje.

    Es el caso que perdía dinero: antes se imputaba por `fecha_fin`, así que la
    liquidación del mes anterior (ya emitida, no recalculable) lo dejaba fuera y
    la del mes corriente tampoco lo veía.
    """
    entorno = _entorno_legacy(sesion_aislada, etiqueta)
    hoy = date.today()
    mes_anterior = hoy.replace(day=1) - timedelta(days=1)
    assert _mes_de(mes_anterior) != _mes_de(hoy)

    viaje = _viaje_legacy(
        sesion_aislada,
        entorno,
        valor=Decimal("1800000"),
        estado=EstadoViajeLegacy.finalizado,
        hoy=mes_anterior,
    )
    # `_facturar` emite con `date.today()`: el viaje se factura hoy.
    _facturar(sesion_aislada, entorno, [viaje], etiqueta)
    sesion_aislada.refresh(viaje)
    assert viaje.estado == EstadoViajeLegacy.facturado

    liquidacion_hoy = _liquidar(sesion_aislada, entorno, _mes_de(hoy))
    liquidacion_anterior = _liquidar(
        sesion_aislada, entorno, _mes_de(mes_anterior)
    )

    assert liquidacion_hoy.comision == Decimal("180000"), (
        "El viaje facturado hoy debe devengar en el mes corriente: 10 % de "
        f"1.800.000 = 180.000. Obtenido {liquidacion_hoy.comision}."
    )
    assert liquidacion_anterior.comision == Decimal("0"), (
        "El mes anterior no debe devengar por un viaje facturado este mes. "
        f"Obtenido {liquidacion_anterior.comision}."
    )


def test_r01_factura_anulada_no_genera_comision(sesion_aislada, etiqueta):
    """R-01: una factura anulada no es facturación; el viaje no devenga.

    `cambiar_estado_factura` al anular desvincula el viaje y lo devuelve a
    `finalizado`, así que tampoco aplica el fallback por fecha del viaje.
    """
    entorno = _entorno_legacy(sesion_aislada, etiqueta)
    hoy = date.today()

    viaje = _viaje_legacy(
        sesion_aislada,
        entorno,
        valor=Decimal("1800000"),
        estado=EstadoViajeLegacy.finalizado,
        hoy=hoy,
    )
    factura = _facturar(sesion_aislada, entorno, [viaje], etiqueta)
    cambiar_estado_factura(
        UUID(factura.id),
        FacturaEstadoUpdate(estado=EstadoFactura.anulada),
        session=sesion_aislada,
        _=None,
    )
    sesion_aislada.refresh(viaje)

    liquidacion = _liquidar(sesion_aislada, entorno, _mes_de(hoy))

    assert liquidacion.comision == Decimal("0"), (
        "Una factura anulada no puede devengar comisión. "
        f"Obtenido {liquidacion.comision}."
    )
    assert liquidacion.total_liquido == Decimal("400000"), (
        "Sin comisión, el líquido es solo el sueldo base (400.000). "
        f"Obtenido {liquidacion.total_liquido}."
    )


def test_r01_viaje_facturado_sin_factura_usa_fecha_del_viaje(
    sesion_aislada, etiqueta
):
    """R-01, fallback declarado: `facturado` sin fila en `factura_viaje`.

    Es un dato inconsistente (el camino real siempre crea la factura), pero
    puede existir por una carga heredada o un `PATCH` de estado. Se atribuye por
    `coalesce(fecha_fin, fecha_inicio)` para no perder la comisión en silencio.
    """
    entorno = _entorno_legacy(sesion_aislada, etiqueta)
    hoy = date.today()

    viaje = _viaje_legacy(
        sesion_aislada,
        entorno,
        valor=Decimal("1800000"),
        estado=EstadoViajeLegacy.finalizado,
        hoy=hoy,
    )
    viaje.estado = EstadoViajeLegacy.facturado
    sesion_aislada.add(viaje)
    sesion_aislada.commit()

    vinculadas = sesion_aislada.exec(
        select(FacturaViaje).where(FacturaViaje.viaje_id == viaje.id)
    ).all()
    assert vinculadas == [], (
        "La prueba necesita un viaje facturado SIN factura vinculada; "
        f"encontró {len(vinculadas)} vínculo(s)."
    )

    liquidacion = _liquidar(sesion_aislada, entorno, _mes_de(hoy))

    assert liquidacion.comision == Decimal("180000"), (
        "El fallback debe atribuir el viaje a su propio mes: 10 % de 1.800.000 "
        f"= 180.000. Obtenido {liquidacion.comision}."
    )


def test_r01_porcentaje_de_comision_por_defecto_es_10_por_ciento(
    sesion_aislada, etiqueta
):
    """R-01: el porcentaje por chofer es configurable y vale 10 % por defecto.

    Se crea el chofer **sin** indicar `porcentaje_produccion`. Hoy el default es
    0 (`backend/app/models/__init__.py:102-104` y
    `backend/app/schemas/catalogos.py:33-35`), por lo que la comisión es 0.
    Verde cuando el valor por defecto del modelo/schema sea `Decimal("0.10")`.
    """
    entorno = _entorno_legacy(sesion_aislada, etiqueta, porcentaje=None)
    hoy = date.today()
    viaje = _viaje_legacy(
        sesion_aislada,
        entorno,
        valor=Decimal("1800000"),
        estado=EstadoViajeLegacy.finalizado,
        hoy=hoy,
    )
    _facturar(sesion_aislada, entorno, [viaje], etiqueta)

    assert entorno["chofer"].porcentaje_produccion == Decimal("0.10"), (
        "El porcentaje de comisión por defecto debe ser 10 % (0,10); "
        f"obtenido {entorno['chofer'].porcentaje_produccion}."
    )

    liquidacion = _liquidar(sesion_aislada, entorno, _mes_de(hoy))
    assert liquidacion.comision == Decimal("180000"), (
        "Con el porcentaje por defecto (10 %) sobre 1.800.000 facturados la "
        f"comisión debe ser 180.000; obtenido {liquidacion.comision}."
    )


# ===========================================================================
# R-02 — licencia: A5 obligatoria, vencida bloquea, por vencer advierte
# ===========================================================================
@pytest.mark.parametrize(
    "clase_licencia",
    ["A3", None],
    ids=["clase_distinta_a_a5", "clase_ausente"],
)
def test_r02a_chofer_sin_clase_a5_bloquea_asignacion(
    sesion_aislada, etiqueta, clase_licencia
):
    """R-02: clase distinta de A5 (o ausente) **bloquea** la asignación.

    Verificado (2026-10-29, `qa`, PostgreSQL local): `politicas.validar_carga`
    emite `LICENCIA_NO_AUTORIZADA` / `LICENCIA_FALTANTE` con
    `bloqueante=True` (`backend/app/nucleo/politicas.py:297-322`) y
    `ServicioDisponibilidad.validar_asignacion` los propaga a `incidencias`
    (`servicio_disponibilidad.py:1265-1274`), por lo que `apto` es `False` y
    `confirmar_asignacion` falla con `ConflictoDisponibilidad` (HTTP 409,
    `codigo="CONFLICTO_DISPONIBILIDAD"`, `errores` con el código `LICENCIA_*`).
    Si la incidencia vuelve a ser no bloqueante, esta prueba falla.

    La migración `supabase/migrations/0016_licencia_a5_bloqueante.sql` impone
    además el bloqueo en la base (23514). Esta prueba exige el bloqueo en el
    servicio: el usuario debe ver el motivo antes de confirmar y la API debe
    responder 409, no un error de integridad de PostgreSQL.
    """
    entorno = _entorno_nucleo(
        sesion_aislada, etiqueta, licencia_clase=clase_licencia
    )
    servicio = entorno["servicio"]

    preview = servicio.validar_asignacion(entorno["viaje"].id, entorno["propuesta"])

    bloqueos_licencia = [
        incidencia
        for incidencia in preview.incidencias
        if incidencia.codigo.startswith("LICENCIA_")
    ]
    assert bloqueos_licencia, (
        "La licencia no A5 debe ser un bloqueo (incidencia bloqueante con "
        f"código LICENCIA_*). Clase del chofer: {clase_licencia!r}. "
        f"Incidencias: {_codigos(preview.incidencias)}. "
        f"Advertencias: {_codigos(preview.advertencias)}."
    )
    assert all(i.bloqueante for i in bloqueos_licencia)
    assert preview.apto is False, (
        "Con una licencia no A5 la asignación no puede ser apta; "
        f"apto={preview.apto}."
    )

    with pytest.raises(ConflictoDisponibilidad) as excinfo:
        servicio.confirmar_asignacion(entorno["viaje"].id, entorno["propuesta"])

    error = excinfo.value
    assert error.status_code == 409, (
        f"El bloqueo de licencia debe responder 409; status={error.status_code}."
    )
    assert error.codigo == "CONFLICTO_DISPONIBILIDAD"
    assert any(
        str(codigo).startswith("LICENCIA_") for codigo in _codigos(error.errores)
    ), (
        "El error de bloqueo debe explicar que el motivo es la licencia; "
        f"errores={error.errores}."
    )


def test_r02b_chofer_a5_con_licencia_vencida_bloquea_asignacion(
    sesion_aislada, etiqueta
):
    """R-02: licencia A5 **vencida** → bloqueo.

    Hoy pasa: el documento vencido ya es un bloqueo duro
    (`backend/app/nucleo/servicio_disponibilidad.py:272-310` y
    `nucleo.validar_documentos_recurso`). Queda como guarda de regresión: la
    implementación de R-02 no puede degradar el vencimiento a advertencia.
    """
    entorno = _entorno_nucleo(
        sesion_aislada,
        etiqueta,
        licencia_clase="A5",
        dias_para_vencer_licencia=-1,
    )
    servicio = entorno["servicio"]

    preview = servicio.validar_asignacion(entorno["viaje"].id, entorno["propuesta"])

    vencidos = [
        incidencia
        for incidencia in preview.incidencias
        if incidencia.codigo == "DOCUMENTO_NO_VIGENTE"
        and incidencia.recurso_tipo == TipoRecurso.chofer
    ]
    assert vencidos, (
        "Una licencia vencida debe generar un bloqueo DOCUMENTO_NO_VIGENTE del "
        f"chofer. Incidencias: {_codigos(preview.incidencias)}."
    )
    assert preview.apto is False

    with pytest.raises(ConflictoDisponibilidad) as excinfo:
        servicio.confirmar_asignacion(entorno["viaje"].id, entorno["propuesta"])

    error = excinfo.value
    assert error.status_code == 409
    assert any(
        codigo == "DOCUMENTO_NO_VIGENTE" for codigo in _codigos(error.errores)
    ), f"errores={error.errores}"


def test_r02c_chofer_a5_con_licencia_por_vencer_no_bloquea_y_advierte(
    sesion_aislada, etiqueta
):
    """R-02: licencia que vence en 10 días → advierte pero **no** bloquea.

    Verificado (2026-10-29, `qa`): la ventana se fija explícitamente en 14 días
    y el documento se informa como `por_vencer`, no bloqueante. Queda como
    guarda: al endurecer R-02 no se puede bloquear una licencia todavía vigente.

    La advertencia observable del contrato actual es
    `DocumentoOut.estado == "por_vencer"` con `dias_restantes = 10`; no se exige
    una `IncidenciaOut` adicional para no fijar una forma de implementación.
    """
    entorno = _entorno_nucleo(
        sesion_aislada,
        etiqueta,
        licencia_clase="A5",
        dias_para_vencer_licencia=10,
        # La ventana se fija explícitamente para que esta prueba no dependa de
        # R-02d (default de 14 días): aquí se prueba la advertencia, no el default.
        dias_alerta_documentos=14,
    )
    servicio = entorno["servicio"]

    preview = servicio.validar_asignacion(entorno["viaje"].id, entorno["propuesta"])
    licencia = _licencia_de(preview, entorno["chofer"].id)

    assert licencia.estado == "por_vencer", (
        "Una licencia que vence en 10 días debe advertirse como 'por_vencer'; "
        f"estado obtenido: {licencia.estado!r}."
    )
    assert licencia.dias_restantes == 10
    assert licencia.bloqueante is False, (
        "Una licencia vigente (vence en 10 días) no puede ser bloqueante."
    )
    assert preview.apto is True, (
        "La advertencia de vencimiento próximo no debe impedir la asignación; "
        f"incidencias={_codigos(preview.incidencias)}."
    )

    resultado = servicio.confirmar_asignacion(
        entorno["viaje"].id, entorno["propuesta"]
    )
    assert resultado.estado == EstadoViajeNucleo.asignado, (
        "La asignación con licencia por vencer (no vencida) debe confirmarse; "
        f"estado obtenido: {resultado.estado}."
    )


def test_r02d_empresa_usa_ventana_de_aviso_de_14_dias_por_defecto(
    sesion_aislada, etiqueta
):
    """R-02: la ventana de aviso por defecto es **14 días**, no 30.

    Verificado (2026-10-29, `qa`): el default del modelo Python es 14
    (`backend/app/nucleo/models.py:222`), por lo que el INSERT del ORM ya no
    envía 30. El `alter column ... set default 14` de
    `supabase/migrations/0016_licencia_a5_bloqueante.sql` es necesario pero no
    suficiente: esta prueba detecta si el ORM vuelve a fijar 30.
    """
    sufijo = uuid.uuid4().hex[:8].upper()
    empresa = Empresa(
        codigo=f"QA-{sufijo}",
        razon_social=f"Empresa QA {etiqueta}",
        rut=f"QA-{sufijo}",
    )
    sesion_aislada.add(empresa)
    sesion_aislada.commit()
    sesion_aislada.refresh(empresa)

    assert empresa.dias_alerta_documentos == 14, (
        "La ventana de aviso de documentos por defecto debe ser 14 días; "
        f"obtenido {empresa.dias_alerta_documentos}."
    )


def test_r02d_licencia_a_20_dias_no_advierte_con_ventana_de_14_dias(
    sesion_aislada, etiqueta
):
    """R-02: con ventana de 14 días, una licencia a 20 días está **vigente**.

    Verificado (2026-10-29, `qa`): la empresa creada sin
    `dias_alerta_documentos` recibe 14 por el default del modelo
    (`backend/app/nucleo/models.py:222`). Con una ventana de 30 días la
    licencia se marcaría `por_vencer` (advertencia prematura); esta prueba
    detecta esa regresión.
    """
    entorno = _entorno_nucleo(
        sesion_aislada,
        etiqueta,
        licencia_clase="A5",
        dias_para_vencer_licencia=20,
    )

    preview = entorno["servicio"].validar_asignacion(
        entorno["viaje"].id, entorno["propuesta"]
    )
    licencia = _licencia_de(preview, entorno["chofer"].id)

    assert licencia.estado == "vigente", (
        "Con una ventana de aviso de 14 días, una licencia que vence en 20 días "
        f"debe estar 'vigente'; estado obtenido: {licencia.estado!r}."
    )
    assert licencia.bloqueante is False
