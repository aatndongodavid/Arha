/**
 * Browser logic engine. Mirrors apps/api/src/arha/modules/logic/engine.py exactly and passes
 * packages/logic-conformance. The server recomputes everything: this engine only drives the UI.
 *
 * Numbers are fixed point BigInt values scaled by 10^6, identical to the Python reference.
 */

/* eslint-disable @typescript-eslint/no-explicit-any */

export const SCALE = 1_000_000n;

export const INPUT_TYPES = new Set([
  "short_text", "long_text", "email", "phone", "url", "number", "single_choice", "multi_choice", "dropdown",
  "yes_no", "ranking", "choice_grid", "rating", "linear_scale", "nps", "date", "time", "date_range",
  "file_upload", "signature", "payment_open", "product_choice", "ticket_choice", "hidden", "consent",
]);
export const PAYMENT_TYPES = new Set([
  "payment_fixed", "payment_computed", "payment_open", "product_choice", "ticket_choice",
]);
const CHOICE_TYPES = new Set(["single_choice", "dropdown"]);
const EMAIL_RE = /^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$/;
const URL_RE = /^https?:\/\/[^\s/$.?#][^\s]*$/i;
const E164_RE = /^\+[1-9]\d{7,14}$/;
const CM_MOBILE_RE = /^\+237[62]\d{8}$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;
const DECIMAL_RE = /^([+-]?)(\d*)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/;
const NUMERIC_STR_RE = /^[+-]?\d+(\.\d+)?$/;

type Dict = Record<string, any>;

/** Scaled number produced by evaluation (Python `Num`). Raw JSON numbers stay plain numbers. */
export class Num {
  constructor(public readonly v: bigint) {}
}

// ------------------------------------------------------------------ fixed point arithmetic

const pow10 = (n: number): bigint => 10n ** BigInt(n);

export function divRoundHalfEven(a: bigint, b: bigint): bigint {
  if (b < 0n) {
    a = -a;
    b = -b;
  }
  // Floor division like Python divmod.
  let q = a / b;
  let r = a % b;
  if (r !== 0n && r < 0n) {
    q -= 1n;
    r += b;
  }
  const twice = 2n * r;
  if (twice > b || (twice === b && (q % 2n !== 0n))) q += 1n;
  return q;
}

function parseDecimal(text: string): bigint {
  const m = DECIMAL_RE.exec(text);
  if (!m || (!m[2] && !m[3])) throw new Error("invalid decimal");
  const sign = m[1] === "-" ? -1n : 1n;
  const frac = m[3] ?? "";
  const digits = (m[2] || "0") + frac;
  const exp = Number(m[4] ?? 0) - frac.length + 6;
  const n = BigInt(digits);
  if (exp >= 0) return sign * n * pow10(exp);
  return sign * divRoundHalfEven(n, pow10(-exp));
}

export function toFixed(value: unknown): bigint {
  if (typeof value === "boolean" || value === null || value === undefined) return 0n;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return 0n;
    return parseDecimal(String(value));
  }
  if (typeof value === "bigint") return value * SCALE;
  if (typeof value === "string") {
    try {
      return parseDecimal(value.trim());
    } catch {
      return 0n;
    }
  }
  return 0n;
}

const fixedMul = (a: bigint, b: bigint): bigint => divRoundHalfEven(a * b, SCALE);
const fixedDiv = (a: bigint, b: bigint): bigint => divRoundHalfEven(a * SCALE, b);
function fixedRound(a: bigint, digits: bigint): bigint {
  const d = digits < 0n ? 0n : digits > 6n ? 6n : digits;
  const unit = pow10(6 - Number(d));
  return divRoundHalfEven(a, unit) * unit;
}
export const toCurrencyUnit = (a: bigint): bigint => divRoundHalfEven(a, SCALE);

export function fixedToJson(a: bigint): number {
  if (a % SCALE === 0n) return Number(a / SCALE);
  const neg = a < 0n;
  const abs = neg ? -a : a;
  const whole = abs / SCALE;
  const frac = (abs % SCALE).toString().padStart(6, "0");
  return Number(`${neg ? "-" : ""}${whole}.${frac}`);
}

