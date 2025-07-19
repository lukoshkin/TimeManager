"""Prompt templates for TimeManager."""

from src.services.intent_parser.intent_models import IntentType

# Intent classification prompt template
INTENT_CLASSIFICATION_PROMPT = (
    "You are a calendar assistant. Based on the user message, "
    "classify the intent as one of the following: create, update, delete, list, fallback. "
    "Respond with just the intent name, nothing else.\n\n"
    "Today's date: {today}\n"
    "Current time: {time}\n\n"
    "User message: {message}\n\n"
    "Intent:"
)

# Slot extraction prompt template
SLOT_EXTRACTION_PROMPT = (
    "You are a calendar assistant. Extract the relevant information from "
    "the user message according to the provided JSON schema. "
    "If a field is not mentioned in the user message, use null for that field. "
    "For datetime fields, use ISO format (YYYY-MM-DDThh:mm:ss). "
    "For recurrence, use one of: daily, weekly, monthly, or none.\n\n"
    "Today's date: {today}\n"
    "Current time: {time}\n\n"
    "User message: {message}\n\n"
    "Response format: {schema}"
)

# Fallback handling prompt template
FALLBACK_PROMPT = (
    "You are a helpful calendar assistant. The user has sent a message that "
    "doesn't seem to be about creating, updating, deleting, or listing calendar events. "
    "Please provide a helpful response that explains your capabilities as a calendar assistant.\n\n"
    "Today's date: {today}\n"
    "Current time: {time}\n\n"
    "User message: {message}"
)

# Slot elicitation prompts
SLOT_ELICITATION_PROMPTS = {
    IntentType.CREATE: {
        "summary": "What would you like to call this event?",
        "start_time": "When should this event start?",
        "duration_minutes": "How long should this event last?",
        "location": "Where will this event take place?",
    },
    IntentType.UPDATE: {
        "event_selection": "Which event would you like to update?",
        "summary": "What would you like to rename this event to?",
        "start_time": "When would you like to reschedule this event to?",
        "duration_minutes": "How long should this event last now?",
        "location": "Where will this event take place now?",
    },
    IntentType.DELETE: {
        "event_selection": "Which event would you like to delete?",
    },
    IntentType.LIST: {
        "time_range_days": "For how many days would you like to see your schedule?",
    },
}
