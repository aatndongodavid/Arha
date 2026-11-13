import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { parse } from "yaml";

// Prices are read from config/plans.yaml at build time: a price change needs no code change (F-FAC-05).
const file = resolve(process.env.ARHA_CONFIG_DIR ?? resolve(process.cwd(), "../../config"), "plans.yaml");
export const plans = parse(readFileSync(file, "utf-8")) as Record<string, any>;
export const APP_URL = process.env.ARHA_APP_URL ?? "http://localhost:5173";
export const API_URL = process.env.ARHA_API_URL ?? "http://localhost:8000";
export const SECURITY_CONTACT = process.env.ARHA_SECURITY_CONTACT ?? "";

export const money = (n: number, locale: "fr" | "en"): string =>
  `${new Intl.NumberFormat(locale === "fr" ? "fr-FR" : "en-US").format(n).replace(/[  ]/g, " ")} FCFA`;
export const rate = (bps: number, locale: "fr" | "en"): string => (bps / 100).toString().replace(".", locale === "fr" ? "," : ".");
