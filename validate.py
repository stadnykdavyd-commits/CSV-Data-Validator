#!/usr/bin/env python3
"""Clean and validate a CSV: emails, phone numbers, IBANs, duplicates.

Examples:
  python validate.py customers.csv
  python validate.py customers.csv --country-code 49 --dedupe-on email
  python validate.py data.csv --email Contact --phone Mobile --iban Bank -o results
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from datavalidator.engine import Config, detect_columns, process, read_csv, write_csv
from datavalidator.report import build_report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Validate and clean a CSV file. The original is never modified.")
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, default=None, help="output folder (default: 'output' next to the input)")
    p.add_argument("--email", metavar="COL", help="email column (default: auto-detect)")
    p.add_argument("--phone", metavar="COL", help="phone column (default: auto-detect)")
    p.add_argument("--iban", metavar="COL", help="IBAN column (default: auto-detect)")
    p.add_argument("--country-code", default="", metavar="CC",
                   help="calling code for national phone numbers, e.g. 49 for Germany (a leading 0 is replaced)")
    p.add_argument("--dedupe-on", default=None, metavar="COLS",
                   help="comma-separated columns that identify a duplicate (default: the email column, if any)")
    p.add_argument("--require", default="", metavar="COLS", help="comma-separated columns that must not be empty")
    args = p.parse_args(argv)

    try:
        fieldnames, rows, delimiter = read_csv(args.input)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    columns = detect_columns(fieldnames)
    for kind, name in (("email", args.email), ("phone", args.phone), ("iban", args.iban)):
        if name:
            if name not in fieldnames:
                print(f"Error: column '{name}' not found. Columns: {', '.join(fieldnames)}", file=sys.stderr)
                return 1
            columns = {c: k for c, k in columns.items() if k != kind}
            columns[name] = kind

    email_col = next((c for c, k in columns.items() if k == "email"), None)
    dedupe = [c.strip() for c in args.dedupe_on.split(",") if c.strip()] if args.dedupe_on is not None else (
        [email_col] if email_col else [])
    required = [c.strip() for c in args.require.split(",") if c.strip()]
    missing = [c for c in dedupe + required if c not in fieldnames]
    if missing:
        print(f"Error: unknown column(s): {', '.join(missing)}", file=sys.stderr)
        return 1

    cfg = Config(columns=columns, country_code=args.country_code.lstrip("+"), dedupe_on=dedupe, required=required)
    outcome = process(fieldnames, rows, cfg)

    out_dir = args.output or args.input.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "cleaned.csv", fieldnames, outcome.clean_rows, delimiter)
    write_csv(out_dir / "rejected.csv", fieldnames + ["_row", "_reasons"], outcome.rejected, delimiter)
    (out_dir / "report.md").write_text(build_report(outcome, args.input.name), encoding="utf-8")

    print(f"{outcome.total} rows -> {len(outcome.clean_rows)} clean, {len(outcome.rejected)} rejected "
          f"({outcome.duplicates} duplicates). Files in: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
