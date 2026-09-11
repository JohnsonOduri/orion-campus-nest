"""Layout-aware extraction of the ORION timetable PDFs.

Strategy (pdfplumber, geometry-first — never a naïve text dump):

1.  Every timetable page has one dominant grid (the largest detected table).
    Columns are periods; rows are weekdays; a leading narrow column holds the
    day name. Repeated headers and per-page legends are handled explicitly.
2.  Period columns are resolved from *geometry*, not text clustering:
      - header cells whose text is a bare digit ("1".."9") anchor a column;
      - all header text x-overlapping the digit cell contributes its time
        range (handles times split across stacked rows, and ranges that
        bleed into neighbouring column bboxes like the "8|9 5.00-7.00 PM"
        evening block);
      - a time range that is wider than one digit column is *shared*: each
        anchored column under it gets the range, flagged as derived so the
        audit trail shows the PDF printed no per-column time;
      - narrow columns whose letters ⊆ {b,r,e,a,k,u,n} are break columns.
3.  Day rows come from the narrow label column ("Mon".."Sat"); cells are
    attributed to a day by row order (labels are sequential) and to a period
    by maximal x-overlap — robust to the Word row-fragment artifacts.
4.  Legend tables ("COURSES | FACULTY") map course codes and faculty initials
    per page; entries resolve against their own page's legend first.

The extractor only reads the PDF; normalization/validation happen later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pdfplumber

from .model import (
    COURSE_CODE_RE,
    CREDITS_RE,
    DocumentMetadata,
    PeriodHeader,
    document_metadata,
    initials_from_name,
    parse_day_row,
    parse_period_header,
)

TIME_RANGE_RE = re.compile(
    r"(\d{1,2})[.:]([0-5]\d)\s*(am|pm)?\s*[-–—]\s*(\d{1,2})[.:]([0-5]\d)\s*(am|pm)?",
    re.IGNORECASE,
)

_BREAK_LETTERS = set("breuknl")  # 'break', 'lunch break' (vertical text)


@dataclass(frozen=True)
class GridCell:
    """One cell of the dominant grid with its page geometry."""

    row: int
    col: int
    x0: float
    x1: float
    top: float
    bottom: float
    text: str


@dataclass(frozen=True)
class PeriodColumn:
    """A period (or break) column of the grid with resolved times."""

    x0: float
    x1: float
    header: PeriodHeader

    @property
    def is_break(self) -> bool:
        return self.header.kind == "break"


@dataclass(frozen=True)
class LegendEntry:
    course_code: str
    course_name: str
    credits_raw: Optional[str]
    faculty_initials: tuple[str, ...]
    faculty_names: tuple[str, ...]


@dataclass(frozen=True)
class Legend:
    page: int
    entries: tuple[LegendEntry, ...] = ()

    def by_code(self, code: str) -> Optional[LegendEntry]:
        wanted = re.sub(r"\s+", "", code).upper()
        for e in self.entries:
            if re.sub(r"\s+", "", e.course_code).upper() == wanted:
                return e
        return None


@dataclass
class Section:
    """A batch/section grid extracted from one page."""

    page: int
    title: str
    metadata: Optional[DocumentMetadata]
    periods: list[PeriodColumn]
    records_raw: list[dict] = field(default_factory=list)
    legend: Legend = Legend(page=0)
    warnings: list[str] = field(default_factory=list)
    # internal geometry stashes used by the normalizer:
    day_spans: dict[str, tuple[float, float]] = field(default_factory=dict)
    day_order: list[str] = field(default_factory=list)
    saturday_text: Optional[str] = None


@dataclass
class TimetableDocument:
    """All sections of one timetable PDF."""

    source_id: str
    path: Path
    pages_processed: int
    page_titles: dict[int, str] = field(default_factory=dict)
    sections: list[Section] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ------------------------------------------------------------- page helpers


def _largest_grid(page):
    tables = page.find_tables()
    if not tables:
        return None
    return max(
        tables,
        key=lambda t: (t.bbox[2] - t.bbox[0]) * (t.bbox[3] - t.bbox[1]),
    )


def _page_title(page, text: Optional[str]) -> str:
    if text:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if lines:
            return " ".join(lines[:2])
    return ""


def _section_title(text: Optional[str]) -> str:
    if not text:
        return ""
    for ln in text.splitlines():
        ln = " ".join(ln.split())
        if re.search(r"SEMESTER\s+\S+", ln, re.IGNORECASE) and re.search(
            r"BATCH\s*[-–—]?\s*\S+", ln, re.IGNORECASE
        ):
            return ln
    return ""


def _cell_text(page, bbox) -> str:
    try:
        return (page.crop(bbox).extract_text() or "").strip()
    except Exception:
        return ""


def _words_cell_text(words, x0: float, top: float, x1: float, bottom: float) -> str:
    """Cell text built from whole-word centers, not `page.crop()`.

    Cropping to a cell bbox can split a word's glyphs across the boundary
    (narrow adjacent break/lunch columns bleed a stray letter into the next
    header cell; digits at a boundary can duplicate/merge, e.g. "4:25" -> "4:625").
    Selecting whole words by center point avoids both classes of corruption.
    """
    found = [
        (w["top"], w["x0"], w["text"])
        for w in words
        if x0 - 1 <= (w["x0"] + w["x1"]) / 2 <= x1 + 1
        and top - 1 <= (w["top"] + w["bottom"]) / 2 <= bottom + 1
    ]
    found.sort()
    return " ".join(t for _, _, t in found)


# ------------------------------------------------------------ column parsing


def _parse_columns(page, grid) -> tuple[list[PeriodColumn], list[str]]:
    """Resolve period/break columns from the grid's header geometry."""
    warnings: list[str] = []
    words = page.extract_words()

    # 1. Find day-label rows to know where the header ends. Day labels live in
    #    a narrow left column; header rows are everything above the first one.
    first_day_top = None
    label_cells: list[tuple[float, float, float, float, str]] = []
    for row in grid.rows:
        for cell in row.cells:
            if cell is None:
                continue
            x0, top, x1, bottom = cell
            if (x1 - x0) < 80:
                text = _words_cell_text(words, x0, top, x1, bottom)
                if parse_day_row(text):
                    label_cells.append((x0, top, x1, bottom, text))
                    if first_day_top is None or top < first_day_top:
                        first_day_top = top
    if first_day_top is None:
        return [], ["page: no day rows found in dominant grid"]

    # 2. Collect header cells above the first day row.
    header_cells: list[tuple[float, float, float, float, str]] = []
    for row in grid.rows:
        for cell in row.cells:
            if cell is None:
                continue
            x0, top, x1, bottom = cell
            if top >= first_day_top:
                continue
            text = _words_cell_text(words, x0, top, x1, bottom)
            if text:
                header_cells.append((x0, top, x1, bottom, text))

    # 3. Anchor columns on bare-digit header cells (period numbers 1..12) and
    #    on combined "<digit> (<range>)" header cells.
    digit_cells: list[tuple[int, float, float, str]] = []
    for x0, top, x1, bottom, text in header_cells:
        flat = " ".join(text.split())
        m = re.match(r"^(\d{1,2})\b", flat)
        if m and 1 <= int(m.group(1)) <= 12 and not re.match(r"^\d+\.\d", flat):
            digit_cells.append((int(m.group(1)), x0, x1, flat))

    # keep the first anchor per slot (dedupe by slot+x overlap)
    columns: list[PeriodColumn] = []
    seen: list[tuple[int, float, float]] = []
    for slot, dx0, dx1, flat in digit_cells:
        if any(slot == s and abs(dx0 - sx0) < 2 for s, sx0, _ in seen):
            continue
        seen.append((slot, dx0, dx1))
        columns.append(
            PeriodColumn(
                x0=dx0,
                x1=dx1,
                header=PeriodHeader(slot, None, None, "teaching", raw=flat),
            )
        )

    if not columns:
        return [], ["page: no digit-anchored period columns found"]

    # 4. Break columns: narrow header cells with break-ish letters.
    for x0, top, x1, bottom, text in header_cells:
        compact = text.replace(" ", "").replace("\n", "").lower()
        letters = set(re.sub(r"[^a-z]", "", compact))
        width = x1 - x0
        if (
            compact
            and letters
            and letters <= _BREAK_LETTERS
            and width < 60
            and x0 < first_day_top  # noqa: static guard, replaced below
        ):
            pass  # handled below by x-overlap check against day rows
    # (re-do cleanly: only cells that end above the first day row and don't
    #  overlap an already-created column)
    for x0, top, x1, bottom, text in header_cells:
        compact = text.replace(" ", "").replace("\n", "").lower()
        letters = set(re.sub(r"[^a-z]", "", compact))
        width = x1 - x0
        if not compact or not letters or letters > _BREAK_LETTERS or width >= 60:
            continue
        overlaps_period = any(
            x0 < c.x1 - 2 and x1 > c.x0 + 2 for c in columns if not c.is_break
        )
        if overlaps_period:
            continue
        columns.append(
            PeriodColumn(
                x0=x0,
                x1=x1,
                header=PeriodHeader(0, None, None, "break", raw=" ".join(text.split())),
            )
        )

    columns.sort(key=lambda c: c.x0)

    # 5. Assign time ranges: gather all header text x-overlapping each column.
    assigned: list[PeriodColumn] = []
    for col in columns:
        texts: list[tuple[float, str]] = []
        for x0, top, x1, bottom, text in header_cells:
            if x0 < col.x1 - 2 and x1 > col.x0 + 2:
                texts.append((top, " ".join(text.split())))
        if texts:
            joined = " ".join(t for _, t in sorted(texts))
            h = parse_period_header(joined)
            if h is not None:
                col = PeriodColumn(x0=col.x0, x1=col.x1, header=h)
        assigned.append(col)
    columns = assigned

    # 6. Shared/derived ranges: a range printed once for a group of digit
    #    columns (evening block "8|9 (5.00-7.00 PM)") renders as one wide
    #    timed header cell. When the widest timed cell overlapping a resolved
    #    column is much wider than the column itself, the column's time is
    #    shared — mark it "[derived]" so consumers can tell a per-column
    #    printed time from a block-level one. (Preview JSON and the
    #    timetable_periods.is_time_derived column surface this flag.)
    for i, col in enumerate(columns):
        if col.is_break or col.header.start is None:
            continue
        widest = 0.0
        for x0, top, x1, bottom, text in header_cells:
            flat = " ".join(text.split())
            if not (
                TIME_RANGE_RE.search(flat) or TIME_RANGE_RE.search(flat.replace(" ", ""))
            ):
                continue
            if x0 < col.x1 - 2 and x1 > col.x0 + 2:
                widest = max(widest, x1 - x0)
        if widest > (col.x1 - col.x0) * 1.5 and "[derived]" not in col.header.raw:
            columns[i] = PeriodColumn(
                x0=col.x0,
                x1=col.x1,
                header=PeriodHeader(
                    col.header.slot_index,
                    col.header.start,
                    col.header.end,
                    "teaching",
                    raw=col.header.raw + " [derived]",
                ),
            )

    return columns, warnings


