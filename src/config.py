"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """MetaboCoach application settings."""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # App
    app_env: str = "development"
    app_debug: bool = False
    app_secret_key: str = "change-me-in-production"

    # Database
    database_url: str = "postgresql+asyncpg://metabocoach:password@localhost:5432/metabocoach"
    database_url_sync: str = "postgresql://metabocoach:password@localhost:5432/metabocoach"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Google Gemini AI
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_vision_model: str = "gemini-2.5-flash"

    # LibreLinkUp
    libre_email: str = ""
    libre_password: str = ""
    libre_region: str = "us"

    # Garmin Connect
    garmin_consumer_key: str = ""
    garmin_consumer_secret: str = ""

    # Twilio (WhatsApp)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"

    # Telegram
    telegram_bot_token: str = ""

    # GCP
    gcp_project_id: str = ""
    gcp_region: str = "us-central1"
    gcs_bucket_name: str = "metabocoach-photos"

    # Sentry
    sentry_dsn: str = ""

    # Defaults
    default_timezone: str = "America/Toronto"
    default_glucose_low: float = 3.9
    default_glucose_high: float = 10.0

    @property
    def libre_api_base(self) -> str:
        endpoints = {
            "us": "https://api.libreview.io",
            "eu": "https://api-eu.libreview.io",
            "au": "https://api-au.libreview.io",
        }
        return endpoints.get(self.libre_region, endpoints["us"])


settings = Settings()
