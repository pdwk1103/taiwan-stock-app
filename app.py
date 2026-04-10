import streamlit as st
import pandas as pd
import requests
import base64
import yfinance as yf
from datetime import datetime

# --- 頁面初始設定 ---
st.set_page_config(
    page_title="台股實戰 AI 決策",
    page_icon="📈",
    layout="centered"
)

# --- API Key 處理邏輯 ---
# 這是您提供的最新 Base64 金鑰
RAW_B64_KEY = "NGFhMmQ2MTktNTIwYy00ZGEzLTk5NjQtNDg2YWU4MGFjMDk0IDc1YzEzNjgwLWYxNGQtNDFjZS04ZTIwLTY0YWE0MDU4Y2FhYQ=="

def get_default_key():
    try:
        decoded = base64.b64decode(RAW_B64_KEY).decode('utf-8')
        # 嘗試抓取第一段或整段
        return decoded.split(' ')[0]
    except:
        return ""

# 優先順序：側邊欄手動輸入 > 程式內解碼
st.sidebar.header("🔑 金鑰設定")
manual_key = st.sidebar.text_input("手動輸入 Fugle API Key", value="", type="password", help="如果下方顯示連線超時，請直接從富果官網複製 Key 貼於此處")
FUGLE_API_KEY = manual_key if manual_key else get_default_key()

# --- iPhone 專屬深色模式 UI 樣式 ---
st.markdown("""
    <style>
    .main { background-color: #0d1117; color: #adbac7; }
    .stMetric { background-color: #1c2128; padding: 15px; border-radius: 20px; border: 1px solid #444c56; }
    div[data-testid="stMetricValue"] > div { font-size: 24px !important; font-weight: 900 !important; color: #539bf5 !important; }
    .card { background-color: #161b22; padding: 20px; border-radius: 20px; border: 1px solid #30363d; margin-bottom: 15px; }
    .recommend-box { border-left: 5px solid #58a6ff; padding-left: 15px; }
    .profit-text { color: #3fb950; font-weight: bold; }
    .us-market-card { background-color: #0d1117; border: 1px solid #238636; border-radius: 15px; padding: 10px; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- 數據獲取函數 ---
@st.cache_data(ttl=300)
def fetch_us_context():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        soxx = yf.Ticker("SOXX").history(period="2d")
        tsm_change = ((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100
        soxx_change = ((soxx['Close'].iloc[-1] - soxx['Close'].iloc[-2]) / soxx['Close'].iloc[-2]) * 100
        return tsm_change, soxx_change
    except:
        return 0.0, 0.0

def fetch_stock_snapshot(symbol):
    """串接富果實時快照 API"""
    if not FUGLE_API_KEY: return None
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/snapshot/{symbol}"
    headers = {"X-API-KEY": FUGLE_API_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 401:
            st.error("API Key 認證失敗，請檢查金鑰是否正確。")
            return None
        else:
            return None
    except:
        return None

# --- 計算邏輯 ---
def get_tick_size(price):
    if price < 10: return 0.01
    elif price < 50: return 0.05
    elif price < 100: return 0.1
    elif price < 500: return 0.5
    elif price < 1000: return 1.0
    else: return 5.0

def analyze_strategy(price, adr_change, discount=0.6):
    fee_rate = 0.001425 * discount
    tax_rate = 0.0015
    total_cost_rate = (fee_rate * 2) + tax_rate
    breakeven = price * (1 + total_cost_rate)
    tick = get_tick_size(price)
    bias = "多方" if adr_change > 0 else "空方"
    entry = price - tick if bias == "多方" else price + tick
    target = price + (tick * 4) if bias == "多方" else price - (tick * 4)
    stop = price - (tick * 3) if bias == "多方" else price + (tick * 3)
    return breakeven, entry, target, stop, bias

# --- App 主介面 ---
def main():
    st.markdown("### 🚀 台股 AI 全方位實戰系統")
    
    tsm_c, soxx_c = fetch_us_context()
    st.markdown(f"""
    <div class="us-market-card">
        <small style="color:#8b949e">🌐 前夜美股連動</small><br>
        <span style="color:{'#3fb950' if tsm_c >= 0 else '#f85149'}">TSM ADR: {tsm_c:+.2f}%</span> | 
        <span style="color:{'#3fb950' if soxx_c >= 0 else '#f85149'}">費半: {soxx_c:+.2f}%</span>
    </div>
    """, unsafe_allow_html=True)

    stocks = {"2449": "京元電子", "2337": "旺宏", "2303": "聯電", "2317": "鴻海", "2330": "台積電", "3711": "日月光"}
    selected_id = st.selectbox("監控標的", list(stocks.keys()), format_func=lambda x: f"{x} {stocks[x]}")
    
    discount = st.sidebar.slider("券商折扣", 0.1, 1.0, 0.6)
    
    with st.spinner("連線數據庫中..."):
        data = fetch_stock_snapshot(selected_id)
    
    if data:
        curr_p = data.get('lastPrice', 0)
        chg_p = data.get('changePercent', 0)
        vol = data.get('totalVolume', 0)
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("即時價", f"{curr_p}", f"{chg_p}%")
        with col2:
            st.metric("成交量", f"{vol:,}")
            
        be_p, entry, target, stop, bias = analyze_strategy(curr_p, tsm_c, discount)
        
        st.markdown(f"""
        <div class="card recommend-box">
            <h4 style="margin-top:0; color:#58a6ff;">🤖 AI 實戰分析報告</h4>
            <p>目前趨勢：<b style="color:{'#3fb950' if bias=='多方' else '#f85149'}">{bias}優先</b></p>
            <p>當沖損平點：<b class="profit-text">{be_p:.2f}</b> (在此之上才獲利)</p>
            <p style="font-size:0.8rem; color:#8b949e;">* 手續費 6 折 | 已計當沖稅 0.15%</p>
        </div>
        """, unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"<div style='text-align:center'><small>建議進場</small><br><b style='color:#3fb950; font-size:20px'>{entry:.1f}</b></div>", unsafe_allow_html=True)
        c2.markdown(f"<div style='text-align:center'><small>短線停利</small><br><b style='color:#539bf5; font-size:20px'>{target:.1f}</b></div>", unsafe_allow_html=True)
        c3.markdown(f"<div style='text-align:center'><small>強勢停損</small><br><b style='color:#f85149; font-size:20px'>{stop:.1f}</b></div>", unsafe_allow_html=True)

        if st.button("🔄 立即更新報價"):
            st.rerun()
            
        st.caption(f"更新時間：{datetime.now().strftime('%H:%M:%S')}")
    else:
        st.warning("⚠️ 數據尚未讀取。請確認 API Key 是否正確，或點擊左上角箭頭展開選單手動輸入 Key。")

if __name__ == "__main__":
    main()
