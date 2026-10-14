.PHONY: dev test lint format

dev:
	docker compose up --build

test:
	uv run pytest

lint:
	uv run ruff check
	uv run ruff format --check
	uv run mypy

format:
	uv run ruff format
	uv run ruff check --fix
