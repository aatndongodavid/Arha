/** Organisation pages: payments (F-PAY-01, F-ANA-03), team (F-ORG-01, F-ORG-02), billing (F-FAC), settings. */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { api, download, errorText } from "../lib/api";
import { date, money, num, t } from "../lib/i18n";
import { atLeast, useMe, useOrg } from "../session";
import { Badge, Button, Card, Empty, Field, Input, Modal, Notice, PageTitle, Select, Spinner, Stat, Table } from "../ui";

const useOrgId = () => (useParams({ strict: false }) as { org: string }).org;
const stateTone = (s: string) => (s === "succeeded" || s === "verified" || s === "active" ? "green" : s === "pending" || s === "created" ? "orange" : "red") as "green" | "orange" | "red";

export function Payments() {
  const orgId = useOrgId();
  const org = useOrg(orgId).data;
  const qc = useQueryClient();
  const [error, setError] = useState("");
  const summary = useQuery<any>({ queryKey: ["pay-summary", orgId], queryFn: () => api(`/orgs/${orgId}/payments/summary`) });
  const list = useQuery<any[]>({ queryKey: ["payments", orgId], queryFn: () => api(`/orgs/${orgId}/payments`) });
  const accounts = useQuery<any[]>({ queryKey: ["pay-accounts", orgId], queryFn: () => api(`/orgs/${orgId}/payment-accounts`) });
  const account = accounts.data?.[0];
  const connect = async () => {
    setError("");
    try {
      const a = await api<any>(`/orgs/${orgId}/payment-accounts`, { json: { provider: "notchpay" } });
      await qc.invalidateQueries({ queryKey: ["pay-accounts", orgId] });
      if (a.onboarding_url) window.open(a.onboarding_url, "_blank", "noopener");
    } catch (e) {
      setError(errorText(e));
    }
  };
  const s = summary.data;
  return (
    <>
      <PageTitle title={t("payments.title")} subtitle={t("payments.subtitle")} />
      {error ? <Notice tone="error">{error}</Notice> : null}
      <Card className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="serif text-2xl">{t("payments.account")}</p>
          <p className="mt-1 max-w-xl text-sm text-grey">{t("payments.account.text")}</p>
        </div>
        <div className="flex items-center gap-3">
          {account ? <Badge tone={stateTone(account.status)}>{t(`account.${account.status}`)}</Badge> : null}
          {atLeast(org, "admin") && account?.status !== "verified" ? <Button onClick={connect}>{account ? t("payments.account.refresh") : t("payments.account.connect")}</Button> : null}
        </div>
      </Card>
      {s ? (
        <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label={t("payments.collected")} value={money(s.collected, org?.currency)} />
          <Stat label={t("payments.fees")} value={money(s.platform_fees, org?.currency)} hint={t("payments.fees.hint", { rate: ((org?.plan_code === "discovery" ? 3 : org?.plan_code === "pro" ? 1.5 : 1)).toString().replace(".", ",") })} />
          <Stat label={t("payments.success")} value={s.success_rate == null ? "-" : `${Math.round(s.success_rate * 100)} %`} hint={t("payments.success.hint", { ok: s.succeeded, ko: s.failed + s.expired })} />
          <Stat label={t("payments.pending")} value={num(s.pending)} />
        </div>
      ) : null}
      {list.isLoading ? <Spinner /> : list.data?.length ? (
        <Table head={[t("payments.date"), t("payments.amount"), t("payments.channel"), t("payments.ref"), t("payments.state")]}>
          {list.data.map((p) => (
            <tr key={p.id}><td className="whitespace-nowrap">{date(p.created_at)}</td><td className="whitespace-nowrap tabular-nums">{money(p.amount, p.currency)}</td>
              <td>{(p.channel ?? "").toUpperCase()}</td><td className="font-mono text-xs">{p.receipt_number ?? p.provider_ref ?? ""}</td>
              <td><Badge tone={stateTone(p.status)}>{t(`paystate.${p.status}`)}</Badge></td></tr>
          ))}
        </Table>
      ) : <Empty title={t("payments.empty.title")} text={t("payments.empty.text")} />}
    </>
  );
}

