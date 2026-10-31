"""Capa HTTP de O2.2 con JWT real y `X-Empresa-ID` (contrato §6.1–§6.4).

Lo que estas pruebas agregan sobre `test_agente_o2_2_buzon.py` (que ejercita el
servicio con un `ContextoEmpresa` armado a mano):

- el JWT de Supabase Auth y la resolución de la membresía por `get_contexto_empresa`;
- `X-Empresa-ID` como **único** origen de la empresa, y el 403 cuando el usuario
  no es miembro de esa empresa;
- la autoridad de permisos del backend: un rol sin `agente:buzon` recibe 403
  aunque la UI no exista;
- el mapeo de `ErrorNucleo` a HTTP (403/404/409/422/501) a través de FastAPI.

Requiere Supabase local arriba y `TEST_ADMIN_*` / `TEST_CONTABILIDAD_*` (los pone
`make test`). Si faltan, la suite se omite: no se simula autenticación.
"""

from __future__ import annotations

import base64
import json
from uuid import UUID

import pytest
from app.core.config import settings

from agente_helpers import asegurar_segunda_empresa, asegurar_segunda_empresa_con_membresia

pytestmark = pytest.mark.integracion

API = settings.API_V1_PREFIX
RUTA = f"{API}/nucleo/agente/solicitudes"


def _sub_del_token(headers: dict) -> str:
    """`sub` del JWT. Solo para localizar la membresía del fixture, no se valida.

    La validación real del token la hace el backend en cada request; aquí se usa
    para elegir una empresa de la que el usuario sea miembro.
    """
    token = headers["Authorization"].split(" ", 1)[1]
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))["sub"]


@pytest.fixture(scope="module")
def admin(db, headers_admin) -> dict:
    auth_id = UUID(_sub_del_token(headers_admin))
    fila = db.execute(
        "select empresa_id, id, rol from nucleo.usuarios_empresa "
        "where auth_id = %s and activo limit 1",
        (auth_id,),
    ).fetchone()
    if fila is None:
        pytest.skip("el usuario admin del seed no tiene membresía en tei_test")
    empresa_id, membresia_id, rol = fila
    otra = db.execute(
        "select id from nucleo.usuarios_empresa "
        "where empresa_id = %s and id <> %s limit 1",
        (empresa_id, membresia_id),
    ).fetchone()
    return {
        "empresa_id": empresa_id,
        "membresia_id": membresia_id,
        "rol": rol,
        "auth_id": auth_id,
        # Solicitante distinto del aprobador: si no existe, la autoaprobación
        # bloquearía toda decisión y las pruebas de camino feliz no servirían.
        "otro_miembro_id": otra[0] if otra else None,
    }


@pytest.fixture
def solicitud(db, admin):
    """Solicitud pendiente real; se borra al terminar."""
    creadas: list[UUID] = []

    def _crear(
        *,
        tipo: str = "otra",
        payload: dict | None = None,
        usuario_empresa_id: UUID | None = None,
        estado: str = "pendiente",
    ) -> UUID:
        solicitante = usuario_empresa_id or admin["otro_miembro_id"]
        if solicitante is None:
            pytest.skip("se necesitan dos membresías para probar decisiones")
        sid = db.execute(
            """
            insert into nucleo.solicitudes
                (empresa_id, tipo, solicitante_usuario_empresa_id, payload, estado)
            values (%s, cast(%s as nucleo.tipo_solicitud), %s,
                    cast(%s as jsonb), cast(%s as nucleo.estado_solicitud))
            returning id
            """,
            (
                admin["empresa_id"],
                tipo,
                solicitante,
                json.dumps(payload or {}),
                estado,
            ),
        ).fetchone()[0]
        creadas.append(sid)
        db.commit()
        return sid

    yield _crear

    if creadas:
        db.execute("delete from nucleo.solicitudes where id = any(%s)", (creadas,))
        db.commit()


def _headers(headers_admin: dict, empresa_id: UUID) -> dict:
    return {**headers_admin, "X-Empresa-ID": str(empresa_id)}


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------


def test_listar_con_jwt_real(client, headers_admin, admin) -> None:
    resp = client.get(RUTA, headers=_headers(headers_admin, admin["empresa_id"]))
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert set(cuerpo) == {"items", "total", "limit", "offset"}
    assert cuerpo["limit"] == 50 and cuerpo["offset"] == 0


def test_sin_token_es_401_o_403(client, admin) -> None:
    resp = client.get(RUTA, headers={"X-Empresa-ID": str(admin["empresa_id"])})
    assert resp.status_code in {401, 403}, resp.text


def test_sin_empresa_es_422(client, headers_admin) -> None:
    """`X-Empresa-ID` es obligatorio (`Header(...)`): FastAPI responde 422."""
    resp = client.get(RUTA, headers=headers_admin)
    assert resp.status_code == 422, resp.text


def test_rol_sin_permiso_no_lee_el_buzon(
    client, headers_contabilidad, admin
) -> None:
    """Contabilidad no tiene `agente:buzon`: el backend responde 403."""
    resp = client.get(
        RUTA, headers=_headers(headers_contabilidad, admin["empresa_id"])
    )
    assert resp.status_code == 403, resp.text
    cuerpo = resp.json()
    assert cuerpo["codigo"] == "ACCESO_DENEGADO"


def test_empresa_ajena_no_es_miembro(client, headers_admin, db, admin) -> None:
    """El JWT es válido pero el usuario no pertenece a esa empresa: 403."""
    otra = (asegurar_segunda_empresa(db),)
    resp = client.get(RUTA, headers=_headers(headers_admin, otra[0]))
    assert resp.status_code == 403, resp.text
    assert resp.json()["codigo"] == "ACCESO_DENEGADO"