def _is_derived(col: PeriodColumn) -> bool:
    """True when the column's time range is shared across multiple columns."""
    return "[derived]" in col.header.raw


def _day_rows(page, grid) -> tuple[dict[str, tuple[float, float]], list[str]]:
    """Day labels in row order: {'Monday': (top, bottom), ...}, [Mon..Sat]."""
    found: list[tuple[str, float, float, float]] = []
    for row in grid.rows:
        for cell in row.cells:
            if cell is None:
                continue
            x0, top, x1, bottom = cell
            if (x1 - x0) >= 80:
                continue
            text = _cell_text(page, cell)
            day = parse_day_row(text)
            if day:
                found.append((day, top, bottom, x0))
    # keep the widest/tallest label per day
    best: dict[str, tuple[float, float, float]] = {}
    for day, top, bottom, x0 in found:
        cur = best.get(day)
        if cur is None or (bottom - top) > (cur[1] - cur[0]):
            best[day] = (top, bottom, x0)
    ordered = sorted(best.items(), key=lambda kv: kv[1][0])
    return {d: (v[0], v[1]) for d, v in ordered}, [d for d, _ in ordered]


def _extract_cells(page, grid, header_bottom: float) -> list[GridCell]:
    cells: list[GridCell] = []
    for r_idx, row in enumerate(grid.rows):
        for c_idx, cell in enumerate(row.cells):
            if cell is None:
                continue
            x0, top, x1, bottom = cell
            if top < header_bottom - 1:
                continue
            text = _cell_text(page, cell)
            cells.append(GridCell(r_idx, c_idx, x0, x1, top, bottom, text))
    return cells


