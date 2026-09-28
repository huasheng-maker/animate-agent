"""FastAPI entrypoint for the first Animate Agent vertical slice."""

import os
import re
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AnyHttpUrl, BaseModel, ConfigDict
from starlette.responses import JSONResponse

from animate_agent.animation.artifacts import DEFAULT_RUNS_DIR
from animate_agent.animation.job_routes import router as jobs_router
from animate_agent.animation.jobs import JobManager, JobStore
from animate_agent.animation.service import generate_animation, generate_animation_from_url
from animate_agent.animation.xiaoyi import router as xiaoyi_router
from animate_agent.animation_ir.compiler import compile_storyboard_render_spec
from animate_agent.documents.file_parser import SUPPORTED_EXTENSIONS
from animate_agent.documents.models import DocumentIR
from animate_agent.documents.service import ingest_file, ingest_source, ingest_url
from animate_agent.ingestion.exceptions import (
    BlockedAddress,
    ContentTooLarge,
    CrawlTimeout,
    IngestionError,
    InvalidURL,
    RobotsDenied,
    UnsupportedScheme,
)
from animate_agent.knowledge.models import LessonIR
from animate_agent.knowledge.service import generate_lesson
from animate_agent.llm import MissingLLMKeyError
from animate_agent.paths import SAMPLES_DIR, STORYBOARD_SAMPLES_DIR
from animate_agent.rendering.models import RenderSpec
from animate_agent.sources.adapters import FileAdapter
from animate_agent.sources.models import FileSourceInput, QuerySourceInput
from animate_agent.storyboard.models import StoryboardIR
from animate_agent.storyboard.service import build_limits
from animate_agent.storyboard.validation import validate_storyboard

ALLOWED_EXTENSIONS = SUPPORTED_EXTENSIONS
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
EXAMPLE_DOCUMENTS = {
    "controller": SAMPLES_DIR / "controller.md",
}
EXAMPLE_STORYBOARDS = {
    "controller": STORYBOARD_SAMPLES_DIR / "controller.json",
}


class FromUrlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: AnyHttpUrl


class FromQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str


class FromExampleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    example_id: str


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    jobs = JobManager(JobStore(DEFAULT_RUNS_DIR / "jobs.sqlite3"))
    jobs.store.interrupt_unfinished()
    application.state.animation_jobs = jobs
    try:
        yield
    finally:
        await jobs.close()


app = FastAPI(title="Animate Agent API", version="0.1.0", lifespan=lifespan)
app.include_router(jobs_router)
app.include_router(xiaoyi_router)


