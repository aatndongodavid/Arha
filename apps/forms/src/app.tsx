/** Public form: pages, logic, local draft, offline queue, payment and ending (F-PUB-01..09). */
import { evaluate, type LogicResult } from "@arha/logic-ts";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { api } from "./api";
import { Field, type FieldCtx } from "./fields";
import { activate, browserLocale, type Locale, t, tx } from "./i18n";
import { type Due, Payment } from "./pay";
import { clearDraft, enqueue, flushQueue, loadDraft, type Queued, saveDraft, send } from "./store";
import { uuid7 } from "./uuid7";

type Meta = Record<string, any>;
type View = "loading" | "notfound" | "closed" | "form" | "queued" | "pay" | "done";

const code = location.pathname.split("/").filter(Boolean)[0] ?? "";
/** Editor preview: the management application sends the draft by postMessage. Nothing is ever submitted. */
const preview = code === "_preview";
const hidden: Record<string, string> = {};
new URLSearchParams(location.search).forEach((v, k) => {
  if (Object.keys(hidden).length < 20 && k.length <= 32) hidden[k] = v.slice(0, 500);
});

/** Readable text colour on the creator's primary colour (WCAG contrast). */
function onColor(hex: string): string {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.3 ? "#2A1F17" : "#fff";
}

