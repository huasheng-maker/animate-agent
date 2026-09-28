"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useAnimationJob } from "./useAnimationJob";

export type DocumentBlock = {
  id: string;
  type: "paragraph" | "code" | "list" | "image";
  text: string;
  language?: string | null;
  source_ref?: string | null;
};

export type Section = {
  id: string;
  title: string;
  level: number;
  blocks: DocumentBlock[];
};

export type DocumentIR = {
  document_id: string;
  title: string;
  sections: Section[];
};

type RenderSpec = {
  storyboard_id: string;
  title: string;
  scenes: unknown[];
};

export type InputMode = "url" | "query" | "file";
export type LoadingState = "document" | "animation" | "controller" | "preview" | "latest" | null;

function apiEndpoint(kind: "documents" | "animations", mode: InputMode) {
  const path = `/api/${kind}/from-${mode}`;
  return process.env.NEXT_PUBLIC_API_BASE_URL
    ? `${process.env.NEXT_PUBLIC_API_BASE_URL}${path}`
    : path;
}

export function useSourceWorkflow() {
  const generation = useAnimationJob();
  const [mode, setMode] = useState<InputMode>("url");
  const [url, setUrl] = useState(
    "https://raw.githubusercontent.com/ManimCommunity/manim/main/docs/source/tutorials/quickstart.rst",
  );
  const [query, setQuery] = useState("How does retrieval-augmented generation work?");
  const [file, setFile] = useState<File | null>(null);
  const [document, setDocument] = useState<DocumentIR | null>(null);
  const [activeSectionId, setActiveSectionId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState<LoadingState>(null);
  const previewDocument = generation.job?.artifacts.document;
  useEffect(() => {
    if (previewDocument) {
      setDocument(previewDocument);
      setActiveSectionId(previewDocument.sections[0]?.id ?? null);
    }
  }, [previewDocument?.document_id]);

  const activeSection = useMemo(
    () => document?.sections.find((section) => section.id === activeSectionId) ?? null,
    [activeSectionId, document],
  );
  const hasInput = mode === "file" ? file !== null : (mode === "url" ? url : query).trim() !== "";

  function sourceRequest(): RequestInit {
    if (mode === "file") {
      if (file === null) throw new Error("请先选择一个文档文件。");
      const body = new FormData();
      body.append("file", file);
      return { method: "POST", body };
    }
    const body = mode === "url" ? { url } : { query };
    return {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    };
  }

  function selectMode(nextMode: InputMode) {
    setMode(nextMode);
    setDocument(null);
    setActiveSectionId(null);
    setError("");
  }

  function openPlayer(spec: RenderSpec) {
    if (!spec.storyboard_id || !Array.isArray(spec.scenes) || spec.scenes.length === 0) {
      throw new Error("The backend returned an empty or invalid RenderSpec.");
    }
    window.sessionStorage.setItem("animate-agent-render-spec", JSON.stringify(spec));
    window.location.assign("/player?spec=session");
  }

  async function parseDocument(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    setLoading("document");
    setError("");
    try {
      const response = await fetch(apiEndpoint("documents", mode), sourceRequest());
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? `Request failed (${response.status})`);
      }
      const nextDocument = (await response.json()) as DocumentIR;
      setDocument(nextDocument);
      setActiveSectionId(nextDocument.sections[0]?.id ?? null);
    } catch (reason) {
      setDocument(null);
      setActiveSectionId(null);
      setError(
        reason instanceof TypeError
          ? "Could not reach the frontend API route. Check that the Next.js development server is still running, then retry."
          : reason instanceof Error
            ? reason.message
            : "Could not parse this document.",
      );
    } finally {
      setLoading(null);
    }
  }

  async function generateAnimation() {
    setError("");
    setDocument(null);
    try {
      const request = mode === "file" ? sourceRequest() : {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, value: mode === "url" ? url : query }),
      };
      await generation.start(mode, request);
    } catch (reason) {
      setError(
        reason instanceof TypeError
          ? "Could not reach the animation API. Check that both development servers are running, then retry."
          : reason instanceof Error
            ? reason.message
            : `Could not generate an animation from this ${mode} input.`,
      );
      setLoading(null);
    }
  }

  async function openControllerExample(preview: boolean) {
    if (!preview) {
      setDocument(null);
      await generation.start("example", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "example", value: "controller" }),
      });
      return;
    }
    setLoading(preview ? "preview" : "controller");
    setError("");
    try {
      const response = await fetch(
        preview ? "/api/animations/examples/controller/preview" : "/api/animations/from-example",
        preview
          ? { cache: "no-store" }
          : {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ example_id: "controller" }),
            },
      );
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? `Request failed (${response.status})`);
      }
      openPlayer((await response.json()) as RenderSpec);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not open the Controller animation.");
      setLoading(null);
    }
  }

  async function openLatestControllerAnimation() {
    setLoading("latest");
    setError("");
    try {
      const response = await fetch("/api/animations/examples/controller/latest", { cache: "no-store" });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? `Request failed (${response.status})`);
      }
      openPlayer((await response.json()) as RenderSpec);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not open the latest generated result.");
      setLoading(null);
    }
  }

  async function openGeneratedMovie() {
    if (!generation.job) return;
    try {
      const response = await fetch(`/api/animation-jobs/${generation.job.run_id}/result`, { cache: "no-store" });
      if (!response.ok) throw new Error("无法读取动画结果，请稍后重试。");
      openPlayer(await response.json() as RenderSpec);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "无法打开动画"); }
  }

  return {
    mode,
    url,
    query,
    file,
    document,
    activeSection,
    activeSectionId,
    error: error || generation.error,
    generation,
    openGeneratedMovie,
    loading,
    hasInput,
    setUrl,
    setQuery,
    setFile,
    setActiveSectionId,
    selectMode,
    parseDocument,
    generateAnimation,
    openControllerExample,
    openLatestControllerAnimation,
  };
}
