#!/bin/sh
set -e

if [ "${DJANGO_DB_ENGINE}" = "django.db.backends.postgresql" ]; then
  echo "Waiting for PostgreSQL ${DJANGO_DB_HOST:-db}:${DJANGO_DB_PORT:-5432}..."
  python - <<'PY'
import os
import socket
import sys
import time

host = os.getenv("DJANGO_DB_HOST", "db")
port = int(os.getenv("DJANGO_DB_PORT", "5432"))

for _ in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            print("PostgreSQL is available.")
            sys.exit(0)
    except OSError:
        time.sleep(1)

print("PostgreSQL is not reachable.", file=sys.stderr)
sys.exit(1)
PY
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn naissanceplus.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout "${GUNICORN_TIMEOUT:-120}"