export function App() {
  const [view, setView] = useState<View>("loading");
  const [meta, setMeta] = useState<Meta | null>(null);
  const [locale, setLocale] = useState<Locale>("fr");
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  const [page, setPage] = useState<string | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [showErrors, setShowErrors] = useState(false);
  const [notice, setNotice] = useState("");
  const [online, setOnline] = useState(navigator.onLine);
  const [due, setDue] = useState<Due | null>(null);
  const [paid, setPaid] = useState<Meta | null>(null);
  const [tickets, setTickets] = useState<Meta[]>([]);
  const [ending, setEnding] = useState<Meta>({});
  const [panel, setPanel] = useState<"" | "report" | "resume">("");
  const [busy, setBusy] = useState(false);
  const subId = useRef(uuid7());
  const started = useRef(false);
  const top = useRef<HTMLElement>(null);

  const schema: Meta | undefined = meta?.schema;
  const fallback: Locale = schema?.defaultLocale ?? "fr";

  useEffect(() => {
    const applyTheme = (m: Meta) => {
      const theme = m.schema.settings?.theme ?? {};
      const root = document.documentElement.style;
      root.setProperty("--p", theme.primary ?? "#C9621B");
      root.setProperty("--on-p", onColor(theme.primary ?? "#C9621B"));
      root.setProperty("--bg", theme.background ?? "#FCF9F4");
    };
    if (preview) {
      void (async () => {
        const { app_origin } = await api<{ app_origin: string }>("/config");
        addEventListener("message", (e) => {
          if (e.origin !== app_origin || e.data?.type !== "arha-preview") return; // only the configured application
          const m: Meta = e.data.meta;
          void activate(e.data.locale ?? "fr").then(() => {
            setLocale(e.data.locale ?? "fr");
            applyTheme(m);
            setMeta(m);
            setPage((p) => (m.schema.pages.some((x: Meta) => x.id === p) ? p : m.schema.pages[0]?.id ?? null));
            setView("form");
          });
        });
        parent.postMessage({ type: "arha-preview-ready" }, app_origin);
      })();
      return;
    }
    void (async () => {
      let m: Meta;
      try {
        m = await api(`/forms/${code}`);
      } catch {
        await activate(browserLocale(["fr", "en"], "fr"));
        return setView("notfound");
      }
      const loc = browserLocale(m.schema.locales ?? ["fr"], m.schema.defaultLocale ?? "fr");
      await activate(loc);
      setLocale(loc);
      document.title = m.title;
      applyTheme(m);
      const draft = await loadDraft(m.version_id);
      if (draft) {
        subId.current = draft.id;
        started.current = true;
        setAnswers(draft.answers);
        setHistory(draft.history ?? []);
        setPage(draft.page);
      }
      setMeta(m);
      setPage((p) => p ?? m.schema.pages[0]?.id ?? null);
      setView(m.status === "closed" ? "closed" : "form");
      void flushQueue(); // responses queued earlier on this device
    })();
    const on = () => {
      setOnline(true);
      void flushQueue();
    };
    const off = () => setOnline(false);
    addEventListener("online", on);
    addEventListener("offline", off);
    return () => {
      removeEventListener("online", on);
      removeEventListener("offline", off);
    };
  }, []);

  const result: LogicResult | null = useMemo(() => (schema ? evaluate(schema, answers, hidden) : null), [schema, answers]);
  const errors = useMemo(() => {
    const map: Record<string, string> = {};
    for (const e of result?.errors ?? []) if (!(e.field in map)) map[e.field] = e.code;
    return map;
  }, [result]);

  if (view === "loading" || !result || !schema || !meta) {
    if (view === "notfound") return <Shell><p class="state">{t("state.notfound")}</p></Shell>;
    return <Shell><p class="state" role="status">&hellip;</p></Shell>;
  }

  const pages: Meta[] = schema.pages;
  const current = pages.find((p) => p.id === page) ?? pages[0]!;
  const blocks: Meta[] = current.blocks.filter((b: Meta) => result.visible.includes(b.id));
  const pageErrors = blocks.filter((b) => errors[b.id]).map((b) => b.id);
  const next = result.nextPage[current.id] ?? null;
  const isLast = next === null;
  const step = result.path.indexOf(current.id) + 1;
  const ctx: FieldCtx = {
    locale, fallback, code, currency: meta.payments.currency, variables: result.variables, remaining: meta.tickets ?? {},
  };

  // Written at once on every change: a reload or a crash loses nothing (F-PUB-03, F-EDI-02 spirit).
  const persist = (a: Record<string, unknown>, p: string | null, h: string[]) =>
    preview ? undefined : void saveDraft(meta.version_id, { id: subId.current, answers: a, page: p, history: h });

  const payload = (partial: boolean, lastField?: string) => ({
    id: subId.current, form_version_id: meta.version_id, answers: partial ? answers : result.cleanAnswers, hidden,
    locale, partial, last_field_id: lastField ?? null, consent_version: schema.settings?.consent?.textVersion ?? null,
  });

  const change = (id: string, v: unknown) => {
    const a = { ...answers, [id]: v };
    if (v === null || v === "" || v === undefined) delete a[id];
    setAnswers(a);
    persist(a, page, history);
    if (!started.current && !preview) {
      started.current = true;
      void api(`/forms/${code}/events`, { method: "POST", json: { step: "start", field_id: id } }).catch(() => {});
    }
  };

  const go = (target: string | null, h: string[]) => {
    setPage(target);
    setHistory(h);
    setShowErrors(false);
    persist(answers, target, h);
    top.current?.scrollIntoView();
    top.current?.focus();
  };

  const finish = async () => {
    if (preview) return setView("done");
    setBusy(true);
    setNotice(t("state.sending"));
    const q: Queued = { code, key: uuid7(), payload: payload(false) };
    await enqueue(q); // written locally before any network call (F-PUB-03)
    const res = await send(q);
    setBusy(false);
    setNotice("");
    if (res.ok) {
      await clearDraft(meta.version_id);
      setEnding(res.result.ending ?? {});
      if (res.result.payment_required) {
        setDue(res.result);
        return setView("pay");
      }
      return setView("done");
    }
    if (res.retry) return setView("queued"); // replayed automatically when the network is back (F-PUB-04)
    const codeErr = res.error?.code ?? "";
    setNotice(t(codeErr === "quota_exceeded" ? "state.quota" : codeErr === "form_closed" ? "state.closed" : "err.summary"));
    setShowErrors(true);
  };

  const onNext = (e: Event) => {
    e.preventDefault();
    if (pageErrors.length) {
      setShowErrors(true);
      const first = document.getElementById(`w-${pageErrors[0]}`);
      first?.scrollIntoView({ block: "center" });
      (first?.querySelector("input,select,textarea,button") as HTMLElement | null)?.focus();
      return;
    }
    if (isLast) return void finish();
    if (online && !preview) {
      void api(`/forms/${code}/submissions`, { method: "POST", json: payload(true, blocks[blocks.length - 1]?.id) }).catch(() => {});
    }
    go(next, [...history, current.id]);
  };

  const afterPaid = async (p: Meta) => {
    setPaid(p);
    setView("done");
    if (p.access_token) {
      try {
        setTickets(await api(`/payments/${p.id}/tickets?t=${encodeURIComponent(p.access_token)}`));
      } catch {
        /* tickets also arrive by email */
      }
    }
  };

  const switchLang = async () => {
    const other: Locale = locale === "fr" ? "en" : "fr";
    localStorage.setItem("arha_lang", other);
    await activate(other);
    setLocale(other);
  };

  const org = meta.organization;
  const footer = (
    <footer>
      {org.verified ? <a href={org.verification_url} class="badge">{t("foot.verified")}</a> : null}
      <p class="help">{t("consent.notice", { org: org.name })}</p>
      <nav>
        {(schema.locales ?? []).length > 1 ? <button type="button" class="link" onClick={switchLang}>{t("foot.lang")}</button> : null}
        {view === "form" && schema.settings?.saveAndResume !== false ? (
          <button type="button" class="link" onClick={() => setPanel("resume")}>{t("resume.save")}</button>
        ) : null}
        <button type="button" class="link" onClick={() => setPanel("report")}>{t("foot.report")}</button>
      </nav>
      {meta.branding_required ? <a class="made" href={meta.branding_url}>{t("foot.made")}</a> : null}
    </footer>
  );

  let body;
  if (view === "closed") {
    body = <p class="state">{tx(schema.settings?.closing?.message, locale, fallback) || t("state.closed")}</p>;
  } else if (view === "queued") {
    body = <p class="state" role="status">{t("state.queued")}</p>;
  } else if (view === "pay" && due) {
    body = <Payment code={code} due={due} feeBearer={meta.payments.fee_bearer} locale={locale} onPaid={afterPaid}
      initialPhone={Object.values(result.cleanAnswers).find((v) => typeof v === "string" && /^\+237\d{9}$/.test(v)) as string | undefined} />;
  } else if (view === "done") {
    const end = ending.message ?? schema.settings?.ending?.message;
    const text = tx(end, locale, fallback).replace(/\{(\w+)\}/g, (_, k: string) => String(answers[k] ?? result.variables[k] ?? ""));
    if (ending.redirectUrl && !paid) location.href = ending.redirectUrl;
    body = (
      <div class="done">
        <p class="state">{text}</p>
        {paid?.receipt_number ? <p class="note">{t("done.paid", { number: paid.receipt_number })}</p> : null}
        {paid?.access_token ? (
          <a class="primary" href={`/v1/public/payments/${paid.id}/receipt.pdf?t=${encodeURIComponent(paid.access_token)}&lang=${locale}`}>
            {t("done.receipt")}
          </a>
        ) : null}
        {tickets.length ? <h2>{t("done.tickets")}</h2> : null}
        {tickets.map((tk) => (
          <figure class="ticket" key={tk.serial + tk.category}>
            <div dangerouslySetInnerHTML={{ __html: tk.qr_svg }} />
            <figcaption>{t("done.ticket", { serial: tk.serial, category: tk.category })}</figcaption>
          </figure>
        ))}
      </div>
    );
  } else {
    body = (
      <form onSubmit={onNext} noValidate>
        {schema.settings?.showProgress !== false && result.path.length > 1 ? (
          <div class="progress">
            <progress max={result.path.length} value={step} aria-label={t("nav.progress", { current: step, total: result.path.length })} />
            <span>{t("nav.progress", { current: step, total: result.path.length })}</span>
          </div>
        ) : null}
        {tx(current.title, locale, fallback) ? <h2>{tx(current.title, locale, fallback)}</h2> : null}
        {showErrors && pageErrors.length ? <p class="err" role="alert">{t("err.summary")}</p> : null}
        {blocks.map((b) => (
          <Field key={b.id} block={b} value={answers[b.id]} required={result.required.includes(b.id)} ctx={ctx}
            error={showErrors ? errors[b.id] : undefined} onChange={(v) => change(b.id, v)} />
        ))}
        {notice ? <p class="note" role="status">{notice}</p> : null}
        {!online ? <p class="note" role="status">{t("state.offline")}</p> : null}
        <div class="actions">
          {history.length ? (
            <button type="button" class="ghost" onClick={() => go(history[history.length - 1]!, history.slice(0, -1))}>{t("nav.prev")}</button>
          ) : null}
          <button type="submit" class="primary" disabled={busy}>{isLast ? t("nav.submit") : t("nav.next")}</button>
        </div>
      </form>
    );
  }

  return (
    <Shell>
      <header ref={top} tabIndex={-1}>
        <p class="org">{org.name}</p>
        <h1>{meta.title}</h1>
      </header>
      {body}
      {panel === "report" ? <Report onClose={() => setPanel("")} /> : null}
      {panel === "resume" ? (
        <Resume online={online} onClose={() => setPanel("")}
          save={async () => {
            await api(`/forms/${code}/submissions`, { method: "POST", json: payload(true) });
            return (await api(`/forms/${code}/submissions/${subId.current}/resume-code`, { method: "POST" })).code as string;
          }}
          load={async (rc) => {
            const d = await api(`/forms/${code}/resume`, { method: "POST", json: { code: rc.toUpperCase() } });
            subId.current = d.id;
            started.current = true;
            setAnswers(d.answers ?? {});
            go(pages[0]!.id, []);
          }} />
      ) : null}
      {footer}
    </Shell>
  );
}

