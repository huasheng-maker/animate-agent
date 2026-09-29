/** Trusted JSXGraph factories. No model-authored markup or executable expressions. */
function group(elements) {
  return { setAttribute(attributes) { for (const e of elements) e.setAttribute(attributes); } };
}
export function Ball({board, data, view, options}) {
  const center = [() => data()[0], () => data()[1]];
  const radius = view.radius ?? .15;
  const elements = [];
  if (view.glow) for (const [scale, opacity] of [[2.4, .06], [1.8, .10], [1.35, .16]]) {
    elements.push(board.create("circle", [center, radius * scale],
      {...options, strokeOpacity: 0, fillOpacity: opacity}));
  }
  elements.push(board.create("circle", [center, radius], {...options, fillOpacity: .9}));
  return group(elements);
}
export const Particle = Ball;
export function VectorArrow({board, data, origin, options}) {
  return board.create("arrow", [
    [() => origin()[0], () => origin()[1]],
    [() => origin()[0] + data()[0], () => origin()[1] + data()[1]],
  ], options);
}
export function Vehicle({board, data, view, options}) {
  const size = (view.radius ?? .15) * 3;
  const x = () => data()[0], y = () => data()[1];
  // Body and cabin form one closed outline. Two wheels are independent circles.
  const outline = [[-1,-.25],[-1,.3],[-.5,.3],[-.25,.7],[.45,.7],
    [.7,.3],[1,.3],[1,-.25]];
  const body = board.create("polygon", outline.map(([dx,dy]) => [
    () => x() + dx * size, () => y() + dy * size,
  ]), {...options, fillOpacity: .6, hasInnerPoints: false,
    vertices: {visible: false, fixed: true, withLabel: false},
    borders: {...options}});
  const wheels = [-.6,.6].map(dx => board.create("circle", [
    [() => x() + dx * size, () => y() - .3 * size], .22 * size,
  ], {...options, fillColor: "#091923", fillOpacity: 1}));
  return group([body, ...(body.borders ?? []), ...wheels]);
}
export const Cart = Vehicle;
export const ElementRegistry = Object.freeze({
  ball: Ball, particle: Particle, vector_arrow: VectorArrow, vehicle: Vehicle, cart: Cart,
  point: ({board, data, options}) => board.create("point", [() => data()[0], () => data()[1]], options),
  vector: VectorArrow,
  circle: ({board, data, origin, options}) => board.create("circle", [
    [() => origin()[0], () => origin()[1]], () => Math.max(0, data()),
  ], {...options, fillOpacity: 0, strokeOpacity: .5}),
  curve: ({board, options}) => board.create("curve", [[], []], {...options, strokeOpacity: .65}),
  trail: ({board, options}) => board.create("curve", [[], []], {...options, strokeOpacity: .65}),
});
export function createElement(context) {
  const factory = Object.hasOwn(ElementRegistry, context.view.kind)
    ? ElementRegistry[context.view.kind] : null;
  if (!factory) throw new Error(`Unsupported element: ${context.view.kind}`);
  return factory(context);
}
