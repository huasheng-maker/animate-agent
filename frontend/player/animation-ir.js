import { cloneValue } from "./property-registry.js";
import { DEFAULT_FPS, validateFps } from "./timing.js";

export const ANIMATION_IR_VERSION = 1;

/** Convert the public RenderSpec v1 contract into the internal runtime IR. */
export function normalizeRenderSpec(spec) {
  if (!spec || typeof spec !== "object") throw new Error("RenderSpec must be an object");
  if (spec.spec_version !== 1) {
    throw new Error(`Unsupported RenderSpec version: ${String(spec.spec_version)}`);
  }
  validateStage(spec.stage);
  if (!Array.isArray(spec.scenes) || spec.scenes.length === 0) {
    throw new Error("RenderSpec must contain at least one scene");
  }

  if (spec.animation_ir !== undefined && spec.animation_ir !== null) {
    const compiled = validateAnimationIR(cloneValue(spec.animation_ir));
    validateCompiledCompatibility(spec, compiled);
    return compiled;
  }

  const ir = {
    irVersion: ANIMATION_IR_VERSION,
    fps: DEFAULT_FPS,
    stage: cloneValue(spec.stage),
    metadata: {
      storyboardId: spec.storyboard_id ?? "",
      lessonId: spec.lesson_id ?? "",
      documentId: spec.document_id ?? "",
      learningIntent: spec.learning_intent ?? "",
      title: spec.title ?? "",
      subject: spec.subject ?? "",
      eyebrow: spec.eyebrow ?? "",
      sourceFormat: "render-spec-v1",
    },
    scenes: spec.scenes.map((scene) => normalizeLegacyScene(scene)),
  };
  return validateAnimationIR(ir);
}

function validateCompiledCompatibility(spec, ir) {
  if (ir.stage.width !== spec.stage.width || ir.stage.height !== spec.stage.height) {
    throw new Error("Compiled AnimationIR stage does not match RenderSpec");
  }
  const renderIds = spec.scenes.map((scene) => scene.id);
  const animationIds = ir.scenes.map((scene) => scene.id);
  if (renderIds.length !== animationIds.length || renderIds.some((id, index) => id !== animationIds[index])) {
    throw new Error("Compiled AnimationIR scenes do not match RenderSpec");
  }
  if (ir.metadata.storyboardId !== (spec.storyboard_id ?? "")) {
    throw new Error("Compiled AnimationIR storyboard does not match RenderSpec");
  }
}

export function validateAnimationIR(ir) {
  if (!ir || typeof ir !== "object") throw new Error("AnimationIR must be an object");
  if (ir.irVersion !== ANIMATION_IR_VERSION) {
    throw new Error(`Unsupported AnimationIR version: ${String(ir.irVersion)}`);
  }
  ir.fps ??= DEFAULT_FPS;
  validateFps(ir.fps);
  validateStage(ir.stage);
  if (!Array.isArray(ir.scenes) || ir.scenes.length === 0) {
    throw new Error("AnimationIR must contain at least one scene");
  }
  for (const scene of ir.scenes) validateScene(scene);
  return ir;
}

function normalizeLegacyScene(scene) {
  if (!scene || typeof scene !== "object" || !scene.id) {
    throw new Error("RenderSpec scene must have an id");
  }
  const elements = Array.isArray(scene.elements) ? scene.elements : [];
  const nodes = elements.map((element) => ({
    id: element.id,
    kind: element.kind,
    // Hierarchy is intentionally not inferred from legacy attachment yet.
    parentId: null,
    transform: {
      position: { x: finite(element.x, `${element.id}.x`), y: finite(element.y, `${element.id}.y`) },
      rotation: finite(element.heading ?? 0, `${element.id}.heading`),
      scale: { x: 1, y: 1 },
      opacity: 1,
      pathProgress: 0,
    },
    style: {
      tone: element.tone ?? "normal",
      highlight: false,
      glowIntensity: 0,
    },
    visual: {
      ...cloneValue(element),
      path: cloneValue(element.path ?? element.points ?? []),
      originalText: element.text ?? "",
      visibleText: element.text ?? "",
      drawProgress: 1,
      trimStart: 0,
      trimEnd: 1,
      revealProgress: 1,
      cursorVisible: false,
    },
    semantic: { progress: 0, intensity: 0, phase: "idle" },
    legacy: cloneValue(element),
  }));
  return {
    id: scene.id,
    metadata: {
      title: scene.title ?? "",
      teachingGoal: scene.teaching_goal ?? "",
      learningQuestion: scene.learning_question ?? "",
      visualPattern: scene.visual_pattern ?? null,
      claims: cloneValue(scene.claims ?? []),
      preset: scene.preset ?? "",
    },
    nodes,
    camera: { id: "main", position: { x: 0, y: 0 }, zoom: 1, rotation: 0 },
    beats: [],
    timeline: { items: [], effects: [] },
    interactions: cloneValue(scene.controls ?? []),
    legacy: cloneValue(scene),
  };
}

function validateScene(scene) {
  if (!scene || typeof scene.id !== "string" || scene.id.length === 0) {
    throw new Error("Animation scene must have an id");
  }
  if (!Array.isArray(scene.nodes)) throw new Error(`Scene ${scene.id} nodes must be an array`);
  const ids = new Set();
  for (const node of scene.nodes) {
    if (!node || typeof node.id !== "string" || node.id.length === 0) {
      throw new Error(`Scene ${scene.id} contains a node without an id`);
    }
    if (ids.has(node.id)) throw new Error(`Duplicate animation node id: ${node.id}`);
    ids.add(node.id);
    if (node.parentId !== null && node.parentId !== undefined) {
      throw new Error(`AnimationIR v1 does not yet enable parentId: ${node.id}`);
    }
  }
  if (!scene.camera || scene.camera.id !== "main") {
    throw new Error(`Scene ${scene.id} must define the main camera`);
  }
  scene.timeline ??= { items: [], effects: [] };
  scene.timeline.items ??= [];
  scene.timeline.effects ??= [];
  scene.beats ??= [];
  if (!Array.isArray(scene.beats)) throw new Error(`Scene ${scene.id} beats must be an array`);
  const beatIds = new Set();
  for (const beat of scene.beats) {
    if (!beat || typeof beat.id !== "string" || beat.id.length === 0) {
      throw new Error(`Scene ${scene.id} contains a beat without an id`);
    }
    if (beatIds.has(beat.id)) throw new Error(`Duplicate animation beat id: ${beat.id}`);
    beatIds.add(beat.id);
    beat.timeline ??= { items: [], effects: [] };
    beat.timeline.items ??= [];
    beat.timeline.effects ??= [];
  }
  scene.interactions ??= [];
}

function validateStage(stage) {
  if (!stage || typeof stage !== "object") throw new Error("Animation stage is required");
  if (!Number.isFinite(stage.width) || stage.width <= 0) throw new Error("Stage width must be positive");
  if (!Number.isFinite(stage.height) || stage.height <= 0) throw new Error("Stage height must be positive");
}

function finite(value, label) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${label} must be a finite number`);
  }
  return value;
}
