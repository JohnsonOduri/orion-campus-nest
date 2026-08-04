import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard, StatCard } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { adminStats, uploads, usageTrend, users } from "@/lib/mock-data";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Users2, Sparkles, ScanText, HardDrive } from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/admin")({
  head: () => ({
    meta: [
      { title: "Admin Portal — ORION Campus" },
      { name: "description", content: "Administrator workspace: approvals, user and faculty management, analytics and storage." },
      { property: "og:title", content: "Admin Portal — ORION" },
      { property: "og:description", content: "Approvals, user management and campus analytics." },
    ],
  }),
  component: AdminPage,
});

const icons = [Users2, Sparkles, ScanText, HardDrive];
const tone = { approved: "success", pending: "warning", rejected: "danger" } as const;

function AdminPage() {
  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader badge="Administrator" title="Admin Portal" subtitle="Institute-wide operations and analytics." />

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {adminStats.map((s, i) => {
            const Icon = icons[i]!;
            return (
              <StatCard
                key={s.label}
                label={s.label}
                value={s.value.toLocaleString()}
                suffix={s.suffix ?? ""}
                delta={s.delta}
                icon={<Icon className="size-4" />}
                tone={i % 2 ? "accent" : "primary"}
              />
            );
          })}
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          <SectionCard title="Daily active users">
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={usageTrend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis dataKey="day" fontSize={11} stroke="var(--color-muted-foreground)" />
                  <YAxis fontSize={11} stroke="var(--color-muted-foreground)" />
                  <Tooltip contentStyle={{ background: "var(--color-card)", border: "1px solid var(--color-border)", borderRadius: 10, fontSize: 12 }} />
                  <Line type="monotone" dataKey="users" stroke="var(--color-chart-1)" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </SectionCard>

          <SectionCard title="AI queries">
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={usageTrend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis dataKey="day" fontSize={11} stroke="var(--color-muted-foreground)" />
                  <YAxis fontSize={11} stroke="var(--color-muted-foreground)" />
                  <Tooltip contentStyle={{ background: "var(--color-card)", border: "1px solid var(--color-border)", borderRadius: 10, fontSize: 12 }} />
                  <Bar dataKey="queries" fill="var(--color-chart-2)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </SectionCard>
        </div>

        <SectionCard title="Approval queue" contentClassName="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Document</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>OCR</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {uploads.map((u) => (
                  <TableRow key={u.file}>
                    <TableCell className="font-mono text-xs">{u.file}</TableCell>
                    <TableCell className="text-xs">{u.type}</TableCell>
                    <TableCell className="font-mono text-xs">{u.confidence}%</TableCell>
                    <TableCell>
                      <PixelBadge tone={tone[u.status as keyof typeof tone]}>{u.status}</PixelBadge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button size="sm" variant="outline" onClick={() => toast.success(`${u.file} approved`)}>
                        Review
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </SectionCard>

        <SectionCard title="User management" contentClassName="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>ID</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Department</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="text-sm font-medium">{u.name}</TableCell>
                    <TableCell className="font-mono text-xs">{u.id}</TableCell>
                    <TableCell className="text-xs">{u.role}</TableCell>
                    <TableCell className="text-xs">{u.dept}</TableCell>
                    <TableCell>
                      <PixelBadge tone={u.status === "active" ? "success" : "danger"}>{u.status}</PixelBadge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </SectionCard>
      </div>
    </AppShell>
  );
}
