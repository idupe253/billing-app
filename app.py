import streamlit as st
import pandas as pd
import re
import json
import os
from io import BytesIO
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

st.set_page_config(page_title="⚡ Billing Automation", layout="wide")

EXTRA_DB_FILE = Path("extra_db_users.json")

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

# ─── Utilities ────────────────────────────────────────────────────────────────

def clean_nick(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        raw = str(raw) if raw is not None else ""
    return re.sub(r"\(.*?\)", "", raw).strip().lower()


def parse_cfo(val) -> str:
    if val and str(val).strip():
        return str(val).strip()
    return "ПП НЕО"


def read_file(uploaded, sheet_name=0) -> pd.DataFrame:
    """Read uploaded file (CSV or XLSX) into a DataFrame."""
    name = uploaded.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded, dtype=str).fillna("")
    else:
        return pd.read_excel(uploaded, sheet_name=sheet_name, dtype=str).fillna("")

# ─── Extra DB persistence ────────────────────────────────────────────────────

def load_extra_db() -> dict:
    """Load extra DB from JSON file. Structure: {nick: {cfo: str, services: [svc_id, ...]}}"""
    if EXTRA_DB_FILE.exists():
        try:
            return json.loads(EXTRA_DB_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_extra_db(extra_db: dict):
    EXTRA_DB_FILE.write_text(json.dumps(extra_db, ensure_ascii=False, indent=2), encoding="utf-8")

# ─── DB Users parser ─────────────────────────────────────────────────────────

def parse_db_users(uploaded) -> pd.DataFrame:
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

# ─── Service parsers ─────────────────────────────────────────────────────────

def parse_google(uploaded) -> list[str]:
    df = read_file(uploaded)
    col = "Last Name [Required]" if "Last Name [Required]" in df.columns else df.columns[1]
    nicks = df[col].str.strip().str.lower().tolist()
    return sorted(set(n for n in nicks if n))


def parse_miro(uploaded) -> list[str]:
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
    df = read_file(uploaded, sheet_name="Copilot Usage")
    col = "SAML Name ID or Email" if "SAML Name ID or Email" in df.columns else df.columns[2]
    nicks = df[col].str.strip().str.lower().tolist()
    return sorted(set(n for n in nicks if n))


def _parse_azure_sheet(uploaded) -> pd.DataFrame:
    return read_file(uploaded, sheet_name="Licenses by user")


def parse_m365(uploaded) -> list[str]:
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
    df = read_file(uploaded)
    col = "NickName" if "NickName" in df.columns else df.columns[0]
    nicks = df[col].str.strip().str.lower().tolist()
    return sorted(set(n for n in nicks if n))


def parse_testit(uploaded) -> list[str]:
    df = read_file(uploaded)
    col = "Nickname" if "Nickname" in df.columns else df.columns[0]
    nicks = df[col].str.strip().str.lower().tolist()
    return sorted(set(n for n in nicks if n))


def parse_nick_from_col_a(uploaded) -> list[str]:
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

# ─── Report builder ──────────────────────────────────────────────────────────

def build_report(db_users: pd.DataFrame, extra_db: dict, service_data: dict) -> dict[str, pd.DataFrame]:
    """Build all report sheets. Returns {sheet_name: DataFrame}."""
    main_map = dict(zip(db_users["nick"], db_users["cfo"]))

    # Extra by service
    extra_by_svc: dict[str, dict[str, str]] = {}
    for nick, entry in extra_db.items():
        for svc_id in entry.get("services", []):
            extra_by_svc.setdefault(svc_id, {})[nick] = entry["cfo"]

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

        # User list
        if user_rows:
            sheets[f"User list {svc_name}"] = pd.DataFrame(user_rows)

        # Pivot
        total = len(nicks)
        pivot_rows = [
            {"ЦФО": d, "Кол-во": c, "%": f"{c / total * 100:.1f}%" if total else "0%"}
            for d, c in sorted(dept_count.items())
        ]
        pivot_rows.append({"ЦФО": "ИТОГО", "Кол-во": total, "%": "100%"})
        sheets[f"Pivot {svc_name}"] = pd.DataFrame(pivot_rows)

    # Summary
    all_cfos = sorted(set(db_users["cfo"].tolist() + [e["cfo"] for e in extra_db.values()]))
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
    sheets["Общая сводка"] = pd.DataFrame(summary_rows)

    # Not found
    nf_rows = [{"Nickname": n, "Сервисы": ", ".join(sorted(s))} for n, s in sorted(all_not_found.items())]
    if nf_rows:
        sheets["Не найдены"] = pd.DataFrame(nf_rows)

    # Extra DB per service
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

    # DB Users (main + extra)
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

    return sheets


def sheets_to_excel(sheets: dict[str, pd.DataFrame]) -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in sheets.items():
            sheet_name = name[:31]
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            ws = writer.sheets[sheet_name]
            for i, col in enumerate(df.columns):
                max_len = max(len(str(col)), df[col].astype(str).str.len().max() if len(df) else 0)
                ws.column_dimensions[chr(65 + i) if i < 26 else f"A{chr(65 + i - 26)}"].width = min(max_len + 3, 40)
    return buf.getvalue()

# ─── Streamlit App ────────────────────────────────────────────────────────────

def main():
    st.markdown("# ⚡ Billing Automation")
    st.caption("Автоматическое распределение лицензий по ЦФО")

    # Init session state
    if "extra_db" not in st.session_state:
        st.session_state.extra_db = load_extra_db()
    if "service_data" not in st.session_state:
        st.session_state.service_data = {}

    extra_db = st.session_state.extra_db

    # ─── Sidebar: file uploads ────────────────────────────────────────────────

    with st.sidebar:
        st.header("📂 Загрузка файлов")

        st.subheader("Справочник сотрудников")
        db_file = st.file_uploader("Список сотрудников (.xlsx)", type=["xlsx"], key="db_file")

        st.divider()
        st.subheader("Сервисы")
        svc_files = {}
        for svc in SERVICES:
            svc_files[svc["id"]] = st.file_uploader(
                svc["name"],
                type=svc["accept"],
                key=f"svc_{svc['id']}",
            )

    # ─── Parse DB Users ───────────────────────────────────────────────────────

    db_users = None
    if db_file:
        try:
            db_users = parse_db_users(db_file)
            cfo_counts = db_users["cfo"].value_counts().sort_index()
            st.success(f"✅ Справочник: **{len(db_users)}** сотрудников · **{len(cfo_counts)}** ЦФО")
            with st.expander("Распределение по ЦФО", expanded=False):
                st.dataframe(cfo_counts.reset_index().rename(columns={"index": "ЦФО", "cfo": "ЦФО", "count": "Кол-во"}), use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Ошибка чтения справочника: {e}")

    # ─── Parse services ───────────────────────────────────────────────────────

    service_data = {}
    for svc in SERVICES:
        uploaded = svc_files.get(svc["id"])
        if uploaded:
            try:
                parser = PARSERS[svc["id"]]
                nicks = parser(uploaded)
                service_data[svc["id"]] = nicks
                st.info(f"**{svc['name']}**: {len(nicks)} пользователей")
            except Exception as e:
                st.error(f"Ошибка {svc['name']}: {e}")

    st.session_state.service_data = service_data

    if not db_users is not None or not service_data:
        if db_file is None:
            st.warning("Загрузите справочник сотрудников и хотя бы один сервис в боковой панели.")
        return

    # ─── Unmatched users ──────────────────────────────────────────────────────

    db_set = set(db_users["nick"])
    unmatched: dict[str, set] = {}  # nick → set of service ids
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
        st.divider()
        st.subheader(f"⚠️ Не найдено в справочнике: {len(unmatched)}")

        # Filter tabs
        svc_ids_in_unmatched = sorted(set(sid for sids in unmatched.values() for sid in sids))
        filter_options = ["Все"] + [SVC_ID_TO_NAME.get(s, s) for s in svc_ids_in_unmatched]
        selected_filter = st.selectbox("Фильтр по сервису", filter_options, key="unmatched_filter")

        filtered = unmatched
        if selected_filter != "Все":
            filter_id = next((s for s in svc_ids_in_unmatched if SVC_ID_TO_NAME.get(s, s) == selected_filter), None)
            if filter_id:
                filtered = {n: s for n, s in unmatched.items() if filter_id in s}

        # Bulk assign
        st.markdown(f"**{len(filtered)}** пользователей")
        bulk_cfo = st.selectbox("Назначить ЦФО всем отображённым", ["—"] + all_cfos, key="bulk_cfo")
        if bulk_cfo != "—":
            if st.button(f"✅ Назначить «{bulk_cfo}» для {len(filtered)} пользователей", key="bulk_assign"):
                for nick, svc_ids in filtered.items():
                    existing = extra_db.get(nick, {"cfo": bulk_cfo, "services": []})
                    merged_svcs = list(set(existing.get("services", []) + list(svc_ids)))
                    extra_db[nick] = {"cfo": bulk_cfo, "services": merged_svcs}
                save_extra_db(extra_db)
                st.session_state.extra_db = extra_db
                st.rerun()

        # Individual table
        with st.expander("Назначить индивидуально", expanded=False):
            for nick in sorted(filtered.keys()):
                svc_ids = filtered[nick]
                svc_names = ", ".join(SVC_ID_TO_NAME.get(s, s) for s in sorted(svc_ids))
                cols = st.columns([3, 3, 4])
                cols[0].markdown(f"**{nick}**")
                cols[1].caption(svc_names)
                cfo_val = cols[2].selectbox("ЦФО", ["—"] + all_cfos, key=f"assign_{nick}")
                if cfo_val != "—":
                    existing = extra_db.get(nick, {"cfo": cfo_val, "services": []})
                    merged_svcs = list(set(existing.get("services", []) + list(svc_ids)))
                    extra_db[nick] = {"cfo": cfo_val, "services": merged_svcs}
                    save_extra_db(extra_db)
                    st.session_state.extra_db = extra_db

    # ─── Extra DB overview ────────────────────────────────────────────────────

    if extra_db:
        st.divider()
        entries = []
        for nick, entry in extra_db.items():
            for svc_id in entry.get("services", []):
                entries.append({"Nickname": nick, "ЦФО": entry["cfo"], "Сервис": SVC_ID_TO_NAME.get(svc_id, svc_id)})
        if entries:
            st.subheader(f"📋 Доп DB Users ({len(entries)})")
            df_extra = pd.DataFrame(entries).sort_values("Nickname")
            st.dataframe(df_extra, use_container_width=True, hide_index=True)
            if st.button("🗑 Очистить все доп. назначения", key="clear_extra"):
                st.session_state.extra_db = {}
                save_extra_db({})
                st.rerun()

    # ─── Report ───────────────────────────────────────────────────────────────

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        generate = st.button("📊 Сформировать отчёт", use_container_width=True, type="primary")
    with col2:
        export = st.button("⬇️ Скачать Excel", use_container_width=True)

    if generate or export:
        sheets = build_report(db_users, extra_db, service_data)

        if generate:
            st.session_state.report_sheets = sheets

        if export:
            excel_bytes = sheets_to_excel(sheets)
            st.download_button(
                "💾 Скачать файл",
                data=excel_bytes,
                file_name=f"Billing_Report_{pd.Timestamp.now().strftime('%Y-%m-%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    # Display report
    if "report_sheets" in st.session_state and st.session_state.report_sheets:
        sheets = st.session_state.report_sheets
        st.subheader(f"📄 Отчёт — {len(sheets)} вкладок")
        tab_names = list(sheets.keys())
        tabs = st.tabs(tab_names)
        for tab, name in zip(tabs, tab_names):
            with tab:
                df = sheets[name]
                st.dataframe(df, use_container_width=True, hide_index=True, height=400)


if __name__ == "__main__":
    main()
