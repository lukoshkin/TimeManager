"""LangChain ReAct Telegram bot implementation using MCP adapters."""

import datetime

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from telethon import TelegramClient, events
from telethon.events import NewMessage

from src.config.env import settings
from src.config.llm_config import get_llm_config
from src.config.logging import logger
from src.llm_solutions.base import BaseTelegramBot
from src.services.event_milvus_connector import (
    EventMilvusConfig,
    EventMilvusConnector,
)


class LangChainReActTelegramBot(BaseTelegramBot):
    """LangChain ReAct-based telegram bot for time management using MCP."""

    def __init__(self) -> None:
        """Initialize the LangChain ReAct Telegram bot."""
        super().__init__()
        self.model: BaseChatModel
        self.tools: list[BaseTool]
        self.memory: MemorySaver
        self.agent_executor: CompiledStateGraph

        config = get_llm_config()
        self._semantic_config = config.semantic_search
        self._model_config = config.llm_solution.langchain_react.model
        self._initialize_services()
        self._initialize_mcp_client()
        self._register_handlers()

    def _initialize_services(self) -> None:
        """Initialize bot services (calendar, time manager, etc.)."""
        self.client = TelegramClient(
            "time_manager_bot_react",
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )
        try:
            milvus_config = EventMilvusConfig(
                uri=settings.milvus_uri,
                collection_name=self._semantic_config.collection_name,
                vector_dim=self._semantic_config.vector_dim,
                model_name=self._semantic_config.model_name,
                embedding_provider=self._semantic_config.model_provider,
            )
            self.semantic_search = EventMilvusConnector(milvus_config)
            self.semantic_search.create_collection()
        except Exception as exc:
            logger.warning(f"Could not initialize Milvus: {exc}")
            self.semantic_search = None

    def _initialize_mcp_client(self) -> None:
        """Initialize the MCP client to connect to our calendar server."""
        try:
            # Let the MCP client handle subprocess creation
            # self.mcp_client = MultiServerMCPClient(
            #     {
            #         "timemanager": {
            #             "command": sys.executable,
            #             "args": [
            #                 str(
            #                     Path(__file__).parents[2]
            #                     / "services"
            #                     / "mcp_server.py"
            #                 )
            #             ],
            #             "transport": "stdio",
            #         }
            #     }
            # )
            # logger.info(
            #     "MCP client initialized successfully using stdio transport"
            # )
            mcp_url = (
                f"http://{settings.mcp_server_host}"
                f":{settings.mcp_server_port}/mcp/"
            )
            self.mcp_client = MultiServerMCPClient(
                {
                    "timemanager": {
                        "url": mcp_url,
                        "transport": "streamable_http",
                    }
                }
            )
            logger.info(
                f"MCP client initialized successfully,"
                f" connecting to {mcp_url}.."
            )
        except Exception as exc:
            logger.error(f"Failed to initialize MCP client: {exc}")
            raise exc

    async def _initialize_agent(self) -> None:
        """Initialize the LangChain ReAct agent with MCP tools."""
        try:
            self.model = init_chat_model(
                model=self._model_config.model,
                model_provider="openai",
                api_key=settings.openai_api_key,
                temperature=self._model_config.temperature,
                max_tokens=self._model_config.max_tokens,
            )
            self.tools = await self.mcp_client.get_tools()
            logger.info(f"Loaded {len(self.tools)} tools from MCP server")
            logger.debug(", ".join(tool.name for tool in self.tools))

            self.memory = MemorySaver()
            self.agent_executor = create_react_agent(
                model=self.model,
                tools=self.tools,
                checkpointer=self.memory,
            )
            logger.info("LangChain ReAct agent initialized successfully")
        except Exception as exc:
            logger.error(f"Failed to initialize LangChain ReAct agent: {exc}")
            raise

    def _register_handlers(self) -> None:
        """Register event handlers for the bot."""
        # Register basic command handlers
        handlers = [
            ("/start", self._start_handler),
            ("/help", self._help_handler),
            ("/clear", self._clear_handler),
        ]

        for pattern, handler in handlers:
            self.client.on(events.NewMessage(pattern=pattern))(handler)

        # Register general message handler for non-commands
        self.client.on(
            events.NewMessage(
                func=lambda event: not event.text.startswith("/")
            )
        )(self._message_handler)

    async def _start_handler(self, event: NewMessage.Event) -> None:
        """Handle the /start command."""
        sender = await event.get_sender()
        user_id = sender.id

        # Initialize user state
        self._reset_user_state(user_id)

        await event.respond(
            "👋 Welcome to the Time Manager Bot (LangChain ReAct MCP Edition)!\n\n"
            "I'm an intelligent assistant powered by the Model Context Protocol (MCP) "
            "that can help you manage your calendar. "
            "I can understand natural language and use various tools to:\n\n"
            "• Create and schedule events\n"
            "• View your schedule\n"
            "• Update existing events\n"
            "• Delete events\n"
            "• Find free time slots\n"
            "• Handle recurring events\n\n"
            "Just tell me what you want to do in natural language! For example:\n"
            '• "Schedule a team meeting for tomorrow at 2pm"\n'
            '• "Show me my schedule for next week"\n'
            '• "Find free time for a 1-hour meeting this week"\n'
            '• "Cancel my dentist appointment"\n\n'
            "I'll ask for clarification if I need more information."
        )

    async def _help_handler(self, event: NewMessage.Event) -> None:
        """Handle the /help command."""
        await event.respond(
            "🔍 Time Manager Bot Help (LangChain ReAct MCP Edition)\n\n"
            "I'm an AI assistant powered by MCP that can help you with calendar management. "
            "Here are some examples of what you can ask me:\n\n"
            "**Creating Events:**\n"
            '• "Schedule a meeting with John tomorrow at 2pm for 1 hour"\n'
            '• "Create a dentist appointment next week"\n'
            '• "Set up a weekly team meeting every Monday at 10am"\n\n'
            "**Viewing Schedule:**\n"
            '• "Show me my schedule for today"\n'
            '• "What do I have planned for next week?"\n'
            '• "List my appointments for the next 3 days"\n\n'
            "**Finding Time:**\n"
            '• "When am I free for a 30-minute meeting?"\n'
            '• "Find 2-hour slots this week"\n'
            '• "What time slots are available tomorrow?"\n\n'
            "**Updating/Deleting:**\n"
            '• "Move my 2pm meeting to 3pm"\n'
            '• "Cancel my dentist appointment"\n'
            '• "Change the location of tomorrow\'s meeting"\n\n'
            "**Commands:**\n"
            "/start - Start the bot\n"
            "/help - Show this help message\n"
            "/clear - Clear conversation history\n\n"
            "I'll remember our conversation and can ask for clarification if needed!"
        )

    async def _clear_handler(self, event: NewMessage.Event) -> None:
        """Handle the /clear command to clear conversation history."""
        sender = await event.get_sender()
        user_id = sender.id

        # Reset user state which will start a new conversation thread
        self._reset_user_state(user_id)

        await event.respond(
            "🧹 Conversation history cleared! \n"
            "I'll start fresh with our next interaction."
        )

    async def _message_handler(self, event: NewMessage.Event) -> None:
        """Handle general messages using the LangChain ReAct agent."""
        sender = await event.get_sender()
        user_id = sender.id
        message = event.text

        if user_id not in self.user_states:
            self._reset_user_state(user_id)

        try:
            # Show typing indicator
            async with self.client.action(sender, "typing"):
                config = {"configurable": {"thread_id": str(user_id)}}
                input_message = {"role": "user", "content": message}
                logger.info(f"Processing msg from user {user_id}: {message}")
                response_text = ""

                # Stream the agent's response
                try:
                    async for step in self.agent_executor.astream(
                        {"messages": [input_message]},
                        config=config,
                        stream_mode="values",
                    ):
                        # Get the last message from the step
                        logger.debug(step)
                        if "messages" in step and step["messages"]:
                            last_message = step["messages"][-1]

                            # Check if it's an AI message
                            if (
                                hasattr(last_message, "content")
                                and last_message.content
                            ):
                                response_text = last_message.content

                except Exception as agent_error:
                    logger.error(f"Agent execution error: {agent_error}")
                    response_text = (
                        "I encountered an error while processing your request."
                        " Please try rephrasing your question or try again."
                    )

                # Send the response
                if response_text:
                    # Split long responses if needed
                    max_length = 4000  # Telegram's message limit is ~4096
                    if len(response_text) > max_length:
                        chunks = [
                            response_text[i : i + max_length]
                            for i in range(0, len(response_text), max_length)
                        ]
                        for chunk in chunks:
                            await event.respond(chunk)
                    else:
                        await event.respond(response_text)
                else:
                    await event.respond(
                        "I'm sorry, I couldn't process your request. "
                        "Please try rephrasing your question."
                    )

        except Exception as exc:
            logger.error(f"Error in message handler: {exc}")
            await event.respond(
                "Sorry, I encountered an error processing your request. "
                "Please try again or contact support if the issue persists."
            )

    async def start(self) -> None:
        """Start the bot and run until disconnected.

        Connects to the Telegram API and starts listening for messages.
        """
        await self._initialize_agent()
        await self.client.start(bot_token=settings.telegram_bot_token)
        logger.info("LangChain ReAct MCP Telegram bot started")

        try:
            await self.client.run_until_disconnected()
        finally:
            # Clean up MCP client
            if hasattr(self, "mcp_client"):
                await self.mcp_client.close()
                logger.info("MCP client closed")

    def _reset_user_state(self, user_id: int) -> None:
        """Reset user state and start new conversation thread."""
        self.user_states[user_id] = {
            "state": "idle",
            "thread_id": f"user_{user_id}_{datetime.datetime.now().timestamp()}",
        }
