# Composable element registry

New planning uses `scene.mechanism.kind="composition"`. It composes a bounded computation graph and visual bindings; there is no topic keyword router. Legacy saved scenes retain their adapters.

- `frontend/player/composable/ElementRegistry.js` exports `ElementRegistry`, `createElement`, `Ball`, `Particle`, `VectorArrow`, `Vehicle`, `Cart`.
- `src/animate_agent/composition.py` defines the Pydantic/JSON Schema visual enum and validates graph dimensions, references, bounds and phases.
- `ComposableStage.tsx` dispatches geometric visuals through the registry. Remotion supplies frame time; JSXGraph owns geometry. Text labels are rendered as React text in the color-matched legend.
- `composition_math.py` uses NumPy for sampled numerical preflight; `evaluate.js` uses mathjs at runtime. Neither runs model-authored source code.

| Element kind | Data binding | Properties |
| --- | --- | --- |
| `ball`, `particle` | 2D position node | radius (coordinate units), mass (positive metadata), glow, label, color |
| `vector_arrow` | 2D vector node `[dx,dy]` | origin (2D node, default zero), label, color |
| `vehicle`, `cart` | 2D position node | radius (size), label, color; polygon body and wheels |

Colors are bounded palette names: teal, gold, violet, red, blue. Mass does not silently create a physics simulation; use explicit graph operations for forces and acceleration. Vehicles currently translate without automatic heading or collision simulation.

`circular_motion_example()` is an executable Few-Shot, included in both planning paths. It computes `p=r(cos(wt),sin(wt))`, `v=rw(-sin(wt),cos(wt))`, and `a=-w²p`. Its evidence IDs must be replaced with actual input evidence. The example is instructional data, never selected as a hardcoded scene by a question match. New plans derive semantic objects and sliders from visuals and parameters.

Tools reused: [JSXGraph geometry](https://jsxgraph.org/docs/), [mathjs operations](https://mathjs.org/docs/reference/functions/multiply.html), [NumPy matrix operations](https://numpy.org/doc/stable/reference/generated/numpy.matmul.html). No expression parser is exposed; see [mathjs security guidance](https://mathjs.org/docs/expressions/security.html). Mafs was evaluated but its resize dependency's React peer range did not match this React 19 project.

Validation: Python numeric/schema/compiler tests, registry dispatch tests, frontend typecheck and isolated production build; browser checks cover moving geometry, radius control, deterministic backward/forward seeking, and vehicle display. These local fixtures do not prove a paid model will always plan correctly. Previously saved movies are not regenerated automatically.

Planning repair now reports all invalid visual bindings with their node ID, actual
shape and required shape in one response. Curves and moving points both require
explicit `[x,y]` nodes; `sample` is a zero-argument independent variable. The
executable `curve_example()` demonstrates separate sampled curve coordinates
and time-driven point coordinates. Scalar coordinates are never guessed.

Visual evidence is unioned into the plan's summary, preserving all declared IDs
and the 12-reference bound. This does not certify evidence: the document-level
validator still rejects invented citations and facts not bound to visuals.
During a geometry schema failure, intent planning also checks raw evidence
bindings in every scene and includes those scenes in the repair scope. This
prevents a schema-valid but evidence-invalid scene from being frozen while
retries fix another scene.

`symbol_lookup_example()` teaches row lookup with linked input, highlighted
matrix row and output vector. `feedback_example()` unrolls three predictions:
row lookup -> softmax -> argmax -> next lookup -> concat. These examples are
available to both planning prompts, never selected by a topic router.
`active_index` binds a scalar to a matrix row or token/bar item; `reveal_count`
limits the visible token prefix. Both references and index bounds are checked.
Greedy `argmax` selects the first maximum; it is not stochastic sampling.

The renderer expands its mathematical viewport to include visible geometry,
including vector endpoints at extreme slider settings. No model-authored camera
code is executed. Published examples have offline fixture regressions and a
provenance manifest; the reviewed LLM feedback example explicitly uses a
first-order state model rather than claiming to implement a full Transformer.
