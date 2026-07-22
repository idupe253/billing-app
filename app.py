import streamlit as st
import pandas as pd
import re
import json
import zipfile
from io import BytesIO
from pathlib import Path
from datetime import datetime

from services import SERVICES, SVC_ID_TO_NAME
import periods
import billing
import analytics

# ─── Конфигурация ─────────────────────────────────────────────────────────────

st.set_page_config(page_title="⚡ Billing Automation", layout="wide")

# Тема оформления хранится в JSON (сознательно не в БД — решение из CLAUDE.md)
THEME_FILE = Path("theme.json")

# Реестр сервисов вынесен в services.py (см. импорт выше)

# ─── Вспомогательные функции ──────────────────────────────────────────────────

def clean_nick(raw: str) -> str:
    """Очистка ника: удаление скобок, приведение к нижнему регистру."""
    if not raw or not isinstance(raw, str):
        raw = str(raw) if raw is not None else ""
    return re.sub(r"\(.*?\)", "", raw).strip().lower()


def parse_cfo(val) -> str:
    """Получение ЦФО, если пусто — ПП НЕО."""
    if val and str(val).strip():
        return str(val).strip()
    return "ПП НЕО"


def parse_price(raw: str):
    """Парсинг цены из строки. Возвращает float или None, если не распознать.

    Поддерживает разделители тысяч пробелами (в т.ч. неразрывными) и запятую
    как десятичный разделитель: '1 200,50' → 1200.5, '581.78' → 581.78.
    """
    s = (raw or "").strip()
    if not s:
        return None
    s = re.sub(r"[\s  ]", "", s)  # убрать пробелы — разделители тысяч
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def read_file(uploaded, sheet_name=0) -> pd.DataFrame:
    """Чтение загруженного файла (CSV или XLSX) в DataFrame.

    Для CSV разделитель определяется автоматически (запятая или точка с запятой),
    BOM убирается (encoding utf-8-sig).
    """
    name = uploaded.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(
            uploaded, dtype=str, sep=None, engine="python", encoding="utf-8-sig"
        ).fillna("")
    else:
        return pd.read_excel(uploaded, sheet_name=sheet_name, dtype=str).fillna("")

# Доп. пользователи и цены теперь хранятся в БД (report_extra_users / report_prices) — см. billing.py


def load_theme() -> str:
    """Загрузка выбранной темы."""
    if THEME_FILE.exists():
        try:
            data = json.loads(THEME_FILE.read_text(encoding="utf-8"))
            return data.get("theme", "accent")
        except Exception:
            pass
    return "accent"


def save_theme(theme: str):
    """Сохранение выбранной темы."""
    THEME_FILE.write_text(json.dumps({"theme": theme}), encoding="utf-8")


# ─── CSS темы для Streamlit UI ────────────────────────────────────────────────

STREAMLIT_THEMES = {
    "light": """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap');
    .stApp { background: #f5f3f7; }
    .stApp > header { background: #f5f3f7; }
    .stSidebar > div:first-child { background: #edeaf2; }
    .stMarkdown, .stMarkdown p, .stCaption, .stAlert p,
    h1, h2, h3, h4,
    .stTabs [data-baseweb="tab"],
    .stButton > button,
    .stDownloadButton > button,
    .stTextInput label, .stSelectbox label, .stFileUploader label,
    .stRadio label, .stCheckbox label,
    div[data-testid="stMetricValue"],
    .stDataFrame th {
        font-family: 'Montserrat', 'Segoe UI', system-ui, sans-serif !important;
    }
    h1, h2, h3 { color: #2d2640 !important; }
    .stTabs [aria-selected="true"] { border-bottom-color: #7c3aed !important; color: #7c3aed !important; }
    .stButton > button[kind="primary"] { background-color: #7c3aed !important; border-color: #7c3aed !important; }
    .stButton > button[kind="primary"]:hover { background-color: #6d28d9 !important; }
    .stDownloadButton > button { border-color: #7c3aed !important; color: #7c3aed !important; }
    div[data-testid="stExpander"] { border-color: #e8e4ef !important; }
    </style>
    """,
    "dark": """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap');
    .stApp { background: #1a1625; color: #e8e4ef; }
    .stApp > header { background: #1a1625; }
    .stSidebar > div:first-child { background: #231e30; }
    .stMarkdown, .stMarkdown p, .stCaption, .stAlert p,
    h1, h2, h3, h4,
    .stTabs [data-baseweb="tab"],
    .stButton > button,
    .stDownloadButton > button,
    .stTextInput label, .stSelectbox label, .stFileUploader label,
    .stRadio label, .stCheckbox label,
    div[data-testid="stMetricValue"],
    .stDataFrame th {
        font-family: 'Montserrat', 'Segoe UI', system-ui, sans-serif !important;
    }
    h1, h2, h3 { color: #e8e4ef !important; }
    .stMarkdown p, .stMarkdown li, .stMarkdown span,
    .stCaption, .stCaption p,
    .stAlert p,
    .stTextInput label, .stSelectbox label, .stFileUploader label,
    .stRadio label, .stRadio label span, .stCheckbox label,
    div[data-testid="stMetricLabel"], div[data-testid="stMetricValue"],
    .stFileUploader section > div,
    .stSidebar p, .stSidebar label, .stSidebar span,
    .stSidebar .stMarkdown p, .stSidebar .stCaption {
        color: #e8e4ef !important;
    }
    small, .stCaption small, .stFileUploader small { color: #9b93a8 !important; }
    .stTabs [data-baseweb="tab"] { color: #9b93a8 !important; }
    .stTabs [aria-selected="true"] { border-bottom-color: #a78bfa !important; color: #a78bfa !important; }
    .stButton > button[kind="primary"] { background-color: #7c3aed !important; border-color: #7c3aed !important; color: #fff !important; }
    .stButton > button[kind="primary"]:hover { background-color: #6d28d9 !important; }
    .stButton > button { color: #e8e4ef !important; border-color: #342d45 !important; }
    .stDownloadButton > button { border-color: #a78bfa !important; color: #a78bfa !important; }
    div[data-testid="stExpander"] { border-color: #342d45 !important; }
    div[data-testid="stExpander"] summary span { color: #e8e4ef !important; }
    .stTextInput > div > div > input { background: #231e30 !important; color: #e8e4ef !important; border-color: #342d45 !important; }
    .stSelectbox > div > div { background: #231e30 !important; color: #e8e4ef !important; }
    .stSelectbox > div > div > div { color: #e8e4ef !important; }
    div[data-testid="stDataFrame"] { background: #231e30 !important; }
    .stAlert { background: #2d2545 !important; color: #e8e4ef !important; }
    .stDivider { border-color: #342d45 !important; }
    hr { border-color: #342d45 !important; }
    .stSidebar hr { border-color: #342d45 !important; }
    .stFileUploader > section { background: #231e30 !important; border-color: #342d45 !important; }
    </style>
    """,
    "accent": """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap');
    .stApp { background: #f7f5fa; }
    .stApp > header { background: #f7f5fa; }
    .stSidebar > div:first-child { background: #f0eafc; }
    .stMarkdown, .stMarkdown p, .stCaption, .stAlert p,
    h1, h2, h3, h4,
    .stTabs [data-baseweb="tab"],
    .stButton > button,
    .stDownloadButton > button,
    .stTextInput label, .stSelectbox label, .stFileUploader label,
    .stRadio label, .stCheckbox label,
    div[data-testid="stMetricValue"],
    .stDataFrame th {
        font-family: 'Montserrat', 'Segoe UI', system-ui, sans-serif !important;
    }
    h1, h2, h3 { color: #1e1535 !important; }
    .stTabs [aria-selected="true"] { border-bottom-color: #7c3aed !important; color: #7c3aed !important; }
    .stButton > button[kind="primary"] { background-color: #7c3aed !important; border-color: #7c3aed !important; }
    .stButton > button[kind="primary"]:hover { background-color: #6d28d9 !important; }
    .stDownloadButton > button { border-color: #7c3aed !important; color: #7c3aed !important; }
    div[data-testid="stExpander"] { border-color: #ddd6ec !important; }
    </style>
    """,
}

