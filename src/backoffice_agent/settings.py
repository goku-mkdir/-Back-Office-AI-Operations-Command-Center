"""Application settings (env-backed) and live YAML configuration manager."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Environment-driven application configuration.

    All secrets and API keys are read strictly from environment variables or `.env`.
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Runtime
    app_mode: str = Field(default="sandbox", alias="APP_MODE")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    database_path: str = Field(
        default=str(PROJECT_ROOT / "data" / "backoffice_agent.db"),
        alias="DATABASE_PATH",
    )
    config_dir: str = Field(
        default=str(PROJECT_ROOT / "config"),
        alias="CONFIG_DIR",
    )

    # Provider-agnostic LLM configuration
    llm_provider: str = Field(default="mock", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gpt-4o-mini", alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.1, alias="LLM_TEMPERATURE")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    # Per-connector mode overrides ("sandbox" | "live")
    email_mode: str = Field(default="sandbox", alias="EMAIL_MODE")
    slack_mode: str = Field(default="sandbox", alias="SLACK_MODE")
    hris_mode: str = Field(default="sandbox", alias="HRIS_MODE")
    accounting_mode: str = Field(default="sandbox", alias="ACCOUNTING_MODE")
    crm_mode: str = Field(default="sandbox", alias="CRM_MODE")

    # Email / SMTP
    smtp_host: str = Field(default="smtp.gmail.com", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str = Field(default="", alias="SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    email_from_address: str = Field(
        default="ops-agent@company.example", alias="EMAIL_FROM_ADDRESS"
    )

    # Slack
    slack_bot_token: str = Field(default="", alias="SLACK_BOT_TOKEN")
    slack_signing_secret: str = Field(default="", alias="SLACK_SIGNING_SECRET")
    slack_approval_channel: str = Field(
        default="#ops-approvals", alias="SLACK_APPROVAL_CHANNEL"
    )
    slack_alerts_channel: str = Field(
        default="#ops-audit-alerts", alias="SLACK_ALERTS_CHANNEL"
    )
    slack_webhook_url: str = Field(default="", alias="SLACK_WEBHOOK_URL")

    # BambooHR
    bamboohr_subdomain: str = Field(default="", alias="BAMBOOHR_SUBDOMAIN")
    bamboohr_api_key: str = Field(default="", alias="BAMBOOHR_API_KEY")

    # Xero
    xero_access_token: str = Field(default="", alias="XERO_ACCESS_TOKEN")
    xero_tenant_id: str = Field(default="", alias="XERO_TENANT_ID")

    # HubSpot
    hubspot_access_token: str = Field(default="", alias="HUBSPOT_ACCESS_TOKEN")

    # Server
    api_host: str = Field(default="127.0.0.1", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_base_url: str = Field(default="http://127.0.0.1:8000", alias="API_BASE_URL")

    def resolve_path(self, path_str: str) -> Path:
        """Resolve relative paths against the project root."""
        p = Path(path_str)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()

    @property
    def db_file(self) -> Path:
        return self.resolve_path(self.database_path)

    @property
    def config_path(self) -> Path:
        return self.resolve_path(self.config_dir)

    @property
    def hr_policy_file(self) -> Path:
        return PROJECT_ROOT / "data" / "hr_policies.md"


class ConfigManager:
    """Loads, validates, and saves YAML rules & prompt files without restarting the agent."""

    def __init__(self, config_dir: Path | str | None = None) -> None:
        settings = get_settings()
        self.config_dir = Path(config_dir) if config_dir else settings.config_path
        self.rules_path = self.config_dir / "agent_rules.yaml"
        self.prompts_path = self.config_dir / "prompts.yaml"

    def load_rules(self) -> dict[str, Any]:
        with self.rules_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise ValueError("agent_rules.yaml must contain a YAML mapping at root.")
        return data

    def load_rules_raw(self) -> str:
        return self.rules_path.read_text(encoding="utf-8")

    def save_rules_raw(self, raw_yaml: str) -> dict[str, Any]:
        parsed = yaml.safe_load(raw_yaml)
        if not isinstance(parsed, dict) or "actions" not in parsed:
            raise ValueError("Invalid rules YAML: must be a mapping containing 'actions'.")
        self.rules_path.write_text(raw_yaml, encoding="utf-8")
        return parsed

    def load_prompts(self) -> dict[str, Any]:
        with self.prompts_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise ValueError("prompts.yaml must contain a YAML mapping at root.")
        return data

    def load_prompts_raw(self) -> str:
        return self.prompts_path.read_text(encoding="utf-8")

    def save_prompts_raw(self, raw_yaml: str) -> dict[str, Any]:
        parsed = yaml.safe_load(raw_yaml)
        if not isinstance(parsed, dict) or "domains" not in parsed:
            raise ValueError("Invalid prompts YAML: must be a mapping containing 'domains'.")
        self.prompts_path.write_text(raw_yaml, encoding="utf-8")
        return parsed


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
