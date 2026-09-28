"""Shared OpenAI-compatible LLM client used by the agent stages."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from animate_agent.observability import animation_run_id
from animate_agent.paths import ENV_FILE

logger = logging.getLogger("uvicorn.error.animate_agent.llm")

#: Local key file, resolved against the repository root rather than the working
#: directory so `animate-agent` reads the same file from anywhere it is invoked.
#: Written by a developer, never committed: `.gitignore` covers `.env` and
#: `.env.*` except the `*.example` files.
#: Output budget for one chat call. The configured endpoint serves a *reasoning*
#: model: `max_tokens` covers the hidden reasoning plus the visible answer, and
#: on the storyboard prompt the reasoning alone runs to ~23k tokens. A tight
#: budget is spent entirely on reasoning, which returns HTTP 200 with an empty
#: body — not an error the transport can flag.
DEFAULT_MAX_TOKENS = 32768
LLM_PROGRESS_LOG_INTERVAL_SECONDS = 30.0


async def _log_llm_waiting(
    done: asyncio.Event,
    *,
    run_id: str,
    started_at: float,
) -> None:
    """Emit a heartbeat while an upstream model request is still pending."""

    while not done.is_set():
        try:
            await asyncio.wait_for(done.wait(), timeout=LLM_PROGRESS_LOG_INTERVAL_SECONDS)
        except TimeoutError:
            logger.info(
                "llm run=%s status=waiting elapsed_seconds=%d",
                run_id,
                round(time.perf_counter() - started_at),
            )


class LLMBudgetExhaustedError(RuntimeError):
    """The model spent its whole output budget on reasoning and never answered.

    Deliberately not a `ValueError`: the agents retry on `ValueError`, and
    retrying at the same budget cannot succeed — it just burns another slow,
    expensive reasoning call.
    """


class MissingLLMKeyError(RuntimeError):
    """The configured LLM endpoint has no credential available."""


@dataclass(frozen=True)
class LLMConfig:
    """Connection settings for an OpenAI-compatible chat-completions endpoint."""

    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 600.0


class LLMClient:
    """Thin async client for OpenAI-compatible chat completions (DeepSeek, Moonshot)."""

    def __init__(self, config: LLMConfig, *, client: httpx.AsyncClient | None = None) -> None:
        self._config = config
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(config.timeout_seconds))

    def _uses_moonshot_api(self) -> bool:
        hostname = urlsplit(self._config.base_url).hostname or ""
        return hostname.lower() == "api.moonshot.cn" or self._config.model.startswith("kimi-")

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Send one chat request and return the assistant message content."""
        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
        }
        if self._uses_moonshot_api():
            # Kimi uses max_completion_tokens and model/mode-specific sampling
            # constraints. Keep that compatibility inside the transport boundary
            # so agent code remains provider-free.
            payload["max_completion_tokens"] = max_tokens
            if self._config.model == "kimi-k2.6":
                # Schema generation benefits from concise final JSON, not a
                # multi-minute hidden reasoning pass. K2.6 explicitly supports
                # disabling thinking; models that require thinking are left alone.
                payload["temperature"] = 0.6
                payload["thinking"] = {"type": "disabled"}
            else:
                payload["temperature"] = 1.0
        else:
            payload["temperature"] = temperature
            payload["max_tokens"] = max_tokens
        headers = {"Authorization": f"Bearer {self._config.api_key}"}
        url = self._config.base_url.rstrip("/") + "/chat/completions"
        run_id = animation_run_id()
        started_at = time.perf_counter()
        logger.info(
            "llm run=%s status=started model=%s timeout_seconds=%g messages=%d max_tokens=%d",
            run_id,
            self._config.model,
            self._config.timeout_seconds,
            len(messages),
            max_tokens,
        )
        from animate_agent.animation.progress import report_progress

        report_progress("model_call")
        request_done = asyncio.Event()
        progress_task = asyncio.create_task(
            _log_llm_waiting(request_done, run_id=run_id, started_at=started_at)
        )

        try:
            response = await self._client.post(url, json=payload, headers=headers)
            if response.status_code == 429:
                report_progress("retry")
                logger.warning(
                    "llm run=%s status=rate_limited elapsed_ms=%d retry_in_seconds=3",
                    run_id,
                    round((time.perf_counter() - started_at) * 1000),
                )
                await asyncio.sleep(3.0)
                response = await self._client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            data = response.json()
            choices = data.get("choices")
            if not choices:
                raise ValueError("LLM returned no choices.")

            choice = choices[0]
            content = choice.get("message", {}).get("content")
            if not isinstance(content, str):
                raise ValueError("LLM returned non-string content.")
            if not content.strip():
                # Left undetected, an exhausted budget surfaces further down as
                # "Expecting value: line 1 column 1", which blames the JSON instead
                # of the budget and sends you looking in the wrong place.
                if choice.get("finish_reason") == "length":
                    raise LLMBudgetExhaustedError(
                        f"模型把 max_tokens({max_tokens}) 全部用在推理上，没有产出正文。"
                        "请调大 max_tokens——用同样的预算重试没有意义。"
                    )
                raise ValueError(
                    f"LLM 返回空正文（finish_reason={choice.get('finish_reason')}）"
                )
            logger.info(
                "llm run=%s status=completed status_code=%d elapsed_ms=%d response_chars=%d",
                run_id,
                response.status_code,
                round((time.perf_counter() - started_at) * 1000),
                len(content),
            )
            return content
        except Exception as exc:
            logger.exception(
                "llm run=%s status=failed elapsed_ms=%d error_type=%s",
                run_id,
                round((time.perf_counter() - started_at) * 1000),
                type(exc).__name__,
            )
            raise
        finally:
            request_done.set()
            await progress_task

    async def aclose(self) -> None:
        """Close the underlying client when this object owns it."""
        if self._owns_client:
            await self._client.aclose()


