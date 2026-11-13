/** Local persistence (master prompt section 10): drafts and the send queue live in IndexedDB. */
import { del, get, keys, set } from "idb-keyval";
import { api, ApiError } from "./api";

export interface Draft {
  id: string;
  answers: Record<string, unknown>;
  page: string | null;
  history: string[];
}

export interface Queued {
  code: string;
  key: string;
  payload: Record<string, unknown>;
}

const safe = async <T>(fn: () => Promise<T>, fallback: T): Promise<T> => {
  try {
    return await fn();
  } catch {
    return fallback; // private browsing or blocked storage: the form still works
  }
};

export const loadDraft = (versionId: string) => safe(() => get<Draft>(`draft:${versionId}`), undefined);
export const saveDraft = (versionId: string, d: Draft) => safe(() => set(`draft:${versionId}`, d), undefined);
export const clearDraft = (versionId: string) => safe(() => del(`draft:${versionId}`), undefined);
export const remember = <T>(key: string, value: T) => safe(() => set(key, value), undefined);
export const recall = <T>(key: string) => safe(() => get<T>(key), undefined);
export const forget = (key: string) => safe(() => del(key), undefined);

export const enqueue = (q: Queued) => safe(() => set(`queue:${q.payload.id}`, q), undefined);

export type SendResult = { ok: true; result: any } | { ok: false; retry: boolean; error?: ApiError };

/** Send one queued response. The server is idempotent on the submission id, so replays are safe. */
export async function send(q: Queued): Promise<SendResult> {
  try {
    const result = await api(`/forms/${q.code}/submissions`, { method: "POST", json: q.payload, key: q.key });
    await safe(() => del(`queue:${q.payload.id}`), undefined);
    return { ok: true, result };
  } catch (e) {
    if (e instanceof ApiError && e.status < 500 && e.status !== 429) {
      await safe(() => del(`queue:${q.payload.id}`), undefined);
      return { ok: false, retry: false, error: e };
    }
    return { ok: false, retry: true };
  }
}

/** Replays every queued response: on page open and when the network comes back. */
export async function flushQueue(except?: string): Promise<void> {
  for (const k of await safe(() => keys(), [])) {
    if (typeof k !== "string" || !k.startsWith("queue:") || k === `queue:${except}`) continue;
    const q = await safe(() => get<Queued>(k), undefined);
    if (q) await send(q);
  }
}
