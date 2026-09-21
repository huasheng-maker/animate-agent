from __future__ import annotations

import asyncio
import logging

import httpx
from pytest import LogCaptureFixture, MonkeyPatch

import animate_agent.llm as llm_module
from animate_agent.llm import LLMClient, LLMConfig


def test_llm_logs_timing_without_prompt_or_secret(caplog: LogCaptureFixture) -> None:
    secret = "do-not-log-this-key"
    prompt = "do-not-log-this-prompt"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {
                        "message": {"content": '{"ok": true}'},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    async def run() -> str:
        transport = httpx.MockTransport(handler)
        http_client = httpx.AsyncClient(transport=transport)
        try:
            client = LLMClient(
                LLMConfig(
                    base_url="https://example.com/v1",
                    api_key=secret,
                    model="test-model",
                    timeout_seconds=12,
                ),
                client=http_client,
            )
            return await client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=100,
            )
        finally:
            await http_client.aclose()

    with caplog.at_level(logging.INFO, logger="uvicorn.error.animate_agent.llm"):
        result = asyncio.run(run())

    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert result == '{"ok": true}'
    assert "status=started" in logs
    assert "status=completed" in logs
    assert "model=test-model" in logs
    assert "timeout_seconds=12" in logs
    assert "response_chars=12" in logs
    assert secret not in logs
    assert prompt not in logs


def test_llm_logs_a_heartbeat_while_waiting(
    monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
) -> None:
    monkeypatch.setattr(llm_module, "LLM_PROGRESS_LOG_INTERVAL_SECONDS", 0.01)

    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.03)
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {"message": {"content": "done"}, "finish_reason": "stop"}
                ]
            },
        )

    async def run() -> None:
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            client = LLMClient(
                LLMConfig(
                    base_url="https://example.com/v1",
                    api_key="test",
                    model="slow-test-model",
                    timeout_seconds=1,
                ),
                client=http_client,
            )
            await client.chat(
                [{"role": "user", "content": "hello"}],
                temperature=0.2,
                max_tokens=100,
            )
        finally:
            await http_client.aclose()

    with caplog.at_level(logging.INFO, logger="uvicorn.error.animate_agent.llm"):
        asyncio.run(run())

    messages = [record.getMessage() for record in caplog.records]
    assert any("status=waiting" in message for message in messages)
