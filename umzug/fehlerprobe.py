"""Fault drill (simulated): break a migrated test Koha in 14 known ways and check that the tools find each one.

    python -m umzug.fehlerprobe <export> <ziel> --container kohaumzug-koha-1 --ergebnis nachweis/…/fehlerprobe.json

Only for a test environment: it changes data in Koha. Afterwards load again (`umzug laden … --leeren`).
Each fault names the deviation the tools must report (tool, area, object). A fault counts as found only if exactly
that deviation is in the result; other deviations caused by the same change are listed as follow-on findings.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from .koha import Koha, sql_text
from .pruefen import Http, ausleihen, beziehungen, mengen, pdf
from .pruefen.stand import ART_PRAEFIX, Ist, Soll

SEED = 7


def faelle(k: Koha, soll: Soll, ist: Ist, upload_pfad: str, rnd: random.Random) -> list[dict]:
    """Apply the faults; return what each one must produce."""
    out = []

    def fall(name: str, werkzeug: str, bereich: str, objekt: str, sql: str | None = None, shell: str | None = None):
        if sql:
            k.sql(sql)
        if shell:
            k.shell(shell, als_root=True)
        out.append({"fehler": name, "werkzeug": werkzeug, "bereich": bereich, "objekt": objekt})

    ausgeliehen = {a["exemplar_id"] for a in soll.ausleihen} | {h["exemplar_id"] for h in soll.historie}
    frei = sorted(e for e in soll.exemplare if e not in ausgeliehen and e in ist.exemplare)
    e1, e2, e14 = rnd.sample(frei, 3)
    fall("Exemplar gelöscht", "mengen", "exemplare", e1,
         sql=f"DELETE FROM items WHERE itemnumber = {ist.exemplare[e1]['itemnumber']};")
    anderer = next(nr for nr in sorted(ist.titel) if nr != ist.exemplare[e2]["titel"])
    bn = ist.titel[anderer]["biblionumber"]
    fall("Exemplar am falschen Titel", "beziehungen", "Titel–Exemplar", f"Exemplar {e2}",
         sql=f"UPDATE items SET biblionumber = {bn}, biblioitemnumber = (SELECT biblioitemnumber FROM biblioitems "
             f"WHERE biblionumber = {bn}) WHERE itemnumber = {ist.exemplare[e2]['itemnumber']};")
    fall("Barcode verändert", "beziehungen", "Barcode", f"Exemplar {e14}",
         sql=f"UPDATE items SET barcode = CONCAT(barcode, 'X') WHERE itemnumber = {ist.exemplare[e14]['itemnumber']};")

    authid_von = {nr: a for a, v in ist.normen.items() for nr in v["nummern"]}
    personen_links = sorted({(t, nr) for t, art, nr in soll.links if art == "person"})
    (t3, n3), (t4, n4) = rnd.sample(personen_links, 2)
    a3, a4 = authid_von[ART_PRAEFIX["person"] + n3], authid_von[ART_PRAEFIX["person"] + n4]
    fremd = next(a for a, v in sorted(ist.normen.items()) if v["art"] == "PERSO_NAME" and a != a4)
    fall("Normdatenverknüpfung entfernt", "beziehungen", "Normdaten", f"Titel {t3}",
         sql=f"UPDATE biblio_metadata SET metadata = REPLACE(metadata, '<subfield code=\"9\">{a3}</subfield>', '') "
             f"WHERE biblionumber = {ist.titel[t3]['biblionumber']};")
    fall("Verknüpfung auf falschen Normsatz", "beziehungen", "Normdaten", f"Titel {t4}",
         sql=f"UPDATE biblio_metadata SET metadata = REPLACE(metadata, '<subfield code=\"9\">{a4}</subfield>', "
             f"'<subfield code=\"9\">{fremd}</subfield>') WHERE biblionumber = {ist.titel[t4]['biblionumber']};")
    sw = sorted({nr for _t, art, nr in soll.links if art == "schlagwort"})
    n5 = rnd.choice(sw)
    fall("Schlagwortsatz gelöscht", "mengen", "schlagwoerter", n5,
         sql=f"DELETE FROM auth_header WHERE authid = {authid_von[ART_PRAEFIX['schlagwort'] + n5]};")

    karten = soll.benutzer
    a6, a7 = rnd.sample(soll.ausleihen[:-1], 2)
    fall("Fälligkeit verschoben", "ausleihen", "laufende Ausleihe", f"Exemplar {a6['exemplar_id']}",
         sql=f"UPDATE issues SET date_due = date_due + INTERVAL 7 DAY "
             f"WHERE itemnumber = {ist.exemplare[a6['exemplar_id']]['itemnumber']};")
    falscher = next(b for b, v in sorted(ist.benutzer.items()) if v["cardnumber"] not in (karten.get(a7["benutzer_id"]), None)
                    and v["alephino"])
    fall("Ausleihe beim falschen Benutzer", "ausleihen", "laufende Ausleihe", f"Exemplar {a7['exemplar_id']}",
         sql=f"UPDATE issues SET borrowernumber = {falscher} "
             f"WHERE itemnumber = {ist.exemplare[a7['exemplar_id']]['itemnumber']};")

    oeff = sorted(t for t, p in soll.pdf.items() if p["oeffentlich"])
    intern = sorted(t for t, p in soll.pdf.items() if not p["oeffentlich"])
    t8, t13 = rnd.sample(oeff, 2)
    t9 = rnd.choice(intern)
    p8, p13 = soll.pdf[t8], soll.pdf[t13]
    fall("PDF-Datei fehlt auf dem Server", "pdf", "Erreichbarkeit", f"Titel {t8}",
         shell=f"rm -f '{upload_pfad}/PDF/{p8['hash']}_{p8['datei']}'")
    fall("PDF-Datei verändert", "pdf", "Unverändert", f"Titel {t13}",
         shell=f"printf '%%%% geändert\\n' >> '{upload_pfad}/PDF/{p13['hash']}_{p13['datei']}'")
    fall("Interne PDF öffentlich gestellt", "pdf", "Zugriffsrecht", f"Titel {t9}",
         sql=f"UPDATE uploaded_files SET public = 1 WHERE hashvalue = {sql_text(soll.pdf[t9]['hash'])};")

    mit_umlaut = sorted(nr for nr, t in soll.titel.items() if "ü" in t and nr in ist.titel)
    t10 = rnd.choice(mit_umlaut)
    fall("Umlaut beschädigt (Zeichensatz)", "beziehungen", "Titel und Sonderzeichen", f"Titel {t10}",
         sql=f"UPDATE biblio_metadata SET metadata = REPLACE(metadata, 'ü', 'Ã¼') "
             f"WHERE biblionumber = {ist.titel[t10]['biblionumber']};")
    t11 = rnd.choice(sorted(t for t in soll.eltern if t in ist.titel))
    fall("Verknüpfung zum übergeordneten Titel entfernt", "beziehungen", "über-/untergeordnet", f"Titel {t11}",
         sql="UPDATE biblio_metadata SET metadata = REGEXP_REPLACE(metadata, "
             "'<datafield tag=\"773\"[^>]*>[\\\\s\\\\S]*?</datafield>', '') "
             f"WHERE biblionumber = {ist.titel[t11]['biblionumber']};")
    # a patron without current loans (Koha keeps the history and empties its borrower: a follow-on finding)
    aktiv = {a["benutzer_id"] for a in soll.ausleihen}
    b12 = rnd.choice(sorted(b for b in soll.benutzer if b not in aktiv))
    fall("Benutzer gelöscht", "mengen", "benutzer", soll.benutzer[b12],
         sql=f"DELETE FROM borrowers WHERE cardnumber = {sql_text(soll.benutzer[b12])};")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("export", type=Path)
    ap.add_argument("ziel", type=Path)
    ap.add_argument("--container", required=True)
    ap.add_argument("--instanz", default="kohadev")
    ap.add_argument("--opac-url", default="http://127.0.0.1:18080")
    ap.add_argument("--ergebnis", type=Path, required=True)
    a = ap.parse_args(argv)
    k = Koha(instanz=a.instanz, container=a.container)
    soll = Soll.lesen(a.export, a.ziel)

    def alle_pruefen():
        ist = Ist.lesen(k)
        abw = []
        for f in (mengen, beziehungen, ausleihen):
            abw += f(soll, ist)[1]
        abw += pdf(soll, ist, a.opac_url, Http())[1]
        return ist, abw

    ist, vorher = alle_pruefen()
    if vorher:
        raise SystemExit(f"Ausgangslage nicht sauber: {len(vorher)} Abweichungen; erst neu laden")
    upload_pfad = k.shell("grep -oP '(?<=<upload_path>)[^<]+' /etc/koha/sites/*/koha-conf.xml", als_root=True).strip()
    erwartet = faelle(k, soll, ist, upload_pfad, random.Random(SEED))
    _ist, nachher = alle_pruefen()
    gefunden = []
    benutzt = set()
    for e in erwartet:
        treffer = [i for i, x in enumerate(nachher) if x.werkzeug == e["werkzeug"] and x.bereich == e["bereich"]
                   and e["objekt"] in x.objekt]
        benutzt.update(treffer)
        gefunden.append({**e, "gefunden": bool(treffer),
                         "meldung": (f"{nachher[treffer[0]].erwartet} → {nachher[treffer[0]].gefunden}" if treffer else None)})
    folge = [vars(x) for i, x in enumerate(nachher) if i not in benutzt]
    ergebnis = {"eingespielt": len(erwartet), "gefunden": sum(f["gefunden"] for f in gefunden),
                "abweichungen_vorher": len(vorher), "abweichungen_nachher": len(nachher),
                "faelle": gefunden, "folgeabweichungen": folge, "hinweis": "simuliert: Fehler absichtlich eingespielt"}
    a.ergebnis.parent.mkdir(parents=True, exist_ok=True)
    a.ergebnis.write_text(json.dumps(ergebnis, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{ergebnis['gefunden']} von {ergebnis['eingespielt']} eingespielten Fehlern gefunden "
          f"({len(folge)} Folgeabweichungen)")
    for f in gefunden:
        print(("  ✓ " if f["gefunden"] else "  ✗ ") + f["fehler"] + (f": {f['meldung']}" if f["meldung"] else ""))
    return 0 if ergebnis["gefunden"] == ergebnis["eingespielt"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
