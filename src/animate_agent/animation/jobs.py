"""Single-process local jobs with durable SQLite snapshots and replayable events.

Browser connections do not own execution. Interrupted server runs are never
automatically replayed, because replay may repeat paid model requests.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from animate_agent.animation.progress import progress_sink
from animate_agent.rendering.models import RenderSpec

TERMINAL = {"completed", "failed", "cancelled", "interrupted"}
JobRunner = Callable[[str], Awaitable[RenderSpec]]


class JobStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS jobs "
                "(id TEXT PRIMARY KEY, fingerprint TEXT, snapshot TEXT, result TEXT)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS events "
                "(job_id TEXT, seq INTEGER, payload TEXT, PRIMARY KEY(job_id, seq))"
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, job_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT snapshot FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return dict(json.loads(row[0]))

    def create(self, job_id: str, fingerprint: str, mode: str) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT fingerprint FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row:
                if row[0] != fingerprint:
                    raise ValueError("同一提交标识对应的输入已改变，请重新提交。")
                return False
            snapshot = {
                "run_id": job_id,
                "mode": mode,
                "status": "queued",
                "seq": 0,
                "stage": "queued",
                "created_at": time.time(),
                "updated_at": time.time(),
                "completed_stages": [],
                "artifacts": {},
                "calls": 0,
                "message": "等待开始",
            }
            db.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, NULL)",
                (job_id, fingerprint, json.dumps(snapshot)),
            )
        self.update(job_id, "queued")
        return True

    def update(self, job_id: str, kind: str, **changes: Any) -> dict[str, Any]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT snapshot FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            snapshot = dict(json.loads(row[0]))
            if snapshot["status"] in TERMINAL:
                return snapshot
            snapshot.update(changes)
            snapshot.update(seq=snapshot["seq"] + 1, updated_at=time.time(), event=kind)
            encoded = json.dumps(snapshot, ensure_ascii=False)
            db.execute("UPDATE jobs SET snapshot = ? WHERE id = ?", (encoded, job_id))
            db.execute("INSERT INTO events VALUES (?, ?, ?)", (job_id, snapshot["seq"], encoded))
        return snapshot

    def events(self, job_id: str, after: int) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT payload FROM events WHERE job_id = ? AND seq > ? ORDER BY seq LIMIT 100",
                (job_id, after),
            ).fetchall()
        return [dict(json.loads(row[0])) for row in rows]

    def save_result(self, job_id: str, spec: RenderSpec) -> None:
        with self.connect() as db:
            db.execute("UPDATE jobs SET result = ? WHERE id = ?", (spec.model_dump_json(), job_id))

    def result(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT result FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(json.loads(row[0])) if row and row[0] else None

    def interrupt_unfinished(self) -> None:
        with self.connect() as db:
            ids = [row[0] for row in db.execute("SELECT id FROM jobs")]
        for job_id in ids:
            self.update(
                job_id,
                "interrupted",
                status="interrupted",
                message="服务已重启，生成已中断。已完成内容仍可查看；重新生成需手动提交。",
            )


class JobManager:
    def __init__(self, store: JobStore) -> None:
        self.store = store
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.slots = asyncio.Semaphore(2)

    def start(self, job_id: str, runner: JobRunner) -> None:
        task = asyncio.create_task(self._run(job_id, runner))
        self.tasks[job_id] = task
        task.add_done_callback(lambda _: self.tasks.pop(job_id, None))

    def progress(self, job_id: str, kind: str, data: dict[str, Any]) -> None:
        snapshot = self.store.get(job_id)
        if kind == "stage":
            self.store.update(job_id, kind, stage=data["stage"], message="")
        elif kind == "artifact":
            artifacts = {**snapshot["artifacts"], data["name"]: data["value"]}
            completed = list(dict.fromkeys([*snapshot["completed_stages"], data["stage"]]))
            self.store.update(job_id, kind, artifacts=artifacts, completed_stages=completed)
        elif kind == "model_call":
            message = snapshot["message"] if snapshot["event"] == "retry" else "正在等待模型回复"
            self.store.update(job_id, kind, calls=snapshot["calls"] + 1, message=message)
        elif kind == "retry":
            self.store.update(job_id, kind, message="正在修正生成结果或重试请求，已完成内容会保留")

    async def _run(self, job_id: str, runner: JobRunner) -> None:
        token = progress_sink.set(lambda kind, data: self.progress(job_id, kind, data))
        try:
            async with self.slots:
                self.store.update(job_id, "started", status="running")
                spec = await runner(job_id)
                self.store.save_result(job_id, spec)
                self.store.update(
                    job_id,
                    "completed",
                    status="completed",
                    stage="completed",
                    message="动画已完成，可以播放",
                )
        except asyncio.CancelledError:
            self.store.update(job_id, "cancelled", status="cancelled", message="生成已取消")
            raise
        except Exception as exc:
            # Exception bodies may contain provider payloads, URLs or credentials.
            from animate_agent.llm import MissingLLMKeyError
            from animate_agent.visualization.agent import StoryboardGenerationError

            message = (
                "模型尚未配置，请检查服务端配置后重新生成。"
                if isinstance(exc, MissingLLMKeyError)
                else "生成未完成，请检查服务端阶段日志。已完成内容已保留，可重新提交。"
            )
            if isinstance(exc, StoryboardGenerationError):
                message = exc.summary
            self.store.update(job_id, "failed", status="failed", message=message)
        finally:
            progress_sink.reset(token)

    async def cancel(self, job_id: str) -> dict[str, Any]:
        snapshot = self.store.get(job_id)
        if snapshot["status"] not in TERMINAL:
            self.store.update(job_id, "cancelled", status="cancelled", message="生成已取消")
            task = self.tasks.get(job_id)
            if task:
                task.cancel()
        return self.store.get(job_id)

    async def close(self) -> None:
        for job_id, task in list(self.tasks.items()):
            self.store.update(
                job_id,
                "interrupted",
                status="interrupted",
                message="服务已停止，生成已中断。已完成内容已保留。",
            )
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
