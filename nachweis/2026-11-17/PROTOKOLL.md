# Messprotokoll 17.11.2026

Erzeugt von `nachweis/messlauf.sh` mit `nachweis/protokoll.py` aus den Dateien in diesem Ordner; jede Zahl steht dort maschinenlesbar. Commit `694725c` (Code ohne ungespeicherte Änderungen: ja) · Koha 26.05.05.000 (aus Koha.pm; koha-testing-docker, Image 26.05) · ein Rechner (Linux, Docker).

Katalogdaten: Deutsche Nationalbibliothek (CC0). **Simuliert:** Exemplare, Benutzer (erfundene Namen, Adressen @example.org), Ausleihen, Ausleihhistorie, PDF-Dateien, die eingebauten Datenfehler und die Fehlerprobe.

## Ablauf

1. `daten/nachbilden.py` baut den Alephino-Export aus den DNB-Daten (`nachbilden.json`).
2. `umzug umwandeln` mit `beispiel/freigaben.json` (`umwandeln.json`, `protokoll.json`, `klaerfaelle.csv`).
3. `umzug laden --leeren`: Beispieldaten der Testumgebung entfernt, dann alles geladen (`laden.log`, `laden.json`).
4. `umzug pruefen alle` mit Anmeldung an der Dienstoberfläche (`pruefbericht/`).
5. `umzug.fehlerprobe`: Fehler eingebaut, alle Werkzeuge erneut (`fehlerprobe.json`, `fehlerprobe-bericht/`).
6. erneut geladen (`laden-wieder.log`, `laden-wieder.json`) und geprüft (`nach-neuladen/`), dann `pytest` (`tests.txt`).
7. die Testumgebung festgehalten: Image mit Digest, Platz, Arbeitsspeicher (`testumgebung.txt`).

## Ergebnis

| Bestand | Alephino-Export | erwartet nach Freigaben | in Koha |
|---|---|---|---|
| Titel | 1.621 | 1.621 | 1.621 |
| Exemplare | 1.882 | 1.881 | 1.881 |
| Personen | 1.120 | 1.120 | 1.120 |
| Körperschaften | 299 | 299 | 299 |
| Schlagwörter | 1.368 | 1.368 | 1.368 |
| Benutzer | 120 | 120 | 120 |
| laufende Ausleihen | 91 | 90 | 90 |
| Ausleihhistorie | 800 | 800 | 800 |
| PDF-Dateien | 40 | 40 | 40 |

„erwartet“ = Export abzüglich der Datensätze, die die Bibliothek zum Weglassen freigegeben hat: Exemplar ohne Titel (1), Ausleihe ohne Benutzer (1).

- Normdatenverknüpfungen gesetzt: 6.388, ohne Koha-Normsatz: 0.
- Werte mit zerlegten Zeichen (NFD) auf NFC gebracht: 4.272.
- Laden (alles, mit Suchindex): 57,3 s, von außen gemessen mit dem Start von Python (`laden.json` vom ersten Laden nennt 57,3 s im Werkzeug, `laden-wieder.json` vom zweiten 55,8 s). Prüfen (vier Werkzeuge): 4,7 s.
- Abweichungen nach dem Umzug: **0**. Nach dem erneuten Laden: 0.
- PDF: 40 geprüft, 30 öffentlich abrufbar und unverändert, 10 intern von außen nicht abrufbar, davon 10 mit Anmeldung abgerufen und unverändert.
- Tests: 33 passed in 6.41s.

## Klärfälle (eingebaut, simuliert) und Entscheidung

| Klärfall | Anzahl | Entscheidung | Menge |
|---|---|---|---|
| Zugangsdatum unbekannt | 5 | freigegeben: ohne Zugangsdatum übernehmen | Datensatz übernommen |
| Barcode doppelt | 1 | freigegeben: zweites Exemplar erhält Suffix -2, Etikett wird neu gedruckt | Datensatz übernommen |
| Exemplar ohne Titel | 1 | freigegeben: weglassen, Liste geht an die Bibliothek | Datensatz weggelassen |
| Feld ohne Zuordnung | 1 | freigegeben: als Fußnote 500 übernehmen | Datensatz übernommen |
| Normdatenverknüpfung ins Leere | 2 | freigegeben: Ansetzung als Text übernehmen, Verknüpfung nachpflegen | Datensatz übernommen |
| Ausleihe ohne Benutzer | 1 | freigegeben: weglassen, Liste geht an die Bibliothek | Datensatz weggelassen |

