from umzug.alephino import Feld, Satz, _parse_zeile, datum, lesen_seq, schreiben_seq, zeile


def test_zeile_hin_und_zurueck():
    f = Feld("100", "  ", unter=[("p", "Müller, Anna"), ("9", "000000017"), ("4", "aut")])
    z = zeile("000000001", f)
    assert z == "000000001 10000 L $$pMüller, Anna$$9000000017$$4aut".replace("10000", "100  ")
    sysno, g = _parse_zeile(z)
    assert sysno == "000000001" and g.unter == f.unter


def test_kontrollfeld_ohne_unterfelder():
    sysno, f = _parse_zeile("000000042 001   L 000000042")
    assert f.daten == "000000042" and not f.unter


def test_datei_rundreise(tmp_path):
    saetze = [Satz("000000001", [Feld("001", daten="000000001"), Feld("331", unter=[("a", "¬Die¬ Erde")])]),
              Satz("000000002", [Feld("001", daten="000000002")])]
    schreiben_seq(tmp_path / "t.seq", saetze)
    gelesen = list(lesen_seq(tmp_path / "t.seq"))
    assert [s.sysno for s in gelesen] == ["000000001", "000000002"]
    assert gelesen[0].wert("331", "a") == "¬Die¬ Erde"


def test_datum():
    assert datum("20261116") == "2026-11-16"
    assert datum("00000000") is None
    assert datum("") is None
    assert datum("2026111") is None
