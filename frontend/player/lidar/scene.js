import { normalizeRenderSpec } from "../animation-ir.js";
import { createAnimationRuntime } from "../runtime.js";
import { center, DEFAULTS, FPS, START, WORLD } from "./model.js";

// Local trusted adapter: domain result -> existing controlled AnimationIR tracks.
export function createDemoScene(result, settings = DEFAULTS) {
  const spec = {
    spec_version: 1, storyboard_id: "lidar-hand-authored", lesson_id: "lidar-lesson", document_id: "lidar-demo-evidence",
    title: "看见障碍，然后绕过去", subject: "robotics", stage: { width: WORLD.width, height: WORLD.height },
    scenes: [{ id: "lidar-lab", elements: [{ id: "robot", kind: "body", role: "vehicle", shape: "circle", x: START.x, y: START.y, width: settings.radius * 2, height: settings.radius * 2, props: {}, binds: {}, label: "", tone: "normal" }], steps: [], controls: [] }],
  };
  const ir = normalizeRenderSpec(spec);
  ir.fps = FPS;
  const scene = ir.scenes[0];
  if (result.path.length > 1) {
    const points = result.path.map(center);
    scene.timeline.items = [{
      type: "track", target: { type: "node", id: "robot" }, property: "transform.position",
      keyframes: [{ time: 0, value: START }, ...points.map((p, i) => ({ time: 12 + i / (points.length - 1) * 11, value: p, easing: "linear" }))],
    }, {
      type: "track", target: { type: "node", id: "robot" }, property: "transform.rotation", interpolation: "discrete",
      keyframes: points.slice(0, -1).map((p, i) => ({ time: 12 + i / (points.length - 1) * 11, value: Math.atan2(points[i+1].y-p.y, points[i+1].x-p.x) * 180 / Math.PI })),
    }];
  }
  return { spec, ir, runtime: createAnimationRuntime(scene, { fps: FPS }) };
}
