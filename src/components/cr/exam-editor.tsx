import { AlertTriangle, Plus, Trash2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { cn } from "@/lib/utils";
import type { DraftIssue, ExamDiff, ExamEntry } from "@/lib/cr";

type Course = { course_code: string; course_name: string };

function weekday(d: string | null): string {
  if (!d) return "";
  const dt = new Date(`${d}T00:00`);
  return Number.isNaN(dt.getTime()) ? "" : dt.toLocaleDateString(undefined, { weekday: "short" });
}

/**
 * Editable exam schedule: one row per exam, grouped visually by date.
 * Rows with problems are outlined (red blocks submitting, amber doesn't).
 * `readOnly` renders the same table for the admin review.
 */
export function ExamEditor({
  entries,
  issues,
  onChange,
  courses = [],
  readOnly = false,
  showDepartment = false,
}: {
  entries: ExamEntry[];
  issues: DraftIssue[];
  onChange?: (entries: ExamEntry[]) => void;
  courses?: Course[];
  readOnly?: boolean;
  showDepartment?: boolean;
}) {
  const byIndex = new Map<number, DraftIssue[]>();
  for (const i of issues) if (i.index >= 0) byIndex.set(i.index, [...(byIndex.get(i.index) ?? []), i]);

  const update = (index: number, patch: Partial<ExamEntry>) =>
    onChange?.(entries.map((e, i) => (i === index ? { ...e, ...patch } : e)));
  const remove = (index: number) => onChange?.(entries.filter((_, i) => i !== index));
  const add = () => {
    const last = entries[entries.length - 1];
    onChange?.([
      ...entries,
      {
        exam_date: last?.exam_date ?? null,
        start_time: last?.start_time ?? "09:30",
        end_time: last?.end_time ?? "12:30",
        course_code: "",
        course_name: "",
        department: last?.department ?? null,
        alt_group: null,
      },
    ]);
  };

  const order = entries
    .map((e, i) => ({ e, i }))
    .sort((a, b) => `${a.e.exam_date ?? "9"}${a.e.start_time ?? ""}`.localeCompare(`${b.e.exam_date ?? "9"}${b.e.start_time ?? ""}`));

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[46rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/40 text-left font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
              <th className="p-2">Date</th>
              <th className="p-2">Starts</th>
              <th className="p-2">Ends</th>
              <th className="p-2">Course code</th>
              <th className="p-2">Course</th>
              {showDepartment ? <th className="p-2">Department</th> : null}
              {!readOnly ? <th className="w-10 p-2" /> : null}
            </tr>
          </thead>
          <tbody>
            {order.map(({ e, i }) => {
              const own = byIndex.get(i) ?? [];
              const error = own.some((x) => x.severity === "error");
              const warn = !error && own.length > 0;
              return (
                <tr
                  key={i}
                  title={own.map((x) => x.message).join("\n") || undefined}
                  className={cn(
                    "border-b border-border align-top last:border-0",
                    error && "bg-destructive/5",
                    warn && "bg-warning/5",
                  )}
                >
                  <td className="p-1.5">
                    {readOnly ? (
                      <span className="whitespace-nowrap font-mono text-xs">
                        {weekday(e.exam_date)} {e.exam_date}
                      </span>
                    ) : (
                      <div className="flex items-center gap-1">
                        <Input
                          type="date"
                          className="h-8 w-36 text-xs"
                          value={e.exam_date ?? ""}
                          onChange={(ev) => update(i, { exam_date: ev.target.value || null })}
                        />
                        <span className="w-8 font-mono text-[10px] text-muted-foreground">{weekday(e.exam_date)}</span>
                      </div>
                    )}
                  </td>
                  <td className="p-1.5">
                    {readOnly ? (
                      <span className="font-mono text-xs">{e.start_time}</span>
                    ) : (
                      <Input type="time" className="h-8 w-24 text-xs" value={e.start_time ?? ""}
                        onChange={(ev) => update(i, { start_time: ev.target.value || null })} />
                    )}
                  </td>
                  <td className="p-1.5">
                    {readOnly ? (
                      <span className="font-mono text-xs">{e.end_time}</span>
                    ) : (
                      <Input type="time" className="h-8 w-24 text-xs" value={e.end_time ?? ""}
                        onChange={(ev) => update(i, { end_time: ev.target.value || null })} />
                    )}
                  </td>
                  <td className="p-1.5">
                    {readOnly ? (
                      <span className="font-mono text-xs font-semibold">{e.course_code}</span>
                    ) : (
                      <Input
                        list="orion-exam-course-codes"
                        className="h-8 w-28 font-mono text-xs uppercase"
                        value={e.course_code ?? ""}
                        onChange={(ev) => {
                          const code = ev.target.value.toUpperCase();
                          const known = courses.find(
                            (c) => c.course_code.replace(/\s/g, "") === code.replace(/\s/g, ""),
                          );
                          update(i, { course_code: code, ...(known ? { course_name: known.course_name } : {}) });
                        }}
                      />
                    )}
                  </td>
                  <td className="p-1.5">
                    <div className="flex items-center gap-1.5">
                      {error ? <XCircle className="size-3.5 shrink-0 text-destructive" /> : null}
                      {warn ? <AlertTriangle className="size-3.5 shrink-0 text-warning-foreground" /> : null}
                      {readOnly ? (
                        <span className="text-xs">{e.course_name}</span>
                      ) : (
                        <Input className="h-8 min-w-48 text-xs" value={e.course_name ?? ""}
                          onChange={(ev) => update(i, { course_name: ev.target.value })} />
                      )}
                      {e.alt_group ? (
                        <PixelBadge tone="muted" className="shrink-0">
                          or {e.alt_group.split("/").filter((c) => c.replace(/\s/g, "") !== (e.course_code ?? "").replace(/\s/g, "")).join("/")}
                        </PixelBadge>
                      ) : null}
                    </div>
                  </td>
                  {showDepartment ? (
                    <td className="p-1.5 text-[11px] text-muted-foreground">{e.department ?? "—"}</td>
                  ) : null}
                  {!readOnly ? (
                    <td className="p-1.5">
                      <Button size="icon" variant="ghost" className="size-8" aria-label="Remove exam" onClick={() => remove(i)}>
                        <Trash2 className="size-4" />
                      </Button>
                    </td>
                  ) : null}
                </tr>
              );
            })}
            {entries.length === 0 ? (
              <tr>
                <td colSpan={showDepartment ? 7 : 6} className="p-4 text-center text-xs text-muted-foreground">
                  No exams yet — add them below.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      {!readOnly ? (
        <Button size="sm" variant="outline" onClick={add}>
          <Plus className="size-4" /> Add exam
        </Button>
      ) : null}
      <datalist id="orion-exam-course-codes">
        {courses.map((c) => (
          <option key={c.course_code} value={c.course_code}>
            {c.course_name}
          </option>
        ))}
      </datalist>
    </div>
  );
}

export function ExamDiffSummary({ diff, currentCount }: { diff: ExamDiff; currentCount: number }) {
  if (!currentCount) return <PixelBadge tone="primary">New schedule — nothing published yet</PixelBadge>;
  return (
    <div className="flex flex-wrap gap-1.5">
      <PixelBadge tone="success">+{diff.added.length} added</PixelBadge>
      <PixelBadge tone="danger">−{diff.removed.length} removed</PixelBadge>
      <PixelBadge tone="warning">~{diff.changed.length} moved</PixelBadge>
      <PixelBadge tone="muted">{diff.unchanged} unchanged</PixelBadge>
    </div>
  );
}
