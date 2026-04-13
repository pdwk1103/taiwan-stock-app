
import streamlit as st
import requests
import base64
import yfinance as yf
from datetime import datetime

# --- 基本設定 ---
st.set_page_config(page_title="台股實戰 AI", layout="centered")

# --- API KEY 處理 ---
# 使用您截圖中顯示的最新 Base64 金鑰
RAW_KEY_B64 = "ODUxMTgzOTMtZjJlMi00NTRhLTgxZDItMzY4MmQzZDA4NTAzZDA0YzRkZTU3LTNmNDVjM2JiYjLWNlZTIzZTI1ZTI1ZDA=="

def get_clean_key():
    try:
        # 解碼 Base64
        decoded = base64.b64decode(RAW_KEY_B64).decode('utf-8')
        # 取第一段有效的 UUID (36位元)
        return decoded.split(' ')[0].split('\n')[0].strip()
    except:
        return ""

# 提供側邊欄設定 (手機版點選左上角箭頭展開)
st.sidebar.title("🛠️ 系統校準")
manual_key = st.sidebar.text_input("手動輸入金鑰 (若失敗)", value="", type="password")
discount = st.sidebar.slider("券商折扣 (6折)", 0.1, 1.0, 0.6)
FINAL_KEY = manual_key if manual_key else get_clean_key()

# --- 核心功能函數 ---
def fetch_adr():
    """抓取前夜台積電 ADR"""
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return ((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100
    except:
        return 0.0

def fetch_market_data(symbol):
    """串接富果實時快照 API"""
    if not FINAL_KEY: return None
    # 使用富果最新的 V1 快照路徑
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/snapshot/{symbol}"
    headers = {"X-API-KEY": FINAL_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
        return {"error": res.status_code, "msg": res.text}
    except Exception as e:
        return {"error": "Timeout", "msg": str(e)}

# --- iPhone App 介面展示 ---
st.title("📈 台股實戰監控")

# 1. 美股環境連動
adr_val = fetch_adr()
st.info(f"🌐 前夜台積電 ADR 連動：{adr_val:+.2f}%")

# 2. 標的選擇
stocks = {"2449": "京元電子", "2330": "台積電", "2317": "鴻海", "2303": "聯電", "3711": "日月光"}
target = st.selectbox("監控標的", list(stocks.keys()), format_func=lambda x: f"{x} {stocks[x]}")

# 3. 執行分析
with st.spinner("連線中..."):
    data = fetch_market_data(target)

if data and "error" not in data:
    # 成功獲取數據
    p = data.get('lastPrice', 0)
    c = data.get('changePercent', 0)
    v = data.get('totalVolume', 0)

    st.divider()
    col1, col2 = st.columns(2)
    col1.metric("即時成交價", f"{p}", f"{c}%")
    col2.metric("總量", f"{v:,}")

    # 4. 決策模型 (6 折計算)
    # 損平公式：價格 * (1 + (手續費率*2*折扣 + 交易稅率))
    be = p * (1 + (0.001425 * 2 * discount + 0.0015))
    tick = 0.5 if p >= 100 else 0.1

    st.success(f"🤖 AI 決策：當沖損平點 {be:.2f}")
    
    t1, t2, t3 = st.columns(3)
    t1.error(f"停損\n{p - tick*3:.1f}")
    t2.warning(f"進場\n{p - tick:.1f}")
    t3.success(f"停利\n{p + tick*4:.1f}")

    if st.button("🔄 更新即時報價"):
        st.rerun()
else:
    # 錯誤處理
    st.error(f"⚠️ 連線失敗 (代碼: {data.get('error') if data else 'None'})")
    with st.expander("查看故障診斷"):
        st.write("目前 Key 前段:", FINAL_KEY[:8] + "...")
        st.write("伺服器回應:", data.get('msg') if data else "無回應")
        st.markdown("""
        **排錯指南：**
        1. **404 錯誤**：通常是金鑰在 Base64 轉換中損毀。請展開左側選單手動貼上。
        2. **401 錯誤**：金鑰無效。請確認富果開發者中心顯示「基本用戶 生效中」。
        """)

st.caption(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")

