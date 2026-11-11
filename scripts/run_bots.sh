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

# Память контейнера общая на двух ботов: glibc по умолчанию заводит арену на каждый поток
# (to_thread, пул SQL) и держит освобождённое. Две арены и возврат хвоста системе — минус десятки МиБ.
export MALLOC_ARENA_MAX=2
export MALLOC_TRIM_THRESHOLD_=131072

PREDVESTNIK_PID=
DOMOVOY_PID=
SHUTDOWN_GRACE_SEC=8

running() {
    [ -n "$1" ] && kill -0 "$1" 2>/dev/null
}

cleanup() {
    trap '' TERM INT
    for pid in "$PREDVESTNIK_PID" "$DOMOVOY_PID"; do
        if running "$pid"; then kill -TERM "$pid" 2>/dev/null; fi
    done
    remaining=$SHUTDOWN_GRACE_SEC
    while [ "$remaining" -gt 0 ] && { running "$PREDVESTNIK_PID" || running "$DOMOVOY_PID"; }; do
        sleep 1
        remaining=$((remaining - 1))
    done
    for pid in "$PREDVESTNIK_PID" "$DOMOVOY_PID"; do
        if running "$pid"; then kill -KILL "$pid" 2>/dev/null; fi
        if [ -n "$pid" ]; then wait "$pid" 2>/dev/null; fi
    done
}
trap 'cleanup; exit 0' TERM INT

(cd predvestnik_v2 && exec python -m bot) &
PREDVESTNIK_PID=$!

(cd domovoy && exec python -m bot) &
DOMOVOY_PID=$!

while running "$PREDVESTNIK_PID" && running "$DOMOVOY_PID"; do
    sleep 1
done
if running "$PREDVESTNIK_PID"; then
    name=domovoy
    failed_pid=$DOMOVOY_PID
else
    name=predvestnik
    failed_pid=$PREDVESTNIK_PID
fi
wait "$failed_pid"
status=$?
echo "$name exited unexpectedly (status $status)" >&2
cleanup
if [ "$status" -eq 0 ]; then status=1; fi
exit "$status"
