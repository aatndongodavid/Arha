import { i18n } from "@lingui/core";
import en from "../../../../packages/i18n/compiled/web.en.json";
import fr from "../../../../packages/i18n/compiled/web.fr.json";

export type Locale = "fr" | "en";
i18n.load({ fr: fr as never, en: en as never });

export function setLocale(locale: Locale): void {
  i18n.activate(locale);
  document.documentElement.lang = locale;
  localStorage.setItem("arha_lang", locale);
}

export function initialLocale(): Locale {
  const saved = localStorage.getItem("arha_lang");
  if (saved === "fr" || saved === "en") return saved;
  return navigator.language.startsWith("en") ? "en" : "fr";
}

setLocale(initialLocale());

export const t = (id: string, values?: Record<string, string | number>): string => i18n._(id, values);
export const locale = (): Locale => i18n.locale as Locale;

export function money(amount: number | null | undefined, currency = "XAF"): string {
  const n = new Intl.NumberFormat(locale() === "fr" ? "fr-FR" : "en-US").format(amount ?? 0).replace(/[  ]/g, " ");
  return `${n} ${currency === "XAF" || currency === "XOF" ? "FCFA" : currency}`;
}
export const num = (n: number): string => new Intl.NumberFormat(locale() === "fr" ? "fr-FR" : "en-US").format(n).replace(/[  ]/g, " ");
export const date = (iso: string | null | undefined, withTime = true): string =>
  iso ? new Intl.DateTimeFormat(locale() === "fr" ? "fr-FR" : "en-GB", withTime ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" }).format(new Date(iso)) : "";
export const tx = (texts: { fr?: string; en?: string } | null | undefined): string => texts?.[locale()] || texts?.fr || texts?.en || "";
