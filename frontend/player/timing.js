export const PLAYBACK_RATES = Object.freeze([0.25, 0.5, 1, 2]);
export const DEFAULT_FPS = 60;

export function normalizePlaybackRate(value) {
  const parsed = Number(value);
  return PLAYBACK_RATES.includes(parsed) ? parsed : 1;
}

export function scaleElapsed(elapsed, playbackRate) {
  return Math.max(0, Number(elapsed) || 0) * normalizePlaybackRate(playbackRate);
}

export function validateFps(value) {
  const fps = Number(value);
  if (!Number.isFinite(fps) || fps <= 0 || fps > 240) {
    throw new Error("fps must be a positive finite number no greater than 240");
  }
  return fps;
}

export function frameToSeconds(frame, fps = DEFAULT_FPS) {
  if (typeof frame !== "number" || !Number.isFinite(frame) || frame < 0) {
    throw new Error("frame must be a non-negative finite number");
  }
  return frame / validateFps(fps);
}

export function secondsToFrame(seconds, fps = DEFAULT_FPS) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) {
    throw new Error("seconds must be a non-negative finite number");
  }
  return seconds * validateFps(fps);
}

/**
 * Remotion-style logical frame clock.
 *
 * Browser RAF only schedules observation. The displayed frame is derived from
 * an anchor frame and the monotonic RAF timestamp, so dropped paints do not
 * slow the animation or accumulate timing error.
 */
export function createFrameClock({
  fps = DEFAULT_FPS,
  durationInFrames = null,
  initialFrame = 0,
  playbackRate = 1,
  loop = false,
} = {}) {
  const resolvedFps = validateFps(fps);
  const resolvedDuration = validateDuration(durationInFrames);
  let rate = normalizePlaybackRate(playbackRate);
  let frame = clampFrame(initialFrame, resolvedDuration);
  let playing = false;
  let ended = false;
  let anchorFrame = frame;
  let anchorTime = null;

  const snapshot = () => Object.freeze({ frame, playing, ended });

  const update = (now) => {
    const timestamp = finiteTimestamp(now);
    if (!playing) return snapshot();
    if (anchorTime === null) anchorTime = timestamp;
    const elapsed = Math.max(0, timestamp - anchorTime) / 1000;
    const advanced = Math.floor(elapsed * resolvedFps * rate + Number.EPSILON);
    const candidate = anchorFrame + advanced;

    if (resolvedDuration === null) {
      frame = candidate;
      return snapshot();
    }
    if (loop) {
      frame = candidate % resolvedDuration;
      return snapshot();
    }
    if (candidate >= resolvedDuration) {
      frame = resolvedDuration - 1;
      playing = false;
      ended = true;
      anchorTime = null;
      anchorFrame = frame;
      return snapshot();
    }
    frame = candidate;
    return snapshot();
  };

  return Object.freeze({
    get fps() {
      return resolvedFps;
    },
    get durationInFrames() {
      return resolvedDuration;
    },
    get playbackRate() {
      return rate;
    },
    get frame() {
      return frame;
    },
    get playing() {
      return playing;
    },
    update,
    play(now) {
      const timestamp = finiteTimestamp(now);
      if (playing) return snapshot();
      if (ended && resolvedDuration !== null && !loop) frame = 0;
      ended = false;
      playing = true;
      anchorFrame = frame;
      anchorTime = timestamp;
      return snapshot();
    },
    pause(now) {
      if (playing) update(now);
      playing = false;
      anchorFrame = frame;
      anchorTime = null;
      return snapshot();
    },
    seek(nextFrame, now = 0) {
      frame = clampFrame(nextFrame, resolvedDuration);
      ended = false;
      anchorFrame = frame;
      anchorTime = playing ? finiteTimestamp(now) : null;
      return snapshot();
    },
    step(delta, now = 0) {
      if (!Number.isInteger(delta)) throw new Error("frame step must be an integer");
      if (playing) update(now);
      playing = false;
      frame = clampFrame(frame + delta, resolvedDuration);
      ended = false;
      anchorFrame = frame;
      anchorTime = null;
      return snapshot();
    },
    setPlaybackRate(nextRate, now) {
      if (playing) update(now);
      rate = normalizePlaybackRate(nextRate);
      anchorFrame = frame;
      anchorTime = playing ? finiteTimestamp(now) : null;
      return snapshot();
    },
  });
}

function validateDuration(value) {
  if (value === null || value === undefined) return null;
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error("durationInFrames must be a positive integer or null");
  }
  return value;
}

function clampFrame(value, duration) {
  if (!Number.isInteger(value) || value < 0) {
    throw new Error("frame must be a non-negative integer");
  }
  return duration === null ? value : Math.min(value, duration - 1);
}

function finiteTimestamp(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error("clock timestamp must be finite");
  }
  return value;
}
