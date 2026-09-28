export const DEFAULT_FPS = 60;

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