# ─── Парсер справочника сотрудников ──────────────────────────────────────────

def parse_db_users(uploaded) -> pd.DataFrame:
    """Парсинг файла сотрудников (1С). Столбец A — ник, C — ЦФО.

    Данные на листе TDSheet; если такого листа нет — берём первый лист.
    """
    xls = pd.ExcelFile(uploaded)
    sheet = "TDSheet" if "TDSheet" in xls.sheet_names else xls.sheet_names[0]
    df = pd.read_excel(xls, sheet_name=sheet, dtype=str).fillna("")
    col_a = df.columns[0]  # ФизЛицо
    col_b = df.columns[1]  # Подразделение
    col_c = df.columns[2]  # ЦФО

    records = []
    for _, row in df.iterrows():
        nick = clean_nick(row[col_a])
        if not nick:
            continue
        records.append({
            "nick": nick,
            "dept": str(row[col_b]).strip(),
            "cfo": parse_cfo(row[col_c]),
        })
    return pd.DataFrame(records)

# ─── Парсеры сервисов ─────────────────────────────────────────────────────────

def parse_google(uploaded) -> list[str]:
    """Google Workspace: ник из столбца B (Last Name [Required])."""
    df = read_file(uploaded)
    col = "Last Name [Required]" if "Last Name [Required]" in df.columns else df.columns[1]
    nicks = df[col].str.strip().str.lower().tolist()
    return sorted(set(n for n in nicks if n))


def parse_miro(uploaded) -> list[str]:
    """Miro: ник — последнее слово из столбца A (Name)."""
    df = read_file(uploaded)
    col = "Name" if "Name" in df.columns else df.columns[0]
    nicks = []
    for val in df[col]:
        val = str(val).strip()
        if not val:
            continue
        parts = val.split()
        nick = parts[-1].lower() if len(parts) > 1 else parts[0].lower()
        if nick:
            nicks.append(nick)
    return sorted(set(nicks))


def parse_github(uploaded) -> list[str]:
    """GitHub: ник из столбца F (SAML Name ID), фоллбэк на столбец A (login)."""
    df = read_file(uploaded, sheet_name=0)
    nicks = []
    saml_col = "GitHub com saml name ID" if "GitHub com saml name ID" in df.columns else None
    login_col = "GitHub com login" if "GitHub com login" in df.columns else df.columns[0]
    for _, row in df.iterrows():
        saml = str(row.get(saml_col, "")).strip() if saml_col else ""
        login = str(row.get(login_col, "")).strip()
        nick = (saml or login).lower()
        nick = nick.split("@")[0]  # SAML приходит как почта — отрезаем домен @deeplay.io
        if nick:
            nicks.append(nick)
    return sorted(set(nicks))


def parse_copilot(uploaded) -> list[str]:
    """GitHub Copilot: ник из столбца C (SAML Name ID or Email), вкладка Copilot Usage."""
    df = read_file(uploaded, sheet_name="Copilot Usage")
    col = "SAML Name ID or Email" if "SAML Name ID or Email" in df.columns else df.columns[2]
    # Значение приходит как почта — отрезаем домен, берём часть до @
    nicks = df[col].str.strip().str.lower().str.split("@").str[0].tolist()
    return sorted(set(n for n in nicks if n))


def _parse_azure_sheet(uploaded) -> pd.DataFrame:
    """Общее чтение вкладки Licenses by user из файла Azure."""
    return read_file(uploaded, sheet_name="Licenses by user")


def parse_m365(uploaded) -> list[str]:
    """M365: фильтр SKU = SPE_E3, ник — последнее слово из столбца A (User)."""
    df = _parse_azure_sheet(uploaded)
    sku_col = "SKU" if "SKU" in df.columns else df.columns[3]
    user_col = "User" if "User" in df.columns else df.columns[0]
    mask = df[sku_col].str.strip() == "SPE_E3"
    nicks = []
    for val in df.loc[mask, user_col]:
        parts = str(val).strip().split()
        nick = parts[-1].lower() if len(parts) > 1 else parts[0].lower()
        if nick:
            nicks.append(nick)
    return sorted(set(nicks))


def parse_powerbi(uploaded) -> list[str]:
    """Power BI: фильтр SKU = POWER_BI_PRO, ник — последнее слово из столбца A (User)."""
    df = _parse_azure_sheet(uploaded)
    sku_col = "SKU" if "SKU" in df.columns else df.columns[3]
    user_col = "User" if "User" in df.columns else df.columns[0]
    mask = df[sku_col].str.strip() == "POWER_BI_PRO"
    nicks = []
    for val in df.loc[mask, user_col]:
        parts = str(val).strip().split()
        nick = parts[-1].lower() if len(parts) > 1 else parts[0].lower()
        if nick:
            nicks.append(nick)
    return sorted(set(nicks))


