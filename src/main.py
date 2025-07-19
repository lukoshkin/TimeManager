import threading

from src.config.logging import logger, setup_logging
from src.config.settings import settings
from src.services.mcp_server import MCPServer
from src.services.telegram_bot import TelegramBot


def start_mcp_server() -> None:
    """Start the MCP server in a separate thread."""
    if settings.mcp_server_enabled:
        logger.info("Starting MCP server..")
        MCPServer().run()


def start_telegram_bot() -> None:
    """Start the Telegram bot."""
    logger.info("Starting Telegram bot..")
    bot = TelegramBot()
    bot.run()


def main() -> None:
    """Run the application."""
    setup_logging(settings.app_log_level)
    logger.info("Starting Time Manager application..")
    logger.info(f"Log level set to: {settings.log_level}")

    if settings.mcp_server_enabled:
        # Start MCP server in a separate thread
        mcp_thread = threading.Thread(target=start_mcp_server, daemon=True)
        mcp_thread.start()
        logger.info("MCP server thread started")

    start_telegram_bot()


if __name__ == "__main__":
    main()
