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

# ── 常數設定 ────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SCHEDULE_DB_ID = "1ewrFUQc1P3YfB3-h9kzuoOLvXcRiee4eLv_R6SBj5oI"
BONUS_DB_ID    = "1KKKgeOCEBmcBxsy0d7KP6ZJqWXyhAtWqNn2FB_okPG8"

WEEKDAY_MAP = ["一", "二", "三", "四", "五", "六", "日"]

# 顯示標籤 → Google Sheets 欄位對應
DISPLAY_MAP = {
    "出席率":    "📍 今日出席",
    "死活題":    "🧩 專項死活題",
    "次一手":    "🎯 關鍵次一手",
    "輸棋討論":  "🗣️ 輸棋討論",
    "AI人機大戰":"🤖 AI人機大戰",
    "新銳循環賽":"⚔️ 新銳循環賽",
}

# 替代任務下拉選項：顯示文字 → 寫入 DB 的欄位名稱
ALT_TASK_OPTIONS = {
    "（本日無替代任務）": "",
    "🏃 運動":            "運動",
    "🤝 交流":            "交流",
    "📚 讀書會":          "讀書會",
}

HEADER_ROW = [
    "時間戳", "姓名", "日期", "星期",
    "出席率(200)", "死活題(300)", "次一手(400)",
    "輸棋討論(400)", "AI人機大戰(400)", "新銳循環賽(600)",
    "替代任務", "審核狀態"
]

# ── Google Sheets 連線 ──────────────────────────────────────────
@st.cache_resource
def get_gc():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    return gspread.authorize(creds)

@st.cache_resource
def get_bonus_ws():
    """Bonus_DB 工作表，session 級別快取，只連線一次"""
    gc = get_gc()
    sh = gc.open_by_key(BONUS_DB_ID)
    return sh.get_worksheet(0)

@st.cache_data(ttl=300)
def load_pin_table() -> dict:
    gc = get_gc()
    sh = gc.open_by_key(SCHEDULE_DB_ID)
    ws = sh.worksheet("PIN")
    rows = ws.get_all_values()
    return {str(row[1]).strip(): row[0].strip()
            for row in rows if len(row) >= 2 and row[1].strip()}

def count_submitted_today(name: str) -> tuple:
    """回傳 (今日已送出筆數, 最近一筆明細dict or None)"""
    ws = get_bonus_ws()
    today_str = date.today().strftime("%Y-%m-%d")
    all_rows = ws.get_all_values()
    count = 0
    last_detail = None
    for row in all_rows[1:]:
        if len(row) >= 3 and row[1] == name and row[2] == today_str:
            count += 1
            status = ""
            for v in row[11:]:
                if v.strip() in ("待審核", "已核准"):
                    status = v.strip()
                    break
            last_detail = {
                "出席率":     len(row) > 4  and row[4]  == "V",
                "死活題":     len(row) > 5  and row[5]  == "V",
                "次一手":     len(row) > 6  and row[6]  == "V",
                "輸棋討論":   len(row) > 7  and row[7]  == "V",
                "AI人機大戰": len(row) > 8  and row[8]  == "V",
                "新銳循環賽": len(row) > 9  and row[9]  == "V",
                "替代任務":   row[10].strip() if len(row) > 10 else "",
                "審核狀態":   status,
            }
    return count, last_detail

def submit_bonus(name: str, checks: dict, alt_task: str):
    """
    checks: 六個主項目的勾選狀態
    alt_task: 替代任務對應的原任務名稱，例如 "次一手"，無則空字串
    """
    ws = get_bonus_ws()
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
        alt_task,   # 替代任務：記錄等值的原任務名稱（或空白）
        "待審核",
    ]
    ws.append_row(row)

