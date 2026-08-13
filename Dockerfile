FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY . .

RUN pip install --no-cache-dir --no-build-isolation --no-deps . \
    && playwright install --with-deps chromium

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade heads && uvicorn skyvern.forge.api_app:create_api_app --factory --host 0.0.0.0 --port 8000"]
