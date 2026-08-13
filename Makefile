.PHONY: setup dev dev-down compose-check backend-dev frontend-dev health test test-backend frontend-test frontend-build verify seed-procurement smoke-quotes sit-controls test-day1 migrate

setup:
	python -m pip install -e ".[dev]"

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

test: test-backend

test-backend:
	python -m pytest tests -q

frontend-test:
	cd skyvern-frontend && npm test

frontend-build:
	cd skyvern-frontend && npm run build

verify: test-backend frontend-test frontend-build compose-check

seed-procurement:
	python scripts/seed_procurement_demo.py

smoke-quotes:
	docker compose exec skyvern python scripts/smoke_procurement.py --scenario quotes

sit-controls:
	docker compose exec skyvern python scripts/smoke_procurement.py --scenario controls

test-day1:
	python -m pytest tests/unit/test_day_1_baseline.py tests/unit/test_day_1_smoke_security.py -q

migrate:
	alembic upgrade heads