Der Export trägt außerdem, wie die DNB-Daten selbst, Zeichen in zerlegter Form; das ist kein Klärfall, sondern eine Regel der Umwandlung.

## Fehlerprobe (simuliert): 14 von 14 gefunden

| Eingebauter Fehler | Werkzeug | Meldung |
|---|---|---|
| Exemplar gelöscht | mengen | ✓ in Koha → fehlt |
| Exemplar am falschen Titel | beziehungen | ✓ bei Titel 000000451 → bei Titel 000000001 |
| Barcode verändert | beziehungen | ✓ B0001272 → B0001272X |
| Normdatenverknüpfung entfernt | beziehungen | ✓ person 000000707 (authid 2413) → Verknüpfung fehlt oder zeigt auf einen anderen Normsatz |
| Verknüpfung auf falschen Normsatz | beziehungen | ✓ person 000000815 (authid 2521) → Verknüpfung fehlt oder zeigt auf einen anderen Normsatz |
| Schlagwortsatz gelöscht | mengen | ✓ in Koha → fehlt |
| Fälligkeit verschoben | ausleihen | ✓ faellig 2026-10-28 → faellig 2026-11-04 |
| Ausleihe beim falschen Benutzer | ausleihen | ✓ karte A100037 → karte A100046 |
| PDF-Datei fehlt auf dem Server | pdf | ✓ http://127.0.0.1:18080/cgi-bin/koha/opac-retrieve-file.pl?id=6eca34d7aa68b9f0bb040d0dc6d4ea997a69f261 liefert die PDF → HTTP 200, text/html; charset=UTF-8 |
| PDF-Datei verändert | pdf | ✓ SHA-256 b5e487bf791f… → SHA-256 63af71657160… |
| Interne PDF öffentlich gestellt | pdf | ✓ nur Dienstoberfläche → ohne Anmeldung abrufbar: http://127.0.0.1:18080/cgi-bin/koha/opac-retrieve-file.pl?id=d5d083ab4ff0272d4bb5511528bca1ece13f62a2 |
| Umlaut beschädigt (Zeichensatz) | beziehungen | ✓ Evaluation und Optimierung der webbasierten Technologie-Mall für Wasserstoffsystem-Produktion gemäß ISO 9241-11 zur Steigerung von Gebrauchstauglichkeit sowie des Verständnisses industrieller und wissenschaftlicher Inhalte → Evaluation und Optimierung der webbasierten Technologie-Mall fÃ¼r Wasserstoffsystem-Produktion gemäß ISO 9241-11 zur Steigerung von Gebrauchstauglichkeit sowie des Verständnisses industrieller und wissenschaftlicher Inhalte |
| Verknüpfung zum übergeordneten Titel entfernt | beziehungen | ✓ 773 $w 000000012 → keine Verknüpfung |
| Benutzer gelöscht | mengen | ✓ in Koha → fehlt |

Dazu 26 Folgeabweichungen: Meldungen, die dieselben Änderungen nach sich ziehen (zum Beispiel Titel, deren Schlagwortsatz gelöscht wurde) und die die Werkzeuge ebenfalls melden:

- ausleihen · Historie: 20
- beziehungen · Normdaten: 4
- beziehungen · Titel–Exemplar: 1
- pdf · Zugriffsrecht: 1

## Grenzen dieser Messung

- Ein Rechner, Testumgebung koha-testing-docker; die Zeiten gelten für diesen Bestand (1.621 Titel), nicht für mehrere zehntausend Titel.
- Laden ist heute nur für die Testumgebung eingerichtet; auf einem Koha-Server laufen bisher die Prüfwerkzeuge (nicht gemessen).
- Rückgabe und Verlängerung nach dem Laden sind nicht automatisch geprüft; die Ausleihen stehen mit Fälligkeit und Verlängerungen in Koha (Werkzeug `ausleihen`).
- Suchindex Zebra; Elasticsearch nicht gemessen.
