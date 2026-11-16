#!/usr/bin/env bash
# Der vollständige Messlauf, dessen Zahlen in README und Protokoll stehen.
#   nachweis/messlauf.sh <koha-container> [<python>]
# Schreibt nachweis/<Datum>/: ergebnisse.json, pruefbericht/, fehlerprobe.json, fehlerprobe-bericht/, nach-neuladen/
# und zuletzt PROTOKOLL.md (nachweis/protokoll.py, aus diesen Dateien). Ein zweiter Lauf am selben Tag ersetzt den Ordner.
# Lädt Koha zweimal neu (--leeren): nur gegen eine Testumgebung laufen lassen.
set -euo pipefail
C="${1:?Koha-Container}"; PY="${2:-python3}"
cd "$(dirname "$0")/.."
TAG="$(TZ=Europe/Berlin date +%F)"; N="nachweis/$TAG"; rm -rf "$N"; mkdir -p "$N"
B=beispiel; ZUGANG="--container $C"
KOHA_VERSION="$(docker exec "$C" grep -oP '(?<=VERSION = ")[^"]+' /kohadevbox/koha/Koha.pm)"
SAUBER=$([ -z "$(git status --porcelain -- umzug daten koha tests nachweis/messlauf.sh nachweis/protokoll.py)" ] \
  && echo 1 || echo 0)

$PY -I daten/nachbilden.py --ziel $B/export > "$N/nachbilden.json"
$PY -m umzug umwandeln $B/export $B/koha --freigaben $B/freigaben.json > "$N/umwandeln.json"
t0=$(date +%s.%N); $PY -m umzug laden $B/koha $B/export $ZUGANG --leeren --sprache de-DE | tee "$N/laden.log"
t_laden=$(echo "$(date +%s.%N) - $t0" | bc)
t0=$(date +%s.%N); $PY -m umzug pruefen alle $B/export $B/koha $ZUGANG --bericht "$N/pruefbericht" \
  --dienst-benutzer koha --dienst-passwort koha | tee "$N/pruefen.log"; t_pruefen=$(echo "$(date +%s.%N) - $t0" | bc)
$PY -m umzug.fehlerprobe $B/export $B/koha $ZUGANG --ergebnis "$N/fehlerprobe.json" | tee "$N/fehlerprobe.log"
$PY -m umzug pruefen alle $B/export $B/koha $ZUGANG --bericht "$N/fehlerprobe-bericht" > /dev/null || true
$PY -m umzug laden $B/koha $B/export $ZUGANG --leeren --sprache de-DE > "$N/laden-wieder.log"
$PY -m umzug pruefen alle $B/export $B/koha $ZUGANG --bericht "$N/nach-neuladen" > /dev/null
$PY -m pytest -q tests | tail -1 > "$N/tests.txt"
cp $B/koha/protokoll.json $B/koha/laden.json $B/koha/klaerfaelle.csv "$N/"
$PY - "$N" "$t_laden" "$t_pruefen" "$(git rev-parse HEAD)" "$KOHA_VERSION" "$SAUBER" <<'PY'
import json, sys
from pathlib import Path
n, t_laden, t_pruefen, commit = Path(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
koha_version, sauber = sys.argv[5], sys.argv[6] == "1"
prot = json.loads((n / "protokoll.json").read_text())
laden = json.loads((n / "laden.json").read_text())
fp = json.loads((n / "fehlerprobe.json").read_text())
abw = sum(len(json.loads(p.read_text())["abweichungen"]) for p in (n / "pruefbericht").glob("*.json"))
abw2 = sum(len(json.loads(p.read_text())["abweichungen"]) for p in (n / "nach-neuladen").glob("*.json"))
pdf = json.loads((n / "pruefbericht" / "pdf.json").read_text())["ergebnis"]["geprueft"]
tests = (n / "tests.txt").read_text().strip()
erg = {"datum": n.name, "commit": commit, "arbeitsbaum_sauber": sauber,
       "koha": f"{koha_version} (aus Koha.pm; koha-testing-docker, Image 26.05)",
       "quelle": prot["quelle"], "ziel": prot["ziel"], "weggelassen_freigegeben": prot["weggelassen"],
       "klaerfaelle": prot["klaerfaelle"], "nfc_korrigiert": prot["nfc_korrigiert"],
       "geladen": {k: laden[k] for k in ("titel", "exemplare", "normdaten", "benutzer", "ausleihen", "ausleihhistorie", "pdf")},
       "normdatenverknuepfungen": laden["verknuepfungen"], "laden_s": round(t_laden, 1), "pruefen_s": round(t_pruefen, 1),
       "abweichungen_nach_umzug": abw, "pdf_geprueft": pdf,
       "fehlerprobe": {"eingespielt": fp["eingespielt"], "gefunden": fp["gefunden"],
                       "folgeabweichungen": len(fp["folgeabweichungen"]), "hinweis": "simuliert"},
       "abweichungen_nach_neuladen": abw2, "tests": tests}
(n / "ergebnisse.json").write_text(json.dumps(erg, ensure_ascii=False, indent=1) + "\n")
print(json.dumps(erg, ensure_ascii=False, indent=1))
PY
$PY -I nachweis/protokoll.py "$N"
