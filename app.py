import streamlit as st
import pandas as pd
import requests
import yfinance as yf
from datetime import datetime

# --- 基本頁面配置 (iPhone 優化) ---
st.set_page_config(page_title="台股 AI 決策系統", layout="centered")

# --- 金鑰設定 (已填入您最新提供的 4f1b 序號) ---
# 重要提醒：請確保在富果開發者後台的「權限範圍 (Scopes)」中勾選了 "Snapshot" 並儲存
FUGLE_API_KEY = "4f1b5371-6a2d-4253-8eb0-373e0858f210"

# --- 側邊欄：功能與診斷 ---
st.sidebar.title("📈 實戰控制台")
discount = st.sidebar.slider("券商手續費折扣", 0.1, 1.0, 0.6)
st.sidebar.markdown("---")
debug_mode = st.sidebar.checkbox("開啟 API 連線診斷")
st.sidebar.info("優先抓取 Fugle 實時數據，失敗時自動切換 Yahoo 延遲數據。")

# --- 數據抓取引擎 ---

def get_yahoo_data(symbol):
    """Yahoo Finance 備援來源 (免金鑰)"""
    try:
        ticker = yf.Ticker(f"{symbol}.TW")
        df = ticker.history(period="1d")
        if not df.empty:
            last_p = df['Close'].iloc[-1]
            # 取得昨日收盤價計算漲跌
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

def get_fugle_snapshot(symbol):
    """依照官方文件規範抓取富果快照"""
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/snapshot/{symbol}"
    headers = {"X-API-KEY": FUGLE_API_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        
        # 診斷模式：在側邊欄顯示 API 狀態
        if debug_mode:
            st.sidebar.write(f"🔍 Fugle 狀態碼: {res.status_code}")
            if res.status_code != 200:
                st.sidebar.error(f"錯誤訊息: {res.text}")
        
        if res.status_code == 200:
            d = res.json()
            return {
                "source": "Fugle (實時數據)",
                "price": d.get('lastPrice'),
                "change": d.get('changePercent'),
                "vol": d.get('totalVolume')
            }
        return None
    except Exception as e:
        if debug_mode:
            st.sidebar.error(f"連線崩潰: {str(e)}")
        return None

# --- 主畫面介面 ---
st.title("🚀 台股 AI 決策系統")

# 1. 標的選取
stocks = {"2449": "京元電子", "2330": "台積電", "2317": "鴻海", "2303": "聯電", "3711": "日月光"}
sid = st.selectbox("監控標的", list(stocks.keys()), format_func=lambda x: f"{x} {stocks[x]}")

# 2. 智慧數據獲取
with st.spinner("數據同步中..."):
    # 優先嘗試富果
    stock_data = get_fugle_snapshot(sid)
    # 若富果失敗，自動無縫切換 Yahoo
    if not stock_data:
        stock_data = get_yahoo_data(sid)

# 3. 數據展示
if stock_data:
    price = stock_data['price']
    source_type = "🟢 實時" if "Fugle" in stock_data['source'] else "🟡 延遲"
    
    st.markdown(f"📡 來源：**{stock_data['source']}** ({source_type})")
    
    col1, col2 = st.columns(2)
    col1.metric("即時成交價", f"{price}", f"{stock_data['change']}%")
    col2.metric("總成交量", f"{stock_data['vol']:,}")

    st.divider()

    # 4. AI 決策模型 (成本計算)
    # 損平點 = 價格 * (1 + 買賣手續費*折扣 + 當沖稅 0.15%)
    cost_rate = (0.001425 * discount * 2) + 0.0015
    be_price = price * (1 + cost_rate)
    tick = 0.5 if price >= 100 else 0.1
    
    st.success(f"🤖 AI 當沖損平點預估：**{be_price:.2f}**")
    
    # 5. 操作參考位
    t1, t2, t3 = st.columns(3)
    t1.error(f"📉 停損位\n{price - tick*3:.1f}")
    t2.warning(f"🟡 進場位\n{price - tick:.1f}")
    t3.success(f"🚀 停利位\n{price + tick*4:.1f}")

    if st.button("🔄 立即更新報價"):
        st.rerun()

    if "Yahoo" in stock_data['source']:
        st.warning("⚠️ 富果 API 權限未開通或金鑰失效，目前自動切換為 Yahoo 延遲數據。")
else:
    st.error("❌ 無法連線至任何數據源，請確認網路或 API 設定。")

st.caption(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")

