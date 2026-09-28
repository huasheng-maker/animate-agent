# Generation progress and background jobs

The Studio now submits generation as a job. Validated source excerpts and scene
plans appear as each pipeline stage finishes. The user can inspect content,
collapse the panel, leave the page, refresh, cancel, or open the finished movie.
Completion does not force navigation. This is stage streaming, not scene playback
before the whole movie is ready (that remains P3).

## Runtime and dependencies

- Install the project dependencies as usual (`uv sync --extra dev`). SSE uses
  `sse-starlette`; the browser uses native `EventSource`. No Redis is needed.
- Start the existing FastAPI entrypoint with **one worker**. SQLite persists
  snapshots, ordered events, and finished results in `data/runs/jobs.sqlite3`.
- Jobs run independently of browser connections, with at most two running jobs
  in this process. A server shutdown/restart marks unfinished jobs interrupted;
  it never automatically repeats paid generation. This is a local single-process
  runner, not a distributed queue. Multiple API workers are not supported by it.
- The Next.js same-origin proxy streams response bodies directly and sets
  `no-store, no-transform` and `X-Accel-Buffering: no`. Any additional reverse
  proxy must also allow SSE without response buffering.

## API

`POST /api/animation-jobs` accepts an `Idempotency-Key` UUID and either:

```json
{"mode":"query","value":"How does a controller work?"}
```

Modes `url` and `example` are also supported; `example` only accepts `controller`.
File input uses multipart `file`, the existing extension allowlist and a 20 MB
limit. A successful submission returns 202, a snapshot, `Location`, and
`Retry-After`. Reusing the same key and input returns the existing job; changed
input with that key returns 409.

- `GET /api/animation-jobs/{id}`: authoritative snapshot; also polling fallback.
- `GET /api/animation-jobs/{id}/events?after=N`: SSE with monotonic event IDs;
  `Last-Event-ID` is supported for reconnects. Heartbeats run every 10 seconds.
- `POST /api/animation-jobs/{id}/cancel`: idempotent cancellation. Stops local
  execution/awaiting; an upstream provider may already have billed accepted work.
- `GET /api/animation-jobs/{id}/result`: finished RenderSpec, or 409 while unfinished.

Stage events contain user-facing status and validated, bounded previews, not raw
model responses or hidden reasoning. Source previews show up to 24 sections,
two excerpts per section and 800 characters per excerpt. The complete pipeline
artifacts retain their existing representation. Progress does not claim invented
percentages or remaining-time estimates.

The browser stores only the current job ID and a submission digest in localStorage.
SSE is the primary transport; healthy streams only reconcile a snapshot once per minute.
Named heartbeats carry the current snapshot every ten seconds. Disconnected streams fall back to
five-second polling; a stream with no signal for 35 seconds is reconnected.
This allows recovery when a proxy prevents streaming. Refresh restores that job, including
completed or failed outcomes. A lost submission response can be retried with the
same input and key. Starting a new task replaces the browser's current-task link.

Schema failures confined to specific scenes now request replacements for only
those scenes within the existing retry budget. All untouched scenes are preserved,
and the merged document must still pass the complete schema/evidence/renderer
validation. Object budgets count edges as well as nodes; no arbitrary objects are
silently removed and the 12-object cap is unchanged. Exhausted failures carry a
safe explanation to the UI. A failed task expands its panel, stops the waiting
indicator and offers state resynchronization and an explicit new submission using
the current input. This does not automatically restart existing failed jobs.

The schema-repair follow-up passed 63 local Python tests (plus 5 subtests), strict
mypy, affected-file Ruff and an isolated production build. A real browser fixture
reproduced the 13-versus-12 object failure while the panel was collapsed: it
expanded the failure reason, stopped animation, retained excerpts, recovered after
refresh, resynchronized and created a new task only on explicit button click.
Screenshot: `output/playwright/generation-schema-failure.png`. Live model quality
was not retested; local scene-patch tests verify full validation still applies.

Uploaded job inputs remain under `data/runs/job-inputs/` alongside durable run
artifacts. There is no automatic deletion; these follow the local run retention
policy and require explicit cleanup. The existing synchronous APIs are unchanged.

## Verification without paid model calls

`tests/test_animation_jobs.py` covers durable replay, idempotency, cancellation,
queueing, errors, restart interruption, input validation and result retrieval.
`tests/manual_generation_server.py` is an opt-in browser fixture using the reviewed
Controller storyboard. It exposes test-only advance controls on a separate local
server and never calls a model. Do not use it as the production API entrypoint.

Verified on 2026-09-23: 56 local Python tests (plus 5 subtests), 32 player tests,
strict mypy across 70 source files, affected-file Ruff, and Next production build
passed. Browser checks at 1440×1000 and 390×844 covered live stages, source excerpts,
SSE delivery with snapshot polling blocked, polling fallback with SSE blocked,
refresh recovery, offline/reconnect,
background navigation, cancellation, failure with preserved content, restart
interruption, completion without forced navigation, and opening the real player.
Reduced-motion mode disabled panel animations; terminal recovery stopped polling.
Screenshots: `output/playwright/generation-desktop.png` and
`output/playwright/generation-mobile.png`.

No paid generation or external ingestion was exercised. Whole-source Ruff also
reports two pre-existing E501 lines in `visualization/prompts.py`; these are outside
this change. The Python test client emits two dependency deprecation warnings;
the existing Remotion player emits its license notice during build/playback.

## Focused query evidence

Query acquisition now keeps at most three unique results. Kimi requests three
results by default; hosted search prompts also request a narrow answer from up to
three primary sources. The resolver ranks title/content matches deterministically,
removes duplicate URLs/content and weak matches, then retains up to 3000 characters
per prose source (up to 9000 total). Relevant paragraphs are preferred while their
original order is retained. Structured custom-adapter blocks remain intact.

This is a lexical filter, not a semantic reranker. With no lexical overlap, such as
cross-language searches, provider ordering is preserved. It adds no LLM calls.
Existing knowledge may guide teaching order, conceptual connections and labeled
analogies; factual claims still require actual evidence references.

The follow-up change passed 60 local Python tests (plus 5 subtests), strict mypy
across 71 source files, affected-file Ruff and an isolated Next production build.
In a real browser, a healthy stream stayed at one initial snapshot GET after 45
seconds. Blocking SSE and reloading restored stage updates via polling. Replaying
the saved source documents from run `ac505ae576cb4dbca3c804746ef89df1` through the
local selector reduced five documents / 17689 characters to three / 6451. This
does not measure a new live search or model-generation latency.
