import uuid
from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlmodel import Session, select

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.core.database import get_session
from app.models import CategoriaGasto, GastoViaje, RolUsuario, Viaje
from app.schemas.viajes import GastoCreate

router = APIRouter(tags=["gastos"])

lectura = Depends(get_current_user)
escritura = Depends(require_roles(RolUsuario.admin, RolUsuario.operacion))

BUCKET = "respaldos"

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".pdf"}


def _upload_respaldo(contenido: bytes, nombre_archivo: str, viaje_id: UUID) -> str:
    ext = "." + nombre_archivo.rsplit(".", 1)[-1].lower() if "." in nombre_archivo else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Formato no permitido. Use: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    from supabase import create_client

    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    path = f"gastos/{viaje_id}/{uuid.uuid4().hex}{ext}"
    result = supabase.storage.from_(BUCKET).upload(path, contenido)
    if hasattr(result, "path"):
        return result.path  # type: ignore[return-value]
    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "No se pudo subir el respaldo")


@router.get("/viajes/{viaje_id}/gastos", response_model=list[GastoViaje])
def listar_gastos(
    viaje_id: UUID,
    session: Session = Depends(get_session),
    _=lectura,
):
    return session.exec(
        select(GastoViaje)
        .where(GastoViaje.viaje_id == viaje_id)
        .order_by(GastoViaje.fecha.desc())  # type: ignore[attr-defined]
    ).all()


@router.post("/viajes/{viaje_id}/gastos", response_model=GastoViaje, status_code=status.HTTP_201_CREATED)
def crear_gasto(
    viaje_id: UUID,
    categoria: CategoriaGasto = Form(...),
    monto: Decimal = Form(...),
    iva_recuperable: bool = Form(False),
    fecha: date | None = Form(default=None),
    notas: str | None = Form(default=None),
    archivo: UploadFile | None = File(default=None),
    session: Session = Depends(get_session),
    _=escritura,
):
    viaje = session.get(Viaje, viaje_id)
    if not viaje:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Viaje no encontrado")

    respaldo_url = None
    if archivo is not None and archivo.filename:
        contenido = archivo.file.read()
        if contenido:
            respaldo_url = _upload_respaldo(contenido, archivo.filename, viaje_id)

    gasto = GastoViaje(
        viaje_id=viaje_id,
        categoria=categoria,
        monto=monto,
        iva_recuperable=iva_recuperable,
        respaldo_url=respaldo_url,
        fecha=fecha or date.today(),
        notas=notas,
    )
    session.add(gasto)
    session.commit()
    session.refresh(gasto)
    return gasto


@router.delete("/gastos/{gasto_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_gasto(
    gasto_id: UUID,
    session: Session = Depends(get_session),
    _=escritura,
):
    gasto = session.get(GastoViaje, gasto_id)
    if not gasto:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gasto no encontrado")
    session.delete(gasto)
    session.commit()


@router.get("/gastos/{gasto_id}/respaldo")
def url_respaldo(
    gasto_id: UUID,
    session: Session = Depends(get_session),
    _=lectura,
):
    gasto = session.get(GastoViaje, gasto_id)
    if not gasto or not gasto.respaldo_url:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sin respaldo adjunto")

    from supabase import create_client

    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    resultado = supabase.storage.from_(BUCKET).create_signed_url(gasto.respaldo_url, 3600)
    url = resultado.get("signedURL")
    if not url:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "No se pudo generar el enlace")
    return {"url": url}
