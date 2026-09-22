import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import {
  LayoutDashboard,
  Sparkles,
  CalendarDays,
  Users,
  UtensilsCrossed,
  Megaphone,
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
  ScrollText,
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
import { useProfile, profileQueryOptions } from "@/hooks/use-profile";
import { apiPost } from "@/lib/api-client";
import { toast } from "sonner";
import { PixelBadge, PixelSprite, SPRITES } from "@/components/pixel/pixel-art";

type NavItem = { to: string; label: string; icon: typeof LayoutDashboard };

const studentNav: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/ai", label: "AI Chat", icon: Sparkles },
  { to: "/timetable", label: "Timetable", icon: CalendarDays },
  { to: "/calendar", label: "Calendar", icon: CalendarRange },
  { to: "/exams", label: "Exams", icon: GraduationCap },
  { to: "/faculty", label: "Faculty", icon: Users },
  { to: "/mess", label: "Mess", icon: UtensilsCrossed },
  { to: "/announcements", label: "Announcements", icon: Megaphone },
];

// Admins manage the institution rather than attending it, so the
// student-facing pages (timetable, exams, mess) are dropped here — the
// routes still exist, they're just not part of an admin's own navigation.
const adminNav: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/ai", label: "AI Chat", icon: Sparkles },
  { to: "/calendar", label: "Calendar", icon: CalendarRange },
  { to: "/faculty", label: "Faculty", icon: Users },
  { to: "/announcements", label: "Announcements", icon: Megaphone },
  { to: "/logs", label: "Logs", icon: ScrollText },
];

const studentBottomNav: NavItem[] = [
  { to: "/dashboard", label: "Home", icon: LayoutDashboard },
  { to: "/timetable", label: "Classes", icon: CalendarDays },
  { to: "/ai", label: "ORION", icon: Sparkles },
  { to: "/mess", label: "Mess", icon: UtensilsCrossed },
  { to: "/profile", label: "Profile", icon: User },
];

