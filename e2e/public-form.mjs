// End to end check of the public form in Chromium at 360 x 740 (master prompt 14.2):
// signup and publish through the API, fill the form, pay with the simulated provider, see ticket and receipt,
// then an offline submission that is sent exactly once when the network is back (F-PUB-04).
import { createRequire } from "node:module";
const { chromium, request } = createRequire(import.meta.url)("playwright");

const API = process.env.API ?? "http://localhost:8000";
const FORMS = process.env.FORMS ?? "http://localhost:5174";
const shots = process.env.SHOTS ?? "/tmp";
const email = `e2e${Date.now()}@exemple.cm`;
const log = (...a) => console.log("[e2e]", ...a);
const assert = (c, m) => { if (!c) { console.error("FAILED:", m); process.exit(1); } log("ok:", m); };

const ctx = await request.newContext({ baseURL: API });
let r = await ctx.post("/v1/auth/signup", { data: { email, password: "Correct-Horse-Battery-42" } });
assert(r.status() === 201, "signup");
const csrf = (await r.json()).csrf_token;
const H = { "X-CSRF-Token": csrf };
const org = (await (await ctx.post("/v1/orgs", { data: { name: "Gala des Lions" }, headers: H })).json()).id;
// Dev shortcut: read the verification link from the local mail outbox.
const { readdirSync, readFileSync } = await import("node:fs");
const dir = "/tmp/arha-mail";
const mailFile = readdirSync(dir).map((f) => readFileSync(`${dir}/${f}`, "utf-8")).find((m) => m.includes(email) && m.includes("verify-email"));
const token = mailFile.split("token=")[1].split(/\s/)[0];
assert((await ctx.post("/v1/auth/verify-email", { data: { token }, headers: H })).status() === 204, "email verified");
const form = await (await ctx.post(`/v1/orgs/${org}/forms`, { data: { title: "Gala 2027", template: "paid_event" }, headers: H })).json();
const schema = form.draft_schema;
schema.settings.payments.feeBearer = "payer";
await ctx.put(`/v1/orgs/${org}/forms/${form.id}/draft`, { data: { schema, revision: form.draft_revision }, headers: H });
r = await ctx.post(`/v1/orgs/${org}/forms/${form.id}/publish`, { headers: H });
assert(r.status() === 200, "form published");
const url = `${FORMS}/${form.short_code}?source=whatsapp`;

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 360, height: 740 }, deviceScaleFactor: 2, locale: "fr-FR" })).newPage();
const consoleErrors = [];
page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
await page.goto(url);
await page.getByLabel("Nom et prénom").fill("Awa Ngono");
await page.screenshot({ path: `${shots}/form-1.png`, fullPage: true });
await page.getByRole("button", { name: "Suivant" }).click();
assert(await page.getByText("Corrigez les champs signalés").isVisible(), "required phone blocks the page");
await page.getByLabel("Numéro de téléphone").fill("677123456");
await page.getByLabel("Adresse e-mail").fill("awa@exemple.cm");
await page.getByRole("button", { name: "Suivant" }).click();
await page.getByRole("button", { name: "Ajouter un Standard" }).click();
await page.getByRole("button", { name: "Ajouter un Standard" }).click();
await page.waitForTimeout(300);
await page.reload(); // brutal reload: nothing is lost (F-PUB-03)
await page.getByRole("button", { name: "Ajouter un Standard" }).waitFor({ timeout: 5000 });
log("ok: draft restored on the same page after reload");
assert((await page.locator(".qty output").first().textContent()) === "2", "quantities restored");
await page.getByRole("checkbox").check();
await page.screenshot({ path: `${shots}/form-2.png`, fullPage: true });
await page.getByRole("button", { name: "Envoyer ma réponse" }).click();
await page.getByText("Total à payer").waitFor();
assert(await page.getByText("10 600 FCFA").first().isVisible(), "total with fees: 10 000 + 300 + 300");
assert((await page.getByLabel("Numéro Orange Money ou MTN MoMo").inputValue()) === "+237677123456", "phone prefilled");
await page.screenshot({ path: `${shots}/form-3-pay.png`, fullPage: true });
await page.getByRole("button", { name: /Payer 10 600 FCFA/ }).click();
await page.getByText("Validez le paiement sur votre téléphone").waitFor();
// The simulated operator confirms: signed webhook, as the aggregator would send it.
const { execSync } = await import("node:child_process");
execSync(`cd ../apps/api && uv run python ../../e2e/approve.py`, { stdio: "inherit", env: { ...process.env, UV_SYSTEM_CERTS: "1" } });
await page.getByText("Paiement reçu").waitFor({ timeout: 15000 });
await page.locator(".ticket svg").first().waitFor();
assert((await page.locator(".ticket").count()) === 2, "two tickets with QR codes");
assert(await page.getByRole("link", { name: "Télécharger le reçu" }).isVisible(), "receipt link");
await page.screenshot({ path: `${shots}/form-4-done.png`, fullPage: true });

// Offline: fill a free form, cut the network, submit, restore the network, exactly one response.
const free = await (await ctx.post(`/v1/orgs/${org}/forms`, { data: { title: "Sondage", template: "poll" }, headers: H })).json();
await ctx.post(`/v1/orgs/${org}/forms/${free.id}/publish`, { headers: H });
const p2 = await (await browser.newContext({ viewport: { width: 360, height: 740 }, locale: "fr-FR" })).newPage();
await p2.goto(`${FORMS}/${free.short_code}`);
await p2.getByText("Option B").click();
await p2.context().setOffline(true);
await p2.getByRole("button", { name: "Envoyer ma réponse" }).click();
await p2.getByText("Elle sera envoyée dès le retour du réseau").waitFor();
let n = (await (await ctx.get(`/v1/orgs/${org}/forms/${free.id}/submissions`)).json()).total;
assert(n === 0, "nothing reached the server while offline");
await p2.context().setOffline(false);
await p2.evaluate(() => window.dispatchEvent(new Event("online")));
await p2.waitForTimeout(1500);
await p2.reload();
await p2.waitForTimeout(1000);
n = (await (await ctx.get(`/v1/orgs/${org}/forms/${free.id}/submissions`)).json()).total;
assert(n === 1, "queued response sent exactly once after reconnection");
const row = (await (await ctx.get(`/v1/orgs/${org}/forms/${form.id}/submissions`)).json()).items[0];
assert(row.payment_status === "paid" && row.source === "whatsapp", "response paid, source=whatsapp recorded");
assert(consoleErrors.filter((e) => !e.includes("ERR_INTERNET_DISCONNECTED") && !e.includes("Failed to load resource")).length === 0, "no console errors");
await browser.close();
log("ALL PASSED");
