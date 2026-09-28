export type Citation = {
  id: string;
  title: string;
  locator: string;
  excerpt: string;
  url: string | null;
};

export type RenderControl = {
  id: string;
  type: "slider" | "toggle" | "button";
  label: string;
  target_property: string;
  min?: number | null;
  max?: number | null;
  default?: number | boolean | null;
  step?: number | null;
  unit?: string;
  action?: string | null;
};

export type RenderScene = {
  id: string;
  mechanism?: Record<string, any> | null;
  title?: string;
  teaching_goal?: string;
  elements: Array<Record<string, unknown> & { id: string; role?: string; props?: Record<string, unknown> }>;
  steps: Array<Record<string, unknown>>;
  controls: RenderControl[];
  params?: Record<string, unknown>;
  thresholds?: Record<string, string>;
};

export type RenderSpec = {
  spec_version: number;
  storyboard_id: string;
  title?: string;
  subject?: string;
  eyebrow?: string;
  stage: { width: number; height: number };
  scenes: RenderScene[];
  animation_ir?: unknown;
};

export type BeatEntry = {
  index: number;
  sceneIndex: number;
  beatIndex: number;
  startFrame: number;
  endFrame: number;
  durationInFrames: number;
  scene: any;
  renderScene: RenderScene;
  beat: {
    id: string;
    title: string;
    narration: string;
    sourceRefs: string[];
  };
};

export type BeatSeries = {
  entries: BeatEntry[];
  durationInFrames: number;
};
