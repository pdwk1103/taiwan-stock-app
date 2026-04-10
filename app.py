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

# --- API Key 處理 (自動解碼新金鑰) ---
# 使用您提供的最新 Base64 金鑰
RAW_B64_KEY = "NGFhMmQ2MTktNTIwYy00ZGEzLTk5NjQtNDg2YWU4MGFjMDk0IDc1YzEzNjgwLWYxNGQtNDFjZS04ZTIwLTY0YWE0MDU4Y2FhYQ=="
try:
    decoded_key = base64.b64decode(RAW_B64_KEY).decode('utf-8').split(' ')[0]
    FUGLE_API_KEY = decoded_key
except:
    FUGLE_API_KEY = ""

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
    """獲取美股前夜連動數據 (TSM ADR, SOXX)"""
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
        res = requests.get(url, headers=headers, timeout=5)
        return res.json() if res.status_code == 200 else None
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
    """綜合美股、成本與跳檔的分析模型 (預設 6 折)"""
    fee_rate = 0.001425 * discount
    tax_rate = 0.0015 # 當沖減半
    # 總交易成本率：(買手續費 + 賣手續費 + 交易稅)
    total_cost_rate = (fee_rate * 2) + tax_rate
    
    breakeven = price * (1 + total_cost_rate)
    tick = get_tick_size(price)
    
    # 根據美股 ADR 決定建議偏向
    bias = "多方" if adr_change > 0 else "空方"
    
    # 點位建議
    entry = price - tick if bias == "多方" else price + tick
    target = price + (tick * 4) if bias == "多方" else price - (tick * 4)
    stop = price - (tick * 3) if bias == "多方" else price + (tick * 3)
    
    return breakeven, entry, target, stop, bias

# --- App 主介面 ---
def main():
    st.markdown("### 🚀 台股 AI 全方位實戰系統")
    
    # 1. 美股連動區
    tsm_c, soxx_c = fetch_us_context()
    st.markdown(f"""
    <div class="us-market-card">
        <small style="color:#8b949e">🌐 前夜美股連動</small><br>
        <span style="color:{'#3fb950' if tsm_c >= 0 else '#f85149'}">TSM ADR: {tsm_c:+.2f}%</span> | 
        <span style="color:{'#3fb950' if soxx_c >= 0 else '#f85149'}">費半: {soxx_c:+.2f}%</span>
    </div>
    """, unsafe_allow_html=True)

    # 2. 標的選擇
    stocks = {"2449": "京元電子", "2337": "旺宏", "2303": "聯電", "2317": "鴻海", "2330": "台積電", "3711": "日月光"}
    selected_id = st.selectbox("監控標的", list(stocks.keys()), format_func=lambda x: f"{x} {stocks[x]}")
    
    # 手續費折扣 (預設 6 折)
    discount = st.sidebar.slider("券商折扣", 0.1, 1.0, 0.6)
    
    # 3. 實時抓取與分析
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
        
        # 4. 決策卡片
        st.markdown(f"""
        <div class="card recommend-box">
            <h4 style="margin-top:0; color:#58a6ff;">🤖 AI 實戰分析報告</h4>
            <p>目前趨勢：<b style="color:{'#3fb950' if bias=='多方' else '#f85149'}">{bias}優先</b></p>
            <p>當沖損平點：<b class="profit-text">{be_p:.2f}</b> (在此之上才賺錢)</p>
            <p style="font-size:0.8rem; color:#8b949e;">* 手續費 {discount*10:.1f} 折 | 已計算當沖稅 0.15%</p>
        </div>
        """, unsafe_allow_html=True)
        
        # 5. 點位提示
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"<div style='text-align:center'><small>建議進場</small><br><b style='color:#3fb950; font-size:20px'>{entry:.1f}</b></div>", unsafe_allow_html=True)
        c2.markdown(f"<div style='text-align:center'><small>短線停利</small><br><b style='color:#539bf5; font-size:20px'>{target:.1f}</b></div>", unsafe_allow_html=True)
        c3.markdown(f"<div style='text-align:center'><small>強勢停損</small><br><b style='color:#f85149; font-size:20px'>{stop:.1f}</b></div>", unsafe_allow_html=True)

        if st.button("🔄 手動更新報價"):
            st.rerun()
            
        st.caption(f"系統狀態：Fugle 實時數據連線中 | 更新時間：{datetime.now().strftime('%H:%M:%S')}")
    else:
        st.error("連線超時，請檢查富果開發者中心 API Key 是否已驗證開通。")

if __name__ == "__main__":
    main()
```

### 覆蓋與部署步驟提醒：

1.  **覆蓋 GitHub**：點擊 `app.py` 的編輯圖示（鉛筆），將舊內容全部刪除，貼上這段新程式碼，然後 **Commit changes**。
2.  **確認 `requirements.txt`**：請確保該檔案內容依然是以下四行：
    ```text
    streamlit
    pandas
    requests
    yfinance
