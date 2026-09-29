// Trusted adapters over math.js; deliberately do not expose its expression parser.
import { add, subtract, dotMultiply, divide, multiply, dot, norm, transpose, sum } from "mathjs";

const checked = (value) => {
  const values = Array.isArray(value) ? value.flat() : [value];
  if (values.length > 256 || values.some((x) => typeof x !== "number" || !Number.isFinite(x) || Math.abs(x) > 1e12))
    throw new Error("Calculation produced nonfinite or oversized data");
  return value;
};
const index = (data, i) => {
  if (!Number.isInteger(i) || i < 0 || i >= data.length) throw new Error("Lookup index out of range");
  return data[i];
};
const ratio = (a, b) => {
  if (b === 0) throw new Error("Division by zero");
  return divide(a, b);
};
export const OPERATIONS = Object.freeze({
  add, subtract, multiply: dotMultiply, divide: ratio, matmul: multiply, dot, norm,
  normalize: (a) => ratio(a, norm(a)), sin: Math.sin, cos: Math.cos, exp: Math.exp,
  sigmoid: (x) => x >= 0 ? 1 / (1 + Math.exp(-x)) : Math.exp(x) / (1 + Math.exp(x)),
  tanh: Math.tanh, transpose, sum,
  softmax: (a) => { const exp = a.map((x) => Math.exp(x - Math.max(...a))); return divide(exp, sum(exp)); },
  vector: (...args) => args, stack: (...args) => args, row: index, item: index,
  concat: (...args) => args.flat(),
  lerp: (a, b, t) => add(a, dotMultiply(subtract(b, a), t)),
  less: (a, b) => Number(a < b), select: (condition, yes, no) => condition ? yes : no,
  floor: Math.floor, clamp: (x, low, high) => Math.min(high, Math.max(low, x)),
  argmax: (a) => a.indexOf(Math.max(...a)),
});

export function evaluateProgram(plan, { time = 0, progress = 0, phase = 0, sample = 0, overrides = {}, sceneId = "" } = {}) {
  if (plan.kind !== "composition" || !Array.isArray(plan.nodes) || plan.nodes.length > 64)
    throw new Error("Invalid composition plan");
  const byId = new Map(plan.nodes.map((n) => [n.id, n]));
  if (byId.size !== plan.nodes.length) throw new Error("Duplicate calculation id");
  const values = Object.create(null), visiting = new Set();
  const clocks = { time, progress, phase, sample };
  function run(id) {
    if (Object.hasOwn(values, id)) return values[id];
    const node = byId.get(id);
    if (!node || visiting.has(id)) throw new Error(`Missing input or cycle: ${id}`);
    visiting.add(id);
    let result;
    if (node.op === "constant") result = node.value;
    else if (node.op === "parameter") {
      const supplied = overrides[`${sceneId}-program.${id}`] ?? node.value;
      result = Math.min(node.max, Math.max(node.min, Number(supplied)));
    } else if (Object.hasOwn(clocks, node.op)) result = clocks[node.op];
    else {
      if (!Object.hasOwn(OPERATIONS, node.op)) throw new Error(`Unknown operation: ${node.op}`);
      const args = node.args.map(run);
      try { result = OPERATIONS[node.op](...args); }
      catch (error) { throw new Error(`${id} (${node.op}): ${error.message}`); }
    }
    values[id] = checked(result);
    visiting.delete(id);
    return values[id];
  }
  for (const node of plan.nodes) run(node.id);
  return values;
}

export function sampleVisual(plan, view, context) {
  const count = 48;
  return Array.from({ length: count + 1 }, (_, i) => {
    const f = i / count;
    const override = view.kind === "trail"
      ? { time: Math.max(0, context.time - view.trail_seconds * (1 - f)) }
      : { sample: view.sample_range[0] + f * (view.sample_range[1] - view.sample_range[0]) };
    return evaluateProgram(plan, { ...context, ...override })[view.data];
  });
}
