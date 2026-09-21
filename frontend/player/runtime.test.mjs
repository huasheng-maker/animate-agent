import assert from "node:assert/strict";
import test from "node:test";

import { compileEffects } from "./effects.js";
import { createAnimationRuntime } from "./runtime.js";

function node(id, kind, visual = {}) {
  return {
    id,
    kind,
    parentId: null,
    transform: {
      position: { x: 0, y: 0 }, rotation: 0, scale: { x: 1, y: 1 }, opacity: 1, pathProgress: 0,
    },
    style: { highlight: false, glowIntensity: 0 },
    visual: { originalText: "", revealProgress: 1, ...visual },
    semantic: { progress: 0, intensity: 0, phase: "idle" },
  };
}

function scene(items = [], effects = []) {
  return {
    id: "scene",
    nodes: [
      node("mover", "body", { path: [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }], orientToPath: true }),
      node("line", "path", { path: [{ x: 0, y: 0 }, { x: 10, y: 0 }], drawProgress: 0 }),
      node("label", "text", { originalText: "hello", visibleText: "hello", revealProgress: 1 }),
    ],
    camera: { id: "main", position: { x: 0, y: 0 }, zoom: 1, rotation: 0 },
    timeline: { items, effects },
    interactions: [],
  };
}

const animation = (target, property, from, to, duration = 2) => ({
  target: { type: target === "main" ? "camera" : "node", id: target },
  property,
  keyframes: [{ time: 0, value: from }, { time: duration, value: to }],
});

test("runtime resolves path motion, text reveal, path drawing, camera and semantic state", () => {
  const runtime = createAnimationRuntime(scene([
    animation("mover", "transform.pathProgress", 0, 1),
    animation("label", "visual.revealProgress", 0, 1),
    animation("line", "visual.drawProgress", 0, 1),
    animation("main", "camera.zoom", 1, 2),
    animation("mover", "semantic.intensity", 0, 1),
  ]));
  const first = runtime.seek(1);
  const second = runtime.seek(1);
  assert.deepEqual(first.nodes, second.nodes);
  assert.deepEqual(first.nodeById.get("mover").transform.position, { x: 10, y: 0 });
  assert.equal(first.nodeById.get("mover").transform.rotation, 90);
  assert.equal(first.nodeById.get("label").visual.visibleText, "he");
  assert.equal(first.nodeById.get("line").visual.drawProgress, 0.5);
  assert.equal(first.camera.zoom, 1.5);
  assert.equal(first.nodeById.get("mover").semantic.intensity, 0.5);
});

test("runtime resolves an integer frame independently of prior seeks", () => {
  const runtime = createAnimationRuntime(scene([
    animation("mover", "transform.position", { x: 0, y: 0 }, { x: 30, y: 60 }, 1),
  ]), { fps: 30 });
  const atFrame15 = runtime.seekFrame(15);
  runtime.seekFrame(29);
  assert.deepEqual(runtime.seekFrame(15), atFrame15);
  assert.equal(atFrame15.time, 0.5);
  assert.equal(atFrame15.frame, 15);
  assert.equal(atFrame15.fps, 30);
  assert.deepEqual(atFrame15.nodeById.get("mover").transform.position, { x: 15, y: 30 });
  assert.deepEqual(atFrame15.nodes, runtime.seek(0.5).nodes);
});

test("semantic effects compile to the same controlled tracks used by the runtime", () => {
  const effects = [
    { effect: "fadeIn", target: "mover", duration: 2 },
    { effect: "drawPath", target: "line", duration: 2 },
    { effect: "typeWriter", target: "label", duration: 2 },
    { effect: "cameraPan", camera: "main", from: { x: 0, y: 0 }, to: { x: 20, y: 10 }, duration: 2 },
  ];
  const direct = createAnimationRuntime(scene(compileEffects(effects))).seek(1);
  const compiled = createAnimationRuntime(scene([], effects)).seek(1);
  assert.deepEqual(compiled.nodes, direct.nodes);
  assert.deepEqual(compiled.camera, direct.camera);
  assert.equal(compiled.nodeById.get("mover").transform.opacity, 0.5);
  assert.deepEqual(compiled.camera.position, { x: 10, y: 5 });
});

test("user controlled property overrides outrank timeline and unsupported effects fail", () => {
  const runtime = createAnimationRuntime(scene([animation("mover", "transform.opacity", 0, 1)]));
  runtime.setPropertyOverride({ type: "node", id: "mover" }, "transform.opacity", 0.9);
  assert.equal(runtime.seek(1).nodeById.get("mover").transform.opacity, 0.9);
  assert.throws(
    () => createAnimationRuntime(scene([], [{ effect: "traceFlow", from: "a", to: "b", duration: 1 }])),
    /reserved but not implemented/,
  );
});

test("setStep selects a replayable beat timeline", () => {
  const input = scene();
  input.beats = [
    { id: "quiet", timeline: { items: [animation("mover", "transform.opacity", 0, 1, 2)], effects: [] } },
    { id: "focus", timeline: { items: [animation("mover", "semantic.intensity", 0, 1, 2)], effects: [] } },
  ];
  const runtime = createAnimationRuntime(input);
  assert.equal(runtime.seek(1).nodeById.get("mover").transform.opacity, 0.5);
  runtime.setStep(1);
  const focused = runtime.seek(1).nodeById.get("mover");
  assert.equal(focused.transform.opacity, 1);
  assert.equal(focused.semantic.intensity, 0.5);
});

test("pulse, followPath and cameraZoom expand through the controlled registry", () => {
  const input = scene([], [
    { effect: "pulse", target: "mover", duration: 2 },
    { effect: "followPath", target: "mover", duration: 2 },
    { effect: "cameraZoom", camera: "main", to: 1.4, duration: 2 },
  ]);
  const middle = createAnimationRuntime(input).seek(1);
  assert.ok(middle.nodeById.get("mover").transform.scale.x > 1);
  assert.deepEqual(middle.nodeById.get("mover").transform.position, { x: 10, y: 0 });
  assert.equal(middle.camera.zoom, 1.2);
});
