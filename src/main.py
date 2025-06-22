import threading

from loguru import logger

from src.config.logging import setup_logging
from src.config.settings import settings
from src.services.mcp_server import MCPServer
from src.services.telegram_bot import TelegramBot


def start_mcp_server() -> None:
    """Start the MCP server in a separate thread."""
    if settings.mcp_server_enabled:
        logger.info("Starting MCP server")
        MCPServer().run()


def start_telegram_bot() -> None:
    """Start the Telegram bot."""
    logger.info("Starting Telegram bot")
    bot = TelegramBot()
    bot.run()


def main() -> None:
    """Main entry point for the application."""
    # Setup logging
    setup_logging(settings.log_level)

    logger.info("Starting Time Manager application")

    if settings.mcp_server_enabled:
        # Start MCP server in a separate thread
        mcp_thread = threading.Thread(target=start_mcp_server, daemon=True)
        mcp_thread.start()
        logger.info("MCP server thread started")

    # Start the Telegram bot in the main thread
    start_telegram_bot()


if __name__ == "__main__":
    main()
