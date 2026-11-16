import csv
import hashlib
import json

import pytest
from pymarc import MARCReader

from umzug.koha import Koha
from umzug.laden import laden
from umzug.umwandeln import umwandeln


def test_mengen_und_freigaben(beispiel):
    export, ziel, prot = beispiel
    q, z = prot["quelle"], prot["ziel"]
    assert z["titel"] == q["titel"]
    assert z["exemplare"] == q["exemplare"] - 1                     # item without title: released to leave out
    assert z["ausleihen"] == q["ausleihen"] - 1                     # loan without patron: released to leave out
    assert z["personen"] == q["personen"] and z["schlagwoerter"] == q["schlagwoerter"]
    assert prot["offen"] == []
    assert prot["nfc_korrigiert"] > 0                               # DNB data comes decomposed (NFD)


def test_ohne_freigaben_stoppt(beispiel, tmp_path):
    export, _ziel, _prot = beispiel
    prot = umwandeln(export, tmp_path / "x", None, "http://opac", "http://dienst")
    arten = {k["art"] for k in prot["offen"]}
    assert {"Barcode doppelt", "Exemplar ohne Titel", "Ausleihe ohne Benutzer"} <= arten


class KeinKoha(Koha):
    """Any call to Koha fails the test: the loader must stop before it touches Koha."""
    def sql(self, anweisung):
        raise AssertionError("Koha angefasst")

    def shell(self, befehl, als_root=False):
        raise AssertionError("Koha angefasst")


def test_laden_verweigert_offene_klaerfaelle(beispiel, tmp_path):
    export, _ziel, _prot = beispiel
    umwandeln(export, tmp_path / "x", None, "http://opac", "http://dienst")
    with pytest.raises(SystemExit, match="Klärfälle ohne Freigabe"):
        laden(tmp_path / "x", export, KeinKoha(container="test"), "http://opac", "http://dienst", False, None)


def test_leeren_nur_in_der_testumgebung(beispiel):
    export, ziel, _prot = beispiel
    with pytest.raises(SystemExit, match="nur mit --container"):
        laden(ziel, export, KeinKoha(sql_befehl="koha-mysql x", shell_befehl="koha-shell x -c"), "http://opac",
              "http://dienst", True, None)


def test_barcodes_eindeutig_und_ausgabe_utf8_nfc(beispiel):
    _export, ziel, _prot = beispiel
    barcodes, n = [], 0
    with open(ziel / "titel.mrc", "rb") as fh:
        for rec in MARCReader(fh, to_unicode=True, force_utf8=True):
            n += 1
            assert rec.leader[9] == "a"                               # UTF-8
            for f in rec.get_fields("952"):
                barcodes.append(f["p"])
            text = " ".join(sf.value for f in rec.get_fields() if not f.is_control_field() for sf in f.subfields)
            import unicodedata
            assert unicodedata.normalize("NFC", text) == text
    assert len(barcodes) == len(set(barcodes))
    assert any(b.endswith("-2") for b in barcodes)


def test_pdf_pruefsummen(beispiel):
    export, ziel, _prot = beispiel
    zeilen = json.loads((ziel / "pdf.json").read_text())
    assert len(zeilen) == 40 and sum(not z["oeffentlich"] for z in zeilen) == 10
    for z in zeilen:
        assert hashlib.sha256((export / "pdf" / z["datei"]).read_bytes()).hexdigest() == z["sha256"]


def test_klaerfaelle_dokumentiert(beispiel):
    export, ziel, _prot = beispiel
    eingebaut = json.loads((export / "eingebaute-probleme.json").read_text())
    with open(ziel / "klaerfaelle.csv", encoding="utf-8") as fh:
        gefunden = {z["art"] for z in csv.DictReader(fh, delimiter=";")}
    erwartet = {"Barcode doppelt", "Exemplar ohne Titel", "Ausleihe ohne Benutzer", "Feld ohne Zuordnung",
                "Normdatenverknüpfung ins Leere", "Zugangsdatum unbekannt"}
    assert erwartet <= gefunden
    assert len(eingebaut) == 6
