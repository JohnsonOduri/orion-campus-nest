import { useMemo, useState } from "react";
import { AlertTriangle, Plus, Trash2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { cn } from "@/lib/utils";
import {
  ENTRY_TYPES,
  WEEK_DAYS,
  blankEntry,
  dayName,
  entryTitle,
  fromMinutes,
  toMinutes,
  type DraftEntry,
  type DraftIssue,
  type TimetableDiff,
} from "@/lib/cr";

type Course = { course_code: string; course_name: string };

const selectClass =
  "h-9 w-full rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

type Placed = { index: number; entry: DraftEntry };

/**
 * Weekly grid of a draft timetable. Days are rows; columns are the distinct
 * period start times, and a period spans the columns it covers (a 2-hour
 * lab spans two). Click a period to edit it, an empty slot to add one.
 * `readOnly` renders the same grid for the admin review.
 */
export function TimetableEditor({
  entries,
  issues,
  onChange,
  courses = [],
  readOnly = false,
  busy = false,
}: {
  entries: DraftEntry[];
  issues: DraftIssue[];
  onChange?: (entries: DraftEntry[]) => void;
  courses?: Course[];
  readOnly?: boolean;
  busy?: boolean;
}) {
  const [editing, setEditing] = useState<{ index: number; entry: DraftEntry } | null>(null);

  const issuesByIndex = useMemo(() => {
    const map = new Map<number, DraftIssue[]>();
    for (const i of issues) {
      if (i.index < 0) continue;
      map.set(i.index, [...(map.get(i.index) ?? []), i]);
    }
    return map;
  }, [issues]);

  const { columns, days, untimed } = useMemo(() => {
    const starts = new Set<number>();
    const dayset = new Set<number>([1, 2, 3, 4, 5, 6]);
    const untimedByDay = new Map<number, Placed[]>();
    entries.forEach((entry, index) => {
      const s = toMinutes(entry.start_time);
      if (entry.day_of_week) dayset.add(entry.day_of_week);
      if (s === null || toMinutes(entry.end_time) === null) {
        const d = entry.day_of_week ?? 0;
        untimedByDay.set(d, [...(untimedByDay.get(d) ?? []), { index, entry }]);
      } else {
        starts.add(s);
      }
    });
    return {
      columns: [...starts].sort((a, b) => a - b),
      days: [...dayset].filter((d) => d >= 1 && d <= 7).sort((a, b) => a - b),
      untimed: untimedByDay,
    };
  }, [entries]);

  const columnEnd = (c: number) => {
    // label: the most common end time among periods starting in this column
    const ends = entries
      .filter((e) => toMinutes(e.start_time) === columns[c])
      .map((e) => toMinutes(e.end_time))
      .filter((m): m is number => m !== null);
    if (!ends.length) return null;
    const counts = new Map<number, number>();
    ends.forEach((m) => counts.set(m, (counts.get(m) ?? 0) + 1));
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0] - b[0])[0]![0];
  };

  function rowCells(day: number) {
    const dayEntries: Placed[] = entries
      .map((entry, index) => ({ entry, index }))
      .filter((p) => p.entry.day_of_week === day && toMinutes(p.entry.start_time) !== null);
    const startsHere = (c: number) => dayEntries.filter((p) => toMinutes(p.entry.start_time) === columns[c]);
    const cells: { col: number; span: number; items: Placed[] }[] = [];
    let c = 0;
    while (c < columns.length) {
      const items = startsHere(c);
      if (!items.length) {
        cells.push({ col: c, span: 1, items: [] });
        c += 1;
        continue;
      }
      const end = Math.max(...items.map((p) => toMinutes(p.entry.end_time) ?? 0));
      let span = 1;
      while (c + span < columns.length && columns[c + span]! < end && !startsHere(c + span).length) span += 1;
      cells.push({ col: c, span, items });
      c += span;
    }
    return cells;
  }

  const openNew = (day: number, col: number | null) => {
    if (readOnly) return;
    const start = col === null ? 9 * 60 + 30 : columns[col]!;
    const next = col !== null && col + 1 < columns.length ? columns[col + 1]! : start + 55;
    const end = col !== null ? (columnEnd(col) ?? next) : start + 55;
    setEditing({ index: -1, entry: blankEntry(day, fromMinutes(start), fromMinutes(end)) });
  };

  const save = (index: number, entry: DraftEntry) => {
    if (!onChange) return;
    const next = [...entries];
    if (index < 0) next.push(entry);
    else next[index] = entry;
    onChange(next);
    setEditing(null);
  };
  const remove = (index: number) => {
    if (!onChange || index < 0) return;
    onChange(entries.filter((_, i) => i !== index));
    setEditing(null);
  };

  const chip = ({ index, entry }: Placed) => {
    const own = issuesByIndex.get(index) ?? [];
    const hasError = own.some((i) => i.severity === "error");
    const hasWarning = !hasError && own.length > 0;
    const activity = !["class", "lab", "tutorial"].includes(String(entry.entry_type));
    return (
      <button
        key={index}
        type="button"
        disabled={readOnly}
        onClick={() => setEditing({ index, entry })}
        title={own.map((i) => i.message).join("\n") || entry.course_name || undefined}
        className={cn(
          "w-full rounded-md border px-2 py-1.5 text-left transition-colors",
          activity ? "border-dashed bg-muted/40" : "bg-secondary/50",
          hasError && "border-destructive bg-destructive/8 ring-1 ring-destructive/40",
          hasWarning && "border-warning bg-warning/10",
          !hasError && !hasWarning && "border-border",
          !readOnly && "hover:border-primary hover:bg-primary/5",
        )}
      >
        <span className="flex items-center gap-1">
          {hasError ? <XCircle className="size-3 shrink-0 text-destructive" /> : null}
          {hasWarning ? <AlertTriangle className="size-3 shrink-0 text-warning-foreground" /> : null}
          <span className="truncate font-mono text-[11px] font-semibold">{entryTitle(entry)}</span>
          {entry.entry_type !== "class" ? (
            <span className="ml-auto shrink-0 font-mono text-[9px] uppercase text-muted-foreground">
              {String(entry.entry_type).replace("_", " ")}
              {entry.lab_batch ? ` B${entry.lab_batch}` : ""}
            </span>
          ) : null}
        </span>
        {entry.faculty_initials.length ? (
          <span className="block truncate font-mono text-[10px] text-muted-foreground">
            {entry.faculty_initials.join(", ")}
          </span>
        ) : null}
        {entry.start_time && entry.end_time ? (
          <span className="block font-mono text-[9px] text-muted-foreground/80">
            {entry.start_time}–{entry.end_time}
          </span>
        ) : null}
      </button>
    );
  };

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[52rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/40">
              <th className="w-28 p-2 text-left font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                Day
              </th>
              {columns.map((m, c) => {
                const end = columnEnd(c);
                return (
                  <th key={m} className="p-2 text-left font-mono text-[11px] text-muted-foreground">
                    {fromMinutes(m)}
                    {end ? `–${fromMinutes(end)}` : ""}
                  </th>
                );
              })}
              {columns.length === 0 ? <th className="p-2" /> : null}
            </tr>
          </thead>
          <tbody>
            {days.map((day) => (
              <tr key={day} className="border-b border-border align-top last:border-0">
                <td className="p-2">
                  <p className="text-sm font-semibold">{dayName(day).slice(0, 3)}</p>
                  <div className="mt-1 space-y-1">{(untimed.get(day) ?? []).map(chip)}</div>
                  {!readOnly ? (
                    <button
                      type="button"
                      onClick={() => openNew(day, null)}
                      className="mt-1 inline-flex items-center gap-1 text-[10px] text-muted-foreground hover:text-primary"
                    >
                      <Plus className="size-3" /> period
                    </button>
                  ) : null}
                </td>
                {rowCells(day).map(({ col, span, items }) => (
                  <td key={col} colSpan={span} className="p-1.5">
                    {items.length ? (
                      <div className="flex flex-col gap-1">{items.map(chip)}</div>
                    ) : readOnly ? (
                      <span className="block py-2 text-center text-xs text-muted-foreground/60">—</span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => openNew(day, col)}
                        aria-label={`Add a period on ${dayName(day)} at ${fromMinutes(columns[col]!)}`}
                        className="grid h-12 w-full place-items-center rounded-md border border-dashed border-transparent text-muted-foreground/40 hover:border-border hover:text-primary"
                      >
                        <Plus className="size-3.5" />
                      </button>
                    )}
                  </td>
                ))}
                {columns.length === 0 ? <td className="p-2 text-xs text-muted-foreground">No periods yet</td> : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(untimed.get(0) ?? []).length ? (
        <div className="rounded-md border border-destructive/40 p-2">
          <p className="mb-1 text-xs font-medium text-destructive">Periods without a day</p>
          <div className="grid gap-1 sm:grid-cols-4">{(untimed.get(0) ?? []).map(chip)}</div>
        </div>
      ) : null}

      {editing ? (
        <EntryDialog
          key={`${editing.index}-${editing.entry.day_of_week}-${editing.entry.start_time}`}
          index={editing.index}
          entry={editing.entry}
          issues={issuesByIndex.get(editing.index) ?? []}
          courses={courses}
          busy={busy}
          onClose={() => setEditing(null)}
          onSave={save}
          onDelete={remove}
        />
      ) : null}
      <datalist id="orion-course-codes">
        {courses.map((c) => (
          <option key={c.course_code} value={c.course_code}>
            {c.course_name}
          </option>
        ))}
      </datalist>
    </div>
  );
}

function EntryDialog({
  index,
  entry,
  issues,
  courses,
  busy,
  onClose,
  onSave,
  onDelete,
}: {
  index: number;
  entry: DraftEntry;
  issues: DraftIssue[];
  courses: Course[];
  busy: boolean;
  onClose: () => void;
  onSave: (index: number, entry: DraftEntry) => void;
  onDelete: (index: number) => void;
}) {
  const [form, setForm] = useState({
    day: entry.day_of_week ?? 1,
    start: entry.start_time ?? "",
    end: entry.end_time ?? "",
    type: String(entry.entry_type || "class"),
    code: entry.course_code ?? "",
    faculty: entry.faculty_initials.join(", "),
    lab: entry.lab_batch ? String(entry.lab_batch) : "",
    note: entry.source_text ?? "",
  });
  const set = (k: keyof typeof form) => (v: string | number) => setForm((f) => ({ ...f, [k]: v }));
  const known = courses.find((c) => c.course_code.replace(/\s/g, "").toUpperCase() === form.code.replace(/\s/g, "").toUpperCase());

  const submit = () =>
    onSave(index, {
      day_of_week: Number(form.day),
      start_time: form.start || null,
      end_time: form.end || null,
      entry_type: form.type,
      course_code: form.code.trim() || null,
      faculty_initials: form.faculty
        .split(/[,/;\s]+/)
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean),
      lab_batch: form.lab ? Number(form.lab) : null,
      source_text: form.note.trim() || null,
    });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{index < 0 ? "Add a period" : "Edit period"}</DialogTitle>
          <DialogDescription>Changes are checked against the course catalogue and faculty directory.</DialogDescription>
        </DialogHeader>
        {issues.length ? (
          <ul className="space-y-1 rounded-md border border-border bg-muted/30 p-2 text-xs">
            {issues.map((i, n) => (
              <li key={n} className={i.severity === "error" ? "text-destructive" : "text-warning-foreground"}>
                {i.severity === "error" ? "✕ " : "⚠ "}
                {i.message}
              </li>
            ))}
          </ul>
        ) : null}
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2 space-y-1.5 sm:col-span-1">
            <Label htmlFor="pe-day">Day</Label>
            <select id="pe-day" className={selectClass} value={form.day} onChange={(e) => set("day")(Number(e.target.value))}>
              {WEEK_DAYS.map((d, i) => (
                <option key={d} value={i + 1}>
                  {d}
                </option>
              ))}
            </select>
          </div>
          <div className="col-span-2 space-y-1.5 sm:col-span-1">
            <Label htmlFor="pe-type">Type</Label>
            <select id="pe-type" className={selectClass} value={form.type} onChange={(e) => set("type")(e.target.value)}>
              {ENTRY_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t.replace("_", " ")}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pe-start">Starts</Label>
            <Input id="pe-start" type="time" value={form.start} onChange={(e) => set("start")(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pe-end">Ends</Label>
            <Input id="pe-end" type="time" value={form.end} onChange={(e) => set("end")(e.target.value)} />
          </div>
          <div className="col-span-2 space-y-1.5">
            <Label htmlFor="pe-code">Course code</Label>
            <Input
              id="pe-code"
              list="orion-course-codes"
              value={form.code}
              onChange={(e) => set("code")(e.target.value.toUpperCase())}
              placeholder="e.g. CSE 311"
            />
            <p className="text-[11px] text-muted-foreground">
              {form.code ? (known ? known.course_name : "Not in the course catalogue yet") : "Leave empty for activities"}
            </p>
          </div>
          <div className="col-span-2 space-y-1.5 sm:col-span-1">
            <Label htmlFor="pe-fac">Faculty initials</Label>
            <Input id="pe-fac" value={form.faculty} onChange={(e) => set("faculty")(e.target.value)} placeholder="ATS, MRC" />
            {entry.faculty_names?.length ? (
              <p className="text-[11px] text-muted-foreground">{entry.faculty_names.join(", ")}</p>
            ) : null}
          </div>
          <div className="col-span-2 space-y-1.5 sm:col-span-1">
            <Label htmlFor="pe-lab">Lab batch (optional)</Label>
            <Input id="pe-lab" inputMode="numeric" value={form.lab} onChange={(e) => set("lab")(e.target.value.replace(/\D/g, ""))} />
          </div>
          <div className="col-span-2 space-y-1.5">
            <Label htmlFor="pe-note">Label (for activities)</Label>
            <Input id="pe-note" value={form.note} onChange={(e) => set("note")(e.target.value)} placeholder="e.g. Coding Club Activities" />
          </div>
        </div>
        <DialogFooter className="gap-2 sm:justify-between">
          {index >= 0 ? (
            <Button variant="outline" className="text-destructive" onClick={() => onDelete(index)} disabled={busy}>
              <Trash2 className="size-4" /> Remove
            </Button>
          ) : (
            <span />
          )}
          <Button onClick={submit} disabled={busy || !form.start || !form.end}>
            {index < 0 ? "Add" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function DiffSummary({ diff, currentCount }: { diff: TimetableDiff; currentCount: number }) {
  if (!currentCount) {
    return <PixelBadge tone="warning">No current timetable found for this class</PixelBadge>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      <PixelBadge tone="success">+{diff.added.length} added</PixelBadge>
      <PixelBadge tone="danger">−{diff.removed.length} removed</PixelBadge>
      <PixelBadge tone="warning">~{diff.changed.length} changed</PixelBadge>
      <PixelBadge tone="muted">{diff.unchanged} unchanged</PixelBadge>
    </div>
  );
}

export function IssueList({ issues, entries }: { issues: DraftIssue[]; entries: DraftEntry[] }) {
  if (!issues.length) return null;
  const errors = issues.filter((i) => i.severity === "error");
  const warnings = issues.filter((i) => i.severity === "warning");
  const where = (i: DraftIssue) => {
    const e = entries[i.index];
    return e ? `${dayName(e.day_of_week).slice(0, 3)} ${e.start_time ?? ""} ${entryTitle(e)}: ` : "";
  };
  return (
    <div className="space-y-2 text-xs">
      {errors.length ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3">
          <p className="mb-1 font-semibold text-destructive">
            {errors.length} to fix before submitting — click the red periods in the grid
          </p>
          <ul className="space-y-0.5">
            {errors.slice(0, 12).map((i, n) => (
              <li key={n}>
                <span className="font-mono">{where(i)}</span>
                {i.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {warnings.length ? (
        <details className="rounded-md border border-warning/40 bg-warning/5 p-3">
          <summary className="cursor-pointer font-semibold">{warnings.length} worth a look (won't block)</summary>
          <ul className="mt-1 space-y-0.5">
            {warnings.map((i, n) => (
              <li key={n}>
                <span className="font-mono">{where(i)}</span>
                {i.message}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
