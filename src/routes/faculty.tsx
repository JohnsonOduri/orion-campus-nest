import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { EmptyState, PageHeader } from "@/components/shared/primitives";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { faculty } from "@/lib/mock-data";
import { Mail, Phone, MapPin, Search } from "lucide-react";

export const Route = createFileRoute("/faculty")({
  head: () => ({
    meta: [
      { title: "Faculty Directory — ORION Campus" },
      { name: "description", content: "Search IIIT Kottayam faculty by department with cabins, office hours and availability." },
      { property: "og:title", content: "Faculty Directory — ORION" },
      { property: "og:description", content: "Cabins, office hours, subjects and live availability." },
    ],
  }),
  component: FacultyPage,
});

const depts = ["All", "CSE", "ECE", "Mathematics", "Humanities"];

function FacultyPage() {
  const [q, setQ] = useState("");
  const [dept, setDept] = useState("All");
  const list = faculty.filter(
    (f) =>
      (dept === "All" || f.dept === dept) &&
      (f.name.toLowerCase().includes(q.toLowerCase()) || f.research.toLowerCase().includes(q.toLowerCase())),
  );

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader badge="Directory" title="Faculty" subtitle="Availability updates every 15 minutes." />

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[12rem] flex-1">
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name or research area" className="h-9 pl-9" />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {depts.map((d) => (
              <Button key={d} size="sm" variant={dept === d ? "default" : "outline"} onClick={() => setDept(d)}>
                {d}
              </Button>
            ))}
          </div>
        </div>

        {list.length === 0 ? (
          <div className="surface-card">
            <EmptyState title="No faculty found" message="Try a different name, department or research keyword." />
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {list.map((f) => (
              <Dialog key={f.name}>
                <DialogTrigger asChild>
                  <button className="surface-card hover-lift p-4 text-left">
                    <div className="flex items-center gap-3">
                      <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-secondary/60 text-sm font-bold">
                        {f.name.split(" ").slice(-1)[0]?.[0]}
                      </span>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold">{f.name}</p>
                        <p className="truncate text-xs text-muted-foreground">{f.role} · {f.dept}</p>
                      </div>
                    </div>
                    <p className="mt-3 flex items-center gap-1 text-xs text-muted-foreground">
                      <MapPin className="size-3.5" /> {f.cabin} · {f.hours}
                    </p>
                    <PixelBadge tone={f.available ? "success" : "muted"} className="mt-3">
                      {f.available ? "Available now" : "Away"}
                    </PixelBadge>
                  </button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>{f.name}</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-2.5 text-sm">
                    <p className="text-muted-foreground">{f.role} · {f.dept}</p>
                    <p className="flex items-center gap-2"><Mail className="size-4 text-muted-foreground" /> {f.email}</p>
                    <p className="flex items-center gap-2"><Phone className="size-4 text-muted-foreground" /> {f.phone}</p>
                    <p className="flex items-center gap-2"><MapPin className="size-4 text-muted-foreground" /> {f.cabin}</p>
                    <p className="text-xs text-muted-foreground">Office hours: {f.hours}</p>
                    <p className="text-xs text-muted-foreground">Research: {f.research}</p>
                    <div className="flex gap-1.5 pt-1">
                      {f.subjects.map((s) => (
                        <PixelBadge key={s}>{s}</PixelBadge>
                      ))}
                    </div>
                  </div>
                </DialogContent>
              </Dialog>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
