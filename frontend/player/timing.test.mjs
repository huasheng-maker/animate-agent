import assert from "node:assert/strict";

import {
  createFrameClock,
  frameToSeconds,
  normalizePlaybackRate,
  scaleElapsed,
  secondsToFrame,
} from "./timing.js";

assert.equal(normalizePlaybackRate("0.25"), 0.25);
assert.equal(normalizePlaybackRate("2"), 2);
assert.equal(normalizePlaybackRate("3"), 1);
assert.equal(scaleElapsed(0.5, 0.5), 0.25);
assert.equal(scaleElapsed(0.5, 2), 1);
assert.equal(scaleElapsed(-1, 2), 0);

assert.equal(frameToSeconds(0, 30), 0);
assert.equal(frameToSeconds(15, 30), 0.5);
assert.equal(frameToSeconds(30, 30), 1);
assert.equal(secondsToFrame(0.5, 30), 15);

const clock = createFrameClock({ fps: 30, durationInFrames: 60, loop: false });
clock.play(1000);
assert.equal(clock.update(1500).frame, 15);
clock.pause(1500);
clock.play(9000);
assert.equal(clock.update(9500).frame, 30);
clock.setPlaybackRate(2, 9500);
assert.equal(clock.update(10000).frame, 59);
assert.equal(clock.playing, false);
assert.equal(clock.step(-1).frame, 58);
assert.equal(clock.seek(10).frame, 10);

const loop = createFrameClock({ fps: 30, durationInFrames: 60, loop: true });
loop.play(0);
assert.equal(loop.update(2000).frame, 0);

const droppedPaints = createFrameClock({ fps: 30 });
droppedPaints.play(0);
assert.equal(droppedPaints.update(1000).frame, 30);

console.log("player timing: ok");
