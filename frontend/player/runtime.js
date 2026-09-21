import {
  cloneValue,
  propertyDescriptor,
  setControlledProperty,
  validatePropertyTarget,
  validatePropertyValue,
} from "./property-registry.js";
import { compileEffects } from "./effects.js";
import { compileTimeline, sampleTimeline, sampleTimelineFrame } from "./timeline.js";
import { DEFAULT_FPS, frameToSeconds, secondsToFrame, validateFps } from "./timing.js";

/** A deterministic, DOM-free and renderer-free runtime for one animation scene. */
export function createAnimationRuntime(scene, { fps = DEFAULT_FPS } = {}) {
  const resolvedFps = validateFps(fps);
  const authoredNodeById = new Map(scene.nodes.map((node) => [node.id, node]));
  const compileForStep = (index) => {
    const beat = scene.beats?.[index];
    return compileTimeline({
      items: [
        ...(scene.timeline?.items ?? []),
        ...compileEffects(scene.timeline?.effects ?? []),
        ...(beat?.timeline?.items ?? []),
        ...compileEffects(beat?.timeline?.effects ?? []),
      ],
    }, scene.nodes, { fps: resolvedFps });
  };
  let compiled = compileForStep(0);
  let stepIndex = 0;
  let legacyOverrides = {};
  const controlledOverrides = new Map();

  return {
    get duration() {
      return compiled.duration;
    },
    get durationInFrames() {
      return compiled.durationInFrames;
    },
    get fps() {
      return resolvedFps;
    },
    setStep(index) {
      stepIndex = index;
      compiled = compileForStep(index);
    },
    setLegacyOverrides(overrides) {
      legacyOverrides = overrides;
    },
    setPropertyOverride(target, property, value) {
      const descriptor = propertyDescriptor(property);
      validatePropertyTarget(descriptor, target, authoredNodeById);
      validatePropertyValue(descriptor, value, `${property} override`);
      controlledOverrides.set(`${target.type}:${target.id}:${property}`, { target, property, value });
    },
    clearPropertyOverride(target, property) {
      controlledOverrides.delete(`${target.type}:${target.id}:${property}`);
    },
    lookup(elementId, prop, fallback) {
      const key = `${elementId}.${prop}`;
      if (key in legacyOverrides) return legacyOverrides[key];
      const step = scene.legacy?.steps?.[stepIndex];
      const fromStep = step?.states?.[elementId];
      if (fromStep && prop in fromStep) return fromStep[prop];
      const element = scene.legacy?.elements?.find((candidate) => candidate.id === elementId);
      const bound = element?.binds?.[prop];
      if (bound && bound in legacyOverrides) return legacyOverrides[bound];
      if (element?.props && prop in element.props) return element.props[prop];
      const sceneKey = `scene.${prop}`;
      if (sceneKey in legacyOverrides) return legacyOverrides[sceneKey];
      if (prop in (scene.legacy?.params ?? {})) return scene.legacy.params[prop];
      return fallback;
    },
    seek(time, { legacyLive = new Map() } = {}) {
      return resolveState({
        time,
        frame: secondsToFrame(time, resolvedFps),
        legacyLive,
        patches: sampleTimeline(compiled, time),
      });
    },
    seekFrame(frame, { legacyLive = new Map() } = {}) {
      return resolveState({
        time: frameToSeconds(frame, resolvedFps),
        frame,
        legacyLive,
        patches: sampleTimelineFrame(compiled, frame),
      });
    },
  };

  function resolveState({ time, frame, legacyLive, patches }) {
      const nodes = scene.nodes.map((node) => cloneValue(node));
      const state = {
        time,
        frame,
        fps: resolvedFps,
        nodes,
        nodeById: new Map(nodes.map((node) => [node.id, node])),
        camera: cloneValue(scene.camera),
        interactions: cloneValue(scene.interactions),
        controlledProperties: new Set(),
      };

      // Legacy simulation is below explicit timeline tracks in precedence.
      for (const [id, live] of legacyLive) {
        const node = state.nodeById.get(id);
        if (!node) continue;
        if (Number.isFinite(live.x) && Number.isFinite(live.y)) {
          node.transform.position = { x: live.x, y: live.y };
        }
        if (Number.isFinite(live.heading)) node.transform.rotation = live.heading;
        if (Number.isFinite(live.progress)) node.semantic.progress = live.progress;
      }

      for (const patch of patches) {
        setControlledProperty(state, patch.target, patch.property, patch.value);
        state.controlledProperties.add(`${patch.target.type}:${patch.target.id}:${patch.property}`);
      }
      // Direct user intent outranks both timeline and legacy state.
      for (const override of controlledOverrides.values()) {
        setControlledProperty(state, override.target, override.property, override.value);
        state.controlledProperties.add(`${override.target.type}:${override.target.id}:${override.property}`);
      }

      resolveDerivedState(state);
      state.legacyLive = new Map(
        nodes.map((node) => [node.id, {
          x: node.transform.position.x,
          y: node.transform.position.y,
          heading: node.transform.rotation,
          progress: node.semantic.progress,
        }]),
      );
      return state;
  }
}

function resolveDerivedState(state) {
  for (const node of state.nodes) {
    const path = node.visual?.path;
    const pathProgressControlled = state.controlledProperties.has(
      `node:${node.id}:transform.pathProgress`,
    );
    if (Array.isArray(path) && path.length >= 2 && pathProgressControlled) {
      const { point, tangent } = pointAndTangent(path, node.transform.pathProgress);
      node.transform.position = point;
      if (node.visual.orientToPath) {
        node.transform.rotation = (Math.atan2(tangent.y, tangent.x) * 180) / Math.PI;
      }
    }
    if (typeof node.visual?.originalText === "string") {
      const progress = clamp(node.visual.revealProgress ?? 1, 0, 1);
      const length = Math.floor(node.visual.originalText.length * progress);
      node.visual.visibleText = node.visual.originalText.slice(0, length);
    }
  }
}

function pointAndTangent(points, progress) {
  const lengths = [];
  let total = 0;
  for (let index = 1; index < points.length; index += 1) {
    const length = Math.hypot(points[index].x - points[index - 1].x, points[index].y - points[index - 1].y);
    lengths.push(length);
    total += length;
  }
  let remaining = clamp(progress, 0, 1) * total;
  for (let index = 0; index < lengths.length; index += 1) {
    if (remaining < lengths[index] || index === lengths.length - 1) {
      const start = points[index];
      const end = points[index + 1];
      const ratio = lengths[index] === 0 ? 0 : remaining / lengths[index];
      return {
        point: { x: start.x + (end.x - start.x) * ratio, y: start.y + (end.y - start.y) * ratio },
        tangent: { x: end.x - start.x, y: end.y - start.y },
      };
    }
    remaining -= lengths[index];
  }
  return { point: cloneValue(points.at(-1)), tangent: { x: 1, y: 0 } };
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
