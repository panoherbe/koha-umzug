"""Befehle:

    python -m umzug umwandeln <export> <ziel> [--freigaben datei] [--opac-url URL] [--dienst-url URL]
    python -m umzug laden <ziel> <export> [--container NAME | --sql BEFEHL --shell BEFEHL] [--leeren] [--sprache de-DE]
    python -m umzug pruefen <mengen|beziehungen|pdf|ausleihen|alle> <export> <ziel> [Koha-Zugang] [--bericht ordner]
    python -m umzug zuordnung            schreibt zuordnung/FELDZUORDNUNG.md aus den Regeln des Konverters
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def koha_zugang(a):
    from .koha import Koha
    return Koha(instanz=a.instanz, container=a.container, sql_befehl=a.sql, shell_befehl=a.shell)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="umzug", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="befehl", required=True)

    def zugang(p):
        p.add_argument("--instanz", default="kohadev")
        p.add_argument("--container", help="Docker-Container mit Koha (Testumgebung)")
        p.add_argument("--sql", help="SQL-Befehl auf dem Server, z. B. 'sudo koha-mysql bibliothek'")
        p.add_argument("--shell", help="Shell-Befehl auf dem Server, z. B. 'sudo koha-shell bibliothek -c'")
        p.add_argument("--opac-url", default="http://127.0.0.1:18080")
        p.add_argument("--dienst-url", default="http://127.0.0.1:18081")

    p = sub.add_parser("umwandeln")
    p.add_argument("export", type=Path)
    p.add_argument("ziel", type=Path)
    p.add_argument("--freigaben", type=Path)
    p.add_argument("--opac-url", default="http://127.0.0.1:18080")
    p.add_argument("--dienst-url", default="http://127.0.0.1:18081")

    p = sub.add_parser("laden")
    p.add_argument("ziel", type=Path)
    p.add_argument("export", type=Path)
    p.add_argument("--leeren", action="store_true",
                   help="nur mit --container (Testumgebung): alle Titel, Exemplare, Benutzer und Ausleihen vorher löschen")
    p.add_argument("--sprache", default=None, help="z. B. de-DE, wenn die Übersetzung installiert ist")
    zugang(p)

    p = sub.add_parser("pruefen")
    p.add_argument("was", choices=["mengen", "beziehungen", "pdf", "ausleihen", "alle"])
    p.add_argument("export", type=Path)
    p.add_argument("ziel", type=Path, help="Ordner der Umwandlung (Freigaben, Protokoll, pdf.json)")
    p.add_argument("--bericht", type=Path, help="Ordner für JSON, CSV und HTML (Standard: <ziel>/pruefung)")
    p.add_argument("--dienst-benutzer", help="Konto der Dienstoberfläche, um interne PDFs zu prüfen")
    p.add_argument("--dienst-passwort")
    zugang(p)

    sub.add_parser("zuordnung")
    a = ap.parse_args(argv)

    if a.befehl == "umwandeln":
        from .umwandeln import umwandeln
        prot = umwandeln(a.export, a.ziel, a.freigaben, a.opac_url.rstrip("/"), a.dienst_url.rstrip("/"))
        print(json.dumps({k: prot[k] for k in ("quelle", "ziel", "weggelassen", "klaerfaelle", "nfc_korrigiert")},
                         ensure_ascii=False, indent=1))
        if prot["offen"]:
            print(f"STOPP: {len(prot['offen'])} Klärfälle ohne Freigabe, siehe {a.ziel / 'klaerfaelle.csv'}",
                  file=sys.stderr)
            return 2
        return 0
    if a.befehl == "laden":
        from .laden import laden
        laden(a.ziel, a.export, koha_zugang(a), a.opac_url.rstrip("/"), a.dienst_url.rstrip("/"), a.leeren, a.sprache)
        return 0
    if a.befehl == "pruefen":
        from .pruefen import ausfuehren
        return ausfuehren(a.was, a.export, a.ziel, koha_zugang(a), a.opac_url.rstrip("/"), a.dienst_url.rstrip("/"),
                          a.bericht or (a.ziel / "pruefung"), a.dienst_benutzer, a.dienst_passwort)
    if a.befehl == "zuordnung":
        from .mab2marc import feldzuordnung_md
        ziel = HERE.parent / "zuordnung" / "FELDZUORDNUNG.md"
        ziel.write_text(feldzuordnung_md(), encoding="utf-8")
        print(ziel)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
