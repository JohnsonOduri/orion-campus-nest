import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { PixelBadge, PixelMascot } from "@/components/pixel/pixel-art";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export function PageHeader({
  title,
  subtitle,
  actions,
  badge,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  badge?: string;
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {badge ? <PixelBadge className="mb-2">{badge}</PixelBadge> : null}
        <h1 className="truncate text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1>
        {subtitle ? <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}

export function SectionCard({
  title,
  description,
  action,
  children,
  className,
  contentClassName,
}: {
  title?: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
}) {
  return (
    <section className={cn("surface-card overflow-hidden", className)}>
      {title ? (
        <header className="flex items-start justify-between gap-3 border-b border-border px-4 py-3 sm:px-5">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold">{title}</h2>
            {description ? (
              <p className="mt-0.5 truncate text-xs text-muted-foreground">{description}</p>
            ) : null}
          </div>
          {action}
        </header>
      ) : null}
      <div className={cn("p-4 sm:p-5", contentClassName)}>{children}</div>
    </section>
  );
}

export function StatCard({
  label,
  value,
  suffix,
  delta,
  icon,
  tone = "primary",
}: {
  label: string;
  value: string | number;
  suffix?: string;
  delta?: string;
  icon?: ReactNode;
  tone?: "primary" | "accent" | "warning" | "success";
}) {
  const tones: Record<string, string> = {
    primary: "bg-primary/10 text-primary",
    accent: "bg-accent/15 text-accent",
    warning: "bg-warning/18 text-warning-foreground",
    success: "bg-success/12 text-success",
  };
  return (
    <div className="surface-card hover-lift pixel-corners p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        {icon ? (
          <span className={cn("grid size-8 place-items-center rounded-lg", tones[tone])}>{icon}</span>
        ) : null}
      </div>
      <p className="mt-3 font-mono text-2xl font-bold tracking-tight">
        {value}
        {suffix ? <span className="text-base text-muted-foreground">{suffix}</span> : null}
      </p>
      {delta ? <p className="mt-1 text-xs font-medium text-success">{delta} this week</p> : null}
    </div>
  );
}

export function EmptyState({
  title,
  message,
  actionLabel,
  onAction,
}: {
  title: string;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-12 text-center">
      <PixelMascot size={5} />
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="max-w-xs text-xs text-muted-foreground">{message}</p>
      {actionLabel ? (
        <Button size="sm" onClick={onAction}>
          {actionLabel}
        </Button>
      ) : null}
    </div>
  );
}

export function CardSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="surface-card shimmer space-y-3 p-4">
      <Skeleton className="h-4 w-1/3" />
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-3 w-full" />
      ))}
    </div>
  );
}
