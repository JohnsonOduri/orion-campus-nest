"""Document ingestion (RAG): PDF -> extract/OCR -> chunk -> screen -> embed -> Supabase.

Covers the semantic (non-SQL-shaped) corpus in Data/Unstructured/ plus two
files from Data/Structured/ that are RAG-shaped, not tables (Hostel Rules,
per docs/timetable.md-adjacent analysis in Data/analysis.md).

Pipeline (README §6 / AGENTS.md §9):
    file validation -> extraction (text layer, or OCR for scans)
    -> sensitive-data screening -> chunking -> embedding -> Supabase

Embeddings: Gemini `gemini-embedding-2`, 768-dim, via backend/query/
embeddings.py (the same module the API uses for query vectors), written to
document_chunks.embedding_gemini (migration 20260922065942). Only chunks
that are actually inserted or whose content changed are embedded, and only
on --import — a dry run makes no Gemini calls. The legacy 384-dim MiniLM
`embedding` column is no longer written; a changed chunk's stale MiniLM
vector is cleared rather than left pointing at old text (docs/embeddings.md).

OCR: tesseract via pytesseract, only for the 3 anti-ragging PDFs that are
scanned images with no text layer (verified in Data/analysis.md §1). Every
OCR'd chunk carries its page-average OCR confidence in confidence_score —
never silently presented as equally reliable to a clean-text extraction
(AGENTS.md §10).

Sensitive data: the committee-roster OM names real people; personal phone
numbers are redacted before storage (names/designations are public-role
governance info, kept). No other file in this corpus contains sensitive
personal data per Data/analysis.md §4.6.

Explicitly excluded: recruiterscorner.pdf (14MB placement/marketing deck).
Data/analysis.md flags it as needing a product-owner decision; README §12
("pure advertisements should not enter the searchable institutional
knowledge base") is the applicable default until that decision is made.

Usage:
    .venv/bin/python scripts/ingest_documents.py                  # dry run, all docs
    .venv/bin/python scripts/ingest_documents.py --only "UG_Regulations"
    .venv/bin/python scripts/ingest_documents.py --import --approved-by "you@x"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.query import embeddings  # noqa: E402

# ------------------------------------------------------------- document specs

@dataclass(frozen=True)
class DocSpec:
    path: Path
    title: str
    document_type: str
    classification: str
    category: Optional[str] = None
    programme: Optional[str] = None
    specialisation: Optional[str] = None
    cohort: Optional[str] = None
    department: Optional[str] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    needs_ocr: bool = False
    sensitive: bool = False


U = Path("Data/Unstructured")
S = Path("Data/Structured")

DOCUMENT_SPECS: list[DocSpec] = [
    # -- curriculum / syllabus (ADM 2026 cohort) --------------------------------
    DocSpec(U / "CSE_ADM_2026.pdf", "B.Tech CSE Curriculum (ADM 2026)", "curriculum", "ACADEMIC",
            programme="B.Tech", specialisation="Computer Science and Engineering", cohort="ADM2026"),
    DocSpec(U / "AI_DS_ADM_2026.pdf", "B.Tech CSE (AI & DS) Curriculum (ADM 2026)", "curriculum", "ACADEMIC",
            programme="B.Tech", specialisation="AI and Data Science", cohort="ADM2026"),
    DocSpec(U / "ECE_ADM_2026.pdf", "B.Tech ECE Curriculum (ADM 2026)", "curriculum", "ACADEMIC",
            programme="B.Tech", specialisation="Electronics and Communication Engineering", cohort="ADM2026"),
    DocSpec(U / "BMC_ADM_2026.pdf", "B.Tech Mathematics & Computing Curriculum (ADM 2026)", "curriculum", "ACADEMIC",
            programme="B.Tech", specialisation="Mathematics and Computing", cohort="ADM2026"),
    DocSpec(U / "Cyber_ADM_2026.pdf", "B.Tech CSE (Cyber Security) Curriculum (ADM 2026)", "curriculum", "ACADEMIC",
            programme="B.Tech", specialisation="Cyber Security", cohort="ADM2026"),
    # -- curriculum annexures (21-25 cohort) -------------------------------------
    DocSpec(U / "Annexure I_CSE 21-25.pdf", "B.Tech CSE Curriculum (2021-25 batch)", "curriculum", "ACADEMIC",
            programme="B.Tech", specialisation="Computer Science and Engineering", cohort="21-25"),
    DocSpec(U / "Annexure II_AI&DS 21-25.pdf", "B.Tech AI & DS Curriculum (2021-25 batch)", "curriculum", "ACADEMIC",
            programme="B.Tech", specialisation="AI and Data Science", cohort="21-25"),
    DocSpec(U / "Annexure III_ECE 21-25.pdf", "B.Tech ECE Curriculum (2021-25 batch)", "curriculum", "ACADEMIC",
            programme="B.Tech", specialisation="Electronics and Communication Engineering", cohort="21-25"),
    DocSpec(U / "Annexure IV_CY 21-25.pdf", "B.Tech Cyber Security Curriculum (2021-25 batch)", "curriculum", "ACADEMIC",
            programme="B.Tech", specialisation="Cyber Security", cohort="21-25"),
    # -- regulations --------------------------------------------------------------
    DocSpec(U / "UG_Regulations 26 onwards.pdf", "UG Regulations (2026 admission onwards)", "regulations", "OFFICIAL",
            programme="B.Tech", cohort="26-onwards", valid_from="2026-07-01"),
    DocSpec(U / "UG Regulations 21-25.pdf", "UG Regulations (2021-25 batch)", "regulations", "OFFICIAL",
            programme="B.Tech", cohort="21-25"),
    # -- procedures -----------------------------------------------------------------
    DocSpec(U / "Transcript verification procedure.pdf", "Transcript Verification Procedure", "procedure", "OFFICIAL",
            category="academics"),
    DocSpec(U / "educational verification.pdf", "Educational Certificate Verification Procedure", "procedure", "OFFICIAL",
            category="academics"),
    # -- anti-ragging (OCR required) -------------------------------------------------
    DocSpec(U / "UGC Regulations- Anti-Ragging - 2009.pdf", "UGC Anti-Ragging Regulations (2009)", "policy", "POLICY",
            category="anti-ragging", valid_from="2009-01-01", needs_ocr=True),
    DocSpec(U / "Letter-UGC-Antiragging.pdf", "UGC Anti-Ragging Circular Letter", "policy", "POLICY",
            category="anti-ragging", needs_ocr=True),
    DocSpec(U / "OM-Anti Ragging Committee-Squad-Jan2024.pdf",
            "Office Memorandum: Anti-Ragging Committee & Squad (Jan 2024)", "circular", "ANNOUNCEMENT",
            category="anti-ragging", valid_from="2024-01-31", needs_ocr=True, sensitive=True),
    # -- hostel rules (Structured/ folder, but prose -> RAG not SQL) ------------------
    DocSpec(S / "IIIT Kottayam - Hostel Rules and Regulations - July 2026 .pdf",
            "Hostel Rules and Regulations (July 2026)", "policy", "OFFICIAL",
            category="hostel", valid_from="2026-07-01"),
]

# recruiterscorner.pdf deliberately excluded — see module docstring.


# ------------------------------------------------------------------- redaction

# Indian mobile/landline numbers in the committee-roster OM — names/roles are
# public governance info and are kept; personal numbers are not (AGENTS.md §11).
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[-\s]?)?[6-9]\d{9}(?!\d)")


def _redact_sensitive(text: str) -> str:
    return _PHONE_RE.sub("[redacted phone number]", text)


# --------------------------------------------------------------- extraction

def _extract_text_pages(spec: DocSpec) -> list[tuple[int, str, float]]:
    """Returns [(page_no, text, confidence_0_100)]. Clean text -> confidence 100."""
    pages: list[tuple[int, str, float]] = []
    with pdfplumber.open(spec.path) as pdf:
        if not spec.needs_ocr:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append((i, text, 100.0))
            return pages

        import pytesseract

        for i, page in enumerate(pdf.pages, start=1):
            image = page.to_image(resolution=200).original
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            text = pytesseract.image_to_string(image)
            confs = [int(c) for c in data["conf"] if c not in ("-1", -1)]
            conf = sum(confs) / len(confs) if confs else 0.0
            if text.strip():
                pages.append((i, text, round(conf, 1)))
    return pages


# ------------------------------------------------------------------- chunking

_TARGET_CHARS = 2400  # ~600 tokens at ~4 chars/token
_MIN_CHARS = 400


@dataclass
class Chunk:
    content: str
    page_start: int
    page_end: int
    confidence: float
    section_title: Optional[str] = None


_HEADING_RE = re.compile(r"^(?:[A-Z][A-Z .&/-]{3,60}|R\.\d+\b.*|\d+(?:\.\d+)+\s+\S.{0,60})$")


def _guess_heading(paragraph: str) -> Optional[str]:
    first_line = paragraph.strip().splitlines()[0].strip() if paragraph.strip() else ""
    if first_line and len(first_line) <= 80 and _HEADING_RE.match(first_line):
        return first_line
    return None


def chunk_pages(pages: list[tuple[int, str, float]]) -> list[Chunk]:
    """Paragraph-aware chunker: accumulate paragraphs to ~_TARGET_CHARS,
    never splitting a paragraph unless it alone exceeds the target."""
    chunks: list[Chunk] = []
    buf: list[str] = []
    buf_pages: list[int] = []
    buf_confs: list[float] = []
    heading: Optional[str] = None

    def flush() -> None:
        nonlocal buf, buf_pages, buf_confs, heading
        if not buf:
            return
        content = "\n\n".join(buf).strip()
        if content:
            chunks.append(
                Chunk(
                    content=content,
                    page_start=min(buf_pages),
                    page_end=max(buf_pages),
                    confidence=sum(buf_confs) / len(buf_confs) if buf_confs else 100.0,
                    section_title=heading,
                )
            )
        buf, buf_pages, buf_confs, heading = [], [], [], None

    for page_no, text, conf in pages:
        for para in re.split(r"\n\s*\n", text):
            para = para.strip()
            if not para:
                continue
            cur_len = sum(len(p) for p in buf)
            if cur_len and cur_len + len(para) > _TARGET_CHARS:
                flush()
            if not buf:
                h = _guess_heading(para)
                if h:
                    heading = h
            if len(para) > _TARGET_CHARS * 1.5:
                # a single overlong paragraph: hard-split on char boundaries
                for i in range(0, len(para), _TARGET_CHARS):
                    buf.append(para[i : i + _TARGET_CHARS])
                    buf_pages.append(page_no)
                    buf_confs.append(conf)
                    flush()
                continue
            buf.append(para)
            buf_pages.append(page_no)
            buf_confs.append(conf)
    flush()

    # merge a trailing tiny chunk into the previous one (avoid 1-line orphans)
    merged: list[Chunk] = []
    for c in chunks:
        if merged and len(c.content) < _MIN_CHARS:
            prev = merged[-1]
            merged[-1] = Chunk(
                content=prev.content + "\n\n" + c.content,
                page_start=prev.page_start,
                page_end=max(prev.page_end, c.page_end),
                confidence=(prev.confidence + c.confidence) / 2,
                section_title=prev.section_title,
            )
        else:
            merged.append(c)
    return merged


# --------------------------------------------------------------------- build

# Below this, OCR output is not text — it's noise (verified against this
# corpus: a Hindi-language tesseract-as-English page reliably scores in the
# 30s-40s, a genuine English page 80s-90s+). Only the `eng` tessdata is
# installed, so a bilingual document's non-English pages cannot be read at
# all right now — store nothing for them rather than embed gibberish that
# could surface as a false "answer".
_MIN_OCR_CONFIDENCE = 60.0


def build_document_preview(spec: DocSpec, warnings: list[str]) -> Optional[dict]:
    if not spec.path.exists():
        warnings.append(f"missing file: {spec.path}")
        return None
    pages = _extract_text_pages(spec)
    if not pages:
        warnings.append(f"no extractable text (OCR or text layer both empty): {spec.path.name}")
        return None

    chunks = chunk_pages(pages)
    dropped_pages: set[int] = set()
    if spec.needs_ocr:
        kept = []
        for c in chunks:
            if c.confidence < _MIN_OCR_CONFIDENCE:
                dropped_pages.update(range(c.page_start, c.page_end + 1))
            else:
                kept.append(c)
        if dropped_pages:
            warnings.append(
                f"{spec.path.name}: page(s) {sorted(dropped_pages)} OCR confidence below "
                f"{_MIN_OCR_CONFIDENCE}% (likely non-English text — only the 'eng' tessdata "
                f"is installed) — excluded; refer to the source PDF directly for that content"
            )
        chunks = kept

    redacted_count = 0
    out_chunks = []
    for idx, c in enumerate(chunks):
        content = c.content
        if spec.sensitive:
            new_content = _redact_sensitive(content)
            if new_content != content:
                redacted_count += 1
            content = new_content
        out_chunks.append(
            {
                "chunk_index": idx,
                "content": content,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "section_title": c.section_title,
                "confidence_score": c.confidence,
                "metadata": {
                    "document_type": spec.document_type,
                    "category": spec.category,
                    "programme": spec.programme,
                    "specialisation": spec.specialisation,
                    "cohort": spec.cohort,
                    "department": spec.department,
                    "classification": spec.classification,
                    "valid_from": spec.valid_from,
                    "valid_until": spec.valid_until,
                },
            }
        )

    return {
        "source_id": spec.path.name,
        "file_name": spec.path.name,
        "title": spec.title,
        "document_type": spec.document_type,
        "classification": spec.classification,
        "category": spec.category,
        "programme": spec.programme,
        "specialisation": spec.specialisation,
        "cohort": spec.cohort,
        "department": spec.department,
        "valid_from": spec.valid_from,
        "valid_until": spec.valid_until,
        "extraction_status": "ocr_completed" if spec.needs_ocr else "completed",
        "extraction_confidence": (
            round(sum(c.confidence for c in chunks) / len(chunks), 1) if chunks else 0.0
        ),
        "sensitive_data_flag": spec.sensitive,
        "redacted_chunks": redacted_count,
        "pages_processed": len(pages),
        "pages_dropped_low_confidence": sorted(dropped_pages),
        "chunks": out_chunks,
    }


# ---------------------------------------------------------------------- embed

def embed_rows(rows: list[dict], document_title: str) -> None:
    """Fill row["embedding_gemini"] for chunk rows about to be written.
    Small paced batches; transient failures back off inside the embeddings
    module, and a hard failure aborts the import before any row without a
    vector is written for this document."""
    batch_size = int(os.environ.get("ORION_EMBED_BATCH_SIZE", 16))
    min_interval = embeddings.batch_interval_s(batch_size)
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        if start:
            time.sleep(min_interval)
        vectors = embeddings.embed_documents(
            [r["content"] for r in batch],
            [embeddings.chunk_title(document_title, r.get("section_title")) for r in batch],
        )
        for r, v in zip(batch, vectors):
            r["embedding_gemini"] = v


# --------------------------------------------------------------------- import

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


def import_previews(previews: list[dict], approved_by: str) -> dict:
    client = get_client()
    totals = {"documents": 0, "versions": 0, "chunks_inserted": 0, "chunks_updated": 0, "chunks_unchanged": 0}

    for d in previews:
        existing = (
            client.table("documents").select("id").eq("source_id", d["source_id"]).limit(1).execute().data
        )
        now = datetime.now(timezone.utc).isoformat()
        doc_row = {
            "title": d["title"],
            "file_name": d["file_name"],
            "document_type": d["document_type"],
            "classification": d["classification"],
            "category": d["category"],
            "programme": d["programme"],
            "specialisation": d["specialisation"],
            "cohort": d["cohort"],
            "department": d["department"],
            "source_id": d["source_id"],
            "valid_from": d["valid_from"],
            "valid_until": d["valid_until"],
            "status": "active",
            "extraction_status": d["extraction_status"],
            "extraction_confidence": d["extraction_confidence"],
            "sensitive_data_flag": d["sensitive_data_flag"],
            "approved_by": None,
            "approved_at": now,
            "published_at": now,
        }
        if existing:
            doc_id = existing[0]["id"]
            client.table("documents").update(doc_row).eq("id", doc_id).execute()
        else:
            inserted = client.table("documents").insert(doc_row).execute().data
            doc_id = inserted[0]["id"]
            totals["documents"] += 1

        existing_v = (
            client.table("document_versions")
            .select("id")
            .eq("document_id", doc_id)
            .eq("source_reference", d["source_id"])
            .limit(1)
            .execute()
            .data
        )
        version_row = {
            "document_id": doc_id,
            "version_label": "v1",
            "source_reference": d["source_id"],
            "valid_from": d["valid_from"],
            "valid_until": d["valid_until"],
            "status": "active",
        }
        if existing_v:
            version_id = existing_v[0]["id"]
            client.table("document_versions").update(version_row).eq("id", version_id).execute()
        else:
            inserted_v = client.table("document_versions").insert(version_row).execute().data
            version_id = inserted_v[0]["id"]
            totals["versions"] += 1

        existing_chunks = {
            c["chunk_index"]: c
            for c in client.table("document_chunks")
            .select("id,chunk_index,content,confidence_score")
            .eq("document_id", doc_id)
            .eq("version_id", version_id)
            .execute()
            .data
        }
        to_insert = []
        to_update = []
        for c in d["chunks"]:
            row = {
                "document_id": doc_id,
                "version_id": version_id,
                "chunk_index": c["chunk_index"],
                "content": c["content"],
                "page_start": c["page_start"],
                "page_end": c["page_end"],
                "section_title": c["section_title"],
                "metadata": c["metadata"],
                "confidence_score": c["confidence_score"],
            }
            cur = existing_chunks.get(c["chunk_index"])
            if cur is None:
                to_insert.append(row)
            elif cur["content"] != c["content"]:
                to_update.append((cur["id"], row))
            else:
                totals["chunks_unchanged"] += 1
        embed_rows(to_insert + [row for _, row in to_update], d["title"])
        for _, row in to_update:
            # Content changed: the old MiniLM vector describes the old text.
            row["embedding"] = None
        for start in range(0, len(to_insert), 100):
            client.table("document_chunks").insert(to_insert[start : start + 100]).execute()
        for cid, row in to_update:
            client.table("document_chunks").update(row).eq("id", cid).execute()
        totals["chunks_inserted"] += len(to_insert)
        totals["chunks_updated"] += len(to_update)

        print(
            f"  [{d['source_id']}] chunks: insert={len(to_insert)} update={len(to_update)} "
            f"unchanged={len(d['chunks']) - len(to_insert) - len(to_update)}"
        )

    client.table("ingestion_runs").insert(
        {
            "source_id": "Data/Unstructured (document ingestion batch)",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "imported",
            "stats": totals,
            "validation_errors": 0,
            "validation_warnings": 0,
            "approved_by": approved_by,
        }
    ).execute()
    return totals


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest Data/Unstructured (+ Hostel Rules) into document_chunks.")
    ap.add_argument("--import", dest="do_import", action="store_true")
    ap.add_argument("--approved-by", default=None)
    ap.add_argument("--only", default=None, help="substring filter on file name, for a partial run")
    ap.add_argument("--out-dir", default="Data/processed")
    args = ap.parse_args()

    specs = DOCUMENT_SPECS
    if args.only:
        specs = [s for s in specs if args.only.lower() in s.path.name.lower()]
        if not specs:
            print(f"error: no document matches --only {args.only!r}", file=sys.stderr)
            return 2

    warnings: list[str] = []
    previews: list[dict] = []
    for spec in specs:
        print(f"extracting: {spec.path.name} ({'OCR' if spec.needs_ocr else 'text'}) ...")
        d = build_document_preview(spec, warnings)
        if d:
            previews.append(d)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    preview_path = out / "documents_preview.json"
    preview_path.write_text(json.dumps({"documents": previews, "warnings": warnings}, indent=2))

    total_chunks = sum(len(d["chunks"]) for d in previews)
    print(f"\ndocuments:    {len(previews)}")
    print(f"chunks:       {total_chunks}")
    print(f"warnings:     {len(warnings)}")
    for w in warnings:
        print(f"  [warn] {w}")
    for d in previews:
        flag = " [SENSITIVE, redacted]" if d["sensitive_data_flag"] else ""
        print(
            f"  - {d['source_id']}: {len(d['chunks'])} chunks, "
            f"confidence={d['extraction_confidence']}%{flag}"
        )
    print(f"preview:      {preview_path}")

    if not args.do_import:
        print("\ndry run complete (no embeddings computed) — re-run with --import to embed + write to Supabase")
        return 0

    if not args.approved_by:
        print("error: --import requires --approved-by", file=sys.stderr)
        return 2

    load_env()
    if not embeddings.is_configured():
        print("error: --import needs GEMINI_API_KEY to embed chunks", file=sys.stderr)
        return 2
    stats = import_previews(previews, args.approved_by)
    print("\nfinal stats:", json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
