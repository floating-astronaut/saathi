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

    # Admission control (pattern from OpenClaw's dmPolicy). "pairing" means an
    # unknown handle must redeem a code before the agent will talk to it; "open"
    # lets anyone in. Default is pairing: an unknown sender otherwise gets free
    # LLM turns and STT minutes on our bill, and this is an eldercare agent.
    # "open" now that onboarding exists and is deterministic: an unknown sender
    # walks a scripted, model-free path, so anyone may start by messaging us
    # without opening a cost vector. "pairing" remains available for a closed
    # pilot.
    saathi_dm_policy: str = "open"
    #: How many times we will explain the pairing requirement to one unknown
    #: handle before going silent. Each reply costs money.
    saathi_admission_max_replies: int = 2


settings = Settings()
