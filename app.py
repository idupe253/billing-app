import streamlit as st
import pandas as pd
import re
import json
import zipfile
from io import BytesIO
from pathlib import Path
from datetime import datetime

# ─── Конфигурация ─────────────────────────────────────────────────────────────

st.set_page_config(page_title="⚡ Billing Automation", layout="wide")

# Файлы для хранения настроек между сессиями
EXTRA_DB_FILE = Path("extra_db_users.json")
PRICES_FILE = Path("service_prices.json")

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


def read_file(uploaded, sheet_name=0) -> pd.DataFrame:
    """Чтение загруженного файла (CSV или XLSX) в DataFrame."""
    name = uploaded.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded, dtype=str).fillna("")
    else:
        return pd.read_excel(uploaded, sheet_name=sheet_name, dtype=str).fillna("")

# ─── Хранение доп. пользователей ─────────────────────────────────────────────

def load_extra_db() -> dict:
    """Загрузка доп. пользователей из JSON. Структура: {nick: {cfo: str, services: [svc_id, ...]}}"""
    if EXTRA_DB_FILE.exists():
        try:
            return json.loads(EXTRA_DB_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_extra_db(extra_db: dict):
    """Сохранение доп. пользователей в JSON."""
    EXTRA_DB_FILE.write_text(json.dumps(extra_db, ensure_ascii=False, indent=2), encoding="utf-8")

# ─── Хранение цен ────────────────────────────────────────────────────────────

def load_prices() -> dict:
    """Загрузка цен за лицензию из JSON. Структура: {svc_id: float}"""
    if PRICES_FILE.exists():
        try:
            return json.loads(PRICES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_prices(prices: dict):
    """Сохранение цен за лицензию в JSON."""
    PRICES_FILE.write_text(json.dumps(prices, ensure_ascii=False, indent=2), encoding="utf-8")

# ─── Парсер справочника сотрудников ──────────────────────────────────────────

def parse_db_users(uploaded) -> pd.DataFrame:
    """Парсинг файла сотрудников (1С). Столбец A — ник, C — ЦФО."""
    df = pd.read_excel(uploaded, sheet_name="TDSheet", dtype=str).fillna("")
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
        if nick:
            nicks.append(nick)
    return sorted(set(nicks))


def parse_copilot(uploaded) -> list[str]:
    """GitHub Copilot: ник из столбца C (SAML Name ID or Email), вкладка Copilot Usage."""
    df = read_file(uploaded, sheet_name="Copilot Usage")
    col = "SAML Name ID or Email" if "SAML Name ID or Email" in df.columns else df.columns[2]
    nicks = df[col].str.strip().str.lower().tolist()
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


def parse_mattermost(uploaded) -> list[str]:
    """Mattermost: ник из столбца A (NickName), все пользователи."""
    df = read_file(uploaded)
    col = "NickName" if "NickName" in df.columns else df.columns[0]
    nicks = df[col].str.strip().str.lower().tolist()
    return sorted(set(n for n in nicks if n))


def parse_testit(uploaded) -> list[str]:
    """TestIT: ник из столбца A (Nickname)."""
    df = read_file(uploaded)
    col = "Nickname" if "Nickname" in df.columns else df.columns[0]
    nicks = df[col].str.strip().str.lower().tolist()
    return sorted(set(n for n in nicks if n))


def parse_nick_from_col_a(uploaded) -> list[str]:
    """1С / Jira: ник из столбца A (ФизЛицо) с очисткой скобок."""
    df = read_file(uploaded)
    col = "ФизЛицо" if "ФизЛицо" in df.columns else df.columns[0]
    nicks = [clean_nick(v) for v in df[col]]
    return sorted(set(n for n in nicks if n))


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

def build_report(db_users: pd.DataFrame, extra_db: dict, service_data: dict, prices: dict) -> dict[str, pd.DataFrame]:
    """Построение всех листов отчёта. Возвращает {имя_листа: DataFrame}."""
    main_map = dict(zip(db_users["nick"], db_users["cfo"]))

    # Доп. пользователи по сервисам
    extra_by_svc: dict[str, dict[str, str]] = {}
    for nick, entry in extra_db.items():
        for svc_id in entry.get("services", []):
            extra_by_svc.setdefault(svc_id, {})[nick] = entry["cfo"]

    all_cfos = sorted(set(db_users["cfo"].tolist() + [e["cfo"] for e in extra_db.values()]))
    sheets: dict[str, pd.DataFrame] = {}
    summary_data: dict[str, dict[str, int]] = {}
    all_not_found: dict[str, set] = {}

    for svc_id, nicks in service_data.items():
        svc_name = SVC_ID_TO_NAME.get(svc_id, svc_id)
        svc_extra = extra_by_svc.get(svc_id, {})
        dept_count: dict[str, int] = {}
        user_rows = []

        for nick in nicks:
            if nick in main_map:
                dept = main_map[nick]
            elif nick in svc_extra:
                dept = svc_extra[nick]
            else:
                dept = "Не найден"
                all_not_found.setdefault(nick, set()).add(svc_name)
            dept_count[dept] = dept_count.get(dept, 0) + 1
            user_rows.append({"Nickname": nick, "ЦФО": dept})

        summary_data[svc_name] = dept_count

        # Лист пользователей
        if user_rows:
            sheets[f"User list {svc_name}"] = pd.DataFrame(user_rows)

        # Сводная таблица
        total = len(nicks)
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
    svc_names = [SVC_ID_TO_NAME.get(sid, sid) for sid in service_data]
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
    for svc_id in service_data:
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

    # Доп DB по сервисам
    for nick, entry in extra_db.items():
        for svc_id in entry.get("services", []):
            svc_name = SVC_ID_TO_NAME.get(svc_id, svc_id)
            sheet_name = f"Доп DB {svc_name}"
            if sheet_name not in sheets:
                sheets[sheet_name] = pd.DataFrame(columns=["Nickname", "ЦФО"])
            sheets[sheet_name] = pd.concat(
                [sheets[sheet_name], pd.DataFrame([{"Nickname": nick, "ЦФО": entry["cfo"]}])],
                ignore_index=True,
            )

    # Общий список: основной справочник + доп. пользователи
    db_rows = db_users[["nick", "cfo", "dept"]].rename(
        columns={"nick": "Nickname", "cfo": "ЦФО", "dept": "Подразделение"}
    ).copy()
    db_rows["Источник"] = "1С"
    extra_nicks_added = set()
    extra_rows_list = []
    for nick, entry in extra_db.items():
        if nick not in extra_nicks_added:
            extra_rows_list.append({"Nickname": nick, "ЦФО": entry["cfo"], "Подразделение": "", "Источник": "Доп DB"})
            extra_nicks_added.add(nick)
    if extra_rows_list:
        db_rows = pd.concat([db_rows, pd.DataFrame(extra_rows_list)], ignore_index=True)
    db_rows = db_rows.sort_values("Nickname").reset_index(drop=True)
    sheets["DB Users"] = db_rows

    # Сводный лист в формате для финансов (все отделы, все сервисы)
    finance_rows = []
    for svc_id, nicks in service_data.items():
        svc_name = SVC_ID_TO_NAME.get(svc_id, svc_id)
        svc_extra = extra_by_svc.get(svc_id, {})
        price = prices.get(svc_id, 0)
        for nick in sorted(nicks):
            dept = main_map.get(nick)
            if dept is None:
                dept = svc_extra.get(nick)
            if dept is None:
                dept = "Не найден"
            cost = round(price, 2) if price else ""
            finance_rows.append({
                "Продукты ТХ": f"ПО {svc_name}",
                "Nickname / Наименование": nick,
                "Потребитель": dept,
                "Единица продукта": "1 лицензия",
                "Количество": 1,
                "Цена": cost,
                "Стоимость": cost,
                "Комментарий": "",
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

def build_dept_html(dept: str, service_data: dict, main_map: dict, extra_by_svc: dict, prices: dict, theme: str = "light") -> str:
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

    for svc_id, nicks in service_data.items():
        svc_name = SVC_ID_TO_NAME.get(svc_id, svc_id)
        svc_extra = extra_by_svc.get(svc_id, {})

        dept_nicks = []
        for nick in sorted(nicks):
            d = main_map.get(nick)
            if d is None:
                d = svc_extra.get(nick)
            if d == dept:
                dept_nicks.append(nick)

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


def build_dept_excel(dept: str, service_data: dict, main_map: dict, extra_by_svc: dict, prices: dict) -> bytes:
    """Генерация Excel для отдела в формате для финансов."""
    all_rows = []
    for svc_id, nicks in service_data.items():
        svc_name = SVC_ID_TO_NAME.get(svc_id, svc_id)
        svc_extra = extra_by_svc.get(svc_id, {})
        price = prices.get(svc_id, 0)
        for nick in sorted(nicks):
            d = main_map.get(nick)
            if d is None:
                d = svc_extra.get(nick)
            if d == dept:
                cost = round(price, 2) if price else ""
                all_rows.append({
                    "Продукты ТХ": f"ПО {svc_name}",
                    "Nickname / Наименование": nick,
                    "Потребитель": dept,
                    "Единица продукта": "1 лицензия",
                    "Количество": 1,
                    "Цена": cost,
                    "Стоимость": cost,
                    "Комментарий": "",
                    "Свободное поле": "",
                })

    if not all_rows:
        all_rows.append({
            "Продукты ТХ": "", "Nickname / Наименование": "", "Потребитель": dept,
            "Единица продукта": "", "Количество": "", "Цена": "",
            "Стоимость": "", "Комментарий": "", "Свободное поле": "",
        })

    return sheets_to_excel({"Лицензии": pd.DataFrame(all_rows)})


def build_all_dept_zip(db_users, extra_db, service_data, prices, theme="light") -> bytes:
    """Генерация ZIP-архива со всеми отчётами по отделам (HTML + XLSX)."""
    main_map = dict(zip(db_users["nick"], db_users["cfo"]))
    extra_by_svc = {}
    for nick, entry in extra_db.items():
        for svc_id in entry.get("services", []):
            extra_by_svc.setdefault(svc_id, {})[nick] = entry["cfo"]

    all_cfos = sorted(set(
        db_users["cfo"].tolist() +
        [e["cfo"] for e in extra_db.values()]
    ))

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for dept in all_cfos:
            safe_name = re.sub(r'[\\/:*?"<>|]', '_', dept)

            html = build_dept_html(dept, service_data, main_map, extra_by_svc, prices, theme=theme)
            if html:
                zf.writestr(f"{safe_name}/{safe_name}.html", html)

            xlsx = build_dept_excel(dept, service_data, main_map, extra_by_svc, prices)
            zf.writestr(f"{safe_name}/{safe_name}.xlsx", xlsx)

    return buf.getvalue()

# ─── Основное приложение ──────────────────────────────────────────────────────

def main():
    st.markdown("# ⚡ Billing Automation")
    st.caption("Автоматическое распределение лицензий по ЦФО")

    # Инициализация состояния сессии
    if "extra_db" not in st.session_state:
        st.session_state.extra_db = load_extra_db()
    if "prices" not in st.session_state:
        st.session_state.prices = load_prices()

    extra_db = st.session_state.extra_db
    prices = st.session_state.prices

    # ─── Боковая панель: загрузка файлов ──────────────────────────────────────

    with st.sidebar:
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

    tab_main, tab_params, tab_extra = st.tabs(["📊 Отчёт", "⚙️ Параметры", "👥 Доп DB Users"])

    # ─── Парсинг справочника ──────────────────────────────────────────────────

    db_users = None
    if db_file:
        try:
            db_users = parse_db_users(db_file)
        except Exception as e:
            st.error(f"Ошибка чтения справочника: {e}")

    # ─── Парсинг сервисов ─────────────────────────────────────────────────────

    service_data = {}
    for svc in SERVICES:
        uploaded = svc_files.get(svc["id"])
        if uploaded:
            try:
                service_data[svc["id"]] = PARSERS[svc["id"]](uploaded)
            except Exception as e:
                st.error(f"Ошибка {svc['name']}: {e}")

    # ─── Вкладка «Параметры» ─────────────────────────────────────────────────

    with tab_params:
        st.subheader("💰 Цены за лицензию")
        st.caption("Задайте стоимость одной лицензии для каждого сервиса (₽). Используется в сводке и отчётах по отделам.")

        cols = st.columns(3)
        new_prices = {}
        for i, svc in enumerate(SERVICES):
            col = cols[i % 3]
            raw = col.text_input(
                svc["name"],
                value=str(prices.get(svc["id"], "0")),
                key=f"price_{svc['id']}",
            )
            try:
                val = float(raw.replace(",", ".").strip())
                if val > 0:
                    new_prices[svc["id"]] = val
            except ValueError:
                pass

        if new_prices != prices:
            st.session_state.prices = new_prices
            prices = new_prices
            save_prices(prices)

        st.divider()
        st.subheader("🎨 Тема HTML-отчётов")
        st.caption("Текущая тема: 💜 Акцентная")
        st.session_state.selected_theme = "accent"

    # ─── Вкладка «Доп DB Users» ──────────────────────────────────────────────

    with tab_extra:
        if extra_db:
            entries = []
            for nick, entry in extra_db.items():
                for svc_id in entry.get("services", []):
                    entries.append({"Nickname": nick, "ЦФО": entry["cfo"], "Сервис": SVC_ID_TO_NAME.get(svc_id, svc_id)})
            if entries:
                st.subheader(f"📋 Доп DB Users ({len(entries)})")
                st.dataframe(pd.DataFrame(entries).sort_values("Nickname"), use_container_width=True, hide_index=True, height=300)
                if st.button("🗑 Очистить все", key="clear_extra"):
                    st.session_state.extra_db = {}
                    save_extra_db({})
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
            with st.expander(f"⚠️ Не найдено в справочнике: {len(unmatched)}", expanded=False):
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
                    if c2.button(f"Назначить ({len(filtered)})", key="bulk_assign"):
                        for nick, svc_ids in filtered.items():
                            existing = extra_db.get(nick, {"cfo": bulk_cfo, "services": []})
                            merged = list(set(existing.get("services", []) + list(svc_ids)))
                            extra_db[nick] = {"cfo": bulk_cfo, "services": merged}
                        save_extra_db(extra_db)
                        st.session_state.extra_db = extra_db
                        st.rerun()

                # Индивидуальное назначение
                for nick in sorted(filtered.keys()):
                    svc_ids = filtered[nick]
                    svc_names = ", ".join(SVC_ID_TO_NAME.get(s, s) for s in sorted(svc_ids))
                    cols = st.columns([3, 3, 4])
                    cols[0].markdown(f"**{nick}**")
                    cols[1].caption(svc_names)
                    cfo_val = cols[2].selectbox("ЦФО", ["—"] + all_cfos, key=f"assign_{nick}")
                    if cfo_val != "—":
                        existing = extra_db.get(nick, {"cfo": cfo_val, "services": []})
                        merged = list(set(existing.get("services", []) + list(svc_ids)))
                        extra_db[nick] = {"cfo": cfo_val, "services": merged}
                        save_extra_db(extra_db)
                        st.session_state.extra_db = extra_db

        # ─── Кнопки генерации ─────────────────────────────────────────────────

        st.divider()
        c1, c2, c3 = st.columns(3)

        with c1:
            generate = st.button("📊 Сформировать", use_container_width=True, type="primary")
        with c2:
            export = st.button("⬇️ Excel (общий)", use_container_width=True)
        with c3:
            export_depts = st.button("📁 По отделам (ZIP)", use_container_width=True)

        if generate or export:
            sheets = build_report(db_users, extra_db, service_data, prices)
            if generate:
                st.session_state.report_sheets = sheets
            if export:
                excel_bytes = sheets_to_excel(sheets)
                st.download_button(
                    "💾 Скачать",
                    data=excel_bytes,
                    file_name=f"Billing_Report_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

        if export_depts:
            selected_theme = st.session_state.get("selected_theme", "light")
            with st.spinner("Генерация отчётов по отделам..."):
                zip_bytes = build_all_dept_zip(db_users, extra_db, service_data, prices, theme=selected_theme)
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
