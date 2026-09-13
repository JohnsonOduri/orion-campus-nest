import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard, StatCard } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { PixelBadge, PixelLoadingBar } from "@/components/pixel/pixel-art";
import { uploads } from "@/lib/mock-data";
import { CheckCircle2, Clock, FileUp, ScanText, UploadCloud, XCircle } from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/cr")({
  head: () => ({
    meta: [
      { title: "CR Portal — ORION Campus" },
      { name: "description", content: "Class representative workspace: upload timetables and notices, verify OCR output, track approvals." },
      { property: "og:title", content: "CR Portal — ORION" },
      { property: "og:description", content: "Uploads, OCR verification and approval history." },
    ],
  }),
  component: CrPage,
});

const tone = { approved: "success", pending: "warning", rejected: "danger" } as const;

function CrPage() {
  return (
    <AppShell allow={["CR"]}>
      <div className="space-y-5">
        <PageHeader badge="Class representative" title="CR Portal" subtitle="CSE · Semester 6 · Section A" />

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard label="Uploads this month" value={14} icon={<UploadCloud className="size-4" />} />
          <StatCard label="Pending review" value={1} tone="warning" icon={<Clock className="size-4" />} />
          <StatCard label="Approved" value={11} tone="success" icon={<CheckCircle2 className="size-4" />} />
          <StatCard label="Avg OCR score" value={91} suffix="%" tone="accent" icon={<ScanText className="size-4" />} />
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          <SectionCard title="Quick upload" description="Timetable, mess menu or announcement">
            <button
              onClick={() => toast.success("Document queued for OCR")}
              className="flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed border-border p-8 text-center transition-colors hover:border-primary"
            >
              <FileUp className="size-6 text-primary" />
              <span className="text-sm font-medium">Drag & drop or browse</span>
              <span className="font-mono text-[11px] text-muted-foreground">PDF, PNG, JPG up to 10 MB</span>
            </button>
            <div className="mt-4 flex flex-wrap gap-2">
              {["Timetable", "Mess menu", "Announcement"].map((t) => (
                <PixelBadge key={t}>{t}</PixelBadge>
              ))}
            </div>
            <Button className="mt-4 w-full" onClick={() => toast.success("Submitted for admin approval")}>
              Submit for approval
            </Button>
          </SectionCard>

          <SectionCard title="OCR verification" description="mess_menu_week32.jpg · 88% confidence">
            <PixelLoadingBar value={88} />
            <Progress value={88} className="mt-3 h-1.5" />
            <Textarea
              className="mt-4 font-mono text-xs"
              rows={6}
              defaultValue={"BREAKFAST 07:30 Idli & sambar, chutney\nLUNCH 12:15 Rice, sambar, thoran, fish curry\nSNACKS 16:30 Parippu vada, tea\nDINNER 19:30 Chapati, veg kurma, egg roast"}
            />
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" onClick={() => toast.success("Approved and published")}>
                <CheckCircle2 className="size-4" /> Approve
              </Button>
              <Button size="sm" variant="outline" onClick={() => toast("Saved as draft")}>
                Save draft
              </Button>
              <Button size="sm" variant="destructive" onClick={() => toast.error("Rejected")}>
                <XCircle className="size-4" /> Reject
              </Button>
            </div>
          </SectionCard>
        </div>

        <SectionCard title="Upload history" contentClassName="p-0">
          <ul className="divide-y divide-border">
            {uploads.map((u) => (
              <li key={u.file} className="flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono text-xs font-medium">{u.file}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {u.type} · {u.date} · OCR {u.confidence}%
                  </p>
                </div>
                <PixelBadge tone={tone[u.status as keyof typeof tone]}>{u.status}</PixelBadge>
              </li>
            ))}
          </ul>
        </SectionCard>
      </div>
    </AppShell>
  );
}
