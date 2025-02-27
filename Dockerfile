FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy source code
COPY src/ /app/src/
COPY run.py .

# Env
ENV ENVIRONMENT=production

# Expose port
EXPOSE 8080

# Run with Gunicorn as the production server
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "run:server"]