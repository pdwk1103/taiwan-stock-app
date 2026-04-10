import streamlit as st
import pandas as pd
import requests
import base64
import yfinance as yf
from datetime import datetime

# --- 設定 ---
st.set_page_config(page_title="台股 AI 決策", layout="centered")

# --- API KEY 處理 ---
# 這是您提供的最新金鑰
RAW_KEY = "NGFhMmQ2MTktNTIwYy00ZGEzLTk5NjQtNDg2YWU4MGFjMDk0IDc1YzEzNjgwLWYxNGQtNDFjZS04ZTIwLTY0YWE0MDU4Y2FhYQ=="

def get_key():
    try:
        # 解碼並嘗試使用第一段金鑰
        decoded = base64.b64decode(RAW_KEY).decode('utf-8')
        return decoded.split(' ')[0]
    except:
        return ""

# 提供側邊欄輸入，以防自動解碼失效
st.sidebar.title("系統設定")
user_key = st.sidebar.text_input("手動輸入 Fugle API Key", value="", type="password")
FINAL_KEY = user_key if user_key else get_key()

# --- UI 樣式 ---
st.markdown("""
    <style>
    .main { background-color: #0d1117; color: #adbac7; }
    .stMetric { background-color: #1c2128; padding: 15px; border-radius: 15px; border: 1px solid #30363d; }
    .card { background-color: #161b22; padding: 15px; border-radius: 15px; border: 1px solid #30363d; margin-top: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 數據獲取 ---
@st.cache_data(ttl=300)
def get_us_data():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        tsm_c = ((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100
        return tsm_c
    except:
        return 0.0

def get_stock(symbol):
    if not FINAL_KEY: return None
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/snapshot/{symbol}"
    headers = {"X-API-KEY": FINAL_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        return res.json() if res.status_code == 200 else None
    except:
        return None

# --- 主程式 ---
st.title("🚀 台股實戰系統")

# 美股連動
adr = get_us_data()
st.info(f"🌐 前夜台積電 ADR 連動: {adr:+.2f}%")

# 標的選擇
stocks = {"2449": "京元電子", "2330": "台積電", "2317": "鴻海", "2303": "聯電"}
sid = st.selectbox("選取監控標的", list(stocks.keys()), format_func=lambda x: f"{x} {stocks[x]}")

# 抓取即時數據
data = get_stock(sid)

if data:
    price = data.get('lastPrice', 0)
    col1, col2 = st.columns(2)
    col1.metric("成交價", f"{price}", f"{data.get('changePercent')}%")
    col2.metric("總量", f"{data.get('totalVolume'):,}")

    # 計算建議 (手續費 6 折)
    # 損平點估算：價格 * 1.0023
    be = price * 1.0023
    tick = 0.5 if price >= 100 else 0.1
    
    st.markdown(f"""
    <div class="card">
        <h4 style="color:#58a6ff; margin:0;">🤖 AI 決策分析</h4>
        <p style="margin:5px 0;">建議操作：<b>{'偏多現沖' if adr > 0 else '保守觀望'}</b></p>
        <p style="margin:5px 0;">當沖損平點：<b style="color:#3fb950;">{be:.2f}</b></p>
    </div>
    """, unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns(3)
    c1.error(f"停損\n{price - tick*3:.1f}")
    c2.warning(f"進場\n{price - tick:.1f}")
    c3.success(f"停利\n{price + tick*4:.1f}")

    if st.button("🔄 更新報價"):
        st.rerun()
else:
    st.error("⚠️ 無法獲取即時數據。請點擊左側箭頭展開選單，手動貼入富果金鑰。")
    st.write("目前的金鑰偵測為：", FINAL_KEY[:5] + "..." if FINAL_KEY else "無")