def parse_mattermost(uploaded) -> list[dict]:
    """Mattermost: ник из столбца B (Username), роль из столбца F (Roles).

    Возвращает список dict {"nick", "comment"}, где comment — роль:
    'guest' если в Roles есть system_guest, иначе 'member'. Все пользователи.
    """
    df = read_file(uploaded)
    user_col = "Username" if "Username" in df.columns else df.columns[1]
    roles_col = "Roles" if "Roles" in df.columns else (
        df.columns[5] if len(df.columns) > 5 else None
    )
    records: dict[str, dict] = {}
    for _, row in df.iterrows():
        nick = str(row[user_col]).strip().lower()
        if not nick:
            continue
        role = ""
        if roles_col is not None:
            role = "guest" if "system_guest" in str(row[roles_col]) else "member"
        records[nick] = {"nick": nick, "comment": role}
    return sorted(records.values(), key=lambda r: r["nick"])


def parse_testit(uploaded) -> list[str]:
    """TestIT: ник из столбца A (Nickname)."""
    df = read_file(uploaded)
    col = "Nickname" if "Nickname" in df.columns else df.columns[0]
    nicks = df[col].str.strip().str.lower().tolist()
    return sorted(set(n for n in nicks if n))


def parse_nick_from_col_a(uploaded) -> list[str]:
    """1С / Jira: ник из столбца A (ФизЛицо) с очисткой скобок.

    Записи без настоящего ника (в ячейке ФИО — несколько слов через пробел)
    исключаем: берём только однословные ники.
    """
    df = read_file(uploaded)
    col = "ФизЛицо" if "ФизЛицо" in df.columns else df.columns[0]
    nicks = [clean_nick(v) for v in df[col]]
    return sorted(set(n for n in nicks if n and " " not in n))


PARSERS = {
    "google": parse_google,
    "miro": parse_miro,
    "github": parse_github,
    "copilot": parse_copilot,
    "m365": parse_m365,
    "powerbi": parse_powerbi,
    "mattermost": parse_mattermost,
    "testit": parse_testit,
    "1c": parse_nick_from_col_a,
    "jira": parse_nick_from_col_a,
}

# ─── Построение отчёта ────────────────────────────────────────────────────────

def _dept_of(row: dict) -> str:
    """ЦФО записи биллинга: реальный cfo или «Не найден» для not_found."""
    return row["cfo"] if row["source"] != "not_found" else "Не найден"


def build_report(report_id: int) -> dict[str, pd.DataFrame]:
    """Построение всех листов отчёта из данных периода (Вариант Б).

    cfo/source берутся из billing_entries (посчитаны recompute_billing),
    повторно в коде не вычисляются. Возвращает {имя_листа: DataFrame}.
    """
    entries = billing.get_entries(report_id)        # service_id -> [{nick,cfo,source}]
    prices = billing.get_prices(report_id)          # {service_id: float}
    employees = billing.get_employees_df(report_id)  # DataFrame[nick,cfo,dept]
    extra_db = billing.get_extra_db(report_id)       # {nick:{cfo,services}}

    # ЦФО для общей сводки: из справочника + из доп-юзеров
    all_cfos = sorted(
        set(employees["cfo"].tolist()) | {e["cfo"] for e in extra_db.values()}
    )
    # Сервисы в порядке реестра, только реально загруженные
    svc_ids = [s["id"] for s in SERVICES if s["id"] in entries]

    sheets: dict[str, pd.DataFrame] = {}
    summary_data: dict[str, dict[str, int]] = {}
    all_not_found: dict[str, set] = {}

    for svc_id in svc_ids:
        svc_name = SVC_ID_TO_NAME.get(svc_id, svc_id)
        rows = entries[svc_id]
        dept_count: dict[str, int] = {}
        user_rows = []

        for row in rows:
            dept = _dept_of(row)
            if row["source"] == "not_found":
                all_not_found.setdefault(row["nick"], set()).add(svc_name)
            dept_count[dept] = dept_count.get(dept, 0) + 1
            user_rows.append({"Nickname": row["nick"], "ЦФО": dept})

        summary_data[svc_name] = dept_count

        # Лист пользователей
        if user_rows:
            sheets[f"User list {svc_name}"] = pd.DataFrame(user_rows)

        # Сводная таблица
        total = len(rows)
        price = prices.get(svc_id, 0)
        pivot_rows = [
            {
                "ЦФО": d,
                "Кол-во": c,
                "%": f"{c / total * 100:.1f}%" if total else "0%",
                "Стоимость": round(c * price, 2) if price else "",
            }
            for d, c in sorted(dept_count.items())
        ]
        pivot_rows.append({
            "ЦФО": "ИТОГО",
            "Кол-во": total,
            "%": "100%",
            "Стоимость": round(total * price, 2) if price else "",
        })
        sheets[f"Pivot {svc_name}"] = pd.DataFrame(pivot_rows)

    # Общая сводка
    svc_names = [SVC_ID_TO_NAME.get(sid, sid) for sid in svc_ids]
    summary_rows = []
    for dept in all_cfos:
        row = {"ЦФО": dept}
        for svc_name in svc_names:
            row[svc_name] = summary_data.get(svc_name, {}).get(dept, 0)
        summary_rows.append(row)
    totals = {"ЦФО": "ИТОГО"}
    for svc_name in svc_names:
        totals[svc_name] = sum(summary_data.get(svc_name, {}).values())
    summary_rows.append(totals)

    # Строка стоимости по сервисам
    cost_row = {"ЦФО": "Стоимость"}
    has_any_price = False
    for svc_id in svc_ids:
        svc_name = SVC_ID_TO_NAME.get(svc_id, svc_id)
        price = prices.get(svc_id, 0)
        total_count = sum(summary_data.get(svc_name, {}).values())
        cost_row[svc_name] = round(total_count * price, 2) if price else ""
        if price:
            has_any_price = True
    if has_any_price:
        summary_rows.append(cost_row)

    sheets["Общая сводка"] = pd.DataFrame(summary_rows)

    # Не найденные
    nf_rows = [{"Nickname": n, "Сервисы": ", ".join(sorted(s))} for n, s in sorted(all_not_found.items())]
    if nf_rows:
        sheets["Не найдены"] = pd.DataFrame(nf_rows)

    # Доп DB по сервисам (из записей source='extra')
    for svc_id in svc_ids:
        svc_name = SVC_ID_TO_NAME.get(svc_id, svc_id)
        extra_rows = [
            {"Nickname": r["nick"], "ЦФО": r["cfo"]}
            for r in entries[svc_id] if r["source"] == "extra"
        ]
        if extra_rows:
            sheets[f"Доп DB {svc_name}"] = pd.DataFrame(extra_rows)

    # Общий список: основной справочник + доп. пользователи
    db_rows = employees[["nick", "cfo", "dept"]].rename(
        columns={"nick": "Nickname", "cfo": "ЦФО", "dept": "Подразделение"}
    ).copy()
    db_rows["Источник"] = "1С"
    extra_rows_list = [
        {"Nickname": nick, "ЦФО": entry["cfo"], "Подразделение": "", "Источник": "Доп DB"}
        for nick, entry in extra_db.items()
    ]
    if extra_rows_list:
        db_rows = pd.concat([db_rows, pd.DataFrame(extra_rows_list)], ignore_index=True)
    db_rows = db_rows.sort_values("Nickname").reset_index(drop=True)
    sheets["DB Users"] = db_rows

    # Сводный лист в формате для финансов (все отделы, все сервисы)
    finance_rows = []
    for svc_id in svc_ids:
        svc_name = SVC_ID_TO_NAME.get(svc_id, svc_id)
        price = prices.get(svc_id, 0)
        cost = round(price, 2) if price else ""
        for row in entries[svc_id]:
            finance_rows.append({
                "Продукты ТХ": f"ПО {svc_name}",
                "Nickname / Наименование": row["nick"],
                "Потребитель": _dept_of(row),
                "Единица продукта": "1 лицензия",
                "Количество": 1,
                "Цена": cost,
                "Стоимость": cost,
                "Комментарий": row.get("comment") or "",
                "Свободное поле": "",
            })
    if finance_rows:
        sheets["Для финансов"] = pd.DataFrame(finance_rows)

    return sheets


