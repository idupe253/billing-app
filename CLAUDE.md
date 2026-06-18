# CLAUDE.md — Контекст проекта для агента

## Что это

Billing Automation Tool — приложение на Python/Streamlit для автоматического распределения лицензий IT-сервисов по ЦФО (центрам финансовой ответственности).

Репозиторий: https://github.com/idupe253/billing-app
Текущий файл: `app.py` — всё приложение в одном файле.

## Текущее состояние

Приложение работает, но хранит данные в JSON-файлах (`extra_db_users.json`, `service_prices.json`, `theme.json`). Нужно мигрировать на PostgreSQL с поддержкой истории по месяцам.

## Архитектура текущая

- **Стек**: Python, Streamlit, Pandas, openpyxl
- **Парсеры сервисов**: каждый парсер — функция, принимает uploaded file, возвращает `list[str]` (список ников)
- **Отчёты**: HTML (по отделам, с раскрывающимися списками пользователей) + Excel (формат для финансов)
- **Темы**: 3 варианта (light/dark/accent) — CSS-инъекция в Streamlit + HTML-отчёты
- **UI**: 3 вкладки (Отчёт / Параметры / Доп DB Users), сайдбар для загрузки файлов

## Сервисы и их парсеры

| id | Сервис | Формат | Как извлекается ник |
|----|--------|--------|---------------------|
| google | Google Workspace | CSV/XLSX | Столбец B (`Last Name [Required]`) |
| miro | Miro | CSV/XLSX | Последнее слово из столбца A (`Name`) |
| github | GitHub | XLSX, 1-я вкладка | Столбец F (`GitHub com saml name ID`), фоллбэк столбец A (`login`) |
| copilot | GitHub Copilot | XLSX, 2-я вкладка `Copilot Usage` | Столбец C (`SAML Name ID or Email`) |
| m365 | M365 | XLSX, вкладка `Licenses by user` | Последнее слово столбца A (`User`), фильтр SKU=`SPE_E3` |
| powerbi | Power BI | XLSX, вкладка `Licenses by user` | Последнее слово столбца A (`User`), фильтр SKU=`POWER_BI_PRO` |
| mattermost | Mattermost | CSV/XLSX | Столбец A (`NickName`), все пользователи без фильтров |
| testit | TestIT | CSV/XLSX | Столбец A (`Nickname`) |
| 1c | 1С Лицензии | XLSX | Столбец A (`ФизЛицо`), очистка скобок |
| jira | Jira + Confluence | XLSX | Столбец A (`ФизЛицо`), очистка скобок |

## Справочник сотрудников

- Файл: `Список_сотрудников.xlsx`, лист `TDSheet`
- Столбец A (`ФизЛицо`) → ник. Очистка: удаление `(...)` скобок, lowercase
- Столбец C (`ЦФО`) → ЦФО. Если пустой → `ПП НЕО`
- Столбец B (`Подразделение`) → подразделение
- Берём ВСЕХ сотрудников (без фильтра по `Работает`)

## Формат Excel для финансов

Столбцы: `Продукты ТХ` (ПО {сервис}), `Nickname / Наименование`, `Потребитель` (ЦФО), `Единица продукта` (1 лицензия), `Количество` (1), `Цена`, `Стоимость`, `Комментарий`, `Свободное поле`

## Что нужно сделать — миграция на PostgreSQL

### Схема БД (7 таблиц)

