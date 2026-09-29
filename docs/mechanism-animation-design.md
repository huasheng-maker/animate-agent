# Computed mechanism animations

Status: the sections below describe the legacy adapters. New generation uses the composable registry described in [element-registry.md](element-registry.md). Existing generic storyboards remain compatible; previously saved movies are not automatically regenerated.

## Research (2026-09-23)

- [LLM Visualization](https://github.com/bbycroft/llm-viz): working tiny GPT-style inference rendered as tensors and operations. Adopt persistent token/tensor identity and computation-driven highlights. Its complete WebGL application is not a drop-in Canvas renderer.
- [TensorFlow Playground](https://github.com/tensorflow/playground): interactive neural-network computation. Adopt parameter -> recomputation -> visible output, rather than decorative neuron pulses.
- [MathBox](https://github.com/unconed/mathbox): browser mathematical diagrams with data-backed geometry. Adopt sampled curves and coordinate transformations; adding its WebGL stack is unnecessary for the initial 2D models.
- [Manim Transform](https://docs.manim.community/en/stable/reference/manim.animation.transform.Transform.html): interpolate mathematical objects while preserving correspondence. Adopt basis/vector identity and deterministic frame interpolation, retaining the existing browser player.
- [ns-3 tutorial](https://www.nsnam.org/docs/release/3.24/tutorial/singlehtml/index.html): discrete-event simulation and tracing separate computed packet events from visualization. Adopt a bounded educational event model; do not represent it as a complete TCP/IP implementation.
- [RFC 9293](https://www.rfc-editor.org/rfc/rfc9293.html): authoritative TCP state and SYN/ACK sequence semantics. Handshake demonstration uses SYN_SENT, SYN_RECEIVED and ESTABLISHED; the separate stop-and-wait demonstration is not labeled as a full TCP retransmission model.

No third-party implementation has been copied, installed, or executed. These references inform architecture; numerical results come from local deterministic models.

## Contract

Add an optional typed `mechanism` to each Storyboard scene, carry it through RenderSpec and AnimationIR, and render it in the normal player. Both query and document/lesson agents receive the capability catalog without an additional LLM call. Each phase binds one existing narrated, cited beat. Reject unknown models, invalid dimensions, nonfinite/out-of-range values, mismatched phases and unsupported controls.

Initial coverage: illustrative language-model inference (embedding, causal attention, probability, autoregression), neuron forward/gradient update, 2D linear transformation, quadratic derivative, TCP handshake and stop-and-wait loss/retransmission. This is a registry of supported mechanisms, not a claim of arbitrary subject simulation. Unsupported topics retain the existing controlled graphics path.

Numbers are explicitly labeled illustrative. Model-authored prose must still cite source evidence; illustrative matrices cannot be presented as internal states of a commercial LLM. Compilation supplies bounded, consumed controls. Matrix cells are renderer-owned children, not dozens of authored scene objects.

## Completion gates

- Query and URL/file/text planning can select all three subject families; no separate demo-only route.
- Strict schema/evidence checks and persisted artifacts retain mechanism parameters/phases.
- Computed embedding lookup, causal mask, normalized probabilities and token append are visible; at least two autoregressive rounds are reproducible.
- Neuron gradients change computed loss; linear transformation changes basis/grid/vector; secant slope converges to derivative; packet loss produces timeout and retry.
- Existing Player playback/seek and controls work without network/model calls. Arbitrary seek reconstructs identical state.
- Local integration tests compile representative generated plans into actual player payloads; browser checks inspect normal player renderings for all three families, controls and seeking. Paid live generation is excluded unless separately authorized.

## Implementation and verification

- `src/animate_agent/mechanisms.py`: discriminated, bounded parameter contracts and shared prompt catalog. `StoryboardScene` checks phase/beat alignment and rejects authored mechanism controls. The existing validator verifies source references and requires a mechanism for recognized supported intents, including the correct TCP protocol.
- `rendering/layout.py`: carries the validated plan and creates scene-scoped controls. `animation_ir/compiler.py` preserves it in canonical AnimationIR as well as compatibility data. Existing persistence, jobs, SSE/result transport and player handoff retain these additive fields.
- `frontend/player/mechanisms/model.js`: pure calculations; `draw.js`: trusted Canvas domain adapter. The existing `KnowledgeMovieComposition` supplies the current frame/beat and overrides. No executable model-authored code and no second playback engine.
- Backend: 95 local tests passed, including 20 combinations of five mechanism kinds and query/URL/file/text orchestration with local source/model stubs. Strict mypy passed for 72 source files. Changed-file Ruff passed; two older long lines in the intent prompt remain outside this change.
- Player: 38 tests passed. Typecheck and isolated Next production build passed. Chromium loaded actual compiled specs through `/player?spec=...`, inspected embedding, two autoregressive rounds, neural calculation, matrix transform, derivative and TCP handshake. Parameter changes produced different Canvas pixels; returning to the same beat/frame produced identical pixels. Zero browser console errors (existing framework/license warnings remain).
- Narrow viewport check confirmed no horizontal page overflow; it retains the existing scaled desktop Canvas layout, so fine matrix values are best viewed in fullscreen. This is not a claim of a redesigned mobile teaching layout.
- Screenshots: `output/playwright/mechanism-embedding.png`, `mechanism-autoregression.png`, `mechanism-neural_network.png`, `mechanism-linear_transform.png`, `mechanism-derivative.png`, `mechanism-tcp.png`, `mechanism-mobile.png`.
- No live paid generation or external acquisition integration was performed. Live provider instruction-following and evidence quality are not established by the local fixtures; strict rejection/repair remains active if a provider ignores the mechanism contract.

To exercise the new generation path, restart the backend/frontend if they do not hot-reload, then generate a new movie, e.g. `How does LLM work?`, `神经网络的工作原理`, `线性变换如何改变平面？`, `导数与割线、切线有什么关系？`, or `TCP 三次握手发生了什么？`.

To extend a capability, add a bounded plan variant and catalog example, a deterministic computation and Canvas adapter, consumed scene-scoped controls, plus numerical/compile/browser checks. Do not route an unsupported topic to an unrelated demonstration merely because it shares a broad subject label.

## Live-generation gap corrected (2026-09-29)

Run `7b00979250c1450394feb5a2ae6d48a3` asked `How does Large-language-Model work?` but all three saved scenes had `mechanism: null`. The running API exposed the new mechanism schema. The deterministic intent guard missed hyphenated wording, so an otherwise valid generic storyboard was accepted even though the system prompt offered mechanisms.

Capability matching now normalizes Unicode, separators and whitespace while preserving the original question. Query and lesson prompts explicitly name the required mechanism before generation. The query JSON example no longer advertises invalid `state` properties on body primitives; the run's first rejected output contained 22 such property errors.

Read-only revalidation of the real saved storyboard now reports `mechanism_required`. Regression tests exercise equivalent spellings, prompt requirements, rejection/repair into a compiled mechanism, and unsupported-topic non-routing. Current local suite: 108 tests passed; strict mypy: 73 source files. No paid regeneration was performed and the existing saved run was not modified. Earlier browser screenshots demonstrate the renderer with offline plans, not guaranteed live-provider compliance. Circular motion is still outside the initial five mechanism kinds.
