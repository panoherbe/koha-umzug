# koha-umzug

**Bibliotheken ziehen geprüft zu Koha um, der freien Bibliothekssoftware.**

koha-umzug bringt den Bestand aus Alephino in Koha: Titel, Exemplare, Normdaten, Benutzer, Ausleihen und PDF-Dateien.
Danach vergleichen vier Prüfwerkzeuge jeden Datensatz mit dem alten Bestand, und sie bleiben bei der Bibliothek. Freie
Software, die heute läuft: gemessen in der Testumgebung an einem Beispielbestand in Koha 26.05.

**Auf einen Blick:** ① Export des alten Systems lesen → ② Felder zuordnen, Datenfehler als Klärfälle entscheiden →
③ in Koha laden → ④ jeden Datensatz vergleichen → ⑤ Prüfbericht: alles angekommen.

**Für wen:** Bibliotheken, die zu Koha wechseln möchten, gerade kleinere, Schul- und Spezialbibliotheken ohne eigene
IT-Abteilung, und alle, die sie dabei begleiten. Heute liest koha-umzug Alephino-Exporte in MAB2, erprobt an einem nachgebildeten
Export; Vorlagen für weitere Systeme und die Formate MARC21, MARCXML und Tabellen sind die nächsten Schritte.

![Rundgang in sechs Szenen: Suche im Koha-Katalog, ein Titel mit Exemplar, Schlagwörtern und PDF, ein Zeitschriftenheft mit seiner Zeitschrift, laufende Ausleihen und Ausleihhistorie einer Benutzerin in der Dienstoberfläche, der Prüfbericht ohne Abweichung, der Prüfbericht nach 14 absichtlich eingebauten Fehlern](medien/rundgang.gif)

