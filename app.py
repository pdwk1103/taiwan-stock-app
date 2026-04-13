import streamlit as st
import pandas as pd
import requests
import base64
import yfinance as yf
from datetime import datetime
import re

# --- 基本設定 (iPhone 優化) ---
st.set_page_config(page_title="台股 AI 實戰", layout="centered")

# --- API KEY 處理 (更新為您最新的 4f1b 序號) ---
# 這是您提供的最新 Base64 金鑰字串
RAW_B64 = "NGYxYjUzNzEtNmEyZC00MjUzLThlYjAtMzczZTA4NThmMjEwIDk1ZWQ4MzY2LWY3N2ItNDM0Yi1iZDM5LWMyNzBjYzRjMjhhOQ=="

def get_final_key():
    try:
        # 解碼 Base64
        decoded = base64.b64decode(RAW_B64).decode('utf-8')
        # 使用正規表達式抓取第一組 UUID (符合 8-4-4-4-12 格式)
        match = re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', decoded)
        if match:
            return match.group(0)
        return decoded.split(' ')[0].strip()
    except:
        return ""

# 側邊欄設定
st.sidebar.title("🛠️ 實戰設定")
manual_k = st.sidebar.text_input("手動貼上 API Key (若讀取失敗)", value="", type="password")
discount = st.sidebar.slider("券商手續費折扣", 0.1, 1.0, 0.6)
FINAL_KEY = manual_k if manual_k else get_final_key()

# --- 數據抓取 ---
def fetch_adr_pct():
    """抓取美股台積電 ADR 漲跌幅"""
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return ((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100
    except:
        return 0.0

def fetch_fugle_data(symbol):
    """抓取富果實時數據 (解決 404 問題)"""
    if not FINAL_KEY: return {"error": "NoKey"}
    
    # 自動嘗試兩種常見的格式路徑
    for s in [symbol, f"{symbol}.TW"]:
        url = f"https://api.fugle.tw/marketdata/v1.0/stock/snapshot/{s}"
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

# 1. 前夜美股影響
adr_val = fetch_adr_pct()
st.info(f"🌐 前夜台積電 ADR 連動：{adr_val:+.2f}%")

# 2. 監控標的選擇
stocks = {"2449": "京元電子", "2330": "台積電", "2317": "鴻海", "2303": "聯電", "3711": "日月光"}
sid = st.selectbox("選取實戰標的", list(stocks.keys()), format_func=lambda x: f"{x} {stocks[x]}")

# 3. 分析與顯示
with st.spinner("連線數據庫中..."):
    data = fetch_fugle_data(sid)

if data and "error" not in data:
    price = data.get('lastPrice', 0)
    chg = data.get('changePercent', 0)
    vol = data.get('totalVolume', 0)

    st.divider()
    
    # 價格看板
    col1, col2 = st.columns(2)
    col1.metric("即時成交價", f"{price}", f"{chg}%")
    col2.metric("總量", f"{vol:,}")

    # 4. 決策模型 (6 折計算)
    # 損平率 = (買手續費 + 賣手續費 + 交易稅 0.15%)
    # 損平點 = 價格 * (1 + 0.001425 * 折扣 * 2 + 0.0015)
    be_p = price * (1 + (0.001425 * discount * 2 + 0.0015))
    tick = 0.5 if price >= 100 else 0.1
    
    st.success(f"🤖 AI 建議：當沖損平點 {be_p:.2f}")
    
    # 實戰點位建議
    t1, t2, t3 = st.columns(3)
    t1.error(f"停損\n{price - tick*3:.1f}")
    t2.warning(f"進場\n{price - tick:.1f}")
    t3.success(f"停利\n{price + tick*4:.1f}")

    if st.button("🔄 更新數據"):
        st.rerun()

else:
    st.error("⚠️ 連線失敗。")
    with st.expander("點此展開查看偵錯資訊"):
        st.write("目前偵測 Key (前8碼):", FINAL_KEY[:8] if FINAL_KEY else "無")
        st.write("錯誤代碼:", data.get('error') if data else "無法連線")
        st.markdown("""
        **排錯指南：**
        1. 點擊手機左上角 `>` 展開選單。
        2. 將富果金鑰視窗中「複製」到的原始字串貼到「手動輸入」欄位。
        3. 確認富果官網顯示「基本用戶 生效中」。
        """)

st.caption(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")
