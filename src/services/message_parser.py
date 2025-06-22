import datetime
import re

from loguru import logger

from src.services.time_slot_manager import EventRequest, RecurrenceFrequency


class MessageParser:
    """Parser for extracting event information from user messages."""

    def __init__(self):
        """Initialize the message parser."""
        # Common time expressions
        self.time_patterns = {
            "today": r"today",
            "tomorrow": r"tomorrow",
            "next week": r"next\s+week",
            "next month": r"next\s+month",
            "at time": r"at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
            "from time to time": r"from\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+to\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
            "on date": r"on\s+(\d{1,2})(?:st|nd|rd|th)?\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)",
            "for duration": r"for\s+(\d+)\s+(minute(?:s)?|hour(?:s)?)",
            "recurrence": r"(every|each)\s+(day|week|month)",
            "recurrence count": r"(\d+)\s+times",
        }

    def parse_message(self, message: str) -> EventRequest:
        """Parse a message to extract event information.

        Args:
            message: The message to parse

        Returns:
            An EventRequest object with the extracted information

        """
        # Extract summary (everything before the first time-related keyword)
        summary = self._extract_summary(message)

        # Extract time information
        start_time, end_time, duration_minutes = self._extract_time_info(
            message,
        )

        # Extract recurrence information
        recurrence, recurrence_count = self._extract_recurrence_info(message)

        # Extract location if present
        location = self._extract_location(message)

        # Extract description (anything else that might be relevant)
        description = self._extract_description(message)

        return EventRequest(
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration_minutes
            or 60,  # Default to 1 hour if not specified
            description=description,
            location=location,
            recurrence=recurrence,
            recurrence_count=recurrence_count,
        )

    def _extract_summary(self, message: str) -> str:
        """Extract the event summary from the message."""
        # Simple heuristic: take the first sentence or everything before a time expression
        time_keywords = [
            "today",
            "tomorrow",
            "next week",
            "next month",
            "at",
            "from",
            "on",
            "for",
            "every",
            "each",
        ]

        # Find the first occurrence of a time keyword
        first_keyword_pos = float("inf")
        for keyword in time_keywords:
            pos = message.lower().find(keyword)
            if pos != -1 and pos < first_keyword_pos:
                first_keyword_pos = pos

        if first_keyword_pos == float("inf"):
            # No time keywords found, use the whole message as summary
            return message.strip()
        # Use everything before the first time keyword
        return message[:first_keyword_pos].strip()

    def _extract_time_info(
        self,
        message: str,
    ) -> tuple[
        datetime.datetime | None,
        datetime.datetime | None,
        int | None,
    ]:
        """Extract time information from the message."""
        message_lower = message.lower()
        # Use datetime.now() with the system's timezone
        now = datetime.datetime.now().astimezone()

        start_time = None
        end_time = None
        duration_minutes = None

        # Check for "today"
        if re.search(self.time_patterns["today"], message_lower):
            start_time = now.replace(hour=9, minute=0, second=0, microsecond=0)

        # Check for "tomorrow"
        elif re.search(self.time_patterns["tomorrow"], message_lower):
            tomorrow = now + datetime.timedelta(days=1)
            start_time = tomorrow.replace(
                hour=9,
                minute=0,
                second=0,
                microsecond=0,
            )

        # Check for "next week"
        elif re.search(self.time_patterns["next week"], message_lower):
            days_until_monday = (7 - now.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 7
            next_monday = now + datetime.timedelta(days=days_until_monday)
            start_time = next_monday.replace(
                hour=9,
                minute=0,
                second=0,
                microsecond=0,
            )

        # Check for "next month"
        elif re.search(self.time_patterns["next month"], message_lower):
            if now.month == 12:
                next_month = now.replace(year=now.year + 1, month=1, day=1)
            else:
                next_month = now.replace(month=now.month + 1, day=1)
            start_time = next_month.replace(
                hour=9,
                minute=0,
                second=0,
                microsecond=0,
            )

        # Check for "at [time]"
        at_time_match = re.search(self.time_patterns["at time"], message_lower)
        if at_time_match:
            hour = int(at_time_match.group(1))
            minute = (
                int(at_time_match.group(2)) if at_time_match.group(2) else 0
            )
            am_pm = at_time_match.group(3)

            # Convert to 24-hour format if needed
            if am_pm and am_pm.lower() == "pm" and hour < 12:
                hour += 12
            elif am_pm and am_pm.lower() == "am" and hour == 12:
                hour = 0

            # Use today's date with the specified time
            start_time = now.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )

            # If the time has already passed today, use tomorrow
            if start_time < now:
                start_time += datetime.timedelta(days=1)

        # Check for "from [time] to [time]"
        from_to_match = re.search(
            self.time_patterns["from time to time"],
            message_lower,
        )
        if from_to_match:
            start_hour = int(from_to_match.group(1))
            start_minute = (
                int(from_to_match.group(2)) if from_to_match.group(2) else 0
            )
            start_am_pm = from_to_match.group(3)

            end_hour = int(from_to_match.group(4))
            end_minute = (
                int(from_to_match.group(5)) if from_to_match.group(5) else 0
            )
            end_am_pm = from_to_match.group(6)

            # Convert to 24-hour format if needed
            if start_am_pm and start_am_pm.lower() == "pm" and start_hour < 12:
                start_hour += 12
            elif (
                start_am_pm
                and start_am_pm.lower() == "am"
                and start_hour == 12
            ):
                start_hour = 0

            if end_am_pm and end_am_pm.lower() == "pm" and end_hour < 12:
                end_hour += 12
            elif end_am_pm and end_am_pm.lower() == "am" and end_hour == 12:
                end_hour = 0

            # Use today's date with the specified times
            start_time = now.replace(
                hour=start_hour,
                minute=start_minute,
                second=0,
                microsecond=0,
            )
            end_time = now.replace(
                hour=end_hour,
                minute=end_minute,
                second=0,
                microsecond=0,
            )

            # If the start time has already passed today, use tomorrow
            if start_time < now:
                start_time += datetime.timedelta(days=1)
                end_time += datetime.timedelta(days=1)

            # Calculate duration
            duration_minutes = int(
                (end_time - start_time).total_seconds() / 60,
            )

        # Check for "for [duration]"
        duration_match = re.search(
            self.time_patterns["for duration"],
            message_lower,
        )
        if duration_match:
            amount = int(duration_match.group(1))
            unit = duration_match.group(2).lower()

            if unit.startswith("hour"):
                duration_minutes = amount * 60
            else:  # minutes
                duration_minutes = amount

        # If we have a start time and duration but no end time, calculate end time
        if start_time and duration_minutes and not end_time:
            end_time = start_time + datetime.timedelta(
                minutes=duration_minutes,
            )

        # If we have a start time and end time but no duration, calculate duration
        elif start_time and end_time and not duration_minutes:
            duration_minutes = int(
                (end_time - start_time).total_seconds() / 60,
            )

        return start_time, end_time, duration_minutes

    def _extract_recurrence_info(
        self,
        message: str,
    ) -> tuple[RecurrenceFrequency, int]:
        """Extract recurrence information from the message."""
        message_lower = message.lower()

        recurrence = RecurrenceFrequency.NONE
        recurrence_count = 0

        # Check for recurrence pattern
        recurrence_match = re.search(
            self.time_patterns["recurrence"],
            message_lower,
        )
        if recurrence_match:
            unit = recurrence_match.group(2).lower()

            try:
                # Use the more robust method to get the recurrence frequency
                recurrence = RecurrenceFrequency.from_string(unit)

                # Default to 4 occurrences if not specified
                recurrence_count = 4
            except ValueError:
                logger.warning(f"Could not parse recurrence frequency: {unit}")

        # Check for recurrence count
        count_match = re.search(
            self.time_patterns["recurrence count"],
            message_lower,
        )
        if count_match:
            recurrence_count = int(count_match.group(1))

        return recurrence, recurrence_count

    def _extract_location(self, message: str) -> str | None:
        """Extract location information from the message."""
        # Look for location indicators
        location_patterns = [
            r"at\s+([^,\.]+?)(?=\s+on|\s+at|\s+from|\s+for|$|\.)",
            r"in\s+([^,\.]+?)(?=\s+on|\s+at|\s+from|\s+for|$|\.)",
        ]

        for pattern in location_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _extract_description(self, message: str) -> str | None:
        """Extract description information from the message."""
        # For now, just use the original message as the description
        # In a more sophisticated implementation, we might want to extract
        # specific details or notes from the message
        return message
