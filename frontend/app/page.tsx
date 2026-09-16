"use client";

import { FormEvent, useState } from "react";

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

type InputMode = "url" | "query";

function apiEndpoint(kind: "documents" | "animations", mode: InputMode) {
  const path = `/api/${kind}/from-${mode}`;
  return process.env.NEXT_PUBLIC_API_BASE_URL
    ? `${process.env.NEXT_PUBLIC_API_BASE_URL}${path}`
    : path;
}

export default function Home() {
  const [mode, setMode] = useState<InputMode>("url");
  const [url, setUrl] = useState(
    "https://raw.githubusercontent.com/ManimCommunity/manim/main/docs/source/tutorials/quickstart.rst",
  );
  const [query, setQuery] = useState("How does retrieval-augmented generation work?");
  const [document, setDocument] = useState<DocumentIR | null>(null);
  const [activeSectionId, setActiveSectionId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState<"document" | "animation" | null>(null);

  const activeSection = document?.sections.find((section) => section.id === activeSectionId);
  const value = mode === "url" ? url : query;
  const requestBody = mode === "url" ? { url } : { query };

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
      const response = await fetch(apiEndpoint("documents", mode), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
      });
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
      const response = await fetch(apiEndpoint("animations", mode), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(payload?.detail ?? `Request failed (${response.status})`);
      }
      const spec = (await response.json()) as RenderSpec;
      if (!spec.storyboard_id || !Array.isArray(spec.scenes) || spec.scenes.length === 0) {
        throw new Error("The backend returned an empty or invalid RenderSpec.");
      }
      window.sessionStorage.setItem("animate-agent-render-spec", JSON.stringify(spec));
      window.location.assign("/player?spec=session");
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

  return (
    <main>
      <header>
        <p className="eyebrow">把世界画出来 · Source to animation</p>
        <h1>Knowledge Movie Studio</h1>
        <p>Search a question or read a public URL, then turn its sources into an interactive animation.</p>
      </header>

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
        </div>
        <label htmlFor="source-input">
          {mode === "url" ? "Documentation URL" : "Question to research"}
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
          ) : (
            <textarea
              id="source-input"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Ask a technical question to research"
              required
              rows={3}
            />
          )}
          <div className="formActions">
            <button type="submit" disabled={loading !== null}>
              {loading === "document" ? "Resolving…" : "Inspect DocumentIR"}
            </button>
            <button
              className="generateButton"
              type="button"
              disabled={loading !== null || !value.trim()}
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
