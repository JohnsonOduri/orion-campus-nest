// Dates in ORION are institute-local (IST). Formatting helpers shared by the
// portal pages so every page phrases dates the same way the assistant does.

const IST_OFFSET_MIN = 330;

export function todayIST(): Date {
  const now = new Date();
  const ist = new Date(now.getTime() + (now.getTimezoneOffset() + IST_OFFSET_MIN) * 60_000);
  return new Date(ist.getFullYear(), ist.getMonth(), ist.getDate());
}

export function parseDate(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y!, (m ?? 1) - 1, d ?? 1);
}

export function daysFromToday(iso: string): number {
  return Math.round((parseDate(iso).getTime() - todayIST().getTime()) / 86_400_000);
}

export function formatDate(iso: string, opts: { weekday?: boolean; year?: boolean } = {}): string {
  const d = parseDate(iso);
  return d.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    ...(opts.weekday ? { weekday: "short" } : {}),
    ...(opts.year || d.getFullYear() !== todayIST().getFullYear() ? { year: "numeric" } : {}),
  });
}

export function relativeDays(iso: string): string {
  const n = daysFromToday(iso);
  if (n === 0) return "today";
  if (n === 1) return "tomorrow";
  if (n === -1) return "yesterday";
  return n > 0 ? `in ${n} days` : `${-n} days ago`;
}

export function formatTime(t: string | null | undefined): string {
  if (!t) return "";
  const [h, m] = t.split(":").map(Number);
  const suffix = (h ?? 0) < 12 ? "AM" : "PM";
  return `${(h ?? 0) % 12 || 12}:${String(m ?? 0).padStart(2, "0")} ${suffix}`;
}
