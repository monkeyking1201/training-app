"""
App 4B — 教練審核 + 院長熱圖戰情端  (UI v4 — Notion Light)
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, timedelta
import pandas as pd

# ── 常數 ─────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SCHEDULE_DB_ID = "1ewrFUQc1P3YfB3-h9kzuoOLvXcRiee4eLv_R6SBj5oI"
BONUS_DB_ID    = "1KKKgeOCEBmcBxsy0d7KP6ZJqWXyhAtWqNn2FB_okPG8"

ITEM_PRICES = {
    "出席率":     200,
    "死活題":     300,
    "次一手":     400,
    "輸棋討論":   400,
    "AI人機大戰": 400,
    "新銳循環賽": 600,    # 原 1000，調整為 600
}

# 替代任務專屬獎金（與主項目分開計算）
ALT_TASK_PRICES = {
    "運動":   300,
    "交流":   300,
    "讀書會": 300,
}
ITEM_COL_IDX = {
    "出席率": 4, "死活題": 5, "次一手": 6,
    "輸棋討論": 7, "AI人機大戰": 8, "新銳循環賽": 9,
}
ALT_COL       = 10
STATUS_COL    = 11
WEEKDAY_ZH    = ["一", "二", "三", "四", "五", "六", "日"]
WEEKLY_TARGET  = 4500
PROJECT_TOTAL  = 100_000         # 每位正式選手各有 $100,000 專案額度
PROJECT_MONTHS = 5               # 專案期間：8–12 月，共 5 個月

# 生力軍：練習參與打卡系統，不計入實際獎金發放
TRAINEE_PLAYERS = ["陳天宸", "楊昕潔"]

# ── 贊助冠軍經費（獨立贊助商，與訓練獎金分開）────────────────────
CHAMPION_TAB  = "Champion_DB"
CHAMPION_ITEMS = {
    "⚔️ 次一手冠軍": 300,
    "🧩 判斷冠軍":   100,
}
CHAMPION_STATUS_OPTIONS = ["🔴 已墊付", "🟡 已報帳", "✅ 已核銷"]
CHAMPION_STATUS_BG = {
    "🔴 已墊付": "#FEE2E2",
    "🟡 已報帳": "#FEF3C7",
    "✅ 已核銷": "#D1FAE5",
}
CHAMP_COL = {"時間戳":0,"日期":1,"比賽項目":2,"選手":3,"金額":4,"狀態":5,"備注":6}

# 只參加次一手比賽、不在訓練打卡系統的選手
NEXTMOVE_PLAYERS = [
    "許皓鋐", "陳祈睿", "徐靖恩", "林君諺", "李維",
    "賴均輔", "王元均", "簡靖庭", "盧奕銓",
]

# ── 菁英隊 ────────────────────────────────────────────────────────
ELITE_TAB         = "Elite_DB"
ELITE_DAILY_BONUS = 4000
# ★ 菁英隊選手名單
ELITE_PLAYERS = [
    "許皓鋐", "陳祈睿", "徐靖恩", "林君諺", "李維",
    "賴均輔", "王元均", "簡靖庭", "盧奕銓",
]
ELITE_COL = {"時間戳":0,"日期":1,"選手":2,"金額":3,"備注":4}

# ── 交流費用（院長個人墊付，與訓練獎金分開）──────────────────────
EXCHANGE_TAB = "Exchange_DB"
EXCHANGE_STATUS_OPTIONS = ["🔴 已墊付", "🟡 已報帳", "✅ 已核銷"]
EXCHANGE_STATUS_BG = {
    "🔴 已墊付": "#FEE2E2",
    "🟡 已報帳": "#FEF3C7",
    "✅ 已核銷": "#D1FAE5",
}
EXCH_COL = {"時間戳": 0, "日期": 1, "項目": 2, "金額": 3, "狀態": 4, "備注": 5}


# ── 狀態欄位 helpers（容忍多餘欄位）─────────────────────────────
def row_status(row: list) -> str:
    for v in row[STATUS_COL:]:
        if v.strip() in ("待審核", "已核准"):
            return v.strip()
    return ""

def row_status_idx_1based(row: list) -> int:
    for i, v in enumerate(row):
        if i >= STATUS_COL and v.strip() in ("待審核", "已核准"):
            return i + 1
    return STATUS_COL + 1


# ── Google Sheets 連線 ────────────────────────────────────────────
@st.cache_resource
def get_gc():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    return gspread.authorize(creds)

@st.cache_resource
def get_bonus_ws():
    return get_gc().open_by_key(BONUS_DB_ID).get_worksheet(0)

@st.cache_data(ttl=20)
def load_bonus_data() -> list:
    return get_bonus_ws().get_all_values()

@st.cache_data(ttl=600)
def load_player_list() -> list:
    sh   = get_gc().open_by_key(SCHEDULE_DB_ID)
    ws   = sh.worksheet("PIN")
    rows = ws.get_all_values()
    return [r[0].strip() for r in rows if len(r) >= 1 and r[0].strip()]


# ── 工具函數 ──────────────────────────────────────────────────────
def get_week_dates(offset: int = 0) -> list[date]:
    """offset=0 本週, offset=-1 上週, offset=-2 兩週前, ..."""
    today  = date.today()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
    return [monday + timedelta(days=i) for i in range(7)]

def get_pending_today(all_data: list) -> list[tuple]:
    today_str = date.today().strftime("%Y-%m-%d")
    return [
        (i + 2, row[1])
        for i, row in enumerate(all_data[1:])
        if len(row) > STATUS_COL and row[2] == today_str and row_status(row) == "待審核"
    ]

def get_pending_makeup(all_data: list) -> list[tuple]:
    """取得非今日的待審核補交申報 → (row_idx_1based, player_name, date_str)"""
    today_str = date.today().strftime("%Y-%m-%d")
    return [
        (i + 2, row[1], row[2])
        for i, row in enumerate(all_data[1:])
        if len(row) > STATUS_COL
        and row[2] != today_str
        and row_status(row) == "待審核"
    ]

def approve_all_pending(all_data: list) -> int:
    today_str = date.today().strftime("%Y-%m-%d")
    cells = [
        gspread.Cell(i + 2, row_status_idx_1based(row), "已核准")
        for i, row in enumerate(all_data[1:])
        if len(row) > STATUS_COL and row[2] == today_str and row_status(row) == "待審核"
    ]
    if cells:
        get_bonus_ws().update_cells(cells)
        load_bonus_data.clear()
    return len(cells)

def approve_one(row_idx: int, all_data: list) -> None:
    """核准單一筆（row_idx 為 Google Sheet 的 1-based 列號）"""
    row = all_data[row_idx - 1]   # all_data 是 0-based，row_idx=2 → all_data[1]
    col = row_status_idx_1based(row)
    get_bonus_ws().update_cell(row_idx, col, "已核准")
    load_bonus_data.clear()

@st.cache_resource
def get_champion_ws():
    sh = get_gc().open_by_key(BONUS_DB_ID)
    try:
        ws = sh.worksheet(CHAMPION_TAB)
    except Exception:
        ws = sh.add_worksheet(title=CHAMPION_TAB, rows=300, cols=10)
        ws.append_row(list(CHAMP_COL.keys()))
    return ws

@st.cache_data(ttl=30)
def load_champion_data() -> list:
    return get_champion_ws().get_all_values()

def add_champion_record(rec_date: date, item: str, player: str,
                        amount: int, status: str, note: str = "") -> None:
    from datetime import datetime
    get_champion_ws().append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        rec_date.strftime("%Y-%m-%d"),
        item, player, str(amount), status, note,
    ])
    load_champion_data.clear()

def update_champion_status(row_idx: int, new_status: str) -> None:
    get_champion_ws().update_cell(row_idx, CHAMP_COL["狀態"] + 1, new_status)
    load_champion_data.clear()

def generate_champion_report_html(year: int, month: int, champ_data: list) -> str:
    prefix    = f"{year:04d}-{month:02d}"
    today_str = date.today().strftime("%Y/%m/%d")
    records   = [r for r in champ_data[1:] if len(r) > 5 and r[1].startswith(prefix)]
    total       = sum(int(r[4]) for r in records)
    outstanding = sum(int(r[4]) for r in records if r[5] == "🔴 已墊付")

    rows_html = "".join(
        f"<tr>"
        f"<td style='padding:8px 14px;'>{r[1]}</td>"
        f"<td style='padding:8px 14px;'>{r[2]}</td>"
        f"<td style='padding:8px 14px;font-weight:700;'>{r[3]}</td>"
        f"<td style='padding:8px 14px;text-align:right;'>${int(r[4]):,}</td>"
        f"<td style='padding:8px 14px;text-align:center;'>{r[5]}</td>"
        f"<td style='padding:8px 14px;color:#6B7280;'>{r[6] if len(r) > 6 else ''}</td>"
        f"</tr>"
        for r in records
    )
    warn_row = (
        f"<tr><td colspan='6' style='padding:10px 14px;color:#DC2626;font-weight:700;'>"
        f"⚠️ 尚未報帳金額：${outstanding:,}</td></tr>"
        if outstanding > 0 else ""
    )
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head><meta charset="utf-8">
<title>次一手贊助經費 {year}年{month:02d}月</title>
<style>
@page {{ margin:20mm; }}
body {{ font-family:'Noto Sans TC','PingFang TC',sans-serif;background:white;color:#111827; }}
h1 {{ font-size:18px;font-weight:800;margin-bottom:4px; }}
.sub {{ color:#6B7280;font-size:13px;margin-bottom:20px; }}
table {{ width:100%;border-collapse:collapse; }}
th {{ background:#1E3A8A;color:white;padding:9px 14px;font-size:12px;text-align:left; }}
tr:nth-child(even) {{ background:#F9FAFB; }}
td {{ border-bottom:1px solid #E5E7EB;font-size:13px; }}
.grand {{ background:#EFF6FF;font-weight:800; }}
.footer {{ margin-top:20px;font-size:11px;color:#9CA3AF; }}
</style></head>
<body>
<h1>次一手 贊助冠軍經費明細</h1>
<div class="sub">{year}年{month:02d}月 &nbsp;·&nbsp; 資金來源：次一手贊助商 &nbsp;·&nbsp; 產出日期：{today_str}</div>
<table>
<thead><tr>
  <th>日期</th><th>比賽項目</th><th>獲獎選手</th>
  <th style="text-align:right">金額</th><th style="text-align:center">狀態</th><th>備注</th>
</tr></thead>
<tbody>
{rows_html}
<tr class="grand">
  <td colspan="3" style="padding:10px 14px;">本月合計</td>
  <td style="padding:10px 14px;text-align:right;font-size:16px;">${total:,}</td>
  <td colspan="2"></td>
</tr>
{warn_row}
</tbody>
</table>
<div class="footer">
  ※ 此報表僅含次一手贊助商經費，與棋院訓練獎金系統完全分開 &nbsp;·&nbsp; 產出日期：{today_str}
</div>
</body></html>"""


def build_heatmap(player: str, week_dates: list[date], all_data: list) -> pd.DataFrame:
    week_strs = {d.strftime("%Y-%m-%d") for d in week_dates}
    # lookup[ds][item] = [approved_count, pending_count]
    lookup     : dict = {}
    lookup_alt : dict = {}   # ds -> [alt_name, approved_count, pending_count]

    for row in all_data[1:]:
        if len(row) > STATUS_COL and row[1] == player and row[2] in week_strs:
            ds, status = row[2], row_status(row)
            if ds not in lookup:
                lookup[ds] = {item: [0, 0] for item in ITEM_COL_IDX}
            for item, col in ITEM_COL_IDX.items():
                if col < len(row) and row[col] == "V":
                    if status == "已核准":
                        lookup[ds][item][0] += 1
                    elif status == "待審核":
                        lookup[ds][item][1] += 1
            if len(row) > ALT_COL and row[ALT_COL].strip():
                alt_name = row[ALT_COL].strip()
                if ds not in lookup_alt:
                    lookup_alt[ds] = [alt_name, 0, 0]
                if status == "已核准":
                    lookup_alt[ds][1] += 1
                elif status == "待審核":
                    lookup_alt[ds][2] += 1

    rows = []
    for d in week_dates:
        ds    = d.strftime("%Y-%m-%d")
        label = f"{d.strftime('%m/%d')}（{WEEKDAY_ZH[d.weekday()]}）"
        rd    = {"日期": label}
        for item in ITEM_COL_IDX:
            a, p = lookup.get(ds, {}).get(item, [0, 0])
            if a > 0:
                rd[item] = "✅" if a == 1 else f"✅×{a}"
            elif p > 0:
                rd[item] = "🟡" if p == 1 else f"🟡×{p}"
            else:
                rd[item] = "・"
        alt = lookup_alt.get(ds)
        if alt:
            alt_name, a_cnt, p_cnt = alt
            if a_cnt > 0:
                rd["🔥替代"] = f"✅ {alt_name}" if a_cnt == 1 else f"✅ {alt_name}×{a_cnt}"
            elif p_cnt > 0:
                rd["🔥替代"] = f"🟡 {alt_name}" if p_cnt == 1 else f"🟡 {alt_name}×{p_cnt}"
            else:
                rd["🔥替代"] = "・"
        else:
            rd["🔥替代"] = "・"
        rows.append(rd)

    return pd.DataFrame(rows).set_index("日期")

def get_month_year(offset: int = 0) -> tuple[int, int]:
    """offset=0 本月, offset=-1 上月, ..."""
    today = date.today()
    m     = today.month - 1 + offset   # 0-based
    return today.year + m // 12, m % 12 + 1

def calc_total_paid_all(paying_players: list, all_data: list) -> int:
    """歷史累計已核准獎金（所有正式選手，不限月份）"""
    names = set(paying_players)
    total = 0
    for row in all_data[1:]:
        if (len(row) > STATUS_COL
                and row[1] in names
                and row_status(row) == "已核准"):
            for item, col in ITEM_COL_IDX.items():
                if col < len(row) and row[col] == "V":
                    total += ITEM_PRICES[item]
            if len(row) > ALT_COL and row[ALT_COL].strip() in ALT_TASK_PRICES:
                total += ALT_TASK_PRICES[row[ALT_COL].strip()]
    return total

