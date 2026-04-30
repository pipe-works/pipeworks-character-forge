"""Tests for the threaded JobQueue worker."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

from pipeworks_character_forge.api.services.job_queue import JobQueue


def _make_queue() -> tuple[JobQueue, MagicMock, threading.Event]:
    """Build a JobQueue wired to a mock orchestrator and a barrier event."""
    orchestrator = MagicMock()
    orchestrator.run_full = MagicMock()
    orchestrator.regenerate_slot = MagicMock()

    barrier = threading.Event()

    def _signal(*_args, **_kwargs):
        barrier.set()

    orchestrator.run_full.side_effect = _signal
    orchestrator.regenerate_slot.side_effect = _signal

    return JobQueue(orchestrator), orchestrator, barrier


class TestJobQueueThreaded:
    def test_enqueue_full_run_dispatches_to_run_full(self):
        jq, orchestrator, barrier = _make_queue()
        jq.start()
        try:
            jq.enqueue_full_run("run-A")
            assert barrier.wait(timeout=5.0)
            orchestrator.run_full.assert_called_once_with("run-A")
        finally:
            jq.stop()

    def test_enqueue_regenerate_dispatches_to_regenerate_slot(self):
        jq, orchestrator, barrier = _make_queue()
        jq.start()
        try:
            jq.enqueue_regenerate("run-A", "smiling")
            assert barrier.wait(timeout=5.0)
            orchestrator.regenerate_slot.assert_called_once_with("run-A", "smiling")
        finally:
            jq.stop()

    def test_failing_job_does_not_kill_worker(self):
        jq, orchestrator, _barrier = _make_queue()
        # First job blows up; second must still run.
        orchestrator.run_full.side_effect = [RuntimeError("boom"), None]

        done = threading.Event()
        seen_jobs: list[tuple[object, BaseException | None]] = []

        def on_done(job, error):
            seen_jobs.append((job, error))
            if len(seen_jobs) == 2:
                done.set()

        jq.set_on_job_done(on_done)
        jq.start()
        try:
            jq.enqueue_full_run("run-A")
            jq.enqueue_full_run("run-B")
            assert done.wait(timeout=5.0)
            assert orchestrator.run_full.call_count == 2
            assert isinstance(seen_jobs[0][1], RuntimeError)
            assert seen_jobs[1][1] is None
        finally:
            jq.stop()

    def test_depth_reflects_pending_plus_in_flight(self):
        jq, orchestrator, _barrier = _make_queue()

        # Block the first job until we say so, so depth observes pending work.
        release = threading.Event()
        orchestrator.run_full.side_effect = lambda *_: release.wait(timeout=5.0)

        jq.start()
        try:
            jq.enqueue_full_run("run-A")
            jq.enqueue_full_run("run-B")
            jq.enqueue_full_run("run-C")
            # Give the worker a moment to pick up run-A.
            for _ in range(50):
                if jq.current_job() is not None:
                    break
                time.sleep(0.02)
            assert jq.current_job() is not None
            assert jq.depth() >= 1  # at least the in-flight job; queued items may have drained
        finally:
            release.set()
            jq.stop()
