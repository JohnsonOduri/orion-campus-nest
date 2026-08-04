import { useEffect, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { motion } from "framer-motion";
import {
  PixelBirds,
  PixelClouds,
  PixelLoadingBar,
  PixelParticles,
  PixelSkyline,
  PixelMascot,
} from "@/components/pixel/pixel-art";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "ORION Campus Companion — IIIT Kottayam" },
      {
        name: "description",
        content:
          "Booting ORION, the intelligent campus assistant for IIIT Kottayam — timetable, mess, faculty, exams and AI answers.",
      },
      { property: "og:title", content: "ORION Campus Companion" },
      { property: "og:description", content: "Your Intelligent Campus Assistant for IIIT Kottayam." },
    ],
  }),
  component: Splash,
});

const MESSAGES = [
  "Preparing workspace…",
  "Loading campus data…",
  "Initializing AI…",
  "Connecting to ORION…",
  "Syncing timetable…",
  "Fetching announcements…",
];

function Splash() {
  const navigate = useNavigate();
  const [progress, setProgress] = useState(6);
  const [msg, setMsg] = useState(0);

  useEffect(() => {
    const p = setInterval(() => setProgress((v) => Math.min(100, v + 4)), 90);
    const m = setInterval(() => setMsg((v) => (v + 1) % MESSAGES.length), 900);
    return () => {
      clearInterval(p);
      clearInterval(m);
    };
  }, []);

  useEffect(() => {
    if (progress >= 100) {
      const t = setTimeout(() => navigate({ to: "/onboarding" }), 500);
      return () => clearTimeout(t);
    }
    return;
  }, [progress, navigate]);

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-background px-6">
      <div className="absolute inset-0" style={{ backgroundImage: "var(--gradient-dawn)" }} />
      <PixelClouds />
      <PixelBirds />
      <PixelParticles count={24} />

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="relative z-10 flex flex-col items-center text-center"
      >
        <PixelMascot size={8} />
        <h1 className="mt-6 font-pixel text-xl text-primary sm:text-2xl">ORION</h1>
        <p className="mt-3 text-sm font-medium text-muted-foreground">Your Intelligent Campus Assistant</p>
        <p className="mt-1 font-mono text-[11px] text-muted-foreground">IIIT KOTTAYAM</p>

        <div className="mt-8 w-[min(22rem,80vw)]">
          <PixelLoadingBar value={progress} />
          <div className="mt-3 flex items-center justify-between font-mono text-[11px] text-muted-foreground">
            <span>{MESSAGES[msg]}</span>
            <span>{progress}%</span>
          </div>
        </div>
      </motion.div>

      <div className="absolute inset-x-0 bottom-0 z-0 opacity-90">
        <PixelSkyline />
      </div>
      <p className="absolute bottom-2 z-10 font-mono text-[10px] text-primary-foreground/80">v2.4.0 · build 2026.08</p>
    </div>
  );
}
