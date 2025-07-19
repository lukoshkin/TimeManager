"""Semantic search for events using sentence embeddings.

DEPRECATED: This module has been replaced by event_milvus_connector.py
which provides better performance and persistence using Milvus vector database.
"""

import numpy as np
from sentence_transformers import SentenceTransformer, util

from src.config.logging import logger
from src.services.google_calendar import CalendarEvent


class EventSemanticSearch:
    """Provides semantic search capabilities for calendar events."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """Initialize the semantic search engine.

        Args:
            model_name: The name of the sentence transformer model to use
        """
        self.embed_model = SentenceTransformer(model_name)
        logger.info(f"Initialized semantic search with model: {model_name}")

    def find_similar_event(
        self,
        query: str,
        events: list[CalendarEvent],
        threshold: float = 0.6,
    ) -> tuple[CalendarEvent | None, float]:
        """Find the most semantically similar event to the query.

        Args:
            query: The query string to match against events
            events: List of calendar events to search
            threshold: Minimum similarity threshold (0-1) to consider a match

        Returns
        -------
            A tuple of (matched_event, similarity_score) or (None, 0.0) if no match
        """
        if not events:
            return None, 0.0

        # Create a list of event texts to search against
        event_texts = []
        for event in events:
            # Combine summary with description for better matching
            text = event.summary
            if event.description:
                text += " " + event.description
            event_texts.append(text)

        # Get embeddings for the query and events
        query_embedding = self.embed_model.encode(query, convert_to_numpy=True)
        event_embeddings = self.embed_model.encode(
            event_texts, convert_to_numpy=True
        )
        # Calculate cosine similarities
        similarities = []
        for event_embedding in event_embeddings:
            similarity = util.cos_sim(query_embedding, event_embedding)
            similarities.append(float(similarity.item()))

        # Find the most similar event
        max_idx = np.argmax(similarities)
        max_similarity = similarities[max_idx]

        if max_similarity >= threshold:
            logger.info(
                f"Found similar event: '{events[max_idx].summary}' "
                f"with similarity: {max_similarity:.2f}"
            )
            return events[max_idx], max_similarity
        else:
            logger.info(
                f"No similar event found above threshold {threshold}. "
                f"Best match: '{events[max_idx].summary}' "
                f"with similarity: {max_similarity:.2f}"
            )
            return None, 0.0
