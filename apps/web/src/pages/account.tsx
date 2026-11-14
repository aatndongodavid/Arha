/** Account: profile, language, active sessions (F-AUT-03), two-factor authentication (F-AUT-02). */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { api, errorText } from "../lib/api";
import { date, setLocale, t } from "../lib/i18n";
import { type Me, useAcceptMe, useMe } from "../session";
import { Badge, Button, Card, Field, Input, Notice, PageTitle, Select, Table } from "../ui";

export function Account() {
  const me = useMe().data!;
  const accept = useAcceptMe();
  const qc = useQueryClient();
  const sessions = useQuery<any[]>({ queryKey: ["sessions"], queryFn: () => api("/me/sessions") });
  const [name, setName] = useState(me.display_name ?? "");
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [backup, setBackup] = useState<string[]>([]);
  const [msg, setMsg] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    try { await fn(); setMsg(ok ? { tone: "success", text: ok } : null); } catch (e) { setMsg({ tone: "error", text: errorText(e) }); }
  };
  const refresh = () => qc.invalidateQueries({ queryKey: ["me"] });
  return (
    <div className="mx-auto max-w-3xl px-5 py-10">
      <Link to="/" className="text-sm text-grey underline">{t("common.back")}</Link>
      <PageTitle title={t("account.title")} subtitle={me.email} />
      {msg ? <Notice tone={msg.tone}>{msg.text}</Notice> : null}
      <div className="grid gap-6">
        <Card>
          <h2 className="mb-4 text-2xl">{t("account.profile")}</h2>
          <Field label={t("auth.name")}>{(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />}</Field>
          <Field label={t("account.language")}>{(id) => (
            <Select id={id} defaultValue={me.locale} onChange={(e) => void run(async () => { accept(await api<Me>("/me", { method: "PATCH", json: { locale: e.target.value } })); setLocale(e.target.value as "fr" | "en"); location.reload(); })}>
              <option value="fr">Français</option><option value="en">English</option>
            </Select>
          )}</Field>
          <Button onClick={() => void run(async () => accept(await api<Me>("/me", { method: "PATCH", json: { display_name: name } })), t("common.saved"))}>{t("common.save")}</Button>
        </Card>
        <Card>
          <h2 className="mb-1 text-2xl">{t("account.mfa")}</h2>
          <p className="mb-4 text-sm text-grey">{t("account.mfa.text")}</p>
          {backup.length ? <Notice tone="success">{t("account.mfa.backup")}<span className="mt-2 block font-mono text-sm">{backup.join("  ")}</span></Notice> : null}
          {me.totp_enabled ? (
            <>
              <Badge tone="green">{t("account.mfa.on")}</Badge>
              {!me.mfa_passed ? (
                <form className="mt-4 flex items-end gap-3" onSubmit={(e) => { e.preventDefault(); void run(async () => { accept(await api<Me>("/auth/mfa", { json: { code } })); setCode(""); }, t("account.mfa.elevated")); }}>
                  <div className="flex-1 [&>div]:mb-0"><Field label={t("auth.totp")} hint={t("account.mfa.elevate.hint")}>{(id) => <Input id={id} inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} />}</Field></div>
                  <Button type="submit">{t("account.mfa.elevate")}</Button>
                </form>
              ) : null}
            </>
          ) : setup ? (
            <form onSubmit={(e) => { e.preventDefault(); void run(async () => { const r = await api<any>("/me/totp/enable", { json: { code } }); setBackup(r.backup_codes); setSetup(null); setCode(""); await refresh(); }); }}>
              <p className="mb-2 text-sm">{t("account.mfa.secret")}</p>
              <p className="mb-4 break-all rounded-lg bg-beige p-3 font-mono text-sm">{setup.secret}</p>
              <Field label={t("auth.totp")}>{(id) => <Input id={id} inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} />}</Field>
              <Button type="submit" disabled={code.length < 6}>{t("account.mfa.enable")}</Button>
            </form>
          ) : <Button variant="secondary" onClick={() => void run(async () => setSetup(await api("/me/totp/setup", { method: "POST" })))}>{t("account.mfa.setup")}</Button>}
        </Card>
        <div>
          <h2 className="mb-3 text-2xl">{t("account.sessions")}</h2>
          <Table head={[t("account.device"), t("account.last_seen"), ""]}>
            {(sessions.data ?? []).map((s) => (
              <tr key={s.id}><td className="max-w-xs truncate">{s.user_agent || "-"} {s.current ? <Badge tone="green">{t("account.current")}</Badge> : null}</td><td className="whitespace-nowrap text-grey">{date(s.last_seen_at)}</td>
                <td className="text-right">{!s.current ? <Button variant="ghost" size="sm" onClick={() => void run(async () => { await api(`/me/sessions/${s.id}`, { method: "DELETE" }); await qc.invalidateQueries({ queryKey: ["sessions"] }); })}>{t("account.revoke")}</Button> : null}</td></tr>
            ))}
          </Table>
        </div>
      </div>
    </div>
  );
}
