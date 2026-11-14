/** Form editor (F-EDI-01..10): block document, slash commands, drag and drop, undo and redo, autosave, live mobile preview. */
import * as Tabs from "@radix-ui/react-tabs";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { api, ApiError, errorText } from "../lib/api";
import { locale as uiLocale, type Locale, t } from "../lib/i18n";
import { atLeast, useOrg } from "../session";
import { Badge, Button, cx, Input, Modal, Notice, Select, Spinner, Textarea } from "../ui";
import { LogicPanel, SettingsPanel, VersionsPanel } from "./editor-panels";
import { statusTone } from "./forms";

export type Schema = Record<string, any>;
export type Block = Record<string, any>;

export const BLOCK_TYPES: [string, string[]][] = [
  ["text", ["short_text", "long_text", "email", "phone", "url", "number"]],
  ["choice", ["single_choice", "multi_choice", "dropdown", "yes_no", "ranking", "choice_grid"]],
  ["scale", ["rating", "linear_scale", "nps"]],
  ["date", ["date", "time", "date_range"]],
  ["file", ["file_upload", "signature"]],
  ["payment", ["payment_fixed", "payment_computed", "payment_open", "product_choice", "ticket_choice"]],
  ["structure", ["heading", "rich_text", "divider", "hidden", "computed_display", "consent"]],
];
const WITH_OPTIONS = new Set(["single_choice", "multi_choice", "dropdown", "ranking", "product_choice", "ticket_choice"]);
const PRICED = new Set(["product_choice", "ticket_choice"]);
const PAYMENT = new Set(["payment_fixed", "payment_computed", "payment_open", "product_choice", "ticket_choice"]);
const NO_LABEL = new Set(["divider", "hidden", "rich_text", "heading"]);
const SECONDS: Record<string, number> = { long_text: 40, file_upload: 30, signature: 15, choice_grid: 25, ranking: 20, heading: 2, rich_text: 8, divider: 0, hidden: 0 };

export const newId = (prefix: string, taken: Set<string>): string => {
  for (let i = 1; ; i++) if (!taken.has(`${prefix}${i}`)) return `${prefix}${i}`;
};
export const allIds = (s: Schema): Set<string> =>
  new Set([...s.pages.flatMap((p: any) => [p.id, ...p.blocks.map((b: Block) => b.id)]), ...s.variables.map((v: any) => v.id), ...s.rules.map((r: any) => r.id)]);

function makeBlock(type: string, s: Schema): Block {
  const id = newId("q", allIds(s));
  const b: Block = { id, type, label: { fr: "", en: "" }, required: false };
  if (WITH_OPTIONS.has(type)) {
    b.options = [1, 2].map((n) => ({ id: `o${n}`, label: { fr: `Option ${n}`, en: `Option ${n}` }, code: n, ...(PRICED.has(type) ? { price: 1000 } : {}) }));
  }
  if (type === "choice_grid") {
    b.rows = [{ id: "r1", label: { fr: "Ligne 1", en: "Row 1" } }];
    b.columns = [{ id: "c1", label: { fr: "Colonne 1", en: "Column 1" } }, { id: "c2", label: { fr: "Colonne 2", en: "Column 2" } }];
  }
  if (type === "payment_fixed") b.amount = 1000;
  if (type === "payment_open") b.minAmount = 500;
  if (type === "rating") b.scale = { max: 5 };
  if (type === "linear_scale") b.scale = { min: 1, max: 5 };
  if (type === "heading" || type === "rich_text") { b.content = { fr: "", en: "" }; delete b.required; }
  if (type === "consent") { b.required = true; b.label = { fr: "J'accepte que mes réponses soient traitées par l'organisateur.", en: "I agree that the organizer processes my answers." }; }
  if (type === "hidden") b.param = "source";
  if (PAYMENT.has(type)) s.settings.payments = { ...(s.settings.payments ?? {}), enabled: true };
  return b;
}

