"""Load the converted files into Koha with Koha's own tools, then write the identifier mapping tables.

    python -m umzug laden <koha-dateien> <export> --container kohaumzug-koha-1 [--leeren] [--sprache de-DE]

Set up for the test environment only (koha-testing-docker): it needs --container and refuses --sql/--shell. Koha's
tools are called from the source folder of that container (KOHA_DIR); on a Koha server installed from packages
they live elsewhere and the work folder, upload folder and index rebuild need other rights. The check tools
(umzug.pruefen) can read a server with --sql; the loader cannot yet.

Refuses to load when the conversion stopped (open Klärfälle in protokoll.json): nothing is loaded that the library
has not decided on. --leeren removes, before loading: all titles, items, authority records, patrons (except the
staff account „koha“ of the test environment), current loans and loan history, holds, fines, statistics, queued
notices and the entries of uploaded files. Every command that fails stops the loader (non-zero exit status).

Order (each step is logged with its counts):

1. --leeren: remove the test environment's sample data (list above)
2. basic settings for the migration: branch, item types, locations, patron categories, upload category, system
   preferences (Koha links 773 $w via 001; no automatic re-linking of authorities)
3. authorities with bulkmarcimport.pl, then read back Koha's authority numbers (authid) by the Alephino number in 035
4. titles: each link „$0 (ALEPHINO-…)nnn“ becomes Koha's „$9 authid“, exact, never guessed from the name; titles and
   their items with bulkmarcimport.pl
5. patrons with import_patrons.pl (match point: card number)
6. current loans and loan history (SQL: issues / old_issues, items.onloan)
7. PDF files as permanent Koha uploads, public or staff-only as released
8. full search index rebuild, caches cleared
9. mapping tables Alephino number → Koha number for titles, items, authorities, patrons (zuordnung-*.csv)
"""
from __future__ import annotations

import csv
import json
import tempfile
import time
from pathlib import Path

from pymarc import MARCReader, MARCWriter

from .koha import Koha, sql_text
from .werte import GRUPPEN, GRUPPENNAMEN, STANDORTE, TYPEN, TYPNAMEN, ZWEIG

KOHA_DIR = "/kohadevbox/koha"           # Koha source in the test container (koha-testing-docker), measured there
UPLOAD_KATEGORIE = "PDF"
GELOESCHT = ("alle Titel, Exemplare, Normsätze, Benutzer (außer dem Konto „koha“), laufenden Ausleihen und die "
             "Ausleihhistorie, Vormerkungen, Gebühren, Statistik, wartende Benachrichtigungen und die Einträge "
             "hochgeladener Dateien")
NORM_PRAEFIX = ("(ALEPHINO-PER)", "(ALEPHINO-KOE)", "(ALEPHINO-SW)")


def log(schritt: str, **werte) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {schritt}" + ("  " + json.dumps(werte, ensure_ascii=False) if werte else ""),
          flush=True)


def leeren(k: Koha) -> None:
    k.sql("""SET FOREIGN_KEY_CHECKS=0;
DELETE FROM issues; DELETE FROM old_issues; DELETE FROM reserves; DELETE FROM old_reserves;
DELETE FROM items; DELETE FROM deleteditems; DELETE FROM biblio_metadata; DELETE FROM biblioitems; DELETE FROM biblio;
DELETE FROM deletedbiblio_metadata; DELETE FROM deletedbiblioitems; DELETE FROM deletedbiblio;
DELETE FROM auth_header; DELETE FROM deletedborrowers; DELETE FROM uploaded_files; DELETE FROM zebraqueue;
DELETE FROM statistics; DELETE FROM accountlines; DELETE FROM message_queue;
DELETE FROM borrowers WHERE userid IS NULL OR userid <> 'koha';
UPDATE borrowers SET branchcode = 'BIB' WHERE userid = 'koha';
SET FOREIGN_KEY_CHECKS=1;""")


