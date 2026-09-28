import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function proxy(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await context.params;
  const valid = path.length === 0 ||
    (path.length <= 2 && /^[a-f0-9-]{32,36}$/i.test(path[0]) &&
      (path.length === 1 || ["events", "result", "cancel"].includes(path[1])));
  if (!valid) return Response.json({ detail: "Unknown task route" }, { status: 404 });
  const base = process.env.BACKEND_API_BASE_URL ?? "http://127.0.0.1:8000";
  const target = new URL(`/api/animation-jobs${path.length ? `/${path.join("/")}` : ""}`, base);
  target.search = request.nextUrl.search;
  const headers = new Headers();
  for (const key of ["Content-Type", "Idempotency-Key", "Last-Event-ID"]) {
    const value = request.headers.get(key);
    if (value) headers.set(key, value);
  }
  try {
    const upstream = await fetch(target, {
      method: request.method, headers, cache: "no-store", signal: request.signal,
      ...(request.method === "POST" ? { body: await request.arrayBuffer() } : {}),
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
        "Cache-Control": "no-store, no-transform",
        "X-Accel-Buffering": "no",
      },
    });
  } catch {
    return Response.json({ detail: "暂时无法连接生成服务，任务状态将在连接恢复后更新。" }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
