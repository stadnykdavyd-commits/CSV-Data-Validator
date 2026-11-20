# CSV Data Validator

Command-line tool that cleans and validates a CSV file and tells you exactly what was wrong.
Pure Python standard library, no installation of packages needed.

```
customers.csv ──► validate ──► cleaned.csv    (valid rows, values normalized)
                          ├──► rejected.csv   (invalid rows + the reason for each)
                          └──► report.md      (before / after summary, common problems, examples)
```

## What it checks

| Check | What it does |
|---|---|
| **Email** | syntax (single `@`, valid characters, dots, domain, TLD), lowercases and trims; warns about probable typos like `@gmial.com` (kept, not rejected) |
| **Phone** | normalizes `0176 1234 5678`, `0049 176…`, `+49 (176) 555-01-23` to `+4917612345678`; rejects letters, too short/long (8–15 digits, ITU E.164), identical digits; national numbers need `--country-code` |
| **IBAN** | removes spaces, uppercases, checks country length (about 70 countries) and the **ISO 13616 mod-97 checksum**, so a single mistyped digit is always caught |
| **Duplicates** | on the email column by default, or on any columns with `--dedupe-on` (case-insensitive; the first row is kept) |
| **Whitespace** | trims and collapses spaces in every cell, including non-breaking and zero-width spaces |
| **Required** | `--require COLS` rejects rows where those columns are empty |

It also handles UTF-8 (with or without BOM) and Windows-1252 files, and detects `,` `;` tab and `|` separators. Output is UTF-8 with BOM so Excel opens umlauts correctly.
Your original file is **never modified**.

## Usage

```bash
python validate.py samples/customers.csv --country-code 49
python validate.py data.csv --email Contact --phone Mobile --iban Bank -o results
python validate.py data.csv --dedupe-on email,phone --require email
```

Columns named like `email`, `phone`/`mobile`/`tel`, `iban` are detected automatically; use `--email`, `--phone`, `--iban` to point at others.

## Example

Input `samples/customers.csv` (11 rows) → 4 clean, 7 rejected (1 duplicate):

```
| Row | Column | Value                        | Problem                                      |
|   3 | email  | clara@@example.com           | must contain exactly one '@'                 |
|   4 | phone  | 0123 45                      | 7 digits (need 8-15)                         |
|   5 | email  | anna.mueller@example.com     | duplicate of row 1                           |
|   6 | iban   | DE89 3704 0044 0532 0130 01  | check digits are wrong (mod-97 failed)       |
|   8 | email  | gina@example                 | invalid domain                               |
```

## Tests

```bash
python -m unittest discover -s tests -v
```

21 tests, including IBAN checks on 10 published example numbers and a check that changing any single digit of an IBAN breaks the checksum.

## Limits

- Email checking is syntactic: it does not verify that the mailbox exists.
- Phone checking verifies format and length, not that the number is assigned.
- IBAN country list covers the common IBAN countries; unknown country codes are rejected.

## License

MIT
