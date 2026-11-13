import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useState } from "react";
import { api, errorText } from "../lib/api";
import { date, num, t, tx } from "../lib/i18n";
import { atLeast, useOrg } from "../session";
import { Badge, Button, Card, Empty, Field, Input, Modal, Notice, PageTitle, Select, Spinner } from "../ui";

export const statusTone = (s: string) => (s === "published" ? "green" : s === "suspended" ? "red" : s === "closed" ? "neutral" : "orange") as "green" | "red" | "neutral" | "orange";

export function FormsList() {
  const { org: orgId } = useParams({ strict: false }) as { org: string };
  const org = useOrg(orgId).data;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("updated");
  const [folder, setFolder] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const canEdit = atLeast(org, "editor");
  const forms = useQuery<any[]>({
    queryKey: ["forms", orgId, q, sort, folder],
    queryFn: () => api(`/orgs/${orgId}/forms?sort=${sort}${q ? `&q=${encodeURIComponent(q)}` : ""}${folder ? `&folder_id=${folder}` : ""}`),
  });
  const folders = useQuery<any[]>({ queryKey: ["folders", orgId], queryFn: () => api(`/orgs/${orgId}/folders`) });
  const templates = useQuery<any[]>({ queryKey: ["templates"], queryFn: () => api("/templates"), enabled: creating });

  const create = async (template: string | null, title: string) => {
    try {
      const form = await api<{ id: string }>(`/orgs/${orgId}/forms`, { json: { title, template, folder_id: folder || null } });
      await navigate({ to: "/o/$org/forms/$form", params: { org: orgId, form: form.id } });
    } catch (e) {
      setError(errorText(e));
    }
  };
  const newFolder = async () => {
    const name = prompt(t("forms.folder.prompt"));
    if (!name) return;
    await api(`/orgs/${orgId}/folders`, { json: { name } });
    await qc.invalidateQueries({ queryKey: ["folders", orgId] });
  };
  const move = async (formId: string, folderId: string) => {
    await api(`/orgs/${orgId}/forms/${formId}`, { method: "PATCH", json: folderId ? { folder_id: folderId } : { move_to_root: true } });
    await qc.invalidateQueries({ queryKey: ["forms", orgId] });
  };

  return (
    <>
      <PageTitle title={t("forms.title")} subtitle={t("forms.subtitle")}
        actions={canEdit ? <><Button variant="secondary" onClick={newFolder}>{t("forms.folder.new")}</Button><Button onClick={() => setCreating(true)}>{t("forms.new")}</Button></> : null} />
      {error ? <Notice tone="error">{error}</Notice> : null}
      <div className="mb-5 grid gap-3 sm:grid-cols-[1fr_200px_200px]">
        <Input type="search" placeholder={t("forms.search")} aria-label={t("forms.search")} value={q} onChange={(e) => setQ(e.target.value)} />
        <Select aria-label={t("forms.folder")} value={folder} onChange={(e) => setFolder(e.target.value)}>
          <option value="">{t("forms.folder.all")}</option>
          {(folders.data ?? []).map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </Select>
        <Select aria-label={t("forms.sort")} value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="updated">{t("forms.sort.updated")}</option>
          <option value="title">{t("forms.sort.title")}</option>
          <option value="created">{t("forms.sort.created")}</option>
        </Select>
      </div>
      {forms.isLoading ? <Spinner /> : forms.data?.length ? (
        <div className="grid gap-3">
          {forms.data.map((f) => (
            <Card key={f.id} className="flex flex-wrap items-center justify-between gap-3 !py-4">
              <div className="min-w-0">
                <Link to="/o/$org/forms/$form" params={{ org: orgId, form: f.id }} className="serif block truncate text-2xl hover:text-orange-dark">{f.title}</Link>
                <p className="mt-0.5 text-sm text-grey">{t("forms.updated", { date: date(f.updated_at) })} &middot; {t("forms.responses", { count: num(f.responses) })}</p>
              </div>
              <div className="flex items-center gap-3">
                <Badge tone={statusTone(f.status)}>{t(`status.${f.status}`)}</Badge>
                {canEdit && folders.data?.length ? (
                  <Select aria-label={t("forms.move")} className="!min-h-9 !w-40 !py-1 text-sm" value={f.folder_id ?? ""} onChange={(e) => void move(f.id, e.target.value)}>
                    <option value="">{t("forms.folder.none")}</option>
                    {folders.data.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
                  </Select>
                ) : null}
                <Link to="/o/$org/forms/$form/responses" params={{ org: orgId, form: f.id }} className="text-sm underline">{t("forms.see_responses")}</Link>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <Empty title={t("forms.empty.title")} text={t("forms.empty.text")} action={canEdit ? <Button onClick={() => setCreating(true)}>{t("forms.new")}</Button> : undefined} />
      )}
      <Modal open={creating} onClose={() => setCreating(false)} title={t("forms.new.title")} wide>
        <BlankForm onCreate={(title) => void create(null, title)} />
        <p className="mb-3 mt-6 text-xs uppercase tracking-widest text-grey">{t("forms.templates")}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          {(templates.data ?? []).map((tpl) => (
            <button key={tpl.code} type="button" onClick={() => void create(tpl.code, tx(tpl.title))}
              className="rounded-xl border border-sand bg-white p-4 text-left hover:border-orange">
              <span className="serif block text-xl">{tx(tpl.title)}</span>
              <span className="mt-1 block text-sm text-grey">{tx(tpl.description)}</span>
            </button>
          ))}
        </div>
      </Modal>
    </>
  );
}

function BlankForm({ onCreate }: { onCreate: (title: string) => void }) {
  const [title, setTitle] = useState("");
  return (
    <form className="flex items-end gap-3" onSubmit={(e) => { e.preventDefault(); onCreate(title); }}>
      <div className="flex-1 [&>div]:mb-0">
        <Field label={t("forms.new.name")}>{(id) => <Input id={id} value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} required autoFocus />}</Field>
      </div>
      <Button type="submit" disabled={!title.trim()}>{t("forms.new.blank")}</Button>
    </form>
  );
}
