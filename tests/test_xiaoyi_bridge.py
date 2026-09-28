"""Xiaoyi bridge contract without paid model or external network calls."""

import asyncio
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from animate_agent.rendering.models import RenderScene, RenderSpec


def test_xiaoyi_submit_status_and_existing_player_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import animate_agent.api as api
    from animate_agent.animation import xiaoyi

    monkeypatch.setattr(api, "DEFAULT_RUNS_DIR", tmp_path)
    monkeypatch.setenv("XIAOYI_PLUGIN_TOKEN", "a" * 32)
    monkeypatch.setenv("XIAOYI_PUBLIC_ORIGIN", "https://movie.example")
    calls: list[str] = []

    async def fake_generation(source: Any, *, job_id: str) -> RenderSpec:
        calls.append(source.query)
        await asyncio.sleep(0)
        return RenderSpec(storyboard_id="xiaoyi-test", scenes=[RenderScene(id="scene")])

    monkeypatch.setattr(xiaoyi, "generate_animation", fake_generation)
    identity = str(uuid4())
    headers = {"Authorization": "Bearer " + "a" * 32}

    with TestClient(api.app) as client:
        path = "/api/xiaoyi/jobs"
        body = {"question": "为什么机器人需要绕开障碍？", "request_id": identity}
        assert client.post(path, json=body).status_code == 401
        bad = client.post(path, headers={"Authorization": "Bearer bad"}, json=body)
        assert bad.status_code == 401
        created = client.post(path, headers=headers, json=body)
        assert created.status_code == 200
        job_id = identity.replace("-", "")
        assert created.json()["run_id"] == job_id
        assert created.json()["watch_url"] == f"https://movie.example/xiaoyi/watch/{job_id}"
        assert client.post(path, headers=headers, json=body).json()["run_id"] == job_id
        conflict = client.post(path, headers=headers, json={**body, "question": "different"})
        assert conflict.status_code == 409
        assert client.get(f"{path}/{job_id}").status_code == 401

        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = client.get(f"{path}/{job_id}", headers=headers).json()
            if state["ready"]:
                break
            time.sleep(0.01)
        assert state["status"] == "completed"
        assert calls == [body["question"]]
        result = client.get(f"/api/animation-jobs/{job_id}/result").json()
        assert result["storyboard_id"] == "xiaoyi-test"


def test_xiaoyi_requires_valid_configuration_and_nonblank_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import animate_agent.api as api

    monkeypatch.setattr(api, "DEFAULT_RUNS_DIR", tmp_path)
    monkeypatch.delenv("XIAOYI_PLUGIN_TOKEN", raising=False)
    monkeypatch.setenv("XIAOYI_PUBLIC_ORIGIN", "https://movie.example")
    with TestClient(api.app) as client:
        assert client.post("/api/xiaoyi/jobs", json={"question": "test"}).status_code == 503
        monkeypatch.setenv("XIAOYI_PLUGIN_TOKEN", "a" * 32)
        headers = {"Authorization": "Bearer " + "a" * 32}
        monkeypatch.setenv("XIAOYI_PUBLIC_ORIGIN", "http://movie.example")
        invalid_origin = client.post(
            "/api/xiaoyi/jobs", headers=headers, json={"question": "test"}
        )
        assert invalid_origin.status_code == 503
        monkeypatch.setenv("XIAOYI_PUBLIC_ORIGIN", "https://movie.example")
        blank_question = client.post(
            "/api/xiaoyi/jobs", headers=headers, json={"question": "   "}
        )
        assert blank_question.status_code == 422
        assert client.get(f"/api/xiaoyi/jobs/{uuid4().hex}", headers=headers).status_code == 404


def test_public_demo_blocks_legacy_generation_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import animate_agent.api as api

    monkeypatch.setattr(api, "DEFAULT_RUNS_DIR", tmp_path)
    monkeypatch.setenv("PUBLIC_DEMO_MODE", "1")
    monkeypatch.setenv("XIAOYI_PLUGIN_TOKEN", "a" * 32)
    monkeypatch.setenv("XIAOYI_PUBLIC_ORIGIN", "https://movie.example")
    with TestClient(api.app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/openapi.json").status_code == 403
        assert client.post(
            "/api/animation-jobs", json={"mode": "query", "value": "test"}
        ).status_code == 403
        assert client.post(
            "/api/animations/from-query", json={"query": "test"}
        ).status_code == 403
        assert client.get(f"/api/animation-jobs/{uuid4().hex}").status_code == 404
        assert client.post("/api/xiaoyi/jobs", json={"question": "test"}).status_code == 401
