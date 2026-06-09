# ⚡ Billing Automation

Автоматическое распределение лицензий IT-сервисов по ЦФО.

## Быстрый старт

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Запустить
streamlit run app.py
```

Приложение откроется в браузере по адресу `http://localhost:8501`.

## Что нужно

- Python 3.8+
- Файлы: справочник сотрудников (.xlsx) и выгрузки сервисов

## Поддерживаемые сервисы

| Сервис | Формат |
|--------|--------|
| Google Workspace | CSV / XLSX |
| Miro | CSV / XLSX |
| GitHub | XLSX |
| GitHub Copilot | XLSX (2-я вкладка) |
| M365 | XLSX |
| Power BI | XLSX |
| Mattermost | CSV / XLSX |
| TestIT | CSV / XLSX |
| 1С Лицензии | XLSX |
| Jira + Confluence | XLSX |

## Доп DB Users

Пользователи, не найденные в справочнике, можно назначить вручную.
Назначения сохраняются в файл `extra_db_users.json` рядом с приложением.
