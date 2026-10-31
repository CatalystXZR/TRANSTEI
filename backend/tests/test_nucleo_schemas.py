from uuid import uuid4

import pytest
from app.nucleo.schemas import SolicitudAsignacion, SolicitudValidacionAsignacion
from pydantic import ValidationError


def payload(**kwargs):
    base = dict(
        tracto_id=uuid4(),
        rampla_id=uuid4(),
        chofer_id=uuid4(),
        inicio_planificado="2026-11-01T08:00:00-03:00",
        fin_planificado="2026-11-01T12:00:00-03:00",
    )
    base.update(kwargs)
    return base


def test_solicitud_valida_acepta_offset():
    s = SolicitudAsignacion(**payload())
    assert s.inicio_planificado.utcoffset() is not None


def test_solicitud_rechaza_naive():
    with pytest.raises(ValidationError):
        SolicitudAsignacion(**payload(inicio_planificado="2026-11-01T08:00:00"))


def test_solicitud_rechaza_fin_antes_de_inicio():
    with pytest.raises(ValidationError):
        SolicitudAsignacion(**payload(fin_planificado="2026-11-01T07:00:00-03:00"))


def test_solicitud_rechaza_ventana_mayor_a_90_dias():
    with pytest.raises(ValidationError):
        SolicitudAsignacion(
            **payload(
                fin_planificado="2027-03-01T12:00:00-03:00",
            )
        )


def test_solicitud_rechaza_campos_extra():
    with pytest.raises(ValidationError):
        SolicitudAsignacion(**payload(empresa_id=str(uuid4())))


def test_solicitud_rechaza_traslado_absurdo():
    with pytest.raises(ValidationError):
        SolicitudAsignacion(**payload(minutos_traslado=1441))


def test_solicitud_validacion_exige_viaje_id():
    with pytest.raises(ValidationError):
        SolicitudValidacionAsignacion(**payload())

    s = SolicitudValidacionAsignacion(**payload(viaje_id=uuid4()))
    assert s.viaje_id is not None


# ---------------------------------------------------------------------------
# Ola B del retiro legacy: esquemas de mantenimiento y nómina
# ---------------------------------------------------------------------------
def test_pauta_solo_tracto_o_rampla_y_intervalo_positivo():
    from app.nucleo.schemas import PautaMantenimientoCreate

    assert PautaMantenimientoCreate(
        recurso_tipo="rampla", item="frenos", intervalo_km=1
    ).recurso_tipo.value == "rampla"
    with pytest.raises(ValidationError):
        PautaMantenimientoCreate(
            recurso_tipo="chofer", item="frenos", intervalo_km=100
        )
    with pytest.raises(ValidationError):
        PautaMantenimientoCreate(recurso_tipo="tracto", item="x", intervalo_km=0)


def test_mantenimiento_exige_un_solo_recurso_y_costo_no_negativo():
    from app.nucleo.schemas import MantenimientoCreate

    base = dict(
        pauta_id=uuid4(),
        fecha="2026-05-01",
        km="100.0",
        costo="0",
    )
    with pytest.raises(ValidationError):
        MantenimientoCreate(**base)  # sin recurso
    with pytest.raises(ValidationError):
        MantenimientoCreate(**base, tracto_id=uuid4(), rampla_id=uuid4())
    with pytest.raises(ValidationError):
        MantenimientoCreate(**{**base, "tracto_id": uuid4(), "costo": "-1"})
    with pytest.raises(ValidationError):
        MantenimientoCreate(**{**base, "tracto_id": uuid4(), "km": "-0.1"})
    valido = MantenimientoCreate(**base, tracto_id=uuid4())
    assert valido.costo == 0


def test_mantenimiento_rechaza_respaldo_fuera_del_almacenamiento():
    from app.nucleo.schemas import MantenimientoCreate

    with pytest.raises(ValidationError):
        MantenimientoCreate(
            pauta_id=uuid4(),
            tracto_id=uuid4(),
            fecha="2026-05-01",
            km="1",
            respaldo_url="https://example.com/x.pdf",
        )
    with pytest.raises(ValidationError):
        MantenimientoCreate(
            pauta_id=uuid4(),
            tracto_id=uuid4(),
            fecha="2026-05-01",
            km="1",
            respaldo_url="../fuera.pdf",
        )


def test_nomina_mes_y_montos():
    from app.nucleo.schemas import AjusteCreate, AnticipoCreate, LiquidacionCreate

    with pytest.raises(ValidationError):
        LiquidacionCreate(chofer_id=uuid4(), mes="2026-13")
    with pytest.raises(ValidationError):
        AnticipoCreate(chofer_id=uuid4(), monto="0", mes_imputacion="2026-05")
    with pytest.raises(ValidationError):
        AjusteCreate(
            chofer_id=uuid4(),
            mes="2026-05",
            tipo="bono",
            concepto="x",
            monto="-1",
        )
    with pytest.raises(ValidationError):
        AjusteCreate(
            chofer_id=uuid4(),
            mes="2026-05",
            tipo="otro",
            concepto="x",
            monto="1",
        )
    assert LiquidacionCreate(chofer_id=uuid4(), mes="2026-12").mes == "2026-12"
