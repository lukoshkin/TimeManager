import sys

from loguru import logger


def setup_logging(log_level: str = "INFO") -> None:
    """Configure logging for the application.

    Args:
        log_level: The logging level to use
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