def sheets_to_excel(sheets: dict[str, pd.DataFrame]) -> bytes:
    """Конвертация листов в Excel-файл (bytes)."""
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in sheets.items():
            sheet_name = name[:31]
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            ws = writer.sheets[sheet_name]
            for i, col in enumerate(df.columns):
                max_len = max(len(str(col)), df[col].astype(str).str.len().max() if len(df) else 0)
                col_letter = chr(65 + i) if i < 26 else f"A{chr(65 + i - 26)}"
                ws.column_dimensions[col_letter].width = min(max_len + 3, 40)
    return buf.getvalue()

# ─── Генерация отчёта по отделу (HTML + XLSX) ────────────────────────────────

def build_dept_html(dept: str, entries: dict, prices: dict, theme: str = "light") -> str:
    """Генерация HTML-отчёта для отдела. Темы: light, dark, accent."""
    date_str = datetime.now().strftime("%d.%m.%Y")

    # Цветовые схемы в стиле брендбука (Montserrat, фиолетовый акцент, мягкие тона)
    themes = {
        "light": {
            "bg": "#f5f3f7", "card": "#ffffff", "text": "#2d2640", "text2": "#6b6480",
            "border": "#e8e4ef", "accent": "#7c3aed", "accent_light": "#f3eeff",
            "hover": "#f9f7fc", "user_bg": "#faf8fe", "user_text": "#5b5272",
            "total_bg": "#f3eeff", "th_bg": "#f8f6fb", "th_text": "#7c6f96",
        },
        "dark": {
            "bg": "#1a1625", "card": "#231e30", "text": "#e8e4ef", "text2": "#9b93a8",
            "border": "#342d45", "accent": "#a78bfa", "accent_light": "#2d2545",
            "hover": "#2a2438", "user_bg": "#1e1a2a", "user_text": "#b0a8c0",
            "total_bg": "#2d2545", "th_bg": "#1e1a2a", "th_text": "#9b93a8",
        },
        "accent": {
            "bg": "#f7f5fa", "card": "#ffffff", "text": "#1e1535", "text2": "#6b6480",
            "border": "#ddd6ec", "accent": "#7c3aed", "accent_light": "#ede5ff",
            "hover": "#f5f0ff", "user_bg": "#f9f5ff", "user_text": "#5b4a80",
            "total_bg": "#7c3aed", "th_bg": "#f0eafc", "th_text": "#6b5a9e",
            "total_text": "#ffffff",
        },
    }
    t = themes.get(theme, themes["light"])
    total_text = t.get("total_text", t["text"])

    rows_html = ""
    total_cost = 0.0

    for svc in SERVICES:
        svc_id = svc["id"]
        if svc_id not in entries:
            continue
        svc_name = SVC_ID_TO_NAME.get(svc_id, svc_id)

        dept_nicks = [r["nick"] for r in entries[svc_id] if _dept_of(r) == dept]
        count = len(dept_nicks)
        if count == 0:
            continue

        price = prices.get(svc_id, 0)
        cost = round(count * price, 2) if price else 0
        total_cost += cost
        cost_str = f"{cost:,.2f} ₽" if price else "—"
        price_str = f"{price:,.2f} ₽" if price else "—"

        # Список пользователей — колонкой
        user_list_html = "".join(f"<li>{n}</li>" for n in dept_nicks)
        svc_id_safe = re.sub(r'\W', '_', svc_id)

        rows_html += f"""
        <tr class="svc-row" onclick="toggle('{svc_id_safe}')">
            <td><span class="arrow" id="arrow_{svc_id_safe}">▶</span> {svc_name}</td>
            <td style="text-align:center">{count}</td>
            <td style="text-align:right">{price_str}</td>
            <td style="text-align:right">{cost_str}</td>
        </tr>
        <tr class="user-row" id="users_{svc_id_safe}" style="display:none">
            <td colspan="4">
                <ul class="user-list">{user_list_html}</ul>
            </td>
        </tr>"""

    if not rows_html:
        return ""

    total_cost_str = f"{total_cost:,.2f} ₽" if total_cost else "—"

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Биллинг — {dept}</title>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Montserrat', 'Segoe UI', system-ui, sans-serif; background: {t['bg']}; color: {t['text']}; padding: 40px; }}
  .container {{ max-width: 800px; margin: 0 auto; background: {t['card']}; border-radius: 16px; box-shadow: 0 4px 24px rgba(124,58,237,0.06); padding: 44px; }}
  .header {{ border-bottom: 2px solid {t['border']}; padding-bottom: 20px; margin-bottom: 24px; }}
  .header h1 {{ font-size: 21px; font-weight: 700; color: {t['text']}; }}
  .header .meta {{ font-size: 13px; color: {t['text2']}; margin-top: 6px; }}
  .accent-bar {{ width: 48px; height: 3px; background: {t['accent']}; border-radius: 2px; margin-bottom: 14px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
  th {{ background: {t['th_bg']}; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: {t['th_text']}; padding: 10px 14px; text-align: left; border-bottom: 2px solid {t['border']}; }}
  td {{ padding: 11px 14px; border-bottom: 1px solid {t['border']}; font-size: 14px; color: {t['text']}; }}
  .svc-row {{ cursor: pointer; transition: background 0.15s; }}
  .svc-row:hover {{ background: {t['hover']}; }}
  .arrow {{ display: inline-block; font-size: 11px; margin-right: 6px; transition: transform 0.2s; color: {t['accent']}; }}
  .arrow.open {{ transform: rotate(90deg); }}
  .user-list {{ list-style: none; padding: 10px 0 10px 28px; margin: 0; }}
  .user-list li {{ font-size: 13px; color: {t['user_text']}; padding: 3px 0; }}
  .user-row td {{ background: {t['user_bg']}; padding: 0 14px; border-bottom: 1px solid {t['border']}; }}
  .total {{ font-weight: 700; background: {t['total_bg']}; }}
  .total td {{ border-top: 2px solid {t['border']}; padding-top: 12px; color: {total_text}; }}
  .footer {{ margin-top: 28px; font-size: 11px; color: {t['text2']}; text-align: center; letter-spacing: 0.02em; }}
</style>
<script>
function toggle(id) {{
  var row = document.getElementById('users_' + id);
  var arrow = document.getElementById('arrow_' + id);
  if (row.style.display === 'none') {{
    row.style.display = 'table-row';
    arrow.classList.add('open');
  }} else {{
    row.style.display = 'none';
    arrow.classList.remove('open');
  }}
}}
</script>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="accent-bar"></div>
    <h1>Биллинг IT-сервисов — {dept}</h1>
    <div class="meta">Период: {date_str}</div>
  </div>
  <table>
    <thead>
      <tr><th>Сервис</th><th style="text-align:center">Лицензии</th><th style="text-align:right">Цена/шт</th><th style="text-align:right">Стоимость</th></tr>
    </thead>
    <tbody>
      {rows_html}
      <tr class="total">
        <td>ИТОГО</td>
        <td></td>
        <td></td>
        <td style="text-align:right">{total_cost_str}</td>
      </tr>
    </tbody>
  </table>
  <div class="footer">Billing Automation Tool</div>
</div>
</body>
</html>"""
    return html


def build_dept_excel(dept: str, entries: dict, prices: dict) -> bytes:
    """Генерация Excel для отдела в формате для финансов."""
    all_rows = []
    for svc in SERVICES:
        svc_id = svc["id"]
        if svc_id not in entries:
            continue
        svc_name = SVC_ID_TO_NAME.get(svc_id, svc_id)
        price = prices.get(svc_id, 0)
        cost = round(price, 2) if price else ""
        for r in entries[svc_id]:
            if _dept_of(r) == dept:
                all_rows.append({
                    "Продукты ТХ": f"ПО {svc_name}",
                    "Nickname / Наименование": r["nick"],
                    "Потребитель": dept,
                    "Единица продукта": "1 лицензия",
                    "Количество": 1,
                    "Цена": cost,
                    "Стоимость": cost,
                    "Комментарий": r.get("comment") or "",
                    "Свободное поле": "",
                })

    if not all_rows:
        all_rows.append({
            "Продукты ТХ": "", "Nickname / Наименование": "", "Потребитель": dept,
            "Единица продукта": "", "Количество": "", "Цена": "",
            "Стоимость": "", "Комментарий": "", "Свободное поле": "",
        })

    return sheets_to_excel({"Лицензии": pd.DataFrame(all_rows)})


def build_general_excel(report_id: int) -> bytes:
    """Общий Excel в формате отчётов по отделам, но одним листом и по порядку систем.

    Строки идут по порядку сервисов (реестр SERVICES): сначала все записи Google,
    потом M365 и т.д. — без разбивки по отделам. Потребитель = реальный ЦФО записи
    (или «Не найден»). Формат столбцов — как в отчётах по отделам (для финансов).
    """
    entries = billing.get_entries(report_id)
    prices = billing.get_prices(report_id)

    all_rows = []
    for svc in SERVICES:
        svc_id = svc["id"]
        if svc_id not in entries:
            continue
        svc_name = SVC_ID_TO_NAME.get(svc_id, svc_id)
        price = prices.get(svc_id, 0)
        cost = round(price, 2) if price else ""
        for r in entries[svc_id]:
            if r["source"] == "not_found":
                continue  # пользователи без найденного отдела в общий файл не попадают
            all_rows.append({
                "Продукты ТХ": f"ПО {svc_name}",
                "Nickname / Наименование": r["nick"],
                "Потребитель": _dept_of(r),
                "Единица продукта": "1 лицензия",
                "Количество": 1,
                "Цена": cost,
                "Стоимость": cost,
                "Комментарий": r.get("comment") or "",
                "Свободное поле": "",
            })

    return sheets_to_excel({"Лицензии": pd.DataFrame(all_rows)})


def build_all_dept_zip(report_id: int, theme="light") -> bytes:
    """Генерация ZIP-архива со всеми отчётами по отделам (HTML + XLSX)."""
    entries = billing.get_entries(report_id)
    prices = billing.get_prices(report_id)
    employees = billing.get_employees_df(report_id)
    extra_db = billing.get_extra_db(report_id)

    all_cfos = sorted(
        set(employees["cfo"].tolist()) | {e["cfo"] for e in extra_db.values()}
    )

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for dept in all_cfos:
            safe_name = re.sub(r'[\\/:*?"<>|]', '_', dept)

            html = build_dept_html(dept, entries, prices, theme=theme)
            if html:
                zf.writestr(f"{safe_name}/{safe_name}.html", html)

            xlsx = build_dept_excel(dept, entries, prices)
            zf.writestr(f"{safe_name}/{safe_name}.xlsx", xlsx)

    return buf.getvalue()

# ─── Вкладка «История» (аналитика по периодам) ────────────────────────────────

def render_history():
    """Динамика по месяцам: потребление лицензий по ЦФО и доходность сервисов."""
    st.subheader("📈 История по периодам")

    rev = analytics.service_revenue()
    if rev.empty:
        st.info("Пока нет данных. Загрузите хотя бы один период с сервисами.")
        return

    rev = rev.copy()
    rev["Сервис"] = rev["service_id"].map(lambda s: SVC_ID_TO_NAME.get(s, s))

    # ─── Доходность сервисов ──────────────────────────────────────────────────
    st.markdown("#### 💰 Доходность сервисов")
    cost_pivot = rev.pivot_table(
        index="month", columns="Сервис", values="cost", aggfunc="sum", fill_value=0
    ).sort_index()
    cost_pivot["ИТОГО"] = cost_pivot.sum(axis=1)

    total_by_month = cost_pivot["ИТОГО"]
    st.caption("Общая стоимость лицензий по месяцам (₽)")
    st.line_chart(total_by_month)

    st.caption("Стоимость по сервисам (₽)")
    chart_cols = [c for c in cost_pivot.columns if c != "ИТОГО"]
    st.line_chart(cost_pivot[chart_cols])
    st.dataframe(cost_pivot, use_container_width=True)

    # Кол-во лицензий по сервисам
    with st.expander("Кол-во лицензий по сервисам"):
        lic_pivot = rev.pivot_table(
            index="month", columns="Сервис", values="licenses", aggfunc="sum", fill_value=0
        ).sort_index()
        lic_pivot["ИТОГО"] = lic_pivot.sum(axis=1)
        st.dataframe(lic_pivot, use_container_width=True)

    st.divider()

    # ─── Потребление по ЦФО ───────────────────────────────────────────────────
    st.markdown("#### 🏢 Потребление лицензий по ЦФО")
    cons = analytics.cfo_consumption()

    metric = st.radio(
        "Показатель", ["Лицензии", "Стоимость, ₽"], horizontal=True, key="hist_cfo_metric"
    )
    value_col = "licenses" if metric == "Лицензии" else "cost"

    # Разбивка по сервисам за выбранный месяц: матрица ЦФО × Сервис
    detail = analytics.cfo_service_consumption()
    months_avail = sorted(detail["month"].unique().tolist(), reverse=True)
    sel_month = st.selectbox("Месяц", months_avail, key="hist_cfo_month")

    md = detail[detail["month"] == sel_month].copy()
    md["Сервис"] = md["service_id"].map(lambda s: SVC_ID_TO_NAME.get(s, s))
    # Порядок колонок-сервисов как в реестре
    svc_order = [SVC_ID_TO_NAME.get(s["id"], s["id"]) for s in SERVICES
                 if s["id"] in set(md["service_id"])]
    matrix = md.pivot_table(
        index="cfo", columns="Сервис", values=value_col, aggfunc="sum", fill_value=0
    )
    matrix = matrix.reindex(columns=svc_order, fill_value=0)
    matrix["ИТОГО"] = matrix.sum(axis=1)
    matrix = matrix.sort_values("ИТОГО", ascending=False)
    # Строка итогов по сервисам
    matrix.loc["ИТОГО"] = matrix.sum(axis=0)
    st.caption(f"ЦФО × Сервис за {sel_month} ({metric.lower()})")
    st.dataframe(matrix, use_container_width=True)

    # Сводно по месяцам (итог по ЦФО без разбивки) — в сворачиваемом блоке
    with st.expander("Сводно по месяцам (итог по ЦФО)"):
        cfo_pivot = cons.pivot_table(
            index="month", columns="cfo", values=value_col, aggfunc="sum", fill_value=0
        ).sort_index()
        cfo_pivot["ИТОГО"] = cfo_pivot.sum(axis=1)
        st.dataframe(cfo_pivot, use_container_width=True)


# ─── Управление периодами ─────────────────────────────────────────────────────

def render_period_controls():
    """Блок выбора/создания/финализации периода в сайдбаре.

    Устанавливает st.session_state.report_id (выбранный период) и
    st.session_state.report_locked (True, если период финализирован → только чтение).
    """
    st.header("🗓 Период")

    reports = periods.list_reports()

    if reports:
        # Выбор активного периода
        labels = {
            r["id"]: f"{r['month']} · {'🔒 финал' if r['status'] == 'finalized' else '✏️ draft'}"
            for r in reports
        }
        ids = [r["id"] for r in reports]
        # Сохраняем выбор между ререндерами
        default_idx = 0
        if st.session_state.get("report_id") in ids:
            default_idx = ids.index(st.session_state["report_id"])

        selected = st.selectbox(
            "Активный период",
            ids,
            index=default_idx,
            format_func=lambda i: labels[i],
            key="period_select",
        )
        st.session_state.report_id = selected
        current = next(r for r in reports if r["id"] == selected)
        st.session_state.report_locked = current["status"] == "finalized"
        st.session_state.report_month = current["month"]

        # Действия над выбранным периодом
        if current["status"] == "draft":
            miss = periods.missing_services(selected)
            if miss:
                names = ", ".join(SVC_ID_TO_NAME.get(m, m) for m in miss)
                st.caption(f"⚠️ Нет файлов: {names}")
            if st.button("🔒 Финализировать", use_container_width=True, key="finalize_btn"):
                periods.finalize_report(selected)
                st.success(f"Период {current['month']} финализирован.")
                st.rerun()

            # Удаление периода (необратимо — удаляет все его данные)
            confirm_del = st.checkbox("Подтвердить удаление", key="confirm_del")
            if st.button(
                "🗑 Удалить период",
                use_container_width=True,
                key="delete_btn",
                disabled=not confirm_del,
            ):
                periods.delete_report(selected)
                st.session_state.report_id = None
                st.success(f"Период {current['month']} удалён.")
                st.rerun()
        else:
            st.info("🔒 Период финализирован — только чтение.")
            if st.button("✏️ Вернуть в draft", use_container_width=True, key="reopen_btn"):
                periods.reopen_report(selected)
                st.rerun()
    else:
        st.caption("Периодов пока нет. Создайте первый ниже.")
        st.session_state.report_id = None
        st.session_state.report_locked = False

    # Создание нового периода
    with st.expander("➕ Новый период"):
        draft = periods.get_open_draft()
        if draft:
            st.caption(
                f"Нельзя создать новый период: есть незавершённый {draft['month']}. "
                "Сначала финализируйте его."
            )
        else:
            default_month = datetime.now().strftime("%Y-%m")
            new_month = st.text_input("Месяц (YYYY-MM)", value=default_month, key="new_month")
            if st.button("Создать", use_container_width=True, key="create_period_btn"):
                try:
                    new_id = periods.create_report(new_month.strip())
                    st.session_state.report_id = new_id
                    st.success(f"Период {new_month} создан.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))


# ─── Основное приложение ──────────────────────────────────────────────────────

def main():
    # Инициализация состояния сессии
    if "selected_theme" not in st.session_state:
        st.session_state.selected_theme = load_theme()

    # Скрываем служебные элементы Streamlit (тулбар Deploy/меню, футер, decoration)
    st.markdown(
        """
        <style>
        [data-testid="stToolbar"] { display: none !important; }
        [data-testid="stDecoration"] { display: none !important; }
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Применение CSS темы
    current_theme = st.session_state.selected_theme
    st.markdown(STREAMLIT_THEMES.get(current_theme, STREAMLIT_THEMES["accent"]), unsafe_allow_html=True)

    st.markdown("# ⚡ Billing Automation")
    st.caption("Автоматическое распределение лицензий по ЦФО")

    # ─── Боковая панель: загрузка файлов ──────────────────────────────────────

    with st.sidebar:
        render_period_controls()
        st.divider()

        st.header("📂 Файлы")

        db_file = st.file_uploader("Справочник сотрудников", type=["xlsx"], key="db_file")

        st.divider()
        st.caption("Сервисы")
        svc_files = {}
        for svc in SERVICES:
            svc_files[svc["id"]] = st.file_uploader(
                svc["name"], type=svc["accept"], key=f"svc_{svc['id']}",
                label_visibility="collapsed" if False else "visible",
            )

    # ─── Вкладки основного интерфейса ─────────────────────────────────────────

    tab_main, tab_history, tab_params, tab_extra = st.tabs(
        ["📊 Отчёт", "📈 История", "⚙️ Параметры", "👥 Доп DB Users"]
    )

    report_id = st.session_state.get("report_id")
    report_locked = st.session_state.get("report_locked", False)

    # ─── Парсинг справочника → снимок в report_employees ───────────────────────

    if db_file and report_id is not None and not report_locked:
        db_sig = f"{db_file.name}:{db_file.size}"
        if st.session_state.get("saved_sig_db") != (report_id, db_sig):
            try:
                parsed = parse_db_users(db_file)
                n = billing.save_employees(report_id, parsed)
                st.session_state["saved_sig_db"] = (report_id, db_sig)
                st.toast(f"Справочник: сохранено {n} сотрудников.")
            except Exception as e:
                st.error(f"Ошибка чтения справочника: {e}")
    elif db_file and report_id is None:
        st.warning("Справочник: выберите/создайте период, чтобы сохранить.")

    # Справочник периода — из БД (DataFrame[nick, cfo, dept]) или None, если пуст
    db_users = None
    if report_id is not None and billing.has_employees(report_id):
        db_users = billing.get_employees_df(report_id)

    # ─── Парсинг сервисов → запись в БД (Вариант А) ───────────────────────────
    # Ники сервиса пишутся в billing_entries выбранного периода. cfo/source
    # считаются позже (при формировании отчёта/финализации).

    for svc in SERVICES:
        uploaded = svc_files.get(svc["id"])
        if not uploaded:
            continue

        # Сигнатура файла — чтобы не перезаписывать БД на каждом ререндере
        sig = f"{uploaded.name}:{uploaded.size}"
        sig_key = f"saved_sig_{svc['id']}"

        if report_id is None:
            st.warning(f"{svc['name']}: выберите/создайте период, чтобы сохранить файл.")
            continue
        if report_locked:
            st.warning(f"{svc['name']}: период финализирован — загрузка заблокирована.")
            continue
        if st.session_state.get(sig_key) == (report_id, sig):
            continue  # этот файл уже сохранён в этот период

        try:
            nicks = PARSERS[svc["id"]](uploaded)
            n = billing.save_service_upload(report_id, svc["id"], uploaded.name, nicks)
            st.session_state[sig_key] = (report_id, sig)
            st.toast(f"{svc['name']}: сохранено {n} польз.")
        except Exception as e:
            st.error(f"Ошибка {svc['name']}: {e}")

    # Источник истины для отчёта — данные периода из БД
    service_data = billing.get_service_nicks(report_id) if report_id else {}

    # Доп-юзеры периода из БД ({nick: {cfo, services:[...]}})
    extra_db = billing.get_extra_db(report_id) if report_id else {}

    # Цены периода из БД ({service_id: float})
    prices = billing.get_prices(report_id) if report_id else {}

    # Пересчёт cfo/source в billing_entries по справочнику и доп-юзерам.
    # Только в draft — финализированный период менять нельзя.
    if report_id is not None and not report_locked:
        billing.recompute_billing(report_id)

    # ─── Вкладка «История» ────────────────────────────────────────────────────

    with tab_history:
        render_history()

    # ─── Вкладка «Параметры» ─────────────────────────────────────────────────

    with tab_params:
        st.subheader("💰 Цены за лицензию")
        st.caption("Задайте стоимость одной лицензии для каждого сервиса (₽). Используется в сводке и отчётах по отделам.")

        if report_id is None:
            st.info("Выберите период, чтобы задать цены.")
        else:
            if report_locked:
                st.info("🔒 Период финализирован — цены только для чтения.")

            cols = st.columns(3)
            new_prices = {}
            invalid = []
            for i, svc in enumerate(SERVICES):
                col = cols[i % 3]
                raw = col.text_input(
                    svc["name"],
                    value=str(prices.get(svc["id"], "0")),
                    key=f"price_{svc['id']}",
                    disabled=report_locked,
                )
                val = parse_price(raw)  # пробелы и запятая обрабатываются автоматически
                if val is None:
                    if (raw or "").strip() not in ("", "0"):
                        invalid.append(svc["name"])
                    continue
                if val > 0:
                    new_prices[svc["id"]] = val

            if invalid:
                st.warning("Не распознаны цены (проверьте формат): " + ", ".join(invalid))

            # Сохраняем в БД только при реальном изменении и в draft
            if not report_locked and new_prices != prices:
                billing.set_prices(report_id, new_prices)
                prices = new_prices

        st.divider()
        st.subheader("🎨 Тема оформления")
        st.caption("Применяется к интерфейсу приложения и HTML-отчётам по отделам.")

        theme_options = ["light", "dark", "accent"]
        theme_labels = {"light": "☀️ Светлая", "dark": "🌙 Тёмная", "accent": "💜 Акцентная"}
        current_idx = theme_options.index(st.session_state.selected_theme) if st.session_state.selected_theme in theme_options else 2

        theme_choice = st.radio(
            "Тема",
            theme_options,
            index=current_idx,
            format_func=lambda x: theme_labels[x],
            horizontal=True,
            key="theme_radio",
        )
        if theme_choice != st.session_state.selected_theme:
            st.session_state.selected_theme = theme_choice
            save_theme(theme_choice)
            st.rerun()

    # ─── Вкладка «Доп DB Users» ──────────────────────────────────────────────

    with tab_extra:
        period_label = st.session_state.get("report_month", "—")
        st.caption(f"Период: **{period_label}** · удаление действует только на этот период")
        if extra_db:
            st.subheader(f"📋 Доп DB Users ({len(extra_db)})")
            if report_locked:
                st.info("🔒 Период финализирован — удаление недоступно.")

            # Поиск по нику (удобно при большом списке)
            search = st.text_input("Поиск по нику", key="extra_search").strip().lower()

            nicks = sorted(n for n in extra_db if not search or search in n.lower())
            st.caption(f"Показано: {len(nicks)} из {len(extra_db)}")

            for nick in nicks:
                entry = extra_db[nick]
                svc_names = ", ".join(
                    SVC_ID_TO_NAME.get(s, s) for s in sorted(entry.get("services", []))
                )
                cols = st.columns([3, 2, 4, 1])
                cols[0].markdown(f"**{nick}**")
                cols[1].caption(entry["cfo"])
                cols[2].caption(svc_names)
                if cols[3].button("🗑", key=f"del_extra_{nick}", disabled=report_locked,
                                  help="Удалить пользователя из доп. списка"):
                    billing.delete_extra_user(report_id, nick)
                    st.rerun()

            st.divider()
            if st.button("🗑 Очистить все", key="clear_extra", disabled=report_locked):
                billing.clear_extra_users(report_id)
                st.rerun()
        else:
            st.info("Доп. пользователи появятся после загрузки сервисов — те, кого нет в справочнике.")

    # ─── Вкладка «Отчёт» ─────────────────────────────────────────────────────

    with tab_main:
        if db_users is not None:
            cfo_counts = db_users["cfo"].value_counts()
            svc_count = len(service_data)
            st.success(f"✅ Справочник: **{len(db_users)}** сотрудников · **{len(cfo_counts)}** ЦФО · Сервисов: **{svc_count}**")

            # Краткая статистика по загруженным сервисам
            if service_data:
                svc_summary = " · ".join(f"{SVC_ID_TO_NAME[sid]}: {len(n)}" for sid, n in service_data.items())
                st.caption(svc_summary)
        else:
            if report_id is None:
                st.warning("Выберите или создайте период в боковой панели ←")
            else:
                st.warning("Загрузите справочник сотрудников и хотя бы один сервис в боковой панели ←")
            return

        if not service_data:
            st.warning("Загрузите хотя бы один сервис в боковой панели ←")
            return

        # ─── Ненайденные пользователи ────────────────────────────────────────

        db_set = set(db_users["nick"])
        unmatched: dict[str, set] = {}
        for svc_id, nicks in service_data.items():
            for nick in nicks:
                if nick in db_set:
                    continue
                entry = extra_db.get(nick)
                if entry and svc_id in entry.get("services", []):
                    continue
                unmatched.setdefault(nick, set()).add(svc_id)

        all_cfos = sorted(db_users["cfo"].unique().tolist())

        if unmatched:
            with st.expander(f"⚠️ Не найдено в справочнике: {len(unmatched)}", expanded=True):
                svc_ids_in_unmatched = sorted(set(sid for sids in unmatched.values() for sid in sids))
                filter_options = ["Все"] + [SVC_ID_TO_NAME.get(s, s) for s in svc_ids_in_unmatched]
                selected_filter = st.selectbox("Фильтр", filter_options, key="unmatched_filter")

                filtered = unmatched
                if selected_filter != "Все":
                    filter_id = next((s for s in svc_ids_in_unmatched if SVC_ID_TO_NAME.get(s, s) == selected_filter), None)
                    if filter_id:
                        filtered = {n: s for n, s in unmatched.items() if filter_id in s}

                # Массовое назначение
                c1, c2 = st.columns([2, 1])
                bulk_cfo = c1.selectbox("ЦФО для всех отображённых", ["—"] + all_cfos, key="bulk_cfo")
                if bulk_cfo != "—":
                    if c2.button(f"Назначить ({len(filtered)})", key="bulk_assign", disabled=report_locked):
                        for nick, svc_ids in filtered.items():
                            billing.set_extra_assignment(report_id, nick, bulk_cfo, list(svc_ids))
                        st.rerun()

                # Индивидуальное назначение — в форме: выборы не вызывают rerun,
                # запись в БД делается одним пакетом по кнопке «Сохранить».
                with st.form("assign_form"):
                    st.caption("Проставьте ЦФО и нажмите «Сохранить» — запись одним пакетом.")
                    for nick in sorted(filtered.keys()):
                        svc_ids = filtered[nick]
                        svc_names = ", ".join(SVC_ID_TO_NAME.get(s, s) for s in sorted(svc_ids))
                        cols = st.columns([3, 3, 4])
                        cols[0].markdown(f"**{nick}**")
                        cols[1].caption(svc_names)
                        cols[2].selectbox("ЦФО", ["—"] + all_cfos, key=f"assign_{nick}")

                    submitted = st.form_submit_button(
                        f"💾 Сохранить назначения ({len(filtered)})", disabled=report_locked
                    )
                    if submitted:
                        items = [
                            (nick, st.session_state[f"assign_{nick}"], list(svc_ids))
                            for nick, svc_ids in filtered.items()
                            if st.session_state.get(f"assign_{nick}", "—") != "—"
                        ]
                        n = billing.set_extra_assignments_bulk(report_id, items)
                        st.success(f"Сохранено назначений: {len(items)} (строк в БД: {n}).")
                        st.rerun()

        # ─── Кнопки генерации ─────────────────────────────────────────────────

        st.divider()
        c1, c2, c3 = st.columns(3)

        with c1:
            generate = st.button("📊 Сформировать", use_container_width=True, type="primary")
        with c2:
            export = st.button("⬇️ Excel (общий)", use_container_width=True)
        with c3:
            export_depts = st.button("📁 По отделам (ZIP)", use_container_width=True)

        if generate:
            st.session_state.report_sheets = build_report(report_id)

        if export:
            excel_bytes = build_general_excel(report_id)
            st.download_button(
                "💾 Скачать",
                data=excel_bytes,
                file_name=f"Billing_Report_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        if export_depts:
            selected_theme = st.session_state.get("selected_theme", "light")
            with st.spinner("Генерация отчётов по отделам..."):
                zip_bytes = build_all_dept_zip(report_id, theme=selected_theme)
            st.download_button(
                "💾 Скачать ZIP",
                data=zip_bytes,
                file_name=f"Billing_by_dept_{datetime.now().strftime('%Y-%m-%d')}.zip",
                mime="application/zip",
            )

        # Отображение отчёта
        if "report_sheets" in st.session_state and st.session_state.report_sheets:
            sheets = st.session_state.report_sheets
            tab_names = list(sheets.keys())
            tabs = st.tabs(tab_names)
            for tab, name in zip(tabs, tab_names):
                with tab:
                    st.dataframe(sheets[name], use_container_width=True, hide_index=True, height=350)


if __name__ == "__main__":
    main()
