import { create } from "zustand";
import { persist } from "zustand/middleware";

// Role/identity live in the server-verified auth context (src/hooks/use-auth.ts,
// backed by src/lib/auth-api.ts) — never here. This store is UI preference
// only (theme/sidebar) plus the pre-login marketing tour's "seen it" flag.
type OrionState = {
  onboarded: boolean;
  theme: "light" | "dark";
  sidebarCollapsed: boolean;
  aiOpen: boolean;
  setOnboarded: (v: boolean) => void;
  toggleTheme: () => void;
  setTheme: (t: "light" | "dark") => void;
  toggleSidebar: () => void;
  setAiOpen: (v: boolean) => void;
};

export const useOrion = create<OrionState>()(
  persist(
    (set, get) => ({
      onboarded: false,
      theme: "light",
      sidebarCollapsed: false,
      aiOpen: false,
      setOnboarded: (onboarded) => set({ onboarded }),
      setTheme: (theme) => {
        set({ theme });
        if (typeof document !== "undefined") {
          document.documentElement.classList.toggle("dark", theme === "dark");
          localStorage.setItem("orion-theme", theme);
        }
      },
      toggleTheme: () => get().setTheme(get().theme === "dark" ? "light" : "dark"),
      toggleSidebar: () => set({ sidebarCollapsed: !get().sidebarCollapsed }),
      setAiOpen: (aiOpen) => set({ aiOpen }),
    }),
    { name: "orion-store", partialize: (s) => ({ onboarded: s.onboarded }) },
  ),
);
