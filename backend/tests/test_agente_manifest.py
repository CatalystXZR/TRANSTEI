"""Pruebas unitarias del manifiesto del agente (contrato §2.4, V1–V16).

No tocan la base ni la red: copian el paquete real a `tmp_path` y mutan una
copia. Cada caso declara la regla que espera, porque el diagnóstico honesto es
parte del contrato (un V2 genérico no dice qué arreglar).
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from app.nucleo.agente.ejecutores import EJECUTORES
from app.nucleo.agente.manifest import (
    RAIZ_PAQUETE,
    EntradaInvalida,
    ErrorManifiesto,
    cargar_modulo,
    validar_instancia,
)


def _copiar_paquete(tmp_path: Path) -> Path:
    destino = tmp_path / "agente"
    shutil.copytree(
        RAIZ_PAQUETE,
        destino,
        ignore=shutil.ignore_patterns("__pycache__", "*.py", "*.pyc"),
    )
    return destino


def _leer(ruta: Path) -> Any:
    return json.loads(ruta.read_text(encoding="utf-8"))


def _escribir(ruta: Path, datos: Any) -> None:
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def _mutar(ruta: Path, fn: Callable[[Any], None]) -> None:
    datos = _leer(ruta)
    fn(datos)
    _escribir(ruta, datos)


def _regla(paquete: Path) -> str:
    with pytest.raises(ErrorManifiesto) as exc:
        cargar_modulo(paquete, EJECUTORES)
    return exc.value.regla


def _primer_descriptor(paquete: Path) -> Path:
    return paquete / "tools" / "despacho.mis_fletes.json"


# ---------------------------------------------------------------------------
# Caso válido
# ---------------------------------------------------------------------------


def test_manifiesto_real_es_valido() -> None:
    modulo = cargar_modulo(RAIZ_PAQUETE, EJECUTORES)
    assert set(modulo.descriptores) == {
        "despacho.mis_fletes",
        "despacho.mis_viajes_asignados",
        "despacho.viajes_del_dia",
    }
    assert modulo.manifiesto.habilitado_por_defecto is False
    assert modulo.manifiesto.schema_di == "di/v1"
    assert set(modulo.esquemas_entrada) == set(modulo.descriptores)


# ---------------------------------------------------------------------------
# V1–V4
# ---------------------------------------------------------------------------


def test_v1_rechaza_claves_duplicadas(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    ruta = paquete / "manifest.json"
    texto = ruta.read_text(encoding="utf-8")
    texto = texto.replace(
        '"modulo_id": "agente-whatsapp",',
        '"modulo_id": "agente-whatsapp", "modulo_id": "agente-whatsapp",',
        1,
    )
    ruta.write_text(texto, encoding="utf-8")
    assert _regla(paquete) == "V1"


def test_v2_rechaza_campo_desconocido(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(paquete / "manifest.json", lambda d: d.update({"campo_nuevo": 1}))
    assert _regla(paquete) == "V2"


def test_v2_rechaza_schema_incorrecto(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(paquete / "manifest.json", lambda d: d.update({"schema": "otro/v9"}))
    assert _regla(paquete) == "V2"


def test_v3_habilitado_por_defecto_no_se_degrada(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(
        paquete / "manifest.json",
        lambda d: d.update({"habilitado_por_defecto": True}),
    )
    assert _regla(paquete) == "V3"


def test_v4_schema_di(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(paquete / "manifest.json", lambda d: d.update({"schema_di": "di/v2"}))
    assert _regla(paquete) == "V4"


# ---------------------------------------------------------------------------
# V5–V12
# ---------------------------------------------------------------------------


def test_v5_ref_con_dos_puntos(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(
        paquete / "manifest.json",
        lambda d: d["tools"][0].update({"$ref": "../tools/despacho.mis_fletes.json"}),
    )
    assert _regla(paquete) == "V5"


def test_v5_ref_inexistente(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(
        paquete / "manifest.json",
        lambda d: d["tools"][0].update({"$ref": "tools/no_existe.json"}),
    )
    assert _regla(paquete) == "V5"


def test_v6_nombre_duplicado(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(
        paquete / "manifest.json",
        lambda d: d["tools"].append({"$ref": "tools/despacho.mis_fletes.json"}),
    )
    assert _regla(paquete) == "V6"


def test_v7_componente_fuera_del_manifiesto(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(
        _primer_descriptor(paquete),
        lambda d: d.update({"componente": "inexistente"}),
    )
    assert _regla(paquete) == "V7"


def test_v8_rol_fuera_del_manifiesto(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(_primer_descriptor(paquete), lambda d: d.update({"roles": ["gerente"]}))
    assert _regla(paquete) == "V8"


def test_v9_permiso_debe_derivarse(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(
        _primer_descriptor(paquete),
        lambda d: d.update({"permiso": "despacho:otra.cosa"}),
    )
    assert _regla(paquete) == "V9"


def test_v10_ejecutor_fuera_de_allow_list(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(
        _primer_descriptor(paquete),
        lambda d: d.update({"ejecutor": "os_system"}),
    )
    assert _regla(paquete) == "V10"


def test_v11_timeout_fuera_de_rango(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(_primer_descriptor(paquete), lambda d: d.update({"timeout_ms": 50}))
    assert _regla(paquete) == "V11"


def test_v11_lectura_exige_max_filas(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(_primer_descriptor(paquete), lambda d: d.update({"max_filas": None}))
    assert _regla(paquete) == "V11"


def test_v12_escritura_exige_modo_clave(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(
        _primer_descriptor(paquete),
        lambda d: d.update(
            {
                "tipo": "escritura_solicitud",
                "max_filas": None,
                "idempotencia": {"modo": "ninguna", "campo": None},
            }
        ),
    )
    assert _regla(paquete) == "V12"


def test_v12_escritura_exige_campo_en_entrada(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(
        _primer_descriptor(paquete),
        lambda d: d.update(
            {
                "tipo": "escritura_solicitud",
                "max_filas": None,
                "idempotencia": {
                    "modo": "clave",
                    "campo": "clave_idempotencia",
                },
            }
        ),
    )
    assert _regla(paquete) == "V12"


# ---------------------------------------------------------------------------
# V13–V16 y §3.3
# ---------------------------------------------------------------------------


def test_v13_keyword_no_soportada_falla_cerrado(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(
        paquete / "schemas" / "despacho.mis_fletes.entrada.json",
        lambda d: d.update({"uniqueItems": True}),
    )
    assert _regla(paquete) == "V13"


def test_v13_objeto_sin_additional_properties_false(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(
        paquete / "schemas" / "despacho.mis_fletes.entrada.json",
        lambda d: d.pop("additionalProperties"),
    )
    assert _regla(paquete) == "V13"


def test_v14_alcance_propio_no_admite_cliente_id(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(
        paquete / "schemas" / "despacho.mis_fletes.entrada.json",
        lambda d: d["properties"].update({"cliente_id": {"type": "string"}}),
    )
    assert _regla(paquete) == "V14"


def test_entrada_no_admite_campos_de_sql(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(
        paquete / "schemas" / "despacho.mis_fletes.entrada.json",
        lambda d: d["properties"].update({"sql": {"type": "string"}}),
    )
    assert _regla(paquete) == "V13"


def test_v15_permiso_de_modulo_fuera_del_conjunto(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(
        paquete / "manifest.json",
        lambda d: d["permisos_modulo"].append("agente:todo"),
    )
    assert _regla(paquete) == "V15"


def test_v15_autoaprobacion_prohibida(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(
        paquete / "manifest.json",
        lambda d: d["aprobacion"].update({"autoaprobacion": True}),
    )
    assert _regla(paquete) == "V15"


def test_v16_modalidad_sin_modelo(tmp_path: Path) -> None:
    paquete = _copiar_paquete(tmp_path)
    _mutar(
        paquete / "manifest.json",
        lambda d: (
            d["modalidades"].update({"pdf": True}),
            d["modelos"].pop("pdf"),
        ),
    )
    assert _regla(paquete) == "V16"


# ---------------------------------------------------------------------------
# Validación de instancias (entrada/salida)
# ---------------------------------------------------------------------------


def _schema_entrada_c1() -> dict[str, Any]:
    modulo = cargar_modulo(RAIZ_PAQUETE, EJECUTORES)
    return modulo.esquemas_entrada["despacho.mis_fletes"]


def test_entrada_valida_acepta_solo_lo_declarado() -> None:
    validar_instancia(_schema_entrada_c1(), {})
    validar_instancia(_schema_entrada_c1(), {"limite": 10, "estado": "en_ruta"})


def test_entrada_invalida_campo_extra() -> None:
    with pytest.raises(EntradaInvalida) as exc:
        validar_instancia(
            _schema_entrada_c1(), {"cliente_id": "11111111-1111-1111-1111-111111111111"}
        )
    assert "no declarados" in str(exc.value)


def test_entrada_invalida_limite_fuera_de_rango() -> None:
    with pytest.raises(EntradaInvalida) as exc:
        validar_instancia(_schema_entrada_c1(), {"limite": 0})
    assert exc.value.campo == "$.limite"


def test_entrada_invalida_estado_fuera_de_enum() -> None:
    with pytest.raises(EntradaInvalida):
        validar_instancia(_schema_entrada_c1(), {"estado": "inventado"})


def test_entrada_invalida_fecha_sin_zona() -> None:
    with pytest.raises(EntradaInvalida):
        validar_instancia(_schema_entrada_c1(), {"desde": "2026-10-31T10:00:00"})


def test_entrada_valida_fecha_con_zona() -> None:
    validar_instancia(
        _schema_entrada_c1(), {"desde": "2026-10-31T10:00:00Z"}
    )
    validar_instancia(
        _schema_entrada_c1(), {"hasta": "2026-10-31T10:00:00-03:00"}
    )


def test_sec_035_cliente_id_anidado_tambien_se_rechaza(tmp_path: Path) -> None:
    """SEC-035: la prohibición de campos de autoridad no es solo de primer nivel."""
    paquete = _copiar_paquete(tmp_path)
    _mutar(
        paquete / "schemas" / "despacho.mis_fletes.entrada.json",
        lambda d: d["properties"].update(
            {
                "filtro": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"cliente_id": {"type": "string"}},
                }
            }
        ),
    )
    assert _regla(paquete) == "V14"
