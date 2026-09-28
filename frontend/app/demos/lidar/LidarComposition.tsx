"use client";

import { useLayoutEffect, useMemo, useRef } from "react";
import { useCurrentFrame } from "remotion";
import { createCanvas2DRenderer } from "../../../player/canvas2d-renderer.js";
import { createCompositionStage } from "../../../player/stage.js";
import { createDemoScene } from "../../../player/lidar/scene.js";
import { drawMap, drawRobotDetails, THEME } from "../../../player/lidar/draw.js";
import { DEFAULTS, solve, WORLD } from "../../../player/lidar/model.js";

export type Settings = typeof DEFAULTS;
export type Result = ReturnType<typeof solve>;
export function LidarComposition({ settings, result }: { settings: Settings; result: Result }) {
  const frame = useCurrentFrame();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const engine = useMemo(() => createDemoScene(result, settings), [result, settings]);
  const surface = useRef<ReturnType<typeof createCompositionStage> | null>(null);
  useLayoutEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    surface.current ??= createCompositionStage(canvas, WORLD);
    const { ctx } = surface.current;
    const state = engine.runtime.seekFrame(frame);
    const node = state.nodeById.get("robot")!;
    const robot = { ...node.transform.position, heading: node.transform.rotation };
    createCanvas2DRenderer(ctx).render(state, {
      stage: WORLD,
      chrome: false,
      clear: () => drawMap(ctx, result, settings, frame, robot),
      view: { theme: THEME, live: new Map([["robot", robot]]), highlighted: new Set(), lookup: (_id: string, _prop: string, fallback: unknown) => fallback, isDangerous: () => false, sceneState: state },
    });
    drawRobotDetails(ctx, robot, settings.radius);
  }, [engine, frame, result, settings]);
  return <canvas ref={canvasRef} aria-label="机器人、激光回波、安全禁区和 A 星规划路线的俯视动画" style={{ width: "100%", height: "100%" }} />;
}
