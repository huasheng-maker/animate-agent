import { NextResponse } from "next/server";

const backendApiBaseUrl = process.env.BACKEND_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function GET(
  _request: Request,
  context: { params: Promise<{ exampleId: string }> },
) {
  const { exampleId } = await context.params;
  try {
    const response = await fetch(
      `${backendApiBaseUrl}/api/animations/examples/${encodeURIComponent(exampleId)}/latest`,
      { cache: "no-store" },
    );

    return new Response(await response.text(), {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      {
        detail: `Could not connect to the backend API at ${backendApiBaseUrl}.`,
      },
      { status: 502 },
    );
  }
}
