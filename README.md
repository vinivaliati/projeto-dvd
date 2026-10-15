# projeto-dvd

[![CI](https://github.com/vinivaliati/projeto-dvd/actions/workflows/ci.yml/badge.svg)](https://github.com/vinivaliati/projeto-dvd/actions/workflows/ci.yml)

**English** | [Português](README.pt-BR.md)

A local web app that turns a personal movie and TV collection into **authored DVD and Blu-ray
discs with navigable menus**, plus **printable covers** for the cases.

The goal is a physical collection meant to last: discs that follow the official DVD-Video and
BDMV specifications closely enough to play on an ordinary player 20 years from now, with menus
simple enough for a child or a grandparent to use with just the remote.

> **Status:** Phase 1 (library). The app lists each disc folder of the input folder and reads
> the technical data of its videos with ffprobe: duration, resolution, codecs, HDR, audio and
> subtitle tracks, chapters and external subtitles. See the roadmap in [`CLAUDE.md`](CLAUDE.md)
> (in Portuguese).

## Planned pipeline

```
scan → probe → match metadata (TMDB) → disc project (DVD-5/9, BD-25/50) → encode → menu → authoring → ISO
```

The app produces an `.iso` file. Burning happens on Windows (ImgBurn or the built-in burner),
because WSL cannot access the optical drive.

## How the input folder works

One subfolder of the input folder is one disc. Put the videos of each disc in its own
subfolder; the app never walks the whole drive.

```
entrada\                          (HOST_MEDIA_DIR, mounted read-only at /media)
  Senhor dos Aneis\               → 1 folder = 1 disc
    A Sociedade do Anel.mkv
    As Duas Torres.mkv
    O Retorno do Rei.mkv
    O Retorno do Rei.pt-BR.srt    → external subtitle of the video above
  Friends T1\
    Temporada 1\S01E01.mkv        → subfolders inside a disc folder are allowed
```

- Videos: `.mkv`, `.mp4`, `.m4v`, `.avi`, `.mov`, `.ts`, `.m2ts`.
- External subtitles: `.srt`, `.ass`, `.ssa`, `.sup`, and `.idx` next to its `.sub`. A
  subtitle belongs to the video whose name starts it (`Movie.pt-BR.srt` → `Movie.mkv`); when
  several match, the longest name wins (`Movie.2.pt.srt` → `Movie.2.mkv`).
- Videos placed directly in the input folder, outside a disc folder, are not listed. Symbolic
  links are ignored.
- Use one video file per title (for example an `.mkv` made with MakeMKV). Copied disc folders
  (`VIDEO_TS`, `BDMV`) are not supported: their `.VOB` files are skipped and a full `BDMV` would list
  every clip.
- Rescans are incremental: a file is read again only when its size or modification time
  changes.
- The input folder can be on `C:` or on the external drive itself. Copying to `C:` takes space
  (a Blu-ray movie is 30 to 50 GB).

## Stack

- Python 3.12, FastAPI, Jinja2, HTMX and a small hand-written CSS (no build step)
- SQLite with SQLModel and Alembic
- Media toolchain: ffmpeg, dvdauthor/spumux, tsMuxeR, xorriso
- Docker and docker compose; GitHub Actions CI
- uv, ruff, mypy (strict), pytest

## Running with Docker

Requirements: Docker (on Windows, Docker Desktop with WSL integration enabled).

```bash
cp .env.example .env   # then edit the three host paths
# Docker would create missing folders as root; the subshell keeps .env out of your shell.
(set -a; . ./.env; mkdir -p "$HOST_WORK_DIR" "$HOST_OUTPUT_DIR")
make dev               # docker compose up --build
```

The input folder (`HOST_MEDIA_DIR`) is not created for you: create it with one subfolder per
disc, and if it lives on the external drive, connect the drive before `make dev`. Otherwise
Docker mounts an empty folder and the library shows no discs.

Open <http://localhost:8000>. <http://localhost:8000/health> lists the media tool versions found
in the container and returns 503 if any of them is missing.

The input folder is mounted **read-only**: the app never modifies the original files.

The scan results are kept in a SQLite database in the `data` Docker volume, so they survive
rebuilds. `docker compose down -v` erases that volume (the scan cache only, never the media);
the next scan reads everything again.

## Development

Requirements: [uv](https://docs.astral.sh/uv/).

| Command | What it does |
|---|---|
| `make test` | Run the unit tests with coverage (minimum 90%) |
| `make test-slow` | Run the integration tests inside the Docker image, with the real ffmpeg and no network |
| `make lint` | ruff lint, ruff format check, mypy strict |
| `make format` | Format and auto-fix with ruff |
| `make fixtures` | Regenerate the ffprobe JSON fixtures with the ffmpeg pinned in the image |
| `make dev` | Build and start the app with docker compose |

To run the app without Docker (needs `ffprobe` on the `PATH` to scan):

```bash
MEDIA_DIR=/path/to/entrada DATABASE_URL=sqlite:///./projeto_dvd.db \
  uv run uvicorn projeto_dvd.app:create_app --factory
```

## Maintenance

- The media toolchain is pinned (base image digest, Debian package versions, tsMuxeR checksum).
  When Debian ships a security update the build breaks on purpose; update the pins in the
  `Dockerfile` and commit. After an ffmpeg update, run `make test-slow`: it compares the
  committed fixtures with the new ffprobe output. The Dolby Vision profile 5 fixture is
  hand-written: also check that ffprobe still names its side data "DOVI configuration record".
- tsMuxeR has low upstream activity. Keep a copy of
  `tsMuxer-2.7.0-linux.zip` (sha256 `ceaaa181ab70e201685b1e45260d337d1cbdb0aba1408d4fbc47e232a7e4c987`)
  outside GitHub.
- HTMX 2.0.11 is vendored at `src/projeto_dvd/web/static/htmx.min.js` (source
  `https://unpkg.com/htmx.org@2.0.11/dist/htmx.min.js`, sha256
  `d6fdc75f204e6bdefa99b69bf1e6d4ac69b8a364f77929f45c13476b4000f717`).

## License

[MIT](LICENSE)
