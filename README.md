# Document Hub Backend

FastAPI backend for Document Hub OCR System.

## Setup

### Prerequisites
- Python 3.11+
- PostgreSQL (recommended via docker-compose)
- Redis (optional)

### Installation

```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\Activate.ps1

# Install dependencies
poetry install
```

### Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your configuration
```

### Database Setup

```bash
# Start Postgres (and Redis) for local dev
docker compose -f docker-compose.yml up -d

# Run migrations
poetry run alembic upgrade head
```

## Development

```bash
# Run development server
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
poetry run pytest

# Run single test
poetry run pytest tests/test_main.py::test_root_endpoint

# Lint and format
poetry run ruff check . --fix
poetry run ruff format .
```

## Seed a Dev User (Login)

Create a user directly in the DB (useful for quick login testing):

```bash
cd backend
poetry run python scripts/seed_user.py --email test@example.com --name "Test User" --password "test1234" --role admin --reset
```

## API Documentation

Visit http://localhost:8000/docs for interactive API documentation.

## External OCR Integration

Trigger external OCR:
- Endpoint: `POST /ocr/trigger/external/{document_id}`
- Body:

```json
{
  "interface_id": "bad04949-e223-408b-adeb-d417fb9f8546",
  "transaction_id": "7494f925-a5d4-48cf-9a87-d23c1a24a1ca",
  "filepath": null
}
```

If `filepath` is null, the backend will build one from `PUBLIC_BASE_URL` (or the request base URL) pointing to `GET /documents/{document_id}/file`.

Webhook for external OCR results:
- Endpoint: `POST /ocr/webhook/external`
- Optional header: `X-OCR-Secret: <OCR_EXTERNAL_WEBHOOK_SECRET>`

## Document Preview (PDF Pages)

Render PDF pages to PNGs (stored under `STORAGE_DIR/pages/<document_id>/`):
- `POST /documents/{document_id}/render`

List available rendered pages:
- `GET /documents/{document_id}/pages`

Fetch a page image:
- `GET /documents/{document_id}/pages/{page_number}/image`

Fetch original file (used by external OCR `filepath`):
- `GET /documents/{document_id}/file`

## Settings: External OCR Interfaces

Manage external OCR interfaces from the frontend:
- `GET /settings/external-ocr`
- `POST /settings/external-ocr`
- `PATCH /settings/external-ocr/{interface_id}`
- `DELETE /settings/external-ocr/{interface_id}`