def load_env_file(path: Path = ENV_FILE) -> list[str]:
    """Fill `os.environ` from a `.env` file, returning the names it actually set.

    A name already present in the environment is left alone and not reported: a
    real `$env:DEEPSEEK_KEY` is a deliberate override, and a file sitting in the
    working copy must not quietly beat it. A missing file is not an error — that
    is the normal case for anyone exporting the variable directly.
    """
    if not path.is_file():
        return []
    filled: list[str] = []
    # `utf-8-sig`, not `utf-8`: Windows editors still offer "UTF-8 with BOM", and
    # a BOM would otherwise ride along on the *first* name in the file, so the
    # name parses as U+FEFF + "DEEPSEEK_KEY" — a variable nobody asked for,
    # while the real key silently never loads. `utf-8-sig` decodes plain UTF-8
    # byte-for-byte identically, so this costs nothing on a BOM-less file.
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        name, separator, value = line.partition("=")
        if not separator:
            continue  # a blank line, or a comment that assigns nothing
        name = name.strip()
        if name.startswith("export "):
            # What most documents show, and what gets copy-pasted. Keeping the
            # name as `export KEY` would set a variable nobody reads while the
            # real one silently never loads.
            name = name[len("export ") :].strip()
        if not name or name.startswith("#"):
            continue
        if name not in os.environ:
            os.environ[name] = value.strip().strip("'\"")
            filled.append(name)
    return filled


def load_llm_config() -> LLMConfig:
    """Build an LLMConfig from the environment, falling back to the `.env` file.

    The file is read here rather than at import time so that importing this
    module never mutates the process environment as a side effect.
    """
    load_env_file(ENV_FILE)
    kimi_key = os.environ.get("KIMI_KEY", "")
    if kimi_key:
        base_url = os.environ.get("KIMI_BASE", "https://api.moonshot.cn/v1")
        api_key = kimi_key
        model = os.environ.get("KIMI_MODEL", "kimi-k2.6")
    else:
        base_url = os.environ.get("DEEPSEEK_BASE", "https://api.deepseek.com")
        api_key = os.environ.get("DEEPSEEK_KEY", "")
        model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
    timeout_seconds = float(os.environ.get("LLM_TIMEOUT_SECONDS", "600"))
    return LLMConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
    )


def require_llm_config() -> LLMConfig:
    """Load LLM settings and fail before network work when the key is absent."""

    config = load_llm_config()
    if not config.api_key:
        raise MissingLLMKeyError(
            "未配置 KIMI_KEY 或 DEEPSEEK_KEY，无法调用 Knowledge/Storyboard Agent。"
            "请在仓库 .env 或进程环境变量中设置后重试。"
        )
    return config
