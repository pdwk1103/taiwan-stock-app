import streamlit as st
import pandas as pd
import requests
import base64
import yfinance as yf
from datetime import datetime

# --- 基本設定 ---
st.set_page_config(page_title="台股實戰系統")

# --- API KEY 處理 ---
# 這是您提供的最新金鑰
RAW_KEY = "NGFhMmQ2MTktNTIwYy00ZGEzLTk5NjQtNDg2YWU4MGFjMDk0IDc1YzEzNjgwLWYxNGQtNDFjZS04ZTIwLTY0YWE0MDU4Y2FhYQ=="

def get_key():
    try:
        # 解碼後取第一段 UUID
        decoded = base64.b64decode(RAW_KEY).decode('utf-8')
        return decoded.split(' ')[0].strip()
    except:
        return ""

# 側邊欄：手動輸入與折扣設定
st.sidebar.title("系統設定")
user_key = st.sidebar.text_input("手動輸入 Fugle Key", value="", type="password")
discount = st.sidebar.slider("券商折扣", 0.1, 1.0, 0.6)
FINAL_KEY = user_key if user_key else get_key()

# --- 數據獲取 (移除快取以防報錯) ---
def get_adr_data():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return ((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100
    except:
        return 0.0

def get_stock_data(symbol):
    if not FINAL_KEY: return None
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/snapshot/{symbol}"
    headers = {"X-API-KEY": FINAL_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
        return {"error": res.status_code}
    except:
        return None

# --- 主程式介面 ---
st.title("📈 台股實戰監控")

# 1. 美股連動
adr_change = get_adr_data()
st.info(f"🌐 前夜台積電 ADR 連動：{adr_change:+.2f}%")

# 2. 標的選擇
stocks = {"2449": "京元電子", "2330": "台積電", "2317": "鴻海", "2303": "聯電", "3711": "日月光"}
target = st.selectbox("監控標的", list(stocks.keys()), format_func=lambda x: f"{x} {stocks[x]}")

# 3. 獲取數據
data = get_stock_data(target)

if data and "error" not in data:
    price = data.get('lastPrice', 0)
    change = data.get('changePercent', 0)
    vol = data.get('totalVolume', 0)

    # 行情看板
    st.divider()
    c1, c2 = st.columns(2)
    c1.metric("成交價", f"{price}", f"{change}%")
    c2.metric("總成交量", f"{vol:,}")

    # 4. 決策模型 (6 折)
    cost_rate = (0.001425 * discount * 2) + 0.0015
    be_price = price * (1 + cost_rate)
    tick = 0.5 if price >= 100 else 0.1

    st.success(f"🤖 AI 建議：當沖損平點為 {be_price:.2f}")
    
    t1, t2, t3 = st.columns(3)
    t1.write(f"📉 停損\n{price - tick*3:.1f}")
    t2.write(f"🟡 進場\n{price - tick:.1f}")
    t3.write(f"🚀 停利\n{price + tick*4:.1f}")

    if st.button("🔄 更新報價"):
        st.rerun()

else:
    st.error("⚠️ 無法讀取即時數據")
    st.write("請展開左側選單，確認 API Key 是否正確。")
    if data and "error" in data:
        st.write(f"錯誤代碼: {data['error']}")

st.caption(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")

