"""Import the ALREADY PROCESSED timetable preview JSON into the LIVE Supabase.

Does NOT re-extract the PDF. Reads
Data/processed/semester_3_timetable_odd_2026_preview.json through
backend/timetable/hosted_adapter.py (pure mapping, no fabrication) and writes
with a service-role client (server-side ingestion per AGENTS.md §9).

Idempotency: hosted PostgREST cannot target expression indexes, so every
entity uses application-level fetch-then-diff reconciliation (mirrors
repository.import_periods):
    fetch existing rows -> compare natural identity -> update changed,
    insert missing -> never duplicate.
Order: faculty -> courses -> periods -> entries (+ co-faculty join).

Usage:
    .venv/bin/python scripts/import_hosted.py                # apply
    .venv/bin/python scripts/import_hosted.py --dry-run      # report only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.timetable.hosted_adapter import adapt_preview, load_preview  # noqa: E402

DEFAULT_PREVIEW = "Data/processed/semester_3_timetable_odd_2026_preview.json"

DAYS = {"Monday": 1, "Tuesday": 2, "Wednesday": 3, "Thursday": 4,
        "Friday": 5, "Saturday": 6, "Sunday": 7}


def load_env() -> None:
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def get_client() -> Any:
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


def _fetch_all(client: Any, table: str, columns: str, filters: dict | None = None) -> list[dict]:
    q = client.table(table).select(columns)
    for col, val in (filters or {}).items():
        q = q.eq(col, val)
    res = q.limit(10_000).execute()
    return res.data or []


def _print_counts(label: str, inserted: int, updated: int, unchanged: int) -> None:
    print(f"{label:<22} insert={inserted:<4} update={updated:<3} unchanged={unchanged}")


def _norm_time(v: Any) -> Any:
    """Normalize a time value for comparison.

    PostgREST returns times as "HH:MM:SS" while adapted rows carry "HH:MM";
    comparing raw strings would flag every row as changed on rerun.
    """
    if isinstance(v, str) and len(v) >= 5 and v[2] == ":":
        return v[:5]
    return v


def reconcile(
    client: Any,
    table: str,
    rows: list[dict],
    key_cols: list[str],
    *,
    compare_cols: list[str],
    label: str,
    time_cols: tuple[str, ...] = (),
) -> dict[str, int]:
    """Generic fetch-then-diff reconciliation on natural identity columns."""
    existing_rows = _fetch_all(client, table, ", ".join(set(key_cols + compare_cols + ["id"])))
    if time_cols:
        for r in existing_rows:
            for c in time_cols:
                r[c] = _norm_time(r.get(c))
    existing: dict[tuple, dict] = {}
    for r in existing_rows:
        existing[tuple(r.get(c) for c in key_cols)] = r

    to_insert: list[dict] = []
    to_update: list[tuple[Any, dict]] = []
    unchanged = 0
    for row in rows:
        cur = existing.get(tuple(row.get(c) for c in key_cols))
        if cur is None:
            to_insert.append(row)
        else:
            patch = {c: row[c] for c in compare_cols if cur.get(c) != row.get(c)}
            if patch:
                to_update.append((cur["id"], patch))
            else:
                unchanged += 1

    for chunk_start in range(0, len(to_insert), 200):
        client.table(table).insert(to_insert[chunk_start : chunk_start + 200]).execute()
    for pid, patch in to_update:
        client.table(table).update(patch).eq("id", pid).execute()

    _print_counts(label, len(to_insert), len(to_update), unchanged)
    return {"inserted": len(to_insert), "updated": len(to_update), "unchanged": unchanged}


def _load_validation_failed_uids(preview_path: str) -> set[str]:
    """The preview JSON lists every extracted record regardless of validation
    outcome (it's the human-inspectable audit trail); only ingest_timetable's
    validation JSON says which ones actually passed. Never import a record
    the validator rejected — load its sibling *_validation.json (same stem)
    and return the source_uids to exclude. Missing file -> nothing to
    exclude (caller still requires the preview to already be 100% valid).
    """
    p = Path(preview_path)
    validation_path = p.with_name(p.name.replace("_preview.json", "_validation.json"))
    if not validation_path.exists():
        return set()
    validation = json.loads(validation_path.read_text())
    return {f["record"]["source_uid"] for f in validation.get("failed", []) if f.get("record")}


def import_preview(preview_path: str, approved_by: str) -> dict:
    preview = load_preview(preview_path)
    failed_uids = _load_validation_failed_uids(preview_path)
    if failed_uids:
        before = len(preview["records"])
        preview["records"] = [r for r in preview["records"] if r.get("source_uid") not in failed_uids]
        print(
            f"excluding {before - len(preview['records'])} record(s) that failed "
            f"validation (see the matching *_validation.json) — importing only "
            f"validated records"
        )
    adapted = adapt_preview(preview)
    source_id = preview["source"]["source_id"]
    recs = preview["records"]

    print(f"source:    {source_id}")
    print(f"records:   {len(recs)}")
    print(
        f"courses:   {len(adapted.courses)}  faculty: {len(adapted.faculty)}  "
        f"periods: {len(adapted.periods)}  entries: {len(adapted.entries)}"
    )
    for issue in adapted.issues[:20]:
        print(f"  [adapt] {issue}")
    if adapted.issues:
        print(f"  ... {len(adapted.issues)} adaptation issue(s) total")

    client = get_client()

    # Before-import state check (task STEP 8: never assume anything).
    before = (
        client.table("timetable_entries")
        .select("id", count="exact").eq("source_id", source_id).limit(0).execute()
    )
    print(f"existing rows for this source: {before.count}")

    # ---- faculty (natural key: initials) --------------------------------
    fac_rows = [
        {"initials": ini, "full_name": f["full_name"], "status": "active"}
        for ini, f in adapted.faculty.items()
    ]
    fac = reconcile(
        client, "faculty", fac_rows, ["initials"],
        compare_cols=["full_name", "status"], label="faculty",
    )
    # ---- courses (natural key: course_code) -----------------------------
    crs_rows = [
        {
            "course_code": code,
            "course_name": c["course_name"],
            "semester": c.get("semester"),
            "programme": c.get("programme"),
            "status": "active",
        }
        for code, c in adapted.courses.items()
    ]
    crs = reconcile(
        client, "courses", crs_rows, ["course_code"],
        compare_cols=["course_name", "semester", "programme", "status"],
        label="courses",
    )

    # ---- periods (source_id, slot_index, start_time) --------------------
    per_rows = [p for p in adapted.periods if p["slot_index"] != 0]  # 0 = break gaps
    per = reconcile(
        client, "timetable_periods", per_rows,
        ["source_id", "slot_index", "start_time"],
        compare_cols=["end_time", "kind", "is_time_derived", "source_page"],
        label="timetable_periods",
        time_cols=("start_time", "end_time"),
    )

    # ---- FK resolution ---------------------------------------------------
    faculty_id: dict[str, Any] = {
        r["initials"]: r["id"] for r in _fetch_all(client, "faculty", "id,initials") if r["initials"]
    }
    course_id: dict[str, Any] = {
        r["course_code"]: r["id"] for r in _fetch_all(client, "courses", "id,course_code")
    }

    # ---- entries (natural key: deterministic source_uid from the model) --
    now = datetime.now(timezone.utc).isoformat()
    entry_rows: list[dict] = []
    faculty_links: list[tuple[dict, list[str]]] = []  # (row, ordered initials)
    unresolved_fac: set[str] = set()
    unresolved_crs: set[str] = set()
    no_course_fk: set[str] = set()  # activities without a course code: course_id NULL is correct

    for rec in recs:
        ini_list = rec.get("faculty_initials") or []
        code = rec.get("course_code")
        row = {
            "course_id": course_id.get(code) if code else None,
            "faculty_id": faculty_id.get(ini_list[0]) if ini_list else None,
            "room_id": None,  # processed data has no rooms; never fabricate
            "day_of_week": DAYS[rec["day"]],
            "slot_index": rec["slot_index"],
            "start_time": rec.get("start_time"),
            "end_time": rec.get("end_time"),
            "semester": rec["semester"],
            "programme": rec["programme"],
            "department": rec["branch"],
            "batch": rec["batch"],
            "section": rec["section"],
            "entry_type": rec["entry_type"],
            "lab_batch": rec.get("lab_batch"),
            "valid_from": rec["valid_from"],
            "valid_until": rec["valid_until"],
            "status": "active",
            "source_id": source_id,
            "source_page": rec.get("source_page"),
            "source_text": rec.get("source_text"),
            "source_uid": rec["source_uid"],
            "approved_at": now,
        }
        if code:
            if course_id.get(code) is None:
                unresolved_crs.add(code)
        else:
            no_course_fk.add(rec["entry_type"])
        for ini in ini_list:
            if faculty_id.get(ini) is None:
                unresolved_fac.add(ini)
        entry_rows.append(row)
        if ini_list:
            # ALL faculty are linked (ord 0 = primary); faculty_id is the
            # denormalized first-teacher convenience column.
            faculty_links.append((row, ini_list))

    if unresolved_crs:
        print(f"  [warn] unresolved courses (course_id NULL): {sorted(unresolved_crs)}")
    if unresolved_fac:
        print(f"  [warn] unresolved faculty (no FK link): {sorted(unresolved_fac)}")
    if no_course_fk:
        print(f"  [info] entries without course code (course_id NULL, by design): {sorted(no_course_fk)}")

    # fetch -> diff on source_uid within this source_id
    existing_entries = {
        r["source_uid"]: r
        for r in _fetch_all(
            client, "timetable_entries",
            "id,source_uid,day_of_week,slot_index,start_time,end_time,semester,"
            "programme,department,batch,section,entry_type,valid_from,valid_until,"
            "status,course_id,faculty_id,room_id,source_page",
            filters={"source_id": source_id},
        )
    }
    to_insert: list[dict] = []
    to_update: list[tuple[Any, dict]] = []
    unchanged = 0
    compare = (
        "day_of_week", "slot_index", "start_time", "end_time",
        "semester", "programme", "department", "batch", "section",
        "entry_type", "valid_from", "valid_until", "status",
        "course_id", "faculty_id", "room_id", "source_page",
    )
    for row in entry_rows:
        cur = existing_entries.get(row["source_uid"])
        if cur is None:
            to_insert.append(row)
        else:
            patch = {c: row[c] for c in compare if cur.get(c) != row.get(c)}
            # time columns compare equal after "HH:MM:SS" -> "HH:MM" folding
            patch = {
                c: v for c, v in patch.items()
                if not (c in ("start_time", "end_time")
                        and _norm_time(cur.get(c)) == _norm_time(v))
            }
            if patch:
                to_update.append((cur["id"], patch))
            else:
                unchanged += 1

    for chunk_start in range(0, len(to_insert), 200):
        client.table("timetable_entries").insert(
            to_insert[chunk_start : chunk_start + 200]
        ).execute()
    for pid, patch in to_update:
        client.table("timetable_entries").update(patch).eq("id", pid).execute()
    _print_counts("timetable_entries", len(to_insert), len(to_update), unchanged)

    # ---- faculty join rows (all entries, ord 0 = primary) ----------------
    join_count = 0
    if faculty_links:
        id_by_uid = {
            r["source_uid"]: r["id"]
            for r in _fetch_all(client, "timetable_entries", "id,source_uid",
                                filters={"source_id": source_id})
        }
        join_rows: list[dict] = []
        seen: set[tuple] = set()
        for row, ini_list in faculty_links:
            eid = id_by_uid.get(row["source_uid"])
            if eid is None:
                continue
            for ord_i, ini in enumerate(ini_list):
                fid = faculty_id.get(ini)
                if fid is None:
                    continue
                if (eid, fid) in seen:
                    continue
                seen.add((eid, fid))
                join_rows.append({"entry_id": eid, "faculty_id": fid, "ord": ord_i})
        existing_joins = {
            (r["entry_id"], r["faculty_id"])
            for r in _fetch_all(client, "timetable_entry_faculty", "entry_id,faculty_id")
        }
        new_joins = [j for j in join_rows if (j["entry_id"], j["faculty_id"]) not in existing_joins]
        for chunk_start in range(0, len(new_joins), 200):
            client.table("timetable_entry_faculty").insert(
                new_joins[chunk_start : chunk_start + 200]
            ).execute()
        join_count = len(new_joins)
        _print_counts("faculty links", join_count, 0, len(join_rows) - join_count)

    # ---- audit (AGENTS.md §28) -------------------------------------------
    stats = {
        "faculty": fac,
        "courses": crs,
        "timetable_periods": per,
        "entries": {"inserted": len(to_insert), "updated": len(to_update),
                    "unchanged": unchanged},
        "faculty_links": join_count,
        "unresolved_courses": sorted(unresolved_crs),
        "unresolved_faculty": sorted(unresolved_fac),
    }
    client.table("ingestion_runs").insert({
        "source_id": source_id,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": "imported",
        "stats": stats,
        "validation_errors": 0,
        "validation_warnings": len(adapted.issues),
        "approved_by": approved_by,
    }).execute()
    print(f"\naudit: ingestion_runs recorded (approved_by={approved_by})")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Import processed timetable preview into live Supabase.")
    ap.add_argument("--preview", default=DEFAULT_PREVIEW)
    ap.add_argument("--approved-by", default="orion-ingestion-script")
    args = ap.parse_args()

    load_env()
    try:
        stats = import_preview(args.preview, args.approved_by)
    except Exception as exc:  # noqa: BLE001
        print(f"IMPORT FAILED: {exc}", file=sys.stderr)
        return 1
    print("\nfinal stats:", json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
