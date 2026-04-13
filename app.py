import streamlit as st
import pandas as pd
import requests
import base64
import yfinance as yf
from datetime import datetime

# --- 基本設定 ---
st.set_page_config(page_title="台股 AI 決策系統", layout="centered")

# --- API KEY 處理邏輯 ---
# 這是您提供的最新 Base64 加密金鑰
RAW_B64 = "NGFhMmQ2MTktNTIwYy00ZGEzLTk5NjQtNDg2YWU4MGFjMDk0IDc1YzEzNjgwLWYxNGQtNDFjZS04ZTIwLTY0YWE0MDU4Y2FhYQ=="

def get_key_from_b64(b64_str):
    try:
        decoded = base64.b64decode(b64_str).decode('utf-8')
        # 取第一段 UUID
        return decoded.split(' ')[0].strip()
    except:
        return ""

# 提供側邊欄設定，方便實戰時手動校正
st.sidebar.title("⚙️ 系統設定")
st.sidebar.markdown("---")
# 手動輸入框：如果自動解碼失敗，可以直接把那串金鑰貼在這裡
manual_key = st.sidebar.text_input("手動輸入 API Key", value="", type="password", help="若連線超時，請貼上富果金鑰")
discount = st.sidebar.slider("券商手續費折扣", 0.1, 1.0, 0.6)

# 決定最後使用的 API Key
FUGLE_API_KEY = manual_key if manual_key else get_key_from_b64(RAW_B64)

# --- 手機版 UI 樣式 ---
st.markdown("""
    <style>
    .main { background-color: #0d1117; color: #adbac7; }
    .stMetric { background-color: #1c2128; padding: 12px; border-radius: 15px; border: 1px solid #30363d; }
    div[data-testid="stMetricValue"] > div { font-size: 26px !important; font-weight: 800 !important; color: #58a6ff !important; }
    .info-card { background-color: #161b22; padding: 15px; border-radius: 15px; border: 1px solid #30363d; margin: 10px 0; }
    .price-box { border-left: 4px solid #58a6ff; padding-left: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 數據抓取 ---
@st.cache_data(ttl=600)
def fetch_adr():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return ((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100
    except:
        return 0.0

def fetch_stock(symbol):
    if not FUGLE_API_KEY: return None
    # 富果 v1.0 快照 API
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/snapshot/{symbol}"
    headers = {"X-API-KEY": FUGLE_API_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
        return {"error": res.status_code, "msg": res.text}
    except Exception as e:
        return {"error": "Timeout", "msg": str(e)}

# --- 主畫面 ---
st.title("📈 台股實戰 AI 監控")

# 1. 前夜美股連動
adr_change = fetch_adr()
st.info(f"🌐 前夜台積電 ADR 連動：{adr_change:+.2f}%")

# 2. 標的選擇
stocks = {"2449": "京元電子", "2330": "台積電", "2317": "鴻海", "2303": "聯電", "3711": "日月光"}
target = st.selectbox("監控標的", list(stocks.keys()), format_func=lambda x: f"{x} {stocks[x]}")

# 3. 獲取並顯示數據
with st.spinner("連線數據庫中..."):
    data = fetch_stock(target)

if data and "error" not in data:
    price = data.get('lastPrice', 0)
    change = data.get('changePercent', 0)
    vol = data.get('totalVolume', 0)

    # 行情看板
    c1, c2 = st.columns(2)
    with c1: st.metric("成交價", f"{price}", f"{change}%")
    with c2: st.metric("總成交量", f"{vol:,}")

    # AI 決策邏輯 (6 折)
    cost_rate = (0.001425 * discount * 2) + 0.0015
    be_price = price * (1 + cost_rate)
    tick = 0.5 if price >= 100 else 0.1

    st.markdown(f"""
    <div class="info-card price-box">
        <h4 style="margin:0; color:#58a6ff;">🤖 AI 實戰分析</h4>
        <p style="margin:5px 0;">建議趨勢：<b>{'偏多操作' if adr_change > 0 else '保守觀望'}</b></p>
        <p style="margin:5px 0;">當沖損平點：<b style="color:#3fb950;">{be_price:.2f}</b> (在此之上才獲利)</p>
    </div>
    """, unsafe_allow_html=True)

    # 點位提示
    t1, t2, t3 = st.columns(3)
    t1.error(f"停損\n{price - tick*3:.1f}")
    t2.warning(f"進場\n{price - tick:.1f}")
    t3.success(f"停利\n{price + tick*4:.1f}")

    if st.button("🔄 即時更新報價"):
        st.rerun()

else:
    st.error("⚠️ 連線超時或金鑰無效")
    if data and "msg" in data:
        st.caption(f"錯誤代碼: {data['error']} | 訊息: {data['msg']}")
    st.markdown("""
        **解決辦法：**
        1. 請點擊手機畫面 **左上角的 `>` 箭頭** 展開側邊選單。
        2. 在 **「手動輸入 API Key」** 欄位貼上您從富果複製的原始 UUID 金鑰。
        3. 檢查富果開發者中心是否已開通「行情數據」權限。
    """)

st.caption(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")