def test_detalle_de_otra_empresa_es_404(client, headers_admin, db, admin) -> None:
    """Con membresía correcta pero id de otra empresa: 404, no filtración."""
    empresa_ajena, miembro_ajeno = asegurar_segunda_empresa_con_membresia(
        db, admin["auth_id"]
    )

    sid = db.execute(
        """
        insert into nucleo.solicitudes
            (empresa_id, tipo, solicitante_usuario_empresa_id, payload)
        values (%s, 'otra', %s, '{}'::jsonb)
        returning id
        """,
        (empresa_ajena, miembro_ajeno),
    ).fetchone()[0]
    db.commit()
    try:
        # La membresía del admin es de SU empresa; el recurso es de otra.
        resp = client.get(
            f"{RUTA}/{sid}", headers=_headers(headers_admin, admin["empresa_id"])
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["codigo"] == "RECURSO_NO_ENCONTRADO"
    finally:
        db.execute("delete from nucleo.solicitudes where id = %s", (sid,))
        db.commit()


# ---------------------------------------------------------------------------
# Decisión
# ---------------------------------------------------------------------------


def test_decidir_sin_permiso_es_403(client, headers_contabilidad, admin, solicitud) -> None:
    sid = solicitud()
    resp = client.post(
        f"{RUTA}/{sid}/decidir",
        json={"accion": "rechazar", "version": 1, "motivo_rechazo": "x"},
        headers=_headers(headers_contabilidad, admin["empresa_id"]),
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["codigo"] == "ACCESO_DENEGADO"


def test_body_incompleto_es_422(client, headers_admin, admin, solicitud) -> None:
    sid = solicitud()
    resp = client.post(
        f"{RUTA}/{sid}/decidir",
        json={"accion": "rechazar"},  # falta version
        headers=_headers(headers_admin, admin["empresa_id"]),
    )
    assert resp.status_code == 422, resp.text


def test_accion_desconocida_es_422(client, headers_admin, admin, solicitud) -> None:
    sid = solicitud()
    resp = client.post(
        f"{RUTA}/{sid}/decidir",
        json={"accion": "borrar", "version": 1},
        headers=_headers(headers_admin, admin["empresa_id"]),
    )
    assert resp.status_code == 422, resp.text


def test_rechazo_completo_por_http(client, headers_admin, admin, solicitud) -> None:
    sid = solicitud()
    resp = client.post(
        f"{RUTA}/{sid}/decidir",
        json={"accion": "rechazar", "version": 1, "motivo_rechazo": "falta POD"},
        headers=_headers(headers_admin, admin["empresa_id"]),
    )
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["solicitud"]["estado"] == "rechazada"
    assert cuerpo["solicitud"]["version"] == 2
    assert cuerpo["resultado"] is None


def test_reintento_tras_exito_es_409(client, headers_admin, admin, solicitud) -> None:
    sid = solicitud()
    cabeceras = _headers(headers_admin, admin["empresa_id"])
    primera = client.post(
        f"{RUTA}/{sid}/decidir",
        json={"accion": "rechazar", "version": 1, "motivo_rechazo": "uno"},
        headers=cabeceras,
    )
    assert primera.status_code == 200, primera.text
    segunda = client.post(
        f"{RUTA}/{sid}/decidir",
        json={"accion": "rechazar", "version": 2, "motivo_rechazo": "dos"},
        headers=cabeceras,
    )
    assert segunda.status_code == 409, segunda.text
    assert segunda.json()["codigo"] == "SOLICITUD_YA_DECIDIDA"


def test_version_vieja_es_409(client, headers_admin, admin, db, solicitud) -> None:
    sid = solicitud()
    db.execute(
        "update nucleo.solicitudes set version = 5 where id = %s", (sid,)
    )
    db.commit()
    resp = client.post(
        f"{RUTA}/{sid}/decidir",
        json={"accion": "rechazar", "version": 1, "motivo_rechazo": "x"},
        headers=_headers(headers_admin, admin["empresa_id"]),
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["codigo"] == "CONFLICTO_CONCURRENCIA"


def test_confirmar_tipo_sin_ejecutor_es_501(
    client, headers_admin, admin, solicitud
) -> None:
    sid = solicitud(tipo="agendamiento")
    resp = client.post(
        f"{RUTA}/{sid}/decidir",
        json={"accion": "confirmar", "version": 1},
        headers=_headers(headers_admin, admin["empresa_id"]),
    )
    assert resp.status_code == 501, resp.text
    assert resp.json()["codigo"] == "TIPO_SIN_EJECUTOR"


def test_autoaprobacion_es_403(client, headers_admin, admin, solicitud) -> None:
    """Solicitud pedida por el propio admin: no puede aprobarla él mismo."""
    sid = solicitud(usuario_empresa_id=admin["membresia_id"])
    resp = client.post(
        f"{RUTA}/{sid}/decidir",
        json={"accion": "rechazar", "version": 1, "motivo_rechazo": "x"},
        headers=_headers(headers_admin, admin["empresa_id"]),
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["codigo"] == "AUTOAPROBACION"


def test_no_revela_datos_fuera_del_buzon(client, headers_admin, admin, solicitud) -> None:
    """El detalle no expone teléfono, contenido de archivos ni costos."""
    sid = solicitud(payload={"km": 10, "evidencia": [{"tipo": "mensaje", "ref": "m-1"}]})
    resp = client.get(
        f"{RUTA}/{sid}", headers=_headers(headers_admin, admin["empresa_id"])
    )
    assert resp.status_code == 200, resp.text
    crudo = json.dumps(resp.json())
    for prohibido in ("telefono", "+569", "costo", "margen", "valor_flete"):
        assert prohibido not in crudo
