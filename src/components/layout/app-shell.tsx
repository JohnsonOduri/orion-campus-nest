import { useEffect, useState, type ReactNode } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import {
  LayoutDashboard,
  Sparkles,
  CalendarDays,
  BookOpen,
  Users,
  UtensilsCrossed,
  Megaphone,
  Bell,
  User,
  Settings,
  Search,
  Menu,
  Moon,
  Sun,
  PanelLeftClose,
  PanelLeft,
  GraduationCap,
  Upload,
  ShieldCheck,
  CalendarRange,
  FileText,
  PartyPopper,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { useOrion } from "@/store/orion";
import { useAuth } from "@/hooks/use-auth";
import { requestCrAccess } from "@/lib/cr-request-api";
import type { AppRole } from "@/lib/auth-api";
import { AuthGate } from "@/components/auth/auth-gate";
import { FloatingAiButton } from "@/components/ai/ai-chat";
import { PixelBadge, PixelParticles, PixelSprite, SPRITES } from "@/components/pixel/pixel-art";
import { toast } from "sonner";

type NavItem = { to: string; label: string; icon: typeof LayoutDashboard };

const studentNav: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/ai", label: "AI Chat", icon: Sparkles },
  { to: "/timetable", label: "Timetable", icon: CalendarDays },
  { to: "/calendar", label: "Calendar", icon: CalendarRange },
  { to: "/exams", label: "Exams", icon: GraduationCap },
  { to: "/courses", label: "Courses", icon: BookOpen },
  { to: "/faculty", label: "Faculty", icon: Users },
  { to: "/clubs", label: "Clubs & Events", icon: PartyPopper },
  { to: "/mess", label: "Mess", icon: UtensilsCrossed },
  { to: "/documents", label: "Documents", icon: FileText },
  { to: "/announcements", label: "Announcements", icon: Megaphone },
  { to: "/notifications", label: "Notifications", icon: Bell },
];

const bottomNav: NavItem[] = [
  { to: "/dashboard", label: "Home", icon: LayoutDashboard },
  { to: "/timetable", label: "Classes", icon: CalendarDays },
  { to: "/mess", label: "Mess", icon: UtensilsCrossed },
  { to: "/profile", label: "Profile", icon: User },
];

const workspaceNav: NavItem[] = [
  { to: "/cr", label: "CR Portal", icon: Upload },
  { to: "/admin", label: "Admin Portal", icon: ShieldCheck },
];

const accountNav: NavItem[] = [
  { to: "/profile", label: "Profile", icon: User },
  { to: "/settings", label: "Settings", icon: Settings },
];

function NavLinks({ items, collapsed, onNavigate }: { items: NavItem[]; collapsed: boolean; onNavigate?: (() => void) | undefined }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  return (
    <nav className="space-y-1">
      {items.map((item) => {
        const active = pathname === item.to;
        const Icon = item.icon;
        return (
          <Link
            key={item.to}
            to={item.to}
            onClick={onNavigate}
            className={cn(
              "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all",
              active
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
              collapsed && "justify-center px-2",
            )}
            title={collapsed ? item.label : undefined}
          >
            {active ? (
              <span className="absolute top-1/2 left-0 h-5 w-1 -translate-y-1/2 pixelated bg-primary" />
            ) : null}
            <Icon className="size-4 shrink-0" />
            {!collapsed && <span className="truncate">{item.label}</span>}
          </Link>
        );
      })}
    </nav>
  );
}

