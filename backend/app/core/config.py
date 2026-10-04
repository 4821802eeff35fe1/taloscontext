from decimal import Decimal
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    app_secret_key: str = Field(default="", alias="APP_SECRET_KEY")
    app_url: str = Field(default="http://localhost:3000", alias="APP_URL")

    database_url: str = Field(
        default="postgresql+asyncpg://channelos:channelos@localhost:5432/channelos",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    admin_email: str = Field(default="", alias="ADMIN_EMAIL")
    admin_password: str = Field(default="", alias="ADMIN_PASSWORD")

    telegram_api_id: int = Field(default=0, alias="TELEGRAM_API_ID")
    telegram_api_hash: str = Field(default="", alias="TELEGRAM_API_HASH")
    telethon_session_encryption_key: str = Field(
        default="", alias="TELETHON_SESSION_ENCRYPTION_KEY"
    )

    timeweb_agent_access_id: str = Field(
        default="3dce7cc5-7e2d-498b-9247-0b1f556cbb5d", alias="TIMEWEB_AGENT_ACCESS_ID"
    )
    timeweb_agent_base_url: str = Field(
        default=(
            "https://agent.timeweb.cloud/api/v1/cloud-ai/agents/"
            "3dce7cc5-7e2d-498b-9247-0b1f556cbb5d/v1"
        ),
        alias="TIMEWEB_AGENT_BASE_URL",
    )
    timeweb_agent_api_key: str = Field(default="", alias="TIMEWEB_AGENT_API_KEY")

    timeweb_text_input_rub_per_m: Decimal = Field(
        default=Decimal(270), alias="TIMEWEB_TEXT_INPUT_RUB_PER_M"
    )
    timeweb_text_output_rub_per_m: Decimal = Field(
        default=Decimal(1350), alias="TIMEWEB_TEXT_OUTPUT_RUB_PER_M"
    )
    timeweb_image_input_rub_per_m: Decimal = Field(
        default=Decimal(675), alias="TIMEWEB_IMAGE_INPUT_RUB_PER_M"
    )
    timeweb_image_output_rub_per_m: Decimal = Field(
        default=Decimal(4050), alias="TIMEWEB_IMAGE_OUTPUT_RUB_PER_M"
    )

    timeweb_ai_gateway_base_url: str = Field(default="", alias="TIMEWEB_AI_GATEWAY_BASE_URL")
    timeweb_ai_gateway_api_key: str = Field(default="", alias="TIMEWEB_AI_GATEWAY_API_KEY")
    timeweb_image_model: str = Field(default="", alias="TIMEWEB_IMAGE_MODEL")

    s3_endpoint: str = Field(default="", alias="S3_ENDPOINT")
    s3_access_key: str = Field(default="", alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(default="", alias="S3_SECRET_KEY")
    s3_bucket: str = Field(default="channelos-media", alias="S3_BUCKET")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")

    use_fake_ai_provider: bool = Field(default=True, alias="USE_FAKE_AI_PROVIDER")
    use_fake_image_provider: bool = Field(default=True, alias="USE_FAKE_IMAGE_PROVIDER")
    use_fake_telegram_provider: bool = Field(default=True, alias="USE_FAKE_TELEGRAM_PROVIDER")

    # Run jobs in-process right after dispatch instead of via ARQ. For tests
    # and single-process demos only; production uses the worker.
    jobs_inline: bool = Field(default=False, alias="JOBS_INLINE")
    # Number of reverse proxies in front of the API whose X-Forwarded-For we
    # trust for client-IP based rate limiting. 0 = use the socket peer address.
    trusted_proxy_count: int = Field(default=0, alias="TRUSTED_PROXY_COUNT")
    session_max_age_seconds: int = Field(default=60 * 60 * 24 * 14, alias="SESSION_MAX_AGE_SECONDS")

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def validate_production(self) -> None:
        if self.is_production and not self.app_secret_key:
            raise RuntimeError("APP_SECRET_KEY must be set when APP_ENV=production")
        if self.is_production and not self.telethon_session_encryption_key:
            raise RuntimeError(
                "TELETHON_SESSION_ENCRYPTION_KEY must be set when APP_ENV=production"
            )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production()
    return settings
