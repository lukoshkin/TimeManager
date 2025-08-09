"""Telegram bot service module for TimeManager."""

import datetime
from typing import TypedDict, cast

from telethon import TelegramClient, events
from telethon.events import NewMessage

from src.config.env import settings
from src.config.logging import logger
from src.services.event_milvus_connector import (
    EventMilvusConfig,
    EventMilvusConnector,
)
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

DEFAULT_DAYS_AHEAD = 7
DEFAULT_DURATION_MINUTES = 60
DEFAULT_EVENT_SEARCH_DAYS = 30
MAX_DESCRIPTION_LENGTH = 50


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
        milvus_config = EventMilvusConfig(
            uri=settings.milvus_uri,
            collection_name=settings.milvus_collection_name,
            vector_dim=settings.milvus_vector_dim,
            model_name=settings.milvus_model_name,
            embedding_provider=settings.milvus_model_provider,
        )
        self.semantic_search = EventMilvusConnector(milvus_config)

        try:
            self.semantic_search.create_collection()
        except Exception as exc:
            logger.warning(f"Could not create Milvus collection: {exc}")

        self.user_states: dict[int, UserState] = {}
        self._register_handlers()

    def _reset_user_state(self, user_id: int) -> None:
        """Reset user state to idle."""
        self.user_states[user_id] = {"state": "idle"}

    async def _handle_error(
        self,
        event: NewMessage.Event,
        user_id: int,
        error: Exception,
        operation: str,
    ) -> None:
        """Handle errors consistently across all operations."""
        logger.error(f"Error in {operation}: {error}")
        await event.respond(
            "Sorry, I encountered an error processing your request. Please try again."
        )
        self._reset_user_state(user_id)

    def _populate_milvus_with_events(
        self, events: list[CalendarEvent]
    ) -> None:
        """Populate Milvus with events for semantic search.

        Uses upsert to handle potential duplicate events safely.

        Args:
            events: List of CalendarEvent objects to store
        """
        if not events:
            return

        try:
            self.semantic_search.upsert_events(events)
            logger.info(f"Updated Milvus with {len(events)} events")
        except Exception as exc:
            logger.warning(f"Could not update Milvus with events: {exc}")

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
            desc = event.description
            if len(desc) > MAX_DESCRIPTION_LENGTH:
                desc = desc[: MAX_DESCRIPTION_LENGTH - 3] + "..."
            response.append(f"   📝 {desc}\n")
            response.append("\n")
        return "".join(response)

    def _format_free_slots_response(
        self, free_slots: list, duration_minutes: int
    ) -> str:
        """Format free slots into a readable response."""
        response = (
            f"Available time slots for {duration_minutes} minute events:\n\n"
        )
        date_slots: dict[str, list[str]] = {}
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

        return response

    def _find_event_for_update(
        self, intent: UpdateIntent, events: list[CalendarEvent]
    ) -> CalendarEvent | None:
        """Find the event to update based on the intent criteria."""
        if (
            intent.event_selection is not None
            and 1 <= intent.event_selection <= len(events)
        ):
            selected_event = events[intent.event_selection - 1]
            logger.info(f"Selected event by index: {selected_event.summary}")
            return selected_event

        if intent.event_id is not None:
            selected_event = next(
                (e for e in events if e.event_id == intent.event_id),
                cast(CalendarEvent, None),  # only to suppress mypy warning
            )
            if selected_event:
                logger.info(f"Selected event by ID: {selected_event.summary}")
                return selected_event

        if intent.event_name is not None:
            result = self.semantic_search.most_similar_event(intent.event_name)
            if result[0] is not None:
                logger.info(
                    f"Selected event by semantic search: {result[0].summary} "
                    f"(similarity: {result[1]:.2f})"
                )
                return result[0]

        return None

    def _log_milvus_debug_info(self, operation: str) -> None:
        """Log debug information about recent events in Milvus.

        Args:
            operation: The operation that triggered this debug log
            (e.g., 'create', 'update', 'delete', 'list')
        """
        try:
            recent_events = self.semantic_search.get_recent_events(limit=5)
            logger.debug(f"[{operation.upper()} DEBUG] Milvus DB state:")
            logger.debug(
                f"[{operation.upper()} DEBUG]"
                f" Total events in DB: {self.semantic_search.count_events()}"
            )
            if recent_events:
                logger.debug(
                    f"[{operation.upper()} DEBUG] Last 5 events in DB:"
                )
                for i, event in enumerate(recent_events, 1):
                    logger.debug(
                        f"[{operation.upper()} DEBUG] {i}. {event.summary} "
                        f"({event.start_time.strftime('%Y-%m-%d %H:%M')} - "
                        f"{event.end_time.strftime('%H:%M')})"
                        f" [ID: {event.event_id}]"
                    )
            else:
                logger.debug(
                    f"[{operation.upper()} DEBUG] No events found in Milvus DB"
                )
        except Exception as exc:
            logger.warning(
                f"[{operation.upper()} DEBUG]"
                f" Could not retrieve Milvus debug info: {exc}"
            )

    def _register_handlers(self) -> None:
        """Register event handlers for the bot."""
        handlers = [
            ("/start", self._start_handler),
            ("/help", self._help_handler),
            ("/schedule", self._schedule_handler),
            ("/update", self._update_handler),
            ("/delete", self._delete_handler),
            ("/cancel", self._cancel_handler),
            ("/freeslots", self._freeslots_handler),
        ]

        for pattern, handler in handlers:
            self.client.on(events.NewMessage(pattern=pattern))(handler)

        self.client.on(
            events.NewMessage(
                func=lambda event: not event.text.startswith("/")
            )
        )(self._message_handler)

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
        now = datetime.datetime.now()
        end_date = now + datetime.timedelta(days=DEFAULT_DAYS_AHEAD)

        try:
            events = self.calendar_service.get_events(now, end_date)
            self._log_milvus_debug_info("schedule_list")
        except Exception as exc:
            await self._handle_error(event, sender.id, exc, "schedule_handler")
            return

        if not events:
            await event.respond(
                "You don't have any upcoming events in the next 7 days."
            )
            return

        response = "📅 Your upcoming events:\n\n"
        for i, calendar_event in enumerate(events, 1):
            response += self._format_event(calendar_event, i)

        await event.respond(response)
        self.user_states[sender.id] = {
            "state": "viewing_events",
            "events": events,
        }

    async def _update_handler(self, event: NewMessage.Event) -> None:
        """Handle the /update command."""
        sender = await event.get_sender()
        now = datetime.datetime.now()
        end_date = now + datetime.timedelta(days=DEFAULT_DAYS_AHEAD)

        try:
            events = self.calendar_service.get_events(now, end_date)
        except Exception as exc:
            await self._handle_error(event, sender.id, exc, "update_handler")
            return

        if not events:
            await event.respond(
                "You don't have any upcoming events to update."
            )
            return

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

    async def _delete_handler(self, event: NewMessage.Event) -> None:
        """Handle the /delete command."""
        sender = await event.get_sender()
        now = datetime.datetime.now()
        end_date = now + datetime.timedelta(days=DEFAULT_DAYS_AHEAD)

        try:
            events = self.calendar_service.get_events(now, end_date)
        except Exception as exc:
            await self._handle_error(event, sender.id, exc, "delete_handler")
            return

        if not events:
            await event.respond(
                "You don't have any upcoming events to delete."
            )
            return

        response = (
            "🗑️ Select an event to delete by replying with its number:\n\n"
        )
        for i, calendar_event in enumerate(events, 1):
            response += self._format_event(calendar_event, i)

        await event.respond(response)
        self.user_states[sender.id] = {
            "state": "selecting_event_to_delete",
            "events": events,
        }

    async def _cancel_handler(self, event: NewMessage.Event) -> None:
        """Handle the /cancel command."""
        sender = await event.get_sender()

        self._reset_user_state(sender.id)

        await event.respond(
            "Operation canceled. What would you like to do next?"
        )

    async def _freeslots_handler(self, event: NewMessage.Event) -> None:
        """Handle the /freeslots command."""
        sender = await event.get_sender()
        days_ahead = DEFAULT_DAYS_AHEAD
        duration_minutes = DEFAULT_DURATION_MINUTES
        self.user_states[sender.id] = {"state": "finding_free_slots"}

        await event.respond(
            "Looking for free time slots. By default, I'll look for"
            " 60-minute slots in the next 7 days.\n\n"
            "You can customize this by saying something like:\n"
            '- "Find 30 minute slots"\n'
            '- "Look for slots in the next 3 days"\n'
            '- "Find 2 hour meetings next week"'
        )

        now = datetime.datetime.now()
        end_date = now + datetime.timedelta(days=days_ahead)

        try:
            free_slots = self.calendar_service.find_free_slots(
                now,
                end_date,
                duration_minutes,
                self.time_slot_manager.working_hours,
            )
        except Exception as exc:
            logger.error(f"Error finding free slots: {exc}")
            await event.respond(
                "Sorry, I couldn't find free time slots. Please try again later."
            )
            return

        if not free_slots:
            await event.respond(
                f"No free slots found in the next {days_ahead} days for"
                f" {duration_minutes} minute events."
            )
            return

        response = self._format_free_slots_response(
            free_slots, duration_minutes
        )
        await event.respond(response)
        self._reset_user_state(sender.id)

    async def _handle_event_selection_for_update(
        self, event: NewMessage.Event, user_id: int, message: str
    ) -> None:
        """Handle event selection for update operation."""
        user_state = self.user_states[user_id]
        events = user_state.get("events", [])

        try:
            selection = int(message.strip())
        except ValueError:
            await event.respond("Please enter a valid number.")
            return
        except Exception as exc:
            await self._handle_error(
                event, user_id, exc, "event_selection_for_update"
            )
            return

        if not (1 <= selection <= len(events)):
            await event.respond("Please select a valid event number.")
            return

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

    async def _handle_event_selection_for_delete(
        self, event: NewMessage.Event, user_id: int, message: str
    ) -> None:
        """Handle event selection for delete operation."""
        user_state = self.user_states[user_id]
        try:
            selection = int(message.strip())
            events = user_state.get("events", [])

            if 1 <= selection <= len(events):
                selected_event = events[selection - 1]

                try:
                    if selected_event.event_id is not None:
                        self.calendar_service.delete_event(
                            selected_event.event_id
                        )
                        self._log_milvus_debug_info("delete")
                        await event.respond(
                            f"✅ Deleted: {selected_event.summary}"
                        )
                        self.user_states[user_id] = {"state": "idle"}
                    else:
                        await event.respond(
                            "Sorry, this event cannot be deleted (no event ID)."
                        )
                except Exception as exc:
                    logger.error(f"Error deleting event: {exc}")
                    await event.respond(
                        f"Sorry, I couldn't delete that event. Error: {exc}"
                    )
            else:
                await event.respond("Please select a valid event number.")

        except ValueError:
            await event.respond("Please enter a valid number.")
        except Exception as exc:
            logger.error(f"Error in event selection for delete: {exc}")
            await event.respond(
                "Sorry, I encountered an error. Please try again."
            )
            self.user_states[user_id] = {"state": "idle"}

    async def _handle_event_update_input(
        self, event: NewMessage.Event, user_id: int, message: str
    ) -> None:
        """Handle event update input from user."""
        user_state = self.user_states[user_id]
        selected_event = user_state.get("selected_event")

        if selected_event is not None:
            # Parse update intent
            try:
                intent = await self.intent_parser.parse_intent(message)

                if isinstance(intent, UpdateIntent):
                    self._update_with_intent_data(selected_event, intent)
                    self.user_states[user_id] = {"state": "idle"}
                    await event.respond(
                        f"✅ Updated: {selected_event.summary}\n"
                        f"Event has been successfully updated!"
                    )
                else:
                    await event.respond(
                        "I'm not sure how to update the event with"
                        " that information. Please be more specific about"
                        " what you want to change."
                    )

            except Exception as exc:
                logger.error(f"Error updating event: {exc}")
                await event.respond(
                    f"Sorry, I couldn't update that event. Error: {exc}"
                )
                # Reset user state on error
                self.user_states[user_id] = {"state": "idle"}
        else:
            await event.respond(
                "Sorry, I lost track of which event you were updating."
                " Please try again."
            )
            self.user_states[user_id] = {"state": "idle"}

    def _update_with_intent_data(
        self, selected_event: CalendarEvent, intent: UpdateIntent
    ):
        if intent.summary:
            selected_event.summary = intent.summary
        if intent.start_time:
            selected_event.start_time = intent.start_time
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

        self.calendar_service.update_event(selected_event)

        try:
            self.semantic_search.upsert_events([selected_event])
            logger.info(f"Updated event in Milvus: {selected_event.summary}")
        except Exception as exc:
            logger.warning(f"Could not update event in Milvus: {exc}")

        self._log_milvus_debug_info("update")

    async def _handle_free_slots_customization(
        self, event: NewMessage.Event, user_id: int, message: str
    ) -> None:
        """Handle free slots customization input from user."""
        try:
            intent = await self.intent_parser.parse_intent(message)
            days_ahead = DEFAULT_DAYS_AHEAD
            duration_minutes = DEFAULT_DURATION_MINUTES

            if isinstance(intent, CreateIntent) and intent.duration_minutes:
                duration_minutes = intent.duration_minutes

            if isinstance(intent, ListIntent) and intent.time_range_days:
                days_ahead = intent.time_range_days

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
                self.user_states[user_id] = {"state": "idle"}
                return

            response = f"Available time slots for {duration_minutes} minute events:\n\n"
            date_slots: dict[str, list[str]] = {}

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

        except Exception as exc:
            logger.error(f"Error finding free slots: {exc}")
            await event.respond(
                "Sorry, I couldn't find free time slots. Please try again later."
            )
        finally:
            # Reset user state
            self.user_states[user_id] = {"state": "idle"}

    async def _message_handler(self, event: NewMessage.Event) -> None:
        """Handle general messages using intent parsing."""
        sender = await event.get_sender()
        user_id = sender.id
        message = event.text

        # Ensure user state exists
        if user_id not in self.user_states:
            self.user_states[user_id] = {"state": "idle"}

        state = self.user_states[user_id].get("state", "idle")

        # Dispatch to appropriate state handler
        try:
            if state == "selecting_event_to_update":
                await self._handle_event_selection_for_update(
                    event, user_id, message
                )
            elif state == "selecting_event_to_delete":
                await self._handle_event_selection_for_delete(
                    event, user_id, message
                )
            elif state == "updating_event":
                await self._handle_event_update_input(event, user_id, message)
            elif state == "finding_free_slots":
                await self._handle_free_slots_customization(
                    event, user_id, message
                )
            else:
                # If not in a special state, parse intent normally
                await self._handle_general_message(event, message)
        except Exception as exc:
            logger.error(
                f"Error in message handler for state '{state}': {exc}"
            )
            await event.respond(
                "Sorry, I encountered an error processing your request. Please try again."
            )
            # Reset user state on error
            self.user_states[user_id] = {"state": "idle"}

    async def _handle_general_message(
        self, event: NewMessage.Event, message: str
    ) -> None:
        """Handle general messages by parsing intent."""
        try:
            intent = await self.intent_parser.parse_intent(message)
            logger.info(f"Handling message with intent: {intent}")

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
            request = EventRequest(
                summary=intent.summary,
                duration_minutes=intent.duration_minutes
                or DEFAULT_DURATION_MINUTES,  # Default to 60 minutes
                description=intent.description,
                location=intent.location,
                recurrence=intent.recurrence,
                recurrence_count=intent.recurrence_count,
            )

            if intent.start_time:
                request.start_time = intent.start_time

            if (
                intent.recurrence != RecurrenceFrequency.NONE
                and intent.recurrence_count > 0
            ):
                self.time_slot_manager.schedule_recurring_event(request)
                await event.respond(
                    f"✅ Created {intent.recurrence_count} recurring events:"
                    f" {intent.summary}"
                )
            else:
                event_id = self.time_slot_manager.schedule_event(request)
                now = datetime.datetime.now()
                end_date = now + datetime.timedelta(
                    days=DEFAULT_EVENT_SEARCH_DAYS
                )
                events = self.calendar_service.get_events(now, end_date)
                self._populate_milvus_with_events(events)
                self._log_milvus_debug_info("create")

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
            days = intent.time_range_days or DEFAULT_DAYS_AHEAD
            now = datetime.datetime.now()
            if intent.start_date:
                start_date = intent.start_date
            else:
                start_date = now

            if intent.end_date:
                end_date = intent.end_date
            else:
                end_date = start_date + datetime.timedelta(days=days)

            logger.info(f"Fetching events from {start_date} to {end_date}..")
            events = self.calendar_service.get_events(start_date, end_date)
            self._populate_milvus_with_events(events)
            logger.info(f"Found {len(events)} events for list intent")

            if not events:
                await event.respond(
                    f"You don't have any events scheduled"
                    f" between {start_date.date()} and {end_date.date()}."
                )
                return

            response = f"📅 Your schedule from {start_date.date()} to {end_date.date()}:\n\n"
            for i, calendar_event in enumerate(events, 1):
                response += self._format_event(calendar_event, i)

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
            now = datetime.datetime.now()
            end_date = now + datetime.timedelta(days=DEFAULT_EVENT_SEARCH_DAYS)
            events = self.calendar_service.get_events(now, end_date)
            self._populate_milvus_with_events(events)

            if not events:
                await event.respond(
                    "You don't have any upcoming events to update."
                )
                return

            selected_event = self._find_event_for_update(intent, events)
            if selected_event is None:
                response = "I couldn't find the event you mentioned. Please select one:"
                for i, calendar_event in enumerate(events, 1):
                    response += f"\n{i}. {calendar_event.summary}"

                await event.respond(response)
                self.user_states[user_id] = {
                    "state": "selecting_event_to_update",
                    "events": events,
                    "intent": intent,  # Store the intent to apply updates later
                }
                return

            self._update_with_intent_data(selected_event, intent)
            self.user_states[user_id] = {"state": "idle"}
            await event.respond(
                f"✅ Updated: {selected_event.summary}\n"
                f"Event has been successfully updated!"
            )

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
        await self.client.run_until_disconnected()

    def run(self) -> None:
        """
        Run the bot in an asyncio event loop.

        This method creates an event loop and runs the bot until it's disconnected.
        """
        import asyncio

        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(self.start())
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
