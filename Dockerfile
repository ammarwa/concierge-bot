# Use a lightweight Python base
FROM python:3.13-slim

# Prevent python from writing pyc files or buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install pipenv
RUN pip install --no-cache-dir pipenv

# Copy dependency files first (for caching layers)
COPY Pipfile Pipfile.lock ./

# Install dependencies system-wide
RUN pipenv install --system --deploy

# Copy the rest of the application
COPY . .

# Create a non-root user and data directory
RUN useradd -m appuser && mkdir -p /data && chown appuser:appuser /data

# Switch to non-root user
USER appuser

# Run the bot
CMD ["python", "bot.py"]
