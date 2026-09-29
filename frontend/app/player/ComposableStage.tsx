"use client";

import { useId, useLayoutEffect, useMemo, useRef } from "react";
import JXG from "jsxgraph";
import { evaluateProgram, sampleVisual } from "../../player/composable/evaluate.js";

import { ElementRegistry, createElement } from "../../player/composable/ElementRegistry.js";
import { geometryBounds } from "../../player/composable/bounds.js";

const colors: Record<string, string> = {
  teal: "#66dfcf", gold: "#ffd17e", violet: "#baabff", red: "#ff858e", blue: "#7ac2ff",
};
const geometric = new Set(Object.keys(ElementRegistry));
const fmt = (v: number) => Number(v).toLocaleString("en-US", { maximumFractionDigits: 3 });
type Props = { plan: any; sceneId: string; beatIndex: number; time: number; progress: number;
  width: number; height: number; overrides: Record<string, number | boolean> };

/** JSXGraph owns geometry; Remotion alone owns time. All labels are React text. */
export function ComposableStage(props: Props) {
  const { plan, sceneId, beatIndex, time, progress, overrides, width, height } = props;
  const phase = plan.phases[beatIndex];
  const result = useMemo(() => {
    const context = { sceneId, phase: beatIndex, time, progress, overrides };
    try {
      const values = evaluateProgram(plan, context);
      const paths: Record<string, number[][]> = {};
      for (const view of plan.visuals) if (["curve", "trail"].includes(view.kind))
        paths[view.id] = sampleVisual(plan, view, context);
      return { values, paths, error: "" };
    } catch (e) {
      return { values: {}, paths: {}, error: e instanceof Error ? e.message : "计算失败" };
    }
  }, [plan, sceneId, beatIndex, time, progress, overrides]);
  const shapes = plan.visuals.filter((view: any) => geometric.has(view.kind));
  const panels = plan.visuals.filter((view: any) => !geometric.has(view.kind) && phase.visible.includes(view.id));
  // Reserve a fixed narration strip plus the native player's controls.
  const stageHeight = height - 236;
  const graphWidth = shapes.length ? (panels.length ? width * .56 : width - 48) : 0;
  if (result.error) return <div role="alert" style={{ padding: 40, color: colors.red }}>
    当前参数超出计算域：{result.error}。请调整参数或重新生成。</div>;
  return <div data-composition="true" style={{ position: "absolute", inset: 0,
    background: "#091923", color: "#eef4f7", padding: 24, fontFamily: "system-ui, sans-serif" }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: 20, marginBottom: 12 }}>
      <strong style={{ fontSize: 19 }}>{plan.goal}</strong>
      <span style={{ color: "#a9baca", fontSize: 13 }}>{plan.example_label}</span>
    </div>
    <div style={{ display: "flex", gap: 20, height: stageHeight }}>
      {shapes.length > 0 && <div style={{ width: graphWidth, flexShrink: 0 }}>
        <GeometryBoard plan={plan} result={result} phase={phase} width={graphWidth} height={stageHeight - 38} />
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", fontSize: 14, paddingTop: 8 }}>
          {shapes.filter((v: any) => phase.visible.includes(v.id)).map((v: any) =>
            <span key={v.id} style={{ color: colors[v.color] }}>{v.label}</span>)}
        </div>
      </div>}
      {panels.length > 0 && <div style={{ flex: 1, display: "grid", minWidth: 0, gap: 10,
        gridTemplateColumns: !shapes.length && panels.length > 1 ? "repeat(2,minmax(0,1fr))" : "1fr",
        alignContent: "start", overflow: "auto" }}>
        {panels.map((view: any) => <DataPanel key={view.id} view={view} value={result.values[view.data]}
          activeIndex={view.active_index ? Math.floor(result.values[view.active_index]) : -1}
          revealCount={view.reveal_count ? Math.max(0, Math.floor(result.values[view.reveal_count])) : Infinity}
          focused={phase.focus.includes(view.id)} />)}
      </div>}
    </div>
  </div>;
}

