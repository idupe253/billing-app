#!/usr/bin/env bash
# Быстрый запуск Billing Automation.
# Первый запуск: создаёт .venv, ставит зависимости, применяет схему БД.
# Повторные запуски: просто поднимает приложение.
set -e

cd "$(dirname "$0")"

PORT="${PORT:-8501}"
PY=".venv/bin/python"

# 1. Виртуальное окружение
if [ ! -d ".venv" ]; then
    echo "→ Создаю виртуальное окружение (.venv)…"
    python3 -m venv .venv
    "$PY" -m pip install --quiet --upgrade pip
    echo "→ Устанавливаю зависимости…"
    "$PY" -m pip install --quiet -r requirements.txt
fi

# 2. Конфигурация БД
if [ ! -f ".env" ]; then
    echo "✗ Нет файла .env — скопируйте .env.example в .env и впишите параметры PostgreSQL:"
    echo "    cp .env.example .env"
    exit 1
fi

# 3. Миграция (идемпотентна: создаёт недостающие таблицы и синкает сервисы)
echo "→ Применяю миграцию БД…"
"$PY" migrate.py

# 4. Запуск
echo "→ Запускаю приложение на http://localhost:${PORT}"
exec .venv/bin/streamlit run app.py --server.port "$PORT"
