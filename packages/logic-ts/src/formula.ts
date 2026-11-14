/**
 * Formula text parser for the editor: `SI(qte >= 10; qte * 4500; qte * 5000)` becomes an Expr AST.
 * The server never parses text: it only receives and evaluates the AST (master prompt section 7).
 * French and English function names are accepted. Arguments are separated by `;` or `,`.
 */

export type Expr =
  | { num: number }
  | { str: string }
  | { bool: boolean }
  | { ref: string }
  | { op: string; args: Expr[] };

const FUNCTIONS: Record<string, string> = {
  SI: "if", IF: "if", SOMME: "sum", SUM: "sum", ARRONDI: "round", ROUND: "round", MIN: "min", MAX: "max",
  ET: "and", AND: "and", OU: "or", OR: "or", NON: "not", NOT: "not", NB_SELECTION: "count_selected",
  COUNT_SELECTED: "count_selected",
};
const COMPARISONS: Record<string, string> = { ">=": "gte", "<=": "lte", "<>": "neq", "!=": "neq", "=": "eq",
  "==": "eq", ">": "gt", "<": "lt" };

export class FormulaError extends Error {
  constructor(message: string, public readonly position: number) {
    super(message);
  }
}

type Token = { kind: "num" | "id" | "str" | "op" | "punct"; value: string; pos: number };

function tokenize(src: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  while (i < src.length) {
    const c = src[i]!;
    if (/\s/.test(c)) { i++; continue; }
    if (/[0-9]/.test(c) || (c === "." && /[0-9]/.test(src[i + 1] ?? ""))) {
      const m = /^\d*(?:[.,]\d+)?/.exec(src.slice(i))!;
      // A comma inside a number is a French decimal separator only when followed by digits and not a space.
      tokens.push({ kind: "num", value: m[0].replace(",", "."), pos: i });
      i += m[0].length;
      continue;
    }
    if (/[A-Za-z_À-ſ]/.test(c)) {
      const m = /^[A-Za-z_À-ſ][A-Za-z0-9_À-ſ]*/.exec(src.slice(i))!;
      tokens.push({ kind: "id", value: m[0], pos: i });
      i += m[0].length;
      continue;
    }
    if (c === '"' || c === "'") {
      const end = src.indexOf(c, i + 1);
      if (end < 0) throw new FormulaError("unterminated_string", i);
      tokens.push({ kind: "str", value: src.slice(i + 1, end), pos: i });
      i = end + 1;
      continue;
    }
    const two = src.slice(i, i + 2);
    if ([">=", "<=", "<>", "!=", "=="].includes(two)) {
      tokens.push({ kind: "op", value: two, pos: i });
      i += 2;
      continue;
    }
    if ("+-*/<>=".includes(c)) { tokens.push({ kind: "op", value: c, pos: i }); i++; continue; }
    if ("();,".includes(c)) { tokens.push({ kind: "punct", value: c, pos: i }); i++; continue; }
    throw new FormulaError("unexpected_character", i);
  }
  return tokens;
}

export function parseFormula(src: string, knownRefs?: Set<string>): Expr {
  const tokens = tokenize(src);
  let p = 0;
  const peek = (): Token | undefined => tokens[p];
  const take = (): Token => {
    const t = tokens[p++];
    if (!t) throw new FormulaError("unexpected_end", src.length);
    return t;
  };
  const expectPunct = (v: string): void => {
    const t = take();
    if (t.kind !== "punct" || t.value !== v) throw new FormulaError(`expected ${v}`, t.pos);
  };

  function comparison(): Expr {
    let left = additive();
    const t = peek();
    if (t && t.kind === "op" && t.value in COMPARISONS) {
      take();
      const right = additive();
      left = { op: COMPARISONS[t.value]!, args: [left, right] };
    }
    return left;
  }
  function additive(): Expr {
    let left = multiplicative();
    for (let t = peek(); t && t.kind === "op" && (t.value === "+" || t.value === "-"); t = peek()) {
      take();
      left = { op: t.value === "+" ? "add" : "sub", args: [left, multiplicative()] };
    }
    return left;
  }
  function multiplicative(): Expr {
    let left = unary();
    for (let t = peek(); t && t.kind === "op" && (t.value === "*" || t.value === "/"); t = peek()) {
      take();
      left = { op: t.value === "*" ? "mul" : "div", args: [left, unary()] };
    }
    return left;
  }
  function unary(): Expr {
    const t = peek();
    if (t && t.kind === "op" && t.value === "-") {
      take();
      return { op: "sub", args: [{ num: 0 }, unary()] };
    }
    return primary();
  }
  function primary(): Expr {
    const t = take();
    if (t.kind === "num") return { num: Number(t.value) };
    if (t.kind === "str") return { str: t.value };
    if (t.kind === "punct" && t.value === "(") {
      const e = comparison();
      expectPunct(")");
      return e;
    }
    if (t.kind === "id") {
      const upper = t.value.toUpperCase();
      if (upper === "VRAI" || upper === "TRUE") return { bool: true };
      if (upper === "FAUX" || upper === "FALSE") return { bool: false };
      const next = peek();
      if (next && next.kind === "punct" && next.value === "(") {
        const op = FUNCTIONS[upper];
        if (!op) throw new FormulaError("unknown_function", t.pos);
        take();
        const args: Expr[] = [];
        const close = peek();
        if (!(close && close.kind === "punct" && close.value === ")")) {
          args.push(comparison());
          for (let s = peek(); s && s.kind === "punct" && (s.value === ";" || s.value === ","); s = peek()) {
            take();
            args.push(comparison());
          }
        }
        expectPunct(")");
        return { op, args };
      }
      if (knownRefs && !knownRefs.has(t.value)) throw new FormulaError("unknown_reference", t.pos);
      return { ref: t.value };
    }
    throw new FormulaError("unexpected_token", t.pos);
  }

  const expr = comparison();
  if (p < tokens.length) throw new FormulaError("unexpected_token", tokens[p]!.pos);
  return expr;
}

const INFIX: Record<string, string> = { add: "+", sub: "-", mul: "*", div: "/", gte: ">=", lte: "<=", neq: "<>", eq: "=", gt: ">", lt: "<" };
const NAMES: Record<string, string> = { if: "SI", sum: "SOMME", round: "ARRONDI", min: "MIN", max: "MAX", and: "ET", or: "OU", not: "NON", count_selected: "NB_SELECTION" };

/** Prints an AST back to formula text so the editor can show and edit stored formulas. */
export function formatFormula(expr: Expr | undefined | null): string {
  if (!expr) return "";
  if ("num" in expr) return String(expr.num).replace(".", ",");
  if ("str" in expr) return `"${expr.str}"`;
  if ("bool" in expr) return expr.bool ? "VRAI" : "FAUX";
  if ("ref" in expr) return expr.ref;
  const { op, args } = expr;
  if (op in INFIX && args.length === 2) {
    const wrap = (e: Expr) => ("op" in e && e.op in INFIX ? `(${formatFormula(e)})` : formatFormula(e));
    return `${wrap(args[0]!)} ${INFIX[op]} ${wrap(args[1]!)}`;
  }
  return `${NAMES[op] ?? op.toUpperCase()}(${args.map(formatFormula).join("; ")})`;
}
