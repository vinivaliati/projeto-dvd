"""Detect which media tools are installed and their versions."""

import re
import subprocess
from functools import cache

# Version command and version regex for each tool, measured in the Docker image.
# dvdauthor and spumux have no version flag: their help text carries the version on
# stderr and they exit with 1 and 255, so exit codes are ignored.
TOOLS: dict[str, tuple[list[str], str]] = {
    "ffmpeg": (["ffmpeg", "-version"], r"ffmpeg version (\S+)"),
    "ffprobe": (["ffprobe", "-version"], r"ffprobe version (\S+)"),
    "dvdauthor": (["dvdauthor", "--help"], r"dvdauthor, version (\d+(?:\.\d+)*)"),
    "spumux": (["spumux", "--help"], r"spumux, version (\d+(?:\.\d+)*)"),
    "xorriso": (["xorriso", "-version"], r"^xorriso (\d+(?:\.\d+)*)"),
    "genisoimage": (["genisoimage", "--version"], r"genisoimage (\d+(?:\.\d+)*)"),
    "tsMuxeR": (["tsMuxeR", "--version"], r"tsMuxeR version (\d+(?:\.\d+)*)"),
}

TIMEOUT_SECONDS = 10


def parse_version(tool: str, output: str) -> str | None:
    """Extract the version of `tool` from its output, or None if it is not there."""
    match = re.search(TOOLS[tool][1], output)
    return match.group(1) if match else None


def _run(command: list[str]) -> str | None:
    """Return stdout and stderr together, or None if the tool cannot run."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout + result.stderr


@cache
def detect_versions() -> dict[str, str | None]:
    """Return the version of each media tool, or None when it is missing or unrecognized.

    Cached because versions cannot change while the process runs, and the container
    healthcheck calls this repeatedly.
    """
    versions: dict[str, str | None] = {}
    for tool, (command, _) in TOOLS.items():
        output = _run(command)
        versions[tool] = None if output is None else parse_version(tool, output)
    return versions
