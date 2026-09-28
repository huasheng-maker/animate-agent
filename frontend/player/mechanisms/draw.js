import { mechanismState } from "./model.js";

const C = { ink: "#e6edf5", muted: "#8ba4b8", teal: "#64ded2", gold: "#ffc779",
  violet: "#b4a0ff", red: "#ff8992", panel: "#112938", grid: "#24414e" };
const fmt = (n) => Number(n).toFixed(2);
function text(ctx, value, x, y, size = 16, color = C.ink) {
  ctx.fillStyle = color; ctx.font = `${size}px system-ui, sans-serif`;
  ctx.fillText(String(value), x, y);
}
function line(ctx, x, y, x2, y2, color = C.grid, width = 2) {
  ctx.strokeStyle = color; ctx.lineWidth = width;
  ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x2, y2); ctx.stroke();
}
function arrow(ctx, x, y, x2, y2, color = C.teal) {
  line(ctx, x, y, x2, y2, color, 3);
  const angle = Math.atan2(y2 - y, x2 - x);
  line(ctx, x2, y2, x2 - 9 * Math.cos(angle - .5), y2 - 9 * Math.sin(angle - .5), color, 3);
  line(ctx, x2, y2, x2 - 9 * Math.cos(angle + .5), y2 - 9 * Math.sin(angle + .5), color, 3);
}
function box(ctx, x, y, w, h, color = C.panel) {
  ctx.fillStyle = color; ctx.beginPath(); ctx.roundRect(x, y, w, h, 7); ctx.fill();
}
function matrix(ctx, values, x, y, cell = 42, highlight = -1, labels = []) {
  values.forEach((row, i) => row.forEach((v, j) => {
    const alpha = Math.min(.85, .18 + Math.abs(v) * .35);
    ctx.fillStyle = i === highlight ? `rgba(100,222,210,${alpha})` :
      v < 0 ? `rgba(180,160,255,${alpha})` : `rgba(88,137,177,${alpha})`;
    ctx.fillRect(x + j * cell, y + i * cell, cell - 3, cell - 3);
    text(ctx, fmt(v), x + j * cell + 4, y + i * cell + cell * .62, Math.min(13, cell * .3));
  }));
  labels.forEach((label, i) => text(ctx, label, x - 64, y + i * cell + cell * .6, 13,
    i === highlight ? C.teal : C.muted));
}

