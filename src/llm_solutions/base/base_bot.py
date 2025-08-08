"""Base interface for Telegram bot implementations."""

from abc import ABC, abstractmethod
from typing import Any

from telethon import TelegramClient
from telethon.events import NewMessage

from src.services.google_calendar import GoogleCalendarService
from src.services.time_slot_manager import TimeSlotManager


class BaseTelegramBot(ABC):
    """Abstract base class for Telegram bot implementations."""

    def __init__(self) -> None:
        """Initialize the base bot with common services."""
        self.client: TelegramClient | None = None
        self.calendar_service: GoogleCalendarService | None = None
        self.time_slot_manager: TimeSlotManager | None = None
        self.user_states: dict[int, Any] = {}

    @abstractmethod
    def _initialize_services(self) -> None:
        """Initialize bot services (calendar, time manager, etc.)."""

    @abstractmethod
    def _register_handlers(self) -> None:
        """Register event handlers for the bot."""

    @abstractmethod
    async def _message_handler(self, event: NewMessage.Event) -> None:
        """Handle incoming messages."""

    @abstractmethod
    async def start(self) -> None:
        """Start the bot and run until disconnected."""

    def run(self) -> None:
        """Run the bot in an asyncio event loop."""
        import asyncio

        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(self.start())
        except KeyboardInterrupt:
            from src.config.logging import logger

            logger.info("Bot stopped by user")

    def _reset_user_state(self, user_id: int) -> None:
        """Reset user state to idle."""
        self.user_states[user_id] = {"state": "idle"}
