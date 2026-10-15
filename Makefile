.PHONY: dev test test-slow lint format fixtures

dev:
	docker compose up --build

test:
	uv run pytest

# Integration tests with the real media toolchain, inside the image, without network.
test-slow:
	docker build --target test -t projeto-dvd-test .
	docker run --rm --network none projeto-dvd-test

lint:
	uv run ruff check
	uv run ruff format --check
	uv run mypy

format:
	uv run ruff format
	uv run ruff check --fix

# Regenerate tests/fixtures/probe/*.json with the ffmpeg pinned in the image.
fixtures:
	docker build --target runtime -t projeto-dvd-fixtures .
	docker run --rm --network none -v "$(CURDIR)/tests/fixtures:/fixtures" \
		--user "$$(id -u):$$(id -g)" projeto-dvd-fixtures sh /fixtures/make_fixtures.sh /fixtures/probe
