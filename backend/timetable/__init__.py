"""ORION timetable ingestion pipeline (Semester 3, Odd 2026).

Layout-aware extraction from the official timetable PDFs → normalization →
strict validation → preview JSON → (admin approval) → Supabase PostgreSQL.

Nothing here is hard-coded institutional data: period times, courses, faculty
and validity windows all come from the source document or its headers.
"""

from .extractor import (
    GridCell,
    Legend,
    LegendEntry,
    PeriodColumn,
    Section,
    TimetableDocument,
    extract_document,
)
from .model import (
    TimetableRecord,
    document_metadata,
    entry_type_from_cell,
    parse_day_row,
    parse_period_header,
)
from .normalizer import NormalizationResult, build_preview, dedupe, normalize_section
from .validator import ValidationIssue, ValidationReport, validate_records

__all__ = [
    "GridCell",
    "Legend",
    "LegendEntry",
    "NormalizationResult",
    "PeriodColumn",
    "Section",
    "TimetableDocument",
    "TimetableRecord",
    "ValidationIssue",
    "ValidationReport",
    "build_preview",
    "dedupe",
    "document_metadata",
    "entry_type_from_cell",
    "extract_document",
    "normalize_section",
    "parse_day_row",
    "parse_period_header",
    "validate_records",
]
