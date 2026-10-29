from app.nucleo import models
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import TSTZRANGE


def test_todas_las_tablas_viven_en_schema_nucleo():
    for nombre in (
        "Empresa",
        "UsuarioEmpresa",
        "Cliente",
        "Tarifa",
        "OrdenCompra",
        "OrdenCompraLinea",
        "Tracto",
        "Rampla",
        "Chofer",
        "Documento",
        "Viaje",
        "ReservaRecurso",
        "FolioContador",
        "TransicionViaje",
        "Auditoria",
    ):
        tabla = getattr(models, nombre).__table__
        assert tabla.schema == "nucleo", nombre


def test_viaje_tiene_ventana_tstzrange_y_monto_generado():
    tabla = models.Viaje.__table__
    assert isinstance(tabla.c.ventana.type, TSTZRANGE)
    assert tabla.c.monto_total_neto.computed is not None
    assert "valor_flete_neto" in str(tabla.c.monto_total_neto.computed.sqltext)


def test_enums_son_tipos_nativos_postgresql():
    tipo = models.Viaje.__table__.c.estado.type
    assert isinstance(tipo, PGEnum)
    assert tipo.name == "estado_viaje"
    assert tipo.schema == "nucleo"
    assert tipo.create_type is False
    assert set(tipo.enums) == {e.value for e in models.EstadoViaje}


def test_viaje_tiene_todos_los_campos_de_carga_del_plan():
    columnas = models.Viaje.__table__.c
    requeridas = {
        "tipo_carga",
        "peso_bruto_kg",
        "peso_neto_kg",
        "tara_kg",
        "volumen_m3",
        "bultos",
        "valor_declarado",
        "carga_peligrosa",
        "numero_un",
        "refrigerada",
        "temperatura_min_c",
        "temperatura_max_c",
        "sobredimensionada",
        "origen_nombre",
        "destino_nombre",
        "distancia_km",
        "km_vacios",
        "tarifa_snapshot",
        "oc_numero_snapshot",
    }
    assert requeridas.issubset(set(columnas.keys()))


def test_reserva_tiene_las_tres_dimensiones_de_recurso():
    columnas = models.ReservaRecurso.__table__.c
    assert {"tracto_id", "rampla_id", "chofer_id", "ventana", "activa"} <= set(
        columnas.keys()
    )


def test_no_hay_cascade_delete_en_viajes():
    # El viaje es el átomo financiero: no se borra en cascada.
    claves = {
        fk.target_fullname
        for fk in models.Viaje.__table__.foreign_keys
        if fk.target_fullname.startswith("nucleo.")
    }
    assert "nucleo.clientes.id" in claves
    assert "nucleo.tractos.id" in claves