def grundeinstellungen(k: Koha, opac_url: str, dienst_url: str, sprache: str | None) -> None:
    zeilen = [f"INSERT IGNORE INTO branches (branchcode, branchname) VALUES ('{ZWEIG}', 'Bibliothek');"]
    for code in sorted(set(TYPEN.values())):
        zeilen.append(f"INSERT INTO itemtypes (itemtype, description) VALUES ('{code}', '{TYPNAMEN[code]}') "
                      f"ON DUPLICATE KEY UPDATE description = '{TYPNAMEN[code]}';")
    for name, code in STANDORTE.items():
        zeilen.append(f"INSERT IGNORE INTO authorised_values (category, authorised_value, lib, lib_opac) "
                      f"VALUES ('LOC', '{code}', '{name}', '{name}');")
    zeilen.append(f"INSERT IGNORE INTO authorised_values (category, authorised_value, lib, lib_opac) "
                  f"VALUES ('UPLOAD', '{UPLOAD_KATEGORIE}', 'Volltexte (PDF)', 'Volltexte (PDF)');")
    for code in sorted(set(GRUPPEN.values())):
        zeilen.append(f"INSERT IGNORE INTO categories (categorycode, description, enrolmentperiod, category_type, "
                      f"default_privacy) VALUES ('{code}', '{GRUPPENNAMEN[code]}', 24, 'A', 'default');")
    prefs = {"UseControlNumber": "1", "AutoLinkBiblios": "0", "CatalogModuleRelink": "0",
             "BiblioAddsAuthorities": "0", "AutoCreateAuthorities": "0", "OPACBaseURL": opac_url,
             "staffClientBaseURL": dienst_url, "dateformat": "dmydot", "CalendarFirstDayOfWeek": "1"}
    if sprache:
        prefs |= {"OPACLanguages": sprache, "StaffInterfaceLanguages": sprache, "language": sprache,
                  "opaclanguagesdisplay": "0"}
    for var, val in prefs.items():
        zeilen.append(f"UPDATE systempreferences SET value = {sql_text(val)} WHERE variable = '{var}';")
    # loan rules of the sample for everybody: 28 days, three renewals of 28 days (a library sets its own)
    for regel, wert in {"issuelength": "28", "renewalperiod": "28", "renewalsallowed": "3", "maxissueqty": "50"}.items():
        zeilen.append(f"UPDATE circulation_rules SET rule_value = '{wert}' WHERE branchcode IS NULL AND "
                      f"categorycode IS NULL AND itemtype IS NULL AND rule_name = '{regel}';")
    k.sql("\n".join(zeilen))


def arbeitsordner(k: Koha) -> str:
    """A folder inside the Koha environment for the import files (not /tmp: a tmpfs in the test container)."""
    ordner = f"/var/lib/koha/{k.instanz}/migration"
    k.shell(f"mkdir -p {ordner} && chmod 755 {ordner}", als_root=True)
    return ordner


def hinein(k: Koha, datei: Path) -> str:
    ziel = f"{arbeitsordner(k)}/{datei.name}"
    k.kopieren(datei, ziel)
    k.shell(f"chmod a+r {ziel}", als_root=True)
    return ziel


def letzte(text: str, n: int) -> str:
    """The last n lines of a tool's output (no pipe to tail: its exit status would hide the tool's)."""
    return "\n".join(text.strip().splitlines()[-n:])


def bulkmarcimport(k: Koha, datei: Path, art: str) -> str:
    ziel = hinein(k, datei)
    flag = "-a" if art == "auth" else "-b"
    return letzte(k.shell(f"cd {KOHA_DIR} && perl misc/migration_tools/bulkmarcimport.pl {flag} -c MARC21 "
                          f"-file {ziel} -v 0 2>&1"), 5)


def authid_karte(k: Koha) -> dict[str, str]:
    """„(ALEPHINO-PER)000000017“ -> Koha authid."""
    karte = {}
    for authid, wert in k.sql("SELECT authid, ExtractValue(marcxml, '//datafield[@tag=\"035\"]/subfield[@code=\"a\"]') "
                              "FROM auth_header"):
        for v in (wert or "").split():
            if v.startswith(NORM_PRAEFIX):
                karte[v] = authid
    return karte


