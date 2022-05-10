# Contributing to Dallas LandScan

Thank you for your interest in contributing. This guide covers the development workflow, code standards, and how to add new features.

## Development Setup

### Prerequisites
- Docker ≥ 24.0 and Docker Compose ≥ 2.24
- Python 3.11+ (for local backend development)
- Node.js 20+ (for local frontend development)
- GDAL 3.6+ (installed via apt on Ubuntu; Homebrew on macOS)

### Quick Start

```bash
git clone https://github.com/jermainewright/dallas-landuse-change-detection.git
cd dallas-landuse-change-detection
cp .env.example .env
make up
make migrate
make seed
```

## Project Structure

```
backend/app/
├── api/v1/          – FastAPI route handlers (thin, delegate to services)
├── core/            – Config, logging, exceptions, metrics
├── db/
│   ├── models/      – SQLAlchemy ORM models
│   └── repositories/– Data access layer (CRUD, no business logic)
├── services/gis/    – Core GIS processing (preprocessor, classifier, detector)
├── utils/           – Shared utilities (raster helpers, validation)
└── worker/          – Celery task definitions
```

## Development Workflow

### Backend

```bash
# Run tests (fast, no Docker needed for unit tests)
make test-unit

# Run full test suite
make test

# Lint and format
make lint
make format
```

### Adding a New GIS Algorithm

1. Create a new module in `backend/app/services/gis/`
2. Write unit tests in `backend/tests/unit/`
3. Expose inputs/outputs via a Celery task in `worker/celery_app.py`
4. Add API endpoint in `api/v1/endpoints/`
5. Add Pydantic schema in `api/v1/schemas/`

### Database Migrations

```bash
# Generate a new migration after changing ORM models
docker compose exec backend alembic revision --autogenerate -m "add_column_x"

# Apply migrations
make migrate
```

### Frontend

```bash
cd frontend
npm install
npm run dev     # Hot-reload dev server at :3000
npm run type-check
npm run lint
```

## Code Standards

### Python
- **Style**: Ruff (PEP8 + isort + pyflakes). Run `make format` before committing.
- **Types**: All new functions must have type annotations.
- **Docstrings**: Google-style for public functions. Include algorithm references where relevant.
- **Tests**: Unit tests required for all new GIS service functions. Aim for >80% coverage on new code.

### TypeScript / React
- Strict TypeScript - no `any` unless absolutely necessary.
- Components in `src/components/` must be functional with typed props.
- API calls must go through `src/lib/api.ts` - no raw `fetch` in components.

### Git Conventions

Branch names: `feat/`, `fix/`, `chore/`, `docs/`
Commit messages: Conventional Commits format
- `feat(classifier): add SAM-based superpixel post-processing`
- `fix(preprocessor): handle rasters with no-data borders`
- `docs(readme): update throughput metrics for Sentinel-2`

## Pull Request Checklist

- [ ] All tests pass (`make test`)
- [ ] Linting passes (`make lint`)
- [ ] TypeScript types check (`cd frontend && npm run type-check`)
- [ ] New functionality has tests
- [ ] README updated if adding new features or changing setup steps
- [ ] `.env.example` updated if adding new environment variables

## Reporting Issues

Please include:
- OS and Docker version
- Raster file details (satellite, bands, size)
- Full error message and stack trace
- Steps to reproduce

## Architecture Decision Records

For significant architectural changes, please open a GitHub Discussion first describing the problem and proposed solution. This is especially important for changes to the GIS pipeline, database schema, or Celery task structure.