// ------------------------------------------------------------------ helpers

const isNum = (v: unknown): v is Num => v instanceof Num;
const isPlainNumber = (v: unknown): v is number => typeof v === "number";
const isDict = (v: unknown): v is Dict =>
  typeof v === "object" && v !== null && !Array.isArray(v) && !(v instanceof Num);

/** Python str() of a JSON value, for list comparisons. */
function pyStr(v: unknown): string {
  if (v === true) return "True";
  if (v === false) return "False";
  if (v === null || v === undefined) return "None";
  return String(v);
}

export function isEmpty(v: unknown): boolean {
  if (v === null || v === undefined) return true;
  if (typeof v === "string") return v.trim() === "";
  if (Array.isArray(v)) return v.length === 0;
  if (isDict(v)) {
    const values = Object.values(v);
    return values.length === 0 || values.every((x) => isEmpty(x) || x === 0 || x === false);
  }
  return false;
}

function numericLike(v: unknown): boolean {
  if (isNum(v)) return true;
  if (isPlainNumber(v)) return true;
  if (typeof v === "string") return NUMERIC_STR_RE.test(v.trim() || "x");
  return false;
}

function asNum(v: unknown): bigint {
  if (isNum(v)) return v.v;
  if (typeof v === "boolean") return v ? SCALE : 0n;
  if (isPlainNumber(v) || typeof v === "string") return toFixed(v);
  if (Array.isArray(v)) return BigInt(v.length) * SCALE;
  return 0n;
}

function truthy(v: unknown): boolean {
  if (isNum(v)) return v.v !== 0n;
  if (v === null || v === undefined || v === false || v === 0 || v === "") return false;
  return !isEmpty(v);
}

function norm(v: unknown): unknown {
  if (isNum(v) || typeof v === "boolean") return v;
  if (isPlainNumber(v)) return new Num(toFixed(v));
  return v;
}

function cmp(a: unknown, b: unknown): number | null {
  if (a === null || a === undefined || b === null || b === undefined) return null;
  if (numericLike(a) && numericLike(b)) {
    const x = asNum(norm(a));
    const y = asNum(norm(b));
    return x > y ? 1 : x < y ? -1 : 0;
  }
  if (typeof a === "string" && typeof b === "string") return a > b ? 1 : a < b ? -1 : 0;
  return null;
}

function deepEqual(a: unknown, b: unknown): boolean {
  if (typeof a === "boolean" || typeof b === "boolean") {
    if (typeof a === "boolean" && typeof b === "boolean") return a === b;
    const other = typeof a === "boolean" ? b : a;
    const flag = typeof a === "boolean" ? a : (b as boolean);
    return isPlainNumber(other) && other === (flag ? 1 : 0);
  }
  if (isNum(a) || isNum(b)) return isNum(a) && isNum(b) && a.v === b.v;
  if (Array.isArray(a) || Array.isArray(b)) {
    return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((x, i) => deepEqual(x, b[i]));
  }
  if (isDict(a) || isDict(b)) {
    if (!isDict(a) || !isDict(b)) return false;
    const ka = Object.keys(a);
    if (ka.length !== Object.keys(b).length) return false;
    return ka.every((k) => k in b && deepEqual(a[k], b[k]));
  }
  return a === b;
}

function eq(a: unknown, b: unknown): boolean {
  if (Array.isArray(a) || Array.isArray(b)) {
    if (Array.isArray(a) && Array.isArray(b)) {
      const sa = a.map(pyStr).sort();
      const sb = b.map(pyStr).sort();
      return sa.length === sb.length && sa.every((x, i) => x === sb[i]);
    }
    return false;
  }
  if (typeof a === "boolean" || typeof b === "boolean") return deepEqual(a, b);
  const c = cmp(a, b);
  if (c !== null) return c === 0;
  return deepEqual(a, b);
}

function codePointLength(s: string): number {
  let n = 0;
  for (const _ of s) n++;
  return n;
}

function validDate(value: string): boolean {
  if (!DATE_RE.test(value)) return false;
  const [y, m, d] = value.split("-").map(Number) as [number, number, number];
  if (y < 1 || m < 1 || m > 12 || d < 1) return false;
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d;
}

