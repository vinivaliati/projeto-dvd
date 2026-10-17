import os
import signal
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from projeto_dvd.authoring.dvd.qa import Check, QaReport
from projeto_dvd.config import Settings
from projeto_dvd.jobs import cache, store, worker
from projeto_dvd.jobs.pipeline import PipelineError, PipelineResult, QaFailed, Step
from projeto_dvd.jobs.runner import Canceled, ProcessRunner
from projeto_dvd.jobs.worker import Worker
from tests.plans import make_movie
from tests.tree import make_file


@pytest.fixture
def settings(tmp_path: Path, database_url: str) -> Settings:
    return Settings(media_dir=tmp_path / "media", work_dir=tmp_path / "work",
                    output_dir=tmp_path / "out", database_url=database_url)  # fmt: skip


def make_worker(engine: Engine, settings: Settings, clock: list[float] | None = None) -> Worker:
    ticks = clock if clock is not None else [0.0]
    return Worker(engine, settings, make_tools=lambda job_dir, cancel: object(),  # type: ignore[arg-type, return-value]
                  clock=lambda: ticks[0])  # fmt: skip


def job(engine: Engine, job_id: int) -> Any:
    with Session(engine) as session:
        return store.get_job(session, job_id)


def queue(session: Session, folder: str = "Filme") -> int:
    return store.enqueue(session, make_movie(folder=folder))


def fake_pipeline(monkeypatch: pytest.MonkeyPatch,
                  behaviour: Callable[..., PipelineResult]) -> list[dict[str, Any]]:  # fmt: skip
    calls: list[dict[str, Any]] = []

    def run(plan: Any, **kwargs: Any) -> PipelineResult:
        calls.append({"plan": plan, **kwargs})
        return behaviour(plan, **kwargs)

    monkeypatch.setattr(worker, "run_pipeline", run)
    return calls


def test_idle_worker_returns_false(engine: Engine, settings: Settings) -> None:
    assert make_worker(engine, settings).run_once() is False


