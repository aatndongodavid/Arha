// Compiles the JSON catalogs of each surface to Lingui's compiled message format.
// Fails when the French and English catalogs do not have exactly the same keys (rule 8, NF-11).
import { mkdirSync, readFileSync, readdirSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(here, "..", "..", "apps", "forms", "package.json"));
const { compileMessage } = require("@lingui/message-utils/compileMessage");

let failed = false;
for (const surface of ["forms", "web"]) {
  const dir = join(here, surface);
  if (!existsSync(dir)) continue;
  const catalogs = Object.fromEntries(
    readdirSync(dir).filter((f) => f.endsWith(".json")).map((f) => [f.replace(".json", ""), JSON.parse(readFileSync(join(dir, f), "utf-8"))]),
  );
  const fr = Object.keys(catalogs.fr).sort();
  const en = Object.keys(catalogs.en).sort();
  const missing = [...fr.filter((k) => !(k in catalogs.en)).map((k) => `en:${k}`), ...en.filter((k) => !(k in catalogs.fr)).map((k) => `fr:${k}`)];
  if (missing.length) {
    console.error(`[i18n] ${surface}: missing translations: ${missing.join(", ")}`);
    failed = true;
  }
  mkdirSync(join(here, "compiled"), { recursive: true });
  for (const [locale, messages] of Object.entries(catalogs)) {
    const compiled = Object.fromEntries(Object.entries(messages).map(([k, v]) => [k, compileMessage(v)]));
    writeFileSync(join(here, "compiled", `${surface}.${locale}.json`), JSON.stringify(compiled));
  }
}
if (failed) process.exit(1);
console.log("[i18n] catalogs compiled");