<sub>Rundgang: 79 Sekunden, sechs Szenen, ohne Ton; aufgenommen am 17.11.2026 in der Testumgebung des Messlaufs.
Bewegtes Bild oben: 4,2 MB.
[Video herunterladen (MP4, 3,3 MB)](https://github.com/panoherbe/koha-umzug/raw/main/medien/rundgang.mp4)
· Text des Rundgangs weiter unten.</sub>

<p align="center">
  <img src="medien/rundgang-2-titel.png" width="49%" alt="Ein Titel im Koha-Katalog: „Typobiografie : Arbeiten aus 60 Jahren / Jost Hochuli“; Verfasser und Schlagwörter verlinkt, unter Online-Ressourcen der Link „Volltext (PDF)“, unten das Exemplar mit Standort und Signatur">
  <img src="medien/rundgang-4-historie.png" width="49%" alt="Ausleihhistorie einer Benutzerin in der Dienstoberfläche: zurückgegebene Ausleihen mit Ausleih- und Rückgabedatum">
  <img src="medien/rundgang-5-pruefbericht.png" width="49%" alt="Prüfbericht nach dem Umzug: „Alles stimmt“, Mengenabgleich je Bestand mit den Zahlen aus Alephino, erwartet und in Koha">
  <img src="medien/rundgang-6-fehlerprobe.png" width="49%" alt="Prüfbericht nach der Fehlerprobe: rot markiert, unter anderem ein fehlendes Exemplar, ein fehlender Schlagwortsatz und ein fehlender Benutzer">
</p>

<sub>Bilder aus dem Rundgang vom 17.11.2026: ein Titel, die Ausleihhistorie, der Prüfbericht nach dem Umzug und nach
der Fehlerprobe.</sub>

## Warum es koha-umzug braucht

Kurz: Viele kleine Bibliotheken möchten wechseln; der Umzug selbst ist die Hürde, und genau dort setzt koha-umzug an.

- In einer Umfrage der Arbeitsgemeinschaften der Spezial- sowie der Kunst- und Museumsbibliotheken (ASpB, AKMB) unter
  136 Bibliotheken planen 41 Prozent einen Systemwechsel; über 90 Prozent sehen Bedarf an Hilfe gegen Qualitätsverlust
  bei Datenmigrationen ([Auswertung, 2026](https://aspb.de/files/2026/08/auswertung-umfrage-aspb-akmb-lokalsysteme.pdf)).
- 4.796 von 6.727 Öffentlichen Bibliotheken der Deutschen Bibliotheksstatistik 2024 arbeiten ohne hauptamtliches
  Personal ([DBS 2024](https://hbz.opus.hbz-nrw.de/files/556/PDFA_dbs_gesamt_engl_2024.pdf)).
- Selbst die KIT-Bibliothek brauchte für ihren Wechsel zu Koha vier Testmigrationen
  ([BiblioCon 2024](https://opus4.kobv.de/opus4-bib-info/files/19135/BiblioCon2024_Koha_KITBibliothek.pdf)).

## Was nach dem Umzug stimmt

Kurz: Die Tabelle folgt dem Ablauf eines Umzugs: lesen, umwandeln, laden, prüfen. Jede Zeile ist gebaut und gemessen.
Die Zahlen stammen aus dem Messlauf vom 17.11.2026 auf Commit `694725c`, gemessen in der Testumgebung
([Messprotokoll](nachweis/2026-11-17/PROTOKOLL.md), Rohdaten [`ergebnisse.json`](nachweis/2026-11-17/ergebnisse.json)).
Die Katalog- und Normdaten sind echt (Deutsche Nationalbibliothek, CC0); Exemplare, Benutzer, Ausleihen und
PDF-Dateien sind **simuliert**.

| Schritt | Worauf es ankommt | So macht es koha-umzug | Gemessen am 17.11.2026 |
|---|---|---|---|
| Lesen | Der ganze Bestand kommt an | liest den Alephino-Export: Titel und Normdaten im Format MAB2 (Zeilenformat „Aleph sequential“), Exemplare, Benutzer, Ausleihen und die Liste der PDF-Dateien als Tabellen | im Export: 1.621 Titel, 1.882 Exemplare, 2.787 Normsätze, 120 Benutzer, 91 laufende und 800 zurückgegebene Ausleihen, 40 PDF-Dateien; in Koha: 1.881 Exemplare, 90 laufende Ausleihen (je 1 nach Entscheidung der Bibliothek weggelassen), alles andere vollständig |
| Umwandeln | Umlaute bleiben Umlaute | schreibt MARC21 im Zeichensatz UTF-8 und setzt zerlegte Zeichen zusammen, damit die Suche „Müller“ auch findet | 4.272 Werte vereinheitlicht |
| Umwandeln | Jede alte Nummer bleibt auffindbar | die Alephino-Nummer steht im Datensatz; je Bestand eine Tabelle „alte Nummer → Koha-Nummer“ | 4 Tabellen, je Datensatz eine Zeile |
| Umwandeln | Personen und Schlagwörter sind verknüpft | Personen, Körperschaften und Schlagwörter werden Normsätze in Koha; jede Verknüpfung über die Nummer, nie über den Namen geraten | 6.388 Verknüpfungen, 0 ohne Normsatz |
| Umwandeln | Vom Heft zur Zeitschrift | jedes Heft und jeder Band zeigt „In: …“ mit einem Link zur Zeitschrift oder Reihe | 234 Hefte und Bände |
| Umwandeln | Nichts verschwindet still | jeder Datenfehler wird ein Klärfall, ebenso jedes Feld und Unterfeld ohne Regel (ihr Inhalt bleibt als Fußnote erhalten) und jeder Wert, für den es keine Zuordnung gibt. Geladen wird erst, wenn die Bibliothek entschieden hat ([Entscheidungen](beispiel/freigaben.json)) | 6 Arten von Datenfehlern eingebaut (simuliert), alle gemeldet |
| Laden | Mit den Werkzeugen von Koha und SQL | Normsätze, Titel und Exemplare mit `bulkmarcimport.pl`, Benutzer mit `import_patrons.pl`; laufende Ausleihen, Historie und die Einträge der PDF-Dateien per SQL; danach der Suchindex. Bricht ab, sobald ein Schritt scheitert | alles zusammen in 57,3 s |
| Laden | Ausleihen laufen weiter | Benutzer mit Ausweisnummer; laufende Ausleihen mit Frist und Zahl der Verlängerungen; die Historie mit Ausleih- und Rückgabedatum in der Dienstoberfläche | 120 Benutzer, 90 laufende Ausleihen, 800 in der Historie |
| Laden | PDF-Dateien hängen am Titel | als Koha-Upload, Byte für Byte unverändert; öffentlich oder nur für das Personal | 40 Dateien, 30 öffentlich, 10 intern; Prüfsummen gleich |
| Prüfen | Belegt, dass alles stimmt | vier Prüfwerkzeuge (unten), ein Bericht zum Lesen und einer für Programme | 0 Abweichungen, geprüft in 4,7 s |
| Prüfen | Die Prüfung ist selbst geprüft | Fehlerprobe: Koha absichtlich an 14 Stellen beschädigt, jede Stelle anders | 14 von 14 gefunden (simuliert), dazu 26 Folgemeldungen |
| Prüfen | Wiederholbar | automatische Tests ohne Koha; der ganze Messlauf mit einem Befehl | 33 von 33 Tests bestanden |

## Die vier Prüfwerkzeuge

Kurz: Sie vergleichen Koha mit dem Alephino-Export und listen jede Abweichung. Sie ändern nichts in Koha und brauchen
nur Python 3.10 oder neuer ohne Zusatzpakete. Das ist auf üblichen Debian- und Ubuntu-Servern installiert (Debian 12:
Python 3.11, Ubuntu 24.04: Python 3.12), sonst genügt `apt install python3`.

| Werkzeug | Was es prüft | Was es ausgibt |
|---|---|---|
| `mengen` | je Bestand: wie viele in Alephino, wie viele nach den Entscheidungen der Bibliothek zu erwarten sind, wie viele in Koha; dazu jede fehlende und jede zusätzliche Nummer | `mengen.json` |
| `beziehungen` | jedes Exemplar am richtigen Titel mit Barcode, Signatur, Standort und Ausleihstatus; jede Verknüpfung zum richtigen Normsatz; jedes Heft an seiner Zeitschrift; jeder Titel Zeichen für Zeichen (findet kaputte Umlaute) | `beziehungen.json` |
| `pdf` | jede PDF-Datei am Titel: öffentlich abrufbar und unverändert (SHA-256); interne Dateien ohne Anmeldung **nicht** abrufbar, mit Anmeldung schon | `pdf.json` |
| `ausleihen` | jede laufende Ausleihe: wer, welches Exemplar, seit wann, bis wann, wie oft verlängert; die Historie vollständig | `ausleihen.json` |

Alle vier schreiben zusammen `abweichungen.csv` und `bericht.html`
([Bericht nach dem Umzug](nachweis/2026-11-17/pruefbericht/bericht.html),
[Bericht nach der Fehlerprobe](nachweis/2026-11-17/fehlerprobe-bericht/bericht.html); auf GitHub über „Raw“ als Datei
laden und im Browser öffnen). Rückgabewert 0 heißt: keine Abweichung. Für Prüfungen im laufenden Betrieb, etwa nach einem Koha-Update, kommen
die Abgleiche als gespeicherte SQL-Berichte (nächste Schritte). In der Testumgebung lesen sie Koha über den Container (`--container`), auf einem Koha-Server
über `--sql "sudo koha-mysql INSTANZ"`, nur lesend; dort sind sie noch nicht gemessen.

Gelernt beim Messen: Koha antwortet auf den Abruf einer fehlenden Datei mit HTTP 200 und einer Hinweisseite. Das
Werkzeug prüft deshalb den Inhalt (beginnt er mit `%PDF`, stimmt die Prüfsumme), nicht nur die Antwort des Servers.

## In zwei Minuten selbst prüfen

Kurz: Umwandlung und Tests laufen ohne Koha; für den ganzen Weg startet ein Skript Koha 26.05 auf Ihrem Rechner.

Ohne Koha (Python 3.10 oder neuer):

```bash
git clone https://github.com/panoherbe/koha-umzug.git && cd koha-umzug
pip install pymarc pytest
python daten/nachbilden.py                     # baut den Beispiel-Export (wenige Sekunden)
python -m umzug umwandeln beispiel/export beispiel/koha --freigaben beispiel/freigaben.json
python -m pytest -q                             # 37 Tests
```

`beispiel/koha/klaerfaelle.csv` zeigt danach jeden Datenfehler mit der Entscheidung aus `freigaben.json`. Ohne
`--freigaben` hält die Umwandlung an und listet, was zu entscheiden ist.

Mit Koha 26.05 (Docker; Platz: Koha-Image 5,2 GB, Koha-Quellcode 1,0 GB; Arbeitsspeicher mit geladenem
Beispiel ≈ 2,1 GB. Gemessen am 17.11.2026 ([`testumgebung.txt`](nachweis/2026-11-17/testumgebung.txt)): Start in
89 Sekunden, als Image und Quellcode schon geladen waren; beim ersten Mal kommen die Downloads dazu):

```bash
koha/testumgebung.sh ~/koha-test                # offizieller Entwicklungs-Container der Koha-Gemeinschaft
python -m umzug laden beispiel/koha beispiel/export --container kohaumzug-koha-1 --leeren --sprache de-DE
python -m umzug pruefen alle beispiel/export beispiel/koha --container kohaumzug-koha-1 \
  --dienst-benutzer koha --dienst-passwort koha
```

Dann den Katalog unter http://127.0.0.1:18080 ansehen, die Dienstoberfläche unter http://127.0.0.1:18081 (Konto
`koha`, Passwort `koha`, nur in dieser Testumgebung). `--leeren` löscht vorher alle Titel, Exemplare, Normsätze,
Benutzer (außer dem Konto `koha`), laufenden Ausleihen und die Ausleihhistorie, Vormerkungen, Gebühren, Statistik,
wartende Benachrichtigungen und die Einträge hochgeladener Dateien. Das Laden läuft deshalb nur mit `--container`
und nimmt kein `--sql` an. Den ganzen Messlauf wiederholen: `nachweis/messlauf.sh kohaumzug-koha-1`.

## Was Sie heute schon prüfen können

Kurz: Feldzuordnung, Klärfälle, Messung und Prüfbericht liegen offen.

- **Die Feldzuordnung** steht als Tabelle in [`zuordnung/FELDZUORDNUNG.md`](zuordnung/FELDZUORDNUNG.md): je MAB2-Feld
  das MARC21-Feld und seine Bedeutung, dazu, was mit Feldern ohne Regel geschieht. Ein Test hält sie gleich mit dem
  Code.
- **Der Umgang mit Datenfehlern** steht in [`beispiel/freigaben.json`](beispiel/freigaben.json) und im
  [Messprotokoll](nachweis/2026-11-17/PROTOKOLL.md): doppelter Barcode, Exemplar ohne Titel, Ausleihe ohne Benutzer,
  Verknüpfung ins Leere, Feld ohne Zuordnung, unbekanntes Zugangsdatum. Unterfelder und Werte ohne Zuordnung prüfen
  die Tests.
- **ISBN und mehrbändige Werke** (seit 27.11.2026, [`umzug/isbn.py`](umzug/isbn.py)): Ein ISBN-Feld, in dem nur das
  Wort „ISBN“ steht, braucht keine Entscheidung; fehlt vorne die 9 von 978 und bestätigt die Prüfziffer die
  Ergänzung, wird sie ergänzt; eine ISSN im ISBN-Feld kommt ins ISSN-Feld. Das zählt `protokoll.json` unter
  „automatisch“. Vertippte und unvollständige ISBN bleiben Klärfälle und stehen als ungültige ISBN im Datensatz. Ein
  Band ohne eigenen Titel bekommt den Titel seines Werks. Der Beispiel-Umzug ergibt damit dieselben Dateien wie vorher.
- **Die Messung ist wiederholbar:** ein Befehl lädt, prüft, beschädigt Koha absichtlich, prüft wieder, lädt neu und
  schreibt das Protokoll; jede Zahl darin kommt aus den Dateien des Laufs.

## Text des Rundgangs

<details>
<summary>Die Sätze im Video (aufklappen)</summary>

Sechs Szenen. Oben rechts steht die ganze Zeit: github.com/panoherbe/koha-umzug. Die beiden Ausleihtabellen zeigen
im Video weniger Spalten als Koha von sich aus (Tabelleneinstellungen der Dienstoberfläche), damit sie ins Bild passen.

| ab | Satz (klein darunter) | Was man sieht |
|---|---|---|
| 0:00 | Der Umzug nach Koha, Satz für Satz geprüft. *(Titel, Exemplare, Normdaten, Ausleihen und PDF-Dateien. Die Prüfwerkzeuge bleiben bei der Bibliothek.)* | Titelkarte |
| 0:06 | Nach dem Umzug: der Katalog in Koha 26.05. *(Katalogdaten der Deutschen Nationalbibliothek; Exemplare und Benutzer simuliert.)* | der Katalog; Suche nach „St. Gallen“, zwei Treffer, „Typobiografie“ wird geöffnet |
| 0:18 | Jeder Titel mit Exemplaren, Normdaten und PDF. *(Signatur und Standort wie vorher; die PDF hängt am Titel.)* | der Titel mit Verfasser und Herausgebern (Rollen auf Deutsch), Schlagwörtern und dem Exemplar mit Standort und Signatur; „Volltext (PDF)“ hervorgehoben |
| 0:27 | Hefte bleiben mit ihrer Zeitschrift verbunden. *(Ein Klick führt vom Heft zur Zeitschrift.)* | das Heft „Dem Licht gewidmet“ mit „In: Monumente“, ein Klick, die Zeitschrift |
| 0:34 | Wer was ausgeliehen hat, und bis wann. *(Die laufenden Ausleihen einer Benutzerin in der Dienstoberfläche.)* | Dienstoberfläche: zwei laufende Ausleihen einer Benutzerin mit Fälligkeit, Standort und Verlängerungen |
| 0:40 | Auch die Historie kommt mit. *(Zurückgegebene Ausleihen mit Ausleih- und Rückgabedatum.)* | ihre Ausleihhistorie: die zwei laufenden und neun zurückgegebene Ausleihen mit Rückgabedatum |
| 0:45 | Das Prüfwerkzeug vergleicht jeden Datensatz. *(Mengen, Verknüpfungen, PDF-Dateien und Ausleihen, gegen den Alephino-Export.)* | Prüfbericht nach dem Umzug: „Alles stimmt“ |
| 0:52 | Zur Probe 14 Fehler eingebaut: alle gefunden. *(Simuliert: absichtlich beschädigt, um die Werkzeuge selbst zu prüfen.)* | Prüfbericht nach der Fehlerprobe, rot markiert |
| 1:02 | Gemessen am 17.11.2026 | 1.621 Titel; 57,3 s Laden mit Koha-Werkzeugen und SQL; 0 Abweichungen, geprüft in 4,7 s; 14 von 14 Fehlern gefunden (simuliert) |
| 1:10 | Selbst prüfen | github.com/panoherbe/koha-umzug; Lizenzen und Herkunft der Daten; Panagiotis Herbe |

</details>

## Stand heute und nächste Schritte

Kurz: ein laufender, gemessener Anfang mit Beispieldaten. Die nächsten Schritte bringen ihn zu echten Bibliotheken.

**Heute:**

- **Beispieldaten:** Der Alephino-Export ist nachgebildet, aus echten Katalogdaten der Deutschen Nationalbibliothek,
  umgesetzt in MAB2 im Zeilenformat von Alephino; Exemplare, Benutzer, Ausleihen und PDF-Dateien sind simuliert. Ein
  echter Export bringt eigene Felder, Codes und Sonderfälle mit; dafür wird die Feldzuordnung angepasst.
- **Bestand:** gemessen mit 1.621 Titeln. Die Prüfwerkzeuge lesen je Tabelle mit einer Abfrage; Messungen an großen
  Beständen folgen mit den Probeumzügen.
- **Laden:** eingerichtet für die Testumgebung; die Prüfwerkzeuge sind für Koha-Server vorbereitet (`--sql`), dort
  aber noch nicht erprobt. Auf einem Server liegen die Koha-Werkzeuge an anderer Stelle, und Arbeits- und Upload-Ordner brauchen
  andere Rechte.
- **Ausleihen** kommen per SQL in Koha, ebenso die Einträge der PDF-Dateien; so bleiben Ausleih- und Rückgabedatum aus
  Alephino erhalten. Zurückbuchen und Verlängern eines übernommenen Exemplars deckt noch kein automatischer Test ab.
- **Passwörter** kommen nicht mit; Benutzerinnen und Benutzer vergeben sie über „Passwort vergessen“ neu.
- **Ausleihhistorie und alle Benutzerkonten** wandern heute immer mit.
- **Suchindex:** gemessen mit Zebra, dem Standard der Testumgebung.

**Als Nächstes:**

1. Die Feldzuordnung als bearbeitbare Tabelle statt Code, mit Vorlagen je Altsystem und Beispielen aus den eigenen
   Daten.
2. Weitere Quellen: MARC21- und MARCXML-Exporte anderer Systeme; Exemplare aus Tabellen, wo ein MARC-Export sie nicht
   enthält.
3. Ein Umzugsassistent im Browser, der bei der Bibliothek läuft: Export ablegen, Klärfälle entscheiden, Probelauf,
   Prüfbericht; ohne Kommandozeile.
4. Die wichtigsten Abgleiche als gespeicherte SQL-Berichte in der Dienstoberfläche von Koha, ohne Installation und für
   jedes spätere Update; Laden auf normalen Koha-Servern mit Elasticsearch.
5. Datensparsam: Ausleihhistorie und alte Benutzerkonten wandern nur mit, wenn die Bibliothek es ausdrücklich
   entscheidet.
6. Probeumzüge mit den echten Exporten von drei Bibliotheken, auf deren eigenen Rechnern; zu mir kommen nur
   Prüfberichte ohne Personendaten.
7. Version 1.0 mit Messbericht aus den Probeumzügen.

## Mitmachen und Kontakt

Probieren Sie den Weg mit dem Beispielbestand aus. Bibliotheken, die einen Probeumzug machen möchten, melden sich gern,
ebenso alle mit Rückmeldungen, Fragen oder Feldern ihres Exports, die hier noch fehlen: als Issue auf GitHub oder über
[panoherbe.com](https://www.panoherbe.com). Bitte keine echten Benutzerdaten hochladen.

Panagiotis Herbe

---

## Für die Technik

Kurz: Python 3, eine Bibliothek für MARC (pymarc) und die Werkzeuge von Koha, alles freie Software.

| | |
|---|---|
| Umwandlung | `umzug/umwandeln.py`, `umzug/mab2marc.py`: Python 3.10+, pymarc; schreibt MARC21 (UTF-8, NFC), CSV und JSON; Werttabellen für Standort, Medientyp, Status und Benutzergruppe in `umzug/werte.py` |
| Laden | `umzug/laden.py`, nur Testumgebung (`--container`): `bulkmarcimport.pl` und `import_patrons.pl` über `koha-shell`; laufende Ausleihen, Historie und die Einträge der PDF-Uploads per SQL über `koha-mysql`, die PDF-Dateien selbst in den Upload-Ordner; verweigert das Laden bei offenen Klärfällen; bricht ab, wenn ein Werkzeug, der Suchindex oder der Neustart von Plack scheitert |
| Prüfen | `umzug/pruefen/`: nur Python-Standardbibliothek; liest Koha über `koha-mysql` (nur lesen) und über HTTP; Testumgebung `--container`, Koha-Server `--sql` (dort nicht gemessen) |
| Fehlerprobe | `umzug/fehlerprobe.py`: nur für Testumgebungen, ändert Daten |
| Testumgebung | `koha/testumgebung.sh`: koha-testing-docker der Koha-Gemeinschaft (Commit `ef7f1f9`), Koha `v26.05.05-1`, Ports nur auf 127.0.0.1. Die Images `koha/koha-testing:26.05` und `mariadb:10.11` sind Tags, die sich ändern können; das Image des Messlaufs steht mit Digest in `nachweis/2026-11-17/testumgebung.txt` |
| Tests | `python -m pytest -q`; GitHub Actions bei jedem Push mit Python 3.10 und 3.12 |
| Daten | `daten/dnb/`: Titel- und Normdaten der Deutschen Nationalbibliothek, geholt mit `daten/holen.py`; `daten/nachbilden.py` baut daraus den Export, gleiche Eingabe ergibt gleiche Bytes |

Befehle:

```text
python -m umzug umwandeln <export> <ziel> --freigaben <datei>
python -m umzug laden <ziel> <export> --container NAME [--leeren] [--sprache de-DE]          # nur Testumgebung
python -m umzug pruefen <mengen|beziehungen|pdf|ausleihen|alle> <export> <ziel> \
  (--container NAME | --sql "sudo koha-mysql INSTANZ") [--bericht ORDNER]                    # Server: nicht gemessen
python -m umzug zuordnung
```

## Daten und Lizenzen

- **Code:** [GNU Affero General Public License 3.0](LICENSE) (AGPL-3.0-only), seit dem ersten Commit.
- **Katalog- und Normdaten** in `daten/dnb/`: Deutsche Nationalbibliothek, [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).
  Auswahl über Schlagwörter zu Kunstgeschichte, Architektur, Denkmalpflege, Malerei, Typografie, Gartenkunst,
  Fotografie und Design; von den Normsätzen nur Namen, Namensformen, Lebensdaten und Kennungen.
- **Simuliert:** Alephino-Nummern und die MAB2-Form der Datensätze, Exemplare, Benutzer (erfundene Namen, Adressen
  @example.org), Ausleihen, PDF-Dateien und die eingebauten Datenfehler.
- **Koha:** Koha-Gemeinschaft, GPL-3.0-or-later. **koha-testing-docker:** Koha-Gemeinschaft, GPL-3.0. Beide werden
  von `koha/testumgebung.sh` geholt und sind nicht Teil dieses Repositorys.
