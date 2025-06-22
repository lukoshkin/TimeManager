import datetime
import os.path
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tzlocal
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from loguru import logger


@dataclass
class CalendarEvent:
    """Represents a calendar event."""

    summary: str
    start_time: datetime.datetime
    end_time: datetime.datetime
    description: str | None = None
    location: str | None = None
    event_id: str | None = None
    recurrence: list | None = None


class GoogleCalendarService:
    """Service for interacting with Google Calendar API."""

    # If modifying these scopes, delete the token file.
    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    def __init__(self, credentials_file: Path, token_file: Path):
        """Initialize the Google Calendar service.

        Args:
            credentials_file: Path to the credentials JSON file
            token_file: Path to the token JSON file

        """
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = self._get_calendar_service()

    def _get_calendar_service(self) -> Any:
        """Get an authorized Google Calendar API service instance."""
        credentials = None

        # The file token.json stores the user's access and refresh tokens
        if os.path.exists(self.token_file):
            try:
                credentials = Credentials.from_authorized_user_info(
                    info=self._read_json_file(self.token_file),
                    scopes=self.SCOPES,
                )
            except Exception as ex:
                logger.error(f"Error loading credentials from token file: {ex}")
                # If we can't load the credentials, we'll create new ones
                credentials = None
                # Delete the invalid token file
                try:
                    os.remove(self.token_file)
                    logger.info(f"Deleted invalid token file: {self.token_file}")
                except OSError as ex:
                    logger.error(f"Error deleting token file: {ex}")

        # If there are no (valid) credentials available, let the user log in
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                except Exception as ex:
                    logger.error(f"Error refreshing token: {ex}")
                    # Token refresh failed, need a new token
                    # Delete the invalid token file
                    try:
                        if os.path.exists(self.token_file):
                            os.remove(self.token_file)
                            logger.info(
                                f"Deleted expired token file: {self.token_file}"
                            )
                    except OSError as ex:
                        logger.error(f"Error deleting token file: {ex}")

                    # Create new credentials
                    logger.info("Starting new OAuth flow to get fresh credentials")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_file,
                        self.SCOPES,
                    )
                    credentials = flow.run_local_server(port=0)
            else:
                logger.info("No valid credentials found, starting OAuth flow")
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file,
                    self.SCOPES,
                )
                credentials = flow.run_local_server(port=0)

            # Save the credentials for the next run
            try:
                self._write_json_file(self.token_file, credentials.to_json())
                logger.info(f"Saved new credentials to {self.token_file}")
            except Exception as ex:
                logger.error(f"Error saving credentials: {ex}")

        try:
            service = build("calendar", "v3", credentials=credentials)
            return service
        except HttpError as error:
            logger.error(f"An error occurred: {error}")
            raise error

    def _read_json_file(self, file_path: Path) -> Any:
        """Read a JSON file and return its contents."""
        import json

        with open(file_path, encoding="utf-8") as file:
            return json.load(file)

    def _write_json_file(self, file_path: Path, content: str) -> None:
        """Write content to a JSON file."""
        # No need to import json since we're directly writing the serialized content
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(content)

    def create_event(self, event: CalendarEvent) -> str:
        """Create a new event in the primary calendar.

        Args:
            event: The event to create

        Returns:
            The ID of the created event

        """
        iana_tz = tzlocal.get_localzone_name()
        event_body = {
            "summary": event.summary,
            "start": {
                "dateTime": event.start_time.isoformat(),
                "timeZone": iana_tz,
            },
            "end": {
                "dateTime": event.end_time.isoformat(),
                "timeZone": iana_tz,
            },
        }

        if event.description:
            event_body["description"] = event.description

        if event.location:
            event_body["location"] = event.location

        try:
            created_event = (
                self.service.events()
                .insert(calendarId="primary", body=event_body)
                .execute()
            )
            logger.info(f"Event created: {created_event.get('htmlLink')}")
            return str(created_event["id"])
        except HttpError as error:
            logger.error(f"An error occurred: {error}")
            raise

    def update_event(self, event: CalendarEvent) -> None:
        """Update an existing event.

        Args:
            event: The event to update

        """
        if not event.event_id:
            raise ValueError("Event ID is required for updating an event")

        iana_tz = tzlocal.get_localzone_name()
        event_body = {
            "summary": event.summary,
            "start": {
                "dateTime": event.start_time.isoformat(),
                "timeZone": iana_tz,
            },
            "end": {
                "dateTime": event.end_time.isoformat(),
                "timeZone": iana_tz,
            },
        }

        if event.description:
            event_body["description"] = event.description

        if event.location:
            event_body["location"] = event.location

        try:
            self.service.events().update(
                calendarId="primary",
                eventId=event.event_id,
                body=event_body,
            ).execute()

            logger.info(f"Event updated: {event.event_id}")
        except HttpError as error:
            logger.error(f"An error occurred: {error}")
            raise

    def delete_event(self, event_id: str) -> None:
        """Delete an event.

        Args:
            event_id: The ID of the event to delete

        """
        try:
            self.service.events().delete(
                calendarId="primary",
                eventId=event_id,
            ).execute()

            logger.info(f"Event deleted: {event_id}")
        except HttpError as error:
            logger.error(f"An error occurred: {error}")
            raise

    def get_events(
        self,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
    ) -> list[CalendarEvent]:
        """Get events in a specified time range.

        Args:
            start_time: The start time of the range
            end_time: The end time of the range

        Returns:
            A list of events in the specified time range

        """
        try:
            events_result = (
                self.service.events()
                .list(
                    calendarId="primary",
                    timeMin=start_time.isoformat() + "Z",
                    timeMax=end_time.isoformat() + "Z",
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            events = events_result.get("items", [])

            result = []
            for event in events:
                start = event["start"].get("dateTime")
                end = event["end"].get("dateTime")

                if start and end:
                    # Handle timezone consistently
                    try:
                        start_dt = datetime.datetime.fromisoformat(start)
                    except ValueError:
                        # Handle 'Z' UTC timezone notation
                        start_dt = datetime.datetime.fromisoformat(
                            start.replace("Z", "+00:00"),
                        )

                    try:
                        end_dt = datetime.datetime.fromisoformat(end)
                    except ValueError:
                        # Handle 'Z' UTC timezone notation
                        end_dt = datetime.datetime.fromisoformat(
                            end.replace("Z", "+00:00"),
                        )

                    result.append(
                        CalendarEvent(
                            summary=event["summary"],
                            start_time=start_dt,
                            end_time=end_dt,
                            description=event.get("description"),
                            location=event.get("location"),
                            event_id=event["id"],
                        ),
                    )

            return result
        except HttpError as error:
            logger.error(f"An error occurred: {error}")
            raise

    def find_free_slots(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        duration_minutes: int,
        working_hours: tuple[int, int] = (9, 17),
    ) -> list[datetime.datetime]:
        """Find free time slots in a given date range.

        Args:
            start_date: The start date of the range
            end_date: The end date of the range
            duration_minutes: The duration of the slot in minutes
            working_hours: Tuple of (start_hour, end_hour) for working hours

        Returns:
            A list of datetime objects representing the start times of free slots

        """
        # Get all events in the date range
        events = self.get_events(start_date, end_date)

        # Create a list of busy time slots
        busy_slots = []
        for event in events:
            busy_slots.append((event.start_time, event.end_time))

        # Sort busy slots by start time
        busy_slots.sort(key=lambda x: x[0])

        # Find free slots
        free_slots = []
        current_date = start_date

        while current_date < end_date:
            # Only consider working hours
            work_day_start = current_date.replace(
                hour=working_hours[0],
                minute=0,
                second=0,
                microsecond=0,
            )
            work_day_end = current_date.replace(
                hour=working_hours[1],
                minute=0,
                second=0,
                microsecond=0,
            )

            # If current_date is already past working hours, move to next day
            if current_date.hour >= working_hours[1]:
                current_date = (current_date + datetime.timedelta(days=1)).replace(
                    hour=working_hours[0],
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                continue

            # If current_date is before working hours, move to start of working hours
            if current_date.hour < working_hours[0]:
                current_date = current_date.replace(
                    hour=working_hours[0],
                    minute=0,
                    second=0,
                    microsecond=0,
                )

            # Check if current_date is in a busy slot
            is_busy = False
            for busy_start, busy_end in busy_slots:
                if busy_start <= current_date < busy_end:
                    current_date = busy_end
                    is_busy = True
                    break

            if is_busy:
                continue

            # Find the next busy slot that starts after current_date
            next_busy_start = None
            for busy_start, _ in busy_slots:
                if busy_start > current_date:
                    next_busy_start = busy_start
                    break

            # Calculate end time of potential free slot
            slot_end = current_date + datetime.timedelta(
                minutes=duration_minutes,
            )

            # Check if slot fits before the next busy slot or end of working hours
            if next_busy_start is None or slot_end <= next_busy_start:
                if slot_end <= work_day_end:
                    free_slots.append(current_date)
                    current_date = slot_end
                else:
                    # Move to next day if slot doesn't fit in current day
                    current_date = (current_date + datetime.timedelta(days=1)).replace(
                        hour=working_hours[0],
                        minute=0,
                        second=0,
                        microsecond=0,
                    )
            else:
                # Move to the start of the next busy slot
                current_date = next_busy_start

        return free_slots
