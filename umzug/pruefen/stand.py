"""What should be in Koha (from the Alephino export and the documented decisions) and what is in Koha.

Both sides are read into plain dictionaries; the checks compare them. Standard library only, so the tools run on
any Koha server with Python 3.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from ..alephino import Export, datum
from ..koha import Koha

ART_PRAEFIX = {"person": "(ALEPHINO-PER)", "koerperschaft": "(ALEPHINO-KOE)", "schlagwort": "(ALEPHINO-SW)"}
PERSONEN = {f"{n:03d}" for n in range(100, 200, 4)}
KOERPERSCHAFTEN = {f"{n:03d}" for n in range(200, 300, 4)}
SW_ART = {"s": "schlagwort", "g": "schlagwort", "p": "person", "k": "koerperschaft"}
MARC = "{http://www.loc.gov/MARC21/slim}"


# Klärfall types whose release lowers the expected amount (the record is left out); all others keep the record
MENGENMINDERND = ("Exemplar ohne Titel", "Ausleihe ohne Benutzer")
ISBD_ENDE = re.compile(r"(?:\s+[:/=;]|[.,])+$")


def nfc(text: str | None) -> str:
    return unicodedata.normalize("NFC", (text or "").replace("¬", "").replace("\x98", "").replace("\x9c", "")).strip()


def titel_text(text: str | None) -> str:
    """A title compared character by character: NFC, without the ISBD separator the converter may have added at the
    end of 245 $a („ :“, „ /“, „ =“, „.“). The same function runs on both sides, so a title that ends in „.“ in
    Alephino is still compared exactly."""
    return ISBD_ENDE.sub("", nfc(text)).rstrip()


@dataclass
class Soll:
    """The expected state: the export minus what the library released to leave out."""
    titel: dict[str, str] = field(default_factory=dict)                 # sysno -> title (NFC)
    eltern: dict[str, str] = field(default_factory=dict)                # sysno -> superior sysno
    links: list[tuple[str, str, str]] = field(default_factory=list)     # (title, art, authority number)
    normen: dict[str, set[str]] = field(default_factory=dict)           # art -> numbers
    exemplare: dict[str, dict] = field(default_factory=dict)            # exemplar id -> row
    benutzer: dict[str, str] = field(default_factory=dict)              # id -> card number
    ausleihen: list[dict] = field(default_factory=list)
    historie: list[dict] = field(default_factory=list)
    pdf: dict[str, dict] = field(default_factory=dict)                  # title -> {datei, sha256, oeffentlich, url}
    freigegeben: dict[str, list[str]] = field(default_factory=dict)     # Klärfall-Art -> objects
    quelle_mengen: dict[str, int] = field(default_factory=dict)

    @classmethod
    def lesen(cls, export: Path, ziel: Path) -> "Soll":
        ex = Export.lesen(export)
        s = cls(quelle_mengen=ex.mengen())
        freigabe: dict[str, list[str]] = {}
        kl = ziel / "klaerfaelle.csv"
        if kl.exists():
            with open(kl, encoding="utf-8", newline="") as fh:
                for z in csv.DictReader(fh, delimiter=";"):
                    if z["aktion"].startswith("freigegeben"):
                        freigabe.setdefault(z["art"], []).append(z["objekt"])
        s.freigegeben = freigabe
        weg_ex = {o.split()[-1] for o in freigabe.get(MENGENMINDERND[0], [])}
        weg_aus = {o.split()[-1] for o in freigabe.get(MENGENMINDERND[1], [])}

        s.normen = {art: {n.sysno for n in saetze} for art, saetze in ex.normen.items()}
        for t in ex.titel:
            s.titel[t.sysno] = titel_text(t.wert("331", "a"))
            if (oben := t.wert("010", "a")):
                s.eltern[t.sysno] = oben
            for f in t.felder:
                art = ("person" if f.tag in PERSONEN else "koerperschaft" if f.tag in KOERPERSCHAFTEN else
                       SW_ART.get(next((c for c in "sgpk" if f.get(c)), ""), None) if f.tag == "902" else None)
                if art and (nr := f.get("9")) and nr in s.normen[art]:
                    s.links.append((t.sysno, art, nr))
        s.exemplare = {e["exemplar_id"]: e for e in ex.exemplare if e["exemplar_id"] not in weg_ex}
        s.benutzer = {b["benutzer_id"]: b["ausweis"] for b in ex.benutzer}
        s.ausleihen = [a for a in ex.ausleihen if not (a["exemplar_id"] in weg_aus and a["benutzer_id"] not in s.benutzer)]
        s.historie = [h for h in ex.historie if h["benutzer_id"] in s.benutzer]
        urls = {}
        if (ziel / "pdf.json").exists():
            urls = {p["titel_id"]: p for p in json.loads((ziel / "pdf.json").read_text(encoding="utf-8"))}
        for p in ex.pdf:
            pfad = ex.ordner / "pdf" / p["datei"]
            s.pdf[p["titel_id"]] = {"datei": p["datei"], "oeffentlich": p["zugriff"] == "oeffentlich",
                                    "sha256": hashlib.sha256(pfad.read_bytes()).hexdigest() if pfad.exists() else None,
                                    "url": urls.get(p["titel_id"], {}).get("url"),
                                    "hash": urls.get(p["titel_id"], {}).get("hash")}
        return s


@dataclass
class Ist:
    """The state in Koha, read with SQL only (no write)."""
    titel: dict[str, dict] = field(default_factory=dict)        # 001 -> {biblionumber, titel, links, eltern, urls}
    titel_ohne_id: list[str] = field(default_factory=list)      # biblionumbers without Alephino number
    normen: dict[str, dict] = field(default_factory=dict)       # authid -> {art, nummern}
    exemplare: dict[str, dict] = field(default_factory=dict)    # Alephino exemplar id -> item
    exemplare_ohne_id: list[str] = field(default_factory=list)
    benutzer: dict[str, dict] = field(default_factory=dict)     # borrowernumber -> {cardnumber, alephino}
    ausleihen: list[dict] = field(default_factory=list)
    historie: list[dict] = field(default_factory=list)
    uploads: dict[str, dict] = field(default_factory=dict)      # hashvalue -> row

    @classmethod
    def lesen(cls, k: Koha) -> "Ist":
        i = cls()
        for bn, xml in k.sql("SELECT biblionumber, metadata FROM biblio_metadata WHERE format = 'marcxml'"):
            rec = ET.fromstring(xml or "<record/>")
            if rec.tag != f"{MARC}record":
                innen = rec.find(f".//{MARC}record")
                rec = innen if innen is not None else rec
            kf = rec.find(f"{MARC}controlfield[@tag='001']")
            nr = (kf.text or "").strip() if kf is not None else ""
            ids = [sf.text or "" for df in rec.findall(f"{MARC}datafield[@tag='035']") for sf in df.findall(f"{MARC}subfield[@code='a']")]
            if not nr or f"(ALEPHINO){nr}" not in ids:
                i.titel_ohne_id.append(bn)
                continue
            t245 = rec.find(f"{MARC}datafield[@tag='245']/{MARC}subfield[@code='a']")
            links = [(df.get("tag"), sf.text or "") for df in rec.findall(f"{MARC}datafield")
                     for sf in df.findall(f"{MARC}subfield[@code='9']")]
            eltern = [sf.text or "" for sf in rec.findall(f"{MARC}datafield[@tag='773']/{MARC}subfield[@code='w']")]
            urls = [sf.text or "" for sf in rec.findall(f"{MARC}datafield[@tag='856']/{MARC}subfield[@code='u']")]
            i.titel[nr] = {"biblionumber": bn, "titel": titel_text(t245.text if t245 is not None else ""), "links": links,
                           "eltern": eltern, "urls": urls}
        for authid, typ, ids in k.sql("SELECT authid, authtypecode, ExtractValue(marcxml, "
                                      "'//datafield[@tag=\"035\"]/subfield[@code=\"a\"]') FROM auth_header"):
            i.normen[authid] = {"art": typ, "nummern": (ids or "").split()}
        bib_zu_nr = {v["biblionumber"]: nr for nr, v in i.titel.items()}
        for itemnumber, bn, barcode, notiz, signatur, nfl in k.sql(
                "SELECT itemnumber, biblionumber, barcode, itemnotes_nonpublic, itemcallnumber, notforloan FROM items"):
            eid = (notiz or "").split(")")[-1] if (notiz or "").startswith("(ALEPHINO-EX)") else None
            if eid is None:
                i.exemplare_ohne_id.append(itemnumber)
                continue
            i.exemplare[eid] = {"itemnumber": itemnumber, "titel": bib_zu_nr.get(bn), "barcode": barcode,
                                "signatur": nfc(signatur), "praesenz": (nfl or "0") != "0"}
        for bnr, karte, sort1 in k.sql("SELECT borrowernumber, cardnumber, sort1 FROM borrowers"):
            i.benutzer[bnr] = {"cardnumber": karte, "alephino": (sort1 or "")[len("(ALEPHINO)"):]
                               if (sort1 or "").startswith("(ALEPHINO)") else None}
        item_zu_ex = {v["itemnumber"]: eid for eid, v in i.exemplare.items()}
        for bnr, inr, aus, faellig, verl in k.sql("SELECT borrowernumber, itemnumber, DATE(issuedate), DATE(date_due), "
                                                  "renewals_count FROM issues"):
            i.ausleihen.append({"exemplar_id": item_zu_ex.get(inr), "karte": i.benutzer.get(bnr, {}).get("cardnumber"),
                                "ausleihe": aus, "faellig": faellig, "verlaengerungen": int(verl or 0)})
        for bnr, inr, aus, zurueck in k.sql("SELECT borrowernumber, itemnumber, DATE(issuedate), DATE(returndate) "
                                            "FROM old_issues"):
            i.historie.append({"exemplar_id": item_zu_ex.get(inr), "karte": i.benutzer.get(bnr, {}).get("cardnumber"),
                               "ausleihe": aus, "rueckgabe": zurueck})
        for uid, h, name, oeff, groesse in k.sql("SELECT id, hashvalue, filename, public, filesize FROM uploaded_files"):
            i.uploads[h] = {"id": uid, "datei": name, "oeffentlich": (oeff or "0") == "1", "groesse": groesse}
        return i


def ausleihe_soll(a: dict, karten: dict[str, str]) -> dict:
    return {"exemplar_id": a["exemplar_id"], "karte": karten.get(a["benutzer_id"]), "ausleihe": datum(a["ausleihe"]),
            **({"faellig": datum(a["faellig"]), "verlaengerungen": int(a.get("verlaengerungen") or 0)}
               if "faellig" in a else {"rueckgabe": datum(a.get("rueckgabe"))})}
