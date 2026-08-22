FROM python:3.11-slim

# Install system dependencies and Stockfish
RUN apt-get update && \
    apt-get install -y --no-install-recommends stockfish ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run unbuffered output so logs show up immediately in cloud dashboard
ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]
