import { useEffect, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { History, Search, SquarePen, Trash2 } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { AiChatPanel } from "@/components/ai/ai-chat";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { apiGet, apiDelete } from "@/lib/api-client";

export const Route = createFileRoute("/ai")({
  head: () => ({
    meta: [
      { title: "ORION AI — Campus Assistant" },
      {
        name: "description",
        content:
          "Ask ORION about classes, faculty, the mess menu and campus rules — by text or voice.",
      },
      { property: "og:title", content: "ORION AI" },
      { property: "og:description", content: "Your campus questions, answered instantly." },
    ],
  }),
  // /ai?q=... opens a new chat and asks that question (links from other pages).
  validateSearch: (search: Record<string, unknown>): { q?: string } => {
    const q = search["q"];
    return typeof q === "string" && q.trim() ? { q: q.slice(0, 500) } : {};
  },
  component: AiPage,
});

type Conversation = { id: string; title: string | null; created_at: string; updated_at: string };

function useConversations() {
  const [conversations, setConversations] = useState<Conversation[]>([]);

  async function refresh() {
    try {
      const res = await apiGet<{ conversations: Conversation[] }>("/ai/conversations");
      setConversations(res.conversations);
    } catch {
      // Signed out or API briefly unreachable: the chat still works, the
      // history list just stays empty.
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  return { conversations, refresh };
}

function relativeDay(iso: string): string {
  const date = new Date(iso);
  const days = Math.floor((Date.now() - date.getTime()) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return date.toLocaleDateString(undefined, { weekday: "short" });
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function ConversationList({
  conversations,
  activeId,
  onSelect,
  onDelete,
}: {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
  onDelete: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const filtered = conversations.filter((c) =>
    (c.title ?? "New chat").toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <Button
        variant="outline"
        className="h-10 justify-start gap-2 rounded-xl"
        onClick={() => onSelect(null)}
      >
        <SquarePen className="size-4" /> New chat
      </Button>
      <div className="relative">
        <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search chats"
          aria-label="Search chats"
          className="h-10 rounded-xl pl-9"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <ul className="scrollbar-thin -mx-1 min-h-0 flex-1 space-y-0.5 overflow-y-auto px-1">
        {filtered.length === 0 ? (
          <li className="px-3 py-6 text-center text-sm text-muted-foreground">
            {conversations.length === 0
              ? "Your conversations will appear here."
              : "No matching chats."}
          </li>
        ) : (
          filtered.map((c) => (
            <li key={c.id} className="group relative">
              <button
                onClick={() => onSelect(c.id)}
                aria-current={activeId === c.id ? "page" : undefined}
                className={cn(
                  "flex min-h-11 w-full items-center gap-2 rounded-xl py-2 pr-11 pl-3 text-left text-sm transition-colors hover:bg-muted",
                  activeId === c.id && "bg-muted font-medium",
                )}
              >
                <span className="min-w-0 flex-1 truncate">{c.title || "New chat"}</span>
                <span className="shrink-0 text-[11px] text-muted-foreground">
                  {relativeDay(c.updated_at)}
                </span>
              </button>
              <button
                aria-label={`Delete “${c.title || "New chat"}”`}
                onClick={() => onDelete(c.id)}
                className="absolute top-1/2 right-1 grid size-9 -translate-y-1/2 place-items-center rounded-lg text-muted-foreground transition-opacity hover:bg-destructive/10 hover:text-destructive focus-visible:opacity-100 md:opacity-0 md:group-hover:opacity-100"
              >
                <Trash2 className="size-4" />
              </button>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}

function AiPage() {
  const { conversations, refresh } = useConversations();
  const { q: askedQuestion } = Route.useSearch();
  const navigate = useNavigate();
  const [activeId, setActiveId] = useState<string | null>(null);
  // The panel remounts only when the user opens a different chat — NOT when
  // its own first message creates a conversation (that would cut off the
  // reply and any voice session mid-answer).
  const [opened, setOpened] = useState<{ id: string | null; key: number }>({ id: null, key: 0 });
  const [historyOpen, setHistoryOpen] = useState(false);
  const activeTitle = conversations.find((c) => c.id === activeId)?.title;

  function handleSelect(id: string | null) {
    setActiveId(id);
    setOpened((o) => ({ id, key: o.key + 1 }));
    setHistoryOpen(false);
  }

  async function handleDelete(id: string) {
    try {
      await apiDelete(`/ai/conversations/${id}`);
      if (activeId === id) handleSelect(null);
      toast.success("Conversation deleted");
      void refresh();
    } catch {
      toast.error("Couldn't delete that conversation.");
    }
  }

  function handleConversationCreated(id: string) {
    setActiveId(id);
    void refresh();
  }

  const list = (
    <ConversationList
      conversations={conversations}
      activeId={activeId}
      onSelect={handleSelect}
      onDelete={handleDelete}
    />
  );

  return (
    <AppShell fill>
      <div className="flex min-h-0 flex-1 gap-4">
        <aside className="hidden w-72 shrink-0 flex-col rounded-2xl border border-border bg-card p-3 lg:flex">
          {list}
        </aside>

        <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background sm:rounded-2xl sm:border sm:border-border">
          <header className="flex h-12 shrink-0 items-center gap-1 border-b border-border/60 px-2">
            <Button
              variant="ghost"
              size="icon"
              className="size-10 rounded-full lg:hidden"
              aria-label="Chat history"
              onClick={() => setHistoryOpen(true)}
            >
              <History className="size-5" />
            </Button>
            <h1 className="min-w-0 flex-1 truncate px-1 text-sm font-semibold lg:px-2">
              {activeTitle || "ORION"}
            </h1>
            <Button
              variant="ghost"
              size="icon"
              className="size-10 rounded-full"
              aria-label="New chat"
              title="New chat"
              onClick={() => handleSelect(null)}
            >
              <SquarePen className="size-5" />
            </Button>
          </header>

          <div className="min-h-0 flex-1">
            <AiChatPanel
              key={opened.key}
              initialConversationId={opened.id}
              {...(!opened.id && askedQuestion ? { initialQuestion: askedQuestion } : {})}
              onInitialQuestionSent={() => void navigate({ to: "/ai", search: {}, replace: true })}
              onConversationCreated={handleConversationCreated}
            />
          </div>
        </section>
      </div>

      <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
        <SheetContent
          side="left"
          className="flex w-[85vw] max-w-sm flex-col p-4 pt-[calc(env(safe-area-inset-top)+1rem)]"
        >
          <SheetHeader className="p-0">
            <SheetTitle>Chats</SheetTitle>
          </SheetHeader>
          <div className="min-h-0 flex-1">{list}</div>
        </SheetContent>
      </Sheet>
    </AppShell>
  );
}
