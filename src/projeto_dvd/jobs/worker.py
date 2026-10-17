"""The worker service: one job at a time, claimed from SQLite, run by the pipeline.

Runs as `python -m projeto_dvd.jobs.worker` in its own compose service (init: true reaps
ffmpeg if anything goes wrong). It never migrates: it waits for the web to do it.
"""

import logging
import math
import signal
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session

from projeto_dvd.config import Settings
from projeto_dvd.db.session import is_migrated, make_engine
from projeto_dvd.jobs import cache, store
from projeto_dvd.jobs.pipeline import (
    CacheUse,
    PipelineError,
    QaFailed,
    Step,
    overall_progress,
    run_pipeline,
    step_text,
)
from projeto_dvd.jobs.runner import Canceled, ProcessRunner, Tools
from projeto_dvd.jobs.store import JobStatus
from projeto_dvd.planner.disc_plan import DiscPlan
from projeto_dvd.tools import detect_versions

RESTARTED = "O worker parou no meio (o WSL ou o PC reiniciou?). Use Retomar."
STOPPED = "O worker foi parado (docker compose stop) no meio da geração. Use Retomar."
UNEXPECTED = "Erro inesperado na geração. Veja os detalhes técnicos no log."
SAVE_EVERY = 1.0
CANCEL_EVERY = 1.0

log = logging.getLogger("projeto_dvd.worker")


def default_tools(job_dir: Path, should_cancel: Callable[[], bool]) -> Tools:
    return ProcessRunner(log_path=job_dir / "job.log", should_cancel=should_cancel, cwd=job_dir)


@dataclass
class Worker:
    engine: Engine
    settings: Settings
    make_tools: Callable[[Path, Callable[[], bool]], Tools] = default_tools
    clock: Callable[[], float] = time.monotonic
    stop: threading.Event = field(default_factory=threading.Event)

    def handle_signal(self, signum: int, frame: object) -> None:
        # Only a flag: the running tool is stopped by the cancel check, then the job is saved.
        self.stop.set()

    def recover(self) -> None:
        """A job left running belongs to a worker that died; a .part file is half a copy."""
        failed = store.fail_interrupted(self.engine, RESTARTED)
        if failed:
            log.warning("marked %d interrupted job(s) as failed", failed)
        for part in (self.settings.output_dir / "iso").glob("*.iso.part"):
            part.unlink()

    def run_once(self) -> bool:
        job_id = store.claim_next(self.engine)
        if job_id is None:
            return False
        with Session(self.engine) as session:
            job = store.get_job(session, job_id)
            assert job is not None
            plan = DiscPlan.model_validate_json(job.plan_json)
        job_dir = self.settings.work_dir / "jobs" / str(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        with (job_dir / "job.log").open("a", encoding="utf-8") as job_log:
            job_log.write(f"[projeto-dvd] Início em {datetime.now(UTC).isoformat()}\n")
        use = self.cache_use()
        keys = cache.plan_keys(plan, use.ffmpeg)
        cache.evict(use.work_dir, use.limit_bytes, keys)
        should_cancel = self._cancel_check(job_id)
        report = self._reporter(job_id, plan)
        try:
            result = run_pipeline(
                plan, media_dir=self.settings.media_dir, job_dir=job_dir,
                output_dir=self.settings.output_dir,
                tools=self.make_tools(job_dir, should_cancel), report=report,
                should_cancel=should_cancel, cache=use,
            )  # fmt: skip
        except Canceled:
            if self.stop.is_set():
                store.finish(self.engine, job_id, JobStatus.FAILED, error=STOPPED)
            else:
                store.finish(self.engine, job_id, JobStatus.CANCELED)
        except QaFailed as error:
            cache.purge(use.work_dir, keys)  # a retry must not reuse the rejected video
            store.finish(self.engine, job_id, JobStatus.FAILED, error=error.message,
                         qa_json=error.report.model_dump_json())  # fmt: skip
        except PipelineError as error:
            store.finish(self.engine, job_id, JobStatus.FAILED, error=error.message)
        except Exception:
            with (job_dir / "job.log").open("a") as job_log:
                job_log.write(traceback.format_exc())
            log.exception("job %d failed unexpectedly", job_id)
            store.finish(self.engine, job_id, JobStatus.FAILED, error=UNEXPECTED)
        else:
            store.finish(self.engine, job_id, JobStatus.DONE, qa_json=result.qa_json,
                         iso_path=str(result.iso_path))  # fmt: skip
        return True

    def cache_use(self) -> CacheUse:
        return CacheUse(
            work_dir=self.settings.work_dir,
            limit_bytes=int(self.settings.cache_limit_gb * 10**9),  # decimal, like the screens
            ffmpeg=detect_versions().get("ffmpeg"),
        )

    def _cancel_check(self, job_id: int) -> Callable[[], bool]:
        last, answer = [-math.inf], [False]

        def should_cancel() -> bool:
            if self.stop.is_set():
                return True
            now = self.clock()
            if now - last[0] >= CANCEL_EVERY:
                last[0] = now
                answer[0] = store.cancel_requested(self.engine, job_id)
            return answer[0]

        return should_cancel

    def _reporter(self, job_id: int, plan: DiscPlan) -> Callable[[Step, float, int], None]:
        last = [-math.inf]

        def report(step: Step, fraction: float, title: int) -> None:
            now = self.clock()
            if fraction >= 1 or now - last[0] >= SAVE_EVERY:
                last[0] = now
                progress = overall_progress(plan, step, fraction, title)
                store.save_progress(self.engine, job_id, step_text(step, title), progress)

        return report


def serve(worker: Worker, engine: Engine, poll_seconds: float = 2.0) -> None:
    while not is_migrated(engine):
        if worker.stop.wait(poll_seconds):
            return
    worker.recover()
    while not worker.stop.is_set():
        if not worker.run_once():
            worker.stop.wait(poll_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("alembic").setLevel(logging.WARNING)  # quiet while waiting for the web
    settings = Settings()
    engine = make_engine(settings.database_url)
    worker = Worker(engine, settings)
    signal.signal(signal.SIGTERM, worker.handle_signal)
    signal.signal(signal.SIGINT, worker.handle_signal)
    log.info("worker started")
    serve(worker, engine)
    engine.dispose()


if __name__ == "__main__":
    main()