function language(ctx, plan, s) {
  const color = [C.teal, C.gold, C.violet, C.red, "#94c7ff", "#e1d293", "#b9e395", "#ecc2ff"];
  const tokenW = Math.min(104, 860 / Math.max(5, s.displayIds.length));
  s.displayIds.forEach((id, i) => {
    box(ctx, 45 + i * tokenW, 70, tokenW - 7, 46, C.panel);
    const token = plan.vocabulary[id];
    text(ctx, token.length > 8 ? `${token.slice(0, 7)}…` : token,
      54 + i * tokenW, 92, 17, color[id]);
    text(ctx, `id ${id}`, 54 + i * tokenW, 109, 11, C.muted);
  });
  text(ctx, `第 ${s.round + 1} 轮 · ${s.ids.length} 个上下文 token`, 45, 143, 15, C.muted);
  if (s.phase === "tokens") {
    text(ctx, "文本 → token → 词表 ID", 85, 220, 30);
    text(ctx, "教学词表按卡片分词；实际 tokenizer 可拆分为子词。", 85, 265, 18, C.muted);
    arrow(ctx, 100, 315, 100 + 640 * s.t, 315);
    return;
  }
  if (s.phase === "embedding") {
    const row = Math.min(s.ids.length - 1, Math.floor(s.t * s.ids.length));
    const selected = s.ids[row];
    const cell = Math.min(44, 250 / plan.embeddings.length, 330 / plan.embeddings[0].length);
    text(ctx, "嵌入表 E · 每个 ID 对应一行", 110, 176, 18);
    matrix(ctx, plan.embeddings, 110, 195, cell, selected, plan.vocabulary);
    const startX = 110 + cell * plan.embeddings[0].length;
    const startY = 195 + selected * cell + cell / 2;
    const p = Math.min(1, s.t * s.ids.length - row);
    arrow(ctx, startX + 15, startY, 480, 235);
    text(ctx, `${plan.vocabulary[selected]} → E[${selected}]`, 510, 205, 22, color[selected]);
    matrix(ctx, [plan.embeddings[selected]], 510, 225, Math.min(44, 350 / plan.embeddings[0].length), 0);
    text(ctx, "按 ID 查表 → 将向量堆叠成输入矩阵", 510, 305, 18, C.muted);
    ctx.save(); ctx.globalAlpha = .65;
    matrix(ctx, [plan.embeddings[selected]], 110 + 400 * p,
      195 + selected * cell + (30 - selected * cell) * p,
      cell + (Math.min(44, 350 / plan.embeddings[0].length) - cell) * p, 0);
    ctx.restore();
    if (row > 0) matrix(ctx, s.vectors.slice(0, row), 510, 325, 23, -1);
    return;
  }
  if (s.phase === "attention") {
    const count = s.ids.length;
    const cell = Math.min(55, 250 / count);
    const row = Math.min(count - 1, Math.floor(s.t * count));
    text(ctx, "因果注意力 · 行查询前文", 110, 176, 20);
    matrix(ctx, s.attention, 110, 195, cell, row, s.ids.map((id) => plan.vocabulary[id]));
    for (let i = 0; i < count; i++) for (let j = i + 1; j < count; j++) {
      box(ctx, 110 + j * cell, 195 + i * cell, cell - 3, cell - 3, "#15232d");
      text(ctx, "×", 118 + j * cell, 195 + i * cell + cell * .64, 16, C.muted);
    }
    text(ctx, "权重 × 向量，再求和", 555, 205, 23, C.teal);
    matrix(ctx, [s.contexts[row]], 555, 230, Math.min(48, 340 / s.contexts[row].length), 0);
    text(ctx, "× 区域是未来位置，不参与计算", 555, 315, 17, C.muted);
    text(ctx, "示意：单头，Q/K/V 为恒等映射", 555, 348, 16, C.muted);
    return;
  }
  text(ctx, "最后位置表示 → logits → softmax", 50, 184, 22);
  const sorted = s.probabilities.map((p, id) => ({ p, id })).sort((a, b) => b.p - a.p);
  sorted.forEach(({ p, id }, i) => {
    const y = 210 + i * 27;
    text(ctx, plan.vocabulary[id], 55, y + 16, 16, color[id]);
    box(ctx, 155, y, Math.max(3, 340 * p * (s.phase === "predict" ? Math.min(1, s.t * 2) : 1)), 20,
      id === s.selected ? C.teal : "#395772");
    text(ctx, `${(p * 100).toFixed(1)}%`, 505, y + 16, 14);
  });
  text(ctx, `温度 T = ${fmt(s.temperature)}`, 655, 223, 19, C.gold);
  text(ctx, `本轮选中：${plan.vocabulary[s.selected]}`, 655, 265, 22, C.teal);
  text(ctx, "固定采样分位，可复现比较", 655, 300, 15, C.muted);
  if (s.phase === "append") {
    arrow(ctx, 705, 330, 705, 330 - 175 * s.t);
    text(ctx, "追加到上下文 → 下一轮", 650, 367, 18);
  }
}

function neural(ctx, plan, s) {
  const active = s.phase === "update";
  const weights = active ? plan.weights.map((w, i) => w + (s.nextWeights[i] - w) * s.t) : plan.weights;
  const ys = [180, 340];
  ys.forEach((y, i) => {
    arrow(ctx, 175, y, 415, 260, weights[i] >= 0 ? C.teal : C.violet);
    box(ctx, 55, y - 30, 120, 60); text(ctx, `x${i + 1} = ${fmt(s.inputs[i])}`, 65, y + 6, 19);
    text(ctx, `w${i + 1} = ${fmt(weights[i])}`, 220, y - 17, 18, C.gold);
  });
  box(ctx, 405, 205, 180, 110); text(ctx, "Σ + bias → σ", 422, 239, 24, C.teal);
  const currentBias = active ? plan.bias + (s.nextBias - plan.bias) * s.t : plan.bias;
  const currentZ = s.inputs.reduce((v, x, i) => v + x * weights[i], currentBias);
  text(ctx, `z = ${fmt(currentZ)}`, 433, 277, 20);
  arrow(ctx, 585, 260, 660, 260); box(ctx, 660, 220, 235, 100);
  const bias = active ? plan.bias + (s.nextBias - plan.bias) * s.t : plan.bias;
  const output = 1 / (1 + Math.exp(-(s.inputs.reduce((v, x, i) => v + x * weights[i], bias))));
  text(ctx, `ŷ = ${fmt(output)}`, 688, 258, 30, C.teal);
  text(ctx, `目标 y = ${fmt(plan.target)}`, 689, 290, 18, C.muted);
  text(ctx, "单神经元 · sigmoid · 一次梯度更新", 55, 97, 22);
  if (s.phase === "loss" || active) {
    text(ctx, `L = ½(ŷ − y)² = ${fmt(.5 * (output - plan.target) ** 2)}`,
      430, 365, 23, C.gold);
    text(ctx, `∂L/∂w = [${s.gradient.map(fmt).join(", ")}]`, 430, 399, 18, C.muted);
  } else {
    text(ctx, `${fmt(s.inputs[0])} × ${fmt(weights[0])} + ${fmt(s.inputs[1])} × ${fmt(weights[1])} + ${fmt(plan.bias)}`,
      330, 372, 21, C.gold);
    text(ctx, "σ(z) = 1 / (1 + exp(−z))", 430, 406, 19, C.muted);
  }
  if (active) arrow(ctx, 800, 160, 280, 160, C.gold);
  else box(ctx, 175 + 230 * s.t, 254, 10, 10, C.teal);
}

