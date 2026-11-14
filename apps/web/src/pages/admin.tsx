/** Internal console (F-ADM-01..04). Reserved to the platform owner, two-factor authentication required. */
import * as Tabs from "@radix-ui/react-tabs";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { api, ApiError, errorText } from "../lib/api";
import { date, money, num, t } from "../lib/i18n";
import { Badge, Button, Card, Empty, Input, Notice, PageTitle, Spinner, Stat, Table } from "../ui";

export function Admin() {
  const qc = useQueryClient();
  const overview = useQuery<any>({ queryKey: ["admin", "overview"], queryFn: () => api("/admin/overview"), retry: false });
  const metrics = useQuery<any>({ queryKey: ["admin", "metrics"], queryFn: () => api("/admin/metrics"), enabled: overview.isSuccess, refetchInterval: 3600_000 });
  const reports = useQuery<any[]>({ queryKey: ["admin", "reports"], queryFn: () => api("/admin/reports"), enabled: overview.isSuccess });
  const reviews = useQuery<any[]>({ queryKey: ["admin", "reviews"], queryFn: () => api("/admin/reviews"), enabled: overview.isSuccess });
  const verifs = useQuery<any[]>({ queryKey: ["admin", "verifications"], queryFn: () => api("/admin/verifications"), enabled: overview.isSuccess });
  const alerts = useQuery<any[]>({ queryKey: ["admin", "alerts"], queryFn: () => api("/admin/reconciliation-alerts"), enabled: overview.isSuccess });
  const [q, setQ] = useState("");
  const orgs = useQuery<any[]>({ queryKey: ["admin", "orgs", q], queryFn: () => api(`/admin/orgs${q ? `?q=${encodeURIComponent(q)}` : ""}`), enabled: overview.isSuccess });
  const [error, setError] = useState("");
  const act = async (path: string, json?: unknown) => {
    setError("");
    try {
      await api(path, { method: "POST", json });
      await qc.invalidateQueries({ queryKey: ["admin"] });
    } catch (e) {
      setError(errorText(e));
    }
  };
  if (overview.isError) {
    const mfa = overview.error instanceof ApiError && overview.error.code === "mfa_required";
    return <div className="mx-auto max-w-xl px-5 py-16"><Notice tone="error">{mfa ? t("admin.mfa") : t("admin.denied")}</Notice><Link to={mfa ? "/account" : "/"} className="underline">{mfa ? t("nav.account") : t("common.back")}</Link></div>;
  }
  if (!overview.data) return <Spinner />;
  const o = overview.data;
  const m = metrics.data;
  const pct = (v: number | null) => (v == null ? "-" : `${Math.round(v * 1000) / 10} %`);
  const tabs: [string, string, number | null][] = [["metrics", t("admin.tab.metrics"), null], ["reports", t("admin.tab.reports"), o.open_reports], ["reviews", t("admin.tab.reviews"), o.open_reviews],
    ["verifications", t("admin.tab.verifications"), o.pending_verifications], ["alerts", t("admin.tab.alerts"), o.open_reconciliation_alerts], ["orgs", t("admin.tab.orgs"), null]];
  return (
    <div className="mx-auto max-w-6xl px-5 py-10">
      <Link to="/" className="text-sm text-grey underline">{t("common.back")}</Link>
      <PageTitle title={t("admin.title")} subtitle={t("admin.subtitle")} />
      {error ? <Notice tone="error">{error}</Notice> : null}
      <Tabs.Root defaultValue="metrics">
        <Tabs.List className="mb-6 flex flex-wrap gap-1 rounded-lg bg-beige p-1">
          {tabs.map(([k, label, n]) => <Tabs.Trigger key={k} value={k} className="rounded-md px-3 py-1.5 text-sm data-[state=active]:bg-white data-[state=active]:font-medium">{label}{n ? <span className="ml-1.5 rounded-full bg-orange px-1.5 text-xs text-white">{n}</span> : null}</Tabs.Trigger>)}
        </Tabs.List>
        <Tabs.Content value="metrics">
          {!m ? <Spinner /> : (
            <>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Stat label={t("admin.m.collected")} value={money(m.collected_month)} hint={t("admin.m.fees", { fees: money(m.platform_fees_month) })} />
                <Stat label={t("admin.m.mrr")} value={money(m.mrr)} />
                <Stat label={t("admin.m.paying")} value={num(m.paying_customers)} hint={t("admin.m.orgs", { active: m.active_organizations, total: m.organizations })} />
                <Stat label={t("admin.m.success")} value={pct(m.payment_success_rate)} />
                <Stat label={t("admin.m.conversion")} value={pct(m.conversion_60d)} />
                <Stat label={t("admin.m.churn")} value={pct(m.churn_30d)} />
              </div>
              <h2 className="mb-3 mt-8 text-2xl">{t("admin.thresholds")}</h2>
              <div className="grid gap-3 sm:grid-cols-4">
                {m.thresholds.map((th: any) => <Card key={th.code}><p className="serif text-2xl">{th.code}</p><p className="my-2 text-sm text-grey">{th.mrr ? t("admin.threshold.mrr", { amount: money(th.mrr) }) : t("admin.threshold.p1")}</p><Badge tone={th.reached ? "green" : "neutral"}>{th.reached ? t("admin.reached") : t("admin.not_reached")}</Badge></Card>)}
              </div>
              <p className="mt-4 text-sm text-grey">{t("admin.m.note", { date: date(m.generated_at) })}</p>
            </>
          )}
        </Tabs.Content>
        <Tabs.Content value="reports">
          {reports.data?.length ? reports.data.map((r) => (
            <Card key={r.id} className="mb-3">
              <div className="flex flex-wrap items-center justify-between gap-2"><p className="serif text-xl">{r.snapshot.title} <span className="text-sm text-grey">({r.snapshot.organization})</span></p><Badge tone="red">{t(`admin.reason.${r.reason}`)}</Badge></div>
              {r.details ? <p className="my-2 text-sm">{r.details}</p> : null}
              <details className="my-2 text-sm"><summary className="cursor-pointer text-grey">{t("admin.snapshot")}</summary><pre className="mt-2 max-h-64 overflow-auto rounded bg-beige p-3 text-xs">{JSON.stringify(r.snapshot.schema?.pages, null, 1)}</pre></details>
              <div className="flex flex-wrap gap-2">
                <Button variant="danger" size="sm" onClick={() => void act(`/admin/reports/${r.id}/decision`, { decision: "suspend_form" })}>{t("admin.suspend.form")}</Button>
                <Button variant="danger" size="sm" onClick={() => void act(`/admin/reports/${r.id}/decision`, { decision: "suspend_org" })}>{t("admin.suspend.org")}</Button>
                <Button variant="secondary" size="sm" onClick={() => void act(`/admin/reports/${r.id}/decision`, { decision: "dismiss" })}>{t("admin.dismiss")}</Button>
              </div>
            </Card>
          )) : <Empty title={t("admin.empty")} />}
        </Tabs.Content>
        <Tabs.Content value="reviews">
          {reviews.data?.length ? reviews.data.map((r) => (
            <Card key={r.id} className="mb-3">
              <p className="serif text-xl">{r.title}</p>
              <p className="my-2 text-sm">{t("admin.review.terms")} {[...new Set<string>((r.matches.items ?? []).map((x: any) => x.term))].join(", ")}</p>
              {r.message ? <p className="mb-2 text-sm text-grey">{r.message}</p> : null}
              <div className="flex gap-2"><Button size="sm" onClick={() => void act(`/admin/reviews/${r.id}/decision`, { decision: "approve" })}>{t("admin.approve")}</Button>
                <Button variant="danger" size="sm" onClick={() => void act(`/admin/reviews/${r.id}/decision`, { decision: "reject" })}>{t("admin.reject")}</Button></div>
            </Card>
          )) : <Empty title={t("admin.empty")} />}
        </Tabs.Content>
        <Tabs.Content value="verifications">
          {verifs.data?.length ? verifs.data.map((v) => (
            <Card key={v.id} className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <div><p className="serif text-xl">{v.name}</p><p className="text-sm text-grey">{t(`doc.${v.document_type}`)} &middot; {date(v.created_at)}</p></div>
              <div className="flex gap-2"><a href={v.document_url} className="inline-flex min-h-9 items-center rounded-lg border border-sand bg-white px-3 text-sm font-medium">{t("admin.document")}</a>
                <Button size="sm" onClick={() => void act(`/admin/verifications/${v.id}/decision`, { decision: "approve" })}>{t("admin.approve")}</Button>
                <Button variant="danger" size="sm" onClick={() => void act(`/admin/verifications/${v.id}/decision`, { decision: "reject" })}>{t("admin.reject")}</Button></div>
            </Card>
          )) : <Empty title={t("admin.empty")} />}
        </Tabs.Content>
        <Tabs.Content value="alerts">
          {alerts.data?.length ? (
            <Table head={[t("payments.date"), t("admin.alert.kind"), t("payments.ref"), t("admin.alert.details"), ""]}>
              {alerts.data.map((a) => <tr key={a.id}><td className="whitespace-nowrap">{date(a.created_at)}</td><td><Badge tone="red">{t(`admin.alert.${a.kind}`)}</Badge></td><td className="font-mono text-xs">{a.provider_ref}</td><td className="font-mono text-xs">{JSON.stringify(a.details)}</td>
                <td className="text-right"><Button variant="ghost" size="sm" onClick={() => void act(`/admin/reconciliation-alerts/${a.id}/resolve`)}>{t("admin.resolve")}</Button></td></tr>)}
            </Table>
          ) : <Empty title={t("admin.empty")} />}
        </Tabs.Content>
        <Tabs.Content value="orgs">
          <Input type="search" className="mb-4 max-w-sm" placeholder={t("admin.orgs.search")} aria-label={t("admin.orgs.search")} value={q} onChange={(e) => setQ(e.target.value)} />
          <Table head={[t("admin.org"), t("admin.plan"), t("team.since"), t("payments.state"), ""]}>
            {(orgs.data ?? []).map((x) => <tr key={x.id}><td>{x.name}<span className="block text-xs text-grey">{x.slug}</span></td><td>{t(`plan.${x.plan_code}`)}</td><td className="text-grey">{date(x.created_at, false)}</td>
              <td>{x.suspended_at ? <Badge tone="red">{t("status.suspended")}</Badge> : x.verified_at ? <Badge tone="green">{t("settings.verified.yes")}</Badge> : null}</td>
              <td className="text-right">{x.suspended_at ? <Button variant="secondary" size="sm" onClick={() => void act(`/admin/orgs/${x.id}/unsuspend`)}>{t("admin.unsuspend")}</Button>
                : <Button variant="danger" size="sm" onClick={() => { const reason = prompt(t("admin.suspend.reason")); if (reason && reason.length >= 3) void act(`/admin/orgs/${x.id}/suspend`, { reason }); }}>{t("admin.suspend.org")}</Button>}</td></tr>)}
          </Table>
        </Tabs.Content>
      </Tabs.Root>
    </div>
  );
}
