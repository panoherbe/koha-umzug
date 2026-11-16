"""Read and write an Alephino export: records in Aleph sequential format plus CSV files.

Aleph sequential is the line format Alephino and Aleph use for exports and loads::

    000000001 FMT   L BK
    000000001 001   L 000000001
    000000001 33100 L $$a¬Die¬ Baukunst der Gotik
    000000001 10000 L $$pMüller, Anna$$9P000017$$4aut

Columns: system number (9 digits), field tag (3) plus two indicators, „L“, then the content. Subfields start with
„$$“ and a one-character code. Fields without „$$“ are control fields.

An export folder holds:

    titel.seq            title records (MAB2 field numbers)
    personen.seq         person authority records        (Stammsätze)
    koerperschaften.seq  corporate body authority records
    schlagwoerter.seq    subject authority records
    exemplare.csv        items:    exemplar_id;titel_id;barcode;signatur;standort;medientyp;status;zugang
    benutzer.csv         patrons:  benutzer_id;ausweis;nachname;vorname;email;gruppe;gueltig_bis
    ausleihen.csv        loans:    exemplar_id;benutzer_id;ausleihe;faellig;verlaengerungen
    ausleihhistorie.csv  history:  exemplar_id;benutzer_id;ausleihe;rueckgabe
    pdf.csv              files:    titel_id;datei;zugriff   (zugriff = oeffentlich | intern)
    pdf/                 the PDF files themselves

CSV files use „;“ and UTF-8, as Alephino's report exports do. Dates are YYYYMMDD; „00000000“ means unknown.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

DATEIEN_NORM = {"person": "personen.seq", "koerperschaft": "koerperschaften.seq", "schlagwort": "schlagwoerter.seq"}
CSV_SPALTEN = {
    "exemplare.csv": ["exemplar_id", "titel_id", "barcode", "signatur", "standort", "medientyp", "status", "zugang"],
    "benutzer.csv": ["benutzer_id", "ausweis", "nachname", "vorname", "email", "gruppe", "gueltig_bis"],
    "ausleihen.csv": ["exemplar_id", "benutzer_id", "ausleihe", "faellig", "verlaengerungen"],
    "ausleihhistorie.csv": ["exemplar_id", "benutzer_id", "ausleihe", "rueckgabe"],
    "pdf.csv": ["titel_id", "datei", "zugriff"],
}


@dataclass
class Feld:
    tag: str                                   # 3 characters
    ind: str = "  "                            # 2 characters
    daten: str = ""                            # control field content, if no subfields
    unter: list[tuple[str, str]] = field(default_factory=list)

    def get(self, code: str) -> str | None:
        return next((v for c, v in self.unter if c == code), None)

    def alle(self, code: str) -> list[str]:
        return [v for c, v in self.unter if c == code]


@dataclass
class Satz:
    sysno: str
    felder: list[Feld] = field(default_factory=list)

    def feld(self, tag: str) -> Feld | None:
        return next((f for f in self.felder if f.tag == tag), None)

    def felder_von(self, *tags: str) -> list[Feld]:
        return [f for f in self.felder if f.tag in tags]

    def wert(self, tag: str, code: str | None = None) -> str | None:
        f = self.feld(tag)
        if f is None:
            return None
        return f.daten if code is None else f.get(code)


def _parse_zeile(zeile: str) -> tuple[str, Feld]:
    if len(zeile) < 18 or zeile[9] != " " or zeile[15:18] != " L ":
        raise ValueError(f"keine Aleph-Sequential-Zeile: {zeile[:40]!r}")
    sysno, tag, ind, inhalt = zeile[:9], zeile[10:13], zeile[13:15], zeile[18:]
    f = Feld(tag=tag, ind=ind)
    if inhalt.startswith("$$"):
        for teil in inhalt.split("$$")[1:]:
            if teil:
                f.unter.append((teil[0], teil[1:]))
    else:
        f.daten = inhalt
    return sysno, f


def lesen_seq(pfad: Path) -> Iterator[Satz]:
    """Records of a sequential file, in file order. Lines of one record are consecutive."""
    aktuell: Satz | None = None
    with open(pfad, encoding="utf-8") as fh:
        for nr, zeile in enumerate(fh, 1):
            zeile = zeile.rstrip("\n")
            if not zeile.strip():
                continue
            try:
                sysno, f = _parse_zeile(zeile)
            except ValueError as e:
                raise ValueError(f"{pfad.name}, Zeile {nr}: {e}") from None
            if aktuell is None or sysno != aktuell.sysno:
                if aktuell is not None:
                    yield aktuell
                aktuell = Satz(sysno)
            aktuell.felder.append(f)
    if aktuell is not None:
        yield aktuell


def zeile(sysno: str, f: Feld) -> str:
    inhalt = "".join(f"$${c}{v}" for c, v in f.unter) if f.unter else f.daten
    return f"{sysno} {f.tag}{f.ind} L {inhalt}"


def schreiben_seq(pfad: Path, saetze: Iterable[Satz]) -> int:
    n = 0
    with open(pfad, "w", encoding="utf-8", newline="\n") as fh:
        for s in saetze:
            for f in s.felder:
                fh.write(zeile(s.sysno, f) + "\n")
            n += 1
    return n


def lesen_csv(pfad: Path) -> list[dict[str, str]]:
    with open(pfad, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def schreiben_csv(pfad: Path, zeilen: Iterable[dict[str, str]]) -> int:
    spalten = CSV_SPALTEN[pfad.name]
    n = 0
    with open(pfad, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=spalten, delimiter=";", lineterminator="\n")
        w.writeheader()
        for z in zeilen:
            w.writerow({k: z.get(k, "") for k in spalten})
            n += 1
    return n


@dataclass
class Export:
    """Everything in one export folder, read once."""
    ordner: Path
    titel: list[Satz]
    normen: dict[str, list[Satz]]               # art -> records
    exemplare: list[dict[str, str]]
    benutzer: list[dict[str, str]]
    ausleihen: list[dict[str, str]]
    historie: list[dict[str, str]]
    pdf: list[dict[str, str]]

    @classmethod
    def lesen(cls, ordner: Path) -> "Export":
        ordner = Path(ordner)
        return cls(
            ordner=ordner,
            titel=list(lesen_seq(ordner / "titel.seq")),
            normen={art: list(lesen_seq(ordner / datei)) for art, datei in DATEIEN_NORM.items()},
            exemplare=lesen_csv(ordner / "exemplare.csv"),
            benutzer=lesen_csv(ordner / "benutzer.csv"),
            ausleihen=lesen_csv(ordner / "ausleihen.csv"),
            historie=lesen_csv(ordner / "ausleihhistorie.csv"),
            pdf=lesen_csv(ordner / "pdf.csv"),
        )

    def mengen(self) -> dict[str, int]:
        return {
            "titel": len(self.titel),
            "exemplare": len(self.exemplare),
            "personen": len(self.normen["person"]),
            "koerperschaften": len(self.normen["koerperschaft"]),
            "schlagwoerter": len(self.normen["schlagwort"]),
            "benutzer": len(self.benutzer),
            "ausleihen": len(self.ausleihen),
            "ausleihhistorie": len(self.historie),
            "pdf": len(self.pdf),
        }


def datum(wert: str | None) -> str | None:
    """YYYYMMDD -> YYYY-MM-DD; empty or 00000000 -> None."""
    if not wert or wert.strip("0") == "" or len(wert) != 8 or not wert.isdigit():
        return None
    return f"{wert[:4]}-{wert[4:6]}-{wert[6:]}"
