"use client";

import { KeyboardEvent, useEffect, useMemo, useRef } from "react";
import type { DocumentBlock, DocumentIR } from "../hooks/useSourceWorkflow";

export type KnowledgeGraphNode = {
  id: string;
  kind: "document" | "section" | "block" | "summary" | "pipeline";
  label: string;
  summary: string;
  sectionId?: string;
  blockType?: DocumentBlock["type"];
  depth: number;
  x: number;
  y: number;
};

export type KnowledgeGraphEdge = {
  source: string;
  target: string;
  kind: "contains" | "pipeline";
};

export type KnowledgeGraphData = {
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
  ambient: boolean;
};

const VIEW_WIDTH = 1000;
const VIEW_HEIGHT = 650;
const MAX_BLOCK_NODES = 42;

function hash(value: string) {
  let result = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 16777619);
  }
  return (result >>> 0) / 4294967295;
}

function compact(value: string, length = 54) {
  const clean = value.replace(/\s+/g, " ").trim();
  return clean.length > length ? `${clean.slice(0, length - 1)}…` : clean;
}

function settle(nodes: KnowledgeGraphNode[], edges: KnowledgeGraphEdge[]) {
  const next = nodes.map((node) => ({ ...node }));
  const byId = new Map(next.map((node) => [node.id, node]));
  for (let iteration = 0; iteration < 90; iteration += 1) {
    const force = new Map(next.map((node) => [node.id, { x: 0, y: 0 }]));
    for (let left = 0; left < next.length; left += 1) {
      for (let right = left + 1; right < next.length; right += 1) {
        const a = next[left];
        const b = next[right];
        const dx = a.x - b.x || 0.01;
        const dy = a.y - b.y || 0.01;
        const distanceSquared = Math.max(900, dx * dx + dy * dy);
        const strength = 19000 / distanceSquared;
        const distance = Math.sqrt(distanceSquared);
        force.get(a.id)!.x += (dx / distance) * strength;
        force.get(a.id)!.y += (dy / distance) * strength;
        force.get(b.id)!.x -= (dx / distance) * strength;
        force.get(b.id)!.y -= (dy / distance) * strength;
      }
    }
    for (const edge of edges) {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      if (!source || !target) continue;
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const distance = Math.max(1, Math.sqrt(dx * dx + dy * dy));
      const ideal = target.depth === 1 ? 210 : 112;
      const spring = (distance - ideal) * 0.012;
      force.get(source.id)!.x += (dx / distance) * spring;
      force.get(source.id)!.y += (dy / distance) * spring;
      force.get(target.id)!.x -= (dx / distance) * spring;
      force.get(target.id)!.y -= (dy / distance) * spring;
    }
    for (const node of next) {
      if (node.kind === "document") {
        node.x = VIEW_WIDTH / 2;
        node.y = VIEW_HEIGHT / 2;
        continue;
      }
      const motion = force.get(node.id)!;
      node.x = Math.max(70, Math.min(VIEW_WIDTH - 70, node.x + motion.x + (VIEW_WIDTH / 2 - node.x) * 0.0015));
      node.y = Math.max(62, Math.min(VIEW_HEIGHT - 62, node.y + motion.y + (VIEW_HEIGHT / 2 - node.y) * 0.0015));
    }
  }
  return next;
}

