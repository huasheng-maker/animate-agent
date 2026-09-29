"use client";

import type { PlayerRef } from "@remotion/player";
import { Player } from "@remotion/player";
import { useEffect, useMemo, useRef, useState } from "react";

import { normalizeRenderSpec } from "../../player/animation-ir.js";
import { beatAtFrame, buildBeatSeries } from "../../player/composition.js";
import { KnowledgeMovieComposition } from "./KnowledgeMovieComposition";
import styles from "./player.module.css";
import type { BeatEntry, BeatSeries, Citation, RenderControl, RenderSpec } from "./types";

type LoadedMovie = { spec: RenderSpec; ir: any; series: BeatSeries };

export default function PlayerPage() {
  const playerRef = useRef<PlayerRef>(null);
  const [movie, setMovie] = useState<LoadedMovie | null>(null);
  const [error, setError] = useState("");
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [ended, setEnded] = useState(false);
  const [overrides, setOverrides] = useState<Record<string, number | boolean>>({});
  const [overrideRevision, setOverrideRevision] = useState(0);

  useEffect(() => {
    void loadSpec().then(
      (spec) => {
        const ir = normalizeRenderSpec(spec);
        const series = buildBeatSeries(spec, ir) as BeatSeries;
        const defaults: Record<string, number | boolean> = {};
        for (const scene of spec.scenes) {
          for (const control of scene.controls ?? []) {
            if (control.type !== "button" && control.default !== null && control.default !== undefined) {
              defaults[control.target_property] = control.type === "toggle"
                ? Boolean(control.default)
                : Number(control.default);
            }
          }
        }
        setOverrides(defaults);
        setMovie({ spec, ir, series });
      },
      (reason) => setError(reason instanceof Error ? reason.message : String(reason)),
    );
  }, []);

  useEffect(() => {
    const player = playerRef.current;
    if (!player || !movie) return;
    const onFrame = (event: { detail: { frame: number } }) => setFrame(event.detail.frame);
    const onPlay = () => { setPlaying(true); setEnded(false); };
    const onPause = () => setPlaying(false);
    const onEnded = () => { setPlaying(false); setEnded(true); setFrame(movie.series.durationInFrames - 1); };
    player.addEventListener("frameupdate", onFrame);
    player.addEventListener("seeked", onFrame);
    player.addEventListener("play", onPlay);
    player.addEventListener("pause", onPause);
    player.addEventListener("ended", onEnded);
    return () => {
      player.removeEventListener("frameupdate", onFrame);
      player.removeEventListener("seeked", onFrame);
      player.removeEventListener("play", onPlay);
      player.removeEventListener("pause", onPause);
      player.removeEventListener("ended", onEnded);
    };
  }, [movie]);

  const active = useMemo(
    () => (movie ? beatAtFrame(movie.series, frame) as BeatEntry : null),
    [frame, movie],
  );
  const citations = useMemo(() => {
    if (!movie || !active) return [];
    const byId = new Map<string, Citation>((movie.ir.citations ?? []).map((item: Citation) => [item.id, item]));
    return active.beat.sourceRefs.map((id) => byId.get(id) ?? {
      id,
      title: movie.spec.title || "来源",
      locator: id,
      excerpt: "",
      url: null,
    });
  }, [active, movie]);

  if (error) return <main className={styles.status}><h1>播放器载入失败</h1><pre>{error}</pre></main>;
  if (!movie || !active) return <main className={styles.status}><h1>正在载入讲解动画…</h1></main>;

  const seekBeat = (delta: number) => {
    const index = Math.max(0, Math.min(movie.series.entries.length - 1, active.index + delta));
    playerRef.current?.seekTo(movie.series.entries[index].startFrame);
  };
  const stepFrame = (delta: number) => {
    playerRef.current?.pause();
    const next = Math.max(0, Math.min(movie.series.durationInFrames - 1, frame + delta));
    playerRef.current?.seekTo(next);
  };
  const replay = () => {
    playerRef.current?.seekTo(0);
    playerRef.current?.play();
  };

  return (
    <main className={styles.shell}>
      <header className={styles.header}>
        <div>
          <div className={styles.brand}><a href="/demos" style={{color:"inherit",textDecoration:"none"}}>ANIMATE/AGENT</a> <em>知识实验室</em></div>
          <p className={styles.eyebrow}>{movie.spec.eyebrow || movie.spec.subject}</p>
          <h1>{movie.spec.title || "Knowledge Movie"}</h1>
          <p className={styles.goal}>{active.renderScene.teaching_goal || ""}</p>
        </div>
        <div className={styles.beatActions}>
          <button type="button" onClick={() => seekBeat(-1)} disabled={active.index === 0}>上一拍</button>
          <button type="button" onClick={() => stepFrame(-1)}>上一帧</button>
          <button type="button" onClick={() => stepFrame(1)}>下一帧</button>
          <button type="button" onClick={() => seekBeat(1)} disabled={active.index === movie.series.entries.length - 1}>下一拍</button>
          {ended && <button type="button" className={styles.replay} onClick={replay}>从头重播</button>}
        </div>
      </header>

      <div className={styles.layout}>
        <section className={styles.playerPanel}>
          <Player
            ref={playerRef}
            component={KnowledgeMovieComposition}
            inputProps={{
              spec: movie.spec,
              ir: movie.ir,
              series: movie.series,
              overrides,
              overrideRevision,
            }}
            durationInFrames={movie.series.durationInFrames}
            compositionWidth={movie.spec.stage.width}
            compositionHeight={movie.spec.stage.height}
            fps={movie.ir.fps}
            autoPlay
            controls
            loop={false}
            moveToBeginningWhenEnded={false}
            showPlaybackRateControl={[0.5, 1, 1.5, 2]}
            style={{ width: "100%", aspectRatio: `${movie.spec.stage.width} / ${movie.spec.stage.height}` }}
          />
          <div className={styles.frameStatus}>
            第 {active.index + 1}/{movie.series.entries.length} 拍 · 帧 {frame}/{movie.series.durationInFrames - 1}
            {playing ? " · 播放中" : " · 已暂停"}
          </div>
        </section>

        <aside className={styles.sidebar}>
          <section className={styles.card}>
            <h2>教学节拍</h2>
            <ol className={styles.beats}>
              {movie.series.entries.map((entry) => (
                <li key={`${entry.scene.id}:${entry.beat.id}`}>
                  <button
                    type="button"
                    className={entry.index === active.index ? styles.activeBeat : ""}
                    onClick={() => playerRef.current?.seekTo(entry.startFrame)}
                  >
                    <strong>{String(entry.index + 1).padStart(2, "0")} {entry.beat.title}</strong>
                    <span>{entry.beat.narration}</span>
                  </button>
                </li>
              ))}
            </ol>
          </section>

          {active.renderScene.controls?.length > 0 && (
            <section className={styles.card}>
              <h2>交互参数</h2>
              <SceneControls
                controls={active.renderScene.controls}
                values={overrides}
                onChange={(key, value) => {
                  setOverrides((current) => ({ ...current, [key]: value }));
                  setOverrideRevision((current) => current + 1);
                }}
                onAction={(action) => {
                  if (action === "toggle_play") playerRef.current?.toggle();
                  else if (action === "advance_timeline") seekBeat(1);
                  else if (action === "reset_scene") playerRef.current?.seekTo(active.startFrame);
                }}
              />
            </section>
          )}

          <section className={styles.card} aria-live="polite">
            <h2>当前拍出处</h2>
            {citations.length === 0 ? <p className={styles.muted}>暂无逐拍出处</p> : citations.map((citation) => (
              <article className={styles.citation} key={citation.id}>
                <h3>{citation.title || "来源"}</h3>
                <p className={styles.locator}>{citation.locator || citation.id}</p>
                {citation.excerpt && <p>{citation.excerpt}</p>}
                {safeHttpUrl(citation.url) && (
                  <a href={citation.url!} target="_blank" rel="noopener noreferrer">打开原始来源</a>
                )}
              </article>
            ))}
          </section>
        </aside>
      </div>
    </main>
  );
}

