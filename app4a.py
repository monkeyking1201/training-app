"""
App 4A — 訓練獎金申報端（選手專用）
流程：輸入 PIN → 顯示姓名 → 勾選今日完成項目 → 送出（每日一次）
資料來源：Schedule_DB（獨立檔案）→ PIN 工作表
資料寫入：Bonus_DB（獨立檔案）→ 工作表1（自動建立 header）
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date, timedelta

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

# 週進度卡用：簡短標籤、項目金額
ITEM_SHORT = {
    "出席率":     "📍出席",
    "死活題":     "🧩死活",
    "次一手":     "🎯次一手",
    "輸棋討論":   "🗣️輸棋",
    "AI人機大戰": "🤖AI",
    "新銳循環賽": "⚔️新銳",
}
ITEM_PRICES_4A = {
    "出席率": 200, "死活題": 300, "次一手": 400,
    "輸棋討論": 400, "AI人機大戰": 400, "新銳循環賽": 600,
}
ALT_PRICES_4A = {"運動": 300, "交流": 300, "讀書會": 300}

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

def get_today_and_week_data(name: str) -> tuple:
    """一次 API，回傳 (今日筆數, 最近一筆明細, 本週週報)
    週報格式：{ds: {item: (approved, pending), "替代任務": str}}
    """
    ws = get_bonus_ws()
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    monday    = today - timedelta(days=today.weekday())
    week_strs = {(monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}

    all_rows    = ws.get_all_values()
    count       = 0
    last_detail = None
    week_data   = {}   # ds -> {item: [approved, pending], "替代任務": str}

    ITEM_COLS = {
        "出席率": 4, "死活題": 5, "次一手": 6,
        "輸棋討論": 7, "AI人機大戰": 8, "新銳循環賽": 9,
    }

    for row in all_rows[1:]:
        if len(row) < 3 or row[1] != name:
            continue
        ds = row[2]
        status = ""
        for v in row[11:]:
            if v.strip() in ("待審核", "已核准"):
                status = v.strip()
                break

        # 今日統計
        if ds == today_str:
            count += 1
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

        # 本週彙整
        if ds in week_strs and status in ("已核准", "待審核"):
            if ds not in week_data:
                week_data[ds] = {item: [0, 0] for item in ITEM_COLS}
            for item, col in ITEM_COLS.items():
                if col < len(row) and row[col] == "V":
                    if status == "已核准":
                        week_data[ds][item][0] += 1
                    else:
                        week_data[ds][item][1] += 1
            if len(row) > 10 and row[10].strip():
                week_data[ds]["替代任務"] = row[10].strip()

    return count, last_detail, week_data

def render_week_summary_html(week_data: dict, today: date) -> str:
    """選手端本週進度卡 HTML"""
    monday     = today - timedelta(days=today.weekday())
    week_start = monday.strftime("%m/%d")
    week_end   = (monday + timedelta(days=6)).strftime("%m/%d")
    WD         = ["一", "二", "三", "四", "五", "六", "日"]
    ITEMS      = ["出席率", "死活題", "次一手", "輸棋討論", "AI人機大戰", "新銳循環賽"]

    total_approved = 0
    rows_html      = ""

    for i in range(7):
        d  = monday + timedelta(days=i)
        ds = d.strftime("%Y-%m-%d")
        label = f"{d.strftime('%m/%d')}（{WD[i]}）"

        if d > today:
            continue

        if ds not in week_data:
            rows_html += (
                f"<div style='padding:7px 0;border-bottom:1px solid #F9FAFB;'>"
                f"<span style='font-size:13px;color:#D1D5DB;font-weight:500;"
                f"display:inline-block;width:90px;'>{label}</span>"
                f"<span style='font-size:12px;color:#E5E7EB;'>（未申報）</span></div>"
            )
            continue

        row_d  = week_data[ds]
        badges = ""
        for item in ITEMS:
            a, p = row_d.get(item, [0, 0])
            if a > 0:
                lbl = ITEM_SHORT[item]
                sfx = f"×{a}" if a > 1 else ""
                total_approved += a
                badges += (
                    f"<span style='background:#D1FAE5;color:#065F46;padding:3px 9px;"
                    f"border-radius:20px;font-size:12px;font-weight:600;"
                    f"margin-right:5px;white-space:nowrap;'>{lbl}{sfx}</span>"
                )
            elif p > 0:
                lbl = ITEM_SHORT[item]
                badges += (
                    f"<span style='background:#FEF3C7;color:#92400E;padding:3px 9px;"
                    f"border-radius:20px;font-size:12px;font-weight:600;"
                    f"margin-right:5px;white-space:nowrap;'>⏳{lbl}</span>"
                )
        alt = row_d.get("替代任務", "")
        if alt:
            total_approved += 1
            badges += (
                f"<span style='background:#FEF3C7;color:#92400E;padding:3px 9px;"
                f"border-radius:20px;font-size:12px;font-weight:600;"
                f"margin-right:5px;white-space:nowrap;'>🔥{alt}</span>"
            )
        if not badges:
            badges = "<span style='font-size:12px;color:#D1D5DB;'>（待審核中）</span>"

        rows_html += (
            f"<div style='padding:8px 0;border-bottom:1px solid #F9FAFB;'>"
            f"<span style='font-size:13px;font-weight:600;color:#374151;"
            f"display:inline-block;width:90px;min-width:90px;'>{label}</span>"
            f"{badges}</div>"
        )

    if not rows_html:
        rows_html = "<div style='color:#9CA3AF;font-size:14px;padding:8px 0;'>本週尚無申報記錄</div>"

    return f"""
    <div style='background:#fff;border:1px solid #E5E7EB;border-radius:14px;
                padding:20px 24px;margin:16px 0 8px 0;
                box-shadow:0 2px 8px rgba(0,0,0,0.05);'>
        <div style='font-size:11px;color:#9CA3AF;font-weight:700;
                    letter-spacing:0.1em;text-transform:uppercase;margin-bottom:14px;'>
            📅 本週訓練進度　{week_start} － {week_end}
        </div>
        {rows_html}
        <div style='margin-top:14px;border-top:1px solid #F3F4F6;padding-top:12px;'>
            <span style='font-size:15px;font-weight:700;color:#1E3A8A;'>
                ✅ 本週已核准 {total_approved} 項
            </span>
            <span style='font-size:12px;color:#9CA3AF;margin-left:10px;'>
                ✅綠色=已核准　⏳黃色=待審核
            </span>
        </div>
    </div>
    """

def _show_makeup_form(name: str, prefix: str):
    """補交申報區塊（不含出席率，供兩個畫面共用）"""
    st.caption("補交之前未完成的任務，教練審核後計入獎金。出席率不可補交。")
    mu_date = st.date_input(
        "補交日期",
        value=date.today() - timedelta(days=1),
        max_value=date.today() - timedelta(days=1),
        min_value=date(2026, 8, 1),
        key=f"{prefix}_mu_date",
    )
    st.markdown("**選擇補交項目**")
    mu_checks = {
        "死活題":     st.checkbox(DISPLAY_MAP["死活題"],     key=f"{prefix}_mu_死活題"),
        "次一手":     st.checkbox(DISPLAY_MAP["次一手"],     key=f"{prefix}_mu_次一手"),
        "輸棋討論":   st.checkbox(DISPLAY_MAP["輸棋討論"],   key=f"{prefix}_mu_輸棋討論"),
        "AI人機大戰": st.checkbox(DISPLAY_MAP["AI人機大戰"], key=f"{prefix}_mu_AI"),
        "新銳循環賽": st.checkbox(DISPLAY_MAP["新銳循環賽"], key=f"{prefix}_mu_新銳"),
    }
    mu_alt_label = st.selectbox(
        "替代任務",
        options=list(ALT_TASK_OPTIONS.keys()),
        label_visibility="collapsed",
        key=f"{prefix}_mu_alt",
    )
    mu_alt = ALT_TASK_OPTIONS[mu_alt_label]
    if st.button("📤 送出補交申請", key=f"{prefix}_mu_btn", use_container_width=True):
        if not any(mu_checks.values()) and not mu_alt:
            st.warning("請至少勾選一個項目")
        else:
            with st.spinner("送出中..."):
                submit_bonus(name, mu_checks, mu_alt, submit_date=mu_date)
            st.success(f"✅ 已送出 {mu_date.strftime('%m/%d')} 補交申請，等待教練審核")
            st.rerun()

def submit_bonus(name: str, checks: dict, alt_task: str, submit_date: date = None):
    """
    checks: 六個主項目的勾選狀態
    alt_task: 替代任務
    submit_date: 補交日期（None = 今日）
    """
    ws = get_bonus_ws()
    now = datetime.now()
    target_date = submit_date if submit_date is not None else date.today()
    weekday = WEEKDAY_MAP[target_date.weekday()]
    row = [
        now.strftime("%Y-%m-%d %H:%M:%S"),
        name,
        target_date.strftime("%Y-%m-%d"),
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
if "week_summary" not in st.session_state:
    st.session_state.week_summary = {}

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
        count, detail, week_data = get_today_and_week_data(name)
        st.session_state.submit_count  = count
        st.session_state.today_detail  = detail
        st.session_state.week_summary  = week_data
        st.session_state.done_checked  = True

    # ── 本週進度卡（常駐顯示）────────────────────────────────────
    st.markdown(
        render_week_summary_html(st.session_state.week_summary, today),
        unsafe_allow_html=True,
    )

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
                st.session_state.authenticated   = False
                st.session_state.player_name     = ""
                st.session_state.done_checked    = False
                st.session_state.submit_count    = 0
                st.session_state.session_submits = 0
                st.session_state.adding_more     = False
                st.session_state.today_detail    = None
                st.session_state.week_summary    = {}
                st.rerun()

        st.divider()
        with st.expander("📬 補交過去項目（不含出席率）"):
            _show_makeup_form(name, prefix="done")
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
            st.session_state.authenticated   = False
            st.session_state.player_name     = ""
            st.session_state.done_checked    = False
            st.session_state.submit_count    = 0
            st.session_state.session_submits = 0
            st.session_state.adding_more     = False
            st.session_state.today_detail    = None
            st.session_state.week_summary    = {}
            st.rerun()

    st.divider()
    with st.expander("📬 補交過去項目（不含出席率）"):
        _show_makeup_form(name, prefix="form")
