import assert from "node:assert/strict";
import test from "node:test";

import { createSimulation } from "./behaviors.js";

function scene() {
  return {
    elements: [{
      id: "body",
      kind: "body",
      role: "subject",
      x: 10,
      y: 20,
      heading: 0,
      props: { speed: 1 },
    }],
    thresholds: {},
    attachment: {},
  };
}

test("legacy simulation can seek to the same frame in any order", () => {
  const simulation = createSimulation(scene(), { width: 1000, height: 500 });
  const lookup = (_id, property, fallback) => property === "speed" ? 1 : fallback;
  simulation.seekFrame(30, 30, lookup, 0);
  const first = structuredClone(simulation.live.get("body"));
  simulation.seekFrame(60, 30, lookup, 0);
  simulation.seekFrame(30, 30, lookup, 0);
  assert.deepEqual(simulation.live.get("body"), first);
  assert.equal(simulation.t, 1);
  assert.equal(first.x, 100);
});

test("changing a control revision recomputes the requested frame", () => {
  const simulation = createSimulation(scene(), { width: 1000, height: 500 });
  let speed = 1;
  const lookup = (_id, property, fallback) => property === "speed" ? speed : fallback;
  simulation.seekFrame(30, 30, lookup, 0);
  assert.equal(simulation.live.get("body").x, 100);
  speed = 2;
  simulation.seekFrame(30, 30, lookup, 1);
  assert.equal(simulation.live.get("body").x, 190);
});
