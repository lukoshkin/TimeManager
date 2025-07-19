import datetime
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from src.config.logging import logger
from src.config.settings import settings
from src.services.google_calendar import GoogleCalendarService
from src.services.time_slot_manager import (
    EventRequest,
    RecurrenceFrequency,
    TimeSlotManager,
)


@dataclass
class CalendarContext:
    """Application context for MCP server."""

    calendar_service: GoogleCalendarService
    time_slot_manager: TimeSlotManager


@asynccontextmanager
async def calendar_lifespan(
    _server: FastMCP,
) -> AsyncIterator[CalendarContext]:
    """Manage application lifecycle with type-safe context for MCP server."""
    calendar_service = GoogleCalendarService(
        settings.google_credentials_file,
        settings.google_token_file,
    )
    time_slot_manager = TimeSlotManager(calendar_service)
    ctx = CalendarContext(calendar_service, time_slot_manager)
    logger.info("Calendar services initialized for MCP server")
    yield ctx


class MCPServer:
    """MCP server implementation providing calendar access."""

    def __init__(self) -> None:
        """Initialize the MCP server."""
        self.mcp = FastMCP(
            "TimeManager",
            lifespan=calendar_lifespan,
            dependencies=[
                "google-api-python-client",
                "google-auth",
                "loguru",
            ],
        )
        self._register_resources()
        self._register_tools()

    def _register_resources(self) -> None:
        """Register resources for the MCP server."""

        @self.mcp.resource("calendar://events/{days}")
        def get_upcoming_events(days: int) -> str:
            """Get upcoming events for the specified number of days.

            Args:
                days: Number of days to look ahead

            Returns
            -------
                Formatted string with event information

            """
            ctx = self.mcp.get_context()
            calendar_service = (
                ctx.request_context.lifespan_context.calendar_service
            )
            now = datetime.datetime.now()
            end_date = now + datetime.timedelta(days=days)
            events = calendar_service.get_events(now, end_date)

            if not events:
                return "No upcoming events found."

            result = f"Upcoming events for the next {days} days:\n\n"

            for event in events:
                start_time = event.start_time.strftime("%A, %B %d at %I:%M %p")
                end_time = event.end_time.strftime("%I:%M %p")

                result += f"• {event.summary}\n"
                result += f"  {start_time} - {end_time}\n"

                if event.location:
                    result += f"  📍 {event.location}\n"

                result += "\n"

            return result

        @self.mcp.resource("calendar://availability/{start_days}/{end_days}")
        def get_availability(start_days: int, end_days: int) -> str:
            """Get availability information for a date range.

            Args:
                start_days: Days from now to start looking
                end_days: Days from now to end looking

            Returns
            -------
                Formatted string with availability information

            """
            ctx = self.mcp.get_context()
            time_slot_manager = (
                ctx.request_context.lifespan_context.time_slot_manager
            )

            now = datetime.datetime.now()
            start_date = now + datetime.timedelta(days=start_days)
            end_date = now + datetime.timedelta(days=end_days)

            # Default to 1 hour slots
            duration_minutes = 60

            free_slots = time_slot_manager.calendar_service.find_free_slots(
                start_date,
                end_date,
                duration_minutes,
                time_slot_manager.working_hours,
            )

            if not free_slots:
                return (
                    f"No free slots found between {start_date.date()}"
                    f" and {end_date.date()}."
                )

            result = (
                f"Available time slots between {start_date.date()}"
                f" and {end_date.date()}:\n\n"
            )
            # Group by date for better readability
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
                result += f"{formatted_date}:\n"

                for time_str in times:
                    result += f"  • {time_str}\n"

                result += "\n"

            return result

    def _register_tools(self) -> None:
        """Register tools for the MCP server."""

        @self.mcp.tool()
        def list_events(days: int = 7) -> str:
            """List all upcoming events for the specified number of days.

            Args:
                days: Number of days to look ahead

            Returns
            -------
                Formatted string with event information

            """
            ctx = self.mcp.get_context()
            calendar_service = (
                ctx.request_context.lifespan_context.calendar_service
            )

            now = datetime.datetime.now()
            end_date = now + datetime.timedelta(days=days)

            events = calendar_service.get_events(now, end_date)

            if not events:
                return "No upcoming events found."

            result = f"Upcoming events for the next {days} days:\n\n"

            for event in events:
                start_time = event.start_time.strftime("%A, %B %d at %I:%M %p")
                end_time = event.end_time.strftime("%I:%M %p")

                result += f"• {event.summary}\n"
                result += f"  {start_time} - {end_time}\n"

                if event.location:
                    result += f"  📍 {event.location}\n"

                result += "\n"

            return result

        @self.mcp.tool()
        def create_event(
            summary: str,
            start_time: str | None = None,
            duration_minutes: int = 60,
            description: str | None = None,
            location: str | None = None,
        ) -> str:
            """Create a new calendar event.

            Args:
                summary: Event title/summary
                start_time: Start time in ISO format (YYYY-MM-DDTHH:MM:SS)
                duration_minutes: Event duration in minutes
                description: Event description
                location: Event location

            Returns
            -------
                Confirmation message with event details

            """
            ctx = self.mcp.get_context()
            time_slot_manager = (
                ctx.request_context.lifespan_context.time_slot_manager
            )

            # Create event request
            request = EventRequest(
                summary=summary,
                duration_minutes=duration_minutes,
                description=description,
                location=location,
            )

            # Parse start time if provided
            if start_time:
                try:
                    request.start_time = datetime.datetime.fromisoformat(
                        start_time,
                    )
                except ValueError:
                    return "Error: Invalid time format. Please use ISO format (YYYY-MM-DDTHH:MM:SS)."

            try:
                # Schedule the event
                event_id = time_slot_manager.schedule_event(request)

                # Get the created event to show details
                calendar_service = (
                    ctx.request_context.lifespan_context.calendar_service
                )
                events = calendar_service.get_events(
                    datetime.datetime.now(),
                    datetime.datetime.now() + datetime.timedelta(days=30),
                )

                created_event = next(
                    (e for e in events if e.event_id == event_id),
                    None,
                )

                if created_event:
                    start_time_str = created_event.start_time.strftime(
                        "%A, %B %d at %I:%M %p",
                    )
                    end_time_str = created_event.end_time.strftime("%I:%M %p")

                    result = "Event created successfully:\n\n"
                    result += f"• {created_event.summary}\n"
                    result += f"  {start_time_str} - {end_time_str}\n"

                    if created_event.location:
                        result += f"  📍 {created_event.location}\n"

                    return result
                return "Event created successfully!"

            except ValueError as ex:
                return f"Error: {ex!s}"
            except Exception as ex:
                logger.error(f"Error creating event: {ex}")
                return "Error creating event. Please try again."

        @self.mcp.tool()
        def create_recurring_event(
            summary: str,
            recurrence: str,
            recurrence_count: int,
            start_time: str | None = None,
            duration_minutes: int = 60,
            description: str | None = None,
            location: str | None = None,
        ) -> str:
            """Create a recurring calendar event.

            Args:
                summary: Event title/summary
                recurrence: Frequency of recurrence ('daily', 'weekly', or 'monthly')
                recurrence_count: Number of occurrences
                start_time: Start time in ISO format (YYYY-MM-DDTHH:MM:SS)
                duration_minutes: Event duration in minutes
                description: Event description
                location: Event location

            Returns
            -------
                Confirmation message with event details

            """
            ctx = self.mcp.get_context()
            time_slot_manager = (
                ctx.request_context.lifespan_context.time_slot_manager
            )

            # Validate recurrence
            try:
                recurrence_freq = RecurrenceFrequency.from_string(recurrence)
            except ValueError as ex:
                return f"Error: {ex!s}"

            # Create event request
            request = EventRequest(
                summary=summary,
                duration_minutes=duration_minutes,
                description=description,
                location=location,
                recurrence=recurrence_freq,
                recurrence_count=recurrence_count,
            )

            # Parse start time if provided
            if start_time:
                try:
                    request.start_time = datetime.datetime.fromisoformat(
                        start_time,
                    )
                except ValueError:
                    return "Error: Invalid time format. Please use ISO format (YYYY-MM-DDTHH:MM:SS)."

            try:
                # Schedule the recurring event
                event_ids = time_slot_manager.schedule_recurring_event(request)

                # Get the first event to show details
                calendar_service = (
                    ctx.request_context.lifespan_context.calendar_service
                )
                events = calendar_service.get_events(
                    datetime.datetime.now(),
                    datetime.datetime.now()
                    + datetime.timedelta(days=30 * recurrence_count),
                )

                first_event = next(
                    (e for e in events if e.event_id == event_ids[0]),
                    None,
                )

                if first_event:
                    start_time_str = first_event.start_time.strftime(
                        "%A, %B %d at %I:%M %p",
                    )
                    end_time_str = first_event.end_time.strftime("%I:%M %p")

                    result = (
                        f"Created {recurrence_count} recurring events:\n\n"
                    )
                    result += f"• {first_event.summary}\n"
                    result += f"  First occurrence: {start_time_str} - {end_time_str}\n"
                    result += (
                        f"  Repeats: {recurrence}, {recurrence_count} times"
                    )

                    return result
                return f"Created {recurrence_count} recurring events successfully!"

            except ValueError as ex:
                return f"Error: {ex!s}"
            except Exception as ex:
                logger.error(f"Error creating recurring event: {ex}")
                return "Error creating recurring event. Please try again."

        @self.mcp.tool()
        def delete_event(event_id: str) -> str:
            """Delete a calendar event by ID.

            Args:
                event_id: The ID of the event to delete

            Returns
            -------
                Confirmation message

            """
            ctx = self.mcp.get_context()
            calendar_service = (
                ctx.request_context.lifespan_context.calendar_service
            )

            try:
                # Get the event first to confirm it exists
                now = datetime.datetime.now()
                end_date = now + datetime.timedelta(days=30)
                events = calendar_service.get_events(now, end_date)

                event = next(
                    (e for e in events if e.event_id == event_id),
                    None,
                )

                if not event:
                    return f"Error: Event with ID {event_id} not found."

                # Delete the event
                calendar_service.delete_event(event_id)

                return f"Event '{event.summary}' deleted successfully."

            except Exception as ex:
                logger.error(f"Error deleting event: {ex}")
                return "Error deleting event. Please try again."

        @self.mcp.tool()
        def update_event(
            event_id: str,
            summary: str | None = None,
            start_time: str | None = None,
            duration_minutes: int | None = None,
            description: str | None = None,
            location: str | None = None,
        ) -> str:
            """Update an existing calendar event.

            Args:
                event_id: The ID of the event to update
                summary: New event title/summary
                start_time: New start time in ISO format (YYYY-MM-DDTHH:MM:SS)
                duration_minutes: New event duration in minutes
                description: New event description
                location: New event location

            Returns
            -------
                Confirmation message with updated event details

            """
            ctx = self.mcp.get_context()
            calendar_service = (
                ctx.request_context.lifespan_context.calendar_service
            )

            try:
                # Get the event first
                now = datetime.datetime.now()
                end_date = now + datetime.timedelta(days=30)
                events = calendar_service.get_events(now, end_date)

                event = next(
                    (e for e in events if e.event_id == event_id),
                    None,
                )

                if not event:
                    return f"Error: Event with ID {event_id} not found."

                # Update fields as needed
                if summary:
                    event.summary = summary

                # Parse and update start_time if provided
                if start_time:
                    try:
                        new_start_time = datetime.datetime.fromisoformat(
                            start_time,
                        )

                        # If we have a new duration, use it to calculate end_time
                        if duration_minutes:
                            event.start_time = new_start_time
                            event.end_time = (
                                new_start_time
                                + datetime.timedelta(minutes=duration_minutes)
                            )
                        else:
                            # Keep the same duration
                            duration = (
                                event.end_time - event.start_time
                            ).total_seconds() / 60
                            event.start_time = new_start_time
                            event.end_time = (
                                new_start_time
                                + datetime.timedelta(minutes=int(duration))
                            )
                    except ValueError:
                        return "Error: Invalid time format. Please use ISO format (YYYY-MM-DDTHH:MM:SS)."
                # If only duration is changing, keep the same start_time but update end_time
                elif duration_minutes:
                    event.end_time = event.start_time + datetime.timedelta(
                        minutes=duration_minutes,
                    )

                if description:
                    event.description = description

                if location:
                    event.location = location

                # Update the event
                calendar_service.update_event(event)

                # Get updated details
                start_time_str = event.start_time.strftime(
                    "%A, %B %d at %I:%M %p",
                )
                end_time_str = event.end_time.strftime("%I:%M %p")

                result = "Event updated successfully:\n\n"
                result += f"• {event.summary}\n"
                result += f"  {start_time_str} - {end_time_str}\n"

                if event.location:
                    result += f"  📍 {event.location}\n"

                return result

            except Exception as ex:
                logger.error(f"Error updating event: {ex}")
                return "Error updating event. Please try again."

        @self.mcp.tool()
        def find_free_slots(
            days_ahead: int = 7,
            duration_minutes: int = 60,
            working_hours_start: int | None = None,
            working_hours_end: int | None = None,
        ) -> str:
            """Find free time slots in the calendar.

            Args:
                days_ahead: Number of days to look ahead
                duration_minutes: Desired slot duration in minutes
                working_hours_start: Start of working hours (0-23)
                working_hours_end: End of working hours (0-23)

            Returns
            -------
                Formatted string with available time slots

            """
            ctx = self.mcp.get_context()
            time_slot_manager = (
                ctx.request_context.lifespan_context.time_slot_manager
            )

            # Set custom working hours if provided
            original_working_hours = time_slot_manager.working_hours

            if (
                working_hours_start is not None
                and working_hours_end is not None
            ):
                try:
                    time_slot_manager.set_working_hours(
                        working_hours_start,
                        working_hours_end,
                    )
                except ValueError:
                    return "Error: Invalid working hours. Start hour must be less than end hour and both must be between 0-24."

            try:
                now = datetime.datetime.now()
                end_date = now + datetime.timedelta(days=days_ahead)

                free_slots = (
                    time_slot_manager.calendar_service.find_free_slots(
                        now,
                        end_date,
                        duration_minutes,
                        time_slot_manager.working_hours,
                    )
                )

                # Reset to original working hours if they were changed
                if (
                    working_hours_start is not None
                    and working_hours_end is not None
                ):
                    time_slot_manager.working_hours = original_working_hours

                if not free_slots:
                    return (
                        f"No free slots found in the next {days_ahead} days"
                        f" for {duration_minutes} minute events."
                    )

                result = f"Available time slots for {duration_minutes} minute events:\n\n"

                # Group by date for better readability
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
                    result += f"{formatted_date}:\n"

                    for time_str in times:
                        result += f"  • {time_str}\n"

                    result += "\n"

                return result

            except Exception as ex:
                logger.error(f"Error finding free slots: {ex}")
                # Reset to original working hours if an error occurred
                if (
                    working_hours_start is not None
                    and working_hours_end is not None
                ):
                    time_slot_manager.working_hours = original_working_hours
                return "Error finding free slots. Please try again."

    def run(self) -> None:
        """Run the MCP server in the event loop."""
        self.mcp.run(transport="streamable-http")
