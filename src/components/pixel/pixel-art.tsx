import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

/* ---------------- Pixel primitives ---------------- */

export function PixelSprite({
  rows,
  size = 4,
  className,
  colors,
}: {
  rows: string[];
  size?: number;
  className?: string;
  colors?: Record<string, string>;
}) {
  const palette: Record<string, string> = {
    "#": "var(--primary)",
    "*": "var(--accent)",
    "+": "var(--leaf)",
    o: "var(--warning)",
    x: "var(--foreground)",
    w: "var(--card)",
    ...colors,
  };
  return (
    <div className={cn("inline-grid pixelated", className)} aria-hidden="true">
      {rows.map((row, y) => (
        <div key={y} className="flex">
          {row.split("").map((c, x) => (
            <span
              key={x}
              style={{
                width: size,
                height: size,
                background: c === "." || c === " " ? "transparent" : palette[c] ?? c,
              }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export const SPRITES = {
  mascot: [
    "..#####..",
    ".#*****#.",
    ".#x***x#.",
    ".#*****#.",
    ".#*ooo*#.",
    "..#####..",
    "...#.#...",
    "..##.##..",
  ],
  bird: ["..#..#..", ".###.###", "..#..#.."],
  tree: ["..***..", ".*****.", "*******", ".*****.", "..***..", "...#...", "...#..."],
  bench: ["........", "########", "........", "#......#", "#......#"],
  book: [".#####.", "#*****#", "#*w*w*#", "#*****#", ".#####."],
  trophy: [".ooooo.", ".ooooo.", "..ooo..", "...o...", ".#####."],
  star: ["...o...", "..ooo..", "oooooooo", "..ooo..", ".o...o."],
  bolt: ["...oo..", "..oo...", ".ooooo.", "...oo..", "..oo..."],
} as const;

/* ---------------- Decorative scenery ---------------- */

export function PixelClouds({ className }: { className?: string }) {
  const clouds = [
    { top: "8%", dur: 46, size: 5, delay: 0 },
    { top: "22%", dur: 64, size: 3, delay: -12 },
    { top: "38%", dur: 80, size: 4, delay: -30 },
  ];
  return (
    <div className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)} aria-hidden="true">
      {clouds.map((c, i) => (
        <div
          key={i}
          className="animate-drift absolute opacity-70"
          style={{ top: c.top, animationDuration: `${c.dur}s`, animationDelay: `${c.delay}s` }}
        >
          <PixelSprite
            size={c.size}
            rows={["..####..", ".######.", "########"]}
            colors={{ "#": "color-mix(in oklab, var(--card) 88%, var(--sky))" }}
          />
        </div>
      ))}
    </div>
  );
}

export function PixelBirds({ className }: { className?: string }) {
  return (
    <div className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)} aria-hidden="true">
      {[
        { top: "14%", dur: 28, delay: 0 },
        { top: "26%", dur: 36, delay: -8 },
      ].map((b, i) => (
        <div
          key={i}
          className="animate-drift absolute"
          style={{ top: b.top, animationDuration: `${b.dur}s`, animationDelay: `${b.delay}s` }}
        >
          <div className="animate-flap">
            <PixelSprite size={3} rows={[...SPRITES.bird]} colors={{ "#": "var(--muted-foreground)" }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function PixelParticles({ count = 18, className }: { count?: number; className?: string }) {
  const dots = Array.from({ length: count }, (_, i) => ({
    left: (i * 37) % 100,
    top: (i * 61) % 100,
    delay: (i % 7) * 0.45,
    size: 3 + (i % 3),
  }));
  return (
    <div className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)} aria-hidden="true">
      {dots.map((d, i) => (
        <span
          key={i}
          className="animate-float absolute pixelated"
          style={{
            left: `${d.left}%`,
            top: `${d.top}%`,
            width: d.size,
            height: d.size,
            background: i % 3 === 0 ? "var(--accent)" : "var(--leaf)",
            opacity: 0.55,
            animationDelay: `${d.delay}s`,
            animationDuration: `${3.4 + (i % 4) * 0.7}s`,
          }}
        />
      ))}
    </div>
  );
}

/** Pixel campus skyline: buildings, trees, benches, pathway, grass. */
export function PixelSkyline({ className }: { className?: string }) {
  const buildings = [
    { w: 34, h: 54, windows: 6 },
    { w: 22, h: 38, windows: 4 },
    { w: 46, h: 74, windows: 9 },
    { w: 26, h: 46, windows: 4 },
    { w: 38, h: 62, windows: 6 },
    { w: 20, h: 34, windows: 3 },
  ];
  return (
    <div className={cn("pointer-events-none relative w-full select-none", className)} aria-hidden="true">
      <div className="flex items-end justify-center gap-2">
        {buildings.map((b, i) => (
          <div
            key={i}
            className="relative pixelated"
            style={{
              width: b.w,
              height: b.h,
              background: i % 2 ? "var(--primary)" : "color-mix(in oklab, var(--primary) 78%, var(--accent))",
            }}
          >
            <div className="absolute inset-x-1 top-1 grid grid-cols-2 gap-1">
              {Array.from({ length: b.windows }).map((_, w) => (
                <span
                  key={w}
                  className={cn("h-1.5 w-full pixelated", w % 4 === 0 && "animate-blink")}
                  style={{ background: "var(--warning)", opacity: 0.85 }}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-0 flex items-end justify-center gap-6">
        <PixelSprite size={3} rows={[...SPRITES.tree]} />
        <PixelSprite size={3} rows={[...SPRITES.bench]} colors={{ "#": "var(--muted-foreground)" }} />
        <PixelSprite size={3} rows={[...SPRITES.tree]} />
      </div>
      <div className="h-2 w-full pixelated" style={{ background: "var(--leaf)" }} />
      <div className="h-1.5 w-full pixelated" style={{ background: "color-mix(in oklab, var(--leaf) 65%, var(--primary))" }} />
    </div>
  );
}

/* ---------------- Pixel UI bits ---------------- */

export function PixelLoadingBar({ value, className }: { value: number; className?: string }) {
  const blocks = 20;
  const filled = Math.round((value / 100) * blocks);
  return (
    <div className={cn("flex gap-[3px] p-1", className)} aria-hidden="true">
      {Array.from({ length: blocks }).map((_, i) => (
        <span
          key={i}
          className="h-3 flex-1 pixelated transition-colors duration-200"
          style={{
            background:
              i < filled ? "var(--primary)" : "color-mix(in oklab, var(--muted-foreground) 22%, transparent)",
          }}
        />
      ))}
    </div>
  );
}

export function PixelBadge({
  children,
  tone = "primary",
  className,
}: {
  children: ReactNode;
  tone?: "primary" | "warning" | "danger" | "success" | "muted";
  className?: string;
}) {
  const tones: Record<string, string> = {
    primary: "bg-primary/12 text-primary",
    warning: "bg-warning/18 text-warning-foreground",
    danger: "bg-destructive/12 text-destructive",
    success: "bg-success/14 text-success",
    muted: "bg-muted text-muted-foreground",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-1 font-mono text-[10px] font-bold tracking-wide uppercase",
        "rounded-[2px] shadow-[2px_2px_0_0_color-mix(in_oklab,currentColor_28%,transparent)]",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function PixelDivider({ className }: { className?: string }) {
  return (
    <div className={cn("flex gap-[3px] overflow-hidden", className)} aria-hidden="true">
      {Array.from({ length: 64 }).map((_, i) => (
        <span
          key={i}
          className="h-[3px] w-[3px] shrink-0 pixelated"
          style={{ background: i % 3 === 0 ? "var(--accent)" : "var(--border)" }}
        />
      ))}
    </div>
  );
}

export function PixelMascot({ size = 6, className }: { size?: number; className?: string }) {
  return (
    <div className={cn("animate-float", className)}>
      <PixelSprite size={size} rows={[...SPRITES.mascot]} />
    </div>
  );
}
