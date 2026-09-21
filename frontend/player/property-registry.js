/**
 * Renderer-neutral animation property capabilities.
 *
 * Animation data may address only properties declared here. The registry owns
 * value validation and interpolation selection so the timeline engine never
 * needs branches for text, paths, cameras, or any particular primitive.
 */

const NODE_KINDS = "*";

export const ANIMATABLE_PROPERTIES = Object.freeze({
  "transform.position": property("node", NODE_KINDS, "vec2", "vector"),
  "transform.rotation": property("node", NODE_KINDS, "number", "number"),
  "transform.scale": property("node", NODE_KINDS, "scale2", "vector"),
  "transform.opacity": property("node", NODE_KINDS, "number", "normalized", { min: 0, max: 1 }),
  "transform.pathProgress": property("node", NODE_KINDS, "number", "normalized", { min: 0, max: 1 }),
  "style.fill": property("node", NODE_KINDS, "color", "color"),
  "style.stroke": property("node", NODE_KINDS, "color", "color"),
  "style.strokeWidth": property("node", NODE_KINDS, "number", "number", { min: 0 }),
  "style.shadowBlur": property("node", NODE_KINDS, "number", "number", { min: 0 }),
  "style.glowIntensity": property("node", NODE_KINDS, "number", "normalized", { min: 0, max: 1 }),
  "style.highlight": property("node", NODE_KINDS, "boolean", "discrete"),
  "visual.drawProgress": property("node", ["path", "trace", "link", "vector"], "number", "normalized", { min: 0, max: 1 }),
  "visual.trimStart": property("node", ["path", "trace", "link"], "number", "normalized", { min: 0, max: 1 }),
  "visual.trimEnd": property("node", ["path", "trace", "link"], "number", "normalized", { min: 0, max: 1 }),
  "visual.pathOffset": property("node", ["path", "trace", "link"], "number", "number"),
  "visual.revealProgress": property("node", ["text", "readout"], "number", "normalized", { min: 0, max: 1 }),
  "visual.cursorVisible": property("node", ["text", "readout"], "boolean", "discrete"),
  "camera.position": property("camera", NODE_KINDS, "vec2", "vector"),
  "camera.zoom": property("camera", NODE_KINDS, "number", "number", { min: 0.000001 }),
  "camera.rotation": property("camera", NODE_KINDS, "number", "number"),
  "semantic.progress": property("node", NODE_KINDS, "number", "normalized", { min: 0, max: 1 }),
  "semantic.intensity": property("node", NODE_KINDS, "number", "normalized", { min: 0, max: 1 }),
  "semantic.phase": property("node", NODE_KINDS, "enum", "discrete"),
});

function property(targetType, nodeKinds, valueType, interpolation, bounds = {}) {
  return Object.freeze({ targetType, nodeKinds, valueType, interpolation, ...bounds });
}

export function propertyDescriptor(name) {
  const descriptor = ANIMATABLE_PROPERTIES[name];
  if (!descriptor) throw new Error(`Unknown animatable property: ${name}`);
  return descriptor;
}

export function validatePropertyTarget(descriptor, target, nodeById) {
  if (!target || target.type !== descriptor.targetType || typeof target.id !== "string") {
    throw new Error(`Property target must be a ${descriptor.targetType} with an id`);
  }
  if (target.type === "camera") {
    if (target.id !== "main") throw new Error(`Unknown camera target: ${target.id}`);
    return;
  }
  const node = nodeById.get(target.id);
  if (!node) throw new Error(`Unknown animation target: ${target.id}`);
  if (descriptor.nodeKinds !== NODE_KINDS && !descriptor.nodeKinds.includes(node.kind)) {
    throw new Error(`Property is not supported by node kind ${node.kind}: ${target.id}`);
  }
}

