import { proxyAnimationPost } from "../../_lib/backend-animation-proxy";

export async function POST(request: Request) {
  return proxyAnimationPost(request, "/api/animations/from-query");
}