def _extract_legend(page) -> Legend:
    """Parse 'COURSES | FACULTY' tables on a page into a lookup."""
    entries: list[LegendEntry] = []
    for t in page.find_tables():
        data = t.extract()
        if not data or not data[0]:
            continue
        first = " ".join((data[0][0] or "").split()).upper()
        if not first.startswith("COURSES"):
            continue
        for row in data[1:]:
            if not row or not row[0]:
                continue
            entry = _parse_legend_row(row[0], row[1] if len(row) > 1 else None)
            if entry:
                entries.append(entry)
    return Legend(page=page.page_number, entries=tuple(_backfill_legend_initials(entries)))


def _backfill_legend_initials(entries: list[LegendEntry]) -> list[LegendEntry]:
    """Derive initials for a legend row that names a faculty member but
    prints no parenthesized initials (e.g. "Dr. Amit Kumar Roy" with no
    "(AKR)"). Mechanical transform of the printed name (see
    `model.initials_from_name`) — never a guess. Dropped entirely if two
    different names on the same page's legend would collide on the same
    derived initials, so resolution never silently picks the wrong person.
    """
    derived: dict[int, str] = {}
    for i, e in enumerate(entries):
        if e.faculty_initials or not e.faculty_names or not e.faculty_names[0]:
            continue
        ini = initials_from_name(e.faculty_names[0])
        if ini:
            derived[i] = ini
    by_ini: dict[str, set[str]] = {}
    for i, ini in derived.items():
        by_ini.setdefault(ini, set()).add(entries[i].faculty_names[0])
    ambiguous = {ini for ini, names in by_ini.items() if len(names) > 1}

    out: list[LegendEntry] = []
    for i, e in enumerate(entries):
        ini = derived.get(i)
        if ini and ini not in ambiguous:
            e = LegendEntry(
                course_code=e.course_code,
                course_name=e.course_name,
                credits_raw=e.credits_raw,
                faculty_initials=(ini,),
                faculty_names=e.faculty_names,
            )
        out.append(e)
    return out


