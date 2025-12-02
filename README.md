# TRG Voice Manager Bot

A feature-rich Discord bot for managing dynamic voice channels, creating private lobbies, and engaging users with fun commands.

## Features

### 🎙️ Dynamic Voice Channels
- **Auto-Creation**: Join "➕ Create Channel" to get your own voice channel.
- **Smart Inheritance**: Channels created in a "Private Lobby" category automatically inherit private permissions.
- **Forever Alone**: If you're alone for 60s, your channel renames to "Forever Alone" (and restores when someone joins).
- **Auto-Cleanup**: Empty channels are deleted automatically.

### 🎛️ Voice Controls (Buttons)
- **🔒 Lock**: Sets the user limit to the current number of members.
- **🔓 Unlock**: Removes the user limit.
- **👥 Role Limit**: Restrict your channel to a specific role (e.g., "Subscribers Only").
- **✏️ Rename**: Instructions on how to rename your channel.

### 🛠️ User Customization
- **`!setname <name>`**: Set a permanent custom name for your channels (e.g., `!setname Magdi's Cave`).
- **`!resetname`**: Reset your channel name to default.

### 🎲 Fun & Chaos
- **`!roulette`**: Russian Roulette. 1 in 6 chance to get kicked from the channel.
- **`!flip`**: Flip a coin (Heads/Tails).
- **`!bonk @user`**: Send a user to AFK jail and back (requires them to be in VC).
- **`!ride @user`**: Send a user on a rollercoaster ride through random channels.

### 👑 Admin Commands
- **`!create_lobby "<Name>" [@Role]`**: Create a new category and trigger channel.
    - Example Public: `!create_lobby "Gaming Lounge"`
    - Example Private: `!create_lobby "Admin Area" @Admin`

## Docker Setup

### 1. Configure Environment
Create a `.env` file:
```bash
DISCORD_TOKEN=your_token_here
DB_PATH=/data/trg.db
```

### 2. Run with Docker Compose
```bash
docker-compose up -d
```

- **Logs**: `docker-compose logs -f`
- **Restart**: `docker-compose restart`

## Configuration Reference

| Variable | Description | Default |
| :--- | :--- | :--- |
| `DISCORD_TOKEN` | **Required**. Your Discord Bot Token. | - |
| `DB_PATH` | Path to the SQLite DB inside the container. | `trg.db` |

## Local Development

1.  **Install Dependencies**
    ```bash
    pipenv install
    ```
2.  **Run the Bot**
    ```bash
    pipenv run python bot.py
    ```
