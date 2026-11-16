"""MAB2 (Alephino) to MARC21 (Koha), UTF-8, normalised to NFC.

Every rule is a line in REGELN_TITEL / REGELN_NORM. The readable field mapping for the library
(zuordnung/FELDZUORDNUNG.md) is generated from these lines, so documentation and code cannot drift apart.

What the conversion does beyond copying fields:

- original identifiers stay: title 001 = Alephino system number (Koha links 773 $w to it), 035 = „(ALEPHINO)nnn“;
  authorities and items carry their Alephino number in 035 / 952 $x
- MAB2 non-sorting markers „¬Die¬ Kunst“ become MARC 245 second indicator 4 and „Die Kunst“; markers anywhere
  else („Loga, Sven ¬von¬“) and the control characters NSB/NSE (U+0098/U+009C) are removed, Koha would show them as
  boxes
- decomposed characters (e.g. „u“ + combining diaeresis) are normalised to NFC, so search finds „Müller“
- authority links: MAB $$9 (Alephino authority number) becomes MARC $0 „(ALEPHINO-PER)nnn“; the loader adds the
  Koha $9 once the authorities are in Koha (laden.py), so the link is exact and never guessed from the name
- hierarchy: MAB 010 (superior record) becomes 773 0_ $w with the superior's system number, MAB 089 the volume
- ISBD punctuation: MAB2 keeps title, other title information and statement of responsibility in separate fields
  without punctuation, Koha shows MARC subfields as they are. The converter writes the punctuation into the record
  („Titel : Zusatz / Verantwortlich“, „Ort : Verlag, Jahr“, „Reihe ; Band“), so leader/18 = „i“ is true
- roles: the relator code ($4, e.g. „edt“) gets the German relator term in $e („Herausgeber“), which Koha shows
- everything the rules do not read is listed, never dropped silently: an unknown field, a subfield without a rule,
  a second occurrence where the rules read only the first. Each becomes a Klaerfall and its content a note (titles
  500 „[MAB 078] …“, authorities 667), so nothing of the export is lost before the library has decided
"""
from __future__ import annotations

import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from pymarc import Field, Leader, Record, Subfield

from .alephino import Feld, Satz, datum

QUELLE = "ALEPHINO"
PRAEFIX_NORM = {"person": "ALEPHINO-PER", "koerperschaft": "ALEPHINO-KOE", "schlagwort": "ALEPHINO-SW"}
NICHTSORT = "¬"


@dataclass
class Klaerfall:
    """A data quality finding: listed for the library, never silently fixed."""
    art: str
    objekt: str
    hinweis: str
    aktion: str = "zur Freigabe"


@dataclass
class Ergebnis:
    record: Record
    klaerfaelle: list[Klaerfall] = field(default_factory=list)
    nfc_korrigiert: int = 0


def nfc(text: str) -> tuple[str, bool]:
    n = unicodedata.normalize("NFC", text)
    return n, n != text


def nichtsortier(text: str) -> tuple[str, int]:
    """„¬Die¬ Kunst“ -> („Die Kunst“, 4). Only a leading marker counts for the indicator; NSB/NSE count as „¬“."""
    text = text.replace("\x98", NICHTSORT).replace("\x9c", NICHTSORT)
    if text.startswith(NICHTSORT) and text.count(NICHTSORT) >= 2:
        ende = text.index(NICHTSORT, 1)
        artikel = text[1:ende]
        rest = text[ende + 1:]
        ohne = (artikel + rest).replace(NICHTSORT, "")
        anzahl = len(artikel) + (1 if rest.startswith(" ") else 0)
        return ohne, min(anzahl, 9)
    return text.replace(NICHTSORT, ""), 0