def _parse_legend_row(
    course_cell: Optional[str], faculty_cell: Optional[str]
) -> Optional[LegendEntry]:
    if not course_cell:
        return None
    flat = " ".join(course_cell.split())
    m = COURSE_CODE_RE.match(flat)
    if not m:
        return None
    code = m.group(1).upper()
    rest = flat[m.end():].strip(" -–")
    credits_raw = None
    cm = CREDITS_RE.search(rest)
    if cm:
        credits_raw = f"[{cm.group(1)}-{cm.group(2)}-{cm.group(3)}] {cm.group(4)}"
        rest = (rest[: cm.start()] + rest[cm.end():]).strip(" -–")
    name = re.sub(r"\s+", " ", rest).strip()

    initials: list[str] = []
    names: list[str] = []
    if faculty_cell:
        fflat = " ".join(faculty_cell.split())
        init_block = re.search(r"\(([^)]+)\)", fflat)
        if init_block:
            parts = [p.strip(". ") for p in init_block.group(1).split("/")]
            initials = [re.sub(r"[^A-Za-z]", "", p).upper() for p in parts if p.strip()]
            names = [n.strip() for n in fflat[: init_block.start()].split("/") if n.strip()]
        else:
            names = [fflat.strip()]
    if not names:
        names = [""]
    names = [re.sub(r"\.\s*$", "", n).strip() for n in names]
    return LegendEntry(
        course_code=code,
        course_name=name,
        credits_raw=credits_raw,
        faculty_initials=tuple(initials),
        faculty_names=tuple(names),
    )


