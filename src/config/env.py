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
    mcp_server_host: str = Field("localhost", description="MCP server host")
    mcp_server_port: int = Field(4433, description="MCP server port")
    openai_api_key: str = Field("", description="OpenAI API key")
    milvus_uri: str = "http://localhost:19530"
    model_config = SettingsConfigDict(
        extra="allow",
        env_file=".env",
        env_nested_delimiter="__",
    )


settings = Settings()
