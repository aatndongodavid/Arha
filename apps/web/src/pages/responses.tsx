/** Responses table with server side pagination (F-REP-01..03, F-REP-07), exports (F-REP-04) and results (F-ANA-01..03). */
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { useState } from "react";
import { api, download, errorText } from "../lib/api";
import { date, money, num, t, tx } from "../lib/i18n";
import { atLeast, useOrg } from "../session";
import { Badge, Button, Card, cx, Empty, Input, Modal, Notice, PageTitle, Select, Spinner, Stat, Table } from "../ui";

const payTone = (s: string) => (s === "paid" ? "green" : s === "failed" || s === "expired" ? "red" : s === "none" ? "neutral" : "orange") as "green" | "red" | "neutral" | "orange";

export function FormHeader({ active }: { active: "responses" | "results" }) {
  const { org, form } = useParams({ strict: false }) as { org: string; form: string };
  const f = useQuery<any>({ queryKey: ["form", form], queryFn: () => api(`/orgs/${org}/forms/${form}`) });
  const tabs: [string, string][] = [["/o/$org/forms/$form", t("form.tab.edit")], ["/o/$org/forms/$form/responses", t("form.tab.responses")], ["/o/$org/forms/$form/results", t("form.tab.results")]];
  return (
    <>
      <Link to="/o/$org" params={{ org }} className="text-sm text-grey underline">{t("nav.forms")}</Link>
      <h1 className="mb-4 mt-1 text-3xl md:text-4xl">{f.data?.title ?? ""}</h1>
      <nav className="mb-6 flex gap-1 border-b border-sand" aria-label={t("form.tabs")}>
        {tabs.map(([to, label], i) => (
          <Link key={to} to={to} params={{ org, form }} className={cx("-mb-px border-b-2 px-3 py-2 text-[15px]", (i === 1 && active === "responses") || (i === 2 && active === "results") ? "border-orange font-medium" : "border-transparent text-grey")}>{label}</Link>
        ))}
      </nav>
    </>
  );
}

function answerText(v: unknown, block: any): string {
  if (v === null || v === undefined || v === "") return "";
  const label = (id: string) => tx(block?.options?.find((o: any) => o.id === id)?.label) || id;
  if (typeof v === "boolean") return v ? t("common.yes") : t("common.no");
  if (Array.isArray(v)) return v.map((x) => (block?.type === "file_upload" ? t("responses.file") : label(String(x)))).join(", ");
  if (typeof v === "object") return Object.entries(v as Record<string, unknown>).map(([k, q]) => `${label(k)}: ${q}`).join(", ");
  if (block?.type === "signature") return t("responses.signed");
  return block?.options ? label(String(v)) : String(v);
}

