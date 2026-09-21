import { readFile } from "node:fs/promises";
import { join } from "node:path";

const contentTypes: Record<string, string> = {
  "index.html": "text/html; charset=utf-8",
  "player.css": "text/css; charset=utf-8",
  "player.js": "text/javascript; charset=utf-8",
  "atoms.js": "text/javascript; charset=utf-8",
  "behaviors.js": "text/javascript; charset=utf-8",
  "primitives.js": "text/javascript; charset=utf-8",
  "registry.js": "text/javascript; charset=utf-8",
  "stage.js": "text/javascript; charset=utf-8",
  "timing.js": "text/javascript; charset=utf-8",
  "animation-ir.js": "text/javascript; charset=utf-8",
  "property-registry.js": "text/javascript; charset=utf-8",
  "timeline.js": "text/javascript; charset=utf-8",
  "effects.js": "text/javascript; charset=utf-8",
  "runtime.js": "text/javascript; charset=utf-8",
  "canvas2d-renderer.js": "text/javascript; charset=utf-8",
  "gsap-easing.js": "text/javascript; charset=utf-8",
  "gsap.min.js": "text/javascript; charset=utf-8",
};

const vendorAssets: Record<string, string> = {
  "gsap.min.js": join(process.cwd(), "node_modules", "gsap", "dist", "gsap.min.js"),
};

export async function GET(
  _request: Request,
  context: { params: Promise<{ asset: string }> },
) {
  const { asset } = await context.params;
  const contentType = contentTypes[asset];
  if (!contentType) {
    return new Response("Not found", { status: 404 });
  }

  try {
    const contents = await readFile(vendorAssets[asset] ?? join(process.cwd(), "player", asset));
    return new Response(contents, {
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return new Response("Player asset not found", { status: 404 });
  }
}
