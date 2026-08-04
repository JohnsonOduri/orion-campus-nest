import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard } from "@/components/shared/primitives";
import { AiChatPanel } from "@/components/ai/ai-chat";
import { Input } from "@/components/ui/input";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { conversations } from "@/lib/mock-data";
import { Pin, Search } from "lucide-react";

export const Route = createFileRoute("/ai")({
  head: () => ({
    meta: [
      { title: "ORION AI Chat — Campus Assistant" },
      { name: "description", content: "Ask ORION about classes, deadlines, faculty and campus life with voice, image and PDF input." },
      { property: "og:title", content: "ORION AI Chat" },
      { property: "og:description", content: "Your campus questions, answered instantly." },
    ],
  }),
  component: AiPage,
});

function AiPage() {
  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader badge="Assistant" title="ORION AI" subtitle="Grounded in IIIT Kottayam campus data." />
        <div className="grid gap-5 lg:grid-cols-[18rem_1fr]">
          <SectionCard title="Conversations" contentClassName="p-3">
            <div className="relative">
              <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input placeholder="Search chats" className="h-9 pl-9" />
            </div>
            <ul className="mt-3 space-y-1">
              {conversations.map((c) => (
                <li key={c.title}>
                  <button className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs transition-colors hover:bg-muted">
                    {c.pinned ? <Pin className="size-3 shrink-0 text-primary" /> : null}
                    <span className="truncate">{c.title}</span>
                    <span className="ml-auto shrink-0 font-mono text-[10px] text-muted-foreground">{c.time}</span>
                  </button>
                </li>
              ))}
            </ul>
            <PixelBadge tone="muted" className="mt-3">
              4 chats · 128 messages
            </PixelBadge>
          </SectionCard>

          <div className="surface-card flex h-[70vh] min-h-[28rem] flex-col overflow-hidden">
            <AiChatPanel />
          </div>
        </div>
      </div>
    </AppShell>
  );
}