export function Team() {
  const orgId = useOrgId();
  const org = useOrg(orgId).data;
  const me = useMe().data!;
  const qc = useQueryClient();
  const canManage = atLeast(org, "admin");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("editor");
  const [msg, setMsg] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  const members = useQuery<any[]>({ queryKey: ["members", orgId], queryFn: () => api(`/orgs/${orgId}/members`) });
  const invitations = useQuery<any[]>({ queryKey: ["invitations", orgId], queryFn: () => api(`/orgs/${orgId}/invitations`), enabled: canManage });
  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    try {
      await fn();
      setMsg(ok ? { tone: "success", text: ok } : null);
      await Promise.all([qc.invalidateQueries({ queryKey: ["members", orgId] }), qc.invalidateQueries({ queryKey: ["invitations", orgId] })]);
    } catch (e) {
      setMsg({ tone: "error", text: errorText(e) });
    }
  };
  return (
    <>
      <PageTitle title={t("team.title")} subtitle={t("team.subtitle", { limit: org?.limits.members ?? 0 })} />
      {msg ? <Notice tone={msg.tone}>{msg.text}</Notice> : null}
      {canManage ? (
        <Card className="mb-6">
          <form className="grid items-end gap-3 sm:grid-cols-[1fr_180px_auto]" onSubmit={(e) => { e.preventDefault(); void run(() => api(`/orgs/${orgId}/invitations`, { json: { email, role } }).then(() => setEmail("")), t("team.invited")); }}>
            <div className="[&>div]:mb-0"><Field label={t("team.invite.email")}>{(id) => <Input id={id} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />}</Field></div>
            <div className="[&>div]:mb-0"><Field label={t("team.role")}>{(id) => (
              <Select id={id} value={role} onChange={(e) => setRole(e.target.value)}>{["admin", "editor", "viewer"].map((r) => <option key={r} value={r}>{t(`role.${r}`)}</option>)}</Select>
            )}</Field></div>
            <Button type="submit">{t("team.invite")}</Button>
          </form>
        </Card>
      ) : null}
      <Table head={[t("team.member"), t("team.role"), t("team.since"), ""]}>
        {(members.data ?? []).map((m) => (
          <tr key={m.user_id}>
            <td><span className="font-medium">{m.display_name || m.email}</span>{m.display_name ? <span className="block text-xs text-grey">{m.email}</span> : null}</td>
            <td>{canManage && m.user_id !== me.id ? (
              <Select aria-label={t("team.role")} className="!min-h-9 !w-40 !py-1" value={m.role} onChange={(e) => void run(() => api(`/orgs/${orgId}/members/${m.user_id}`, { method: "PATCH", json: { role: e.target.value } }))}>
                {["owner", "admin", "editor", "viewer"].map((r) => <option key={r} value={r}>{t(`role.${r}`)}</option>)}
              </Select>
            ) : t(`role.${m.role}`)}</td>
            <td className="text-grey">{date(m.created_at, false)}</td>
            <td className="text-right">{canManage && m.user_id !== me.id ? <Button variant="ghost" size="sm" onClick={() => confirm(t("team.remove.confirm")) && void run(() => api(`/orgs/${orgId}/members/${m.user_id}`, { method: "DELETE" }))}>{t("team.remove")}</Button> : null}</td>
          </tr>
        ))}
        {(invitations.data ?? []).map((i) => (
          <tr key={i.id}><td>{i.email}</td><td>{t(`role.${i.role}`)}</td><td><Badge tone="orange">{t("team.pending")}</Badge></td>
            <td className="text-right"><Button variant="ghost" size="sm" onClick={() => void run(() => api(`/orgs/${orgId}/invitations/${i.id}`, { method: "DELETE" }))}>{t("common.cancel")}</Button></td></tr>
        ))}
      </Table>
      <p className="mt-4 text-sm text-grey">{t("team.roles.help")}</p>
    </>
  );
}