function SidebarBody({
  collapsed,
  onNavigate,
  role,
}: {
  collapsed: boolean;
  onNavigate?: (() => void) | undefined;
  role: AppRole | null;
}) {
  const visibleWorkspaceNav = workspaceNav.filter((item) => {
    if (item.to === "/cr") return role === "CR" || role === "ADMIN";
    if (item.to === "/admin") return role === "ADMIN";
    return true;
  });
  return (
    <div className="flex h-full flex-col">
      <div className={cn("flex items-center gap-2.5 px-4 py-4", collapsed && "justify-center px-2")}>
        <PixelSprite size={3} rows={[...SPRITES.mascot]} />
        {!collapsed && (
          <div className="min-w-0">
            <p className="truncate text-sm font-bold tracking-tight">ORION</p>
            <p className="truncate font-mono text-[10px] text-muted-foreground">IIIT KOTTAYAM</p>
          </div>
        )}
      </div>
      <div className="scrollbar-thin flex-1 space-y-5 overflow-y-auto px-3 pb-4">
        <div>
          {!collapsed && (
            <p className="px-3 pb-2 font-mono text-[10px] tracking-widest text-muted-foreground uppercase">
              Campus
            </p>
          )}
          <NavLinks items={studentNav} collapsed={collapsed} onNavigate={onNavigate} />
        </div>
        {visibleWorkspaceNav.length > 0 && (
          <div>
            {!collapsed && (
              <p className="px-3 pb-2 font-mono text-[10px] tracking-widest text-muted-foreground uppercase">
                Workspaces
              </p>
            )}
            <NavLinks items={visibleWorkspaceNav} collapsed={collapsed} onNavigate={onNavigate} />
          </div>
        )}
        <div>
          {!collapsed && (
            <p className="px-3 pb-2 font-mono text-[10px] tracking-widest text-muted-foreground uppercase">
              Account
            </p>
          )}
          <NavLinks items={accountNav} collapsed={collapsed} onNavigate={onNavigate} />
        </div>
      </div>
      {!collapsed && (
        <div className="relative m-3 overflow-hidden rounded-xl border border-border bg-secondary/50 p-3">
          <PixelParticles count={8} />
          <p className="relative text-xs font-semibold">Semester 6 progress</p>
          <p className="relative mt-1 font-mono text-[11px] text-muted-foreground">118 / 160 credits</p>
          <div className="relative mt-2 h-1.5 w-full overflow-hidden rounded-full bg-background">
            <div className="h-full gradient-campus" style={{ width: "74%" }} />
          </div>
        </div>
      )}
    </div>
  );
}

function initialsOf(name: string | null, email: string | null): string {
  if (name) {
    const parts = name.trim().split(/\s+/);
    return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "U";
  }
  return (email?.[0] ?? "U").toUpperCase();
}

