import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/app-shell";
import { EmptyState, PageHeader } from "@/components/shared/primitives";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Briefcase, ExternalLink, Mail, MapPin, Phone, Search } from "lucide-react";
import { apiGet } from "@/lib/api-client";

export const Route = createFileRoute("/faculty")({
  head: () => ({
    meta: [
      { title: "Faculty Directory — ORION Campus" },
      { name: "description", content: "Search IIIT Kottayam faculty." },
      { property: "og:title", content: "Faculty Directory — ORION" },
      { property: "og:description", content: "IIIT Kottayam faculty directory." },
    ],
  }),
  component: FacultyPage,
});

type Category = "hod" | "administrative" | "faculty" | "professional_support";

type FacultyMember = {
  id: number;
  full_name: string;
  initials: string | null;
  email: string | null;
  phone: string | null;
  designation: string | null;
  office_location: string | null;
  office_hours: string | null;
  research_interests: string | null;
  profile_url: string | null;
  category: Category[] | null;
  status: string;
};

const CATEGORY_LABEL: Record<Category, string> = {
  hod: "HOD",
  administrative: "Administrative",
  faculty: "Faculty",
  professional_support: "Professional Support",
};

const CATEGORY_FILTERS: { value: Category | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "hod", label: "HOD" },
  { value: "administrative", label: "Administrative" },
  { value: "faculty", label: "Faculty" },
  { value: "professional_support", label: "Professional Support" },
];

function FacultyPage() {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState<Category | "all">("all");
  const { data, isLoading } = useQuery({
    queryKey: ["faculty"],
    queryFn: () => apiGet<FacultyMember[]>("/faculty"),
  });

  const faculty = data ?? [];
  const query = q.trim().toLowerCase();
  const list = faculty
    .filter((f) => category === "all" || (f.category ?? []).includes(category))
    .filter(
      (f) =>
        !query ||
        f.full_name.toLowerCase().includes(query) ||
        (f.research_interests ?? "").toLowerCase().includes(query),
    );

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader badge="Directory" title="Faculty" subtitle={`${faculty.length} people`} />

        <div className="relative min-w-[12rem]">
          <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name" className="h-9 pl-9" />
        </div>

        <div className="flex flex-wrap gap-2">
          {CATEGORY_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setCategory(f.value)}
              className={
                "rounded-full border px-3 py-1 text-xs font-medium transition-colors " +
                (category === f.value
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-card text-muted-foreground hover:text-foreground")
              }
            >
              {f.label}
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="surface-card">
            <EmptyState title="Loading…" message="Fetching the faculty directory." />
          </div>
        ) : list.length === 0 ? (
          <div className="surface-card">
            <EmptyState title="No faculty found" message="Try a different search term." />
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {list.map((f) => (
              <Dialog key={f.id}>
                <DialogTrigger asChild>
                  <button className="surface-card hover-lift p-4 text-left">
                    <div className="flex items-center gap-3">
                      <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-secondary/60 text-sm font-bold">
                        {f.initials ?? f.full_name[0]}
                      </span>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold">{f.full_name}</p>
                        {(f.designation || f.office_location) && (
                          <p className="truncate text-xs text-muted-foreground">
                            {f.designation || f.office_location}
                          </p>
                        )}
                      </div>
                    </div>
                    {f.category && f.category.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1">
                        {f.category.map((c) => (
                          <span
                            key={c}
                            className="inline-block rounded-full border border-border bg-muted px-2 py-0.5 text-[10px] font-medium tracking-wide text-muted-foreground uppercase"
                          >
                            {CATEGORY_LABEL[c]}
                          </span>
                        ))}
                      </div>
                    )}
                    {f.office_hours && (
                      <p className="mt-3 flex items-center gap-1 text-xs text-muted-foreground">
                        <MapPin className="size-3.5" /> {f.office_hours}
                      </p>
                    )}
                  </button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>{f.full_name}</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-2.5 text-sm">
                    {f.category && f.category.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {f.category.map((c) => (
                          <span
                            key={c}
                            className="inline-block rounded-full border border-border bg-muted px-2 py-0.5 text-[10px] font-medium tracking-wide text-muted-foreground uppercase"
                          >
                            {CATEGORY_LABEL[c]}
                          </span>
                        ))}
                      </div>
                    )}
                    {f.designation && (
                      <p className="flex items-center gap-2">
                        <Briefcase className="size-4 text-muted-foreground" /> {f.designation}
                      </p>
                    )}
                    {f.email && (
                      <p className="flex items-center gap-2">
                        <Mail className="size-4 text-muted-foreground" />
                        <a href={`mailto:${f.email}`} className="hover:underline">
                          {f.email}
                        </a>
                      </p>
                    )}
                    {f.phone && (
                      <p className="flex items-center gap-2">
                        <Phone className="size-4 text-muted-foreground" /> {f.phone}
                      </p>
                    )}
                    {f.office_location && (
                      <p className="flex items-center gap-2">
                        <MapPin className="size-4 text-muted-foreground" /> {f.office_location}
                      </p>
                    )}
                    {f.office_hours && (
                      <p className="text-xs text-muted-foreground">Office hours: {f.office_hours}</p>
                    )}
                    {f.research_interests && (
                      <p className="text-xs text-muted-foreground">Research: {f.research_interests}</p>
                    )}
                    {f.profile_url && (
                      <a
                        href={f.profile_url}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center gap-2 text-xs text-primary hover:underline"
                      >
                        <ExternalLink className="size-3.5" /> View full profile
                      </a>
                    )}
                    {!f.designation &&
                      !f.email &&
                      !f.phone &&
                      !f.office_location &&
                      !f.office_hours &&
                      !f.research_interests &&
                      !f.profile_url && (
                        <p className="text-xs text-muted-foreground">
                          No additional details on record for this faculty member yet.
                        </p>
                      )}
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