export function buildKnowledgeGraph(document: DocumentIR | null): KnowledgeGraphData {
  if (!document) {
    const labels = ["SOURCE", "PARSE", "PLAN", "RENDER"];
    return {
      ambient: true,
      nodes: labels.map((label, index) => ({
        id: `pipeline-${label.toLowerCase()}`,
        kind: "pipeline",
        label,
        summary: index === 0 ? "Awaiting a URL, question, or file" : "Pipeline standby",
        depth: index,
        x: 170 + index * 220,
        y: 325 + (index % 2 === 0 ? -34 : 34),
      })),
      edges: labels.slice(1).map((_, index) => ({
        source: `pipeline-${labels[index].toLowerCase()}`,
        target: `pipeline-${labels[index + 1].toLowerCase()}`,
        kind: "pipeline",
      })),
    };
  }

  const nodes: KnowledgeGraphNode[] = [{
    id: `document-${document.document_id}`,
    kind: "document",
    label: compact(document.title, 34),
    summary: `${document.sections.length} sections · ${document.sections.reduce((sum, section) => sum + section.blocks.length, 0)} blocks`,
    depth: 0,
    x: VIEW_WIDTH / 2,
    y: VIEW_HEIGHT / 2,
  }];
  const edges: KnowledgeGraphEdge[] = [];
  let blockBudget = MAX_BLOCK_NODES;
  document.sections.forEach((section, sectionIndex) => {
    const angle = (sectionIndex / Math.max(1, document.sections.length)) * Math.PI * 2 - Math.PI / 2;
    const sectionId = `section-${section.id}`;
    nodes.push({
      id: sectionId,
      kind: "section",
      label: compact(section.title, 28),
      summary: `${section.blocks.length} content blocks`,
      sectionId: section.id,
      depth: 1,
      x: VIEW_WIDTH / 2 + Math.cos(angle) * 230,
      y: VIEW_HEIGHT / 2 + Math.sin(angle) * 210,
    });
    edges.push({ source: nodes[0].id, target: sectionId, kind: "contains" });

    const visibleBlocks = section.blocks.slice(0, Math.max(0, blockBudget));
    blockBudget -= visibleBlocks.length;
    visibleBlocks.forEach((block, blockIndex) => {
      const spread = angle + (blockIndex - (visibleBlocks.length - 1) / 2) * 0.23;
      const blockId = `block-${block.id}`;
      nodes.push({
        id: blockId,
        kind: "block",
        label: block.type === "code" ? compact(block.language || "CODE", 18) : compact(block.text, 24),
        summary: compact(block.text, 140),
        sectionId: section.id,
        blockType: block.type,
        depth: 2,
        x: VIEW_WIDTH / 2 + Math.cos(spread) * (345 + hash(block.id) * 75),
        y: VIEW_HEIGHT / 2 + Math.sin(spread) * (290 + hash(`${block.id}-y`) * 58),
      });
      edges.push({ source: sectionId, target: blockId, kind: "contains" });
    });

    const hidden = section.blocks.length - visibleBlocks.length;
    if (hidden > 0) {
      const summaryId = `summary-${section.id}`;
      nodes.push({
        id: summaryId,
        kind: "summary",
        label: `+${hidden} MORE`,
        summary: `${hidden} additional blocks are grouped for performance`,
        sectionId: section.id,
        depth: 2,
        x: VIEW_WIDTH / 2 + Math.cos(angle + 0.32) * 390,
        y: VIEW_HEIGHT / 2 + Math.sin(angle + 0.32) * 320,
      });
      edges.push({ source: sectionId, target: summaryId, kind: "contains" });
    }
  });

  return { nodes: settle(nodes, edges), edges, ambient: false };
}

function edgePath(source: KnowledgeGraphNode, target: KnowledgeGraphNode) {
  const mx = (source.x + target.x) / 2;
  const my = (source.y + target.y) / 2;
  const bend = source.depth === target.depth ? 42 : 26;
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  const distance = Math.max(1, Math.sqrt(dx * dx + dy * dy));
  const cx = mx - (dy / distance) * bend;
  const cy = my + (dx / distance) * bend;
  return { d: `M ${source.x} ${source.y} Q ${cx} ${cy} ${target.x} ${target.y}`, cx, cy };
}

function pointOnCurve(source: KnowledgeGraphNode, target: KnowledgeGraphNode, cx: number, cy: number, t: number) {
  const inverse = 1 - t;
  return {
    x: inverse * inverse * source.x + 2 * inverse * t * cx + t * t * target.x,
    y: inverse * inverse * source.y + 2 * inverse * t * cy + t * t * target.y,
  };
}

type KnowledgeGraphProps = {
  data: KnowledgeGraphData;
  selectedId: string | null;
  onSelect: (node: KnowledgeGraphNode) => void;
  busy: boolean;
};

