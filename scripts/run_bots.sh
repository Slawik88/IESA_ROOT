#!/bin/sh
# Лаунчер для App Platform: Предвестник и Домовой в одном контейнере
# (экономия отдельного воркера — см. Procfile, процесс `worker`).
#
# Оба бота запускаются как дети лаунчера; SIGTERM контейнеру (деплой/рестарт)
# останавливает обоих, перезапуск поднимает обоих. Логи идут в один поток
# компонента — различаются префиксами (🔮 Предвестник, 🤖 Домовой).
#
# Если контейнеру станет не хватать памяти (Insights → Memory) — вернуться
# к отдельному воркеру: Procfile `domovoy: cd domovoy && python -m bot`.

set -u

# Память контейнера — 512 МБ на двух ботов: glibc по умолчанию заводит арену на каждый поток
# (to_thread, пул SQL) и держит освобождённое. Две арены и возврат хвоста системе — минус десятки МиБ.
export MALLOC_ARENA_MAX=2
export MALLOC_TRIM_THRESHOLD_=131072

PREDVESTNIK_PID=0
DOMOVOY_PID=0

cleanup() {
    kill "$PREDVESTNIK_PID" "$DOMOVOY_PID" 2>/dev/null
    exit 0
}
trap cleanup TERM INT

(cd predvestnik_v2 && exec python -m bot) &
PREDVESTNIK_PID=$!

(cd domovoy && exec python -m bot) &
DOMOVOY_PID=$!

wait
