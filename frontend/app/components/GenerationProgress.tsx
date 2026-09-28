"use client";

import { useEffect, useRef, useState } from "react";
import type { useAnimationJob } from "../hooks/useAnimationJob";
import styles from "./generation-progress.module.css";

const labels: Record<string, string> = {
  queued: "等待开始", source_ingestion: "读取资料", lesson_generation: "组织讲解",
  storyboard_generation: "设计分镜", intent_storyboard_generation: "设计分镜",
  layout: "编排画面", animation_ir_compile: "编排动作", persist: "保存动画",
  completed: "动画已完成",
};

export function GenerationProgress({ generation, onPlay, onRetry, canRetry }: {
  generation: ReturnType<typeof useAnimationJob>; onPlay: () => void;
  onRetry: () => void; canRetry: boolean;
}) {
  const { job, active, connection, collapsed, setCollapsed, cancel, submitting } = generation;
  const [now, setNow] = useState(Date.now());
  const [visible, setVisible] = useState(true);
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    if (job && window.matchMedia("(max-width: 760px)").matches) {
      panel.current?.scrollIntoView({ block: "start", behavior: "instant" });
    }
  }, [job?.run_id]);
  useEffect(() => {
    const update = () => { setVisible(!document.hidden); setNow(Date.now()); };
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => { if (!document.hidden) setNow(Date.now()); }, 1000);
    return () => clearInterval(timer);
  }, [active]);
  if (!job) return submitting ? <div className={styles.panel} role="status">正在提交生成任务…</div> : null;
  const elapsed = Math.max(0, Math.floor(((active ? now / 1000 : job.updated_at) - job.created_at)));
  const duration = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")}`;
  const stopped = ["failed", "interrupted", "cancelled"].includes(job.status);
  const title = stopped ? { failed: "生成失败", interrupted: "生成已中断", cancelled: "生成已取消" }[job.status] : labels[job.stage];
  const scenes = job.artifacts.storyboard?.scenes ?? job.artifacts.lesson?.scenes;
  const steps = [
    { name: "读取资料", done: !!job.artifacts.document, current: job.stage === "source_ingestion" },
    ...(job.mode !== "query" ? [{ name: "组织讲解", done: !!job.artifacts.lesson, current: job.stage === "lesson_generation" }] : []),
    { name: "设计分镜", done: !!job.artifacts.storyboard, current: job.stage.includes("storyboard") },
    { name: "完成动画", done: job.status === "completed", current: ["layout", "animation_ir_compile", "persist"].includes(job.stage) },
  ];
  return <section ref={panel} className={`${styles.panel} ${collapsed ? styles.compact : ""}`} data-paused={!active || !visible} aria-label="动画生成进度">
    <div className={styles.heading}>
      <div><span className={styles.eyebrow}>YOUR KNOWLEDGE, TAKING SHAPE</span><h3 aria-live="polite">{title ?? "准备生成"}</h3></div>
      <span className={styles.clock} aria-label={`已用时 ${duration}`}>{duration}</span>
    </div>
    {stopped && <p className={styles.failure} role="alert">{job.message} 本次任务已停止，不会继续等待或自动重试。</p>}
    {active && <p className={styles.connection} role="status">{connection === "offline"
      ? "连接暂时中断，正在自动重连。后台任务可能仍在继续。"
      : connection === "polling" ? "正在定期同步进度 · 后台生成继续" : "后台生成中 · 可离开此页，返回后自动恢复"}</p>}
    {!collapsed && <>
      <ol className={styles.steps} aria-label="生成阶段">{steps.map(step => <li key={step.name}
        className={step.done ? styles.done : step.current && active ? styles.current : ""}
        aria-current={step.current && active ? "step" : undefined}>
        <span>{step.done ? "✓" : step.current && active ? "◉" : "○"}</span>{step.name}
      </li>)}</ol>
      {!job.artifacts.document && <div className={styles.assembly} aria-hidden="true">
        <i /><i /><i /><div>资料 → 讲解 → 动画</div>
      </div>}
      {job.artifacts.document && <div className={styles.content}>
        <div className={styles.contentTitle}><strong>{job.artifacts.document.title}</strong><span>资料摘录 · 最多展示 24 节</span></div>
        <div className={styles.sources}>{job.artifacts.document.sections.map(section => <details key={section.id}>
          <summary>{section.title || "正文"}<span>{section.blocks.length} 段摘录</span></summary>
          {section.blocks.map(block => <p key={block.id}>{block.text}</p>)}
        </details>)}</div>
      </div>}
      {scenes && <div className={styles.content}>
        <div className={styles.contentTitle}><strong>{job.artifacts.storyboard ? "分镜已就绪" : "讲解结构已就绪"}</strong><span>{scenes.length} 个场景</span></div>
        <div className={styles.scenes}>{scenes.map((scene, index) => <article key={scene.id}>
          <span>SCENE {String(index + 1).padStart(2, "0")}</span><h4>{scene.title}</h4>
          {"summary" in scene && <p>{String(scene.summary)}</p>}
        </article>)}</div>
      </div>}
      {!stopped && job.message && <p className={styles.message} aria-live="polite">{job.message}</p>}
      {active && now / 1000 - job.updated_at > 30 && <p className={styles.message}>此阶段仍在处理，暂时没有新内容。已完成内容可以先阅读。</p>}
    </>}
    <div className={styles.actions}>
      {job.status === "completed" && <button className={styles.play} onClick={onPlay}>播放完整动画 ↗</button>}
      <button onClick={() => setCollapsed(!collapsed)}>{collapsed ? "展开生成详情" : active ? "收起，后台继续" : "收起详情"}</button>
      {active && <button onClick={() => void cancel()}>取消生成</button>}
      <button onClick={generation.refresh}>重新同步状态</button>
      {stopped && <button disabled={!canRetry} onClick={onRetry}>使用左侧输入重新生成</button>}
      {stopped && <span>已完成内容已保留。可从左侧重新提交。</span>}
    </div>
  </section>;
}
