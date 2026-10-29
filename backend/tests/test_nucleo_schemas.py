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