export function validatePropertyValue(descriptor, value, label = "value") {
  switch (descriptor.valueType) {
    case "number":
      assertFiniteNumber(value, label);
      if (descriptor.min !== undefined && value < descriptor.min) {
        throw new Error(`${label} must be at least ${descriptor.min}`);
      }
      if (descriptor.max !== undefined && value > descriptor.max) {
        throw new Error(`${label} must be at most ${descriptor.max}`);
      }
      break;
    case "vec2":
    case "scale2":
      if (!value || typeof value !== "object") throw new Error(`${label} must be a vec2`);
      assertFiniteNumber(value.x, `${label}.x`);
      assertFiniteNumber(value.y, `${label}.y`);
      if (descriptor.valueType === "scale2" && (value.x <= 0 || value.y <= 0)) {
        throw new Error(`${label} scale components must be positive`);
      }
      break;
    case "color":
      parseColor(value, label);
      break;
    case "boolean":
      if (typeof value !== "boolean") throw new Error(`${label} must be a boolean`);
      break;
    case "enum":
      if (typeof value !== "string" || value.length === 0) {
        throw new Error(`${label} must be a non-empty enum string`);
      }
      break;
    default:
      throw new Error(`Unsupported property value type: ${descriptor.valueType}`);
  }
}

export function interpolateProperty(descriptor, from, to, progress, override) {
  const interpolation = override ?? descriptor.interpolation;
  // GSAP's back/elastic curves intentionally leave the 0..1 range. Preserve
  // that character for spatial values while bounded channels remain clamped.
  const t = ["normalized", "color", "discrete"].includes(interpolation)
    ? clamp(progress, 0, 1)
    : progress;
  switch (interpolation) {
    case "number":
      return from + (to - from) * t;
    case "normalized":
      return clamp(from + (to - from) * t, 0, 1);
    case "vector":
      return { x: from.x + (to.x - from.x) * t, y: from.y + (to.y - from.y) * t };
    case "color": {
      const a = parseColor(from);
      const b = parseColor(to);
      const channel = (name) => Math.round(a[name] + (b[name] - a[name]) * t);
      const alpha = a.a + (b.a - a.a) * t;
      return `rgba(${channel("r")}, ${channel("g")}, ${channel("b")}, ${trim(alpha)})`;
    }
    case "discrete":
      return t < 1 ? cloneValue(from) : cloneValue(to);
    default:
      throw new Error(`Unknown interpolation: ${interpolation}`);
  }
}

export function setControlledProperty(state, target, name, value) {
  const root = target.type === "camera" ? state.camera : state.nodeById.get(target.id);
  if (!root) throw new Error(`Cannot write missing animation target: ${target.id}`);
  const path = name.split(".");
  if (target.type === "camera" && path[0] === "camera") path.shift();
  let cursor = root;
  for (let index = 0; index < path.length - 1; index += 1) {
    const part = path[index];
    cursor[part] ??= {};
    cursor = cursor[part];
  }
  cursor[path.at(-1)] = cloneValue(value);
}

export function cloneValue(value) {
  if (Array.isArray(value)) return value.map(cloneValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, cloneValue(item)]));
  }
  return value;
}

function assertFiniteNumber(value, label) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${label} must be a finite number`);
  }
}

function parseColor(value, label = "color") {
  if (typeof value === "string") {
    const short = /^#([0-9a-f]{3})$/i.exec(value);
    if (short) {
      const [r, g, b] = short[1].split("").map((part) => parseInt(part + part, 16));
      return { r, g, b, a: 1 };
    }
    const hex = /^#([0-9a-f]{6})([0-9a-f]{2})?$/i.exec(value);
    if (hex) {
      return {
        r: parseInt(hex[1].slice(0, 2), 16),
        g: parseInt(hex[1].slice(2, 4), 16),
        b: parseInt(hex[1].slice(4, 6), 16),
        a: hex[2] ? parseInt(hex[2], 16) / 255 : 1,
      };
    }
  }
  if (value && typeof value === "object") {
    for (const channel of ["r", "g", "b"]) {
      assertFiniteNumber(value[channel], `${label}.${channel}`);
      if (value[channel] < 0 || value[channel] > 255) {
        throw new Error(`${label}.${channel} must be between 0 and 255`);
      }
    }
    const alpha = value.a ?? 1;
    assertFiniteNumber(alpha, `${label}.a`);
    if (alpha < 0 || alpha > 1) throw new Error(`${label}.a must be between 0 and 1`);
    return { r: value.r, g: value.g, b: value.b, a: alpha };
  }
  throw new Error(`${label} must be a hex or RGBA color`);
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function trim(value) {
  return Number(value.toFixed(4));
}