# ── 頁面設定 ────────────────────────────────────────────────────
st.set_page_config(
    page_title="訓練申報 | 新銳隊",
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
    .section-title {
        font-size: 1rem;
        font-weight: 700;
        color: #444;
        margin: 8px 0 4px 0;
    }
</style>
""", unsafe_allow_html=True)

# ── Session state ────────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.player_name = ""
if "done_checked" not in st.session_state:
    st.session_state.done_checked = False
if "submit_count" not in st.session_state:
    st.session_state.submit_count = 0       # 從 Sheets 讀到的今日送出筆數
if "session_submits" not in st.session_state:
    st.session_state.session_submits = 0    # 本次登入後新增的筆數
if "adding_more" not in st.session_state:
    st.session_state.adding_more = False    # 是否正在新增第二筆
if "today_detail" not in st.session_state:
    st.session_state.today_detail = None

# ══════════════════════════════════════════════════════════════════
# 畫面 A：登入
# ══════════════════════════════════════════════════════════════════
if not st.session_state.authenticated:
    st.markdown("## 🏆 訓練申報")
    st.markdown("每日訓練結束後，輸入你的專屬 PIN 碼來申報今日完成項目。")
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

    # 已送出判斷（只在登入後執行一次，避免重複打 API）
    if not st.session_state.done_checked:
        count, detail = count_submitted_today(name)
        st.session_state.submit_count = count
        st.session_state.today_detail = detail
        st.session_state.done_checked = True

    total_today = st.session_state.submit_count + st.session_state.session_submits

    if total_today > 0 and not st.session_state.adding_more:
        detail = st.session_state.today_detail

        # ── 審核狀態 banner ──────────────────────────────────────
        if total_today > 1:
            st.info(f"📋 今日已申報 {total_today} 筆（最近一筆如下）")
        elif detail and detail["審核狀態"] == "已核准":
            st.success("🎉 今日申報已核准！獎金入袋！")
        else:
            st.success("✅ 今日申報完成，等待教練審核！")

        # ── 申報明細卡片 ─────────────────────────────────────────
        if detail:
            ITEM_LABELS = [
                ("出席率",     "📍 今日出席"),
                ("死活題",     "🧩 專項死活題"),
                ("次一手",     "🎯 關鍵次一手"),
                ("輸棋討論",   "🗣️ 輸棋討論"),
                ("AI人機大戰", "🤖 AI人機大戰"),
                ("新銳循環賽", "⚔️ 新銳循環賽"),
            ]
            done_items = [label for key, label in ITEM_LABELS if detail.get(key)]
            alt = detail.get("替代任務", "")
            status = detail.get("審核狀態", "待審核")

            status_badge = (
                "<span style='background:#D1FAE5;color:#065F46;padding:3px 12px;"
                "border-radius:12px;font-weight:700;font-size:0.9rem;'>✅ 已核准</span>"
                if status == "已核准" else
                "<span style='background:#FEF3C7;color:#92400E;padding:3px 12px;"
                "border-radius:12px;font-weight:700;font-size:0.9rem;'>⏳ 待審核</span>"
            )

            items_html = "".join(
                f"<div style='padding:6px 0;font-size:1rem;'>✓ &nbsp;{lbl}</div>"
                for lbl in done_items
            )
            if alt:
                items_html += (
                    f"<div style='padding:6px 0;font-size:1rem;color:#b45309;'>"
                    f"🔥 替代任務：{alt}</div>"
                )
            if not done_items and not alt:
                items_html = "<div style='color:#aaa;'>（無申報項目）</div>"

            st.markdown(f"""
            <div style='background:#fff;border:1px solid #E5E7EB;border-radius:14px;
                        padding:20px 24px;margin:12px 0;
                        box-shadow:0 2px 8px rgba(0,0,0,0.05);'>
                <div style='font-size:0.8rem;color:#9CA3AF;font-weight:600;
                            letter-spacing:0.08em;text-transform:uppercase;
                            margin-bottom:10px;'>今日申報明細</div>
                {items_html}
                <div style='margin-top:14px;border-top:1px solid #F3F4F6;
                            padding-top:12px;'>
                    審核狀態：{status_badge}
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.write("")
        col_add, col_out = st.columns(2)
        with col_add:
            if st.button("➕ 新增一筆申報", type="primary", use_container_width=True):
                st.session_state.adding_more = True
                st.rerun()
        with col_out:
            if st.button("登出", use_container_width=True):
                st.session_state.authenticated  = False
                st.session_state.player_name    = ""
                st.session_state.done_checked   = False
                st.session_state.submit_count   = 0
                st.session_state.session_submits = 0
                st.session_state.adding_more    = False
                st.session_state.today_detail   = None
                st.rerun()
        st.stop()

    checks = {}

    # ── 第一區塊：基礎自律模組 ──────────────────────────────────
    st.markdown("#### 【基礎自律模組】")
    checks["出席率"]   = st.checkbox(DISPLAY_MAP["出席率"],   key="出席率")
    checks["死活題"]   = st.checkbox(DISPLAY_MAP["死活題"],   key="死活題")

    st.divider()

    # ── 第二區塊：高壓實戰模組 ──────────────────────────────────
    st.markdown("#### 【高壓實戰模組】")
    checks["次一手"]    = st.checkbox(DISPLAY_MAP["次一手"],    key="次一手")
    checks["輸棋討論"]  = st.checkbox(DISPLAY_MAP["輸棋討論"],  key="輸棋討論")
    checks["AI人機大戰"]= st.checkbox(DISPLAY_MAP["AI人機大戰"],key="AI人機大戰")
    checks["新銳循環賽"]= st.checkbox(DISPLAY_MAP["新銳循環賽"],key="新銳循環賽")

    st.divider()

    # ── 替代任務（下拉選擇等值項目）────────────────────────────
    st.markdown("#### 🔥 教練特批替代任務")
    st.caption("教練有指定替代項目時，請選擇等值的原任務。")
    alt_label = st.selectbox(
        "替代任務等值項目",
        options=list(ALT_TASK_OPTIONS.keys()),
        label_visibility="collapsed",
        key="alt_task_select",
    )
    alt_task = ALT_TASK_OPTIONS[alt_label]  # "" 或 "次一手" 等

    st.divider()

    if st.session_state.adding_more:
        n = st.session_state.submit_count + st.session_state.session_submits + 1
        st.info(f"➕ 新增第 {n} 筆申報")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📤 送出申請", type="primary", use_container_width=True):
            if not any(checks.values()) and not alt_task:
                st.warning("請至少勾選一個項目，或選擇替代任務再送出")
            else:
                with st.spinner("送出中..."):
                    submit_bonus(name, checks, alt_task)
                st.session_state.session_submits += 1
                st.session_state.adding_more = False
                st.session_state.today_detail = {
                    "出席率":     checks.get("出席率",     False),
                    "死活題":     checks.get("死活題",     False),
                    "次一手":     checks.get("次一手",     False),
                    "輸棋討論":   checks.get("輸棋討論",   False),
                    "AI人機大戰": checks.get("AI人機大戰", False),
                    "新銳循環賽": checks.get("新銳循環賽", False),
                    "替代任務":   alt_task,
                    "審核狀態":   "待審核",
                }
                st.balloons()
                st.rerun()
    with col2:
        if st.button("登出", use_container_width=True):
            st.session_state.authenticated  = False
            st.session_state.player_name    = ""
            st.session_state.done_checked   = False
            st.session_state.submit_count   = 0
            st.session_state.session_submits = 0
            st.session_state.adding_more    = False
            st.session_state.today_detail   = None
            st.rerun()