function Shell({ children }: { children: preact.ComponentChildren }) {
  return <main>{children}</main>;
}

function Report({ onClose }: { onClose: () => void }) {
  const [reason, setReason] = useState("phishing");
  const [details, setDetails] = useState("");
  const [sent, setSent] = useState(false);
  const submit = async (e: Event) => {
    e.preventDefault();
    await api(`/forms/${code}/report`, { method: "POST", json: { reason, details: details || null } }).catch(() => {});
    setSent(true);
  };
  return (
    <section class="panel" aria-labelledby="rp-t">
      <h2 id="rp-t">{t("report.title")}</h2>
      {sent ? <p class="note" role="status">{t("report.sent")}</p> : (
        <form onSubmit={submit}>
          {["phishing", "scam", "inappropriate", "other"].map((r) => (
            <label class="opt" key={r}>
              <input type="radio" name="reason" checked={reason === r} onChange={() => setReason(r)} />
              <span>{t(`report.${r}`)}</span>
            </label>
          ))}
          <div class="field">
            <label for="rp-d">{t("report.details")}</label>
            <textarea id="rp-d" rows={3} maxLength={2000} value={details} onInput={(e) => setDetails(e.currentTarget.value)} />
          </div>
          <button class="primary" type="submit">{t("report.send")}</button>
        </form>
      )}
      <button type="button" class="link" onClick={onClose}>{t("report.cancel")}</button>
    </section>
  );
}

