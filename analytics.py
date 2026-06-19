"""Аналитика по периодам (история, сравнение месяцев).

Кросс-периодные запросы поверх billing_entries / report_prices.
Считаются все периоды (и draft, и finalized) — порядок по месяцу.
"""
from __future__ import annotations

import pandas as pd

from db import get_cursor


def service_revenue() -> pd.DataFrame:
    """Доходность сервисов по месяцам.

    Колонки: month, service_id, licenses, price, cost.
    cost = licenses * price (цена за лицензию на период).
    Учитываются все лицензии сервиса (включая не найденных — лицензия потреблена).
    """
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT r.month,
                   b.service_id,
                   COUNT(*)              AS licenses,
                   COALESCE(p.price, 0)  AS price
            FROM reports r
            JOIN billing_entries b ON b.report_id = r.id
            LEFT JOIN report_prices p
                   ON p.report_id = r.id AND p.service_id = b.service_id
            GROUP BY r.month, b.service_id, p.price
            ORDER BY r.month, b.service_id;
            """
        )
        rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=["month", "service_id", "licenses", "price"])
    if df.empty:
        return df.assign(cost=pd.Series(dtype=float))
    df["price"] = df["price"].astype(float)
    df["licenses"] = df["licenses"].astype(int)
    df["cost"] = (df["licenses"] * df["price"]).round(2)
    return df


def cfo_consumption() -> pd.DataFrame:
    """Потребление лицензий по ЦФО по месяцам.

    Колонки: month, cfo, licenses, cost.
    cost = сумма цен сервисов по всем записям ЦФО.
    Не найденные (cfo='') сводятся в «Не найден».
    """
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT r.month,
                   b.cfo,
                   COUNT(*)                   AS licenses,
                   SUM(COALESCE(p.price, 0))  AS cost
            FROM reports r
            JOIN billing_entries b ON b.report_id = r.id
            LEFT JOIN report_prices p
                   ON p.report_id = r.id AND p.service_id = b.service_id
            GROUP BY r.month, b.cfo
            ORDER BY r.month, b.cfo;
            """
        )
        rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=["month", "cfo", "licenses", "cost"])
    if df.empty:
        return df
    df["cfo"] = df["cfo"].replace("", "Не найден")
    df["licenses"] = df["licenses"].astype(int)
    df["cost"] = df["cost"].astype(float).round(2)
    return df
