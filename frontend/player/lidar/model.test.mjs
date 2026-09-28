import assert from "node:assert/strict";
import test from "node:test";
import { DEFAULTS, WORLD, START, GOAL, astar, center, cellAt, inflate, occupancy, observe, rayBox, scan, solve } from "./model.js";

test("laser returns the first surface and respects occlusion/range", () => {
  const boxes = [{ x: 200, y: 250, width: 24, height: 48 }, { x: 300, y: 250, width: 24, height: 48 }];
  assert.equal(rayBox(START, { x: 1, y: 0 }, boxes[0]), 92);
  assert.equal(scan(START, boxes, 400)[0].distance, 92);
  assert.equal(scan(START, boxes, 80)[0].hit, false);
  assert.equal(scan(START, boxes, 80)[0].distance, 80);
  assert.equal(rayBox(START, { x: 0, y: 1 }, boxes[0]), Infinity);
});

test("A* matches a BFS oracle; no diagonal edges or inflated collisions", () => {
  for (const preset of ["detour", "gap", "wall"]) for (const radius of [10, 16, 30]) {
    const result = solve({ ...DEFAULTS, preset, radius });
    const queue = [[cellAt(START), 0]];
    const seen = new Set([cellAt(START)]);
    let distance = Infinity;
    while (queue.length) {
      const [id, cost] = queue.shift();
      if (result.blocked.has(id)) continue;
      if (id === cellAt(GOAL)) { distance = cost; break; }
      const x = id % WORLD.cols, y = Math.floor(id / WORLD.cols);
      for (const [nx, ny] of [[x-1,y], [x+1,y], [x,y-1], [x,y+1]]) {
        if (nx < 0 || nx >= WORLD.cols || ny < 0 || ny >= WORLD.rows) continue;
        const next = ny * WORLD.cols + nx;
        if (!seen.has(next) && !result.blocked.has(next)) { seen.add(next); queue.push([next, cost+1]); }
      }
    }
    assert.equal(result.cost, distance);
    result.path.forEach((id, i) => {
      assert.ok(!result.blocked.has(id));
      if (i) assert.equal(Math.hypot(center(id).x-center(result.path[i-1]).x, center(id).y-center(result.path[i-1]).y), 24);
    });
  }
});

test("continuous route clears physical rectangles by the robot radius plus margin", () => {
  for (let obstacleY = 2; obstacleY <= 12; obstacleY += 2) {
    const result = solve({ ...DEFAULTS, obstacleY });
    assert.ok(result.path.length);
    for (let i = 1; i < result.path.length; i++) for (let t = 0; t <= 1; t += .1) {
      const a = center(result.path[i-1]), b = center(result.path[i]);
      const p = { x: a.x+(b.x-a.x)*t, y: a.y+(b.y-a.y)*t };
      for (const o of result.obstacles) {
        const distance = Math.hypot(Math.max(o.x-p.x, 0, p.x-o.x-o.width), Math.max(o.y-p.y, 0, p.y-o.y-o.height));
        assert.ok(distance > DEFAULTS.radius + DEFAULTS.margin);
      }
    }
  }
});

test("environment edits, larger footprint, no-route and unknown space have causal outcomes", () => {
  assert.notDeepEqual(solve(DEFAULTS).path, solve({ ...DEFAULTS, obstacleY: 2 }).path);
  assert.ok(solve({ ...DEFAULTS, preset: "gap", radius: 10 }).path.length);
  assert.equal(solve({ ...DEFAULTS, preset: "gap", radius: 30 }).path.length, 0);
  assert.equal(solve({ ...DEFAULTS, preset: "wall" }).path.length, 0);
  assert.equal(solve({ ...DEFAULTS, mode: "sensor", range: 180 }).path.length, 0);
  assert.deepEqual(solve(DEFAULTS), solve(DEFAULTS));
  assert.deepEqual(solve(DEFAULTS).path, solve({ ...DEFAULTS, range: 180 }).path);
  const small = inflate(occupancy(solve(DEFAULTS).obstacles), 10);
  const large = inflate(occupancy(solve(DEFAULTS).obstacles), 30);
  assert.ok([...small].every((id) => large.has(id)));
  assert.equal(astar(new Set(), cellAt(START), cellAt(START)).cost, 0);
});

test("scan-derived free cells never include a physical obstacle along the route", () => {
  for (const preset of ["detour", "gap"]) {
    const result = solve({ ...DEFAULTS, preset });
    for (const id of result.path) {
      const pose = center(id);
      const observation = observe(pose, scan(pose, result.obstacles, DEFAULTS.range));
      assert.ok([...observation.free].every((cell) => !result.occupied.has(cell)));
      assert.ok([...observation.occupied].every((cell) => result.occupied.has(cell)));
    }
  }
});
