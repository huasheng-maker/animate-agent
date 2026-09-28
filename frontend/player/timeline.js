import {
  interpolateProperty,
  propertyDescriptor,
  validatePropertyTarget,
  validatePropertyValue,
} from "./property-registry.js";
import { resolveEase, SUPPORTED_EASINGS } from "./gsap-easing.js";
import { DEFAULT_FPS, secondsToFrame, validateFps } from "./frame-math.js";

export function compileTimeline(timeline, nodes, { fps = DEFAULT_FPS } = {}) {
  const resolvedFps = validateFps(fps);
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const tracks = [];
  const duration = compileItems(timeline?.items ?? [], 0, tracks, nodeById, "parallel", resolvedFps);
  tracks.sort((a, b) => a.start - b.start || a.key.localeCompare(b.key));
  rejectOverlaps(tracks);
  return Object.freeze({
    tracks: Object.freeze(tracks),
    duration,
    // Authored keyframe times include their endpoint. Keep one final logical
    // frame so a 1s track at 30fps can actually resolve frame 30 (value=to)
    // before the player enters its ended state.
    durationInFrames: duration === 0 ? 0 : Math.ceil(secondsToFrame(duration, resolvedFps)) + 1,
    fps: resolvedFps,
  });
}

export function sampleTimeline(compiled, time) {
  if (typeof time !== "number" || !Number.isFinite(time)) throw new Error("Timeline time must be finite");
  return sampleTimelineAtFrame(compiled, secondsToFrame(time, compiled.fps));
}

export function sampleTimelineFrame(compiled, frame) {
  if (!Number.isInteger(frame) || frame < 0) {
    throw new Error("Timeline frame must be a non-negative integer");
  }
  return sampleTimelineAtFrame(compiled, frame);
}

function sampleTimelineAtFrame(compiled, frame) {
  const patches = [];
  for (const track of compiled.tracks) {
    if (frame < track.startFrame) continue;
    patches.push({ target: track.target, property: track.property, value: sampleTrack(track, frame) });
  }
  return patches;
}

function compileItems(items, offset, output, nodeById, mode, fps) {
  if (!Array.isArray(items)) throw new Error("Timeline items must be an array");
  let cursor = offset;
  let furthest = offset;
  for (const item of items) {
    if (!item || typeof item !== "object") throw new Error("Timeline item must be an object");
    const itemOffset = mode === "sequence" ? cursor : offset;
    let end;
    if (item.type === "sequence" || item.type === "parallel") {
      const delay = nonNegative(item.delay ?? 0, "group delay");
      const start = itemOffset + delay;
      end = compileItems(item.children ?? [], start, output, nodeById, item.type, fps);
    } else {
      end = compileTrack(item, itemOffset, output, nodeById, fps);
    }
    if (mode === "sequence") cursor = end;
    furthest = Math.max(furthest, end);
  }
  return mode === "sequence" ? cursor : furthest;
}

function compileTrack(track, offset, output, nodeById, fps) {
  const descriptor = propertyDescriptor(track.property);
  validatePropertyTarget(descriptor, track.target, nodeById);
  if (!Array.isArray(track.keyframes) || track.keyframes.length < 2) {
    throw new Error(`Track ${track.property} needs at least two keyframes`);
  }
  const delay = nonNegative(track.delay ?? 0, `${track.property} delay`);
  let keyframes = track.keyframes.map((keyframe, index) => {
    const time = nonNegative(keyframe.time, `${track.property} keyframe time`);
    validatePropertyValue(descriptor, keyframe.value, `${track.property} keyframe ${index}`);
    const easing = keyframe.easing ?? "linear";
    if (!SUPPORTED_EASINGS.includes(easing)) throw new Error(`Unknown easing: ${easing}`);
    if (keyframe.interpolation && !["number", "normalized", "vector", "color", "discrete"].includes(keyframe.interpolation)) {
      throw new Error(`Unknown interpolation: ${keyframe.interpolation}`);
    }
    return { time, value: keyframe.value, easing, interpolation: keyframe.interpolation };
  });
  for (let index = 1; index < keyframes.length; index += 1) {
    if (keyframes[index].time <= keyframes[index - 1].time) {
      throw new Error(`Track ${track.property} keyframe times must increase`);
    }
  }
  // Pydantic serializes an omitted optional duration as JSON null. Treat null
  // like absence so Python-authored tracks use their last keyframe time.
  if (track.duration != null) {
    const duration = positive(track.duration, `${track.property} duration`);
    const authoredDuration = keyframes.at(-1).time;
    keyframes = keyframes.map((keyframe) => ({
      ...keyframe,
      time: (keyframe.time / authoredDuration) * duration,
    }));
  }
  const start = offset + delay;
  const end = start + keyframes.at(-1).time;
  const startFrame = secondsToFrame(start, fps);
  output.push(Object.freeze({
    target: Object.freeze({ ...track.target }),
    property: track.property,
    descriptor,
    keyframes: Object.freeze(keyframes.map((keyframe) => Object.freeze({
      ...keyframe,
      frame: startFrame + secondsToFrame(keyframe.time, fps),
    }))),
    start,
    end,
    startFrame,
    endFrame: secondsToFrame(end, fps),
    key: `${track.target.type}:${track.target.id}:${track.property}`,
  }));
  return end;
}

function sampleTrack(track, absoluteFrame) {
  const frames = track.keyframes;
  if (absoluteFrame <= frames[0].frame) return frames[0].value;
  if (absoluteFrame >= frames.at(-1).frame) return frames.at(-1).value;
  let rightIndex = 1;
  while (frames[rightIndex].frame < absoluteFrame) rightIndex += 1;
  const left = frames[rightIndex - 1];
  const right = frames[rightIndex];
  const raw = (absoluteFrame - left.frame) / (right.frame - left.frame);
  const eased = resolveEase(right.easing)(raw);
  return interpolateProperty(track.descriptor, left.value, right.value, eased, right.interpolation);
}

function rejectOverlaps(tracks) {
  const byKey = new Map();
  for (const track of tracks) {
    const previous = byKey.get(track.key);
    if (previous && track.start < previous.end) {
      throw new Error(`Overlapping tracks for ${track.key}`);
    }
    byKey.set(track.key, track);
  }
}

function nonNegative(value, label) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new Error(`${label} must be a non-negative finite number`);
  }
  return value;
}

function positive(value, label) {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    throw new Error(`${label} must be a positive finite number`);
  }
  return value;
}
