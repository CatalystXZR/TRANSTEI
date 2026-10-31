from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    PROJECT_NAME: str = "ERP Transportes TEI SpA"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""
    DATABASE_URL: str = ""
    # ADR-0005: DSN del rol `tei_app` (NOBYPASSRLS) para el schema `nucleo`.
    # Sin esta variable el núcleo cae al motor legacy (un solo motor) y RLS
    # queda inerte; `get_engine_nucleo()` registra el warning correspondiente.
    NUCLEO_DATABASE_URL: str = ""
    NUCLEO_TEST_DATABASE_URL: str = ""

    CORS_ORIGINS: str = "http://localhost:3000"
    FRONTEND_URL: str = "http://localhost:3000"

    # Empresa dueña del legacy monoempresa (`public.*`, sin `empresa_id`).
    # El legacy no puede aislar por fila: la única frontera posible es negar
    # `/api/v1/*` (salvo `/nucleo` y `/auth`) a quien no tenga membresía activa
    # en esta empresa (`backend/app/main.py:GateLegacyMiddleware`).
    LEGACY_EMPRESA_ID: str = "11111111-1111-1111-1111-111111111111"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
