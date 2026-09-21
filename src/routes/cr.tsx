import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard, StatCard } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { CheckCircle2, Clock, Megaphone } from "lucide-react";
import { toast } from "sonner";
import { apiGet, apiPost, ApiError } from "@/lib/api-client";
import { requireRole } from "@/lib/route-guards";

export const Route = createFileRoute("/cr")({
  beforeLoad: requireRole(["CR", "ADMIN"]),
  head: () => ({
    meta: [
      { title: "CR Portal — ORION Campus" },
      { name: "description", content: "Class representative workspace: author announcements and track approvals." },
      { property: "og:title", content: "CR Portal — ORION" },
      { property: "og:description", content: "Announcement authoring and approval history." },
    ],
  }),
  component: CrPage,
});

type Announcement = {
  id: number;
  title: string;
  status: "pending" | "active" | "rejected" | string;
  category: string | null;
  rejection_reason: string | null;
  created_at: string;
  published_at: string | null;
};

const tone = { active: "success", pending: "warning", rejected: "danger" } as const;

function CrPage() {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [category, setCategory] = useState("");

  const announcementsQuery = useQuery({
    queryKey: ["cr", "announcements"],
    queryFn: () => apiGet<Announcement[]>("/cr/announcements"),
  });

  const submit = useMutation({
    mutationFn: () =>
      apiPost("/cr/announcements", {
        title,
        content,
        category: category || undefined,
      }),
    onSuccess: () => {
      toast.success("Submitted for admin approval");
      setTitle("");
      setContent("");
      setCategory("");
      queryClient.invalidateQueries({ queryKey: ["cr", "announcements"] });
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.message : "Could not submit announcement");
    },
  });

  const announcements = announcementsQuery.data ?? [];
  const pending = announcements.filter((a) => a.status === "pending").length;
  const active = announcements.filter((a) => a.status === "active").length;

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader badge="Class representative" title="CR Portal" subtitle="Author announcements for admin approval" />

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
          <StatCard label="Submitted" value={announcements.length} icon={<Megaphone className="size-4" />} />
          <StatCard label="Pending review" value={pending} tone="warning" icon={<Clock className="size-4" />} />
          <StatCard label="Live" value={active} tone="success" icon={<CheckCircle2 className="size-4" />} />
        </div>

        <SectionCard title="New announcement" description="Goes live only after admin approval">
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="title">Title</Label>
              <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Mid-sem exam schedule" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="category">Category (optional)</Label>
              <Input id="category" value={category} onChange={(e) => setCategory(e.target.value)} placeholder="OFFICIAL, EVENT, CLUB…" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="content">Content</Label>
              <Textarea id="content" rows={5} value={content} onChange={(e) => setContent(e.target.value)} />
            </div>
            <Button
              className="w-full"
              disabled={!title.trim() || !content.trim() || submit.isPending}
              onClick={() => submit.mutate()}
            >
              {submit.isPending ? "Submitting…" : "Submit for approval"}
            </Button>
          </div>
        </SectionCard>

        <SectionCard title="Submission history" contentClassName="p-0">
          {announcementsQuery.isLoading ? (
            <p className="p-4 text-sm text-muted-foreground">Loading…</p>
          ) : announcements.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">No announcements submitted yet.</p>
          ) : (
            <ul className="divide-y divide-border">
              {announcements.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center gap-3 p-4">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{a.title}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {a.category ?? "General"} · {new Date(a.created_at).toLocaleString()}
                      {a.rejection_reason ? ` · ${a.rejection_reason}` : ""}
                    </p>
                  </div>
                  <PixelBadge tone={tone[a.status as keyof typeof tone] ?? "muted"}>{a.status}</PixelBadge>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>
    </AppShell>
  );
}
