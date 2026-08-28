# Use the official Playwright Python base image
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

# Set environment variables for Python performance and output buffering
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN playwright install --with-deps

COPY . .

RUN chmod -R 777 /app

# Shell execution form allows environment variable expansion ($PERFIL, $FLAGS)
CMD python main.py --perfil $PERFIL $FLAGS
