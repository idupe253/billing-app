"""Запись и чтение данных биллинга по периоду.

Вариант А: при загрузке файла сервиса ники пишутся в billing_entries с
временным cfo='' и source='pending'. Реальные cfo/source считаются позже
(при формировании отчёта/финализации) по report_employees + report_extra_users.
Загрузка файлов НЕ зависит от того, загружен ли справочник.
"""
from __future__ import annotations

from psycopg2.extras import execute_values

from db import get_cursor


def save_service_upload(report_id: int, service_id: str, filename: str, nicks: list[str]) -> int:
    """Сохранить выгрузку сервиса в период (перезапись).

    Удаляет прежние billing_entries и service_uploads по (период, сервис),
    вставляет новые. Ники уже очищены/дедуплицированы парсером.
    Возвращает число записанных ников.
    """
    with get_cursor(commit=True) as cur:
        # Перезагрузка: убираем прежние данные сервиса в этом периоде
        cur.execute(
            "DELETE FROM billing_entries WHERE report_id = %s AND service_id = %s;",
            (report_id, service_id),
        )
        cur.execute(
            "DELETE FROM service_uploads WHERE report_id = %s AND service_id = %s;",
            (report_id, service_id),
        )

        cur.execute(
            "INSERT INTO service_uploads (report_id, service_id, filename, row_count) "
            "VALUES (%s, %s, %s, %s);",
            (report_id, service_id, filename, len(nicks)),
        )

        if nicks:
            execute_values(
                cur,
                "INSERT INTO billing_entries (report_id, service_id, nick, cfo, source) "
                "VALUES %s ON CONFLICT (report_id, service_id, nick) DO NOTHING;",
                [(report_id, service_id, n, "", "pending") for n in nicks],
            )
    return len(nicks)


def get_upload_status(report_id: int) -> dict[str, dict]:
    """Загруженные сервисы периода: service_id -> {filename, row_count, uploaded_at}."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT service_id, filename, row_count, uploaded_at "
            "FROM service_uploads WHERE report_id = %s;",
            (report_id,),
        )
        return {r["service_id"]: dict(r) for r in cur.fetchall()}


def get_service_nicks(report_id: int) -> dict[str, list[str]]:
    """Ники по каждому сервису периода: service_id -> [nick, ...]."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT service_id, nick FROM billing_entries WHERE report_id = %s "
            "ORDER BY service_id, nick;",
            (report_id,),
        )
        result: dict[str, list[str]] = {}
        for r in cur.fetchall():
            result.setdefault(r["service_id"], []).append(r["nick"])
        return result
