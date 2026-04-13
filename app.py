import streamlit as st
import pandas as pd
import requests
import base64
import yfinance as yf
from datetime import datetime

# --- 基本頁面配置 ---
st.set_page_config(page_title="台股 AI 實戰決策", layout="centered")

# --- API KEY 處理邏輯 (針對您的最新金鑰優化) ---
# 這是您最新申請的 Base64 金鑰字串
RAW_B64 = "ODUxMTgzOTMtZjJlMi00NTRhLTgxZDItMzY4MmQzZDA4NTAzZDA0YzRkZTU3LTNmNDVjM2JiYjLWNlZTIzZTI1ZTI1ZDA=="

def decode_key(b64_str):
    try:
        # 去除可能存在的空白字元並解碼
        decoded = base64.b64decode(b64_str.strip()).decode('utf-8')
        # 針對您的金鑰格式進行多段嘗試 (UUID 有時包含空格或後綴)
        return decoded.split(' ')[0].strip()
    except Exception as e:
        return ""

# 側邊欄：實戰參數設定
st.sidebar.title("🛠️ 實戰設定")
manual_key = st.sidebar.text_input("手動貼上 API Key (若讀取失敗)", value="", type="password")
discount = st.sidebar.slider("券商折扣 (6折請設為 0.6)", 0.1, 1.0, 0.6)

# 確定最後使用的 API Key
FUGLE_API_KEY = manual_key if manual_key else decode_key(RAW_B64)

# --- 數據獲取 ---
def get_adr_info():
    """獲取台積電 ADR 漲跌幅"""
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return ((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100
    except:
        return 0.0

def get_realtime_data(symbol):
    """串接富果快照 API"""
    if not FUGLE_API_KEY:
        return {"error": "NoKey", "msg": "金鑰解碼失敗"}
    
    # 嘗試標準 v1.0 快照路徑
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/snapshot/{symbol}"
    headers = {"X-API-KEY": FUGLE_API_KEY}
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
        return {"error": res.status_code, "msg": res.text}
    except Exception as e:
        return {"error": "Timeout", "msg": str(e)}

# --- 主程式介面 ---
st.title("🚀 台股 AI 實戰系統")

# 1. 美股環境資訊
adr_pct = get_adr_info()
st.info(f"🌐 前夜美股連動：TSM ADR {adr_pct:+.2f}%")

# 2. 監控標的選擇
stocks = {"2449": "京元電子", "2330": "台積電", "2317": "鴻海", "2303": "聯電", "3711": "日月光"}
target = st.selectbox("選取實戰標的", list(stocks.keys()), format_func=lambda x: f"{x} {stocks[x]}")

# 3. 獲取並顯示數據
with st.spinner("連線富果數據庫中..."):
    data = get_realtime_data(target)

if data and "error" not in data:
    # 成功獲取數據
    price = data.get('lastPrice', 0)
    change = data.get('changePercent', 0)
    vol = data.get('totalVolume', 0)

    st.divider()
    
    # 行情儀表板
    c1, c2 = st.columns(2)
    c1.metric("成交價", f"{price}", f"{change}%")
    c2.metric("總量", f"{vol:,}")

    # AI 決策計算 (6 折成本)
    cost_factor = (0.001425 * discount * 2) + 0.0015
    be_price = price * (1 + cost_factor)
    tick = 0.5 if price >= 100 else 0.1

    # 決策結果顯示
    st.success(f"🤖 AI 決策：{'偏多現沖' if adr_pct > 0 else '保守觀望'}")
    
    # 點位計算卡片
    st.markdown(f"""
    <div style="background-color:#161b22; padding:15px; border-radius:15px; border:1px solid #30363d;">
        <p style="margin:0; color:#8b949e;">當沖損平點：<b style="color:#3fb950; font-size:20px;">{be_price:.2f}</b></p>
        <p style="font-size:12px; color:#58a6ff;">(價格漲過此位才算獲利，已計 6 折手續費)</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 操作區間
    st.write("")
    t1, t2, t3 = st.columns(3)
    t1.error(f"停損\n{price - tick*3:.1f}")
    t2.warning(f"進場\n{price - tick:.1f}")
    t3.success(f"停利\n{price + tick*4:.1f}")

    if st.button("🔄 更新即時報價"):
        st.rerun()

else:
    # 錯誤處理區
    st.error(f"⚠️ 數據讀取失敗 (錯誤碼: {data.get('error', 'Unknown')})")
    
    with st.expander("點此查看偵錯資訊"):
        st.write("目前使用的 API Key (前5碼):", FUGLE_API_KEY[:5] if FUGLE_API_KEY else "無")
        st.write("伺服器回應訊息:", data.get('msg', '無'))
        st.markdown("""
        **常見解決方案：**
        1. **404 錯誤**：代表金鑰或標的格式有誤。請展開左側選單，將金鑰貼到「手動輸入」欄位。
        2. **401 錯誤**：代表金鑰權限不符。請檢查富果開發者中心是否已開通「基本用戶」權限。
        3. **新金鑰生效**：新申請的金鑰有時需要 5-10 分鐘才會生效。
        """)

st.caption(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")
