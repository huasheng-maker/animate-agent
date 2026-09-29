"use client";

import type { Caption } from "@remotion/captions";
import { gsap } from "gsap";
import { useLayoutEffect, useMemo, useRef } from "react";
import { AbsoluteFill, Series, useCurrentFrame, useVideoConfig } from "remotion";

import { createAnimationRuntime } from "../../player/runtime.js";
import { createSimulation } from "../../player/behaviors.js";
import { createCanvas2DRenderer } from "../../player/canvas2d-renderer.js";
import { drawMechanism } from "../../player/mechanisms/draw.js";
import { registerGsap } from "../../player/gsap-easing.js";
import { createCompositionStage, readTheme } from "../../player/stage.js";
import type { BeatEntry, BeatSeries, RenderSpec } from "./types";
import { ComposableStage } from "./ComposableStage";

registerGsap(gsap);

export type KnowledgeMovieCompositionProps = {
  spec: RenderSpec;
  ir: any;
  series: BeatSeries;
  overrides: Record<string, number | boolean>;
  overrideRevision: number;
};

export function KnowledgeMovieComposition(props: KnowledgeMovieCompositionProps) {
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ backgroundColor: "#050507" }}>
      <Series>
        {props.series.entries.map((entry) => (
          <Series.Sequence
            key={`${entry.scene.id}:${entry.beat.id}`}
            durationInFrames={entry.durationInFrames}
            premountFor={fps}
            name={`${entry.index + 1}. ${entry.beat.title}`}
          >
            <CanvasBeat {...props} entry={entry} />
          </Series.Sequence>
        ))}
      </Series>
    </AbsoluteFill>
  );
}

function CanvasBeat({
  spec,
  ir,
  entry,
  overrides,
  overrideRevision,
}: KnowledgeMovieCompositionProps & { entry: BeatEntry }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const program = entry.scene.mechanism ?? entry.renderScene.mechanism;
  const drawingRef = useRef<{
    canvas: HTMLCanvasElement;
    viewport: ReturnType<typeof createCompositionStage>;
    renderer: ReturnType<typeof createCanvas2DRenderer>;
    theme: ReturnType<typeof readTheme>;
  } | null>(null);
  const caption: Caption = useMemo(
    () => ({
      text: entry.beat.narration,
      startMs: 0,
      endMs: (entry.durationInFrames / fps) * 1000,
      timestampMs: null,
      confidence: null,
    }),
    [entry.beat.narration, entry.durationInFrames, fps],
  );
  const engine = useMemo(() => {
    const runtime = createAnimationRuntime(entry.scene, { fps });
    runtime.setStep(entry.beatIndex);
    const simulation = createSimulation(entry.renderScene, spec.stage);
    return { runtime, simulation };
  }, [entry, fps, spec.stage]);

  useLayoutEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    if (!drawingRef.current || drawingRef.current.canvas !== canvas) {
      const viewport = createCompositionStage(canvas, spec.stage);
      drawingRef.current = {
        canvas,
        viewport,
        renderer: createCanvas2DRenderer(viewport.ctx),
        theme: readTheme(canvas.closest("section") ?? document.documentElement),
      };
    }
    const { viewport, renderer, theme } = drawingRef.current;
    const mechanism = entry.scene.mechanism ?? entry.renderScene.mechanism;
    if (mechanism) {
      viewport.clear();
      drawMechanism(viewport.ctx, mechanism, {
        ...spec.stage,
        beatIndex: entry.beatIndex,
        progress: frame / Math.max(1, entry.durationInFrames - 1),
        overrides,
        sceneId: entry.renderScene.id,
      });
      return;
    }
    engine.runtime.setLegacyOverrides(overrides);
    const lookup = (elementId: string, prop: string, fallback: unknown) =>
      engine.runtime.lookup(elementId, prop, fallback);
    engine.simulation.seekFrame(frame, fps, lookup, overrideRevision);
    const sceneState = engine.runtime.seekFrame(frame, { legacyLive: engine.simulation.live });
    const byId = new Map(entry.renderScene.elements.map((element) => [element.id, element]));
    const obstacleIds = entry.renderScene.elements
      .filter((element) => element.role === "obstacle")
      .map((element) => element.id);
    const obstacleRadius = new Map(
      obstacleIds.map((id) => [id, Number(byId.get(id)?.props?.radius ?? 0)]),
    );
    const timelineHighlights = sceneState.nodes
      .filter((node: any) => node.style.highlight === true)
      .map((node: any) => node.id);
    const authoredHighlights = (entry.renderScene.steps[entry.beatIndex]?.highlights ?? []) as string[];
    renderer.render(sceneState, {
      stage: spec.stage,
      clear: viewport.clear,
      view: {
        live: engine.simulation.live,
        time: sceneState.time,
        frame,
        theme,
        lookup,
        elementById: byId,
        obstacleIds,
        obstacleRadius,
        highlighted: new Set([...authoredHighlights, ...timelineHighlights]),
        sceneState,
        isDangerous: (id: string) => engine.simulation.isDangerous(id),
      },
    });
  }, [engine, entry, fps, frame, ir, overrideRevision, overrides, spec.stage]);

  return (
    <AbsoluteFill style={{ backgroundColor: "#050507" }}>
      {program?.kind === "composition" ? <ComposableStage
        plan={program} sceneId={entry.renderScene.id} beatIndex={entry.beatIndex}
        time={(entry.scene.beats.slice(0, entry.beatIndex).reduce(
          (sum: number, beat: any) => sum + beat.durationInFrames, 0,
        ) + frame) / fps}
        progress={frame / Math.max(1, entry.durationInFrames - 1)}
        width={spec.stage.width} height={spec.stage.height} overrides={overrides}
      /> : <canvas
        ref={canvasRef}
        aria-label={entry.renderScene.title || entry.beat.title}
        style={{ width: "100%", height: "100%", display: "block" }}
      />}
      <div
        style={{
          position: "absolute",
          right: 24,
          bottom: program?.kind === "composition" ? 54 : 22,
          left: 24,
          padding: "12px 18px",
          height: program?.kind === "composition" ? 130 : undefined,
          overflow: "auto",
          color: "#f4f7ee",
          background: "linear-gradient(90deg, rgba(5,5,7,.94), rgba(5,5,7,.72))",
          borderLeft: "3px solid #8addcc",
          fontFamily: "Inter, system-ui, sans-serif",
        }}
      >
        <div style={{ marginBottom: 6, color: "#8addcc", fontSize: 16, fontWeight: 700 }}>
          {String(entry.index + 1).padStart(2, "0")} · {entry.beat.title}
        </div>
        <div style={{ fontSize: 20, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{caption.text}</div>
      </div>
    </AbsoluteFill>
  );
}
