import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { PixelMascot, PixelParticles, PixelLoadingBar } from "@/components/pixel/pixel-art";

// Shown between a successful login/register and the destination route
// actually rendering — beforeLoad on /admin and /cr does a real network
// round trip (GET /auth/me) before the page mounts, so without this the
// transition is a silent gap rather than a signal that something is
// happening.
export function RedirectOverlay({ label = "Setting up your workspace…" }: { label?: string }) {
  const [progress, setProgress] = useState(12);

  useEffect(() => {
    // Eases toward ~90% and holds — it never claims to finish, since we
    // don't know exactly when navigation will complete; the real page swap
    // is what ends this component's lifetime, not the bar reaching 100.
    const id = setInterval(() => {
      setProgress((p) => (p < 90 ? p + (90 - p) * 0.18 : p));
    }, 120);
    return () => clearInterval(id);
  }, []);

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-6 bg-background"
      >
        <PixelParticles count={16} />
        <motion.div
          initial={{ scale: 0.85, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.3 }}
          className="relative z-10 flex flex-col items-center gap-5"
        >
          <motion.div
            animate={{ y: [0, -6, 0] }}
            transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
          >
            <PixelMascot size={7} />
          </motion.div>
          <div className="text-center">
            <p className="font-pixel text-[11px] text-primary">ORION</p>
            <p className="mt-2 text-sm text-muted-foreground">{label}</p>
          </div>
          <PixelLoadingBar value={progress} className="w-56" />
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