```sql
-- Справочник сервисов
CREATE TABLE services (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    accept_formats VARCHAR NOT NULL
);

-- Отчётные периоды
CREATE TABLE reports (
    id SERIAL PRIMARY KEY,
    month VARCHAR UNIQUE NOT NULL,  -- '2026-06'
    status VARCHAR NOT NULL DEFAULT 'draft',  -- draft / finalized
    created_at TIMESTAMP DEFAULT NOW(),
    finalized_at TIMESTAMP
);

-- Снимок справочника сотрудников на период
CREATE TABLE report_employees (
    report_id INT REFERENCES reports(id),
    nick VARCHAR NOT NULL,
    cfo VARCHAR NOT NULL,
    dept VARCHAR DEFAULT '',
    PRIMARY KEY (report_id, nick)
);

-- Доп. пользователи на период
CREATE TABLE report_extra_users (
    report_id INT REFERENCES reports(id),
    nick VARCHAR NOT NULL,
    service_id VARCHAR REFERENCES services(id),
    cfo VARCHAR NOT NULL,
    PRIMARY KEY (report_id, service_id, nick)
);

-- Цены на период
CREATE TABLE report_prices (
    report_id INT REFERENCES reports(id),
    service_id VARCHAR REFERENCES services(id),
    price NUMERIC NOT NULL DEFAULT 0,
    PRIMARY KEY (report_id, service_id)
);

-- Прогресс загрузки файлов
CREATE TABLE service_uploads (
    report_id INT REFERENCES reports(id),
    service_id VARCHAR REFERENCES services(id),
    filename VARCHAR NOT NULL,
    row_count INT NOT NULL,
    uploaded_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (report_id, service_id)
);

-- Основные данные биллинга
CREATE TABLE billing_entries (
    id SERIAL PRIMARY KEY,
    report_id INT REFERENCES reports(id),
    service_id VARCHAR REFERENCES services(id),
    nick VARCHAR NOT NULL,
    cfo VARCHAR NOT NULL,
    source VARCHAR NOT NULL,  -- employee / extra / not_found
    UNIQUE (report_id, service_id, nick)
);
```

### Начальные данные для services

```sql
INSERT INTO services VALUES
('google', 'Google Workspace', 'csv,xlsx'),
('miro', 'Miro', 'csv,xlsx'),
('github', 'GitHub', 'xlsx'),
('copilot', 'GitHub Copilot', 'xlsx'),
('m365', 'M365', 'xlsx'),
('powerbi', 'Power BI', 'xlsx'),
('mattermost', 'Mattermost', 'csv,xlsx'),
('testit', 'TestIT', 'csv,xlsx'),
('1c', '1С Лицензии', 'xlsx'),
('jira', 'Jira + Confluence', 'xlsx');
```

### Правила бизнес-логики

1. Нельзя создать новый draft, пока предыдущий не finalized
2. При создании нового периода — копировать extra_users и prices из предыдущего
3. При перезагрузке файла сервиса — DELETE старых billing_entries + service_uploads, INSERT новых
4. При финализации — пересчитать cfo в billing_entries по report_employees + report_extra_users
5. При финализации — предупреждение если загружены не все сервисы (не блокировка, именно предупреждение)
6. Финализированный отчёт — только чтение
7. Кнопка «Вернуть в draft» для исправлений

### План реализации (шаги)

**Шаг 1.** Подключение к БД — psycopg2/sqlalchemy, конфиг через .env файл
**Шаг 2.** Скрипт миграции — создание таблиц + начальные данные
**Шаг 3.** UI управления периодами — создать/выбрать/финализировать
**Шаг 4.** Парсеры пишут в БД вместо памяти
**Шаг 5.** Справочник и extra_users через БД
**Шаг 6.** Цены через БД
**Шаг 7.** Генерация отчётов из БД
**Шаг 8.** История и аналитика (сравнение месяцев)

### Подключение к PostgreSQL

Пользователь поднял PostgreSQL локально. Нужно спросить:
- Порт (обычно 5432)
- Имя базы данных
- Имя пользователя
- Пароль — через .env файл, НЕ хранить в коде

### Важные решения

- Тема оформления (light/dark/accent) остаётся через CSS, не в БД
- HTML-отчёты по отделам: акцентная тема, раскрывающиеся списки пользователей по клику, итого только стоимость
- Все комменты в коде на русском языке
