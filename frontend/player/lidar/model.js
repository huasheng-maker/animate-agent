// Deterministic teaching model. Units are canvas pixels; 60 px = 1 metre.
export const WORLD = { width: 864, height: 528, cell: 24, cols: 36, rows: 22 };
export const START = { x: 108, y: 276 };
export const GOAL = { x: 756, y: 276 };
export const FPS = 30;
export const DURATION = 720;
export const PHASE_FRAMES = [0, 120, 240, 360];
export const DEFAULTS = { obstacleY: 7, radius: 16, margin: 6, range: 660, mode: "known", preset: "detour" };
const key = (x, y) => y * WORLD.cols + x;
export const center = (id) => ({ x: (id % WORLD.cols + 0.5) * WORLD.cell, y: (Math.floor(id / WORLD.cols) + 0.5) * WORLD.cell });
export const cellAt = (p) => key(Math.floor(p.x / WORLD.cell), Math.floor(p.y / WORLD.cell));

export function obstaclesFor(settings) {
  const rect = (id, x, y, w, h) => ({ id, x: x * 24, y: y * 24, width: w * 24, height: h * 24 });
  if (settings.preset === "wall") return [rect("wall", 17, 0, 2, 22)];
  if (settings.preset === "gap") return [rect("upper", 17, 0, 2, 9), rect("lower", 17, 13, 2, 9)];
  return [rect("movable", 16, settings.obstacleY, 3, 8), rect("shelf", 25, 15, 4, 4), rect("crate", 25, 3, 3, 3)];
}

// Slab intersection: nearest positive hit, never a centre-to-centre distance.
export function rayBox(origin, direction, box) {
  let near = -Infinity;
  let far = Infinity;
  for (const axis of ["x", "y"]) {
    const size = axis === "x" ? box.width : box.height;
    if (Math.abs(direction[axis]) < 1e-10) {
      if (origin[axis] < box[axis] || origin[axis] > box[axis] + size) return Infinity;
    } else {
      const a = (box[axis] - origin[axis]) / direction[axis];
      const b = (box[axis] + size - origin[axis]) / direction[axis];
      near = Math.max(near, Math.min(a, b));
      far = Math.min(far, Math.max(a, b));
    }
  }
  return far >= Math.max(near, 0) ? Math.max(near, 0) : Infinity;
}

export function scan(origin, obstacles, range, count = 180) {
  return Array.from({ length: count }, (_, i) => {
    const angle = i * Math.PI * 2 / count;
    const direction = { x: Math.cos(angle), y: Math.sin(angle) };
    let distance = range;
    let hit = false;
    for (const box of obstacles) {
      const candidate = rayBox(origin, direction, box);
      if (candidate <= distance) { distance = candidate; hit = true; }
    }
    // The room boundary also returns a measurement.
    const dx = direction.x > 0 ? (WORLD.width - origin.x) / direction.x : -origin.x / direction.x;
    const dy = direction.y > 0 ? (WORLD.height - origin.y) / direction.y : -origin.y / direction.y;
    const wall = Math.min(dx > 0 ? dx : Infinity, dy > 0 ? dy : Infinity);
    if (wall <= distance) { distance = wall; hit = true; }
    return { angle, distance, hit, x: origin.x + direction.x * distance, y: origin.y + direction.y * distance };
  });
}

export function observe(origin, rays) {
  const free = new Set();
  const occupied = new Set();
  for (const ray of rays) {
    // Obstacles occupy whole cells in this deliberately discrete model.
    for (let d = 0; d < ray.distance - 0.01; d += 3) {
      const p = { x: origin.x + Math.cos(ray.angle) * d, y: origin.y + Math.sin(ray.angle) * d };
      if (p.x >= 0 && p.y >= 0 && p.x < WORLD.width && p.y < WORLD.height) free.add(cellAt(p));
    }
    const p = { x: ray.x + Math.cos(ray.angle) * 0.01, y: ray.y + Math.sin(ray.angle) * 0.01 };
    if (ray.hit && p.x >= 0 && p.y >= 0 && p.x < WORLD.width && p.y < WORLD.height) occupied.add(cellAt(p));
  }
  occupied.forEach((id) => free.delete(id));
  return { free, occupied };
}

