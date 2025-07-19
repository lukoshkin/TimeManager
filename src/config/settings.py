import os
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    telegram_api_id: int = Field(..., description="Telegram API ID")
    telegram_api_hash: str = Field(..., description="Telegram API hash")
    telegram_bot_token: str = Field(..., description="Telegram bot token")

    google_credentials_file: Path = Field(
        Path("credentials.json"),
        description="Path to Google API credentials file",
    )
    google_token_file: Path = Field(
        Path("token.json"),
        description="Path to Google API token file",
    )
    mcp_server_enabled: bool = Field(True, description="Enable MCP server")
    mcp_server_host: str = Field("localhost", description="MCP server host")
    mcp_server_port: int = Field(8000, description="MCP server port")

    openai_api_key: str = Field("", description="OpenAI API key")
    openai_model: str = Field("gpt-4o", description="OpenAI model to use")

    milvus_uri: str = "http://localhost:19530"
    milvus_collection_name: str = "calendar_events"
    milvus_vector_dim: int = 384
    milvus_model_name: str = "text-embedding-3-small"
    milvus_model_provider: str = "openai"

    log_level: str = Field("DEBUG", description="General logging level")
    litellm_log: str = Field("INFO", description="LiteLLM logging level")
    app_log_level: str = Field("INFO", description="For custom log messages")

    model_config = SettingsConfigDict(
        extra="allow",
        env_file=".env",
        env_nested_delimiter="__",
    )

    @model_validator(mode="after")
    def set_litellm_env(self):
        """Ensure LITELLM_LOG environment variable is set to match the config value."""
        os.environ["LITELLM_LOG"] = self.litellm_log
        return self


settings = Settings()
