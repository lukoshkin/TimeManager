import os
import sys

from loguru import logger


def setup_logging(log_level: str = "INFO", litellm_log: str = "INFO") -> None:
    """Configure logging for the application.

    Args:
        log_level: The logging level to use
        litellm_log: The LiteLLM logging level to use
    """
    logger.remove()  # Remove default handler
    # log_format = (
    #     "<green>{time:YYYY-MM-DD HH:mm:ss}</green>"
    #     " | <level>{level: <8}</level>"
    #     " | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>"
    #     " - <level>{message}</level>"
    #     " | <blue>{extra}</blue>"
    #     " | <magenta>File: {file.path}</magenta>"
    # )
    # logger.add(sys.stderr, level=log_level, format=log_format)
    logger.add(sys.stderr, level=log_level)

    # Set LiteLLM environment variable
    os.environ["LITELLM_LOG"] = litellm_log


def setup_logging_from_config() -> None:
    """Set up logging using configuration from LLM config."""
    try:
        from src.config.llm_config import get_llm_config

        config = get_llm_config()
        logging_config = config.logging

        setup_logging(
            log_level=logging_config.log_level,
            litellm_log=logging_config.litellm_log,
        )

        logger.info(
            f"Logging configured: level={logging_config.log_level},"
            f" litellm={logging_config.litellm_log}"
        )

    except Exception as exc:
        logger.warning(f"Failed to load logging config, using defaults: {exc}")
        setup_logging()
