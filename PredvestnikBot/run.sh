#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run.sh — Точка входа для DigitalOcean App Platform (basic-xxs).
#
# Последовательность:
#   1. Догоняющая миграция достижений (идемпотентна, безопасно при каждом запуске)
#   2. Запуск FastAPI (uvicorn) — 1 воркер (критично для basic-xxs, иначе OOM)
# ─────────────────────────────────────────────────────────────────────────────
set -e

echo "═══ PredvestnikBot: запуск сервера ═══"

# Шаг 1: Догоняющая миграция достижений
echo "▶ Запуск achievements_catchup..."
python scripts/achievements_catchup.py || echo "⚠ achievements_catchup завершился с ошибкой (не критично)"

# Шаг 2: Запуск uvicorn (FastAPI + aiogram webhook)
# 1 воркер — обязательно для basic-xxs (512 МБ RAM)
echo "▶ Запуск uvicorn на порту ${PORT:-8080}..."
exec uvicorn web_app:app --host 0.0.0.0 --port "${PORT:-8080}" --workers 1 --log-level info
