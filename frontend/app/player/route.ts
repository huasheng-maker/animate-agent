export function GET(request: Request) {
  const { search } = new URL(request.url);
  return new Response(null, {
    status: 307,
    headers: { Location: `/player-runtime/index.html${search}` },
  });
}
