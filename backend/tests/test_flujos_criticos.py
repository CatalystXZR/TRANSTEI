"""Pruebas de integración de los flujos críticos (requieren Supabase real).

Se omiten automáticamente si no hay credenciales TEST_* definidas.
Cada prueba crea sus propios datos con una etiqueta única y los elimina al final.
"""

from datetime import date

import pytest

API = "/api/v1"


@pytest.fixture
def entorno(client, headers_admin, db, etiqueta):
    """Crea cliente/chofer/tracto/rampla de prueba y los limpia al terminar."""
    cl = client.post(
        f"{API}/clientes",
        json={"razon_social": f"Cliente {etiqueta}", "rut": "70000000-1", "dias_pago": 30},
        headers=headers_admin,
    ).json()
    ch = client.post(
        f"{API}/choferes",
        json={
            "nombre": f"Chofer {etiqueta}",
            "rut": "70000000-2",
            "sueldo_base": 400000,
            "porcentaje_produccion": 0.10,
        },
        headers=headers_admin,
    ).json()
    tr = client.post(
        f"{API}/tractos",
        json={"patente": f"{etiqueta}-A", "marca": "Test", "km_actual": 10000},
        headers=headers_admin,
    ).json()
    rp = client.post(
        f"{API}/ramplas",
        json={"patente": f"{etiqueta}-B", "tipo": "plana"},
        headers=headers_admin,
    ).json()

    ids = {"cliente": cl["id"], "chofer": ch["id"], "tracto": tr["id"], "rampla": rp["id"]}
    yield ids

    with db.cursor() as cur:
        cur.execute("delete from gastos_viaje where viaje_id in (select id from viajes where cliente_id=%s)", (ids["cliente"],))
        cur.execute("delete from factura_viaje where viaje_id in (select id from viajes where cliente_id=%s)", (ids["cliente"],))
        cur.execute("delete from facturas where cliente_id=%s", (ids["cliente"],))
        cur.execute("delete from viajes where cliente_id=%s", (ids["cliente"],))
        cur.execute("delete from mantenimientos where tracto_id=%s", (ids["tracto"],))
        cur.execute("delete from liquidaciones where chofer_id=%s", (ids["chofer"],))
        cur.execute("delete from anticipos_chofer where chofer_id=%s", (ids["chofer"],))
        cur.execute("delete from ajustes_liquidacion where chofer_id=%s", (ids["chofer"],))
        cur.execute("delete from clientes where id=%s", (ids["cliente"],))
        cur.execute("delete from choferes where id=%s", (ids["chofer"],))
        cur.execute("delete from tractos where id=%s", (ids["tracto"],))
        cur.execute("delete from ramplas where id=%s", (ids["rampla"],))
        db.commit()


def _crear_viaje(client, headers, ids, valor=1000000, fecha="2026-09-05"):
    return client.post(
        f"{API}/viajes",
        json={
            "fecha_inicio": fecha,
            "origen": "Santiago",
            "destino": "Concepción",
            "valor_flete_neto": valor,
            "cliente_id": ids["cliente"],
            "chofer_id": ids["chofer"],
            "tracto_id": ids["tracto"],
            "rampla_id": ids["rampla"],
        },
        headers=headers,
    )


def _finalizar(client, headers, viaje_id):
    client.patch(f"{API}/viajes/{viaje_id}/estado", json={"estado": "en_ruta"}, headers=headers)
    client.patch(f"{API}/viajes/{viaje_id}/estado", json={"estado": "finalizado"}, headers=headers)


def test_login_y_rol(client, headers_admin):
    r = client.get(f"{API}/auth/me", headers=headers_admin)
    assert r.status_code == 200
    assert r.json()["rol"] == "admin"


def test_sin_token_no_accede(client):
    assert client.get(f"{API}/clientes").status_code == 401


def test_cliente_rut_duplicado(client, headers_admin, db, etiqueta):
    rut = f"{etiqueta}-RUT"
    body = {"razon_social": f"Dup {etiqueta}", "rut": rut}
    r1 = client.post(f"{API}/clientes", json=body, headers=headers_admin)
    assert r1.status_code == 201
    r2 = client.post(f"{API}/clientes", json=body, headers=headers_admin)
    assert r2.status_code == 400, "El RUT duplicado debe ser rechazado"
    with db.cursor() as cur:
        cur.execute("delete from clientes where rut=%s", (rut,))
        db.commit()


