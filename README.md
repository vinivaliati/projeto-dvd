# projeto-dvd

[![CI](https://github.com/vinivaliati/projeto-dvd/actions/workflows/ci.yml/badge.svg)](https://github.com/vinivaliati/projeto-dvd/actions/workflows/ci.yml)

A local web app that turns a personal movie and TV collection into **authored DVD and Blu-ray
discs with navigable menus**, plus **printable covers** for the cases.

The goal is a physical collection meant to last: discs that follow the official DVD-Video and
BDMV specifications closely enough to play on an ordinary player 20 years from now, with menus
simple enough for a child or a grandparent to use with just the remote.

> **Status:** Phase 0 (project setup). Today the app serves a hello page and a media toolchain
> health check. See the roadmap in [`CLAUDE.md`](CLAUDE.md) (in Portuguese).

## Planned pipeline

```
scan → probe → match metadata (TMDB) → disc project (DVD-5/9, BD-25/50) → encode → menu → authoring → ISO
```

The app produces an `.iso` file. Burning happens on Windows (ImgBurn or the built-in burner),
because WSL cannot access the optical drive.

## Stack

- Python 3.12, FastAPI, Jinja2 (HTMX and Tailwind arrive with the first real screens)
- Media toolchain: ffmpeg, dvdauthor/spumux, tsMuxeR, xorriso
- Docker and docker compose; GitHub Actions CI
- uv, ruff, mypy (strict), pytest

## Running with Docker

Requirements: Docker (on Windows, Docker Desktop with WSL integration enabled).

```bash
cp .env.example .env   # then edit the three host paths
set -a; . ./.env; set +a
mkdir -p "$HOST_WORK_DIR" "$HOST_OUTPUT_DIR"   # Docker would create missing ones as root
make dev               # docker compose up --build
```

Open <http://localhost:8000>. <http://localhost:8000/health> lists the media tool versions found
in the container and returns 503 if any of them is missing.

The media folder is mounted **read-only**: the app never modifies the original files.

## Development

Requirements: [uv](https://docs.astral.sh/uv/).

| Command | What it does |
|---|---|
| `make test` | Run the test suite with coverage (minimum 90%) |
| `make lint` | ruff lint, ruff format check, mypy strict |
| `make format` | Format and auto-fix with ruff |
| `make dev` | Build and start the app with docker compose |

## Maintenance

- The media toolchain is pinned (base image digest, Debian package versions, tsMuxeR checksum).
  When Debian ships a security update the build breaks on purpose; update the pins in the
  `Dockerfile` and commit.
- tsMuxeR has low upstream activity. Keep a copy of
  `tsMuxer-2.7.0-linux.zip` (sha256 `ceaaa181ab70e201685b1e45260d337d1cbdb0aba1408d4fbc47e232a7e4c987`)
  outside GitHub.

## License

[MIT](LICENSE)