export function conditionFields(cond: Dict): string[] {
  if ("all" in cond) return (cond.all as Dict[]).flatMap(conditionFields);
  if ("any" in cond) return (cond.any as Dict[]).flatMap(conditionFields);
  return "field" in cond ? [cond.field as string] : [];
}

// ------------------------------------------------------------------ evaluation

export interface LogicError {
  field: string;
  code: string;
}

export interface LineItem {
  block: string;
  amount: number;
  option?: string;
  quantity?: number;
  unit_price?: number;
}

export interface LogicResult {
  visible: string[];
  required: string[];
  variables: Record<string, unknown>;
  path: string[];
  ended: boolean;
  nextPage: Record<string, string | null>;
  errors: LogicError[];
  amount: number;
  lineItems: LineItem[];
  cleanAnswers: Record<string, unknown>;
}

type VarValue = bigint | unknown;

export class Evaluator {
  private pages: Dict[];
  private blocks = new Map<string, Dict>();
  private blockPage = new Map<string, string>();
  private pageIndex = new Map<string, number>();
  private variablesDef: Dict[];
  private rules: Dict[];
  private errors: LogicError[] = [];

  constructor(schema: Dict) {
    this.pages = (schema.pages as Dict[]) ?? [];
    this.pages.forEach((page, i) => {
      this.pageIndex.set(page.id, i);
      for (const b of (page.blocks as Dict[]) ?? []) {
        this.blocks.set(b.id, b);
        this.blockPage.set(b.id, page.id);
      }
    });
    this.variablesDef = (schema.variables as Dict[]) ?? [];
    this.rules = (schema.rules as Dict[]) ?? [];
  }

  private fieldValue(fid: string, answers: Dict, variables: Map<string, VarValue>): unknown {
    if (variables.has(fid)) {
      const v = variables.get(fid);
      if (typeof v === "bigint") return new Num(v);
      if (isPlainNumber(v) && Number.isInteger(v)) return new Num(BigInt(v));
      return v;
    }
    const block = this.blocks.get(fid);
    const raw = answers[fid];
    if (block === undefined) return raw;
    if (raw === null || raw === undefined) return null;
    const t = block.type as string;
    if (["number", "rating", "linear_scale", "nps", "payment_open"].includes(t)) {
      return numericLike(raw) ? new Num(toFixed(raw)) : null;
    }
    if (t === "yes_no") return typeof raw === "boolean" ? raw : null;
    return raw;
  }

