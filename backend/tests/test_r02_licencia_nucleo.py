"""R-02 — licencia de conducir en el **núcleo**: A5 obligatoria, vencida
bloquea, por vencer advierte (ventana por defecto 14 días).

Origen: estas pruebas vivían en `tests/test_reglas_negocio.py`, junto a las de
R-01. La Ola C (ADR-0002 §6.5, 2026-10-31) retiró el router legacy
`liquidaciones` —y con él la implementación legacy de R-01—, pero **R-02 nunca
fue legacy**: se ejercita sobre `nucleo.politicas` +
`nucleo.servicio_disponibilidad` (sin HTTP, sin `public`). Por eso se conserva
como archivo propio en vez de borrarse: retirar una prueba de una regla
bloqueante vigente sería perder cobertura, no retirar legacy.

R-02 (dueño, vía `docs/negocio/catalogo-reglas.md`):
    Única clase válida **A5**; clase distinta o ausente → **bloqueo**. Licencia
    **vencida → bloqueo**. Licencia que vence **entre 14 y 1 días → advertencia**
    (no bloquea). Ventana de aviso por defecto **14 días**.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlmodel import Session, create_engine

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
from rut_helpers import rut_empresa

pytestmark = pytest.mark.integracion


# ---------------------------------------------------------------------------
# Infraestructura de aislamiento
# ---------------------------------------------------------------------------
@pytest.fixture
def sesion_aislada(base_url_test):
    """Sesión sobre una transacción que **siempre** se revierte.

    `join_transaction_mode="create_savepoint"` hace que los `commit()` de la
    capa de producción liberen solo un SAVEPOINT: nada llega a la base. Un
    `rollback()` interno (por ejemplo el que ejecuta `confirmar_asignacion`
    cuando bloquea) tampoco destruye los datos de la prueba.

    La URL proviene del fixture `base_url_test` (conftest.py): la integración
    se omite si `NUCLEO_TEST_DATABASE_URL` no está definida o apunta a la base
    de la aplicación (RA-13).
    """
    motor = create_engine(base_url_test, future=True)
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
    `bloqueante=True` y `ServicioDisponibilidad.validar_asignacion` los propaga
    a `incidencias`, por lo que `apto` es `False` y `confirmar_asignacion` falla
    con `ConflictoDisponibilidad` (HTTP 409,
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

    El documento vencido ya es un bloqueo duro
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
        rut=rut_empresa(),
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