def mit_authid(quelle: Path, ziel: Path, karte: dict[str, str]) -> tuple[int, int]:
    gesetzt = fehlt = 0
    with open(quelle, "rb") as fh, open(ziel, "wb") as out:
        w = MARCWriter(out)
        for rec in MARCReader(fh, to_unicode=True, force_utf8=True):
            for f in rec.get_fields("100", "110", "600", "610", "650", "651", "700", "710"):
                for nr in [v for v in f.get_subfields("0") if v.startswith(NORM_PRAEFIX)]:
                    f.delete_subfield("0")
                    if nr in karte:
                        f.add_subfield("9", karte[nr])
                        gesetzt += 1
                    else:
                        fehlt += 1
            w.write(rec)
    return gesetzt, fehlt


def ausleihen_laden(k: Koha, dateien: Path) -> tuple[int, int]:
    laufend = json.loads((dateien / "ausleihen.json").read_text())
    hist = json.loads((dateien / "historie.json").read_text())
    s = ["CREATE TEMPORARY TABLE mig_ausleihe (barcode VARCHAR(40), cardnumber VARCHAR(40), ausleihe DATE, "
         "faellig DATE, rueckgabe DATE, verl INT, nr INT) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"]
    werte = [f"({sql_text(a['barcode'])},{sql_text(a['cardnumber'])},{sql_text(a['ausleihe'])},"
             f"{sql_text(a['faellig'])},NULL,{a['verlaengerungen']},{i})" for i, a in enumerate(laufend)]
    werte += [f"({sql_text(h['barcode'])},{sql_text(h['cardnumber'])},{sql_text(h['ausleihe'])},NULL,"
              f"{sql_text(h['rueckgabe'])},0,{100000 + i})" for i, h in enumerate(hist)]
    for i in range(0, len(werte), 500):
        s.append("INSERT INTO mig_ausleihe VALUES " + ",".join(werte[i:i + 500]) + ";")
    # timestamp = the last change in Alephino (checkout or return), not the moment of the migration: Koha shows it
    # as „Datum“ in the loan history
    s.append(f"""INSERT INTO issues (borrowernumber, itemnumber, date_due, branchcode, issuedate, renewals_count, timestamp)
SELECT b.borrowernumber, it.itemnumber, CONCAT(m.faellig, ' 23:59:00'), '{ZWEIG}', CONCAT(m.ausleihe, ' 10:00:00'), m.verl,
       CONCAT(m.ausleihe, ' 10:00:00')
FROM mig_ausleihe m JOIN items it ON it.barcode = m.barcode JOIN borrowers b ON b.cardnumber = m.cardnumber
WHERE m.rueckgabe IS NULL ORDER BY m.nr;
UPDATE items it JOIN issues i ON i.itemnumber = it.itemnumber SET it.onloan = DATE(i.date_due);
INSERT INTO old_issues (issue_id, borrowernumber, itemnumber, date_due, branchcode, returndate, issuedate, timestamp)
SELECT 5000000 + m.nr, b.borrowernumber, it.itemnumber, CONCAT(m.rueckgabe, ' 23:59:00'), '{ZWEIG}',
       CONCAT(m.rueckgabe, ' 12:00:00'), CONCAT(m.ausleihe, ' 10:00:00'), CONCAT(m.rueckgabe, ' 12:00:00')
FROM mig_ausleihe m JOIN items it ON it.barcode = m.barcode JOIN borrowers b ON b.cardnumber = m.cardnumber
WHERE m.rueckgabe IS NOT NULL ORDER BY m.nr;
UPDATE items it SET it.issues = (SELECT COUNT(*) FROM old_issues o WHERE o.itemnumber = it.itemnumber)
                              + (SELECT COUNT(*) FROM issues i WHERE i.itemnumber = it.itemnumber);
SELECT (SELECT COUNT(*) FROM issues), (SELECT COUNT(*) FROM old_issues);""")
    z = k.sql("\n".join(s))
    return int(z[-1][0] or 0), int(z[-1][1] or 0)