  evalExpr(expr: Dict, answers: Dict, variables: Map<string, VarValue>): unknown {
    if ("num" in expr) return new Num(toFixed(expr.num));
    if ("str" in expr) return expr.str;
    if ("bool" in expr) return Boolean(expr.bool);
    if ("ref" in expr) return this.fieldValue(expr.ref, answers, variables);
    const op = expr.op as string;
    const args = (expr.args as Dict[]) ?? [];
    if (op === "if") {
      const cond = args.length ? this.evalExpr(args[0]!, answers, variables) : false;
      const branch = truthy(cond) ? args[1] : args.length > 2 ? args[2] : undefined;
      return branch !== undefined ? this.evalExpr(branch, answers, variables) : new Num(0n);
    }
    if (op === "and" || op === "or") {
      const vals = args.map((a) => truthy(this.evalExpr(a, answers, variables)));
      return op === "and" ? vals.every(Boolean) : vals.some(Boolean);
    }
    if (op === "not") return args.length ? !truthy(this.evalExpr(args[0]!, answers, variables)) : true;
    if (op === "count_selected") {
      const v = args.length ? this.evalExpr(args[0]!, answers, variables) : null;
      if (Array.isArray(v)) return new Num(BigInt(v.length) * SCALE);
      if (isDict(v)) return new Num(BigInt(Object.values(v).filter((q) => asNum(q) > 0n).length) * SCALE);
      return new Num(isEmpty(v) ? 0n : SCALE);
    }
    const vals = args.map((a) => this.evalExpr(a, answers, variables));
    if (["eq", "neq", "gt", "gte", "lt", "lte"].includes(op)) {
      if (vals.length < 2) return false;
      const [a, b] = vals;
      if (op === "eq") return eq(a, b);
      if (op === "neq") return !eq(a, b);
      const c = cmp(a, b);
      if (c === null) return false;
      return { gt: c > 0, gte: c >= 0, lt: c < 0, lte: c <= 0 }[op as "gt"];
    }
    const nums = vals.map((v) =>
      isDict(v) ? Object.values(v).reduce<bigint>((s, q) => s + asNum(q), 0n) : asNum(v),
    );
    const sum = (xs: bigint[]): bigint => xs.reduce((s, x) => s + x, 0n);
    switch (op) {
      case "add":
      case "sum":
        return new Num(sum(nums));
      case "sub":
        return new Num(nums.length ? nums[0]! - sum(nums.slice(1)) : 0n);
      case "mul": {
        let acc = SCALE;
        for (const n of nums) acc = fixedMul(acc, n);
        return new Num(nums.length ? acc : 0n);
      }
      case "div":
        if (nums.length < 2) return new Num(0n);
        if (nums[1] === 0n) {
          this.errors.push({ field: "_formula", code: "division_by_zero" });
          return new Num(0n);
        }
        return new Num(fixedDiv(nums[0]!, nums[1]!));
      case "round": {
        const digits = nums.length > 1 ? toCurrencyUnit(nums[1]!) : 0n;
        return new Num(fixedRound(nums.length ? nums[0]! : 0n, digits));
      }
      case "min":
        return new Num(nums.length ? nums.reduce((m, x) => (x < m ? x : m)) : 0n);
      case "max":
        return new Num(nums.length ? nums.reduce((m, x) => (x > m ? x : m)) : 0n);
      default:
        return null;
    }
  }

  evalCondition(cond: Dict, answers: Dict, variables: Map<string, VarValue>): boolean {
    if ("all" in cond) return (cond.all as Dict[]).every((c) => this.evalCondition(c, answers, variables));
    if ("any" in cond) return (cond.any as Dict[]).some((c) => this.evalCondition(c, answers, variables));
    const value = this.fieldValue(cond.field, answers, variables);
    const op = cond.op as string;
    const expected = cond.value;
    switch (op) {
      case "empty":
        return isEmpty(value);
      case "not_empty":
        return !isEmpty(value);
      case "eq":
        return eq(value, expected);
      case "neq":
        return !eq(value, expected);
      case "contains":
      case "not_contains": {
        let hit: boolean;
        if (Array.isArray(value)) hit = value.some((x) => pyStr(x) === pyStr(expected));
        else if (isDict(value)) hit = asNum(value[pyStr(expected)]) > 0n;
        else if (typeof value === "string" && typeof expected === "string")
          hit = value.toLowerCase().includes(expected.toLowerCase());
        else hit = false;
        return op === "contains" ? hit : !hit;
      }
      case "in":
      case "not_in": {
        const options: unknown[] = Array.isArray(expected) ? expected : [expected];
        const hit = Array.isArray(value)
          ? value.some((v) => options.some((o) => eq(v, o)))
          : value !== null && value !== undefined && options.some((o) => eq(value, o));
        return op === "in" ? hit : !hit;
      }
      case "between": {
        if (!Array.isArray(expected) || expected.length !== 2) return false;
        const lo = cmp(value, expected[0]);
        const hi = cmp(value, expected[1]);
        return lo !== null && hi !== null && lo >= 0 && hi <= 0;
      }
      default: {
        const c = cmp(value, expected);
        if (c === null) return false;
        if (op === "gt") return c > 0;
        if (op === "gte") return c >= 0;
        if (op === "lt") return c < 0;
        if (op === "lte") return c <= 0;
        return false;
      }
    }
  }

  private rulePage(rule: Dict): string | null {
    if (rule.page) return rule.page as string;
    const idx = conditionFields(rule.when)
      .filter((f) => this.blockPage.has(f))
      .map((f) => this.pageIndex.get(this.blockPage.get(f)!)!);
    if (idx.length) return this.pages[Math.max(...idx)]!.id as string;
    return this.pages.length ? (this.pages[0]!.id as string) : null;
  }

