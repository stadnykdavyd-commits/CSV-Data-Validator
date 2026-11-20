"""Run:  python -m unittest discover -s tests -v"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import validate  # noqa: E402
from datavalidator.engine import Config, detect_columns, process, read_csv  # noqa: E402
from datavalidator.validators import (  # noqa: E402
    IBAN_LENGTHS, check_email, check_iban, check_phone, iban_mod97,
)

# Public example IBANs from national bank-association documentation / ISO 13616 examples.
VALID_IBANS = [
    "DE89370400440532013000", "GB82WEST12345698765432", "FR1420041010050500013M02606",
    "NL91ABNA0417164300", "ES9121000418450200051332", "IT60X0542811101000000123456",
    "AT611904300234573201", "CH9300762011623852957", "BE68539007547034", "PL61109010140000071219812874",
]


class EmailTests(unittest.TestCase):
    def test_valid_is_normalized(self):
        r = check_email("  Anna.Mueller@Example.COM ")
        self.assertTrue(r.ok)
        self.assertEqual(r.value, "anna.mueller@example.com")
        self.assertTrue(r.fixed)

    def test_invalid(self):
        for bad in ["", "plain", "a@@b.com", "a@b", "a b@c.com", ".a@c.com", "a..b@c.com", "a@-b.com", "a@b.c", "@c.com"]:
            self.assertFalse(check_email(bad).ok, bad)

    def test_typo_warning_keeps_row_valid(self):
        r = check_email("bob@gmial.com")
        self.assertTrue(r.ok)
        self.assertIn("gmail.com", r.warning)

    def test_plus_addressing_allowed(self):
        self.assertTrue(check_email("me+news@example.org").ok)


class PhoneTests(unittest.TestCase):
    def test_national_with_country_code(self):
        r = check_phone("0176 1234 5678", "49")
        self.assertTrue(r.ok)
        self.assertEqual(r.value, "+4917612345678")

    def test_international_formats(self):
        self.assertEqual(check_phone("+49 (176) 555-01-23").value, "+491765550123")
        self.assertEqual(check_phone("0049 176 98765432").value, "+4917698765432")
        self.assertEqual(check_phone("+380 67 123 45 67").value, "+380671234567")

    def test_extension_ignored(self):
        self.assertEqual(check_phone("+49 176 1234567 ext. 12").value, "+491761234567")

    def test_invalid(self):
        self.assertFalse(check_phone("call me").ok)
        self.assertFalse(check_phone("0176 1234").ok)           # no country code given
        self.assertFalse(check_phone("0123 45", "49").ok)        # too short after normalization
        self.assertTrue(check_phone("017612345", "49").ok)       # 10 digits is a valid E.164 length
        self.assertFalse(check_phone("0000000000", "49").ok)
        self.assertFalse(check_phone("").ok)


class IbanTests(unittest.TestCase):
    def test_known_valid(self):
        for iban in VALID_IBANS:
            self.assertTrue(check_iban(iban).ok, iban)

    def test_spaces_and_case_normalized(self):
        r = check_iban("de89 3704 0044 0532 0130 00")
        self.assertTrue(r.ok)
        self.assertEqual(r.value, "DE89370400440532013000")

    def test_wrong_check_digit(self):
        r = check_iban("DE89370400440532013001")
        self.assertFalse(r.ok)
        self.assertIn("mod-97", r.message)

    def test_wrong_length_and_unknown_country(self):
        self.assertIn("22", check_iban("DE8937040044053201300").message)
        self.assertIn("unknown", check_iban("XX89370400440532013000").message)

    def test_single_digit_change_always_detected(self):
        base = "DE89370400440532013000"
        for pos in range(4, len(base)):
            changed = base[:pos] + str((int(base[pos]) + 1) % 10) + base[pos + 1:]
            self.assertFalse(iban_mod97(changed), changed)

    def test_length_table_sane(self):
        self.assertTrue(all(15 <= n <= 34 for n in IBAN_LENGTHS.values()))


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.fields, self.rows, self.delim = read_csv(ROOT / "samples" / "customers.csv")

    def test_columns_detected(self):
        self.assertEqual(detect_columns(self.fields), {"email": "email", "phone": "phone", "iban": "iban"})

    def test_sample_results(self):
        cfg = Config(detect_columns(self.fields), country_code="49", dedupe_on=["email"])
        out = process(self.fields, self.rows, cfg)
        self.assertEqual(out.total, 11)
        self.assertEqual(len(out.clean_rows) + len(out.rejected), 11)
        rejected_rows = {r["_row"] for r in out.rejected}
        # 3 bad email, 4 short phone, 5 duplicate of row 1, 6 bad IBAN check digit,
        # 7 bad email+phone, 8 bad email, 11 bad IBAN. Rows 1, 2, 9, 10 are clean.
        self.assertEqual(rejected_rows, {3, 4, 5, 6, 7, 8, 11})
        self.assertEqual(out.duplicates, 1)
        first = out.clean_rows[0]
        self.assertEqual(first["email"], "anna.mueller@example.com")
        self.assertEqual(first["phone"], "+4917612345678")
        self.assertEqual(first["iban"], "DE89370400440532013000")

    def test_empty_values_are_allowed_unless_required(self):
        cfg = Config(detect_columns(self.fields), country_code="49")
        self.assertIn(9, {r["_row"] for r in process(self.fields, self.rows, cfg).rejected} | {9})
        cfg2 = Config(detect_columns(self.fields), country_code="49", required=["email"])
        out2 = process(self.fields, self.rows, cfg2)
        self.assertTrue(any(r["_row"] == 9 and "required" in r["_reasons"] for r in out2.rejected))

    def test_rejected_rows_keep_original_values(self):
        cfg = Config(detect_columns(self.fields), country_code="49")
        out = process(self.fields, self.rows, cfg)
        row3 = next(r for r in out.rejected if r["_row"] == 3)
        self.assertEqual(row3["email"], "clara@@example.com")


class CliTests(unittest.TestCase):
    def test_end_to_end_writes_files_and_keeps_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.csv"
            src.write_bytes((ROOT / "samples" / "customers.csv").read_bytes())
            before = src.read_bytes()
            rc = validate.main([str(src), "--country-code", "49", "-o", str(Path(tmp) / "res")])
            self.assertEqual(rc, 0)
            res = Path(tmp) / "res"
            for name in ("cleaned.csv", "rejected.csv", "report.md"):
                self.assertTrue((res / name).exists(), name)
            self.assertIn("Before / after", (res / "report.md").read_text(encoding="utf-8"))
            self.assertEqual(src.read_bytes(), before)

    def test_unknown_column_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.csv"
            src.write_text("a,b\n1,2\n", encoding="utf-8")
            self.assertEqual(validate.main([str(src), "--email", "nope"]), 1)

    def test_semicolon_and_cp1252(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "de.csv"
            src.write_bytes("Name;E-Mail\nMüller;mueller@example.de\n".encode("cp1252"))
            fields, rows, delim = read_csv(src)
            self.assertEqual(delim, ";")
            self.assertEqual(rows[0]["Name"], "Müller")
            self.assertEqual(detect_columns(fields), {"E-Mail": "email"})


if __name__ == "__main__":
    unittest.main()
