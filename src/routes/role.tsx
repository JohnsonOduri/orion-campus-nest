import { useEffect } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { PixelParticles, PixelSprite, SPRITES } from "@/components/pixel/pixel-art";
import { useAuth } from "@/hooks/use-auth";

export const Route = createFileRoute("/role")({
  head: () => ({
    meta: [
      { title: "Switch portal — ORION Campus" },
      { name: "description", content: "Switch between the admin and CR portals." },
    ],
  }),
  component: RolePage,
});

const PORTALS = [
  {
    id: "admin",
    title: "Administrator",
    desc: "Approve submissions, manage users and faculty, monitor analytics.",
    sprite: SPRITES.trophy,
    to: "/admin",
  },
  {
    id: "cr",
    title: "Class Representative",
    desc: "Upload timetables and notices, run OCR verification, track approvals.",
    sprite: SPRITES.bolt,
    to: "/cr",
  },
  {
    id: "student",
    title: "Student view",
    desc: "See what students see: timetable, attendance, exams, mess, clubs.",
    sprite: SPRITES.book,
    to: "/dashboard",
  },
] as const;

/**
 * Roles are assigned server-side (signup trigger + admin-approved CR
 * requests), never chosen here. This page only lets an ADMIN — the one
 * role allowed into every portal — jump between them; anyone else is sent
 * back to their own portal.
 */
function RolePage() {
  const navigate = useNavigate();
  const { context, loading } = useAuth();

  useEffect(() => {
    if (loading) return;
    if (!context?.authenticated) {
      navigate({ to: "/login", search: { error: undefined } });
    } else if (context.role !== "ADMIN") {
      navigate({ to: context.role === "CR" ? "/cr" : "/dashboard" });
    }
  }, [loading, context, navigate]);

  if (loading || context?.role !== "ADMIN") {
    return (
      <div className="grid min-h-screen place-items-center bg-background">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-5 py-16">
      <PixelParticles count={18} />
      <div className="relative z-10 w-full max-w-4xl">
        <div className="text-center">
          <p className="font-pixel text-[11px] text-primary">ORION</p>
          <h1 className="mt-4 text-2xl font-bold tracking-tight sm:text-3xl">Which portal?</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            As an administrator you can view every portal.
          </p>
        </div>

        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {PORTALS.map((r, i) => (
            <motion.button
              key={r.id}
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.08 }}
              onClick={() => navigate({ to: r.to })}
              className="surface-card hover-lift pixel-corners group flex flex-col items-start p-5 text-left"
            >
              <div className="grid size-16 place-items-center rounded-xl bg-secondary/60">
                <PixelSprite size={5} rows={[...r.sprite]} />
              </div>
              <h2 className="mt-4 text-base font-semibold">{r.title}</h2>
              <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{r.desc}</p>
              <span className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-primary">
                Continue
                <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-1" />
              </span>
            </motion.button>
          ))}
        </div>
      </div>
    </div>
  );
}
