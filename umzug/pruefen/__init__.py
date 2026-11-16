"""The check tools. Each one compares the expected state (export + released decisions) with Koha and lists every
deviation; none of them writes to Koha.

    mengen       amount reconciliation per data set, with the identifiers that are missing or extra
    beziehungen  title–item assignment, authority links, superior records, titles with special characters
    pdf          title–PDF links: reachable, unchanged (SHA-256), and staff-only files not reachable from outside
    ausleihen    current loans (patron, item, dates, renewals) and loan history

Results: <bericht>/<werkzeug>.json (machine-readable), abweichungen.csv, bericht.html. Exit code 0 = no deviation.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import html
import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from ..koha import Koha
from .stand import ART_PRAEFIX, MENGENMINDERND, Ist, Soll, ausleihe_soll

KOHA_TYP = {"person": "PERSO_NAME", "koerperschaft": "CORPO_NAME", "schlagwort": ("TOPIC_TERM", "GEOGR_NAME")}


@dataclass
class Abweichung:
    werkzeug: str
    bereich: str
    objekt: str
    erwartet: str
    gefunden: str


def _abw(liste: list, werkzeug: str, bereich: str, objekt: str, erwartet: object, gefunden: object) -> None:
    liste.append(Abweichung(werkzeug, bereich, objekt, str(erwartet), str(gefunden)))


# --- 1. amounts --------------------------------------------------------------------------------------------------
def mengen(soll: Soll, ist: Ist) -> tuple[dict, list[Abweichung]]:
    abw: list[Abweichung] = []
    norm_ist: dict[str, set[str]] = {art: set() for art in ART_PRAEFIX}
    for v in ist.normen.values():
        for nr in v["nummern"]:
            for art, p in ART_PRAEFIX.items():
                if nr.startswith(p):
                    norm_ist[art].add(nr[len(p):])
    karten_ist = {v["cardnumber"] for v in ist.benutzer.values() if v["alephino"]}
    paare = {
        "titel": (set(soll.titel), set(ist.titel)),
        "exemplare": (set(soll.exemplare), set(ist.exemplare)),
        "personen": (soll.normen["person"], norm_ist["person"]),
        "koerperschaften": (soll.normen["koerperschaft"], norm_ist["koerperschaft"]),
        "schlagwoerter": (soll.normen["schlagwort"], norm_ist["schlagwort"]),
        "benutzer": (set(soll.benutzer.values()), karten_ist),
    }
    zeilen = []
    for name, (s, i) in paare.items():
        fehlt, extra = sorted(s - i), sorted(i - s)
        for x in fehlt[:200]:
            _abw(abw, "mengen", name, x, "in Koha", "fehlt")
        for x in extra[:200]:
            _abw(abw, "mengen", name, x, "nicht in Koha", "zusätzlich")
        zeilen.append({"bestand": name, "quelle": soll.quelle_mengen.get(name, len(s)), "erwartet": len(s),
                       "koha": len(i), "fehlt": len(fehlt), "zusaetzlich": len(extra), "ok": not fehlt and not extra})
    for name, s_n, i_n in (("ausleihen", len(soll.ausleihen), len(ist.ausleihen)),
                           ("ausleihhistorie", len(soll.historie), len(ist.historie)),
                           ("pdf", len(soll.pdf), sum(1 for u in ist.uploads.values()))):
        if s_n != i_n:
            _abw(abw, "mengen", name, "Anzahl", s_n, i_n)
        zeilen.append({"bestand": name, "quelle": soll.quelle_mengen.get(name, s_n), "erwartet": s_n, "koha": i_n,
                       "fehlt": max(0, s_n - i_n), "zusaetzlich": max(0, i_n - s_n), "ok": s_n == i_n})
    if ist.titel_ohne_id:
        _abw(abw, "mengen", "titel", f"{len(ist.titel_ohne_id)} Titel", "mit Alephino-Nummer", "ohne Alephino-Nummer")
    if ist.exemplare_ohne_id:
        _abw(abw, "mengen", "exemplare", f"{len(ist.exemplare_ohne_id)} Exemplare", "mit Alephino-Nummer",
             "ohne Alephino-Nummer")
    # only the released cases that lower an amount explain the column „erwartet“ (the others keep their record)
    freigegeben = {k: len(v) for k, v in soll.freigegeben.items() if k in MENGENMINDERND}
    return {"bestaende": zeilen, "freigegebene_abweichungen": freigegeben}, abw


# --- 2. relations ------------------------------------------------------------------------------------------------
def beziehungen(soll: Soll, ist: Ist) -> tuple[dict, list[Abweichung]]:
    abw: list[Abweichung] = []
    doppelt = {o.split()[-1] for o in soll.freigegeben.get("Barcode doppelt", [])}
    n = Counter()
    for eid, e in soll.exemplare.items():
        n["exemplare"] += 1
        k = ist.exemplare.get(eid)
        if k is None:
            _abw(abw, "beziehungen", "Titel–Exemplar", f"Exemplar {eid}", f"bei Titel {e['titel_id']}", "fehlt in Koha")
            continue
        if k["titel"] != e["titel_id"]:
            _abw(abw, "beziehungen", "Titel–Exemplar", f"Exemplar {eid}", f"bei Titel {e['titel_id']}",
                 f"bei Titel {k['titel']}")
        if k["barcode"] != e["barcode"] and not (eid in doppelt and k["barcode"].startswith(e["barcode"] + "-")):
            _abw(abw, "beziehungen", "Barcode", f"Exemplar {eid}", e["barcode"], k["barcode"])
        if k["signatur"] != e["signatur"]:
            _abw(abw, "beziehungen", "Signatur", f"Exemplar {eid}", e["signatur"], k["signatur"])
        if k["praesenz"] != (e["status"] == "praesenz"):
            _abw(abw, "beziehungen", "Ausleihstatus", f"Exemplar {eid}", e["status"],
                 "Präsenz" if k["praesenz"] else "ausleihbar")

    # authority links: the Koha title must carry $9 = the authid whose 035 is the expected Alephino number
    authid_von = {}
    for authid, v in ist.normen.items():
        for nr in v["nummern"]:
            authid_von[nr] = (authid, v["art"])
    for titel, art, nr in soll.links:
        n["normdatenverknuepfungen"] += 1
        t = ist.titel.get(titel)
        if t is None:
            continue                                     # already reported as missing title
        ziel = authid_von.get(ART_PRAEFIX[art] + nr)
        if ziel is None:
            _abw(abw, "beziehungen", "Normdaten", f"Titel {titel}", f"{art} {nr}", "Normsatz fehlt in Koha")
            continue
        if ziel[0] not in {a for _tag, a in t["links"]}:
            _abw(abw, "beziehungen", "Normdaten", f"Titel {titel}", f"{art} {nr} (authid {ziel[0]})",
                 "Verknüpfung fehlt oder zeigt auf einen anderen Normsatz")
        typ = KOHA_TYP[art]
        if ziel[1] not in (typ if isinstance(typ, tuple) else (typ,)):
            _abw(abw, "beziehungen", "Normdaten", f"Normsatz {nr}", art, f"Koha-Typ {ziel[1]}")
    for nr, t in ist.titel.items():
        for tag, authid in t["links"]:
            if authid not in ist.normen:
                _abw(abw, "beziehungen", "Normdaten", f"Titel {nr}, Feld {tag}", "vorhandener Normsatz",
                     f"$9 {authid} zeigt ins Leere")

    for kind, oben in soll.eltern.items():
        n["hierarchie"] += 1
        t = ist.titel.get(kind)
        if t is None:
            continue
        if oben not in t["eltern"] or oben not in ist.titel:
            _abw(abw, "beziehungen", "über-/untergeordnet", f"Titel {kind}", f"773 $w {oben}",
                 ", ".join(t["eltern"]) or "keine Verknüpfung")

    for nr, titel in soll.titel.items():
        n["titel_text"] += 1
        t = ist.titel.get(nr)
        if t is not None and t["titel"] != titel:
            _abw(abw, "beziehungen", "Titel und Sonderzeichen", f"Titel {nr}", titel, t["titel"])
    return {"geprueft": dict(n), "abweichungen": Counter(a.bereich for a in abw)}, abw


# --- 3. PDF ------------------------------------------------------------------------------------------------------
class Http:
    def __init__(self, timeout: float = 20):
        self.timeout = timeout
        self.anonym = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
        self.dienst = None

    def anmelden(self, dienst_url: str, benutzer: str, passwort: str) -> bool:
        jar = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        csrf = ""
        daten = op.open(f"{dienst_url}/cgi-bin/koha/mainpage.pl", timeout=self.timeout).read().decode("utf-8", "replace")
        if 'name="csrf_token" value="' in daten:
            csrf = daten.split('name="csrf_token" value="', 1)[1].split('"', 1)[0]
        form = urllib.parse.urlencode({"login_userid": benutzer, "login_password": passwort, "login_op": "cud-login",
                                       "koha_login_context": "intranet", "csrf_token": csrf, "branch": ""}).encode()
        antwort = op.open(f"{dienst_url}/cgi-bin/koha/mainpage.pl", data=form, timeout=self.timeout).read()
        self.dienst = op
        return b"loginform" not in antwort and b'id="login"' not in antwort

    def holen(self, url: str, dienst: bool = False) -> tuple[int, str, bytes]:
        op = self.dienst if dienst and self.dienst else self.anonym
        try:
            with op.open(url, timeout=self.timeout) as r:
                return r.status, r.headers.get("Content-Type", ""), r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type", ""), b""
        except (urllib.error.URLError, TimeoutError) as e:
            return 0, str(e), b""


def pdf(soll: Soll, ist: Ist, opac_url: str, http_: Http) -> tuple[dict, list[Abweichung]]:
    abw: list[Abweichung] = []
    n = Counter()
    for titel, p in sorted(soll.pdf.items()):
        n["pdf"] += 1
        t = ist.titel.get(titel)
        if t is None:
            continue
        url = next((u for u in t["urls"] if "upload" in u or "retrieve-file" in u), None)
        if url is None:
            _abw(abw, "pdf", "Verknüpfung", f"Titel {titel}", p["datei"], "kein Verweis (856 $u) im Titel")
            continue
        if p["hash"] and p["hash"] not in ist.uploads:
            _abw(abw, "pdf", "Datei in Koha", f"Titel {titel}", p["datei"], "kein Upload-Eintrag")
        status, typ, inhalt = http_.holen(url)
        ist_pdf = inhalt.startswith(b"%PDF")
        if p["oeffentlich"]:
            n["oeffentlich"] += 1
            if status != 200 or not ist_pdf:
                _abw(abw, "pdf", "Erreichbarkeit", f"Titel {titel}", f"{url} liefert die PDF",
                     f"HTTP {status}, {typ or 'kein Inhalt'}")
            elif hashlib.sha256(inhalt).hexdigest() != p["sha256"]:
                _abw(abw, "pdf", "Unverändert", f"Titel {titel}", f"SHA-256 {p['sha256'][:12]}…",
                     f"SHA-256 {hashlib.sha256(inhalt).hexdigest()[:12]}…")
        else:
            n["intern"] += 1
            # staff-only: neither the link nor the public retrieval may hand out the file to an anonymous visitor
            offen = f"{opac_url}/cgi-bin/koha/opac-retrieve-file.pl?id={p['hash']}"
            for pruef_url in (url, offen):
                s2, _t2, i2 = http_.holen(pruef_url)
                if i2.startswith(b"%PDF"):
                    _abw(abw, "pdf", "Zugriffsrecht", f"Titel {titel}", "nur Dienstoberfläche",
                         f"ohne Anmeldung abrufbar: {pruef_url}")
                    break
            if http_.dienst is not None:
                s3, _t3, i3 = http_.holen(url, dienst=True)
                if not i3.startswith(b"%PDF") or hashlib.sha256(i3).hexdigest() != p["sha256"]:
                    _abw(abw, "pdf", "Erreichbarkeit (Dienst)", f"Titel {titel}", "PDF nach Anmeldung",
                         f"HTTP {s3}")
                else:
                    n["intern_mit_anmeldung_geprueft"] += 1
    oeffentliche_hashes = {p["hash"] for p in soll.pdf.values() if p["oeffentlich"]}
    for h, u in ist.uploads.items():
        if u["oeffentlich"] and h not in oeffentliche_hashes:
            _abw(abw, "pdf", "Zugriffsrecht", f"Upload {u['datei']}", "nicht öffentlich", "in Koha öffentlich")
    return {"geprueft": dict(n)}, abw


# --- 4. loans ----------------------------------------------------------------------------------------------------
def ausleihen(soll: Soll, ist: Ist) -> tuple[dict, list[Abweichung]]:
    abw: list[Abweichung] = []
    koha = {a["exemplar_id"]: a for a in ist.ausleihen}
    for a in soll.ausleihen:
        s = ausleihe_soll(a, soll.benutzer)
        k = koha.pop(a["exemplar_id"], None)
        if k is None:
            _abw(abw, "ausleihen", "laufende Ausleihe", f"Exemplar {a['exemplar_id']}", f"an {s['karte']}", "fehlt")
            continue
        for feld in ("karte", "ausleihe", "faellig", "verlaengerungen"):
            if str(s[feld]) != str(k[feld]):
                _abw(abw, "ausleihen", "laufende Ausleihe", f"Exemplar {a['exemplar_id']}", f"{feld} {s[feld]}",
                     f"{feld} {k[feld]}")
    for eid in koha:
        _abw(abw, "ausleihen", "laufende Ausleihe", f"Exemplar {eid}", "nicht ausgeliehen", "in Koha ausgeliehen")
    soll_h = Counter(tuple(ausleihe_soll(h, soll.benutzer).values()) for h in soll.historie)
    ist_h = Counter((h["exemplar_id"], h["karte"], h["ausleihe"], h["rueckgabe"]) for h in ist.historie)
    for t, anz in (soll_h - ist_h).items():
        _abw(abw, "ausleihen", "Historie", f"Exemplar {t[0]}", f"{anz}× {t[1]} {t[2]}–{t[3]}", "fehlt")
    for t, anz in (ist_h - soll_h).items():
        _abw(abw, "ausleihen", "Historie", f"Exemplar {t[0]}", "nicht in Alephino", f"{anz}× {t[1]} {t[2]}–{t[3]}")
    return {"geprueft": {"laufend": len(soll.ausleihen), "historie": len(soll.historie)}}, abw


# --- report ------------------------------------------------------------------------------------------------------
TITEL = {"mengen": "Mengenabgleich", "beziehungen": "Titel, Exemplare und Normdaten",
         "pdf": "Titel und PDF-Dateien", "ausleihen": "Benutzer und Ausleihen"}


BESTAND = {"titel": "Titel", "exemplare": "Exemplare", "personen": "Personen (Normdaten)",
           "koerperschaften": "Körperschaften (Normdaten)", "schlagwoerter": "Schlagwörter (Normdaten)",
           "benutzer": "Benutzer", "ausleihen": "laufende Ausleihen", "ausleihhistorie": "Ausleihhistorie",
           "pdf": "PDF-Dateien"}
GEPRUEFT = {"exemplare": "Exemplare am richtigen Titel", "normdatenverknuepfungen": "Normdatenverknüpfungen",
            "hierarchie": "Bände mit ihrer Reihe", "titel_text": "Titel Zeichen für Zeichen",
            "pdf": "PDF-Verknüpfungen", "oeffentlich": "davon öffentlich abrufbar und unverändert",
            "intern": "davon nur intern", "intern_mit_anmeldung_geprueft": "intern mit Anmeldung geprüft",
            "laufend": "laufende Ausleihen", "historie": "Einträge der Ausleihhistorie"}


def _zahl(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def bericht_html(ergebnisse: dict, abw: list[Abweichung], zeit: str) -> str:
    """One page for people: a verdict per tool, the counts, and the first 50 deviations of each tool."""
    def esc(x):
        return html.escape(str(x))
    gesamt = "Alles stimmt" if not abw else f"{_zahl(len(abw))} Abweichungen"
    teile = [f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Prüfbericht Koha-Umzug</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{{font:18px/1.5 "Source Sans 3","Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;max-width:940px;
margin:28px auto;padding:0 20px;color:#1c2529;background:#fff}}
h1{{font-size:32px;line-height:1.15;margin:0 0 6px}} .zeit{{color:#5d6b71;margin-bottom:20px;font-size:16px}}
.gesamt{{font-size:22px;font-weight:700;padding:12px 18px;border-radius:6px;margin-bottom:8px}}
.gesamt.ok{{background:#e7f4ec;color:#1d5c37}} .gesamt.nein{{background:#fbe9e7;color:#8c1d18}}
.karte{{border:1px solid #d5dfe1;border-radius:6px;padding:14px 20px;margin:16px 0}}
.karte.ok{{border-left:8px solid #2e7d4f}} .karte.nein{{border-left:8px solid #b3261e}}
.urteil{{font-weight:700;font-size:21px;margin-bottom:6px}} .ok .marke{{color:#2e7d4f}} .nein .marke{{color:#b3261e}}
table{{border-collapse:collapse;width:100%;font-size:16px;margin-top:6px}}
td,th{{border-bottom:1px solid #e6edef;padding:6px 8px;text-align:left;vertical-align:top;overflow-wrap:anywhere}}
th{{color:#5d6b71;font-weight:600;font-size:15px}} .zahl{{text-align:right;font-variant-numeric:tabular-nums}}
.hinweis{{color:#5d6b71;font-size:16px;margin:8px 0 0}}</style></head><body>
<h1>Prüfbericht Koha-Umzug</h1><div class="zeit">Erstellt {esc(zeit)} · Vergleich mit dem Alephino-Export ·
maschinenlesbar in den JSON-Dateien daneben</div>
<div class="gesamt {'ok' if not abw else 'nein'}">{'✓' if not abw else '✗'} {gesamt}</div>"""]
    for name, erg in ergebnisse.items():
        eigene = [a for a in abw if a.werkzeug == name]
        klasse = "ok" if not eigene else "nein"
        urteil = "alles stimmt" if not eigene else f"{_zahl(len(eigene))} Abweichung{'en' if len(eigene) != 1 else ''}"
        teile.append(f'<div class="karte {klasse}" id="{name}"><div class="urteil"><span class="marke">'
                     f'{"✓" if not eigene else "✗"}</span> {esc(TITEL[name])}: {urteil}</div>')
        if name == "mengen":
            teile.append('<table><tr><th>Bestand</th><th class="zahl">in Alephino</th><th class="zahl">erwartet</th>'
                         '<th class="zahl">in Koha</th><th>Ergebnis</th></tr>')
            for z in erg["bestaende"]:
                teil = [f"{z['fehlt']} {'fehlt' if z['fehlt'] == 1 else 'fehlen'}" if z["fehlt"] else "",
                        f"{z['zusaetzlich']} zusätzlich" if z["zusaetzlich"] else ""]
                stand = "✓ vollständig" if z["ok"] else "✗ " + ", ".join(x for x in teil if x)
                teile.append(f'<tr><td>{esc(BESTAND.get(z["bestand"], z["bestand"]))}</td>'
                             f'<td class="zahl">{_zahl(z["quelle"])}</td><td class="zahl">{_zahl(z["erwartet"])}</td>'
                             f'<td class="zahl">{_zahl(z["koha"])}</td><td>{esc(stand)}</td></tr>')
            teile.append("</table>")
            if erg["freigegebene_abweichungen"]:
                teile.append('<p class="hinweis">„erwartet“ = Alephino abzüglich der Datensätze, die die Bibliothek '
                             "als Klärfall zum Weglassen freigegeben hat: " + esc(", ".join(
                                 f"{k} ({v})" for k, v in erg["freigegebene_abweichungen"].items())) + "</p>")
        else:
            teile.append("<table>" + "".join(
                f'<tr><td>{esc(GEPRUEFT.get(k, k))}</td><td class="zahl">{_zahl(v)} geprüft</td></tr>'
                for k, v in erg["geprueft"].items()) + "</table>")
        if eigene:
            teile.append("<table><tr><th>Bereich</th><th>Objekt</th><th>erwartet</th><th>gefunden</th></tr>")
            for a in eigene[:50]:
                teile.append(f"<tr><td>{esc(a.bereich)}</td><td>{esc(a.objekt)}</td><td>{esc(a.erwartet)}</td>"
                             f"<td>{esc(a.gefunden)}</td></tr>")
            teile.append("</table>")
            if len(eigene) > 50:
                teile.append(f'<p class="hinweis">… und {_zahl(len(eigene) - 50)} weitere in abweichungen.csv</p>')
        teile.append("</div>")
    teile.append("</body></html>")
    return "\n".join(teile)


