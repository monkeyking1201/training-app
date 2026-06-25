"""
App 4B — 教練審核 + 院長熱圖戰情端  (UI v2 — McKinsey Dark)
上半：今日待審核清單 + 一鍵核准
下半：Metrics → 熱圖矩陣 → 達成率進度條
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
    "新銳循環賽": 1000,
}
ITEM_COL_IDX = {
    "出席率": 4, "死活題": 5, "次一手": 6,
    "輸棋討論": 7, "AI人機大戰": 8, "新銳循環賽": 9,
}
ALT_COL       = 10
STATUS_COL    = 11
WEEKDAY_ZH    = ["一", "二", "三", "四", "五", "六", "日"]
WEEKLY_TARGET = 4500
PROJECT_TOTAL = 100_000


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
    sh  = get_gc().open_by_key(SCHEDULE_DB_ID)
    ws  = sh.worksheet("PIN")
    rows = ws.get_all_values()
    return [r[0].strip() for r in rows if len(r) >= 1 and r[0].strip()]


# ── 工具函數 ──────────────────────────────────────────────────────
def get_week_dates() -> list[date]:
    today  = date.today()
    monday = today - timedelta(days=today.weekday())
    return [monday + timedelta(days=i) for i in range(7)]

def get_pending_today(all_data: list) -> list[tuple]:
    today_str = date.today().strftime("%Y-%m-%d")
    return [
        (i + 2, row[1])
        for i, row in enumerate(all_data[1:])
        if len(row) > STATUS_COL and row[2] == today_str and row_status(row) == "待審核"
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

def build_heatmap(player: str, week_dates: list[date], all_data: list) -> pd.DataFrame:
    week_strs   = {d.strftime("%Y-%m-%d") for d in week_dates}
    lookup      : dict[str, dict]  = {}
    lookup_alt  : dict[str, tuple] = {}

    for row in all_data[1:]:
        if len(row) > STATUS_COL and row[1] == player and row[2] in week_strs:
            ds, status = row[2], row_status(row)
            lookup.setdefault(ds, {})
            for item, col in ITEM_COL_IDX.items():
                if col < len(row) and row[col] == "V":
                    lookup[ds][item] = status
            if len(row) > ALT_COL and row[ALT_COL].strip():
                lookup_alt[ds] = (row[ALT_COL].strip(), status)

    rows = []
    for d in week_dates:
        ds    = d.strftime("%Y-%m-%d")
        label = f"{d.strftime('%m/%d')}（{WEEKDAY_ZH[d.weekday()]}）"
        rd    = {"日期": label}
        for item in ITEM_COL_IDX:
            s = lookup.get(ds, {}).get(item, "")
            rd[item] = "✅" if s == "已核准" else ("🟡" if s == "待審核" else "・")
        alt = lookup_alt.get(ds)
        if alt:
            alt_name, alt_status = alt
            rd["🔥替代"] = f"✅ {alt_name}" if alt_status == "已核准" else f"🟡 {alt_name}"
        else:
            rd["🔥替代"] = "・"
        rows.append(rd)

    return pd.DataFrame(rows).set_index("日期")

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
                if alt in ITEM_PRICES:
                    rb += ITEM_PRICES[alt]
            total_earned += rb
            if row[2] in week_strs:
                weekly_earned += rb
    achievement = round(weekly_earned / WEEKLY_TARGET * 100)
    return weekly_earned, achievement, total_earned


# ── Pandas Styler：色塊化熱圖 ─────────────────────────────────────
def _cell_style(val: str) -> str:
    v = str(val)
    if v.startswith("✅"):
        return (
            "background-color: #dcfce7;"
            "color: #166534;"
            "font-weight: 700;"
            "text-align: center;"
        )
    if v.startswith("🟡"):
        return (
            "background-color: #fef9c3;"
            "color: #854d0e;"
            "font-weight: 700;"
            "text-align: center;"
        )
    # 未申報
    return (
        "background-color: #f1f5f9;"
        "color: #94a3b8;"
        "text-align: center;"
    )

def style_heatmap(df: pd.DataFrame):
    try:
        styler = df.style.map(_cell_style)          # pandas ≥ 2.1
    except AttributeError:
        styler = df.style.applymap(_cell_style)     # pandas < 2.1 fallback

    styler.set_properties(**{
        "padding":     "10px 18px",
        "font-size":   "1.05rem",
        "line-height": "1.9",
        "border":      "none",
    })
    styler.set_table_styles([
        {"selector": "thead th", "props": [
            ("background-color", "#1e293b"),
            ("color",            "#94a3b8"),
            ("font-size",        "0.75rem"),
            ("font-weight",      "700"),
            ("letter-spacing",   "0.07em"),
            ("text-transform",   "uppercase"),
            ("padding",          "10px 18px"),
            ("border",           "none"),
        ]},
        {"selector": "td, th", "props": [
            ("border-bottom", "1px solid #e2e8f0"),
        ]},
        {"selector": "table", "props": [
            ("border-collapse", "collapse"),
            ("width",           "100%"),
        ]},
        {"selector": "tbody tr:nth-child(even) td", "props": [
            ("filter", "brightness(0.97)"),
        ]},
    ])
    return styler


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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

/* ── Global ── */
*, *::before, *::after { box-sizing: border-box; }

html, body, .stApp {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    background-color: #0a0f1e !important;
}

.block-container {
    padding-top: 1.8rem  !important;
    padding-bottom: 3rem !important;
    max-width: 1440px    !important;
}

/* Hide Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }

/* ── Card shell (wraps st.container border=True) ── */
[data-testid="stVerticalBlockBorderWrapper"] > div {
    background:    #ffffff !important;
    border-radius: 16px    !important;
    border:        1px solid #e2e8f0 !important;
    box-shadow:    0 1px 4px rgba(0,0,0,0.06),
                   0 6px 20px rgba(0,0,0,0.05) !important;
    padding:       8px 4px !important;
}

/* Dark card variant — audit section */
.audit-card [data-testid="stVerticalBlockBorderWrapper"] > div {
    background: #1e293b !important;
    border:     1px solid #334155 !important;
}

/* ── Metric card (pure HTML) ── */
.kpi-row { display: flex; gap: 16px; margin-bottom: 24px; }

.kpi-card {
    flex: 1;
    background:    #ffffff;
    border:        1px solid #e2e8f0;
    border-radius: 16px;
    padding:       22px 28px 18px;
    box-shadow:    0 1px 3px rgba(0,0,0,0.06), 0 4px 12px rgba(0,0,0,0.04);
}

.kpi-value {
    font-family:   'Inter', sans-serif;
    font-size:     2.15rem;
    font-weight:   800;
    color:         #0f172a;
    line-height:   1.1;
    letter-spacing:-0.02em;
}
.kpi-value-warn   { color: #fb7185 !important; }
.kpi-value-amber  { color: #f59e0b !important; }
.kpi-value-ok     { color: #16a34a !important; }

.kpi-label {
    font-family:   'Inter', sans-serif;
    font-size:     0.72rem;
    font-weight:   600;
    color:         #64748b;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    margin-top:    7px;
}

.kpi-note {
    font-size:   0.8rem;
    color:       #64748b;
    margin-top:  4px;
}

/* ── Progress bar ── */
.prog-wrap {
    background:    #e2e8f0;
    border-radius: 999px;
    height:        7px;
    margin-top:    10px;
    overflow:      hidden;
}
.prog-bar {
    height:        7px;
    border-radius: 999px;
}

/* ── Section label ── */
.sec-label {
    font-family:   'Inter', sans-serif;
    font-size:     0.72rem;
    font-weight:   700;
    color:         #64748b;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    padding-bottom: 10px;
    border-bottom:  1px solid #e2e8f0;
    margin-bottom:  16px;
}

.sec-label-dark {
    font-family:   'Inter', sans-serif;
    font-size:     0.72rem;
    font-weight:   700;
    color:         #64748b;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    padding-bottom: 10px;
    border-bottom:  1px solid #334155;
    margin-bottom:  16px;
}

/* ── Big player name ── */
.big-name {
    font-size:     3rem;
    font-weight:   900;
    color:         #0f172a;
    letter-spacing: 8px;
    text-align:    center;
    padding:       12px 0 2px;
}

.week-label {
    text-align:  center;
    color:       #64748b;
    font-size:   0.88rem;
    margin-bottom: 20px;
}

/* ── Pending badge ── */
.pending-badge {
    display:       inline-block;
    background:    #1e293b;
    border:        1px solid #f59e0b;
    border-radius: 20px;
    padding:       5px 16px;
    margin:        4px;
    font-size:     0.88rem;
    font-weight:   600;
    color:         #fbbf24;
}

/* ── Page title area ── */
.page-eyebrow {
    font-family:   'Inter', sans-serif;
    font-size:     0.72rem;
    font-weight:   700;
    color:         #334155;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    margin-bottom:  4px;
}
.page-heading {
    font-family:   'Inter', sans-serif;
    font-size:     1.9rem;
    font-weight:   900;
    color:         #f1f5f9;
    margin-bottom: 28px;
    letter-spacing: -0.01em;
}

/* ── Legend ── */
.legend {
    font-size:  0.8rem;
    color:      #94a3b8;
    text-align: center;
    margin-top: 8px;
}

/* ── Dataframe container ── */
[data-testid="stDataFrame"] {
    border-radius: 12px;
    overflow:      hidden;
    border:        1px solid #e2e8f0 !important;
}

/* Selectbox dark */
.stSelectbox label { color: #94a3b8 !important; font-size: 0.8rem !important; }

/* Button */
.stButton > button {
    border-radius: 10px    !important;
    font-family:   'Inter', sans-serif !important;
    font-weight:   600 !important;
    letter-spacing: 0.02em !important;
}

/* Divider */
hr { border-color: #1e293b !important; margin: 20px 0 !important; }
</style>
""", unsafe_allow_html=True)


