"""CRUD de maestros del núcleo y documentos versionados.

Reglas:
- Toda consulta y escritura se filtra por la empresa del contexto.
- Las actualizaciones usan bloqueo optimista por `version`.
- Los maestros no se borran: se desactivan.
- Un recurso con reservas futuras no se puede desactivar.
- Los documentos no se borran: se versionan; el archivo vive en Storage.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, text, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.config import settings
from app.nucleo.deps import ContextoEmpresa
from app.nucleo.errores import (
    ConflictoConcurrencia,
    DatosInvalidos,
    ErrorPersistencia,
    RecursoNoEncontrado,
    traducir_integrity_error,
)
from app.nucleo.models import (
    Chofer,
    Cliente,
    Documento,
    EstadoViaje,
    Rampla,
    ReservaRecurso,
    TipoDocumento,
    TipoRecurso,
    Tracto,
    Viaje,
)
from app.nucleo.schemas import (
    ChoferCreateNucleo,
    ClienteCreateNucleo,
    DocumentoOutNucleo,
    DocumentoUrlOut,
    RamplaCreateNucleo,
    TractoCreateNucleo,
)
from app.nucleo.tiempo import ahora_utc

BUCKET = "respaldos"
MAX_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic"}

ESTADOS_VIAJE_ACTIVOS = [
    EstadoViaje.confirmado,
    EstadoViaje.asignado,
    EstadoViaje.en_carga,
    EstadoViaje.cargado,
    EstadoViaje.en_ruta,
    EstadoViaje.en_descarga,
    EstadoViaje.descargado,
    EstadoViaje.pod_pendiente,
    EstadoViaje.cerrado,
]

MODELO_RECURSO = {
    TipoRecurso.tracto: Tracto,
    TipoRecurso.rampla: Rampla,
    TipoRecurso.chofer: Chofer,
}
CAMPO_RECURSO = {
    TipoRecurso.tracto: "tracto_id",
    TipoRecurso.rampla: "rampla_id",
    TipoRecurso.chofer: "chofer_id",
}


class ServicioMaestros:
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

    def _get(self, modelo, recurso_id: UUID):
        obj = self.session.get(modelo, recurso_id)
        if obj is None or obj.empresa_id != self.empresa.id:
            raise RecursoNoEncontrado("Registro no encontrado en la empresa.")
        return obj

    def _actualizar(self, modelo, obj, datos: dict[str, Any]):
        try:
            resultado = self.session.execute(
                update(modelo)
                .where(
                    modelo.id == obj.id,
                    modelo.empresa_id == self.empresa.id,
                    modelo.version == obj.version,
                )
                .values(**datos)
            )
            if resultado.rowcount != 1:
                raise ConflictoConcurrencia(
                    "El registro fue modificado por otro usuario. Recargue e intente nuevamente."
                )
            self.session.commit()
            self.session.refresh(obj)
            return obj
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise

    def _recurso_con_reservas_futuras(
        self, tipo: TipoRecurso, recurso_id: UUID
    ) -> bool:
        columna = {
            TipoRecurso.tracto: ReservaRecurso.tracto_id,
            TipoRecurso.rampla: ReservaRecurso.rampla_id,
            TipoRecurso.chofer: ReservaRecurso.chofer_id,
        }[tipo]
        reserva = self.session.exec(
            select(ReservaRecurso)
            .where(
                ReservaRecurso.empresa_id == self.empresa.id,
                ReservaRecurso.recurso_tipo == tipo,
                ReservaRecurso.activa == True,  # noqa: E712
                columna == recurso_id,
                func.upper(ReservaRecurso.ventana) > ahora_utc(),
            )
            .limit(1)
        ).first()
        return reserva is not None

    def _validar_cliente_desactivable(self, cliente_id: UUID) -> None:
        viaje = self.session.exec(
            select(Viaje)
            .where(
                Viaje.empresa_id == self.empresa.id,
                Viaje.cliente_id == cliente_id,
                Viaje.estado.in_(ESTADOS_VIAJE_ACTIVOS),
            )
            .limit(1)
        ).first()
        if viaje is not None:
            raise DatosInvalidos(
                f"El cliente tiene el viaje {viaje.numero_viaje or ''} activo; "
                "no se puede desactivar."
            )

    def _validar_recurso_desactivable(
        self, tipo: TipoRecurso, recurso_id: UUID, etiqueta: str
    ) -> None:
        if self._recurso_con_reservas_futuras(tipo, recurso_id):
            raise DatosInvalidos(
                f"{etiqueta} tiene reservas futuras; reasigne o cancele antes de desactivarlo."
            )

    # ------------------------------------------------------------------
    # Clientes
    # ------------------------------------------------------------------
    def listar_clientes(self, *, activo: bool | None = None, q: str | None = None):
        filtros = [Cliente.empresa_id == self.empresa.id]
        if activo is not None:
            filtros.append(Cliente.activo == activo)
        if q and q.strip():
            patron = f"%{q.strip()}%"
            filtros.append(
                or_(Cliente.razon_social.ilike(patron), Cliente.rut.ilike(patron))
            )
        return self.session.exec(
            select(Cliente).where(*filtros).order_by(Cliente.razon_social)
        ).all()

    def crear_cliente(self, data: ClienteCreateNucleo):
        self._fijar_contexto_bd()
        cliente = Cliente(empresa_id=self.empresa.id, **data.model_dump())
        try:
            self.session.add(cliente)
            self.session.commit()
            self.session.refresh(cliente)
            return cliente
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise

    def actualizar_cliente(self, cliente_id: UUID, data: ClienteCreateNucleo):
        cliente = self._get(Cliente, cliente_id)
        if cliente.activo and not data.activo:
            self._validar_cliente_desactivable(cliente_id)
        self._fijar_contexto_bd()
        return self._actualizar(Cliente, cliente, data.model_dump())

    def desactivar_cliente(self, cliente_id: UUID):
        cliente = self._get(Cliente, cliente_id)
        self._validar_cliente_desactivable(cliente_id)
        self._fijar_contexto_bd()
        return self._actualizar(Cliente, cliente, {"activo": False})

    # ------------------------------------------------------------------
    # Tractos
    # ------------------------------------------------------------------
    def listar_tractos(self, *, activo: bool | None = None, q: str | None = None):
        filtros = [Tracto.empresa_id == self.empresa.id]
        if activo is not None:
            filtros.append(Tracto.activo == activo)
        if q and q.strip():
            patron = f"%{q.strip()}%"
            filtros.append(
                or_(Tracto.patente.ilike(patron), Tracto.marca.ilike(patron))
            )
        return self.session.exec(
            select(Tracto).where(*filtros).order_by(Tracto.patente)
        ).all()

    def crear_tracto(self, data: TractoCreateNucleo):
        self._fijar_contexto_bd()
        tracto = Tracto(empresa_id=self.empresa.id, **data.model_dump())
        try:
            self.session.add(tracto)
            self.session.commit()
            self.session.refresh(tracto)
            return tracto
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise

    def actualizar_tracto(self, tracto_id: UUID, data: TractoCreateNucleo):
        tracto = self._get(Tracto, tracto_id)
        if tracto.activo and not data.activo:
            self._validar_recurso_desactivable(TipoRecurso.tracto, tracto_id, "El tracto")
        self._fijar_contexto_bd()
        return self._actualizar(Tracto, tracto, data.model_dump())

    def desactivar_tracto(self, tracto_id: UUID):
        tracto = self._get(Tracto, tracto_id)
        self._validar_recurso_desactivable(TipoRecurso.tracto, tracto_id, "El tracto")
        self._fijar_contexto_bd()
        return self._actualizar(Tracto, tracto, {"activo": False})

    # ------------------------------------------------------------------
    # Ramplas
    # ------------------------------------------------------------------
    def listar_ramplas(self, *, activo: bool | None = None, q: str | None = None):
        filtros = [Rampla.empresa_id == self.empresa.id]
        if activo is not None:
            filtros.append(Rampla.activo == activo)
        if q and q.strip():
            patron = f"%{q.strip()}%"
            filtros.append(Rampla.patente.ilike(patron))
        return self.session.exec(
            select(Rampla).where(*filtros).order_by(Rampla.patente)
        ).all()

    def crear_rampla(self, data: RamplaCreateNucleo):
        self._fijar_contexto_bd()
        rampla = Rampla(empresa_id=self.empresa.id, **data.model_dump())
        try:
            self.session.add(rampla)
            self.session.commit()
            self.session.refresh(rampla)
            return rampla
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise

    def actualizar_rampla(self, rampla_id: UUID, data: RamplaCreateNucleo):
        rampla = self._get(Rampla, rampla_id)
        if rampla.activo and not data.activo:
            self._validar_recurso_desactivable(TipoRecurso.rampla, rampla_id, "La rampla")
        self._fijar_contexto_bd()
        return self._actualizar(Rampla, rampla, data.model_dump())

    def desactivar_rampla(self, rampla_id: UUID):
        rampla = self._get(Rampla, rampla_id)
        self._validar_recurso_desactivable(TipoRecurso.rampla, rampla_id, "La rampla")
        self._fijar_contexto_bd()
        return self._actualizar(Rampla, rampla, {"activo": False})

    # ------------------------------------------------------------------
    # Choferes
    # ------------------------------------------------------------------
    def listar_choferes(self, *, activo: bool | None = None, q: str | None = None):
        filtros = [Chofer.empresa_id == self.empresa.id]
        if activo is not None:
            filtros.append(Chofer.activo == activo)
        if q and q.strip():
            patron = f"%{q.strip()}%"
            filtros.append(
                or_(
                    Chofer.nombre.ilike(patron),
                    Chofer.rut.ilike(patron),
                    Chofer.apellido_paterno.ilike(patron),
                )
            )
        return self.session.exec(
            select(Chofer).where(*filtros).order_by(Chofer.nombre)
        ).all()

    def crear_chofer(self, data: ChoferCreateNucleo):
        self._fijar_contexto_bd()
        chofer = Chofer(empresa_id=self.empresa.id, **data.model_dump())
        try:
            self.session.add(chofer)
            self.session.commit()
            self.session.refresh(chofer)
            return chofer
        except IntegrityError as exc:
            self.session.rollback()
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            raise

    def actualizar_chofer(self, chofer_id: UUID, data: ChoferCreateNucleo):
        chofer = self._get(Chofer, chofer_id)
        if chofer.activo and not data.activo:
            self._validar_recurso_desactivable(TipoRecurso.chofer, chofer_id, "El chofer")
        self._fijar_contexto_bd()
        return self._actualizar(Chofer, chofer, data.model_dump())

    def desactivar_chofer(self, chofer_id: UUID):
        chofer = self._get(Chofer, chofer_id)
        self._validar_recurso_desactivable(TipoRecurso.chofer, chofer_id, "El chofer")
        self._fijar_contexto_bd()
        return self._actualizar(Chofer, chofer, {"activo": False})

    # ------------------------------------------------------------------
    # Documentos
    # ------------------------------------------------------------------
    def _validar_recurso(self, recurso_tipo: TipoRecurso, recurso_id: UUID):
        modelo = MODELO_RECURSO[recurso_tipo]
        return self._get(modelo, recurso_id)

    def listar_documentos(
        self, recurso_tipo: TipoRecurso, recurso_id: UUID
    ) -> list[DocumentoOutNucleo]:
        self._validar_recurso(recurso_tipo, recurso_id)
        campo = CAMPO_RECURSO[recurso_tipo]
        documentos = self.session.exec(
            select(Documento)
            .where(
                Documento.empresa_id == self.empresa.id,
                Documento.recurso_tipo == recurso_tipo,
                getattr(Documento, campo) == recurso_id,
            )
            .order_by(Documento.created_at.desc())
        ).all()
        return [self._documento_out(d) for d in documentos]

    @staticmethod
    def _documento_out(doc: Documento) -> DocumentoOutNucleo:
        return DocumentoOutNucleo(
            id=doc.id,
            recurso_tipo=doc.recurso_tipo,
            tracto_id=doc.tracto_id,
            rampla_id=doc.rampla_id,
            chofer_id=doc.chofer_id,
            tipo=doc.tipo,
            numero=doc.numero,
            entidad_emisora=doc.entidad_emisora,
            emitido_en=doc.emitido_en,
            vence_en=doc.vence_en,
            archivo_url=doc.archivo_url,
            hash_sha256=doc.hash_sha256,
            es_vigente=doc.es_vigente,
            observaciones=doc.observaciones,
            created_at=doc.created_at,
            version=doc.version,
        )

    def subir_documento(
        self,
        *,
        recurso_tipo: TipoRecurso,
        recurso_id: UUID,
        tipo: TipoDocumento,
        numero: str | None,
        entidad_emisora: str | None,
        emitido_en: date | None,
        vence_en: date,
        observaciones: str | None,
        nombre_archivo: str,
        contenido: bytes,
        content_type: str | None = None,
    ) -> DocumentoOutNucleo:
        self._validar_recurso(recurso_tipo, recurso_id)
        if len(contenido) == 0:
            raise DatosInvalidos("El archivo está vacío.")
        if len(contenido) > MAX_BYTES:
            raise DatosInvalidos("El archivo no puede superar 10 MB.")
        ext = os.path.splitext(nombre_archivo)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise DatosInvalidos(
                "Formato no permitido. Use PDF, JPG, JPEG, PNG, WEBP o HEIC."
            )
        if emitido_en is not None and vence_en < emitido_en:
            raise DatosInvalidos("La fecha de vencimiento no puede ser anterior a la emisión.")

        path = (
            f"nucleo/{self.empresa.id}/documentos/{recurso_tipo.value}/"
            f"{recurso_id}/{uuid.uuid4().hex}{ext}"
        )
        hash_sha = hashlib.sha256(contenido).hexdigest()

        storage = self._storage()
        try:
            storage.storage.from_(BUCKET).upload(
                path,
                contenido,
                {"content-type": content_type or "application/octet-stream"},
            )
        except Exception as exc:  # pragma: no cover - depende de Storage
            raise ErrorPersistencia(
                "No se pudo subir el documento a Storage."
            ) from exc

        self._fijar_contexto_bd()
        documento = Documento(
            empresa_id=self.empresa.id,
            recurso_tipo=recurso_tipo,
            **{CAMPO_RECURSO[recurso_tipo]: recurso_id},
            tipo=tipo,
            numero=(numero.strip() if numero else None),
            entidad_emisora=(entidad_emisora.strip() if entidad_emisora else None),
            emitido_en=emitido_en,
            vence_en=vence_en,
            archivo_url=path,
            hash_sha256=hash_sha,
            es_vigente=True,
            observaciones=observaciones,
        )
        try:
            self.session.add(documento)
            self.session.commit()
            self.session.refresh(documento)
            return self._documento_out(documento)
        except IntegrityError as exc:
            self.session.rollback()
            self._eliminar_storage(path)
            raise traducir_integrity_error(exc) from exc
        except Exception:
            self.session.rollback()
            self._eliminar_storage(path)
            raise

    def url_documento(self, documento_id: UUID) -> DocumentoUrlOut:
        documento = self._get(Documento, documento_id)
        if not documento.archivo_url:
            raise RecursoNoEncontrado("El documento no tiene archivo adjunto.")
        storage = self._storage()
        try:
            resultado = storage.storage.from_(BUCKET).create_signed_url(
                documento.archivo_url, 3600
            )
        except Exception as exc:  # pragma: no cover - depende de Storage
            raise ErrorPersistencia("No se pudo generar el enlace del documento.") from exc
        url = resultado.get("signedURL")
        if not url:
            raise ErrorPersistencia("No se pudo generar el enlace del documento.")
        return DocumentoUrlOut(url=url, expires_in=3600)

    @staticmethod
    def _storage():
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
            raise ErrorPersistencia("Storage no configurado.")
        from supabase import create_client

        return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    def _eliminar_storage(self, path: str) -> None:
        try:
            self._storage().storage.from_(BUCKET).remove([path])
        except Exception:
            # El registro no se creó; dejar el archivo huérfano es preferible a
            # ocultar el error original. La limpieza puede hacerse por job.
            pass
