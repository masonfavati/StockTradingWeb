# StockTradingWeb

An evidence-driven stock-market research, forecasting,
and portfolio-tracking application.

## Project status

Initial development. No live investment recommendations
or real-money trading capabilities are available.

## Technology

- Backend: Python 3.14, FastAPI, SQLAlchemy, PostgreSQL
- Frontend: React, TypeScript, Vite, Tailwind CSS
- Package managers: uv and pnpm
- Database migrations: Alembic
- Testing: pytest and Vitest

## Local development

### Database

Start Docker Desktop, then:

    docker compose up -d db

### Backend

    cd backend
    cp .env.example .env
    uv sync --locked
    uv run alembic upgrade head
    uv run uvicorn app.main:app --reload --port 8000

API documentation: http://127.0.0.1:8000/docs

### Frontend

In a separate terminal:

    cd frontend
    pnpm install --frozen-lockfile
    pnpm run dev

Frontend: http://localhost:5173

## Quality checks

Backend:

    cd backend
    uv run pytest -v
    uv run ruff check .
    uv run mypy app
    uv run alembic check

Frontend:

    cd frontend
    pnpm exec vitest run
    pnpm run lint
    pnpm run build

## Documentation

See docs/PROJECT_CONSTITUTION.md for engineering
and statistical integrity requirements.

## Disclaimer

This project is research software in development.
Financial forecasts are uncertain and do not guarantee
investment profits.