export function Responses() {
  const { org: orgId, form: formId } = useParams({ strict: false }) as { org: string; form: string };
  const org = useOrg(orgId).data;
  const qc = useQueryClient();
  const base = `/orgs/${orgId}/forms/${formId}`;
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [partial, setPartial] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const form = useQuery<any>({ queryKey: ["form", formId], queryFn: () => api(base) });
  const pages = useInfiniteQuery({
    queryKey: ["responses", formId, status, q, partial],
    initialPageParam: "",
    queryFn: ({ pageParam }) => api<any>(`${base}/submissions?limit=50${status ? `&status=${status}` : ""}${q ? `&q=${encodeURIComponent(q)}` : ""}${partial ? "&partial=true" : ""}${pageParam ? `&cursor=${pageParam}` : ""}`),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const rows = pages.data?.pages.flatMap((p) => p.items) ?? [];
  const total = pages.data?.pages[0]?.total ?? 0;
  const schema = form.data?.draft_schema;
  const blocks: any[] = (schema?.pages ?? []).flatMap((p: any) => p.blocks).filter((b: any) => !["heading", "rich_text", "divider", "computed_display", "payment_fixed", "payment_computed", "hidden"].includes(b.type));
  const cols = blocks.slice(0, 4);
  const canExport = atLeast(org, "editor") || !!org?.viewer_can_export;
  const refresh = () => qc.invalidateQueries({ queryKey: ["responses", formId] });
  const doExport = async (format: string) => {
    setError("");
    try {
      await download(`${base}/export?format=${format}`, `${form.data?.short_code ?? "export"}.${format === "dictionary" ? "csv" : format}`);
    } catch (e) {
      setError(errorText(e));
    }
  };
  const bulk = async (action: "anonymize" | "delete") => {
    if (!confirm(t(`responses.${action}.confirm`, { count: picked.size }))) return;
    await api(`${base}/submissions/${action}`, { json: { ids: [...picked] } });
    setPicked(new Set());
    await refresh();
  };
  return (
    <>
      <FormHeader active="responses" />
      {error ? <Notice tone="error">{error}</Notice> : null}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input type="search" className="max-w-xs" placeholder={t("responses.search")} aria-label={t("responses.search")} value={q} onChange={(e) => setQ(e.target.value)} />
        <Select aria-label={t("responses.status")} className="!w-44" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">{t("responses.status.all")}</option>
          {["new", "in_progress", "done", "rejected"].map((s) => <option key={s} value={s}>{t(`rstatus.${s}`)}</option>)}
        </Select>
        {org?.features.includes("partial_responses") ? (
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-orange" checked={partial} onChange={(e) => setPartial(e.target.checked)} />{t("responses.partial")}</label>
        ) : null}
        <span className="ml-auto text-sm text-grey">{t("responses.count", { count: num(total) })}</span>
      </div>
      {canExport ? (
        <div className="mb-5 flex flex-wrap items-center gap-2">
          <span className="text-sm text-grey">{t("responses.export")}</span>
          {[["csv", "CSV"], ["xlsx", "Excel"], ["sav", "SPSS"], ["dta", "Stata"], ["dictionary", t("responses.dictionary")]].map(([f, label]) => (
            <Button key={f} variant="secondary" size="sm" onClick={() => void doExport(f!)}>{label}</Button>
          ))}
        </div>
      ) : null}
      {picked.size && atLeast(org, "admin") ? (
        <div className="mb-4 flex items-center gap-2 rounded-lg bg-beige px-4 py-2 text-sm">
          <span>{t("responses.selected", { count: picked.size })}</span>
          <Button variant="secondary" size="sm" onClick={() => void bulk("anonymize")}>{t("responses.anonymize")}</Button>
          <Button variant="danger" size="sm" onClick={() => void bulk("delete")}>{t("common.delete")}</Button>
        </div>
      ) : null}
      {pages.isLoading ? <Spinner /> : rows.length ? (
        <>
          <Table head={["", t("responses.date"), ...cols.map((b) => tx(b.label) || b.id), t("responses.payment"), t("responses.status")]}>
            {rows.map((r: any) => (
              <tr key={r.id} className="hover:bg-cream">
                <td className="w-8"><input type="checkbox" aria-label={t("responses.select")} className="h-4 w-4 accent-orange" checked={picked.has(r.id)}
                  onChange={(e) => { const n = new Set(picked); if (e.target.checked) n.add(r.id); else n.delete(r.id); setPicked(n); }} /></td>
                <td className="whitespace-nowrap"><button type="button" className="underline" onClick={() => setOpen(r.id)}>{date(r.submitted_at ?? r.started_at)}</button>
                  {r.is_partial ? <span className="ml-2"><Badge tone="orange">{t("responses.partial.badge")}</Badge></span> : null}</td>
                {cols.map((b) => <td key={b.id} className="max-w-48 truncate">{answerText(r.answers[b.id], b)}</td>)}
                <td>{r.payment_status === "none" ? "" : <Badge tone={payTone(r.payment_status)}>{t(`pstatus.${r.payment_status}`)}{r.amount_due ? ` · ${money(r.amount_due, r.currency)}` : ""}</Badge>}</td>
                <td><Badge>{t(`rstatus.${r.status}`)}</Badge></td>
              </tr>
            ))}
          </Table>
          {pages.hasNextPage ? <div className="mt-4 text-center"><Button variant="secondary" disabled={pages.isFetchingNextPage} onClick={() => void pages.fetchNextPage()}>{t("responses.more")}</Button></div> : null}
        </>
      ) : <Empty title={t("responses.empty.title")} text={t("responses.empty.text")} />}
      {open ? <Detail base={base} id={open} blocks={blocks} canEdit={atLeast(org, "editor")} onClose={() => { setOpen(null); void refresh(); }} /> : null}
    </>
  );
}

function Detail({ base, id, blocks, canEdit, onClose }: { base: string; id: string; blocks: any[]; canEdit: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const d = useQuery<any>({ queryKey: ["response", id], queryFn: () => api(`${base}/submissions/${id}`) });
  const s = d.data?.submission;
  const used: any[] = d.data?.schema ? d.data.schema.pages.flatMap((p: any) => p.blocks) : blocks;
  return (
    <Modal open onClose={onClose} title={t("responses.detail")} wide>
      {!s ? <Spinner /> : (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
            <span className="text-grey">{date(s.submitted_at ?? s.started_at)}</span>
            {s.source ? <Badge>{t("responses.source", { source: s.source })}</Badge> : null}
            {s.is_partial ? <Badge tone="orange">{t("responses.stopped", { field: tx(used.find((b) => b.id === s.last_field_id)?.label) || s.last_field_id || "" })}</Badge> : null}
            {canEdit ? (
              <Select aria-label={t("responses.status")} className="!ml-auto !min-h-9 !w-40 !py-1" value={s.status}
                onChange={async (e) => { await api(`${base}/submissions/${id}`, { method: "PATCH", json: { status: e.target.value } }); await qc.invalidateQueries({ queryKey: ["response", id] }); }}>
                {["new", "in_progress", "done", "rejected"].map((x) => <option key={x} value={x}>{t(`rstatus.${x}`)}</option>)}
              </Select>
            ) : null}
          </div>
          <dl className="divide-y divide-beige">
            {used.filter((b) => b.id in s.answers).map((b) => (
              <div key={b.id} className="grid gap-1 py-2.5 sm:grid-cols-[40%_1fr]"><dt className="text-sm text-grey">{tx(b.label) || b.id}</dt><dd className="break-words">{answerText(s.answers[b.id], b)}</dd></div>
            ))}
          </dl>
          {d.data.payments.length ? (
            <div className="mt-5">
              <p className="mb-2 text-xs uppercase tracking-widest text-grey">{t("responses.payments")}</p>
              {d.data.payments.map((p: any) => (
                <p key={p.id} className="text-sm"><Badge tone={p.status === "succeeded" ? "green" : p.status === "pending" ? "orange" : "red"}>{t(`paystate.${p.status}`)}</Badge> {money(p.amount, p.currency)} &middot; {(p.channel ?? "").toUpperCase()} &middot; {p.receipt_number ?? p.provider_ref ?? ""}</p>
              ))}
            </div>
          ) : null}
          {d.data.history.length ? (
            <div className="mt-5">
              <p className="mb-2 text-xs uppercase tracking-widest text-grey">{t("responses.history")}</p>
              {d.data.history.map((h: any, i: number) => <p key={i} className="text-sm text-grey">{date(h.at)} &middot; {t(`rstatus.${h.from}`)} &rarr; {t(`rstatus.${h.to}`)}</p>)}
            </div>
          ) : null}
        </>
      )}
      <div className="mt-5 text-right"><Button variant="ghost" onClick={onClose}>{t("common.close")}</Button></div>
    </Modal>
  );
}

function Bars({ data }: { data: { label: string; count: number }[] }) {
  const max = Math.max(1, ...data.map((d) => d.count));
  const total = data.reduce((n, d) => n + d.count, 0);
  return (
    <div className="grid gap-2">
      {data.map((d, i) => (
        <div key={i} className="grid grid-cols-[minmax(80px,32%)_1fr_64px] items-center gap-3 text-sm">
          <span className="truncate" title={d.label}>{d.label}</span>
          <div className="h-5 rounded bg-beige" role="img" aria-label={`${d.label}: ${d.count}`}><div className="h-5 rounded bg-orange" style={{ width: `${(d.count / max) * 100}%` }} /></div>
          <span className="text-right tabular-nums text-grey">{d.count}{total ? ` · ${Math.round((d.count / total) * 100)} %` : ""}</span>
        </div>
      ))}
    </div>
  );
}

export function Results() {
  const { org: orgId, form: formId } = useParams({ strict: false }) as { org: string; form: string };
  const s = useQuery<any>({ queryKey: ["summary", formId], queryFn: () => api(`/orgs/${orgId}/forms/${formId}/summary`) });
  if (!s.data) return <><FormHeader active="results" />{s.isError ? <Notice tone="error">{errorText(s.error)}</Notice> : <Spinner />}</>;
  const { funnel, payments, questions, responses } = s.data;
  const rate = funnel.views ? Math.round((funnel.completes / funnel.views) * 100) : 0;
  return (
    <>
      <FormHeader active="results" />
      <div className="mb-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label={t("results.views")} value={num(funnel.views)} hint={t("results.views.hint")} />
        <Stat label={t("results.starts")} value={num(funnel.starts)} />
        <Stat label={t("results.completes")} value={num(responses)} hint={t("results.rate", { rate })} />
        {payments ? <Stat label={t("results.collected")} value={money(payments.collected)} hint={t("results.fees", { fees: money(payments.platform_fees), failed: payments.failed + payments.expired })} /> : <Stat label={t("results.abandon")} value={num(Math.max(0, funnel.starts - funnel.completes))} />}
      </div>
      {funnel.fields.length ? (
        <Card className="mb-4"><h2 className="mb-3 text-xl">{t("results.funnel")}</h2><Bars data={funnel.fields.map((f: any) => ({ label: f.label, count: f.reached }))} /></Card>
      ) : null}
      {questions.length === 0 ? <Empty title={t("results.empty.title")} text={t("results.empty.text")} /> : questions.map((q: any) => (
        <Card key={q.id} className="mb-4">
          <div className="mb-3 flex items-baseline justify-between gap-3"><h2 className="text-xl">{q.label}</h2><span className="shrink-0 text-sm text-grey">{t("results.answered", { n: q.answered, total: q.total })}</span></div>
          {q.chart === "words" ? (
            <p className="leading-loose">{q.data.map((w: any) => <span key={w.word} className="mr-3 inline-block" style={{ fontSize: `${Math.min(28, 13 + w.count * 2)}px` }}>{w.word}</span>)}</p>
          ) : <Bars data={q.data.map((d: any) => ({ label: d.label, count: d.count }))} />}
          {q.stats?.mean != null ? <p className="mt-3 text-sm text-grey">{t("results.stats", { mean: q.stats.mean, median: q.stats.median, min: q.stats.min, max: q.stats.max })}{q.nps != null ? ` · NPS ${q.nps}` : ""}</p> : null}
        </Card>
      ))}
    </>
  );
}

export { PageTitle };
