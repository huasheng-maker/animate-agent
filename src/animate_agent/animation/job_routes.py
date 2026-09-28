"""Local asynchronous generation API; the existing synchronous API is unchanged."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sse_starlette import EventSourceResponse
from starlette.datastructures import UploadFile

from animate_agent.animation.jobs import TERMINAL, JobManager
from animate_agent.animation.service import generate_animation
from animate_agent.documents.file_parser import SUPPORTED_EXTENSIONS
from animate_agent.paths import RUNS_DIR, SAMPLES_DIR
from animate_agent.sources.models import FileSourceInput, QuerySourceInput, UrlSourceInput

router = APIRouter(prefix="/api/animation-jobs")


class JobInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["url", "query", "example"]
    value: str = Field(min_length=1, max_length=16000)


def manager(request: Request) -> JobManager:
    result: JobManager = request.app.state.animation_jobs
    return result


def snapshot(request: Request, run_id: UUID) -> dict[str, Any]:
    try:
        return manager(request).store.get(run_id.hex)
    except KeyError as exc:
        raise HTTPException(404, "找不到该生成任务") from exc


@router.post("", status_code=202)
async def create_job(request: Request, response: Response) -> dict[str, Any]:
    try:
        job_id = UUID(request.headers.get("Idempotency-Key", "")).hex
    except ValueError as exc:
        raise HTTPException(422, "需要有效的 Idempotency-Key") from exc
    content: bytes | None = None
    ext = ""
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        async with request.form(max_files=1, max_fields=1) as form:
            upload = form.get("file")
            if not isinstance(upload, UploadFile):
                raise HTTPException(422, "请选择文件")
            ext = Path(upload.filename or "").suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                raise HTTPException(422, "不支持的文件格式")
            content = await upload.read(20 * 1024 * 1024 + 1)
            if len(content) > 20 * 1024 * 1024:
                raise HTTPException(413, "文件不能超过 20 MB")
            mode = "file"
            fingerprint = hashlib.sha256(ext.encode() + content).hexdigest()
            source: FileSourceInput | QuerySourceInput | UrlSourceInput = FileSourceInput(
                path=RUNS_DIR / "job-inputs" / f"{job_id}{ext}"
            )
    else:
        try:
            body = JobInput.model_validate(await request.json())
            mode = body.mode
            if mode == "example":
                if body.value != "controller":
                    raise HTTPException(404, "未知示例")
                source = FileSourceInput(path=SAMPLES_DIR / "controller.md")
            elif mode == "query":
                source = QuerySourceInput(query=body.value)
            else:
                source = UrlSourceInput(url=body.value)
            fingerprint = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
        except (ValidationError, json.JSONDecodeError) as exc:
            raise HTTPException(422, "请输入有效的生成来源") from exc
    jobs = manager(request)
    try:
        created = jobs.store.create(job_id, fingerprint, mode)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if created:
        if content is not None and isinstance(source, FileSourceInput):
            try:
                source.path.parent.mkdir(parents=True, exist_ok=True)
                with source.path.open("xb") as output:
                    output.write(content)
            except OSError as exc:
                jobs.store.update(job_id, "failed", status="failed", message="无法保存上传文件")
                raise HTTPException(500, "无法保存上传文件") from exc

        async def run(identity: str) -> Any:
            return await generate_animation(source, job_id=identity)

        jobs.start(job_id, run)
    response.headers["Location"] = f"/api/animation-jobs/{job_id}"
    response.headers["Retry-After"] = "5"
    return jobs.store.get(job_id)


@router.get("/{run_id}")
async def get_job(request: Request, run_id: UUID) -> dict[str, Any]:
    return snapshot(request, run_id)


@router.post("/{run_id}/cancel")
async def cancel_job(request: Request, run_id: UUID) -> dict[str, Any]:
    snapshot(request, run_id)
    return await manager(request).cancel(run_id.hex)


@router.get("/{run_id}/result")
async def get_result(request: Request, run_id: UUID) -> dict[str, Any]:
    state = snapshot(request, run_id)
    if state["status"] != "completed":
        raise HTTPException(409, "动画尚未完成")
    result = manager(request).store.result(run_id.hex)
    if result is None:
        raise HTTPException(404, "结果不存在")
    return result


@router.get("/{run_id}/events")
async def job_events(request: Request, run_id: UUID, after: int = 0) -> EventSourceResponse:
    snapshot(request, run_id)
    try:
        cursor = max(0, after, int(request.headers.get("last-event-id", "0")))
    except ValueError as exc:
        raise HTTPException(422, "无效的事件序号") from exc
    store = manager(request).store

    async def events() -> AsyncIterator[dict[str, str]]:
        nonlocal cursor
        yield {"comment": "connected"}
        heartbeat_at = time.monotonic()
        while True:
            batch = store.events(run_id.hex, cursor)
            for event in batch:
                cursor = event["seq"]
                yield {"id": str(cursor), "data": json.dumps(event, ensure_ascii=False)}
            current = store.get(run_id.hex)
            if current["status"] in TERMINAL and cursor >= current["seq"]:
                return
            if time.monotonic() - heartbeat_at >= 10:
                yield {"event": "heartbeat", "data": json.dumps(current, ensure_ascii=False)}
                heartbeat_at = time.monotonic()
            await asyncio.sleep(0.5)

    return EventSourceResponse(
        events(), ping=10, send_timeout=20, headers={"Cache-Control": "no-store"}
    )
