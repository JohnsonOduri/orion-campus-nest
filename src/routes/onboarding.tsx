import { useState } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import {
  PixelClouds,
  PixelParticles,
  PixelSkyline,
  PixelSprite,
  SPRITES,
} from "@/components/pixel/pixel-art";

export const Route = createFileRoute("/onboarding")({
  head: () => ({
    meta: [
      { title: "Get started with ORION — IIIT Kottayam" },
      { name: "description", content: "A quick tour of ORION: AI assistant, academics and campus life in one app." },
      { property: "og:title", content: "Get started with ORION" },
      { property: "og:description", content: "AI assistant, academics and campus life in one place." },
    ],
  }),
  component: Onboarding,
});

const SLIDES = [
  {
    title: "AI Campus Assistant",
    body: "Ask ORION about classes, deadlines, mess menus or faculty cabins — answers in seconds, in plain language.",
    sprite: SPRITES.mascot,
  },
  {
    title: "Academics Made Easy",
    body: "Timetable, attendance, assignments, hall tickets and results — organised, searchable and always current.",
    sprite: SPRITES.book,
  },
  {
    title: "Campus Life in One Place",
    body: "Clubs, events, mess ratings, announcements and documents — the whole campus in your pocket.",
    sprite: SPRITES.trophy,
  },
];

function Onboarding() {
  const [step, setStep] = useState(0);
  const navigate = useNavigate();
  const slide = SLIDES[step]!;

  function finish() {
    navigate({ to: "/login" });
  }

  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden bg-background">
      <div className="absolute inset-0" style={{ backgroundImage: "var(--gradient-dawn)" }} />
      <PixelClouds />
      <PixelParticles count={16} />

      <header className="relative z-10 flex items-center justify-between px-5 py-4">
        <span className="font-pixel text-xs text-primary">ORION</span>
        <Button variant="ghost" size="sm" onClick={finish}>
          Skip
        </Button>
      </header>

      <main className="relative z-10 flex flex-1 items-center justify-center px-6">
        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            initial={{ opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -24 }}
            transition={{ duration: 0.35 }}
            className="w-full max-w-md text-center"
          >
            <div className="surface-card pixel-corners mx-auto flex size-36 items-center justify-center">
              <PixelSprite size={9} rows={[...slide.sprite]} />
            </div>
            <h1 className="mt-8 text-2xl font-bold tracking-tight sm:text-3xl">{slide.title}</h1>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{slide.body}</p>
          </motion.div>
        </AnimatePresence>
      </main>

      <footer className="relative z-10 px-6 pb-10">
        <div className="mx-auto flex max-w-md items-center justify-between gap-4">
          <div className="flex gap-1.5">
            {SLIDES.map((_, i) => (
              <span
                key={i}
                className="h-2 pixelated transition-all"
                style={{
                  width: i === step ? 24 : 8,
                  background: i === step ? "var(--primary)" : "var(--border)",
                }}
              />
            ))}
          </div>
          {step < SLIDES.length - 1 ? (
            <Button onClick={() => setStep((s) => s + 1)}>Next</Button>
          ) : (
            <Button onClick={finish}>Get started</Button>
          )}
        </div>
        <p className="mt-6 text-center text-xs text-muted-foreground">
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-primary underline-offset-4 hover:underline">
            Sign in
          </Link>
        </p>
      </footer>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-0 opacity-60">
        <PixelSkyline />
      </div>
    </div>
  );
}
