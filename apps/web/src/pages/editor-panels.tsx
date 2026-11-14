import { formatFormula, FormulaError, parseFormula } from "@arha/logic-ts";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../lib/api";
import { date, type Locale, t } from "../lib/i18n";
import { Badge, Button, Card, Field, Input, Notice, Select, Textarea } from "../ui";
import { allIds, newId, type Schema } from "./editor";

interface PanelProps { schema: Schema; setSchema: (s: Schema) => void; lang: Locale; disabled: boolean }

const OPS = ["eq", "neq", "contains", "not_contains", "gt", "gte", "lt", "lte", "empty", "not_empty"];
const ACTIONS = ["show", "hide", "require", "unrequire", "jump_to_page", "end_form"];

const useUpdate = (schema: Schema, setSchema: (s: Schema) => void) => (fn: (draft: Schema) => void) => {
  const next = structuredClone(schema);
  fn(next);
  setSchema(next);
};

function coerce(raw: string): unknown {
  if (raw === "true") return true;
  if (raw === "false") return false;
  return /^-?\d+(\.\d+)?$/.test(raw) ? Number(raw) : raw;
}

export function LogicPanel({ schema, setSchema, lang, disabled }: PanelProps) {
  const update = useUpdate(schema, setSchema);
  const fields: { id: string; label: string; options?: any[]; type: string }[] = schema.pages.flatMap((p: any) => p.blocks)
    .filter((b: any) => !["heading", "rich_text", "divider", "computed_display"].includes(b.type))
    .map((b: any) => ({ id: b.id, label: b.label?.[lang] || b.id, options: b.options, type: b.type }));
  const blocks = schema.pages.flatMap((p: any) => p.blocks);
  const refs = new Set<string>([...fields.map((f) => f.id), ...schema.variables.map((v: any) => v.id)]);

  /** Rules are edited as one group of conditions joined by ALL or ANY; deeper nesting stays valid in the schema. */
  const parts = (when: any): { mode: "all" | "any"; items: any[] } =>
    when.all ? { mode: "all", items: when.all } : when.any ? { mode: "any", items: when.any } : { mode: "all", items: [when] };

  return (
    <div className="grid gap-8">
      <section>
        <h2 className="mb-1 text-2xl">{t("logic.rules")}</h2>
        <p className="mb-4 text-sm text-grey">{t("logic.rules.hint")}</p>
        {schema.rules.map((rule: any, ri: number) => {
          const { mode, items } = parts(rule.when);
          const setItems = (next: any[], m = mode) => update((s) => { s.rules[ri].when = { [m]: next }; });
          return (
            <Card key={rule.id} className="mb-3">
              <div className="mb-3 flex items-center gap-2 text-sm">
                <span>{t("logic.when")}</span>
                <Select aria-label={t("logic.mode")} className="!min-h-9 !w-auto !py-1" value={mode} disabled={disabled} onChange={(e) => setItems(items, e.target.value as "all" | "any")}>
                  <option value="all">{t("logic.all")}</option><option value="any">{t("logic.any")}</option>
                </Select>
              </div>
              {items.map((c: any, ci: number) => {
                const field = fields.find((f) => f.id === c.field);
                const nested = !("field" in c);
                return nested ? <p key={ci} className="mb-2 text-sm text-grey">{t("logic.nested")}</p> : (
                  <div key={ci} className="mb-2 grid gap-2 sm:grid-cols-[1.4fr_1fr_1fr_auto]">
                    <Select aria-label={t("logic.field")} value={c.field} disabled={disabled} onChange={(e) => setItems(items.map((x, i) => (i === ci ? { ...x, field: e.target.value } : x)))}>
                      {fields.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
                      {schema.variables.map((v: any) => <option key={v.id} value={v.id}>{v.id}</option>)}
                    </Select>
                    <Select aria-label={t("logic.op")} value={c.op} disabled={disabled} onChange={(e) => setItems(items.map((x, i) => (i === ci ? { ...x, op: e.target.value } : x)))}>
                      {OPS.map((o) => <option key={o} value={o}>{t(`logic.op.${o}`)}</option>)}
                    </Select>
                    {["empty", "not_empty"].includes(c.op) ? <span /> : field?.options?.length ? (
                      <Select aria-label={t("logic.value")} value={String(c.value ?? "")} disabled={disabled} onChange={(e) => setItems(items.map((x, i) => (i === ci ? { ...x, value: e.target.value } : x)))}>
                        <option value="" />
                        {field.options.map((o: any) => <option key={o.id} value={o.id}>{o.label?.[lang] || o.id}</option>)}
                      </Select>
                    ) : field?.type === "yes_no" ? (
                      <Select aria-label={t("logic.value")} value={String(c.value ?? "")} disabled={disabled} onChange={(e) => setItems(items.map((x, i) => (i === ci ? { ...x, value: e.target.value === "true" } : x)))}>
                        <option value="true">{t("common.yes")}</option><option value="false">{t("common.no")}</option>
                      </Select>
                    ) : (
                      <Input aria-label={t("logic.value")} value={String(c.value ?? "")} disabled={disabled} onChange={(e) => setItems(items.map((x, i) => (i === ci ? { ...x, value: coerce(e.target.value) } : x)))} />
                    )}
                    {!disabled && items.length > 1 ? <Button variant="ghost" size="sm" aria-label={t("common.delete")} onClick={() => setItems(items.filter((_, i) => i !== ci))}>&times;</Button> : <span />}
                  </div>
                );
              })}
              {!disabled && fields.length ? <Button variant="ghost" size="sm" onClick={() => setItems([...items, { field: fields[0]!.id, op: "eq", value: "" }])}>{t("logic.condition.add")}</Button> : null}
              <p className="mb-2 mt-4 text-sm">{t("logic.then")}</p>
              {rule.then.map((a: any, ai: number) => (
                <div key={ai} className="mb-2 grid gap-2 sm:grid-cols-[1fr_1.4fr_auto]">
                  <Select aria-label={t("logic.action")} value={a.action} disabled={disabled || a.action === "set_variable"} onChange={(e) => update((s) => {
                    const action = e.target.value;
                    s.rules[ri].then[ai] = action === "end_form" ? { action } : { action, target: action === "jump_to_page" ? s.pages[s.pages.length - 1].id : blocks[0]?.id };
                  })}>
                    {[...ACTIONS, ...(a.action === "set_variable" ? ["set_variable"] : [])].map((x) => <option key={x} value={x}>{t(`logic.action.${x}`)}</option>)}
                  </Select>
                  {a.action === "end_form" ? <span /> : (
                    <Select aria-label={t("logic.target")} value={a.target ?? ""} disabled={disabled} onChange={(e) => update((s) => { s.rules[ri].then[ai].target = e.target.value; })}>
                      {a.action === "jump_to_page" ? schema.pages.map((p: any, i: number) => <option key={p.id} value={p.id}>{p.title?.[lang] || t("editor.page", { n: i + 1 })}</option>)
                        : a.action === "set_variable" ? schema.variables.map((v: any) => <option key={v.id} value={v.id}>{v.id}</option>)
                        : blocks.map((b: any) => <option key={b.id} value={b.id}>{b.label?.[lang] || b.content?.[lang] || b.id}</option>)}
                    </Select>
                  )}
                  {!disabled && rule.then.length > 1 ? <Button variant="ghost" size="sm" aria-label={t("common.delete")} onClick={() => update((s) => { s.rules[ri].then.splice(ai, 1); })}>&times;</Button> : <span />}
                </div>
              ))}
              {!disabled ? (
                <div className="mt-3 flex gap-2">
                  <Button variant="ghost" size="sm" onClick={() => update((s) => { s.rules[ri].then.push({ action: "show", target: blocks[0]?.id }); })}>{t("logic.action.add")}</Button>
                  <Button variant="danger" size="sm" onClick={() => update((s) => { s.rules.splice(ri, 1); })}>{t("logic.rule.delete")}</Button>
                </div>
              ) : null}
            </Card>
          );
        })}
        {!disabled ? (
          <Button variant="secondary" disabled={!fields.length} onClick={() => update((s) => {
            s.rules.push({ id: newId("r", allIds(s)), when: { all: [{ field: fields[0]!.id, op: "not_empty" }] }, then: [{ action: "show", target: blocks[blocks.length - 1].id }] });
          })}>{t("logic.rule.add")}</Button>
        ) : null}
      </section>

      <section>
        <h2 className="mb-1 text-2xl">{t("logic.variables")}</h2>
        <p className="mb-4 text-sm text-grey">{t("logic.variables.hint")}</p>
        {schema.variables.map((v: any, vi: number) => (
          <VariableRow key={v.id} variable={v} refs={refs} disabled={disabled}
            onFormula={(ast) => update((s) => { s.variables[vi].formula = ast; })}
            onDelete={() => update((s) => { s.variables.splice(vi, 1); })} />
        ))}
        {!disabled ? (
          <Button variant="secondary" onClick={() => update((s) => { s.variables.push({ id: newId("total", allIds(s)), type: "number", formula: { num: 0 } }); })}>{t("logic.variable.add")}</Button>
        ) : null}
      </section>
    </div>
  );
}

function VariableRow({ variable, refs, disabled, onFormula, onDelete }: { variable: any; refs: Set<string>; disabled: boolean; onFormula: (ast: unknown) => void; onDelete: () => void }) {
  const [text, setText] = useState(() => formatFormula(variable.formula));
  const [error, setError] = useState("");
  const commit = () => {
    try {
      onFormula(parseFormula(text, refs));
      setError("");
    } catch (e) {
      setError(e instanceof FormulaError ? t(`formula.${e.message.startsWith("expected") ? "unexpected_token" : e.message}`, { position: e.position + 1 }) : String(e));
    }
  };
  return (
    <Card className="mb-3">
      <div className="mb-2 flex items-center justify-between"><span className="font-mono text-sm">{variable.id}</span>
        {!disabled ? <Button variant="ghost" size="sm" onClick={onDelete}>{t("common.delete")}</Button> : null}</div>
      <Field label={t("logic.formula")} hint={t("logic.formula.hint")} error={error || undefined}>
        {(id) => <Input id={id} className="font-mono" value={text} disabled={disabled} onChange={(e) => setText(e.target.value)} onBlur={commit} spellCheck={false} />}
      </Field>
    </Card>
  );
}

/** WCAG contrast ratio between two colours. A theme under 4.5 to 1 is refused (F-EDI-05). */
function contrast(a: string, b: string): number {
  const lum = (hex: string) => {
    const [r, g, bl] = [1, 3, 5].map((i) => { const c = parseInt(hex.slice(i, i + 2), 16) / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }) as [number, number, number];
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  };
  const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m) as [number, number];
  return (x + 0.05) / (y + 0.05);
}

