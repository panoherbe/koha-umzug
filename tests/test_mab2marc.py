import unicodedata

from umzug.alephino import Feld, Satz
from umzug.mab2marc import Umsetzer, feldzuordnung_md, nfc, nichtsortier


def test_nichtsortierzeichen():
    assert nichtsortier("¬Die¬ Gartenkunst") == ("Die Gartenkunst", 4)
    assert nichtsortier("\x98Der\x9c Baumeister") == ("Der Baumeister", 4)        # NSB/NSE wie in DNB-Daten
    assert nichtsortier("¬The¬ Garden") == ("The Garden", 4)
    assert nichtsortier("Gartenkunst") == ("Gartenkunst", 0)


def test_nfc():
    zerlegt = unicodedata.normalize("NFD", "Müller")
    assert zerlegt != "Müller"
    assert nfc(zerlegt) == ("Müller", True)


def satz():
    return Satz("000000005", [
        Feld("001", daten="000000005"), Feld("010", unter=[("a", "000000001")]),
        Feld("089", unter=[("a", "Bd. 3")]),
        Feld("100", unter=[("p", unicodedata.normalize("NFD", "Jäger, Ida")), ("9", "000000007"), ("4", "aut")]),
        Feld("104", unter=[("p", "Ohne, Satz"), ("9", "000000999")]),
        Feld("331", unter=[("a", "¬Das¬ Ornament")]), Feld("425", unter=[("a", "2019")]),
        Feld("902", unter=[("s", "Architektur"), ("9", "000000003")]),
        Feld("078", unter=[("a", "intern")]),
    ])


def umsetzer():
    return Umsetzer({"person": {"000000007"}, "koerperschaft": set(), "schlagwort": {"000000003"}},
                    {"000000001": "Ornamente Europas", "000000005": "Das Ornament"})


def test_titel_umsetzung():
    erg = umsetzer().titel(satz())
    r = erg.record
    assert r["001"].data == "000000005"
    assert r["035"]["a"] == "(ALEPHINO)000000005"
    assert r["245"]["a"] == "Das Ornament." and r["245"].indicator2 == "4" and r["245"]["n"] == "Bd. 3"
    assert r["100"]["a"] == "Jäger, Ida" and r["100"]["0"] == "(ALEPHINO-PER)000000007"
    assert r["100"]["e"] == "Verfasser" and r["100"]["4"] == "aut"
    assert r["773"]["w"] == "000000001" and r["773"]["g"] == "Bd. 3" and r["773"]["t"] == "Ornamente Europas"
    assert r["650"]["a"] == "Architektur" and r["650"]["0"] == "(ALEPHINO-SW)000000003"
    assert r["264"]["c"] == "2019"
    assert erg.nfc_korrigiert >= 1


def test_klaerfaelle_statt_stiller_verluste():
    erg = umsetzer().titel(satz())
    arten = sorted(k.art for k in erg.klaerfaelle)
    assert arten == ["Feld ohne Zuordnung", "Normdatenverknüpfung ins Leere"]
    r = erg.record
    assert [f["a"] for f in r.get_fields("700")] == ["Ohne, Satz"]       # name kept as text, no link
    assert any("[MAB 078]" in f["a"] for f in r.get_fields("500"))     # unknown field kept as note


def test_feldzuordnung_ist_aktuell():
    from pathlib import Path
    datei = Path(__file__).resolve().parents[1] / "zuordnung" / "FELDZUORDNUNG.md"
    assert datei.read_text(encoding="utf-8") == feldzuordnung_md(), "python -m umzug zuordnung ausführen"


def test_isbd_satzzeichen_und_rollen():
    """Koha shows subfields as they are: the converter writes „Titel : Zusatz / Verantwortlich“ (leader/18 = i)."""
    s = Satz("000000006", [
        Feld("001", daten="000000006"),
        Feld("100", unter=[("p", "Krüger, Vera"), ("4", "edt")]),
        Feld("104", unter=[("p", "Albrecht, Ben"), ("4", "xyz")]),
        Feld("331", unter=[("a", "Fachwerk")]), Feld("335", unter=[("a", "Bauten und Techniken")]),
        Feld("359", unter=[("a", "hrsg. von Vera Krüger")]),
        Feld("410", unter=[("a", "Weimar")]), Feld("412", unter=[("a", "Verlag am Markt")]),
        Feld("425", unter=[("a", "2019")]),
        Feld("451", unter=[("a", "Beiträge zur Baugeschichte")]), Feld("455", unter=[("a", "12")]),
    ])
    r = umsetzer().titel(s).record
    assert r.leader[18] == "i"
    assert [sf.value for sf in r["245"].subfields] == ["Fachwerk :", "Bauten und Techniken /", "hrsg. von Vera Krüger"]
    assert [sf.value for sf in r["264"].subfields] == ["Weimar :", "Verlag am Markt,", "2019"]
    assert [sf.value for sf in r["490"].subfields] == ["Beiträge zur Baugeschichte ;", "12"]
    assert r["100"]["e"] == "Herausgeber" and r["100"]["4"] == "edt"
    assert r["700"].get("e") is None and r["700"]["4"] == "xyz"        # unknown code: only $4

    parallel = Satz("000000008", [Feld("001", daten="000000008"), Feld("331", unter=[("a", "Bulletin")]),
                                  Feld("335", unter=[("a", "= Journal of design history")])])
    r = umsetzer().titel(parallel).record
    assert [sf.value for sf in r["245"].subfields] == ["Bulletin =", "Journal of design history"]


def test_nichtsortierzeichen_in_namen_entfernt():
    s = Satz("000000009", [Feld("001", daten="000000009"), Feld("100", unter=[("p", "Loga, Sven ¬von¬")]),
                           Feld("331", unter=[("a", "¬Der¬ Baumeister")])])
    r = umsetzer().titel(s).record
    assert r["100"]["a"] == "Loga, Sven von"
    assert r["245"]["a"] == "Der Baumeister" and r["245"].indicator2 == "4"
