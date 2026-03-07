FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    pkg-config \
    libpq-dev \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    libjpeg62-turbo-dev \
    libcairo2-dev \
    libpango1.0-dev \
    libgdk-pixbuf-2.0-dev \
    libcairo2 \
    libpango-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install -r /app/requirements.txt

COPY . /app

RUN mkdir -p /app/staticfiles /app/media \
    && sed -i 's/\r$//' /app/docker/entrypoint.sh \
    && chmod +x /app/docker/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
