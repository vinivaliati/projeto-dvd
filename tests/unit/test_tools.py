import subprocess
import sys

import pytest

from projeto_dvd import tools

# First lines of the real output of each tool in the Docker image
# (Debian trixie packages and tsMuxeR 2.7.0), mapped to the expected version.
REAL_OUTPUT: dict[str, tuple[str, str]] = {
    "ffmpeg": (
        "ffmpeg version 7.1.5-0+deb13u1 Copyright (c) 2000-2026 the FFmpeg developers\n"
        "built with gcc 14 (Debian 14.2.0-19)\n",
        "7.1.5-0+deb13u1",
    ),
    "ffprobe": (
        "ffprobe version 7.1.5-0+deb13u1 Copyright (c) 2007-2026 the FFmpeg developers\n"
        "built with gcc 14 (Debian 14.2.0-19)\n",
        "7.1.5-0+deb13u1",
    ),
    "dvdauthor": (
        "DVDAuthor::dvdauthor, version 0.7.2.\n"
        "Build options: gnugetopt iconv freetype fribidi fontconfig\n",
        "0.7.2",
    ),
    "spumux": (
        "DVDAuthor::spumux, version 0.7.2.\n"
        "Build options: gnugetopt iconv freetype fribidi fontconfig\n",
        "0.7.2",
    ),
    "xorriso": (
        "xorriso 1.5.6 : RockRidge filesystem manipulator, libburnia project.\n\nxorriso 1.5.6\n",
        "1.5.6",
    ),
    "tsMuxeR": ("tsMuxeR version 2.7.0. github.com/justdan96/tsMuxer\n", "2.7.0"),
}

# dvdauthor and spumux print their version on stderr and exit with these codes.
STDERR_EXIT_CODES = {"dvdauthor": 1, "spumux": 255}


def completed(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Simulate the real behavior of a tool when asked for its version."""
    tool = command[0]
    text = REAL_OUTPUT[tool][0]
    if tool in STDERR_EXIT_CODES:
        return subprocess.CompletedProcess(command, STDERR_EXIT_CODES[tool], "", text)
    return subprocess.CompletedProcess(command, 0, text, "")


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    tools.detect_versions.cache_clear()


def test_every_tool_has_a_real_output_sample() -> None:
    assert REAL_OUTPUT.keys() == tools.TOOLS.keys()


@pytest.mark.parametrize(("tool", "sample"), REAL_OUTPUT.items())
def test_parse_version_reads_real_output(tool: str, sample: tuple[str, str]) -> None:
    output, expected = sample
    assert tools.parse_version(tool, output) == expected


@pytest.mark.parametrize("tool", REAL_OUTPUT)
@pytest.mark.parametrize("output", ["", "sh: 1: command not found\n"])
def test_parse_version_returns_none_for_unexpected_output(tool: str, output: str) -> None:
    assert tools.parse_version(tool, output) is None


def test_detect_versions_ignores_exit_code_and_reads_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subprocess, "run", lambda command, **_: completed(command))

    assert tools.detect_versions() == {tool: version for tool, (_, version) in REAL_OUTPUT.items()}


@pytest.mark.parametrize(
    "error",
    [FileNotFoundError(), PermissionError(), subprocess.TimeoutExpired("ffmpeg", 10)],
)
def test_detect_versions_marks_tool_missing_on_error(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if command[0] == "ffmpeg":
            raise error
        return completed(command)

    monkeypatch.setattr(subprocess, "run", run)

    versions = tools.detect_versions()
    assert versions["ffmpeg"] is None
    assert versions["ffprobe"] == "7.1.5-0+deb13u1"


def test_detect_versions_runs_without_shell_and_with_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(kwargs)
        return completed(command)

    monkeypatch.setattr(subprocess, "run", run)
    tools.detect_versions()

    assert calls
    assert all(
        call.get("shell") is not True and call["timeout"] == tools.TIMEOUT_SECONDS for call in calls
    )


def test_detect_versions_reads_a_real_process(monkeypatch: pytest.MonkeyPatch) -> None:
    # A real child process that behaves like dvdauthor: version on stderr, exit code 1,
    # plus a byte that is not valid UTF-8.
    fake_dvdauthor = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.buffer.write(b'DVDAuthor::dvdauthor, version 0.7.2.\\n\\xff');"
        " sys.exit(1)",
    ]
    regex = tools.TOOLS["dvdauthor"][1]
    monkeypatch.setattr(tools, "TOOLS", {"dvdauthor": (fake_dvdauthor, regex)})

    assert tools.detect_versions() == {"dvdauthor": "0.7.2"}


def test_detect_versions_runs_each_tool_only_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command[0])
        return completed(command)

    monkeypatch.setattr(subprocess, "run", run)
    tools.detect_versions()
    tools.detect_versions()

    assert sorted(calls) == sorted(tools.TOOLS)
