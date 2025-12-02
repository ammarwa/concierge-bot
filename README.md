# TRG Voice Manager Bot

A Discord bot designed to manage dynamic voice channels with unique features like "Forever Alone" detection and persistent custom channel names.

## Features

- **Dynamic Voice Channels**: Automatically creates a new voice channel when a user joins the "Create Channel" trigger.
- **Forever Alone Mode**: If a user is alone in a channel for more than 60 seconds, the channel is renamed to "Forever Alone". It restores the original name when someone else joins.
- **Persistence**: Remembers custom channel names for users using a SQLite database.
- **Clean Up**: Automatically deletes empty dynamic channels.
- **Dockerized**: Ready for deployment with Docker and Docker Compose.

## Setup

### Prerequisites

- Docker & Docker Compose
- A Discord Bot Token

### Quick Start (Docker)

1.  **Clone the repository**
2.  **Create a `.env` file** (or set environment variables in `docker-compose.yml`)
    ```bash
    DISCORD_TOKEN=your_token_here
    DB_PATH=/data/trg.db
    ```
3.  **Run with Docker Compose**
    ```bash
    docker-compose up -d
    ```

### Configuration

| Variable | Description | Default |
| :--- | :--- | :--- |
| `DISCORD_TOKEN` | Your Discord Bot Token | Required |
| `DB_PATH` | Path to the SQLite database | `trg.db` |

### Local Development

1.  **Install Dependencies**
    ```bash
    pipenv install
    ```
2.  **Run the Bot**
    ```bash
    pipenv run python bot.py
    ```

## Project Structure

- `bot.py`: Main bot logic.
- `Dockerfile`: Docker image definition (runs as non-root `appuser`).
- `docker-compose.yml.sample`: Example Compose configuration.
- `.github/workflows`: CI/CD pipeline for building and publishing the Docker image.
