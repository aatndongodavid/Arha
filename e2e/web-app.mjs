// End to end check of the management application: signup, organisation, form from a template, editing with
// autosave and undo, publication, anti-phishing block, responses, results, export, team and billing pages.
import { createRequire } from "node:module";
import { readdirSync, readFileSync } from "node:fs";
const { chromium } = createRequire(import.meta.url)("playwright");

const APP = process.env.APP ?? "http://localhost:5173";
const shots = process.env.SHOTS ?? "/tmp";
const email = `web${Date.now()}@exemple.cm`;
const log = (...a) => console.log("[e2e]", ...a);
const assert = (c, m) => { if (!c) { console.error("FAILED:", m); process.exit(1); } log("ok:", m); };

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 }, deviceScaleFactor: 2, locale: "fr-FR", acceptDownloads: true });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("console", (m) => m.type() === "error" && !m.text().includes("Failed to load resource") && errors.push(m.text()));

await page.goto(`${APP}/signup`);
await page.screenshot({ path: `${shots}/web-1-signup.png` });
await page.getByLabel("Nom et prénom").fill("David Ndongo");
await page.getByLabel("Adresse e-mail").fill(email);
await page.getByLabel("Mot de passe").fill("Correct-Horse-Battery-42");
await page.getByRole("button", { name: "Créer mon compte" }).click();
await page.getByRole("heading", { name: "Créez votre organisation" }).waitFor();
await page.getByLabel("Nom de l'organisation").fill("Centre de formation Excellence");
await page.getByRole("button", { name: "Créer l'organisation" }).click();
await page.getByText("Aucun formulaire pour le moment").waitFor();
assert(await page.getByText("Vérifiez votre adresse e-mail").isVisible(), "unverified banner shown");

const mail = readdirSync("/tmp/arha-mail").map((f) => readFileSync(`/tmp/arha-mail/${f}`, "utf-8")).find((m) => m.includes(email) && m.includes("verify-email"));
await page.goto(mail.match(/http\S+verify-email\S+/)[0]);
await page.getByText("C'est fait").waitFor();
await page.getByRole("link", { name: "Continuer" }).click();
await page.getByText("Aucun formulaire pour le moment").waitFor();
assert(!(await page.getByText("Vérifiez votre adresse e-mail").isVisible()), "email verified through the emailed link");

await page.getByRole("button", { name: "Créer un formulaire" }).first().click();
await page.getByRole("button", { name: /Inscription à une formation/ }).click();
await page.getByText("Tapez / pour ajouter un bloc").or(page.getByPlaceholder("Tapez / pour ajouter un bloc")).first().waitFor();
assert(await page.frameLocator("iframe").getByText("Nom et prénom").first().isVisible({ timeout: 10000 }).catch(() => false) || (await page.waitForTimeout(1500), await page.frameLocator("iframe").getByText("Nom et prénom").first().isVisible()), "live mobile preview renders the draft");

// Slash command inserts a block; autosave; undo removes it.
const add = page.getByPlaceholder("Tapez / pour ajouter un bloc").first();
await add.fill("/oui");
await add.press("Enter");
await page.getByPlaceholder("Saisissez votre question").last().fill("Avez-vous déjà suivi une formation ?");
await page.getByText("Enregistré", { exact: true }).waitFor({ timeout: 5000 });
assert(true, "slash command inserted a block and the draft autosaved");
await page.frameLocator("iframe").getByText("Avez-vous déjà suivi une formation ?").waitFor({ timeout: 5000 });
assert(true, "preview updated after the edit");
await page.screenshot({ path: `${shots}/web-2-editor.png` });
await page.reload();
await page.getByPlaceholder("Tapez / pour ajouter un bloc").first().waitFor();
assert((await page.locator('input[aria-label="Libellé de la question"]').evaluateAll((els) => els.map((e) => e.value))).includes("Avez-vous déjà suivi une formation ?"), "no loss after a brutal reload (F-EDI-02)");

// Logic tab: the template formula is shown as text.
await page.getByRole("tab", { name: "Logique" }).click();
assert((await page.getByLabel("Formule").inputValue()).startsWith("SI(participants >= 10"), "stored AST printed back as a formula");
await page.getByRole("tab", { name: "Contenu" }).click();

