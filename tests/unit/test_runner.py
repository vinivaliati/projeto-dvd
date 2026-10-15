import os
import sys
import time
from pathlib import Path

import pytest

from projeto_dvd.jobs.runner import (
    Canceled,
    ProcessRunner,
    ToolError,
    parse_progress,
    progress_fraction,
)

PY = sys.executable


def runner(tmp_path: Path, cancel: list[bool] | None = None) -> ProcessRunner:
    flag = cancel if cancel is not None else [False]
    return ProcessRunner(log_path=tmp_path / "job.log", should_cancel=lambda: flag[0],
                         cwd=tmp_path, poll_seconds=0.05, terminate_seconds=0.5)  # fmt: skip


def test_parse_progress_blocks() -> None:
    lines = ["frame=10\n", "out_time_us=N/A\n", "progress=continue\n",
             "out_time_us=5000000\n", "dup_frames=0\n", "progress=end\n"]  # fmt: skip

    blocks = list(parse_progress(lines))

    assert blocks == [
        {"frame": "10", "out_time_us": "N/A", "progress": "continue"},
        {"out_time_us": "5000000", "dup_frames": "0", "progress": "end"},
    ]


@pytest.mark.parametrize(
    ("block", "duration", "fraction"),
    [
        ({"out_time_us": "5000000", "progress": "continue"}, 10.0, 0.5),
        ({"out_time_us": "N/A", "progress": "continue"}, 10.0, None),
        ({"out_time_us": "20000000", "progress": "continue"}, 10.0, 1.0),
        ({"progress": "end"}, 10.0, 1.0),
        ({"out_time_us": "5000000", "progress": "continue"}, None, None),
    ],
)
def test_progress_fraction(block: dict[str, str], duration: float | None,
                           fraction: float | None) -> None:  # fmt: skip
    assert progress_fraction(block, duration) == fraction


def test_run_reports_progress_and_returns_the_last_block(tmp_path: Path) -> None:
    script = "print('out_time_us=1000000\\nprogress=continue\\nout_time_us=2000000\\n" \
             "dup_frames=0\\nprogress=end', flush=True)"  # fmt: skip
    seen: list[float] = []

    result = runner(tmp_path).run([PY, "-c", script], duration=2.0, on_progress=seen.append)

    assert seen == [0.5, 1.0]
    assert result.progress["dup_frames"] == "0"


def test_stderr_goes_to_the_log_and_never_blocks(tmp_path: Path) -> None:
    script = "import sys; sys.stderr.write('x' * 5_000_000 + '\\nbuffer underflow\\n')"

    result = runner(tmp_path).run([PY, "-c", script])

    assert "buffer underflow" in result.stderr
    log = (tmp_path / "job.log").read_text()
    assert log.startswith("$ ") and "buffer underflow" in log


def test_failing_tool_raises_with_the_stderr_tail(tmp_path: Path) -> None:
    script = "import sys; sys.stderr.write('No space left on device\\n'); sys.exit(3)"

    with pytest.raises(ToolError) as caught:
        runner(tmp_path).run([PY, "-c", script])

    assert caught.value.returncode == 3
    assert "No space left" in caught.value.stderr


def test_cancel_terminates_the_process(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    script = f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); " \
             "time.sleep(60)"  # fmt: skip
    cancel = [False]
    run = runner(tmp_path, cancel)

    def cancel_when_started() -> bool:
        cancel[0] = pid_file.exists()
        return cancel[0]

    run.should_cancel = cancel_when_started
    with pytest.raises(Canceled):
        run.run([PY, "-c", script])

    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


def test_cancel_kills_a_process_that_ignores_sigterm(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    script = ("import os, signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
              f"open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep(60)")  # fmt: skip
    run = runner(tmp_path)
    run.should_cancel = pid_file.exists
    started = time.monotonic()

    with pytest.raises(Canceled):
        run.run([PY, "-c", script])

    assert time.monotonic() - started < 10
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


def test_canceled_before_start_runs_nothing(tmp_path: Path) -> None:
    with pytest.raises(Canceled):
        runner(tmp_path, [True]).run([PY, "-c", "open('ran', 'w')"])

    assert not (tmp_path / "ran").exists()


def test_stdin_and_stdout_files(tmp_path: Path) -> None:
    (tmp_path / "in.txt").write_text("hello")
    script = "import sys; sys.stdout.write(sys.stdin.read().upper())"

    runner(tmp_path).run([PY, "-c", script], stdin=tmp_path / "in.txt",
                         stdout=tmp_path / "out.txt")  # fmt: skip

    assert (tmp_path / "out.txt").read_text() == "HELLO"


def test_capture_returns_stdout(tmp_path: Path) -> None:
    assert runner(tmp_path).capture([PY, "-c", "print('0.055')"]).strip() == "0.055"


def test_capture_failure_raises(tmp_path: Path) -> None:
    with pytest.raises(ToolError):
        runner(tmp_path).capture([PY, "-c", "import sys; sys.exit(1)"])


def test_missing_tool_is_a_tool_error(tmp_path: Path) -> None:
    with pytest.raises(ToolError) as caught:
        runner(tmp_path).run(["/nonexistent/tool"])

    assert "not found" in caught.value.stderr


def test_blank_progress_lines_are_skipped() -> None:
    assert list(parse_progress(["\n", "frame=1\n", "progress=end\n"])) == [
        {"frame": "1", "progress": "end"}
    ]


def test_capture_of_a_missing_tool_is_a_tool_error(tmp_path: Path) -> None:
    with pytest.raises(ToolError):
        runner(tmp_path).capture(["/nonexistent/tool"])


def test_slow_tool_is_polled_until_it_ends(tmp_path: Path) -> None:
    script = "import time; time.sleep(0.3); print('progress=end', flush=True)"

    result = runner(tmp_path).run([PY, "-c", script])

    assert result.progress == {"progress": "end"}
