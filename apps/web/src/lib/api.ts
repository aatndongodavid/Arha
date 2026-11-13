/** Same origin API client. The session cookie is HttpOnly; the CSRF token travels in a header (S-02). */
import { locale } from "./i18n";

export class ApiError extends Error {
  constructor(public status: number, public code: string, public detail: string, public body: Record<string, any>) {
    super(detail || code);
  }
}

let csrf = "";
export const setCsrf = (token: string): void => { csrf = token; };

export async function api<T = any>(path: string, init: { method?: string; json?: unknown; body?: BodyInit; key?: string } = {}): Promise<T> {
  const method = init.method ?? (init.json !== undefined || init.body ? "POST" : "GET");
  const headers: Record<string, string> = { Accept: "application/json", "Accept-Language": locale() };
  if (init.json !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = csrf;
  if (init.key) headers["Idempotency-Key"] = init.key;
  const res = await fetch(`/v1${path}`, {
    method, headers, credentials: "same-origin", body: init.json !== undefined ? JSON.stringify(init.json) : init.body,
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body.code ?? "error", body.detail ?? "", body);
  return body as T;
}

export async function download(path: string, filename: string): Promise<void> {
  const res = await fetch(`/v1${path}`, { credentials: "same-origin", headers: { "Accept-Language": locale() } });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.code ?? "error", body.detail ?? "", body);
  }
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}

export const errorText = (e: unknown): string => (e instanceof ApiError && e.detail ? e.detail : String((e as Error)?.message ?? e));
