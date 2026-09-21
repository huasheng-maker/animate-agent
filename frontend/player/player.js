/**
 * Player: load the RenderSpec compatibility envelope, run AnimationIR, and
 * hand resolved Scene State to the selected renderer.
 *
 * Everything here consumes the spec as data. There is no `eval`, no
 * `new Function`, and spec text only ever reaches `textContent` or `fillText`
 * (decision D4 — a model-authored string is data, never code).
 *
 * RAF schedules paints but never advances logical time by itself. Playback is
 * anchored to an integer frame, like Remotion's Player, so dropped browser
 * paints skip to the correct logical frame instead of slowing the animation.
 */

import { createSimulation } from "./behaviors.js";
import { normalizeRenderSpec } from "./animation-ir.js";
import { createCanvas2DRenderer } from "./canvas2d-renderer.js";
import { createAnimationRuntime } from "./runtime.js";
import { createStage, readTheme } from "./stage.js";
import { createFrameClock, normalizePlaybackRate } from "./timing.js";

const ui = {
  canvas: document.getElementById("stage"),
  title: document.getElementById("title"),
  eyebrow: document.getElementById("eyebrow"),
  goal: document.getElementById("goal"),
  steps: document.getElementById("steps"),
  controls: document.getElementById("controls"),
  play: document.getElementById("play"),
  nextBeat: document.getElementById("step"),
  previousFrame: document.getElementById("frame-prev"),
  nextFrame: document.getElementById("frame-next"),
  framePosition: document.getElementById("frame-position"),
  reset: document.getElementById("reset"),
  prev: document.getElementById("prev"),
  playbackRate: document.getElementById("playback-rate"),
  error: document.getElementById("error"),
};

const state = {
  spec: null,
  ir: null,
  scene: null,
  sceneIndex: 0,
  sim: null,
  runtime: null,
  sceneState: null,
  viewport: null,
  renderer: null,
  theme: null,
  byId: new Map(),
  obstacleIds: [],
  obstacleRadius: new Map(),
  overrides: {},
  lookup: null,
  stepIndex: 0,
  playing: true,
  playbackRate: 1,
  currentFrame: 0,
  clock: null,
  overrideRevision: 0,
  stopped: null,
};

/* ------------------------------------------------------------------ lookup */

/**
 * Resolve a property, most specific source first.
 *
 * 1. a control the user moved — user intent outranks everything
 * 2. the current step's `object_states` — this is what makes a step a beat
 * 3. the element's own `props`, carried verbatim from the StoryboardIR
 * 4. the scene's `params`, reached by `scene.<prop>` controls
 *
 * `safe_distance` is the case that exercises tier 4: the baseline exposes it as
 * a scene-level slider, not as a property of the circle drawn for it.
 */
function makeLookup(scene) {
  return (elementId, prop, fallback) => {
    const key = `${elementId}.${prop}`;
    if (key in state.overrides) return state.overrides[key];

    const step = scene.steps[state.stepIndex];
    const fromStep = step?.states?.[elementId];
    if (fromStep && prop in fromStep) return fromStep[prop];

    const element = state.byId.get(elementId);
    // A binding names the control that drives this property, and it outranks
    // the element's own props — a static prop is exactly what a binding exists
    // to override. Without this tier the safe-distance circle kept the radius
    // layout baked in while the slider moved the danger threshold, so the
    // picture changed but the circle named 安全距离 did not: the label and the
    // thing disagreed, and only a person would notice.
    const bound = element?.binds?.[prop];
    if (bound && bound in state.overrides) return state.overrides[bound];

    if (element?.props && prop in element.props) return element.props[prop];

    const sceneKey = `scene.${prop}`;
    if (sceneKey in state.overrides) return state.overrides[sceneKey];
    if (prop in (scene.params ?? {})) return scene.params[prop];

    return fallback;
  };
}

/* -------------------------------------------------------------------- view */

function buildView() {
  const step = state.scene.steps[state.stepIndex];
  state.sim.seekFrame(
    state.currentFrame,
    state.ir.fps,
    state.lookup,
    state.overrideRevision,
  );
  state.sceneState = state.runtime.seekFrame(state.currentFrame, { legacyLive: state.sim.live });
  const timelineHighlights = state.sceneState.nodes
    .filter((node) => node.style.highlight === true)
    .map((node) => node.id);
  return {
    live: state.sceneState.legacyLive,
    time: state.sceneState.time,
    frame: state.currentFrame,
    theme: state.theme,
    lookup: state.lookup,
    elementById: state.byId,
    obstacleIds: state.obstacleIds,
    obstacleRadius: state.obstacleRadius,
    highlighted: new Set([...(step?.highlights ?? []), ...timelineHighlights]),
    sceneState: state.sceneState,
    isDangerous: (id) => state.sim.isDangerous(id),
  };
}

function render() {
  const stage = state.spec.stage;
  const view = buildView();
  renderFramePosition();
  try {
    state.renderer.render(state.sceneState, { stage, view, clear: state.viewport.clear });
  } catch (error) {
    // A blank canvas and a half-drawn one look the same to a person. Say what
    // broke, on the page, and stop rather than throwing once per frame.
    fail(error instanceof Error ? error.message : String(error));
  }
}