export function KnowledgeGraph({ data, selectedId, onSelect, busy }: KnowledgeGraphProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const byId = useMemo(() => new Map(data.nodes.map((node) => [node.id, node])), [data.nodes]);
  const curves = useMemo(() => data.edges.flatMap((edge) => {
    const source = byId.get(edge.source);
    const target = byId.get(edge.target);
    return source && target ? [{ ...edge, sourceNode: source, targetNode: target, ...edgePath(source, target) }] : [];
  }), [byId, data.edges]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let animationFrame = 0;
    let visible = !document.hidden;

    const resize = () => {
      const rect = wrap.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      canvas.height = Math.max(1, Math.floor(rect.height * dpr));
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
      context.setTransform((rect.width / VIEW_WIDTH) * dpr, 0, 0, (rect.height / VIEW_HEIGHT) * dpr, 0, 0);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(wrap);
    resize();

    const render = (time: number) => {
      const rect = wrap.getBoundingClientRect();
      context.clearRect(0, 0, VIEW_WIDTH, VIEW_HEIGHT);
      if (!reduceMotion && visible && rect.width > 0) {
        curves.slice(0, 30).forEach((curve, index) => {
          const t = ((time * 0.00009 * (busy ? 2.1 : 1) + index / Math.max(1, curves.length)) % 1);
          const point = pointOnCurve(curve.sourceNode, curve.targetNode, curve.cx, curve.cy, t);
          context.save();
          context.shadowBlur = busy ? 24 : 15;
          context.shadowColor = index % 3 === 0 ? "#CCFF00" : "#00EAF2";
          context.fillStyle = index % 3 === 0 ? "rgba(204,255,0,.9)" : "rgba(0,234,242,.8)";
          context.beginPath();
          context.arc(point.x, point.y, busy ? 3.2 : 2.2, 0, Math.PI * 2);
          context.fill();
          context.restore();
        });
      }
      animationFrame = requestAnimationFrame(render);
    };
    const visibility = () => { visible = !document.hidden; };
    document.addEventListener("visibilitychange", visibility);
    animationFrame = requestAnimationFrame(render);
    return () => {
      cancelAnimationFrame(animationFrame);
      observer.disconnect();
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [busy, curves]);

  function handleKey(event: KeyboardEvent<SVGGElement>, index: number) {
    if (["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key)) {
      event.preventDefault();
      const direction = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1;
      const nextIndex = (index + direction + data.nodes.length) % data.nodes.length;
      onSelect(data.nodes[nextIndex]);
      const elements = wrapRef.current?.querySelectorAll<SVGGElement>("[data-graph-node]");
      elements?.[nextIndex]?.focus();
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(data.nodes[index]);
    }
  }

  return (
    <div className="graph-viewport" ref={wrapRef}>
      <canvas aria-hidden="true" className="graph-particles" ref={canvasRef} />
      <svg className="knowledge-graph" viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`} role="group" aria-label={data.ambient ? "Animate Agent processing pipeline" : "Interactive document knowledge graph"}>
        <defs>
          <filter id="nodeGlow" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="9" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <linearGradient id="edgeGradient" x1="0" x2="1">
            <stop offset="0" stopColor="#A56BFF" />
            <stop offset="0.55" stopColor="#00EAF2" />
            <stop offset="1" stopColor="#CCFF00" />
          </linearGradient>
        </defs>
        <g className="graph-edges" aria-hidden="true">
          {curves.map((curve) => <path className={busy ? "is-busy" : ""} d={curve.d} key={`${curve.source}-${curve.target}`} />)}
        </g>
        <g className="graph-nodes">
          {data.nodes.map((node, index) => {
            const selected = node.id === selectedId;
            const radius = node.kind === "document" ? 45 : node.kind === "section" ? 28 : node.kind === "pipeline" ? 34 : 17;
            return (
              <g
                aria-label={`${node.kind}: ${node.label}. ${node.summary}`}
                aria-pressed={selected}
                className={`graph-node node-${node.kind} ${node.blockType ? `block-${node.blockType}` : ""} ${selected ? "is-selected" : ""}`}
                data-graph-node
                key={node.id}
                onClick={() => onSelect(node)}
                onKeyDown={(event) => handleKey(event, index)}
                role="button"
                tabIndex={0}
                transform={`translate(${node.x} ${node.y})`}
              >
                <circle className="node-halo" r={radius + 12} />
                <circle className="node-core" filter={selected ? "url(#nodeGlow)" : undefined} r={radius} />
                {node.kind === "document" && <circle className="node-orbit" r={radius + 20} />}
                <text className="node-label" textAnchor="middle" y={radius + 25}>{node.label}</text>
                {node.kind === "pipeline" && <text className="node-index" textAnchor="middle" y="5">0{index + 1}</text>}
              </g>
            );
          })}
        </g>
      </svg>
      <div className="graph-scanline" aria-hidden="true" />
    </div>
  );
}
