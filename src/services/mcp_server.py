import datetime
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastmcp import Context, FastMCP

from src.config.env import settings
from src.config.logging import logger
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

    def _get_calendar_service(self, ctx: Context) -> GoogleCalendarService:
        """Extract calendar service from context."""
        return ctx.request_context.lifespan_context.calendar_service

    def _get_time_slot_manager(self, ctx: Context) -> TimeSlotManager:
        """Extract time slot manager from context."""
        return ctx.request_context.lifespan_context.time_slot_manager

    def _format_event_time(
        self, start_time: datetime.datetime, end_time: datetime.datetime
    ) -> tuple[str, str]:
        """Format event start and end times for display."""
        start_str = start_time.strftime("%A, %B %d at %I:%M %p")
        end_str = end_time.strftime("%I:%M %p")
        return start_str, end_str

    def _format_events_list(self, events: list, days: int) -> str:
        """Format a list of events into a readable string."""
        if not events:
            return "No upcoming events found."

        result = [f"Upcoming events for the next {days} days:\n\n"]
        for event in events:
            start_str, end_str = self._format_event_time(
                event.start_time, event.end_time
            )
            result.append(f"• {event.summary}\n  {start_str} - {end_str}\n")

            if event.location:
                result.append(f"  📍 {event.location}\n")
            result.append("\n")

        return "".join(result)

    def _format_single_event(self, event) -> str:
        """Format a single event for display."""
        start_str, end_str = self._format_event_time(
            event.start_time, event.end_time
        )
        result = [f"• {event.summary}\n  {start_str} - {end_str}\n"]

        if event.location:
            result.append(f"  📍 {event.location}\n")

        return "".join(result)

    def _get_events_in_range(
        self,
        ctx: Context,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
    ) -> list:
        """Get events from calendar service within a date range."""
        calendar_service = self._get_calendar_service(ctx)
        return calendar_service.get_events(start_date, end_date)

    def _find_event_by_id(self, ctx: Context, event_id: str):
        """Find an event by ID within the next 30 days."""
        now = datetime.datetime.now()
        end_date = now + datetime.timedelta(days=30)
        events = self._get_events_in_range(ctx, now, end_date)

        return next((e for e in events if e.event_id == event_id), None)

    def _parse_iso_time(self, time_str: str) -> datetime.datetime:
        """Parse ISO format time string with proper error handling."""
        try:
            return datetime.datetime.fromisoformat(time_str)
        except ValueError as exc:
            raise ValueError(
                "Invalid time format."
                " Please use ISO format (YYYY-MM-DDTHH:MM:SS)."
            ) from exc

    def _group_slots_by_date(
        self, free_slots: list[datetime.datetime]
    ) -> dict[str, list[str]]:
        """Group free time slots by date for better readability."""
        date_slots: dict[str, list[str]] = {}

        for slot in free_slots:
            date_str = slot.strftime("%Y-%m-%d")
            time_str = slot.strftime("%I:%M %p")

            if date_str not in date_slots:
                date_slots[date_str] = []
            date_slots[date_str].append(time_str)

        return date_slots

    def _format_free_slots(
        self,
        free_slots: list[datetime.datetime],
        duration_minutes: int,
        date_range_desc: str,
    ) -> str:
        """Format free time slots into a readable string."""
        if not free_slots:
            return f"No free slots found {date_range_desc}."

        result = [
            f"Available time slots for {duration_minutes} minute events:\n\n"
        ]
        date_slots = self._group_slots_by_date(free_slots)

        for date_str, times in date_slots.items():
            date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%A, %B %d")
            result.append(f"{formatted_date}:\n")

            for time_str in times:
                result.append(f"  • {time_str}\n")
            result.append("\n")

        return "".join(result)

    def _create_event_request(
        self,
        summary: str,
        start_time: str | None = None,
        duration_minutes: int = 60,
        description: str | None = None,
        location: str | None = None,
        recurrence: RecurrenceFrequency = RecurrenceFrequency.NONE,
        recurrence_count: int = 0,
    ) -> EventRequest:
        """Create and configure an EventRequest object."""
        request = EventRequest(
            summary=summary,
            duration_minutes=duration_minutes,
            description=description,
            location=location,
            recurrence=recurrence,
            recurrence_count=recurrence_count,
        )
        if start_time:
            request.start_time = self._parse_iso_time(start_time)

        return request

    def _register_resources(self) -> None:
        """Register resources for the MCP server."""

        @self.mcp.resource("calendar://events/{days}")
        def get_upcoming_events(days: int, ctx: Context) -> str:
            """Get upcoming events for the specified number of days.

            Args:
                days: Number of days to look ahead

            Returns
            -------
                Formatted string with event information

            """
            now = datetime.datetime.now()
            end_date = now + datetime.timedelta(days=days)
            events = self._get_events_in_range(ctx, now, end_date)
            return self._format_events_list(events, days)

        @self.mcp.resource("calendar://availability/{start_days}/{end_days}")
        def get_availability(
            start_days: int, end_days: int, ctx: Context
        ) -> str:
            """Get availability information for a date range.

            Args:
                start_days: Days from now to start looking
                end_days: Days from now to end looking

            Returns
            -------
                Formatted string with availability information

            """
            time_slot_manager = self._get_time_slot_manager(ctx)

            now = datetime.datetime.now()
            start_date = now + datetime.timedelta(days=start_days)
            end_date = now + datetime.timedelta(days=end_days)

            ## Default to 1 hour slots  # FIXME
            duration_minutes = 60

            free_slots = time_slot_manager.calendar_service.find_free_slots(
                start_date,
                end_date,
                duration_minutes,
                time_slot_manager.working_hours,
            )

            date_range_desc = (
                f"between {start_date.date()} and {end_date.date()}"
            )
            return self._format_free_slots(
                free_slots, duration_minutes, date_range_desc
            )

    def _register_tools(self) -> None:
        """Register tools for the MCP server."""

        @self.mcp.tool()
        def list_events(days: int = 7, ctx: Context = None) -> str:
            """List all upcoming events for the specified number of days.

            Args:
                days: Number of days to look ahead

            Returns
            -------
                Formatted string with event information

            """
            now = datetime.datetime.now()
            end_date = now + datetime.timedelta(days=days)
            events = self._get_events_in_range(ctx, now, end_date)
            return self._format_events_list(events, days)

        @self.mcp.tool()
        def create_event(
            summary: str,
            start_time: str | None = None,
            duration_minutes: int = 60,
            description: str | None = None,
            location: str | None = None,
            ctx: Context = None,
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
            time_slot_manager = self._get_time_slot_manager(ctx)

            try:
                request = self._create_event_request(
                    summary=summary,
                    start_time=start_time,
                    duration_minutes=duration_minutes,
                    description=description,
                    location=location,
                )

                event_id = time_slot_manager.schedule_event(request)
                created_event = self._find_event_by_id(ctx, event_id)
                if created_event:
                    return (
                        "Event created successfully:\n\n"
                        + self._format_single_event(created_event)
                    )
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
            ctx: Context = None,
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
            time_slot_manager = self._get_time_slot_manager(ctx)

            try:
                recurrence_freq = RecurrenceFrequency.from_string(recurrence)
            except ValueError as ex:
                return f"Error: {ex!s}"

            try:
                request = self._create_event_request(
                    summary=summary,
                    start_time=start_time,
                    duration_minutes=duration_minutes,
                    description=description,
                    location=location,
                    recurrence=recurrence_freq,
                    recurrence_count=recurrence_count,
                )
                event_ids = time_slot_manager.schedule_recurring_event(request)
                first_event = self._find_event_by_id(ctx, event_ids[0])
                if first_event:
                    start_str, end_str = self._format_event_time(
                        first_event.start_time, first_event.end_time
                    )
                    return (
                        f"Created {recurrence_count} recurring events:\n\n"
                        f"• {first_event.summary}\n  First occurrence:"
                        f" {start_str} - {end_str}\n  Repeats:"
                        f" {recurrence}, {recurrence_count} times"
                    )
                return f"Created {recurrence_count} recurring events successfully!"

            except ValueError as ex:
                return f"Error: {ex!s}"
            except Exception as ex:
                logger.error(f"Error creating recurring event: {ex}")
                return "Error creating recurring event. Please try again."

        @self.mcp.tool()
        def delete_event(event_id: str, ctx: Context) -> str:
            """Delete a calendar event by ID.

            Args:
                event_id: The ID of the event to delete

            Returns
            -------
                Confirmation message

            """
            calendar_service = self._get_calendar_service(ctx)

            try:
                event = self._find_event_by_id(ctx, event_id)
                if not event:
                    return f"Error: Event with ID {event_id} not found."

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
            ctx: Context = None,
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
            calendar_service = self._get_calendar_service(ctx)

            try:
                event = self._find_event_by_id(ctx, event_id)
                if not event:
                    return f"Error: Event with ID {event_id} not found."

                if summary:
                    event.summary = summary

                if start_time:
                    try:
                        new_start_time = self._parse_iso_time(start_time)
                        if duration_minutes:
                            event.start_time = new_start_time
                            event.end_time = (
                                new_start_time
                                + datetime.timedelta(minutes=duration_minutes)
                            )
                        else:
                            duration = (
                                event.end_time - event.start_time
                            ).total_seconds() / 60
                            event.start_time = new_start_time
                            event.end_time = (
                                new_start_time
                                + datetime.timedelta(minutes=int(duration))
                            )
                    except ValueError as ex:
                        return f"Error: {ex!s}"
                elif duration_minutes:
                    event.end_time = event.start_time + datetime.timedelta(
                        minutes=duration_minutes,
                    )

                if description:
                    event.description = description

                if location:
                    event.location = location

                calendar_service.update_event(event)
                return (
                    "Event updated successfully:\n\n"
                    + self._format_single_event(event)
                )
            except Exception as ex:
                logger.error(f"Error updating event: {ex}")
                return "Error updating event. Please try again."

        @self.mcp.tool()
        def find_free_slots(
            days_ahead: int = 7,
            duration_minutes: int = 60,
            working_hours_start: int | None = None,
            working_hours_end: int | None = None,
            ctx: Context = None,
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
            time_slot_manager = self._get_time_slot_manager(ctx)
            original_working_hours = time_slot_manager.working_hours

            def _reset_working_hours_if_need_be():
                if (
                    working_hours_start is not None
                    and working_hours_end is not None
                ):
                    time_slot_manager.working_hours = original_working_hours

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
                    return (
                        "Error: Invalid working hours."
                        " Start hour must be less than end hour"
                        " and both must be between 0-24."
                    )
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
                _reset_working_hours_if_need_be()
                date_range_desc = f"in the next {days_ahead} days"
                return self._format_free_slots(
                    free_slots, duration_minutes, date_range_desc
                )
            except Exception as ex:
                logger.error(f"Error finding free slots: {ex}")
                _reset_working_hours_if_need_be()
                return "Error finding free slots. Please try again."

        @self.mcp.tool()
        def get_current_time() -> str:
            """Get the current date and time.

            Returns
            -------
                Formatted string with current date and time
            """
            now = datetime.datetime.now()
            formatted_time = now.strftime("%A, %B %d, %Y at %I:%M:%S %p")
            iso_time = now.isoformat()
            return f"Current time: {formatted_time}\nISO format: {iso_time}"

    def run(
        self,
        transport: str = "streamable-http",
        host: str = "localhost",
        port: int = 8000,
        **kwargs: Any,
    ) -> None:
        """Run the MCP server in the event loop."""
        kwargs["transport"] = transport.split("-")[1]
        if transport in ("http", "streamable-http"):
            kwargs["host"] = host
            kwargs["port"] = port

        self.mcp.run(**kwargs)


if __name__ == "__main__":
    ## Entry point for running MCP server as subprocess.
    server = MCPServer()
    server.run(transport="stdio")
