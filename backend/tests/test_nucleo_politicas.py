from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.nucleo.models import (
    Chofer,
    Cliente,
    Empresa,
    EstadoOC,
    EstadoRecurso,
    ModalidadTarifa,
    OrdenCompra,
    Rampla,
    Tarifa,
    TipoCarga,
    TipoDocumento,
    TipoRampla,
    TipoRecurso,
    Tracto,
    Viaje,
)
from app.nucleo.politicas import (
    documentos_requeridos,
    validar_carga,
    validar_oc,
    validar_tarifa,
)


def empresa(**kwargs) -> Empresa:
    base = dict(codigo="TEI", razon_social="Transportes TEI SpA", rut="76.123.456-7")
    base.update(kwargs)
    return Empresa(**base)


def tracto(**kwargs) -> Tracto:
    base = dict(
        empresa_id=uuid4(),
        patente="ABCD12",
        peso_bruto_kg=Decimal("39000"),
        tara_kg=Decimal("9000"),
        capacidad_carga_kg=Decimal("30000"),
        licencias_permitidas=["A5"],
    )
    base.update(kwargs)
    return Tracto(**base)


def rampla(**kwargs) -> Rampla:
    base = dict(
        empresa_id=uuid4(),
        patente="RPLA12",
        tipo=TipoRampla.plana,
        capacidad_carga_kg=Decimal("30000"),
        volumen_m3=Decimal("80"),
    )
    base.update(kwargs)
    return Rampla(**base)


def chofer(**kwargs) -> Chofer:
    base = dict(
        empresa_id=uuid4(),
        rut="12.345.678-9",
        nombre="Juan Pérez",
        licencia_clase="A5",
        autorizado_carga_peligrosa=False,
    )
    base.update(kwargs)
    return Chofer(**base)


def viaje(**kwargs) -> Viaje:
    base = dict(
        empresa_id=uuid4(),
        numero_viaje="VJ-2026-000001",
        cliente_id=uuid4(),
        inicio_planificado=datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc),
        fin_planificado=datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc),
        origen_nombre="Santiago",
        destino_nombre="Concepción",
        peso_bruto_kg=Decimal("25000"),
    )
    base.update(kwargs)
    return Viaje(**base)


def test_documentos_tracto_incluye_soap_y_peligrosa():
    reqs = documentos_requeridos(
        TipoRecurso.tracto, empresa(exigir_soap=True), carga_peligrosa=True
    )
    tipos = {r.tipo for r in reqs}
    assert TipoDocumento.revision_tecnica in tipos
    assert TipoDocumento.permiso_circulacion in tipos
    assert TipoDocumento.seguro_obligatorio in tipos
    assert TipoDocumento.soap in tipos
    assert TipoDocumento.permiso_carga_peligrosa in tipos


def test_documentos_rampla_refrigerada_exige_gases():
    reqs = documentos_requeridos(
        TipoRecurso.rampla, empresa(exigir_seguro_carga=True), refrigerada=True
    )
    tipos = {r.tipo for r in reqs}
    assert TipoDocumento.certificado_gases in tipos
    assert TipoDocumento.seguro_carga in tipos


def test_documentos_chofer_peligrosa_exige_curso():
    reqs = documentos_requeridos(
        TipoRecurso.chofer, empresa(exigir_curso_carga_peligrosa=True), carga_peligrosa=True
    )
    tipos = {r.tipo for r in reqs}
    assert TipoDocumento.licencia_conducir in tipos
    assert TipoDocumento.examen_medico in tipos
    assert TipoDocumento.curso_carga_peligrosa in tipos


def test_capacidad_ok_no_genera_bloqueos():
    v = viaje()
    t = tracto(empresa_id=v.empresa_id)
    r = rampla(empresa_id=v.empresa_id)
    c = chofer(empresa_id=v.empresa_id)
    assert validar_carga(v, t, r, c) == []


def test_sobrepeso_bloquea():
    v = viaje(peso_bruto_kg=Decimal("31000"))
    t = tracto(empresa_id=v.empresa_id)
    r = rampla(empresa_id=v.empresa_id)
    c = chofer(empresa_id=v.empresa_id)
    errores = validar_carga(v, t, r, c)
    assert any(e.codigo == "SOBREPESO_TRACTO" for e in errores)


