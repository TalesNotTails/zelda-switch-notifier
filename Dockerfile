FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY config.yaml .

# Persist "last known state" across restarts
# commented out to work on Railway
# VOLUME ["/app/state"]

CMD ["python", "-u", "app/main.py"]
