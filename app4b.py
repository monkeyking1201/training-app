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
    sh   = get_gc().open_by_key(SCHEDULE_DB_ID)
    ws   = sh.worksheet("PIN")
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
    week_strs  = {d.strftime("%Y-%m-%d") for d in week_dates}
    lookup     : dict[str, dict]  = {}
    lookup_alt : dict[str, tuple] = {}

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


# ── HTML 熱圖渲染（取代 st.dataframe，獲得完整 CSS 控制權）────────
def render_heatmap_html(df: pd.DataFrame) -> str:
    cols = list(df.columns)

    # 表頭標籤：加上價格小字
    col_headers = {}
    for item, price in ITEM_PRICES.items():
        col_headers[item] = (
            f'<span style="display:block;font-size:13px;font-weight:700;'
            f'color:#374151;letter-spacing:0.04em;">{item}</span>'
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
                html += (
                    f'<td style="background:{row_bg};padding:12px 16px;'
                    f'text-align:center;vertical-align:middle;'
                    f'border-left:1px solid #F3F4F6;">'
                    f'<span style="font-size:20px;color:#D1D5DB;">·</span></td>'
                )
        html += "</tr>"

    html += "</tbody></table></div>"
    return html


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
    max-width:      1480px  !important;
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
    font-size:      42px;
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
all_data   = load_bonus_data()
week_dates = get_week_dates()
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
        badge_html = "".join(
            f'<span class="pending-badge">⏳ {name}</span>'
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

    # 大名字（純黑 60px，無陰影）
    st.markdown(f'<div class="big-name">{selected}</div>', unsafe_allow_html=True)
    week_start = week_dates[0].strftime("%m/%d")
    week_end   = week_dates[6].strftime("%m/%d")
    st.markdown(
        f'<div class="week-label">本週　{week_start} － {week_end}</div>',
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
        '<span style="color:#D1D5DB;margin-right:4px;">·</span> 未申報'
        '</div>',
        unsafe_allow_html=True,
    )


# ── 手動刷新 ─────────────────────────────────────────────────────
st.write("")
if st.button("🔄 刷新資料"):
    load_bonus_data.clear()
    st.rerun()
