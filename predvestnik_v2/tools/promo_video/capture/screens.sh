#!/bin/bash
# Снимает настоящие экраны мини-приложения (в разных SSS-скинах) и веб-админки для роликов.
# Нужны: локальный PostgreSQL с базой predvestnik_preprod (docs/UI_STAND_AND_SMOKE.md), Node + playwright, ffmpeg.
# Результат: ../assets/screens/*.jpg. Перед первым запуском залей демо-игроков и чаты: psql … -f seed_demo.sql.
set -e
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../../.." && pwd)
TMP=$(mktemp -d); OUT="$HERE/../assets/screens"; mkdir -p "$OUT"
stand() {   # перезапуск стенда в нужном скине, печатает ссылку входа
  pkill -f "^python3 tools/ui_stand" || true; sleep 1
  (cd "$ROOT" && setsid nohup python3 tools/ui_stand.py --skin "$1" --tier SSS --rich --name "Лиза" --flags on > "$TMP/stand.log" 2>&1 < /dev/null &)
  for i in $(seq 1 90); do grep -q "activate?" "$TMP/stand.log" 2>/dev/null && break; sleep 1; done
  grep -o "http://[^ ]*activate[^ ]*" "$TMP/stand.log"
}
TOPCHATS="openTopV3();setTimeout(()=>{const b=[...document.querySelectorAll('button,a,[role=tab]')].find(x=>x.textContent.trim()==='Чаты'); b&&b.click()},1200)"
cd "$HERE"
node app_shots.cjs "$(stand starheart)" "$TMP" "profile+full=switchPage('profile')" "looks=openLooksModal()" "more=switchPage('more')"
node app_shots.cjs "$(stand midnight_comet)" "$TMP" "quests=openQuestsV1()" "ach=openAchievementsV1()" "profile_comet=switchPage('profile')"
node app_shots.cjs "$(stand scarlet_star)" "$TMP" "pets=openPetsV1()" "pass=openSeasonPass()" "profile_scarlet=switchPage('profile')"
node app_shots.cjs "$(stand sakura_storm)" "$TMP" "top=openTopV3()" "topchats=$TOPCHATS" "tracker=openChatTracker()" "profile_sakura=switchPage('profile')"
U=$(stand crimson_dark)
MOCK=mocks/purge.json node app_shots.cjs "$U" "$TMP" "purge=openPurgeHub(-1004)"
MOCK=mocks/purge_done.json node app_shots.cjs "$U" "$TMP" "purge_done=openPurgeHub(-1004)"
MOCK=mocks/purge_start.json node app_shots.cjs "$U" "$TMP" "purge_start=openPurgeHub(-1004)"
pkill -f "^python3 tools/ui_stand" || true
node admin_shots.cjs "$TMP"
for f in "$TMP"/*.png; do ffmpeg -loglevel error -y -i "$f" -q:v 3 "$OUT/$(basename "${f%.png}").jpg"; done
echo "снимки: $OUT"
