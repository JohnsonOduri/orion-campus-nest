"""Regenerate backend/query/data/protected_words.txt.

The spelling corrector (backend/query/lexicon.py) snaps typos to the nearest
campus word. A real English word that happens to sit near a campus word
("hostile" / "hostel", "clause" / "classes") must never be "corrected", so
this writes every dictionary word within the corrector's own edit limit of
some campus word. Only those neighbours matter, which keeps the file small
and makes the corrector behave identically on every machine (Render has no
system dictionary).

Usage: .venv/bin/python scripts/build_lexicon_data.py [--dict /usr/share/dict/words]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from query import lexicon  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dict", default="/usr/share/dict/words")
    args = ap.parse_args()
    words = {w.strip() for w in Path(args.dict).read_text().split() if w.strip().isalpha() and w.strip().islower()}
    domain = lexicon.DOMAIN_WORDS
    keep: set[str] = set()
    for w in words:
        if len(w) < 4 or w in domain:
            continue
        limit = 1.0 if len(w) <= 5 else 2.0
        for d in domain:
            if abs(len(d) - len(w)) <= limit and lexicon.edit_distance(w, d) <= limit:
                keep.add(w)
                break
    out = ROOT / "backend" / "query" / "data" / "protected_words.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(sorted(keep)) + "\n")
    print(f"{len(keep)} protected words -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
