// Keep declared coordinates as the minimum view, expanding for visible geometry.
// Radial bounds avoid camera oscillation when a vector rotates around the origin.
export function geometryBounds(plan, values, paths, visible) {
  const cx = (plan.x_range[0] + plan.x_range[1]) / 2;
  const cy = (plan.y_range[0] + plan.y_range[1]) / 2;
  let radius = 0;
  const include = (point, padding = 0) => {
    if (Array.isArray(point) && point.length === 2)
      radius = Math.max(radius, Math.hypot(point[0] - cx, point[1] - cy) + padding);
  };
  for (const view of plan.visuals) {
    if (!visible.includes(view.id)) continue;
    const data = values[view.data];
    const origin = view.origin ? values[view.origin] : [0, 0];
    if (["vector", "vector_arrow"].includes(view.kind)) {
      include(origin);
      include([origin[0] + data[0], origin[1] + data[1]]);
    } else if (view.kind === "circle") include(origin, data);
    else if (["point", "ball", "particle", "vehicle", "cart"].includes(view.kind))
      include(data, (view.radius ?? .1) * 2);
    else if (["curve", "trail"].includes(view.kind))
      for (const point of paths[view.id] ?? []) include(point);
  }
  const x = Math.max((plan.x_range[1] - plan.x_range[0]) / 2, radius * 1.1);
  const y = Math.max((plan.y_range[1] - plan.y_range[0]) / 2, radius * 1.1);
  return [cx - x, cy + y, cx + x, cy - y];
}