/** F-EDI-06: estimated duration and a simple readability score, recomputed at every change. */
function insights(s: Schema, loc: Locale): { seconds: number; score: number } {
  const blocks: Block[] = s.pages.flatMap((p: any) => p.blocks);
  const seconds = blocks.reduce((n, b) => n + (SECONDS[b.type] ?? 10), 0);
  const labels = blocks.map((b) => (b.label?.[loc] ?? "") as string).filter(Boolean);
  const avg = labels.length ? labels.reduce((n, l) => n + l.split(/\s+/).length, 0) / labels.length : 0;
  const longPenalty = Math.max(0, avg - 12) * 4 + Math.max(0, blocks.length - 25);
  return { seconds, score: Math.max(0, Math.min(100, Math.round(100 - longPenalty))) };
}

export function Editor() {
  const { org: orgId, form: formId } = useParams({ strict: false }) as { org: string; form: string };
  const org = useOrg(orgId).data;
  const qc = useQueryClient();
  const base = `/orgs/${orgId}/forms/${formId}`;
  const form = useQuery<any>({ queryKey: ["form", formId], queryFn: () => api(base) });
  const [schema, setSchemaState] = useState<Schema | null>(null);
  const [title, setTitle] = useState("");
  const [lang, setLang] = useState<Locale>("fr");
  const [selected, setSelected] = useState<string | null>(null);
  const [saving, setSaving] = useState<"saved" | "saving" | "error" | "conflict">("saved");
  const [publishing, setPublishing] = useState<any>(null);
  const [showPreview, setShowPreview] = useState(false);
  const revision = useRef(0);
  const undo = useRef<Schema[]>([]);
  const redo = useRef<Schema[]>([]);
  const timer = useRef<number>(undefined);
  const dirty = useRef<Schema | null>(null);
  const canEdit = atLeast(org, "editor");

  useEffect(() => {
    if (form.data && !schema) {
      setSchemaState(form.data.draft_schema);
      setTitle(form.data.title);
      revision.current = form.data.draft_revision;
      setLang(form.data.draft_schema.defaultLocale ?? "fr");
    }
  }, [form.data]);

  const flush = useCallback(async () => {
    const s = dirty.current;
    if (!s) return;
    dirty.current = null;
    setSaving("saving");
    try {
      const r = await api<any>(`${base}/draft`, { method: "PUT", json: { schema: s, revision: revision.current } });
      revision.current = r.draft_revision;
      setSaving(dirty.current ? "saving" : "saved");
      qc.setQueryData(["form", formId], r);
    } catch (e) {
      setSaving(e instanceof ApiError && e.code === "form_revision_conflict" ? "conflict" : "error");
    }
  }, [base]);

  /** Every change goes through here: history for undo, autosave within one second (F-EDI-02). */
  const setSchema = useCallback((next: Schema, record = true) => {
    setSchemaState((prev) => {
      if (record && prev) {
        undo.current = [...undo.current.slice(-99), prev];
        redo.current = [];
      }
      return next;
    });
    dirty.current = next;
    setSaving("saving");
    clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void flush(), 800);
  }, [flush]);

  const step = useCallback((from: React.MutableRefObject<Schema[]>, to: React.MutableRefObject<Schema[]>) => {
    const target = from.current.pop();
    if (!target) return;
    setSchemaState((prev) => {
      if (prev) to.current = [...to.current, prev];
      return target;
    });
    dirty.current = target;
    clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void flush(), 800);
  }, [flush]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z") return;
      const el = e.target as HTMLElement;
      if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") return; // native undo inside a field
      e.preventDefault();
      if (e.shiftKey) step(redo, undo);
      else step(undo, redo);
    };
    const onLeave = () => { if (dirty.current) void flush(); };
    addEventListener("keydown", onKey);
    addEventListener("pagehide", onLeave);
    return () => {
      removeEventListener("keydown", onKey);
      removeEventListener("pagehide", onLeave);
      onLeave();
    };
  }, [step, flush]);

  const info = useMemo(() => (schema ? insights(schema, lang) : { seconds: 0, score: 100 }), [schema, lang]);
  if (!schema || !form.data) return form.isError ? <Notice tone="error">{errorText(form.error)}</Notice> : <Spinner />;

  const patchForm = async (body: Record<string, unknown>) => qc.setQueryData(["form", formId], await api(base, { method: "PATCH", json: body }));
  const publish = async () => {
    await flush();
    try {
      const r = await api<any>(`${base}/publish`, { method: "POST" });
      setPublishing({ ok: true, ...r });
      await qc.invalidateQueries({ queryKey: ["form", formId] });
    } catch (e) {
      setPublishing({ ok: false, error: e instanceof ApiError ? e : null, message: errorText(e) });
    }
  };
  const f = form.data;
  const previewMeta = {
    title, schema, version_id: "preview", code: "_preview", status: "open", tickets: {},
    organization: { name: org?.name ?? "", verified: org?.verified ?? false, slug: org?.slug ?? "" },
    branding_required: !!org && org.plan_code === "discovery", branding_url: "#",
    payments: { currency: schema.settings?.payments?.currency ?? "XAF", fee_bearer: schema.settings?.payments?.feeBearer ?? "org" },
  };
  const formsOrigin = new URL(f.public_url).origin;

  return (
    <div className="-mx-5 -my-8 md:-mx-10">
      <div className="sticky top-0 z-20 flex flex-wrap items-center gap-3 border-b border-sand bg-cream/95 px-5 py-3 backdrop-blur md:px-10">
        <Link to="/o/$org" params={{ org: orgId }} className="text-sm text-grey underline">{t("nav.forms")}</Link>
        <input aria-label={t("editor.title")} value={title} disabled={!canEdit} maxLength={200}
          onChange={(e) => setTitle(e.target.value)} onBlur={() => title.trim() && title !== f.title && void patchForm({ title })}
          className="serif min-w-0 flex-1 rounded bg-transparent px-1 text-2xl outline-none focus:bg-white" />
        <Badge tone={statusTone(f.status)}>{t(`status.${f.status}`)}</Badge>
        <span className={cx("text-sm", saving === "error" || saving === "conflict" ? "font-medium text-red" : "text-grey")} role="status">{t(`editor.save.${saving}`)}</span>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" disabled={!undo.current.length} onClick={() => step(undo, redo)} title="Ctrl+Z">{t("editor.undo")}</Button>
          <Button variant="ghost" size="sm" disabled={!redo.current.length} onClick={() => step(redo, undo)} title="Ctrl+Shift+Z">{t("editor.redo")}</Button>
          <Button variant="secondary" size="sm" className="lg:hidden" onClick={() => setShowPreview(true)}>{t("editor.preview")}</Button>
          {canEdit ? <Button size="sm" onClick={publish}>{f.current_version ? t("editor.republish") : t("editor.publish")}</Button> : null}
        </div>
      </div>

      <div className="grid gap-8 px-5 py-6 md:px-10 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0">
          {f.status === "published" ? (
            <Notice>
              {t("editor.live")} <a className="font-medium underline" href={f.public_url} target="_blank" rel="noreferrer">{f.public_url}</a>{" "}
              <button type="button" className="underline" onClick={() => void navigator.clipboard.writeText(f.public_url)}>{t("common.copy")}</button>
              {f.has_unpublished_changes ? <span className="mt-1 block">{t("editor.unpublished")}</span> : null}
            </Notice>
          ) : null}
          <Tabs.Root defaultValue="content">
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <Tabs.List className="flex gap-1 rounded-lg bg-beige p-1" aria-label={t("editor.sections")}>
                {["content", "logic", "settings", "versions"].map((k) => (
                  <Tabs.Trigger key={k} value={k} className="rounded-md px-3 py-1.5 text-sm data-[state=active]:bg-white data-[state=active]:font-medium data-[state=active]:shadow-sm">
                    {t(`editor.tab.${k}`)}
                  </Tabs.Trigger>
                ))}
              </Tabs.List>
              <div className="flex items-center gap-3 text-sm text-grey">
                <span>{t("editor.duration", { minutes: Math.max(1, Math.round(info.seconds / 60)) })}</span>
                <span>{t("editor.readability", { score: info.score })}</span>
                <div className="flex rounded-lg border border-sand bg-white p-0.5" role="group" aria-label={t("editor.language")}>
                  {(["fr", "en"] as Locale[]).map((l) => (
                    <button key={l} type="button" aria-pressed={lang === l} onClick={() => setLang(l)}
                      className={cx("rounded-md px-2.5 py-1 text-xs font-medium uppercase", lang === l && "bg-ink text-white")}>{l}</button>
                  ))}
                </div>
              </div>
            </div>
            <Tabs.Content value="content">
              <Content schema={schema} setSchema={setSchema} lang={lang} selected={selected} setSelected={setSelected} disabled={!canEdit} />
            </Tabs.Content>
            <Tabs.Content value="logic"><LogicPanel schema={schema} setSchema={setSchema} lang={lang} disabled={!canEdit} /></Tabs.Content>
            <Tabs.Content value="settings"><SettingsPanel schema={schema} setSchema={setSchema} lang={lang} form={f} patchForm={patchForm} disabled={!canEdit} /></Tabs.Content>
            <Tabs.Content value="versions"><VersionsPanel base={base} form={f} onRestore={(r) => { setSchemaState(r.draft_schema); revision.current = r.draft_revision; qc.setQueryData(["form", formId], r); }} disabled={!canEdit} /></Tabs.Content>
          </Tabs.Root>
        </div>
        <aside className="hidden lg:block">
          <div className="sticky top-24">
            <p className="mb-2 text-xs uppercase tracking-widest text-grey">{t("editor.preview")}</p>
            <Preview origin={formsOrigin} meta={previewMeta} lang={lang} />
          </div>
        </aside>
      </div>

      <Modal open={showPreview} onClose={() => setShowPreview(false)} title={t("editor.preview")}>
        <Preview origin={formsOrigin} meta={previewMeta} lang={lang} />
      </Modal>
      <PublishResult state={publishing} onClose={() => setPublishing(null)} base={base} />
    </div>
  );
}

