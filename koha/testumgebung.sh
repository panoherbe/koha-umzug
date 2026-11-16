#!/usr/bin/env bash
# Koha 26.05 zum Ausprobieren, mit dem offiziellen Entwicklungs-Container der Koha-Gemeinschaft
# (koha-testing-docker, https://gitlab.com/koha-community/koha-testing-docker). Nur für Tests, nicht für den Betrieb.
#
#   koha/testumgebung.sh <ordner>     # legt <ordner>/ktd und <ordner>/koha an und startet Koha
#
# Danach: OPAC http://127.0.0.1:18080, Dienstoberfläche http://127.0.0.1:18081 (Konto koha / koha).
# Die Ports sind nur auf diesem Rechner erreichbar (127.0.0.1). Festgelegt sind Koha (Release 26.05.05, Git-Tag
# v26.05.05-1) und koha-testing-docker (Stand vom 24.07.2026, Commit ef7f1f9). Die Images koha/koha-testing:26.05 und
# mariadb:10.11 sind Tags, die sich mit der Zeit ändern können; welches Image ein Messlauf hatte (mit Digest), steht in
# nachweis/<Datum>/testumgebung.txt. Dauer und Platz stehen mit Messdatum in der README („In zwei Minuten selbst prüfen“).
set -euo pipefail
KOHA_TAG="v26.05.05-1"
KTD_COMMIT="ef7f1f97a5ba24d7552d3c4ed6396f196e6b1b36"
ORDNER="$(realpath "${1:?Ordner angeben}")"
mkdir -p "$ORDNER"
cd "$ORDNER"
GIT="docker run --rm --user $(id -u):$(id -g) -e HOME=/tmp -v $ORDNER:/w -w /w alpine/git:latest"
[ -d ktd ] || { $GIT clone -q https://gitlab.com/koha-community/koha-testing-docker.git ktd \
  && $GIT -C ktd -c advice.detachedHead=false checkout -q "$KTD_COMMIT"; }
[ -d koha ] || $GIT clone --depth 1 --branch "$KOHA_TAG" https://git.koha-community.org/Koha-community/Koha.git koha
cd ktd
cp env/defaults.env .env
sed -i "s/^KOHA_IMAGE=.*/KOHA_IMAGE=26.05/; s/^KOHA_DOMAIN=.*//" .env
printf 'SYNC_REPO=%s\nLOCAL_USER_ID=%s\nKTD_HOME=%s\nKOHA_DOMAIN=.koha.test\n' "$ORDNER/koha" "$(id -u)" "$ORDNER/ktd" >> .env
# ältere docker compose kennen enable_ipv4/enable_ipv6 nicht
sed -i '/enable_ipv4:/d;/enable_ipv6:/d' compose/base.yml
cat > compose/nur_lokal.yml <<'YML'
services:
    koha:
        ports:
            - "127.0.0.1:18080:8080"
            - "127.0.0.1:18081:8081"
YML
docker compose --project-directory . -p kohaumzug -f compose/base.yml -f compose/db-mariadb.yml \
  -f compose/nur_lokal.yml up -d
echo "Warte auf Koha …"
until docker exec kohaumzug-koha-1 test -f /ktd_ready 2>/dev/null; do sleep 10; done
# deutsche Oberfläche
docker exec kohaumzug-koha-1 bash -c "cd /kohadevbox/koha/misc/translator && sudo -u kohadev-koha -E env \
  KOHA_CONF=/etc/koha/sites/kohadev/koha-conf.xml PERL5LIB=/kohadevbox/koha:/kohadevbox/koha/lib perl translate install de-DE"
VERSION="$(docker exec kohaumzug-koha-1 grep -oP '(?<=VERSION = ")[^"]+' /kohadevbox/koha/Koha.pm)"
echo "Koha läuft: Container kohaumzug-koha-1, Koha $VERSION, nach $SECONDS s"
