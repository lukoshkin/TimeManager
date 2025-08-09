"""LLM-based intent parser for TimeManager."""

import json

import litellm

from src.config.logging import logger
from src.prompts.templates import (
    FALLBACK_PROMPT,
    INTENT_CLASSIFICATION_PROMPT,
    SLOT_ELICITATION_PROMPTS,
    SLOT_EXTRACTION_PROMPT,
)
from src.services.intent_parser.intent_models import (
    BaseIntent,
    CreateIntent,
    DeleteIntent,
    FallbackIntent,
    IntentType,
    ListIntent,
    UpdateIntent,
)
from src.utils.time_utils import time_aware_text


class LLMIntentParser:
    """Parser that uses LLM to extract intents and slots from user messages."""

    TRUNC_LEN = 50

    def __init__(self, api_key: str, model: str):
        """Initialize the LLM Intent Parser.

        Args:
            api_key: API key of the LLM in use
            model: LLM model to use

        """
        self.api_key = api_key
        self.model = model
        self.slot_elicitation_prompts = SLOT_ELICITATION_PROMPTS

    async def parse_intent(
        self,
        message: str,
    ) -> (
        CreateIntent
        | UpdateIntent
        | DeleteIntent
        | ListIntent
        | FallbackIntent
    ):
        """Parse a user message to determine intent and extract slots.

        Args:
            message: User message text

        Returns
        -------
            An intent object with extracted slots

        """
        try:
            # First, classify the intent
            intent_type = await self._classify_intent(message)

            # Then extract slots based on the intent type
            if intent_type == IntentType.CREATE:
                return await self._extract_slots(
                    message,
                    intent_type,
                    CreateIntent,
                )
            if intent_type == IntentType.UPDATE:
                return await self._extract_slots(
                    message,
                    intent_type,
                    UpdateIntent,
                )
            if intent_type == IntentType.DELETE:
                return await self._extract_slots(
                    message,
                    intent_type,
                    DeleteIntent,
                )
            if intent_type == IntentType.LIST:
                return await self._extract_slots(
                    message,
                    intent_type,
                    ListIntent,
                )
            return await self._handle_fallback(message)

        except Exception as exc:
            logger.error(f"Error parsing intent: {exc}")
            return await self._handle_fallback(message)

    async def _classify_intent(self, message: str) -> IntentType:
        """Classify the intent of a user message.

        Args:
            message: User message text

        Returns
        -------
            The classified intent type
        """
        prompt = time_aware_text(
            INTENT_CLASSIFICATION_PROMPT, "message"
        ).format(message=message)
        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                api_key=self.api_key,
                max_tokens=10,
            )
            intent_text = response.choices[0].message.content.strip().lower()
            for intent_type in IntentType:
                if intent_type.value in intent_text:
                    truncated_msg = (
                        message[:self.TRUNC_LEN] + "..."
                        if len(message) > self.TRUNC_LEN
                        else message
                    )
                    logger.info(
                        f"Classified intent: {intent_type.value}"
                        f" for message: '{truncated_msg}'"
                    )
                    return intent_type

            logger.warning(f"Failed to classify the intent: {intent_text}")
            return IntentType.FALLBACK

        except Exception as exc:
            logger.error(f"Error classifying intent: {exc}")
            return IntentType.FALLBACK

    async def _extract_slots(
        self,
        message: str,
        intent_type: IntentType,
        model_class: type[BaseIntent],
    ) -> BaseIntent:
        """Extract slots for a specific intent type.

        Args:
            message: User message text
            intent_type: The classified intent type
            model_class: The pydantic model class to use for the intent

        Returns
        -------
            An intent object with extracted slots

        """
        # Create a schema for the response format
        schema = model_class.model_json_schema()

        prompt = time_aware_text(
            SLOT_EXTRACTION_PROMPT, "message", "schema"
        ).format(message=message, schema=json.dumps(schema))

        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                api_key=self.api_key,
                response_format={"type": "json_object"},
                max_tokens=500,
            )

            # Parse the response as JSON
            response_text = response.choices[0].message.content
            parsed_data = json.loads(response_text)

            # Add original message
            parsed_data["original_text"] = message

            # Set the intent type
            parsed_data["intent_type"] = intent_type.value

            # Create the intent object
            intent_obj = model_class(**parsed_data)
            return intent_obj

        except json.JSONDecodeError as exc:
            logger.error(f"Failed to parse LLM response as JSON: {exc}")
            if intent_type == IntentType.CREATE:
                return CreateIntent(
                    intent_type=intent_type,
                    summary="Untitled Event",
                    original_text=message,
                )
            return model_class(intent_type=intent_type, original_text=message)

        except Exception as exc:
            logger.error(f"Error extracting slots: {exc}")
            return model_class(intent_type=intent_type, original_text=message)

    async def _handle_fallback(self, message: str) -> FallbackIntent:
        """Handle fallback intent when specific intent cannot be determined.

        Args:
            message: User message text

        Returns
        -------
            A FallbackIntent object with LLM response

        """
        prompt = time_aware_text(FALLBACK_PROMPT, "message").format(
            message=message
        )

        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                api_key=self.api_key,
                max_tokens=150,
            )

            llm_response = response.choices[0].message.content.strip()
            return FallbackIntent(
                intent_type=IntentType.FALLBACK,
                llm_response=llm_response,
                original_text=message,
            )

        except Exception as exc:
            logger.error(f"Error generating fallback response: {exc}")
            return FallbackIntent(
                intent_type=IntentType.FALLBACK,
                llm_response="I'm sorry, I encountered an error processing your request. "
                "Could you try rephrasing it or try again later?",
                original_text=message,
            )

    def get_slot_elicitation_prompt(
        self,
        intent_type: IntentType,
        slot_name: str,
    ) -> str:
        """Get the prompt to elicit a specific slot for an intent.

        Args:
            intent_type: The intent type
            slot_name: The name of the slot to elicit

        Returns
        -------
            A prompt string to elicit the slot

        """
        if intent_type in self.slot_elicitation_prompts:
            return self.slot_elicitation_prompts[intent_type].get(
                slot_name,
                f"Please provide the {slot_name}.",
            )
        return f"Please provide the {slot_name}."
