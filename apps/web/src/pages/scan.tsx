/** Ticket control (F-PAY-08): camera scan, works offline from a downloaded signed list, reports double scans. */
import { useQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { date, t } from "../lib/i18n";
import { Button, Card, Field, Input, Notice, PageTitle, Select } from "../ui";

interface Bundle { public_key: string; generated_at: string; tickets: { id: string; hash: string; serial: number; category: string; scanned_at: string | null }[] }
type Verdict = { tone: "success" | "error" | "info"; text: string };

const unb64 = (s: string) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (s.length % 4)) % 4)), (c) => c.charCodeAt(0));
const sha256 = async (s: string) => [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)))].map((b) => b.toString(16).padStart(2, "0")).join("");

/** Local Ed25519 check when the browser supports it; the downloaded hash list is the second barrier. */
async function signatureOk(token: string, publicKey: string): Promise<boolean | null> {
  try {
    const [body, sig] = token.split(".");
    const key = await crypto.subtle.importKey("raw", unb64(publicKey), { name: "Ed25519" }, false, ["verify"]);
    return await crypto.subtle.verify({ name: "Ed25519" }, key, unb64(sig!), unb64(body!));
  } catch {
    return null; // Ed25519 not available in this browser
  }
}

export function Scan() {
  const { org: orgId } = useParams({ strict: false }) as { org: string };
  const forms = useQuery<any[]>({ queryKey: ["forms", orgId, "scan"], queryFn: () => api(`/orgs/${orgId}/forms?limit=200`) });
  const [formId, setFormId] = useState("");
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [manual, setManual] = useState("");
  const [camera, setCamera] = useState(false);
  const [pending, setPending] = useState<number>(0);
  const video = useRef<HTMLVideoElement>(null);
  const last = useRef("");
  const storeKey = `arha_scan_${formId}`;
  const queueKey = `arha_scan_queue_${orgId}`;

  const readQueue = (): { hash: string }[] => JSON.parse(localStorage.getItem(queueKey) ?? "[]");
  const sync = async () => {
    const scans = readQueue();
    if (!scans.length || !navigator.onLine) return setPending(scans.length);
    try {
      await api(`/orgs/${orgId}/tickets/sync`, { json: { scans } });
      localStorage.removeItem(queueKey);
      setPending(0);
    } catch {
      setPending(scans.length);
    }
  };
  useEffect(() => {
    setPending(readQueue().length);
    const on = () => void sync();
    addEventListener("online", on);
    return () => removeEventListener("online", on);
  }, []);

  const load = async (id: string) => {
    setFormId(id);
    setVerdict(null);
    if (!id) return setBundle(null);
    try {
      const b = await api<Bundle>(`/orgs/${orgId}/forms/${id}/tickets/offline-bundle`);
      localStorage.setItem(`arha_scan_${id}`, JSON.stringify(b));
      setBundle(b);
    } catch {
      const saved = localStorage.getItem(`arha_scan_${id}`);
      setBundle(saved ? JSON.parse(saved) : null);
    }
  };

  const check = async (token: string) => {
    token = token.trim();
    if (!token || token === last.current) return;
    last.current = token;
    setTimeout(() => { last.current = ""; }, 3000);
    if (navigator.onLine) {
      try {
        const r = await api<any>(`/orgs/${orgId}/tickets/scan`, { json: { token } });
        return setVerdict(r.already_scanned
          ? { tone: "error", text: t("scan.duplicate", { date: date(r.scanned_at) }) }
          : { tone: "success", text: t("scan.valid", { category: r.category, serial: r.serial }) });
      } catch (e) {
        if (e instanceof ApiError && e.status < 500) return setVerdict({ tone: "error", text: t("scan.invalid") });
      }
    }
    // Offline path: signature, then the downloaded list, then the local scan state.
    if (!bundle) return setVerdict({ tone: "error", text: t("scan.no_list") });
    const sig = await signatureOk(token, bundle.public_key);
    const hash = await sha256(token);
    const ticket = bundle.tickets.find((x) => x.hash === hash);
    if (sig === false || !ticket) return setVerdict({ tone: "error", text: t("scan.invalid") });
    if (ticket.scanned_at) return setVerdict({ tone: "error", text: t("scan.duplicate", { date: date(ticket.scanned_at) }) });
    ticket.scanned_at = new Date().toISOString();
    localStorage.setItem(storeKey, JSON.stringify(bundle));
    const q = [...readQueue(), { hash }];
    localStorage.setItem(queueKey, JSON.stringify(q));
    setPending(q.length);
    setVerdict({ tone: "success", text: `${t("scan.valid", { category: ticket.category, serial: ticket.serial })} ${t("scan.offline")}` });
  };

  useEffect(() => {
    if (!camera) return;
    let stream: MediaStream | undefined;
    let stop = false;
    void (async () => {
      const Detector = (window as any).BarcodeDetector;
      if (!Detector) { setCamera(false); return setVerdict({ tone: "info", text: t("scan.no_camera") }); }
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      } catch {
        setCamera(false);
        return setVerdict({ tone: "info", text: t("scan.no_camera") });
      }
      video.current!.srcObject = stream;
      await video.current!.play();
      const detector = new Detector({ formats: ["qr_code"] });
      const loop = async () => {
        if (stop) return;
        try {
          const codes = await detector.detect(video.current!);
          if (codes[0]?.rawValue) await check(codes[0].rawValue);
        } catch { /* frame not ready */ }
        setTimeout(loop, 350);
      };
      void loop();
    })();
    return () => { stop = true; stream?.getTracks().forEach((x) => x.stop()); };
  }, [camera, bundle]);

  const scanned = bundle?.tickets.filter((x) => x.scanned_at).length ?? 0;
  return (
    <>
      <PageTitle title={t("scan.title")} subtitle={t("scan.subtitle")} />
      <Card className="mb-4">
        <Field label={t("scan.form")}>{(id) => (
          <Select id={id} value={formId} onChange={(e) => void load(e.target.value)}>
            <option value="">{t("scan.form.choose")}</option>
            {(forms.data ?? []).map((f) => <option key={f.id} value={f.id}>{f.title}</option>)}
          </Select>
        )}</Field>
        {bundle ? <p className="text-sm text-grey">{t("scan.list", { total: bundle.tickets.length, scanned, date: date(bundle.generated_at) })}</p> : null}
        {pending ? <p className="mt-2 text-sm text-orange-dark">{t("scan.pending", { count: pending })} <button type="button" className="underline" onClick={() => void sync()}>{t("scan.sync")}</button></p> : null}
      </Card>
      {verdict ? <div aria-live="assertive"><Notice tone={verdict.tone}><span className="text-lg font-medium">{verdict.text}</span></Notice></div> : null}
      {formId ? (
        <Card>
          {camera ? <video ref={video} playsInline muted className="mb-4 aspect-square w-full max-w-sm rounded-xl bg-ink object-cover" /> : null}
          <Button className="mb-4 w-full sm:w-auto" onClick={() => setCamera(!camera)}>{camera ? t("scan.camera.stop") : t("scan.camera.start")}</Button>
          <form className="flex gap-3" onSubmit={(e) => { e.preventDefault(); void check(manual); setManual(""); }}>
            <Input aria-label={t("scan.manual")} placeholder={t("scan.manual")} value={manual} onChange={(e) => setManual(e.target.value)} />
            <Button type="submit" variant="secondary">{t("scan.check")}</Button>
          </form>
        </Card>
      ) : null}
    </>
  );
}