/** Live mobile preview: the public form itself, in a frame, fed by postMessage. Nothing is submitted. */
function Preview({ origin, meta, lang }: { origin: string; meta: Record<string, any>; lang: Locale }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const onMsg = (e: MessageEvent) => e.origin === origin && e.data?.type === "arha-preview-ready" && setReady(true);
    addEventListener("message", onMsg);
    return () => removeEventListener("message", onMsg);
  }, [origin]);
  useEffect(() => {
    if (ready) frame.current?.contentWindow?.postMessage({ type: "arha-preview", meta, locale: lang }, origin);
  }, [ready, meta, lang]);
  return (
    <div className="mx-auto w-[360px] max-w-full overflow-hidden rounded-[28px] border-[6px] border-ink bg-cream shadow-lg">
      <iframe ref={frame} title={t("editor.preview")} src={`${origin}/_preview`} className="h-[640px] w-full" />
    </div>
  );
}

function PublishResult({ state, onClose, base }: { state: any; onClose: () => void; base: string }) {
  const [asked, setAsked] = useState(false);
  if (!state) return null;
  const body = state.error?.body ?? {};
  return (
    <Modal open onClose={onClose} title={state.ok ? t("publish.done.title") : t("publish.failed.title")}>
      {state.ok ? (
        <>
          <p className="mb-3">{t("publish.done.text", { version: state.version })}</p>
          <Input readOnly value={state.public_url} onFocus={(e) => e.target.select()} aria-label={t("publish.link")} />
          <div className="mt-4 flex gap-2">
            <Button onClick={() => void navigator.clipboard.writeText(state.public_url)}>{t("common.copy")}</Button>
            <a className="inline-flex min-h-11 items-center rounded-lg border border-sand bg-white px-4 font-medium" target="_blank" rel="noreferrer"
              href={`https://wa.me/?text=${encodeURIComponent(state.public_url)}`}>{t("publish.whatsapp")}</a>
          </div>
          {(state.warnings ?? []).length ? <ul className="mt-4 list-disc pl-5 text-sm text-grey">{state.warnings.map((w: any, i: number) => <li key={i}>{t(`issue.${w.code}`, { target: w.target ?? "", detail: w.detail ?? "" })}</li>)}</ul> : null}
        </>
      ) : (
        <>
          <Notice tone="error">{state.message}</Notice>
          {(body.issues ?? []).filter((i: any) => i.severity === "error").map((i: any, n: number) => (
            <p key={n} className="mb-1 text-sm">{t(`issue.${i.code}`, { target: i.target ?? "", detail: i.detail ?? "" })}</p>
          ))}
          {(body.matches ?? []).length ? (
            <>
              <p className="mb-2 text-sm">{t("publish.blocked.text")}</p>
              <ul className="mb-4 list-disc pl-5 text-sm">{[...new Set<string>(body.matches.map((m: any) => m.term))].map((m) => <li key={m}>{m === "card_number" ? t("publish.blocked.card") : m}</li>)}</ul>
              {asked ? <Notice tone="success">{t("publish.review.sent")}</Notice> : (
                <Button variant="secondary" onClick={async () => { await api(`${base}/publication-review`, { json: {} }); setAsked(true); }}>{t("publish.review.ask")}</Button>
              )}
            </>
          ) : null}
        </>
      )}
      <div className="mt-5 text-right"><Button variant="ghost" onClick={onClose}>{t("common.close")}</Button></div>
    </Modal>
  );
}

