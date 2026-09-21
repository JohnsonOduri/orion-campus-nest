import { createIsomorphicFn } from "@tanstack/react-start";
import { getRequest } from "@tanstack/react-start/server";

// Thin fetch wrapper for the ORION FastAPI service (backend/api/). Sessions
// live in httpOnly cookies set by that service (design decision D7) — the
// browser never sees a Supabase access token directly, so every call here
// carries `credentials: "include"` and nothing else needs to attach auth.
const API_BASE_URL = import.meta.env["VITE_API_BASE_URL"] ?? "http://localhost:8000";

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const cookie = getCookieHeader();
  const res = await fetch(`${API_BASE_URL}${path}`, {
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
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method: "POST" };
  if (body !== undefined) init.body = JSON.stringify(body);
  return request<T>(path, init);
}

export function apiBaseUrl(): string {
  return API_BASE_URL;
}
