"""Run the media tools: progress from -progress, stderr to the job log, cancel and kill.

stderr goes straight to the log file (never a pipe, which would block the tool once its
buffer fills); only the -progress lines on stdout are read.
"""

import shlex
import subprocess
import threading
from collections.abc import Callable, Iterable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Protocol

STDERR_KEEP = 1_000_000  # bytes of stderr kept in a RunResult
ERROR_TAIL = 2000
CAPTURE_TIMEOUT = 600


class Canceled(Exception):
    """The job was canceled, or the worker is stopping."""


class ToolError(Exception):
    def __init__(self, tool: str, returncode: int, stderr: str) -> None:
        super().__init__(f"{tool} exited with {returncode}")
        self.tool = tool
        self.returncode = returncode
        self.stderr = stderr[-ERROR_TAIL:]


@dataclass(frozen=True)
class RunResult:
    progress: dict[str, str]  # the last -progress block
    stderr: str  # what the tool wrote to stderr in this run


class Tools(Protocol):
    def run(
        self,
        command: list[str],
        *,
        duration: float | None = None,
        on_progress: Callable[[float], None] | None = None,
        stdin: Path | None = None,
        stdout: Path | None = None,
    ) -> RunResult: ...

    def capture(self, command: list[str]) -> str: ...


def parse_progress(lines: Iterable[str]) -> Iterator[dict[str, str]]:
    block: dict[str, str] = {}
    for line in lines:
        key, _, value = line.strip().partition("=")
        if not key:
            continue
        block[key] = value
        if key == "progress":
            yield block
            block = {}


def progress_fraction(block: dict[str, str], duration: float | None) -> float | None:
    if block.get("progress") == "end":
        return 1.0
    microseconds = block.get("out_time_us", "")
    if not duration or not microseconds.isdecimal():
        return None
    return min(1.0, int(microseconds) / 1e6 / duration)


@dataclass
class ProcessRunner:
    log_path: Path
    should_cancel: Callable[[], bool]
    cwd: Path | None = None
    poll_seconds: float = 1.0
    terminate_seconds: float = 3.0

    def run(
        self,
        command: list[str],
        *,
        duration: float | None = None,
        on_progress: Callable[[float], None] | None = None,
        stdin: Path | None = None,
        stdout: Path | None = None,
    ) -> RunResult:
        if self.should_cancel():
            raise Canceled
        blocks: list[dict[str, str]] = []
        with ExitStack() as stack:
            log = stack.enter_context(self.log_path.open("ab"))
            log.write(f"$ {shlex.join(command)}\n".encode())
            log.flush()
            start = log.tell()
            source: IO[bytes] | int = (
                stack.enter_context(stdin.open("rb")) if stdin else subprocess.DEVNULL
            )
            target: IO[bytes] | int = (
                stack.enter_context(stdout.open("wb")) if stdout else subprocess.PIPE
            )
            try:
                process = subprocess.Popen(
                    command, stdin=source, stdout=target, stderr=log, cwd=self.cwd
                )
            except OSError as error:
                raise ToolError(command[0], -1, f"{command[0]} not found: {error}") from error
            reader = None
            if process.stdout is not None:
                reader = threading.Thread(
                    target=self._read, args=(process.stdout, duration, on_progress, blocks),
                    daemon=True,
                )  # fmt: skip
                reader.start()
            try:
                self._wait(process)
            finally:
                if reader is not None:
                    reader.join()
        stderr = self._stderr_since(start)
        if process.returncode != 0:
            raise ToolError(command[0], process.returncode, stderr)
        return RunResult(blocks[-1] if blocks else {}, stderr)

    def capture(self, command: list[str]) -> str:
        with self.log_path.open("ab") as log:
            log.write(f"$ {shlex.join(command)}\n".encode())
            try:
                result = subprocess.run(
                    command, stdin=subprocess.DEVNULL, capture_output=True,
                    timeout=CAPTURE_TIMEOUT, cwd=self.cwd, check=False,
                )  # fmt: skip
            except (OSError, subprocess.TimeoutExpired) as error:
                raise ToolError(command[0], -1, str(error)) from error
            log.write(result.stderr)
        if result.returncode != 0:
            raise ToolError(command[0], result.returncode, result.stderr.decode(errors="replace"))
        return result.stdout.decode(errors="replace")

    def _wait(self, process: subprocess.Popen[bytes]) -> None:
        while True:
            try:
                process.wait(timeout=self.poll_seconds)
                return
            except subprocess.TimeoutExpired:
                pass
            if self.should_cancel():
                # The tools start no children of their own: the process itself is enough.
                process.terminate()
                try:
                    process.wait(timeout=self.terminate_seconds)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise Canceled

    @staticmethod
    def _read(
        stream: IO[bytes],
        duration: float | None,
        on_progress: Callable[[float], None] | None,
        blocks: list[dict[str, str]],
    ) -> None:
        lines = (line.decode(errors="replace") for line in stream)
        for block in parse_progress(lines):
            blocks.append(block)
            fraction = progress_fraction(block, duration)
            if fraction is not None and on_progress is not None:
                on_progress(fraction)

    def _stderr_since(self, start: int) -> str:
        with self.log_path.open("rb") as log:
            log.seek(max(start, log.seek(0, 2) - STDERR_KEEP))
            return log.read().decode(errors="replace")
