"""Запись и чтение данных биллинга по периоду.

Вариант А: при загрузке файла сервиса ники пишутся в billing_entries с
временным cfo='' и source='pending'. Реальные cfo/source считаются позже
(при формировании отчёта/финализации) по report_employees + report_extra_users.
Загрузка файлов НЕ зависит от того, загружен ли справочник.
"""
from __future__ import annotations

import pandas as pd
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


# ─── Справочник сотрудников (снимок на период) ────────────────────────────────

def save_employees(report_id: int, df: pd.DataFrame) -> int:
    """Сохранить снимок справочника на период (перезапись report_employees).

    df: колонки nick, cfo, dept. Возвращает число записанных строк.
    """
    rows = [
        (report_id, r["nick"], r["cfo"], str(r.get("dept", "") or ""))
        for _, r in df.iterrows()
        if r["nick"]
    ]
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM report_employees WHERE report_id = %s;", (report_id,))
        if rows:
            execute_values(
                cur,
                "INSERT INTO report_employees (report_id, nick, cfo, dept) VALUES %s "
                "ON CONFLICT (report_id, nick) DO UPDATE "
                "SET cfo = EXCLUDED.cfo, dept = EXCLUDED.dept;",
                rows,
            )
    return len(rows)


def has_employees(report_id: int) -> bool:
    with get_cursor() as cur:
        cur.execute(
            "SELECT 1 FROM report_employees WHERE report_id = %s LIMIT 1;", (report_id,)
        )
        return cur.fetchone() is not None


def get_employees_df(report_id: int) -> pd.DataFrame:
    """Справочник периода как DataFrame[nick, cfo, dept]."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT nick, cfo, dept FROM report_employees WHERE report_id = %s "
            "ORDER BY nick;",
            (report_id,),
        )
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["nick", "cfo", "dept"]) if rows else pd.DataFrame(
        columns=["nick", "cfo", "dept"]
    )


# ─── Доп. (вручную назначенные) пользователи ──────────────────────────────────

def get_extra_db(report_id: int) -> dict[str, dict]:
    """Доп-юзеры периода в формате {nick: {"cfo": str, "services": [service_id,...]}}."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT nick, service_id, cfo FROM report_extra_users WHERE report_id = %s;",
            (report_id,),
        )
        result: dict[str, dict] = {}
        for r in cur.fetchall():
            entry = result.setdefault(r["nick"], {"cfo": r["cfo"], "services": []})
            entry["cfo"] = r["cfo"]
            entry["services"].append(r["service_id"])
        return result


def set_extra_assignment(report_id: int, nick: str, cfo: str, service_ids: list[str]) -> None:
    """Назначить нику ЦФО для указанных сервисов (upsert по каждому сервису)."""
    if not service_ids:
        return
    with get_cursor(commit=True) as cur:
        execute_values(
            cur,
            "INSERT INTO report_extra_users (report_id, nick, service_id, cfo) VALUES %s "
            "ON CONFLICT (report_id, service_id, nick) DO UPDATE SET cfo = EXCLUDED.cfo;",
            [(report_id, nick, sid, cfo) for sid in service_ids],
        )


def clear_extra_users(report_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM report_extra_users WHERE report_id = %s;", (report_id,))


# ─── Пересчёт cfo/source в billing_entries ────────────────────────────────────

def recompute_billing(report_id: int) -> None:
    """Проставить cfo и source в billing_entries по справочнику и доп-юзерам.

    Приоритет: employee (справочник) > extra (доп-юзер) > not_found.
    """
    with get_cursor(commit=True) as cur:
        # 1. Сотрудники из справочника
        cur.execute(
            "UPDATE billing_entries b SET source = 'employee', cfo = e.cfo "
            "FROM report_employees e "
            "WHERE b.report_id = e.report_id AND b.nick = e.nick AND b.report_id = %s;",
            (report_id,),
        )
        # 2. Доп-юзеры (по конкретному сервису), кто не сотрудник
        cur.execute(
            "UPDATE billing_entries b SET source = 'extra', cfo = x.cfo "
            "FROM report_extra_users x "
            "WHERE b.report_id = x.report_id AND b.service_id = x.service_id "
            "AND b.nick = x.nick AND b.report_id = %s AND b.source <> 'employee';",
            (report_id,),
        )
        # 3. Остальные — не найдены
        cur.execute(
            "UPDATE billing_entries SET source = 'not_found', cfo = '' "
            "WHERE report_id = %s AND source NOT IN ('employee', 'extra');",
            (report_id,),
        )
