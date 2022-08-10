# ─── Dallas LandScan – Developer Makefile ──────────────────────────────────────
# Usage: make <target>
# Requires: Docker, Docker Compose, Python 3.11+

.PHONY: help up down build logs shell-backend shell-db migrate test lint format seed clean

COMPOSE = docker compose
BACKEND = $(COMPOSE) exec backend

# Default target
help:
	@echo ""
	@echo "  Dallas LandScan – Available Commands"
	@echo "  ────────────────────────────────────────────────────────────────"
	@echo "  up            Start all services (build if needed)"
	@echo "  down          Stop and remove containers"
	@echo "  build         Rebuild Docker images"
	@echo "  logs          Tail logs from all services"
	@echo "  logs-worker   Tail Celery worker logs only"
	@echo ""
	@echo "  migrate       Run Alembic database migrations"
	@echo "  seed          Generate synthetic test rasters"
	@echo ""
	@echo "  test          Run all backend tests with coverage"
	@echo "  test-unit     Run unit tests only (fast)"
	@echo "  lint          Run Ruff linter"
	@echo "  format        Auto-format code with Ruff"
	@echo "  typecheck     Run mypy type checker"
	@echo ""
	@echo "  shell-backend  Open shell inside backend container"
	@echo "  shell-db       Open psql inside PostgreSQL container"
	@echo ""
	@echo "  clean         Remove all containers, volumes, and build cache"
	@echo "  reset-db      Drop and recreate the database"
	@echo ""

up:
	$(COMPOSE) up --build -d
	@echo ""
	@echo "  Services:"
	@echo "  Frontend  → http://localhost:3000"
	@echo "  API Docs  → http://localhost:8000/api/docs"
	@echo "  Flower    → http://localhost:5555"
	@echo "  Metrics   → http://localhost:8000/metrics"
	@echo ""

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build --no-cache

logs:
	$(COMPOSE) logs -f

logs-worker:
	$(COMPOSE) logs -f celery_worker

shell-backend:
	$(BACKEND) bash

shell-db:
	$(COMPOSE) exec db psql -U landuse -d landuse_db

# ─── Database ─────────────────────────────────────────────────────────────────

migrate:
	$(BACKEND) alembic upgrade head
	@echo "✓ Migrations applied"

reset-db:
	$(BACKEND) alembic downgrade base
	$(BACKEND) alembic upgrade head
	@echo "✓ Database reset"

# ─── Test data ────────────────────────────────────────────────────────────────

seed:
	$(BACKEND) python /app/../scripts/generate_test_rasters.py
	@echo "✓ Synthetic rasters generated in backend/data/rasters/test/"

# ─── Testing ──────────────────────────────────────────────────────────────────

test:
	$(BACKEND) pytest tests/ -v --tb=short

test-unit:
	$(BACKEND) pytest tests/unit/ -v --tb=short --no-cov

test-integration:
	$(BACKEND) pytest tests/integration/ -v --tb=short

# ─── Code quality ─────────────────────────────────────────────────────────────

lint:
	$(BACKEND) ruff check app/ tests/

format:
	$(BACKEND) ruff format app/ tests/
	$(BACKEND) ruff check --fix app/ tests/

typecheck:
	$(BACKEND) mypy app/ --ignore-missing-imports

# ─── Cleanup ──────────────────────────────────────────────────────────────────

clean:
	$(COMPOSE) down -v --rmi local --remove-orphans
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".pytest_cache" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "htmlcov" -type d -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Cleanup complete"
