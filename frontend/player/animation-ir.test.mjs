import assert from "node:assert/strict";
import test from "node:test";

import { normalizeRenderSpec, validateAnimationIR } from "./animation-ir.js";

function renderSpec() {
  return {
    spec_version: 1,
    storyboard_id: "storyboard-1",
    lesson_id: "lesson-1",
    document_id: "document-1",
    learning_intent: "How does a request reach the server?",
    title: "Controller",
    subject: "systems",
    eyebrow: "demo",
    stage: { width: 960, height: 600 },
    scenes: [{
      id: "scene-1",
      title: "Flow",
      teaching_goal: "Show the request flow",
      learning_question: "Which hop handles the request?",
      visual_pattern: "flow",
      claims: [{ id: "claim-1", text: "The server receives the request.", source_refs: ["evidence-1"] }],
      preset: "flow",
      attachment: { label: "server" },
      thresholds: {},
      params: { rate: 1 },
      elements: [{
        id: "server",
        kind: "body",
        role: "server",
        label: "Server",
        x: 100,
        y: 120,
        heading: 15,
        tone: "accent",
        props: { speed: 2 },
        binds: {},
        shape: "rect",
        width: 80,
        height: 50,
        path: [],
        duration: 0,
      }],
      steps: [{ id: "step-1", states: { server: { speed: 3 } }, highlights: ["server"] }],
      controls: [{ id: "rate", type: "slider", target_property: "scene.rate" }],
    }],
  };
}

test("RenderSpec v1 normalizes without losing compatibility data", () => {
  const source = renderSpec();
  const ir = normalizeRenderSpec(source);
  assert.equal(ir.irVersion, 1);
  assert.equal(ir.fps, 60);
  assert.equal(ir.metadata.storyboardId, "storyboard-1");
  assert.equal(ir.metadata.learningIntent, "How does a request reach the server?");
  assert.deepEqual(ir.stage, source.stage);
  assert.equal(ir.scenes[0].nodes[0].kind, "body");
  assert.deepEqual(ir.scenes[0].nodes[0].transform.position, { x: 100, y: 120 });
  assert.deepEqual(ir.scenes[0].legacy.steps, source.scenes[0].steps);
  assert.deepEqual(ir.scenes[0].interactions, source.scenes[0].controls);
  assert.equal(ir.scenes[0].beats.length, 1);
  assert.equal(ir.scenes[0].beats[0].id, "step-1");
  assert.equal(ir.scenes[0].beats[0].durationInFrames, 180);
  assert.equal(ir.scenes[0].nodes[0].parentId, null);
  assert.equal(ir.scenes[0].metadata.learningQuestion, "Which hop handles the request?");
  assert.equal(ir.scenes[0].metadata.visualPattern, "flow");
  assert.deepEqual(ir.scenes[0].metadata.claims, source.scenes[0].claims);
});

test("compiled beats are validated and preserved", () => {
  const source = renderSpec();
  const compiled = normalizeRenderSpec(source);
  compiled.metadata.sourceFormat = "storyboard-compiler-v1";
  compiled.scenes[0].beats = [{
    id: "step-1",
    title: "Observe",
    narration: "Watch the request move.",
    timeline: { items: [], effects: [] },
  }];
  source.animation_ir = compiled;

  assert.equal(normalizeRenderSpec(source).scenes[0].beats[0].id, "step-1");
  compiled.scenes[0].beats.push({ ...compiled.scenes[0].beats[0] });
  assert.throws(() => normalizeRenderSpec(source), /Duplicate animation beat id/);
});

test("normalization rejects unsupported versions and duplicate nodes", () => {
  assert.throws(() => normalizeRenderSpec({ ...renderSpec(), spec_version: 2 }), /Unsupported RenderSpec/);
  const ir = normalizeRenderSpec(renderSpec());
  ir.scenes[0].nodes.push({ ...ir.scenes[0].nodes[0] });
  assert.throws(() => validateAnimationIR(ir), /Duplicate animation node id/);
  assert.throws(() => validateAnimationIR({ ...normalizeRenderSpec(renderSpec()), fps: 0 }), /fps must/);
});

test("normalization prefers validated compiler output and rejects mismatched payloads", () => {
  const source = renderSpec();
  const compiled = normalizeRenderSpec(source);
  compiled.metadata.sourceFormat = "storyboard-compiler-v1";
  source.animation_ir = compiled;

  const normalized = normalizeRenderSpec(source);
  assert.deepEqual(normalized, compiled);
  assert.equal(normalized.metadata.sourceFormat, "storyboard-compiler-v1");

  source.animation_ir = { ...compiled, stage: { width: 1, height: 1 } };
  assert.throws(() => normalizeRenderSpec(source), /stage does not match/);
});

test("v1 rejects hierarchy until scene graph evaluation exists", () => {
  const ir = normalizeRenderSpec(renderSpec());
  ir.scenes[0].nodes[0].parentId = "root";
  assert.throws(() => validateAnimationIR(ir), /does not yet enable parentId/);
});
