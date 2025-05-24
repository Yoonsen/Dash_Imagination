FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production
ENV PYTHONPATH=/app/src

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire application directory structure
COPY . .

COPY src/dash_imagination/assets/ /app/src/dash_imagination/assets/

RUN mkdir -p /app/src/dash_imagination/data
COPY src/dash_imagination/data/imagination.db /app/src/dash_imagination/data/

# Make the application port available

EXPOSE 8080

# Start the application with Gunicorn
CMD exec gunicorn --bind :8080 \
    --workers 1 \
    --threads 8 \
    --timeout 0 \
    --access-logfile - \
    --error-logfile - \
    "src.dash_imagination.app:server"