export function Billing() {
  const orgId = useOrgId();
  const org = useOrg(orgId).data;
  const qc = useQueryClient();
  const billing = useQuery<any>({ queryKey: ["billing", orgId], queryFn: () => api(`/orgs/${orgId}/billing`) });
  const plans = useQuery<any>({ queryKey: ["plans"], queryFn: () => api("/plans") });
  const [period, setPeriod] = useState<"monthly" | "yearly">("monthly");
  const [buying, setBuying] = useState<string | null>(null);
  if (!billing.data || !plans.data) return <Spinner />;
  const b = billing.data;
  const pct = b.usage.limit ? Math.min(100, Math.round((b.usage.responses / b.usage.limit) * 100)) : 0;
  const isOwner = org?.role === "owner";
  return (
    <>
      <PageTitle title={t("billing.title")} subtitle={t("billing.current", { plan: t(`plan.${b.plan}`) })} />
      <Card className="mb-6">
        <div className="mb-2 flex items-baseline justify-between"><p className="font-medium">{t("billing.usage")}</p><p className="text-sm text-grey">{t("billing.usage.count", { used: num(b.usage.responses), limit: num(b.usage.limit ?? 0) })}</p></div>
        <div className="h-2.5 rounded-full bg-beige" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={t("billing.usage")}><div className={`h-2.5 rounded-full ${pct >= 100 ? "bg-red" : pct >= 80 ? "bg-orange" : "bg-green"}`} style={{ width: `${pct}%` }} /></div>
        {b.usage.quota_exceeded_at ? <p className="mt-3 text-sm font-medium text-red">{t("billing.grace")}</p> : pct >= 80 ? <p className="mt-3 text-sm text-orange-dark">{t("billing.near")}</p> : null}
        {b.subscription ? <p className="mt-3 text-sm text-grey">{t("billing.renews", { date: date(b.subscription.period_end, false) })}</p> : null}
      </Card>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-2xl">{t("billing.plans")}</h2>
        <div className="flex rounded-lg border border-sand bg-white p-0.5" role="group" aria-label={t("billing.period")}>
          {(["monthly", "yearly"] as const).map((p) => <button key={p} type="button" aria-pressed={period === p} onClick={() => setPeriod(p)} className={`rounded-md px-3 py-1.5 text-sm ${period === p ? "bg-ink text-white" : ""}`}>{t(`billing.${p}`)}</button>)}
        </div>
      </div>
      {b.pioneer_seats_left > 0 ? <Notice>{t("billing.pioneer", { seats: b.pioneer_seats_left, pct: plans.data.pioneer.discount_bps / 100, months: plans.data.pioneer.months })}</Notice> : null}
      <div className="grid gap-4 md:grid-cols-3">
        {["pro", "business", "terrain"].map((code) => {
          const p = plans.data.plans[code];
          const price = period === "monthly" ? p.price_monthly : p.price_yearly;
          return (
            <Card key={code} className={b.plan === code ? "!border-orange" : ""}>
              <p className="serif text-2xl">{t(`plan.${code}`)}</p>
              <p className="mt-2"><span className="serif text-3xl">{money(price)}</span> <span className="text-sm text-grey">{t(`billing.per.${period}`)}</span></p>
              <ul className="my-4 grid gap-1.5 text-sm text-ink/80">
                <li>{t("billing.f.responses", { n: num(p.responses_per_month) })}</li>
                <li>{t("billing.f.members", { n: p.members })}</li>
                <li>{t("billing.f.fee", { rate: (p.fee_bps / 100).toString().replace(".", ",") })}</li>
                <li>{t(`billing.f.${code}`)}</li>
              </ul>
              {b.plan === code ? <Badge tone="green">{t("billing.active")}</Badge> : isOwner ? <Button className="w-full" onClick={() => setBuying(code)}>{t("billing.choose")}</Button> : null}
            </Card>
          );
        })}
      </div>
      <p className="mt-3 text-sm text-grey">{t("billing.enterprise", { price: money(plans.data.plans.enterprise.price_monthly_from) })}</p>
      {b.invoices.length ? (
        <div className="mt-8"><h2 className="mb-3 text-2xl">{t("billing.invoices")}</h2>
          <Table head={[t("billing.invoice.number"), t("payments.date"), t("payments.amount"), ""]}>
            {b.invoices.map((i: any) => (
              <tr key={i.id}><td className="font-mono text-xs">{i.number}</td><td>{date(i.issued_at, false)}</td><td className="tabular-nums">{money(i.amount, i.currency)}</td>
                <td className="text-right"><Button variant="ghost" size="sm" onClick={() => void download(`/orgs/${orgId}/billing/invoices/${i.id}.pdf`, `${i.number}.pdf`)}>PDF</Button></td></tr>
            ))}
          </Table></div>
      ) : null}
      {buying ? <Subscribe orgId={orgId} plan={buying} period={period} onClose={() => { setBuying(null); void qc.invalidateQueries({ queryKey: ["billing", orgId] }); void qc.invalidateQueries({ queryKey: ["org", orgId] }); }} /> : null}
    </>
  );
}

