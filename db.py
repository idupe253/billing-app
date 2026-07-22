"""Подключение к PostgreSQL.

Конфиг берётся из .env (см. .env.example). Пароль в коде НЕ хранится.
Соединение кешируется средствами Streamlit, чтобы не открывать его на каждый ререндер.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import streamlit as st
from dotenv import load_dotenv

# Загружаем .env один раз при импорте модуля
load_dotenv()


def _db_config() -> dict:
    """Параметры подключения из переменных окружения."""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.getenv("DB_NAME", "billing_app"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
    }


@st.cache_resource
def get_connection():
    """Единое соединение с БД на всё приложение (кешируется Streamlit)."""
    conn = psycopg2.connect(**_db_config())
    conn.autocommit = False
    return conn


@contextmanager
def get_cursor(commit: bool = False):
    """Курсор с автокоммитом/откатом.

    Возвращает строки как dict (RealDictCursor).
    При исключении делает rollback, иначе — commit, если commit=True.
    """
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield cur
        # Закрываем транзакцию в любом случае: commit при записи, иначе rollback —
        # чтобы соединение не оставалось «idle in transaction» и не держало блокировки.
        conn.commit() if commit else conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def ping() -> str:
    """Проверка соединения. Возвращает версию сервера или пробрасывает ошибку."""
    with get_cursor() as cur:
        cur.execute("SELECT version();")
        return cur.fetchone()["version"]


def apply_schema() -> None:
    """Прогон schema.sql (идемпотентно — создаёт недостающие таблицы)."""
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, encoding="utf-8") as f:
        sql = f.read()
    with get_cursor(commit=True) as cur:
        cur.execute(sql)


def sync_services() -> None:
    """Синхронизация реестра сервисов (services.py) → таблица services.

    Upsert по id: добавляет новые, обновляет name/accept_formats у существующих.
    Сервисы не удаляются (на них завязана история billing_entries).
    Вызывается при старте приложения и из migrate.py.
    """
    from services import SERVICES

    with get_cursor(commit=True) as cur:
        for svc in SERVICES:
            cur.execute(
                """
                INSERT INTO services (id, name, accept_formats)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                    SET name = EXCLUDED.name,
                        accept_formats = EXCLUDED.accept_formats;
                """,
                (svc["id"], svc["name"], ",".join(svc["accept"])),
            )
