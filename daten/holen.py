"""Fetch public catalogue data from the German National Library (DNB) as the raw material for the sample library.

DNB metadata is free under CC0 1.0 (https://www.dnb.de/EN/Professionell/Metadatendienste/Datenbezug/
Gesamtabzuege/gesamtabzuege_node.html). We take titles on art history, architecture, design and photography, the
parent records they point to (773 $w) and every GND authority record they link to (persons, corporate bodies,
subjects, places). Of an authority record we keep only the fields the sample uses (names, name variants, life dates,
identifiers): no biographical notes, places of birth or other details.

    python daten/holen.py            # writes daten/dnb/titel.xml.gz and daten/dnb/normdaten.xml.gz

The result is committed, so nobody has to fetch again; this script documents how it was made.
"""
from __future__ import annotations

import gzip
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "dnb"
SRU_TITEL = "https://services.dnb.de/sru/dnb"
SRU_NORM = "https://services.dnb.de/sru/authorities"
NS = {"srw": "http://www.loc.gov/zing/srw/", "m": "http://www.loc.gov/MARC21/slim"}
ET.register_namespace("", NS["m"])

# Subject queries (GND subject headings). Each gives at most PRO_ABFRAGE records, newest first is not guaranteed.
ABFRAGEN = [
    "sw=Kunstgeschichte and jhr>2010",
    "sw=Architektur and jhr>2010",
    "sw=Denkmalpflege and jhr>2010",
    "sw=Malerei and jhr>2010",
    "sw=Typografie",
    "sw=Gartenkunst",
    "sw=Fotografie and jhr>2014",
    "sw=Design and jhr>2014",
]
PRO_ABFRAGE = 220
# The sample must not copy the holdings of a real public body: leave out official publications of state, regional
# and federal agencies and every title about a single German federal state.
LAENDER = ("Baden-Württemberg|Bayern|Berlin|Brandenburg|Bremen|Hamburg|Hessen|Mecklenburg-Vorpommern|Niedersachsen|"
           "Nordrhein-Westfalen|Rheinland-Pfalz|Saarland|Sachsen|Sachsen-Anhalt|Schleswig-Holstein|Thüringen")
AUSLASSEN = re.compile(rf"Landesamt|Landesanstalt|Landschaftsverband|Bundesamt|Bundesanstalt|{LAENDER}", re.I)
GND = re.compile(r"^\(DE-588\)(.+)$")
DNB = re.compile(r"^\(DE-101\)(.+)$")
# fields of a GND record the sample uses (daten/nachbilden.py): identifiers, the name, its variants, life dates
NORM_FELDER = {"001", "024", "035", "100", "110", "111", "150", "151", "400", "410", "411", "450", "451"}


def holen(url: str, versuche: int = 4) -> bytes:
    for i in range(versuche):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "koha-umzug-beispieldaten/0.1"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - network hiccups: retry a few times, then give up
            if i == versuche - 1:
                raise
            print(f"  retry after {e}", file=sys.stderr)
            time.sleep(3 * (i + 1))
    raise AssertionError


def sru(basis: str, query: str, start: int, anzahl: int) -> tuple[int, list[ET.Element]]:
    q = urllib.parse.urlencode({"version": "1.1", "operation": "searchRetrieve", "query": query,
                                "recordSchema": "MARC21-xml", "maximumRecords": anzahl, "startRecord": start})
    root = ET.fromstring(holen(f"{basis}?{q}"))
    n = int(root.findtext("srw:numberOfRecords", "0", NS))
    recs = root.findall(".//srw:recordData/m:record", NS)
    time.sleep(0.5)
    return n, recs


def text(rec: ET.Element) -> str:
    """All subfield text, composed (NFC): the DNB delivers decomposed characters, „ü“ would not match the filter."""
    return unicodedata.normalize("NFC", " ".join(sf.text or "" for sf in rec.iter(f"{{{NS['m']}}}subfield")))


def kontrollnummer(rec: ET.Element) -> str:
    return rec.findtext("m:controlfield[@tag='001']", "", NS)


def unterfelder(rec: ET.Element, tags: tuple[str, ...], code: str) -> list[str]:
    out = []
    for df in rec.findall("m:datafield", NS):
        if df.get("tag") in tags:
            out += [sf.text or "" for sf in df.findall(f"m:subfield[@code='{code}']", NS)]
    return out


def schlank(rec: ET.Element) -> ET.Element:
    """The authority record reduced to NORM_FELDER (and the leader)."""
    for f in list(rec):
        if f.tag != f"{{{NS['m']}}}leader" and f.get("tag") not in NORM_FELDER:
            rec.remove(f)
    return rec


def schreiben(recs: list[ET.Element], ziel: Path) -> None:
    coll = ET.Element(f"{{{NS['m']}}}collection")
    coll.extend(recs)
    data = ET.tostring(coll, encoding="utf-8", xml_declaration=True)
    with gzip.GzipFile(ziel, "wb", mtime=0) as f:   # mtime=0: same bytes for the same records
        f.write(data)
    print(f"{ziel.name}: {len(recs)} Datensätze, {ziel.stat().st_size // 1024} KB")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    titel: dict[str, ET.Element] = {}
    for q in ABFRAGEN:
        start, geholt = 1, 0
        while geholt < PRO_ABFRAGE:
            n, recs = sru(SRU_TITEL, q, start, 100)
            if not recs:
                break
            for r in recs:
                if AUSLASSEN.search(text(r)):
                    continue
                titel.setdefault(kontrollnummer(r), r)
            geholt += len(recs)
            start += len(recs)
            if start > n:
                break
        print(f"{q}: {len(titel)} Titel bisher")

    # parent records (773 $w), so volumes and articles have their superior record in the sample
    eltern = {m.group(1) for r in titel.values() for w in unterfelder(r, ("773",), "w") if (m := DNB.match(w))}
    eltern -= set(titel)
    for chunk in [sorted(eltern)[i:i + 25] for i in range(0, len(eltern), 25)]:
        _n, recs = sru(SRU_TITEL, " or ".join(f"idn={x}" for x in chunk), 1, 100)
        for r in recs:
            if not AUSLASSEN.search(text(r)):
                titel.setdefault(kontrollnummer(r), r)
    print(f"mit übergeordneten Sätzen: {len(titel)} Titel")

    gnd = {m.group(1) for r in titel.values()
           for v in unterfelder(r, ("100", "110", "111", "600", "610", "650", "651", "689", "700", "710"), "0")
           if (m := GND.match(v))}
    normen: dict[str, ET.Element] = {}
    ids = sorted(gnd)
    for i in range(0, len(ids), 25):
        _n, recs = sru(SRU_NORM, " or ".join(f"nid={x}" for x in ids[i:i + 25]), 1, 100)
        for r in recs:
            normen.setdefault(kontrollnummer(r), schlank(r))
        if i % 500 == 0:
            print(f"  Normdaten {i}/{len(ids)}")
    schreiben([titel[k] for k in sorted(titel)], OUT / "titel.xml.gz")
    schreiben([normen[k] for k in sorted(normen)], OUT / "normdaten.xml.gz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