def test_viaje_validaciones(client, headers_admin, entorno):
    # Fecha de fin anterior → rechazado
    r = _crear_viaje(client, headers_admin, entorno)
    assert r.status_code == 201
    viaje = r.json()
    r = client.put(
        f"{API}/viajes/{viaje['id']}",
        json={"fecha_inicio": "2026-09-10", "fecha_fin": "2026-09-01"},
        headers=headers_admin,
    )
    assert r.status_code == 400

    # Tracto ocupado: crear otro viaje con el mismo tracto → rechazado
    r2 = _crear_viaje(client, headers_admin, entorno)
    assert r2.status_code == 400

    # Transición inválida programado → facturado
    r3 = client.patch(
        f"{API}/viajes/{viaje['id']}/estado", json={"estado": "facturado"}, headers=headers_admin
    )
    assert r3.status_code == 400

    # No se puede eliminar un viaje no programado
    _finalizar(client, headers_admin, viaje["id"])
    r4 = client.delete(f"{API}/viajes/{viaje['id']}", headers=headers_admin)
    assert r4.status_code == 400


def test_facturacion_iva_y_pago(client, headers_admin, headers_contabilidad, entorno):
    v1 = _crear_viaje(client, headers_admin, entorno, valor=1000000).json()
    _finalizar(client, headers_admin, v1["id"])
    v2 = _crear_viaje(client, headers_admin, entorno, valor=800000).json()
    _finalizar(client, headers_admin, v2["id"])

    r = client.post(
        f"{API}/facturas",
        json={
            "numero_sii": "900001",
            "cliente_id": entorno["cliente"],
            "tipo": "afecta",
            "viaje_ids": [v1["id"], v2["id"]],
        },
        headers=headers_admin,
    )
    assert r.status_code == 201
    f = r.json()
    assert float(f["monto_neto"]) == 1800000
    assert float(f["iva"]) == 342000
    assert float(f["total"]) == 2142000

    # Los viajes quedan facturados
    assert client.get(f"{API}/viajes/{v1['id']}", headers=headers_admin).json()["estado"] == "facturado"

    # Pago por contabilidad
    r = client.patch(
        f"{API}/facturas/{f['id']}/estado", json={"estado": "pagada"}, headers=headers_contabilidad
    )
    assert r.status_code == 200
    assert r.json()["fecha_pago"] is not None


def test_liquidacion_calculo(client, headers_admin, headers_contabilidad, entorno, etiqueta):
    """R-01: la comisión es el 10 % de la facturación del mes.

    El mes no está hardcodeado: se deriva del viaje persistido, que es la clave
    con que liquida `_comision_chofer` (`coalesce(fecha_fin, fecha_inicio)`).
    Los viajes se **facturan** antes de liquidar porque, desde R-01, la base de
    la comisión son los viajes en estado `facturado`; uno solo `finalizado`
    devenga 0 (caso negativo en la prueba siguiente).
    """
    hoy = date.today()
    viaje_ids = []
    for valor in (1000000, 800000):
        r = _crear_viaje(
            client, headers_admin, entorno, valor=valor, fecha=hoy.isoformat()
        )
        assert r.status_code == 201, r.text
        viaje_id = r.json()["id"]
        _finalizar(client, headers_admin, viaje_id)
        viaje_ids.append(viaje_id)

    detalle = client.get(f"{API}/viajes/{viaje_ids[0]}", headers=headers_admin).json()
    mes = (detalle.get("fecha_fin") or detalle["fecha_inicio"])[:7]
    assert mes == hoy.strftime("%Y-%m"), (
        "La finalización debe fechar el viaje en el mes corriente; "
        f"fecha_fin={detalle.get('fecha_fin')!r}."
    )

    # Facturar los viajes: la factura los marca `facturado` (base de R-01).
    r = client.post(
        f"{API}/facturas",
        json={
            "numero_sii": f"FAC-{etiqueta}",
            "cliente_id": entorno["cliente"],
            "tipo": "afecta",
            "viaje_ids": viaje_ids,
        },
        headers=headers_admin,
    )
    assert r.status_code == 201, r.text
    assert float(r.json()["monto_neto"]) == 1800000

    # anticipo 100.000 y bono 50.000
    r = client.post(
        f"{API}/anticipos?chofer_id={entorno['chofer']}&monto=100000&mes_liquidacion={mes}",
        headers=headers_contabilidad,
    )
    assert r.status_code == 201, r.text
    r = client.post(
        f"{API}/ajustes?chofer_id={entorno['chofer']}&mes={mes}&tipo=bono&concepto=Bonus&monto=50000",
        headers=headers_contabilidad,
    )
    assert r.status_code == 201, r.text

    r = client.post(
        f"{API}/liquidaciones/calcular?chofer_id={entorno['chofer']}&mes={mes}",
        headers=headers_contabilidad,
    )
    assert r.status_code == 200, r.text
    liq = r.json()
    # 400.000 base + 10% de 1.800.000 (180.000) + 50.000 - 100.000 = 530.000
    assert float(liq["comision"]) == 180000
    assert float(liq["total_liquido"]) == 530000


