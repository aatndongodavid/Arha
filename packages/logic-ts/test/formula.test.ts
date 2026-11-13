import { describe, expect, it } from "vitest";
import { evaluate } from "../src/engine";
import { FormulaError, parseFormula } from "../src/formula";

describe("formula parser", () => {
  it("parses the French SI example from the master prompt", () => {
    expect(parseFormula("SI(qte >= 10; qte * 4500; qte * 5000)")).toEqual({
      op: "if",
      args: [
        { op: "gte", args: [{ ref: "qte" }, { num: 10 }] },
        { op: "mul", args: [{ ref: "qte" }, { num: 4500 }] },
        { op: "mul", args: [{ ref: "qte" }, { num: 5000 }] },
      ],
    });
  });

  it("respects precedence and parentheses", () => {
    expect(parseFormula("1 + 2 * 3")).toEqual({ op: "add", args: [{ num: 1 }, { op: "mul", args: [{ num: 2 }, { num: 3 }] }] });
    expect(parseFormula("(1 + 2) * 3")).toEqual({ op: "mul", args: [{ op: "add", args: [{ num: 1 }, { num: 2 }] }, { num: 3 }] });
  });

  it("accepts English names, unary minus, booleans and strings", () => {
    expect(parseFormula("ROUND(-x / 3, 0)")).toEqual({
      op: "round", args: [{ op: "div", args: [{ op: "sub", args: [{ num: 0 }, { ref: "x" }] }, { num: 3 }] }, { num: 0 }],
    });
    expect(parseFormula("ET(VRAI; role = 'vip')")).toEqual({
      op: "and", args: [{ bool: true }, { op: "eq", args: [{ ref: "role" }, { str: "vip" }] }],
    });
  });

  it("rejects unknown functions, references and junk", () => {
    expect(() => parseFormula("EVAL(1)")).toThrow(FormulaError);
    expect(() => parseFormula("a + b", new Set(["a"]))).toThrow(FormulaError);
    expect(() => parseFormula("1 +")).toThrow(FormulaError);
    expect(() => parseFormula("1 $ 2")).toThrow(FormulaError);
    expect(() => parseFormula("(1")).toThrow(FormulaError);
  });

  it("evaluates a parsed formula through the engine", () => {
    const schema = {
      pages: [{ id: "p1", blocks: [{ id: "qte", type: "number" }, { id: "pay", type: "payment_computed", variable: "t" }] }],
      variables: [{ id: "t", type: "number", formula: parseFormula("SI(qte >= 10; qte * 4500; qte * 5000)") }],
      rules: [],
    };
    expect(evaluate(schema, { qte: 12 }).amount).toBe(54000);
  });
});
