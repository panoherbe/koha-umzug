"""Write PROTOKOLL.md of a measurement run from the files the run produced (called by nachweis/messlauf.sh).

    python nachweis/protokoll.py nachweis/<Datum>

Reads ergebnisse.json, laden.json, laden-wieder.json, pruefbericht/mengen.json, klaerfaelle.csv and fehlerprobe.json
in that folder. Every number in the protocol comes from these files; nothing in it is typed by hand.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

BESTAND = {"titel": "Titel", "exemplare": "Exemplare", "personen": "Personen", "koerperschaften": "Körperschaften",
           "schlagwoerter": "Schlagwörter", "benutzer": "Benutzer", "ausleihen": "laufende Ausleihen",
           "ausleihhistorie": "Ausleihhistorie", "pdf": "PDF-Dateien"}
MENGENMINDERND = ("Exemplar ohne Titel", "Ausleihe ohne Benutzer")


def zahl(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def komma(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def protokoll(n: Path) -> str:
    e = json.loads((n / "ergebnisse.json").read_text(encoding="utf-8"))
    mengen = json.loads((n / "pruefbericht" / "mengen.json").read_text(encoding="utf-8"))["ergebnis"]["bestaende"]
    fp = json.loads((n / "fehlerprobe.json").read_text(encoding="utf-8"))
    laden = json.loads((n / "laden.json").read_text(encoding="utf-8"))
    wieder = json.loads((n / "laden-wieder.json").read_text(encoding="utf-8"))
    with open(n / "klaerfaelle.csv", encoding="utf-8", newline="") as fh:
        klaer = list(csv.DictReader(fh, delimiter=";"))
    j, m, t = e["datum"].split("-")
    sauber = "ja" if e.get("arbeitsbaum_sauber") else "nein"
    z = [f"# Messprotokoll {t}.{m}.{j}", "",
         f"Erzeugt von `nachweis/messlauf.sh` mit `nachweis/protokoll.py` aus den Dateien in diesem Ordner; jede Zahl "
         f"steht dort maschinenlesbar. Commit `{e['commit'][:7]}` (Code ohne ungespeicherte Änderungen: {sauber}) · "
         f"Koha {e['koha']} · ein Rechner (Linux, Docker).", "",
         "Katalogdaten: Deutsche Nationalbibliothek (CC0). **Simuliert:** Exemplare, Benutzer (erfundene Namen, "
         "Adressen @example.org), Ausleihen, Ausleihhistorie, PDF-Dateien, die eingebauten Datenfehler und die "
         "Fehlerprobe.", "",
         "## Ablauf", "",
         "1. `daten/nachbilden.py` baut den Alephino-Export aus den DNB-Daten (`nachbilden.json`).",
         "2. `umzug umwandeln` mit `beispiel/freigaben.json` (`umwandeln.json`, `protokoll.json`, `klaerfaelle.csv`).",
         "3. `umzug laden --leeren`: Beispieldaten der Testumgebung entfernt, dann alles geladen (`laden.log`, "
         "`laden.json`).",
         "4. `umzug pruefen alle` mit Anmeldung an der Dienstoberfläche (`pruefbericht/`).",
         "5. `umzug.fehlerprobe`: Fehler eingebaut, alle Werkzeuge erneut (`fehlerprobe.json`, `fehlerprobe-bericht/`).",
         "6. erneut geladen (`laden-wieder.log`, `laden-wieder.json`) und geprüft (`nach-neuladen/`), dann `pytest` "
         "(`tests.txt`).",
         "7. die Testumgebung festgehalten: Image mit Digest, Platz, Arbeitsspeicher (`testumgebung.txt`).", "",
         "## Ergebnis", "",
         "| Bestand | Alephino-Export | erwartet nach Freigaben | in Koha |", "|---|---|---|---|"]
    for b in mengen:
        z.append(f"| {BESTAND.get(b['bestand'], b['bestand'])} | {zahl(b['quelle'])} | {zahl(b['erwartet'])} | "
                 f"{zahl(b['koha'])} |")
    weg = ", ".join(f"{art} ({sum(1 for k in klaer if k['art'] == art and 'weglassen' in k['aktion'])})"
                    for art in MENGENMINDERND if any(k["art"] == art and "weglassen" in k["aktion"] for k in klaer))
    weg = weg or "keine"
    v = e["normdatenverknuepfungen"]
    p = e["pdf_geprueft"]
    z += ["", f"„erwartet“ = Export abzüglich der Datensätze, die die Bibliothek zum Weglassen freigegeben hat: {weg}.",
          "",
          f"- Normdatenverknüpfungen gesetzt: {zahl(v['gesetzt'])}, ohne Koha-Normsatz: {zahl(v['ohne_koha_normsatz'])}.",
          f"- Werte mit zerlegten Zeichen (NFD) auf NFC gebracht: {zahl(e['nfc_korrigiert'])}.",
          f"- Laden (alles, mit Suchindex): {komma(e['laden_s'])} s, von außen gemessen mit dem Start von Python "
          f"(`laden.json` vom ersten Laden nennt {komma(laden['dauer_s'])} s im Werkzeug, `laden-wieder.json` vom "
          f"zweiten {komma(wieder['dauer_s'])} s). Prüfen (vier Werkzeuge): {komma(e['pruefen_s'])} s.",
          f"- Abweichungen nach dem Umzug: **{e['abweichungen_nach_umzug']}**. Nach dem erneuten Laden: "
          f"{e['abweichungen_nach_neuladen']}.",
          f"- PDF: {p['pdf']} geprüft, {p['oeffentlich']} öffentlich abrufbar und unverändert, {p['intern']} intern von "
          f"außen nicht abrufbar, davon {p.get('intern_mit_anmeldung_geprueft', 0)} mit Anmeldung abgerufen und "
          "unverändert.",
          f"- Tests: {e['tests']}.", "",
          "## Klärfälle (eingebaut, simuliert) und Entscheidung", "",
          "| Klärfall | Anzahl | Entscheidung | Menge |", "|---|---|---|---|"]
    arten = Counter(k["art"] for k in klaer)
    for art, anzahl in arten.items():
        aktion = "; ".join(sorted({k["aktion"] for k in klaer if k["art"] == art}))
        menge = "Datensatz weggelassen" if art in MENGENMINDERND and "weglassen" in aktion else "Datensatz übernommen"
        z.append(f"| {art} | {anzahl} | {aktion} | {menge} |")
    z += ["", "Der Export trägt außerdem, wie die DNB-Daten selbst, Zeichen in zerlegter Form; das ist kein Klärfall, "
          "sondern eine Regel der Umwandlung.", "",
          f"## Fehlerprobe (simuliert): {fp['gefunden']} von {fp['eingespielt']} gefunden", "",
          "| Eingebauter Fehler | Werkzeug | Meldung |", "|---|---|---|"]
    for f in fp["faelle"]:
        z.append(f"| {f['fehler']} | {f['werkzeug']} | {'✓' if f['gefunden'] else '✗'} "
                 f"{str(f.get('meldung', '')).replace('|', '/')} |")
    folge = Counter((a["werkzeug"], a["bereich"]) for a in fp["folgeabweichungen"])
    z += ["", f"Dazu {len(fp['folgeabweichungen'])} Folgeabweichungen: Meldungen, die dieselben Änderungen nach sich "
          "ziehen (zum Beispiel Titel, deren Schlagwortsatz gelöscht wurde) und die die Werkzeuge ebenfalls melden:", ""]
    z += [f"- {w} · {b}: {anzahl}" for (w, b), anzahl in sorted(folge.items())]
    titel = next((b["quelle"] for b in mengen if b["bestand"] == "titel"), 0)
    z += ["", "## Grenzen dieser Messung", "",
          f"- Ein Rechner, Testumgebung koha-testing-docker; die Zeiten gelten für diesen Bestand ({zahl(titel)} Titel), "
          "nicht für mehrere zehntausend Titel.",
          "- Laden ist heute nur für die Testumgebung eingerichtet; auf einem Koha-Server laufen bisher die "
          "Prüfwerkzeuge (nicht gemessen).",
          "- Rückgabe und Verlängerung nach dem Laden sind nicht automatisch geprüft; die Ausleihen stehen mit "
          "Fälligkeit und Verlängerungen in Koha (Werkzeug `ausleihen`).",
          "- Suchindex Zebra; Elasticsearch nicht gemessen.", ""]
    return "\n".join(z)


if __name__ == "__main__":
    ordner = Path(sys.argv[1])
    (ordner / "PROTOKOLL.md").write_text(protokoll(ordner), encoding="utf-8")
    print(ordner / "PROTOKOLL.md")
