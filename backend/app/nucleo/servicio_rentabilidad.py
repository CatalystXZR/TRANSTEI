"""Margen, tarifa piso y Freight Score v1 (P0-09).

El cálculo se hace siempre en backend, con parámetros explícitos y explicación
por componente. La tarifa piso estratégica cubre costo total + margen objetivo;
la táctica cubre costos variables + contribución mínima.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import (
    ConflictoConcurrencia,
    DatosInvalidos,
    RecursoNoEncontrado,
    traducir_integrity_error,
)
from app.nucleo.models import (
    Cliente,
    ConfiguracionCostos,
    EstadoViaje,
    Rampla,
    Tracto,
    Viaje,
)
from app.nucleo.schemas import (
    ComponenteFreightScoreOut,
    ConfiguracionCostosOut,
    ConfiguracionCostosUpdate,
    ResultadoRentabilidadOut,
    RentabilidadViajeOut,
    SimulacionFlete,
)
from app.nucleo.servicio_gastos import ServicioGastos
from app.nucleo.tiempo import ahora_utc

PESOS = {
    "margen_pct": Decimal("0.30"),
    "margen_km": Decimal("0.20"),
    "pago": Decimal("0.15"),
    "utilizacion": Decimal("0.15"),
    "retorno": Decimal("0.10"),
    "riesgo": Decimal("0.10"),
}

RETORNO_SCORE = {
    "cargado_completo": Decimal("1.00"),
    "parcial": Decimal("0.60"),
    "vacio_cercano": Decimal("0.30"),
    "vacio_sin_alternativa": Decimal("0.00"),
    "no_aplica": Decimal("0.30"),
}


def _clamp(valor: Decimal) -> Decimal:
    return max(Decimal("0"), min(Decimal("1"), valor))


def _d(valor: Decimal | int | str | None) -> Decimal:
    return Decimal(valor or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _score_pago(dias: int) -> tuple[Decimal, str]:
    if dias <= 30:
        return Decimal("1.00"), "≤ 30 días: 1,00"
    if dias <= 45:
        return Decimal("0.70"), "31–45 días: 0,70"
    if dias <= 60:
        return Decimal("0.40"), "46–60 días: 0,40"
    if dias <= 90:
        return Decimal("0.20"), "61–90 días: 0,20"
    return Decimal("0.00"), "> 90 días: 0,00"


class ServicioRentabilidad:
    def __init__(self, session: Session, contexto: ContextoEmpresa) -> None:
        self.session = session
        self.contexto = contexto
        self.empresa = contexto.empresa

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

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------
    def _config_modelo(self) -> ConfiguracionCostos | None:
        return self.session.exec(
            select(ConfiguracionCostos).where(
                ConfiguracionCostos.empresa_id == self.empresa.id
            )
        ).first()

    def obtener_config(self) -> ConfiguracionCostosOut:
        config = self._config_modelo()
        if config is None:
            base = ConfiguracionCostosOut()
            return base
        return ConfiguracionCostosOut(
            id=config.id,
            configurado=True,
            costo_fijo_mensual=config.costo_fijo_mensual,
            viajes_estimados_mes=config.viajes_estimados_mes,
            margen_objetivo=config.margen_objetivo,
            benchmark_margen_km=config.benchmark_margen_km,
            contribucion_minima=config.contribucion_minima,
            costo_variable_km_estandar=config.costo_variable_km_estandar,
            rendimiento_km_l=config.rendimiento_km_l,
            precio_diesel=config.precio_diesel,
            version=config.version,
            updated_at=config.updated_at,
        )

    def guardar_config(self, data: ConfiguracionCostosUpdate) -> ConfiguracionCostosOut:
        config = self._config_modelo()
        self._fijar_contexto_bd()
        if config is None:
            config = ConfiguracionCostos(
                empresa_id=self.empresa.id,
                **data.model_dump(exclude={"version"}),
            )
            try:
                self.session.add(config)
                self.session.commit()
                self.session.refresh(config)
            except IntegrityError as exc:
                self.session.rollback()
                raise traducir_integrity_error(exc) from exc
            except Exception:
                self.session.rollback()
                raise
            return self.obtener_config()
        version = data.version if data.version is not None else config.version
        if version != config.version:
            raise ConflictoConcurrencia(
                "La configuración de costos fue modificada por otro usuario. Recargue e intente nuevamente."
            )
        try:
            resultado = self.session.execute(
                update(ConfiguracionCostos)
                .where(
                    ConfiguracionCostos.id == config.id,
                    ConfiguracionCostos.empresa_id == self.empresa.id,
                    ConfiguracionCostos.version == version,
                )
                .values(**data.model_dump(exclude={"version"}))
            )
            if resultado.rowcount != 1:
                raise ConflictoConcurrencia(
                    "La configuración fue modificada por otro usuario."
                )
            self.session.commit()
            self.session.refresh(config)
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise
        return self.obtener_config()

    # ------------------------------------------------------------------
    # Cálculo
    # ------------------------------------------------------------------
    def _resultado(
        self,
        *,
        ingreso: Decimal,
        costo_variable: Decimal,
        costo_fijo_asignado: Decimal,
        km_totales: Decimal,
        dias_pago: int,
        utilizacion: Decimal,
        retorno: str,
        riesgo_puntos: int,
    ) -> ResultadoRentabilidadOut:
        config = self.obtener_config()
        margen = _d(ingreso - costo_variable)
        margen_pct = (
            (margen / ingreso).quantize(Decimal("0.0001")) if ingreso > 0 else Decimal("0")
        )
        margen_km = (
            (margen / km_totales).quantize(Decimal("0.01"))
            if km_totales > 0
            else Decimal("0")
        )
        costo_total = _d(costo_variable + costo_fijo_asignado)
        objetivo = config.margen_objetivo
        piso_estrategico = (
            (costo_total / (Decimal("1") - objetivo)).quantize(Decimal("0.01"))
            if objetivo < 1
            else costo_total
        )
        piso_tactico = _d(costo_variable + config.contribucion_minima)

        score_margen_pct = (
            _clamp(margen_pct / objetivo) if objetivo > 0 else Decimal("1")
        )
        score_margen_km = (
            _clamp(margen_km / config.benchmark_margen_km)
            if config.benchmark_margen_km > 0
            else Decimal("1")
        )
        score_pago, detalle_pago = _score_pago(dias_pago)
        score_utilizacion = _clamp(utilizacion)
        score_retorno = RETORNO_SCORE.get(retorno, Decimal("0.30"))
        score_riesgo = _clamp(Decimal("1") - (Decimal(riesgo_puntos) / Decimal("10")))

        definiciones = [
            ("margen_pct", "Margen de contribución %", score_margen_pct,
             f"Margen {margen_pct * 100:.2f}% / objetivo {objetivo * 100:.0f}%"),
            ("margen_km", "Margen por km", score_margen_km,
             f"${margen_km:,.0f}/km / benchmark ${config.benchmark_margen_km:,.0f}/km"),
            ("pago", "Comportamiento de pago", score_pago, detalle_pago),
            ("utilizacion", "Utilización de capacidad", score_utilizacion,
             f"{utilizacion * 100:.1f}% de la capacidad"),
            ("retorno", "Retorno / backhaul", score_retorno,
             retorno.replace("_", " ")),
            ("riesgo", "Riesgo operativo", score_riesgo,
             f"{riesgo_puntos} punto(s) de riesgo"),
        ]
        componentes: list[ComponenteFreightScoreOut] = []
        total = Decimal("0")
        for codigo, nombre, score, detalle in definiciones:
            peso = PESOS[codigo]
            aporte = (score * peso * 100).quantize(Decimal("0.1"))
            total += aporte
            componentes.append(
                ComponenteFreightScoreOut(
                    codigo=codigo,
                    nombre=nombre,
                    score=score.quantize(Decimal("0.0001")),
                    peso=peso,
                    aporte=aporte,
                    detalle=detalle,
                )
            )
        total = total.quantize(Decimal("0.01"))
        semaforo = "verde" if total >= 80 else "amarillo" if total >= 60 else "rojo"
        explicacion = [
            f"Ingreso del viaje: ${ingreso:,.2f}.",
            f"Costo variable: ${costo_variable:,.2f}; costo fijo asignado: ${costo_fijo_asignado:,.2f}.",
            f"Margen de contribución: ${margen:,.2f} ({margen_pct * 100:.2f}%).",
            f"Tarifa piso estratégica: ${piso_estrategico:,.2f} (costo total / (1 - margen objetivo)).",
            f"Tarifa piso táctica: ${piso_tactico:,.2f} (costos variables + contribución mínima).",
            f"Freight Score: {total}/100 → {semaforo}.",
        ]
        if total < 60:
            explicacion.append(
                "Score rojo: rechazar o aprobar solo el dueño con justificación escrita."
            )
        elif total < 80:
            explicacion.append(
                "Score amarillo: negociar precio, plazo de pago o retorno antes de aceptar."
            )
        if not config.configurado:
            explicacion.append(
                "La empresa aún no guarda configuración de costos; se usan valores por defecto."
            )
        return ResultadoRentabilidadOut(
            ingreso_total=_d(ingreso),
            costo_variable=_d(costo_variable),
            costo_fijo_asignado=_d(costo_fijo_asignado),
            costo_total=costo_total,
            margen=margen,
            margen_pct=margen_pct,
            margen_km=margen_km,
            km_totales=km_totales,
            tarifa_piso_estrategica=piso_estrategico,
            tarifa_piso_tactica=piso_tactico,
            score=total,
            semaforo=semaforo,
            componentes=componentes,
            explicacion=explicacion,
            margen_objetivo=objetivo,
            benchmark_margen_km=config.benchmark_margen_km,
            configurado=config.configurado,
        )

    def simular(self, data: SimulacionFlete) -> ResultadoRentabilidadOut:
        config = self.obtener_config()
        km_totales = data.distancia_km + data.km_vacios
        costo_variable = (
            data.costos_variables
            if data.costos_variables is not None
            else (km_totales * config.costo_variable_km_estandar).quantize(
                Decimal("0.01")
            )
        )
        fijo = (
            config.costo_fijo_mensual / Decimal(config.viajes_estimados_mes)
        ).quantize(Decimal("0.01"))
        utilizacion = (
            Decimal(data.peso_kg) / Decimal(data.capacidad_kg)
            if data.capacidad_kg and data.capacidad_kg > 0
            else Decimal("0")
        )
        return self._resultado(
            ingreso=data.flete_neto,
            costo_variable=costo_variable,
            costo_fijo_asignado=fijo,
            km_totales=km_totales,
            dias_pago=data.dias_pago,
            utilizacion=utilizacion,
            retorno=data.retorno,
            riesgo_puntos=data.riesgo_puntos,
        )

    def rentabilidad_viaje(self, viaje_id: UUID) -> RentabilidadViajeOut:
        viaje = self.session.exec(
            select(Viaje).where(
                Viaje.id == viaje_id, Viaje.empresa_id == self.empresa.id
            )
        ).first()
        if viaje is None:
            raise RecursoNoEncontrado("Viaje no encontrado en la empresa.")
        if viaje.estado == EstadoViaje.anulado:
            raise DatosInvalidos("El viaje está anulado; no tiene rentabilidad operativa.")
        config = self.obtener_config()
        costos = ServicioGastos(self.session, self.contexto).costos(viaje.id)
        cliente = self.session.get(Cliente, viaje.cliente_id)
        km_base = viaje.distancia_km or costos.km_recorridos or Decimal("0")
        km_vacios = viaje.km_vacios or Decimal("0")
        km_totales = km_base + km_vacios
        estimado = (km_totales * config.costo_variable_km_estandar).quantize(
            Decimal("0.01")
        )
        if costos.gastos_aprobados > 0:
            costo_variable = costos.costo_variable
            fuente = "real"
        else:
            costo_variable = estimado + costos.comision_estimada
            fuente = "estandar"
        fijo = (
            config.costo_fijo_mensual / Decimal(config.viajes_estimados_mes)
        ).quantize(Decimal("0.01"))
        capacidad = Decimal("0")
        if viaje.rampla_id is not None:
            rampla = self.session.get(Rampla, viaje.rampla_id)
            if rampla is not None:
                capacidad = rampla.capacidad_carga_kg or Decimal("0")
        if capacidad <= 0 and viaje.tracto_id is not None:
            tracto = self.session.get(Tracto, viaje.tracto_id)
            if tracto is not None:
                capacidad = tracto.capacidad_carga_kg or Decimal("0")
        utilizacion = (
            Decimal(viaje.peso_bruto_kg or 0) / capacidad if capacidad > 0 else Decimal("0")
        )
        dias_pago = (
            viaje.condiciones_pago_dias
            if viaje.condiciones_pago_dias is not None
            else (cliente.dias_pago if cliente is not None else 30)
        )
        if viaje.km_vacios is None:
            retorno = "vacio_cercano"
        else:
            ratio = km_vacios / km_base if km_base > 0 else Decimal("0")
            if km_vacios <= 0:
                retorno = "cargado_completo"
            elif ratio <= Decimal("0.1"):
                retorno = "parcial"
            elif ratio <= Decimal("0.35"):
                retorno = "vacio_cercano"
            else:
                retorno = "vacio_sin_alternativa"
        riesgo = 0
        if viaje.carga_peligrosa:
            riesgo += 3
        if viaje.sobredimensionada:
            riesgo += 2
        if viaje.refrigerada:
            riesgo += 1

        resultado = self._resultado(
            ingreso=costos.ingreso_total,
            costo_variable=costo_variable,
            costo_fijo_asignado=fijo,
            km_totales=km_totales,
            dias_pago=dias_pago,
            utilizacion=utilizacion,
            retorno=retorno,
            riesgo_puntos=riesgo,
        )
        # Persistir el score para tableros y alertas; no bloquea la respuesta.
        try:
            self.session.execute(
                update(Viaje)
                .where(Viaje.id == viaje.id, Viaje.empresa_id == self.empresa.id)
                .values(
                    freight_score_estimado=resultado.score,
                    freight_score_detalle={
                        "score": str(resultado.score),
                        "semaforo": resultado.semaforo,
                        "componentes": [
                            c.model_dump(mode="json") for c in resultado.componentes
                        ],
                        "calculado_en": ahora_utc().isoformat(),
                        "fuente_costos": fuente,
                    },
                )
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
        return RentabilidadViajeOut(
            **resultado.model_dump(),
            viaje_id=viaje.id,
            numero_viaje=viaje.numero_viaje or "",
            fuente_costos=fuente,
            cliente_nombre=cliente.razon_social if cliente is not None else "-",
            distancia_km=viaje.distancia_km,
            km_vacios=viaje.km_vacios,
        )