export function SettingsPanel({ schema, setSchema, lang, disabled, form, patchForm }: PanelProps & { form: any; patchForm: (b: Record<string, unknown>) => Promise<unknown> }) {
  const update = useUpdate(schema, setSchema);
  const st = schema.settings ?? {};
  const theme = st.theme ?? {};
  const [themeError, setThemeError] = useState("");
  const setTheme = (key: "primary" | "background", value: string) => {
    const next = { ...theme, [key]: value };
    const onPrimary = Math.max(contrast(next.primary ?? "#C9621B", "#ffffff"), contrast(next.primary ?? "#C9621B", "#2A1F17"));
    const body = contrast(next.background ?? "#FCF9F4", "#2A1F17");
    if (onPrimary < 4.5 || body < 4.5) return setThemeError(t("settings.theme.contrast"));
    setThemeError("");
    update((s) => { s.settings.theme = next; });
  };
  const text = (path: "closing" | "ending", value: string) => update((s) => { s.settings[path] = { ...(s.settings[path] ?? {}), message: { ...(s.settings[path]?.message ?? {}), [lang]: value } }; });
  const emailFields = schema.pages.flatMap((p: any) => p.blocks).filter((b: any) => b.type === "email");
  return (
    <div className="grid gap-6">
      <Card>
        <h2 className="mb-4 text-2xl">{t("settings.theme")}</h2>
        {themeError ? <Notice tone="error">{themeError}</Notice> : null}
        <div className="grid gap-4 sm:grid-cols-2">
          {(["primary", "background"] as const).map((k) => (
            <label key={k} className="flex items-center gap-3 text-sm font-medium">
              <input type="color" disabled={disabled} value={theme[k] ?? (k === "primary" ? "#C9621B" : "#FCF9F4")} onChange={(e) => setTheme(k, e.target.value)} className="h-11 w-14 rounded border border-sand bg-white" />
              {t(`settings.theme.${k}`)}
            </label>
          ))}
        </div>
      </Card>
      <Card>
        <h2 className="mb-4 text-2xl">{t("settings.closing")}</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("settings.closes_at")}>
            {(id) => <Input id={id} type="datetime-local" disabled={disabled} defaultValue={form.closes_at ? form.closes_at.slice(0, 16) : ""}
              onBlur={(e) => void patchForm({ closes_at: e.target.value ? new Date(e.target.value).toISOString() : null })} />}
          </Field>
          <Field label={t("settings.max_responses")}>
            {(id) => <Input id={id} inputMode="numeric" disabled={disabled} defaultValue={form.max_responses ?? ""}
              onBlur={(e) => void patchForm({ max_responses: e.target.value ? Number(e.target.value.replace(/\D/g, "")) : null })} />}
          </Field>
        </div>
        <Field label={t("settings.closing.message")}>{(id) => <Textarea id={id} disabled={disabled} value={st.closing?.message?.[lang] ?? ""} onChange={(e) => text("closing", e.target.value)} />}</Field>
      </Card>
      <Card>
        <h2 className="mb-4 text-2xl">{t("settings.ending")}</h2>
        <Field label={t("settings.ending.message")} hint={t("settings.ending.hint", { full_name: "{full_name}" })}>{(id) => <Textarea id={id} disabled={disabled} value={st.ending?.message?.[lang] ?? ""} onChange={(e) => text("ending", e.target.value)} />}</Field>
        <Field label={t("settings.ending.redirect")} hint={t("settings.ending.redirect.hint")}>
          {(id) => <Input id={id} type="url" placeholder="https://" disabled={disabled} value={st.ending?.redirectUrl ?? ""}
            onChange={(e) => update((s) => { s.settings.ending = { ...(s.settings.ending ?? {}), redirectUrl: e.target.value.startsWith("https://") && e.target.value.length > 8 ? e.target.value : null }; })} />}
        </Field>
        <Field label={t("settings.respondent_email")} hint={t("settings.respondent_email.hint")}>
          {(id) => (
            <Select id={id} disabled={disabled} value={st.respondentEmailField ?? ""} onChange={(e) => update((s) => { s.settings.respondentEmailField = e.target.value || null; })}>
              <option value="">{t("common.none")}</option>
              {emailFields.map((b: any) => <option key={b.id} value={b.id}>{b.label?.[lang] || b.id}</option>)}
            </Select>
          )}
        </Field>
      </Card>
      <Card>
        <h2 className="mb-4 text-2xl">{t("settings.payments")}</h2>
        <Field label={t("settings.fee_bearer")} hint={t("settings.fee_bearer.hint")}>
          {(id) => (
            <Select id={id} disabled={disabled} value={st.payments?.feeBearer ?? "org"} onChange={(e) => update((s) => { s.settings.payments = { ...(s.settings.payments ?? {}), feeBearer: e.target.value }; })}>
              <option value="org">{t("settings.fee_bearer.org")}</option><option value="payer">{t("settings.fee_bearer.payer")}</option>
            </Select>
          )}
        </Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-orange" disabled={disabled} checked={st.saveAndResume !== false} onChange={(e) => update((s) => { s.settings.saveAndResume = e.target.checked; })} />{t("settings.resume")}</label>
        <label className="mt-2 flex items-center gap-2 text-sm"><input type="checkbox" className="h-4 w-4 accent-orange" disabled={disabled} checked={st.showProgress !== false} onChange={(e) => update((s) => { s.settings.showProgress = e.target.checked; })} />{t("settings.progress")}</label>
      </Card>
    </div>
  );
}

export function VersionsPanel({ base, form, onRestore, disabled }: { base: string; form: any; onRestore: (form: any) => void; disabled: boolean }) {
  const versions = useQuery<any[]>({ queryKey: ["versions", base, form.current_version], queryFn: () => api(`${base}/versions`) });
  if (!versions.data?.length) return <p className="text-grey">{t("versions.empty")}</p>;
  return (
    <div className="grid gap-3">
      <p className="text-sm text-grey">{t("versions.hint")}</p>
      {versions.data.map((v) => (
        <Card key={v.id} className="flex items-center justify-between !py-3">
          <div><span className="serif text-xl">{t("versions.number", { n: v.number })}</span> {v.current ? <Badge tone="green">{t("versions.current")}</Badge> : null}
            <p className="text-sm text-grey">{date(v.published_at)}</p></div>
          {!disabled ? <Button variant="secondary" size="sm" onClick={async () => confirm(t("versions.restore.confirm")) && onRestore(await api(`${base}/versions/${v.id}/restore`, { method: "POST" }))}>{t("versions.restore")}</Button> : null}
        </Card>
      ))}
    </div>
  );
}
