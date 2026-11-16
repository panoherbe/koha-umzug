# Feldzuordnung Alephino (MAB2) → Koha (MARC21)

Erzeugt aus `umzug/mab2marc.py` (`python -m umzug zuordnung`); Code und Tabelle können nicht auseinanderlaufen. Jede Zeile ist eine Regel des Konverters.

## Titeldaten

| MAB2 | Unterfeld | MARC21 | Bedeutung |
|---|---|---|---|
| 001 |  | 001 / 035 | Alephino-Systemnummer: 001 unverändert, 035 „(ALEPHINO)nnn“ |
| 002 | a | 008/00-05 | Datum der Ersterfassung |
| 010 | a | 773 0_ $t $w | übergeordneter Datensatz: Titel und Systemnummer; Koha verlinkt über 001 |
| 089 | a | 245 $n, 773 $g | Bandangabe des untergeordneten Titels |
| 025 | a | 016 7_ $a $2 DE-101 | Nummer der Deutschen Nationalbibliothek, falls vorhanden |
| 037 | b | 041 $a, 008/35-37 | Sprache |
| 100, 104 … 196 | p, 9, 4 | 100 1_ / 700 1_ ($a, $e, $0, $4) | Personen; erste Verfasserin oder erster Verfasser in 100; $e = Rolle auf Deutsch (Tabelle unten) |
| 200, 204 … 296 | k, 9, 4 | 110 2_ / 710 2_ ($a, $e, $0, $4) | Körperschaften; $e wie bei Personen |
| 331 | a | 245 $a, 2. Indikator | Hauptsachtitel; „¬…¬“ am Anfang wird zur Zahl der Nichtsortierzeichen, an anderer Stelle (auch in Namen) entfernt |
| 902 | s / g / p / k, 9 | 650 / 651 / 600 / 610 _7 $2 gnd | Schlagwörter (Sach, Geografikum, Person, Körperschaft) |
| PDF | pdf.csv | 856 42 $u $y $q | titelverknüpfte PDF-Datei, über Koha-Upload mit Zugriffsrecht |
| Exemplar | exemplare.csv | 952 | Exemplar: Barcode $p, Signatur $o, Standort $c, Typ $y, Status $7, Zugang $d |
| 335 | a | 245 $b | Zusätze zum Hauptsachtitel |
| 359 | a | 245 $c | Verantwortlichkeitsangabe |
| 403 | a | 250 $a | Ausgabebezeichnung |
| 410 | a | 264 $a | Verlagsort |
| 412 | a | 264 $b | Verlag |
| 425 | a | 264 $c | Erscheinungsjahr |
| 433 | a | 300 $a | Umfang |
| 451 | a | 490 $a | Gesamttitel |
| 455 | a | 490 $v | Bandangabe zum Gesamttitel |
| 540 | a | 020 $a | ISBN |
| 542 | a | 022 $a | ISSN |
| 655 | u | 856 $u | Elektronische Adresse (Web) |

Satzzeichen nach ISBD schreibt der Konverter in den Datensatz (Leader/18 = „i“), weil Koha die Unterfelder so anzeigt, wie sie sind: 245 „Titel : Zusatz / Verantwortlich“ („Titel = Paralleltitel“, „Titel. Band“), 264 „Ort : Verlag, Jahr“, 490 „Reihe ; Band“.

### Rollen ($4 → $e)

| $4 | $e |
|---|---|
| aut | Verfasser |
| edt | Herausgeber |
| isb | Herausgebendes Organ |
| ctb | Mitwirkender |
| pbl | Verlag |
| trl | Übersetzer |
| ill | Illustrator |
| pht | Fotograf |
| ctg | Kartograf |
| aui | Verfasser einer Einleitung |
| wpr | Verfasser eines Vorworts |
| com | Zusammenstellender |
| cre | Geistiger Schöpfer |
| art | Künstler |
| dsr | Designer |
| rev | Rezensent |
| hnr | Gefeierte Person |
| dgs | Akademischer Betreuer |
| dgg | Grad-verleihende Institution |
| oth | Sonstige |

Ein Code ohne Eintrag bleibt nur als $4 stehen.

### Was keine Regel hat

Ein Feld ohne Regel, ein Unterfeld ohne Regel und ein zweites Vorkommen, wo die Regel nur das erste liest, gehen nicht verloren: Der Inhalt kommt als Fußnote 500 „[MAB 078] …“ (Normsätze: Anmerkung 667) in den Datensatz, und je Feld entsteht ein Klärfall („Feld ohne Zuordnung“, „Unterfeld ohne Zuordnung“, „Normsatzfeld ohne Zuordnung“). Ohne Regel in `freigaben.json` hält die Umwandlung an.

## Normdaten

| Alephino-Stammsatz | MAB-Feld | MARC21-Normsatz | Bedeutung |
|---|---|---|---|
| Person | 800 $p, $d | 100 1_ $a, $d | Ansetzung |
| Person | 830 $p | 400 1_ $a | Verweisung |
| Körperschaft | 800 $k | 110 2_ $a | Ansetzung |
| Körperschaft | 830 $k | 410 2_ $a | Verweisung |
| Schlagwort | 800 $s / $g | 150 / 151 $a | Sachschlagwort / Geografikum |
| Schlagwort | 830 $s / $g | 450 / 451 $a | Verweisung |
| alle | 001 | 035 „(ALEPHINO-PER\|KOE\|SW)nnn“ | Alephino-Nummer bleibt erhalten |
| alle | 024 $a | 024 7_ $a $2 gnd | GND-Nummer |

## Benutzer und Ausleihen

| Alephino (CSV) | Koha | Bedeutung |
|---|---|---|
| benutzer_id | borrowers.sort1 | Alephino-Nummer bleibt erhalten |
| ausweis | cardnumber | Ausweisnummer, Schlüssel für die Ausleihe |
| nachname, vorname, email | surname, firstname, email | |
| gruppe | categorycode | Benutzergruppe (Tabelle in `umzug/werte.py`) |
| gueltig_bis | dateexpiry | |
| ausleihen.csv | issues (issuedate, date_due, renewals_count), items.onloan | laufende Ausleihen |
| ausleihhistorie.csv | old_issues (issuedate, returndate) | Historie, in der Dienstoberfläche sichtbar |

Exemplarwerte (Standort, Medientyp, Status) und Benutzergruppen übersetzen die Tabellen in `umzug/werte.py`; ein Wert, der dort fehlt, wird ein Klärfall „Wert ohne Zuordnung“.

Passwörter werden nicht übertragen: Benutzerinnen und Benutzer setzen ihr Passwort über „Passwort vergessen“ im OPAC neu.