interface ContentProps { schema: Schema; setSchema: (s: Schema) => void; lang: Locale; selected: string | null; setSelected: (id: string | null) => void; disabled: boolean }

function Content({ schema, setSchema, lang, selected, setSelected, disabled }: ContentProps) {
  const drag = useRef<{ page: number; index: number } | null>(null);
  const update = (fn: (draft: Schema) => void) => {
    const next = structuredClone(schema);
    fn(next);
    setSchema(next);
  };
  const moveBlock = (fromPage: number, from: number, toPage: number, to: number) => update((s) => {
    const [b] = s.pages[fromPage].blocks.splice(from, 1);
    s.pages[toPage].blocks.splice(to, 0, b);
  });
  return (
    <div>
      {schema.pages.map((page: any, pi: number) => (
        <section key={page.id} className="mb-8" aria-label={t("editor.page", { n: pi + 1 })}>
          <div className="mb-3 flex items-center gap-3">
            <span className="text-xs uppercase tracking-widest text-grey">{t("editor.page", { n: pi + 1 })}</span>
            <input aria-label={t("editor.page.title")} placeholder={t("editor.page.title")} disabled={disabled} value={page.title?.[lang] ?? ""}
              onChange={(e) => update((s) => { s.pages[pi].title = { ...(s.pages[pi].title ?? {}), [lang]: e.target.value }; })}
              className="serif min-w-0 flex-1 border-b border-transparent bg-transparent text-xl outline-none focus:border-sand" />
            {schema.pages.length > 1 && !disabled ? (
              <Button variant="ghost" size="sm" onClick={() => confirm(t("editor.page.delete.confirm")) && update((s) => { s.pages.splice(pi, 1); })}>{t("editor.page.delete")}</Button>
            ) : null}
          </div>
          <div className="grid gap-3"
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => { if (drag.current && page.blocks.length === 0) moveBlock(drag.current.page, drag.current.index, pi, 0); drag.current = null; }}>
            {page.blocks.map((b: Block, bi: number) => (
              <BlockCard key={b.id} block={b} lang={lang} open={selected === b.id} disabled={disabled} schema={schema}
                onToggle={() => setSelected(selected === b.id ? null : b.id)}
                onChange={(fn) => update((s) => fn(s.pages[pi].blocks[bi]))}
                onDragStart={() => { drag.current = { page: pi, index: bi }; }}
                onDropOn={() => { if (drag.current) moveBlock(drag.current.page, drag.current.index, pi, bi); drag.current = null; }}
                actions={{
                  up: bi > 0 ? () => moveBlock(pi, bi, pi, bi - 1) : pi > 0 ? () => moveBlock(pi, bi, pi - 1, schema.pages[pi - 1].blocks.length) : undefined,
                  down: bi < page.blocks.length - 1 ? () => moveBlock(pi, bi, pi, bi + 1) : pi < schema.pages.length - 1 ? () => moveBlock(pi, bi, pi + 1, 0) : undefined,
                  duplicate: () => update((s) => { const copy = structuredClone(b); copy.id = newId("q", allIds(s)); s.pages[pi].blocks.splice(bi + 1, 0, copy); }),
                  remove: () => update((s) => { s.pages[pi].blocks.splice(bi, 1); }),
                }} />
            ))}
          </div>
          {!disabled ? <AddBlock onAdd={(type) => update((s) => { const b = makeBlock(type, s); s.pages[pi].blocks.push(b); setSelected(b.id); })} /> : null}
        </section>
      ))}
      {!disabled ? (
        <Button variant="secondary" onClick={() => update((s) => { s.pages.push({ id: newId("p", allIds(s)), title: {}, blocks: [] }); })}>{t("editor.page.add")}</Button>
      ) : null}
    </div>
  );
}

