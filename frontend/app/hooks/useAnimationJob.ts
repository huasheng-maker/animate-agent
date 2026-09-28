"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { DocumentIR } from "./useSourceWorkflow";

export type JobSnapshot = {
  run_id: string; mode: string; seq: number; status: string; stage: string;
  created_at: number; updated_at: number; message: string; calls: number;
  completed_stages: string[];
  artifacts: {
    document?: DocumentIR;
    lesson?: { title: string; scenes: { id: string; title: string; summary?: string }[] };
    storyboard?: { title: string; scenes: { id: string; title: string }[] };
  };
};

const STORAGE = "animate-agent-generation-job";
const terminal = new Set(["completed", "failed", "cancelled", "interrupted"]);
export const isJobActive = (job: JobSnapshot | null) => !!job && !terminal.has(job.status);

function saved(): { id: string; fingerprint: string } | null {
  try {
    const value = JSON.parse(localStorage.getItem(STORAGE) ?? "null");
    return typeof value?.id === "string" && typeof value?.fingerprint === "string"
      ? { id: value.id.replaceAll("-", ""), fingerprint: value.fingerprint } : null;
  } catch { return null; }
}

async function readResponse(response: Response) {
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "任务请求失败");
  return body;
}

export function useAnimationJob() {
  const [job, setJob] = useState<JobSnapshot | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [connection, setConnection] = useState("connecting");
  const [error, setError] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const current = useRef<JobSnapshot | null>(null);
  const submittingRef = useRef(false);

  const accept = useCallback((next: JobSnapshot) => {
    if (current.current?.run_id === next.run_id && current.current.seq > next.seq) return;
    current.current = next;
    setJob(next);
    if (terminal.has(next.status)) setCollapsed(false);
  }, []);

  useEffect(() => { const previous = saved(); if (previous?.id) setRunId(previous.id); }, []);

  useEffect(() => {
    if (!runId) return;
    let disposed = false;
    let stream: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout>;
    let lastSignal = 0;
    let lastSnapshotCheck = 0;
    const controller = new AbortController();

    async function poll() {
      try {
        // A healthy SSE connection owns updates. Poll only on disconnect/stall.
        if (stream?.readyState === EventSource.OPEN) {
          if (Date.now() - lastSignal < 35000 && Date.now() - lastSnapshotCheck < 60000) return;
          if (Date.now() - lastSignal >= 35000) {
            stream.close();
            stream = null;
          }
        }
        const response = await fetch(`/api/animation-jobs/${runId}`, {
          cache: "no-store", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]),
        });
        if (response.status === 404) {
          if (!disposed) setError("尚未找到任务。如果提交时断网，请用原输入再次点击生成，系统会避免重复提交。");
          return;
        }
        const state = await readResponse(response) as JobSnapshot;
        lastSnapshotCheck = Date.now();
        if (disposed) return;
        accept(state);
        setError("");
        setConnection(stream?.readyState === EventSource.OPEN ? "live" : "polling");
        if (terminal.has(state.status)) { stream?.close(); return; }
        if (!stream) {
          stream = new EventSource(`/api/animation-jobs/${runId}/events?after=${state.seq}`);
          stream.onopen = () => {
            lastSignal = Date.now();
            if (!disposed) setConnection("live");
          };
          stream.addEventListener("heartbeat", (event) => {
            lastSignal = Date.now();
            if (disposed) return;
            setConnection("live");
            try {
              const state = JSON.parse((event as MessageEvent).data) as JobSnapshot;
              if (state.run_id === runId && typeof state.seq === "number") {
                accept(state);
                if (terminal.has(state.status)) { stream?.close(); clearTimeout(timer); }
              }
            } catch { lastSignal = 0; }
          });
          stream.onmessage = (event) => {
            if (disposed) return;
            lastSignal = Date.now();
            try {
              const next = JSON.parse(event.data) as JobSnapshot;
              accept(next);
              if (terminal.has(next.status)) { stream?.close(); clearTimeout(timer); }
            } catch { setConnection("polling"); }
          };
          stream.onerror = () => { if (!disposed) setConnection("polling"); };
        }
      } catch {
        if (!disposed) setConnection("offline");
      } finally {
        if (!disposed && !(current.current?.run_id === runId && terminal.has(current.current.status))) {
          timer = setTimeout(poll, 5000);
        }
      }
    }
    void poll();
    return () => { disposed = true; controller.abort(); stream?.close(); clearTimeout(timer); };
  }, [runId, accept, refreshVersion]);

  async function start(mode: string, request: RequestInit) {
    if (submittingRef.current || isJobActive(current.current)) return;
    submittingRef.current = true;
    setSubmitting(true); setError(""); setCollapsed(false);
    try {
      let content: Uint8Array;
      if (request.body instanceof FormData) {
        const file = request.body.get("file") as File;
        const header = new TextEncoder().encode(`${mode}:${file.name}:`);
        content = new Uint8Array(header.length + file.size);
        content.set(header); content.set(new Uint8Array(await file.arrayBuffer()), header.length);
      } else content = new TextEncoder().encode(String(request.body));
      const hash = await crypto.subtle.digest("SHA-256", content as BufferSource);
      const fingerprint = Array.from(new Uint8Array(hash), n => n.toString(16).padStart(2, "0")).join("");
      const previous = saved();
      const id = previous?.fingerprint === fingerprint && !terminal.has(current.current?.status ?? "")
        ? previous.id : crypto.randomUUID().replaceAll("-", "");
      // Persist before sending: a lost POST response can be recovered with the same id.
      localStorage.setItem(STORAGE, JSON.stringify({ id, fingerprint }));
      current.current = null; setJob(null); setRunId(id);
      const response = await fetch("/api/animation-jobs", {
        ...request, headers: { ...request.headers, "Idempotency-Key": id },
        signal: AbortSignal.timeout(30000),
      });
      accept(await readResponse(response) as JobSnapshot);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "提交未确认，请保留输入后重试。");
    } finally { submittingRef.current = false; setSubmitting(false); }
  }

  async function cancel() {
    if (!runId) return;
    try {
      accept(await readResponse(await fetch(`/api/animation-jobs/${runId}/cancel`, {
        method: "POST", signal: AbortSignal.timeout(10000),
      })) as JobSnapshot);
      setError("");
    } catch { setError("取消尚未确认，请恢复连接后重试；任务可能仍在运行。"); }
  }

  return { job, submitting, active: isJobActive(job), connection, error, collapsed, setCollapsed, start, cancel,
    refresh: () => setRefreshVersion(value => value + 1) };
}
