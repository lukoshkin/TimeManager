"""Milvus connector for storing and searching calendar events."""

import json
from collections.abc import Generator
from datetime import datetime
from typing import Any, Literal

from pymilvus import (
    DataType,
    Function,
    FunctionType,
    MilvusClient,
)

from src.config.logging import logger
from src.services.google_calendar import CalendarEvent


def batch_generator(
    data: list[Any], batch_size: int
) -> Generator[list[Any], None, None]:
    """Generate batches from a list.

    Args:
        data: Input data list
        batch_size: Size of each batch

    Yields
    ------
        List batches of the specified size
    """
    for i in range(0, len(data), batch_size):
        yield data[i : i + batch_size]


class EventMilvusConfig:
    """Configuration for Milvus event database."""

    def __init__(
        self,
        uri: str = "http://localhost:19530",
        collection_name: str = "calendar_events",
        vector_dim: int = 384,  # all-MiniLM-L6-v2 dimension
        summary_max_length: int = 500,
        description_max_length: int = 1500,
        other_text_max_length: int = 500,
        model_name: str = "all-MiniLM-L6-v2",
        embedding_provider: str = "sentence_transformers",
    ) -> None:
        """Initialize Milvus configuration.

        Args:
            uri: Milvus server URI
            collection_name: Name of the collection to store events
            vector_dim: Dimension of the embedding vectors
            summary_max_length: Maximum length for summary field
            description_max_length: Maximum length for description field
            other_text_max_length: Maximum length for other text fields
            model_name: Embedding model name
            embedding_provider: Embedding model provider
                (e.g., 'sentence_transformers', 'openai')
        """
        self.uri = uri
        self.collection_name = collection_name
        self.vector_dim = vector_dim
        self.summary_max_length = summary_max_length
        self.description_max_length = description_max_length
        self.other_text_max_length = other_text_max_length
        self.model_name = model_name
        self.embedding_provider = embedding_provider


