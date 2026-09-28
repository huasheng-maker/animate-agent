"""Job lifecycle, durable replay and API tests without model/network calls."""

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from animate_agent.animation.jobs import JobManager, JobStore
from animate_agent.animation.progress import report_progress
from animate_agent.rendering.models import RenderScene, RenderSpec


def test_store_replay_idempotency_restart(tmp_path: Path) -> None:
    path = tmp_path / "jobs.sqlite3"
    store = JobStore(path)
    assert store.create("one", "input", "query")
    assert not store.create("one", "input", "query")
    with pytest.raises(ValueError):
        store.create("one", "changed-input", "query")
    store.update("one", "stage", status="running", stage="source_ingestion")
    store.update("one", "artifact", artifacts={"document": {"title": "Real evidence"}})
    assert [event["seq"] for event in store.events("one", 1)] == [2, 3]
    restored = JobStore(path)
    restored.interrupt_unfinished()
    state = restored.get("one")
    assert state["status"] == "interrupted"
    assert state["artifacts"]["document"]["title"] == "Real evidence"
    restored.update("one", "completed", status="completed")
    assert restored.get("one") == state  # terminal states cannot be overwritten


def test_manager_cancel_failure_queue_and_success(tmp_path: Path) -> None:
    async def exercise() -> None:
        store = JobStore(tmp_path / "jobs.sqlite3")
        jobs = JobManager(store)
        entered = asyncio.Event()

        async def pending(_: str) -> RenderSpec:
            report_progress("stage", stage="source_ingestion")
            report_progress(
                "artifact",
                name="document",
                stage="source_ingestion",
                value={"title": "Read before cancellation"},
            )
            entered.set()
            await asyncio.Event().wait()
            raise AssertionError("cancel must stop work")

        for identity in ("one", "two", "queued"):
            store.create(identity, identity, "query")
            jobs.start(identity, pending)
        await entered.wait()
        await asyncio.sleep(0)
        assert store.get("queued")["status"] == "queued"
        await jobs.cancel("queued")
        await jobs.cancel("one")
        await asyncio.sleep(0)
        assert store.result("one") is None
        assert store.get("one")["artifacts"]["document"]["title"]
        assert store.get("queued")["status"] == "cancelled"

        async def success(_: str) -> RenderSpec:
            report_progress("model_call")
            report_progress("retry")
            return RenderSpec(storyboard_id="done", scenes=[RenderScene(id="scene")])

        store.create("success", "success", "query")
        jobs.start("success", success)
        await jobs.tasks["success"]
        assert store.get("success")["status"] == "completed"
        assert store.get("success")["calls"] == 1
        assert store.result("success")["storyboard_id"] == "done"  # type: ignore[index]

        async def fail(_: str) -> RenderSpec:
            raise ValueError("secret-provider-payload")

        store.create("fail", "fail", "query")
        jobs.start("fail", fail)
        await jobs.tasks["fail"]
        assert store.get("fail")["status"] == "failed"
        assert "secret-provider-payload" not in json.dumps(store.get("fail"))
        await jobs.close()
        assert store.get("two")["status"] == "interrupted"

    asyncio.run(exercise())


def test_api_background_replay_result_and_duplicate_submission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import animate_agent.api as api
    from animate_agent.animation import job_routes

    monkeypatch.setattr(api, "DEFAULT_RUNS_DIR", tmp_path)
    release = threading.Event()
    calls: list[str] = []

    async def generate(source: Any, *, job_id: str) -> RenderSpec:
        calls.append(job_id)
        report_progress("stage", stage="source_ingestion")
        report_progress(
            "artifact",
            name="document",
            stage="source_ingestion",
            value={"document_id": "real", "title": "Actual content", "sections": []},
        )
        while not release.is_set():
            await asyncio.sleep(0.01)
        return RenderSpec(storyboard_id="result", scenes=[RenderScene(id="scene")])

    monkeypatch.setattr(job_routes, "generate_animation", generate)
    identity = uuid4().hex
    with TestClient(api.app) as client:
        options = {
            "headers": {"Idempotency-Key": identity},
            "json": {"mode": "query", "value": "explain feedback"},
        }
        response = client.post("/api/animation-jobs", **options)
        assert response.status_code == 202
        assert client.post("/api/animation-jobs", **options).json()["run_id"] == identity
        state = client.get(f"/api/animation-jobs/{identity}").json()
        assert state["status"] == "running"
        assert state["artifacts"]["document"]["title"] == "Actual content"
        assert client.get(f"/api/animation-jobs/{identity}/result").status_code == 409
        release.set()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = client.get(f"/api/animation-jobs/{identity}").json()
            if state["status"] == "completed":
                break
            time.sleep(0.01)
        assert state["status"] == "completed"
        assert calls == [identity]
        assert (
            client.get(f"/api/animation-jobs/{identity}/result").json()["storyboard_id"] == "result"
        )
        replay = client.get(
            f"/api/animation-jobs/{identity}/events", headers={"Last-Event-ID": "2"}
        )
        events = [
            json.loads(line[6:]) for line in replay.text.splitlines() if line.startswith("data: ")
        ]
        assert events and all(event["seq"] > 2 for event in events)
        assert events[-1]["status"] == "completed"
        assert client.post(f"/api/animation-jobs/{identity}/cancel").json()["status"] == "completed"
        assert client.get(f"/api/animation-jobs/{uuid4().hex}").status_code == 404
        assert (
            client.post("/api/animation-jobs", json={"mode": "query", "value": "x"}).status_code
            == 422
        )


def test_job_upload_validates_and_retains_input_for_background_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import animate_agent.api as api
    from animate_agent.animation import job_routes

    monkeypatch.setattr(api, "DEFAULT_RUNS_DIR", tmp_path)
    monkeypatch.setattr(job_routes, "RUNS_DIR", tmp_path)
    contents: list[str] = []

    async def generate(source: Any, *, job_id: str) -> RenderSpec:
        contents.append(source.path.read_text())
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    monkeypatch.setattr(job_routes, "generate_animation", generate)
    with TestClient(api.app) as client:
        identity = uuid4().hex
        for _ in range(2):
            response = client.post(
                "/api/animation-jobs",
                headers={"Idempotency-Key": identity},
                files={"file": ("notes.txt", b"evidence")},
            )
            assert response.status_code == 202
        assert contents == ["evidence"]
        assert client.post(f"/api/animation-jobs/{identity}/cancel").json()["status"] == "cancelled"
        assert (
            client.post(
                "/api/animation-jobs",
                headers={"Idempotency-Key": uuid4().hex},
                files={"file": ("payload.exe", b"bad")},
            ).status_code
            == 422
        )