function Resume(p: { online: boolean; onClose: () => void; save: () => Promise<string>; load: (code: string) => Promise<void> }) {
  const [issued, setIssued] = useState("");
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const run = async (fn: () => Promise<void>, failure: string) => {
    setError("");
    try {
      await fn();
    } catch {
      setError(t(failure));
    }
  };
  return (
    <section class="panel" aria-labelledby="rs-t">
      <h2 id="rs-t">{t("resume.save")}</h2>
      {issued ? <p class="note code" role="status">{t("resume.code", { code: issued })}</p> : (
        <button type="button" class="primary" disabled={!p.online}
          onClick={() => run(async () => setIssued(await p.save()), "state.error")}>{t("resume.save")}</button>
      )}
      {!p.online ? <p class="help">{t("resume.needs_network")}</p> : null}
      <form onSubmit={(e) => {
        e.preventDefault();
        void run(async () => {
          await p.load(input);
          p.onClose();
        }, "resume.invalid");
      }}>
        <div class="field">
          <label for="rs-c">{t("resume.have")}</label>
          <input id="rs-c" value={input} maxLength={6} autocapitalize="characters" autocomplete="off"
            onInput={(e) => setInput(e.currentTarget.value)} />
        </div>
        <button type="submit" class="ghost" disabled={input.length !== 6}>{t("resume.go")}</button>
      </form>
      {error ? <p class="err" role="alert">{error}</p> : null}
      <button type="button" class="link" onClick={p.onClose}>{t("report.cancel")}</button>
    </section>
  );
}
