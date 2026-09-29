import { createIsomorphicFn } from "@tanstack/react-start";
import { getRequest } from "@tanstack/react-start/server";

// Thin fetch wrapper for the ORION FastAPI service (backend/api/). Sessions
// live in httpOnly cookies set by that service (design decision D7) — the
// browser never sees a Supabase access token directly, so every call here
// carries `credentials: "include"` and nothing else needs to attach auth.
const REAL_API_BASE_URL = import.meta.env["VITE_API_BASE_URL"] ?? "http://localhost:8000";

// The browser calls its OWN origin at "/be" (proxied to REAL_API_BASE_URL
// server-side — src/lib/backend-proxy.ts, src/server.ts), not the API
// directly. The frontend (Vercel) and API (Render) are different
// registrable domains, so a direct browser fetch is cross-site; Safari/
// WebKit — which is every iOS browser, Chrome included, since Apple
// requires that engine — blocks third-party cookies outright regardless of
// SameSite=None; Secure, so the session cookie from a direct cross-site
// call silently never persists there (confirmed live: login completed but
// bounced back to /login on iOS Chrome, worked everywhere Chrome runs its
// own engine). Routing through this app's own origin keeps the cookie
// first-party for every browser. SSR loaders are unaffected: they call
// REAL_API_BASE_URL directly and forward the incoming Cookie header by
// hand (`getCookieHeader` below) — there's no browser cookie jar or
// same-site policy involved in a server-to-server call.
const API_BASE_URL = createIsomorphicFn()
  .server(() => REAL_API_BASE_URL)
  .client(() => "/be");

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// Route `beforeLoad` guards run this same code during SSR (a direct URL
// load), where there is no browser cookie jar for `credentials: "include"`
// to draw on — the incoming request's Cookie header has to be forwarded by
// hand. createIsomorphicFn's compiler transform strips the .server() branch
// (and the getRequest import it alone uses) out of the client bundle, so
// this doesn't trip Start's server-only import protection the way a plain
// runtime `typeof window` guard did.
const getCookieHeader = createIsomorphicFn()
  .server(() => getRequest().headers.get("cookie") ?? undefined)
  .client(() => undefined);

async function send(path: string, init?: RequestInit): Promise<Response> {
  const cookie = getCookieHeader();
  const res = await fetch(`${API_BASE_URL()}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(cookie ? { Cookie: cookie } : {}),
      ...init?.headers,
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body?.detail ?? `Request failed (${res.status})`);
  }
  return res;
}

// Only the browser can refresh: during SSR there is no cookie jar to write
// the rotated pair back into, so a 401 there is left to the route guards.
const isBrowser = createIsomorphicFn()
  .server(() => false)
  .client(() => true);

// Supabase rotates the refresh token on every use, so two concurrent
// refreshes would spend the rotation on one of them and sign the user out.
// A dashboard fires half a dozen queries at once and they all 401 together,
// so every caller has to share one in-flight refresh.
let refreshInFlight: Promise<boolean> | null = null;

function refreshSession(): Promise<boolean> {
  refreshInFlight ??= fetch(`${API_BASE_URL()}/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
  })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshInFlight = null;
    });
  return refreshInFlight;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await send(path, init);
  } catch (err) {
    // An expired access token comes back as 401 (backend/main.py maps
    // PostgREST's PGRST301 "JWT expired" to 401 rather than lumping it in
    // with validation errors). A 401 means Supabase rejected the JWT before
    // running anything, so nothing was written and replaying the request is
    // safe. One attempt only — if the refreshed token still 401s the session
    // is genuinely over and the error propagates to the route guards.
    if (
      !(err instanceof ApiError) ||
      err.status !== 401 ||
      !isBrowser() ||
      path === "/auth/refresh"
    ) {
      throw err;
    }
    if (!(await refreshSession())) throw err;
    res = await send(path, init);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

export function apiPost<T>(
  path: string,
  body?: unknown,
  opts?: { signal?: AbortSignal },
): Promise<T> {
  const init: RequestInit = { method: "POST" };
  if (opts?.signal) init.signal = opts.signal;
  if (body !== undefined) init.body = JSON.stringify(body);
  return request<T>(path, init);
}

// Raw file body (the backend sniffs the real type from the bytes; no
// multipart dependency). Kept under ~4 MB — the /be proxy runs on Vercel,
// whose request bodies are capped at 4.5 MB.
export function apiUpload<T>(path: string, file: Blob): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: file,
    headers: { "Content-Type": file.type || "application/octet-stream" },
  });
}

export function apiDelete<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

export function apiBaseUrl(): string {
  return API_BASE_URL();
}