class EventMilvusConnector:
    """Milvus connector for calendar events with semantic search."""

    def __init__(self, cfg: EventMilvusConfig) -> None:
        """Initialize the Milvus connector.

        Args:
            cfg: Milvus configuration object
        """
        self.cfg = cfg
        self.client = MilvusClient(uri=cfg.uri)
        self._scalar_fields = list(CalendarEvent.model_fields.keys())
        logger.info(
            "Initialized Milvus connector for collection"
            f" '{cfg.collection_name}' with model '{cfg.model_name}'"
        )

    def create_collection(self) -> None:
        """Create a collection for calendar events.

        The schema includes:
        - event_id: Primary key (VARCHAR)
        - summary: Event title (VARCHAR)
        - description: Event description (VARCHAR, nullable)
        - location: Event location (VARCHAR, nullable)
        - start_time: Event start time (INT64, timestamp)
        - end_time: Event end time (INT64, timestamp)
        - recurrence: Recurrence rules (JSON, stored as VARCHAR)
        - combined_text_vector: Embedding of concatenated summary and
            description (auto-generated)
        """
        if self.client.has_collection(self.cfg.collection_name):
            logger.info(
                f"Collection '{self.cfg.collection_name}' already exists."
            )
            return

        schema = self.client.create_schema(auto_id=False)
        schema.add_field(
            field_name="event_id",
            datatype=DataType.VARCHAR,
            is_primary=True,
            max_length=100,
        )
        schema.add_field(
            field_name="summary",
            datatype=DataType.VARCHAR,
            max_length=self.cfg.summary_max_length,
        )
        schema.add_field(
            field_name="description",
            datatype=DataType.VARCHAR,
            max_length=self.cfg.description_max_length,
        )
        schema.add_field(
            field_name="location",
            datatype=DataType.VARCHAR,
            max_length=self.cfg.other_text_max_length,
        )
        schema.add_field(
            field_name="start_time",
            datatype=DataType.INT64,
        )
        schema.add_field(
            field_name="end_time",
            datatype=DataType.INT64,
        )
        schema.add_field(
            field_name="recurrence",
            datatype=DataType.VARCHAR,
            max_length=500,
        )
        schema.add_field(
            field_name="combined_text",
            datatype=DataType.VARCHAR,
            max_length=(
                self.cfg.summary_max_length
                + self.cfg.description_max_length
                + 2  # for "\n\n" separator
            ),
        )
        schema.add_field(
            field_name="combined_text_vector",
            datatype=DataType.FLOAT_VECTOR,
            dim=self.cfg.vector_dim,
        )
        schema.add_function(
            Function(
                name="combined_text_embedding",
                function_type=FunctionType.TEXTEMBEDDING,
                input_field_names=["combined_text"],
                output_field_names=["combined_text_vector"],
                params={
                    "provider": self.cfg.embedding_provider,
                    "model_name": self.cfg.model_name,
                    "dim": self.cfg.vector_dim,
                },
            )
        )
        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="combined_text_vector",
            index_type="AUTOINDEX",
            metric_type="IP",
        )
        self.client.create_collection(
            collection_name=self.cfg.collection_name,
            schema=schema,
            index_params=index_params,
            consistency_level="Strong",
        )
        logger.info(f"Created collection '{self.cfg.collection_name}'")

    def upsert_events(
        self,
        events: list[CalendarEvent],
        batch_size: int | None = None,
    ) -> None:
        """Upsert calendar events into the Milvus collection.

        Args:
            events: List of CalendarEvent objects to upsert
            batch_size: Optional batch size for upsert operation
        """
        if not events:
            logger.warning("No events to upsert")
            return

        if batch_size is None:
            data = self._prepare_event_data(events)
            self.client.upsert(
                collection_name=self.cfg.collection_name, data=data
            )
            logger.info(f"Upserted {len(events)} events into Milvus")
            return

        total_upserted = 0
        for batch in batch_generator(events, batch_size):
            data = self._prepare_event_data(batch)
            self.client.upsert(
                collection_name=self.cfg.collection_name,
                data=data,
            )
            total_upserted += len(batch)
            logger.info(f"Upserted batch of {len(batch)} events")
        logger.info(f"Total upserted: {total_upserted} events")

    def insert_events(
        self,
        events: list[CalendarEvent],
        batch_size: int | None = None,
    ) -> None:
        """Insert calendar events into the Milvus collection.

        Note: This method will fail if events with the same ID already exist.
        Use upsert_events() for safer insertion that handles duplicates.

        Args:
            events: List of CalendarEvent objects to insert
            batch_size: Optional batch size for insertion
        """
        if not events:
            logger.warning("No events to insert")
            return

        if batch_size is None:
            data = self._prepare_event_data(events)
            self.client.insert(
                collection_name=self.cfg.collection_name, data=data
            )
            logger.info(f"Inserted {len(events)} events into Milvus")
            return

        total_inserted = 0
        for batch in batch_generator(events, batch_size):
            data = self._prepare_event_data(batch)
            self.client.insert(
                collection_name=self.cfg.collection_name, data=data
            )
            total_inserted += len(batch)
            logger.info(f"Inserted batch of {len(batch)} events")

        logger.info(f"Total inserted: {total_inserted} events")

    def search_similar_events(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.6,
        expr: str | None = None,
    ) -> list[tuple[CalendarEvent, float]]:
        """Search for similar events using semantic search.

        Args:
            query: Query string to search for
            limit: Maximum number of results to return
            threshold: Minimum similarity threshold (IP score, -1 to 1)
            expr: Optional boolean expression for filtering

        Returns
        -------
            List of tuples (CalendarEvent, similarity_score)
        """
        results = self.client.search(
            collection_name=self.cfg.collection_name,
            data=[query],
            anns_field="combined_text_vector",
            limit=limit,
            filter=expr,
            output_fields=self._scalar_fields,
        )

        similar_events = []
        for hits in results:
            for hit in hits:
                processed_hit = self._process_search_hit(hit, threshold)
                if processed_hit is not None:
                    similar_events.append(processed_hit)

        logger.info(
            f"Found {len(similar_events)} similar events"
            f" above threshold {threshold}"
        )
        return similar_events

    def most_similar_event(
        self,
        query: str,
        threshold: float = 0.6,
    ) -> tuple[CalendarEvent | None, float]:
        """Find the most similar event to the query.

        Args:
            query: Query string to match against events
            threshold: Minimum similarity threshold

        Returns
        -------
            Tuple of (matched_event, similarity_score) or (None, 0.0)
        """
        similar_events = self.search_similar_events(
            query=query, limit=1, threshold=threshold
        )
        if similar_events:
            return similar_events[0]
        return None, 0.0

    def delete_events(self, event_ids: list[str]) -> None:
        """Delete events by their IDs.

        Args:
            event_ids: List of event IDs to delete
        """
        if not event_ids:
            logger.warning("No event IDs provided for deletion")
            return

        id_list = [f'"{event_id}"' for event_id in event_ids]
        self.client.delete(
            collection_name=self.cfg.collection_name,
            filter=f"event_id in [{', '.join(id_list)}]",
        )
        logger.info(f"Deleted {len(event_ids)} events from Milvus")

    def count_events(
        self,
        consistency_level: Literal[
            "Session", "Strong", "Bounded", "Eventual"
        ] = "Strong",
    ) -> int:
        """Count the number of events in the collection.

        Args:
            consistency_level: Consistency level for the count operation

        Returns
        -------
            Number of events in the collection
        """
        return self.client.query(
            collection_name=self.cfg.collection_name,
            output_fields=["count(*)"],
            consistency_level=consistency_level,
        )[0]["count(*)"]

    def get_recent_events(
        self,
        limit: int = 5,
        consistency_level: Literal[
            "Session", "Strong", "Bounded", "Eventual"
        ] = "Strong",
    ) -> list[CalendarEvent]:
        """Get the most recently inserted events from the collection.

        Args:
            limit: Number of recent events to retrieve
            consistency_level: Consistency level for the query operation

        Returns
        -------
            List of CalendarEvent objects, ordered by start_time
            (most recent first)
        """
        try:
            results = self.client.query(
                collection_name=self.cfg.collection_name,
                filter="",  # No filter, get all events
                output_fields=self._scalar_fields,
                limit=limit,
                consistency_level=consistency_level,
            )

            events = []
            for entity in results:
                start_time = datetime.fromtimestamp(entity["start_time"])
                end_time = datetime.fromtimestamp(entity["end_time"])
                recurrence_str = entity.get("recurrence", "")
                recurrence = None
                if recurrence_str:
                    try:
                        recurrence = json.loads(recurrence_str)
                    except json.JSONDecodeError:
                        recurrence = None

                event = CalendarEvent(
                    summary=entity["summary"],
                    start_time=start_time,
                    end_time=end_time,
                    description=entity.get("description") or None,
                    location=entity.get("location") or None,
                    event_id=entity["event_id"],
                    recurrence=recurrence,
                )
                events.append(event)

            # Sort by start_time (most recent first)
            events.sort(key=lambda e: e.start_time, reverse=True)

            logger.debug(f"Retrieved {len(events)} recent events from Milvus")
            return events

        except Exception as exc:
            logger.error(f"Error retrieving recent events: {exc}")
            return []

    def drop_collection(self) -> None:
        """Drop the entire collection and all its data."""
        if self.client.has_collection(self.cfg.collection_name):
            self.client.drop_collection(self.cfg.collection_name)
            logger.info(f"Dropped collection '{self.cfg.collection_name}'")
            return

        logger.warning(f"Missing collection '{self.cfg.collection_name}'")

    def _prepare_event_data(
        self, events: list[CalendarEvent]
    ) -> list[dict[str, Any]]:
        """Prepare event data for insertion into Milvus.

        Args:
            events: List of CalendarEvent objects

        Returns
        -------
            List of dictionaries with event data
        """
        data = []
        for event in events:
            recurrence_str = ""
            if event.recurrence:
                # Convert list to JSON string if recurrence is given
                recurrence_str = json.dumps(event.recurrence)

            # Create combined_text for embedding
            combined_text = event.summary
            if event.description and event.description.strip():
                combined_text += "\n\n" + event.description

            event_data = {
                "event_id": event.event_id,
                "summary": event.summary,
                "description": event.description or "",
                "location": event.location or "",
                "start_time": int(event.start_time.timestamp()),
                "end_time": int(event.end_time.timestamp()),
                "recurrence": recurrence_str,
                "combined_text": combined_text,
            }
            data.append(event_data)

        return data

    def _process_search_hit(
        self, hit: dict[str, Any], threshold: float
    ) -> tuple[CalendarEvent, float] | None:
        """Process a search hit and return CalendarEvent if above threshold.

        Args:
            hit: Search hit dictionary from Milvus
            threshold: Minimum similarity threshold

        Returns
        -------
            Tuple of (CalendarEvent, similarity_score)
            or None if below threshold
        """
        similarity = hit["distance"]
        if similarity < threshold:
            return None

        entity = hit["entity"]
        start_time = datetime.fromtimestamp(entity["start_time"])
        end_time = datetime.fromtimestamp(entity["end_time"])
        recurrence_str = entity.get("recurrence", "")
        recurrence = None
        if recurrence_str:
            try:
                recurrence = json.loads(recurrence_str)
            except json.JSONDecodeError:
                logger.warning(
                    f"Failed to parse recurrence data: {recurrence_str}"
                )
                recurrence = None

        event = CalendarEvent(
            summary=entity["summary"],
            start_time=start_time,
            end_time=end_time,
            description=entity.get("description") or None,
            location=entity.get("location") or None,
            event_id=entity["event_id"],
            recurrence=recurrence,
        )
        return event, similarity