def pdf_laden(k: Koha, export: Path, dateien: Path, upload_pfad: str) -> int:
    zeilen = json.loads((dateien / "pdf.json").read_text())
    admin = k.wert("SELECT borrowernumber FROM borrowers WHERE userid = 'koha'") or "NULL"
    with tempfile.TemporaryDirectory() as tmp:
        ordner = Path(tmp) / UPLOAD_KATEGORIE
        ordner.mkdir()
        for z in zeilen:
            (ordner / f"{z['hash']}_{z['datei']}").write_bytes((export / "pdf" / z["datei"]).read_bytes())
        k.shell(f"mkdir -p {upload_pfad}", als_root=True)
        k.kopieren(ordner, f"{upload_pfad}/")
    k.shell(f"chown -R {k.instanz}-koha:{k.instanz}-koha {upload_pfad}", als_root=True)
    werte = ",".join(f"({z['upload_id']},{sql_text(z['hash'])},{sql_text(z['datei'])},'{UPLOAD_KATEGORIE}',"
                     f"{z['groesse']},'{UPLOAD_KATEGORIE}',{admin},{1 if z['oeffentlich'] else 0},1)" for z in zeilen)
    k.sql("INSERT INTO uploaded_files (id, hashvalue, filename, dir, filesize, uploadcategorycode, owner, public, "
          f"permanent) VALUES {werte};")
    return len(zeilen)


