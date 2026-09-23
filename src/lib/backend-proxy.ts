// Same-origin proxy for the FastAPI backend, mounted at /be/* (src/server.ts).
//
// Why this exists: the frontend (Vercel) and the API (Render) are on
// different registrable domains, so the session cookie is cross-site.
// SameSite=None; Secure (backend/app/core/cookies.py) makes that work in
// Chrome — desktop and Android — but Safari/WebKit blocks third-party
// cookies by default ("Prevent Cross-Site Tracking"), and Apple requires
// EVERY iOS browser (Chrome, Firefox, Edge included) to use WebKit under
// the hood, so this wasn't an iOS-Chrome-specific bug — it's the same
// restriction Safari has always had, just invisible until someone tried
// this exact flow on an iOS browser. No cookie attribute fixes that; the
// browser has to stop treating the API as a third party at all.
//
// The fix: the browser only ever talks to its own origin
// (`API_BASE_URL` in api-client.ts is "/be" on the client). This module
// forwards that request to the real API server-to-server — a plain HTTP
// call, not a browser fetch, so no CORS or cookie-jar policy applies to
// it — and relays the response back verbatim, including every Set-Cookie
// header. From the browser's point of view it made a same-origin request
// and got a same-origin cookie: first-party everywhere, including Safari.
//
// SSR route loaders are unaffected — they already call the real API
// directly (api-client.ts's `.server()` branch) and forward the incoming
// Cookie header by hand; that path was never subject to browser cookie
// policy in the first place.

export const PROXY_PREFIX = "/be/";

const HOP_BY_HOP_REQUEST_HEADERS = new Set(["host", "connection", "content-length"]);
const HOP_BY_HOP_RESPONSE_HEADERS = new Set([
  "content-encoding", // the body below is already decoded by `fetch`; forwarding this would mislabel it
  "content-length", // the actual re-encoded length may differ
  "connection",
  "transfer-encoding",
]);

function backendOrigin(): string {
  // Same value api-client.ts's server-side branch uses to reach the real
  // API — see that file for why VITE_-prefixed vars are readable here too
  // (one Vite build, both client and server bundles).
  return import.meta.env["VITE_API_BASE_URL"] ?? "http://localhost:8000";
}

function getSetCookies(headers: Headers): string[] {
  // Fetch's Headers spec-mandates Set-Cookie never gets comma-joined, but
  // only runtimes exposing getSetCookie() give a reliable way to read that
  // back out; fall back to a single value on anything older (Node >=18.14
  // and every current Vercel Node runtime has it).
  const withGetter = headers as Headers & { getSetCookie?: () => string[] };
  if (typeof withGetter.getSetCookie === "function") return withGetter.getSetCookie();
  const raw = headers.get("set-cookie");
  return raw ? [raw] : [];
}

export function isProxyRequest(url: URL): boolean {
  return url.pathname.startsWith(PROXY_PREFIX);
}

export async function proxyToBackend(request: Request): Promise<Response> {
  const url = new URL(request.url);
  // "/be/ai/ask" -> "/ai/ask" (keep the leading slash, drop only the prefix).
  const target = new URL(url.pathname.slice(PROXY_PREFIX.length - 1) + url.search, backendOrigin());

  const headers = new Headers();
  for (const [key, value] of request.headers) {
    if (!HOP_BY_HOP_REQUEST_HEADERS.has(key.toLowerCase())) headers.set(key, value);
  }

  const init: RequestInit = { method: request.method, headers, redirect: "manual" };
  if (request.method !== "GET" && request.method !== "HEAD") {
    // Buffering (rather than streaming, which would need `duplex: "half"`)
    // is fine — every request this proxy carries (JSON asks, the cookie
    // exchange) is small.
    init.body = await request.arrayBuffer();
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch (error) {
    console.error(`[backend-proxy] ${target} unreachable:`, error);
    return new Response(
      JSON.stringify({ detail: "Could not reach the ORION backend. Please try again." }),
      {
        status: 502,
        headers: { "content-type": "application/json" },
      },
    );
  }

  const responseHeaders = new Headers();
  for (const [key, value] of upstream.headers) {
    const lower = key.toLowerCase();
    if (lower === "set-cookie" || HOP_BY_HOP_RESPONSE_HEADERS.has(lower)) continue;
    responseHeaders.append(key, value);
  }
  for (const cookie of getSetCookies(upstream.headers))
    responseHeaders.append("set-cookie", cookie);

  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}
