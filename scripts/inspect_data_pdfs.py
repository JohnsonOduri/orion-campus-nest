"""Dependency-free PDF inspector for the ORION Data folder.

Extracts per-file metadata (page count, producer, encryption) and attempts
text extraction by decompressing FlateDecode streams and reading Tj/TJ text
operators. Read-only analysis; prints a JSON report.
"""

import json
import re
import sys
import zlib
from pathlib import Path

DATA_DIR = Path("Data")

TEXT_OPERATORS = re.compile(
    rb"\((?:\\.|[^\\()])*\)\s*Tj"          # (text) Tj
    rb"|<[^>]*>\s*Tj"                       # <hex> Tj
    rb"|\[(?:[^\[\]]|\\.)*\]\s*TJ"          # [(text) ...] TJ
    rb"|T\*"                                # line break
    rb"|Td|TD"                              # positioning (approx newline)
)


def decode_pdf_string(raw: bytes) -> str:
    """Decode a PDF literal string, handling escapes and UTF-16/latin fallback."""
    if raw.startswith(b"\xfe\xff"):
        try:
            return raw[2:].decode("utf-16-be", errors="replace")
        except Exception:
            return raw.decode("latin-1", errors="replace")
    out = []
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == 0x5C and i + 1 < len(raw):  # backslash
            nxt = raw[i + 1]
            mapping = {0x6E: "\n", 0x72: "\r", 0x74: "\t", 0x62: "\b", 0x66: "\f"}
            if nxt in mapping:
                out.append(mapping[nxt])
                i += 2
                continue
            if 0x30 <= nxt <= 0x37:  # octal escape (up to 3 digits)
                j = i + 1
                digits = b""
                while j < len(raw) and len(digits) < 3 and 0x30 <= raw[j] <= 0x37:
                    digits += bytes([raw[j]])
                    j += 1
                out.append(chr(int(digits, 8) & 0xFF))
                i = j
                continue
            out.append(chr(nxt))
            i += 2
            continue
        out.append(chr(c))
        i += 1
    return "".join(out)


def extract_stream_text(content: bytes) -> str:
    """Pull readable text out of a decompressed content stream."""
    pieces = []
    # (string) Tj
    for m in re.finditer(rb"\(((?:\\.|[^\\()])*)\)\s*Tj", content):
        pieces.append(decode_pdf_string(m.group(1)))
        pieces.append(" ")
    # <hex> Tj
    for m in re.finditer(rb"<([0-9A-Fa-f\s]+)>\s*Tj", content):
        hx = re.sub(rb"\s", b"", m.group(1))
        try:
            data = bytes.fromhex(hx.decode("ascii"))
            pieces.append(decode_pdf_string(data))
            pieces.append(" ")
        except Exception:
            pass
    # [ (a) 120 (b) ... ] TJ
    for m in re.finditer(rb"\[((?:[^\[\]\\\\]|\\.)*)\]\s*TJ", content):
        inner = m.group(1)
        for sm in re.finditer(rb"\(((?:\\.|[^\\()])*)\)", inner):
            pieces.append(decode_pdf_string(sm.group(1)))
        pieces.append(" ")
    text = "".join(pieces)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"(\s*\n)+", "\n", text)
    return text.strip()


def parse_pdf(path: Path) -> dict:
    raw = path.read_bytes()
    info = {
        "path": str(path),
        "size_bytes": len(raw),
        "encrypted": b"/Encrypt" in raw,
        "pages": raw.count(b"/Type /Page") - raw.count(b"/Type /Pages"),
        "producer": None,
        "creator": None,
        "has_embedded_text": False,
        "text_chars": 0,
        "text_preview": "",
        "images_estimate": len(re.findall(rb"/Subtype\s*/Image", raw)),
        "fonts": sorted({f.decode("latin-1", "replace") for f in re.findall(rb"/BaseFont\s*/([A-Za-z0-9+\-,]+)", raw)})[:10],
    }

    m = re.search(rb"/Producer\s*\(([^)]*)\)", raw)
    if m:
        info["producer"] = decode_pdf_string(m.group(1))[:80]
    m = re.search(rb"/Creator\s*\(([^)]*)\)", raw)
    if m:
        info["creator"] = decode_pdf_string(m.group(1))[:80]

    # Extract and decompress FlateDecode streams.
    all_text = []
    for sm in re.finditer(rb"stream\r?\n", raw):
        start = sm.end()
        end = raw.find(b"endstream", start)
        if end == -1:
            continue
        chunk = raw[start:end]
        try:
            data = zlib.decompress(chunk)
        except Exception:
            continue
        if b"Tj" in data or b"TJ" in data:
            txt = extract_stream_text(data)
            if txt:
                all_text.append(txt)

    combined = "\n".join(all_text)
    info["has_embedded_text"] = len(combined) > 40
    info["text_chars"] = len(combined)
    info["text_preview"] = combined[:1200]
    return info


def main() -> int:
    pdfs = sorted(DATA_DIR.rglob("*.pdf"))
    if not pdfs:
        print(json.dumps({"error": "no PDFs found"}))
        return 1
    report = [parse_pdf(p) for p in pdfs]
    json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