export function occupancy(obstacles) {
  const result = new Set();
  for (let id = 0; id < WORLD.cols * WORLD.rows; id++) {
    const p = center(id);
    if (obstacles.some((o) => p.x >= o.x && p.x < o.x + o.width && p.y >= o.y && p.y < o.y + o.height)) result.add(id);
  }
  return result;
}

export function inflate(occupied, clearance) {
  const blocked = new Set();
  const cells = [...occupied].map(center);
  // Extra half-cell protects every point of a four-neighbour edge, not only its endpoints.
  const pad = clearance + WORLD.cell / 2;
  for (let id = 0; id < WORLD.cols * WORLD.rows; id++) {
    const p = center(id);
    if (p.x <= pad || p.y <= pad || WORLD.width - p.x <= pad || WORLD.height - p.y <= pad || cells.some((o) => Math.hypot(Math.max(0, Math.abs(p.x - o.x) - 12), Math.max(0, Math.abs(p.y - o.y) - 12)) <= pad)) blocked.add(id);
  }
  return blocked;
}

export function astar(blocked, start = cellAt(START), goal = cellAt(GOAL), heuristic = true) {
  const expanded = [];
  const visits = [];
  if (blocked.has(start) || blocked.has(goal)) return { path: [], expanded, visits, cost: Infinity };
  const h = (id) => heuristic ? Math.abs(id % WORLD.cols - goal % WORLD.cols) + Math.abs(Math.floor(id / WORLD.cols) - Math.floor(goal / WORLD.cols)) : 0;
  const open = new Set([start]);
  const closed = new Set();
  const costs = new Map([[start, 0]]);
  const parents = new Map();
  while (open.size) {
    const id = [...open].sort((a, b) => (costs.get(a) + h(a)) - (costs.get(b) + h(b)) || h(a) - h(b) || a - b)[0];
    open.delete(id);
    expanded.push(id);
    visits.push({ id, g: costs.get(id), h: h(id), f: costs.get(id) + h(id) });
    if (id === goal) {
      const path = [id];
      while (parents.has(path[0])) path.unshift(parents.get(path[0]));
      return { path, expanded, visits, cost: costs.get(id) ?? Infinity };
    }
    closed.add(id);
    const x = id % WORLD.cols;
    const y = Math.floor(id / WORLD.cols);
    for (const [nx, ny] of [[x + 1, y], [x, y + 1], [x - 1, y], [x, y - 1]]) {
      if (nx < 0 || ny < 0 || nx >= WORLD.cols || ny >= WORLD.rows) continue;
      const next = key(nx, ny);
      if (blocked.has(next) || closed.has(next)) continue;
      const cost = costs.get(id) + 1;
      if (cost < (costs.get(next) ?? Infinity)) { costs.set(next, cost); parents.set(next, id); open.add(next); }
    }
  }
  return { path: [], expanded, visits, cost: Infinity };
}

export function solve(settings) {
  const obstacles = obstaclesFor(settings);
  const rays = scan(START, obstacles, settings.range);
  const observed = observe(START, rays);
  const occupied = occupancy(obstacles);
  // In sensor-only mode, UNKNOWN is not FREE. No hidden truth enters planning.
  const plannerOccupied = settings.mode === "known" ? occupied : new Set(Array.from({ length: WORLD.cols * WORLD.rows }, (_, id) => id).filter((id) => !observed.free.has(id)));
  const blocked = inflate(plannerOccupied, settings.radius + settings.margin);
  return { obstacles, rays, observed, occupied, blocked, ...astar(blocked) };
}

export function phaseAt(frame) { return frame < 120 ? 0 : frame < 240 ? 1 : frame < 360 ? 2 : 3; }