function GeometryBoard({ plan, result, phase, width, height }: any) {
  const id = `geometry-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const current = useRef({ result, phase });
  current.current = { result, phase };
  const drawing = useRef<any>(null);
  useLayoutEffect(() => {
    const board = JXG.JSXGraph.initBoard(id, {
      boundingbox: [plan.x_range[0], plan.y_range[1], plan.x_range[1], plan.y_range[0]],
      axis: true, keepaspectratio: true, showNavigation: false,
      pan: { enabled: false }, zoom: { enabled: false, wheel: false },
      resize: { enabled: false }, keyboard: { enabled: false },
      defaultAxes: { x: { strokeColor: "#69818f", ticks: { label: { strokeColor: "#90a5b3" } } },
        y: { strokeColor: "#69818f", ticks: { label: { strokeColor: "#90a5b3" } } } },
    } as any);
    const entries: any[] = [];
    for (const view of plan.visuals.filter((v: any) => geometric.has(v.kind))) {
      const data = () => current.current.result.values[view.data];
      const origin = () => view.origin ? current.current.result.values[view.origin] : [0, 0];
      const options: any = { name: "", withLabel: false, fixed: true, highlight: false,
        strokeColor: colors[view.color], fillColor: colors[view.color],
        strokeWidth: 3, size: 5, showInfobox: false, transitionDuration: 0 };
      const element = createElement({ board, view, data, origin, options });
      entries.push({ view, element });
    }
    drawing.current = { board, entries };
    return () => { drawing.current = null; JXG.JSXGraph.freeBoard(board); };
  }, [id, plan, width, height]);
  useLayoutEffect(() => {
    if (!drawing.current) return;
    const { board, entries } = drawing.current;
    board.suspendUpdate();
    board.setBoundingBox(geometryBounds(plan, result.values, result.paths, phase.visible), true);
    for (const { view, element } of entries) {
      const points = result.paths[view.id];
      if (points) { element.dataX = points.map((p: number[]) => p[0]); element.dataY = points.map((p: number[]) => p[1]); }
      element.setAttribute({ visible: phase.visible.includes(view.id),
        strokeWidth: phase.focus.includes(view.id) ? 4 : 2 });
    }
    board.unsuspendUpdate();
  }, [result, phase, plan]);
  return <div id={id} aria-label="计算驱动的几何画面" style={{ width, height, overflow: "hidden" }} />;
}

function DataPanel({ view, value, focused, activeIndex, revealCount }: any) {
  const color = colors[view.color];
  const rows: number[][] = Array.isArray(value?.[0]) ? value : [Array.isArray(value) ? value : [value]];
  return <section data-visual={view.id} style={{ padding: 12, borderRadius: 8, background: "#122b3a",
    border: `1px solid ${focused ? color : "#254352"}`, minWidth: 0 }}>
    <div style={{ fontSize: 17, marginBottom: 8, color }}>{view.label}</div>
    {view.kind === "matrix" ? <table style={{ borderCollapse: "separate", borderSpacing: 3, width: "100%" }}>
      <tbody>{rows.map((row, i) => <tr key={i} data-active={i === activeIndex}>
        {view.labels[i] && <th style={{fontSize:12,color,padding:4,textAlign:"left"}}>{view.labels[i]}</th>}
        {row.map((n, j) => <td key={j} style={{
        padding: "6px 4px", textAlign: "center", fontSize: Math.max(11, 18 - row.length),
        background: n < 0 ? "#574b78" : "#215f68", fontVariantNumeric: "tabular-nums",
        outline: i === activeIndex ? `2px solid ${color}` : "none", opacity: activeIndex >= 0 && i !== activeIndex ? .45 : 1,
      }}>{fmt(n)}</td>)}</tr>)}</tbody></table>
      : view.kind === "tokens" ? <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {value.slice(0, revealCount).map((n: number, i: number) => <span key={i} data-token-id={n}
          style={{ padding: 10, borderRadius: 5, border:`1px solid ${i === activeIndex ? color : "#35556b"}`,
          background: "#23465b", fontSize: 19 }}>{view.labels[n] ?? `ID ${n}`}<small style={{display:"block",fontSize:10,opacity:.65}}>ID {n}</small></span>)}
      </div> : view.kind === "bars" ? <div>{value.map((n: number, i: number) => <div key={i}
        style={{ display: "grid", gridTemplateColumns: "72px 1fr 65px", alignItems: "center", gap: 6, margin: "5px 0", fontSize: 13 }}>
        <span style={{color: i === activeIndex ? color : undefined}}>{view.labels[i] ?? i}</span><div style={{ background: "#1c3d50", height: 12 }}>
          <div style={{ height: 12, background: color, width: `${100 * Math.abs(n) / Math.max(1e-9, ...value.map(Math.abs))}%` }} />
        </div><span>{fmt(n)}</span></div>)}</div>
        : <output style={{ fontSize: 22, color, fontVariantNumeric: "tabular-nums" }}>
          {rows.map((row) => row.map(fmt).join(", ")).join("; ")}</output>}
  </section>;
}