# --- rules -------------------------------------------------------------------------------------------------------
# (MAB field, MAB subfield, MARC field, ind, MARC subfield, meaning). Used for documentation and for the simple fields.
EINFACH = [
    ("335", "a", "245", None, "b", "Zusätze zum Hauptsachtitel"),
    ("359", "a", "245", None, "c", "Verantwortlichkeitsangabe"),
    ("403", "a", "250", "  ", "a", "Ausgabebezeichnung"),
    ("410", "a", "264", " 1", "a", "Verlagsort"),
    ("412", "a", "264", " 1", "b", "Verlag"),
    ("425", "a", "264", " 1", "c", "Erscheinungsjahr"),
    ("433", "a", "300", "  ", "a", "Umfang"),
    ("451", "a", "490", "0 ", "a", "Gesamttitel"),
    ("455", "a", "490", "0 ", "v", "Bandangabe zum Gesamttitel"),
    ("540", "a", "020", "  ", "a", "ISBN"),
    ("542", "a", "022", "  ", "a", "ISSN"),
    ("655", "u", "856", "40", "u", "Elektronische Adresse (Web)"),
]
BESONDERS = [
    ("001", "", "001 / 035", "Alephino-Systemnummer: 001 unverändert, 035 „(ALEPHINO)nnn“"),
    ("002", "a", "008/00-05", "Datum der Ersterfassung"),
    ("010", "a", "773 0_ $t $w", "übergeordneter Datensatz: Titel und Systemnummer; Koha verlinkt über 001"),
    ("089", "a", "245 $n, 773 $g", "Bandangabe des untergeordneten Titels"),
    ("025", "a", "016 7_ $a $2 DE-101", "Nummer der Deutschen Nationalbibliothek, falls vorhanden"),
    ("037", "b", "041 $a, 008/35-37", "Sprache"),
    ("100, 104 … 196", "p, 9, 4", "100 1_ / 700 1_ ($a, $e, $0, $4)",
     "Personen; erste Verfasserin oder erster Verfasser in 100; $e = Rolle auf Deutsch (Tabelle unten)"),
    ("200, 204 … 296", "k, 9, 4", "110 2_ / 710 2_ ($a, $e, $0, $4)", "Körperschaften; $e wie bei Personen"),
    ("331", "a", "245 $a, 2. Indikator",
     "Hauptsachtitel; „¬…¬“ am Anfang wird zur Zahl der Nichtsortierzeichen, an anderer Stelle (auch in Namen) entfernt"),
    ("902", "s / g / p / k, 9", "650 / 651 / 600 / 610 _7 $2 gnd", "Schlagwörter (Sach, Geografikum, Person, Körperschaft)"),
    ("PDF", "pdf.csv", "856 42 $u $y $q", "titelverknüpfte PDF-Datei, über Koha-Upload mit Zugriffsrecht"),
    ("Exemplar", "exemplare.csv", "952", "Exemplar: Barcode $p, Signatur $o, Standort $c, Typ $y, Status $7, Zugang $d"),
]

# relator codes (MARC relator list) -> German relator term (Beziehungskennzeichnung) for $e; unknown codes keep only $4
ROLLEN = {"aut": "Verfasser", "edt": "Herausgeber", "isb": "Herausgebendes Organ", "ctb": "Mitwirkender",
          "pbl": "Verlag", "trl": "Übersetzer", "ill": "Illustrator", "pht": "Fotograf", "ctg": "Kartograf",
          "aui": "Verfasser einer Einleitung", "wpr": "Verfasser eines Vorworts", "com": "Zusammenstellender",
          "cre": "Geistiger Schöpfer", "art": "Künstler", "dsr": "Designer", "rev": "Rezensent",
          "hnr": "Gefeierte Person", "dgs": "Akademischer Betreuer", "dgg": "Grad-verleihende Institution",
          "oth": "Sonstige"}

# ISBD: the separator that ends a subfield, by the code of the subfield that follows (MARC21 practice)
ISBD = {"245": {"b": " :", "n": ".", "p": ".", "c": " /"}, "264": {"a": " ;", "b": " :", "c": ","},
        "490": {"v": " ;"}}