def _saturday_text(page, grid) -> Optional[str]:
    """Saturday rows are a single merged wide cell with a whole-grid activity."""
    for row in grid.rows:
        for cell in row.cells:
            if cell is None:
                continue
            x0, top, x1, bottom = cell
            if (x1 - x0) <= 100:
                continue
            text = _cell_text(page, cell)
            if text and "sports" in text.lower():
                return " ".join(text.split())
    return None


# ------------------------------------------------------------------- public


def extract_section(page, page_index: int) -> Optional[Section]:
    """Extract one batch/section grid from a timetable page."""
    text = page.extract_text() or ""
    title = _section_title(text)
    if not title:
        return None
    meta = document_metadata(title, _page_title(page, text))
    grid = _largest_grid(page)
    if grid is None:
        return None

    columns, col_warnings = _parse_columns(page, grid)
    teaching = [c for c in columns if not c.is_break]
    if not teaching:
        return None

    day_spans, day_order = _day_rows(page, grid)
    if not day_spans:
        return None

    header_bottom = min(top for top, _ in day_spans.values())
    cells = _extract_cells(page, grid, header_bottom)
    legend = _extract_legend(page)

    warnings = list(col_warnings)

    records_raw = [
        {"x0": c.x0, "x1": c.x1, "top": c.top, "bottom": c.bottom, "text": c.text, "row": c.row}
        for c in cells
        if c.text
    ]

    return Section(
        page=page_index,
        title=title,
        metadata=meta,
        periods=columns,
        records_raw=records_raw,
        legend=legend,
        warnings=warnings,
        day_spans=day_spans,
        day_order=day_order,
        saturday_text=_saturday_text(page, grid),
    )


def extract_document(pdf_path: str | Path) -> TimetableDocument:
    """Extract all section grids from a timetable PDF."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"source PDF not found: {path}")
    doc = TimetableDocument(source_id=path.name, path=path, pages_processed=0)

    with pdfplumber.open(path) as pdf:
        doc.pages_processed = len(pdf.pages)
        for idx, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if not _section_title(text):
                continue  # cover/appendix pages carry no section grid
            section = extract_section(page, idx)
            if section is None:
                doc.warnings.append(f"page {idx}: section-like header but no grid extracted")
                continue
            doc.sections.append(section)
    _backfill_missing_period_times(doc)
    return doc


def _backfill_missing_period_times(doc: TimetableDocument) -> None:
    """Some pages of a multi-batch timetable print no time for a slot that
    IS printed on other pages of the same document (one institutional period
    schedule, reprinted per batch). Backfill a missing per-page time only
    when every page of this document that DOES print the slot agrees exactly
    — never invent a time that isn't evidenced verbatim somewhere in the
    source PDF. Backfilled columns are flagged "[derived]", same as an
    intra-page shared range.
    """
    canonical: dict[int, tuple[str, str]] = {}
    conflicting: set[int] = set()
    for section in doc.sections:
        for col in section.periods:
            if col.is_break or col.header.start is None:
                continue
            slot = col.header.slot_index
            value = (col.header.start, col.header.end)
            if slot in canonical and canonical[slot] != value:
                conflicting.add(slot)
            canonical.setdefault(slot, value)
    for slot in conflicting:
        canonical.pop(slot, None)
    if not canonical:
        return

    for section in doc.sections:
        backfilled = False
        new_periods: list[PeriodColumn] = []
        for col in section.periods:
            value = canonical.get(col.header.slot_index)
            if not col.is_break and col.header.start is None and value is not None:
                start, end = value
                new_periods.append(
                    PeriodColumn(
                        x0=col.x0,
                        x1=col.x1,
                        header=PeriodHeader(
                            col.header.slot_index,
                            start,
                            end,
                            "teaching",
                            raw=col.header.raw + " [derived]",
                        ),
                    )
                )
                backfilled = True
            else:
                new_periods.append(col)
        if backfilled:
            section.periods = new_periods
            section.warnings.append(
                "backfilled missing period time(s) from sibling pages of the same source"
            )
