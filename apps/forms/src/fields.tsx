/** Field renderers for every V1 block type. Mobile first, 44 px touch targets, labels tied to inputs. */
import type { ComponentChildren, JSX } from "preact";
import { useRef, useState } from "preact/hooks";
import { api } from "./api";
import { type Locale, money, t, tx } from "./i18n";

export interface FieldCtx {
  locale: Locale;
  fallback: Locale;
  code: string;
  currency: string;
  variables: Record<string, unknown>;
  remaining: Record<string, Record<string, number | null>>;
}

interface Props {
  block: Record<string, any>;
  value: any;
  required: boolean;
  error?: string;
  ctx: FieldCtx;
  onChange: (v: unknown) => void;
}

const DISPLAY = new Set(["heading", "rich_text", "image", "divider", "computed_display", "payment_fixed", "payment_computed"]);

export function normalizePhone(raw: string): string {
  const v = raw.replace(/[\s.()-]/g, "");
  if (/^[62]\d{8}$/.test(v)) return `+237${v}`;
  if (/^00\d+$/.test(v)) return `+${v.slice(2)}`;
  if (/^237[62]\d{8}$/.test(v)) return `+${v}`;
  return v;
}

function Wrap(p: { block: Record<string, any>; required: boolean; error?: string; ctx: FieldCtx; group?: boolean; children: ComponentChildren }) {
  const { block, ctx } = p;
  const id = `f-${block.id}`;
  const label = tx(block.label, ctx.locale, ctx.fallback);
  const help = tx(block.help, ctx.locale, ctx.fallback);
  const head = (
    <>
      {label}
      {p.required ? <span class="req"> ({t("field.required")})</span> : null}
    </>
  );
  return (
    <div class={`field${p.error ? " bad" : ""}`} id={`w-${block.id}`}>
      {p.group ? (
        <fieldset aria-describedby={p.error ? `${id}-e` : help ? `${id}-h` : undefined}>
          <legend>{head}</legend>
          {help ? <p class="help" id={`${id}-h`}>{help}</p> : null}
          {p.children}
        </fieldset>
      ) : (
        <>
          <label for={id}>{head}</label>
          {help ? <p class="help" id={`${id}-h`}>{help}</p> : null}
          {p.children}
        </>
      )}
      {p.error ? <p class="err" id={`${id}-e`} role="alert">{t(`err.${p.error}`)}</p> : null}
    </div>
  );
}

function Signature({ id, value, onChange }: { id: string; value: string; onChange: (v: string) => void }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const pos = (e: PointerEvent) => {
    const r = ref.current!.getBoundingClientRect();
    return [((e.clientX - r.left) * 600) / r.width, ((e.clientY - r.top) * 200) / r.height] as const;
  };
  const down = (e: PointerEvent) => {
    drawing.current = true;
    const c = ref.current!.getContext("2d")!;
    c.lineWidth = 3;
    c.lineCap = "round";
    c.beginPath();
    c.moveTo(...pos(e));
    ref.current!.setPointerCapture(e.pointerId);
  };
  const move = (e: PointerEvent) => {
    if (!drawing.current) return;
    const c = ref.current!.getContext("2d")!;
    c.lineTo(...pos(e));
    c.stroke();
  };
  const up = () => {
    if (!drawing.current) return;
    drawing.current = false;
    onChange(ref.current!.toDataURL("image/png"));
  };
  return (
    <div>
      <canvas ref={ref} id={id} class="sign" width={600} height={200} role="img" aria-label={t("sign.hint")}
        onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerLeave={up} />
      <p class="help">{t("sign.hint")}</p>
      {value ? (
        <button type="button" class="link" onClick={() => {
          ref.current!.getContext("2d")!.clearRect(0, 0, 600, 200);
          onChange("");
        }}>{t("sign.clear")}</button>
      ) : null}
    </div>
  );
}

function Files({ id, value, max, ctx, onChange }: { id: string; value: string[]; max: number; ctx: FieldCtx; onChange: (v: string[]) => void }) {
  const [state, setState] = useState<"" | "busy" | "failed">("");
  const pick = async (e: JSX.TargetedEvent<HTMLInputElement>) => {
    const file = e.currentTarget.files?.[0];
    e.currentTarget.value = "";
    if (!file) return;
    setState("busy");
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await api<{ key: string }>(`/forms/${ctx.code}/files`, { method: "POST", body });
      onChange([...value, res.key]);
      setState("");
    } catch {
      setState("failed");
    }
  };
  return (
    <div>
      {value.map((k, i) => (
        <div class="file" key={k}>
          <span>{`${i + 1}. ${k.slice(-12)}`}</span>
          <button type="button" class="link" onClick={() => onChange(value.filter((x) => x !== k))}>{t("file.remove")}</button>
        </div>
      ))}
      {value.length < max ? <input id={id} type="file" accept="image/*,application/pdf" onChange={pick} /> : null}
      {state === "busy" ? <p class="help" role="status">{t("file.uploading")}</p> : null}
      {state === "failed" ? <p class="err" role="alert">{t("file.failed")}</p> : null}
    </div>
  );
}

