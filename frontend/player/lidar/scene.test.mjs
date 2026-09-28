import assert from "node:assert/strict";
import test from "node:test";
import { validateAnimationIR } from "../animation-ir.js";
import { DEFAULTS, GOAL, START, solve } from "./model.js";
import { createDemoScene } from "./scene.js";

test("domain adapter produces valid IR and deterministic forward/backward seeks", () => {
  const { ir, runtime } = createDemoScene(solve(DEFAULTS));
  validateAnimationIR(ir);
  const position = (frame) => runtime.seekFrame(frame).nodeById.get("robot").transform.position;
  assert.deepEqual(position(0), START);
  assert.deepEqual(position(359), START);
  const middle = position(510);
  assert.notDeepEqual(middle, START);
  assert.deepEqual(position(690), GOAL);
  assert.deepEqual(position(510), middle);
  assert.deepEqual(position(0), START);
});

test("no route never creates movement; edits replace the planned trajectory", () => {
  const blocked = createDemoScene(solve({ ...DEFAULTS, preset: "wall" }));
  assert.deepEqual(blocked.runtime.seekFrame(719).nodeById.get("robot").transform.position, START);
  const before = createDemoScene(solve(DEFAULTS));
  const after = createDemoScene(solve({ ...DEFAULTS, obstacleY: 2 }));
  assert.notDeepEqual(before.runtime.seekFrame(510).nodes, after.runtime.seekFrame(510).nodes);
});