function mathPlot(ctx, project) {
  for (let x = -4; x <= 4; x++) line(ctx, ...project(x, -4), ...project(x, 4));
  for (let y = -4; y <= 4; y++) line(ctx, ...project(-4, y), ...project(4, y));
  arrow(ctx, ...project(-4, 0), ...project(4, 0), C.muted);
  arrow(ctx, ...project(0, -4), ...project(0, 4), C.muted);
}
function linear(ctx, plan, s) {
  const extent = Math.max(4, ...s.vector.map((v) => Math.abs(v) + 1),
    ...s.matrix.flat().map((v) => Math.abs(v) * 2));
  const scale = 160 / extent;
  const project = (x, y) => [650 + x * scale, 265 - y * scale];
  text(ctx, "二维线性变换", 55, 100, 26);
  text(ctx, "Aₜ =", 55, 174, 24); matrix(ctx, s.matrix, 115, 140, 65);
  text(ctx, `v = [${plan.vector.map(fmt).join(", ")}]`, 55, 325, 21, C.gold);
  text(ctx, `Aₜv = [${s.vector.map(fmt).join(", ")}]`, 55, 363, 21, C.teal);
  text(ctx, `det(Aₜ) = ${fmt(s.determinant)}`, 55, 403, 20, C.violet);
  ctx.save(); ctx.beginPath(); ctx.rect(440, 82, 455, 340); ctx.clip();
  mathPlot(ctx, project);
  const p = (x, y) => project(s.matrix[0][0] * x + s.matrix[0][1] * y,
    s.matrix[1][0] * x + s.matrix[1][1] * y);
  for (let x = -4; x <= 4; x++) line(ctx, ...p(x, -4), ...p(x, 4), "#386f75", 1);
  for (let y = -4; y <= 4; y++) line(ctx, ...p(-4, y), ...p(4, y), "#386f75", 1);
  ctx.fillStyle = "rgba(180,160,255,.23)";
  ctx.beginPath(); [p(0, 0), p(1, 0), p(1, 1), p(0, 1)].forEach(([x, y], i) =>
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.closePath(); ctx.fill();
  arrow(ctx, ...p(0, 0), ...p(1, 0), C.teal); arrow(ctx, ...p(0, 0), ...p(0, 1), C.violet);
  arrow(ctx, ...project(0, 0), ...project(...s.vector), C.gold);
  ctx.restore();
  text(ctx, "青：基向量 e₁   紫：e₂   金：向量 v", 460, 446, 15, C.muted);
}
function calculus(ctx, plan, s) {
  const samples = Array.from({ length: 201 }, (_, i) => s.f(-4 + i * .04));
  const low = Math.min(0, ...samples) - 1, high = Math.max(0, ...samples) + 1;
  const project = (x, y) => [660 + x * 55, 415 - (y - low) / (high - low) * 305];
  const [a, b, c] = plan.coefficients;
  text(ctx, "从割线到切线", 50, 98, 26);
  text(ctx, `f(x) = ${a}x² + ${b}x + ${c}`, 50, 158, 23, C.teal);
  text(ctx, `x = ${fmt(s.x)}   Δx = ${s.h.toFixed(3)}`, 50, 217, 21);
  text(ctx, `割线斜率 = ${s.slope.toFixed(3)}`, 50, 278, 23, C.gold);
  text(ctx, `f′(x) = 2ax + b = ${fmt(s.derivative)}`, 50, 333, 22, C.violet);
  text(ctx, "减小 Δx，观察两个斜率趋于一致", 50, 403, 18, C.muted);
  ctx.save(); ctx.beginPath(); ctx.rect(430, 90, 465, 340); ctx.clip();
  for (let x = -4; x <= 4; x++) line(ctx, ...project(x, low), ...project(x, high));
  for (let i = 0; i <= 6; i++) {
    const y = low + (high - low) * i / 6;
    line(ctx, ...project(-4, y), ...project(4, y));
  }
  arrow(ctx, ...project(-4, 0), ...project(4, 0), C.muted);
  arrow(ctx, ...project(0, low), ...project(0, high), C.muted);
  ctx.beginPath(); ctx.strokeStyle = C.teal; ctx.lineWidth = 3;
  for (let i = 0; i <= 200; i++) {
    const x = -4 + i * .04; const [px, py] = project(x, s.f(x));
    i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
  }
  ctx.stroke();
  if (s.phase !== "curve") {
    line(ctx, ...project(-4, s.y + s.slope * (-4 - s.x)),
      ...project(4, s.y + s.slope * (4 - s.x)), C.gold, 2);
    for (const [x, y] of [[s.x, s.y], [s.x + s.h, s.nextY]]) {
      ctx.fillStyle = C.gold; ctx.beginPath(); ctx.arc(...project(x, y), 6, 0, 2 * Math.PI); ctx.fill();
    }
  }
  ctx.restore();
}
function packets(ctx, plan, s) {
  const duration = Math.max(s.duration, 1);
  const yAt = (t) => 150 + t / duration * 260;
  const xAt = (side) => side === "client" ? 240 : 760;
  text(ctx, plan.protocol === "tcp_handshake" ? "TCP · 三次握手" : "停止等待 · 可靠传输", 45, 93, 25);
  text(ctx, "发送端 / Client", 173, 127, 19, C.teal);
  text(ctx, "接收端 / Server", 689, 127, 19, C.violet);
  line(ctx, 240, 143, 240, 435, C.teal); line(ctx, 760, 143, 760, 435, C.violet);
  s.events.forEach((event) => {
    if (s.time < event.start) return;
    if (event.type === "timeout") {
      text(ctx, event.label, 45, yAt(event.start), 14, C.red); return;
    }
    const p = Math.min(1, (s.time - event.start) / (event.end - event.start));
    const from = xAt(event.from), to = xAt(event.to);
    const visualP = event.dropped ? Math.min(.5, p) : p;
    const x = from + (to - from) * visualP;
    const y = yAt(event.start + (event.end - event.start) * visualP);
    arrow(ctx, from, yAt(event.start), x, y, event.dropped ? C.red : C.teal);
    text(ctx, event.label, 320, yAt(event.start) - 8, 15, C.ink);
    if (event.dropped && p >= .5) text(ctx, "× 丢失", x, y + 22, 16, C.red);
    else if (p < 1) box(ctx, x - 8, y - 6, 16, 12, C.gold);
  });
  const complete = s.time >= s.duration - .001;
  if (plan.protocol === "tcp_handshake") {
    const retry = s.loss ? 3 * plan.latency : 0;
    const clientState = s.time >= retry + 2 * plan.latency ? "ESTABLISHED" : "SYN_SENT";
    const serverState = complete ? "ESTABLISHED" :
      s.time >= retry + plan.latency ? "SYN_RECEIVED" : "LISTEN";
    text(ctx, clientState, 100, 435, 13, C.teal);
    text(ctx, serverState, 775, 435, 13, C.violet);
  }
  text(ctx, complete ? (plan.protocol === "tcp_handshake" ? "双方 ESTABLISHED" : "收到 ACK，发送完成") :
    `t = ${fmt(s.time)} · ${s.loss ? "首包丢失，等待重传" : "正常传输"}`, 330, 450, 18, C.gold);
}

/** Shared Canvas surface and existing frame clock; no parallel player/engine. */
export function drawMechanism(ctx, plan, { width, height, beatIndex, progress, overrides, sceneId }) {
  const state = mechanismState(plan, beatIndex, progress, overrides, sceneId);
  ctx.save(); ctx.scale(width / 960, height / 600);
  ctx.fillStyle = "#091923"; ctx.fillRect(0, 0, 960, 600);
  text(ctx, "MECHANISM LAB", 32, 32, 13, C.teal);
  text(ctx, plan.example_label, 550, 32, 13, C.muted);
  const render = { language_model: language, neural_network: neural,
    linear_transform: linear, derivative: calculus, packet_network: packets }[plan.kind];
  if (!render) throw new Error(`Unsupported mechanism: ${plan.kind}`);
  render(ctx, plan, state);
  ctx.restore();
  return state;
}