function Subscribe({ orgId, plan, period, onClose }: { orgId: string; plan: string; period: string; onClose: () => void }) {
  const [msisdn, setMsisdn] = useState("");
  const [state, setState] = useState<"idle" | "starting" | "waiting" | "done" | "failed">("idle");
  const [info, setInfo] = useState<any>(null);
  const [error, setError] = useState("");
  const key = useRef(crypto.randomUUID());
  const timer = useRef<number>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  const start = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setState("starting");
    try {
      const r = await api<any>(`/orgs/${orgId}/billing/subscribe`, { json: { plan, period, msisdn: msisdn.replace(/\s/g, "") }, key: key.current });
      setInfo(r);
      if (r.payment.status === "failed") { key.current = crypto.randomUUID(); return setState("failed"); }
      setState("waiting");
      const poll = async () => {
        const p = await api<any>(`/public/payments/${r.payment.id}`).catch(() => null);
        if (p?.status === "succeeded") return setState("done");
        if (p?.status === "failed" || p?.status === "expired") { key.current = crypto.randomUUID(); return setState("failed"); }
        timer.current = window.setTimeout(poll, 3000);
      };
      void poll();
    } catch (err) {
      setError(errorText(err));
      setState("idle");
    }
  };
  return (
    <Modal open onClose={onClose} title={t("billing.subscribe.title", { plan: t(`plan.${plan}`) })}>
      {error ? <Notice tone="error">{error}</Notice> : null}
      {state === "done" ? <Notice tone="success">{t("billing.subscribe.done")}</Notice> : state === "waiting" ? (
        <Notice>{t("billing.subscribe.waiting", { amount: money(info.amount) })}</Notice>
      ) : (
        <form onSubmit={start}>
          {state === "failed" ? <Notice tone="error">{t("billing.subscribe.failed")}</Notice> : null}
          <Field label={t("billing.subscribe.phone")} hint={t("billing.subscribe.hint")}>{(id) => <Input id={id} type="tel" inputMode="tel" placeholder="6 77 12 34 56" required value={msisdn} onChange={(e) => setMsisdn(e.target.value)} />}</Field>
          <Button type="submit" className="w-full" disabled={state === "starting" || msisdn.length < 8}>{t("billing.subscribe.pay")}</Button>
        </form>
      )}
      <div className="mt-4 text-right"><Button variant="ghost" onClick={onClose}>{t("common.close")}</Button></div>
    </Modal>
  );
}

