"""Before/after report in Markdown."""

from __future__ import annotations

import re
from collections import Counter

from .engine import Outcome

MAX_EXAMPLES = 8


def build_report(out: Outcome, source_name: str) -> str:
    total, ok, bad = out.total, len(out.clean_rows), len(out.rejected)
    pct = lambda n: f"{(100 * n / total):.1f}%" if total else "-"
    lines = [
        f"# Data validation report: {source_name}",
        "",
        "## Before / after",
        "",
        "| | Rows | Share |",
        "|---|---:|---:|",
        f"| Input | {total} | 100% |",
        f"| Clean (cleaned.csv) | {ok} | {pct(ok)} |",
        f"| Rejected (rejected.csv) | {bad} | {pct(bad)} |",
        f"| of which duplicates | {out.duplicates} | {pct(out.duplicates)} |",
        "",
        "## Checked columns",
        "",
    ]
    if out.config.columns:
        for col, kind in out.config.columns.items():
            errs = sum(1 for i in out.issues if i.column == col and i.level == "error")
            warns = sum(1 for i in out.issues if i.column == col and i.level == "warning")
            lines.append(f"- **{col}** ({kind}): {errs} invalid, {warns} warnings, {out.fixes.get(kind, 0)} normalized")
    else:
        lines.append("- none detected (use --email / --phone / --iban to choose columns)")
    if out.config.dedupe_on:
        lines.append(f"- duplicates checked on: {', '.join(out.config.dedupe_on)}")
    lines += ["", f"Whitespace cleaned in {out.whitespace_fixed} cells.", ""]

    errors = [i for i in out.issues if i.level == "error"]
    if errors:
        lines += ["## Most common problems", "", "| Problem | Count |", "|---|---:|"]
        kinds = Counter(f"{i.column}: {_generic(i.message)}" for i in errors)
        for msg, n in kinds.most_common(10):
            lines.append(f"| {msg} | {n} |")
        lines += ["", "## Examples", "", "| Row | Column | Value | Problem |", "|---:|---|---|---|"]
        for i in errors[:MAX_EXAMPLES * 2]:
            lines.append(f"| {i.row} | {i.column} | `{i.value}` | {i.message} |")
        if len(errors) > MAX_EXAMPLES * 2:
            lines.append(f"| ... | | | {len(errors) - MAX_EXAMPLES * 2} more in rejected.csv |")
        lines.append("")

    warnings = [i for i in out.issues if i.level == "warning"]
    if warnings:
        lines += ["## Warnings (kept in cleaned.csv, please review)", "", "| Row | Column | Value | Hint |", "|---:|---|---|---|"]
        for i in warnings[:MAX_EXAMPLES * 2]:
            lines.append(f"| {i.row} | {i.column} | `{i.value}` | {i.message} |")
        lines.append("")
    return "\n".join(lines)


def _generic(message: str) -> str:
    """Group messages that only differ in numbers (e.g. '7 digits' / '6 digits')."""
    message = re.sub(r"^\d+ digits", "N digits", message)
    message = re.sub(r"duplicate of row \d+", "duplicate of an earlier row", message)
    message = re.sub(r"must be \d+ characters, got \d+", "wrong length for the country", message)
    return re.sub(r"\(\w{2} IBAN\)", "", message)
