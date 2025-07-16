"""Telegram bot service module for TimeManager."""

from collections.abc import Callable
import datetime
from typing import TypedDict

from loguru import logger
from telethon import TelegramClient, events
from telethon.events import NewMessage

from src.config.settings import settings
from src.services.event_semantic_search import EventSemanticSearch
from src.services.google_calendar import CalendarEvent, GoogleCalendarService
from src.services.intent_parser import (
    BaseIntent,
    CreateIntent,
    FallbackIntent,
    LLMIntentParser,
    ListIntent,
    UpdateIntent,
)
from src.services.time_slot_manager import (
    EventRequest,
    RecurrenceFrequency,
    TimeSlotManager,
)


# Define TypedDict for user states
class UserState(TypedDict, total=False):
    """TypedDict for storing user conversation states."""

    state: str
    events: list[CalendarEvent]
    selected_event: CalendarEvent
    intent: BaseIntent


class TelegramBot:
    """Telegram bot for time management."""

    def __init__(self) -> None:
        """Initialize the Telegram bot."""
        self.client = TelegramClient(
            "time_manager_bot",
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )
        self.calendar_service = GoogleCalendarService(
            settings.google_credentials_file,
            settings.google_token_file,
        )
        self.time_slot_manager = TimeSlotManager(self.calendar_service)
        self.intent_parser = LLMIntentParser(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )
        self.semantic_search = EventSemanticSearch(
            model_name="all-MiniLM-L6-v2"
        )
        self.user_states: dict[int, UserState] = {}
        self._register_handlers()

    def _format_event(
        self,
        event: CalendarEvent,
        index: int | None = None,
        include_number: bool = True,
    ) -> str:
        """Format a calendar event for display in a message.

        Args:
            event: The calendar event to format
            index: Optional index number for the event in a list
            include_number: Whether to include the index number in the format

        Returns
        -------
            A formatted string representation of the event
        """
        start_time = event.start_time.strftime("%A, %B %d at %I:%M %p")
        end_time = event.end_time.strftime("%I:%M %p")

        response = [
            f"{index}. {event.summary}\n"
            if include_number and index is not None
            else f"{event.summary}\n"
        ]
        response.append(f"   📅 {start_time} - {end_time}\n")
        if event.location:
            response.append(f"   📍 {event.location}\n")

        if event.description:
            description = event.description
            if len(description) > 50:
                description = description[:47] + "..."
            response.append(f"   📝 {description}\n")

        response.append("\n")
        return "".join(response)

    def _register_handlers(self) -> None:
        """Register event handlers for the bot."""

        def _register_handler(
            pattern_or_func: str | Callable,
            handler: Callable,
        ) -> None:
            """Register a handler for a specific command pattern."""
            self.client.on(
                events.NewMessage(
                    **(
                        {"pattern": pattern_or_func}
                        if isinstance(pattern_or_func, str)
                        else {"func": pattern_or_func}  # type: ignore[dict-item]
                    )
                )
            )(handler)

        _register_handler("/start", self._start_handler)
        _register_handler("/help", self._help_handler)
        _register_handler("/schedule", self._schedule_handler)
        _register_handler("/update", self._update_handler)
        _register_handler("/delete", self._delete_handler)
        _register_handler("/cancel", self._cancel_handler)
        _register_handler("/freeslots", self._freeslots_handler)
        _register_handler(
            lambda event: event.text.startswith("/"),
            self._message_handler,
        )

    async def _start_handler(self, event: NewMessage.Event) -> None:
        """Handle the /start command."""
        await event.respond(
            "👋 Welcome to the Time Manager Bot!\n\n"
            "I can help you manage your calendar events. Here's what you can do:\n\n"
            "- Create an event: Just tell me what you want to schedule\n"
            "- Update an event: Use /update command\n"
            "- Delete an event: Use /delete command\n"
            "- View your schedule: Use /schedule command\n"
            "- Find free time slots: Use /freeslots command\n\n"
            "Try saying something like:\n"
            '"Schedule a meeting with John tomorrow at 2pm for 1 hour"'
        )

        # Reset user state
        sender = await event.get_sender()
        self.user_states[sender.id] = {"state": "idle"}

    async def _help_handler(self, event: NewMessage.Event) -> None:
        """Handle the /help command."""
        await event.respond(
            "🔍 Time Manager Bot Help\n\n"
            "Here are some examples of what you can say:\n\n"
            '- "Schedule a meeting with John tomorrow at 2pm for 1 hour"\n'
            '- "Create a dentist appointment next week"\n'
            '- "Set up a weekly team meeting every Monday at 10am for 4 weeks"\n\n'
            "Commands:\n"
            "/start - Start the bot\n"
            "/help - Show this help message\n"
            "/schedule - View your upcoming events\n"
            "/update - Update an existing event\n"
            "/delete - Delete an event\n"
            "/freeslots - Find free time slots\n"
            "/cancel - Cancel the current operation"
        )

    async def _schedule_handler(self, event: NewMessage.Event) -> None:
        """Handle the /schedule command."""
        sender = await event.get_sender()

        # Get events for the next 7 days
        now = datetime.datetime.now()
        end_date = now + datetime.timedelta(days=7)

        try:
            events = self.calendar_service.get_events(now, end_date)

            if not events:
                await event.respond(
                    "You don't have any upcoming events in the next 7 days."
                )
                return

            # Format the events
            response = "📅 Your upcoming events:\n\n"
            for i, calendar_event in enumerate(events, 1):
                response += self._format_event(calendar_event, i)

            await event.respond(response)

            # Store events in user state
            self.user_states[sender.id] = {
                "state": "viewing_events",
                "events": events,
            }

        except Exception as exc:
            logger.error(f"Error fetching events: {exc}")
            await event.respond(
                "Sorry, I couldn't fetch your events. Please try again later."
            )

    async def _update_handler(self, event: NewMessage.Event) -> None:
        """Handle the /update command."""
        sender = await event.get_sender()

        # Get events for the next 7 days
        now = datetime.datetime.now()
        end_date = now + datetime.timedelta(days=7)

        try:
            events = self.calendar_service.get_events(now, end_date)

            if not events:
                await event.respond(
                    "You don't have any upcoming events to update."
                )
                return

            # Format the events for selection
            response = (
                "📝 Select an event to update by replying with its number:\n\n"
            )
            for i, calendar_event in enumerate(events, 1):
                response += self._format_event(calendar_event, i)

            await event.respond(response)

            # Store events in user state
            self.user_states[sender.id] = {
                "state": "selecting_event_to_update",
                "events": events,
            }

        except Exception as exc:
            logger.error(f"Error fetching events for update: {exc}")
            await event.respond(
                "Sorry, I couldn't fetch your events. Please try again later."
            )

    async def _delete_handler(self, event: NewMessage.Event) -> None:
        """Handle the /delete command."""
        sender = await event.get_sender()

        # Get events for the next 7 days
        now = datetime.datetime.now()
        end_date = now + datetime.timedelta(days=7)

        try:
            events = self.calendar_service.get_events(now, end_date)

            if not events:
                await event.respond(
                    "You don't have any upcoming events to delete."
                )
                return

            # Format the events for selection
            response = (
                "🗑️ Select an event to delete by replying with its number:\n\n"
            )
            for i, calendar_event in enumerate(events, 1):
                response += self._format_event(calendar_event, i)

            await event.respond(response)

            # Store events in user state
            self.user_states[sender.id] = {
                "state": "selecting_event_to_delete",
                "events": events,
            }

        except Exception as exc:
            logger.error(f"Error fetching events for deletion: {exc}")
            await event.respond(
                "Sorry, I couldn't fetch your events. Please try again later."
            )

    async def _cancel_handler(self, event: NewMessage.Event) -> None:
        """Handle the /cancel command."""
        sender = await event.get_sender()

        # Reset user state
        self.user_states[sender.id] = {"state": "idle"}

        await event.respond(
            "Operation canceled. What would you like to do next?"
        )

    async def _freeslots_handler(self, event: NewMessage.Event) -> None:
        """Handle the /freeslots command."""
        sender = await event.get_sender()

        # Set default parameters
        days_ahead = 7
        duration_minutes = 60

        # Update user state
        self.user_states[sender.id] = {
            "state": "finding_free_slots",
        }

        await event.respond(
            "Looking for free time slots. By default, I'll look for"
            " 60-minute slots in the next 7 days.\n\n"
            "You can customize this by saying something like:\n"
            '- "Find 30 minute slots"\n'
            '- "Look for slots in the next 3 days"\n'
            '- "Find 2 hour meetings next week"'
        )

        # Find free slots with default parameters
        now = datetime.datetime.now()
        end_date = now + datetime.timedelta(days=days_ahead)

        try:
            free_slots = self.calendar_service.find_free_slots(
                now,
                end_date,
                duration_minutes,
                self.time_slot_manager.working_hours,
            )

            if not free_slots:
                await event.respond(
                    f"No free slots found in the next {days_ahead} days for"
                    f" {duration_minutes} minute events."
                )
                return

            response = (
                f"Available time slots for {duration_minutes} minute"
                f" events:\n\n"
            )

            # Group by date for better readability
            date_slots = {}

            for slot in free_slots:
                date_str = slot.strftime("%Y-%m-%d")
                time_str = slot.strftime("%I:%M %p")

                if date_str not in date_slots:
                    date_slots[date_str] = []

                date_slots[date_str].append(time_str)

            for date_str, times in date_slots.items():
                date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                formatted_date = date_obj.strftime("%A, %B %d")
                response += f"{formatted_date}:\n"

                for time_str in times:
                    response += f"  • {time_str}\n"

                response += "\n"

            await event.respond(response)

            # Reset user state
            self.user_states[sender.id] = {"state": "idle"}

        except Exception as exc:
            logger.error(f"Error finding free slots: {exc}")
            await event.respond(
                "Sorry, I couldn't find free time slots. Please try again later."
            )

    async def _message_handler(self, event: NewMessage.Event) -> None:
        """Handle general messages using intent parsing."""
        sender = await event.get_sender()
        user_id = sender.id
        message = event.text

        # Check if user is in the middle of an operation based on state
        if user_id in self.user_states:
            user_state = self.user_states[user_id]

            # Handle event selection for update
            if user_state.get("state") == "selecting_event_to_update":
                try:
                    selection = int(message.strip())
                    events = user_state.get("events", [])

                    if 1 <= selection <= len(events):
                        selected_event = events[selection - 1]

                        # Store the selected event and update state
                        self.user_states[user_id] = {
                            "state": "updating_event",
                            "selected_event": selected_event,
                        }

                        await event.respond(
                            f"Updating: {selected_event.summary}\n"
                            "Please tell me what you'd like to change. For example:\n"
                            "- Change title to Team Meeting\n"
                            "- Move to tomorrow at 3pm\n"
                            "- Change location to Conference Room B\n"
                            "- Make it 90 minutes long"
                        )
                    else:
                        await event.respond(
                            "Please select a valid event number."
                        )

                except ValueError:
                    await event.respond("Please enter a valid number.")

            # Handle event selection for delete
            elif user_state.get("state") == "selecting_event_to_delete":
                try:
                    selection = int(message.strip())
                    events = user_state.get("events", [])

                    if 1 <= selection <= len(events):
                        selected_event = events[selection - 1]

                        # Delete the event
                        try:
                            # Ensure event_id is not None before deleting
                            if selected_event.event_id is not None:
                                self.calendar_service.delete_event(
                                    selected_event.event_id
                                )
                                await event.respond(
                                    f"✅ Deleted: {selected_event.summary}"
                                )

                                # Reset user state
                                self.user_states[user_id] = {"state": "idle"}
                            else:
                                await event.respond(
                                    "Sorry, this event cannot be deleted (no event ID)."
                                )
                        except Exception as exc:
                            logger.error(f"Error deleting event: {exc}")
                            await event.respond(
                                "Sorry, I couldn't delete that event. Error: {exc}"
                            )
                    else:
                        await event.respond(
                            "Please select a valid event number."
                        )

                except ValueError:
                    await event.respond("Please enter a valid number.")

            # Handle event update
            elif user_state.get("state") == "updating_event":
                selected_event = user_state.get("selected_event")

                if selected_event:
                    # Parse update intent
                    try:
                        intent = await self.intent_parser.parse_intent(message)

                        if isinstance(intent, UpdateIntent):
                            # Update the event with the intent data
                            if intent.summary:
                                selected_event.summary = intent.summary
                            if intent.start_time:
                                selected_event.start_time = intent.start_time
                                # Adjust end time to maintain duration if not specified
                                if not intent.duration_minutes:
                                    duration = (
                                        selected_event.end_time
                                        - selected_event.start_time
                                    ).total_seconds() / 60
                                    selected_event.end_time = (
                                        selected_event.start_time
                                        + datetime.timedelta(
                                            minutes=int(duration)
                                        )
                                    )
                            if intent.duration_minutes:
                                selected_event.end_time = (
                                    selected_event.start_time
                                    + datetime.timedelta(
                                        minutes=intent.duration_minutes
                                    )
                                )
                            if intent.description:
                                selected_event.description = intent.description
                            if intent.location:
                                selected_event.location = intent.location

                            # Update the event
                            self.calendar_service.update_event(selected_event)

                            # Confirm the update
                            await event.respond(
                                f"✅ Updated: {selected_event.summary}\n"
                                f"Event has been successfully updated!"
                            )

                            # Reset user state
                            self.user_states[user_id] = {"state": "idle"}
                        else:
                            # If intent parsing failed to return an update intent
                            await event.respond(
                                "I'm not sure how to update the event with that information. "
                                "Please be more specific about what you want to change."
                            )

                    except Exception as exc:
                        logger.error(f"Error updating event: {exc}")
                        await event.respond(
                            f"Sorry, I couldn't update that event. Error: {exc}"
                        )
                else:
                    await event.respond(
                        "Sorry, I lost track of which event you were updating. Please try again."
                    )

            # Handle finding free slots with custom parameters
            elif user_state.get("state") == "finding_free_slots":
                try:
                    # Parse intent to get duration and days
                    intent = await self.intent_parser.parse_intent(message)
                    days_ahead = 7
                    duration_minutes = 60

                    # Try to extract parameters from the message
                    if (
                        isinstance(intent, CreateIntent)
                        and intent.duration_minutes
                    ):
                        duration_minutes = intent.duration_minutes

                    if (
                        isinstance(intent, ListIntent)
                        and intent.time_range_days
                    ):
                        days_ahead = intent.time_range_days

                    # Find free slots with updated parameters
                    now = datetime.datetime.now()
                    end_date = now + datetime.timedelta(days=days_ahead)

                    free_slots = self.calendar_service.find_free_slots(
                        now,
                        end_date,
                        duration_minutes,
                        self.time_slot_manager.working_hours,
                    )

                    if not free_slots:
                        await event.respond(
                            f"No free slots found in the next {days_ahead}"
                            f" days for {duration_minutes} minute events."
                        )
                        # Reset user state
                        self.user_states[user_id] = {"state": "idle"}
                        return

                    response = f"Available time slots for {duration_minutes} minute events:\n\n"

                    # Group by date for better readability
                    date_slots = {}

                    for slot in free_slots:
                        date_str = slot.strftime("%Y-%m-%d")
                        time_str = slot.strftime("%I:%M %p")

                        if date_str not in date_slots:
                            date_slots[date_str] = []

                        date_slots[date_str].append(time_str)

                    for date_str, times in date_slots.items():
                        date_obj = datetime.datetime.strptime(
                            date_str, "%Y-%m-%d"
                        )
                        formatted_date = date_obj.strftime("%A, %B %d")
                        response += f"{formatted_date}:\n"

                        for time_str in times:
                            response += f"  • {time_str}\n"

                        response += "\n"

                    await event.respond(response)

                except Exception as exc:
                    logger.error(f"Error finding free slots: {exc}")
                    await event.respond(
                        f"Sorry, I couldn't find free time slots. Error: {exc}"
                    )
                finally:
                    # Reset user state
                    self.user_states[user_id] = {"state": "idle"}

            else:
                # If not in a special state, parse intent normally
                await self._handle_general_message(event, message)
        else:
            # No state yet, parse intent normally
            await self._handle_general_message(event, message)

    async def _handle_general_message(
        self, event: NewMessage.Event, message: str
    ) -> None:
        """Handle general messages by parsing intent."""
        try:
            # Parse the message to determine intent
            intent = await self.intent_parser.parse_intent(message)

            # Log the intent type that was determined
            logger.info(
                f"Handling message with intent type: {intent.intent_type}"
            )

            if isinstance(intent, CreateIntent):
                await self._handle_create_intent(event, intent)
            elif isinstance(intent, ListIntent):
                await self._handle_list_intent(event, intent)
            elif isinstance(intent, UpdateIntent):
                await self._handle_update_intent(event, intent)
            elif isinstance(intent, FallbackIntent):
                await self._handle_fallback_intent(event, intent)
            else:
                await event.respond(
                    "I'm not sure what you want to do. You can create an"
                    " event, update an event with /update, delete an"
                    " event with /delete, or view your schedule with"
                    " /schedule."
                )

        except Exception as exc:
            logger.error(f"Error handling message: {exc}")
            await event.respond(
                "Sorry, I encountered an error processing your request. Please try again."
            )

    async def _handle_create_intent(
        self, event: NewMessage.Event, intent: CreateIntent
    ) -> None:
        """Handle a create intent by creating a calendar event."""
        try:
            # Create an event request
            request = EventRequest(
                summary=intent.summary,
                duration_minutes=intent.duration_minutes
                or 60,  # Default to 60 minutes
                description=intent.description,
                location=intent.location,
                recurrence=intent.recurrence,
                recurrence_count=intent.recurrence_count,
            )

            # Set start time if provided
            if intent.start_time:
                request.start_time = intent.start_time

            # Schedule the event
            if (
                intent.recurrence != RecurrenceFrequency.NONE
                and intent.recurrence_count > 0
            ):
                # Store event_ids but don't use directly
                _ = self.time_slot_manager.schedule_recurring_event(request)
                await event.respond(
                    f"✅ Created {intent.recurrence_count} recurring events: {intent.summary}"
                )
            else:
                event_id = self.time_slot_manager.schedule_event(request)

                # Get the created event details
                now = datetime.datetime.now()
                end_date = now + datetime.timedelta(days=30)
                events = self.calendar_service.get_events(now, end_date)
                created_event = next(
                    (e for e in events if e.event_id == event_id), None
                )

                if created_event is not None:
                    response = "✅ Event created:\n\n"
                    response += self._format_event(
                        created_event, include_number=False
                    )
                    await event.respond(response)
                else:
                    await event.respond(f"✅ Event created: {intent.summary}")

        except ValueError as exc:
            await event.respond(f"Error: {exc}")
        except Exception as exc:
            logger.error(f"Error creating event: {exc}")
            await event.respond(
                "Sorry, I couldn't create that event. Please try again."
            )

    async def _handle_list_intent(
        self, event: NewMessage.Event, intent: ListIntent
    ) -> None:
        """Handle a list intent by showing upcoming events."""
        try:
            days = intent.time_range_days or 7

            now = datetime.datetime.now()
            if intent.start_date:
                start_date = intent.start_date
            else:
                start_date = now

            if intent.end_date:
                end_date = intent.end_date
            else:
                end_date = start_date + datetime.timedelta(days=days)

            # Log the date range being used
            logger.info(
                f"Fetching events from {start_date} to {end_date} for list intent"
            )

            events = self.calendar_service.get_events(start_date, end_date)

            # Log the number of events found
            logger.info(f"Found {len(events)} events for list intent")

            if not events:
                await event.respond(
                    f"You don't have any events scheduled"
                    f" between {start_date.date()} and {end_date.date()}."
                )
                return

            # Format the events
            response = f"📅 Your schedule from {start_date.date()} to {end_date.date()}:\n\n"
            for i, calendar_event in enumerate(events, 1):
                response += self._format_event(calendar_event, i)

            # Log that we're sending a response with events
            logger.info(f"Sending response with {len(events)} events")
            await event.respond(response)

        except Exception as exc:
            logger.error(f"Error listing events: {exc}")
            await event.respond(
                "Sorry, I couldn't retrieve your schedule. Please try again."
            )

    async def _handle_update_intent(
        self, event: NewMessage.Event, intent: UpdateIntent
    ) -> None:
        """Handle an update intent by finding and updating a calendar event."""
        sender = await event.get_sender()
        user_id = sender.id

        try:
            # Get events for the next 30 days to search through
            now = datetime.datetime.now()
            end_date = now + datetime.timedelta(days=30)
            events = self.calendar_service.get_events(now, end_date)

            if not events:
                await event.respond(
                    "You don't have any upcoming events to update."
                )
                return

            selected_event = None

            # First check if an event index was specified
            if (
                intent.event_selection is not None
                and 1 <= intent.event_selection <= len(events)
            ):
                selected_event = events[intent.event_selection - 1]
                logger.info(
                    f"Selected event by index: {selected_event.summary}"
                )
            # Then check if an event_id was provided
            elif intent.event_id is not None:
                selected_event = next(
                    (e for e in events if e.event_id == intent.event_id), None
                )
                if selected_event:
                    logger.info(
                        f"Selected event by ID: {selected_event.summary}"
                    )
            # Finally, use semantic search to find by name if provided
            elif intent.event_name is not None:
                selected_event, similarity = (
                    self.semantic_search.find_similar_event(
                        intent.event_name, events
                    )
                )
                if selected_event:
                    logger.info(
                        f"Selected event by semantic search: {selected_event.summary} "
                        f"(similarity: {similarity:.2f})"
                    )

            if selected_event is None:
                # No event found, ask user to select from list
                response = "I couldn't find the event you mentioned. Please select one:"
                for i, calendar_event in enumerate(events, 1):
                    response += f"\n{i}. {calendar_event.summary}"
                await event.respond(response)

                # Update user state for event selection
                self.user_states[user_id] = {
                    "state": "selecting_event_to_update",
                    "events": events,
                    "intent": intent,  # Store the intent to apply updates later
                }
                return

            # Update the selected event
            if intent.summary:
                selected_event.summary = intent.summary
            if intent.start_time:
                selected_event.start_time = intent.start_time
                # Adjust end time to maintain duration if not specified
                if not intent.duration_minutes:
                    duration = (
                        selected_event.end_time - selected_event.start_time
                    ).total_seconds() / 60
                    selected_event.end_time = (
                        selected_event.start_time
                        + datetime.timedelta(minutes=int(duration))
                    )
            if intent.duration_minutes:
                selected_event.end_time = (
                    selected_event.start_time
                    + datetime.timedelta(minutes=intent.duration_minutes)
                )
            if intent.description:
                selected_event.description = intent.description
            if intent.location:
                selected_event.location = intent.location

            # Update the event
            self.calendar_service.update_event(selected_event)

            # Confirm the update
            await event.respond(
                f"✅ Updated: {selected_event.summary}\n"
                f"Event has been successfully updated!"
            )

            # Reset user state
            self.user_states[user_id] = {"state": "idle"}

        except Exception as exc:
            logger.error(f"Error handling update intent: {exc}")
            await event.respond(
                "Sorry, I couldn't update that event. Please try again."
            )

    async def _handle_fallback_intent(
        self, event: NewMessage.Event, intent: FallbackIntent
    ) -> None:
        """Handle fallback intent when specific intent cannot be determined."""
        await event.respond(intent.llm_response)

    async def start(self) -> None:
        """
        Start the bot and run until disconnected.

        This method connects to the Telegram API and starts listening for messages.
        """
        await self.client.start(bot_token=settings.telegram_bot_token)

        logger.info("Bot started")

        # Run the bot until disconnected
        await self.client.run_until_disconnected()

    def run(self) -> None:
        """
        Run the bot in an asyncio event loop.

        This method creates an event loop and runs the bot until it's disconnected.
        """
        import asyncio

        # Create a new event loop and run the bot
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.start())