def isbd(f: Field) -> Field:
    """Write the ISBD separators into a data field: „Titel“ $b „Zusatz“ -> „Titel :“ $b „Zusatz“.

    A parallel title in $b that starts with „= “ moves its „=“ to the end of the subfield before. Nothing is added
    where the text already ends with that sign (or with „.“, „?“, „!“ before a period)."""
    regeln = ISBD.get(f.tag, {})
    unter = list(f.subfields)
    for i in range(len(unter) - 1):
        nach = unter[i + 1]
        zeichen = regeln.get(nach.code)
        if f.tag == "245" and nach.code == "b" and nach.value.startswith("="):
            zeichen = " ="
            unter[i + 1] = Subfield("b", nach.value[1:].lstrip())
        if not zeichen:
            continue
        wert = unter[i].value.rstrip()
        if wert.endswith(zeichen.strip()) or (zeichen == "." and wert[-1:] in ".?!"):
            continue
        unter[i] = Subfield(unter[i].code, wert + zeichen)
    f.subfields = unter
    return f


def rolle_e(code: str) -> list[Subfield]:
    return [Subfield("e", ROLLEN[code])] if code in ROLLEN else []


PERSONEN = [f"{n:03d}" for n in range(100, 200, 4)]
KOERPERSCHAFTEN = [f"{n:03d}" for n in range(200, 300, 4)]
SW_TAG = {"s": ("650", "s"), "g": ("651", "g"), "p": ("600", "p"), "k": ("610", "k")}
NORMART_VON_CODE = {"s": "schlagwort", "g": "schlagwort", "p": "person", "k": "koerperschaft"}

# What the title rules read, per MAB field: the subfield codes and whether every occurrence of the field is read
# (False: only the first, s.wert). Of each code only the first occurrence in a field is read (Feld.get).
KONTROLLFELDER = {"001", "FMT", "LDR"}
LESEN_TITEL: dict[str, tuple[str, bool]] = {
    **{mab: (code, True) for mab, code, *_ in EINFACH},
    **{t: ("p94", True) for t in PERSONEN}, **{t: ("k94", True) for t in KOERPERSCHAFTEN},
    "002": ("a", False), "010": ("a", False), "025": ("a", False), "037": ("b", False), "089": ("a", False),
    "331": ("a", False), "335": ("a", False), "359": ("a", False), "902": ("sgpk9", True),
}


def ungenutzt(f: Feld, codes: str, einer_von: str = "") -> list[tuple[str, str]]:
    """The non-empty subfields of f that the rules do not read: codes outside `codes` and repeated codes.
    `einer_von`: of these codes only the first one present is read (902: the name in s, g, p or k); without one of
    them the rules skip the field, so nothing of it is read."""
    erster = next((c for c in einer_von if f.get(c)), None)
    if einer_von and erster is None:
        return [(c, v) for c, v in f.unter if v.strip()]
    gelesen, rest = set(), []
    for c, v in f.unter:
        if c in codes and c not in gelesen and (c not in einer_von or c == erster):
            gelesen.add(c)
        elif v.strip():
            rest.append((c, v))
    return rest


