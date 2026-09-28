/** Pure teaching computations. No random clock, DOM, network, or generated code. */
export const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));
export const dot = (a, b) => a.reduce((sum, value, i) => sum + value * b[i], 0);
export function softmax(values, temperature = 1) {
  const maximum = Math.max(...values);
  const exp = values.map((value) => Math.exp((value - maximum) / temperature));
  const total = exp.reduce((a, b) => a + b, 0);
  return exp.map((value) => value / total);
}

export function inferTokens(plan, ids, temperature, round = 0) {
  const vectors = ids.map((id) => [...plan.embeddings[id]]);
  const size = vectors[0].length;
  // Illustrative identity Q/K/V projection, one causal head, tied output embeddings.
  const attention = vectors.map((q, i) => {
    const weights = softmax(vectors.slice(0, i + 1).map((k) => dot(q, k) / Math.sqrt(size)));
    return [...weights, ...Array(vectors.length - i - 1).fill(0)];
  });
  const contexts = attention.map((weights) => Array.from({ length: size }, (_, dim) =>
    weights.reduce((sum, weight, i) => sum + weight * vectors[i][dim], 0)));
  const logits = plan.embeddings.map((row) => dot(row, contexts.at(-1)));
  const probabilities = softmax(logits, temperature);
  // A fixed quantile per round makes seeks and parameter comparisons reproducible.
  const quantile = ((round * 73 + 41) % 97) / 97;
  let accumulated = 0;
  let selected = probabilities.length - 1;
  for (let i = 0; i < probabilities.length; i++) {
    accumulated += probabilities[i];
    if (quantile < accumulated) { selected = i; break; }
  }
  return { ids, vectors, attention, contexts, logits, probabilities, selected, quantile };
}

export function neuron(plan, input = plan.inputs[0]) {
  const inputs = [input, plan.inputs[1]];
  const products = inputs.map((x, i) => x * plan.weights[i]);
  const z = products.reduce((a, b) => a + b, plan.bias);
  const activation = 1 / (1 + Math.exp(-z));
  const loss = .5 * (activation - plan.target) ** 2;
  const dz = (activation - plan.target) * activation * (1 - activation);
  const gradient = inputs.map((x) => dz * x);
  const nextWeights = plan.weights.map((w, i) => w - plan.learning_rate * gradient[i]);
  const nextBias = plan.bias - plan.learning_rate * dz;
  const nextActivation = 1 / (1 + Math.exp(-(dot(inputs, nextWeights) + nextBias)));
  return { inputs, products, z, activation, loss, gradient, nextWeights, nextBias,
    nextActivation, nextLoss: .5 * (nextActivation - plan.target) ** 2 };
}

export function transform(matrix, vector, blend = 1) {
  const effective = matrix.map((row, i) => row.map((v, j) =>
    (i === j ? 1 : 0) * (1 - blend) + v * blend));
  return { matrix: effective, vector: effective.map((row) => dot(row, vector)),
    determinant: effective[0][0] * effective[1][1] - effective[0][1] * effective[1][0] };
}

export function derivative(plan, x, h) {
  const [a, b, c] = plan.coefficients;
  const f = (v) => a * v * v + b * v + c;
  return { x, h, y: f(x), nextY: f(x + h), slope: a * (2 * x + h) + b,
    derivative: 2 * a * x + b, f };
}

export function packetTrace(plan, loss = plan.drop_first) {
  const d = plan.latency;
  const events = [];
  const send = (label, from, start, dropped = false) => events.push({
    label, from, to: from === "client" ? "server" : "client", start,
    end: start + d, dropped, type: "packet",
  });
  if (plan.protocol === "tcp_handshake") {
    send("SYN · seq=100", "client", 0, loss);
    const retryAt = loss ? 3 * d : 0;
    if (loss) {
      events.push({ type: "timeout", start: 3 * d, end: 3 * d, label: "SYN 超时" });
      send("SYN · seq=100 (重传)", "client", retryAt);
    }
    send("SYN+ACK · seq=500 ack=101", "server", retryAt + d);
    send("ACK · seq=101 ack=501", "client", retryAt + 2 * d);
  } else {
    send(`DATA #0 · ${plan.payload}`, "client", 0, loss);
    if (loss) {
      events.push({ type: "timeout", start: 3 * d, end: 3 * d, label: "未收到 ACK，超时" });
      send(`DATA #0 · ${plan.payload} (重传)`, "client", 3 * d);
    }
    send("ACK #0", "server", loss ? 4 * d : d);
  }
  return { events, duration: Math.max(...events.map((e) => e.end)), loss };
}

export function mechanismState(plan, beatIndex, progress, overrides = {}, sceneId = "") {
  const read = (name, fallback) => overrides[`${sceneId}-mechanism.${name}`] ?? fallback;
  const t = clamp(progress, 0, 1);
  const phase = plan.phases[beatIndex];
  if (!phase) throw new Error("Mechanism phase is missing for beat");
  if (plan.kind === "language_model") {
    const temperature = clamp(Number(read("temperature", plan.temperature)), .1, 2);
    let ids = [...plan.token_ids];
    let round = 0;
    for (const previous of plan.phases.slice(0, beatIndex)) {
      if (previous === "append") {
        ids.push(inferTokens(plan, ids, temperature, round++).selected);
      }
    }
    const state = inferTokens(plan, ids, temperature, round);
    return { ...state, phase, t, round, temperature,
      displayIds: phase === "append" && t >= .65 ? [...ids, state.selected] : ids };
  }
  if (plan.kind === "neural_network") return {
    ...neuron(plan, clamp(Number(read("input", plan.inputs[0])), -10, 10)), phase, t,
  };
  if (plan.kind === "linear_transform") {
    const blend = clamp(Number(read("blend", 1)), 0, 1) *
      (phase === "basis" ? 0 : phase === "transform" ? t : 1);
    return { ...transform(plan.matrix, plan.vector, blend), phase, t, blend };
  }
  if (plan.kind === "derivative") {
    const h = phase === "limit" ? plan.h * (1 - t) + .001 * t :
      phase === "tangent" ? .001 : plan.h;
    return { ...derivative(plan, clamp(Number(read("x", plan.x)), -2, 2), h), phase, t };
  }
  if (plan.kind === "packet_network") {
    const trace = packetTrace(plan, Boolean(read("loss", plan.drop_first)));
    const d = plan.latency;
    const starts = { send: 0, travel: .2 * d, ack: trace.loss ? 4 * d : d,
      timeout: trace.loss ? d : trace.duration, retransmit: trace.loss ? 3 * d : trace.duration,
      deliver: Math.max(0, trace.duration - d) };
    const ends = { send: .2 * d, travel: d,
      ack: plan.protocol === "tcp_handshake" ? trace.duration - d : trace.duration,
      timeout: trace.loss ? 3 * d : trace.duration,
      retransmit: trace.loss ? 4 * d : trace.duration, deliver: trace.duration };
    return { ...trace, phase, t, time: starts[phase] + (ends[phase] - starts[phase]) * t };
  }
  throw new Error(`Unsupported mechanism: ${plan.kind}`);
}
