"""Runtime de un turno del chat in-app.

Flujo (`ServicioChat.enviar`):

1. valida agente, permiso y API key (503 si falta);
2. obtiene/crea la conversación activa `(empresa, usuario, agente)`; un
   `conversacion_id` de otra empresa u otro usuario es 404;
3. aplica idempotencia por `(empresa, clave_idempotencia)`: un reintento devuelve
   el turno previo **sin** volver a llamar al LLM;
4. persiste el turno `user`, arma system prompt + últimos N mensajes;
5. itera hasta `AGENTE_LLM_MAX_ITERACIONES`: ejecuta tools (allowlist del agente,
   muro de pago y validación de argumentos), persiste el turno `tool` y repite;
6. cuando el modelo entrega contenido, persiste `assistant` y responde.

La transacción la cierra el endpoint: el runtime no hace `commit()` propio. Las
escrituras de tools usan `commit=False` y las confirma el endpoint del turno; si
algo falla, directiva, solicitud y memoria se revierten juntos. Nunca se persiste
ni se devuelve la API key.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings
from app.nucleo.agente.chat import capacidades
from app.nucleo.agente.chat import herramientas as registro
from app.nucleo.agente.chat import servicio_modulos
from app.nucleo.agente.chat.llm import (
    AgenteLLMError,
    AgenteNoConfigurado,
    ClienteLLM,
)
from app.nucleo.agente.chat.modelos import (
    LlamadaHerramienta,
    MensajeLLM,
)
from app.nucleo.agente.chat.personas import AGENTES, Persona
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import (
    AccesoDenegado,
    DatosInvalidos,
    ErrorNucleo,
    RecursoNoEncontrado,
)
from app.nucleo.permisos import tiene_permiso

# Errores de validación que no dejan la transacción de PostgreSQL abortada: se
# devuelven al modelo como resultado de la tool para que explique el problema.
_ERRORES_TOOL_EXPLICABLES = (DatosInvalidos, RecursoNoEncontrado, AccesoDenegado)


class ServicioChat:
    def __init__(
        self,
        session: Session,
        contexto: ContextoEmpresa,
        cliente_llm: ClienteLLM,
    ) -> None:
        self.session = session
        self.contexto = contexto
        self.cliente = cliente_llm

    # ------------------------------------------------------------------
    # Configuración por agente
    # ------------------------------------------------------------------
    @staticmethod
    def _api_key(persona: Persona) -> str:
        return str(getattr(settings, persona.api_key_setting, "") or "").strip()

    @staticmethod
    def _modelo(persona: Persona) -> str:
        modelo = str(getattr(settings, persona.modelo_setting, "") or "").strip()
        return modelo or "deepseek-chat"

    def agentes_disponibles(self) -> list[dict[str, Any]]:
        """Agentes, si su clave está configurada y sus tools efectivas.

        `herramientas` refleja las capacidades habilitadas para la empresa y el
        rol actual: el panel del chat no muestra tools que el turno rechazaría.
        """
        agentes = []
        for persona in AGENTES.values():
            habilitadas = capacidades.habilitadas(
                self.session, self.contexto, persona.clave
            )
            agentes.append(
                {
                    "clave": persona.clave,
                    "nombre": persona.nombre,
                    "configurado": bool(self._api_key(persona)),
                    "herramientas": [
                        nombre
                        for nombre in persona.tools
                        if nombre in registro.HERRAMIENTAS
                        and registro.HERRAMIENTAS[nombre].capacidad in habilitadas
                    ],
                }
            )
        return agentes

    # ------------------------------------------------------------------
    # Identidad / conversación
    # ------------------------------------------------------------------
    def _usuario_empresa_id(self) -> str:
        fila = self.session.execute(
            text(
                """
                select id::text
                  from nucleo.usuarios_empresa
                 where empresa_id = :empresa_id
                   and auth_id = :auth_id
                   and activo
                 limit 1
                """
            ),
            {
                "empresa_id": self.contexto.empresa_id,
                "auth_id": self.contexto.auth_id,
            },
        ).scalar_one_or_none()
        if fila is None:
            raise AccesoDenegado(
                "El usuario no tiene una membresía activa en la empresa."
            )
        return str(fila)

    def _conversacion(
        self, agente: str, conversacion_id: str | None, usuario: str
    ) -> str:
        if conversacion_id is not None:
            fila = self.session.execute(
                text(
                    """
                    select id::text
                      from nucleo.agente_chat_conversaciones
                     where empresa_id = :empresa_id
                       and id = :conversacion_id
                       and usuario_empresa_id = :usuario
                       and agente = :agente
                    """
                ),
                {
                    "empresa_id": self.contexto.empresa_id,
                    "conversacion_id": conversacion_id,
                    "usuario": usuario,
                    "agente": agente,
                },
            ).scalar_one_or_none()
            if fila is None:
                # 404 también para una conversación de otra empresa: no se
                # revela su existencia (§6.1).
                raise RecursoNoEncontrado("La conversación no existe.")
            return str(fila)

        fila = self.session.execute(
            text(
                """
                select id::text
                  from nucleo.agente_chat_conversaciones
                 where empresa_id = :empresa_id
                   and usuario_empresa_id = :usuario
                   and agente = :agente
                   and activa
                 limit 1
                """
            ),
            {
                "empresa_id": self.contexto.empresa_id,
                "usuario": usuario,
                "agente": agente,
            },
        ).scalar_one_or_none()
        if fila is not None:
            return str(fila)

        creada = self.session.execute(
            text(
                """
                insert into nucleo.agente_chat_conversaciones
                    (empresa_id, usuario_empresa_id, agente)
                values (:empresa_id, :usuario, :agente)
                on conflict (empresa_id, usuario_empresa_id, agente)
                    where activa
                do nothing
                returning id::text
                """
            ),
            {
                "empresa_id": self.contexto.empresa_id,
                "usuario": usuario,
                "agente": agente,
            },
        ).scalar_one_or_none()
        if creada is not None:
            return str(creada)
        # Carrera: otra conexión creó la conversación activa; se reutiliza.
        return str(
            self.session.execute(
                text(
                    """
                    select id::text
                      from nucleo.agente_chat_conversaciones
                     where empresa_id = :empresa_id
                       and usuario_empresa_id = :usuario
                       and agente = :agente
                       and activa
                     limit 1
                    """
                ),
                {
                    "empresa_id": self.contexto.empresa_id,
                    "usuario": usuario,
                    "agente": agente,
                },
            ).scalar_one()
        )

    # ------------------------------------------------------------------
    # Historial
    # ------------------------------------------------------------------
    def historial(self, conversacion_id: str) -> dict[str, Any]:
        usuario = self._usuario_empresa_id()
        conversacion = self.session.execute(
            text(
                """
                select id::text, agente, activa, abierta_en, cerrada_en,
                       resumen, resumen_en, version
                  from nucleo.agente_chat_conversaciones
                 where empresa_id = :empresa_id
                   and id = :conversacion_id
                   and usuario_empresa_id = :usuario
                """
            ),
            {
                "empresa_id": self.contexto.empresa_id,
                "conversacion_id": conversacion_id,
                "usuario": usuario,
            },
        ).mappings().first()
        if conversacion is None:
            raise RecursoNoEncontrado("La conversación no existe.")

        filas = self.session.execute(
            text(
                """
                select id::text, rol, contenido, tool_calls, tool_call_id,
                       nombre_herramienta, metadata, created_at
                  from nucleo.agente_chat_mensajes
                 where empresa_id = :empresa_id
                   and conversacion_id = :conversacion_id
                 order by created_at, id
                 limit 100
                """
            ),
            {
                "empresa_id": self.contexto.empresa_id,
                "conversacion_id": conversacion_id,
            },
        ).mappings()
        mensajes = [
            {
                "id": f["id"],
                "rol": f["rol"],
                "contenido": f["contenido"],
                "tool_calls": f["tool_calls"],
                "tool_call_id": f["tool_call_id"],
                "nombre_herramienta": f["nombre_herramienta"],
                "metadata": f["metadata"],
                "creado_en": _iso(f["created_at"]),
            }
            for f in filas
        ]
        return {
            "conversacion": {
                "id": conversacion["id"],
                "agente": conversacion["agente"],
                "activa": conversacion["activa"],
                "abierta_en": _iso(conversacion["abierta_en"]),
                "cerrada_en": _iso(conversacion["cerrada_en"]),
                "resumen": conversacion["resumen"],
                "resumen_en": _iso(conversacion["resumen_en"]),
                "version": conversacion["version"],
            },
            "mensajes": mensajes,
        }

    # ------------------------------------------------------------------
    # Persistencia de turnos
    # ------------------------------------------------------------------
    def _insertar_mensaje(
        self,
        *,
        conversacion_id: str,
        rol: str,
        contenido: str | None = None,
        tool_calls: list[LlamadaHerramienta] | None = None,
        tool_call_id: str | None = None,
        nombre_herramienta: str | None = None,
        clave_idempotencia: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        fila = self.session.execute(
            text(
                """
                insert into nucleo.agente_chat_mensajes
                    (empresa_id, conversacion_id, rol, contenido, tool_calls,
                     tool_call_id, nombre_herramienta, clave_idempotencia,
                     metadata, created_at)
                values
                    (:empresa_id, :conversacion_id, :rol, :contenido,
                     cast(:tool_calls as jsonb), :tool_call_id,
                     :nombre_herramienta, :clave, cast(:metadata as jsonb),
                     clock_timestamp())
                on conflict (empresa_id, clave_idempotencia)
                    where clave_idempotencia is not null
                do nothing
                returning id::text
                """
            ),
            {
                "empresa_id": self.contexto.empresa_id,
                "conversacion_id": conversacion_id,
                "rol": rol,
                "contenido": contenido,
                "tool_calls": None
                if not tool_calls
                else json.dumps(
                    [c.a_openai() for c in tool_calls], ensure_ascii=False
                ),
                "tool_call_id": tool_call_id,
                "nombre_herramienta": nombre_herramienta,
                "clave": clave_idempotencia,
                "metadata": json.dumps(metadata or {}, ensure_ascii=False),
            },
        ).scalar_one_or_none()
        return None if fila is None else str(fila)

    def _ultima_respuesta(
        self, conversacion_id: str, mensaje_usuario_id: str
    ) -> dict[str, Any] | None:
        fila = self.session.execute(
            text(
                """
                select a.id::text, a.contenido, a.metadata
                  from nucleo.agente_chat_mensajes a
                 where a.empresa_id = :empresa_id
                   and a.conversacion_id = :conversacion_id
                   and a.rol = 'assistant'
                   and a.contenido is not null
                   and a.created_at >= (
                       select u.created_at
                         from nucleo.agente_chat_mensajes u
                        where u.empresa_id = :empresa_id and u.id = :usuario_id
                   )
                 order by a.created_at desc, a.id desc
                 limit 1
                """
            ),
            {
                "empresa_id": self.contexto.empresa_id,
                "conversacion_id": conversacion_id,
                "usuario_id": mensaje_usuario_id,
            },
        ).mappings().first()
        if fila is None:
            return None
        metadata = fila["metadata"] if isinstance(fila["metadata"], dict) else {}
        return {
            "id": fila["id"],
            "respuesta": fila["contenido"] or "",
            "herramientas": metadata.get("herramientas") or [],
            "upsell": metadata.get("upsell"),
        }

    def _previa_por_clave(
        self, clave: str, usuario: str
    ) -> tuple[str, str, dict[str, Any]] | None:
        fila = self.session.execute(
            text(
                """
                select m.id::text as mensaje_id,
                       m.conversacion_id::text as conversacion_id,
                       m.metadata
                  from nucleo.agente_chat_mensajes m
                  join nucleo.agente_chat_conversaciones c
                    on c.empresa_id = m.empresa_id
                   and c.id = m.conversacion_id
                 where m.empresa_id = :empresa_id
                   and m.clave_idempotencia = :clave
                   and c.usuario_empresa_id = :usuario
                 limit 1
                """
            ),
            {
                "empresa_id": self.contexto.empresa_id,
                "clave": clave,
                "usuario": usuario,
            },
        ).mappings().first()
        if fila is None:
            return None
        metadata = fila["metadata"] if isinstance(fila["metadata"], dict) else {}
        return str(fila["conversacion_id"]), str(fila["mensaje_id"]), metadata

    # ------------------------------------------------------------------
    # Contexto del sistema
    # ------------------------------------------------------------------
    def _system_prompt(self, persona: Persona) -> str:
        partes = [persona.system_prompt, "", "# Contexto de la empresa (solo lectura)"]

        empresa = getattr(self.contexto.empresa, "razon_social", "la empresa")
        partes.append(f"Empresa: {empresa}.")

        configuracion = registro.configuracion_vigente(
            self.session, self.contexto.empresa_id
        )
        if configuracion:
            partes.append(
                "Configuración vigente: "
                + ", ".join(
                    f"{c['clave']}={_corto(c['valor'])}" for c in configuracion
                )
                + "."
            )
        else:
            partes.append("Configuración vigente: sin claves registradas.")

        reglas = registro.reglas_abiertas(
            self.session, self.contexto.empresa_id, limit=50
        )
        if reglas:
            partes.append(
                "Reglas abiertas: "
                + "; ".join(
                    f"{r['entidad']}:{r['clave']}={_corto(r['valor'])}"
                    for r in reglas
                )
                + "."
            )
        else:
            partes.append("Reglas abiertas: ninguna.")

        modulos_activos = [
            modulo
            for modulo in servicio_modulos.MODULOS
            if servicio_modulos.estado(self.session, self.contexto, modulo)[
                "activo"
            ]
        ]
        partes.append(
            "Módulos premium activos: "
            + (", ".join(modulos_activos) if modulos_activos else "ninguno")
            + "."
        )
        return "\n".join(partes)

    # ------------------------------------------------------------------
    # Turno
    # ------------------------------------------------------------------
    def enviar(
        self,
        agente: str,
        mensaje: str,
        *,
        conversacion_id: str | None = None,
        clave_idempotencia: str | None = None,
    ) -> dict[str, Any]:
        persona = AGENTES.get(agente)
        if persona is None:
            raise DatosInvalidos(
                "Agente no válido.",
                contexto={"agentes": sorted(AGENTES)},
            )
        if not tiene_permiso(self.contexto.rol, persona.permiso):
            raise AccesoDenegado(
                "Su rol no permite usar el chat del agente.",
                contexto={"permiso_requerido": persona.permiso},
            )

        texto = (mensaje or "").strip()
        if not texto:
            raise DatosInvalidos("El mensaje no puede estar vacío.")
        if len(texto) > 4000:
            raise DatosInvalidos("El mensaje supera 4000 caracteres.")

        api_key = self._api_key(persona)
        if not api_key:
            raise AgenteNoConfigurado(
                f"El agente {persona.nombre} no tiene una API key configurada "
                "en el servidor.",
                contexto={"agente": persona.clave},
            )

        usuario = self._usuario_empresa_id()
        clave = (clave_idempotencia or "").strip() or None
        hash_mensaje = hashlib.sha256(
            f"{agente}\n{texto}".encode()
        ).hexdigest()

        if clave is not None:
            previa = self._previa_por_clave(clave, usuario)
            if previa is not None:
                conv_previa, msg_usuario, metadata_previa = previa
                if metadata_previa.get("hash") not in (None, hash_mensaje):
                    raise DatosInvalidos(
                        "La clave de idempotencia ya se usó con otro mensaje."
                    )
                respuesta = self._ultima_respuesta(conv_previa, msg_usuario)
                if respuesta is not None:
                    return {
                        "conversacion_id": conv_previa,
                        "mensaje_id": respuesta["id"],
                        "agente": persona.clave,
                        "respuesta": respuesta["respuesta"],
                        "herramientas": respuesta["herramientas"],
                        "upsell": respuesta["upsell"],
                    }

        conv = self._conversacion(agente, conversacion_id, usuario)
        mensaje_usuario_id = self._insertar_mensaje(
            conversacion_id=conv,
            rol="user",
            contenido=texto,
            clave_idempotencia=clave,
            metadata={"hash": hash_mensaje},
        )
        if mensaje_usuario_id is None:
            # Carrera con la misma clave: devolver el turno ya persistido.
            previa = self._previa_por_clave(clave or "", usuario)
            if previa is not None:
                if previa[2].get("hash") not in (None, hash_mensaje):
                    raise DatosInvalidos(
                        "La clave de idempotencia ya se usó con otro mensaje."
                    )
                respuesta = self._ultima_respuesta(previa[0], previa[1])
                if respuesta is not None:
                    return {
                        "conversacion_id": previa[0],
                        "mensaje_id": respuesta["id"],
                        "agente": persona.clave,
                        "respuesta": respuesta["respuesta"],
                        "herramientas": respuesta["herramientas"],
                        "upsell": respuesta["upsell"],
                    }
            raise AgenteLLMError(
                "El turno se está procesando en otra solicitud. Reintente."
            )

        mensajes = [MensajeLLM(role="system", content=self._system_prompt(persona))]
        mensajes.extend(self._historial_llm(conv))
        # Capacidades efectivas del turno: intersección de catálogo, agente,
        # permiso humano, módulo activo y override/default de la empresa. Se
        # calcula una vez y se usa tanto para las especificaciones que ve el
        # modelo como para autorizar cada ejecución.
        habilitadas = capacidades.habilitadas(
            self.session, self.contexto, persona.clave
        )
        especificaciones = registro.especificaciones(persona.tools, habilitadas)
        modelo = self._modelo(persona)
        max_iteraciones = max(1, int(settings.AGENTE_LLM_MAX_ITERACIONES))
        # SEC-065: el proveedor LLM elige cuántas tools trae una respuesta. Se
        # acota por respuesta y por turno para que un proveedor comprometido o un
        # prompt injection no cree/altere N registros en una sola petición.
        max_tools_respuesta = max(1, int(settings.AGENTE_LLM_MAX_TOOL_CALLS))
        max_tools_turno = max(1, int(settings.AGENTE_LLM_MAX_TOOL_CALLS_TURNO))
        tools_ejecutadas = 0

        herramientas: list[dict[str, Any]] = []
        upsell: dict[str, Any] | None = None
        # SEC-062: deduplicación por turno. Si el modelo repite exactamente la
        # misma tool con los mismos argumentos (dos `tool_call` o un reintento
        # dentro del turno), se ejecuta una sola vez y se reutiliza el resultado.
        # El proveedor exige una respuesta por cada `tool_call_id`, así que el
        # mensaje `tool` se persiste igual para cada llamada.
        resultados_por_firma: dict[tuple[str, str], dict[str, Any]] = {}

        for _ in range(max_iteraciones):
            respuesta = self.cliente.responder(
                mensajes,
                especificaciones,
                api_key=api_key,
                modelo=modelo,
            )

            if len(respuesta.llamadas) > max_tools_respuesta:
                raise AgenteLLMError(
                    "El asistente intentó ejecutar demasiadas acciones en un "
                    "solo paso. Reformule la petición en partes más pequeñas."
                )
            tools_ejecutadas += len(respuesta.llamadas)
            if tools_ejecutadas > max_tools_turno:
                raise AgenteLLMError(
                    "El asistente superó el máximo de acciones por turno. "
                    "Reformule la petición en partes más pequeñas."
                )

            if respuesta.llamadas:
                self._insertar_mensaje(
                    conversacion_id=conv,
                    rol="assistant",
                    contenido=limpiar_respuesta(respuesta.contenido or ""),
                    tool_calls=respuesta.llamadas,
                    metadata={"usage": respuesta.usage} if respuesta.usage else None,
                )
                mensajes.append(
                    MensajeLLM(
                        role="assistant",
                        content=respuesta.contenido,
                        tool_calls=respuesta.llamadas,
                    )
                )
                for llamada in respuesta.llamadas:
                    firma = (
                        llamada.nombre,
                        json.dumps(
                            llamada.argumentos,
                            sort_keys=True,
                            default=str,
                        ),
                    )
                    if firma in resultados_por_firma:
                        resultado = copy.deepcopy(
                            resultados_por_firma[firma]
                        )
                    else:
                        resultado = self._ejecutar_tool(
                            persona, llamada, habilitadas
                        )
                        resultados_por_firma[firma] = copy.deepcopy(resultado)
                    estado = str(resultado.pop("estado_tool", "ok"))
                    resumen = resultado.pop("resumen", None)
                    if estado == "upsell" and upsell is None:
                        upsell = {
                            "modulo": resultado.get("modulo"),
                            "mensaje": resultado.get("mensaje")
                            or resultado.get("mensaje_upsell"),
                        }
                    herramientas.append(
                        {
                            "nombre": llamada.nombre,
                            "estado": estado,
                            "resumen": _resumen_tool(resumen, resultado),
                        }
                    )
                    self._insertar_mensaje(
                        conversacion_id=conv,
                        rol="tool",
                        contenido=json.dumps(
                            resultado, ensure_ascii=False, default=str
                        ),
                        tool_call_id=llamada.id,
                        nombre_herramienta=llamada.nombre,
                    )
                    mensajes.append(
                        MensajeLLM(
                            role="tool",
                            content=json.dumps(
                                resultado, ensure_ascii=False, default=str
                            ),
                            tool_call_id=llamada.id,
                            name=llamada.nombre,
                        )
                    )
                continue

            contenido = limpiar_respuesta(respuesta.contenido or "")
            if contenido:
                mensaje_id = self._insertar_mensaje(
                    conversacion_id=conv,
                    rol="assistant",
                    contenido=contenido,
                    metadata={
                        "herramientas": herramientas,
                        "upsell": upsell,
                        "usage": respuesta.usage,
                    },
                )
                return {
                    "conversacion_id": conv,
                    "mensaje_id": mensaje_id,
                    "agente": persona.clave,
                    "respuesta": contenido,
                    "herramientas": herramientas,
                    "upsell": upsell,
                }

        # Se agotaron las iteraciones sin una respuesta textual: no se inventa
        # un "listo". La excepción la traduce el endpoint a un 502 explicable.
        raise AgenteLLMError(
            "El asistente no logró completar la solicitud en el número máximo "
            "de pasos. Reformule la petición o intente nuevamente."
        )

    def _ejecutar_tool(
        self,
        persona: Persona,
        llamada: LlamadaHerramienta,
        habilitadas: frozenset[str],
    ) -> dict[str, Any]:
        herramienta = registro.HERRAMIENTAS.get(llamada.nombre)
        if (
            herramienta is None
            or llamada.nombre not in persona.tools
            or herramienta.agente != persona.clave
        ):
            return {
                "estado_tool": "error",
                "mensaje": "La herramienta no está permitida para este agente.",
            }

        capacidad = capacidades.obtener(herramienta.capacidad)
        if capacidad is None:
            # Tool mal registrada: se falla cerrado, nunca se ejecuta.
            return {
                "estado_tool": "error",
                "mensaje": "Esa capacidad no está habilitada para este agente.",
            }
        if persona.clave not in capacidad.agentes:
            # Límite duro: una fila `habilitada=true` no concede lo que el
            # catálogo prohíbe para el agente (p. ej. finanzas a la secretaria).
            return {
                "estado_tool": "error",
                "mensaje": "Esa capacidad no está habilitada para este agente.",
            }
        if not tiene_permiso(self.contexto.rol, capacidad.permiso):
            # Defensa en profundidad: `habilitadas` ya filtró por permiso, pero
            # el permiso se vuelve a exigir justo antes de ejecutar.
            return {
                "estado_tool": "error",
                "mensaje": "Esa capacidad no está habilitada para este agente.",
            }

        # El muro de pago se evalúa antes del override: `habilitadas()` excluye
        # las capacidades con módulo inactivo, pero la respuesta correcta para el
        # chat es `upsell` (no ejecutar), no un error genérico. SEC-052 depende
        # de este orden.
        if herramienta.modulo is not None:
            estado = servicio_modulos.estado(
                self.session, self.contexto, herramienta.modulo
            )
            if not estado["activo"]:
                return {
                    **estado,
                    "mensaje": estado["mensaje_upsell"],
                    "estado_tool": "upsell",
                }

        if capacidad.clave not in habilitadas:
            return {
                "estado_tool": "error",
                "mensaje": "Esa capacidad no está habilitada para este agente.",
            }

        try:
            resultado = herramienta.ejecutar(
                self.session, self.contexto, llamada.argumentos
            )
        except _ERRORES_TOOL_EXPLICABLES as exc:
            # Validación/alcance: no hay violación de PostgreSQL, la transacción
            # sigue utilizable y el modelo puede explicar el problema.
            if not self.session.is_active:
                # Un IntegrityError traducido a DatosInvalidos deja la
                # transacción abortada; continuar rompería el siguiente INSERT.
                # Se propaga para que el endpoint haga rollback del turno.
                raise
            return {"estado_tool": "error", "mensaje": exc.mensaje}
        except ErrorNucleo:
            # Un error de base deja la transacción abortada: se propaga para que
            # el endpoint haga rollback (no se continúa sobre una conexión rota).
            raise
        return resultado if isinstance(resultado, dict) else {
            "resultado": resultado,
            "estado_tool": "ok",
        }

    def _historial_llm(self, conversacion_id: str) -> list[MensajeLLM]:
        limite = max(1, int(settings.AGENTE_LLM_MAX_MENSAJES_CONTEXTO))
        filas = self.session.execute(
            text(
                """
                select rol, contenido, tool_calls, tool_call_id,
                       nombre_herramienta
                  from (
                        select rol, contenido, tool_calls, tool_call_id,
                               nombre_herramienta, created_at, id
                          from nucleo.agente_chat_mensajes
                         where empresa_id = :empresa_id
                           and conversacion_id = :conversacion_id
                         order by created_at desc, id desc
                         limit :limite
                  ) recientes
                 order by created_at, id
                """
            ),
            {
                "empresa_id": self.contexto.empresa_id,
                "conversacion_id": conversacion_id,
                "limite": limite,
            },
        ).mappings()
        salida: list[MensajeLLM] = []
        for fila in filas:
            llamadas: list[LlamadaHerramienta] = []
            crudas = fila["tool_calls"]
            if isinstance(crudas, list):
                for cruda in crudas:
                    if not isinstance(cruda, dict):
                        continue
                    funcion = cruda.get("function") or {}
                    argumentos = funcion.get("arguments")
                    if isinstance(argumentos, str):
                        try:
                            argumentos = json.loads(argumentos)
                        except json.JSONDecodeError:
                            argumentos = {}
                    llamadas.append(
                        LlamadaHerramienta(
                            id=str(cruda.get("id", "")),
                            nombre=str(funcion.get("name", "")),
                            argumentos=argumentos
                            if isinstance(argumentos, dict)
                            else {},
                        )
                    )
            salida.append(
                MensajeLLM(
                    role=str(fila["rol"]),
                    content=fila["contenido"],
                    tool_calls=llamadas,
                    tool_call_id=fila["tool_call_id"],
                    name=fila["nombre_herramienta"],
                )
            )
        return salida


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def limpiar_respuesta(texto: str) -> str:
    """Quita el formato que delata al modelo y las claves internas.

    El chat se lee como una conversación, no como un documento: se eliminan
    negritas, backticks, encabezados y viñetas iniciales; las claves
    `directiva_*` se reemplazan por una expresión natural para no exponer el
    nombre técnico. No se recorta contenido legítimo.
    """
    if not texto:
        return ""
    limpio = texto.replace("\r\n", "\n").replace("\r", "\n")
    # Encabezados markdown al inicio de una línea (### Título -> Título).
    limpio = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", limpio)
    # Negritas, cursivas con guiones bajos y backticks.
    limpio = limpio.replace("**", "").replace("__", "").replace("`", "")
    # Viñetas iniciales: "- ", "* ", "• ", "– " y numeradas "1. ".
    limpio = re.sub(r"(?m)^\s{0,3}(?:[-*•–]|\d{1,2}[.)])\s+", "", limpio)
    # Claves internas: el usuario no necesita ver `directiva_horario`.
    limpio = re.sub(r"directiva_[a-z0-9_]+", "la instrucción", limpio)
    # Más de dos saltos de línea seguidos no aportan nada en el chat.
    limpio = re.sub(r"\n{3,}", "\n\n", limpio)
    return limpio.strip()


def _corto(valor: Any, limite: int = 80) -> str:
    texto = json.dumps(valor, ensure_ascii=False, default=str)
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def _resumen_tool(resumen: Any, resultado: dict[str, Any]) -> str:
    if isinstance(resumen, str) and resumen:
        return resumen[:200]
    mensaje = resultado.get("mensaje")
    if isinstance(mensaje, str) and mensaje:
        return mensaje[:200]
    return "Herramienta ejecutada."


def _iso(valor: Any) -> Any:
    if valor is None:
        return None
    try:
        return valor.isoformat().replace("+00:00", "Z")
    except AttributeError:
        return str(valor)
