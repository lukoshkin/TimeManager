# TimeManager

TimeManager is a comprehensive time and calendar management application that helps you schedule and manage events efficiently. It offers both a Telegram bot interface and an MCP (Machine-Computer-Protocol) server for seamless interaction.

## Features

- **Intelligent Event Scheduling**: Easily create, update, and delete calendar events.
- **Natural Language Processing**: Use natural language to schedule events (e.g., "Schedule meeting with John tomorrow at 2pm").
- **Recurring Events**: Set up recurring events (daily, weekly, or monthly).
- **Free Slot Finding**: Automatically find available time slots for your events.
- **Multiple Interfaces**: Access via Telegram bot or MCP server.
- **Google Calendar Integration**: Sync with your Google Calendar account.

## Installation

### Option 1: Using pip

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/TimeManager.git
   cd TimeManager
   ```

2. Set up a virtual environment (optional but recommended):

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

### Option 2: Using uv (Recommended)

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/TimeManager.git
   cd TimeManager
   ```

2. Install with uv:

   ```bash
   # Install uv if you don't have it yet
   # pip install uv

   # Create and activate a virtual environment with uv
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate

   # Install the package in development mode
   uv pip install -e .
   ```

3. Create a `.env` file in the root directory with the following configuration:

   ```
   telegram_api_id=your_telegram_api_id
   telegram_api_hash=your_telegram_api_hash
   telegram_bot_token=your_telegram_bot_token
   google_credentials_file=path/to/credentials.json
   google_token_file=path/to/token.json
   log_level=INFO
   ```

4. Set up Google Calendar API:
   - Visit the [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project and enable the Google Calendar API
   - Create OAuth 2.0 credentials and download them as `credentials.json`
   - Place the file in your project directory or specify its path in the `.env` file

## Usage

### Running the Application

```bash
python -m src.main
```

This will start both the Telegram bot and the MCP server (if enabled).

### Telegram Bot

Once the bot is running, start a chat with your bot on Telegram and use the following commands:

- `/start` - Start the bot
- `/help` - Show help message
- `/schedule` - View your upcoming events
- `/update` - Update an existing event
- `/delete` - Delete an event
- `/cancel` - Cancel the current operation

You can also interact with the bot using natural language:

- "Schedule a meeting with John tomorrow at 2pm for 1 hour"
- "Create a weekly team meeting every Monday at 10am for 4 weeks"
- "Set up a dentist appointment next week"

### MCP Server

The MCP server provides an API for interacting with the calendar. By default, it runs on `localhost:8000/mcp`. You can use MCP-compatible tools to interact with it.

## Configuration

You can configure the application by modifying the `.env` file or setting environment variables. Available settings include:

- `telegram_api_id` - Telegram API ID
- `telegram_api_hash` - Telegram API hash
- `telegram_bot_token` - Telegram bot token
- `google_credentials_file` - Path to Google API credentials file
- `google_token_file` - Path to Google API token file
- `mcp_server_enabled` - Enable MCP server (true/false)
- `mcp_server_host` - MCP server host (default: localhost)
- `mcp_server_port` - MCP server port (default: 8000)
- `log_level` - Logging level (default: INFO)

## Development

The project structure is organized as follows:

```
TimeManager/
├── src/
│   ├── config/
│   │   ├── logging.py
│   │   └── settings.py
│   ├── services/
│   │   ├── google_calendar.py
│   │   ├── mcp_server.py
│   │   ├── message_parser.py
│   │   ├── telegram_bot.py
│   │   └── time_slot_manager.py
│   └── main.py
├── .env
└── README.md
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
