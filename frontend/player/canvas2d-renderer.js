import { drawElement } from "./registry.js";

/**
 * Canvas backend for an already-resolved Scene State.
 *
 * It does not inspect timelines, effects, clocks, or input events. Those belong
 * to the runtime and interaction layers. The renderer only translates current
 * visual state into Canvas 2D drawing operations.
 */
export function createCanvas2DRenderer(ctx) {
  if (!ctx) throw new Error("Canvas2DRenderer requires a drawing context");
  return {
    render(sceneState, { stage, view, clear }) {
      if (!sceneState || !Array.isArray(sceneState.nodes)) {
        throw new Error("Canvas2DRenderer requires a resolved Scene State");
      }
      clear();
      ctx.save();
      applyCamera(ctx, sceneState.camera, stage);
      drawChrome(ctx, sceneState.nodes, view.theme, stage.width, stage.height);
      for (const node of sceneState.nodes) drawNode(ctx, node, view);
      ctx.restore();
    },
  };
}

export function resolveRenderableElement(node) {
  const element = {
    ...node.visual,
    id: node.id,
    kind: node.kind,
    x: node.transform.position.x,
    y: node.transform.position.y,
    tone: node.style.tone ?? node.visual.tone ?? "normal",
  };
  if (node.kind === "body" || node.kind === "emitter") {
    element.heading = node.transform.rotation;
  }
  if (typeof node.visual.visibleText === "string") {
    element.text = node.visual.visibleText;
  }
  const progress = clamp(node.visual.drawProgress ?? 1, 0, 1);
  if (Array.isArray(element.points) && progress < 1) {
    element.points = trimPolyline(element.points, progress);
  }
  if (node.kind === "vector" && progress < 1) {
    element.dx = Number(element.dx ?? 0) * progress;
    element.dy = Number(element.dy ?? 0) * progress;
  }
  return element;
}

function drawNode(ctx, node, view) {
  const element = resolveRenderableElement(node);
  const { x, y } = node.transform.position;
  const scale = node.transform.scale ?? { x: 1, y: 1 };
  const drawerOwnsRotation = node.kind === "body" || node.kind === "emitter";
  ctx.save();
  ctx.globalAlpha *= clamp(node.transform.opacity ?? 1, 0, 1);
  ctx.translate(x, y);
  if (!drawerOwnsRotation) ctx.rotate(((node.transform.rotation ?? 0) * Math.PI) / 180);
  ctx.scale(scale.x ?? 1, scale.y ?? 1);
  ctx.translate(-x, -y);
  if ((node.style.glowIntensity ?? 0) > 0) {
    ctx.shadowColor = view.theme.lineHot;
    ctx.shadowBlur = 24 * clamp(node.style.glowIntensity, 0, 1);
  }
  drawMotionAccent(ctx, node, view);
  drawElement(ctx, element, view);
  ctx.restore();
}

/** Return renderer-only accent geometry without leaking it into AnimationIR. */
export function resolveMotionAccent(node) {
  const intensity = clamp(node.style?.glowIntensity ?? 0, 0, 1);
  if (intensity <= 0.01) return null;
  const path = node.visual?.path ?? node.visual?.points;
  if (Array.isArray(path) && path.length >= 2 && node.kind !== "body") {
    return {
      kind: "spark",
      point: pointOnPolyline(path, clamp(node.visual?.drawProgress ?? 1, 0, 1)),
      radius: 3 + intensity * 5,
      alpha: 0.25 + intensity * 0.65,
    };
  }
  const width = Number(node.visual?.width ?? node.visual?.radius ?? node.visual?.size ?? 44);
  const height = Number(node.visual?.height ?? node.visual?.radius ?? node.visual?.size ?? 44);
  return {
    kind: "halo",
    x: node.transform.position.x,
    y: node.transform.position.y,
    radius: Math.max(24, Math.max(width, height) * 0.58) + (1 - intensity) * 16,
    alpha: intensity * 0.42,
  };
}

function drawMotionAccent(ctx, node, view) {
  const accent = resolveMotionAccent(node);
  if (!accent) return;
  ctx.save();
  ctx.strokeStyle = view.theme.lineHot;
  ctx.fillStyle = view.theme.lineHot;
  ctx.globalAlpha *= accent.alpha;
  ctx.shadowColor = view.theme.lineHot;
  ctx.shadowBlur = 18;
  if (accent.kind === "spark") {
    ctx.beginPath();
    ctx.arc(accent.point.x, accent.point.y, accent.radius, 0, Math.PI * 2);
    ctx.fill();
  } else {
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(accent.x, accent.y, accent.radius, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();
}

function applyCamera(ctx, camera, stage) {
  const position = camera?.position ?? { x: 0, y: 0 };
  const zoom = camera?.zoom ?? 1;
  const rotation = ((camera?.rotation ?? 0) * Math.PI) / 180;
  ctx.translate(stage.width / 2, stage.height / 2);
  ctx.rotate(rotation);
  ctx.scale(zoom, zoom);
  ctx.translate(-stage.width / 2 - position.x, -stage.height / 2 - position.y);
}

function drawChrome(ctx, nodes, theme, width, height) {
  const lane = nodes.find((node) => node.visual?.role === "vehicle");
  const laneY = lane?.transform?.position?.y ?? height / 2;
  ctx.save();
  ctx.strokeStyle = "rgba(83, 246, 255, 0.07)";
  ctx.lineWidth = 1;
  for (let x = 0; x <= width; x += 40) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
  }
  for (let y = 0; y <= height; y += 40) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }
  ctx.setLineDash([10, 14]);
  ctx.strokeStyle = theme.line;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(0, laneY);
  ctx.lineTo(width, laneY);
  ctx.stroke();
  ctx.restore();
}

function trimPolyline(points, fraction) {
  if (fraction >= 1 || points.length < 2) return points.map((point) => ({ ...point }));
  if (fraction <= 0) return [points[0]];
  const lengths = [];
  let total = 0;
  for (let index = 1; index < points.length; index += 1) {
    const length = Math.hypot(
      points[index].x - points[index - 1].x,
      points[index].y - points[index - 1].y,
    );
    lengths.push(length);
    total += length;
  }
  let remaining = total * fraction;
  const result = [{ ...points[0] }];
  for (let index = 0; index < lengths.length; index += 1) {
    const start = points[index];
    const end = points[index + 1];
    if (remaining <= lengths[index]) {
      const ratio = lengths[index] === 0 ? 0 : remaining / lengths[index];
      result.push({
        x: start.x + (end.x - start.x) * ratio,
        y: start.y + (end.y - start.y) * ratio,
      });
      return result;
    }
    result.push({ ...end });
    remaining -= lengths[index];
  }
  return result;
}

function pointOnPolyline(points, fraction) {
  const trimmed = trimPolyline(points, fraction);
  return { ...trimmed.at(-1) };
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
