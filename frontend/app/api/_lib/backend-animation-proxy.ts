import { request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";

import { NextResponse } from "next/server";

const backendApiBaseUrl = process.env.BACKEND_API_BASE_URL ?? "http://127.0.0.1:8000";
const defaultTimeoutMs = 30 * 60 * 1000;

class BackendAnimationTimeoutError extends Error {}

function configuredTimeoutMs() {
  const configured = Number(process.env.BACKEND_ANIMATION_TIMEOUT_MS ?? defaultTimeoutMs);
  return Number.isFinite(configured) && configured > 0 ? configured : defaultTimeoutMs;
}

function errorCode(error: unknown) {
  if (typeof error !== "object" || error === null || !("code" in error)) return "UNKNOWN";
  return String(error.code);
}

async function requestBackend(pathname: string, body: Buffer, contentType: string) {
  const target = new URL(pathname, backendApiBaseUrl);
  const timeoutMs = configuredTimeoutMs();
  const requestFn = target.protocol === "https:" ? httpsRequest : httpRequest;

  return new Promise<Response>((resolve, reject) => {
    const upstream = requestFn(
      target,
      {
        method: "POST",
        headers: {
          "Content-Type": contentType,
          "Content-Length": String(body.byteLength),
        },
      },
      (upstreamResponse) => {
        const chunks: Buffer[] = [];
        upstreamResponse.on("data", (chunk: Buffer) => chunks.push(chunk));
        upstreamResponse.on("end", () => {
          const contents = new Uint8Array(Buffer.concat(chunks));
          resolve(
            new Response(contents, {
              status: upstreamResponse.statusCode ?? 502,
              headers: {
                "Content-Type":
                  String(upstreamResponse.headers["content-type"] ?? "application/json"),
                "Cache-Control": "no-store",
              },
            }),
          );
        });
      },
    );

    upstream.setTimeout(timeoutMs, () => {
      upstream.destroy(
        new BackendAnimationTimeoutError(
          `Backend animation request exceeded ${timeoutMs} milliseconds.`,
        ),
      );
    });
    upstream.on("error", reject);
    upstream.end(body);
  });
}

export async function proxyAnimationPost(request: Request, pathname: string) {
  try {
    const body = Buffer.from(await request.arrayBuffer());
    const contentType = request.headers.get("content-type") ?? "application/octet-stream";
    return await requestBackend(pathname, body, contentType);
  } catch (error) {
    const code = errorCode(error);
    console.error("Animation backend proxy failed", { pathname, code });

    if (error instanceof BackendAnimationTimeoutError) {
      const minutes = Math.round(configuredTimeoutMs() / 60_000);
      return NextResponse.json(
        {
          detail:
            `Animation generation did not return within ${minutes} minutes. ` +
            "The backend may still finish and persist the result; check its stage logs, " +
            "then use 查看最近生成结果.",
        },
        { status: 504 },
      );
    }

    if (code === "ECONNREFUSED") {
      return NextResponse.json(
        {
          detail: `Could not connect to the backend API at ${backendApiBaseUrl}. Start it with "uv run uvicorn animate_agent.api:app --reload", then retry.`,
        },
        { status: 502 },
      );
    }

    return NextResponse.json(
      {
        detail:
          `The frontend proxy lost its connection to ${backendApiBaseUrl} (${code}). ` +
          "The backend may still be generating; check its logs and use 查看最近生成结果.",
      },
      { status: 502 },
    );
  }
}
