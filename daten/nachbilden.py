"""Build a sample Alephino export from public DNB data, so the whole migration can be shown and measured in public.

    python daten/nachbilden.py [--ziel beispiel/export]

What is real and what is simulated:

- **real (DNB, CC0):** titles, authors, corporate bodies, subjects, GND authority records, superior records
- **simulated:** the Alephino system numbers, the MAB2 form of the records, items, patrons (invented names),
  loans, loan history and the PDF files (one page each, generated here)
- **as found in the DNB data:** characters in decomposed form (NFD), which the converter normalises
- **built-in data quality problems (simulated, on purpose):** a duplicate barcode, an item without
  title, links to authority records missing from the export, a loan without patron, an unmapped field, unknown dates.
  The converter must find every one of them; the tests check that it does.

Deterministic: the same input gives the same export, byte for byte (fixed random seed, sorted input).
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import random
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from umzug.alephino import Feld, Satz, schreiben_csv, schreiben_seq  # noqa: E402

M = "{http://www.loc.gov/MARC21/slim}"
SEED = 20261116
BENUTZER = 120                      # simulated patrons
ARTIKEL = ("Der ", "Die ", "Das ", "Den ", "Dem ", "Des ", "Ein ", "Eine ", "The ", "A ", "An ")
VORNAMEN = ["Anna", "Ben", "Clara", "David", "Elif", "Felix", "Greta", "Hannes", "Ida", "Jonas", "Katharina", "Lukas",
            "Mara", "Niklas", "Olga", "Paul", "Rosa", "Simon", "Tara", "Uwe", "Vera", "Wim", "Yusuf", "Zoe"]
NACHNAMEN = ["Albrecht", "Becker", "Çelik", "Dietrich", "Engel", "Fuchs", "Günther", "Hoffmann", "Jäger", "Krüger",
             "Lehmann", "Möller", "Neumann", "Öztürk", "Peters", "Quast", "Richter", "Schäfer", "Thiel", "Ulrich",
             "Vogel", "Weiß", "Yilmaz", "Zimmermann"]


def lesen(pfad: Path) -> list[ET.Element]:
    with gzip.open(pfad) as f:
        return list(ET.parse(f).getroot())


def cf(rec: ET.Element, tag: str) -> str:
    e = rec.find(f"{M}controlfield[@tag='{tag}']")
    return (e.text or "") if e is not None else ""


def dfs(rec: ET.Element, *tags: str) -> list[ET.Element]:
    return [d for d in rec.findall(f"{M}datafield") if d.get("tag") in tags]


def mab_text(text: str | None) -> str | None:
    """DNB marks non-sorting parts with the control characters NSB/NSE (U+0098, U+009C); MAB2 and Alephino use a
    pair of „¬“. The export carries them the way Alephino does."""
    return None if text is None else text.replace("\x98", "¬").replace("\x9c", "¬")


def sf(d: ET.Element, code: str) -> str | None:
    e = d.find(f"{M}subfield[@code='{code}']")
    return mab_text(e.text) if e is not None else None


def sfs(d: ET.Element, code: str) -> list[str]:
    return [mab_text(e.text) or "" for e in d.findall(f"{M}subfield[@code='{code}']")]


def gnd_id(d: ET.Element) -> str | None:
    return next((v[8:] for v in sfs(d, "0") if v.startswith("(DE-588)")), None)


def normart(rec: ET.Element) -> tuple[str, str] | None:
    """(art, MAB subfield code) of a GND record: person p, corporate k, subject s, place g."""
    if dfs(rec, "100") and sf(dfs(rec, "100")[0], "t") is None:
        return "person", "p"
    if dfs(rec, "110", "111"):
        return "koerperschaft", "k"
    if dfs(rec, "150"):
        return "schlagwort", "s"
    if dfs(rec, "151"):
        return "schlagwort", "g"
    return None


def pdf_bytes(titel: str, nummer: str) -> bytes:
    """A minimal one-page PDF (Helvetica, WinAnsi) with the title. Enough for a link and a checksum."""
    t = unicodedata.normalize("NFC", titel)[:80].encode("cp1252", "replace").decode("cp1252")
    t = t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    inhalt = (f"BT /F1 14 Tf 60 760 Td (Beispieldokument {nummer}) Tj 0 -24 Td /F1 11 Tf ({t}) Tj "
              "0 -20 Td (Simulierte Datei fuer die Migrationsprobe.) Tj ET").encode("cp1252")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(inhalt) + inhalt + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out, offs = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ziel", type=Path, default=HERE.parent / "beispiel" / "export")
    a = ap.parse_args(argv)
    rnd = random.Random(SEED)
    ziel: Path = a.ziel
    (ziel / "pdf").mkdir(parents=True, exist_ok=True)
    for alt in (ziel / "pdf").glob("*.pdf"):
        alt.unlink()

    titel_dnb = sorted(lesen(HERE / "dnb" / "titel.xml.gz"), key=lambda r: cf(r, "001"))
    norm_dnb = sorted(lesen(HERE / "dnb" / "normdaten.xml.gz"), key=lambda r: cf(r, "001"))

    # --- authority records: one Alephino „Stammsatz“ per GND record, numbered per file -----------------------
    normen: dict[str, list[Satz]] = {"person": [], "koerperschaft": [], "schlagwort": []}
    gnd_zu: dict[str, tuple[str, str, str]] = {}          # GND id -> (art, code, Alephino number)
    for r in norm_dnb:
        na = normart(r)
        gnd = next((sf(d, "a") for d in dfs(r, "024") if sf(d, "2") == "gnd"), None) or cf(r, "001")
        if na is None:
            continue
        art, code = na
        nr = f"{len(normen[art]) + 1:09d}"
        s = Satz(nr, [Feld("001", daten=nr), Feld("024", unter=[("a", f"(DE-588){gnd}")])])
        if art == "person":
            d = dfs(r, "100")[0]
            unter = [("p", sf(d, "a") or "")] + ([("d", sf(d, "d"))] if sf(d, "d") else [])
            s.felder.append(Feld("800", unter=unter))
            s.felder += [Feld("830", unter=[("p", sf(v, "a") or "")]) for v in dfs(r, "400")[:5] if sf(v, "a")]
        elif art == "koerperschaft":
            d = (dfs(r, "110") or dfs(r, "111"))[0]
            name = ". ".join([sf(d, "a") or ""] + sfs(d, "b"))
            s.felder.append(Feld("800", unter=[("k", name)]))
            s.felder += [Feld("830", unter=[("k", sf(v, "a") or "")]) for v in dfs(r, "410")[:5] if sf(v, "a")]
        else:
            d = (dfs(r, "150") or dfs(r, "151"))[0]
            s.felder.append(Feld("800", unter=[(code, sf(d, "a") or "")]))
            s.felder += [Feld("830", unter=[(code, sf(v, "a") or "")]) for v in dfs(r, "450", "451")[:5] if sf(v, "a")]
        normen[art].append(s)
        gnd_zu[gnd] = (art, code, nr)
        for alt in (d.text for d in r.findall(f"{M}datafield[@tag='035']/{M}subfield[@code='a']")):
            if alt and alt.startswith("(DE-588)"):
                gnd_zu.setdefault(alt[8:], (art, code, nr))

    # --- titles --------------------------------------------------------------------------------------------
    sysno = {cf(r, "001"): f"{i + 1:09d}" for i, r in enumerate(titel_dnb)}
    titel: list[Satz] = []
    serien: set[str] = set()
    for r in titel_dnb:
        nr = sysno[cf(r, "001")]
        s = Satz(nr, [Feld("FMT", daten="BK"), Feld("001", daten=nr)])
        d008 = cf(r, "008")
        if len(d008) >= 6 and d008[:6].isdigit():
            s.felder.append(Feld("002", "a ", unter=[("a", ("19" if d008[0] in "789" else "20") + d008[:6])]))
        s.felder.append(Feld("025", "a ", unter=[("a", cf(r, "001"))]))
        for d in dfs(r, "041")[:1]:
            s.felder.append(Feld("037", "b ", unter=[("b", sf(d, "a") or "ger")]))
        for d in dfs(r, "773")[:1]:
            w = next((v[8:] for v in sfs(d, "w") if v.startswith("(DE-101)")), None)
            if w and w in sysno:
                s.felder.append(Feld("010", unter=[("a", sysno[w])]))
                serien.add(sysno[w])
        p_tags = iter(f"{n:03d}" for n in range(100, 200, 4))
        for d in dfs(r, "100", "700"):
            if sf(d, "t"):
                continue
            unter = [("p", sf(d, "a") or "")]
            if (g := gnd_id(d)) and g in gnd_zu and gnd_zu[g][0] == "person":
                unter.append(("9", gnd_zu[g][2]))
            if (rolle := (sfs(d, "4") or [None])[0]):
                unter.append(("4", rolle))
            if (t := next(p_tags, None)):
                s.felder.append(Feld(t, unter=unter))
        k_tags = iter(f"{n:03d}" for n in range(200, 300, 4))
        for d in dfs(r, "110", "710"):
            if sf(d, "t"):
                continue
            unter = [("k", ". ".join([sf(d, "a") or ""] + sfs(d, "b")))]
            if (g := gnd_id(d)) and g in gnd_zu and gnd_zu[g][0] == "koerperschaft":
                unter.append(("9", gnd_zu[g][2]))
            if (rolle := (sfs(d, "4") or [None])[0]):
                unter.append(("4", rolle))
            if (t := next(k_tags, None)):
                s.felder.append(Feld(t, unter=unter))
        t245 = dfs(r, "245")[0] if dfs(r, "245") else None
        if t245 is not None:
            haupt = " ".join([sf(t245, "a") or ""] + sfs(t245, "p")).strip(" /:;")
            nsz = int(t245.get("ind2") or "0") if (t245.get("ind2") or " ").isdigit() else 0
            if nsz == 0:
                art = next((x for x in ARTIKEL if haupt.startswith(x)), None)
                nsz = len(art) if art else 0
            if nsz:
                haupt = f"¬{haupt[:nsz].rstrip()}¬ {haupt[nsz:]}"
            s.felder.append(Feld("331", unter=[("a", haupt)]))
            if (b := sf(t245, "b")):
                s.felder.append(Feld("335", unter=[("a", b.strip(" /:;"))]))
            if (n := sf(t245, "n")):
                s.felder.append(Feld("089", unter=[("a", n)]))
            if (c := sf(t245, "c")):
                s.felder.append(Feld("359", unter=[("a", c)]))
        for tag, mab in (("250", "403"),):
            for d in dfs(r, tag)[:1]:
                s.felder.append(Feld(mab, unter=[("a", sf(d, "a") or "")]))
        for d in [x for x in dfs(r, "264") if x.get("ind2") == "1"][:1]:
            for code, mab in (("a", "410"), ("b", "412"), ("c", "425")):
                if sf(d, code):
                    s.felder.append(Feld(mab, unter=[("a", sf(d, code) or "")]))
        for d in dfs(r, "300")[:1]:
            s.felder.append(Feld("433", unter=[("a", sf(d, "a") or "")]))
        for d in dfs(r, "490")[:1]:
            s.felder.append(Feld("451", unter=[("a", sf(d, "a") or "")]))
            if sf(d, "v"):
                s.felder.append(Feld("455", unter=[("a", sf(d, "v") or "")]))
        for d in dfs(r, "020")[:2]:
            if sf(d, "a"):
                s.felder.append(Feld("540", unter=[("a", (sf(d, "a") or "").split(" ")[0])]))
        for d in dfs(r, "022")[:1]:
            if sf(d, "a"):
                s.felder.append(Feld("542", unter=[("a", sf(d, "a") or "")]))
        gesehen = set()
        for d in dfs(r, "689", "650", "651", "600", "610"):
            g = gnd_id(d)
            if not g or g in gesehen or g not in gnd_zu:
                continue
            gesehen.add(g)
            art, code, nnr = gnd_zu[g]
            name = sf(d, "a") or ""
            s.felder.append(Feld("902", unter=[(code, name), ("9", nnr)]))
        for d in dfs(r, "856")[:1]:
            if sf(d, "u"):
                s.felder.append(Feld("655", "e ", unter=[("u", sf(d, "u") or "")]))
        titel.append(s)

    # --- built-in data quality problems (simulated, on purpose) ---------------------------------------------
    probleme: dict[str, list[str]] = {}
    # The DNB data comes in decomposed Unicode (NFD, e.g. „u“ + combining diaeresis), as many Aleph exports do.
    # We keep it that way: the converter must normalise to NFC, and its protocol counts how many values it fixed.
    for s in titel:
        s.felder = [f for f in s.felder if f.daten or any(v.strip() for _c, v in f.unter)]
    ohne_feld = rnd.choice(titel)                                            # an unmapped field
    ohne_feld.felder.append(Feld("078", unter=[("a", "Interne Bemerkung: Altbestand, Stempel prüfen")]))
    probleme["Feld ohne Zuordnung (MAB 078)"] = [ohne_feld.sysno]
    verlinkte = sorted({f.get("9") for s in titel for f in s.felder_von("100") if f.get("9")})
    weg = set(rnd.sample(verlinkte, k=2))                                    # authority records missing from export
    normen["person"] = [p for p in normen["person"] if p.sysno not in weg]
    probleme["Normsatz fehlt im Export (Person)"] = sorted(weg)

    # --- items -----------------------------------------------------------------------------------------------
    standorte = [("Magazin", 60), ("Lesesaal", 25), ("Freihand", 15)]
    exemplare: list[dict[str, str]] = []
    for s in titel:
        if s.sysno in serien:
            continue                                                         # superior records: no items of their own
        n = 1 + (rnd.random() < 0.15) + (rnd.random() < 0.03)
        for _ in range(n):
            nr = f"{len(exemplare) + 1:09d}"
            ort = rnd.choices([o for o, _w in standorte], [w for _o, w in standorte])[0]
            typ = "ZS" if s.feld("010") else "BK"
            zugang = f"{rnd.randint(2011, 2026)}{rnd.randint(1, 12):02d}{rnd.randint(1, 28):02d}"
            exemplare.append({"exemplar_id": nr, "titel_id": s.sysno, "barcode": f"B{int(nr):07d}",
                              "signatur": f"{rnd.choice('ABCDEFGH')} {rnd.randint(1, 99)}.{rnd.randint(1, 999):03d}",
                              "standort": ort, "medientyp": typ,
                              "status": "praesenz" if ort == "Lesesaal" else "ausleihbar", "zugang": zugang})
    for ex in rnd.sample(exemplare, k=5):
        ex["zugang"] = "00000000"
    probleme["Zugangsdatum unbekannt (00000000)"] = sorted(e["exemplar_id"] for e in exemplare if e["zugang"] == "00000000")
    a, b = rnd.sample(exemplare, k=2)
    b["barcode"] = a["barcode"]
    probleme["Barcode doppelt"] = [a["exemplar_id"], b["exemplar_id"]]
    waise = {"exemplar_id": f"{len(exemplare) + 1:09d}", "titel_id": "999999999", "barcode": "B9999999",
             "signatur": "X 1.001", "standort": "Magazin", "medientyp": "BK", "status": "ausleihbar",
             "zugang": "20190301"}
    exemplare.append(waise)
    probleme["Exemplar ohne Titel"] = [waise["exemplar_id"]]

    # --- patrons (simulated people) ------------------------------------------------------------------------------
    benutzer = []
    def person(r: random.Random, i: int) -> dict:
        vn, nn = r.choice(VORNAMEN), r.choice(NACHNAMEN)
        return {"benutzer_id": f"{i + 1:09d}", "ausweis": f"A{100000 + i:06d}", "nachname": nn,
                "vorname": vn, "email": f"{vn.lower()}.{i + 1}@example.org",
                "gruppe": "MA" if r.random() < 0.7 else "EX",
                "gueltig_bis": f"{r.choice([2027, 2028])}{r.randint(1, 12):02d}28"}

    benutzer = [person(rnd, i) for i in range(BENUTZER)]

    # --- loans and history ------------------------------------------------------------------------------------
    eindeutig = [e for e in exemplare if e["status"] == "ausleihbar" and e is not waise and e not in (a, b)]
    laufend = rnd.sample(eindeutig, k=90)
    ausleihen = []
    stichtag = dt.date(2026, 11, 16)
    for e in laufend:
        aus = stichtag - dt.timedelta(days=rnd.randint(1, 60))
        faellig = aus + dt.timedelta(days=28 * (1 + rnd.choice([0, 0, 1, 2])))
        ausleihen.append({"exemplar_id": e["exemplar_id"], "benutzer_id": rnd.choice(benutzer)["benutzer_id"],
                          "ausleihe": f"{aus:%Y%m%d}", "faellig": f"{faellig:%Y%m%d}",
                          "verlaengerungen": str((faellig - aus).days // 28 - 1)})
    ausleihen.append({"exemplar_id": rnd.choice([e for e in eindeutig if e not in laufend])["exemplar_id"],
                      "benutzer_id": "000000999", "ausleihe": "20261002", "faellig": "20261130",
                      "verlaengerungen": "0"})
    probleme["Ausleihe ohne Benutzer"] = ["000000999"]
    historie = []
    for _ in range(800):
        e = rnd.choice(eindeutig)
        aus = dt.date(2018, 1, 1) + dt.timedelta(days=rnd.randint(0, 3200))
        zurueck = aus + dt.timedelta(days=rnd.randint(3, 80))
        historie.append({"exemplar_id": e["exemplar_id"], "benutzer_id": rnd.choice(benutzer)["benutzer_id"],
                         "ausleihe": f"{aus:%Y%m%d}", "rueckgabe": f"{zurueck:%Y%m%d}"})
    historie.sort(key=lambda h: (h["ausleihe"], h["exemplar_id"]))

    # --- PDF files linked to titles ------------------------------------------------------------------------------
    mit_pdf = rnd.sample([s for s in titel if s.sysno not in serien], k=40)
    pdf = []
    for i, s in enumerate(sorted(mit_pdf, key=lambda x: x.sysno)):
        name = f"{s.sysno}.pdf"
        titeltext = (s.wert("331", "a") or "").replace("¬", "")
        (ziel / "pdf" / name).write_bytes(pdf_bytes(titeltext, s.sysno))
        pdf.append({"titel_id": s.sysno, "datei": name, "zugriff": "intern" if i % 4 == 3 else "oeffentlich"})

    schreiben_seq(ziel / "titel.seq", titel)
    schreiben_seq(ziel / "personen.seq", normen["person"])
    schreiben_seq(ziel / "koerperschaften.seq", normen["koerperschaft"])
    schreiben_seq(ziel / "schlagwoerter.seq", normen["schlagwort"])
    schreiben_csv(ziel / "exemplare.csv", exemplare)
    schreiben_csv(ziel / "benutzer.csv", benutzer)
    schreiben_csv(ziel / "ausleihen.csv", ausleihen)
    schreiben_csv(ziel / "ausleihhistorie.csv", historie)
    schreiben_csv(ziel / "pdf.csv", pdf)
    (ziel / "eingebaute-probleme.json").write_text(json.dumps(probleme, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({"titel": len(titel), "personen": len(normen["person"]),
                      "koerperschaften": len(normen["koerperschaft"]), "schlagwoerter": len(normen["schlagwort"]),
                      "exemplare": len(exemplare), "benutzer": len(benutzer), "ausleihen": len(ausleihen),
                      "historie": len(historie), "pdf": len(pdf),
                      "probleme": {k: len(v) for k, v in probleme.items()}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
