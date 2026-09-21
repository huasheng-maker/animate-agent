/**
 * Controlled GSAP bridge.
 *
 * AnimationIR still owns the allowlist. GSAP only supplies deterministic ease
 * curves; model-authored code and arbitrary GSAP expressions never enter the
 * player. A small fallback keeps the IR inspectable in Node and produces a
 * visible error if a GSAP-only curve is requested without the vendor runtime.
 */

const EASE_NAMES = Object.freeze({
  linear: "none",
  easeIn: "power1.in",
  easeOut: "power1.out",
  easeInOut: "power1.inOut",
  expoOut: "expo.out",
  backOut: "back.out(1.7)",
  elasticOut: "elastic.out(1, 0.45)",
});

const FALLBACKS = Object.freeze({
  linear: (t) => t,
  easeIn: (t) => t * t,
  easeOut: (t) => 1 - (1 - t) * (1 - t),
  easeInOut: (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2),
});

let gsapEngine = globalThis.gsap ?? null;
const cache = new Map();

export const SUPPORTED_EASINGS = Object.freeze(Object.keys(EASE_NAMES));

export function registerGsap(engine) {
  if (!engine || typeof engine.parseEase !== "function") {
    throw new Error("GSAP runtime must provide parseEase()");
  }
  gsapEngine = engine;
  cache.clear();
}

export function resolveEase(name) {
  if (!(name in EASE_NAMES)) throw new Error(`Unknown easing: ${name}`);
  if (cache.has(name)) return cache.get(name);
  const easing = gsapEngine?.parseEase(EASE_NAMES[name]) ?? FALLBACKS[name];
  if (typeof easing !== "function") {
    throw new Error(`Easing ${name} requires the GSAP runtime`);
  }
  cache.set(name, easing);
  return easing;
}

