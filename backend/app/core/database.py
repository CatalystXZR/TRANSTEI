from fastapi import HTTPException, status
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from app.core.config import settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        if not settings.DATABASE_URL:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Base de datos no configurada. Copie backend/.env.example "
                    "a backend/.env y complete los datos del proyecto Supabase."
                ),
            )
        _engine = create_engine(
            settings.DATABASE_URL, pool_pre_ping=True, echo=settings.DEBUG
        )
    return _engine


def get_session():
    with Session(get_engine()) as session:
        yield session
