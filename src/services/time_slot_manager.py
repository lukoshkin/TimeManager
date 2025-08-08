import datetime
from dataclasses import dataclass
from enum import Enum

from src.config.logging import logger
from src.services.google_calendar import CalendarEvent, GoogleCalendarService


class RecurrenceFrequency(str, Enum):
    """Frequency of event recurrence."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    NONE = "none"

    @classmethod
    def from_string(cls, value: str) -> "RecurrenceFrequency":
        """Convert a string value to a RecurrenceFrequency enum.

        Handles common variations of frequency names.

        Args:
            value: The string value to convert

        Returns
        -------
            The corresponding RecurrenceFrequency enum value

        Raises
        ------
            ValueError: If the value cannot be converted
        """
        value_lower = value.lower().strip()

        if value_lower in ("day", "daily", "every day", "each day"):
            return cls.DAILY
        if value_lower in ("week", "weekly", "every week", "each week"):
            return cls.WEEKLY
        if value_lower in ("month", "monthly", "every month", "each month"):
            return cls.MONTHLY
        if value_lower in ("none", "no", "never"):
            return cls.NONE
        valid_values = ", ".join([f"'{v.value}'" for v in cls])
        raise ValueError(
            f"Invalid recurrence frequency: '{value}'. "
            f"Valid values are: {valid_values}",
        )


@dataclass
class EventRequest:
    """Represents a request to create an event."""

    summary: str
    duration_minutes: int
    start_time: datetime.datetime | None = None
    end_time: datetime.datetime | None = None
    description: str | None = None
    location: str | None = None
    recurrence: RecurrenceFrequency = RecurrenceFrequency.NONE
    recurrence_count: int = 0


class TimeSlotManager:
    """Manages time slots and scheduling logic."""

    def __init__(self, calendar_service: GoogleCalendarService):
        """Initialize the time slot manager.

        Args:
            calendar_service: The calendar service to use

        """
        self.calendar_service = calendar_service
        self.working_hours = (9, 17)  # Default working hours (9 AM to 5 PM)

    def set_working_hours(self, start_hour: int, end_hour: int) -> None:
        """Set the working hours.

        Args:
            start_hour: The start hour (0-23)
            end_hour: The end hour (0-23)

        """
        if not (0 <= start_hour < end_hour <= 24):
            raise ValueError("Invalid working hours")

        self.working_hours = (start_hour, end_hour)
        logger.info(f"Working hours set to {start_hour}:00 - {end_hour}:00")

    def schedule_event(self, request: EventRequest) -> str:
        """Schedule an event based on the request.

        Args:
            request: The event request

        Returns
        -------
            The ID of the created event
        """
        if request.start_time and request.end_time:
            event = CalendarEvent(
                summary=request.summary,
                start_time=request.start_time,
                end_time=request.end_time,
                description=request.description,
                location=request.location,
            )
            return self.calendar_service.create_event(event)

        if request.start_time:
            end_time = request.start_time + datetime.timedelta(
                minutes=request.duration_minutes,
            )
            event = CalendarEvent(
                summary=request.summary,
                start_time=request.start_time,
                end_time=end_time,
                description=request.description,
                location=request.location,
            )
            return self.calendar_service.create_event(event)

        start_date = datetime.datetime.now()
        end_date = start_date + datetime.timedelta(days=7)
        free_slots = self.calendar_service.find_free_slots(
            start_date,
            end_date,
            request.duration_minutes,
            self.working_hours,
        )
        if not free_slots:
            raise ValueError(
                "No free slots available in the specified time range",
            )
        start_time = free_slots[0]
        end_time = start_time + datetime.timedelta(
            minutes=request.duration_minutes,
        )
        event = CalendarEvent(
            summary=request.summary,
            start_time=start_time,
            end_time=end_time,
            description=request.description,
            location=request.location,
        )
        return self.calendar_service.create_event(event)

    def schedule_recurring_event(self, request: EventRequest) -> list[str]:
        """Schedule a recurring event.

        Args:
            request: The event request

        Returns
        -------
            A list of created event IDs

        """
        if (
            request.recurrence == RecurrenceFrequency.NONE
            or request.recurrence_count <= 0
        ):
            raise ValueError("Invalid recurrence parameters")

        event_ids = []
        first_event_id = self.schedule_event(request)
        event_ids.append(first_event_id)
        events = self.calendar_service.get_events(
            datetime.datetime.now(),
            datetime.datetime.now() + datetime.timedelta(days=30),
        )
        first_event = next(
            (e for e in events if e.event_id == first_event_id),
            None,
        )

        if not first_event:
            logger.error("Could not find the first event")
            return event_ids

        current_start = first_event.start_time
        current_end = first_event.end_time

        for _ in range(1, request.recurrence_count):
            if request.recurrence == RecurrenceFrequency.DAILY:
                current_start += datetime.timedelta(days=1)
                current_end += datetime.timedelta(days=1)
            elif request.recurrence == RecurrenceFrequency.WEEKLY:
                current_start += datetime.timedelta(weeks=1)
                current_end += datetime.timedelta(weeks=1)
            elif request.recurrence == RecurrenceFrequency.MONTHLY:
                if current_start.month == 12:
                    next_month = 1
                    next_year = current_start.year + 1
                else:
                    next_month = current_start.month + 1
                    next_year = current_start.year

                try:
                    current_start = current_start.replace(
                        year=next_year,
                        month=next_month,
                    )
                    time_diff = current_end - current_start
                    current_end = current_start + time_diff
                except ValueError:
                    if next_month == 12:
                        last_day = 31
                    else:
                        if next_month + 1 > 12:
                            last_month_date = datetime.datetime(
                                next_year + 1, 1, 1
                            )
                        else:
                            last_month_date = datetime.datetime(
                                next_year, next_month + 1, 1
                            )
                        last_day = (
                            last_month_date - datetime.timedelta(days=1)
                        ).day

                    old_hour, old_minute = (
                        current_start.hour,
                        current_start.minute,
                    )
                    old_second, old_microsecond = (
                        current_start.second,
                        current_start.microsecond,
                    )
                    current_start = current_start.replace(
                        year=next_year,
                        month=next_month,
                        day=last_day,
                        hour=old_hour,
                        minute=old_minute,
                        second=old_second,
                        microsecond=old_microsecond,
                    )

                    duration = (current_end - current_start).total_seconds()
                    current_end = current_start + datetime.timedelta(
                        seconds=duration,
                    )
            event = CalendarEvent(
                summary=first_event.summary,
                start_time=current_start,
                end_time=current_end,
                description=first_event.description,
                location=first_event.location,
            )
            event_id = self.calendar_service.create_event(event)
            event_ids.append(event_id)

        return event_ids
