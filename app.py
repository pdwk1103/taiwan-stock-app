import streamlit as st
import pandas as pd
import requests
import base64
import yfinance as yf
from datetime import datetime

# --- 基本設定 ---
st.set_page_config(page_title="台股實戰系統")

# --- 萬用金鑰處理解碼器 ---
# 這是您截圖中最新申請的那串金鑰
RAW_B64 = "NGFhMmQ2MTktNTIwYy00ZGEzLTk5NjQtNDg2YWU4MGFjMDk0IDc1YzEzNjgwLWYxNGQtNDFjZS04ZTIwLTY0YWE0MDU4Y2FhYQ=="

def get_valid_key():
    try:
        # 解碼 Base64
        decoded = base64.b64decode(RAW_B64).decode('utf-8')
        # 取出第一段 36 位元的 UUID 格式
        import re
        keys = re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', decoded)
        return keys[0] if keys else decoded.split(' ')[0].strip()
    except:
        return ""

# 提供側邊欄讓您在 iPhone 上可以手動校正
st.sidebar.title("🛠️ 實戰校準")
user_input_key = st.sidebar.text_input("手動輸入 API Key (若讀取失敗)", value="", type="password")
FUGLE_KEY = user_input_key if user_input_key else get_valid_key()
discount = st.sidebar.slider("手續費折扣", 0.1, 1.0, 0.6)

# --- 數據獲取函數 ---
def fetch_adr():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return ((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100
    except:
        return 0.0

def fetch_realtime(symbol):
    if not FUGLE_KEY: return {"error": "NoKey"}
    # 富果 v1.0 快照 API 路徑
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/snapshot/{symbol}"
    headers = {"X-API-KEY": FUGLE_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
        else:
            return {"error": res.status_code, "msg": res.text}
    except:
        return {"error": "Timeout"}

# --- iPhone 主介面 ---
st.title("🚀 台股 AI 決策系統")

# 1. 前夜美股連動
adr_pct = fetch_adr()
st.info(f"🌐 前夜台積電 ADR 連動：{adr_pct:+.2f}%")

# 2. 標定選擇
stocks = {"2449": "京元電子", "2330": "台積電", "2317": "鴻海", "2303": "聯電"}
target = st.selectbox("選取監控標的", list(stocks.keys()), format_func=lambda x: f"{x} {stocks[x]}")

# 3. 分析區域
data = fetch_realtime(target)

if data and "error" not in data:
    price = data.get('lastPrice', 0)
    st.divider()
    c1, c2 = st.columns(2)
    c1.metric("成交價", f"{price}", f"{data.get('changePercent')}%")
    c2.metric("總量", f"{data.get('totalVolume'):,}")

    # 決策計算 (6 折)
    # 總成本率 = (手續費率 * 折扣 * 2) + 交易稅率
    be = price * (1 + (0.001425 * discount * 2 + 0.0015))
    tick = 0.5 if price >= 100 else 0.1
    
    st.success(f"🤖 AI 建議：當沖損平點 {be:.2f}")
    
    t1, t2, t3 = st.columns(3)
    t1.error(f"停損\n{price - tick*3:.1f}")
    t2.warning(f"進場\n{price - tick:.1f}")
    t3.success(f"停利\n{price + tick*4:.1f}")

    if st.button("🔄 更新數據"):
        st.rerun()
else:
    st.error(f"⚠️ 連線失敗 (錯誤碼: {data.get('error') if data else 'Unknown'})")
    with st.expander("點此查看偵錯建議"):
        st.write("目前使用的 Key (前10碼):", FUGLE_KEY[:10] if FUGLE_KEY else "無")
        st.write("錯誤詳情:", data.get('msg') if data else "無回應")
        st.markdown("""
        **解決方案：**
        1. 請展開左側選單，將富果視窗中「複製」的金鑰直接貼上。
        2. 確認富果開發者中心顯示「生效中」。
        """)

st.caption(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")
