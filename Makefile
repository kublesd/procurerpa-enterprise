.PHONY: dev dev-down compose-check backend-dev frontend-dev health test test-day1 migrate

dev:
	docker compose up --build

dev-down:
	docker compose down

compose-check:
	docker compose config

backend-dev:
	python -m uvicorn skyvern.forge.api_app:create_api_app --factory --host 0.0.0.0 --port 18000

frontend-dev:
	cd skyvern-frontend && npm run dev

health:
	curl -f "http://localhost:18000/api/v1/enterprise/procurement/health?ready=true"

test:
	python -m pytest tests -q

test-day1:
	python -m pytest tests/unit/test_day_1_baseline.py tests/unit/test_day_1_smoke_security.py -q

migrate:
	alembic upgrade heads
