import streamlit as st
import pandas as pd
import requests
import yfinance as yf
from datetime import datetime

# --- 基本頁面配置 ---
st.set_page_config(page_title="台股 AI 實戰決策", layout="centered")

# --- 金鑰設定 (這是您最新提供的 4f1b 序號) ---
FUGLE_API_KEY = "4f1b5371-6a2d-4253-8eb0-373e0858f210"

# --- 側邊欄：實戰設定 ---
st.sidebar.title("🛠️ 交易控制台")
discount = st.sidebar.slider("券商手續費折扣", 0.1, 1.0, 0.6)
st.sidebar.markdown("---")
debug_mode = st.sidebar.checkbox("開啟 API 偵錯訊息", value=True)

# --- 核心數據引擎 ---

def get_yahoo_data(symbol):
    """Yahoo Finance 備援來源"""
    try:
        ticker = yf.Ticker(f"{symbol}.TW")
        df = ticker.history(period="1d")
        if not df.empty:
            last_p = df['Close'].iloc[-1]
            prev_p = ticker.info.get('regularMarketPreviousClose', last_p)
            change = ((last_p - prev_p) / prev_p) * 100
            return {
                "source": "Yahoo (延遲數據)",
                "price": round(last_p, 2),
                "change": round(change, 2),
                "vol": int(df['Volume'].iloc[-1])
            }
    except:
        return None

def get_fugle_intraday(symbol):
    """依照官方 SDK 規範：使用 intraday/quote 獲取數據，徹底修復 404"""
    # 富果 V1.0 標準端點：/intraday/quote/{symbol}
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}"
    headers = {"X-API-KEY": FUGLE_API_KEY}
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        
        if debug_mode:
            st.sidebar.write(f"📡 API 請求: {url}")
            st.sidebar.write(f"🔍 狀態碼: {res.status_code}")
            if res.status_code != 200:
                st.sidebar.error(f"錯誤訊息: {res.text}")
        
        if res.status_code == 200:
            d = res.json()
            # 根據 V1.0 結構解析資料
            return {
                "source": "Fugle (實時報價)",
                "price": d.get('lastPrice'),
                "change": d.get('changePercent'),
                "vol": d.get('totalVolume')
            }
    except Exception as e:
        if debug_mode:
            st.sidebar.error(f"連線異常: {str(e)}")
    return None

# --- 主介面 ---
st.title("🚀 台股 AI 決策系統")

# 1. 標的選取
stocks = {"2449": "京元電子", "2330": "台積電", "2317": "鴻海", "2303": "聯電", "3711": "日月光"}
sid = st.selectbox("監控標的", list(stocks.keys()), format_func=lambda x: f"{x} {stocks[x]}")

# 2. 數據獲取邏輯
with st.spinner("同步數據中..."):
    # 優先嘗試富果最新官方路徑
    stock_data = get_fugle_intraday(sid)
    # 若失敗，自動無縫切換 Yahoo
    if not stock_data:
        stock_data = get_yahoo_data(sid)

# 3. 數據展示
if stock_data:
    p = stock_data['price']
    source_label = "🟢 實時" if "Fugle" in stock_data['source'] else "🟡 延遲"
    
    st.markdown(f"數據來源：**{stock_data['source']}** ({source_label})")
    
    col1, col2 = st.columns(2)
    col1.metric("成交價", f"{p}", f"{stock_data['change']}%")
    col2.metric("總成交量", f"{stock_data['vol']:,}")

    st.divider()

    # 4. AI 決策模型 (成本計算)
    # 損平點公式：價格 * (1 + 買賣手續費率*折扣 + 交易稅 0.15%)
    cost_rate = (0.001425 * discount * 2) + 0.0015
    be_price = p * (1 + cost_rate)
    tick = 0.5 if p >= 100 else 0.1
    
    st.success(f"🤖 AI 當沖損平點預估：**{be_price:.2f}**")
    
    # 5. 操作參考位
    t1, t2, t3 = st.columns(3)
    t1.error(f"📉 停損位\n{p - tick*3:.1f}")
    t2.warning(f"🟡 進場位\n{p - tick:.1f}")
    t3.success(f"🚀 停利位\n{p + tick*4:.1f}")

    if st.button("🔄 更新行情"):
        st.rerun()

    if "Yahoo" in stock_data['source']:
        st.warning("⚠️ 富果 API 暫時無法獲取實時數據，目前使用 Yahoo 備援。")
else:
    st.error("❌ 無法讀取數據。")

st.caption(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")

