"""Gastos del viaje, combustible, peajes y costo real (P0-08)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import (
    AccesoDenegado,
    ConflictoConcurrencia,
    DatosInvalidos,
    RecursoNoEncontrado,
    ReglaNegocioViolada,
    traducir_integrity_error,
)
from app.nucleo.models import (
    Chofer,
    EstadoViaje,
    PrecioDiesel,
    RolEmpresa,
    Viaje,
    ViajeEvento,
    ViajeGasto,
)
from app.nucleo.schemas import (
    AprobarGasto,
    CostoPorTipoOut,
    CostosViajeOut,
    GastoCreate,
    GastoOut,
    PrecioDieselCreate,
    PrecioDieselOut,
    RechazarGasto,
)
from app.nucleo.storage import (
    eliminar_archivo,
    ruta_archivo,
    subir_archivo,
    url_firmada,
    validar_archivo,
)
from app.nucleo.tiempo import ahora_utc

CENTAVO = Decimal("0.01")
ROLES_APRUEBAN_GASTO = {
    RolEmpresa.admin,
    RolEmpresa.gerente,
    RolEmpresa.contador,
    RolEmpresa.tesoreria,
}
ESTADOS_GASTO = {"pendiente", "aprobado", "rechazado"}


def _d(valor: Decimal | int | str | None) -> Decimal:
    return Decimal(valor or 0).quantize(CENTAVO, rounding=ROUND_HALF_UP)


class ServicioGastos:
    def __init__(self, session: Session, contexto: ContextoEmpresa) -> None:
        self.session = session
        self.contexto = contexto
        self.empresa = contexto.empresa

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _fijar_contexto_bd(self) -> None:
        self.session.execute(
            text("select set_config('nucleo.auth_id', :auth_id, true)"),
            {"auth_id": self.contexto.auth_id},
        )
        if self.contexto.request_id:
            self.session.execute(
                text("select set_config('nucleo.request_id', :request_id, true)"),
                {"request_id": self.contexto.request_id},
            )

    def _get_viaje(self, viaje_id: UUID) -> Viaje:
        viaje = self.session.exec(
            select(Viaje).where(
                Viaje.id == viaje_id, Viaje.empresa_id == self.empresa.id
            )
        ).first()
        if viaje is None:
            raise RecursoNoEncontrado("Viaje no encontrado en la empresa.")
        return viaje

    def _get_gasto(self, gasto_id: UUID) -> ViajeGasto:
        gasto = self.session.get(ViajeGasto, gasto_id)
        if gasto is None or gasto.empresa_id != self.empresa.id:
            raise RecursoNoEncontrado("Gasto no encontrado en la empresa.")
        return gasto

    def _gasto_out(self, gasto: ViajeGasto) -> GastoOut:
        firmada = None
        if gasto.comprobante_url:
            try:
                firmada = url_firmada(gasto.comprobante_url)
            except Exception:
                firmada = None
        return GastoOut(
            id=gasto.id,
            viaje_id=gasto.viaje_id,
            tipo=gasto.tipo,
            proveedor=gasto.proveedor,
            numero_documento=gasto.numero_documento,
            fecha=gasto.fecha,
            monto_total=gasto.monto_total,
            iva=gasto.iva,
            monto_neto=_d(gasto.monto_neto),
            moneda=gasto.moneda,
            litros=gasto.litros,
            precio_litro=gasto.precio_litro,
            km_odometro=gasto.km_odometro,
            estacion=gasto.estacion,
            tag=gasto.tag,
            comprobante_url=gasto.comprobante_url,
            comprobante_url_firmada=firmada,
            estado=gasto.estado,
            motivo_rechazo=gasto.motivo_rechazo,
            aprobado_por=gasto.aprobado_por,
            aprobado_en=gasto.aprobado_en,
            observaciones=gasto.observaciones,
            activo=gasto.activo,
            created_at=gasto.created_at,
            created_by=gasto.created_by,
            version=gasto.version,
        )

    def _agregar_evento(
        self, viaje: Viaje, tipo: str, descripcion: str, payload: dict
    ) -> None:
        self.session.add(
            ViajeEvento(
                empresa_id=self.empresa.id,
                viaje_id=viaje.id,
                tipo=tipo,
                descripcion=descripcion,
                ocurrido_en=ahora_utc(),
                payload=payload,
                auth_id=self.contexto.auth_id,
            )
        )

    def _validar_aprobador(self, gasto: ViajeGasto) -> None:
        if self.contexto.rol not in ROLES_APRUEBAN_GASTO:
            raise AccesoDenegado(
                "Su rol no permite aprobar o rechazar gastos.",
                contexto={"rol": self.contexto.rol.value},
            )
        if gasto.created_by == self.contexto.auth_id:
            raise AccesoDenegado(
                "Quien registra un gasto no puede aprobarlo; se requiere otro usuario. "
                "Es una regla de segregación de funciones."
            )

    # ------------------------------------------------------------------
    # Precio diésel
    # ------------------------------------------------------------------
    def listar_precios(self, *, limite: int = 60) -> list[PrecioDieselOut]:
        precios = self.session.exec(
            select(PrecioDiesel)
            .where(PrecioDiesel.empresa_id == self.empresa.id)
            .order_by(PrecioDiesel.fecha.desc())
            .limit(limite)
        ).all()
        return [
            PrecioDieselOut(
                id=p.id,
                fecha=p.fecha,
                precio_litro=p.precio_litro,
                fuente=p.fuente,
                created_at=p.created_at,
            )
            for p in precios
        ]

    def precio_vigente(self, fecha: date | None = None) -> PrecioDieselOut | None:
        filtros = [PrecioDiesel.empresa_id == self.empresa.id]
        if fecha is not None:
            filtros.append(PrecioDiesel.fecha <= fecha)
        precio = self.session.exec(
            select(PrecioDiesel).where(*filtros).order_by(PrecioDiesel.fecha.desc()).limit(1)
        ).first()
        if precio is None:
            return None
        return PrecioDieselOut(
            id=precio.id,
            fecha=precio.fecha,
            precio_litro=precio.precio_litro,
            fuente=precio.fuente,
            created_at=precio.created_at,
        )

    def crear_precio(self, data: PrecioDieselCreate) -> PrecioDieselOut:
        self._fijar_contexto_bd()
        precio = PrecioDiesel(
            empresa_id=self.empresa.id,
            fecha=data.fecha,
            precio_litro=data.precio_litro,
            fuente=data.fuente,
        )
        try:
            self.session.add(precio)
            self.session.commit()
            self.session.refresh(precio)
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return PrecioDieselOut(
            id=precio.id,
            fecha=precio.fecha,
            precio_litro=precio.precio_litro,
            fuente=precio.fuente,
            created_at=precio.created_at,
        )

    # ------------------------------------------------------------------
    # Gastos
    # ------------------------------------------------------------------
    def listar_gastos(
        self,
        viaje_id: UUID,
        *,
        estado: str | None = None,
        incluir_inactivos: bool = False,
    ) -> list[GastoOut]:
        viaje = self._get_viaje(viaje_id)
        filtros = [
            ViajeGasto.empresa_id == self.empresa.id,
            ViajeGasto.viaje_id == viaje.id,
        ]
        if estado is not None:
            if estado not in ESTADOS_GASTO:
                raise DatosInvalidos("Estado de gasto no válido.")
            filtros.append(ViajeGasto.estado == estado)
        if not incluir_inactivos:
            filtros.append(ViajeGasto.activo == True)  # noqa: E712
        gastos = self.session.exec(
            select(ViajeGasto)
            .where(*filtros)
            .order_by(ViajeGasto.fecha.desc(), ViajeGasto.created_at.desc())
        ).all()
        return [self._gasto_out(g) for g in gastos]

    def crear_gasto(self, viaje_id: UUID, data: GastoCreate) -> GastoOut:
        viaje = self._get_viaje(viaje_id)
        if viaje.estado in (EstadoViaje.anulado, EstadoViaje.facturado, EstadoViaje.cobrado):
            raise ReglaNegocioViolada(
                f"El viaje está en {viaje.estado.value}; no admite gastos nuevos."
            )
        if data.moneda != self.empresa.moneda:
            raise DatosInvalidos(
                f"El gasto debe estar en la moneda de la empresa ({self.empresa.moneda})."
            )
        precio = data.precio_litro
        if data.tipo == "combustible":
            if data.litros is None:
                raise DatosInvalidos("El gasto de combustible requiere litros.")
            if precio is None:
                vigente = self.precio_vigente(data.fecha)
                precio = vigente.precio_litro if vigente is not None else None
        self._fijar_contexto_bd()
        gasto = ViajeGasto(
            empresa_id=self.empresa.id,
            viaje_id=viaje.id,
            tipo=data.tipo,
            proveedor=data.proveedor,
            numero_documento=data.numero_documento,
            fecha=data.fecha,
            monto_total=data.monto_total,
            iva=data.iva,
            moneda=data.moneda,
            litros=data.litros,
            precio_litro=precio,
            km_odometro=data.km_odometro,
            estacion=data.estacion,
            tag=data.tag,
            observaciones=data.observaciones,
            estado="pendiente",
            activo=True,
            created_by=self.contexto.auth_id,
        )
        try:
            self.session.add(gasto)
            self._agregar_evento(
                viaje,
                "gasto_registrado",
                f"Gasto {data.tipo} por ${data.monto_total:,.2f}",
                {"gasto_id": str(gasto.id), "tipo": data.tipo},
            )
            self.session.commit()
            self.session.refresh(gasto)
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return self._gasto_out(gasto)

    def adjuntar_comprobante(
        self,
        gasto_id: UUID,
        *,
        nombre_archivo: str,
        contenido: bytes,
        content_type: str | None,
    ) -> GastoOut:
        gasto = self._get_gasto(gasto_id)
        if gasto.estado != "pendiente":
            raise ReglaNegocioViolada(
                "Solo se puede adjuntar respaldo a un gasto pendiente."
            )
        ext = validar_archivo(nombre_archivo, contenido)
        path = ruta_archivo(
            "nucleo",
            str(self.empresa.id),
            "viajes",
            str(gasto.viaje_id),
            "gastos",
            extension=ext,
        )
        subir_archivo(path, contenido, content_type)
        self._fijar_contexto_bd()
        try:
            gasto.comprobante_url = path
            self.session.add(gasto)
            self.session.commit()
            self.session.refresh(gasto)
        except Exception:
            self.session.rollback()
            eliminar_archivo(path)
            raise
        return self._gasto_out(gasto)

    def aprobar_gasto(self, gasto_id: UUID, data: AprobarGasto) -> GastoOut:
        gasto = self._get_gasto(gasto_id)
        self._validar_aprobador(gasto)
        if gasto.estado != "pendiente":
            raise ReglaNegocioViolada(
                f"El gasto está {gasto.estado}; solo se aprueba desde pendiente."
            )
        viaje = self._get_viaje(gasto.viaje_id)
        self._fijar_contexto_bd()
        try:
            resultado = self.session.execute(
                update(ViajeGasto)
                .where(
                    ViajeGasto.id == gasto.id,
                    ViajeGasto.empresa_id == self.empresa.id,
                    ViajeGasto.version == gasto.version,
                )
                .values(
                    estado="aprobado",
                    aprobado_por=self.contexto.auth_id,
                    aprobado_en=ahora_utc(),
                    observaciones=data.observacion or gasto.observaciones,
                )
            )
            if resultado.rowcount != 1:
                raise ConflictoConcurrencia(
                    "El gasto fue modificado por otro usuario. Recargue e intente nuevamente."
                )
            self._agregar_evento(
                viaje,
                "gasto_aprobado",
                f"Gasto {gasto.tipo} aprobado por ${gasto.monto_total:,.2f}",
                {"gasto_id": str(gasto.id), "monto": str(gasto.monto_total)},
            )
            self.session.commit()
            self.session.refresh(gasto)
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return self._gasto_out(gasto)

    def rechazar_gasto(self, gasto_id: UUID, data: RechazarGasto) -> GastoOut:
        gasto = self._get_gasto(gasto_id)
        self._validar_aprobador(gasto)
        if gasto.estado != "pendiente":
            raise ReglaNegocioViolada(
                f"El gasto está {gasto.estado}; solo se rechaza desde pendiente."
            )
        viaje = self._get_viaje(gasto.viaje_id)
        self._fijar_contexto_bd()
        try:
            resultado = self.session.execute(
                update(ViajeGasto)
                .where(
                    ViajeGasto.id == gasto.id,
                    ViajeGasto.empresa_id == self.empresa.id,
                    ViajeGasto.version == gasto.version,
                )
                .values(
                    estado="rechazado",
                    motivo_rechazo=data.motivo.strip(),
                    aprobado_por=self.contexto.auth_id,
                    aprobado_en=ahora_utc(),
                )
            )
            if resultado.rowcount != 1:
                raise ConflictoConcurrencia(
                    "El gasto fue modificado por otro usuario. Recargue e intente nuevamente."
                )
            self._agregar_evento(
                viaje,
                "gasto_rechazado",
                f"Gasto {gasto.tipo} rechazado: {data.motivo.strip()}",
                {"gasto_id": str(gasto.id)},
            )
            self.session.commit()
            self.session.refresh(gasto)
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return self._gasto_out(gasto)

    # ------------------------------------------------------------------
    # Costos
    # ------------------------------------------------------------------
    def costos(self, viaje_id: UUID) -> CostosViajeOut:
        viaje = self._get_viaje(viaje_id)
        gastos = self.session.exec(
            select(ViajeGasto).where(
                ViajeGasto.empresa_id == self.empresa.id,
                ViajeGasto.viaje_id == viaje.id,
                ViajeGasto.activo == True,  # noqa: E712
            )
        ).all()
        aprobados = [g for g in gastos if g.estado == "aprobado"]
        pendientes = [g for g in gastos if g.estado == "pendiente"]
        gastos_aprobados = sum((_d(g.monto_neto) for g in aprobados), Decimal("0"))
        gastos_pendientes = sum((_d(g.monto_total) for g in pendientes), Decimal("0"))
        litros = sum((g.litros or Decimal("0") for g in aprobados), Decimal("0"))
        odometros = [g.km_odometro for g in aprobados if g.km_odometro is not None]
        km = viaje.distancia_km
        if km is None and len(odometros) >= 2:
            km = max(odometros) - min(odometros)
        ingreso = _d(viaje.monto_total_neto or (viaje.valor_flete_neto + viaje.monto_recargos))
        comision = Decimal("0")
        if viaje.chofer_id is not None:
            chofer = self.session.get(Chofer, viaje.chofer_id)
            if chofer is not None:
                comision = _d(ingreso * (chofer.porcentaje_comision or Decimal("0")))
        costo_variable = _d(gastos_aprobados + comision)
        costo_total = costo_variable
        margen = _d(ingreso - costo_total)
        margen_pct = (
            (margen / ingreso * 100).quantize(Decimal("0.01")) if ingreso > 0 else Decimal("0")
        )
        por_tipo: list[CostoPorTipoOut] = []
        for tipo in sorted({g.tipo for g in aprobados}):
            del_tipo = [g for g in aprobados if g.tipo == tipo]
            por_tipo.append(
                CostoPorTipoOut(
                    tipo=tipo,
                    cantidad=len(del_tipo),
                    monto=sum((_d(g.monto_neto) for g in del_tipo), Decimal("0")),
                )
            )
        rendimiento = (
            (km / litros).quantize(Decimal("0.01")) if km and litros > 0 else None
        )
        costo_km = (
            (costo_total / km).quantize(Decimal("0.01")) if km and km > 0 else None
        )
        return CostosViajeOut(
            viaje_id=viaje.id,
            flete_neto=_d(viaje.valor_flete_neto),
            recargos=_d(viaje.monto_recargos),
            ingreso_total=ingreso,
            gastos_aprobados=_d(gastos_aprobados),
            gastos_pendientes=_d(gastos_pendientes),
            comision_estimada=comision,
            costo_variable=costo_variable,
            costo_total=costo_total,
            margen=margen,
            margen_pct=margen_pct,
            litros=litros.quantize(Decimal("0.001")),
            km_recorridos=km,
            rendimiento_km_l=rendimiento,
            costo_por_km=costo_km,
            por_tipo=por_tipo,
            actualizado_en=viaje.costo_actualizado_en,
            mensaje=(
                "Costo calculado con gastos aprobados y comisión del chofer."
                if aprobados
                else "Aún no hay gastos aprobados; el costo solo incluye la comisión."
            ),
        )
