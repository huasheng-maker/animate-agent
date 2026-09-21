"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  buildKnowledgeGraph,
  KnowledgeGraph,
  type KnowledgeGraphNode,
} from "./components/KnowledgeGraph";
import { useSourceWorkflow } from "./hooks/useSourceWorkflow";

type DocumentBlock = {
  id: string;
  type: "paragraph" | "code" | "list" | "image";
  text: string;
  language?: string | null;
  source_ref?: string | null;
};

type Section = {
  id: string;
  title: string;
  level: number;
  blocks: DocumentBlock[];
};

type DocumentIR = {
  document_id: string;
  title: string;
  sections: Section[];
};

type RenderSpec = {
  storyboard_id: string;
  title: string;
  scenes: unknown[];
};

type InputMode = "url" | "query" | "file";

function apiEndpoint(kind: "documents" | "animations", mode: InputMode) {
  const path = `/api/${kind}/from-${mode}`;
  return process.env.NEXT_PUBLIC_API_BASE_URL
    ? `${process.env.NEXT_PUBLIC_API_BASE_URL}${path}`
    : path;
}

function LegacyHome() {
  const [mode, setMode] = useState<InputMode>("url");
  const [url, setUrl] = useState(
    "https://raw.githubusercontent.com/ManimCommunity/manim/main/docs/source/tutorials/quickstart.rst",
  );
  const [query, setQuery] = useState("How does retrieval-augmented generation work?");
  const [file, setFile] = useState<File | null>(null);
  const [document, setDocument] = useState<DocumentIR | null>(null);
  const [activeSectionId, setActiveSectionId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState<
    "document" | "animation" | "controller" | "preview" | "latest" | null
  >(null);

  const activeSection = document?.sections.find((section) => section.id === activeSectionId);
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

  async function parseDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
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
    setLoading("animation");
    setError("");
    try {
      const response = await fetch(apiEndpoint("animations", mode), sourceRequest());
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? `Request failed (${response.status})`);
      }
      openPlayer((await response.json()) as RenderSpec);
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

  function openPlayer(spec: RenderSpec) {
    if (!spec.storyboard_id || !Array.isArray(spec.scenes) || spec.scenes.length === 0) {
      throw new Error("The backend returned an empty or invalid RenderSpec.");
    }
    window.sessionStorage.setItem("animate-agent-render-spec", JSON.stringify(spec));
    window.location.assign("/player?spec=session");
  }

  async function openControllerExample(preview: boolean) {
    setLoading(preview ? "preview" : "controller");
    setError("");
    try {
      const response = await fetch(
        preview
          ? "/api/animations/examples/controller/preview"
          : "/api/animations/from-example",
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
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not open the Kubernetes Controller animation.",
      );
      setLoading(null);
    }
  }

  async function openLatestControllerAnimation() {
    setLoading("latest");
    setError("");
    try {
      const response = await fetch("/api/animations/examples/controller/latest", {
        cache: "no-store",
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? `Request failed (${response.status})`);
      }
      openPlayer((await response.json()) as RenderSpec);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not open the latest generated result.",
      );
      setLoading(null);
    }
  }

  return (
    <main>
      <header>
        <p className="eyebrow">把世界画出来 · Source to animation</p>
        <h1>Knowledge Movie Studio</h1>
        <p>Search a question, read a public URL, or upload a document, then turn it into an interactive animation.</p>
      </header>

      <section className="exampleCard" aria-labelledby="controller-example-title">
        <div>
          <p className="eyebrow">固定技术文档 · controller.md</p>
          <h2 id="controller-example-title">Kubernetes Controller 控制循环</h2>
          <p>
            观察期望状态与当前状态，比较差异，通过 API Server 执行动作，再把结果反馈到下一轮协调。
          </p>
        </div>
        <div className="exampleActions">
          <button
            type="button"
            disabled={loading !== null}
            onClick={() => openControllerExample(false)}
          >
            {loading === "controller" ? "生成中…" : "生成 Controller 动画"}
          </button>
          <button
            className="secondaryButton"
            type="button"
            disabled={loading !== null}
            onClick={() => openControllerExample(true)}
          >
            {loading === "preview" ? "载入中…" : "即时预览"}
          </button>
          <button
            className="secondaryButton"
            type="button"
            disabled={loading !== null}
            onClick={openLatestControllerAnimation}
          >
            {loading === "latest" ? "载入中…" : "查看最近生成结果"}
          </button>
        </div>
      </section>

      <form onSubmit={parseDocument}>
        <div className="modeSwitch" aria-label="Source type">
          <button
            aria-pressed={mode === "url"}
            className={mode === "url" ? "active" : ""}
            onClick={() => selectMode("url")}
            type="button"
          >
            URL
          </button>
          <button
            aria-pressed={mode === "query"}
            className={mode === "query" ? "active" : ""}
            onClick={() => selectMode("query")}
            type="button"
          >
            问题 / Web Search
          </button>
          <button
            aria-pressed={mode === "file"}
            className={mode === "file" ? "active" : ""}
            onClick={() => selectMode("file")}
            type="button"
          >
            文件
          </button>
        </div>
        <label htmlFor="source-input">
          {mode === "url"
            ? "Documentation URL"
            : mode === "query"
              ? "Question to research"
              : "Document file (.md, .txt, .pdf, .docx, .pptx)"}
        </label>
        <div className="formRow">
          {mode === "url" ? (
            <input
              id="source-input"
              type="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://docs.example.com/quickstart"
              required
            />
          ) : mode === "query" ? (
            <textarea
              id="source-input"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Ask a technical question to research"
              required
              rows={3}
            />
          ) : (
            <input
              accept=".md,.markdown,.txt,.pdf,.docx,.pptx"
              id="source-input"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              required
              type="file"
            />
          )}
          <div className="formActions">
            <button type="submit" disabled={loading !== null}>
              {loading === "document" ? "Resolving…" : "Inspect DocumentIR"}
            </button>
            <button
              className="generateButton"
              type="button"
              disabled={loading !== null || !hasInput}
              onClick={generateAnimation}
            >
              {loading === "animation" ? "Generating…" : "生成动画"}
            </button>
          </div>
        </div>
      </form>

      {error && <p className="error" role="alert">{error}</p>}

      {document && (
        <section className="result" aria-live="polite">
          <div className="resultHeader">
            <p>Document title</p>
            <h2>{document.title}</h2>
            <code>{document.document_id}</code>
          </div>
          <div className="browser">
            <nav aria-label="Document sections">
              <h3>Sections</h3>
              {document.sections.map((section) => (
                <button
                  className={section.id === activeSectionId ? "active" : ""}
                  key={section.id}
                  onClick={() => setActiveSectionId(section.id)}
                  type="button"
                >
                  {section.title}
                </button>
              ))}
            </nav>
            <article>
              {activeSection ? (
                <>
                  <h3>{activeSection.title}</h3>
                  {activeSection.blocks.map((block) => {
                    if (block.type === "code") {
                      return <pre key={block.id}><code>{block.text}</code></pre>;
                    }
                    if (block.type === "list") {
                      return <ul key={block.id}>{block.text.split("\n").map((item) => <li key={item}>{item}</li>)}</ul>;
                    }
                    if (block.type === "image" && block.source_ref) {
                      return <figure key={block.id}><img src={block.source_ref} alt={block.text} /></figure>;
                    }
                    return <p key={block.id}>{block.text}</p>;
                  })}
                </>
              ) : (
                <p>This document has no extractable sections.</p>
              )}
            </article>
          </div>
        </section>
      )}
    </main>
  );
}