def test_liquidacion_sin_facturacion_no_genera_comision(
    client, headers_admin, headers_contabilidad, entorno
):
    """R-01 (caso negativo): viajes solo `finalizado`, sin factura → comisión 0.

    Mismos montos que el caso facturado (1.000.000 + 800.000). Si el cálculo
    volviera a sumar `finalizado`, la comisión sería 180.000 y esta prueba
    fallaría por la razón correcta.
    """
    hoy = date.today()
    viaje_ids = []
    for valor in (1000000, 800000):
        r = _crear_viaje(
            client, headers_admin, entorno, valor=valor, fecha=hoy.isoformat()
        )
        assert r.status_code == 201, r.text
        viaje_id = r.json()["id"]
        _finalizar(client, headers_admin, viaje_id)
        viaje_ids.append(viaje_id)

    detalle = client.get(f"{API}/viajes/{viaje_ids[0]}", headers=headers_admin).json()
    mes = (detalle.get("fecha_fin") or detalle["fecha_inicio"])[:7]

    r = client.post(
        f"{API}/liquidaciones/calcular?chofer_id={entorno['chofer']}&mes={mes}",
        headers=headers_contabilidad,
    )
    assert r.status_code == 200, r.text
    liq = r.json()
    assert float(liq["comision"]) == 0, (
        "Un viaje solo finalizado no genera comisión; "
        f"obtenido {liq['comision']}."
    )
    # 400.000 de sueldo base, sin comisión ni anticipos/ajustes.
    assert float(liq["total_liquido"]) == 400000


def test_mantenimiento_estados(client, headers_admin, entorno):
    pautas = client.get(f"{API}/pautas", headers=headers_admin).json()
    aceite = next(p for p in pautas if "aceite" in p["item"].lower())

    # registrar mantención a 10.000 km; intervalo 20.000 → próximo 30.000
    r = client.post(
        f"{API}/mantenimientos?tracto_id={entorno['tracto']}&pauta_id={aceite['id']}&km=10000",
        headers=headers_admin,
    )
    assert r.status_code == 201

    estado = client.get(f"{API}/mantenimiento/estado", headers=headers_admin).json()
    tracto = next(t for t in estado if t["tracto_id"] == entorno["tracto"])
    item = next(i for i in tracto["items"] if i["item"] == aceite["item"])
    assert item["estado"] == "ok"

    # subir km a 31.000 → pendiente
    client.put(
        f"{API}/tractos/{entorno['tracto']}", json={"km_actual": 31000}, headers=headers_admin
    )
    estado = client.get(f"{API}/mantenimiento/estado", headers=headers_admin).json()
    tracto = next(t for t in estado if t["tracto_id"] == entorno["tracto"])
    item = next(i for i in tracto["items"] if i["item"] == aceite["item"])
    assert item["estado"] == "pendiente"


def test_kpis_crud_y_preview(client, headers_admin, headers_contabilidad):
    # Preview de fórmula inválida devuelve error, no rompe
    r = client.post(
        f"{API}/kpis/preview",
        json={"formula": "metrica_inexistente + 1", "ambito": "global"},
        headers=headers_admin,
    )
    assert r.status_code == 200 and r.json()["error"]

    # Crear KPI
    r = client.post(
        f"{API}/kpis",
        json={
            "nombre": "KPI Temporal Test",
            "ambito": "global",
            "formula": "viajes_mes + 1",
            "formato": "numero",
            "uso": "interno",
        },
        headers=headers_admin,
    )
    assert r.status_code == 201
    kid = r.json()["id"]

    # No-admin no puede editar
    assert client.put(f"{API}/kpis/{kid}", json={"nombre": "X"}, headers=headers_contabilidad).status_code == 403

    # Editar con fórmula inválida → 400
    assert client.put(
        f"{API}/kpis/{kid}", json={"formula": "no_existe"}, headers=headers_admin
    ).status_code == 400

    # Eliminar (soft)
    assert client.delete(f"{API}/kpis/{kid}", headers=headers_admin).status_code == 204
