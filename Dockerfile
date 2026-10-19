FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_APP=app:create_app \
    APP_ENV=production

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN useradd --create-home --uid 1000 flowmap && chown -R flowmap /app
USER flowmap

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"

# Migrations run on every start (idempotent), then gunicorn.
CMD ["sh", "-c", "flask db upgrade && exec gunicorn 'app:create_app()' --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY:-2} --threads 4 --timeout 120 --access-logfile -"]
