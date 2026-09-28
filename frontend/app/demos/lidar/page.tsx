"use client";

import { Player, type PlayerRef } from "@remotion/player";
import { useEffect, useMemo, useRef, useState } from "react";
import { DEFAULTS, DURATION, FPS, PHASE_FRAMES, phaseAt, solve, WORLD } from "../../../player/lidar/model.js";
import plan from "../../../player/lidar/visual-plan.json";
import { LidarComposition, type Settings } from "./LidarComposition";
import styles from "./page.module.css";

export default function LidarDemo() {
  const [settings, setSettings] = useState<Settings>({ ...DEFAULTS });
  const [frame, setFrame] = useState(0);
  const [answer, setAnswer] = useState<number | null>(null);
  const ref = useRef<PlayerRef>(null);
  const result = useMemo(() => solve(settings), [settings]);
  const phase = phaseAt(frame);
  useEffect(() => {
    const player = ref.current;
    if (!player) return;
    const update = (event: { detail: { frame: number } }) => setFrame(event.detail.frame);
    player.addEventListener("frameupdate", update);
    player.addEventListener("seeked", update);
    return () => { player.removeEventListener("frameupdate", update); player.removeEventListener("seeked", update); };
  }, []);
  const change = (patch: Partial<Settings>, at = 240) => {
    ref.current?.pause();
    setSettings((old) => ({ ...old, ...patch }));
    ref.current?.seekTo(at);
    setFrame(at);
  };
  const seek = (index: number) => { ref.current?.pause(); ref.current?.seekTo(PHASE_FRAMES[index]); setFrame(PHASE_FRAMES[index]); };
  const found = result.path.length > 0;
  const visited = phase < 2 ? 0 : phase === 2 ? Math.floor(result.expanded.length * Math.min(1, (frame-240)/100)) : result.expanded.length;
  return <main className={styles.shell}>
    <nav className={styles.nav}><a href="/">ANIMATE AGENT <span>/ LEARNING LAB</span></a><span>01 — 机器人导航</span></nav>
    <header className={styles.header}>
      <p className={styles.eyebrow}>看得见的机制 · 可验证的理解</p>
      <h1>看见障碍，<span>然后绕过去。</span></h1>
      <p>让一束激光、一片安全空间和一次路径搜索，解释机器人如何抵达目标。</p>
    </header>
    <div className={styles.layout}>
      <section className={styles.stagePanel} aria-label="教学动画">
        <div className={styles.stageBar}><span><i /> 实验场 / TOP VIEW</span><span>{String(phase+1).padStart(2,"0")} · {plan.beats[phase].title}</span></div>
        <Player ref={ref} component={LidarComposition} inputProps={{ settings, result }} durationInFrames={DURATION} fps={FPS} compositionWidth={WORLD.width} compositionHeight={WORLD.height} controls clickToPlay={false} style={{ width: "100%", aspectRatio: `${WORLD.width}/${WORLD.height}` }} />
        <div className={styles.legend}><span>● 回波</span><span>■ 障碍实物</span><span>■ 安全禁区</span><span>■ 搜索访问</span><span>━ 规划路线</span></div>
        <div className={styles.chapters}>{plan.beats.map((beat, i) => <button key={beat.id} aria-pressed={phase===i} onClick={() => seek(i)}><small>0{i+1}</small>{beat.title}</button>)}</div>
        <div className={styles.narration}><span>这一刻，理解什么？</span><p>{plan.beats[phase].explanation}</p></div>
      </section>
      <aside className={styles.controls}>
        <div className={styles.asideHeading}><span>动手改变一个条件</span><button onClick={() => { change({ ...DEFAULTS }, 0); setAnswer(null); }}>重置</button></div>
        <p className={styles.hint}>先预测结果，再播放。修改会暂停动画并重新计算。</p>
        <label>实验环境<select value={settings.preset} onChange={(e) => change({ preset: e.target.value })}><option value="detour">绕开货架</option><option value="gap">窄门实验</option><option value="wall">完全封路</option></select></label>
        <label>规划依据<select value={settings.mode} onChange={(e) => change({ mode: e.target.value }, 0)}><option value="known">已知静态地图</option><option value="sensor">仅起点单帧雷达</option></select></label>
        <div className={styles.sliders}>
          <label>货架纵向位置 <output>{settings.obstacleY} 格</output><input aria-label="货架纵向位置" type="range" min={2} max={12} step={1} disabled={settings.preset!=="detour"} value={settings.obstacleY} onChange={(e) => change({ obstacleY: Number(e.target.value) })} /></label>
          <label>机器人半径 <output>{(settings.radius/60).toFixed(2)} m</output><input aria-label="机器人半径" type="range" min={10} max={30} step={2} value={settings.radius} onChange={(e) => change({ radius: Number(e.target.value) }, 120)} /></label>
          <label>安全余量 <output>{(settings.margin/60).toFixed(2)} m</output><input aria-label="安全余量" type="range" min={0} max={18} step={2} value={settings.margin} onChange={(e) => change({ margin: Number(e.target.value) }, 120)} /></label>
          <label>雷达量程 <output>{(settings.range/60).toFixed(1)} m</output><input aria-label="雷达量程" type="range" min={180} max={900} step={60} value={settings.range} onChange={(e) => change({ range: Number(e.target.value) }, 0)} /></label>
        </div>
        <div className={styles.result} role="status" data-testid="plan-result">
          <span>本次完整计算</span><strong>{found ? "找到可行路径" : settings.mode === "sensor" ? "观测不足，保持停止" : "没有可行路径，保持停止"}</strong>
          <div><span>路线长度<b>{found ? `${(result.cost*24/60).toFixed(1)} m` : "—"}</b></span><span>已展示搜索<b>{visited} / {result.expanded.length} 格</b></span></div>
        </div>
        <p className={styles.modelNote}>{settings.mode === "known" ? "量程只改变测量。这里已有静态地图，A* 不需要从这一帧雷达重建全图。" : "场景可见 ≠ 机器人已知。灰色区域缺少观测，规划器不会把它当作空地。"}</p>
      </aside>
    </div>
    <section className={styles.questions}><div><p className={styles.eyebrow}>理解检查</p><h2>如果改变条件，<br />你能预测结果吗？</h2></div><div>{plan.checks.map((check, i) => <article key={check.question}><button aria-expanded={answer===i} onClick={() => setAnswer(answer===i ? null : i)}>{check.question}<span>{answer===i ? "−" : "+"}</span></button>{answer===i && <p>{check.answer}</p>}</article>)}</div></section>
    <footer className={styles.footer}><strong>这个模型解释什么，以及它的边界</strong><p>{plan.model.assumptions.join("；")}。不模拟 SLAM、动态避障或真实车辆控制。机器人沿离散路线运动，转角处瞬时改变朝向。</p><p>原理参考：<a href="https://docs.nav2.org/rolling/configuration_and_development/first_time_robot_setup_guide/footprint/setup_footprint/">Nav2 机器人轮廓</a> · <a href="https://theory.stanford.edu/~amitp/GameProgramming/Heuristics.html">A* 启发式</a>。本例是手工编排的验证 Demo，不代表自动生成质量已经达到这一水平。</p></footer>
  </main>;
}
