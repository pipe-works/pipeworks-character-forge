"""Single-worker FIFO job queue.

The GPU is the bottleneck — only one i2i can run at a time — so the API
routers enqueue work here rather than running it inline. The worker
thread pulls jobs off the queue and dispatches them to the
orchestrator. Cancellation is best-effort: an in-flight i2i call
finishes before the worker checks the stop event.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass

from pipeworks_character_forge.api.services.pipeline_orchestrator import (
    PipelineOrchestrator,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _FullRunJob:
    run_id: str


@dataclass(frozen=True)
class _RegenJob:
    run_id: str
    slot_id: str


@dataclass(frozen=True)
class _CascadeJob:
    run_id: str


_Job = _FullRunJob | _RegenJob | _CascadeJob


class JobQueue:
    """FIFO job dispatcher backed by a single worker thread."""

    def __init__(self, orchestrator: PipelineOrchestrator) -> None:
        self._orchestrator = orchestrator
        self._queue: queue.Queue[_Job | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._current: _Job | None = None
        self._on_job_done: Callable[[_Job, BaseException | None], None] | None = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True, name="pw-forge-jobs")
        self._thread.start()
        logger.info("JobQueue worker started")

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._thread = None
        logger.info("JobQueue worker stopped")

    # -- enqueue -----------------------------------------------------------

    def enqueue_full_run(self, run_id: str) -> None:
        self._queue.put(_FullRunJob(run_id=run_id))

    def enqueue_regenerate(self, run_id: str, slot_id: str) -> None:
        self._queue.put(_RegenJob(run_id=run_id, slot_id=slot_id))

    def enqueue_cascade(self, run_id: str) -> None:
        self._queue.put(_CascadeJob(run_id=run_id))

    # -- introspection -----------------------------------------------------

    def depth(self) -> int:
        """Approximate queue depth, including the in-flight job if any."""
        pending = self._queue.qsize()
        return pending + (1 if self._current is not None else 0)

    def current_job(self) -> _Job | None:
        return self._current

    def set_on_job_done(
        self, callback: Callable[[_Job, BaseException | None], None] | None
    ) -> None:
        """Optional hook for tests / SSE plumbing. Called after each job."""
        self._on_job_done = callback

    # -- worker ------------------------------------------------------------

    def _worker(self) -> None:
        while not self._stop.is_set():
            job = self._queue.get()
            if job is None:
                self._queue.task_done()
                break
            self._current = job
            error: BaseException | None = None
            try:
                if isinstance(job, _FullRunJob):
                    self._orchestrator.run_full(job.run_id)
                elif isinstance(job, _RegenJob):
                    self._orchestrator.regenerate_slot(job.run_id, job.slot_id)
                elif isinstance(job, _CascadeJob):
                    self._orchestrator.cascade_from_base(job.run_id)
            except BaseException as exc:  # noqa: BLE001 — log + continue
                logger.exception("Job failed: %r", job)
                error = exc
            finally:
                self._current = None
                self._queue.task_done()
                if self._on_job_done is not None:
                    try:
                        self._on_job_done(job, error)
                    except Exception:
                        logger.exception("on_job_done callback raised")
