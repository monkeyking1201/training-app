"""
App 4B — 教練審核 + 院長熱圖戰情端
上半：今日待審核清單 + 一鍵核准
下半：下拉選手 → 大名字 + 本週任務熱圖矩陣 + 獎金加總
資料來源：Bonus_DB（讀取 + 修改審核狀態）
         Schedule_DB（讀取選手名單）
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, timedelta
import pandas as pd

# ── 常數 ────────────────────────────────────────────────────────
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
    "新銳循環賽": 1000,
}
# Bonus_DB 欄位索引（0-based）
ITEM_COL_IDX = {
    "出席率": 4, "死活題": 5, "次一手": 6,
    "輸棋討論": 7, "AI人機大戰": 8, "新銳循環賽": 9,
}
STATUS_COL    = 11   # L 欄，審核狀態
WEEKDAY_ZH    = ["一", "二", "三", "四", "五", "六", "日"]
WEEKLY_TARGET = 4500    # 100,000 ÷ 22週 ≈ 每週理想進度
PROJECT_TOTAL = 100_000 # 半年總預算

# ── Google Sheets 連線 ──────────────────────────────────────────
@st.cache_resource
def get_gc():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    return gspread.authorize(creds)

@st.cache_resource
def get_bonus_ws():
    gc = get_gc()
    return gc.open_by_key(BONUS_DB_ID).get_worksheet(0)

@st.cache_data(ttl=20)
def load_bonus_data() -> list:
    """讀取 Bonus_DB 全部資料，20 秒快取"""
    return get_bonus_ws().get_all_values()

@st.cache_data(ttl=600)
def load_player_list() -> list:
    gc = get_gc()
    sh = gc.open_by_key(SCHEDULE_DB_ID)
    ws = sh.worksheet("PIN")
    rows = ws.get_all_values()
    return [row[0].strip() for row in rows if len(row) >= 1 and row[0].strip()]

# ── 工具函數 ────────────────────────────────────────────────────
def get_week_dates() -> list[date]:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return [monday + timedelta(days=i) for i in range(7)]

def get_pending_today(all_data: list) -> list[tuple]:
    """回傳今日待審核的 [(1-based row index, 選手名), ...]"""
    today_str = date.today().strftime("%Y-%m-%d")
    return [
        (i + 2, row[1])
        for i, row in enumerate(all_data[1:])
        if len(row) > STATUS_COL and row[2] == today_str and row[STATUS_COL] == "待審核"
    ]

def approve_all_pending(all_data: list) -> int:
    """把今日所有 '待審核' 改為 '已核准'，回傳核准筆數"""
    today_str = date.today().strftime("%Y-%m-%d")
    cells = [
        gspread.Cell(i + 2, STATUS_COL + 1, "已核准")   # gspread 1-based
        for i, row in enumerate(all_data[1:])
        if len(row) > STATUS_COL and row[2] == today_str and row[STATUS_COL] == "待審核"
    ]
    if cells:
        get_bonus_ws().update_cells(cells)
        load_bonus_data.clear()
    return len(cells)

def build_heatmap(player: str, week_dates: list[date], all_data: list) -> pd.DataFrame:
    week_strs = {d.strftime("%Y-%m-%d") for d in week_dates}
    # lookup[date_str][item] = "已核准" | "待審核" | ""
    lookup: dict[str, dict] = {}
    for row in all_data[1:]:
        if len(row) > STATUS_COL and row[1] == player and row[2] in week_strs:
            ds = row[2]
            status = row[STATUS_COL]
            if ds not in lookup:
                lookup[ds] = {}
            for item, col in ITEM_COL_IDX.items():
                if col < len(row) and row[col] == "V":
                    lookup[ds][item] = status

    rows = []
    for d in week_dates:
        ds = d.strftime("%Y-%m-%d")
        label = f"{d.strftime('%m/%d')}（{WEEKDAY_ZH[d.weekday()]}）"
        row_data = {"日期": label}
        for item in ITEM_COL_IDX:
            s = lookup.get(ds, {}).get(item, "")
            if s == "已核准":
                row_data[item] = "✅"
            elif s == "待審核":
                row_data[item] = "🟡"
            else:
                row_data[item] = "・"
        rows.append(row_data)

    return pd.DataFrame(rows).set_index("日期")

def calc_bonus(player: str, week_dates: list[date], all_data: list) -> tuple[int, int, int]:
    """回傳 (本週已核准獎金, 本週預算達成率%, 專案累計總獎金)"""
    week_strs = {d.strftime("%Y-%m-%d") for d in week_dates}
    weekly_earned = 0
    total_earned  = 0
    for row in all_data[1:]:
        if len(row) > STATUS_COL and row[1] == player and row[STATUS_COL] == "已核准":
            row_bonus = sum(
                ITEM_PRICES[item]
                for item, col in ITEM_COL_IDX.items()
                if col < len(row) and row[col] == "V"
            )
            total_earned += row_bonus
            if row[2] in week_strs:
                weekly_earned += row_bonus
    achievement = round(weekly_earned / WEEKLY_TARGET * 100)
    return weekly_earned, achievement, total_earned

# ── 頁面設定 ────────────────────────────────────────────────────
st.set_page_config(
    page_title="戰情台 | 新銳隊",
    page_icon="📊",
    layout="wide",
)

st.markdown("""
<style>
    .big-name {
        font-size: 3.2rem;
        font-weight: 900;
        color: #1a3a6b;
        letter-spacing: 8px;
        text-align: center;
        padding: 16px 0 4px 0;
    }
    .section-header {
        font-size: 1.1rem;
        font-weight: 700;
        color: #555;
        margin-bottom: 8px;
    }
    .pending-badge {
        display: inline-block;
        background: #fff3cd;
        border: 1px solid #ffc107;
        border-radius: 20px;
        padding: 4px 14px;
        margin: 4px;
        font-size: 0.95rem;
        font-weight: 600;
    }
    .bonus-box {
        background: linear-gradient(135deg, #e8f5e9, #f0f4ff);
        border-radius: 14px;
        padding: 20px 32px;
        text-align: center;
        margin: 12px 0;
    }
    .bonus-num {
        font-size: 2.4rem;
        font-weight: 900;
        color: #d32f2f;
    }
    .rate-perfect  { font-size:1.6rem; font-weight:900; color:#2e7d32; }
    .rate-behind   { font-size:1.6rem; font-weight:900; color:#d32f2f; }
    .rate-overburn { font-size:1.6rem; font-weight:900; color:#f57f17; }
    .remain-num {
        font-size: 1.6rem;
        font-weight: 800;
        color: #1565c0;
    }
    .legend {
        font-size: 0.85rem;
        color: #888;
        text-align: center;
        margin-top: 6px;
    }
</style>
""", unsafe_allow_html=True)

# ── 資料載入 ────────────────────────────────────────────────────
all_data   = load_bonus_data()
week_dates = get_week_dates()
players    = load_player_list()

# ══════════════════════════════════════════════════════════════════
# 上半：教練審核台
# ══════════════════════════════════════════════════════════════════
st.markdown("## 🔍 今日審核台")

pending = get_pending_today(all_data)
today_label = date.today().strftime("%Y / %m / %d")

if not pending:
    st.success(f"✅ {today_label}　今日無待審核申報")
else:
    st.markdown(f"**{today_label}　待審核：{len(pending)} 筆**")
    badge_html = "".join(
        f'<span class="pending-badge">🟡 {name}</span>'
        for _, name in pending
    )
    st.markdown(badge_html, unsafe_allow_html=True)

    st.write("")
    if st.button("✅ 一鍵核准今日全部", type="primary", use_container_width=False):
        with st.spinner("核准中..."):
            count = approve_all_pending(all_data)
            all_data = load_bonus_data()   # 重新讀取
        st.success(f"已核准 {count} 筆！綠格會立即更新。")
        st.rerun()

st.divider()

# ══════════════════════════════════════════════════════════════════
# 下半：院長熱圖矩陣
# ══════════════════════════════════════════════════════════════════
st.markdown("## 📊 本週任務熱圖")

if not players:
    st.warning("無法讀取選手名單")
    st.stop()

selected = st.selectbox("選擇選手", players, label_visibility="collapsed")

# 大名字
st.markdown(f'<div class="big-name">{selected}</div>', unsafe_allow_html=True)

week_start = week_dates[0].strftime("%m/%d")
week_end   = week_dates[6].strftime("%m/%d")
st.markdown(
    f"<div style='text-align:center;color:#888;margin-bottom:12px;'>"
    f"本週　{week_start} － {week_end}</div>",
    unsafe_allow_html=True,
)

# 熱圖表格
df = build_heatmap(selected, week_dates, all_data)

st.dataframe(
    df,
    use_container_width=True,
    height=320,
    column_config={
        item: st.column_config.TextColumn(
            f"{item}\n${price}",
            width="small",
        )
        for item, price in ITEM_PRICES.items()
    },
)

st.markdown(
    '<div class="legend">✅ 已核准　🟡 待審核　・ 未申報</div>',
    unsafe_allow_html=True,
)

# KPI 加總
weekly_earned, achievement, total_earned = calc_bonus(selected, week_dates, all_data)
remaining = PROJECT_TOTAL - total_earned

# 達成率動態顏色與文字
if 90 <= achievement <= 110:
    rate_class, rate_note = "rate-perfect",  "進度完美 ✅"
elif achievement < 90:
    rate_class, rate_note = "rate-behind",   "進度落後 ⚠️"
else:
    rate_class, rate_note = "rate-overburn", "超前燃燒 🔥"

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(f"""
    <div class="bonus-box">
        本週已累計獎金<br>
        <span class="bonus-num">${weekly_earned:,}</span> 元
    </div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown(f"""
    <div class="bonus-box">
        【本週預算達成率】<br>
        <span class="{rate_class}">{achievement}%</span><br>
        <small>{rate_note}</small>
    </div>
    """, unsafe_allow_html=True)
with col3:
    st.markdown(f"""
    <div class="bonus-box">
        【10萬專案剩餘額度】<br>
        <span class="remain-num">${remaining:,}</span> 元
    </div>
    """, unsafe_allow_html=True)

# 手動刷新按鈕
st.write("")
if st.button("🔄 刷新資料", use_container_width=False):
    load_bonus_data.clear()
    st.rerun()
