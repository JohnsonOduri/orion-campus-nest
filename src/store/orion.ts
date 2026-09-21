import { create } from "zustand";
import { persist } from "zustand/middleware";

// Role and onboarding status now come from GET /auth/me (see
// src/hooks/use-profile.ts), backed by real RLS/is_admin() checks — this
// store only holds UI-only preferences that have no server-side meaning.
type OrionState = {
  theme: "light" | "dark";
  sidebarCollapsed: boolean;
  aiOpen: boolean;
  toggleTheme: () => void;
  setTheme: (t: "light" | "dark") => void;
  toggleSidebar: () => void;
  setAiOpen: (v: boolean) => void;
};

export const useOrion = create<OrionState>()(
  persist(
    (set, get) => ({
      theme: "light",
      sidebarCollapsed: false,
      aiOpen: false,
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
    { name: "orion-store", partialize: (s) => ({ sidebarCollapsed: s.sidebarCollapsed }) },
  ),
);
