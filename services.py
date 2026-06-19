"""Реестр сервисов — единый источник правды.

Парсеры живут в коде (app.py), а здесь — только метаданные сервисов.
Этот список синхронизируется в таблицу `services` при старте приложения
(см. db_sync_services). Сервисы добавляет разработчик: строка сюда + парсер в app.py.

ВАЖНО: id сервиса стабилен и не меняется — он завязан на FK во всей истории
billing_entries. Менять можно name и accept, id — нет.
"""

# Реестр сервисов
SERVICES = [
    {"id": "google",      "name": "Google Workspace",  "accept": ["csv", "xlsx"]},
    {"id": "miro",        "name": "Miro",              "accept": ["csv", "xlsx"]},
    {"id": "github",      "name": "GitHub",            "accept": ["xlsx"]},
    {"id": "copilot",     "name": "GitHub Copilot",    "accept": ["xlsx"]},
    {"id": "m365",        "name": "M365",              "accept": ["xlsx"]},
    {"id": "powerbi",     "name": "Power BI",          "accept": ["xlsx"]},
    {"id": "mattermost",  "name": "Mattermost",        "accept": ["csv", "xlsx"]},
    {"id": "testit",      "name": "TestIT",            "accept": ["csv", "xlsx"]},
    {"id": "1c",          "name": "1С Лицензии",       "accept": ["xlsx"]},
    {"id": "jira",        "name": "Jira + Confluence",  "accept": ["xlsx"]},
]

SVC_ID_TO_NAME = {s["id"]: s["name"] for s in SERVICES}