function SceneControls({
  controls,
  values,
  onChange,
  onAction,
}: {
  controls: RenderControl[];
  values: Record<string, number | boolean>;
  onChange: (key: string, value: number | boolean) => void;
  onAction: (action: string | null | undefined) => void;
}) {
  return <div className={styles.controls}>{controls.map((control) => {
    if (control.type === "button") {
      return <button type="button" key={control.id} onClick={() => onAction(control.action)}>{control.label}</button>;
    }
    if (control.type === "toggle") {
      return <label key={control.id}><input type="checkbox" checked={Boolean(values[control.target_property])} onChange={(event) => onChange(control.target_property, event.target.checked)} /> {control.label}</label>;
    }
    const value = Number(values[control.target_property] ?? control.default ?? control.min ?? 0);
    return <label key={control.id}>
      <span>{control.label} <output>{value}{control.unit ? ` ${control.unit}` : ""}</output></span>
      <input type="range" min={control.min ?? 0} max={control.max ?? 1} step={control.step ?? 0.1} value={value} onChange={(event) => onChange(control.target_property, Number(event.target.value))} />
    </label>;
  })}</div>;
}

async function loadSpec(): Promise<RenderSpec> {
  const specUrl = new URLSearchParams(window.location.search).get("spec");
  if (!specUrl) throw new Error("缺少 spec 参数。请从生成页面打开播放器。");
  if (specUrl === "session") {
    const stored = window.sessionStorage.getItem("animate-agent-render-spec");
    if (!stored) throw new Error("当前浏览器会话里没有生成的 RenderSpec");
    return JSON.parse(stored) as RenderSpec;
  }
  const response = await fetch(specUrl);
  if (!response.ok) throw new Error(`取不到 spec：HTTP ${response.status}`);
  return await response.json() as RenderSpec;
}

function safeHttpUrl(value: string | null): boolean {
  if (!value) return false;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}