def zuordnungen(k: Koha, ziel: Path) -> dict[str, int]:
    tabellen = {
        "titel": "SELECT ExtractValue(metadata, '//controlfield[@tag=\"001\"]'), biblionumber FROM biblio_metadata",
        "exemplare": "SELECT SUBSTRING_INDEX(itemnotes_nonpublic, ')', -1), itemnumber, barcode FROM items",
        "normdaten": "SELECT ExtractValue(marcxml, '//datafield[@tag=\"035\"]/subfield[@code=\"a\"]'), authid, authtypecode "
                     "FROM auth_header",
        "benutzer": "SELECT SUBSTRING_INDEX(sort1, ')', -1), borrowernumber, cardnumber FROM borrowers "
                    "WHERE sort1 LIKE '(ALEPHINO)%'",
    }
    kopf = {"titel": ["alephino", "koha_biblionumber"], "exemplare": ["alephino", "koha_itemnumber", "barcode"],
            "normdaten": ["alephino", "koha_authid", "art"], "benutzer": ["alephino", "koha_borrowernumber", "ausweis"]}
    n = {}
    for name, anweisung in tabellen.items():
        zeilen = sorted(k.sql(anweisung), key=lambda z: z[0] or "")
        with open(ziel / f"zuordnung-{name}.csv", "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter=";", lineterminator="\n")
            w.writerow(kopf[name])
            w.writerows(zeilen)
        n[name] = len(zeilen)
    return n


def vorpruefen(dateien: Path, k: Koha, leeren_erst: bool) -> None:
    """Stop before anything touches Koha: open Klärfälle, --leeren or loading outside a test container."""
    prot = dateien / "protokoll.json"
    if not prot.exists():
        raise SystemExit(f"STOPP: {prot} fehlt, erst umwandeln")
    offen = json.loads(prot.read_text(encoding="utf-8")).get("offen", [])
    if offen:
        arten = sorted({o["art"] for o in offen})
        raise SystemExit(f"STOPP: {len(offen)} Klärfälle ohne Freigabe ({', '.join(arten)}); erst entscheiden "
                         f"(freigaben.json), dann neu umwandeln. Siehe {dateien / 'klaerfaelle.csv'}")
    if leeren_erst and (not k.container or k.sql_befehl or k.shell_befehl):
        raise SystemExit(f"STOPP: --leeren löscht {GELOESCHT} und ist nur mit --container (Testumgebung) erlaubt, "
                         "nicht zusammen mit --sql oder --shell")
    if not k.container or k.sql_befehl or k.shell_befehl:
        raise SystemExit("STOPP: Laden ist heute nur für die Testumgebung eingerichtet (--container NAME, ohne --sql "
                         "und --shell); auf einem Koha-Server laufen bisher nur die Prüfwerkzeuge")


def laden(dateien: Path, export: Path, k: Koha, opac_url: str, dienst_url: str, leeren_erst: bool,
          sprache: str | None) -> dict:
    vorpruefen(dateien, k, leeren_erst)
    start = time.time()
    ergebnis: dict = {}
    if leeren_erst:
        leeren(k)
        log("Testumgebung geleert")
    grundeinstellungen(k, opac_url, dienst_url, sprache)
    log("Grundeinstellungen gesetzt")

    bulkmarcimport(k, dateien / "normdaten.mrc", "auth")
    karte = authid_karte(k)
    ergebnis["normdaten"] = len(karte)
    log("Normdaten geladen", anzahl=len(karte))

    mit9 = dateien / "titel-mit-authid.mrc"
    gesetzt, fehlt = mit_authid(dateien / "titel.mrc", mit9, karte)
    ergebnis["verknuepfungen"] = {"gesetzt": gesetzt, "ohne_koha_normsatz": fehlt}
    log("Normdatenverknüpfungen gesetzt", gesetzt=gesetzt, fehlt=fehlt)
    bulkmarcimport(k, mit9, "biblio")
    ergebnis["titel"] = int(k.wert("SELECT COUNT(*) FROM biblio") or 0)
    ergebnis["exemplare"] = int(k.wert("SELECT COUNT(*) FROM items") or 0)
    log("Titel und Exemplare geladen", titel=ergebnis["titel"], exemplare=ergebnis["exemplare"])

    ziel = hinein(k, dateien / "benutzer.csv")
    k.shell(f"cd {KOHA_DIR} && perl misc/import_patrons.pl --file {ziel} --matchpoint cardnumber --confirm 2>&1")
    ergebnis["benutzer"] = int(k.wert("SELECT COUNT(*) FROM borrowers WHERE sort1 LIKE '(ALEPHINO)%'") or 0)
    log("Benutzer geladen", anzahl=ergebnis["benutzer"])

    ergebnis["ausleihen"], ergebnis["ausleihhistorie"] = ausleihen_laden(k, dateien)
    log("Ausleihen geladen", laufend=ergebnis["ausleihen"], historie=ergebnis["ausleihhistorie"])

    upload_pfad = k.shell(f"grep -oP '(?<=<upload_path>)[^<]+' /etc/koha/sites/{k.instanz}/koha-conf.xml",
                          als_root=True).strip()
    if not upload_pfad:
        raise RuntimeError(f"kein <upload_path> in /etc/koha/sites/{k.instanz}/koha-conf.xml")
    ergebnis["pdf"] = pdf_laden(k, export, dateien, upload_pfad)
    log("PDF-Dateien geladen", anzahl=ergebnis["pdf"])

    # each step on its own, so a failing index rebuild or Plack restart stops the loader (k.shell checks the status);
    # clearing memcached is optional (the caches expire anyway)
    k.shell(f"koha-rebuild-zebra -f {k.instanz}", als_root=True)
    k.shell(f"koha-plack --restart {k.instanz}", als_root=True)
    k.shell("echo flush_all | nc -q1 memcached 11211 >/dev/null 2>&1 || true", als_root=True)
    log("Suchindex neu aufgebaut")
    ergebnis["zuordnungstabellen"] = zuordnungen(k, dateien)
    ergebnis["dauer_s"] = round(time.time() - start, 1)
    (dateien / "laden.json").write_text(json.dumps(ergebnis, ensure_ascii=False, indent=1) + "\n")
    log("fertig", dauer_s=ergebnis["dauer_s"])
    return ergebnis
