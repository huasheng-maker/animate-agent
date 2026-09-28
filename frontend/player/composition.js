/** Build the exact sequential beat list passed to Remotion <Series>. */
export function buildBeatSeries(spec, ir) {
  const renderScenes = new Map(spec.scenes.map((scene) => [scene.id, scene]));
  let startFrame = 0;
  const entries = [];
  for (const [sceneIndex, scene] of ir.scenes.entries()) {
    const renderScene = renderScenes.get(scene.id);
    if (!renderScene) throw new Error(`Missing RenderSpec scene: ${scene.id}`);
    for (const [beatIndex, beat] of scene.beats.entries()) {
      const durationInFrames = positiveDuration(beat.durationInFrames, ir.fps);
      entries.push({
        index: entries.length,
        sceneIndex,
        beatIndex,
        startFrame,
        endFrame: startFrame + durationInFrames,
        durationInFrames,
        scene,
        renderScene,
        beat,
      });
      startFrame += durationInFrames;
    }
  }
  if (entries.length === 0) throw new Error("AnimationIR must contain at least one beat");
  return Object.freeze({ entries: Object.freeze(entries), durationInFrames: startFrame });
}

export function beatAtFrame(series, frame) {
  const clamped = Math.max(0, Math.min(series.durationInFrames - 1, Math.floor(frame)));
  return series.entries.find((entry) => clamped < entry.endFrame) ?? series.entries.at(-1);
}

function positiveDuration(value, fps) {
  if (Number.isInteger(value) && value > 0) return value;
  return Math.max(1, Math.round((Number(fps) || 60) * 3));
}
