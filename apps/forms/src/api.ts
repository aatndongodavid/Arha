/** Same origin API: the reverse proxy routes /v1 to the API, so no domain appears in the code. */
export class ApiError extends Error {
  constructor(public status: number, public code: string, public body: Record<string, any>) {
    super(code);
  }
}

export async function api<T = any>(path: string, init: RequestInit & { json?: unknown; key?: string } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", "Accept-Language": document.documentElement.lang };
  if (init.json !== undefined) headers["Content-Type"] = "application/json";
  if (init.key) headers["Idempotency-Key"] = init.key;
  const res = await fetch(`/v1/public${path}`, {
    ...init, headers, credentials: "omit", body: init.json !== undefined ? JSON.stringify(init.json) : init.body,
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body.code ?? "error", body);
  return body as T;
}
