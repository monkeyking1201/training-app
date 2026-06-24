"""
App 4A — 訓練獎金申報端（選手專用）
流程：輸入 PIN → 顯示姓名 → 勾選今日完成項目 → 送出（每日一次）
資料來源：Schedule_DB（獨立檔案）→ PIN 工作表
資料寫入：Bonus_DB（獨立檔案）→ 工作表1（自動建立 header）
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date
import json

# ── 常數設定 ────────────────────────────────────────────────────
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ⚠️ 兩個不同的 Google Sheets 檔案 ID（網址列 /d/ 後面那段）
SCHEDULE_DB_ID = "1ewrFUQc1P3YfB3-h9kzuoOLvXcRiee4eLv_R6SBj5oI"   # Schedule_DB（讀 PIN 碼）
BONUS_DB_ID    = "1KKKgeOCEBmcBxsy0d7KP6ZJqWXyhAtWqNn2FB_okPG8"       # Bonus_DB（寫申報資料）

BONUS_ITEMS = [
    ("出席率",      200),
    ("死活題",      300),
    ("次一手",      400),
    ("輸棋討論",    400),
    ("AI人機大戰",  400),
    ("新銳循環賽", 1000),
]

WEEKDAY_MAP = ["一", "二", "三", "四", "五", "六", "日"]

HEADER_ROW = [
    "時間戳", "姓名", "日期", "星期",
    "出席率(200)", "死活題(300)", "次一手(400)",
    "輸棋討論(400)", "AI人機大戰(400)", "新銳循環賽(1000)",
    "審核狀態"
]

# ── Google Sheets 連線 ──────────────────────────────────────────
@st.cache_resource
def get_gc():
    creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

@st.cache_data(ttl=300)
def load_pin_table() -> dict:
    """從 Schedule_DB 的 PIN 工作表，回傳 {PIN字串: 姓名}"""
    gc = get_gc()
    sh = gc.open_by_key(SCHEDULE_DB_ID)
    ws = sh.worksheet("PIN")
    rows = ws.get_all_values()
    return {str(row[1]).strip(): row[0].strip()
            for row in rows if len(row) >= 2 and row[1].strip()}

def get_or_create_bonus_ws():
    """開啟 Bonus_DB，若工作表1不存在則自動建立並寫入 header"""
    gc = get_gc()
    sh = gc.open_by_key(BONUS_DB_ID)
    try:
        ws = sh.get_worksheet(0)   # 取第一個工作表
        # 若是全新空白表，補上 header
        if ws.row_count == 0 or ws.cell(1, 1).value != "時間戳":
            ws.insert_row(HEADER_ROW, index=1)
    except Exception:
        ws = sh.add_worksheet("申報記錄", rows=2000, cols=12)
        ws.append_row(HEADER_ROW)
    return ws

def already_submitted_today(name: str) -> bool:
    ws = get_or_create_bonus_ws()
    today_str = date.today().strftime("%Y-%m-%d")
    all_rows = ws.get_all_values()
    for row in all_rows[1:]:   # 跳過 header
        if len(row) >= 3 and row[1] == name and row[2] == today_str:
            return True
    return False

def submit_bonus(name: str, checks: dict):
    ws = get_or_create_bonus_ws()
    now = datetime.now()
    weekday = WEEKDAY_MAP[now.weekday()]
    row = [
        now.strftime("%Y-%m-%d %H:%M:%S"),
        name,
        now.strftime("%Y-%m-%d"),
        f"星期{weekday}",
        "V" if checks.get("出席率")     else "",
        "V" if checks.get("死活題")     else "",
        "V" if checks.get("次一手")     else "",
        "V" if checks.get("輸棋討論")   else "",
        "V" if checks.get("AI人機大戰") else "",
        "V" if checks.get("新銳循環賽") else "",
        "待審核",
    ]
    ws.append_row(row)

# ── 頁面設定 ────────────────────────────────────────────────────
st.set_page_config(
    page_title="獎金申報 | 新銳隊",
    page_icon="🏆",
    layout="centered",
)

st.markdown("""
<style>
    .big-name {
        text-align: center;
        font-size: 3rem;
        font-weight: 900;
        color: #1a3a6b;
        letter-spacing: 6px;
        padding: 24px 0 4px 0;
    }
    .sub-date {
        text-align: center;
        font-size: 1rem;
        color: #888;
        margin-bottom: 12px;
    }
    .price-tag {
        color: #2e7d32;
        font-weight: 700;
        font-size: 1.1rem;
    }
    .total-box {
        background: #f0f4ff;
        border-radius: 12px;
        padding: 16px 24px;
        text-align: center;
        margin: 16px 0;
    }
    .total-amount {
        font-size: 2rem;
        font-weight: 900;
        color: #d32f2f;
    }
</style>
""", unsafe_allow_html=True)

# ── Session state 初始化 ────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.player_name = ""
if "submitted" not in st.session_state:
    st.session_state.submitted = False

# ══════════════════════════════════════════════════════════════════
# 畫面 A：登入
# ══════════════════════════════════════════════════════════════════
if not st.session_state.authenticated:
    st.markdown("## 🏆 訓練獎金申報")
    st.markdown("每日訓練結束後，輸入你的專屬 PIN 碼來申報今日獎金。")
    st.divider()

    pin_input = st.text_input(
        "PIN 碼",
        type="password",
        max_chars=6,
        placeholder="輸入 4 位數字",
    )

    if st.button("登入", type="primary", use_container_width=True):
        if pin_input.strip():
            pin_table = load_pin_table()
            if pin_input.strip() in pin_table:
                st.session_state.authenticated = True
                st.session_state.player_name = pin_table[pin_input.strip()]
                st.rerun()
            else:
                st.error("❌ PIN 碼錯誤，請重試")
        else:
            st.warning("請輸入 PIN 碼")

# ══════════════════════════════════════════════════════════════════
# 畫面 B：申報表單
# ══════════════════════════════════════════════════════════════════
else:
    name = st.session_state.player_name
    today = date.today()
    weekday = WEEKDAY_MAP[today.weekday()]

    # 大名字標題
    st.markdown(f'<div class="big-name">{name}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="sub-date">{today.strftime("%Y / %m / %d")}　星期{weekday}</div>',
        unsafe_allow_html=True,
    )
    st.divider()

    # 已送出判斷
    if already_submitted_today(name) or st.session_state.submitted:
        st.success("✅ 今日申報完成，等待教練審核！")
        st.info("明天訓練結束後再回來申報。")
        if st.button("登出", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.player_name = ""
            st.session_state.submitted = False
            st.rerun()
        st.stop()

    # 勾選項目
    st.markdown("### 今日完成的項目")
    st.caption("勾選你今天完成的訓練，完成後按送出。")

    checks = {}
    total = 0
    for item, price in BONUS_ITEMS:
        col1, col2 = st.columns([5, 1])
        with col1:
            checked = st.checkbox(f"**{item}**", key=item)
        with col2:
            st.markdown(f'<span class="price-tag">${price}</span>', unsafe_allow_html=True)
        checks[item] = checked
        if checked:
            total += price

    # 即時金額顯示
    st.markdown(f"""
    <div class="total-box">
        本次申報金額<br>
        <span class="total-amount">${total:,}</span> 元
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📤 送出申請", type="primary", use_container_width=True):
            if not any(checks.values()):
                st.warning("請至少勾選一個項目再送出")
            else:
                with st.spinner("送出中..."):
                    submit_bonus(name, checks)
                st.session_state.submitted = True
                st.balloons()
                st.rerun()
    with col2:
        if st.button("登出", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.player_name = ""
            st.rerun()
