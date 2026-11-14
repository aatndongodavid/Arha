import * as Menu from "@radix-ui/react-dropdown-menu";
import { useQueryClient } from "@tanstack/react-query";
import { Link, Outlet, useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { api, errorText } from "../lib/api";
import { t } from "../lib/i18n";
import { atLeast, useMe, useOrg } from "../session";
import { Button, cx, Field, Input, Notice, Spinner } from "../ui";

/** Requires a session. Anonymous visitors go to the sign-in page. */
export function Protected() {
  const me = useMe();
  const navigate = useNavigate();
  useEffect(() => {
    if (me.data === null) void navigate({ to: "/login", search: { next: location.pathname + location.search } });
  }, [me.data]);
  if (!me.data) return <Spinner />;
  return <Outlet />;
}

export function Home() {
  const me = useMe().data!;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    const last = localStorage.getItem("arha_org");
    const target = me.memberships.find((m) => m.organization_id === last) ?? me.memberships[0];
    if (target) void navigate({ to: "/o/$org", params: { org: target.organization_id }, replace: true });
  }, []);
  if (me.memberships.length) return <Spinner />;
  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const org = await api<{ id: string }>("/orgs", { json: { name } });
      await qc.invalidateQueries({ queryKey: ["me"] });
      await navigate({ to: "/o/$org", params: { org: org.id } });
    } catch (err) {
      setError(errorText(err));
    }
  };
  return (
    <div className="mx-auto max-w-md px-5 py-16">
      <p className="serif text-3xl">Arha</p>
      <h1 className="mt-10 text-4xl">{t("onboarding.title")}</h1>
      <p className="mb-8 mt-2 text-grey">{t("onboarding.subtitle")}</p>
      {error ? <Notice tone="error">{error}</Notice> : null}
      <form onSubmit={create}>
        <Field label={t("onboarding.name")} hint={t("onboarding.name.hint")}>
          {(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} minLength={2} maxLength={120} required autoFocus />}
        </Field>
        <div className="mb-6" />
        <Button type="submit" className="w-full" disabled={name.trim().length < 2}>{t("onboarding.submit")}</Button>
      </form>
    </div>
  );
}

