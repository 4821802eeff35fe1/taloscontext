import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { endpoints, type KnowledgeBase, type KnowledgeDoc } from "@/lib/api";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  Input,
  PageHeader,
  SkeletonRows,
  Textarea,
} from "@/components/ui/primitives";
import { DateTimePicker, Select, Switch } from "@/components/ui/forms";
import { ConfirmDialog, Dialog } from "@/components/ui/overlays";
import { useOperation } from "@/hooks/useOperations";
const kinds = [
  "FACT",
  "CONTACT",
  "STYLE_EXAMPLE_GOOD",
  "STYLE_EXAMPLE_BAD",
  "HISTORICAL_POST",
  "RULE",
  "PROHIBITED_CLAIM",
  "LINK",
];
export function KnowledgePage({ workspaceId: ws }: { workspaceId: string }) {
  const [base, setBase] = useState("all"),
    [kind, setKind] = useState("FACT"),
    [q, setQ] = useState(""),
    [create, setCreate] = useState(false),
    [entry, setEntry] = useState(false),
    [name, setName] = useState(""),
    [text, setText] = useState(""),
    [selected, setSelected] = useState<string | null>(null),
    [remove, setRemove] = useState<KnowledgeDoc | null>(null);
  const [editingBase, setEditingBase] = useState<KnowledgeBase | null>(null),
    [removingBase, setRemovingBase] = useState<KnowledgeBase | null>(null),
    [baseDescription, setBaseDescription] = useState(""),
    [validUntil, setValidUntil] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const bases = useQuery({
    queryKey: ["knowledge-bases", ws],
    queryFn: () => endpoints.knowledgeBases(ws),
  });
  const docs = useQuery({
    queryKey: ["knowledge", ws, base],
    queryFn: () =>
      endpoints.knowledgeDocs(ws, {
        base_id: base === "all" ? undefined : base,
      }),
  });
  const hits = useQuery({
    queryKey: ["knowledge-search", ws, q],
    queryFn: () => endpoints.searchKnowledge(ws, q),
    enabled: q.trim().length > 1,
  });
  const detail = useQuery({
    queryKey: ["knowledge-detail", ws, selected],
    queryFn: () => endpoints.knowledgeDoc(ws, selected!),
    enabled: !!selected,
  });
  const action = useOperation(ws, (fn: () => Promise<unknown>) => fn());
  return (
    <div className="space-y-4">
      <PageHeader
        title="Knowledge"
        description="Current facts and rules take priority over historical posts."
        actions={
          <>
            <Button onClick={() => setCreate(true)}>
              Create knowledge base
            </Button>
            <Button onClick={() => setEntry(true)}>Add entry</Button>
            <Button variant="primary" onClick={() => file.current?.click()}>
              Upload
            </Button>
            <input
              ref={file}
              type="file"
              accept=".txt,.md,.json,.csv,.pdf"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f)
                  action.mutate(() =>
                    endpoints.uploadKnowledge(
                      ws,
                      f,
                      kind,
                      base === "all" ? null : base,
                    ),
                  );
                e.target.value = "";
              }}
            />
          </>
        }
      />
      <div className="flex flex-wrap gap-2">
        <Select
          ariaLabel="Knowledge base"
          className="w-60"
          value={base}
          onValueChange={setBase}
          options={[
            { value: "all", label: "All knowledge bases" },
            ...(bases.data ?? []).map((b) => ({ value: b.id, label: b.name })),
          ]}
        />
        <Select
          ariaLabel="Upload entry type"
          className="w-60"
          value={kind}
          onValueChange={setKind}
          options={kinds.map((value) => ({
            value,
            label: value.replaceAll("_", " "),
          }))}
        />
        <Input
          aria-label="Search knowledge"
          placeholder="Search knowledge…"
          className="max-w-xs"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>
      {base !== "all" &&
        bases.data
          ?.filter((b) => b.id === base)
          .map((b) => (
            <Card
              key={b.id}
              className="p-4 flex flex-wrap justify-between gap-3"
            >
              <span>
                {b.name} · {b.documents} documents · {b.entries} entries
              </span>
              <Button
                onClick={() => {
                  setEditingBase(b);
                  setName(b.name);
                  setBaseDescription(b.description);
                }}
              >
                Edit
              </Button>
              <Button variant="danger" onClick={() => setRemovingBase(b)}>
                Delete base
              </Button>
              <Switch
                label="Enable knowledge base"
                checked={b.enabled}
                onCheckedChange={(enabled) =>
                  action.mutate(() =>
                    endpoints.updateKnowledgeBase(ws, b.id, {
                      name: b.name,
                      description: b.description,
                      enabled,
                    }),
                  )
                }
              />
            </Card>
          ))}
      {q.length > 1 ? (
        <Card className="p-4">
          {hits.isError ? (
            <ErrorState error={hits.error} />
          ) : (
            hits.data?.map((h, i) => (
              <button
                key={i}
                onClick={() => setSelected(h.document_id)}
                className="block border-b py-3 text-left w-full"
              >
                <p>
                  {h.document_title} · {h.kind}
                </p>
                <p className="text-sm text-ink-muted">{h.snippet}</p>
              </button>
            ))
          )}
        </Card>
      ) : docs.isPending ? (
        <SkeletonRows />
      ) : docs.isError ? (
        <ErrorState error={docs.error} />
      ) : !docs.data.length ? (
        <EmptyState
          title="No knowledge yet"
          description="Upload TXT, MD, JSON, CSV, PDF or Telegram Desktop result.json."
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {docs.data.map((d) => (
            <Card key={d.id} className="p-4 space-y-3">
              <div className="flex justify-between gap-3">
                <button
                  onClick={() => setSelected(d.id)}
                  className="font-medium text-left"
                >
                  {d.title}
                </button>
                <Switch
                  label={`Enable ${d.title}`}
                  checked={d.enabled}
                  onCheckedChange={(enabled) =>
                    action.mutate(() =>
                      endpoints.updateKnowledgeDoc(ws, d.id, { enabled }),
                    )
                  }
                />
              </div>
              <p className="text-xs text-ink-muted">
                {d.kind} · {d.format} · {d.entries} entries
                {d.valid_until && " · valid until " + d.valid_until}
              </p>
              {d.warnings.map((w) => (
                <p key={w} className="text-xs text-warning">
                  {w}
                </p>
              ))}
              <div className="flex gap-2">
                <Button onClick={() => setSelected(d.id)}>Preview</Button>
                <Button variant="danger" onClick={() => setRemove(d)}>
                  Delete
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
      <Dialog
        open={create}
        onOpenChange={setCreate}
        title="Create knowledge base"
      >
        <Field label="Name">
          <Input
            aria-label="Knowledge base name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Button
          className="mt-3"
          disabled={!name.trim()}
          onClick={() => {
            action.mutate(() =>
              endpoints.createKnowledgeBase(ws, {
                name,
                description: "",
                enabled: true,
              }),
            );
            setCreate(false);
            setName("");
          }}
        >
          Create
        </Button>
      </Dialog>
      <Dialog open={entry} onOpenChange={setEntry} title="Add knowledge entry">
        <div className="space-y-3">
          <Input
            aria-label="Entry title"
            placeholder="Title"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Select
            ariaLabel="Entry type"
            value={kind}
            onValueChange={setKind}
            options={kinds.map((value) => ({ value, label: value }))}
          />
          <Textarea
            aria-label="Entry text"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <Button
            disabled={!text.trim() || !name.trim()}
            onClick={() => {
              action.mutate(() =>
                endpoints.createKnowledgeEntry(ws, {
                  title: name,
                  kind,
                  text,
                  knowledge_base_id: base === "all" ? null : base,
                }),
              );
              setEntry(false);
              setName("");
              setText("");
            }}
          >
            Save entry
          </Button>
        </div>
      </Dialog>
      <Dialog
        open={!!selected}
        onOpenChange={(open) => !open && setSelected(null)}
        title={detail.data?.title || "Parsed content"}
        size="lg"
      >
        <div className="mb-4 space-y-2">
          <p className="text-xs text-ink-muted">
            Optional validity date: expired facts are excluded from AI context.
          </p>
          <DateTimePicker
            value={validUntil ?? detail.data?.valid_until ?? null}
            onChange={setValidUntil}
            timeZone="UTC"
          />
          <Button
            disabled={action.isPending}
            onClick={() =>
              action.mutate(() =>
                endpoints.updateKnowledgeDoc(ws, selected!, {
                  valid_until: validUntil,
                }),
              )
            }
          >
            Save validity
          </Button>
          <Button
            onClick={() =>
              action.mutate(() =>
                endpoints.updateKnowledgeDoc(ws, selected!, {
                  valid_until: null,
                }),
              )
            }
          >
            Clear validity
          </Button>
        </div>
        {detail.isPending ? (
          <SkeletonRows />
        ) : detail.isError ? (
          <ErrorState error={detail.error} />
        ) : (
          detail.data?.preview.map((p) => (
            <div className="border-b py-3" key={p.id}>
              <p className="text-xs text-ink-faint">
                {p.kind} · {p.effective_at}
              </p>
              <p className="whitespace-pre-wrap text-sm">{p.content}</p>
              <pre className="overflow-auto text-xs text-ink-muted mt-2">
                {JSON.stringify(p.metadata, null, 2)}
              </pre>
            </div>
          ))
        )}
      </Dialog>
      <Dialog
        open={!!editingBase}
        onOpenChange={(open) => !open && setEditingBase(null)}
        title="Edit knowledge base"
      >
        <div className="space-y-3">
          <Input
            aria-label="Knowledge base name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Textarea
            aria-label="Knowledge base description"
            value={baseDescription}
            onChange={(e) => setBaseDescription(e.target.value)}
          />
          <Button
            disabled={!name.trim()}
            onClick={() => {
              action.mutate(() =>
                endpoints.updateKnowledgeBase(ws, editingBase!.id, {
                  name,
                  description: baseDescription,
                  enabled: editingBase!.enabled,
                }),
              );
              setEditingBase(null);
            }}
          >
            Save base
          </Button>
        </div>
      </Dialog>
      <ConfirmDialog
        open={!!removingBase}
        onOpenChange={(open) => !open && setRemovingBase(null)}
        title="Delete this knowledge base?"
        description="Its documents remain available without a base."
        destructive
        onConfirm={() => {
          action.mutate(() =>
            endpoints.deleteKnowledgeBase(ws, removingBase!.id),
          );
          setRemovingBase(null);
          setBase("all");
        }}
      />
      <ConfirmDialog
        open={!!remove}
        onOpenChange={(open) => !open && setRemove(null)}
        title="Delete this document?"
        destructive
        onConfirm={() => {
          action.mutate(() => endpoints.deleteKnowledgeDoc(ws, remove!.id));
          setRemove(null);
        }}
      />
    </div>
  );
}
