/** Small UI kit in the Arha identity: soft radii, thin rules, generous space. */
import * as Dialog from "@radix-ui/react-dialog";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { useId } from "react";

const cx = (...c: (string | false | null | undefined)[]): string => c.filter(Boolean).join(" ");
export { cx };

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger"; size?: "sm" | "md" };
export function Button({ variant = "primary", size = "md", className, ...rest }: BtnProps) {
  const variants = {
    primary: "bg-orange text-white hover:bg-orange-dark border-orange",
    secondary: "bg-white text-ink border-sand hover:border-grey",
    ghost: "bg-transparent text-ink border-transparent hover:bg-beige",
    danger: "bg-white text-red border-red/40 hover:bg-red/5",
  };
  return (
    <button type="button" {...rest}
      className={cx("inline-flex items-center justify-center gap-2 rounded-lg border font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none",
        size === "sm" ? "min-h-9 px-3 text-sm" : "min-h-11 px-4 text-[15px]", variants[variant], className)} />
  );
}

export function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string; children: (id: string, describedBy?: string) => ReactNode }) {
  const id = useId();
  const sub = error ? `${id}-e` : hint ? `${id}-h` : undefined;
  return (
    <div className="mb-4">
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium">{label}</label>
      {children(id, sub)}
      {hint && !error ? <p id={`${id}-h`} className="mt-1 text-sm text-grey">{hint}</p> : null}
      {error ? <p id={`${id}-e`} role="alert" className="mt-1 text-sm font-medium text-red">{error}</p> : null}
    </div>
  );
}

const inputCls = "w-full min-h-11 rounded-lg border border-sand bg-white px-3 py-2 text-[15px] placeholder:text-grey/70 focus:border-orange";
export const Input = (p: InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={cx(inputCls, p.className)} />;
export const Textarea = (p: TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...p} className={cx(inputCls, "min-h-24", p.className)} />;
export const Select = (p: SelectHTMLAttributes<HTMLSelectElement>) => <select {...p} className={cx(inputCls, p.className)} />;

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("rounded-xl border border-sand bg-white p-5", className)}>{children}</div>;
}

export function Badge({ tone = "neutral", children }: { tone?: "neutral" | "green" | "orange" | "red"; children: ReactNode }) {
  const tones = { neutral: "bg-beige text-ink", green: "bg-green/10 text-green", orange: "bg-orange/10 text-orange-dark", red: "bg-red/10 text-red" };
  return <span className={cx("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium", tones[tone])}>{children}</span>;
}

export function Notice({ tone = "info", children }: { tone?: "info" | "error" | "success"; children: ReactNode }) {
  const tones = { info: "border-orange bg-beige", error: "border-red bg-red/5 text-red", success: "border-green bg-green/5" };
  return <div role={tone === "error" ? "alert" : "status"} className={cx("mb-4 rounded-md border-l-[3px] px-4 py-3 text-sm", tones[tone])}>{children}</div>;
}

export function PageTitle({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-3xl md:text-4xl">{title}</h1>
        {subtitle ? <p className="mt-1 text-grey">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}

export function Empty({ title, text, action }: { title: string; text?: string; action?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-sand px-6 py-14 text-center">
      <p className="serif text-2xl">{title}</p>
      {text ? <p className="mx-auto mt-2 max-w-md text-grey">{text}</p> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; wide?: boolean }) {
  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/40" />
        <Dialog.Content aria-describedby={undefined}
          className={cx("fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl bg-cream p-6 shadow-xl", wide ? "max-w-3xl" : "max-w-md")}>
          <Dialog.Title className="serif mb-4 text-2xl">{title}</Dialog.Title>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <p className="text-xs uppercase tracking-widest text-grey">{label}</p>
      <p className="serif mt-1 text-3xl">{value}</p>
      {hint ? <p className="mt-1 text-sm text-grey">{hint}</p> : null}
    </Card>
  );
}

export function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-sand bg-white">
      <table className="w-full text-left text-sm">
        <thead><tr className="border-b border-sand text-xs uppercase tracking-wider text-grey">{head.map((h) => <th key={h} scope="col" className="px-4 py-3 font-medium">{h}</th>)}</tr></thead>
        <tbody className="[&>tr]:border-b [&>tr]:border-beige [&>tr:last-child]:border-0 [&_td]:px-4 [&_td]:py-3">{children}</tbody>
      </table>
    </div>
  );
}

export const Spinner = () => <div role="status" aria-label="..." className="mx-auto my-16 h-6 w-6 animate-spin rounded-full border-2 border-sand border-t-orange" />;
