"""Convert an Alephino export into Koha import files.

    python -m umzug umwandeln <export> <ziel> --freigaben freigaben.json --opac-url URL --dienst-url URL

Writes into <ziel>:

    normdaten.mrc     MARC21 authority records (UTF-8, NFC)
    titel.mrc         MARC21 bibliographic records with embedded items (952); links as $0 „(ALEPHINO-…)nnn“
    benutzer.csv      patrons for Koha's import_patrons.pl
    ausleihen.json    current loans (barcode, card number, dates) for laden.py
    historie.json     loan history
    pdf.json          PDF files with checksum, Koha upload key and access right
    klaerfaelle.csv   every data quality finding with the action taken
    protokoll.json    counts in, counts out, what was left out and why, NFC corrections

Every data finding becomes a line in klaerfaelle.csv (a Klärfall). A finding counts as decided only if the release
file (--freigaben, e.g. beispiel/freigaben.json) has a rule for its kind; then the rule's text is written next to it.
Findings without a rule stop the conversion with exit code 2: the files are still written, so they can be read, and
`laden` refuses them. What each kind does to the data:

    Barcode doppelt                  the second item gets the suffix -2 (with a rule naming „Suffix“), else left out
    Exemplar ohne Titel              item left out (counted in protokoll.json „weggelassen“)
    Ausleihe ohne Benutzer           loan left out (counted)
    Ausleihe ohne Exemplar           loan left out
    Zugangsdatum unbekannt           item kept, without 952 $d
    Wert ohne Zuordnung              item or patron kept; the value outside the tables in werte.py is not set
                                     (no location, item type BK, loanable, patron category EX)
    Feld / Unterfeld ohne Zuordnung  content kept as a note (titles 500, authorities 667), see mab2marc.py
    Normsatzfeld ohne Zuordnung      content kept as a note 667 in the authority record
    Normdatenverknüpfung ins Leere   name kept as text, without link
    Übergeordneter Titel fehlt       record kept, without 773
    Hauptsachtitel fehlt             record kept with „[ohne Titel]“ (a volume whose work is in the export takes the
                                     work's title instead, no Klärfall)
    ISBN vertippt / unvollständig    record kept, the number in 020 $z (invalid ISBN)

Done without a decision and counted in protokoll.json „automatisch“ (umzug/isbn.py): an ISBN field with only the word
„ISBN“, a missing leading 9 of 978, an ISSN in the ISBN field (to 022), a volume titled with its work.
    PDF-Datei fehlt                  title kept, without 856
    Normsatz ohne Ansetzung          authority record left out
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from pymarc import Field, MARCWriter, Subfield

from .alephino import Export, datum
from .mab2marc import Klaerfall, Umsetzer, exemplar_952, nichtsortier
from .mab2marc import nfc as nfc_text
from .werte import GRUPPEN, STANDORTE, STATUS, TYPEN, ZWEIG

DATEN = ("normdaten.mrc", "titel.mrc", "benutzer.csv", "ausleihen.json", "historie.json", "pdf.json",
         "klaerfaelle.csv", "protokoll.json")


def upload_hash(titel_id: str, sha256: str) -> str:
    """The key Koha stores for an uploaded file (40 hex characters), stable across runs."""
    return hashlib.sha1(f"alephino-pdf:{titel_id}:{sha256}".encode()).hexdigest()


def upload_id(nr: int) -> int:
    return 1000 + nr


class Freigaben:
    def __init__(self, regeln: dict[str, str]):
        self.regeln = regeln
        self.offen: list[Klaerfall] = []

    @classmethod
    def lesen(cls, pfad: Path | None) -> "Freigaben":
        if pfad is None:
            return cls({})
        return cls(json.loads(Path(pfad).read_text(encoding="utf-8")).get("regeln", {}))

    def pruefen(self, k: Klaerfall) -> Klaerfall:
        if k.art in self.regeln:
            k.aktion = f"freigegeben: {self.regeln[k.art]}"
        else:
            self.offen.append(k)
        return k


def umwandeln(export: Path, ziel: Path, freigaben: Path | None, opac_url: str, dienst_url: str) -> dict:
    ex = Export.lesen(export)
    fg = Freigaben.lesen(freigaben)
    ziel.mkdir(parents=True, exist_ok=True)
    for name in DATEN:
        (ziel / name).unlink(missing_ok=True)
    klaer: list[Klaerfall] = []
    weg: Counter[str] = Counter()
    nfc = 0
    auto: Counter[str] = Counter()

    norm_ids = {art: {s.sysno for s in saetze} for art, saetze in ex.normen.items()}
    titel_ids = {s.sysno for s in ex.titel}
    namen = {s.sysno: nichtsortier(nfc_text(s.wert("331", "a") or "")[0])[0] for s in ex.titel}
    u = Umsetzer(norm_ids, namen)

    # authorities
    n_norm = Counter()
    with open(ziel / "normdaten.mrc", "wb") as fh:
        w = MARCWriter(fh)
        for art, saetze in ex.normen.items():
            for s in saetze:
                erg = u.norm(art, s)
                nfc += erg.nfc_korrigiert
                klaer += [fg.pruefen(k) for k in erg.klaerfaelle]
                if erg.record.get_fields("100", "110", "150", "151"):
                    w.write(erg.record)
                    n_norm[art] += 1
                else:
                    weg[f"{art}: ohne Ansetzung"] += 1

    # items: duplicates and orphans need a release rule
    nach_titel: dict[str, list[dict]] = {}
    gesehen: dict[str, str] = {}
    barcodes: dict[str, str] = {}                         # exemplar_id -> barcode in Koha
    for e in ex.exemplare:
        if e["titel_id"] not in titel_ids:
            k = fg.pruefen(Klaerfall("Exemplar ohne Titel", f"Exemplar {e['exemplar_id']}",
                                     f"Titel {e['titel_id']} fehlt im Export"))
            klaer.append(k)
            if "weglassen" in k.aktion:
                weg["exemplare: ohne Titel (freigegeben)"] += 1
            continue
        bc = e["barcode"]
        if bc in gesehen:
            k = fg.pruefen(Klaerfall("Barcode doppelt", f"Exemplar {e['exemplar_id']}",
                                     f"Barcode {bc} schon bei Exemplar {gesehen[bc]}"))
            klaer.append(k)
            if "Suffix" in k.aktion:
                n = 2
                while f"{bc}-{n}" in gesehen:
                    n += 1
                e = dict(e, barcode=f"{bc}-{n}")
            else:
                continue
        if datum(e.get("zugang")) is None:
            klaer.append(fg.pruefen(Klaerfall("Zugangsdatum unbekannt", f"Exemplar {e['exemplar_id']}",
                                              f"Wert „{e.get('zugang')}“", "übernommen ohne Zugangsdatum")))
        for spalte, tabelle, ersatz in (("standort", STANDORTE, "ohne Standort"), ("medientyp", TYPEN, "als BK"),
                                        ("status", STATUS, "als ausleihbar")):
            if e.get(spalte) not in tabelle:
                klaer.append(fg.pruefen(Klaerfall("Wert ohne Zuordnung", f"Exemplar {e['exemplar_id']}",
                                                  f"{spalte} „{e.get(spalte)}“", f"übernommen {ersatz}")))
        gesehen[e["barcode"]] = e["exemplar_id"]
        barcodes[e["exemplar_id"]] = e["barcode"]
        nach_titel.setdefault(e["titel_id"], []).append(e)

    # PDFs
    pdf_zeilen = []
    pdf_von: dict[str, dict] = {}
    for i, p in enumerate(ex.pdf, 1):
        datei = ex.ordner / "pdf" / p["datei"]
        if not datei.exists():
            klaer.append(fg.pruefen(Klaerfall("PDF-Datei fehlt", f"Titel {p['titel_id']}", p["datei"])))
            continue
        sha = hashlib.sha256(datei.read_bytes()).hexdigest()
        h = upload_hash(p["titel_id"], sha)
        oeffentlich = p["zugriff"] == "oeffentlich"
        zeile = {"titel_id": p["titel_id"], "datei": p["datei"], "sha256": sha, "groesse": datei.stat().st_size,
                 "hash": h, "upload_id": upload_id(i), "oeffentlich": oeffentlich,
                 "url": (f"{opac_url}/cgi-bin/koha/opac-retrieve-file.pl?id={h}" if oeffentlich
                         else f"{dienst_url}/cgi-bin/koha/tools/upload.pl?op=download&id={upload_id(i)}")}
        pdf_zeilen.append(zeile)
        pdf_von[p["titel_id"]] = zeile

    # titles
    n_titel = n_ex = 0
    with open(ziel / "titel.mrc", "wb") as fh:
        w = MARCWriter(fh)
        for s in ex.titel:
            erg = u.titel(s)
            nfc += erg.nfc_korrigiert
            auto += erg.automatisch
            klaer += [fg.pruefen(k) for k in erg.klaerfaelle]
            rec = erg.record
            exemplare = nach_titel.get(s.sysno, [])
            typ = TYPEN.get(exemplare[0]["medientyp"], "BK") if exemplare else ("ZS" if s.feld("010") else "BK")
            rec.add_field(Field(tag="942", indicators=[" ", " "], subfields=[Subfield("c", typ)]))
            if (p := pdf_von.get(s.sysno)):
                sub = [Subfield("u", p["url"]), Subfield("y", "Volltext (PDF)"), Subfield("q", "application/pdf")]
                if not p["oeffentlich"]:
                    sub.append(Subfield("z", "nur in der Dienstoberfläche"))
                rec.add_field(Field(tag="856", indicators=["4", "2"], subfields=sub))
            for e in exemplare:
                rec.add_field(exemplar_952(e, ZWEIG, TYPEN, STANDORTE))
                n_ex += 1
            w.write(rec)
            n_titel += 1

    # patrons
    karten = {}
    with open(ziel / "benutzer.csv", "w", encoding="utf-8", newline="") as fh:
        spalten = ["cardnumber", "surname", "firstname", "email", "branchcode", "categorycode", "dateexpiry", "sort1"]
        wr = csv.DictWriter(fh, fieldnames=spalten, lineterminator="\n")
        wr.writeheader()
        for b in ex.benutzer:
            karten[b["benutzer_id"]] = b["ausweis"]
            if b.get("gruppe") not in GRUPPEN:
                klaer.append(fg.pruefen(Klaerfall("Wert ohne Zuordnung", f"Benutzer {b['benutzer_id']}",
                                                  f"gruppe „{b.get('gruppe')}“", "übernommen als EX")))
            wr.writerow({"cardnumber": b["ausweis"], "surname": b["nachname"], "firstname": b["vorname"],
                         "email": b["email"], "branchcode": ZWEIG, "categorycode": GRUPPEN.get(b["gruppe"], "EX"),
                         "dateexpiry": datum(b["gueltig_bis"]) or "", "sort1": f"(ALEPHINO){b['benutzer_id']}"})

    def ausleihe(a: dict, historie: bool) -> dict | None:
        if a["benutzer_id"] not in karten:
            k = fg.pruefen(Klaerfall("Ausleihe ohne Benutzer", f"Exemplar {a['exemplar_id']}",
                                     f"Benutzer {a['benutzer_id']} fehlt im Export"))
            klaer.append(k)
            weg[f"{'historie' if historie else 'ausleihen'}: ohne Benutzer (freigegeben)"] += "weglassen" in k.aktion
            return None
        if a["exemplar_id"] not in barcodes:
            klaer.append(fg.pruefen(Klaerfall("Ausleihe ohne Exemplar", f"Exemplar {a['exemplar_id']}",
                                              "Exemplar nicht übernommen")))
            return None
        z = {"barcode": barcodes[a["exemplar_id"]], "cardnumber": karten[a["benutzer_id"]],
             "ausleihe": datum(a["ausleihe"])}
        if historie:
            z["rueckgabe"] = datum(a["rueckgabe"])
        else:
            z["faellig"] = datum(a["faellig"])
            z["verlaengerungen"] = int(a.get("verlaengerungen") or 0)
        return z

    laufend = [z for a in ex.ausleihen if (z := ausleihe(a, False))]
    hist = [z for a in ex.historie if (z := ausleihe(a, True))]
    (ziel / "ausleihen.json").write_text(json.dumps(laufend, ensure_ascii=False, indent=0) + "\n")
    (ziel / "historie.json").write_text(json.dumps(hist, ensure_ascii=False, indent=0) + "\n")
    (ziel / "pdf.json").write_text(json.dumps(pdf_zeilen, ensure_ascii=False, indent=1) + "\n")

    with open(ziel / "klaerfaelle.csv", "w", encoding="utf-8", newline="") as fh:
        wr = csv.writer(fh, delimiter=";", lineterminator="\n")
        wr.writerow(["art", "objekt", "hinweis", "aktion"])
        for k in klaer:
            wr.writerow([k.art, k.objekt, k.hinweis, k.aktion])

    protokoll = {
        "quelle": ex.mengen(),
        "ziel": {"titel": n_titel, "exemplare": n_ex, "personen": n_norm["person"],
                 "koerperschaften": n_norm["koerperschaft"], "schlagwoerter": n_norm["schlagwort"],
                 "benutzer": len(karten), "ausleihen": len(laufend), "ausleihhistorie": len(hist),
                 "pdf": len(pdf_zeilen)},
        "weggelassen": dict(sorted(weg.items())),
        "klaerfaelle": dict(sorted(Counter(k.art for k in klaer).items())),
        "offen": [vars(k) for k in fg.offen],
        "nfc_korrigiert": nfc,
        "automatisch": dict(sorted(auto.items())),
    }
    (ziel / "protokoll.json").write_text(json.dumps(protokoll, ensure_ascii=False, indent=1) + "\n")
    return protokoll
