"""The check tools against a Koha state simulated from the conversion output (no Koha needed)."""
import copy
import csv
import json

import pytest
from pymarc import MARCReader

from umzug.pruefen import ausleihen, beziehungen, mengen
from umzug.pruefen.stand import Ist, Soll, nfc, titel_text

TYP = {"100": "PERSO_NAME", "110": "CORPO_NAME", "150": "TOPIC_TERM", "151": "GEOGR_NAME"}


def ist_wie_geladen(ziel):
    """What laden.py would leave in Koha, built from the converter's files."""
    ist = Ist()
    authid = {}
    with open(ziel / "normdaten.mrc", "rb") as fh:
        for i, rec in enumerate(MARCReader(fh, to_unicode=True, force_utf8=True), 1):
            nr = rec["035"]["a"]
            typ = next(TYP[t] for t in TYP if rec.get_fields(t))
            ist.normen[str(i)] = {"art": typ, "nummern": [nr]}
            authid[nr] = str(i)
    karten = {}
    with open(ziel / "benutzer.csv", encoding="utf-8") as fh:
        for i, b in enumerate(csv.DictReader(fh), 1):
            ist.benutzer[str(i)] = {"cardnumber": b["cardnumber"], "alephino": b["sort1"][len("(ALEPHINO)"):]}
            karten[b["cardnumber"]] = str(i)
    item = 0
    with open(ziel / "titel.mrc", "rb") as fh:
        for bn, rec in enumerate(MARCReader(fh, to_unicode=True, force_utf8=True), 1):
            nr = rec["001"].data
            links = [(f.tag, authid[v]) for f in rec.get_fields() if not f.is_control_field()
                     for v in f.get_subfields("0") if v in authid]
            ist.titel[nr] = {"biblionumber": str(bn), "titel": titel_text(rec["245"]["a"]), "links": links,
                             "eltern": [f["w"] for f in rec.get_fields("773")],
                             "urls": [u for f in rec.get_fields("856") for u in f.get_subfields("u")]}
            for f in rec.get_fields("952"):
                item += 1
                eid = f["x"].split(")")[-1]
                ist.exemplare[eid] = {"itemnumber": str(item), "titel": nr, "barcode": f["p"],
                                      "signatur": nfc(f.get("o")), "praesenz": f.get("7") == "1",
                                      "standort": f.get("c")}
    per_barcode = {v["barcode"]: e for e, v in ist.exemplare.items()}
    for a in json.loads((ziel / "ausleihen.json").read_text()):
        ist.ausleihen.append({"exemplar_id": per_barcode[a["barcode"]], "karte": a["cardnumber"],
                              "ausleihe": a["ausleihe"], "faellig": a["faellig"],
                              "verlaengerungen": a["verlaengerungen"]})
    for h in json.loads((ziel / "historie.json").read_text()):
        ist.historie.append({"exemplar_id": per_barcode[h["barcode"]], "karte": h["cardnumber"],
                             "ausleihe": h["ausleihe"], "rueckgabe": h["rueckgabe"]})
    for p in json.loads((ziel / "pdf.json").read_text()):
        ist.uploads[p["hash"]] = {"id": p["upload_id"], "datei": p["datei"], "oeffentlich": p["oeffentlich"],
                                  "groesse": p["groesse"]}
    return ist


@pytest.fixture(scope="module")
def stand(beispiel):
    export, ziel, _ = beispiel
    return Soll.lesen(export, ziel), ist_wie_geladen(ziel)


def test_sauberer_umzug_ohne_abweichung(stand):
    soll, ist = stand
    for werkzeug in (mengen, beziehungen, ausleihen):
        erg, abw = werkzeug(soll, ist)
        assert abw == [], (werkzeug.__name__, abw[:3])


def test_mengen_findet_fehlendes_exemplar(stand):
    soll, ist = stand
    ist = copy.deepcopy(ist)
    eid = sorted(ist.exemplare)[10]
    del ist.exemplare[eid]
    _erg, abw = mengen(soll, ist)
    assert [(a.bereich, a.objekt) for a in abw] == [("exemplare", eid)]


def test_beziehungen_findet_falsche_zuordnung_und_verknuepfung(stand):
    soll, ist = stand
    ist = copy.deepcopy(ist)
    eid = sorted(ist.exemplare)[20]
    ist.exemplare[eid]["titel"] = "000000001"
    titel = next(t for t, _a, _n in soll.links)
    ist.titel[titel]["links"] = []
    _erg, abw = beziehungen(soll, ist)
    bereiche = {(a.bereich, a.objekt) for a in abw}
    assert ("Titel–Exemplar", f"Exemplar {eid}") in bereiche
    assert any(b == "Normdaten" and o == f"Titel {titel}" for b, o in bereiche)


def test_beziehungen_findet_falschen_standort(stand):
    soll, ist = stand
    ist = copy.deepcopy(ist)
    eid = next(e for e, v in sorted(soll.exemplare.items()) if v["standort"] == "Magazin")
    ist.exemplare[eid]["standort"] = "LS"
    _erg, abw = beziehungen(soll, ist)
    assert [(a.bereich, a.objekt, a.gefunden) for a in abw] == [("Standort", f"Exemplar {eid}", "LS")]


def test_mengen_listet_jede_fehlende_nummer(stand):
    """No cap: 300 missing items give 300 lines."""
    soll, ist = stand
    ist = copy.deepcopy(ist)
    weg = sorted(ist.exemplare)[:300]
    for eid in weg:
        del ist.exemplare[eid]
    _erg, abw = mengen(soll, ist)
    assert sorted(a.objekt for a in abw if a.bereich == "exemplare") == weg


def test_beziehungen_findet_zerstoerten_umlaut(stand):
    soll, ist = stand
    ist = copy.deepcopy(ist)
    nr = next(n for n, t in sorted(soll.titel.items()) if "ä" in t)
    ist.titel[nr]["titel"] = ist.titel[nr]["titel"].replace("ä", "Ã¤")
    _erg, abw = beziehungen(soll, ist)
    assert [a.objekt for a in abw if a.bereich == "Titel und Sonderzeichen"] == [f"Titel {nr}"]


def test_ausleihen_findet_falschen_benutzer_und_fehlende_historie(stand):
    soll, ist = stand
    ist = copy.deepcopy(ist)
    ist.ausleihen[0]["karte"] = "A999999"
    ist.historie.pop()
    _erg, abw = ausleihen(soll, ist)
    assert {a.bereich for a in abw} == {"laufende Ausleihe", "Historie"}
