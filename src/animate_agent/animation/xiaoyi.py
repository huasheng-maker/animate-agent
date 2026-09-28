"""Small, authenticated cloud-plugin bridge to the existing animation jobs."""

from __future__ import annotations

import hashlib
import os
import secrets
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from animate_agent.animation import job_routes
from animate_agent.animation.service import generate_animation
from animate_agent.rendering.models import RenderSpec
from animate_agent.sources.models import QuerySourceInput

router = APIRouter(prefix="/api/xiaoyi", tags=["xiaoyi"])


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=500)
    request_id: UUID | None = None


def _configuration(authorization: str | None) -> str:
    token = os.environ.get("XIAOYI_PLUGIN_TOKEN", "")
    origin = os.environ.get("XIAOYI_PUBLIC_ORIGIN", "").rstrip("/")
    parsed = urlsplit(origin)
    local = parsed.hostname in {"localhost", "127.0.0.1"}
    if (
        len(token) < 32
        or not parsed.hostname
        or parsed.scheme not in ({"http", "https"} if local else {"https"})
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(503, "小艺接入尚未配置")
    if not authorization or not secrets.compare_digest(authorization, f"Bearer {token}"):
        raise HTTPException(401, "小艺插件认证失败", headers={"WWW-Authenticate": "Bearer"})
    return origin


def _reply(state: dict[str, object], origin: str) -> dict[str, object]:
    job_id = str(state["run_id"])
    status = str(state["status"])
    return {
        "run_id": job_id,
        "status": status,
        "stage": state["stage"],
        "message": state["message"],
        "ready": status == "completed",
        "watch_url": f"{origin}/xiaoyi/watch/{job_id}",
    }


@router.post("/jobs")
async def start_job(
    body: StartRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    origin = _configuration(authorization)
    question = body.question.strip()
    if not question:
        raise HTTPException(422, "请输入要讲解的问题")
    job_id = (body.request_id or uuid4()).hex
    payload = job_routes.JobInput(mode="query", value=question)
    fingerprint = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
    jobs = job_routes.manager(request)
    try:
        created = jobs.store.create(job_id, fingerprint, "query")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if created:
        source = QuerySourceInput(query=question)

        async def run(identity: str) -> RenderSpec:
            return await generate_animation(source, job_id=identity)

        jobs.start(job_id, run)
    return _reply(jobs.store.get(job_id), origin)


@router.get("/jobs/{run_id}")
async def job_status(
    run_id: UUID,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    origin = _configuration(authorization)
    return _reply(job_routes.snapshot(request, run_id), origin)
