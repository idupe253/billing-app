"""Управление отчётными периодами (таблица reports) и их жизненным циклом.

Бизнес-правила (см. CLAUDE.md):
- Нельзя создать новый draft, пока есть незавершённый (не finalized) период.
- При создании периода копируются extra_users и prices из предыдущего.
- Финализированный период — только чтение; есть возврат в draft.
"""
from __future__ import annotations

from db import get_cursor


def list_reports() -> list[dict]:
    """Все периоды, новые сверху."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, month, status, created_at, finalized_at "
            "FROM reports ORDER BY month DESC;"
        )
        return cur.fetchall()


def get_report(report_id: int) -> dict | None:
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, month, status, created_at, finalized_at "
            "FROM reports WHERE id = %s;",
            (report_id,),
        )
        return cur.fetchone()


def get_open_draft() -> dict | None:
    """Текущий незавершённый период (draft), если есть."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, month, status FROM reports "
            "WHERE status = 'draft' ORDER BY month DESC LIMIT 1;"
        )
        return cur.fetchone()


def create_report(month: str) -> int:
    """Создать новый период (draft) за месяц 'YYYY-MM'.

    Блокирует создание, если уже есть открытый draft.
    Копирует extra_users и prices из самого свежего предыдущего периода.
    Возвращает id нового периода.
    """
    draft = get_open_draft()
    if draft:
        raise ValueError(
            f"Уже есть незавершённый период {draft['month']}. "
            "Финализируйте его, прежде чем создавать новый."
        )

    with get_cursor(commit=True) as cur:
        # Проверка дубля месяца
        cur.execute("SELECT 1 FROM reports WHERE month = %s;", (month,))
        if cur.fetchone():
            raise ValueError(f"Период {month} уже существует.")

        # Предыдущий период (самый свежий месяц меньше нового) — источник копирования
        cur.execute(
            "SELECT id FROM reports WHERE month < %s ORDER BY month DESC LIMIT 1;",
            (month,),
        )
        prev = cur.fetchone()

        cur.execute(
            "INSERT INTO reports (month, status) VALUES (%s, 'draft') RETURNING id;",
            (month,),
        )
        new_id = cur.fetchone()["id"]

        if prev:
            prev_id = prev["id"]
            # Копируем доп. пользователей
            cur.execute(
                "INSERT INTO report_extra_users (report_id, nick, service_id, cfo) "
                "SELECT %s, nick, service_id, cfo FROM report_extra_users WHERE report_id = %s;",
                (new_id, prev_id),
            )
            # Копируем цены
            cur.execute(
                "INSERT INTO report_prices (report_id, service_id, price) "
                "SELECT %s, service_id, price FROM report_prices WHERE report_id = %s;",
                (new_id, prev_id),
            )

    return new_id


def finalize_report(report_id: int) -> None:
    """Финализировать период (status='finalized', проставить finalized_at)."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE reports SET status = 'finalized', finalized_at = NOW() "
            "WHERE id = %s AND status = 'draft';",
            (report_id,),
        )


def reopen_report(report_id: int) -> None:
    """Вернуть период в draft (для исправлений)."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE reports SET status = 'draft', finalized_at = NULL WHERE id = %s;",
            (report_id,),
        )


def missing_services(report_id: int) -> list[str]:
    """Сервисы (id), по которым в периоде нет загруженных файлов.

    Используется как предупреждение при финализации (не блокировка).
    """
    with get_cursor() as cur:
        cur.execute(
            "SELECT s.id FROM services s "
            "WHERE s.id NOT IN ("
            "    SELECT service_id FROM service_uploads WHERE report_id = %s"
            ") ORDER BY s.id;",
            (report_id,),
        )
        return [r["id"] for r in cur.fetchall()]