function fail(message) {
  state.stopped = message;
  state.playing = false;
  ui.error.textContent = message;
  ui.error.hidden = false;
}

/* --------------------------------------------------------------------- loop */

function tick(now) {
  requestAnimationFrame(tick);
  if (state.stopped !== null) return;
  if (state.clock) {
    const playback = state.clock.update(now);
    state.currentFrame = playback.frame;
    if (state.playing !== playback.playing) setPlaying(playback.playing);
  }
  render();
}

/* --------------------------------------------------------------------- step */

function setStep(index) {
  const total = state.scene.steps.length;
  state.stepIndex = Math.max(0, Math.min(total - 1, index));
  state.runtime.setStep(state.stepIndex);
  // Restart the beat from rest: a step is a moment, and a beat that inherits the
  // previous one's elapsed time can never be looked at twice.
  state.sim.reset(state.lookup);
  resetFrameClock();
  renderSteps();
}

function moveStep(delta) {
  const next = state.stepIndex + delta;
  if (next >= state.scene.steps.length && state.sceneIndex < state.spec.scenes.length - 1) {
    loadScene(state.sceneIndex + 1);
    return;
  }
  if (next < 0 && state.sceneIndex > 0) {
    loadScene(state.sceneIndex - 1, -1);
    return;
  }
  setStep(next);
}

function renderSteps() {
  ui.steps.replaceChildren(
    ...state.scene.steps.map((step, index) => {
      const item = document.createElement("li");
      item.className = index === state.stepIndex ? "step is-current" : "step";
      const title = document.createElement("span");
      title.className = "step-title";
      title.textContent = `${String(index + 1).padStart(2, "0")} ${step.title}`;
      const body = document.createElement("p");
      body.className = "step-body";
      // `textContent`, never `innerHTML` — this string may be model-authored.
      body.textContent = step.narration;
      item.append(title, body);
      item.addEventListener("click", () => setStep(index));
      return item;
    }),
  );
}

/* ----------------------------------------------------------------- controls */

function renderControls() {
  const scene = state.scene;
  ui.controls.replaceChildren();

  for (const control of scene.controls) {
    if (control.type === "button") {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "control-button";
      button.textContent = control.label || control.action || control.id;
      button.addEventListener("click", () => {
        if (control.action === "reset_scene") setStep(state.stepIndex);
        else if (control.action === "toggle_play") togglePlay();
        else if (control.action === "advance_timeline") moveStep(1);
      });
      ui.controls.append(button);
      continue;
    }

    if (control.type === "toggle") {
      const label = document.createElement("label");
      label.className = "control";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = Boolean(control.default);
      box.addEventListener("change", () => {
        state.overrides[control.target_property] = box.checked ? 1 : 0;
        state.overrideRevision += 1;
      });
      state.overrides[control.target_property] = box.checked ? 1 : 0;
      const caption = document.createElement("span");
      caption.textContent = control.label;
      label.append(box, caption);
      ui.controls.append(label);
      continue;
    }

    const label = document.createElement("label");
    label.className = "control";
    const caption = document.createElement("span");
    const value = document.createElement("output");
    const input = document.createElement("input");
    input.type = "range";
    input.min = String(control.min ?? 0);
    input.max = String(control.max ?? 1);
    input.step = String(control.step ?? 0.1);
    input.value = String(control.default ?? control.min ?? 0);
    state.overrides[control.target_property] = Number(input.value);

    const show = () => {
      value.textContent = `${input.value}${control.unit ? ` ${control.unit}` : ""}`;
    };
    show();
    input.addEventListener("input", () => {
      state.overrides[control.target_property] = Number(input.value);
      state.overrideRevision += 1;
      show();
    });

    caption.textContent = control.label;
    label.append(caption, input, value);
    ui.controls.append(label);
  }
}

/* -------------------------------------------------------------------- boot */

function togglePlay() {
  setPlaying(!state.playing);
}

function setPlaying(playing) {
  const now = performance.now();
  if (state.clock) {
    const playback = playing ? state.clock.play(now) : state.clock.pause(now);
    state.currentFrame = playback.frame;
  }
  state.playing = Boolean(playing);
  ui.play.textContent = state.playing ? "暂停" : "播放";
  ui.play.setAttribute("aria-pressed", String(state.playing));
}

function stepFrame(delta) {
  setPlaying(false);
  const playback = state.clock.step(delta, performance.now());
  state.currentFrame = playback.frame;
  render();
}

function nextBeat() {
  setPlaying(false);
  moveStep(1);
}

function resetFrameClock() {
  state.clock = createFrameClock({
    fps: state.ir.fps,
    durationInFrames: state.runtime.durationInFrames || null,
    playbackRate: state.playbackRate,
    loop: false,
  });
  state.currentFrame = 0;
  if (state.playing) state.clock.play(performance.now());
  renderFramePosition();
}

