.PHONY: dev test lint format fixtures

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

# Regenerate tests/fixtures/probe/*.json with the ffmpeg pinned in the image.
fixtures:
	docker build -t projeto-dvd-fixtures .
	docker run --rm --network none -v "$(CURDIR)/tests/fixtures:/fixtures" \
		--user "$$(id -u):$$(id -g)" projeto-dvd-fixtures sh /fixtures/make_fixtures.sh /fixtures/probe
