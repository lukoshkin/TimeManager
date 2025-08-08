"""Intent models for TimeManager."""

import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from src.services.time_slot_manager import RecurrenceFrequency


class IntentType(str, Enum):
    """Types of intents that can be recognized."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"
    FALLBACK = "fallback"


class BaseIntent(BaseModel):
    """Base model for all intents."""

    intent_type: IntentType
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    original_text: str = Field(description="Original user message")


class CreateIntent(BaseIntent):
    """Intent for creating a new calendar event."""

    intent_type: IntentType = IntentType.CREATE
    summary: str = Field(description="Event title/summary")
    start_time: datetime.datetime | None = Field(
        None,
        description="Event start time",
    )
    end_time: datetime.datetime | None = Field(
        None,
        description="Event end time",
    )
    duration_minutes: int | None = Field(
        None,
        description="Duration of the event in minutes",
    )
    description: str | None = Field(None, description="Event description")
    location: str | None = Field(None, description="Event location")
    recurrence: RecurrenceFrequency = Field(
        RecurrenceFrequency.NONE,
        description="Event recurrence frequency",
    )
    recurrence_count: int = Field(0, description="Number of recurrences")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "intent_type": "create",
                "summary": "Team Meeting",
                "start_time": "2025-06-10T14:00:00",
                "duration_minutes": 60,
                "location": "Conference Room A",
                "recurrence": "weekly",
                "recurrence_count": 4,
                "original_text": (
                    "Schedule a team meeting every Tuesday at 2pm for a month"
                ),
            },
        }
    )


class UpdateIntent(BaseIntent):
    """Intent for updating an existing calendar event."""

    intent_type: IntentType = IntentType.UPDATE
    event_selection: int | None = Field(
        None,
        description="Index of the event to update from a list",
    )
    event_id: str | None = Field(
        None,
        description="ID of the event to update",
    )
    event_name: str | None = Field(
        None,
        description="Name or description of the event to update",
    )
    summary: str | None = Field(None, description="New event title/summary")
    start_time: datetime.datetime | None = Field(
        None,
        description="New event start time",
    )
    end_time: datetime.datetime | None = Field(
        None,
        description="New event end time",
    )
    duration_minutes: int | None = Field(
        None,
        description="New duration in minutes",
    )
    description: str | None = Field(
        None,
        description="New event description",
    )
    location: str | None = Field(None, description="New event location")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "intent_type": "update",
                "event_selection": 2,
                "event_name": "Meeting with John",
                "summary": "Updated Meeting Title",
                "start_time": "2025-06-11T15:00:00",
                "original_text": "Change the meeting with John to tomorrow at 3pm",
            },
        }
    )


class DeleteIntent(BaseIntent):
    """Intent for deleting a calendar event."""

    intent_type: IntentType = IntentType.DELETE
    event_selection: int | None = Field(
        None,
        description="Index of the event to delete from a list",
    )
    event_id: str | None = Field(
        None,
        description="ID of the event to delete",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "intent_type": "delete",
                "event_selection": 3,
                "original_text": "Delete the third event",
            },
        }
    )


class ListIntent(BaseIntent):
    """Intent for listing calendar events."""

    intent_type: IntentType = IntentType.LIST
    time_range_days: int = Field(
        7,
        description="Number of days to show events for",
    )
    start_date: datetime.datetime | None = Field(
        None,
        description="Start date for listing events",
    )
    end_date: datetime.datetime | None = Field(
        None,
        description="End date for listing events",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "intent_type": "list",
                "time_range_days": 14,
                "original_text": "Show me my schedule for the next two weeks",
            },
        }
    )


class FallbackIntent(BaseIntent):
    """Fallback intent when no specific intent can be determined."""

    intent_type: IntentType = IntentType.FALLBACK
    llm_response: str = Field(
        "",
        description="Response generated by the LLM for fallback handling",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "intent_type": "fallback",
                "llm_response": (
                    "I'm sorry, I couldn't understand your request. "
                    "Could you please rephrase it?"
                ),
                "original_text": "What's the weather like today?",
            },
        }
    )
