"""ISBN field checks (umzug/isbn.py) and their use in the conversion. Synthetic records, invented titles."""
from umzug.alephino import Feld, Satz
from umzug.isbn import beurteilen
from umzug.mab2marc import Umsetzer, nur_band


def test_beurteilen():
    assert beurteilen("ISBN").art == "leer"
    assert beurteilen("ISBN keine vorh.").art == "leer" and beurteilen("ISBN keine vorh.").wert == ""
    assert beurteilen("kart. : DM 12,80").art == "leer"
    assert beurteilen("ISBN 3-16-148410-X").art == "ok"
    assert (beurteilen("ISBN 783161484100").art, beurteilen("ISBN 783161484100").wert) == ("neun-ergaenzt", "9783161484100")
    assert beurteilen("ISBN 783161484101").art == "pruefziffer"
    assert (beurteilen("ISBN 0317-8471").art, beurteilen("ISBN 0317-8471").wert) == ("issn", "0317-8471")
    assert beurteilen("ISBN 3-16-1484").art == "unvollstaendig"


def isbn_satz(nr: str, isbn: str, ind: str = "  ") -> Satz:
    return Satz(nr, [Feld("001", daten=nr), Feld("331", unter=[("a", "Die Stimme des Waldes")]),
                     Feld("540", ind=ind, unter=[("a", isbn)])])


def umsetzer() -> Umsetzer:
    return Umsetzer({"person": set(), "koerperschaft": set(), "schlagwort": set()},
                    {"000000100": "Geschichte der Seefahrt"})


def test_isbn_ohne_entscheidung():
    u = umsetzer()
    erg = u.titel(isbn_satz("000000001", "ISBN"))
    assert not erg.klaerfaelle and not erg.record.get_fields("020")
    assert erg.automatisch["ISBN-Feld ohne Nummer"] == 1
    erg = u.titel(isbn_satz("000000002", "ISBN 783161484100"))
    assert erg.record["020"]["a"] == "9783161484100" and not erg.klaerfaelle
    erg = u.titel(isbn_satz("000000003", "ISBN 0317-8471"))
    assert erg.record["022"]["a"] == "0317-8471" and not erg.record.get_fields("020")
    erg = u.titel(isbn_satz("000000004", "kart. : DM 12,80", ind="z "))
    assert erg.record["020"]["c"] == "kart. : DM 12,80" and not erg.klaerfaelle


def test_isbn_vertippt_und_unvollstaendig_bleiben_klaerfaelle():
    u = umsetzer()
    erg = u.titel(isbn_satz("000000005", "ISBN 3-16-148410-1"))
    assert [k.art for k in erg.klaerfaelle] == ["ISBN vertippt"] and erg.record["020"]["z"] == "ISBN 3-16-148410-1"
    erg = u.titel(isbn_satz("000000006", "ISBN 3-16-1484"))
    assert [k.art for k in erg.klaerfaelle] == ["ISBN unvollständig"]


def test_band_ohne_eigenen_titel_bekommt_den_titel_seines_werks():
    u = umsetzer()
    ohne = Satz("000000101", [Feld("001", daten="000000101"), Feld("010", unter=[("a", "000000100")]),
                              Feld("089", unter=[("a", "Band 3")])])
    erg = u.titel(ohne)
    assert not erg.klaerfaelle
    assert [sf.value for sf in erg.record["245"].subfields] == ["Geschichte der Seefahrt.", "Band 3"]
    assert erg.record["773"]["w"] == "000000100" and erg.record["773"]["g"] == "Band 3"
    nur_zahl = Satz("000000102", [Feld("001", daten="000000102"), Feld("010", unter=[("a", "000000100")]),
                                  Feld("331", unter=[("a", "4")])])
    assert [sf.value for sf in u.titel(nur_zahl).record["245"].subfields] == ["Geschichte der Seefahrt.", "4"]
    fremd = Satz("000000103", [Feld("001", daten="000000103"), Feld("010", unter=[("a", "000000999")])])
    assert sorted(k.art for k in u.titel(fremd).klaerfaelle) == ["Hauptsachtitel fehlt", "Übergeordneter Titel fehlt"]
    assert nur_band("XI.") and nur_band("Bd. 12") and not nur_band("1984") and not nur_band("Buch 3")
