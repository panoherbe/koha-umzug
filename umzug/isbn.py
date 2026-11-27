"""ISBN field (MAB 540) checks, the same rules as the Probe-Check on panoherbe.com/projekte/koha-umzug/ausprobieren.

Since 2026-11-27. Common patterns in MAB2 exports of small libraries: many ISBN fields hold only the word „ISBN“, some
miss the leading 9 of 978, some hold an ISSN. What needs no decision is done automatically and counted; what needs one
stays a Klärfall:

    leer           only the word „ISBN“ („ISBN keine vorh.“) or only a price: no 020, the rest of the text in 020 $c
    neun-ergaenzt  twelve digits starting 783/784, and „9“ + digits is a valid ISBN-13: 020 $a with the 9
    issn           an ISSN (NNNN-NNN[NX]) in the ISBN field: 022 $a; with a wrong check digit 022 $y and Klärfall
                   „ISSN vertippt“
    pruefziffer    right length, wrong check digit: Klärfall „ISBN vertippt“, kept in 020 $z (invalid ISBN)
    unvollstaendig too few or too many digits: Klärfall „ISBN unvollständig“, kept in 020 $z
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_WAEHRUNG = r"(?:DM|EUR|€|sFr\.?|SFr\.?|Fr\.|öS)"
_BETRAG = r"\d+(?:[.,]\d{1,2}|[.,]-+)?"
PREIS = re.compile(rf"(?<![\w-]){_WAEHRUNG}\s*{_BETRAG}|{_BETRAG}\s*{_WAEHRUNG}(?!\w)")
ISSN = re.compile(r"(?<![\dXx-])(\d{4})-(\d{3}[\dXx])(?![\dXx-])")
WORT = re.compile(r"^\s*IS[BS]N\s*:?\s*", re.I)


@dataclass
class Urteil:
    art: str            # ok | leer | neun-ergaenzt | issn | issn-falsch | pruefziffer | unvollstaendig
    wert: str = ""      # the ISBN or ISSN to write; for leer the leftover text (price, binding) or ""


def ziffern(feld: str) -> str:
    """First group of digits, X and hyphens with at least nine digits; otherwise all digits of the field."""
    for teil in re.split(r"[^0-9Xx-]+", feld):
        c = teil.replace("-", "").upper()
        if len(c.replace("X", "")) >= 9:
            return c
    return re.sub(r"[^0-9]", "", feld)


def isbn13_ok(d: str) -> bool:
    return bool(re.fullmatch(r"\d{13}", d)) and sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(d)) % 10 == 0


def isbn10_ok(d: str) -> bool:
    if not re.fullmatch(r"\d{9}[\dX]", d):
        return False
    return sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(d)) % 11 == 0


def issn_ok(d: str) -> bool:
    if not re.fullmatch(r"\d{7}[\dX]", d):
        return False
    p = (11 - sum((8 - i) * int(c) for i, c in enumerate(d[:7])) % 11) % 11
    return ("X" if p == 10 else str(p)) == d[7]


def beurteilen(feld: str) -> Urteil:
    ohne_preis = PREIS.sub(" ", feld)
    d = ziffern(ohne_preis)
    m = ISSN.search(ohne_preis)
    if m and len(d) < 10:
        issn = f"{m[1]}-{m[2].upper()}"
        return Urteil("issn" if issn_ok(issn.replace("-", "")) else "issn-falsch", issn)
    if not d:
        rest = WORT.sub("", feld).strip()
        return Urteil("leer", "" if re.match(r"(?i)^(keine|ohne|o\.)", rest) else rest)
    if len(d) == 13:
        return Urteil("ok" if isbn13_ok(d) else "pruefziffer", d)
    if len(d) == 10:
        return Urteil("ok" if isbn10_ok(d) else "pruefziffer", d)
    if re.fullmatch(r"78[34]\d{9}", d):
        return Urteil("neun-ergaenzt", "9" + d) if isbn13_ok("9" + d) else Urteil("pruefziffer", d)
    return Urteil("unvollstaendig", d)
