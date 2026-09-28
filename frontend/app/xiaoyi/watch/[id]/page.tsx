"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import styles from "./watch.module.css";

type Snapshot = {
  run_id: string;
  status: string;
  stage: string;
  message: string;
  created_at: number;
  updated_at: number;
};

const stages: Record<string, string> = {
  queued: "等待开始", source_ingestion: "读取资料", lesson_generation: "组织讲解",
  storyboard_generation: "设计分镜", intent_storyboard_generation: "设计分镜",
  layout: "编排画面", animation_ir_compile: "编排动作", persist: "保存动画",
  completed: "动画已完成",
};
const terminal = new Set(["completed", "failed", "cancelled", "interrupted"]);

export default function XiaoyiWatchPage() {
  const { id } = useParams<{ id: string }>();
  const [job, setJob] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());
  const valid = /^[a-f0-9]{32}$/i.test(id ?? "");

  useEffect(() => {
    if (!valid) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const response = await fetch(`/api/animation-jobs/${id}`, { cache: "no-store" });
        if (!response.ok) throw new Error(response.status === 404 ? "找不到这段动画任务" : "暂时无法读取任务状态");
        const next = await response.json() as Snapshot;
        if (stopped) return;
        setJob(next);
        setError("");
        if (!terminal.has(next.status)) timer = setTimeout(refresh, 5000);
      } catch (reason) {
        if (stopped) return;
        setError(reason instanceof Error ? reason.message : "连接暂时中断");
        timer = setTimeout(refresh, 5000);
      }
    }
    void refresh();
    return () => { stopped = true; clearTimeout(timer); };
  }, [id, valid]);

  useEffect(() => {
    if (!job || terminal.has(job.status)) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [job]);

  const elapsed = job ? Math.max(0, Math.floor(((terminal.has(job.status) ? job.updated_at * 1000 : now) - job.created_at * 1000) / 1000)) : 0;
  const duration = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")}`;
  const resultPath = `/api/animation-jobs/${id}/result`;
  const playerUrl = `/player?spec=${encodeURIComponent(resultPath)}`;

  return <main className={styles.shell}>
    <header><a href="/">ANIMATE / AGENT</a><span>小艺 · 知识电影</span></header>
    <section className={styles.card} aria-live="polite">
      <p className={styles.eyebrow}>从问题到看得见的理解</p>
      <h1>{!valid ? "链接无效" : job?.status === "completed" ? "你的动画已准备好" : "正在制作知识电影"}</h1>
      {!valid ? <p>请从小艺返回的观看链接打开。</p> : <>
        <p className={styles.status}>{error || (job ? stages[job.stage] ?? job.message : "正在连接生成服务…")}</p>
        {job && <p className={styles.time}>已用时 {duration} · {terminal.has(job.status) ? "任务已结束" : "可稍后返回，进度会继续保存"}</p>}
        {job?.status === "completed" && <a className={styles.play} href={playerUrl}>播放并探索动画 →</a>}
        {job && ["failed", "cancelled", "interrupted"].includes(job.status) && <p role="alert">{job.message}</p>}
      </>}
    </section>
  </main>;
}