# ── 資料載入 ──────────────────────────────────────────────────────
all_data   = load_bonus_data()
week_dates = get_week_dates()
players    = load_player_list()

# ── 頁面標題 ──────────────────────────────────────────────────────
st.markdown('<div class="page-eyebrow">新銳圍棋學院</div>', unsafe_allow_html=True)
st.markdown('<div class="page-heading">📊 訓練獎金戰情台</div>', unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════
# 上半：教練審核台
# ═════════════════════════════════════════════════════════════════
with st.container(border=True):
    st.markdown('<div class="sec-label">🔍 今日審核台</div>', unsafe_allow_html=True)

    pending     = get_pending_today(all_data)
    today_label = date.today().strftime("%Y / %m / %d")

    if not pending:
        st.success(f"✅ {today_label}　今日無待審核申報")
    else:
        st.markdown(
            f"<span style='font-weight:600;font-size:1rem;color:#0f172a;'>"
            f"{today_label}　待審核：{len(pending)} 筆</span>",
            unsafe_allow_html=True,
        )
        st.write("")
        badge_html = "".join(
            f'<span class="pending-badge">🟡 {name}</span>'
            for _, name in pending
        )
        st.markdown(badge_html, unsafe_allow_html=True)
        st.write("")
        if st.button("✅ 一鍵核准今日全部", type="primary"):
            with st.spinner("核准中..."):
                count    = approve_all_pending(all_data)
                all_data = load_bonus_data()
            st.success(f"已核准 {count} 筆！綠格立即更新。")
            st.rerun()


# ═════════════════════════════════════════════════════════════════
# 下半：院長熱圖矩陣
# ═════════════════════════════════════════════════════════════════
if not players:
    st.warning("無法讀取選手名單")
    st.stop()

with st.container(border=True):
    st.markdown('<div class="sec-label">📊 本週任務熱圖矩陣</div>', unsafe_allow_html=True)

    # 選手下拉
    selected = st.selectbox("選擇選手", players, label_visibility="collapsed")

    # 大名字
    st.markdown(f'<div class="big-name">{selected}</div>', unsafe_allow_html=True)
    week_start = week_dates[0].strftime("%m/%d")
    week_end   = week_dates[6].strftime("%m/%d")
    st.markdown(
        f'<div class="week-label">本週　{week_start} － {week_end}</div>',
        unsafe_allow_html=True,
    )

    # ── 計算 KPI ────────────────────────────────────────────────
    weekly_earned, achievement, total_earned = calc_bonus(selected, week_dates, all_data)
    remaining = PROJECT_TOTAL - total_earned

    # 達成率樣式
    if achievement < 70:
        val_cls, rate_note, bar_color = "kpi-value kpi-value-warn",  "進度落後 ⚠️",  "#fb7185"
    elif achievement < 90:
        val_cls, rate_note, bar_color = "kpi-value kpi-value-amber", "需加速 ⚡",     "#f59e0b"
    elif achievement <= 110:
        val_cls, rate_note, bar_color = "kpi-value kpi-value-ok",    "進度完美 ✅",   "#22c55e"
    else:
        val_cls, rate_note, bar_color = "kpi-value kpi-value-amber", "超前燃燒 🔥",  "#f59e0b"

    bar_width = min(achievement, 100)

    # ── 三格 KPI 卡片（在熱圖上方）──────────────────────────────
    st.markdown(f"""
    <div class="kpi-row">
      <div class="kpi-card">
        <div class="kpi-value">${weekly_earned:,}</div>
        <div class="kpi-label">本週已累計獎金（元）</div>
      </div>
      <div class="kpi-card">
        <div class="{val_cls}">{achievement}%</div>
        <div class="kpi-label">本週預算達成率</div>
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

    # ── 熱圖 ─────────────────────────────────────────────────────
    df     = build_heatmap(selected, week_dates, all_data)
    styled = style_heatmap(df)

    st.dataframe(
        styled,
        use_container_width=True,
        height=320,
        column_config={
            **{
                item: st.column_config.TextColumn(f"{item} ${price}", width="small")
                for item, price in ITEM_PRICES.items()
            },
            "🔥替代": st.column_config.TextColumn("🔥替代任務", width="medium"),
        },
    )

    st.markdown(
        '<div class="legend">✅ 已核准　🟡 待審核　・ 未申報</div>',
        unsafe_allow_html=True,
    )


# ── 手動刷新 ─────────────────────────────────────────────────────
st.write("")
if st.button("🔄 刷新資料"):
    load_bonus_data.clear()
    st.rerun()
