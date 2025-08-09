from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    telegram_api_id: int = Field(..., description="Telegram API ID")
    telegram_api_hash: str = Field(..., description="Telegram API hash")
    telegram_bot_token: str = Field(..., description="Telegram bot token")
    mcp_server_host: str = Field("localhost", description="MCP server host")
    mcp_server_port: int = Field(4433, description="MCP server port")
    milvus_uri: str = "http://localhost:19530"
    google_credentials_file: Path = Field(
        Path("credentials.json"),
        description="Path to Google API credentials file",
    )
    google_token_file: Path = Field(
        Path("token.json"),
        description="Path to Google API token file",
    )
    chat_model_api_key: str = Field(
        "",
        description="API key for chat models (defaults to OPENAI_API_KEY)",
        validation_alias="OPENAI_API_KEY",
    )
    embed_model_api_key: str = Field(
        "",
        description=(
            "API key for embedding models"
            " (defaults to chat_model_api_key if not set)\nCurrently, is"
            " not used in the code anywhere as the Milvus Standalone server"
            " relies on the provided MILVUSAI_OPENAI_API_KEY environment"
            " variable hardcoded in the respective docker compose file"
        ),
    )

    @model_validator(mode="after")
    def set_embed_model_api_key_default(self) -> "Settings":
        """Set embed_model_api_key to chat_model_api_key if not provided."""
        if not self.embed_model_api_key and self.chat_model_api_key:
            self.embed_model_api_key = self.chat_model_api_key
        return self

    model_config = SettingsConfigDict(
        extra="allow",
        env_file=".env",
        env_nested_delimiter="__",
    )


settings = Settings()
