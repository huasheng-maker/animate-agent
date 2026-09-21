import assert from "node:assert/strict";
import test from "node:test";
import gsapPackage from "gsap";

import { registerGsap } from "./gsap-easing.js";
import { compileTimeline, sampleTimeline, sampleTimelineFrame } from "./timeline.js";

registerGsap(gsapPackage.gsap ?? gsapPackage.default ?? gsapPackage);

const nodes = [
  { id: "box", kind: "body" },
  { id: "path", kind: "path" },
  { id: "label", kind: "text" },
];

const target = (id) => ({ type: "node", id });
const track = (id, property, from, to, duration = 2, extra = {}) => ({
  target: target(id),
  property,
  keyframes: [{ time: 0, value: from }, { time: duration, value: to, ...extra }],
});

test("timeline interpolates generic number, vector, color and discrete channels", () => {
  const compiled = compileTimeline({ items: [
    track("box", "transform.position", { x: 0, y: 10 }, { x: 20, y: 30 }),
    track("box", "style.glowIntensity", 0, 1),
    track("box", "style.fill", "#000000", "#ffffff"),
    track("box", "style.highlight", false, true),
  ] }, nodes);
  const values = new Map(sampleTimeline(compiled, 1).map((patch) => [patch.property, patch.value]));
  assert.deepEqual(values.get("transform.position"), { x: 10, y: 20 });
  assert.equal(values.get("style.glowIntensity"), 0.5);
  assert.equal(values.get("style.fill"), "rgba(128, 128, 128, 1)");
  assert.equal(values.get("style.highlight"), false);
  assert.equal(sampleTimeline(compiled, 2).find((patch) => patch.property === "style.highlight").value, true);
});

test("delay, easing, sequence and parallel compile to deterministic absolute time", () => {
  const compiled = compileTimeline({ items: [{
    type: "sequence",
    delay: 1,
    children: [
      track("box", "transform.opacity", 0, 1, 2, { easing: "easeIn" }),
      { type: "parallel", children: [
        track("box", "transform.rotation", 0, 90, 1),
        track("path", "visual.drawProgress", 0, 1, 3),
      ] },
    ],
  }] }, nodes);
  assert.equal(compiled.duration, 6);
  assert.equal(sampleTimeline(compiled, 0.5).length, 0);
  assert.equal(sampleTimeline(compiled, 2).find((patch) => patch.property === "transform.opacity").value, 0.25);
  assert.equal(sampleTimeline(compiled, 3.5).find((patch) => patch.property === "transform.rotation").value, 45);
});

test("an explicit duration scales authored keyframe timing", () => {
  const item = track("box", "transform.rotation", 0, 90, 1);
  item.duration = 4;
  const compiled = compileTimeline({ items: [item] }, nodes);
  assert.equal(compiled.duration, 4);
  assert.equal(sampleTimeline(compiled, 2)[0].value, 45);
});

test("frame sampling is deterministic and keeps seconds as a compatibility view", () => {
  const compiled = compileTimeline({ items: [
    track("box", "transform.opacity", 0, 1, 1),
  ] }, nodes, { fps: 30 });
  assert.equal(compiled.fps, 30);
  assert.equal(compiled.durationInFrames, 31);
  assert.equal(sampleTimelineFrame(compiled, 30)[0].value, 1);
  assert.equal(sampleTimelineFrame(compiled, 15)[0].value, 0.5);
  assert.deepEqual(sampleTimelineFrame(compiled, 15), sampleTimeline(compiled, 0.5));
  assert.throws(() => sampleTimelineFrame(compiled, 1.5), /non-negative integer/);
});

test("GSAP eases add expressive overshoot while sampling remains deterministic", () => {
  const compiled = compileTimeline({ items: [
    track("box", "transform.scale", { x: 1, y: 1 }, { x: 1.1, y: 1.1 }, 1, { easing: "backOut" }),
  ] }, nodes);
  const first = sampleTimeline(compiled, 0.7)[0].value;
  const second = sampleTimeline(compiled, 0.7)[0].value;
  assert.deepEqual(first, second);
  assert.ok(first.x > 1.1);
});

test("a Python-authored null duration uses keyframe timing", () => {
  const item = track("box", "transform.opacity", 0, 1, 1.25);
  item.duration = null;
  const compiled = compileTimeline({ items: [item] }, nodes);
  assert.equal(compiled.duration, 1.25);
  assert.equal(sampleTimeline(compiled, 0.625)[0].value, 0.5);
});

test("invalid channels, values, targets and overlapping tracks fail at compile time", () => {
  assert.throws(() => compileTimeline({ items: [track("box", "canvas.lineWidth", 0, 1)] }, nodes), /Unknown animatable property/);
  assert.throws(() => compileTimeline({ items: [track("missing", "transform.opacity", 0, 1)] }, nodes), /Unknown animation target/);
  assert.throws(() => compileTimeline({ items: [track("box", "transform.position", 0, 1)] }, nodes), /must be a vec2/);
  assert.throws(() => compileTimeline({ items: [track("box", "transform.opacity", 0, 2)] }, nodes), /must be at most 1/);
  assert.throws(() => compileTimeline({ items: [track("box", "visual.revealProgress", 0, 1)] }, nodes), /not supported by node kind/);
  assert.throws(() => compileTimeline({ items: [
    track("box", "transform.opacity", 0, 1, 2),
    { ...track("box", "transform.opacity", 1, 0, 2), delay: 1 },
  ] }, nodes), /Overlapping tracks/);
});
