import threading

from src.config.env import settings
from src.config.llm_config import get_llm_config
from src.config.logging import logger, setup_logging_from_config
from src.llm_solutions import create_telegram_bot
from src.llm_solutions.factory import (
    print_configuration_status,
    validate_configuration,
)
from src.services.mcp_server import MCPServer


def start_mcp_server() -> None:
    """Start the MCP server in a separate process."""
    logger.info(
        f"Starting MCP server on {settings.mcp_server_host}"
        f":{settings.mcp_server_port}"
    )
    server = MCPServer()
    server.run(
        host=settings.mcp_server_host,
        port=settings.mcp_server_port,
        path="/mcp",
    )


def start_telegram_bot() -> None:
    """Start the Telegram bot using the configured LLM solution."""
    try:
        validation = validate_configuration()
        if not validation["solution_supported"]:
            logger.error("Unsupported LLM solution type.")
            return

        if not validation["dependencies_available"]:
            config = get_llm_config()
            required_deps = config.get_required_dependencies()
            logger.error(
                f"\nMissing dependencies for {config.get_solution_type()}"
                f" solution: {', '.join(required_deps)}\nAdd the flag"
                f" --extra={config.get_solution_type()}"
            )
            return

        print_configuration_status()
        bot = create_telegram_bot()
        bot.run()
    except Exception as exc:
        logger.error(f"Failed to start Telegram bot: {exc}")
        raise


def main() -> None:
    """Run the application."""
    setup_logging_from_config()
    logger.info("Starting Time Manager application...")

    try:
        config = get_llm_config()
        logger.info(
            f"Loaded LLM configuration: {config.get_solution_type()} solution"
        )
    except Exception as exc:
        logger.error(f"Failed to load LLM configuration: {exc}")
        logger.error("Application cannot start without valid configuration.")
        return

    mcp_thread = threading.Thread(target=start_mcp_server, daemon=True)
    mcp_thread.start()

    logger.info("MCP server thread started")
    start_telegram_bot()


if __name__ == "__main__":
    main()
