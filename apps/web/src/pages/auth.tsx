import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { api, ApiError, errorText } from "../lib/api";
import { locale, setLocale, t } from "../lib/i18n";
import { type Me, useAcceptMe } from "../session";
import { Button, Field, Input, Notice } from "../ui";

export function AuthShell({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  const [, force] = useState(0);
  return (
    <div className="grid min-h-screen md:grid-cols-[1fr_1.1fr]">
      <aside className="hidden flex-col justify-between bg-beige p-12 md:flex">
        <p className="serif text-3xl">Arha</p>
        <div>
          <p className="serif text-5xl leading-tight">{t("brand.promise")}</p>
          <p className="mt-4 max-w-sm text-grey">{t("brand.pitch")}</p>
        </div>
        <p className="text-sm text-grey">{t("brand.origin")}</p>
      </aside>
      <main className="flex items-center justify-center px-5 py-10">
        <div className="w-full max-w-sm">
          <p className="serif mb-8 text-3xl md:hidden">Arha</p>
          <h1 className="text-3xl">{title}</h1>
          {subtitle ? <p className="mb-6 mt-1 text-grey">{subtitle}</p> : <div className="mb-6" />}
          {children}
          <button type="button" className="mt-8 text-sm text-grey underline"
            onClick={() => { setLocale(locale() === "fr" ? "en" : "fr"); force((n) => n + 1); location.reload(); }}>
            {t("lang.switch")}
          </button>
        </div>
      </main>
    </div>
  );
}

const credentials = z.object({ email: z.string().email(), password: z.string().min(1), totp_code: z.string().optional() });

export function Login() {
  const accept = useAcceptMe();
  const navigate = useNavigate();
  const search = useSearch({ strict: false }) as { next?: string };
  const [error, setError] = useState("");
  const [needCode, setNeedCode] = useState(false);
  const [magic, setMagic] = useState(false);
  const { register, handleSubmit, getValues, formState } = useForm<z.infer<typeof credentials>>({ resolver: zodResolver(credentials) });
  const submit = handleSubmit(async (v) => {
    setError("");
    try {
      accept(await api<Me>("/auth/login", { json: { ...v, totp_code: v.totp_code || null } }));
      await navigate({ to: search.next && search.next.startsWith("/") ? search.next : "/" });
    } catch (e) {
      if (e instanceof ApiError && e.code === "mfa_code_required") return setNeedCode(true);
      setError(errorText(e));
    }
  });
  const sendMagic = async () => {
    const email = getValues("email");
    if (!email) return setError(t("auth.email_first"));
    await api("/auth/magic-link", { json: { email } }).catch(() => undefined);
    setMagic(true);
  };
  return (
    <AuthShell title={t("auth.login.title")} subtitle={t("auth.login.subtitle")}>
      {error ? <Notice tone="error">{error}</Notice> : null}
      {magic ? <Notice tone="success">{t("auth.magic.sent")}</Notice> : null}
      <form onSubmit={submit} noValidate>
        <Field label={t("auth.email")} error={formState.errors.email ? t("auth.email.invalid") : undefined}>
          {(id) => <Input id={id} type="email" autoComplete="email" {...register("email")} />}
        </Field>
        <Field label={t("auth.password")}>
          {(id) => <Input id={id} type="password" autoComplete="current-password" {...register("password")} />}
        </Field>
        {needCode ? (
          <Field label={t("auth.totp")} hint={t("auth.totp.hint")}>
            {(id) => <Input id={id} inputMode="numeric" autoComplete="one-time-code" autoFocus {...register("totp_code")} />}
          </Field>
        ) : null}
        <Button type="submit" className="w-full" disabled={formState.isSubmitting}>{t("auth.login.submit")}</Button>
      </form>
      <Button variant="secondary" className="mt-3 w-full" onClick={sendMagic}>{t("auth.magic.send")}</Button>
      <a href="/v1/auth/google/start" className="mt-3 flex min-h-11 w-full items-center justify-center rounded-lg border border-sand bg-white text-[15px] font-medium hover:border-grey">
        {t("auth.google")}
      </a>
      <p className="mt-6 text-sm text-grey">{t("auth.no_account")} <Link to="/signup" className="text-ink underline">{t("auth.signup.link")}</Link></p>
    </AuthShell>
  );
}

const signupSchema = z.object({ display_name: z.string().max(120).optional(), email: z.string().email(), password: z.string().min(10) });

export function Signup() {
  const accept = useAcceptMe();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const { register, handleSubmit, formState } = useForm<z.infer<typeof signupSchema>>({ resolver: zodResolver(signupSchema) });
  const submit = handleSubmit(async (v) => {
    setError("");
    try {
      accept(await api<Me>("/auth/signup", { json: { ...v, display_name: v.display_name || null, locale: locale() } }));
      await navigate({ to: "/" });
    } catch (e) {
      setError(errorText(e));
    }
  });
  return (
    <AuthShell title={t("auth.signup.title")} subtitle={t("auth.signup.subtitle")}>
      {error ? <Notice tone="error">{error}</Notice> : null}
      <form onSubmit={submit} noValidate>
        <Field label={t("auth.name")}>{(id) => <Input id={id} autoComplete="name" {...register("display_name")} />}</Field>
        <Field label={t("auth.email")} error={formState.errors.email ? t("auth.email.invalid") : undefined}>
          {(id) => <Input id={id} type="email" autoComplete="email" {...register("email")} />}
        </Field>
        <Field label={t("auth.password")} hint={t("auth.password.hint")} error={formState.errors.password ? t("auth.password.short") : undefined}>
          {(id) => <Input id={id} type="password" autoComplete="new-password" {...register("password")} />}
        </Field>
        <Button type="submit" className="w-full" disabled={formState.isSubmitting}>{t("auth.signup.submit")}</Button>
      </form>
      <p className="mt-6 text-sm text-grey">{t("auth.have_account")} <Link to="/login" className="text-ink underline">{t("auth.login.link")}</Link></p>
      <p className="mt-3 text-xs text-grey">{t("auth.terms")}</p>
    </AuthShell>
  );
}

/** Handles the links sent by e-mail: verification, magic link, password reset, invitation. */
export function TokenLanding({ kind }: { kind: "verify-email" | "magic" | "reset-password" | "invitation" }) {
  const { token } = useSearch({ strict: false }) as { token?: string };
  const accept = useAcceptMe();
  const navigate = useNavigate();
  const [state, setState] = useState<"working" | "done" | "error" | "form">(kind === "reset-password" ? "form" : "working");
  const [message, setMessage] = useState("");
  const [password, setPassword] = useState("");
  useEffect(() => {
    if (kind === "reset-password") return;
    void (async () => {
      try {
        if (kind === "verify-email") {
          await api("/auth/verify-email", { json: { token } });
          setState("done");
        } else if (kind === "magic") {
          accept(await api<Me>("/auth/magic-link/consume", { json: { token } }));
          await navigate({ to: "/" });
        } else {
          const r = await api<{ organization_id: string }>("/invitations/accept", { json: { token } });
          await navigate({ to: "/o/$org", params: { org: r.organization_id } });
        }
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return void navigate({ to: "/login", search: { next: location.pathname + location.search } });
        setMessage(errorText(e));
        setState("error");
      }
    })();
  }, []);
  const reset = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api("/auth/password-reset/confirm", { json: { token, password } });
      setState("done");
    } catch (err) {
      setMessage(errorText(err));
    }
  };
  return (
    <AuthShell title={t(`auth.landing.${kind}`)}>
      {state === "working" ? <p className="text-grey">{t("common.loading")}</p> : null}
      {state === "error" ? <Notice tone="error">{message}</Notice> : null}
      {state === "done" ? <Notice tone="success">{t("auth.landing.done")}</Notice> : null}
      {state === "form" ? (
        <form onSubmit={reset}>
          {message ? <Notice tone="error">{message}</Notice> : null}
          <Field label={t("auth.password.new")} hint={t("auth.password.hint")}>
            {(id) => <Input id={id} type="password" autoComplete="new-password" minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} />}
          </Field>
          <Button type="submit" className="w-full" disabled={password.length < 10}>{t("auth.password.save")}</Button>
        </form>
      ) : null}
      {state !== "working" ? <Link to="/" className="mt-4 inline-block underline">{t("common.continue")}</Link> : null}
    </AuthShell>
  );
}
