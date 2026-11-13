import { i18n } from "@lingui/core";

export type Locale = "fr" | "en";
export type Texts = { fr?: string; en?: string } | undefined | null;

const loaders: Record<Locale, () => Promise<{ default: Record<string, unknown> }>> = {
  fr: () => import("../../../packages/i18n/compiled/forms.fr.json"),
  en: () => import("../../../packages/i18n/compiled/forms.en.json"),
};

export async function activate(locale: Locale): Promise<void> {
  const mod = await loaders[locale]();
  i18n.load(locale, mod.default as never);
  i18n.activate(locale);
  document.documentElement.lang = locale;
}

export const t = (id: string, values?: Record<string, string | number>): string => i18n._(id, values);

/** Text written by the form creator, in the respondent's language with a fallback. */
export const tx = (texts: Texts, locale: Locale, fallback: Locale): string =>
  texts?.[locale] || texts?.[fallback] || texts?.fr || texts?.en || "";

export function money(amount: number, currency: string, locale: Locale): string {
  const n = new Intl.NumberFormat(locale === "fr" ? "fr-FR" : "en-US").format(amount).replace(/[  ]/g, " ");
  return `${n} ${currency === "XAF" || currency === "XOF" ? "FCFA" : currency}`;
}

export function browserLocale(supported: string[], fallback: Locale): Locale {
  const saved = localStorage.getItem("arha_lang");
  if (saved && supported.includes(saved)) return saved as Locale;
  const nav = (navigator.language || "").slice(0, 2);
  return supported.includes(nav) ? (nav as Locale) : fallback;
}