function AppShellInner({ children, allow }: { children: ReactNode; allow: AppRole[] }) {
  const { sidebarCollapsed, toggleSidebar, theme, setTheme } = useOrion();
  const { context, signOut, refresh } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const isDark = document.documentElement.classList.contains("dark");
    if (isDark !== (theme === "dark")) setTheme(isDark ? "dark" : "light");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const role = context?.role ?? null;
  const canSeeBothPortals = role === "ADMIN";

  async function onRequestCrAccess() {
    try {
      await requestCrAccess();
      toast.success("CR access requested — an admin will review it.");
      await refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not submit the request.");
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 hidden border-r border-sidebar-border bg-sidebar transition-[width] duration-300 lg:block",
          sidebarCollapsed ? "w-[72px]" : "w-64",
        )}
      >
        <SidebarBody collapsed={sidebarCollapsed} role={role} />
      </aside>

      <div className={cn("transition-[padding] duration-300", sidebarCollapsed ? "lg:pl-[72px]" : "lg:pl-64")}>
        <header className="sticky top-0 z-30 border-b border-border bg-background/80 backdrop-blur-md">
          <div className="flex h-14 items-center gap-2 px-3 sm:px-5">
            <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open menu">
                  <Menu className="size-5" />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="w-72 bg-sidebar p-0">
                <SheetTitle className="sr-only">Navigation</SheetTitle>
                <SidebarBody collapsed={false} onNavigate={() => setMobileOpen(false)} role={role} />
              </SheetContent>
            </Sheet>

            <Button
              variant="ghost"
              size="icon"
              className="hidden lg:inline-flex"
              onClick={toggleSidebar}
              aria-label="Toggle sidebar"
            >
              {sidebarCollapsed ? <PanelLeft className="size-5" /> : <PanelLeftClose className="size-5" />}
            </Button>

            <Link
              to="/search"
              className="flex h-9 flex-1 items-center gap-2 rounded-lg border border-border bg-card px-3 text-sm text-muted-foreground transition-colors hover:border-primary/50 md:max-w-md"
            >
              <Search className="size-4" />
              <span className="truncate">Search campus…</span>
              <kbd className="ml-auto hidden rounded border border-border px-1.5 font-mono text-[10px] md:inline">
                ⌘K
              </kbd>
            </Link>

            <div className="ml-auto flex items-center gap-1">
              <PixelBadge tone="success" className="hidden sm:inline-flex">
                {role}
              </PixelBadge>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                aria-label="Toggle theme"
              >
                {theme === "dark" ? <Sun className="size-5" /> : <Moon className="size-5" />}
              </Button>
              <Link to="/notifications" aria-label="Notifications">
                <Button variant="ghost" size="icon" className="relative">
                  <Bell className="size-5" />
                  <span className="absolute top-2 right-2 size-2 pixelated bg-destructive" />
                </Button>
              </Link>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button aria-label="Account menu" className="ml-1">
                    <Avatar className="size-8 rounded-lg">
                      <AvatarFallback className="rounded-lg bg-primary text-xs font-bold text-primary-foreground">
                        {initialsOf(context?.fullName ?? null, context?.email ?? null)}
                      </AvatarFallback>
                    </Avatar>
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <DropdownMenuLabel>
                    <p className="truncate text-sm font-semibold">{context?.fullName ?? "Account"}</p>
                    <p className="truncate font-mono text-[11px] text-muted-foreground">{context?.email}</p>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem asChild>
                    <Link to="/profile">Profile</Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <Link to="/settings">Settings</Link>
                  </DropdownMenuItem>
                  {canSeeBothPortals && (
                    <DropdownMenuItem asChild>
                      <Link to="/role">Switch portal</Link>
                    </DropdownMenuItem>
                  )}
                  {role === "STUDENT" && context?.crRequestStatus === "none" && (
                    <DropdownMenuItem onSelect={onRequestCrAccess}>Request CR access</DropdownMenuItem>
                  )}
                  {role === "STUDENT" && context?.crRequestStatus === "pending" && (
                    <DropdownMenuItem disabled>CR access requested — pending</DropdownMenuItem>
                  )}
                  {role === "STUDENT" && context?.crRequestStatus === "rejected" && (
                    <DropdownMenuItem onSelect={onRequestCrAccess}>Request CR access again</DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onSelect={() => void signOut()}>Sign out</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1400px] px-3 pt-4 pb-28 sm:px-5 md:pb-10">{children}</main>
      </div>

      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-background/95 backdrop-blur-md md:hidden">
        <div className="grid grid-cols-4">
          {bottomNav.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.to}
                to={item.to}
                className="flex flex-col items-center gap-1 py-2.5 text-[11px] text-muted-foreground transition-colors [&.active]:text-primary"
                activeProps={{ className: "active" }}
              >
                <Icon className="size-5" />
                {item.label}
              </Link>
            );
          })}
        </div>
      </nav>

      <FloatingAiButton />
    </div>
  );
}

const DEFAULT_ALLOW: AppRole[] = ["STUDENT", "CR", "ADMIN"];

/**
 * `allow` restricts which roles may view this page (ADMIN always passes —
 * see AuthGate). Defaults to any signed-in role, which is correct for every
 * page except /cr (["CR"]) and /admin (["ADMIN"]).
 */
export function AppShell({ children, allow = DEFAULT_ALLOW }: { children: ReactNode; allow?: AppRole[] }) {
  return (
    <AuthGate allow={allow}>
      <AppShellInner allow={allow}>{children}</AppShellInner>
    </AuthGate>
  );
}