def test_done_job_keeps_the_iso_path_and_qa(engine: Engine, session: Session,
                                            settings: Settings,
                                            monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    job_id = queue(session)
    calls = fake_pipeline(monkeypatch, lambda plan, **kw: PipelineResult(
        iso_path=settings.output_dir / "iso" / "Filme.iso", qa_json='{"ok": 1}'))  # fmt: skip

    assert make_worker(engine, settings).run_once() is True

    done = job(engine, job_id)
    assert (done.status, done.iso_path, done.qa_json) == (
        "done",
        str(settings.output_dir / "iso" / "Filme.iso"),
        '{"ok": 1}',
    )
    assert calls[0]["job_dir"] == settings.work_dir / "jobs" / str(job_id)
    assert calls[0]["plan"] == make_movie()


def test_progress_is_saved_at_most_once_a_second(
    engine: Engine, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = queue(session)
    clock = [0.0]
    seen: list[float] = []

    def behaviour(plan: Any, report: Any, **kwargs: Any) -> PipelineResult:
        report(Step.VIDEO_PASS1, 0.1, 1)
        seen.append(job(engine, job_id).progress)
        report(Step.VIDEO_PASS1, 0.2, 1)  # same second: not saved
        seen.append(job(engine, job_id).progress)
        clock[0] = 1.5
        report(Step.VIDEO_PASS1, 0.3, 1)
        seen.append(job(engine, job_id).progress)
        return PipelineResult(iso_path=Path("/x.iso"), qa_json=None)

    fake_pipeline(monkeypatch, behaviour)
    make_worker(engine, settings, clock).run_once()

    assert seen == pytest.approx([0.1 * 35 / 103, 0.1 * 35 / 103, 0.3 * 35 / 103])
    assert job(engine, job_id).step == "1:video_pass1"


@pytest.mark.parametrize(
    ("error", "status", "message"),
    [
        (PipelineError("Falhou na etapa Áudio.", Step.AUDIO), "failed", "Falhou na etapa Áudio."),
        (RuntimeError("boom"), "failed", worker.UNEXPECTED),
    ],
)
def test_failures(engine: Engine, session: Session, settings: Settings,
                  monkeypatch: pytest.MonkeyPatch, error: Exception, status: str,
                  message: str) -> None:  # fmt: skip
    job_id = queue(session)

    def behaviour(plan: Any, **kwargs: Any) -> PipelineResult:
        raise error

    fake_pipeline(monkeypatch, behaviour)
    make_worker(engine, settings).run_once()

    failed = job(engine, job_id)
    assert (failed.status, failed.error) == (status, message)
    log = settings.work_dir / "jobs" / str(job_id) / "job.log"
    if isinstance(error, RuntimeError):
        assert "Traceback" in log.read_text()


def test_qa_failure_keeps_the_report(engine: Engine, session: Session, settings: Settings,
                                     monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    job_id = queue(session)
    report = QaReport(checks=(Check(name="sync", label="Áudio sincronizado", ok=False),),
                      iso_bytes=1, estimated_bytes=1)  # fmt: skip

    def behaviour(plan: Any, **kwargs: Any) -> PipelineResult:
        raise QaFailed(report)

    fake_pipeline(monkeypatch, behaviour)
    make_worker(engine, settings).run_once()

    failed = job(engine, job_id)
    assert failed.status == "failed" and "Áudio sincronizado" in failed.error
    assert QaReport.model_validate_json(failed.qa_json) == report


def test_cancel_requested_by_the_user(engine: Engine, session: Session, settings: Settings,
                                      monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    job_id = queue(session)

    def behaviour(plan: Any, should_cancel: Any, **kwargs: Any) -> PipelineResult:
        store.request_cancel(engine, job_id)
        assert should_cancel()
        raise Canceled

    fake_pipeline(monkeypatch, behaviour)
    make_worker(engine, settings).run_once()

    assert job(engine, job_id).status == "canceled"


def test_sigterm_fails_the_running_job(engine: Engine, session: Session, settings: Settings,
                                       monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    job_id = queue(session)
    instance = make_worker(engine, settings)

    def behaviour(plan: Any, should_cancel: Any, **kwargs: Any) -> PipelineResult:
        instance.handle_signal(signal.SIGTERM, None)
        assert should_cancel()
        raise Canceled

    fake_pipeline(monkeypatch, behaviour)
    instance.run_once()

    failed = job(engine, job_id)
    assert (failed.status, failed.error) == ("failed", worker.STOPPED)


def test_recover_fails_running_jobs_and_removes_partial_isos(
    engine: Engine, session: Session, settings: Settings
) -> None:
    job_id = queue(session)
    store.claim_next(engine)
    make_file(settings.output_dir / "iso" / "Filme.iso.part")
    make_file(settings.output_dir / "iso" / "Outro.iso")

    make_worker(engine, settings).recover()

    assert (job(engine, job_id).status, job(engine, job_id).error) == ("failed", worker.RESTARTED)
    assert sorted(p.name for p in (settings.output_dir / "iso").iterdir()) == ["Outro.iso"]


def test_serve_waits_for_migrations_then_runs_until_stopped(
    engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = make_worker(engine, settings)
    answers = iter([False, True])
    monkeypatch.setattr(worker, "is_migrated", lambda engine: next(answers))
    runs: list[int] = []

    def run_once() -> bool:
        runs.append(1)
        if len(runs) == 3:  # recover, then two idle rounds
            instance.stop.set()
        return False

    monkeypatch.setattr(instance, "run_once", run_once)
    monkeypatch.setattr(instance, "recover", lambda: runs.append(0))

    worker.serve(instance, engine, poll_seconds=0.0)

    assert runs == [0, 1, 1]


def test_main_wires_signals_and_serves(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'db.sqlite'}")
    handlers: dict[int, Any] = {}
    monkeypatch.setattr(signal, "signal", lambda sig, handler: handlers.update({sig: handler}))
    served: list[Worker] = []
    monkeypatch.setattr(worker, "serve", lambda instance, engine: served.append(instance))

    worker.main()

    assert set(handlers) == {signal.SIGTERM, signal.SIGINT}
    assert len(served) == 1


def test_default_tools_log_into_the_job_folder(tmp_path: Path) -> None:
    tools = worker.default_tools(tmp_path, lambda: False)

    assert isinstance(tools, ProcessRunner)
    assert tools.log_path == tmp_path / "job.log"


def test_recover_with_nothing_to_do(engine: Engine, settings: Settings) -> None:
    make_worker(engine, settings).recover()  # no output folder, no running job: no error


def test_cancel_is_asked_to_the_database_at_most_once_a_second(
    engine: Engine, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = queue(session)
    asked: list[int] = []

    def cancel_requested(engine: Engine, job: int) -> bool:
        asked.append(job)
        return False

    monkeypatch.setattr(store, "cancel_requested", cancel_requested)

    def behaviour(plan: Any, should_cancel: Any, **kwargs: Any) -> PipelineResult:
        assert not should_cancel() and not should_cancel()
        return PipelineResult(iso_path=Path("/x.iso"), qa_json=None)

    fake_pipeline(monkeypatch, behaviour)
    make_worker(engine, settings).run_once()

    assert asked == [job_id]


def test_serve_stops_while_waiting_for_migrations(
    engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = make_worker(engine, settings)
    instance.stop.set()
    monkeypatch.setattr(worker, "is_migrated", lambda engine: False)
    monkeypatch.setattr(instance, "recover", lambda: pytest.fail("must not recover"))

    worker.serve(instance, engine, poll_seconds=0.0)


def test_serve_keeps_going_while_there_are_jobs(
    engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = make_worker(engine, settings)
    monkeypatch.setattr(worker, "is_migrated", lambda engine: True)
    results = iter([True, True, False])
    calls: list[bool] = []

    def run_once() -> bool:
        result = next(results)
        calls.append(result)
        if not result:
            instance.stop.set()
        return result

    monkeypatch.setattr(instance, "run_once", run_once)

    worker.serve(instance, engine, poll_seconds=0.0)

    assert calls == [True, True, False]


def test_the_worker_passes_the_cache_and_notes_the_start(
    engine: Engine, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = queue(session)
    monkeypatch.setattr(worker, "detect_versions", lambda: {"ffmpeg": "7.1"})
    calls = fake_pipeline(monkeypatch, lambda plan, **kw: PipelineResult(
        iso_path=settings.output_dir / "iso" / "Filme.iso", qa_json=None))  # fmt: skip

    make_worker(engine, settings).run_once()

    use = calls[0]["cache"]
    assert (use.work_dir, use.limit_bytes, use.ffmpeg) == (settings.work_dir, 50 * 10**9, "7.1")
    log = (settings.work_dir / "jobs" / str(job_id) / "job.log").read_text()
    assert "[projeto-dvd] Início em " in log


def cache_entry(work_dir: Path, key: str, age: int) -> Path:
    video = make_file(work_dir / "cache" / f"{key}.m2v", b"x" * 10)
    make_file(work_dir / "cache" / f"{key}.json", b'{"size": 10, "progress": {}}')
    os.utime(video, (age, age))
    return video


def test_the_worker_trims_the_cache_before_a_job(
    engine: Engine, session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    database_url: str,
) -> None:  # fmt: skip
    settings = Settings(media_dir=tmp_path / "media", work_dir=tmp_path / "work",
                        output_dir=tmp_path / "out", database_url=database_url,
                        cache_limit_gb=0)  # fmt: skip
    old = cache_entry(settings.work_dir, "0" * 64, 1)
    queue(session)
    fake_pipeline(monkeypatch, lambda plan, **kw: PipelineResult(
        iso_path=settings.output_dir / "iso" / "Filme.iso", qa_json=None))  # fmt: skip

    make_worker(engine, settings).run_once()

    assert not old.exists()


def test_a_failed_qa_forgets_the_cached_video(
    engine: Engine, session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue(session)
    monkeypatch.setattr(worker, "detect_versions", lambda: {"ffmpeg": "7.1"})
    keys = cache.plan_keys(make_movie(), "7.1")
    video = cache_entry(settings.work_dir, keys[0], 100)
    other = cache_entry(settings.work_dir, "f" * 64, 100)
    report = QaReport(checks=(Check(name="gop", label="GOP", ok=False),), iso_bytes=1,
                      estimated_bytes=1)  # fmt: skip

    def behaviour(plan: Any, **kwargs: Any) -> PipelineResult:
        raise QaFailed(report)

    fake_pipeline(monkeypatch, behaviour)
    make_worker(engine, settings).run_once()

    assert not video.exists() and other.exists()


def test_the_messages_point_to_resume() -> None:
    assert "Retomar" in worker.RESTARTED and "Retomar" in worker.STOPPED
