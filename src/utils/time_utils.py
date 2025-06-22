"""Time-related utility functions."""

from datetime import datetime


def time_aware_text(text: str, *args: str) -> str:
    """Format the text with the current date and time.

    Args:
        text: The text template with {today} and {time} placeholders
        *args: Placeholder names that should be preserved for later formatting

    Returns:
        The formatted text with current date and time
    """
    now = datetime.now()
    kwargs = {arg: f"{{{arg}}}" for arg in args}
    return text.format(
        today=now.strftime("%Y-%m-%d"), time=now.strftime("%H:%M:%S"), **kwargs
    )
