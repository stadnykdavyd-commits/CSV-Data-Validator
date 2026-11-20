"""Read a CSV, validate/normalize the chosen columns, find duplicates, write results."""

from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .validators import Check, check_email, check_iban, check_phone, clean_text

KIND_HINTS = {
    "email": ("email", "e-mail", "e_mail", "mail", "почта", "пошта"),
    "phone": ("phone", "mobile", "tel", "handy", "телефон", "тел"),
    "iban": ("iban",),
}


@dataclass
class Config:
    columns: dict[str, str] = field(default_factory=dict)   # column name -> kind (email/phone/iban)
    country_code: str = ""
    dedupe_on: list[str] = field(default_factory=list)
    required: list[str] = field(default_factory=list)


@dataclass
class Issue:
    row: int            # 1-based data row number (header not counted)
    column: str
    value: str
    message: str
    level: str = "error"   # error | warning


@dataclass
class Outcome:
    fieldnames: list[str]
    total: int
    clean_rows: list[dict]
    rejected: list[dict]          # original row + "_row", "_reasons"
    issues: list[Issue]
    fixes: Counter               # kind -> number of values normalized
    duplicates: int
    whitespace_fixed: int
    config: Config


# ----- reading ------------------------------------------------------------------------------

def read_csv(path: Path) -> tuple[list[str], list[dict], str]:
    """Return (fieldnames, rows, delimiter). Handles UTF-8 (with/without BOM) and Windows-1252."""
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - cp1252 only fails on a few undefined bytes
        text = raw.decode("utf-8", errors="replace")
    sample = text[:4096]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = ","
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("The file is empty or has no header row.")
    names = [clean_text(n) for n in reader.fieldnames]
    if len(set(names)) != len(names):
        raise ValueError(f"Duplicate column names in the header: {names}")
    rows = []
    for r in reader:
        rows.append({clean_text(k or ""): (v or "") for k, v in r.items() if k is not None})
    return names, rows, delimiter


def detect_columns(fieldnames: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for name in fieldnames:
        low = name.lower()
        for kind, hints in KIND_HINTS.items():
            if kind not in found.values() and any(h in low for h in hints):
                found[name] = kind
                break
    return found


# ----- processing ---------------------------------------------------------------------------

def _validate(kind: str, value: str, cfg: Config) -> Check:
    if kind == "email":
        return check_email(value)
    if kind == "phone":
        return check_phone(value, cfg.country_code)
    return check_iban(value)


def process(fieldnames: list[str], rows: list[dict], cfg: Config) -> Outcome:
    issues: list[Issue] = []
    fixes: Counter = Counter()
    clean_rows: list[dict] = []
    rejected: list[dict] = []
    seen: dict[tuple, int] = {}
    duplicates = 0
    ws_fixed = 0

    dedupe_cols = cfg.dedupe_on
    for i, original in enumerate(rows, 1):
        row = dict(original)
        reasons: list[str] = []

        for col in fieldnames:                      # whitespace clean-up everywhere
            before = row.get(col, "")
            after = clean_text(before)
            if after != before:
                ws_fixed += 1
            row[col] = after

        for col, kind in cfg.columns.items():
            value = row.get(col, "")
            if not value:
                if col in cfg.required:
                    reasons.append(f"{col}: required value is missing")
                    issues.append(Issue(i, col, "", "required value is missing"))
                continue
            res = _validate(kind, value, cfg)
            if res.ok:
                if res.fixed and res.value != value:
                    fixes[kind] += 1
                row[col] = res.value
                if res.warning:
                    issues.append(Issue(i, col, value, res.warning, "warning"))
            else:
                reasons.append(f"{col}: {res.message}")
                issues.append(Issue(i, col, value, res.message))

        if not reasons and dedupe_cols:
            key = tuple(row.get(c, "").lower() for c in dedupe_cols)
            if any(key):
                if key in seen:
                    duplicates += 1
                    reasons.append(f"duplicate of row {seen[key]} ({', '.join(dedupe_cols)})")
                    issues.append(Issue(i, ", ".join(dedupe_cols), " | ".join(key), f"duplicate of row {seen[key]}"))
                else:
                    seen[key] = i

        if reasons:
            rejected.append({**original, "_row": i, "_reasons": "; ".join(reasons)})
        else:
            clean_rows.append(row)

    return Outcome(fieldnames, len(rows), clean_rows, rejected, issues, fixes, duplicates, ws_fixed, cfg)


# ----- writing ------------------------------------------------------------------------------

def write_csv(path: Path, fieldnames: list[str], rows: list[dict], delimiter: str = ",") -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as fh:   # BOM so Excel opens UTF-8 correctly
        w = csv.DictWriter(fh, fieldnames=fieldnames, delimiter=delimiter, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
