import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { evaluate } from "../src/engine";

const dir = join(__dirname, "..", "..", "logic-conformance", "cases");
const schemas = JSON.parse(readFileSync(join(dir, "_schemas.json"), "utf-8")) as Record<string, object>;
const cases = readdirSync(dir)
  .filter((f) => f.endsWith(".json") && !f.startsWith("_"))
  .flatMap((f) => JSON.parse(readFileSync(join(dir, f), "utf-8")) as Array<Record<string, any>>);

describe("F-LOG-02 conformance suite", () => {
  it("has at least 300 cases", () => expect(cases.length).toBeGreaterThanOrEqual(300));

  it.each(cases.map((c) => [c.name, c]))("%s", (_name, c) => {
    const r = evaluate(schemas[c.base]!, c.answers, c.hidden);
    const result: Record<string, unknown> = {
      visible: r.visible, required: r.required, variables: r.variables, path: r.path, ended: r.ended,
      nextPage: r.nextPage, errors: r.errors, amount: r.amount,
    };
    const exact = String(c.name).startsWith("gen_");
    for (const [key, expected] of Object.entries(c.expect as Record<string, unknown>)) {
      if (expected && typeof expected === "object" && !Array.isArray(expected) && !exact) {
        const got = result[key] as Record<string, unknown>;
        const subset = Object.fromEntries(Object.keys(expected).map((k) => [k, got[k] ?? null]));
        expect(subset, `${c.name}: ${key}`).toEqual(expected);
      } else {
        expect(result[key], `${c.name}: ${key}`).toEqual(expected);
      }
    }
  });
});
