from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    PROJECT_NAME: str = "ERP Transportes TEI SpA"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    # Documentación interactiva desactivada por defecto. En local se habilita
    # con ENABLE_DOCS=true; en producción no debe exponerse.
    ENABLE_DOCS: bool = False

    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""
    # Emisor esperado del JWT. Si se deja vacío se deriva de SUPABASE_URL
    # (`<url>/auth/v1`). Se valida en `core/security.py`.
    SUPABASE_JWT_ISSUER: str = ""
    DATABASE_URL: str = ""
    # ADR-0005: DSN del rol `tei_app` (NOBYPASSRLS) para el schema `nucleo`.
    # Sin esta variable el núcleo cae al motor legacy (un solo motor) y RLS
    # queda inerte; `get_engine_nucleo()` registra el warning correspondiente.
    NUCLEO_DATABASE_URL: str = ""
    NUCLEO_TEST_DATABASE_URL: str = ""

    # Enrolamiento del agente (D-12): el admin inicia el alta y el OTP viaja
    # por WhatsApp. El código se guarda solo como HMAC-SHA256; este pepper es
    # el secreto compartido entre workers (no se rota por request).
    AGENTE_OTP_PEPPER: str = ""
    WHATSAPP_MODE: str = "fake"  # fake (local/tests) | meta
    WHATSAPP_API_URL: str = ""
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_ID: str = ""

    # ==================== AGENTES CONVERSACIONALES (Ola 3) ====================
    # Proveedor LLM. DeepSeek es compatible con la API de OpenAI; para cambiar de
    # proveedor basta ajustar BASE_URL/MODELO (el cliente es genérico).
    AGENTE_LLM_PROVEEDOR: str = "deepseek"
    AGENTE_LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    AGENTE_LLM_TIMEOUT_S: float = 45.0
    AGENTE_LLM_MAX_ITERACIONES: int = 4
    AGENTE_LLM_MAX_MENSAJES_CONTEXTO: int = 30
    AGENTE_PLANES_PREMIUM: str = "premium,pro"
    # Tope de turnos de chat concurrentes por proceso (SEC-053). No es un rate
    # limit distribuido: cada worker tiene su propio semáforo.
    AGENTE_CHAT_MAX_CONCURRENT: int = 4

    # >>> PEGA TU API KEY EN backend/.env — NUNCA AQUÍ <<<
    GERENTE_API_KEY: str = ""
    SECRETARIA_API_KEY: str = ""
    GERENTE_LLM_MODELO: str = "deepseek-chat"
    SECRETARIA_LLM_MODELO: str = "deepseek-chat"

    CORS_ORIGINS: str = "http://localhost:3000"
    FRONTEND_URL: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def planes_premium_list(self) -> list[str]:
        """Códigos de plan que habilitan los módulos premium del chat."""
        return [p.strip() for p in self.AGENTE_PLANES_PREMIUM.split(",") if p.strip()]

    @property
    def jwt_issuer(self) -> str:
        """Emisor esperado del JWT: explícito o derivado de SUPABASE_URL."""
        if self.SUPABASE_JWT_ISSUER.strip():
            return self.SUPABASE_JWT_ISSUER.strip()
        url = self.SUPABASE_URL.rstrip("/")
        return f"{url}/auth/v1" if url else ""


settings = Settings()
