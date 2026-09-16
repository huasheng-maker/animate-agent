import { NextResponse } from "next/server";

const backendApiBaseUrl = process.env.BACKEND_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function POST(request: Request) {
  try {
    const response = await fetch(`${backendApiBaseUrl}/api/documents/from-query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await request.text(),
      cache: "no-store",
    });

    return new Response(await response.text(), {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") ?? "application/json",
      },
    });
  } catch {
    return NextResponse.json(
      {
        detail: `Could not reach the backend API at ${backendApiBaseUrl}. Start it with "uv run uvicorn animate_agent.api:app --reload", then retry.`,
      },
      { status: 502 },
    );
  }
}
