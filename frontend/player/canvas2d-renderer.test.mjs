import assert from "node:assert/strict";
import test from "node:test";

import { resolveMotionAccent, resolveRenderableElement } from "./canvas2d-renderer.js";

function node(kind = "readout") {
  return {
    id: "message",
    kind,
    transform: {
      position: { x: 120, y: 80 },
      rotation: 30,
      scale: { x: 1, y: 1 },
      opacity: 0.5,
    },
    style: { tone: "accent", glowIntensity: 0 },
    visual: {
      id: "message",
      kind,
      x: 10,
      y: 20,
      text: "full text",
      visibleText: "full",
      points: [{ x: 0, y: 0 }, { x: 100, y: 0 }],
      drawProgress: 0.25,
    },
  };
}

test("Canvas2D renderer resolves text, position and path drawing from Scene State", () => {
  const element = resolveRenderableElement(node());
  assert.equal(element.x, 120);
  assert.equal(element.y, 80);
  assert.equal(element.text, "full");
  assert.equal(element.tone, "accent");
  assert.deepEqual(element.points, [{ x: 0, y: 0 }, { x: 25, y: 0 }]);
});

test("rotation-aware primitives receive runtime rotation without Canvas-specific IR", () => {
  const element = resolveRenderableElement(node("body"));
  assert.equal(element.heading, 30);
});

test("Canvas accents derive deterministic halos and path sparks from resolved state", () => {
  const focused = node("body");
  focused.style.glowIntensity = 0.8;
  const halo = resolveMotionAccent(focused);
  assert.equal(halo.kind, "halo");
  assert.equal(halo.x, 120);

  const flowing = node("link");
  flowing.style.glowIntensity = 1;
  const spark = resolveMotionAccent(flowing);
  assert.equal(spark.kind, "spark");
  assert.deepEqual(spark.point, { x: 25, y: 0 });
});
