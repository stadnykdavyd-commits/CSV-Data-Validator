"""Single-value validators. Each returns Check(ok, value, message, warning):
`value` is the cleaned/normalized form, `message` explains a failure, `warning` is a soft hint."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Check:
    ok: bool
    value: str            # normalized value (original, trimmed, if it is invalid)
    message: str = ""     # why it failed
    warning: str = ""     # valid, but worth a look (e.g. probable typo)
    fixed: bool = False   # the normalized value differs from the input in a meaningful way


def clean_text(value: str) -> str:
    """Trim and collapse whitespace, including non-breaking spaces and zero-width characters."""
    value = value.replace(" ", " ").replace("​", "").replace("﻿", "")
    return " ".join(value.split())


# ----- email --------------------------------------------------------------------------------

_LOCAL = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+")
_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")

COMMON_TYPOS = {
    "gmial.com": "gmail.com", "gmal.com": "gmail.com", "gamil.com": "gmail.com", "gmail.co": "gmail.com",
    "gmail.con": "gmail.com", "gnail.com": "gmail.com", "hotmial.com": "hotmail.com",
    "hotmal.com": "hotmail.com", "yaho.com": "yahoo.com", "yahooo.com": "yahoo.com",
    "outlok.com": "outlook.com", "outllok.com": "outlook.com", "icloud.con": "icloud.com",
}


def check_email(raw: str) -> Check:
    value = clean_text(raw).lower()
    if value.startswith("mailto:"):
        value = value[7:]
    value = value.strip("<>,;")
    if not value:
        return Check(False, value, "empty")
    if value.count("@") != 1:
        return Check(False, value, "must contain exactly one '@'")
    local, domain = value.split("@")
    if not local or len(local) > 64:
        return Check(False, value, "local part is empty or longer than 64 characters")
    if not _LOCAL.fullmatch(local) or local.startswith(".") or local.endswith(".") or ".." in local:
        return Check(False, value, "invalid characters or dots in the part before '@'")
    labels = domain.split(".")
    if len(labels) < 2 or len(domain) > 253 or not all(_LABEL.fullmatch(l) for l in labels):
        return Check(False, value, "invalid domain")
    if not re.fullmatch(r"[a-z]{2,}|xn--[a-z0-9-]+", labels[-1]):
        return Check(False, value, "invalid top-level domain")
    warning = ""
    if domain in COMMON_TYPOS:
        warning = f"probable typo, did you mean @{COMMON_TYPOS[domain]}?"
    return Check(True, value, warning=warning, fixed=value != raw)


# ----- phone --------------------------------------------------------------------------------

def check_phone(raw: str, country_code: str = "") -> Check:
    """Normalize to international format (+4917612345678). `country_code` (e.g. '49') is used
    for national numbers that start with a single 0. Length rule: 8-15 digits (ITU E.164)."""
    text = clean_text(raw)
    if not text:
        return Check(False, text, "empty")
    # drop an extension, then everything that is not a digit or a leading +
    text = re.split(r"(?i)\b(?:ext\.?|x|доб\.?)\s*\d+$", text)[0]
    plus = text.lstrip().startswith("+")
    digits = re.sub(r"\D", "", text)
    if re.search(r"[A-Za-zА-Яа-я]", re.sub(r"(?i)\b(?:ext|x|доб)\b", "", text)):
        return Check(False, clean_text(raw), "contains letters")
    if plus:
        pass
    elif digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0") and country_code:
        digits = country_code + digits[1:]
    elif not country_code:
        return Check(False, clean_text(raw), "no country code (use +CC... or pass --country-code)")
    else:
        digits = country_code + digits
    if digits.startswith("0"):
        return Check(False, clean_text(raw), "country code cannot start with 0")
    if not 8 <= len(digits) <= 15:
        return Check(False, clean_text(raw), f"{len(digits)} digits (need 8-15)")
    if len(set(digits)) == 1:
        return Check(False, clean_text(raw), "all digits identical")
    normalized = "+" + digits
    return Check(True, normalized, fixed=normalized != raw.strip())


# ----- IBAN ---------------------------------------------------------------------------------

IBAN_LENGTHS = {
    "AD": 24, "AL": 28, "AT": 20, "AZ": 28, "BA": 20, "BE": 16, "BG": 22, "BH": 22, "BR": 29, "CH": 21,
    "CR": 22, "CY": 28, "CZ": 24, "DE": 22, "DK": 18, "DO": 28, "EE": 20, "ES": 24, "FI": 18, "FO": 18,
    "FR": 27, "GB": 22, "GE": 22, "GI": 23, "GL": 18, "GR": 27, "GT": 28, "HR": 21, "HU": 28, "IE": 22,
    "IL": 23, "IS": 26, "IT": 27, "JO": 30, "KW": 30, "KZ": 20, "LB": 28, "LI": 21, "LT": 20, "LU": 20,
    "LV": 21, "MC": 27, "MD": 24, "ME": 22, "MK": 19, "MR": 27, "MT": 31, "MU": 30, "NL": 18, "NO": 15,
    "PK": 24, "PL": 28, "PS": 29, "PT": 25, "QA": 29, "RO": 24, "RS": 22, "SA": 24, "SE": 24, "SI": 19,
    "SK": 24, "SM": 27, "TN": 24, "TR": 26, "UA": 29, "VA": 22, "VG": 24, "XK": 20,
}


def iban_mod97(iban: str) -> bool:
    """ISO 13616: move the first 4 characters to the end, letters -> numbers (A=10..Z=35), mod 97 == 1."""
    rearranged = iban[4:] + iban[:4]
    number = "".join(str(int(c, 36)) for c in rearranged)
    return int(number) % 97 == 1


def check_iban(raw: str) -> Check:
    value = re.sub(r"[\s\-.]", "", clean_text(raw)).upper()
    if not value:
        return Check(False, value, "empty")
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]+", value):
        return Check(False, clean_text(raw), "must start with 2 letters + 2 check digits, then letters/digits only")
    country = value[:2]
    expected = IBAN_LENGTHS.get(country)
    if expected is None:
        return Check(False, value, f"unknown country code {country}")
    if len(value) != expected:
        return Check(False, value, f"{country} IBAN must be {expected} characters, got {len(value)}")
    if not iban_mod97(value):
        return Check(False, value, "check digits are wrong (mod-97 failed), probably a typo")
    return Check(True, value, fixed=value != raw.strip())
