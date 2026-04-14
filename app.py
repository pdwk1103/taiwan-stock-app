import streamlit as st
import pandas as pd
import requests
import yfinance as yf
from datetime import datetime

# --- 頁面初始設定 ---
st.set_page_config(page_title="台股 AI 多源驗證系統", layout="centered")

# --- 金鑰與設定 ---
# 這是從你最新提供的 Base64 解碼出來的原始 UUID
DEFAULT_FUGLE_KEY = "4f1b5371-6a2d-4253-8eb0-373e0858f210"

st.sidebar.title("🛠️ 數據源校準")
provider = st.sidebar.radio("選擇數據來源", ["Yahoo Finance (免金鑰/延遲)", "Fugle 富果 (需金鑰/實時)"])
discount = st.sidebar.slider("券商折扣", 0.1, 1.0, 0.6)
manual_key = st.sidebar.text_input("手動更換 Fugle Key", value="", type="password")
FINAL_KEY = manual_key if manual_key else DEFAULT_FUGLE_KEY

# --- 數據抓取函數 ---

def fetch_yahoo_data(symbol):
    """使用 Yahoo Finance 獲取數據 (免金鑰)"""
    try:
        # 台股代碼在 Yahoo 需要加 .TW
        ticker = yf.Ticker(f"{symbol}.TW")
        df = ticker.history(period="1d")
        if not df.empty:
            return {
                "price": round(df['Close'].iloc[-1], 2),
                "change": round(((df['Close'].iloc[-1] - df['Open'].iloc[-1]) / df['Open'].iloc[-1]) * 100, 2),
                "volume": int(df['Volume'].iloc[-1])
            }
        return None
    except:
        return None

def fetch_fugle_data(symbol):
    """使用 Fugle API 獲取數據"""
    if not FINAL_KEY: return {"error": "NoKey"}
    # 嘗試兩種路徑格式
    for s in [symbol, f"{symbol}.TW"]:
        url = f"https://api.fugle.tw/marketdata/v1.0/stock/snapshot/{s}"
        headers = {"X-API-KEY": FINAL_KEY}
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                return {
                    "price": data.get('lastPrice'),
                    "change": data.get('changePercent'),
                    "volume": data.get('totalVolume')
                }
        except:
            continue
    return {"error": "ConnectFail"}

# --- 主介面 ---
st.title("🚀 台股 AI 決策驗證系統")

# 1. 標的選擇
stocks = {"2449": "京元電子", "2330": "台積電", "2317": "鴻海", "2303": "聯電", "3711": "日月光"}
target_id = st.selectbox("選取監控標的", list(stocks.keys()), format_func=lambda x: f"{x} {stocks[x]}")

# 2. 根據選擇的來源抓取數據
st.write(f"📡 目前使用來源：**{provider}**")

with st.spinner("正在獲取數據..."):
    if "Yahoo" in provider:
        stock_data = fetch_yahoo_data(target_id)
    else:
        stock_data = fetch_fugle_data(target_id)

# 3. 顯示結果
if stock_data and "error" not in stock_data:
    price = stock_data['price']
    
    st.divider()
    col1, col2 = st.columns(2)
    col1.metric("即時/延遲價", f"{price}", f"{stock_data['change']}%")
    col2.metric("成交量", f"{stock_data['volume']:,}")

    # 4. AI 決策模型
    # 當沖成本 = 手續費(買+賣)*折扣 + 交易稅(0.15%)
    cost_rate = (0.001425 * discount * 2) + 0.0015
    be_price = price * (1 + cost_rate)
    tick = 0.5 if price >= 100 else 0.1
    
    st.success(f"🤖 AI 建議：當沖損平點 {be_price:.2f}")
    
    t1, t2, t3 = st.columns(3)
    t1.error(f"停損\n{price - tick*3:.1f}")
    t2.warning(f"進場\n{price - tick:.1f}")
    t3.success(f"停利\n{price + tick*4:.1f}")

else:
    st.error("❌ 數據讀取失敗")
    if "Fugle" in provider:
        st.warning("提示：Fugle 連線失敗。這通常代表 API Key 尚未生效或權限不足。")
        st.info("建議：請切換到 Yahoo Finance 來源，確認 App 本身功能是否正常。")
    else:
        st.warning("提示：Yahoo 暫時無法獲取數據，請稍後再試。")

st.caption(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")
