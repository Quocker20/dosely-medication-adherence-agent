.PHONY: run test test-up test-db test-run test-down lint format typecheck check clean web-install web-dev web-build web-check

run:
	uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Tests run against a throwaway Postgres (:5433) + Redis (:6380) from
# docker-compose.test.yml with settings from .env.test -- never a real database.
PYTHON ?= python

test-up:
	docker compose -f docker-compose.test.yml up -d --wait

# Resets the test DB's public schema, applies docs/database_v1_init.sql, runs alembic upgrade head.
test-db:
	$(PYTHON) scripts/test_db_setup.py

test-run:
	$(PYTHON) -m pytest tests/ -v

test: test-up test-db test-run

test-down:
	docker compose -f docker-compose.test.yml down -v

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

typecheck:
	mypy src/

check: lint format test

# Portal bác sĩ (web/) — dev server proxy /api sang uvicorn cổng 8000.
web-install:
	cd web && npm install

web-dev:
	cd web && npm run dev

web-build:
	cd web && npm run build

web-check:
	cd web && npm run typecheck

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