  private store(v: unknown): VarValue {
    return isNum(v) ? v.v : v;
  }

  run(answersIn: Dict, hidden?: Record<string, string> | null): LogicResult {
    this.errors = [];
    const answers: Dict = { ...answersIn };
    for (const [bid, b] of this.blocks) {
      if (b.type === "hidden" && hidden) {
        const param = (b.param as string) || bid;
        if (param in hidden) answers[bid] = String(hidden[param]).slice(0, 500);
      }
    }

    const variables = new Map<string, VarValue>();
    for (const v of this.variablesDef) {
      if (v.formula !== undefined && v.formula !== null) {
        variables.set(v.id, this.store(this.evalExpr(v.formula, answers, variables)));
      } else {
        const init = v.initial;
        variables.set(v.id, isPlainNumber(init) ? toFixed(init) : init ?? null);
      }
    }

    const shownByRule = new Set<string>();
    for (const r of this.rules) for (const a of r.then as Dict[]) if (a.action === "show") shownByRule.add(a.target);
    const visible = new Set([...this.blocks.keys()].filter((b) => !shownByRule.has(b)));
    const required = new Set(
      [...this.blocks.entries()].filter(([, b]) => b.required && INPUT_TYPES.has(b.type)).map(([id]) => id),
    );
    const jumps = new Map<string, string | null>();
    const endedAt = new Set<string>();

    for (const rule of this.rules) {
      if (!this.evalCondition(rule.when, answers, variables)) continue;
      const page = this.rulePage(rule);
      for (const act of rule.then as Dict[]) {
        const kind = act.action as string;
        const target = act.target as string | undefined;
        if (kind === "show" && target) visible.add(target);
        else if (kind === "hide" && target) visible.delete(target);
        else if (kind === "require" && target) required.add(target);
        else if (kind === "unrequire" && target) required.delete(target);
        else if (kind === "set_variable" && target)
          variables.set(target, this.store(this.evalExpr(act.value ?? { num: 0 }, answers, variables)));
        else if (kind === "jump_to_page" && target && page && !jumps.has(page)) jumps.set(page, target);
        else if (kind === "end_form" && page && !jumps.has(page)) {
          jumps.set(page, null);
          endedAt.add(page);
        }
      }
    }

    const nextPage: Record<string, string | null> = {};
    this.pages.forEach((page, i) => {
      const pid = page.id as string;
      if (jumps.has(pid)) {
        const target = jumps.get(pid)!;
        nextPage[pid] = target !== null && this.pageIndex.has(target) ? target : null;
      } else {
        nextPage[pid] = i + 1 < this.pages.length ? (this.pages[i + 1]!.id as string) : null;
      }
    });
    const path: string[] = [];
    let ended = false;
    let current: string | null = this.pages.length ? (this.pages[0]!.id as string) : null;
    const seen = new Set<string>();
    while (current !== null && !seen.has(current)) {
      seen.add(current);
      path.push(current);
      if (endedAt.has(current)) {
        ended = true;
        break;
      }
      current = nextPage[current] ?? null;
    }
    const onPath = new Set(path);
    for (const b of [...visible]) if (!onPath.has(this.blockPage.get(b) ?? "")) visible.delete(b);

    const clean: Dict = {};
    for (const bid of this.blocks.keys()) {
      if (visible.has(bid) && bid in answers && INPUT_TYPES.has(this.blocks.get(bid)!.type)) clean[bid] = answers[bid];
    }
    for (const r of [...required]) if (!visible.has(r)) required.delete(r);

    this.validate(clean, visible, required);
    const [amountFixed, items] = this.amount(clean, visible, variables);

    const outVars: Record<string, unknown> = {};
    for (const [k, v] of variables) outVars[k] = typeof v === "bigint" ? fixedToJson(v) : v;
    const amount = toCurrencyUnit(amountFixed);
    return {
      visible: [...this.blocks.keys()].filter((b) => visible.has(b)),
      required: [...this.blocks.keys()].filter((b) => required.has(b)),
      variables: outVars,
      path,
      ended,
      nextPage,
      errors: this.errors,
      amount: Number(amount < 0n ? 0n : amount),
      lineItems: items,
      cleanAnswers: clean,
    };
  }

