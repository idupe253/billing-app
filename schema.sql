-- Схема БД Billing Automation.
-- Идемпотентна (IF NOT EXISTS) — можно прогонять повторно.
-- Наполнение таблицы services делается из кода (services.py) при старте,
-- здесь только структура.

-- Справочник сервисов (метаданные; парсеры — в коде app.py)
CREATE TABLE IF NOT EXISTS services (
    id             VARCHAR PRIMARY KEY,        -- 'google' (стабилен, FK во всей истории)
    name           VARCHAR NOT NULL,           -- 'Google Workspace'
    accept_formats VARCHAR NOT NULL            -- 'csv,xlsx'
);

-- Отчётные периоды (месяцы)
CREATE TABLE IF NOT EXISTS reports (
    id           SERIAL PRIMARY KEY,
    month        VARCHAR UNIQUE NOT NULL,             -- '2026-06'
    status       VARCHAR NOT NULL DEFAULT 'draft',    -- draft / finalized
    created_at   TIMESTAMP DEFAULT NOW(),
    finalized_at TIMESTAMP
);

-- Снимок справочника сотрудников на период
CREATE TABLE IF NOT EXISTS report_employees (
    report_id INT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    nick      VARCHAR NOT NULL,
    cfo       VARCHAR NOT NULL,
    dept      VARCHAR DEFAULT '',
    PRIMARY KEY (report_id, nick)
);

-- Доп. (вручную назначенные) пользователи на период
CREATE TABLE IF NOT EXISTS report_extra_users (
    report_id  INT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    nick       VARCHAR NOT NULL,
    service_id VARCHAR NOT NULL REFERENCES services(id),
    cfo        VARCHAR NOT NULL,
    PRIMARY KEY (report_id, service_id, nick)
);

-- Цены за лицензию на период
CREATE TABLE IF NOT EXISTS report_prices (
    report_id  INT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    service_id VARCHAR NOT NULL REFERENCES services(id),
    price      NUMERIC NOT NULL DEFAULT 0,
    PRIMARY KEY (report_id, service_id)
);

-- Прогресс загрузки файлов сервисов
CREATE TABLE IF NOT EXISTS service_uploads (
    report_id   INT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    service_id  VARCHAR NOT NULL REFERENCES services(id),
    filename    VARCHAR NOT NULL,
    row_count   INT NOT NULL,
    uploaded_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (report_id, service_id)
);

-- Основные данные биллинга
CREATE TABLE IF NOT EXISTS billing_entries (
    id         SERIAL PRIMARY KEY,
    report_id  INT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    service_id VARCHAR NOT NULL REFERENCES services(id),
    nick       VARCHAR NOT NULL,
    cfo        VARCHAR NOT NULL,
    source     VARCHAR NOT NULL,                       -- employee / extra / not_found
    UNIQUE (report_id, service_id, nick)
);

-- Индекс для частых выборок по периоду+сервису
CREATE INDEX IF NOT EXISTS idx_billing_report_service
    ON billing_entries (report_id, service_id);