def calc_monthly_bonus_one(player: str, year: int, month: int, all_data: list) -> dict:
    """計算單一選手某月份的已核准獎金明細"""
    prefix = f"{year:04d}-{month:02d}"
    total  = 0
    days   = 0
    item_counts = {item: 0 for item in ITEM_COL_IDX}
    alt_count   = 0

    for row in all_data[1:]:
        if (len(row) > STATUS_COL
                and row[1] == player
                and row[2].startswith(prefix)
                and row_status(row) == "已核准"):
            days += 1
            for item, col in ITEM_COL_IDX.items():
                if col < len(row) and row[col] == "V":
                    item_counts[item] += 1
                    total += ITEM_PRICES[item]
            if len(row) > ALT_COL and row[ALT_COL].strip() in ALT_TASK_PRICES:
                alt_count += 1
                total += ALT_TASK_PRICES[row[ALT_COL].strip()]
    return {"total": total, "days": days, "item_counts": item_counts, "alt_count": alt_count}

def render_monthly_table_html(summary: list, trainee_names: set) -> str:
    """summary: list of {name, total, days, item_counts, alt_count}
       trainee_names: set of names that are trainees (no actual payout)
    """
    paying   = sorted([s for s in summary if s["name"] not in trainee_names],
                      key=lambda x: x["total"], reverse=True)
    trainees = [s for s in summary if s["name"] in trainee_names]
    grand    = sum(s["total"] for s in paying)
    ITEMS    = ["出席率", "死活題", "次一手", "輸棋討論", "AI人機大戰", "新銳循環賽"]
    EMOJIS   = {"出席率":"📍","死活題":"🧩","次一手":"🎯","輸棋討論":"🗣️","AI人機大戰":"🤖","新銳循環賽":"⚔️"}

    html = (
        '<div style="overflow-x:auto;border-radius:14px;'
        'border:1px solid #E5E7EB;box-shadow:0 1px 4px rgba(0,0,0,0.05);">'
        '<table style="width:100%;border-collapse:collapse;'
        'font-family:\'Inter\',\'Helvetica Neue\',sans-serif;">'
    )

    # 表頭
    html += (
        '<thead><tr style="background:#F9FAFB;border-bottom:2px solid #E5E7EB;">'
        '<th style="padding:12px 12px;text-align:center;font-size:12px;color:#9CA3AF;width:40px;">#</th>'
        '<th style="padding:12px 20px;text-align:left;font-size:13px;font-weight:700;color:#374151;">姓 名</th>'
    )
    for item in ITEMS:
        html += (
            f'<th style="padding:10px 14px;text-align:center;vertical-align:middle;">'
            f'<span style="display:block;font-size:15px;">{EMOJIS[item]}</span>'
            f'<span style="font-size:11px;font-weight:400;color:#9CA3AF;">${ITEM_PRICES[item]}</span></th>'
        )
    html += (
        '<th style="padding:10px 12px;text-align:center;vertical-align:middle;">'
        '<span style="display:block;font-size:15px;">🔥</span>'
        '<span style="font-size:11px;font-weight:400;color:#9CA3AF;">$300</span></th>'
        '<th style="padding:12px 20px;text-align:right;font-size:13px;font-weight:700;color:#374151;white-space:nowrap;">本月獎金</th>'
        '</tr></thead><tbody>'
    )

    def render_row(s: dict, rank_tag: str, bg: str, is_trainee: bool = False) -> str:
        name_style = (
            "font-size:16px;font-weight:700;color:#94A3B8;"   # 生力軍灰色
            if is_trainee else
            "font-size:16px;font-weight:700;color:#111827;"
        )
        r = (
            f'<tr style="background:{bg};border-bottom:1px solid #F3F4F6;">'
            f'<td style="padding:14px 12px;text-align:center;font-size:14px;">{rank_tag}</td>'
            f'<td style="padding:14px 20px;{name_style}">{s["name"]}'
        )
        if is_trainee:
            r += '<span style="margin-left:8px;font-size:12px;background:#E0F2FE;color:#0369A1;padding:2px 8px;border-radius:10px;font-weight:600;">生力軍</span>'
        r += '</td>'

        for item in ITEMS:
            cnt = s["item_counts"].get(item, 0)
            cell_bg = "#EEF2FF" if is_trainee and cnt > 0 else ("#D1FAE5" if cnt > 0 else bg)
            txt_col = "#4F46E5" if is_trainee and cnt > 0 else ("#065F46" if cnt > 0 else "#E5E7EB")
            bdr     = "#C7D2FE" if is_trainee and cnt > 0 else ("#A7F3D0" if cnt > 0 else "#F3F4F6")
            if cnt > 0:
                r += (
                    f'<td style="background:{cell_bg};padding:12px 14px;text-align:center;'
                    f'border-left:1px solid {bdr};font-weight:700;color:{txt_col};font-size:15px;">'
                    f'{cnt}</td>'
                )
            else:
                r += (
                    f'<td style="background:{bg};padding:12px 14px;text-align:center;'
                    f'border-left:1px solid #F3F4F6;color:#E5E7EB;font-size:13px;">-</td>'
                )

        # 替代任務
        alt = s["alt_count"]
        if alt > 0:
            r += (
                f'<td style="background:#FEF3C7;padding:12px 14px;text-align:center;'
                f'border-left:1px solid #FDE68A;font-weight:700;color:#92400E;font-size:15px;">'
                f'{alt}</td>'
            )
        else:
            r += (
                f'<td style="background:{bg};padding:12px 14px;text-align:center;'
                f'border-left:1px solid #F3F4F6;color:#E5E7EB;font-size:13px;">-</td>'
            )

        # 獎金欄
        if is_trainee:
            r += (
                '<td style="padding:14px 20px;text-align:right;">'
                '<span style="background:#E0F2FE;color:#0369A1;padding:4px 12px;'
                'border-radius:12px;font-size:13px;font-weight:600;">🌱 練習</span></td>'
            )
        elif s["total"] > 0:
            r += (
                f'<td style="padding:14px 20px;text-align:right;font-size:18px;'
                f'font-weight:800;color:#1E3A8A;white-space:nowrap;">${s["total"]:,}</td>'
            )
        else:
            r += '<td style="padding:14px 20px;text-align:right;font-size:14px;color:#D1D5DB;">$0</td>'

        r += '</tr>'
        return r

    medals = ["🥇","🥈","🥉"]
    for rank, s in enumerate(paying, 1):
        bg  = "#FFFFFF" if rank % 2 == 1 else "#FAFAFA"
        tag = medals[rank-1] if rank <= 3 else str(rank)
        html += render_row(s, tag, bg, is_trainee=False)

    # 生力軍分隔 + 列
    if trainees:
        colspan_total = len(ITEMS) + 3
        html += (
            f'<tr><td colspan="{colspan_total}" style="padding:8px 20px;'
            f'background:#F0F9FF;font-size:12px;font-weight:600;color:#0369A1;'
            f'letter-spacing:0.06em;border-top:2px solid #BAE6FD;border-bottom:1px solid #BAE6FD;">'
            f'🌱 生力軍（練習參與，不計入正式發放）</td></tr>'
        )
        for s in trainees:
            html += render_row(s, "🌱", "#F8FAFC", is_trainee=True)

    # 合計列（只含正式選手）
    colspan_mid = len(ITEMS) + 1
    html += (
        f'<tr style="background:#EFF6FF;border-top:2px solid #BFDBFE;">'
        f'<td colspan="2" style="padding:16px 20px;font-size:14px;font-weight:700;'
        f'color:#1E3A8A;letter-spacing:0.04em;">📋 本月正式選手發放合計</td>'
        f'<td colspan="{colspan_mid}" style="padding:16px;"></td>'
        f'<td style="padding:16px 20px;text-align:right;font-size:22px;'
        f'font-weight:900;color:#1E3A8A;white-space:nowrap;">${grand:,}</td>'
        f'</tr>'
    )
    html += '</tbody></table></div>'
    return html

def calc_bonus(player: str, week_dates: list[date], all_data: list) -> tuple[int, int, int]:
    week_strs     = {d.strftime("%Y-%m-%d") for d in week_dates}
    weekly_earned = 0
    total_earned  = 0
    for row in all_data[1:]:
        if len(row) > STATUS_COL and row[1] == player and row_status(row) == "已核准":
            rb = sum(
                ITEM_PRICES[item]
                for item, col in ITEM_COL_IDX.items()
                if col < len(row) and row[col] == "V"
            )
            if len(row) > ALT_COL:
                alt = row[ALT_COL].strip()
                if alt in ALT_TASK_PRICES:
                    rb += ALT_TASK_PRICES[alt]
            total_earned += rb
            if row[2] in week_strs:
                weekly_earned += rb
    achievement = round(weekly_earned / WEEKLY_TARGET * 100)
    return weekly_earned, achievement, total_earned


# ── HTML 熱圖渲染（取代 st.dataframe，獲得完整 CSS 控制權）────────
def render_heatmap_html(df: pd.DataFrame) -> str:
    cols = list(df.columns)

    # 表頭標籤：Emoji + 名稱 + 價格小字
    EMOJI_MAP = {
        "出席率":     "📍",
        "死活題":     "🧩",
        "次一手":     "🎯",
        "輸棋討論":   "🗣️",
        "AI人機大戰": "🤖",
        "新銳循環賽": "⚔️",
    }
    col_headers = {}
    for item, price in ITEM_PRICES.items():
        emoji = EMOJI_MAP.get(item, "")
        col_headers[item] = (
            f'<span style="display:block;font-size:13px;font-weight:700;'
            f'color:#374151;letter-spacing:0.04em;">{emoji} {item}</span>'
            f'<span style="font-size:11px;font-weight:400;color:#9CA3AF;">${price}</span>'
        )
    col_headers["🔥替代"] = (
        '<span style="display:block;font-size:13px;font-weight:700;'
        'color:#374151;letter-spacing:0.04em;">🔥 替代任務</span>'
    )

    # 表格外框
    html = (
        '<div style="overflow-x:auto;border-radius:14px;'
        'border:1px solid #E5E7EB;box-shadow:0 1px 4px rgba(0,0,0,0.05);">'
        '<table style="width:100%;border-collapse:collapse;'
        'font-family:\'Inter\',\'Helvetica Neue\',sans-serif;">'
    )

    # 表頭列
    html += (
        '<thead><tr style="background:#F9FAFB;border-bottom:2px solid #E5E7EB;">'
        '<th style="padding:14px 20px;text-align:left;font-size:13px;'
        'font-weight:700;color:#374151;letter-spacing:0.05em;'
        'text-transform:uppercase;white-space:nowrap;">日 期</th>'
    )
    for col in cols:
        html += (
            f'<th style="padding:14px 16px;text-align:center;vertical-align:middle;">'
            f'{col_headers.get(col, col)}</th>'
        )
    html += "</tr></thead><tbody>"

    # 資料列
    for i, (idx, row) in enumerate(df.iterrows()):
        row_bg = "#FFFFFF" if i % 2 == 0 else "#FAFAFA"
        html += (
            f'<tr style="background:{row_bg};border-bottom:1px solid #F3F4F6;">'
            f'<td style="padding:14px 20px;font-size:15px;font-weight:600;'
            f'color:#374151;white-space:nowrap;">{idx}</td>'
        )
        for col in cols:
            val = str(row[col])
            if val.startswith("✅"):
                extra = val[2:].strip()
                inner = (
                    '<span style="font-size:20px;color:#065F46;font-weight:700;'
                    'line-height:1;">✓</span>'
                )
                if extra:
                    inner += (
                        f'<br><span style="font-size:12px;color:#065F46;'
                        f'font-weight:600;">{extra}</span>'
                    )
                html += (
                    f'<td style="background:#D1FAE5;padding:12px 16px;'
                    f'text-align:center;vertical-align:middle;'
                    f'border-left:1px solid #A7F3D0;">{inner}</td>'
                )
            elif val.startswith("🟡"):
                extra = val[2:].strip()
                inner = (
                    '<span style="font-size:18px;color:#92400E;font-weight:700;'
                    'line-height:1;">⏳</span>'
                )
                if extra:
                    inner += (
                        f'<br><span style="font-size:12px;color:#92400E;'
                        f'font-weight:600;">{extra}</span>'
                    )
                html += (
                    f'<td style="background:#FEF3C7;padding:12px 16px;'
                    f'text-align:center;vertical-align:middle;'
                    f'border-left:1px solid #FDE68A;">{inner}</td>'
                )
            else:
                # 未申報：純白空格，無任何視覺雜訊
                html += (
                    f'<td style="background:{row_bg};padding:12px 16px;'
                    f'text-align:center;vertical-align:middle;'
                    f'border-left:1px solid #F3F4F6;">&nbsp;</td>'
                )
        html += "</tr>"

    html += "</tbody></table></div>"
    return html


# ── 菁英隊 Google Sheet 連線與資料函式 ───────────────────────────
@st.cache_resource
def get_elite_ws():
    sh = get_gc().open_by_key(BONUS_DB_ID)
    try:
        ws = sh.worksheet(ELITE_TAB)
    except Exception:
        ws = sh.add_worksheet(title=ELITE_TAB, rows=500, cols=8)
        ws.append_row(list(ELITE_COL.keys()))
    return ws

@st.cache_data(ttl=30)
def load_elite_data() -> list:
    return get_elite_ws().get_all_values()

def record_elite_attendance(rec_date: date, attending: list[str], note: str = "") -> int:
    """記錄當日出席名單，跳過已存在的 player+date 組合，回傳新增筆數"""
    from datetime import datetime
    existing = load_elite_data()
    date_str = rec_date.strftime("%Y-%m-%d")
    already  = {row[2] for row in existing[1:] if len(row) > 2 and row[1] == date_str}
    ws       = get_elite_ws()
    now_str  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_rows = [
        [now_str, date_str, p, str(ELITE_DAILY_BONUS), note]
        for p in attending if p not in already
    ]
    if new_rows:
        ws.append_rows(new_rows)
        load_elite_data.clear()
    return len(new_rows)

def delete_elite_record(rec_date: date, player: str) -> None:
    """刪除特定日期某選手的出席記錄（誤打卡用）"""
    date_str = rec_date.strftime("%Y-%m-%d")
    ws       = get_elite_ws()
    data     = ws.get_all_values()
    for i, row in enumerate(data[1:], start=2):
        if len(row) > 2 and row[1] == date_str and row[2] == player:
            ws.delete_rows(i)
            load_elite_data.clear()
            return

