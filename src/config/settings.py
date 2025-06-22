from pathlib import Path

from pydantic import Field
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

    # MCP server settings
    mcp_server_enabled: bool = Field(True, description="Enable MCP server")
    mcp_server_host: str = Field("localhost", description="MCP server host")
    mcp_server_port: int = Field(8000, description="MCP server port")

    # OpenAI settings for LLM intent parsing
    openai_api_key: str = Field("", description="OpenAI API key")
    openai_model: str = Field("gpt-4o", description="OpenAI model to use")

    log_level: str = Field("INFO", description="Logging level")
    model_config = SettingsConfigDict(
        extra="allow",
        env_file=".env",
        env_nested_delimiter="__",
    )


settings = Settings()