def ausfuehren(was: str, export: Path, ziel: Path, k: Koha, opac_url: str, dienst_url: str, bericht: Path,
               dienst_benutzer: str | None = None, dienst_passwort: str | None = None) -> int:
    soll = Soll.lesen(export, ziel)
    ist = Ist.lesen(k)
    bericht.mkdir(parents=True, exist_ok=True)
    werkzeuge = ["mengen", "beziehungen", "pdf", "ausleihen"] if was == "alle" else [was]
    ergebnisse, alle = {}, []
    http_ = Http()
    if "pdf" in werkzeuge and dienst_benutzer:
        if not http_.anmelden(dienst_url, dienst_benutzer, dienst_passwort or ""):
            print("Anmeldung an der Dienstoberfläche fehlgeschlagen: interne PDFs nur von außen geprüft")
            http_.dienst = None
    for w in werkzeuge:
        erg, abw = (pdf(soll, ist, opac_url, http_) if w == "pdf" else
                    {"mengen": mengen, "beziehungen": beziehungen, "ausleihen": ausleihen}[w](soll, ist))
        zeit = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        (bericht / f"{w}.json").write_text(json.dumps({"werkzeug": w, "zeit": zeit, "ergebnis": erg,
                                                       "abweichungen": [asdict(a) for a in abw]},
                                                      ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        ergebnisse[w] = erg
        alle += abw
        print(f"{TITEL[w]}: {'alles stimmt' if not abw else str(len(abw)) + ' Abweichungen'}")
    with open(bericht / "abweichungen.csv", "w", encoding="utf-8", newline="") as fh:
        wr = csv.writer(fh, delimiter=";", lineterminator="\n")
        wr.writerow(["werkzeug", "bereich", "objekt", "erwartet", "gefunden"])
        wr.writerows([[a.werkzeug, a.bereich, a.objekt, a.erwartet, a.gefunden] for a in alle])
    zeit = dt.datetime.now().astimezone().strftime("%d.%m.%Y, %H:%M")
    (bericht / "bericht.html").write_text(bericht_html(ergebnisse, alle, zeit), encoding="utf-8")
    print(f"Bericht: {bericht / 'bericht.html'}")
    return 0 if not alle else 1