/** Slash command: type "/" then a few letters, arrows and Enter insert the block (F-EDI-01). */
function AddBlock({ onAdd }: { onAdd: (type: string) => void }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const needle = query.replace(/^\//, "").toLowerCase();
  const items = BLOCK_TYPES.flatMap(([group, types]) => types.map((type) => ({ group, type, label: t(`block.${type}`) })))
    .filter((i) => !needle || i.label.toLowerCase().includes(needle) || i.type.includes(needle));
  const pick = (type: string) => { onAdd(type); setQuery(""); setOpen(false); setCursor(0); };
  return (
    <div className="relative mt-3">
      <Input role="combobox" aria-expanded={open} aria-controls="block-menu" aria-label={t("editor.add")} placeholder={t("editor.add.placeholder")} value={query}
        onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); setCursor(0); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setCursor((c) => Math.min(items.length - 1, c + 1)); }
          if (e.key === "ArrowUp") { e.preventDefault(); setCursor((c) => Math.max(0, c - 1)); }
          if (e.key === "Enter" && items[cursor]) { e.preventDefault(); pick(items[cursor]!.type); }
          if (e.key === "Escape") setOpen(false);
        }} className="border-dashed" />
      {open && items.length ? (
        <ul id="block-menu" role="listbox" className="absolute z-30 mt-1 max-h-72 w-full overflow-y-auto rounded-xl border border-sand bg-white p-1.5 shadow-lg">
          {items.map((i, n) => (
            <li key={i.type} role="option" aria-selected={n === cursor} onMouseDown={(e) => { e.preventDefault(); pick(i.type); }} onMouseEnter={() => setCursor(n)}
              className={cx("flex cursor-pointer items-center justify-between rounded-md px-3 py-2 text-sm", n === cursor && "bg-beige")}>
              <span>{i.label}</span><span className="text-xs text-grey">{t(`block.group.${i.group}`)}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

interface CardProps {
  block: Block; lang: Locale; open: boolean; disabled: boolean; schema: Schema; onToggle: () => void;
  onChange: (fn: (b: Block) => void) => void; onDragStart: () => void; onDropOn: () => void;
  actions: { up?: () => void; down?: () => void; duplicate: () => void; remove: () => void };
}

function BlockCard({ block: b, lang, open, disabled, schema, onToggle, onChange, onDragStart, onDropOn, actions }: CardProps) {
  const setText = (key: string, value: string) => onChange((x) => { x[key] = { ...(x[key] ?? {}), [lang]: value }; });
  const mainKey = b.type === "heading" || b.type === "rich_text" ? "content" : "label";
  const optionList = (key: "options" | "rows" | "columns", priced: boolean) => (
    <div className="mt-3">
      <p className="mb-1.5 text-sm font-medium">{t(`editor.${key}`)}</p>
      {(b[key] ?? []).map((o: any, oi: number) => (
        <div key={o.id} className="mb-2 flex flex-wrap gap-2">
          <Input aria-label={t("editor.option.label")} className="min-w-40 flex-1" value={o.label?.[lang] ?? ""} disabled={disabled}
            onChange={(e) => onChange((x) => { x[key][oi].label = { ...(x[key][oi].label ?? {}), [lang]: e.target.value }; })} />
          {priced ? (
            <>
              <Input aria-label={t("editor.option.price")} title={t("editor.option.price")} className="!w-28" inputMode="numeric" value={o.price ?? 0} disabled={disabled}
                onChange={(e) => onChange((x) => { x[key][oi].price = Math.max(0, Number(e.target.value.replace(/\D/g, "")) || 0); })} />
              {b.type === "ticket_choice" ? (
                <Input aria-label={t("editor.option.quota")} title={t("editor.option.quota")} placeholder={t("editor.option.quota")} className="!w-28" inputMode="numeric" value={o.quota ?? ""} disabled={disabled}
                  onChange={(e) => onChange((x) => { const v = e.target.value.replace(/\D/g, ""); x[key][oi].quota = v === "" ? null : Number(v); })} />
              ) : null}
            </>
          ) : null}
          {!disabled && (b[key] ?? []).length > 1 ? <Button variant="ghost" size="sm" aria-label={t("common.delete")} onClick={() => onChange((x) => { x[key].splice(oi, 1); })}>&times;</Button> : null}
        </div>
      ))}
      {!disabled ? (
        <Button variant="secondary" size="sm" onClick={() => onChange((x) => {
          const ids = new Set<string>((x[key] ?? []).map((o: any) => o.id));
          const id = newId(key === "options" ? "o" : key === "rows" ? "r" : "c", ids);
          const n = (x[key] ?? []).length + 1;
          x[key] = [...(x[key] ?? []), { id, label: { fr: `Option ${n}`, en: `Option ${n}` }, ...(key === "options" ? { code: n } : {}), ...(priced ? { price: 1000 } : {}) }];
        })}>{t("editor.option.add")}</Button>
      ) : null}
    </div>
  );
  return (
    <div draggable={!disabled} onDragStart={onDragStart} onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.stopPropagation(); onDropOn(); }}
      className={cx("rounded-xl border bg-white", open ? "border-orange shadow-sm" : "border-sand")}>
      <div className="flex items-start gap-3 p-4">
        <span aria-hidden className="mt-2 cursor-grab select-none text-grey" title={t("editor.drag")}>&#8942;&#8942;</span>
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center gap-2 text-xs text-grey">
            <span className="uppercase tracking-wider">{t(`block.${b.type}`)}</span>
            {b.required ? <span>&middot; {t("editor.required")}</span> : null}
            <span className="font-mono">{b.id}</span>
          </div>
          {b.type === "divider" ? <hr className="my-2 border-sand" /> : b.type === "rich_text" ? (
            <Textarea aria-label={t("editor.content")} value={b.content?.[lang] ?? ""} disabled={disabled} placeholder={t("editor.content")} onChange={(e) => setText("content", e.target.value)} />
          ) : (
            <input aria-label={t("editor.label")} placeholder={b.type === "hidden" ? t("editor.hidden.hint") : t("editor.label.placeholder")} disabled={disabled || b.type === "hidden"}
              value={b[mainKey]?.[lang] ?? ""} onChange={(e) => setText(mainKey, e.target.value)}
              className={cx("w-full bg-transparent outline-none placeholder:text-grey/60", b.type === "heading" ? "serif text-2xl" : "text-[17px] font-medium")} />
          )}
        </div>
        <div className="flex shrink-0 gap-0.5">
          <Button variant="ghost" size="sm" disabled={disabled || !actions.up} aria-label={t("editor.move.up")} onClick={actions.up}>&#8593;</Button>
          <Button variant="ghost" size="sm" disabled={disabled || !actions.down} aria-label={t("editor.move.down")} onClick={actions.down}>&#8595;</Button>
          <Button variant="ghost" size="sm" aria-expanded={open} onClick={onToggle}>{open ? t("common.close") : t("editor.configure")}</Button>
        </div>
      </div>
      {open ? (
        <div className="border-t border-beige p-4">
          {!NO_LABEL.has(b.type) ? (
            <>
              <label className="mb-1.5 block text-sm font-medium" htmlFor={`help-${b.id}`}>{t("editor.help")}</label>
              <Input id={`help-${b.id}`} value={b.help?.[lang] ?? ""} disabled={disabled} onChange={(e) => setText("help", e.target.value)} />
              <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-sm">
                {b.type !== "computed_display" && !["payment_fixed", "payment_computed"].includes(b.type) ? (
                  <label className="flex items-center gap-2"><input type="checkbox" className="h-4 w-4 accent-orange" checked={!!b.required} disabled={disabled} onChange={(e) => onChange((x) => { x.required = e.target.checked; })} />{t("editor.required")}</label>
                ) : null}
                <label className="flex items-center gap-2" title={t("editor.identifying.hint")}><input type="checkbox" className="h-4 w-4 accent-orange" checked={!!b.identifying} disabled={disabled} onChange={(e) => onChange((x) => { x.identifying = e.target.checked; })} />{t("editor.identifying")}</label>
              </div>
            </>
          ) : null}
          {WITH_OPTIONS.has(b.type) ? optionList("options", PRICED.has(b.type)) : null}
          {b.type === "choice_grid" ? <>{optionList("rows", false)}{optionList("columns", false)}</> : null}
          {b.type === "payment_fixed" ? <NumberRow label={t("editor.amount")} value={b.amount} disabled={disabled} onChange={(v) => onChange((x) => { x.amount = v ?? 0; })} /> : null}
          {b.type === "payment_open" ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <NumberRow label={t("editor.amount.min")} value={b.minAmount} disabled={disabled} onChange={(v) => onChange((x) => { x.minAmount = v ?? 0; })} />
              <NumberRow label={t("editor.amount.max")} value={b.maxAmount} disabled={disabled} onChange={(v) => onChange((x) => { if (v == null) delete x.maxAmount; else x.maxAmount = v; })} />
            </div>
          ) : null}
          {b.type === "payment_computed" || b.type === "computed_display" ? (
            <div className="mt-3">
              <label className="mb-1.5 block text-sm font-medium" htmlFor={`var-${b.id}`}>{t("editor.variable")}</label>
              <Select id={`var-${b.id}`} value={b.variable ?? ""} disabled={disabled} onChange={(e) => onChange((x) => { x.variable = e.target.value; })}>
                <option value="">{t("editor.variable.choose")}</option>
                {schema.variables.map((v: any) => <option key={v.id} value={v.id}>{v.id}</option>)}
              </Select>
              <p className="mt-1 text-sm text-grey">{t("editor.variable.hint")}</p>
            </div>
          ) : null}
          {b.type === "number" ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <NumberRow label={t("editor.min")} value={b.validation?.min} disabled={disabled} onChange={(v) => onChange((x) => { x.validation = { ...(x.validation ?? {}) }; if (v == null) delete x.validation.min; else x.validation.min = v; })} />
              <NumberRow label={t("editor.max")} value={b.validation?.max} disabled={disabled} onChange={(v) => onChange((x) => { x.validation = { ...(x.validation ?? {}) }; if (v == null) delete x.validation.max; else x.validation.max = v; })} />
            </div>
          ) : null}
          {b.type === "linear_scale" || b.type === "rating" ? (
            <NumberRow label={t("editor.scale.max")} value={b.scale?.max ?? 5} disabled={disabled} onChange={(v) => onChange((x) => { x.scale = { ...(x.scale ?? {}), max: Math.min(10, Math.max(2, v ?? 5)) }; })} />
          ) : null}
          {b.type === "hidden" ? (
            <div><label className="mb-1.5 block text-sm font-medium" htmlFor={`param-${b.id}`}>{t("editor.hidden.param")}</label>
              <Input id={`param-${b.id}`} value={b.param ?? ""} disabled={disabled} onChange={(e) => onChange((x) => { x.param = e.target.value.replace(/[^a-zA-Z0-9_]/g, "").slice(0, 32); })} />
              <p className="mt-1 text-sm text-grey">{t("editor.hidden.example", { param: b.param || "source" })}</p></div>
          ) : null}
          {!disabled ? (
            <div className="mt-4 flex gap-2 border-t border-beige pt-3">
              <Button variant="secondary" size="sm" onClick={actions.duplicate}>{t("editor.duplicate")}</Button>
              <Button variant="danger" size="sm" onClick={actions.remove}>{t("common.delete")}</Button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function NumberRow({ label, value, onChange, disabled }: { label: string; value: number | undefined | null; onChange: (v: number | null) => void; disabled?: boolean }) {
  const id = useId();
  return (
    <div className="mt-3">
      <label className="mb-1.5 block text-sm font-medium" htmlFor={id}>{label}</label>
      <Input id={id} inputMode="numeric" disabled={disabled} value={value ?? ""} onChange={(e) => { const v = e.target.value.replace(/[^\d-]/g, ""); onChange(v === "" || v === "-" ? null : Number(v)); }} />
    </div>
  );
}

export { uiLocale };