class Umsetzer:
    """Converts title and authority records. Knows the authority numbers that exist, to find broken links."""

    def __init__(self, norm_ids: dict[str, set[str]], titel_ids: set[str] | dict[str, str], heute: str = "261116"):
        self.norm_ids = norm_ids
        self.titel_ids = set(titel_ids)
        # title of each record (for 773 $t, so the OPAC shows „In: <superior title>“); empty if only ids are known
        self.titel_namen = dict(titel_ids) if isinstance(titel_ids, dict) else {}
        self.heute = heute

    def _t(self, text: str, erg: Ergebnis, roh: bool = False) -> str:
        """NFC; without roh also without non-sorting markers (only the title start keeps them for nichtsortier)."""
        n, geaendert = nfc(text)
        if geaendert:
            erg.nfc_korrigiert += 1
        return n if roh else n.replace(NICHTSORT, "").replace("\x98", "").replace("\x9c", "")

    def _rest(self, s: Satz, lesen: dict[str, tuple[str, bool]], erg: Ergebnis, objekt: str, notiz: str,
              feld_art: str) -> None:
        """Everything of s the rules do not read: one Klärfall per field, the content kept as note `notiz`."""
        wo = "Fußnote" if notiz == "500" else "Anmerkung"

        def notieren(kennung: str, inhalt: str) -> None:
            erg.record.add_field(Field(tag=notiz, indicators=[" ", " "],
                                       subfields=[Subfield("a", f"[MAB {kennung}] {self._t(inhalt, erg)}")]))

        anzahl: Counter[str] = Counter()
        for f in s.felder:
            if f.tag in KONTROLLFELDER:
                continue
            anzahl[f.tag] += 1
            regel = lesen.get(f.tag)
            if regel is None or (not regel[1] and anzahl[f.tag] > 1):
                erg.klaerfaelle.append(Klaerfall(
                    feld_art, f"{objekt}, Feld {f.tag}",
                    ("Feld wiederholt, umgesetzt ist das erste; " if regel else "")
                    + f"Inhalt in {notiz} $a übernommen, Zuordnung festlegen", f"übernommen als {wo}"))
                notieren(f.tag, f.daten or " ".join(v for _c, v in f.unter))
                continue
            rest = ungenutzt(f, regel[0], "sgpk" if f.tag == "902" else "")
            if rest:
                erg.klaerfaelle.append(Klaerfall(
                    "Unterfeld ohne Zuordnung", f"{objekt}, Feld {f.tag} " + " ".join(f"${c}" for c, _v in rest),
                    f"Inhalt in {notiz} $a übernommen, Zuordnung festlegen", f"übernommen als {wo}"))
                for c, v in rest:
                    notieren(f"{f.tag} ${c}", v)

    def _link(self, art: str, nummer: str | None, tag: str, erg: Ergebnis, sysno: str, name: str) -> list[Subfield]:
        if not nummer:
            return []
        if nummer not in self.norm_ids[art]:
            erg.klaerfaelle.append(Klaerfall("Normdatenverknüpfung ins Leere", f"Titel {sysno}, Feld {tag}",
                                             f"{art} {nummer} „{name}“ fehlt im Export; Ansetzung bleibt als Text",
                                             "übernommen ohne Verknüpfung"))
            return []
        return [Subfield("0", f"({PRAEFIX_NORM[art]}){nummer}")]

    def titel(self, s: Satz) -> Ergebnis:
        rec = Record(force_utf8=True)
        rec.leader = Leader("00000nam a2200000 i 4500")
        erg = Ergebnis(rec)
        sysno = s.sysno
        rec.add_field(Field(tag="001", data=sysno))
        rec.add_field(Field(tag="003", data=QUELLE))
        erfasst = s.wert("002", "a") or ""
        sprache = (s.wert("037", "b") or "ger")[:3]
        jahr = (s.wert("425", "a") or "")[:4]
        d008 = (erfasst[2:8] if len(erfasst) == 8 else self.heute) + ("s" + jahr if jahr.isdigit() else "n    ")
        d008 = d008.ljust(15) + "xx " + " " * 17 + sprache + " d"
        rec.add_field(Field(tag="008", data=d008[:40].ljust(40)))
        if (dnb := s.wert("025", "a")):
            rec.add_field(Field(tag="016", indicators=["7", " "], subfields=[Subfield("a", dnb), Subfield("2", "DE-101")]))
        rec.add_field(Field(tag="035", indicators=[" ", " "], subfields=[Subfield("a", f"({QUELLE}){sysno}")]))
        rec.add_field(Field(tag="041", indicators=[" ", " "], subfields=[Subfield("a", sprache)]))

        # persons and corporate bodies: the first author goes to 100/110, everybody else to 700/710
        haupt = False
        for f in s.felder_von(*PERSONEN):
            name = self._t(f.get("p") or "", erg)
            rolle = f.get("4")
            sub = [Subfield("a", name)] + (rolle_e(rolle) if rolle else []) \
                + self._link("person", f.get("9"), f.tag, erg, sysno, name)
            if rolle:
                sub.append(Subfield("4", rolle))
            tag = "100" if (f.tag == "100" and not haupt) else "700"
            haupt = haupt or tag == "100"
            rec.add_field(Field(tag=tag, indicators=["1", " "], subfields=sub))
        for f in s.felder_von(*KOERPERSCHAFTEN):
            name = self._t(f.get("k") or "", erg)
            rolle = f.get("4")
            sub = [Subfield("a", name)] + (rolle_e(rolle) if rolle else []) \
                + self._link("koerperschaft", f.get("9"), f.tag, erg, sysno, name)
            if rolle:
                sub.append(Subfield("4", rolle))
            tag = "110" if (f.tag == "200" and not haupt) else "710"
            haupt = haupt or tag == "110"
            rec.add_field(Field(tag=tag, indicators=["2", " "], subfields=sub))

        titel = s.wert("331", "a")
        if not titel:
            erg.klaerfaelle.append(Klaerfall("Hauptsachtitel fehlt", f"Titel {sysno}", "kein Feld 331",
                                             "übernommen mit Titel „[ohne Titel]“"))
            titel = "[ohne Titel]"
        titel, nsz = nichtsortier(self._t(titel, erg, roh=True))
        sub245 = [Subfield("a", titel)]
        if (zusatz := s.wert("335", "a")):
            sub245.append(Subfield("b", nichtsortier(self._t(zusatz, erg, roh=True))[0]))
        if (band := s.wert("089", "a")):
            sub245.append(Subfield("n", self._t(band, erg)))
        if (verantw := s.wert("359", "a")):
            sub245.append(Subfield("c", self._t(verantw, erg)))
        rec.add_field(isbd(Field(tag="245", indicators=["1" if haupt else "0", str(nsz)], subfields=sub245)))

        for mab, code, marc, ind, mcode, _ in EINFACH:
            if mab in ("335", "359"):
                continue
            werte = [self._t(f.get(code) or "", erg) for f in s.felder_von(mab) if f.get(code)]
            for w in werte:
                if mab == "655":
                    rec.add_field(Field(tag="856", indicators=["4", "0"], subfields=[Subfield("u", w)]))
                    continue
                vorhanden = rec.get_fields(marc)
                if marc in ("264", "490") and vorhanden:
                    vorhanden[0].add_subfield(mcode, w)
                else:
                    rec.add_field(Field(tag=marc, indicators=list(ind), subfields=[Subfield(mcode, w)]))

        for f in rec.get_fields("264", "490"):
            isbd(f)

        if (oben := s.wert("010", "a")):
            if oben not in self.titel_ids:
                erg.klaerfaelle.append(Klaerfall("Übergeordneter Titel fehlt", f"Titel {sysno}",
                                                 f"Feld 010 zeigt auf {oben}, der nicht im Export ist",
                                                 "übernommen ohne Verknüpfung"))
            else:
                sub = [Subfield("t", self.titel_namen[oben])] if self.titel_namen.get(oben) else []
                sub.append(Subfield("w", oben))
                if band:
                    sub.append(Subfield("g", self._t(band, erg)))
                rec.add_field(Field(tag="773", indicators=["0", " "], subfields=sub))

        for f in s.felder_von("902"):
            code = next((c for c in ("s", "g", "p", "k") if f.get(c)), None)
            if code is None:
                continue
            tag, _ = SW_TAG[code]
            name = self._t(f.get(code) or "", erg)
            sub = [Subfield("a", name)] + self._link(NORMART_VON_CODE[code], f.get("9"), "902", erg, sysno, name)
            sub.append(Subfield("2", "gnd"))
            ind = ["1", "7"] if tag == "600" else ["2", "7"] if tag == "610" else [" ", "7"]
            rec.add_field(Field(tag=tag, indicators=ind, subfields=sub))

        self._rest(s, LESEN_TITEL, erg, f"Titel {sysno}", "500", "Feld ohne Zuordnung")
        return erg

    def norm(self, art: str, s: Satz) -> Ergebnis:
        rec = Record(force_utf8=True)
        rec.leader = Leader("00000nz  a2200000n  4500")
        erg = Ergebnis(rec)
        rec.add_field(Field(tag="008", data=f"{self.heute}n| azannaabn          |a aaa      ".ljust(40)[:40]))
        rec.add_field(Field(tag="035", indicators=[" ", " "], subfields=[Subfield("a", f"({PRAEFIX_NORM[art]}){s.sysno}")]))
        if (gnd := s.wert("024", "a")):
            rec.add_field(Field(tag="024", indicators=["7", " "], subfields=[Subfield("a", gnd), Subfield("2", "gnd")]))
        ans = s.feld("800")
        if ans is None:
            erg.klaerfaelle.append(Klaerfall("Normsatz ohne Ansetzung", f"{art} {s.sysno}", "kein Feld 800",
                                             "nicht übernommen, zur Freigabe"))
            return erg
        if art == "person":
            lesen800 = "pd"
            sub = [Subfield("a", self._t(ans.get("p") or "", erg))]
            if (d := ans.get("d")):
                sub.append(Subfield("d", self._t(d, erg)))
            rec.add_field(Field(tag="100", indicators=["1", " "], subfields=sub))
            vtag, vcode, vind = "400", "p", ["1", " "]
        elif art == "koerperschaft":
            lesen800 = "k"
            rec.add_field(Field(tag="110", indicators=["2", " "], subfields=[Subfield("a", self._t(ans.get("k") or "", erg))]))
            vtag, vcode, vind = "410", "k", ["2", " "]
        else:
            geo = ans.get("g") is not None
            lesen800 = "g" if geo else "s"
            rec.add_field(Field(tag="151" if geo else "150", indicators=[" ", " "],
                                subfields=[Subfield("a", self._t(ans.get("g") or ans.get("s") or "", erg))]))
            vtag, vcode, vind = ("451", "g", [" ", " "]) if geo else ("450", "s", [" ", " "])
        for f in s.felder_von("830"):
            if (v := f.get(vcode)):
                rec.add_field(Field(tag=vtag, indicators=vind, subfields=[Subfield("a", self._t(v, erg))]))
        lesen = {"024": ("a", False), "800": (lesen800, False), "830": (vcode, True)}
        self._rest(s, lesen, erg, f"{art} {s.sysno}", "667", "Normsatzfeld ohne Zuordnung")
        return erg


