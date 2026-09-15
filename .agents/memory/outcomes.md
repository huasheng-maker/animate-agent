# Outcomes

date: 2026-07-29

- date: 2026-07-29
  capability: AgentGo bootstrap
  result: helped
  artifact: `.agents/`
  action: Created minimal repository memory structure after installing AgentGo v1.14.0.
  validation: Directory and file creation verified locally.

- date: 2026-09-08
  capability: Playwright browser verification
  result: helped
  artifact: `frontend/app/` and `src/animate_agent/documents/parser.py`
  action: Exercised fixture and live Manim URL flows through the built UI.
  validation: Found and fixed missing favicon metadata, Sphinx headerlink contamination, and readability structure loss; final browser load had no console errors and the final parser returned 10 sections, 68 blocks, 16 code blocks, and 9 list blocks for the live Manim page.

- date: 2026-09-11
  capability: Crawl4AI NormalizedDocument acquisition boundary
  result: helped
  artifact: `src/animate_agent/ingestion/`
  action: Added typed URL/raw-HTML acquisition, stable configuration, SSRF checks, compatibility DTO,
    retention policies, structured failures/logging, and reusable browser lifecycle.
  validation: 51 tests passed with one opt-in integration skipped; the real Crawl4AI 0.9.3 raw-HTML
    Chromium integration passed separately; Ruff, strict mypy, and git diff checks passed.

- date: 2026-09-11
  capability: Local API and CORS diagnosis
  result: helped
  artifact: `src/animate_agent/api.py`, `frontend/app/page.tsx`, and `tests/unit/test_document_ingestion.py`
  action: Confirmed that frontend-only startup leaves port 8000 unavailable, verified the live API
    and Manim request, added actionable connection feedback, allowed dynamic local Next.js ports,
    and routed the browser through a same-origin Next.js proxy to avoid CORS and loopback restrictions.
  validation: Live API POST returned 200 with 10 sections; live localhost:3001 preflight returned the
    matching allow-origin header; the live frontend proxy returned 200 with 10 sections; 11 focused
    tests, Ruff, strict mypy, typecheck, and build passed.

- date: 2026-09-11
  capability: Playwright browser verification
  result: no_effect
  artifact: `frontend/app/page.tsx`
  action: Attempted to reproduce the request in a real browser using the repository Playwright skill.
  correction or failure: The Windows host had no Bash for the bundled wrapper and no installed
    Playwright CLI; downloading and executing the CLI through npx was not authorized.
  next action: Re-run the browser submission when a local Playwright CLI is already installed.

- date: 2026-09-11
  capability: Local API and CORS diagnosis
  result: helped
  artifact: `src/animate_agent/api.py`, `frontend/app/page.tsx`, and `tests/unit/test_document_ingestion.py`
  action: Confirmed that frontend-only startup leaves port 8000 unavailable, verified the live API
    and Manim request, added actionable connection feedback, allowed dynamic local Next.js ports,
    and routed the browser through a same-origin Next.js proxy to avoid CORS and loopback restrictions.
  validation: Live API POST returned 200 with 10 sections; live localhost:3001 preflight returned the
    matching allow-origin header; the live frontend proxy returned 200 with 10 sections; 11 focused
    tests, Ruff, strict mypy, typecheck, and build passed.

- date: 2026-09-11
  capability: Playwright browser verification
  result: no_effect
  artifact: `frontend/app/page.tsx`
  action: Attempted to reproduce the request in a real browser using the repository Playwright skill.
  correction or failure: The Windows host had no Bash for the bundled wrapper and no installed
    Playwright CLI; downloading and executing the CLI through npx was not authorized.
  next action: Re-run the browser submission when a local Playwright CLI is already installed.
