import hashlib

from daten import nachbilden


def test_gleiche_eingabe_gleicher_export(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    nachbilden.main(["--ziel", str(a)])
    nachbilden.main(["--ziel", str(b)])
    for name in ("titel.seq", "personen.seq", "exemplare.csv", "ausleihen.csv", "pdf.csv"):
        assert hashlib.sha256((a / name).read_bytes()).digest() == hashlib.sha256((b / name).read_bytes()).digest()


def test_keine_echten_personen_im_benutzerbestand(tmp_path):
    nachbilden.main(["--ziel", str(tmp_path)])
    text = (tmp_path / "benutzer.csv").read_text(encoding="utf-8")
    assert "@example.org" in text and text.count("@") == text.count("@example.org")