function renderFramePosition() {
  if (!ui.framePosition || !state.runtime) return;
  const duration = state.runtime.durationInFrames;
  const suffix = duration > 0 ? ` / ${duration - 1}` : "";
  ui.framePosition.textContent = `帧 ${state.currentFrame}${suffix} · ${state.ir.fps} fps`;
}

function bind() {
  ui.play.addEventListener("click", togglePlay);
  ui.reset.addEventListener("click", () => setStep(0));
  ui.prev.addEventListener("click", () => moveStep(-1));
  ui.nextBeat.addEventListener("click", nextBeat);
  ui.previousFrame.addEventListener("click", () => stepFrame(-1));
  ui.nextFrame.addEventListener("click", () => stepFrame(1));
  ui.playbackRate.addEventListener("change", () => {
    state.playbackRate = normalizePlaybackRate(ui.playbackRate.value);
    ui.playbackRate.value = String(state.playbackRate);
    state.clock.setPlaybackRate(state.playbackRate, performance.now());
  });
  window.addEventListener("keydown", (event) => {
    if (event.code === "Space") {
      event.preventDefault();
      togglePlay();
    } else if (event.code === "ArrowRight") {
      nextBeat();
    } else if (event.code === "ArrowLeft") {
      moveStep(-1);
    } else if (event.code === "Comma") {
      stepFrame(-1);
    } else if (event.code === "Period") {
      stepFrame(1);
    }
  });
  window.addEventListener("resize", () => state.viewport.resize());
}

function loadScene(index, stepIndex = 0) {
  state.sceneIndex = index;
  state.scene = state.spec.scenes[index];
  state.runtime = createAnimationRuntime(state.ir.scenes[index], { fps: state.ir.fps });
  state.byId = new Map(state.scene.elements.map((element) => [element.id, element]));
  state.obstacleIds = state.scene.elements
    .filter((element) => element.role === "obstacle")
    .map((element) => element.id);
  state.obstacleRadius = new Map(
    state.obstacleIds.map((id) => [id, Number(state.byId.get(id)?.props?.radius ?? 0)]),
  );
  state.lookup = (elementId, prop, fallback) => state.runtime.lookup(elementId, prop, fallback);
  state.sim = createSimulation(state.scene, state.spec.stage);
  state.overrides = {};
  state.overrideRevision += 1;
  state.runtime.setLegacyOverrides(state.overrides);

  ui.title.textContent = state.spec.title || state.scene.title || "";
  ui.eyebrow.textContent = state.spec.eyebrow || state.spec.subject || "";
  ui.goal.textContent = state.scene.teaching_goal || "";

  renderControls();
  setStep(stepIndex < 0 ? state.scene.steps.length - 1 : stepIndex);
}

async function main() {
  const params = new URLSearchParams(window.location.search);
  const specUrl = params.get("spec");

  if (!specUrl) {
    fail("缺少 spec 参数。请从生成页面打开播放器，或提供明确的 RenderSpec URL。");
    return;
  }

  let spec;
  try {
    if (specUrl === "session") {
      const stored = window.sessionStorage.getItem("animate-agent-render-spec");
      if (!stored) throw new Error("当前浏览器会话里没有生成的 RenderSpec");
      spec = JSON.parse(stored);
    } else {
      const response = await fetch(specUrl);
      if (!response.ok) throw new Error(`HTTP ${response.status} ${response.statusText}`);
      spec = await response.json();
    }
  } catch (error) {
    fail(`取不到 spec：${specUrl}\n${error instanceof Error ? error.message : error}`);
    return;
  }

  if (!spec.scenes || spec.scenes.length === 0) {
    fail("spec 里一个场景都没有");
    return;
  }

  state.spec = spec;
  try {
    state.ir = normalizeRenderSpec(spec);
  } catch (error) {
    fail(`RenderSpec validation failed\n${error instanceof Error ? error.message : error}`);
    return;
  }
  state.playbackRate = normalizePlaybackRate(ui.playbackRate.value);
  state.theme = readTheme(document.documentElement);
  state.viewport = createStage(ui.canvas, spec.stage);
  state.viewport.resize();
  state.renderer = createCanvas2DRenderer(state.viewport.ctx);

  // `?scene=N&step=N` opens the player at a given beat. Added for acceptance:
  // a headless screenshot can only capture whatever is on screen when it fires,
  // so without this the only frame anyone could look at was the first beat of
  // the first scene — which is exactly how "four identical rounded rectangles"
  // got recorded for one document and never checked in the other two.
  //
  // Out of range is clamped rather than rejected, here and in `setStep`: a bad
  // index in a URL should still show you a picture, not a blank page.
  const sceneIndex = Number(params.get("scene") ?? 0);
  const stepIndex = Number(params.get("step") ?? 0);
  loadScene(
    Number.isInteger(sceneIndex) ? Math.max(0, Math.min(spec.scenes.length - 1, sceneIndex)) : 0,
    Number.isInteger(stepIndex) ? stepIndex : 0,
  );
  bind();
  requestAnimationFrame(tick);
}

main().catch((error) => fail(error instanceof Error ? error.message : String(error)));
