import streamlit as st
import pandas as pd
import requests
import yfinance as yf
from datetime import datetime

# --- 基本頁面設定 ---
st.set_page_config(page_title="台股 AI 實戰", layout="centered")

# --- 原始金鑰直接填入 (這就是從你那串 Base64 解碼出來的) ---
FUGLE_API_KEY = "4f1b5371-6a2d-4253-8eb0-373e0858f210"

# 側邊欄：實戰參數校準
st.sidebar.title("🛠️ 實戰設定")
manual_k = st.sidebar.text_input("手動更換 API Key", value="", type="password")
discount = st.sidebar.slider("券商手續費折扣", 0.1, 1.0, 0.6)
# 如果手動欄位有填，就用手動的，否則用上面的預設值
FINAL_KEY = manual_k if manual_k else FUGLE_API_KEY

# --- 數據獲取函數 ---
def fetch_adr():
    """抓取前夜台積電 ADR 漲跌"""
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return ((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100
    except:
        return 0.0

def fetch_realtime(symbol):
    """抓取富果即時快照 (支援自動校正格式)"""
    if not FINAL_KEY: return None
    # 嘗試兩種常見的 API 路徑格式
    for sym in [symbol, f"{symbol}.TW"]:
        url = f"https://api.fugle.tw/marketdata/v1.0/stock/snapshot/{sym}"
        headers = {"X-API-KEY": FINAL_KEY}
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                return res.json()
        except:
            continue
    return {"error": 404}

# --- iPhone 主介面 ---
st.title("🚀 台股 AI 決策系統")

# 1. 前夜美股連動
adr_pct = fetch_adr()
st.info(f"🌐 前夜台積電 ADR 連動：{adr_pct:+.2f}%")

# 2. 標的選取
stocks = {"2449": "京元電子", "2330": "台積電", "2317": "鴻海", "2303": "聯電", "3711": "日月光"}
target = st.selectbox("監控標的", list(stocks.keys()), format_func=lambda x: f"{x} {stocks[x]}")

# 3. 執行即時分析
with st.spinner("連線數據庫中..."):
    data = fetch_realtime(target)

if data and "error" not in data:
    p = data.get('lastPrice', 0)
    st.divider()
    c1, c2 = st.columns(2)
    c1.metric("即時價", f"{p}", f"{data.get('changePercent')}%")
    c2.metric("總量", f"{data.get('totalVolume'):,}")

    # 4. 決策模型 (6折成本計算)
    # 損平比率 = (買手續費率 + 賣手續費率 + 交易稅率 0.15%)
    # 公式：價格 * (1 + 0.001425 * 0.6 * 2 + 0.0015)
    be = p * (1 + (0.001425 * discount * 2 + 0.0015))
    tick = 0.5 if p >= 100 else 0.1
    
    st.success(f"🤖 AI 建議：當沖損平點 {be:.2f}")
    
    # 點位提示
    t1, t2, t3 = st.columns(3)
    t1.error(f"停損\n{p - tick*3:.1f}")
    t2.warning(f"進場\n{p - tick:.1f}")
    t3.success(f"停利\n{p + tick*4:.1f}")

    if st.button("🔄 手動更新報價"):
        st.rerun()
else:
    st.error("⚠️ 數據讀取失敗。請檢查 API Key 權限或網路。")
    if data and "error" in data:
        st.write(f"錯誤代碼: {data['error']}")

st.caption(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")
