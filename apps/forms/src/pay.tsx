/** Mobile Money payment (F-PAY-02, F-PAY-05). The secret code is never asked here (rule 3). */
import { useEffect, useRef, useState } from "preact/hooks";
import { api, ApiError } from "./api";
import { normalizePhone } from "./fields";
import { type Locale, money, t } from "./i18n";
import { forget, recall, remember } from "./store";
import { uuid7 } from "./uuid7";

export interface Due {
  id: string;
  amount: number;
  currency: string;
  platform_fee: number;
  estimated_provider_fee: number;
  total_to_pay: number;
}

interface Props {
  code: string;
  due: Due;
  feeBearer: string;
  locale: Locale;
  initialPhone?: string;
  onPaid: (payment: Record<string, any>) => void;
}

const MESSAGES: Record<string, string> = {
  ticket_sold_out: "pay.soldout", payment_invalid_phone: "pay.invalid_phone",
  payment_provider_unavailable: "pay.unavailable", rate_limited: "pay.unavailable",
};

export function Payment({ code, due, feeBearer, locale, initialPhone, onPaid }: Props) {
  const [phone, setPhone] = useState(initialPhone ?? "");
  const [state, setState] = useState<"idle" | "starting" | "waiting" | "failed" | "expired">("idle");
  const [error, setError] = useState("");
  const [online, setOnline] = useState(navigator.onLine);
  const timer = useRef<number>();
  const keyName = `paykey:${due.id}`;
  const f = (n: number) => money(n, due.currency, locale);

  const watch = (paymentId: string) => {
    setState("waiting");
    const tick = async () => {
      try {
        const p = await api(`/payments/${paymentId}`);
        if (p.status === "succeeded") {
          await forget(keyName);
          return onPaid(p);
        }
        if (p.status === "failed" || p.status === "expired") {
          await forget(keyName); // a new attempt needs a new idempotency key
          return setState(p.status);
        }
      } catch {
        /* network hiccup: keep polling */
      }
      timer.current = window.setTimeout(tick, 3000); // every 3 seconds (master prompt 9.4)
    };
    void tick();
  };

  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    addEventListener("online", on);
    addEventListener("offline", off);
    // A reload during the wait resumes the same attempt instead of charging again.
    void recall<{ key: string; payment?: string }>(keyName).then((saved) => saved?.payment && watch(saved.payment));
    return () => {
      removeEventListener("online", on);
      removeEventListener("offline", off);
      clearTimeout(timer.current);
    };
  }, []);

  const start = async (e: Event) => {
    e.preventDefault();
    if (state === "starting" || state === "waiting") return; // double click guard, the server is idempotent too
    setError("");
    setState("starting");
    const saved = await recall<{ key: string }>(keyName);
    const key = saved?.key ?? uuid7();
    await remember(keyName, { key });
    try {
      const p = await api(`/forms/${code}/submissions/${due.id}/payments`, {
        method: "POST", key, json: { msisdn: normalizePhone(phone) },
      });
      if (p.status === "failed") {
        await forget(keyName);
        return setState("failed");
      }
      await remember(keyName, { key, payment: p.id });
      watch(p.id);
    } catch (err) {
      const apiErr = err instanceof ApiError ? err : null;
      if (apiErr?.code === "payment_in_progress" && apiErr.body.payment_id) return watch(apiErr.body.payment_id);
      if (apiErr?.code === "payment_already_paid") return onPaid({ status: "succeeded" });
      if (apiErr && apiErr.status !== 409) await forget(keyName);
      setError(t(MESSAGES[apiErr?.code ?? ""] ?? "state.error"));
      setState("idle");
    }
  };

  const busy = state === "starting" || state === "waiting";
  return (
    <form class="pay" onSubmit={start} noValidate>
      <h2>{t("pay.title")}</h2>
      <dl>
        <div><dt>{t("pay.price")}</dt><dd>{f(due.amount)}</dd></div>
        {feeBearer === "payer" ? (
          <>
            <div><dt>{t("pay.fee_arha")}</dt><dd>{f(due.platform_fee)}</dd></div>
            <div><dt>{t("pay.fee_operator")}</dt><dd>{f(due.estimated_provider_fee)}</dd></div>
          </>
        ) : null}
        <div class="sum"><dt>{t("pay.total")}</dt><dd>{f(due.total_to_pay)}</dd></div>
      </dl>
      {state === "waiting" ? (
        <p class="note" role="status">{t("pay.waiting")}</p>
      ) : (
        <>
          <div class="field">
            <label for="msisdn">{t("pay.phone")}</label>
            <input id="msisdn" type="tel" inputMode="tel" autocomplete="tel" required placeholder="6 77 12 34 56"
              value={phone} onInput={(e) => setPhone(e.currentTarget.value)} />
          </div>
          <p class="help">{t("pay.never_pin")}</p>
          {state === "failed" ? <p class="err" role="alert">{t("pay.failed")}</p> : null}
          {state === "expired" ? <p class="err" role="alert">{t("pay.expired")}</p> : null}
          {error ? <p class="err" role="alert">{error}</p> : null}
          {!online ? <p class="note" role="status">{t("pay.offline")}</p> : null}
          <button class="primary" type="submit" disabled={busy || !online || phone.trim().length < 8}>
            {state === "failed" || state === "expired" ? t("pay.retry") : t("nav.pay", { amount: f(due.total_to_pay) })}
          </button>
        </>
      )}
    </form>
  );
}