def exemplar_952(ex: dict[str, str], zweig: str, typen: dict[str, str], standorte: dict[str, str]) -> Field:
    """952 for Koha's default MARC21 framework. Status „praesenz“ -> not for loan (1)."""
    sub = [Subfield("a", zweig), Subfield("b", zweig)]
    if (ort := standorte.get(ex.get("standort", ""))):
        sub.append(Subfield("c", ort))
    if (zugang := datum(ex.get("zugang"))):
        sub.append(Subfield("d", zugang))
    if ex.get("signatur"):
        sub.append(Subfield("o", unicodedata.normalize("NFC", ex["signatur"])))
    sub.append(Subfield("p", ex["barcode"]))
    sub.append(Subfield("y", typen.get(ex.get("medientyp", ""), "BK")))
    if ex.get("status") == "praesenz":
        sub.append(Subfield("7", "1"))
    sub.append(Subfield("x", f"(ALEPHINO-EX){ex['exemplar_id']}"))
    return Field(tag="952", indicators=[" ", " "], subfields=sub)


def feldzuordnung_md() -> str:
    """The readable field mapping for the library, generated from the rules above."""
    zeilen = ["# Feldzuordnung Alephino (MAB2) → Koha (MARC21)", "",
              "Erzeugt aus `umzug/mab2marc.py` (`python -m umzug zuordnung`); Code und Tabelle können nicht "
              "auseinanderlaufen. Jede Zeile ist eine Regel des Konverters.", "",
              "## Titeldaten", "", "| MAB2 | Unterfeld | MARC21 | Bedeutung |", "|---|---|---|---|"]
    for mab, code, marc, bedeutung in BESONDERS:
        zeilen.append(f"| {mab} | {code} | {marc} | {bedeutung} |")
    for mab, code, marc, ind, mcode, bedeutung in EINFACH:
        zeilen.append(f"| {mab} | {code} | {marc} ${mcode} | {bedeutung} |")
    zeilen += ["", "Satzzeichen nach ISBD schreibt der Konverter in den Datensatz (Leader/18 = „i“), weil Koha die "
               "Unterfelder so anzeigt, wie sie sind: 245 „Titel : Zusatz / Verantwortlich“ („Titel = Paralleltitel“, "
               "„Titel. Band“), 264 „Ort : Verlag, Jahr“, 490 „Reihe ; Band“.", "",
               "### Rollen ($4 → $e)", "", "| $4 | $e |", "|---|---|"]
    zeilen += [f"| {code} | {wort} |" for code, wort in ROLLEN.items()]
    zeilen += ["", "Ein Code ohne Eintrag bleibt nur als $4 stehen.", "",
               "### Was keine Regel hat", "",
               "Ein Feld ohne Regel, ein Unterfeld ohne Regel und ein zweites Vorkommen, wo die Regel nur das erste "
               "liest, gehen nicht verloren: Der Inhalt kommt als Fußnote 500 „[MAB 078] …“ (Normsätze: Anmerkung "
               "667) in den Datensatz, und je Feld entsteht ein Klärfall („Feld ohne Zuordnung“, „Unterfeld ohne "
               "Zuordnung“, „Normsatzfeld ohne Zuordnung“). Ohne Regel in `freigaben.json` hält die Umwandlung an."]
    zeilen += ["", "## Normdaten", "", "| Alephino-Stammsatz | MAB-Feld | MARC21-Normsatz | Bedeutung |",
               "|---|---|---|---|",
               "| Person | 800 $p, $d | 100 1_ $a, $d | Ansetzung |",
               "| Person | 830 $p | 400 1_ $a | Verweisung |",
               "| Körperschaft | 800 $k | 110 2_ $a | Ansetzung |",
               "| Körperschaft | 830 $k | 410 2_ $a | Verweisung |",
               "| Schlagwort | 800 $s / $g | 150 / 151 $a | Sachschlagwort / Geografikum |",
               "| Schlagwort | 830 $s / $g | 450 / 451 $a | Verweisung |",
               "| alle | 001 | 035 „(ALEPHINO-PER\\|KOE\\|SW)nnn“ | Alephino-Nummer bleibt erhalten |",
               "| alle | 024 $a | 024 7_ $a $2 gnd | GND-Nummer |",
               "", "## Benutzer und Ausleihen", "",
               "| Alephino (CSV) | Koha | Bedeutung |", "|---|---|---|",
               "| benutzer_id | borrowers.sort1 | Alephino-Nummer bleibt erhalten |",
               "| ausweis | cardnumber | Ausweisnummer, Schlüssel für die Ausleihe |",
               "| nachname, vorname, email | surname, firstname, email | |",
               "| gruppe | categorycode | Benutzergruppe (Tabelle in `umzug/werte.py`) |",
               "| gueltig_bis | dateexpiry | |",
               "| ausleihen.csv | issues (issuedate, date_due, renewals_count), items.onloan | laufende Ausleihen |",
               "| ausleihhistorie.csv | old_issues (issuedate, returndate) | Historie, in der Dienstoberfläche sichtbar |",
               "", "Exemplarwerte (Standort, Medientyp, Status) und Benutzergruppen übersetzen die Tabellen in "
               "`umzug/werte.py`; ein Wert, der dort fehlt, wird ein Klärfall „Wert ohne Zuordnung“.", "",
               "Passwörter werden nicht übertragen: Benutzerinnen und Benutzer setzen ihr Passwort über "
               "„Passwort vergessen“ im OPAC neu.", ""]
    return "\n".join(zeilen)