// Mirrors adminNav rather than leaving an admin with Classes/Mess shortcuts
// they no longer have in the sidebar.
const adminBottomNav: NavItem[] = [
  { to: "/dashboard", label: "Home", icon: LayoutDashboard },
  { to: "/ai", label: "ORION", icon: Sparkles },
  { to: "/admin", label: "Admin", icon: ShieldCheck },
  { to: "/logs", label: "Logs", icon: ScrollText },
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
  campusItems,
  workspaceItems,
}: {
  collapsed: boolean;
  onNavigate?: (() => void) | undefined;
  campusItems: NavItem[];
  workspaceItems: NavItem[];
}) {
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
          <NavLinks items={campusItems} collapsed={collapsed} onNavigate={onNavigate} />
        </div>
        {workspaceItems.length > 0 && (
          <div>
            {!collapsed && (
              <p className="px-3 pb-2 font-mono text-[10px] tracking-widest text-muted-foreground uppercase">
                Workspaces
              </p>
            )}
            <NavLinks items={workspaceItems} collapsed={collapsed} onNavigate={onNavigate} />
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
    </div>
  );
}

export function AppShell({ children, fill = false }: { children: ReactNode; fill?: boolean }) {
  const { sidebarCollapsed, toggleSidebar, theme, setTheme } = useOrion();
  const [mobileOpen, setMobileOpen] = useState(false);
  const { data: profile } = useProfile();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const isAdmin = profile?.role === "ADMIN";
  // A CR keeps the full student navigation alongside the CR Portal link, so
  // they can move between their own student view and the portal freely.
  const campusItems = isAdmin ? adminNav : studentNav;
  const bottomNav = isAdmin ? adminBottomNav : studentBottomNav;

  const workspaceItems = workspaceNav.filter((item) => {
    if (!profile) return false;
    if (item.to === "/cr") return profile.role === "CR";
    if (item.to === "/admin") return profile.role === "ADMIN";
    return false;
  });

  async function handleSignOut() {
    try {
      await apiPost("/auth/logout");
    } finally {
      queryClient.setQueryData(profileQueryOptions.queryKey, null);
      toast.success("Signed out");
      navigate({ to: "/login" });
    }
  }

  useEffect(() => {
    const isDark = document.documentElement.classList.contains("dark");
    if (isDark !== (theme === "dark")) setTheme(isDark ? "dark" : "light");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="min-h-screen bg-background">
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 hidden border-r border-sidebar-border bg-sidebar transition-[width] duration-300 lg:block",
          sidebarCollapsed ? "w-[72px]" : "w-64",
        )}
      >
        <SidebarBody collapsed={sidebarCollapsed} campusItems={campusItems} workspaceItems={workspaceItems} />
      </aside>

      <div className={cn("transition-[padding] duration-300", sidebarCollapsed ? "lg:pl-[72px]" : "lg:pl-64")}>
        <header className="sticky top-0 z-30 border-b border-border bg-background/80 pt-[env(safe-area-inset-top)] backdrop-blur-md">
          <div className="flex h-14 items-center gap-2 px-3 sm:px-5">
            <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open menu">
                  <Menu className="size-5" />
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="w-72 bg-sidebar p-0">
                <SheetTitle className="sr-only">Navigation</SheetTitle>
                <SidebarBody
                  collapsed={false}
                  onNavigate={() => setMobileOpen(false)}
                  campusItems={campusItems}
                  workspaceItems={workspaceItems}
                />
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
              {profile && (
                <PixelBadge tone="success" className="hidden sm:inline-flex">
                  {profile.role}
                </PixelBadge>
              )}
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                aria-label="Toggle theme"
              >
                {theme === "dark" ? <Sun className="size-5" /> : <Moon className="size-5" />}
              </Button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button aria-label="Account menu" className="ml-1">
                    <Avatar className="size-8 rounded-lg">
                      <AvatarFallback className="rounded-lg bg-primary text-xs font-bold text-primary-foreground">
                        {(profile?.full_name ?? profile?.display_name ?? profile?.email ?? "?")
                          .split(" ")
                          .map((p) => p[0])
                          .slice(0, 2)
                          .join("")
                          .toUpperCase()}
                      </AvatarFallback>
                    </Avatar>
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-52">
                  <DropdownMenuLabel>
                    <p className="truncate text-sm font-semibold">
                      {profile?.full_name ?? profile?.display_name ?? "Account"}
                    </p>
                    <p className="truncate font-mono text-[11px] text-muted-foreground">{profile?.email}</p>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem asChild>
                    <Link to="/profile">Profile</Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <Link to="/settings">Settings</Link>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={handleSignOut}>Sign out</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </header>

        <main
          className={cn(
            "mx-auto w-full max-w-[1400px]",
            fill
              ? // Exactly the space between the header and the mobile bottom nav — the page
                // itself never scrolls; the child manages its own scrolling (AI chat).
                "flex h-[calc(100dvh-3.5rem-env(safe-area-inset-top)-4rem-env(safe-area-inset-bottom))] min-h-0 flex-col sm:px-5 sm:pt-4 md:h-[calc(100dvh-3.5rem-env(safe-area-inset-top))] md:pb-4"
              : "px-3 pt-4 pb-[calc(5.5rem+env(safe-area-inset-bottom))] sm:px-5 md:pb-10",
          )}
        >
          {children}
        </main>
      </div>

      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md md:hidden">
        <div className="grid grid-cols-5">
          {bottomNav.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.to}
                to={item.to}
                className="flex h-16 flex-col items-center justify-center gap-1 text-[11px] text-muted-foreground transition-colors [&.active]:text-primary"
                activeProps={{ className: "active" }}
              >
                <Icon className="size-5" />
                {item.label}
              </Link>
            );
          })}
        </div>
      </nav>
    </div>
  );
}