def test_licencia_a5_es_valida_aunque_el_tracto_configure_otra_clase():
    """R-02/0016: la clase válida es A5 global; el array del tracto está deprecado.

    Antes de R-02, `tractos.licencias_permitidas=["A3"]` hacía que un chofer A5
    apareciera como `LICENCIA_NO_AUTORIZADA` no bloqueante. Desde 0016 ese
    arreglo no otorga ni restringe permisos: un chofer A5 no genera ningún
    hallazgo de licencia aunque el tracto configure otra clase.
    """
    v = viaje()
    t = tracto(empresa_id=v.empresa_id, licencias_permitidas=["A3"])
    r = rampla(empresa_id=v.empresa_id)
    c = chofer(empresa_id=v.empresa_id, licencia_clase="A5")
    hallazgos = validar_carga(v, t, r, c)
    assert not [h for h in hallazgos if h.codigo.startswith("LICENCIA_")], (
        "Un chofer A5 no puede rechazarse por la configuración deprecada del "
        f"tracto. Hallazgos: {[(h.codigo, h.bloqueante) for h in hallazgos]}"
    )


def test_licencia_no_a5_bloquea():
    """R-02: clase distinta de A5 es bloqueante (ya no es advertencia)."""
    v = viaje()
    t = tracto(empresa_id=v.empresa_id)
    r = rampla(empresa_id=v.empresa_id)
    c = chofer(empresa_id=v.empresa_id, licencia_clase="A3")
    hallazgos = validar_carga(v, t, r, c)
    licencia = next(h for h in hallazgos if h.codigo == "LICENCIA_NO_AUTORIZADA")
    assert licencia.bloqueante is True


def test_licencia_sin_clase_bloquea():
    """R-02: clase ausente también es bloqueante."""
    v = viaje()
    t = tracto(empresa_id=v.empresa_id)
    r = rampla(empresa_id=v.empresa_id)
    c = chofer(empresa_id=v.empresa_id, licencia_clase=None)
    hallazgos = validar_carga(v, t, r, c)
    licencia = next(h for h in hallazgos if h.codigo == "LICENCIA_FALTANTE")
    assert licencia.bloqueante is True


def test_carga_peligrosa_sin_autorizacion_bloquea():
    v = viaje(carga_peligrosa=True)
    t = tracto(empresa_id=v.empresa_id)
    r = rampla(empresa_id=v.empresa_id)
    c = chofer(empresa_id=v.empresa_id, autorizado_carga_peligrosa=False)
    errores = validar_carga(v, t, r, c)
    assert any(e.codigo == "CHOFER_NO_PELIGROSA" for e in errores)


def test_refrigerada_requiere_rampla_refrigerada_y_temperaturas():
    v = viaje(refrigerada=True)
    t = tracto(empresa_id=v.empresa_id)
    r = rampla(empresa_id=v.empresa_id, tipo=TipoRampla.plana)
    c = chofer(empresa_id=v.empresa_id)
    errores = validar_carga(v, t, r, c)
    codigos = {e.codigo for e in errores}
    assert "RAMPLA_NO_REFRIGERADA" in codigos
    assert "TEMPERATURA_FALTANTE" in codigos


def test_contenedor_requiere_portacontenedor():
    v = viaje(tipo_carga=TipoCarga.contenedor)
    t = tracto(empresa_id=v.empresa_id)
    r = rampla(empresa_id=v.empresa_id, tipo=TipoRampla.plana)
    c = chofer(empresa_id=v.empresa_id)
    errores = validar_carga(v, t, r, c)
    assert any(e.codigo == "RAMPLA_NO_CONTENEDOR" for e in errores)


def test_recurso_baja_bloquea():
    v = viaje()
    t = tracto(empresa_id=v.empresa_id, estado=EstadoRecurso.baja)
    r = rampla(empresa_id=v.empresa_id)
    c = chofer(empresa_id=v.empresa_id)
    errores = validar_carga(v, t, r, c)
    assert any(e.codigo == "RECURSO_BLOQUEADO" for e in errores)


def cliente(**kwargs) -> Cliente:
    base = dict(
        empresa_id=uuid4(),
        razon_social="Cliente Uno",
        rut="96.111.222-3",
        exige_oc=False,
    )
    base.update(kwargs)
    return Cliente(**base)