export function OrgLayout() {
  const { org: orgId } = useParams({ strict: false }) as { org: string };
  const me = useMe().data!;
  const org = useOrg(orgId);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  useEffect(() => localStorage.setItem("arha_org", orgId), [orgId]);
  if (org.isError) return <div className="p-10"><Notice tone="error">{errorText(org.error)}</Notice><Link to="/account" className="underline">{t("nav.account")}</Link></div>;
  if (!org.data) return <Spinner />;
  const o = org.data;
  const links: [string, string, boolean][] = [
    ["/o/$org", t("nav.forms"), true],
    ["/o/$org/payments", t("nav.payments"), true],
    ["/o/$org/scan", t("nav.scan"), atLeast(o, "editor")],
    ["/o/$org/team", t("nav.team"), true],
    ["/o/$org/billing", t("nav.billing"), true],
    ["/o/$org/settings", t("nav.settings"), atLeast(o, "admin")],
  ];
  const logout = async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    qc.clear();
    await navigate({ to: "/login" });
  };
  const nav = (
    <nav className="flex flex-col gap-1" aria-label={t("nav.main")}>
      {links.filter((l) => l[2]).map(([to, label]) => (
        <Link key={to} to={to} params={{ org: orgId }} activeOptions={{ exact: to === "/o/$org" }} onClick={() => setOpen(false)}
          className="rounded-lg px-3 py-2.5 text-[15px] text-ink/80 hover:bg-beige"
          activeProps={{ className: "bg-beige font-medium !text-ink" }}>{label}</Link>
      ))}
      {me.is_platform_admin ? <Link to="/admin" className="rounded-lg px-3 py-2.5 text-[15px] text-ink/80 hover:bg-beige">{t("nav.admin")}</Link> : null}
    </nav>
  );
  return (
    <div className="min-h-screen md:grid md:grid-cols-[248px_1fr]">
      <aside className={cx("border-sand bg-cream md:sticky md:top-0 md:block md:h-screen md:border-r md:p-5", open ? "block border-b p-5" : "hidden")}>
        <p className="serif mb-6 hidden text-3xl md:block">Arha</p>
        <Menu.Root>
          <Menu.Trigger className="mb-5 flex w-full items-center justify-between rounded-lg border border-sand bg-white px-3 py-2.5 text-left">
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium">{o.name}</span>
              <span className="block text-xs text-grey">{t(`plan.${o.plan_code}`)}</span>
            </span>
            <span aria-hidden className="text-grey">&#9662;</span>
          </Menu.Trigger>
          <Menu.Portal>
            <Menu.Content align="start" sideOffset={6} className="z-50 min-w-56 rounded-xl border border-sand bg-white p-1.5 shadow-lg">
              {me.memberships.map((m) => (
                <Menu.Item key={m.organization_id} className="cursor-pointer rounded-md px-3 py-2 text-sm outline-none data-[highlighted]:bg-beige"
                  onSelect={() => void navigate({ to: "/o/$org", params: { org: m.organization_id } })}>{m.name}</Menu.Item>
              ))}
              <Menu.Separator className="my-1 h-px bg-sand" />
              <Menu.Item className="cursor-pointer rounded-md px-3 py-2 text-sm outline-none data-[highlighted]:bg-beige"
                onSelect={() => { localStorage.removeItem("arha_org"); void navigate({ to: "/new-organization" }); }}>{t("nav.new_org")}</Menu.Item>
              <Menu.Item className="cursor-pointer rounded-md px-3 py-2 text-sm outline-none data-[highlighted]:bg-beige"
                onSelect={() => void navigate({ to: "/account" })}>{t("nav.account")}</Menu.Item>
              <Menu.Item className="cursor-pointer rounded-md px-3 py-2 text-sm outline-none data-[highlighted]:bg-beige" onSelect={logout}>{t("nav.logout")}</Menu.Item>
            </Menu.Content>
          </Menu.Portal>
        </Menu.Root>
        {nav}
      </aside>
      <div className="min-w-0">
        <header className="flex items-center justify-between border-b border-sand px-5 py-3 md:hidden">
          <p className="serif text-2xl">Arha</p>
          <Button variant="secondary" size="sm" aria-expanded={open} onClick={() => setOpen(!open)}>{t("nav.menu")}</Button>
        </header>
        {!me.email_verified ? (
          <div className="border-b border-sand bg-beige px-5 py-2.5 text-sm">
            {t("verify.banner")}{" "}
            <button type="button" className="underline" onClick={() => void api("/auth/resend-verification", { method: "POST" })}>{t("verify.resend")}</button>
          </div>
        ) : null}
        {o.suspended ? <div className="bg-red/10 px-5 py-2.5 text-sm text-red">{t("org.suspended")}</div> : null}
        <main className="mx-auto max-w-6xl px-5 py-8 md:px-10"><Outlet /></main>
      </div>
    </div>
  );
}

export function NewOrganization() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  return (
    <div className="mx-auto max-w-md px-5 py-16">
      <h1 className="text-4xl">{t("onboarding.title")}</h1>
      {error ? <Notice tone="error">{error}</Notice> : null}
      <form className="mt-8" onSubmit={async (e) => {
        e.preventDefault();
        try {
          const org = await api<{ id: string }>("/orgs", { json: { name } });
          await qc.invalidateQueries({ queryKey: ["me"] });
          await navigate({ to: "/o/$org", params: { org: org.id } });
        } catch (err) {
          setError(errorText(err));
        }
      }}>
        <Field label={t("onboarding.name")}>{(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} required minLength={2} />}</Field>
        <Button type="submit" className="w-full">{t("onboarding.submit")}</Button>
      </form>
    </div>
  );
}