def get_elite_month_summary(year: int, month: int, elite_data: list) -> dict:
    """回傳 {player: [date_str, ...]} 當月已出席日期清單"""
    prefix  = f"{year:04d}-{month:02d}"
    summary = {p: [] for p in ELITE_PLAYERS}
    seen    = set()
    for row in elite_data[1:]:
        if len(row) > 2 and row[1].startswith(prefix):
            key = (row[2], row[1])
            if key not in seen:
                seen.add(key)
                if row[2] in summary:
                    summary[row[2]].append(row[1])
                else:
                    summary[row[2]] = [row[1]]
    return summary

def generate_elite_report_html(year: int, month: int, elite_data: list) -> str:
    import calendar
    prefix    = f"{year:04d}-{month:02d}"
    today_str = date.today().strftime("%Y/%m/%d")
    summary   = get_elite_month_summary(year, month, elite_data)
    n_days    = calendar.monthrange(year, month)[1]
    days      = [f"{month:02d}/{d:02d}" for d in range(1, n_days + 1)]
    day_strs  = [f"{year:04d}-{month:02d}-{d:02d}" for d in range(1, n_days + 1)]

    # 每位選手的出席天數與金額
    player_rows = ""
    grand_days  = 0
    grand_total = 0
    for player in ELITE_PLAYERS:
        attended = set(summary.get(player, []))
        cnt      = len(attended)
        amt      = cnt * ELITE_DAILY_BONUS
        grand_days  += cnt
        grand_total += amt
        day_cells = "".join(
            f"<td style='text-align:center;background:#D1FAE5;color:#065F46;"
            f"font-weight:700;'>✓</td>"
            if ds in attended else
            f"<td style='text-align:center;color:#E5E7EB;'>-</td>"
            for ds in day_strs
        )
        player_rows += (
            f"<tr><td style='padding:8px 12px;font-weight:700;white-space:nowrap;'>{player}</td>"
            f"{day_cells}"
            f"<td style='padding:8px 12px;text-align:center;font-weight:700;'>{cnt}</td>"
            f"<td style='padding:8px 12px;text-align:right;font-weight:800;"
            f"color:#1E3A8A;white-space:nowrap;'>${amt:,}</td></tr>"
        )

    day_headers = "".join(
        f"<th style='text-align:center;padding:6px 4px;min-width:28px;"
        f"font-size:10px;'>{d}</th>"
        for d in days
    )
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head><meta charset="utf-8">
<title>菁英隊 出席獎金 {year}年{month:02d}月</title>
<style>
@page {{ margin:10mm; size:A3 landscape; }}
body {{ font-family:'Noto Sans TC','PingFang TC',sans-serif;background:white;
       color:#111827;font-size:12px; }}
h1 {{ font-size:18px;font-weight:800;margin-bottom:4px; }}
.sub {{ color:#6B7280;font-size:12px;margin-bottom:16px; }}
table {{ width:100%;border-collapse:collapse; }}
th {{ background:#1E3A8A;color:white;padding:7px 4px;font-size:11px; }}
tr:nth-child(even) {{ background:#F9FAFB; }}
td {{ border:1px solid #E5E7EB; }}
.grand {{ background:#EFF6FF;font-weight:800; }}
.footer {{ margin-top:16px;font-size:10px;color:#9CA3AF; }}
</style></head>
<body>
<h1>菁英隊 出席獎金明細</h1>
<div class="sub">
  {year}年{month:02d}月 &nbsp;·&nbsp; 出席費 ${ELITE_DAILY_BONUS:,}/天 &nbsp;·&nbsp; 產出日期：{today_str}
</div>
<table>
<thead><tr>
  <th style="text-align:left;padding:7px 12px;min-width:80px;">姓名</th>
  {day_headers}
  <th style="text-align:center;padding:7px 8px;">天數</th>
  <th style="text-align:right;padding:7px 12px;min-width:70px;">金額</th>
</tr></thead>
<tbody>
{player_rows}
<tr class="grand">
  <td style="padding:8px 12px;">合計</td>
  <td colspan="{n_days}"></td>
  <td style="padding:8px 12px;text-align:center;">{grand_days}</td>
  <td style="padding:8px 12px;text-align:right;font-size:15px;">${grand_total:,}</td>
</tr>
</tbody>
</table>
<div class="footer">※ 出席費 ${ELITE_DAILY_BONUS:,}/天 &nbsp;·&nbsp; 產出日期：{today_str}</div>
</body></html>"""


# ── 交流費用 Google Sheet 連線與資料函式 ─────────────────────────
@st.cache_resource
def get_exchange_ws():
    sh = get_gc().open_by_key(BONUS_DB_ID)
    try:
        ws = sh.worksheet(EXCHANGE_TAB)
    except Exception:
        ws = sh.add_worksheet(title=EXCHANGE_TAB, rows=500, cols=8)
        ws.append_row(list(EXCH_COL.keys()))
    return ws

@st.cache_data(ttl=30)
def load_exchange_data() -> list:
    return get_exchange_ws().get_all_values()

def add_exchange_record(rec_date: date, item_desc: str, amount: int,
                        status: str, note: str = "") -> None:
    from datetime import datetime
    get_exchange_ws().append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        rec_date.strftime("%Y-%m-%d"),
        item_desc, str(amount), status, note,
    ])
    load_exchange_data.clear()

def update_exchange_status(row_idx: int, new_status: str) -> None:
    get_exchange_ws().update_cell(row_idx, EXCH_COL["狀態"] + 1, new_status)
    load_exchange_data.clear()

def generate_exchange_report_html(year: int, month: int, exch_data: list) -> str:
    prefix    = f"{year:04d}-{month:02d}"
    today_str = date.today().strftime("%Y/%m/%d")
    records   = [r for r in exch_data[1:] if len(r) > 4 and r[1].startswith(prefix)]
    total       = sum(int(r[3]) for r in records)
    outstanding = sum(int(r[3]) for r in records if r[4] == "🔴 已墊付")

    rows_html = "".join(
        f"<tr>"
        f"<td style='padding:8px 14px;'>{r[1]}</td>"
        f"<td style='padding:8px 14px;'>{r[2]}</td>"
        f"<td style='padding:8px 14px;text-align:right;'>${int(r[3]):,}</td>"
        f"<td style='padding:8px 14px;text-align:center;'>{r[4]}</td>"
        f"<td style='padding:8px 14px;color:#6B7280;'>{r[5] if len(r) > 5 else ''}</td>"
        f"</tr>"
        for r in records
    )
    warn_row = (
        f"<tr><td colspan='5' style='padding:10px 14px;color:#DC2626;font-weight:700;'>"
        f"⚠️ 尚未報帳金額：${outstanding:,}</td></tr>"
        if outstanding > 0 else ""
    )
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head><meta charset="utf-8">
<title>交流費用 {year}年{month:02d}月</title>
<style>
@page {{ margin:20mm; }}
body {{ font-family:'Noto Sans TC','PingFang TC',sans-serif;background:white;color:#111827; }}
h1 {{ font-size:18px;font-weight:800;margin-bottom:4px; }}
.sub {{ color:#6B7280;font-size:13px;margin-bottom:20px; }}
table {{ width:100%;border-collapse:collapse; }}
th {{ background:#065F46;color:white;padding:9px 14px;font-size:12px;text-align:left; }}
tr:nth-child(even) {{ background:#F9FAFB; }}
td {{ border-bottom:1px solid #E5E7EB;font-size:13px; }}
.grand {{ background:#ECFDF5;font-weight:800; }}
.footer {{ margin-top:20px;font-size:11px;color:#9CA3AF; }}
</style></head>
<body>
<h1>交流費用明細</h1>
<div class="sub">{year}年{month:02d}月 &nbsp;·&nbsp; 教練墊付 &nbsp;·&nbsp; 產出日期：{today_str}</div>
<table>
<thead><tr>
  <th>日期</th><th>交流項目</th>
  <th style="text-align:right">金額</th><th style="text-align:center">狀態</th><th>備注</th>
</tr></thead>
<tbody>
{rows_html}
<tr class="grand">
  <td colspan="2" style="padding:10px 14px;">本月合計</td>
  <td style="padding:10px 14px;text-align:right;font-size:16px;">${total:,}</td>
  <td colspan="2"></td>
</tr>
{warn_row}
</tbody>
</table>
<div class="footer">
  ※ 此報表為教練交流費用墊付記錄，與棋院訓練獎金系統完全分開 &nbsp;·&nbsp; 產出日期：{today_str}
</div>
</body></html>"""


# ── 院長訓練總覽 HTML 生成 ───────────────────────────────────────
def render_principal_matrix_html(
    summary_cur: list, summary_prev: list, year: int, month: int
) -> str:
    """summary_cur/prev: list of {name, item_counts, alt_count, days}"""
    TASK_ITEMS = list(ITEM_COL_IDX.keys())
    TASK_ICON  = {"出席率":"📌","死活題":"🧩","次一手":"🎯","輸棋討論":"🗣️","AI人機大戰":"🤖","新銳循環賽":"⚔️"}
    # Thresholds: [green_min, yellow_min]
    THRESHOLDS = {
        "出席率":     (14, 9),
        "死活題":     (12, 8),
        "次一手":     (5,  3),
        "輸棋討論":   (5,  3),
        "AI人機大戰": (7,  4),
        "新銳循環賽": (7,  4),
    }
    def cell_style(item, cnt):
        g, y = THRESHOLDS[item]
        if cnt >= g:   return "background:#D1FAE5;color:#065F46;"
        if cnt >= y:   return "background:#FEF3C7;color:#92400E;"
        if cnt == 0:   return "background:#FEE2E2;color:#DC2626;opacity:.5;"
        return                "background:#FEE2E2;color:#DC2626;"
    def arrow(c, p):
        d = c - p
        if p == 0 or abs(d) <= 1: return ""
        if d > 0: return f'<span style="color:#059669;font-size:9px;"> ▲{d}</span>'
        return          f'<span style="color:#DC2626;font-size:9px;"> ▼{abs(d)}</span>'

    prev_map = {s["name"]: s for s in summary_prev}

    # Header
    th = "".join(
        f'<th style="background:#1F2937;color:white;padding:7px 8px;'
        f'text-align:center;font-size:11px;white-space:nowrap;">'
        f'{TASK_ICON[item]} {item}<br>'
        f'<span style="font-weight:400;font-size:9px;opacity:.7;">${ITEM_PRICES[item]}/次</span></th>'
        for item in TASK_ITEMS
    )

    # Rows
    rows = ""
    totals = {item: 0 for item in TASK_ITEMS}
    total_alt = 0
    n = len(summary_cur)
    for s in summary_cur:
        nm = s["name"]
        prev = prev_map.get(nm, {"item_counts": {i: 0 for i in TASK_ITEMS}, "alt_count": 0})
        cells = ""
        for item in TASK_ITEMS:
            cnt  = s["item_counts"].get(item, 0)
            pcnt = prev["item_counts"].get(item, 0)
            totals[item] += cnt
            cells += (f'<td style="padding:7px 8px;text-align:center;'
                      f'{cell_style(item, cnt)}font-weight:700;">'
                      f'{cnt}{arrow(cnt, pcnt)}</td>')
        alt = s.get("alt_count", 0)
        total_alt += alt
        p_alt = prev.get("alt_count", 0)
        rows += (f'<tr><td style="padding:7px 12px;font-weight:800;'
                 f'white-space:nowrap;border-right:2px solid #E5E7EB;">{nm}</td>'
                 f'{cells}'
                 f'<td style="padding:7px 8px;text-align:center;'
                 f'background:#F3F4F6;color:#374151;font-weight:600;">'
                 f'{alt}{arrow(alt, p_alt)}</td></tr>')

    # Totals / averages row
    tot_cells = ""
    for item in TASK_ITEMS:
        avg = totals[item] / n if n else 0
        tot_cells += (f'<td style="padding:7px 8px;text-align:center;'
                      f'background:#EFF6FF;font-weight:900;color:#1E3A8A;">'
                      f'{totals[item]}<br>'
                      f'<span style="font-size:9px;font-weight:400;color:#6B7280;">均{avg:.1f}</span></td>')
    tot_cells += (f'<td style="padding:7px 8px;text-align:center;'
                  f'background:#EFF6FF;font-weight:900;color:#1E3A8A;">{total_alt}</td>')

    # Difficulty spotlight (lowest avg column)
    min_item = min(TASK_ITEMS[1:], key=lambda i: totals[i] / n if n else 0)  # skip 出席率
    spotlight = (f'<div style="margin-top:8px;background:#FEF3C7;border-left:3px solid #D97706;'
                 f'padding:7px 12px;border-radius:0 6px 6px 0;font-size:11.5px;color:#92400E;">'
                 f'⚠️ <strong>{year}年{month:02d}月 最需加強項目：{TASK_ICON[min_item]} {min_item}</strong>'
                 f'（全隊均 {totals[min_item]/n:.1f} 次）</div>')

    return f"""
<style>
.pm-tbl {{width:100%;border-collapse:collapse;font-size:12.5px;}}
.pm-tbl td,.pm-tbl th {{border:1px solid #E5E7EB;}}
.pm-tbl tbody tr:hover td {{filter:brightness(0.95);}}
</style>
<table class="pm-tbl">
<thead>
  <tr>
    <th style="background:#1F2937;color:white;padding:7px 12px;text-align:left;min-width:80px;">選手</th>
    {th}
    <th style="background:#1F2937;color:white;padding:7px 8px;text-align:center;font-size:11px;">🔥 替代任務</th>
  </tr>
</thead>
<tbody>
{rows}
<tr style="border-top:2px solid #93C5FD;">
  <td style="padding:7px 12px;font-weight:900;background:#EFF6FF;color:#1E3A8A;border-right:2px solid #E5E7EB;">全隊合計</td>
  {tot_cells}
</tr>
</tbody>
</table>
{spotlight}
"""




# ── 個人月報 HTML 生成 ────────────────────────────────────────────
def generate_player_monthly_report_html(
    player: str, year: int, month: int, all_data: list
) -> str:
    """Clean single-player A4 monthly training report."""
    from datetime import date as _date
    today_str = _date.today().strftime("%Y/%m/%d")

    s = calc_monthly_bonus_one(player, year, month, all_data)
    is_trainee = player in TRAINEE_PLAYERS

    TASK_ITEMS = list(ITEM_COL_IDX.keys())
    TASK_ICON  = {
        "出席率":"📌","死活題":"🧩","次一手":"🎯",
        "輸棋討論":"🗣️","AI人機大戰":"🤖","新銳循環賽":"⚔️",
    }
    THRESHOLDS = {
        "出席率":(14,9),"死活題":(12,8),"次一手":(5,3),
        "輸棋討論":(5,3),"AI人機大戰":(7,4),"新銳循環賽":(7,4),
    }

    task_rows = ""
    for item in TASK_ITEMS:
        cnt   = s["item_counts"].get(item, 0)
        amt   = cnt * ITEM_PRICES[item]
        g, y  = THRESHOLDS[item]
        if cnt >= g:
            status_col, status_txt, bar_col = "#059669", "良好 ✓", "#10B981"
        elif cnt >= y:
            status_col, status_txt, bar_col = "#D97706", "尚可", "#F59E0B"
        elif cnt > 0:
            status_col, status_txt, bar_col = "#DC2626", "加強", "#EF4444"
        else:
            status_col, status_txt, bar_col = "#9CA3AF", "未完成", "#E5E7EB"
        pct  = int(cnt / g * 100) if g else 0
        pct  = min(pct, 100)
        task_rows += f"""
<tr>
  <td class="item-icon">{TASK_ICON[item]}</td>
  <td class="item-name">{item}</td>
  <td class="item-price">${ITEM_PRICES[item]:,}/次</td>
  <td class="item-cnt">{cnt} 次</td>
  <td class="item-bar">
    <div class="bar-track">
      <div class="bar-fill" style="width:{pct}%;background:{bar_col};"></div>
    </div>
  </td>
  <td class="item-status" style="color:{status_col};">{status_txt}</td>
  <td class="item-amt">{"+" if amt > 0 else ""}${amt:,}</td>
</tr>"""

    alt_cnt = s.get("alt_count", 0)
    alt_amt = alt_cnt * 300
    alt_row = f"""
<tr class="alt-row">
  <td class="item-icon">🔥</td>
  <td class="item-name">替代任務</td>
  <td class="item-price">$300/次</td>
  <td class="item-cnt">{alt_cnt} 次</td>
  <td class="item-bar"></td>
  <td class="item-status" style="color:#6B7280;">{"已完成" if alt_cnt > 0 else "-"}</td>
  <td class="item-amt">{"+" if alt_amt > 0 else ""}${alt_amt:,}</td>
</tr>"""

    total     = s["total"]
    days      = s["days"]
    target_txt = "（生力軍：訓練期，不計發放）" if is_trainee else f"${total:,}"
    badge     = '<span class="trainee-badge">生力軍</span>' if is_trainee else ""

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="utf-8">
<title>{player} 訓練月報 {year}年{month:02d}月</title>
<style>
@page {{ size: A4; margin: 18mm 20mm; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'Noto Sans TC','PingFang TC','Microsoft JhengHei',sans-serif;
        background: white; color: #111827; font-size: 12.5px; }}

/* Header */
.header {{ border-bottom: 3px solid #1F2937; padding-bottom: 10px; margin-bottom: 18px; }}
.org  {{ font-size: 11px; color: #6B7280; letter-spacing: .5px; margin-bottom: 4px; }}
.name {{ font-size: 28px; font-weight: 900; color: #1F2937; display: flex; align-items: center; gap: 10px; }}
.month-badge {{ font-size: 13px; font-weight: 700; background: #1F2937; color: white;
                padding: 4px 12px; border-radius: 20px; }}
.trainee-badge {{ font-size: 11px; background: #E0F2FE; color: #0369A1;
                  padding: 3px 10px; border-radius: 10px; font-weight: 600; }}

/* KPI strip */
.kpi-strip {{ display: flex; gap: 12px; margin-bottom: 20px; }}
.kpi {{ flex: 1; border: 1px solid #E5E7EB; border-radius: 8px; padding: 10px 14px; }}
.kpi-label {{ font-size: 10px; color: #6B7280; margin-bottom: 3px; }}
.kpi-value {{ font-size: 20px; font-weight: 900; color: #1F2937; }}
.kpi-unit  {{ font-size: 11px; color: #6B7280; font-weight: 400; margin-left: 2px; }}

/* Task table */
table {{ width: 100%; border-collapse: collapse; margin-bottom: 6px; }}
th {{ background: #1F2937; color: white; font-size: 10.5px; padding: 7px 10px;
      text-align: left; white-space: nowrap; }}
th.r {{ text-align: right; }}
td {{ border-bottom: 1px solid #F3F4F6; padding: 9px 10px; vertical-align: middle; }}
.item-icon  {{ width: 28px; font-size: 14px; text-align: center; }}
.item-name  {{ font-weight: 700; font-size: 13px; }}
.item-price {{ font-size: 10px; color: #9CA3AF; white-space: nowrap; }}
.item-cnt   {{ text-align: center; font-weight: 700; font-size: 13px; width: 52px; }}
.item-bar   {{ width: 100px; }}
.bar-track  {{ height: 8px; background: #F3F4F6; border-radius: 4px; overflow: hidden; }}
.bar-fill   {{ height: 100%; border-radius: 4px; }}
.item-status{{ text-align: center; font-weight: 700; font-size: 11.5px; width: 60px; white-space: nowrap; }}
.item-amt   {{ text-align: right; font-weight: 800; font-size: 13px; white-space: nowrap; color: #1E3A8A; }}
.alt-row td {{ background: #FAFAF9; color: #6B7280; }}
.alt-row .item-amt {{ color: #374151; }}

/* Total row */
.total-row td {{ background: #EFF6FF; border-top: 2px solid #93C5FD;
                 font-weight: 900; color: #1E3A8A; padding: 10px; }}

/* Legend */
.legend {{ display: flex; gap: 14px; font-size: 10px; color: #6B7280;
           margin: 8px 0 20px; flex-wrap: wrap; }}
.dot {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block;
        margin-right: 3px; vertical-align: middle; }}

/* Footer */
.footer {{ margin-top: 20px; border-top: 1px solid #E5E7EB; padding-top: 8px;
           font-size: 9.5px; color: #9CA3AF; display: flex; justify-content: space-between; }}
</style>
</head>
<body>

<div class="header">
  <div class="org">🏆 新銳隊 個人訓練月報</div>
  <div class="name">
    {player} {badge}
    <span class="month-badge">{year}年{month:02d}月</span>
  </div>
</div>

<div class="kpi-strip">
  <div class="kpi">
    <div class="kpi-label">出席天數</div>
    <div class="kpi-value">{days}<span class="kpi-unit">天</span></div>
  </div>
  <div class="kpi">
    <div class="kpi-label">任務類型完成</div>
    <div class="kpi-value">{sum(1 for v in s["item_counts"].values() if v > 0)}<span class="kpi-unit"> / {len(TASK_ITEMS)} 項</span></div>
  </div>
  <div class="kpi" style="border-color:#93C5FD;background:#EFF6FF;">
    <div class="kpi-label">本月訓練獎金</div>
    <div class="kpi-value" style="color:#1E3A8A;">{target_txt}</div>
  </div>
</div>

<table>
<thead>
  <tr>
    <th style="width:28px;"></th>
    <th>訓練項目</th>
    <th>單價</th>
    <th style="text-align:center;">完成次數</th>
    <th>達成進度</th>
    <th style="text-align:center;">狀態</th>
    <th class="r">小計</th>
  </tr>
</thead>
<tbody>
{task_rows}
{alt_row}
<tr class="total-row">
  <td colspan="6">本月訓練獎金合計{" （生力軍不計入發放）" if is_trainee else ""}</td>
  <td style="text-align:right;">${total:,}</td>
</tr>
</tbody>
</table>

<div class="legend">
  <span><span class="dot" style="background:#10B981;"></span>良好：達標</span>
  <span><span class="dot" style="background:#F59E0B;"></span>尚可：接近目標</span>
  <span><span class="dot" style="background:#EF4444;"></span>加強：需努力</span>
  <span>·　進度條以「良好門檻」為 100%</span>
</div>

<div class="footer">
  <span>新銳隊 教育訓練管理系統</span>
  <span>產出日期：{today_str}</span>
</div>

</body>
</html>"""


# ── 院長訓練總覽 獨立 HTML 報告 ──────────────────────────────────
def generate_principal_report_html(
    summary_cur: list, summary_prev: list, year: int, month: int
) -> str:
    """Standalone A4 printable HTML for the principal training overview."""
    from datetime import date as _date
    today_str = _date.today().strftime("%Y/%m/%d")

    TASK_ITEMS = list(ITEM_COL_IDX.keys())
    TASK_ICON  = {"出席率":"📌","死活題":"🧩","次一手":"🎯","輸棋討論":"🗣️","AI人機大戰":"🤖","新銳循環賽":"⚔️"}
    THRESHOLDS = {
        "出席率":     (14, 9),
        "死活題":     (12, 8),
        "次一手":     (5,  3),
        "輸棋討論":   (5,  3),
        "AI人機大戰": (7,  4),
        "新銳循環賽": (7,  4),
    }

    def cell_style(item, cnt):
        g, y = THRESHOLDS[item]
        if cnt >= g:   return "background:#D1FAE5;color:#065F46;"
        if cnt >= y:   return "background:#FEF3C7;color:#92400E;"
        if cnt == 0:   return "background:#FEE2E2;color:#DC2626;opacity:.5;"
        return                "background:#FEE2E2;color:#DC2626;"

    def arrow(c, p):
        d = c - p
        if p == 0 or abs(d) <= 1: return ""
        if d > 0: return f'<span style="color:#059669;font-size:9px;"> ▲{d}</span>'
        return          f'<span style="color:#DC2626;font-size:9px;"> ▼{abs(d)}</span>'

    prev_map = {s["name"]: s for s in summary_prev}

    # Table header
    th = "".join(
        f'<th>{TASK_ICON[item]} {item}<br><span class="price">${ITEM_PRICES[item]}/次</span></th>'
        for item in TASK_ITEMS
    )

    # Data rows
    rows = ""
    totals   = {item: 0 for item in TASK_ITEMS}
    total_alt = 0
    n = len(summary_cur)
    for s in summary_cur:
        nm   = s["name"]
        prev = prev_map.get(nm, {"item_counts": {i: 0 for i in TASK_ITEMS}, "alt_count": 0})
        cells = ""
        for item in TASK_ITEMS:
            cnt  = s["item_counts"].get(item, 0)
            pcnt = prev["item_counts"].get(item, 0)
            totals[item] += cnt
            cells += f'<td style="{cell_style(item, cnt)}font-weight:700;">{cnt}{arrow(cnt, pcnt)}</td>'
        alt   = s.get("alt_count", 0)
        p_alt = prev.get("alt_count", 0)
        total_alt += alt
        rows += (f'<tr><td class="name">{nm}</td>{cells}'
                 f'<td style="background:#F3F4F6;color:#374151;font-weight:600;">{alt}{arrow(alt, p_alt)}</td></tr>')

    # Totals row
    tot_cells = ""
    for item in TASK_ITEMS:
        avg = totals[item] / n if n else 0
        tot_cells += (f'<td style="background:#EFF6FF;font-weight:900;color:#1E3A8A;">'
                      f'{totals[item]}<br><span class="price">均{avg:.1f}</span></td>')
    tot_cells += f'<td style="background:#EFF6FF;font-weight:900;color:#1E3A8A;">{total_alt}</td>'

    # Spotlight
    min_item   = min(TASK_ITEMS[1:], key=lambda i: totals[i] / n if n else 0)
    spotlight  = (f'<div class="spotlight">⚠️ <strong>{year}年{month:02d}月 最需加強：{TASK_ICON[min_item]} {min_item}</strong>'
                  f'（全隊均 {totals[min_item]/n:.1f} 次）</div>')

    # Individual bar charts
    player_cards = ""
    max_per_item = {item: max((s["item_counts"].get(item, 0) for s in summary_cur), default=1) or 1
                    for item in TASK_ITEMS}
    for s in summary_cur:
        nm   = s["name"]
        bars = ""
        for item in TASK_ITEMS:
            cnt  = s["item_counts"].get(item, 0)
            g, y = THRESHOLDS[item]
            pct  = int(cnt / max_per_item[item] * 100)
            bar_color = "#10B981" if cnt >= g else ("#F59E0B" if cnt >= y else "#EF4444")
            bars += (f'<div class="bar-row">'
                     f'<div class="bar-label">{TASK_ICON[item]} {item}</div>'
                     f'<div class="bar-track">'
                     f'<div class="bar-fill" style="width:{pct}%;background:{bar_color};"></div>'
                     f'</div>'
                     f'<div class="bar-val">{cnt}</div></div>')
        alt = s.get("alt_count", 0)
        player_cards += (f'<div class="card">'
                         f'<div class="card-name">{nm}</div>'
                         f'{bars}'
                         f'<div class="card-alt">🔥 替代任務 {alt} 次</div>'
                         f'</div>')

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="utf-8">
<title>新銳隊 院長訓練總覽 {year}年{month:02d}月</title>
<style>
@page {{ size: A4; margin: 15mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family: 'Noto Sans TC','PingFang TC','Microsoft JhengHei',sans-serif;
        background: white; color: #111827; font-size: 12px; margin: 0; padding: 0; }}
h1 {{ font-size: 20px; font-weight: 900; margin: 0 0 2px; }}
.sub {{ color: #6B7280; font-size: 11px; margin-bottom: 14px; }}
/* Matrix table */
.pm-tbl {{ width: 100%; border-collapse: collapse; font-size: 11.5px; margin-bottom: 6px; }}
.pm-tbl th {{ background: #1F2937; color: white; padding: 6px 7px;
              text-align: center; font-size: 10.5px; white-space: nowrap; }}
.pm-tbl th.name-col {{ text-align: left; padding-left: 10px; min-width: 70px; }}
.pm-tbl td {{ border: 1px solid #E5E7EB; padding: 6px 7px; text-align: center; }}
.pm-tbl td.name {{ padding: 6px 10px; font-weight: 800; white-space: nowrap;
                   border-right: 2px solid #E5E7EB; text-align: left; }}
.pm-tbl .tot td {{ background: #EFF6FF; font-weight: 900; color: #1E3A8A;
                   border-top: 2px solid #93C5FD; }}
.price {{ font-weight: 400; font-size: 9px; opacity: .7; }}
.spotlight {{ margin-top: 7px; background: #FEF3C7; border-left: 3px solid #D97706;
              padding: 6px 10px; border-radius: 0 5px 5px 0; font-size: 11px; color: #92400E; }}
/* Legend */
.legend {{ display: flex; gap: 14px; margin: 10px 0 14px; font-size: 10.5px; }}
.legend span {{ display: flex; align-items: center; gap: 4px; }}
.dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
/* Player cards */
.cards {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 14px; }}
.card {{ border: 1px solid #E5E7EB; border-radius: 6px; padding: 8px 10px; }}
.card-name {{ font-size: 13px; font-weight: 800; color: #1F2937;
              margin-bottom: 6px; border-bottom: 1px solid #F3F4F6; padding-bottom: 4px; }}
.bar-row {{ display: flex; align-items: center; gap: 5px; margin-bottom: 3px; }}
.bar-label {{ width: 72px; font-size: 9.5px; white-space: nowrap; color: #374151; flex-shrink: 0; }}
.bar-track {{ flex: 1; height: 8px; background: #F3F4F6; border-radius: 4px; overflow: hidden; }}
.bar-fill {{ height: 100%; border-radius: 4px; transition: width .3s; }}
.bar-val {{ width: 20px; text-align: right; font-size: 10px; font-weight: 700; color: #374151; flex-shrink: 0; }}
.card-alt {{ font-size: 9.5px; color: #6B7280; margin-top: 5px; padding-top: 4px;
             border-top: 1px dashed #E5E7EB; }}
.section-title {{ font-size: 13px; font-weight: 800; color: #1F2937; margin: 14px 0 6px; }}
.footer {{ margin-top: 14px; font-size: 9.5px; color: #9CA3AF; border-top: 1px solid #E5E7EB;
           padding-top: 6px; }}
</style>
</head>
<body>

<h1>🏆 新銳隊 院長訓練總覽</h1>
<div class="sub">{year}年{month:02d}月 &nbsp;·&nbsp; ▲▼ 與上月比較 &nbsp;·&nbsp; 產出日期：{today_str}</div>

<div class="section-title">📊 各選手任務完成矩陣</div>
<table class="pm-tbl">
<thead>
  <tr>
    <th class="name-col">選手</th>
    {th}
    <th>🔥 替代任務</th>
  </tr>
</thead>
<tbody>
{rows}
<tr class="tot">
  <td class="name">全隊合計</td>
  {tot_cells}
</tr>
</tbody>
</table>
{spotlight}

<div class="legend">
  <span><span class="dot" style="background:#10B981;"></span>綠色 = 表現良好</span>
  <span><span class="dot" style="background:#F59E0B;"></span>黃色 = 尚可，可加強</span>
  <span><span class="dot" style="background:#EF4444;"></span>紅色 = 需要關注</span>
  <span style="color:#6B7280;">·　數字後 ▲▼ 為與上月差值</span>
</div>

<div class="section-title">📈 個人訓練進度圖</div>
<div class="cards">{player_cards}</div>

<div class="footer">※ 新銳隊 教育訓練管理系統 &nbsp;·&nbsp; 產出日期：{today_str}</div>
</body>
</html>"""

# ── 週報告 HTML 生成 ─────────────────────────────────────────────
def generate_weekly_report_html(players_list: list, wd: list[date], all_data: list) -> str:
    trainee_set = set(TRAINEE_PLAYERS)
    week_start  = wd[0].strftime("%Y年%m月%d日")
    week_end    = wd[6].strftime("%m月%d日")
    today_str   = date.today().strftime("%Y/%m/%d")

    rows_html = ""
    for player in players_list:
        if player in trainee_set:
            continue
        weekly, achievement, total = calc_bonus(player, wd, all_data)
        if achievement >= 100:
            color, icon, note = "#059669", "✅", "達標"
        elif achievement >= 70:
            color, icon, note = "#D97706", "⚡", "需加速"
        else:
            color, icon, note = "#DC2626", "⚠️", "落後"
        rows_html += (
            f"<tr>"
            f"<td style='padding:10px 16px;font-size:15px;font-weight:700;'>{player}</td>"
            f"<td style='padding:10px 16px;text-align:right;'>${weekly:,}</td>"
            f"<td style='padding:10px 16px;text-align:center;color:{color};font-weight:700;'>{achievement}%</td>"
            f"<td style='padding:10px 16px;text-align:center;'>{icon} {note}</td>"
            f"<td style='padding:10px 16px;text-align:right;color:#6B7280;'>${total:,}</td>"
            f"</tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="utf-8">
<title>新銳隊 週報告 {week_start}</title>
<style>
@page {{ margin: 20mm; }}
body {{ font-family: 'Noto Sans TC','PingFang TC','Microsoft JhengHei',sans-serif;
       background: white; color: #111827; }}
h1 {{ font-size: 22px; font-weight: 800; margin-bottom: 4px; }}
.subtitle {{ color: #6B7280; font-size: 14px; margin-bottom: 24px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
th {{ background: #F3F4F6; padding: 10px 16px; font-size: 12px; font-weight: 700;
      color: #6B7280; text-align: left; border-bottom: 2px solid #E5E7EB; }}
tr:nth-child(even) {{ background: #F9FAFB; }}
td {{ border-bottom: 1px solid #E5E7EB; }}
.footer {{ margin-top: 24px; font-size: 12px; color: #9CA3AF; }}
</style>
</head>
<body>
<h1>新銳隊 週訓練報告</h1>
<div class="subtitle">
  {week_start} ～ {week_end} &nbsp;·&nbsp;
  週目標 ${WEEKLY_TARGET:,}／人
</div>
<table>
<thead><tr>
  <th>選手</th>
  <th style="text-align:right">本週獎金</th>
  <th style="text-align:center">達成率</th>
  <th style="text-align:center">狀態</th>
  <th style="text-align:right">累計獎金</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table>
<div class="footer">
  ※ 以上數據僅含教練已核准項目 &nbsp;·&nbsp; 產出日期：{today_str}
</div>
</body>
</html>"""


# ── 月度財務 HTML 生成 ────────────────────────────────────────────
def generate_monthly_finance_html(players_list: list, year: int, month: int, all_data: list) -> str:
    trainee_set    = set(TRAINEE_PLAYERS)
    formal_players = [p for p in players_list if p not in trainee_set]
    today_str      = date.today().strftime("%Y/%m/%d")
    ITEMS = ["出席率", "死活題", "次一手", "輸棋討論", "AI人機大戰", "新銳循環賽"]

    rows_data = sorted(
        [{"name": p, **calc_monthly_bonus_one(p, year, month, all_data)} for p in formal_players],
        key=lambda x: x["total"], reverse=True,
    )
    grand_total = sum(r["total"] for r in rows_data)

    rows_html = ""
    for r in rows_data:
        cells = ""
        for item in ITEMS:
            cnt    = r["item_counts"].get(item, 0)
            amount = cnt * ITEM_PRICES[item]
            if cnt > 0:
                cells += (
                    f"<td style='text-align:center;background:#F0FDF4;'>"
                    f"{cnt}次<br><small style='color:#065F46;'>${amount:,}</small></td>"
                )
            else:
                cells += "<td style='text-align:center;color:#D1D5DB;'>-</td>"
        alt = r["alt_count"]
        if alt > 0:
            cells += (
                f"<td style='text-align:center;background:#FFFBEB;'>"
                f"{alt}次<br><small style='color:#92400E;'>${alt*300:,}</small></td>"
            )
        else:
            cells += "<td style='text-align:center;color:#D1D5DB;'>-</td>"
        rows_html += (
            f"<tr><td style='padding:10px 16px;font-weight:700;'>{r['name']}</td>"
            f"{cells}"
            f"<td style='padding:10px 16px;text-align:right;font-weight:800;"
            f"color:#1E3A8A;white-space:nowrap;'>${r['total']:,}</td></tr>"
        )

    # 合計列
    rows_html += (
        f"<tr style='background:#EFF6FF;'>"
        f"<td style='padding:10px 16px;font-weight:700;'>合計發放</td>"
        f"<td colspan='{len(ITEMS)+1}'></td>"
        f"<td style='padding:10px 16px;text-align:right;font-size:17px;"
        f"font-weight:900;color:#1E3A8A;white-space:nowrap;'>${grand_total:,}</td></tr>"
    )

    item_headers = ""
    for item in ITEMS:
        item_headers += (
            f"<th style='text-align:center;'>{item}<br>"
            f"<small style='color:#BAE6FD;'>${ITEM_PRICES[item]}/次</small></th>"
        )

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="utf-8">
<title>新銳隊 {year}年{month:02d}月 訓練獎金發放明細</title>
<style>
@page {{ margin: 15mm; size: A4 landscape; }}
body {{ font-family: 'Noto Sans TC','PingFang TC','Microsoft JhengHei',sans-serif;
       background: white; color: #111827; font-size: 13px; }}
h1 {{ font-size: 18px; font-weight: 800; margin-bottom: 4px; }}
.subtitle {{ color: #6B7280; font-size: 12px; margin-bottom: 20px; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ background: #1E3A8A; color: white; padding: 8px 12px; font-size: 11px;
      font-weight: 700; text-align: center; }}
tr:nth-child(even) {{ background: #F9FAFB; }}
td {{ border: 1px solid #E5E7EB; font-size: 12px; }}
.footer {{ margin-top: 20px; font-size: 11px; color: #9CA3AF; }}
small {{ font-size: 10px; display: block; }}
</style>
</head>
<body>
<h1>新銳隊 訓練獎金發放明細</h1>
<div class="subtitle">
  {year}年{month:02d}月 &nbsp;·&nbsp; 正式選手 {len(formal_players)} 位 &nbsp;·&nbsp;
  各有 $100,000 專案額度
</div>
<table>
<thead><tr>
  <th style="text-align:left;min-width:80px;">姓名</th>
  {item_headers}
  <th style="text-align:center;">🔥替代任務<br>
    <small style="color:#BAE6FD;">$300/次</small></th>
  <th style="text-align:right;min-width:80px;">本月獎金</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table>
<div class="footer">
  ※ 僅含教練已核准項目 &nbsp;·&nbsp; 產出日期：{today_str} &nbsp;·&nbsp;
  生力軍（{"、".join(TRAINEE_PLAYERS)}）不計入發放
</div>
</body>
</html>"""


# ── 月度週報彙整 HTML 生成 ────────────────────────────────────────
def generate_monthly_weekly_report_html(players_list: list, year: int,
                                        month: int, all_data: list) -> str:
    import calendar
    trainee_set = set(TRAINEE_PLAYERS)
    formal      = [p for p in players_list if p not in trainee_set]
    today_str   = date.today().strftime("%Y/%m/%d")
    first_day   = date(year, month, 1)
    last_day    = date(year, month, calendar.monthrange(year, month)[1])

    # 找出所有與本月有重疊的週（週一開始）
    start_monday = first_day - timedelta(days=first_day.weekday())
    weeks = []
    cur = start_monday
    while cur <= last_day:
        week = [cur + timedelta(days=i) for i in range(7)]
        if week[-1] >= first_day:
            weeks.append(week)
        cur += timedelta(weeks=1)

    weeks_html = ""
    for week in weeks:
        ws = week[0].strftime("%m/%d")
        we = week[6].strftime("%m/%d")
        rows = ""
        for player in formal:
            weekly, achievement, _ = calc_bonus(player, week, all_data)
            if achievement >= 100:
                color, status = "#059669", "✅ 達標"
            elif achievement >= 70:
                color, status = "#D97706", "⚡ 需加速"
            else:
                color, status = "#DC2626", "⚠️ 落後"
            rows += (
                f"<tr>"
                f"<td style='padding:7px 14px;font-weight:600;'>{player}</td>"
                f"<td style='padding:7px 14px;text-align:right;'>${weekly:,}</td>"
                f"<td style='padding:7px 14px;text-align:center;"
                f"color:{color};font-weight:700;'>{achievement}%</td>"
                f"<td style='padding:7px 14px;'>{status}</td>"
                f"</tr>"
            )
        weeks_html += f"""
        <div style='margin-bottom:28px;page-break-inside:avoid;'>
        <div style='font-size:14px;font-weight:800;color:#1E3A8A;margin-bottom:8px;
                    border-bottom:2px solid #BFDBFE;padding-bottom:5px;'>
            {ws} ～ {we} &nbsp;·&nbsp; 週目標 ${WEEKLY_TARGET:,}／人
        </div>
        <table style='width:100%;border-collapse:collapse;font-size:13px;'>
        <thead><tr style='background:#F3F4F6;'>
            <th style='padding:7px 14px;text-align:left;border-bottom:1px solid #E5E7EB;'>選手</th>
            <th style='padding:7px 14px;text-align:right;border-bottom:1px solid #E5E7EB;'>本週獎金</th>
            <th style='padding:7px 14px;text-align:center;border-bottom:1px solid #E5E7EB;'>達成率</th>
            <th style='padding:7px 14px;border-bottom:1px solid #E5E7EB;'>狀態</th>
        </tr></thead>
        <tbody>{rows}</tbody>
        </table></div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head><meta charset="utf-8">
<title>新銳隊 {year}年{month:02d}月 月度週報</title>
<style>
@page {{ margin:20mm; }}
body {{ font-family:'Noto Sans TC','PingFang TC',sans-serif;background:white;color:#111827; }}
h1 {{ font-size:20px;font-weight:800;margin-bottom:4px; }}
.sub {{ color:#6B7280;font-size:13px;margin-bottom:24px; }}
tr:nth-child(even) {{ background:#F9FAFB; }}
.footer {{ margin-top:24px;font-size:11px;color:#9CA3AF; }}
</style></head>
<body>
<h1>新銳隊 月度週報</h1>
<div class="sub">{year}年{month:02d}月 &nbsp;·&nbsp; 產出日期：{today_str}</div>
{weeks_html}
<div class="footer">※ 以上數據僅含教練已核准項目</div>
</body></html>"""


# ═════════════════════════════════════════════════════════════════
# 頁面設定
# ═════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="戰情台 | 新銳隊",
    page_icon="📊",
    layout="wide",
)

st.markdown("""
<style>
/* ═══════════════════════════════════════════════
   0. 字體載入
═══════════════════════════════════════════════ */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

/* ═══════════════════════════════════════════════
   1. 全域 Reset & 背景
═══════════════════════════════════════════════ */
*, *::before, *::after { box-sizing: border-box; }

html, body, .stApp {
    font-family: 'Inter','SF Pro Display','Helvetica Neue',sans-serif !important;
    background-color: #F8F9FA !important;
    color: #111827 !important;
}

.block-container {
    padding-top:    2rem    !important;
    padding-bottom: 3rem    !important;
    max-width:      1200px  !important;
    margin-left:    auto    !important;
    margin-right:   auto    !important;
}

#MainMenu, footer, header { visibility: hidden; }

/* ═══════════════════════════════════════════════
   2. 卡片容器（st.container border=True）
═══════════════════════════════════════════════ */
[data-testid="stVerticalBlockBorderWrapper"] > div {
    background:    #FFFFFF                              !important;
    border:        1px solid #E5E7EB                    !important;
    border-radius: 16px                                 !important;
    box-shadow:    0 4px 6px -1px rgba(0,0,0,0.05),
                   0 2px 4px -1px rgba(0,0,0,0.03)     !important;
    padding:       8px 6px                              !important;
}

/* ═══════════════════════════════════════════════
   3. 頁首文字
═══════════════════════════════════════════════ */
.page-brand {
    font-family:   'Inter','SF Pro Display',sans-serif;
    font-size:     24px;
    font-weight:   800;
    color:         #111827;
    letter-spacing: -0.01em;
    margin-bottom: 4px;
}

.page-subtitle {
    font-size:     14px;
    color:         #6B7280;
    margin-bottom: 28px;
    font-weight:   500;
}

/* ═══════════════════════════════════════════════
   4. 選手大名字
═══════════════════════════════════════════════ */
.big-name {
    font-family:    'Inter','SF Pro Display',sans-serif !important;
    font-size:      60px          !important;
    font-weight:    800           !important;
    color:          #111827       !important;
    letter-spacing: 6px           !important;
    text-align:     center        !important;
    padding:        20px 0 4px    !important;
    text-shadow:    none          !important;
    line-height:    1.1           !important;
}

.week-label {
    text-align:    center;
    color:         #6B7280;
    font-size:     15px;
    font-weight:   500;
    margin-bottom: 24px;
}

/* ═══════════════════════════════════════════════
   5. KPI 卡片（純 HTML，外層容器）
═══════════════════════════════════════════════ */
.kpi-row {
    display:       flex;
    gap:           16px;
    margin-bottom: 28px;
}

.kpi-card {
    flex:          1;
    background:    #FFFFFF;
    border:        1px solid #E5E7EB;
    border-radius: 14px;
    padding:       24px 28px;
    box-shadow:    0 4px 6px -1px rgba(0,0,0,0.05),
                   0 2px 4px -1px rgba(0,0,0,0.03);
}

/* 數值：大字、深色 */
.kpi-value {
    font-family:    'Inter','SF Pro Display',sans-serif;
    font-size:      48px;
    font-weight:    800;
    color:          #1E3A8A;       /* 深藍 */
    line-height:    1.05;
    letter-spacing: -0.03em;
}
.kpi-value-warn {
    font-size:     42px;
    font-weight:   800;
    color:         #DC2626;        /* 正紅（< 70%） */
    line-height:   1.05;
    letter-spacing: -0.03em;
}
.kpi-value-amber {
    font-size:     42px;
    font-weight:   800;
    color:         #D97706;        /* 琥珀橙 */
    line-height:   1.05;
    letter-spacing: -0.03em;
}
.kpi-value-ok {
    font-size:     42px;
    font-weight:   800;
    color:         #059669;        /* 翠綠 */
    line-height:   1.05;
    letter-spacing: -0.03em;
}

/* 標籤：16px 深灰 */
.kpi-label {
    font-family:    'Inter','SF Pro Display',sans-serif;
    font-size:      16px;
    font-weight:    500;
    color:          #4B5563;
    margin-top:     8px;
}

.kpi-note {
    font-size:  14px;
    color:      #9CA3AF;
    margin-top: 4px;
    font-weight: 500;
}

/* ═══════════════════════════════════════════════
   6. 進度條
═══════════════════════════════════════════════ */
.prog-wrap {
    background:    #E5E7EB;
    border-radius: 999px;
    height:        8px;
    margin-top:    12px;
    overflow:      hidden;
}
.prog-bar {
    height:        8px;
    border-radius: 999px;
}

/* ═══════════════════════════════════════════════
   7. Section 標籤
═══════════════════════════════════════════════ */
.sec-label {
    font-family:    'Inter','SF Pro Display',sans-serif;
    font-size:      11px;
    font-weight:    700;
    color:          #9CA3AF;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    padding-bottom: 10px;
    border-bottom:  1px solid #F3F4F6;
    margin-bottom:  20px;
}

/* ═══════════════════════════════════════════════
   8. 待審核 Badge
═══════════════════════════════════════════════ */
.pending-badge {
    display:       inline-block;
    background:    #FEF3C7;
    border:        1px solid #FCD34D;
    border-radius: 20px;
    padding:       5px 16px;
    margin:        4px;
    font-size:     14px;
    font-weight:   600;
    color:         #92400E;
}

/* ═══════════════════════════════════════════════
   9. 圖例
═══════════════════════════════════════════════ */
.legend {
    font-size:   13px;
    color:       #9CA3AF;
    text-align:  center;
    margin-top:  12px;
    font-weight: 500;
}

/* ═══════════════════════════════════════════════
   10. Streamlit 原生元件
═══════════════════════════════════════════════ */
[data-testid="stAlert"] {
    border-radius: 10px !important;
}

.stButton > button {
    border-radius:  10px !important;
    font-family:    'Inter',sans-serif !important;
    font-weight:    600 !important;
    font-size:      14px !important;
    letter-spacing: 0.02em !important;
}

.stSelectbox > div > div {
    border-radius: 10px !important;
    font-family:   'Inter',sans-serif !important;
}
.stSelectbox label {
    font-size:   13px !important;
    color:       #6B7280 !important;
    font-weight: 500 !important;
}

hr { border-color: #F3F4F6 !important; margin: 20px 0 !important; }
</style>
""", unsafe_allow_html=True)


# ── 資料載入 ──────────────────────────────────────────────────────
if "week_offset" not in st.session_state:
    st.session_state.week_offset = 0
if "month_offset" not in st.session_state:
    st.session_state.month_offset = 0
if "elite_month_offset" not in st.session_state:
    st.session_state.elite_month_offset = 0
if "report_month_offset" not in st.session_state:
    st.session_state.report_month_offset = 0
if "report_week_offset" not in st.session_state:
    st.session_state.report_week_offset = 0
if "exchange_month_offset" not in st.session_state:
    st.session_state.exchange_month_offset = 0
if "champ_month_offset" not in st.session_state:
    st.session_state.champ_month_offset = 0
if "principal_month_offset" not in st.session_state:
    st.session_state.principal_month_offset = 0

all_data   = load_bonus_data()
week_dates = get_week_dates(st.session_state.week_offset)
players    = load_player_list()

# ── 頁首 ─────────────────────────────────────────────────────────
today_str_header = date.today().strftime("%Y 年 %m 月 %d 日")
st.markdown('<div class="page-brand">新銳隊</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="page-subtitle">📊 訓練獎金戰情台　·　{today_str_header}</div>',
    unsafe_allow_html=True,
)


# ═════════════════════════════════════════════════════════════════
# 上半：教練審核台
# ═════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.markdown('<div class="sec-label">🔍 今日審核台</div>', unsafe_allow_html=True)

    pending = get_pending_today(all_data)

    if not pending:
        st.success(f"✅ 今日無待審核申報")
    else:
        st.markdown(
            f"<span style='font-size:16px;font-weight:600;color:#111827;'>"
            f"待審核：{len(pending)} 筆</span>",
            unsafe_allow_html=True,
        )
        st.write("")

        # ── 個別核准列表 ──────────────────────────────────────────
        for row_idx, name in pending:
            col_name, col_btn = st.columns([5, 1])
            with col_name:
                st.markdown(
                    f'<div style="padding:8px 0;">'
                    f'<span class="pending-badge">⏳ {name}</span></div>',
                    unsafe_allow_html=True,
                )
            with col_btn:
                if st.button("✅ 核准", key=f"approve_{row_idx}"):
                    with st.spinner(f"核准 {name}..."):
                        approve_one(row_idx, all_data)
                    st.rerun()

        st.divider()

        # ── 一鍵全部核准 ─────────────────────────────────────────
        if st.button("✅ 一鍵核准今日全部", type="primary"):
            with st.spinner("核准中..."):
                count    = approve_all_pending(all_data)
                all_data = load_bonus_data()
            st.success(f"已核准 {count} 筆！綠格立即更新。")
            st.rerun()

    # ── 補交待審核 ───────────────────────────────────────────────
    makeup_pending = get_pending_makeup(all_data)
    if makeup_pending:
        st.divider()
        st.markdown(
            '<div class="sec-label" style="margin-top:4px;">📬 補交待審核</div>',
            unsafe_allow_html=True,
        )
        for row_idx, pname, sub_date in makeup_pending:
            col_info, col_btn = st.columns([5, 1])
            with col_info:
                st.markdown(
                    f'<div style="padding:8px 0;">'
                    f'<span class="pending-badge">📬 {pname}</span>'
                    f'<span style="font-size:12px;color:#9CA3AF;margin-left:10px;">'
                    f'補交日期：{sub_date}</span></div>',
                    unsafe_allow_html=True,
                )
            with col_btn:
                if st.button("✅ 核准", key=f"makeup_{row_idx}"):
                    with st.spinner(f"核准中..."):
                        approve_one(row_idx, all_data)
                    st.rerun()


# ═════════════════════════════════════════════════════════════════
# 下半：院長熱圖矩陣
# ═════════════════════════════════════════════════════════════════
if not players:
    st.warning("無法讀取選手名單")
    st.stop()

with st.container(border=True):
    st.markdown('<div class="sec-label">📊 任務熱圖矩陣</div>', unsafe_allow_html=True)

    # 選手下拉
    selected = st.selectbox("選擇選手", players, label_visibility="collapsed")

    # ── 週切換導航 ───────────────────────────────────────────────
    week_start = week_dates[0].strftime("%m/%d")
    week_end   = week_dates[6].strftime("%m/%d")
    offset     = st.session_state.week_offset
    week_label = "本週" if offset == 0 else (f"上週" if offset == -1 else f"{abs(offset)} 週前")

    nav_l, nav_mid, nav_r = st.columns([1, 3, 1])
    with nav_l:
        if st.button("← 上週", use_container_width=True):
            st.session_state.week_offset -= 1
            st.rerun()
    with nav_mid:
        st.markdown(
            f"<div style='text-align:center;font-size:15px;font-weight:600;"
            f"color:#374151;padding:8px 0;'>"
            f"{week_label}　{week_start} － {week_end}</div>",
            unsafe_allow_html=True,
        )
    with nav_r:
        if st.button("下週 →", use_container_width=True,
                     disabled=(offset >= 0)):
            st.session_state.week_offset += 1
            st.rerun()

    # 大名字
    st.markdown(f'<div class="big-name">{selected}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="week-label">{week_start} － {week_end}</div>',
        unsafe_allow_html=True,
    )

    # ── 計算 KPI ─────────────────────────────────────────────────
    weekly_earned, achievement, total_earned = calc_bonus(selected, week_dates, all_data)
    remaining = PROJECT_TOTAL - total_earned

    if achievement < 70:
        val_cls, rate_note, bar_color = "kpi-value-warn",  "進度落後 ⚠️",  "#EF4444"
    elif achievement < 90:
        val_cls, rate_note, bar_color = "kpi-value-amber", "需加速 ⚡",    "#D97706"
    elif achievement <= 110:
        val_cls, rate_note, bar_color = "kpi-value-ok",    "進度完美 ✅",  "#059669"
    else:
        val_cls, rate_note, bar_color = "kpi-value-amber", "超前燃燒 🔥", "#D97706"

    bar_width = min(achievement, 100)

    # ── KPI 卡片（在熱圖上方）───────────────────────────────────
    st.markdown(f"""
    <div class="kpi-row">
      <div class="kpi-card">
        <div class="kpi-value">${weekly_earned:,}</div>
        <div class="kpi-label">本週已累計獎金（元）</div>
      </div>
      <div class="kpi-card">
        <div class="{val_cls}">{achievement}%</div>
        <div class="kpi-label">【目標達成率】</div>
        <div class="kpi-note">{rate_note}</div>
        <div class="prog-wrap">
          <div class="prog-bar" style="width:{bar_width}%;background:{bar_color};"></div>
        </div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value">${remaining:,}</div>
        <div class="kpi-label">10 萬專案剩餘額度（元）</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── HTML 熱圖（df.to_html 替代方案，獲得完整 CSS 控制）──────
    df       = build_heatmap(selected, week_dates, all_data)
    heatmap_html = render_heatmap_html(df)
    st.markdown(heatmap_html, unsafe_allow_html=True)

    st.markdown(
        '<div class="legend">'
        '<span style="background:#D1FAE5;padding:2px 10px;border-radius:4px;'
        'margin-right:8px;color:#065F46;">✓ 已核准</span>'
        '<span style="background:#FEF3C7;padding:2px 10px;border-radius:4px;'
        'margin-right:8px;color:#92400E;">⏳ 待審核</span>'
        '<span style="background:#F9FAFB;padding:2px 10px;border-radius:4px;'
        'border:1px solid #E5E7EB;color:#9CA3AF;">空白 未申報</span>'
        '</div>',
        unsafe_allow_html=True,
    )


# ═════════════════════════════════════════════════════════════════
# 月度獎金總表
# ═════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.markdown('<div class="sec-label">📅 月度獎金總表</div>', unsafe_allow_html=True)

    mo   = st.session_state.month_offset
    year, month = get_month_year(mo)
    month_label = f"{year} 年 {month:02d} 月"

    m_l, m_mid, m_r = st.columns([1, 3, 1])
    with m_l:
        if st.button("← 上月", use_container_width=True, key="prev_month"):
            st.session_state.month_offset -= 1
            st.rerun()
    with m_mid:
        st.markdown(
            f"<div style='text-align:center;font-size:16px;font-weight:700;"
            f"color:#374151;padding:8px 0;'>{month_label}</div>",
            unsafe_allow_html=True,
        )
    with m_r:
        if st.button("下月 →", use_container_width=True, key="next_month",
                     disabled=(mo >= 0)):
            st.session_state.month_offset += 1
            st.rerun()

    st.write("")

    # 計算所有選手該月獎金
    monthly_summary = [
        {"name": p, **calc_monthly_bonus_one(p, year, month, all_data)}
        for p in players
    ]

    trainee_set   = set(TRAINEE_PLAYERS)
    paying_only   = [s for s in monthly_summary if s["name"] not in trainee_set]
    n_paying      = len(paying_only)
    grand_total   = sum(s["total"] for s in paying_only)

    # 方案整體完成度（歷史累計，不限月份）
    paying_names   = [p for p in players if p not in trainee_set]
    total_all_time = calc_total_paid_all(paying_names, all_data)
    total_budget   = n_paying * PROJECT_TOTAL
    completion_pct = round(total_all_time / total_budget * 100, 1) if total_budget > 0 else 0.0

    if completion_pct < 40:
        comp_color = "#059669"
    elif completion_pct < 70:
        comp_color = "#D97706"
    else:
        comp_color = "#1E3A8A"

    # 本月完成度（月目標 = 總預算 ÷ 專案月數 = 7人×10萬÷5個月 = 14萬）
    monthly_target   = (n_paying * PROJECT_TOTAL) // PROJECT_MONTHS
    monthly_comp_pct = round(grand_total / monthly_target * 100, 1) if monthly_target > 0 else 0.0

    if monthly_comp_pct < 70:
        mo_color = "#DC2626"
    elif monthly_comp_pct < 90:
        mo_color = "#D97706"
    else:
        mo_color = "#059669"

    # 月度 KPI 卡片
    st.markdown(f"""
    <div class="kpi-row">
      <div class="kpi-card">
        <div class="kpi-value">${grand_total:,}</div>
        <div class="kpi-label">本月正式選手發放合計（元）</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value" style="color:{mo_color};">{monthly_comp_pct}%</div>
        <div class="kpi-label">本月完成度</div>
        <div class="kpi-note">已發 ${grand_total:,}／月目標 ${monthly_target:,}</div>
        <div class="prog-wrap">
          <div class="prog-bar" style="width:{min(monthly_comp_pct,100)}%;background:{mo_color};"></div>
        </div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value" style="color:{comp_color};">{completion_pct}%</div>
        <div class="kpi-label">方案整體完成度</div>
        <div class="kpi-note">已累計發出 ${total_all_time:,}／目標 ${total_budget:,}</div>
        <div class="prog-wrap">
          <div class="prog-bar" style="width:{min(completion_pct,100)}%;background:{comp_color};"></div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # 月度總表
    st.markdown(render_monthly_table_html(monthly_summary, trainee_set), unsafe_allow_html=True)

    st.markdown(
        '<div class="legend" style="margin-top:12px;">'
        '數字 = 該月已核准次數　'
        '<span style="background:#D1FAE5;padding:2px 8px;border-radius:4px;color:#065F46;">綠色 已完成</span>　'
        '<span style="background:#FEF3C7;padding:2px 8px;border-radius:4px;color:#92400E;">橘色 替代任務</span>'
        '</div>',
        unsafe_allow_html=True,
    )


# ═════════════════════════════════════════════════════════════════
# 贊助冠軍經費追蹤
# ═════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.markdown('<div class="sec-label">🏆 贊助冠軍經費</div>', unsafe_allow_html=True)
    st.caption("資金來源：次一手贊助商 ｜ 與棋院訓練獎金完全分開記帳")

    champ_data = load_champion_data()

    # ── 快速新增 ─────────────────────────────────────────────────
    with st.expander("➕ 新增一筆冠軍獎金"):
        ci1, ci2 = st.columns(2)
        with ci1:
            item_label  = st.selectbox("比賽項目", list(CHAMPION_ITEMS.keys()), key="ci_item")
            item_amount = CHAMPION_ITEMS[item_label]
            st.caption(f"金額：**${item_amount}**")
        with ci2:
            all_champ_players = sorted(set(players) | set(NEXTMOVE_PLAYERS))
            ci_player = st.selectbox("獲獎選手", all_champ_players, key="ci_player")
        ci3, ci4 = st.columns(2)
        with ci3:
            ci_date   = st.date_input("比賽日期", value=date.today(), key="ci_date")
        with ci4:
            ci_status = st.selectbox("入帳狀態", CHAMPION_STATUS_OPTIONS, key="ci_status")
        ci_note = st.text_input("備注（選填）", key="ci_note", placeholder="例如：第3局")
        if st.button("💾 記帳", type="primary", use_container_width=True, key="ci_submit"):
            with st.spinner("記錄中..."):
                add_champion_record(ci_date, item_label, ci_player,
                                    item_amount, ci_status, ci_note)
            st.success(f"✅ 已記錄 {item_label}　{ci_player}　${item_amount}　{ci_status}")
            st.rerun()

    # ── 月份導覽（獨立）─────────────────────────────────────────
    mo_c = st.session_state.champ_month_offset
    yr_c, mo_c_num = get_month_year(mo_c)

    cm_l, cm_mid, cm_r = st.columns([1, 3, 1])
    with cm_l:
        if st.button("← 上月", use_container_width=True, key="champ_prev"):
            st.session_state.champ_month_offset -= 1
            st.rerun()
    with cm_mid:
        st.markdown(
            f"<div style='text-align:center;font-size:15px;font-weight:700;"
            f"color:#374151;padding:6px 0;'>{yr_c} 年 {mo_c_num:02d} 月</div>",
            unsafe_allow_html=True,
        )
    with cm_r:
        if st.button("下月 →", use_container_width=True, key="champ_next",
                     disabled=(mo_c >= 0)):
            st.session_state.champ_month_offset += 1
            st.rerun()

    # ── 本月紀錄 ─────────────────────────────────────────────────
    prefix_c = f"{yr_c:04d}-{mo_c_num:02d}"

    month_champ = [
        (i + 2, row)
        for i, row in enumerate(champ_data[1:])
        if len(row) > 5 and row[1].startswith(prefix_c)
    ]

    st.write("")
    if not month_champ:
        st.info(f"{yr_c}年{mo_c_num:02d}月 尚無記錄")
    else:
        total_c       = sum(int(r[4]) for _, r in month_champ)
        outstanding_c = sum(int(r[4]) for _, r in month_champ if r[5] == "🔴 已墊付")

        kc1, kc2, kc3 = st.columns(3)
        kc1.metric("本月發放次數", f"{len(month_champ)} 次")
        kc2.metric("本月發放金額", f"${total_c:,}")
        kc3.metric("⚠️ 未報帳金額", f"${outstanding_c:,}",
                   delta=f"-${outstanding_c:,}" if outstanding_c else None,
                   delta_color="inverse")

        st.write("")
        for row_idx, row in month_champ:
            d_str, item, player = row[1], row[2], row[3]
            amt, status = row[4], row[5]
            note = row[6] if len(row) > 6 else ""
            bg   = CHAMPION_STATUS_BG.get(status, "#FFFFFF")

            rc1, rc2, rc3, rc4 = st.columns([2, 4, 2, 3])
            rc1.markdown(
                f"<small style='color:#9CA3AF;'>{d_str}</small>",
                unsafe_allow_html=True,
            )
            rc2.markdown(f"**{item}**　{player}", unsafe_allow_html=True)
            rc3.markdown(f"**${int(amt):,}**", unsafe_allow_html=True)
            with rc4:
                new_s = st.selectbox(
                    "狀態",
                    CHAMPION_STATUS_OPTIONS,
                    index=CHAMPION_STATUS_OPTIONS.index(status)
                          if status in CHAMPION_STATUS_OPTIONS else 0,
                    key=f"cs_{row_idx}",
                    label_visibility="collapsed",
                )
                if new_s != status:
                    update_champion_status(row_idx, new_s)
                    st.rerun()

    # ── 獨立報表下載 ─────────────────────────────────────────────
    st.divider()
    champ_html  = generate_champion_report_html(yr_c, mo_c_num, champ_data)
    fname_champ = f"次一手贊助經費_{yr_c}{mo_c_num:02d}.html"
    st.download_button(
        label=f"📄 下載 {yr_c}年{mo_c_num:02d}月 贊助明細（交會計用）",
        data=champ_html.encode("utf-8"),
        file_name=fname_champ,
        mime="text/html",
        use_container_width=True,
        key="dl_champ",
    )


# ═════════════════════════════════════════════════════════════════
# 交流費用追蹤
# ═════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.markdown('<div class="sec-label">🌏 交流費用</div>', unsafe_allow_html=True)
    st.caption("教練墊付 ｜ 與棋院訓練獎金完全分開記帳")

    exch_data = load_exchange_data()

    # ── 快速新增 ─────────────────────────────────────────────────
    with st.expander("➕ 新增一筆交流費用"):
        import calendar as _cal2
        _today2 = date.today()
        _m_opts2 = list(range(8, 13)) if _today2.year == 2026 else list(range(1, 13))
        ex_col_y, ex_col_m, ex_col_d = st.columns(3)
        with ex_col_y:
            ex_year = st.selectbox("年", [2026, 2027],
                                   index=0 if _today2.year == 2026 else 1, key="ex_year")
        with ex_col_m:
            ex_month = st.selectbox("月", _m_opts2,
                                    format_func=lambda x: f"{x:02d} 月",
                                    index=len(_m_opts2) - 1, key="ex_month")
        with ex_col_d:
            _max_d2 = _cal2.monthrange(ex_year, ex_month)[1]
            _def_d2 = _today2.day if ex_month == _today2.month and ex_year == _today2.year else _max_d2
            ex_day = st.selectbox("日", list(range(1, _max_d2 + 1)),
                                  format_func=lambda x: f"{x:02d} 日",
                                  index=min(_def_d2, _max_d2) - 1, key="ex_day")
        ex_date = date(ex_year, ex_month, ex_day)

        ex_amount = st.number_input("金額（元）", min_value=0, step=100,
                                    value=0, key="ex_amount")
        ex_desc = st.text_input("交流項目描述", key="ex_desc",
                                placeholder="例如：中日韓交流餐費、場地費、住宿費...")
        ex3, ex4 = st.columns(2)
        with ex3:
            ex_status = st.selectbox("入帳狀態", EXCHANGE_STATUS_OPTIONS, key="ex_status")
        with ex4:
            ex_note = st.text_input("備注（選填）", key="ex_note")
        if st.button("💾 記帳", type="primary", use_container_width=True, key="ex_submit"):
            if not ex_desc.strip():
                st.warning("請填寫交流項目描述")
            elif ex_amount <= 0:
                st.warning("請填寫金額")
            else:
                with st.spinner("記錄中..."):
                    add_exchange_record(ex_date, ex_desc.strip(),
                                        int(ex_amount), ex_status, ex_note)
                st.success(f"✅ 已記錄　{ex_desc.strip()}　${int(ex_amount):,}　{ex_status}")
                st.rerun()

    # ── 月份導覽（獨立，不影響其他區塊）────────────────────────
    ex_mo_off = st.session_state.exchange_month_offset
    yr_ex, mo_ex_num = get_month_year(ex_mo_off)

    exm_l, exm_mid, exm_r = st.columns([1, 3, 1])
    with exm_l:
        if st.button("← 上月", use_container_width=True, key="ex_prev"):
            st.session_state.exchange_month_offset -= 1
            st.rerun()
    with exm_mid:
        st.markdown(
            f"<div style='text-align:center;font-size:15px;font-weight:700;"
            f"color:#374151;padding:6px 0;'>{yr_ex} 年 {mo_ex_num:02d} 月</div>",
            unsafe_allow_html=True,
        )
    with exm_r:
        if st.button("下月 →", use_container_width=True, key="ex_next",
                     disabled=(ex_mo_off >= 0)):
            st.session_state.exchange_month_offset += 1
            st.rerun()

    # ── 本月記錄 ─────────────────────────────────────────────────
    prefix_ex  = f"{yr_ex:04d}-{mo_ex_num:02d}"
    month_exch = [
        (i + 2, row)
        for i, row in enumerate(exch_data[1:])
        if len(row) > 4 and row[1].startswith(prefix_ex)
    ]

    st.write("")
    if not month_exch:
        st.info(f"{yr_ex}年{mo_ex_num:02d}月 尚無記錄")
    else:
        total_ex       = sum(int(r[3]) for _, r in month_exch)
        outstanding_ex = sum(int(r[3]) for _, r in month_exch if r[4] == "🔴 已墊付")

        ek1, ek2, ek3 = st.columns(3)
        ek1.metric("本月記錄筆數", f"{len(month_exch)} 筆")
        ek2.metric("本月墊付合計", f"${total_ex:,}")
        ek3.metric("⚠️ 未報帳金額", f"${outstanding_ex:,}",
                   delta=f"-${outstanding_ex:,}" if outstanding_ex else None,
                   delta_color="inverse")

        st.write("")
        for row_idx, row in month_exch:
            d_str  = row[1]
            item_d = row[2]
            amt    = row[3]
            status = row[4]

            re1, re2, re3, re4 = st.columns([2, 4, 2, 3])
            re1.markdown(
                f"<small style='color:#9CA3AF;'>{d_str}</small>",
                unsafe_allow_html=True,
            )
            re2.markdown(item_d)
            re3.markdown(f"**${int(amt):,}**", unsafe_allow_html=True)
            with re4:
                new_s = st.selectbox(
                    "狀態",
                    EXCHANGE_STATUS_OPTIONS,
                    index=EXCHANGE_STATUS_OPTIONS.index(status)
                          if status in EXCHANGE_STATUS_OPTIONS else 0,
                    key=f"es_{row_idx}",
                    label_visibility="collapsed",
                )
                if new_s != status:
                    update_exchange_status(row_idx, new_s)
                    st.rerun()

    # ── 報表下載 ─────────────────────────────────────────────────
    st.divider()
    exch_html  = generate_exchange_report_html(yr_ex, mo_ex_num, exch_data)
    fname_exch = f"交流費用_{yr_ex}{mo_ex_num:02d}.html"
    st.download_button(
        label=f"📄 下載 {yr_ex}年{mo_ex_num:02d}月 交流費用明細（交會計用）",
        data=exch_html.encode("utf-8"),
        file_name=fname_exch,
        mime="text/html",
        use_container_width=True,
        key="dl_exch",
    )


# ═════════════════════════════════════════════════════════════════
# 菁英隊 出席簽到
# ═════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.markdown('<div class="sec-label">👑 菁英隊 出席簽到</div>', unsafe_allow_html=True)
    st.caption(f"出席費 ${ELITE_DAILY_BONUS:,} 元／天")

    elite_data = load_elite_data()
    yr_e_off   = st.session_state.elite_month_offset
    yr_e, mo_e_num = get_month_year(yr_e_off)
    elite_month_label = f"{yr_e} 年 {mo_e_num:02d} 月"

    em_l, em_mid, em_r = st.columns([1, 3, 1])
    with em_l:
        if st.button("← 上月", use_container_width=True, key="elite_prev"):
            st.session_state.elite_month_offset -= 1
            st.rerun()
    with em_mid:
        st.markdown(
            f"<div style='text-align:center;font-size:15px;font-weight:700;"
            f"color:#374151;padding:6px 0;'>{elite_month_label}</div>",
            unsafe_allow_html=True,
        )
    with em_r:
        if st.button("下月 →", use_container_width=True, key="elite_next",
                     disabled=(yr_e_off >= 0)):
            st.session_state.elite_month_offset += 1
            st.rerun()

    if not ELITE_PLAYERS:
        st.warning("⚠️ 尚未設定菁英隊選手名單，請在程式碼 ELITE_PLAYERS 填入名單。")
    else:
        # ── 每日簽到 ─────────────────────────────────────────────
        with st.expander("📋 記錄今日出席"):
            import calendar as _cal
            _today = date.today()
            _year_opts  = [2026, 2027]
            _month_opts = list(range(8, 13)) if _today.year == 2026 else list(range(1, 13))
            ec_y, ec_m, ec_d = st.columns(3)
            with ec_y:
                e_year = st.selectbox("年", _year_opts,
                                      index=_year_opts.index(_today.year) if _today.year in _year_opts else 0,
                                      key="e_year")
            with ec_m:
                e_month = st.selectbox("月", _month_opts,
                                       format_func=lambda x: f"{x:02d} 月",
                                       index=len(_month_opts) - 1,
                                       key="e_month")
            with ec_d:
                _max_day = _cal.monthrange(e_year, e_month)[1]
                _default_day = _today.day if e_month == _today.month and e_year == _today.year else _max_day
                _default_day = min(_default_day, _max_day)
                e_day = st.selectbox("日", list(range(1, _max_day + 1)),
                                     format_func=lambda x: f"{x:02d} 日",
                                     index=_default_day - 1,
                                     key="e_day")
            e_date = date(e_year, e_month, e_day)
            st.caption(f"出席日期：{e_year}/{e_month:02d}/{e_day:02d}（{WEEKDAY_ZH[e_date.weekday()]}）")
            st.markdown("**勾選今日出席選手：**")

            date_str_e = e_date.strftime("%Y-%m-%d")
            already_in = {
                row[2] for row in elite_data[1:]
                if len(row) > 2 and row[1] == date_str_e
            }

            e_checks = {}
            cols_e   = st.columns(3)
            for idx, p in enumerate(ELITE_PLAYERS):
                with cols_e[idx % 3]:
                    default = p in already_in
                    e_checks[p] = st.checkbox(
                        f"{'✅ ' if default else ''}{p}",
                        value=default,
                        key=f"ep_{p}",
                    )

            e_note = st.text_input("備注（選填）", key="e_note")

            ec1, ec2 = st.columns(2)
            with ec1:
                if st.button("💾 送出今日出席", type="primary",
                             use_container_width=True, key="e_submit"):
                    attending = [p for p, v in e_checks.items() if v]
                    if not attending:
                        st.warning("請至少勾選一位出席選手")
                    else:
                        with st.spinner("記錄中..."):
                            added = record_elite_attendance(e_date, attending, e_note)
                        st.success(f"✅ 已記錄 {len(attending)} 人出席"
                                   + (f"（{added} 筆新增）" if added < len(attending) else ""))
                        st.rerun()
            with ec2:
                # 刪除誤打卡
                del_player = st.selectbox("刪除誤打卡", ["（不刪除）"] + ELITE_PLAYERS,
                                          key="e_del_p", label_visibility="collapsed")
                if del_player != "（不刪除）":
                    if st.button(f"🗑️ 刪除 {del_player} {date_str_e}",
                                 key="e_del_btn", use_container_width=True):
                        delete_elite_record(e_date, del_player)
                        st.success(f"已刪除 {del_player} {date_str_e} 的記錄")
                        st.rerun()

        # ── 本月出席總覽 ──────────────────────────────────────────
        st.write("")
        e_summary = get_elite_month_summary(yr_e, mo_e_num, elite_data)

        total_e_days = sum(len(v) for v in e_summary.values())
        total_e_amt  = total_e_days * ELITE_DAILY_BONUS

        ek1, ek2 = st.columns(2)
        ek1.metric(f"{yr_e}年{mo_e_num:02d}月 總出席人次", f"{total_e_days} 次")
        ek2.metric("本月發放合計", f"${total_e_amt:,}")

        st.write("")
        for player in ELITE_PLAYERS:
            days_list = sorted(e_summary.get(player, []))
            cnt       = len(days_list)
            amt       = cnt * ELITE_DAILY_BONUS
            day_tags  = " ".join(
                f"<span style='background:#D1FAE5;color:#065F46;padding:2px 7px;"
                f"border-radius:8px;font-size:12px;margin:2px;display:inline-block;'>"
                f"{d[5:]}</span>"
                for d in days_list
            ) or "<span style='color:#D1D5DB;font-size:13px;'>尚無記錄</span>"
            st.markdown(
                f"<div style='padding:10px 0;border-bottom:1px solid #F3F4F6;'>"
                f"<span style='font-weight:700;font-size:15px;margin-right:12px;'>{player}</span>"
                f"<span style='color:#6B7280;font-size:13px;margin-right:16px;'>"
                f"{cnt} 天 · ${amt:,}</span>"
                f"{day_tags}</div>",
                unsafe_allow_html=True,
            )

        # ── 報表下載 ─────────────────────────────────────────────
        st.divider()
        elite_html  = generate_elite_report_html(yr_e, mo_e_num, elite_data)
        fname_elite = f"菁英隊_出席獎金_{yr_e}{mo_e_num:02d}.html"
        st.download_button(
            label=f"📄 下載 {yr_e}年{mo_e_num:02d}月 菁英隊出席明細（交會計用）",
            data=elite_html.encode("utf-8"),
            file_name=fname_elite,
            mime="text/html",
            use_container_width=True,
            key="dl_elite",
        )


# ═════════════════════════════════════════════════════════════════
# 院長訓練總覽
# ═════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.markdown('<div class="sec-label">🎯 院長訓練總覽</div>', unsafe_allow_html=True)
    st.write("")

    pmo = st.session_state.principal_month_offset
    yr_p, mo_p = get_month_year(pmo)
    yr_prev_p, mo_prev_p = get_month_year(pmo - 1)

    pp_l, pp_mid, pp_r = st.columns([1, 3, 1])
    with pp_l:
        if st.button("← 上月", use_container_width=True, key="principal_prev"):
            st.session_state.principal_month_offset -= 1
            st.rerun()
    with pp_mid:
        st.markdown(
            f"<div style='text-align:center;font-size:15px;font-weight:700;"
            f"color:#374151;padding:6px 0;'>{yr_p} 年 {mo_p:02d} 月</div>",
            unsafe_allow_html=True,
        )
    with pp_r:
        if st.button("下月 →", use_container_width=True, key="principal_next",
                     disabled=(pmo >= 0)):
            st.session_state.principal_month_offset += 1
            st.rerun()

    # Build data for current and previous month
    paying = [p for p in players if p not in TRAINEE_PLAYERS]
    trainees = [p for p in players if p in TRAINEE_PLAYERS]
    all_pnames = paying + trainees

    summary_cur  = []
    summary_prev = []
    for p in all_pnames:
        sc = calc_monthly_bonus_one(p, yr_p, mo_p, all_data)
        sc["name"] = p
        summary_cur.append(sc)
        sp = calc_monthly_bonus_one(p, yr_prev_p, mo_prev_p, all_data)
        sp["name"] = p
        summary_prev.append(sp)

    st.markdown(
        render_principal_matrix_html(summary_cur, summary_prev, yr_p, mo_p),
        unsafe_allow_html=True,
    )
    st.caption("🟢 綠色 = 表現良好　🟡 黃色 = 尚可，可加強　🔴 紅色 = 需要關注　·　小箭頭 ▲▼ 為與上月比較")

    st.write("")
    principal_html = generate_principal_report_html(summary_cur, summary_prev, yr_p, mo_p)
    st.download_button(
        label=f"⬇️ 下載 {yr_p}年{mo_p:02d}月 訓練總覽（傳院長）",
        data=principal_html.encode("utf-8"),
        file_name=f"新銳隊_院長訓練總覽_{yr_p:04d}{mo_p:02d}.html",
        mime="text/html",
        use_container_width=True,
        key="dl_principal",
    )
    st.caption("下載後用瀏覽器開啟 → Ctrl+P（或 ⌘P）→ 另存為 PDF")


# ═════════════════════════════════════════════════════════════════
# 報告下載區
# ═════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.markdown('<div class="sec-label">📄 新銳隊 報告下載</div>', unsafe_allow_html=True)
    st.write("")

    # ── 月份導覽（獨立，不影響其他區塊）────────────────────────
    rmo = st.session_state.report_month_offset
    yr_r, mo_r = get_month_year(rmo)
    rl, rmid, rr = st.columns([1, 3, 1])
    with rl:
        if st.button("← 上月", use_container_width=True, key="rpt_prev"):
            st.session_state.report_month_offset -= 1
            st.rerun()
    with rmid:
        st.markdown(
            f"<div style='text-align:center;font-size:15px;font-weight:700;"
            f"color:#374151;padding:6px 0;'>{yr_r} 年 {mo_r:02d} 月</div>",
            unsafe_allow_html=True,
        )
    with rr:
        if st.button("下月 →", use_container_width=True, key="rpt_next",
                     disabled=(rmo >= 0)):
            st.session_state.report_month_offset += 1
            st.rerun()

    st.divider()

    # ── 單週報告（可切換週）─────────────────────────────────────
    st.markdown("**📊 單週訓練報告**")
    rwo = st.session_state.report_week_offset
    rw_dates = get_week_dates(rwo)
    rw_label = f"{rw_dates[0].strftime('%m/%d')} ～ {rw_dates[6].strftime('%m/%d')}"
    rw_l, rw_mid, rw_r = st.columns([1, 3, 1])
    with rw_l:
        if st.button("← 上週", use_container_width=True, key="rpt_week_prev"):
            st.session_state.report_week_offset -= 1
            st.rerun()
    with rw_mid:
        st.markdown(
            f"<div style='text-align:center;font-size:14px;font-weight:600;"
            f"color:#374151;padding:6px 0;'>{rw_label}</div>",
            unsafe_allow_html=True,
        )
    with rw_r:
        if st.button("下週 →", use_container_width=True, key="rpt_week_next",
                     disabled=(rwo >= 0)):
            st.session_state.report_week_offset += 1
            st.rerun()

    week_html  = generate_weekly_report_html(players, rw_dates, all_data)
    fname_week = f"新銳隊_週報告_{rw_dates[0].strftime('%Y%m%d')}.html"
    st.download_button(
        label=f"⬇️ 下載 {rw_label} 週報告",
        data=week_html.encode("utf-8"),
        file_name=fname_week,
        mime="text/html",
        use_container_width=True,
        key="dl_week",
    )
    st.caption("下載後用瀏覽器開啟 → Ctrl+P（或 ⌘P）→ 另存為 PDF")

    st.divider()

    # ── 月度報告（財務明細 + 週報彙整）─────────────────────────
    st.markdown(f"**📅 {yr_r}年{mo_r:02d}月 月度報告**")
    btn_month, btn_monthly_weekly = st.columns(2)

    with btn_month:
        month_html = generate_monthly_finance_html(players, yr_r, mo_r, all_data)
        fname_month = f"新銳隊_獎金明細_{yr_r}{mo_r:02d}.html"
        st.download_button(
            label="💰 財務明細（交會計）",
            data=month_html.encode("utf-8"),
            file_name=fname_month,
            mime="text/html",
            use_container_width=True,
            key="dl_month",
        )
        st.caption("橫式 A4，逐人逐項，含合計")

    with btn_monthly_weekly:
        mw_html  = generate_monthly_weekly_report_html(players, yr_r, mo_r, all_data)
        fname_mw = f"新銳隊_月度週報_{yr_r}{mo_r:02d}.html"
        st.download_button(
            label="📊 月度週報彙整",
            data=mw_html.encode("utf-8"),
            file_name=fname_mw,
            mime="text/html",
            use_container_width=True,
            key="dl_monthly_weekly",
        )
        st.caption("每週一張表，整個月一次看完")

    st.divider()

    # ── 個人月報 ─────────────────────────────────────────────────
    st.markdown("**🧑 個人訓練月報**")
    all_pnames_r = [p for p in players if p not in TRAINEE_PLAYERS] +                    [p for p in players if p in TRAINEE_PLAYERS]
    sel_player   = st.selectbox("選擇選手", all_pnames_r, key="player_report_sel",
                                label_visibility="collapsed")
    if sel_player:
        player_html  = generate_player_monthly_report_html(sel_player, yr_r, mo_r, all_data)
        fname_player = f"新銳隊_{sel_player}_{yr_r}{mo_r:02d}月報.html"
        st.download_button(
            label=f"⬇️ 下載 {sel_player} · {yr_r}年{mo_r:02d}月 個人月報",
            data=player_html.encode("utf-8"),
            file_name=fname_player,
            mime="text/html",
            use_container_width=True,
            key="dl_player_report",
        )
        st.caption("下載後用瀏覽器開啟 → Ctrl+P（或 ⌘P）→ 另存為 PDF，可直接寄給選手或家長")


# ── 手動刷新 ─────────────────────────────────────────────────────
st.write("")
if st.button("🔄 刷新資料"):
    load_bonus_data.clear()
    st.rerun()
