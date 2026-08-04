import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Role = "student" | "cr" | "admin";

type OrionState = {
  role: Role;
  userName: string;
  onboarded: boolean;
  theme: "light" | "dark";
  sidebarCollapsed: boolean;
  aiOpen: boolean;
  setRole: (r: Role) => void;
  setOnboarded: (v: boolean) => void;
  toggleTheme: () => void;
  setTheme: (t: "light" | "dark") => void;
  toggleSidebar: () => void;
  setAiOpen: (v: boolean) => void;
};

export const useOrion = create<OrionState>()(
  persist(
    (set, get) => ({
      role: "student",
      userName: "Aarav Menon",
      onboarded: false,
      theme: "light",
      sidebarCollapsed: false,
      aiOpen: false,
      setRole: (role) => set({ role }),
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
    { name: "orion-store", partialize: (s) => ({ role: s.role, onboarded: s.onboarded }) },
  ),
);
