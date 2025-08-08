"""Factory for creating telegram bot instances based on configuration."""

from src.config.llm_config import get_llm_config
from src.config.logging import logger
from src.llm_solutions.base import BaseTelegramBot


def create_telegram_bot() -> BaseTelegramBot:
    """Create a telegram bot instance based on the current configuration.

    Returns
    -------
        Telegram bot instance

    Raises
    ------
        ValueError: If the solution type is not supported
        ImportError: If required dependencies are missing
    """
    config = get_llm_config()
    solution_type = config.get_solution_type()
    logger.info(f"Creating telegram bot with solution: {solution_type}")

    if solution_type == "rigid_intent":
        return _create_rigid_intent_bot()
    if solution_type == "langchain_react":
        return _create_langchain_react_bot()

    raise ValueError(f"Unsupported solution type: {solution_type}")


def _create_rigid_intent_bot() -> BaseTelegramBot:
    """Create a rigid intent-based telegram bot.

    Returns
    -------
        RigidTelegramBot instance

    Raises
    ------
        ImportError: If required dependencies are missing
    """
    try:
        from src.llm_solutions.rigid_intent import RigidTelegramBot

        logger.info("Creating rigid intent telegram bot")
        return RigidTelegramBot()

    except ImportError as exc:
        logger.error(f"Failed to import rigid intent bot: {exc}")
        raise ImportError(
            "Required dependencies for rigid_intent solution are missing. "
            "Please install: pydantic, openai"
        ) from exc


def _create_langchain_react_bot() -> BaseTelegramBot:
    """Create a LangChain ReAct telegram bot.

    Returns
    -------
        LangChainReActTelegramBot instance

    Raises
    ------
        ImportError: If required dependencies are missing
    """
    try:
        from src.llm_solutions.langchain_react import LangChainReActTelegramBot

        logger.info("Creating LangChain ReAct telegram bot")
        return LangChainReActTelegramBot()

    except ImportError as exc:
        logger.error(f"Failed to import LangChain ReAct bot: {exc}")
        raise ImportError(
            "Required dependencies for langchain_react solution are missing. "
            "Please install: langchain, langchain-openai, langchain-core, langgraph"
        ) from exc


def get_available_solutions() -> list[str]:
    """Get list of available LLM solutions.

    Returns
    -------
        List of solution names
    """
    return ["rigid_intent", "langchain_react"]


def check_solution_dependencies(solution_type: str) -> bool:
    """Check if dependencies for a solution are available.

    Args:
        solution_type: The solution type to check

    Returns
    -------
        True if all dependencies are available
    """
    if solution_type == "rigid_intent":
        return True
    if solution_type == "langchain_react":
        try:
            import langchain
            import langchain_core
            import langchain_mcp_adapters
            import langchain_openai
            import langgraph

            return True
        except ImportError:
            return False

    return False


def validate_configuration() -> dict[str, bool]:
    """Validate the current configuration and dependencies.

    Returns
    -------
        Dictionary with validation results
    """
    config = get_llm_config()
    solution_type = config.get_solution_type()
    results = {
        "solution_supported": solution_type in get_available_solutions(),
        "dependencies_available": check_solution_dependencies(solution_type),
    }
    return results


def print_configuration_status() -> None:
    """Print current configuration status to logs."""
    config = get_llm_config()
    logger.info("=== LLM Solutions Configuration Status ===")
    logger.info(f"Solution Type: {config.get_solution_type()}")
    logger.info(f"Environment: {config.deployment.environment}")
    logger.info("============================================")
