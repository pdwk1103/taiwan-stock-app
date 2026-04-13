import streamlit as st
import pandas as pd
import requests
import base64
import yfinance as yf
from datetime import datetime

# --- 基本設定 ---
st.set_page_config(page_title="台股實戰 AI 決策", layout="centered")

# --- API KEY 處理 (更新為您最新的 8511 序號) ---
RAW_B64_KEY = "ODUxMTgzOTMtZjJlMi00NTRhLTgxZDItMzY4MmQzZDA4NTAzZDA0YzRkZTU3LTNmNDVjM2JiYjLWNlZTIzZTI1ZTI1ZDA="

def get_latest_key():
    try:
        # 解碼您最新的 Base64 金鑰
        decoded = base64.b64decode(RAW_B64_KEY).decode('utf-8')
        # 取出第一段 UUID (85118393-f2e2-454a-81d2-3682d3d08503)
        return decoded.split(' ')[0].split('\n')[0].strip()
    except:
        return ""

# 側邊欄：手動輸入備案
st.sidebar.title("🛠️ 實戰設定")
manual_key = st.sidebar.text_input("手動輸入 API Key", value="", type="password")
discount = st.sidebar.slider("券商折扣 (6折請設 0.6)", 0.1, 1.0, 0.6)
FINAL_KEY = manual_key if manual_key else get_latest_key()

# --- 數據抓取 ---
def fetch_adr():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return ((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100
    except:
        return 0.0

def fetch_fugle_data(symbol):
    """獲取富果實時快照，增加自動修正邏輯以解決 404 問題"""
    if not FINAL_KEY: return None
    
    # 嘗試兩種常見的格式：純數字 與 .TW
    for sym in [symbol, f"{symbol}.TW"]:
        url = f"https://api.fugle.tw/marketdata/v1.0/stock/snapshot/{sym}"
        headers = {"X-API-KEY": FINAL_KEY}
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                return res.json()
        except:
            continue
    
    # 如果都失敗，回傳最後一次的錯誤訊息
    return {"error": 404, "msg": "找不到標的或金鑰權限未開通"}

# --- 主程式介面 ---
st.title("📈 台股實戰監控")

# 1. 前夜美股連動
adr_pct = fetch_adr()
st.info(f"🌐 前夜台積電 ADR 連動：{adr_pct:+.2f}%")

# 2. 標的選擇
stocks = {"2449": "京元電子", "2330": "台積電", "2317": "鴻海", "2303": "聯電", "3711": "日月光"}
target = st.selectbox("監控標的", list(stocks.keys()), format_func=lambda x: f"{x} {stocks[x]}")

# 3. 分析與顯示
with st.spinner("連線數據庫中..."):
    data = fetch_fugle_data(target)

if data and "error" not in data:
    price = data.get('lastPrice', 0)
    chg = data.get('changePercent', 0)
    vol = data.get('totalVolume', 0)

    st.divider()
    c1, c2 = st.columns(2)
    c1.metric("成交價", f"{price}", f"{chg}%")
    c2.metric("總成交量", f"{vol:,}")

    # 4. 決策模型 (6 折成本計算)
    cost_rate = (0.001425 * discount * 2) + 0.0015
    be_price = price * (1 + cost_rate)
    tick = 0.5 if price >= 100 else 0.1

    st.success(f"🤖 AI 建議：當沖損平點 {be_price:.2f}")
    
    t1, t2, t3 = st.columns(3)
    t1.error(f"停損\n{price - tick*3:.1f}")
    t2.warning(f"進場\n{price - tick:.1f}")
    t3.success(f"停利\n{price + tick*4:.1f}")

    if st.button("🔄 更新即時報價"):
        st.rerun()

else:
    st.error("⚠️ 連線失敗")
    with st.expander("點此查看偵錯資訊"):
        st.write("目前使用的 Key (前10碼):", FINAL_KEY[:10] if FINAL_KEY else "無")
        st.write("錯誤原因:", data.get('msg') if data else "無法連線至富果伺服器")

st.caption(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")

