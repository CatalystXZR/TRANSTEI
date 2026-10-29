"""Políticas duras de cumplimiento, capacidad y OC.

Estas funciones son puras y se prueban sin base de datos. El servicio las usa
para explicar al despachador POR QUÉ no puede asignar; los triggers de
PostgreSQL repiten las reglas como última línea de defensa.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from app.nucleo.models import (
    Chofer,
    Cliente,
    Empresa,
    EstadoOC,
    EstadoRecurso,
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


@dataclass(frozen=True, slots=True)
class RequisitoDocumento:
    tipo: TipoDocumento
    motivo: str
    condicional: bool = False


@dataclass(frozen=True, slots=True)
class Hallazgo:
    codigo: str
    mensaje: str
    bloqueante: bool = True
    recurso_tipo: TipoRecurso | None = None
    recurso_id: str | None = None


def documentos_requeridos(
    recurso_tipo: TipoRecurso,
    empresa: Empresa,
    *,
    carga_peligrosa: bool = False,
    refrigerada: bool = False,
) -> list[RequisitoDocumento]:
    """Documentos mínimos exigibles para despachar un recurso.

    La ausencia de un documento obligatorio se trata igual que un vencimiento:
    bloquea. No hay "documento pendiente" para un viaje que ya va a salir.
    """
    if recurso_tipo == TipoRecurso.tracto:
        req = [
            RequisitoDocumento(TipoDocumento.revision_tecnica, "Revisión técnica del tracto"),
            RequisitoDocumento(TipoDocumento.permiso_circulacion, "Permiso de circulación del tracto"),
            RequisitoDocumento(TipoDocumento.seguro_obligatorio, "Seguro obligatorio del tracto"),
        ]
        if empresa.exigir_soap:
            req.append(RequisitoDocumento(TipoDocumento.soap, "SOAP del tracto"))
        if carga_peligrosa:
            req.append(
                RequisitoDocumento(
                    TipoDocumento.permiso_carga_peligrosa,
                    "Permiso de carga peligrosa del tracto",
                    condicional=True,
                )
            )
        return req

    if recurso_tipo == TipoRecurso.rampla:
        req = [
            RequisitoDocumento(TipoDocumento.revision_tecnica, "Revisión técnica de la rampla"),
            RequisitoDocumento(TipoDocumento.permiso_circulacion, "Permiso de circulación de la rampla"),
        ]
        if empresa.exigir_seguro_carga:
            req.append(RequisitoDocumento(TipoDocumento.seguro_carga, "Seguro de carga"))
        if refrigerada:
            req.append(
                RequisitoDocumento(
                    TipoDocumento.certificado_gases,
                    "Certificado de gases de la rampla refrigerada",
                    condicional=True,
                )
            )
        if carga_peligrosa:
            req.append(
                RequisitoDocumento(
                    TipoDocumento.permiso_carga_peligrosa,
                    "Permiso de carga peligrosa de la rampla",
                    condicional=True,
                )
            )
        return req

    if recurso_tipo == TipoRecurso.chofer:
        req = [
            RequisitoDocumento(TipoDocumento.licencia_conducir, "Licencia de conducir"),
            RequisitoDocumento(TipoDocumento.examen_medico, "Examen médico ocupacional"),
        ]
        if carga_peligrosa and empresa.exigir_curso_carga_peligrosa:
            req.append(
                RequisitoDocumento(
                    TipoDocumento.curso_carga_peligrosa,
                    "Curso de carga peligrosa",
                    condicional=True,
                )
            )
        return req

    raise ValueError(f"Tipo de recurso no soportado: {recurso_tipo}")


def _estado_recurso_bloqueante(estado: EstadoRecurso) -> str | None:
    if estado == EstadoRecurso.baja:
        return "El recurso está dado de baja"
    if estado == EstadoRecurso.bloqueado:
        return "El recurso está bloqueado operativamente"
    return None


def validar_carga(
    viaje: Viaje,
    tracto: Tracto,
    rampla: Rampla,
    chofer: Chofer,
) -> list[Hallazgo]:
    """Capacidad, compatibilidad de rampla, temperatura y licencia."""
    errores: list[Hallazgo] = []

    for recurso, tipo, etiqueta in (
        (tracto, TipoRecurso.tracto, tracto.patente),
        (rampla, TipoRecurso.rampla, rampla.patente),
        (chofer, TipoRecurso.chofer, chofer.nombre),
    ):
        if not recurso.activo:
            errores.append(
                Hallazgo("RECURSO_INACTIVO", f"{etiqueta} está inactivo", True, tipo, str(recurso.id))
            )
        bloqueo = _estado_recurso_bloqueante(recurso.estado)
        if bloqueo:
            errores.append(Hallazgo("RECURSO_BLOQUEADO", f"{etiqueta}: {bloqueo}", True, tipo, str(recurso.id)))

    if viaje.peso_bruto_kg is None:
        errores.append(
            Hallazgo(
                "PESO_FALTANTE",
                "El viaje no tiene peso bruto de carga; no se puede validar capacidad",
                True,
                None,
                None,
            )
        )
    else:
        if tracto.capacidad_carga_kg <= 0:
            errores.append(
                Hallazgo("CAPACIDAD_TRACTO", "El tracto no tiene capacidad configurada", True, TipoRecurso.tracto, str(tracto.id))
            )
        elif viaje.peso_bruto_kg > tracto.capacidad_carga_kg:
            errores.append(
                Hallazgo(
                    "SOBREPESO_TRACTO",
                    f"Sobrepeso: {viaje.peso_bruto_kg} kg > capacidad del tracto "
                    f"{tracto.patente} ({tracto.capacidad_carga_kg} kg)",
                    True,
                    TipoRecurso.tracto,
                    str(tracto.id),
                )
            )
        if rampla.capacidad_carga_kg <= 0:
            errores.append(
                Hallazgo("CAPACIDAD_RAMPLA", "La rampla no tiene capacidad configurada", True, TipoRecurso.rampla, str(rampla.id))
            )
        elif viaje.peso_bruto_kg > rampla.capacidad_carga_kg:
            errores.append(
                Hallazgo(
                    "SOBREPESO_RAMPLA",
                    f"Sobrepeso: {viaje.peso_bruto_kg} kg > capacidad de la rampla "
                    f"{rampla.patente} ({rampla.capacidad_carga_kg} kg)",
                    True,
                    TipoRecurso.rampla,
                    str(rampla.id),
                )
            )

    if viaje.volumen_m3 is not None and rampla.volumen_m3 is not None:
        if viaje.volumen_m3 > rampla.volumen_m3:
            errores.append(
                Hallazgo(
                    "SOBREVOLUMEN",
                    f"Sobrevolumen: {viaje.volumen_m3} m3 > capacidad de la rampla "
                    f"{rampla.patente} ({rampla.volumen_m3} m3)",
                    True,
                    TipoRecurso.rampla,
                    str(rampla.id),
                )
            )

    if viaje.refrigerada:
        if rampla.tipo != TipoRampla.refrigerada:
            errores.append(
                Hallazgo(
                    "RAMPLA_NO_REFRIGERADA",
                    f"La carga es refrigerada y la rampla {rampla.patente} es {rampla.tipo.value}",
                    True,
                    TipoRecurso.rampla,
                    str(rampla.id),
                )
            )
        if viaje.temperatura_min_c is None or viaje.temperatura_max_c is None:
            errores.append(
                Hallazgo(
                    "TEMPERATURA_FALTANTE",
                    "La carga refrigerada requiere temperatura mínima y máxima",
                    True,
                    None,
                    None,
                )
            )
        else:
            if rampla.temperatura_min_c is not None and viaje.temperatura_min_c < rampla.temperatura_min_c:
                errores.append(
                    Hallazgo(
                        "TEMPERATURA_MINIMA",
                        f"Temperatura mínima {viaje.temperatura_min_c} °C bajo el límite "
                        f"de la rampla ({rampla.temperatura_min_c} °C)",
                        True,
                        TipoRecurso.rampla,
                        str(rampla.id),
                    )
                )
            if rampla.temperatura_max_c is not None and viaje.temperatura_max_c > rampla.temperatura_max_c:
                errores.append(
                    Hallazgo(
                        "TEMPERATURA_MAXIMA",
                        f"Temperatura máxima {viaje.temperatura_max_c} °C sobre el límite "
                        f"de la rampla ({rampla.temperatura_max_c} °C)",
                        True,
                        TipoRecurso.rampla,
                        str(rampla.id),
                    )
                )

    if viaje.tipo_carga == TipoCarga.contenedor and rampla.tipo != TipoRampla.portacontenedor:
        errores.append(
            Hallazgo(
                "RAMPLA_NO_CONTENEDOR",
                f"La carga es contenedor y la rampla {rampla.patente} es {rampla.tipo.value}",
                True,
                TipoRecurso.rampla,
                str(rampla.id),
            )
        )

    if viaje.sobredimensionada and rampla.tipo not in (TipoRampla.cama_baja, TipoRampla.plana):
        errores.append(
            Hallazgo(
                "RAMPLA_NO_SOBREDIMENSION",
                f"La carga sobredimensionada requiere rampla plana o cama baja; "
                f"{rampla.patente} es {rampla.tipo.value}",
                True,
                TipoRecurso.rampla,
                str(rampla.id),
            )
        )

    if viaje.carga_peligrosa:
        if not viaje.numero_un:
            errores.append(
                Hallazgo(
                    "UN_FALTANTE",
                    "La carga peligrosa requiere número UN",
                    True,
                    None,
                    None,
                )
            )
        if not chofer.autorizado_carga_peligrosa:
            errores.append(
                Hallazgo(
                    "CHOFER_NO_PELIGROSA",
                    f"El chofer {chofer.nombre} no está autorizado para carga peligrosa",
                    True,
                    TipoRecurso.chofer,
                    str(chofer.id),
                )
            )

    # R-02 (dueño, 2026-10-29): la única clase válida es A5 y es bloqueante.
    # La base lo impone en trg_viajes_03_licencia_a5; aquí se informa antes de
    # intentar la escritura para que la UI muestre el motivo.
    clase = (chofer.licencia_clase or "").strip().upper()
    if not clase:
        errores.append(
            Hallazgo(
                "LICENCIA_FALTANTE",
                f"El chofer {chofer.nombre} no tiene clase de licencia registrada "
                f"(se exige A5)",
                True,
                TipoRecurso.chofer,
                str(chofer.id),
            )
        )
    elif clase != "A5":
        errores.append(
            Hallazgo(
                "LICENCIA_NO_AUTORIZADA",
                f"Licencia {clase} no autorizada: se exige A5 "
                f"(chofer {chofer.nombre})",
                True,
                TipoRecurso.chofer,
                str(chofer.id),
            )
        )

    return errores


def validar_tarifa(
    viaje: Viaje,
    tarifa: Tarifa | None,
    fecha_local_viaje: date,
) -> list[Hallazgo]:
    if tarifa is None:
        return [
            Hallazgo(
                "TARIFA_FALTANTE",
                "El viaje no tiene tarifa asignada; no se puede despachar",
                True,
                None,
                None,
            )
        ]

    errores: list[Hallazgo] = []
    if not tarifa.activo:
        errores.append(Hallazgo("TARIFA_INACTIVA", f"La tarifa {tarifa.codigo} está inactiva"))
    if tarifa.cliente_id != viaje.cliente_id:
        errores.append(
            Hallazgo("TARIFA_OTRO_CLIENTE", f"La tarifa {tarifa.codigo} pertenece a otro cliente")
        )
    if tarifa.moneda != viaje.moneda:
        errores.append(
            Hallazgo(
                "TARIFA_MONEDA",
                f"La tarifa {tarifa.codigo} está en {tarifa.moneda} y el viaje en {viaje.moneda}",
            )
        )
    if fecha_local_viaje < tarifa.vigencia_desde:
        errores.append(
            Hallazgo(
                "TARIFA_NO_VIGENTE",
                f"La tarifa {tarifa.codigo} comienza a regir el {tarifa.vigencia_desde}",
            )
        )
    if tarifa.vigencia_hasta is not None and fecha_local_viaje > tarifa.vigencia_hasta:
        errores.append(
            Hallazgo(
                "TARIFA_VENCIDA",
                f"La tarifa {tarifa.codigo} venció el {tarifa.vigencia_hasta}",
            )
        )
    return errores


def validar_oc(
    viaje: Viaje,
    oc: OrdenCompra | None,
    cliente: Cliente,
    empresa: Empresa,
    *,
    consumo_neto: Decimal,
    fecha_local_viaje: date,
    fecha_local_fin: date | None = None,
) -> list[Hallazgo]:
    """Valida la OC vinculada y advierte si falta para facturar.

    Si no hay OC, el viaje puede despacharse pero no facturarse. Si hay OC,
    se valida cliente, moneda, vigencia y saldo. `consumo_neto` debe excluir
    el monto del viaje actual si ya estaba contabilizado en la OC.
    """
    if oc is None:
        # La OC es requisito de facturación, no de despacho. El trigger de
        # facturación impide pasar a 'facturado' sin ella.
        return [
            Hallazgo(
                "OC_PENDIENTE_FACTURACION",
                "El viaje no tiene OC: puede operar, pero no se podrá facturar "
                "hasta cargarla. Es un requisito de facturación, no de despacho.",
                False,
            )
        ]

    errores: list[Hallazgo] = []
    if oc.cliente_id != viaje.cliente_id:
        errores.append(Hallazgo("OC_OTRO_CLIENTE", f"La OC {oc.numero_oc} pertenece a otro cliente"))
    if oc.estado == EstadoOC.anulada:
        errores.append(Hallazgo("OC_ANULADA", f"La OC {oc.numero_oc} está anulada"))
    if oc.estado == EstadoOC.vencida:
        errores.append(Hallazgo("OC_VENCIDA", f"La OC {oc.numero_oc} está vencida"))
    if oc.moneda != viaje.moneda:
        errores.append(
            Hallazgo(
                "OC_MONEDA",
                f"La OC {oc.numero_oc} está en {oc.moneda} y el viaje en {viaje.moneda}",
            )
        )
    if fecha_local_viaje < oc.vigencia_desde or fecha_local_viaje > oc.vigencia_hasta:
        errores.append(
            Hallazgo(
                "OC_FUERA_VIGENCIA",
                f"La OC {oc.numero_oc} no está vigente para el {fecha_local_viaje} "
                f"({oc.vigencia_desde} a {oc.vigencia_hasta})",
            )
        )
    elif fecha_local_fin is not None and fecha_local_fin > oc.vigencia_hasta:
        errores.append(
            Hallazgo(
                "OC_FUERA_VIGENCIA_FIN",
                f"La OC {oc.numero_oc} vence el {oc.vigencia_hasta}, antes del fin "
                f"del viaje ({fecha_local_fin})",
            )
        )

    monto_viaje = (viaje.valor_flete_neto or Decimal("0")) + (viaje.monto_recargos or Decimal("0"))
    disponible = (oc.monto_autorizado or Decimal("0")) + (oc.sobregiro_autorizado or Decimal("0")) - consumo_neto
    if monto_viaje > disponible:
        errores.append(
            Hallazgo(
                "OC_SIN_SALDO",
                f"La OC {oc.numero_oc} no tiene saldo: viaje ${monto_viaje:,.0f}, "
                f"disponible ${disponible:,.0f}",
            )
        )
    return errores


def filtrar_bloqueantes(hallazgos: Iterable[Hallazgo]) -> list[Hallazgo]:
    return [h for h in hallazgos if h.bloqueante]
