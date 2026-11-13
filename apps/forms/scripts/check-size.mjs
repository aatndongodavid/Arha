// F-PUB-01: the public form ships less than 60 KB of compressed JavaScript and CSS. CI fails beyond.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

const LIMIT = 60 * 1024;
const dir = join(import.meta.dirname, "..", "dist", "assets");
let total = 0;
for (const f of readdirSync(dir)) {
  if (!/\.(js|css)$/.test(f)) continue;
  const size = gzipSync(readFileSync(join(dir, f)), { level: 9 }).length;
  total += size;
  console.log(`${(size / 1024).toFixed(1).padStart(6)} KB  ${f}`);
}
console.log(`Public form JS and CSS, gzip: ${(total / 1024).toFixed(1)} KB (limit 60 KB)`);
if (total > LIMIT) {
  console.error("Size budget exceeded (F-PUB-01)");
  process.exit(1);
}
