# Mitmachen bei koha-umzug

Kurz: Bibliotheken, Koha-Kundige und alle mit Rückmeldungen sind willkommen. Bitte nie echte Benutzerdaten.

## Etwas melden

- **Fehler oder Wunsch:** ein [Issue](https://github.com/panoherbe/koha-umzug/issues) mit drei Sätzen: Was haben Sie
  gemacht, was ist passiert, was hätten Sie erwartet? Die Version (`pyproject.toml` oder die
  [Releases](https://github.com/panoherbe/koha-umzug/releases)) und die Koha-Version helfen.
- **Felder aus Ihrem Export:** Welche Felder oder Codes Ihres Programms fehlen in der
  [Feldzuordnung](zuordnung/FELDZUORDNUNG.md)? Ein paar Zeilen mit erfundenen Werten genügen, nie echte Benutzer- oder
  Ausleihdaten. Was in Ihrem Export steckt, zeigt vorab die
  [Probierseite](https://www.panoherbe.com/projekte/koha-umzug/ausprobieren), ohne die Datei zu verschicken.
- **Probeumzug:** Bibliotheken, die einen Probeumzug machen möchten, schreiben an kontakt@panoherbe.com.
- **Sicherheitslücke:** bitte nicht öffentlich als Issue, sondern per Mail an kontakt@panoherbe.com.

## Selbst etwas ändern

- Tests ohne Koha (Python 3.10 oder neuer):

  ```bash
  pip install pymarc pytest
  python -m pytest -q
  ```

- Ein Pull Request ändert eine Sache und die Tests laufen grün (GitHub Actions prüft jeden Pull Request mit Python 3.10
  und 3.12). Ändert er die Zuordnung, wird [`zuordnung/FELDZUORDNUNG.md`](zuordnung/FELDZUORDNUNG.md) mit
  `python -m umzug zuordnung` neu geschrieben; ein Test hält beides gleich.
- Die Prüfwerkzeuge (`umzug/pruefen/`) bleiben bei der Python-Standardbibliothek und ändern nichts in Koha.

## Was geplant ist

Die nächsten Schritte stehen in der README unter [Fahrplan 2027](README.md#fahrplan-2027) und als Issues mit dem Label
[„Fahrplan 2027“](https://github.com/panoherbe/koha-umzug/issues?q=label%3A%22Fahrplan+2027%22). Hinweise dort sind
willkommen.

## Lizenz

Beiträge stehen unter derselben Lizenz wie das Projekt: GNU AGPL-3.0-only ([`LICENSE`](LICENSE)).
