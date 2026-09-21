const PENDING_EFFECTS = new Set(["traceFlow", "particleEffect"]);

/** Compile semantic effects to ordinary, renderer-neutral timeline tracks. */
export function compileEffects(effects = []) {
  if (!Array.isArray(effects)) throw new Error("Effects must be an array");
  return effects.map((effect) => compileEffect(effect));
}

function compileEffect(effect) {
  if (!effect || typeof effect.effect !== "string") throw new Error("Effect must have a name");
  const duration = positive(effect.duration ?? 0.3, `${effect.effect} duration`);
  const targetId = effect.target;
  switch (effect.effect) {
    case "fadeIn":
      return track(node(targetId), "transform.opacity", effect.from ?? 0, effect.to ?? 1, duration, effect);
    case "moveTo":
      return track(node(targetId), "transform.position", required(effect.from, "moveTo from"), required(effect.to, "moveTo to"), duration, effect);
    case "drawPath":
      return track(node(targetId), "visual.drawProgress", effect.from ?? 0, effect.to ?? 1, duration, effect);
    case "highlight":
      return track(node(targetId), "style.highlight", effect.from ?? true, effect.to ?? false, duration, { ...effect, interpolation: "discrete" });
    case "typeWriter":
      return track(node(targetId), "visual.revealProgress", effect.from ?? 0, effect.to ?? 1, duration, effect);
    case "cameraPan":
      return track({ type: "camera", id: effect.camera ?? "main" }, "camera.position", required(effect.from, "cameraPan from"), required(effect.to, "cameraPan to"), duration, effect);
    case "pulse":
      return multiTrack(node(targetId), "transform.scale", [
        { time: 0, value: effect.from ?? { x: 1, y: 1 } },
        { time: duration * 0.42, value: effect.to ?? { x: 1.1, y: 1.1 }, easing: effect.easing ?? "easeOut" },
        { time: duration, value: effect.from ?? { x: 1, y: 1 }, easing: "easeInOut" },
      ], effect);
    case "followPath":
      return track(node(targetId), "transform.pathProgress", effect.from ?? 0, effect.to ?? 1, duration, effect);
    case "cameraZoom":
      return track({ type: "camera", id: effect.camera ?? "main" }, "camera.zoom", effect.from ?? 1, required(effect.to, "cameraZoom to"), duration, effect);
    default:
      if (PENDING_EFFECTS.has(effect.effect)) {
        throw new Error(`Effect is reserved but not implemented: ${effect.effect}`);
      }
      throw new Error(`Unknown semantic effect: ${effect.effect}`);
  }
}

function multiTrack(target, property, keyframes, effect) {
  return { target, property, delay: effect.delay ?? 0, keyframes };
}

function track(target, property, from, to, duration, effect) {
  return {
    target,
    property,
    delay: effect.delay ?? 0,
    keyframes: [
      { time: 0, value: from },
      { time: duration, value: to, easing: effect.easing ?? "linear", interpolation: effect.interpolation },
    ],
  };
}

function node(id) {
  if (typeof id !== "string" || id.length === 0) throw new Error("Effect target is required");
  return { type: "node", id };
}

function required(value, label) {
  if (value === undefined) throw new Error(`${label} is required`);
  return value;
}

function positive(value, label) {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    throw new Error(`${label} must be a positive finite number`);
  }
  return value;
}
