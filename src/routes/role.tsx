import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { PixelParticles, PixelSprite, SPRITES } from "@/components/pixel/pixel-art";
import { useOrion, type Role } from "@/store/orion";

export const Route = createFileRoute("/role")({
  head: () => ({
    meta: [
      { title: "Choose your role — ORION Campus" },
      { name: "description", content: "Continue to ORION as a student, class representative or administrator." },
      { property: "og:title", content: "Choose your role — ORION" },
      { property: "og:description", content: "Student, class representative or administrator workspaces." },
    ],
  }),
  component: RolePage,
});

const ROLES: { id: Role; title: string; desc: string; sprite: readonly string[]; to: string }[] = [
  {
    id: "student",
    title: "Student",
    desc: "Timetable, attendance, exams, mess, clubs and your AI assistant.",
    sprite: SPRITES.book,
    to: "/dashboard",
  },
  {
    id: "cr",
    title: "Class Representative",
    desc: "Upload timetables and notices, run OCR verification, track approvals.",
    sprite: SPRITES.bolt,
    to: "/cr",
  },
  {
    id: "admin",
    title: "Administrator",
    desc: "Approve submissions, manage users and faculty, monitor analytics.",
    sprite: SPRITES.trophy,
    to: "/admin",
  },
];

function RolePage() {
  const navigate = useNavigate();
  const setRole = useOrion((s) => s.setRole);

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-5 py-16">
      <PixelParticles count={18} />
      <div className="relative z-10 w-full max-w-4xl">
        <div className="text-center">
          <p className="font-pixel text-[11px] text-primary">ORION</p>
          <h1 className="mt-4 text-2xl font-bold tracking-tight sm:text-3xl">How are you joining today?</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            You can switch roles anytime from your account menu.
          </p>
        </div>

        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {ROLES.map((r, i) => (
            <motion.button
              key={r.id}
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.08 }}
              onClick={() => {
                setRole(r.id);
                navigate({ to: r.to });
              }}
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