def oc(**kwargs) -> OrdenCompra:
    base = dict(
        empresa_id=uuid4(),
        cliente_id=uuid4(),
        numero_oc="OC-1",
        vigencia_hasta=date(2027, 12, 31),
        monto_autorizado=Decimal("1000000"),
        sobregiro_autorizado=Decimal("0"),
        monto_consumido=Decimal("0"),
        estado=EstadoOC.abierta,
    )
    base.update(kwargs)
    return OrdenCompra(**base)


def test_oc_faltante_no_bloquea_despacho_pero_no_factura():
    cli = cliente(exige_oc=True)
    v = viaje(cliente_id=cli.id)
    hallazgos = validar_oc(
        v,
        None,
        cli,
        empresa(),
        consumo_neto=Decimal("0"),
        fecha_local_viaje=date(2026, 11, 1),
    )
    pendiente = next(e for e in hallazgos if e.codigo == "OC_PENDIENTE_FACTURACION")
    assert pendiente.bloqueante is False


def test_oc_sin_saldo_bloquea():
    cli = cliente()
    v = viaje(cliente_id=cli.id, valor_flete_neto=Decimal("600000"))
    orden = oc(
        cliente_id=cli.id,
        monto_autorizado=Decimal("1000000"),
        monto_consumido=Decimal("500000"),
    )
    errores = validar_oc(
        v,
        orden,
        cli,
        empresa(),
        consumo_neto=Decimal("500000"),
        fecha_local_viaje=date(2026, 11, 1),
    )
    assert any(e.codigo == "OC_SIN_SALDO" for e in errores)


def test_oc_vencida_bloquea():
    cli = cliente()
    v = viaje(cliente_id=cli.id)
    orden = oc(cliente_id=cli.id, estado=EstadoOC.vencida)
    errores = validar_oc(
        v,
        orden,
        cli,
        empresa(),
        consumo_neto=Decimal("0"),
        fecha_local_viaje=date(2026, 11, 1),
    )
    assert any(e.codigo == "OC_VENCIDA" for e in errores)


def test_oc_en_otra_moneda_bloquea():
    cli = cliente()
    v = viaje(cliente_id=cli.id, moneda="CLP")
    orden = oc(cliente_id=cli.id, moneda="USD")
    errores = validar_oc(
        v,
        orden,
        cli,
        empresa(),
        consumo_neto=Decimal("0"),
        fecha_local_viaje=date(2026, 11, 1),
    )
    assert any(e.codigo == "OC_MONEDA" for e in errores)


def test_oc_que_vence_antes_del_fin_del_viaje_bloquea():
    cli = cliente()
    v = viaje(cliente_id=cli.id)
    orden = oc(
        cliente_id=cli.id,
        vigencia_hasta=date(2026, 11, 1),
    )
    errores = validar_oc(
        v,
        orden,
        cli,
        empresa(),
        consumo_neto=Decimal("0"),
        fecha_local_viaje=date(2026, 11, 1),
        fecha_local_fin=date(2026, 11, 2),
    )
    assert any(e.codigo == "OC_FUERA_VIGENCIA_FIN" for e in errores)


def test_tarifa_en_otra_moneda_bloquea():
    cli = cliente()
    v = viaje(cliente_id=cli.id, moneda="CLP")
    t = Tarifa(
        empresa_id=v.empresa_id,
        cliente_id=cli.id,
        codigo="T-USD",
        nombre="Tarifa USD",
        modalidad=ModalidadTarifa.viaje,
        vigencia_desde=date(2026, 1, 1),
        vigencia_hasta=date(2027, 12, 31),
        moneda="USD",
    )
    errores = validar_tarifa(v, t, date(2026, 11, 1))
    assert any(e.codigo == "TARIFA_MONEDA" for e in errores)


def test_tarifa_no_vigente_bloquea():
    cli = cliente()
    v = viaje(cliente_id=cli.id)
    t = Tarifa(
        empresa_id=v.empresa_id,
        cliente_id=cli.id,
        codigo="T-1",
        nombre="Santiago-Concepción",
        modalidad=ModalidadTarifa.viaje,
        vigencia_desde=date(2027, 1, 1),
        vigencia_hasta=date(2027, 12, 31),
    )
    errores = validar_tarifa(v, t, date(2026, 11, 1))
    assert any(e.codigo == "TARIFA_NO_VIGENTE" for e in errores)