  private err(field: string, code: string): void {
    this.errors.push({ field, code });
  }

  private validate(answers: Dict, visible: Set<string>, required: Set<string>): void {
    for (const [bid, block] of this.blocks) {
      if (!visible.has(bid) || !INPUT_TYPES.has(block.type)) continue;
      const value = answers[bid];
      if (isEmpty(value) || (block.type === "consent" && value !== true)) {
        if (required.has(bid)) this.err(bid, "required");
        continue;
      }
      this.validateValue(bid, block, value);
    }
  }

  private numericBounds(block: Dict): [bigint | null, bigint | null] {
    const t = block.type as string;
    const rules: Dict = block.validation ?? {};
    const scale: Dict = block.scale ?? {};
    if (t === "nps") return [0n, 10n * SCALE];
    if (t === "rating") return [SCALE, toFixed(scale.max ?? 5)];
    if (t === "linear_scale") return [toFixed(scale.min ?? 1), toFixed(scale.max ?? 5)];
    if (t === "payment_open") {
      const hi = block.maxAmount;
      return [toFixed(block.minAmount ?? 1), hi !== undefined && hi !== null ? toFixed(hi) : toFixed(10_000_000)];
    }
    return ["min" in rules ? toFixed(rules.min) : null, "max" in rules ? toFixed(rules.max) : null];
  }

  private validateValue(bid: string, block: Dict, value: any): void {
    const t = block.type as string;
    const rules: Dict = block.validation ?? {};
    const optionIds = new Set(((block.options as Dict[]) ?? []).map((o) => o.id as string));
    if (["short_text", "long_text", "hidden", "signature"].includes(t)) {
      if (typeof value !== "string") return this.err(bid, "invalid_type");
      let maxLen = rules.maxLength ?? (t === "short_text" || t === "hidden" ? 500 : 10000);
      if (t === "signature") maxLen = 200_000;
      if (codePointLength(value) > maxLen) return this.err(bid, "too_long");
      if (codePointLength(value.trim()) < (rules.minLength ?? 0)) return this.err(bid, "too_short");
    } else if (t === "email") {
      if (typeof value !== "string" || value.length > 254 || !EMAIL_RE.test(value.trim()))
        return this.err(bid, "invalid_email");
    } else if (t === "url") {
      if (typeof value !== "string" || value.length > 2048 || !URL_RE.test(value.trim()))
        return this.err(bid, "invalid_url");
    } else if (t === "phone") {
      if (typeof value !== "string" || !E164_RE.test(value)) return this.err(bid, "invalid_phone");
      if (value.startsWith("+237") && !CM_MOBILE_RE.test(value)) return this.err(bid, "invalid_phone");
    } else if (["number", "rating", "linear_scale", "nps", "payment_open"].includes(t)) {
      if (!numericLike(value)) return this.err(bid, "invalid_number");
      const n = toFixed(value);
      const [lo, hi] = this.numericBounds(block);
      const integer = rules.integer || ["rating", "linear_scale", "nps", "payment_open"].includes(t);
      if (integer && n % SCALE !== 0n) return this.err(bid, "invalid_number");
      if (lo !== null && n < lo) return this.err(bid, "below_min");
      if (hi !== null && n > hi) return this.err(bid, "above_max");
    } else if (CHOICE_TYPES.has(t)) {
      if (typeof value !== "string" || !optionIds.has(value)) return this.err(bid, "invalid_choice");
    } else if (t === "multi_choice" || t === "ranking") {
      if (!Array.isArray(value) || value.some((v) => typeof v !== "string" || !optionIds.has(v)))
        return this.err(bid, "invalid_choice");
      if (new Set(value).size !== value.length) return this.err(bid, "invalid_choice");
      if (t === "ranking" && (value.length !== optionIds.size || !value.every((v) => optionIds.has(v))))
        return this.err(bid, "invalid_choice");
      if (value.length < (rules.minSelected ?? 0)) return this.err(bid, "too_few");
      if ("maxSelected" in rules && value.length > rules.maxSelected) return this.err(bid, "too_many");
    } else if (t === "yes_no") {
      if (typeof value !== "boolean") return this.err(bid, "invalid_choice");
    } else if (t === "consent") {
      if (value !== true) return this.err(bid, "required");
    } else if (t === "choice_grid") {
      const rows = new Set(((block.rows as Dict[]) ?? []).map((r) => r.id));
      const cols = new Set(((block.columns as Dict[]) ?? []).map((c) => c.id));
      if (!isDict(value) || Object.entries(value).some(([k, v]) => !rows.has(k) || typeof v !== "string" || !cols.has(v)))
        return this.err(bid, "invalid_choice");
    } else if (t === "date") {
      if (typeof value !== "string" || !validDate(value)) return this.err(bid, "invalid_date");
      if (rules.minDate && value < rules.minDate) return this.err(bid, "below_min");
      if (rules.maxDate && value > rules.maxDate) return this.err(bid, "above_max");
    } else if (t === "time") {
      if (typeof value !== "string" || !TIME_RE.test(value)) return this.err(bid, "invalid_time");
    } else if (t === "date_range") {
      if (
        !isDict(value) ||
        !validDate(pyStr(value.start ?? "")) ||
        !validDate(pyStr(value.end ?? "")) ||
        value.start > value.end
      )
        return this.err(bid, "invalid_date");
    } else if (t === "file_upload") {
      if (!Array.isArray(value) || value.some((v) => typeof v !== "string" || codePointLength(v) > 200))
        return this.err(bid, "invalid_file");
      if (value.length > (rules.maxFiles ?? 1)) return this.err(bid, "too_many");
    } else if (t === "product_choice" || t === "ticket_choice") {
      if (!isDict(value)) return this.err(bid, "invalid_choice");
      const opts = new Map(((block.options as Dict[]) ?? []).map((o) => [o.id as string, o]));
      for (const [k, q] of Object.entries(value)) {
        if (!opts.has(k) || typeof q !== "number" || !Number.isInteger(q) || q < 0)
          return this.err(bid, "invalid_choice");
        if (q > (opts.get(k)!.maxQuantity ?? 10)) return this.err(bid, "too_many");
      }
    }
  }

