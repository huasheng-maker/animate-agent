import assert from "node:assert/strict";
import test from "node:test";

import { beatAtFrame, buildBeatSeries } from "./composition.js";

const spec = {
  scenes: [
    { id: "scene-a" },
    { id: "scene-b" },
  ],
};
const ir = {
  fps: 30,
  scenes: [
    {
      id: "scene-a",
      beats: [
        { id: "a", durationInFrames: 60 },
        { id: "b", durationInFrames: 90 },
      ],
    },
    { id: "scene-b", beats: [{ id: "c", durationInFrames: 30 }] },
  ],
};

test("beat series matches Remotion Series sequential frame semantics", () => {
  const series = buildBeatSeries(spec, ir);
  assert.equal(series.durationInFrames, 180);
  assert.deepEqual(series.entries.map(({ startFrame, endFrame }) => [startFrame, endFrame]), [
    [0, 60],
    [60, 150],
    [150, 180],
  ]);
  assert.equal(beatAtFrame(series, 0).beat.id, "a");
  assert.equal(beatAtFrame(series, 59).beat.id, "a");
  assert.equal(beatAtFrame(series, 60).beat.id, "b");
  assert.equal(beatAtFrame(series, 179).beat.id, "c");
});

test("legacy beats receive a deterministic three-second fallback", () => {
  const series = buildBeatSeries(
    { scenes: [{ id: "scene-a" }] },
    { fps: 24, scenes: [{ id: "scene-a", beats: [{ id: "legacy" }] }] },
  );
  assert.equal(series.durationInFrames, 72);
});
