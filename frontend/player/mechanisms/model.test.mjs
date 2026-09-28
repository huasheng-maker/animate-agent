import assert from "node:assert/strict";
import test from "node:test";
import { derivative, inferTokens, mechanismState, neuron, packetTrace, transform } from "./model.js";

const llm = { kind: "language_model", vocabulary: ["A", "B", "C"],
  token_ids: [0, 1], embeddings: [[1, 0], [0, 1], [1, 1]], temperature: 1,
  phases: ["embedding", "attention", "predict", "append", "predict", "append"] };

test("embedding lookup and causal attention compute bounded normalized distributions", () => {
  const s = inferTokens(llm, [0, 1], 1);
  assert.deepEqual(s.vectors, [[1, 0], [0, 1]]);
  assert.equal(s.attention[0][1], 0);
  for (const row of [...s.attention, s.probabilities])
    assert.ok(Math.abs(row.reduce((a, b) => a + b, 0) - 1) < 1e-12);
  assert.notDeepEqual(inferTokens(llm, [0, 1], .1).probabilities, s.probabilities);
});
test("two autoregressive rounds append computed tokens and reconstruct identical seek state", () => {
  const first = mechanismState(llm, 3, 1);
  const second = mechanismState(llm, 5, 1);
  assert.equal(first.displayIds.length, 3);
  assert.equal(second.displayIds.length, 4);
  assert.deepEqual(second.ids, first.displayIds);
  mechanismState(llm, 0, .2);
  assert.deepEqual(mechanismState(llm, 5, 1), second);
  assert.notDeepEqual(mechanismState(llm, 2, 1, { "s-mechanism.temperature": .1 }, "s").probabilities,
    mechanismState(llm, 2, 1).probabilities);
});
test("analytical neuron gradient matches finite difference and update reduces loss", () => {
  const plan = { inputs: [1, .5], weights: [.8, -.4], bias: .1, target: 1, learning_rate: .5 };
  const s = neuron(plan), eps = 1e-5;
  const next = neuron({ ...plan, weights: [plan.weights[0] + eps, plan.weights[1]] });
  assert.ok(Math.abs((next.loss - s.loss) / eps - s.gradient[0]) < 1e-5);
  assert.ok(s.nextLoss < s.loss);
  assert.notEqual(neuron(plan, -1).activation, s.activation);
});
test("matrix transformation and determinant reflect parameters", () => {
  assert.deepEqual(transform([[1, 2], [0, 1]], [1, 1]).vector, [3, 1]);
  assert.deepEqual(transform([[1, 2], [0, 1]], [1, 1], 0).vector, [1, 1]);
  assert.equal(transform([[0, 1], [1, 0]], [1, 1]).determinant, -1);
});
test("quadratic secant converges to analytical derivative", () => {
  const plan = { coefficients: [2, 3, 1] };
  const wide = derivative(plan, 1, 1), narrow = derivative(plan, 1, .001);
  assert.equal(narrow.derivative, 7);
  assert.ok(Math.abs(narrow.slope - 7) < Math.abs(wide.slope - 7));
});
test("loss schedules timeout then same-sequence retransmission and acknowledgement", () => {
  const plan = { protocol: "stop_and_wait", latency: 1, payload: "hello", drop_first: true };
  const lost = packetTrace(plan), good = packetTrace(plan, false);
  assert.equal(lost.events[0].dropped, true);
  assert.equal(lost.events[1].type, "timeout");
  assert.match(lost.events[2].label, /DATA #0/);
  assert.equal(lost.events[3].label, "ACK #0");
  assert.equal(good.events.length, 2);
  assert.ok(lost.duration > good.duration);
  const tcp = packetTrace({ ...plan, protocol: "tcp_handshake" }, false);
  assert.deepEqual(tcp.events.map((e) => e.label), ["SYN · seq=100", "SYN+ACK · seq=500 ack=101", "ACK · seq=101 ack=501"]);
});
