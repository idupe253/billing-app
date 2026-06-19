"""Скрипт миграции БД.

Запуск:  .venv/bin/python migrate.py

Создаёт таблицы (schema.sql) и синхронизирует реестр сервисов.
Идемпотентен — можно прогонять повторно.
"""
import db


def main() -> None:
    print("Подключение:", db.ping())

    print("Применяю схему (schema.sql)...")
    db.apply_schema()

    print("Синхронизирую сервисы (services.py → services)...")
    db.sync_services()

    with db.get_cursor() as cur:
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1;"
        )
        tables = [r["tablename"] for r in cur.fetchall()]
        cur.execute("SELECT count(*) AS n FROM services;")
        n_services = cur.fetchone()["n"]

    print(f"Таблицы ({len(tables)}): {', '.join(tables)}")
    print(f"Сервисов в БД: {n_services}")
    print("Миграция завершена.")


if __name__ == "__main__":
    main()