@app.middleware("http")
async def restrict_public_demo(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Keep legacy development endpoints off the public demo service."""
    if os.environ.get("PUBLIC_DEMO_MODE") == "1":
        path = request.url.path
        method = request.method
        allowed = (
            (method == "GET" and path == "/health")
            or (method == "POST" and path == "/api/xiaoyi/jobs")
            or (method == "GET" and re.fullmatch(r"/api/xiaoyi/jobs/[a-fA-F0-9-]{32,36}", path))
            or (
                method == "GET"
                and re.fullmatch(
                    r"/api/animation-jobs/[a-fA-F0-9-]{32,36}(?:/result)?", path
                )
            )
        )
        if not allowed:
            return JSONResponse({"detail": "Public demo route unavailable"}, status_code=403)
    return await call_next(request)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"http://(?:localhost|127\.0\.0\.1)(?::\d+)?",
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


def _ingestion_http_error(exc: IngestionError) -> HTTPException:
    if isinstance(exc, (InvalidURL, UnsupportedScheme)):
        status_code = 422
    elif isinstance(exc, (BlockedAddress, RobotsDenied)):
        status_code = 403
    elif isinstance(exc, ContentTooLarge):
        status_code = 413
    elif isinstance(exc, CrawlTimeout):
        status_code = 504
    else:
        status_code = 502
    return HTTPException(status_code=status_code, detail=str(exc))


def _example_path(paths: dict[str, Path], example_id: str) -> Path:
    """Resolve a repository-owned example without accepting filesystem paths."""

    path = paths.get(example_id)
    if path is None:
        raise HTTPException(status_code=404, detail=f"Unknown animation example: {example_id}")
    if not path.is_file():
        raise HTTPException(status_code=500, detail=f"Animation example is missing: {example_id}")
    return path


async def _read_upload(file: UploadFile) -> tuple[str, bytes]:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        supported = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {ext}。支持: {supported}",
        )
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件超过 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB 上限。",
        )
    return ext, content


def _write_temporary_upload(ext: str, content: bytes) -> Path:
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        return Path(tmp.name)


@app.post("/api/documents/from-url", response_model=DocumentIR)
async def create_document_from_url(request: FromUrlRequest) -> DocumentIR:
    try:
        return await ingest_url(str(request.url))
    except IngestionError as exc:
        raise _ingestion_http_error(exc) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch document: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/documents/from-query", response_model=DocumentIR)
async def create_document_from_query(request: FromQueryRequest) -> DocumentIR:
    try:
        return await ingest_source(QuerySourceInput(query=request.query))
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Web Search failed: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/documents/from-file", response_model=DocumentIR)
async def create_document_from_file(file: Annotated[UploadFile, File()]) -> DocumentIR:
    ext, content = await _read_upload(file)
    tmp_path = _write_temporary_upload(ext, content)
    try:
        return ingest_file(tmp_path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)


@app.post("/api/lessons/from-url", response_model=LessonIR)
async def create_lesson_from_url(request: FromUrlRequest) -> LessonIR:
    try:
        document = await ingest_url(str(request.url))
        return await generate_lesson(document)
    except IngestionError as exc:
        raise _ingestion_http_error(exc) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch document: {exc}") from exc
    except MissingLLMKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/animations/from-url", response_model=RenderSpec)
async def create_animation_from_url(request: FromUrlRequest) -> RenderSpec:
    try:
        return await generate_animation_from_url(str(request.url))
    except IngestionError as exc:
        raise _ingestion_http_error(exc) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Animation generation failed: {exc}") from exc
    except MissingLLMKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/animations/from-query", response_model=RenderSpec)
async def create_animation_from_query(request: FromQueryRequest) -> RenderSpec:
    try:
        return await generate_animation(QuerySourceInput(query=request.query))
    except IngestionError as exc:
        raise _ingestion_http_error(exc) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Animation generation failed: {exc}") from exc
    except MissingLLMKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/animations/from-example", response_model=RenderSpec)
async def create_animation_from_example(request: FromExampleRequest) -> RenderSpec:
    """Generate an animation from an allowlisted, version-controlled document."""

    source = _example_path(EXAMPLE_DOCUMENTS, request.example_id)
    try:
        return await generate_animation(FileSourceInput(path=source))
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Animation generation failed: {exc}") from exc
    except MissingLLMKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/animations/from-file", response_model=RenderSpec)
async def create_animation_from_file(file: Annotated[UploadFile, File()]) -> RenderSpec:
    ext, content = await _read_upload(file)
    tmp_path = _write_temporary_upload(ext, content)
    try:
        return await generate_animation(FileSourceInput(path=tmp_path))
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Animation generation failed: {exc}") from exc
    except MissingLLMKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)


@app.get("/api/animations/examples/{example_id}/preview", response_model=RenderSpec)
def preview_animation_example(example_id: str) -> RenderSpec:
    """Render the reviewed visual baseline; this endpoint does not call an LLM."""

    source = _example_path(EXAMPLE_STORYBOARDS, example_id)
    storyboard = StoryboardIR.model_validate_json(source.read_text(encoding="utf-8"))
    issues = validate_storyboard(storyboard, limits=build_limits())
    if issues:
        summary = "; ".join(f"{issue.where}: {issue.detail}" for issue in issues)
        raise HTTPException(status_code=500, detail=f"Invalid reviewed storyboard: {summary}")
    return compile_storyboard_render_spec(storyboard)


@app.get("/api/animations/examples/{example_id}/latest", response_model=RenderSpec)
def latest_generated_animation_example(example_id: str) -> RenderSpec:
    """Return the last successfully persisted generated result for an example."""

    source_path = _example_path(EXAMPLE_DOCUMENTS, example_id)
    source = FileAdapter().resolve_sync(FileSourceInput(path=source_path))[0]
    candidates = sorted(
        DEFAULT_RUNS_DIR.glob("*/06-render-spec.json"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for render_path in candidates:
        spec = RenderSpec.model_validate_json(render_path.read_text(encoding="utf-8"))
        if spec.document_id == source.id:
            return spec
    raise HTTPException(
        status_code=404,
        detail=f"No generated animation is available yet for example: {example_id}",
    )


@app.post("/api/lessons/from-file", response_model=LessonIR)
async def create_lesson_from_file(file: Annotated[UploadFile, File()]) -> LessonIR:
    ext, content = await _read_upload(file)
    tmp_path = _write_temporary_upload(ext, content)
    try:
        document = ingest_file(tmp_path)
        return await generate_lesson(document)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MissingLLMKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)
