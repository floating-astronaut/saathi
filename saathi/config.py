"""Settings. Values come from the environment; nothing secret is defaulted."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    saathi_env: str = "dev"
    saathi_db_dsn: str = "postgresql:///saathi"

    # WhatsApp Cloud API (Meta direct)
    wa_phone_number_id: str = ""
    wa_business_account_id: str = ""
    wa_access_token: str = ""
    wa_webhook_verify_token: str = ""
    wa_app_secret: str = ""

    # Bedrock — regional ap-south-1, inference stays in India (plan §5c)
    bedrock_region: str = "ap-south-1"
    saathi_model_id: str = "zai.glm-5"
    # No prompt caching on this model, so cost is linear in prompt size.
    # The agent asserts against this before every call.
    saathi_prefix_token_budget: int = 3000

    sarvam_api_key: str = ""


settings = Settings()
