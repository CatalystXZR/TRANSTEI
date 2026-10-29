"""POD y evidencia de entrega (P0-06).

La firma y las fotos viven en Storage; la base guarda rutas, hash y metadatos.
Un POD no se borra: se reemplaza con una nueva versión auditada. Sin POD,
PostgreSQL bloquea el paso del viaje a `facturado`.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import (
    ConflictoConcurrencia,
    DatosInvalidos,
    RecursoNoEncontrado,
    ReglaNegocioViolada,
    traducir_integrity_error,
)
from app.nucleo.models import (
    EstadoViaje,
    POD,
    Viaje,
    ViajeEvento,
)
from app.nucleo.schemas import PODFotoOut, PODOut, PODUpdate
from app.nucleo.storage import (
    eliminar_archivo,
    ruta_archivo,
    subir_archivo,
    url_firmada,
    validar_archivo,
)
from app.nucleo.tiempo import ahora_utc

ESTADOS_POD = {
    EstadoViaje.en_ruta,
    EstadoViaje.en_descarga,
    EstadoViaje.descargado,
    EstadoViaje.pod_pendiente,
}
EXTENSIONES_FIRMA = {".png", ".jpg", ".jpeg", ".webp"}


class ServicioPOD:
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

    def _get_viaje(self, viaje_id: UUID) -> Viaje:
        viaje = self.session.exec(
            select(Viaje).where(
                Viaje.id == viaje_id, Viaje.empresa_id == self.empresa.id
            )
        ).first()
        if viaje is None:
            raise RecursoNoEncontrado(
                "Viaje no encontrado en la empresa.",
                contexto={"viaje_id": str(viaje_id)},
            )
        return viaje

    def _get_pod(self, viaje_id: UUID) -> POD | None:
        return self.session.exec(
            select(POD).where(
                POD.empresa_id == self.empresa.id, POD.viaje_id == viaje_id
            )
        ).first()

    def _validar_firma(self, nombre: str, contenido: bytes) -> str:
        if not contenido:
            raise DatosInvalidos("La firma está vacía.")
        ext = os.path.splitext(nombre)[1].lower()
        if ext not in EXTENSIONES_FIRMA:
            raise DatosInvalidos("La firma debe ser PNG, JPG, JPEG o WEBP.")
        if len(contenido) > 5 * 1024 * 1024:
            raise DatosInvalidos("La firma no puede superar 5 MB.")
        return ext

    def _foto_out(self, foto: dict[str, Any]) -> PODFotoOut:
        path = str(foto.get("path", ""))
        signed: str | None = None
        if path:
            try:
                signed = url_firmada(path)
            except Exception:
                signed = None
        return PODFotoOut(
            path=path,
            nombre=foto.get("nombre"),
            content_type=foto.get("content_type"),
            url_firmada=signed,
        )

    def _out(self, pod: POD) -> PODOut:
        firma = None
        try:
            firma = url_firmada(pod.firma_url)
        except Exception:
            firma = None
        return PODOut(
            id=pod.id,
            viaje_id=pod.viaje_id,
            receptor_nombre=pod.receptor_nombre,
            receptor_rut=pod.receptor_rut,
            receptor_cargo=pod.receptor_cargo,
            fecha_hora=pod.fecha_hora,
            lat=pod.lat,
            lon=pod.lon,
            firma_url=pod.firma_url,
            firma_url_firmada=firma,
            firma_hash=pod.firma_hash,
            fotos=[self._foto_out(f) for f in (pod.fotos or []) if isinstance(f, dict)],
            danios=pod.danios,
            observaciones=pod.observaciones,
            created_at=pod.created_at,
            created_by=pod.created_by,
            version=pod.version,
            facturacion_habilitada=True,
            mensaje="POD registrado: el viaje puede facturarse.",
        )

    def _agregar_evento(
        self, viaje: Viaje, tipo: str, descripcion: str, payload: dict[str, Any]
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

    def obtener(self, viaje_id: UUID) -> PODOut | None:
        viaje = self._get_viaje(viaje_id)
        pod = self._get_pod(viaje.id)
        return self._out(pod) if pod is not None else None

    def crear(
        self,
        viaje_id: UUID,
        *,
        receptor_nombre: str,
        receptor_rut: str | None,
        receptor_cargo: str | None,
        fecha_hora: datetime | None,
        lat: Decimal | None,
        lon: Decimal | None,
        danios: str | None,
        observaciones: str | None,
        firma_nombre: str,
        firma_contenido: bytes,
        firma_content_type: str | None,
        fotos: list[tuple[str, bytes, str | None]],
    ) -> PODOut:
        viaje = self._get_viaje(viaje_id)
        if viaje.estado not in ESTADOS_POD:
            raise ReglaNegocioViolada(
                f"El viaje está en estado {viaje.estado.value}; el POD se registra "
                "en ruta, en descarga, descargado o con POD pendiente."
            )
        if self._get_pod(viaje.id) is not None:
            raise ReglaNegocioViolada(
                "El viaje ya tiene POD. Use la actualización auditada para reemplazarlo."
            )
        if not receptor_nombre.strip():
            raise DatosInvalidos("El nombre del receptor es obligatorio.")
        ext_firma = self._validar_firma(firma_nombre, firma_contenido)
        for nombre, contenido, _ in fotos:
            validar_archivo(nombre, contenido)

        path_firma = ruta_archivo(
            "nucleo",
            str(self.empresa.id),
            "viajes",
            str(viaje.id),
            "pod",
            "firma",
            extension=ext_firma,
        )
        subidas: list[str] = [path_firma]
        try:
            subir_archivo(path_firma, firma_contenido, firma_content_type)
            metadatos_fotos: list[dict[str, Any]] = []
            for nombre, contenido, content_type in fotos:
                ext = validar_archivo(nombre, contenido)
                path = ruta_archivo(
                    "nucleo",
                    str(self.empresa.id),
                    "viajes",
                    str(viaje.id),
                    "pod",
                    "fotos",
                    extension=ext,
                )
                subir_archivo(path, contenido, content_type)
                subidas.append(path)
                metadatos_fotos.append(
                    {
                        "path": path,
                        "nombre": nombre,
                        "content_type": content_type,
                        "hash_sha256": hashlib.sha256(contenido).hexdigest(),
                    }
                )
        except Exception:
            for path in subidas:
                eliminar_archivo(path)
            raise

        self._fijar_contexto_bd()
        pod = POD(
            empresa_id=self.empresa.id,
            viaje_id=viaje.id,
            receptor_nombre=receptor_nombre.strip(),
            receptor_rut=(receptor_rut.strip() if receptor_rut else None),
            receptor_cargo=(receptor_cargo.strip() if receptor_cargo else None),
            fecha_hora=fecha_hora or ahora_utc(),
            lat=lat,
            lon=lon,
            firma_url=path_firma,
            firma_hash=hashlib.sha256(firma_contenido).hexdigest(),
            fotos=metadatos_fotos,
            danios=danios,
            observaciones=observaciones,
            created_by=self.contexto.auth_id,
        )
        try:
            self.session.add(pod)
            self._agregar_evento(
                viaje,
                "pod_registrado",
                f"POD registrado por {receptor_nombre.strip()}",
                {
                    "pod_id": str(pod.id),
                    "fotos": len(metadatos_fotos),
                    "fecha_hora": (fecha_hora or ahora_utc()).isoformat(),
                },
            )
            self.session.commit()
            self.session.refresh(pod)
        except IntegrityError as exc:
            self.session.rollback()
            for path in subidas:
                eliminar_archivo(path)
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            for path in subidas:
                eliminar_archivo(path)
            raise
        return self._out(pod)

    def actualizar(
        self,
        viaje_id: UUID,
        data: PODUpdate,
        *,
        firma_nombre: str | None = None,
        firma_contenido: bytes | None = None,
        firma_content_type: str | None = None,
        fotos: list[tuple[str, bytes, str | None]] | None = None,
    ) -> PODOut:
        viaje = self._get_viaje(viaje_id)
        pod = self._get_pod(viaje.id)
        if pod is None:
            raise RecursoNoEncontrado("El viaje no tiene POD registrado.")
        version = data.version if data.version is not None else pod.version
        if version != pod.version:
            raise ConflictoConcurrencia(
                "El POD fue modificado por otro usuario. Recargue e intente nuevamente."
            )

        valores: dict[str, Any] = {
            "receptor_nombre": data.receptor_nombre.strip(),
            "receptor_rut": data.receptor_rut.strip() if data.receptor_rut else None,
            "receptor_cargo": data.receptor_cargo.strip() if data.receptor_cargo else None,
            "danios": data.danios,
            "observaciones": data.observaciones,
            "fecha_hora": data.fecha_hora or pod.fecha_hora,
            "lat": data.lat if data.lat is not None else pod.lat,
            "lon": data.lon if data.lon is not None else pod.lon,
        }
        subidas: list[str] = []
        nuevas_fotos = list(pod.fotos or [])
        try:
            if firma_nombre and firma_contenido:
                ext = self._validar_firma(firma_nombre, firma_contenido)
                path = ruta_archivo(
                    "nucleo",
                    str(self.empresa.id),
                    "viajes",
                    str(viaje.id),
                    "pod",
                    "firma",
                    extension=ext,
                )
                subir_archivo(path, firma_contenido, firma_content_type)
                subidas.append(path)
                valores["firma_url"] = path
                valores["firma_hash"] = hashlib.sha256(firma_contenido).hexdigest()
            for nombre, contenido, content_type in fotos or []:
                ext = validar_archivo(nombre, contenido)
                path = ruta_archivo(
                    "nucleo",
                    str(self.empresa.id),
                    "viajes",
                    str(viaje.id),
                    "pod",
                    "fotos",
                    extension=ext,
                )
                subir_archivo(path, contenido, content_type)
                subidas.append(path)
                nuevas_fotos.append(
                    {
                        "path": path,
                        "nombre": nombre,
                        "content_type": content_type,
                        "hash_sha256": hashlib.sha256(contenido).hexdigest(),
                    }
                )
        except Exception:
            for path in subidas:
                eliminar_archivo(path)
            raise
        valores["fotos"] = nuevas_fotos

        self._fijar_contexto_bd()
        try:
            resultado = self.session.execute(
                update(POD)
                .where(
                    POD.id == pod.id,
                    POD.empresa_id == self.empresa.id,
                    POD.version == version,
                )
                .values(**valores)
            )
            if resultado.rowcount != 1:
                raise ConflictoConcurrencia("El POD fue modificado por otro usuario.")
            self._agregar_evento(
                viaje,
                "pod_actualizado",
                "POD actualizado (nueva versión)",
                {"pod_id": str(pod.id), "fotos": len(nuevas_fotos)},
            )
            self.session.commit()
            self.session.refresh(pod)
        except IntegrityError as exc:
            self.session.rollback()
            for path in subidas:
                eliminar_archivo(path)
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            for path in subidas:
                eliminar_archivo(path)
            raise
        return self._out(pod)