export function Field(p: Props) {
  const { block, value, ctx, onChange } = p;
  const type = block.type as string;
  const id = `f-${block.id}`;
  const L = (x: any) => tx(x, ctx.locale, ctx.fallback);
  const described = p.error ? `${id}-e` : block.help ? `${id}-h` : undefined;
  const common = { id, "aria-invalid": p.error ? true : undefined, "aria-describedby": described, "aria-required": p.required || undefined };
  const options: Record<string, any>[] = block.options ?? [];

  if (type === "heading") return <h2>{L(block.content) || L(block.label)}</h2>;
  if (type === "rich_text") return <div class="rich" dangerouslySetInnerHTML={{ __html: L(block.content) }} />; // sanitized by the server (nh3)
  if (type === "divider") return <hr />;
  if (type === "image") return block.imageKey ? <img src={block.imageKey} alt={L(block.alt)} loading="lazy" /> : null;
  if (type === "hidden") return null;
  if (type === "computed_display" || type === "payment_computed" || type === "payment_fixed") {
    const raw = type === "payment_fixed" ? block.amount : ctx.variables[block.variable];
    const n = typeof raw === "number" ? Math.round(raw) : 0;
    return (
      <div class="total">
        <span>{L(block.label)}</span>
        <strong>{money(n, ctx.currency, ctx.locale)}</strong>
      </div>
    );
  }
  if (DISPLAY.has(type)) return null;

  let input: ComponentChildren;
  let group = false;
  const text = (kind: string, mode?: string, extra: Record<string, unknown> = {}) => (
    <input {...common} type={kind} inputMode={mode as any} value={value ?? ""} placeholder={L(block.placeholder)}
      onInput={(e) => onChange(e.currentTarget.value)} {...extra} />
  );

  switch (type) {
    case "short_text":
      input = text("text", undefined, { maxLength: block.validation?.maxLength ?? 500 });
      break;
    case "long_text":
      input = <textarea {...common} rows={4} value={value ?? ""} maxLength={block.validation?.maxLength ?? 10000}
        onInput={(e) => onChange(e.currentTarget.value)} />;
      break;
    case "email":
      input = text("email", "email", { autocomplete: "email" });
      break;
    case "url":
      input = text("url", "url");
      break;
    case "phone":
      input = <input {...common} type="tel" inputMode="tel" autocomplete="tel" value={value ?? ""} placeholder="6 77 12 34 56"
        onInput={(e) => onChange(e.currentTarget.value)} onBlur={(e) => onChange(normalizePhone(e.currentTarget.value))} />;
      break;
    case "number":
    case "payment_open":
      input = <input {...common} type="text" inputMode="decimal" value={value ?? ""}
        onInput={(e) => {
          const raw = e.currentTarget.value.replace(",", ".").trim();
          onChange(raw === "" ? null : /^-?\d+(\.\d+)?$/.test(raw) ? Number(raw) : raw);
        }} />;
      break;
    case "date":
      input = text("date", undefined, { min: block.validation?.minDate, max: block.validation?.maxDate });
      break;
    case "time":
      input = text("time");
      break;
    case "date_range": {
      const v = value ?? {};
      group = true;
      input = (
        <div class="row">
          <label>{t("date.start")}<input type="date" value={v.start ?? ""} onInput={(e) => onChange({ ...v, start: e.currentTarget.value })} /></label>
          <label>{t("date.end")}<input type="date" value={v.end ?? ""} onInput={(e) => onChange({ ...v, end: e.currentTarget.value })} /></label>
        </div>
      );
      break;
    }
    case "dropdown":
      input = (
        <select {...common} value={value ?? ""} onChange={(e) => onChange(e.currentTarget.value || null)}>
          <option value="">{t("choice.select")}</option>
          {options.map((o) => <option key={o.id} value={o.id}>{L(o.label)}</option>)}
        </select>
      );
      break;
    case "single_choice":
    case "yes_no": {
      group = true;
      const opts = type === "yes_no" ? [{ id: true, text: t("choice.yes") }, { id: false, text: t("choice.no") }]
        : options.map((o) => ({ id: o.id, text: L(o.label) }));
      input = opts.map((o) => (
        <label class="opt" key={String(o.id)}>
          <input type="radio" name={id} checked={value === o.id} onChange={() => onChange(o.id)} />
          <span>{o.text}</span>
        </label>
      ));
      break;
    }
    case "multi_choice": {
      group = true;
      const sel: string[] = Array.isArray(value) ? value : [];
      input = options.map((o) => (
        <label class="opt" key={o.id}>
          <input type="checkbox" checked={sel.includes(o.id)}
            onChange={(e) => onChange(e.currentTarget.checked ? [...sel, o.id] : sel.filter((x) => x !== o.id))} />
          <span>{L(o.label)}</span>
        </label>
      ));
      break;
    }
    case "consent":
      return (
        <div class={`field${p.error ? " bad" : ""}`} id={`w-${block.id}`}>
          <label class="opt">
            <input {...common} type="checkbox" checked={value === true} onChange={(e) => onChange(e.currentTarget.checked)} />
            <span>{L(block.label) || L(block.content)}</span>
          </label>
          {p.error ? <p class="err" id={`${id}-e`} role="alert">{t(`err.${p.error}`)}</p> : null}
        </div>
      );
    case "rating":
    case "linear_scale":
    case "nps": {
      group = true;
      const min = type === "nps" ? 0 : type === "rating" ? 1 : block.scale?.min ?? 1;
      const max = type === "nps" ? 10 : block.scale?.max ?? 5;
      const nums = Array.from({ length: max - min + 1 }, (_, i) => min + i);
      input = (
        <>
          <div class="scale">
            {nums.map((n) => (
              <label key={n} class={value === n ? "on" : ""}>
                <input type="radio" name={id} checked={value === n} onChange={() => onChange(n)} />
                <span>{n}</span>
              </label>
            ))}
          </div>
          {block.scale?.minLabel || block.scale?.maxLabel ? (
            <div class="ends"><span>{L(block.scale?.minLabel)}</span><span>{L(block.scale?.maxLabel)}</span></div>
          ) : null}
        </>
      );
      break;
    }
    case "ranking": {
      group = true;
      const order: string[] = Array.isArray(value) && value.length === options.length ? value : options.map((o) => o.id);
      const swap = (i: number, j: number) => {
        const next = [...order];
        [next[i], next[j]] = [next[j]!, next[i]!];
        onChange(next);
      };
      input = (
        <ol class="rank">
          {order.map((oid, i) => {
            const label = L(options.find((o) => o.id === oid)?.label);
            return (
              <li key={oid}>
                <span>{label}</span>
                <button type="button" disabled={i === 0} aria-label={t("rank.up", { label })} onClick={() => swap(i, i - 1)}>&#8593;</button>
                <button type="button" disabled={i === order.length - 1} aria-label={t("rank.down", { label })} onClick={() => swap(i, i + 1)}>&#8595;</button>
              </li>
            );
          })}
        </ol>
      );
      break;
    }
    case "choice_grid": {
      group = true;
      const v: Record<string, string> = value ?? {};
      input = (
        <div class="grid">
          <table>
            <thead><tr><td />{(block.columns ?? []).map((c: any) => <th scope="col" key={c.id}>{L(c.label)}</th>)}</tr></thead>
            <tbody>
              {(block.rows ?? []).map((r: any) => (
                <tr key={r.id}>
                  <th scope="row">{L(r.label)}</th>
                  {(block.columns ?? []).map((c: any) => (
                    <td key={c.id}>
                      <input type="radio" name={`${id}-${r.id}`} aria-label={`${L(r.label)}: ${L(c.label)}`}
                        checked={v[r.id] === c.id} onChange={() => onChange({ ...v, [r.id]: c.id })} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      break;
    }
    case "product_choice":
    case "ticket_choice": {
      group = true;
      const q: Record<string, number> = value ?? {};
      const left: Record<string, number | null> = ctx.remaining[block.id] ?? {};
      input = options.map((o) => {
        const label = L(o.label);
        const n = q[o.id] ?? 0;
        const rest = left[o.id];
        const cap = Math.min(o.maxQuantity ?? 10, rest ?? Infinity);
        const set = (x: number) => {
          const next: Record<string, number> = { ...q, [o.id]: x };
          if (x <= 0) delete next[o.id];
          onChange(next);
        };
        return (
          <div class="qty" key={o.id}>
            <div>
              <strong>{label}</strong>
              <span>{money(o.price ?? 0, ctx.currency, ctx.locale)}</span>
              {rest === 0 ? <em>{t("qty.soldout")}</em> : rest != null && rest <= 20 ? <em>{t("qty.left", { count: rest })}</em> : null}
            </div>
            <div class="step">
              <button type="button" disabled={n <= 0} aria-label={t("qty.less", { label })} onClick={() => set(n - 1)}>&minus;</button>
              <output aria-live="polite">{n}</output>
              <button type="button" disabled={n >= cap} aria-label={t("qty.more", { label })} onClick={() => set(n + 1)}>+</button>
            </div>
          </div>
        );
      });
      break;
    }
    case "file_upload":
      input = <Files id={id} value={Array.isArray(value) ? value : []} max={block.validation?.maxFiles ?? 1} ctx={ctx} onChange={onChange} />;
      break;
    case "signature":
      input = <Signature id={id} value={value ?? ""} onChange={onChange} />;
      break;
    default:
      return null;
  }
  return <Wrap block={block} required={p.required} error={p.error} ctx={ctx} group={group}>{input}</Wrap>;
}