export function Settings() {
  const orgId = useOrgId();
  const org = useOrg(orgId).data;
  const qc = useQueryClient();
  const [msg, setMsg] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  const [name, setName] = useState(org?.name ?? "");
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [docType, setDocType] = useState("rccm");
  const file = useRef<HTMLInputElement>(null);
  const verification = useQuery<any>({ queryKey: ["verification", orgId], queryFn: () => api(`/orgs/${orgId}/verification`) });
  const hooks = useQuery<any[]>({ queryKey: ["webhooks", orgId], queryFn: () => api(`/orgs/${orgId}/webhooks`) });
  const run = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); setMsg({ tone: "success", text: ok }); } catch (e) { setMsg({ tone: "error", text: errorText(e) }); }
  };
  if (!org) return <Spinner />;
  return (
    <>
      <PageTitle title={t("settings.title")} />
      {msg ? <Notice tone={msg.tone}>{msg.text}</Notice> : null}
      <div className="grid gap-6">
        <Card>
          <h2 className="mb-4 text-2xl">{t("settings.org")}</h2>
          <Field label={t("onboarding.name")}>{(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
          <label className="mb-4 flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-orange" checked={org.viewer_can_export}
            onChange={(e) => void run(async () => { await api(`/orgs/${orgId}`, { method: "PATCH", json: { viewer_can_export: e.target.checked } }); await qc.invalidateQueries({ queryKey: ["org", orgId] }); }, t("common.saved"))} />{t("settings.viewer_export")}</label>
          <Button onClick={() => void run(async () => { await api(`/orgs/${orgId}`, { method: "PATCH", json: { name } }); await qc.invalidateQueries({ queryKey: ["org", orgId] }); }, t("common.saved"))}>{t("common.save")}</Button>
        </Card>
        <Card>
          <h2 className="mb-1 text-2xl">{t("settings.verified")}</h2>
          <p className="mb-4 text-sm text-grey">{t("settings.verified.text")}</p>
          {org.verified ? <Badge tone="green">{t("settings.verified.yes")}</Badge> : verification.data?.status === "pending" ? <Badge tone="orange">{t("settings.verified.pending")}</Badge> : (
            <div className="grid items-end gap-3 sm:grid-cols-[200px_1fr_auto]">
              <Select aria-label={t("settings.verified.type")} value={docType} onChange={(e) => setDocType(e.target.value)}>
                {["rccm", "association_receipt", "official_letter"].map((d) => <option key={d} value={d}>{t(`doc.${d}`)}</option>)}
              </Select>
              <input ref={file} type="file" accept="application/pdf,image/png,image/jpeg" aria-label={t("settings.verified.file")} className="min-h-11 rounded-lg border border-dashed border-sand bg-beige px-3 py-2 text-sm" />
              <Button onClick={() => {
                const f = file.current?.files?.[0];
                if (!f) return;
                const body = new FormData();
                body.append("document_type", docType);
                body.append("file", f);
                void run(async () => { await api(`/orgs/${orgId}/verification`, { body }); await qc.invalidateQueries({ queryKey: ["verification", orgId] }); }, t("settings.verified.sent"));
              }}>{t("settings.verified.send")}</Button>
            </div>
          )}
          {verification.data?.status === "rejected" ? <p className="mt-3 text-sm text-red">{t("settings.verified.rejected")} {verification.data.note ?? ""}</p> : null}
        </Card>
        <Card>
          <h2 className="mb-1 text-2xl">{t("settings.webhooks")}</h2>
          <p className="mb-4 text-sm text-grey">{t("settings.webhooks.text")}</p>
          {secret ? <Notice tone="success">{t("settings.webhooks.secret")} <code className="break-all font-mono">{secret}</code></Notice> : null}
          {(hooks.data ?? []).filter((h) => h.active).map((h) => (
            <div key={h.id} className="mb-2 flex items-center justify-between gap-3 rounded-lg border border-sand px-3 py-2 text-sm"><span className="truncate font-mono">{h.url}</span>
              <Button variant="ghost" size="sm" onClick={() => void run(async () => { await api(`/orgs/${orgId}/webhooks/${h.id}`, { method: "DELETE" }); await qc.invalidateQueries({ queryKey: ["webhooks", orgId] }); }, t("common.saved"))}>{t("common.delete")}</Button></div>
          ))}
          <form className="mt-3 flex gap-3" onSubmit={(e) => { e.preventDefault(); void run(async () => { const r = await api<any>(`/orgs/${orgId}/webhooks`, { json: { url } }); setSecret(r.secret); setUrl(""); await qc.invalidateQueries({ queryKey: ["webhooks", orgId] }); }, t("common.saved")); }}>
            <Input type="url" placeholder="https://" aria-label={t("settings.webhooks.url")} value={url} onChange={(e) => setUrl(e.target.value)} required />
            <Button type="submit">{t("common.add")}</Button>
          </form>
        </Card>
      </div>
    </>
  );
}