  private amount(answers: Dict, visible: Set<string>, variables: Map<string, VarValue>): [bigint, LineItem[]] {
    let total = 0n;
    const items: LineItem[] = [];
    for (const [bid, block] of this.blocks) {
      const t = block.type as string;
      if (!PAYMENT_TYPES.has(t) || !visible.has(bid)) continue;
      if (t === "payment_fixed") {
        const amt = toFixed(block.amount ?? 0);
        total += amt;
        items.push({ block: bid, amount: Number(toCurrencyUnit(amt)) });
      } else if (t === "payment_computed") {
        const v = variables.get(block.variable ?? "");
        let amt = typeof v === "bigint" ? v : 0n;
        if (amt < 0n) amt = 0n;
        total += amt;
        items.push({ block: bid, amount: Number(toCurrencyUnit(amt)) });
      } else if (t === "payment_open") {
        const v = answers[bid];
        if (numericLike(v)) {
          let amt = toFixed(v);
          if (amt < 0n) amt = 0n;
          total += amt;
          items.push({ block: bid, amount: Number(toCurrencyUnit(amt)) });
        }
      } else {
        const qty = answers[bid];
        if (!isDict(qty)) continue;
        for (const opt of (block.options as Dict[]) ?? []) {
          const q = qty[opt.id];
          if (typeof q === "number" && Number.isInteger(q) && q > 0) {
            const amt = toFixed(opt.price ?? 0) * BigInt(q);
            total += amt;
            items.push({
              block: bid, option: opt.id, quantity: q, unit_price: Number(opt.price ?? 0),
              amount: Number(toCurrencyUnit(amt)),
            });
          }
        }
      }
    }
    return [total, items];
  }
}

export function evaluate(schema: Dict, answers: Dict, hidden?: Record<string, string> | null): LogicResult {
  return new Evaluator(schema).run(answers, hidden);
}
