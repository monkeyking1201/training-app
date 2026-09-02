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

    # ── 本月紀錄 ─────────────────────────────────────────────────
    mo_c  = st.session_state.month_offset
    yr_c, mo_c_num = get_month_year(mo_c)
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
            e_date = st.date_input("出席日期", value=date.today(), key="e_date")
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
# 報告下載區
# ═════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.markdown('<div class="sec-label">📄 報告下載</div>', unsafe_allow_html=True)
    st.write("")
    btn_week, btn_month = st.columns(2)

    with btn_week:
        week_html = generate_weekly_report_html(players, week_dates, all_data)
        fname_week = f"新銳隊_週報告_{week_dates[0].strftime('%Y%m%d')}.html"
        st.download_button(
            label="📊 生成本週訓練報告",
            data=week_html.encode("utf-8"),
            file_name=fname_week,
            mime="text/html",
            use_container_width=True,
        )
        st.caption("下載後用瀏覽器開啟 → Ctrl+P（或 ⌘P）→ 另存為 PDF")

    with btn_month:
        mo_now = st.session_state.month_offset
        yr_now, mo_num = get_month_year(mo_now)
        month_html = generate_monthly_finance_html(players, yr_now, mo_num, all_data)
        fname_month = f"新銳隊_獎金明細_{yr_now}{mo_num:02d}.html"
        st.download_button(
            label=f"💰 生成 {yr_now}年{mo_num:02d}月 財務明細",
            data=month_html.encode("utf-8"),
            file_name=fname_month,
            mime="text/html",
            use_container_width=True,
        )
        st.caption("橫式 A4，含明細 · 項目 · 金額，可交財務")


# ── 手動刷新 ─────────────────────────────────────────────────────
st.write("")
if st.button("🔄 刷新資料"):
    load_bonus_data.clear()
    st.rerun()
