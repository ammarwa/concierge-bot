# Concierge

A professional Discord bot acts as a **Concierge** for your server—managing dynamic voice channels, creating private lobbies, and handling room service (with a few chaotic twists).

## Features

### 🎙️ Dynamic Voice Channels
- **Auto-Creation**: Join "➕ Create Channel" to be assigned your own room.
- **Smart Inheritance**: Channels created in a "Private Lobby" category automatically inherit private permissions.
- **Forever Alone**: If you're alone for 60s, your channel renames to "Forever Alone" (and restores when someone joins).
- **Auto-Cleanup**: Empty channels are swept away automatically.

### 🎛️ Room Service (Buttons)
- **🔒 Lock**: Sets the user limit to the current number of members.
- **🔓 Unlock**: Removes the user limit.
- **👥 Role Limit**: Restrict your channel to a specific role (e.g., "Subscribers Only").
- **✏️ Rename**: Instructions on how to rename your channel.

### 🛠️ User Customization
- **`!setname <name>`**: Set a permanent custom name for your rooms (e.g., `!setname Magdi's Lounge`).
- **`!resetname`**: Reset your channel name to default.

### 🎲 Fun & Chaos
- **`!roulette`**: Russian Roulette. 1 in 6 chance to get kicked from the channel.
- **`!flip`**: Flip a coin (Heads/Tails).
- **`!bonk @user`**: Send a user to AFK jail and back (requires them to be in VC).
- **`!ride @user`**: Send a user on a rollercoaster ride through random channels.
- **`!mimic @user`**: The bot mimics the user's nickname for 2 minutes.
- **`!lag @user`**: Simulates lag by moving the user between channels rapidly.
- **`!mute_roulette`**: Mutes a random user in your voice channel for 30 seconds.

### 👑 Admin Commands
- **`!create_lobby "<Name>" [@Role]`**: Create a new category and trigger channel.
    - Example Public: `!create_lobby "General Lounge"`
    - Example Private: `!create_lobby "VIP Area" @VIP`

## Prerequisites

- **Python 3.13+** (for local development)
- **Pipenv** (for dependency management)
- **Docker** (optional, for containerized deployment)
- **Discord Bot Token**: Get one from the [Discord Developer Portal](https://discord.com/developers/applications).

## Docker Setup

### 1. Configure Environment
Create a `.env` file in the project root:
```bash
DISCORD_TOKEN=your_token_here
DB_PATH=/data/concierge.db
MOD_CHANNEL_ID=123456789012345678  # Optional: ID for error logging
```

### 2. Run with Docker Compose (Recommended)
```bash
docker-compose up -d
```
- **Logs**: `docker-compose logs -f`
- **Restart**: `docker-compose restart`
- **Stop**: `docker-compose down`

### 3. Manual Docker Run
If you prefer not to use Compose:

**Build the image:**
```bash
docker build -t concierge-bot .
```

**Run the container:**
```bash
docker run -d \
  --name concierge_bot \
  --restart always \
  --env-file .env \
  -v $(pwd)/concierge.db:/data/concierge.db \
  concierge-bot
```

## Local Development

1.  **Install Dependencies**
    ```bash
    pipenv install
    ```

2.  **Activate Virtual Environment**
    ```bash
    pipenv shell
    ```

3.  **Run the Bot**
    ```bash
    python bot.py
    ```
    *Or one-liner:* `pipenv run python bot.py`

## Configuration Reference

| Variable | Description | Default |
| :--- | :--- | :--- |
| `DISCORD_TOKEN` | **Required**. Your Discord Bot Token. | - |
| `DB_PATH` | Path to the SQLite DB. | `concierge.db` |
| `MOD_CHANNEL_ID`| Channel ID to log bot errors. | `None` |

## Troubleshooting

- **Bot not creating channels?** Ensure the bot has "Manage Channels" and "Move Members" permissions.
- **Commands not working?** Check if the bot has "Message Content Intent" enabled in the Discord Developer Portal.
- **Database errors?** Ensure the `DB_PATH` directory is writable.