const modeCopy: Record<InputMode, { index: string; label: string; hint: string }> = {
  url: { index: "01", label: "URL", hint: "Public documentation" },
  query: { index: "02", label: "ASK", hint: "Web research query" },
  file: { index: "03", label: "FILE", hint: "MD, TXT, PDF, DOCX, PPTX" },
};

function Icon({ name }: { name: "spark" | "arrow" | "grid" | "pulse" }) {
  const paths = {
    spark: <><path d="M12 2l1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8L12 2Z" /><path d="M5 17l.7 2.3L8 20l-2.3.7L5 23l-.7-2.3L2 20l2.3-.7L5 17Z" /></>,
    arrow: <><path d="M5 12h13" /><path d="m14 7 5 5-5 5" /></>,
    grid: <><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /></>,
    pulse: <path d="M3 12h4l2-6 4 12 2-6h6" />,
  };
  return <svg aria-hidden="true" className="ui-icon" viewBox="0 0 24 24">{paths[name]}</svg>;
}

export default function Home() {
  const workflow = useSourceWorkflow();
  const graph = useMemo(() => buildKnowledgeGraph(workflow.document), [workflow.document]);
  const [selectedNode, setSelectedNode] = useState<KnowledgeGraphNode | null>(graph.nodes[0] ?? null);
  const [inspectorOpen, setInspectorOpen] = useState(false);

  useEffect(() => setSelectedNode(graph.nodes[0] ?? null), [graph]);

  function selectNode(node: KnowledgeGraphNode) {
    setSelectedNode(node);
    if (node.sectionId) workflow.setActiveSectionId(node.sectionId);
  }

  const blockCount = workflow.document?.sections.reduce((sum, section) => sum + section.blocks.length, 0) ?? 0;
  const busy = workflow.loading !== null;
  const phase = busy ? "PROCESSING" : workflow.document ? "MAPPED" : "STANDBY";

  return (
    <main className="studio-shell">
      <div className="ambient-grid" aria-hidden="true" />
      <header className="studio-topbar">
        <a className="brand" href="#studio" aria-label="Animate Agent studio home">
          <span className="brand-mark"><span /></span>
          <span className="brand-wordmark">ANIMATE<span>/</span>AGENT</span>
        </a>
        <div className="pipeline-strip" aria-label={`Pipeline status: ${phase}`}>
          <span className={`status-dot ${busy ? "is-busy" : ""}`} />
          <span>PIPELINE</span><strong>{phase}</strong><span className="pipeline-separator" />
          <span className="pipeline-clock">{workflow.document ? `${graph.nodes.length} NODES` : "READY 00:00"}</span>
        </div>
        <div className="topbar-actions">
          <span className="model-badge">IR / RENDER 01</span>
          <button className="icon-button inspector-toggle" onClick={() => setInspectorOpen(true)} type="button" aria-label="Open inspector"><Icon name="grid" /></button>
          <button className="top-generate" disabled={busy || !workflow.hasInput} onClick={workflow.generateAnimation} type="button">
            <Icon name="spark" />{workflow.loading === "animation" ? "GENERATING" : "GENERATE MOVIE"}
          </button>
        </div>
      </header>

      <div className="studio-layout" id="studio">
        <aside className="source-dock glass-panel" aria-label="Source controls">
          <div className="panel-heading">
            <div><span className="panel-index">/ 01</span><h1>SOURCE<br /><em>INPUT</em></h1></div>
            <span className="vertical-label">INGEST</span>
          </div>
          <form className="source-form" onSubmit={workflow.parseDocument}>
            <div className="mode-tabs" role="tablist" aria-label="Source type">
              {(Object.keys(modeCopy) as InputMode[]).map((mode) => (
                <button aria-selected={workflow.mode === mode} className={workflow.mode === mode ? "is-active" : ""} key={mode} onClick={() => workflow.selectMode(mode)} role="tab" type="button">
                  <span>{modeCopy[mode].index}</span>{modeCopy[mode].label}
                </button>
              ))}
            </div>
            <label className="source-label" htmlFor="source-input"><span>{modeCopy[workflow.mode].hint}</span><span className="required-mark">ACTIVE CHANNEL</span></label>
            <div className={`input-frame input-${workflow.mode}`}>
              {workflow.mode === "url" ? (
                <textarea id="source-input" value={workflow.url} onChange={(event) => workflow.setUrl(event.target.value)} placeholder="https://docs.example.com/system" required rows={5} />
              ) : workflow.mode === "query" ? (
                <textarea id="source-input" value={workflow.query} onChange={(event) => workflow.setQuery(event.target.value)} placeholder="Ask a technical question to research…" required rows={5} />
              ) : (
                <label className="file-drop" htmlFor="source-input">
                  <input accept=".md,.markdown,.txt,.pdf,.docx,.pptx" id="source-input" onChange={(event) => workflow.setFile(event.target.files?.[0] ?? null)} required type="file" />
                  <span className="file-plus">+</span><strong>{workflow.file?.name ?? "DROP KNOWLEDGE"}</strong><small>{workflow.file ? "FILE LINKED" : "or select from device"}</small>
                </label>
              )}
              {workflow.mode !== "file" && <span className="input-cursor" aria-hidden="true" />}
            </div>
            <div className="source-actions">
              <button className="action-secondary" disabled={busy} type="submit">{workflow.loading === "document" ? "RESOLVING…" : "MAP DOCUMENT"}</button>
              <button className="action-primary" disabled={busy || !workflow.hasInput} onClick={workflow.generateAnimation} type="button"><span>{workflow.loading === "animation" ? "GENERATING" : "CREATE"}</span><Icon name="arrow" /></button>
            </div>
          </form>

          <section className="example-module" aria-labelledby="controller-example-title">
            <div className="module-kicker"><span>LIVE SPECIMEN</span><span>K8S / 001</span></div>
            <h2 id="controller-example-title">CONTROLLER<br />FEEDBACK LOOP</h2>
            <p>观察状态、比较差异、执行动作，将结果反馈至下一轮协调。</p>
            <div className="example-buttons">
              <button disabled={busy} onClick={() => workflow.openControllerExample(true)} type="button">{workflow.loading === "preview" ? "LOADING" : "INSTANT PREVIEW"}</button>
              <button disabled={busy} onClick={() => workflow.openControllerExample(false)} type="button">{workflow.loading === "controller" ? "GENERATING" : "GENERATE"}</button>
              <button aria-label="Open latest generated Controller result" className="mini-button" disabled={busy} onClick={workflow.openLatestControllerAnimation} type="button">↗</button>
            </div>
          </section>
          <div className="dock-footer"><span>LOCAL-FIRST</span><span>VALIDATED IR</span><span>NO EVAL</span></div>
        </aside>

        <section className="graph-stage glass-panel" aria-labelledby="graph-title">
          <div className="stage-heading">
            <div><span className="panel-index">/ 02 · KNOWLEDGE FIELD</span><h2 id="graph-title">{workflow.document ? workflow.document.title : "WAITING FOR SIGNAL"}</h2></div>
            <div className="stage-metrics">
              <span><strong>{workflow.document?.sections.length ?? "—"}</strong> SECTIONS</span>
              <span><strong>{blockCount || "—"}</strong> BLOCKS</span>
              <span><strong>100%</strong> LOCAL</span>
            </div>
          </div>
          <KnowledgeGraph data={graph} selectedId={selectedNode?.id ?? null} onSelect={selectNode} busy={busy} />
          <div className="stage-hud stage-hud-left" aria-hidden="true"><span>X 33.917</span><span>Y 08.402</span><span>Z 01.000</span></div>
          <div className="stage-hud stage-hud-right"><span className={busy ? "is-live" : ""}>{busy ? "AGENT RUNNING" : "INTERACTIVE"}</span><span>TAB / ← → TO NAVIGATE</span></div>
          {busy && <div className="processing-overlay" role="status" aria-live="polite"><span className="processing-ring" /><strong>{workflow.loading === "document" ? "MAPPING KNOWLEDGE" : "COMPOSING MOTION"}</strong><span>Deterministic pipeline active</span></div>}
        </section>

        <aside className={`agent-inspector glass-panel ${inspectorOpen ? "is-open" : ""}`} aria-label="Agent inspector">
          <button className="inspector-close" onClick={() => setInspectorOpen(false)} type="button" aria-label="Close inspector">×</button>
          <div className="panel-heading compact"><div><span className="panel-index">/ 03</span><h2>AGENT<br /><em>INSPECTOR</em></h2></div><Icon name="pulse" /></div>
          <section className="inspector-focus" aria-live="polite">
            <span className="focus-kind">{selectedNode?.kind ?? "system"} / ACTIVE</span>
            <h3>{selectedNode?.label ?? "NO SIGNAL"}</h3><p>{selectedNode?.summary ?? "Select a graph node to inspect its semantic payload."}</p>
            <div className="signal-bars" aria-hidden="true">{[18, 42, 28, 66, 48, 78, 32, 56, 24, 70, 38, 62].map((height, index) => <i key={index} style={{ height }} />)}</div>
          </section>
          {workflow.document ? (
            <div className="document-inspector">
              <div className="document-meta"><span>DOCUMENT ID</span><code>{workflow.document.document_id}</code></div>
              <nav className="section-list" aria-label="Document sections">
                {workflow.document.sections.map((section, index) => (
                  <button className={section.id === workflow.activeSectionId ? "is-active" : ""} key={section.id} onClick={() => workflow.setActiveSectionId(section.id)} type="button">
                    <span>{String(index + 1).padStart(2, "0")}</span><strong>{section.title}</strong><em>{section.blocks.length}</em>
                  </button>
                ))}
              </nav>
              <article className="document-content">
                <div className="content-heading"><span>EXTRACTED CONTENT</span><span>{workflow.activeSection?.blocks.length ?? 0} ITEMS</span></div>
                <h3>{workflow.activeSection?.title}</h3>
                {workflow.activeSection?.blocks.map((block) => {
                  if (block.type === "code") return <pre key={block.id}><code>{block.text}</code></pre>;
                  if (block.type === "list") return <ul key={block.id}>{block.text.split("\n").map((item, index) => <li key={`${block.id}-${index}`}>{item}</li>)}</ul>;
                  if (block.type === "image" && block.source_ref) return <figure key={block.id}><img src={block.source_ref} alt={block.text} /></figure>;
                  return <p key={block.id}>{block.text}</p>;
                })}
              </article>
            </div>
          ) : (
            <div className="empty-inspector"><span>00</span><strong>NO DOCUMENT MAPPED</strong><p>Connect a source and run Map Document to expose its semantic topology.</p></div>
          )}
        </aside>
      </div>
      {inspectorOpen && <button className="drawer-scrim" aria-label="Close inspector" onClick={() => setInspectorOpen(false)} type="button" />}
      {workflow.error && <div className="error-banner" role="alert"><strong>PIPELINE FAULT</strong><span>{workflow.error}</span></div>}
      <footer className="studio-footer"><span>ANIMATE-AGENT / INTERACTIVE KNOWLEDGE MOVIE SYSTEM</span><span>BUILD 0.1.0 · OBSIDIAN CHANNEL</span></footer>
    </main>
  );
}