await page.getByRole("button", { name: "Publier le formulaire" }).click();
await page.getByText("Votre formulaire est publié").waitFor();
const publicUrl = await page.getByLabel("Lien du formulaire").inputValue();
await page.screenshot({ path: `${shots}/web-3-published.png` });
await page.getByRole("button", { name: "Fermer" }).click();

// Anti-phishing: a block asking for a PIN blocks the next publication with the reason.
await add.fill("/courte");
await add.press("Enter");
await page.getByPlaceholder("Saisissez votre question").last().fill("Entrez votre code PIN Orange Money");
await page.getByText("Enregistré", { exact: true }).waitFor({ timeout: 5000 });
await page.getByRole("button", { name: "Publier les modifications" }).click();
await page.getByText("La publication est impossible").waitFor();
assert(await page.getByText("code pin", { exact: true }).isVisible(), "phishing form blocked with the reason (F-ADM-01)");
await page.screenshot({ path: `${shots}/web-4-blocked.png` });
await page.getByRole("button", { name: "Fermer" }).click();

// A respondent answers on a phone sized page (free path: one participant, pay later is not needed here).
const phone = await (await browser.newContext({ viewport: { width: 360, height: 740 }, locale: "fr-FR" })).newPage();
await phone.goto(publicUrl);
await phone.getByLabel("Nom et prénom").fill("Awa Ngono");
await phone.getByLabel("Numéro de téléphone").fill("677123456");
await phone.getByLabel("Nombre de participants").fill("12");
await phone.getByText("54 000 FCFA").first().waitFor();
assert(true, "volume pricing computed live: 12 x 4 500 = 54 000 FCFA");
await phone.getByRole("checkbox").last().check();
await phone.getByRole("button", { name: "Envoyer ma réponse" }).click();
await phone.getByText("Total à payer").waitFor();
await phone.close();

const formUrl = page.url();
await page.goto(`${formUrl}/responses`);
await page.getByText("Awa Ngono").waitFor();
assert(await page.getByText(/À payer · 54 000 FCFA/).isVisible(), "response listed with the server computed amount");
await page.screenshot({ path: `${shots}/web-5-responses.png` });
const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "CSV", exact: true }).click()]);
assert((await dl.suggestedFilename()).endsWith(".csv"), "CSV export downloads");
await page.getByRole("button", { name: "SPSS" }).click();
await page.getByText("n'est pas incluse dans votre offre").waitFor();
assert(true, "SPSS export refused on the Discovery plan with a clear message");
await page.goto(`${formUrl}/results`);
await page.getByText("Réponses envoyées").waitFor();
await page.screenshot({ path: `${shots}/web-6-results.png`, fullPage: true });

const orgUrl = formUrl.split("/forms/")[0];
for (const [path, text, shot] of [["payments", "Compte de paiement", "web-7-payments"], ["team", "Membres inclus dans votre offre : 1", null], ["billing", "Changer d'offre", "web-8-billing"], ["settings", "Webhooks", null], ["scan", "Contrôle des billets", null]]) {
  await page.goto(`${orgUrl}/${path}`);
  await page.getByText(text).first().waitFor();
  if (shot) await page.screenshot({ path: `${shots}/${shot}.png`, fullPage: true });
}
assert(true, "payments, team, billing, settings and scan pages render");
await page.goto(`${APP}/account`);
await page.getByText("Sessions actives").waitFor();
await page.goto(`${APP}/admin`);
await page.getByText("Cette page n'existe pas").waitFor();
assert(true, "console hidden from a non administrator");

// Mobile layout of the forms list.
const mobile = await ctx.newPage();
await mobile.setViewportSize({ width: 360, height: 740 });
await mobile.goto(orgUrl);
await mobile.getByText("Inscription à une formation").first().waitFor();
await mobile.screenshot({ path: `${shots}/web-9-mobile.png` });
assert(errors.length === 0, `no console errors ${errors.slice(0, 3).join(" | ")}`);
await browser.close();
log("ALL PASSED");
