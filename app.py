import streamlit as st
import pandas as pd
import requests
import datetime

# --- 防禦型匯入：檢查 yfinance 是否安裝 ---
try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

# --- 基本頁面配置 ---
st.set_page_config(page_title="台股 AI 決策系統", layout="centered")

# --- 金鑰設定 (您的最新 4f1b 序號) ---
FUGLE_API_KEY = "4f1b5371-6a2d-4253-8eb0-373e0858f210"

# --- 側邊欄 ---
st.sidebar.title("📈 實戰控制台")
discount = st.sidebar.slider("券商手續費折扣", 0.1, 1.0, 0.6)
st.sidebar.markdown("---")
debug_mode = st.sidebar.checkbox("開啟 API 連線診斷")

# --- 數據獲取引擎 ---

def get_yahoo_data(symbol):
    """Yahoo Finance 備援來源"""
    if not YF_AVAILABLE:
        return None
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

def get_fugle_snapshot(symbol):
    """依照官方規範抓取富果快照"""
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/snapshot/{symbol}"
    headers = {"X-API-KEY": FUGLE_API_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if debug_mode:
            st.sidebar.write(f"🔍 Fugle 狀態碼: {res.status_code}")
        if res.status_code == 200:
            d = res.json()
            return {
                "source": "Fugle (實時數據)",
                "price": d.get('lastPrice'),
                "change": d.get('changePercent'),
                "vol": d.get('totalVolume')
            }
        return None
    except:
        return None

# --- 主畫面 ---
st.title("🚀 台股 AI 決策系統")

if not YF_AVAILABLE:
    st.error("🚨 偵測到環境設定錯誤！")
    st.markdown("""
    **系統偵測到尚未安裝 `yfinance` 工具包。請依照以下步驟修復：**
    1. 確保 GitHub 上的檔案名稱為 `requirements.txt` (不可有大寫)。
    2. 內容必須包含 `yfinance` 這一行。
    3. 到 Streamlit Cloud 控制面板點擊 **Manage app** -> **Reboot App**。
    """)
    st.stop()

# 1. 標的選取
stocks = {"2449": "京元電子", "2330": "台積電", "2317": "鴻海", "2303": "聯電", "3711": "日月光"}
sid = st.selectbox("監控標的", list(stocks.keys()), format_func=lambda x: f"{x} {stocks[x]}")

# 2. 智慧獲取數據
with st.spinner("同步數據中..."):
    # 優先富果
    stock_data = get_fugle_snapshot(sid)
    # 失敗換 Yahoo
    if not stock_data:
        stock_data = get_yahoo_data(sid)

# 3. 數據展示
if stock_data:
    price = stock_data['price']
    source_label = "🟢 實時" if "Fugle" in stock_data['source'] else "🟡 延遲"
    st.markdown(f"📡 數據來源：**{stock_data['source']}** ({source_label})")
    
    col1, col2 = st.columns(2)
    col1.metric("即時成交價", f"{price}", f"{stock_data['change']}%")
    col2.metric("總量", f"{stock_data['vol']:,}")

    st.divider()

    # 4. AI 決策模型
    cost_rate = (0.001425 * discount * 2) + 0.0015
    be_price = price * (1 + cost_rate)
    tick = 0.5 if price >= 100 else 0.1
    
    st.success(f"🤖 AI 當沖損平點建議：**{be_price:.2f}**")
    
    t1, t2, t3 = st.columns(3)
    t1.error(f"停損\n{price - tick*3:.1f}")
    t2.warning(f"進場\n{price - tick:.1f}")
    t3.success(f"停利\n{price + tick*4:.1f}")

    if st.button("🔄 手動刷新報價"):
        st.rerun()
else:
    st.error("❌ 所有數據源連線失敗。")

st.caption(f"最後更新：{datetime.datetime.now().strftime('%H:%M:%S')}")

