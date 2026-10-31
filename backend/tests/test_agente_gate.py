"""Pruebas unitarias del gate de cuatro llaves (contrato §4.3–§4.7).

Sin base: se usa una fuente falsa que devuelve exactamente lo que cada llave
necesita. La integración con RLS y `tei_app` vive en
`test_agente_o2_1_integracion.py`.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from app.nucleo.agente.contexto import ContextoAgente, RolContacto
from app.nucleo.agente.ejecutores import EJECUTORES
from app.nucleo.agente.gate import autorizar
from app.nucleo.agente.manifest import RAIZ_PAQUETE, Descriptor, cargar_modulo
from app.nucleo.agente.registry import (
    Registry,
    _limite,
    clasificar_error,
)
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError


class FuenteFalsa:
    """Fuente determinista: `acl[(componente, variable)]` o ausencia."""

    def __init__(self, *, modulo: bool | None = True, acl: dict | None = None) -> None:
        self._modulo = modulo
        self._acl = acl or {}

    def modulo_habilitado(self, empresa_id: UUID) -> bool | None:
        return self._modulo

    def acl(
        self, contexto: ContextoAgente, componente: str, variable: str | None
    ) -> bool | None:
        return self._acl.get((componente, variable))


def _descriptor(nombre: str = "despacho.mis_fletes") -> Descriptor:
    return cargar_modulo(RAIZ_PAQUETE, EJECUTORES).descriptores[nombre]


def _ctx(
    *,
    rol: RolContacto = RolContacto.cliente_final,
    activo: bool = True,
    otp: str = "verificado",
    entidad: UUID | None = None,
) -> ContextoAgente:
    return ContextoAgente(
        empresa_id=uuid4(),
        contacto_id=uuid4(),
        rol=rol,
        entidad_id=entidad if entidad is not None else uuid4(),
        activo=activo,
        otp_estado=otp,
        telefono="+56911111111",
        request_id="req-test",
    )


def _acl_completa(descriptor: Descriptor) -> dict:
    return {
        (descriptor.componente, None): True,
        (descriptor.componente, descriptor.variable): True,
    }


# ---------------------------------------------------------------------------
# Llaves y orden
# ---------------------------------------------------------------------------


def test_autoriza_con_todas_las_llaves() -> None:
    descriptor = _descriptor()
    decision = autorizar(
        descriptor=descriptor,
        contexto=_ctx(),
        manifiesto_valido=True,
        fuente=FuenteFalsa(acl=_acl_completa(descriptor)),
    )
    assert decision.permitido is True


def test_manifiesto_invalido_gana_sobre_todo() -> None:
    descriptor = _descriptor()
    decision = autorizar(
        descriptor=descriptor,
        contexto=_ctx(activo=False, otp="pendiente"),
        manifiesto_valido=False,
        fuente=FuenteFalsa(modulo=False, acl={}),
    )
    assert not decision.permitido
    assert decision.codigo == "MODULO_INACTIVO"
    assert decision.nivel == "modulo"


def test_contacto_inactivo_deniega_identidad() -> None:
    descriptor = _descriptor()
    decision = autorizar(
        descriptor=descriptor,
        contexto=_ctx(activo=False),
        manifiesto_valido=True,
        fuente=FuenteFalsa(acl=_acl_completa(descriptor)),
    )
    assert decision.codigo == "NO_AUTORIZADO"
    assert decision.nivel == "identidad"
    assert decision.respuesta == "NO_AUTORIZADO:identidad"


def test_otp_pendiente_deniega_identidad() -> None:
    decision = autorizar(
        descriptor=_descriptor(),
        contexto=_ctx(otp="pendiente"),
        manifiesto_valido=True,
        fuente=FuenteFalsa(acl=_acl_completa(_descriptor())),
    )
    assert decision.nivel == "identidad"


@pytest.mark.parametrize("modulo", [False, None])
def test_modulo_apagado_o_ausente_deniega(modulo: bool | None) -> None:
    descriptor = _descriptor()
    decision = autorizar(
        descriptor=descriptor,
        contexto=_ctx(),
        manifiesto_valido=True,
        fuente=FuenteFalsa(modulo=modulo, acl=_acl_completa(descriptor)),
    )
    assert decision.codigo == "MODULO_INACTIVO"
    assert decision.nivel == "modulo"


def test_rol_fuera_del_descriptor_deniega() -> None:
    descriptor = _descriptor()  # solo cliente_final
    decision = autorizar(
        descriptor=descriptor,
        contexto=_ctx(rol=RolContacto.conductor),
        manifiesto_valido=True,
        fuente=FuenteFalsa(acl=_acl_completa(descriptor)),
    )
    assert decision.nivel == "rol"
    assert decision.respuesta == "NO_AUTORIZADO:rol"


def test_rol_antes_que_acl() -> None:
    """Un rol incorrecto no debe depender de la ACL: se deniega igual."""
    descriptor = _descriptor()
    decision = autorizar(
        descriptor=descriptor,
        contexto=_ctx(rol=RolContacto.conductor),
        manifiesto_valido=True,
        fuente=FuenteFalsa(acl=_acl_completa(descriptor)),
    )
    assert decision.nivel == "rol"


@pytest.mark.parametrize("valor", [None, False])
def test_acl_de_componente_ausente_o_false_deniega(valor: bool | None) -> None:
    descriptor = _descriptor()
    acl = {(descriptor.componente, descriptor.variable): True}
    if valor is not None:
        acl[(descriptor.componente, None)] = valor
    decision = autorizar(
        descriptor=descriptor,
        contexto=_ctx(),
        manifiesto_valido=True,
        fuente=FuenteFalsa(acl=acl),
    )
    assert decision.nivel == "componente"
    assert decision.variable is None
    assert decision.respuesta == "NO_AUTORIZADO:componente"


@pytest.mark.parametrize("valor", [None, False])
def test_acl_de_variable_ausente_o_false_deniega(valor: bool | None) -> None:
    descriptor = _descriptor()
    acl = {(descriptor.componente, None): True}
    if valor is not None:
        acl[(descriptor.componente, descriptor.variable)] = valor
    decision = autorizar(
        descriptor=descriptor,
        contexto=_ctx(),
        manifiesto_valido=True,
        fuente=FuenteFalsa(acl=acl),
    )
    assert decision.nivel == "variable"
    assert decision.variable == descriptor.variable
    assert decision.respuesta == "NO_AUTORIZADO:variable"


def test_admin_sin_acl_no_ve_nada() -> None:
    descriptor = _descriptor("despacho.viajes_del_dia")
    decision = autorizar(
        descriptor=descriptor,
        contexto=_ctx(rol=RolContacto.admin, entidad=None),
        manifiesto_valido=True,
        fuente=FuenteFalsa(acl={}),
    )
    assert decision.nivel == "componente"


# ---------------------------------------------------------------------------
# Registry declarativo
# ---------------------------------------------------------------------------


def _registry() -> Registry:
    modulo = cargar_modulo(RAIZ_PAQUETE, EJECUTORES)
    return Registry(modulo=modulo, valido=True, motivo=None)


def test_tools_para_rol_es_declarativo() -> None:
    registry = _registry()
    assert [d.nombre for d in registry.tools_para_rol(RolContacto.cliente_final)] == [
        "despacho.mis_fletes"
    ]
    assert [d.nombre for d in registry.tools_para_rol(RolContacto.conductor)] == [
        "despacho.mis_viajes_asignados"
    ]
    assert [d.nombre for d in registry.tools_para_rol(RolContacto.admin)] == [
        "despacho.viajes_del_dia"
    ]


def test_registry_no_expone_tool_desconocida() -> None:
    assert _registry().get("despacho.no_existe") is None


def test_registry_vacio_si_manifiesto_invalido() -> None:
    registry = Registry(modulo=None, valido=False, motivo="V2 en manifest.json")
    assert registry.valido is False
    assert registry.tools_cargadas == 0
    assert registry.estado() == {
        "valido": False,
        "version": None,
        "schema_di": None,
        "motivo": "V2 en manifest.json",
    }


# ---------------------------------------------------------------------------
# Límites y clasificación de errores
# ---------------------------------------------------------------------------


def test_limite_nunca_excede_max_filas() -> None:
    descriptor = _descriptor()
    assert descriptor.max_filas == 50
    assert _limite(descriptor, {}) == 50
    assert _limite(descriptor, {"limite": 3}) == 3
    assert _limite(descriptor, {"limite": 200}) == 50
    escritura = descriptor.model_copy(update={"tipo": "escritura_solicitud"})
    assert _limite(escritura, {"limite": 10}) is None


class _Orig:
    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate


def test_clasificar_integrity_por_sqlstate() -> None:
    assert (
        clasificar_error(IntegrityError("s", {}, _Orig("23514"))) == "REGLA_NEGOCIO"
    )
    assert (
        clasificar_error(IntegrityError("s", {}, _Orig("23505")))
        == "CONFLICTO_IDEMPOTENCIA"
    )
    assert (
        clasificar_error(IntegrityError("s", {}, _Orig("40001")))
        == "CONFLICTO_CONCURRENCIA"
    )


def test_clasificar_42501_como_no_autorizado() -> None:
    assert (
        clasificar_error(ProgrammingError("s", {}, _Orig("42501"))) == "NO_AUTORIZADO"
    )


def test_clasificar_timeout() -> None:
    assert clasificar_error(OperationalError("s", {}, _Orig("57014"))) == "TIMEOUT_TOOL"


def test_clasificar_error_no_conocido() -> None:
    assert clasificar_error(RuntimeError("boom")) == "ERROR_INTERNO"


# ---------------------------------------------------------------------------
# SEC-030 — el paquete nunca abre sesiones saltando la guarda de rol
# ---------------------------------------------------------------------------


def test_sesion_nucleo_aplica_la_guarda_antes_de_abrir_sesion(monkeypatch) -> None:
    """`sesion_nucleo` debe negarse si el rol del engine no es seguro.

    Se sustituye la guarda para probar el orden: si se abriera la `Session`
    primero, este test no lanzaría.
    """
    from app.core import database
    from fastapi import HTTPException

    def _revienta(engine) -> None:
        raise HTTPException(status_code=503, detail="nucleo_rls_inactivo")

    monkeypatch.setattr(database, "_asegurar_rol_nucleo", _revienta)
    with pytest.raises(HTTPException), database.sesion_nucleo():  # pragma: no cover
        pass


def test_el_paquete_agente_no_abre_sesiones_directas() -> None:
    """Ningún archivo del paquete puede usar `Session(get_engine_nucleo())`."""
    from pathlib import Path

    import app.nucleo.agente as paquete

    raiz = Path(paquete.__file__).parent
    ofensores = sorted(
        ruta.name
        for ruta in raiz.rglob("*.py")
        if "Session(get_engine_nucleo())" in ruta.read_text(encoding="utf-8")
    )
    assert ofensores == [], (
        "usar `sesion_nucleo()` (aplica la guarda de rol de core/database.py): "
        f"{ofensores}"
    )


def test_sec_032_nombre_de_tool_se_acota_y_sanea() -> None:
    from app.nucleo.agente.registry import _nombre_seguro

    largo = "despacho." + "x" * 5000
    assert len(_nombre_seguro(largo)) == 120
    assert "\n" not in _nombre_seguro("a\nb")
    assert _nombre_seguro("") == "<vacío>"
    assert _nombre_seguro(None) == "None"


def test_sec_034_motivo_no_expone_la_ruta_absoluta(monkeypatch) -> None:
    from app.nucleo.agente import registry as reg

    def _revienta(raiz, ejecutores):
        raise reg.ErrorManifiesto("V13", f"{raiz}/schemas/x.json", "boom")

    monkeypatch.setattr(reg, "cargar_modulo", _revienta)
    cargado = reg.cargar_registry(recargar=True)
    assert cargado.valido is False
    assert str(reg.RAIZ_PAQUETE) not in (cargado.motivo or "")
    assert "<paquete-agente>" in (cargado.motivo or "")
    reg._registry = None  # no contaminar el singleton de otros tests


def test_sec_036_registry_no_lanza_si_la_carga_falla_de_otra_forma(
    monkeypatch,
) -> None:
    from app.nucleo.agente import registry as reg

    def _revienta(raiz, ejecutores):
        raise RuntimeError("fallo inesperado del validador")

    monkeypatch.setattr(reg, "cargar_modulo", _revienta)
    cargado = reg.cargar_registry(recargar=True)
    assert cargado.valido is False
    assert cargado.tools_cargadas == 0
    assert "RuntimeError" in (cargado.motivo or "")
    reg._registry = None
