import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime

# --- 基本頁面配置 ---
st.set_page_config(page_title="台股 AI 實戰系統", layout="centered")

# --- 金鑰設定 (這是您最新提供的 4f1b 序號) ---
FUGLE_KEY = "4f1b5371-6a2d-4253-8eb0-373e0858f210"

# --- 側邊欄設定 ---
st.sidebar.title("🛠️ 交易參數設定")
discount = st.sidebar.slider("券商手續費折扣", 0.1, 1.0, 0.6)
st.sidebar.markdown("---")
st.sidebar.info("系統會優先嘗試 Fugle 實時數據，若失敗將自動切換至 Yahoo 延遲數據。")

# --- 數據獲取引擎 ---

def get_yahoo_data(symbol):
    """Yahoo Finance 備援引擎 (免金鑰)"""
    try:
        ticker = yf.Ticker(f"{symbol}.TW")
        df = ticker.history(period="1d")
        if not df.empty:
            last_p = df['Close'].iloc[-1]
            prev_p = ticker.info.get('regularMarketPreviousClose', last_p)
            change = ((last_p - prev_p) / prev_p) * 100
            return {
                "source": "Yahoo (延遲15分)",
                "price": round(last_p, 2),
                "change": round(change, 2),
                "vol": int(df['Volume'].iloc[-1])
            }
    except:
        return None

def get_fugle_data(symbol):
    """富果實時引擎 (需金鑰)"""
    # 嘗試兩種常見的 API URL 格式
    for url in [
        f"https://api.fugle.tw/marketdata/v1.0/stock/snapshot/{symbol}",
        f"https://api.fugle.tw/marketdata/v1.0/stock/snapshot/{symbol}.TW"
    ]:
        try:
            res = requests.get(url, headers={"X-API-KEY": FUGLE_KEY}, timeout=5)
            if res.status_code == 200:
                d = res.json()
                return {
                    "source": "Fugle (實時數據)",
                    "price": d.get('lastPrice'),
                    "change": d.get('changePercent'),
                    "vol": d.get('totalVolume')
                }
        except:
            continue
    return None

# --- App 主介面 ---
st.title("🚀 台股 AI 全方位決策")

# 1. 標的選取
stocks = {"2449": "京元電子", "2330": "台積電", "2317": "鴻海", "2303": "聯電", "3711": "日月光"}
sid = st.selectbox("監控標的", list(stocks.keys()), format_func=lambda x: f"{x} {stocks[x]}")

# 2. 數據抓取邏輯 (優先 Fugle, 備援 Yahoo)
with st.spinner("數據同步中..."):
    final_data = get_fugle_data(sid)
    if not final_data:
        final_data = get_yahoo_data(sid)

# 3. 介面呈現
if final_data:
    p = final_data['price']
    
    # 頂部狀態列
    st.markdown(f"📡 數據源：`{final_data['source']}`")
    
    col1, col2 = st.columns(2)
    col1.metric("目前成交價", f"{p}", f"{final_data['change']}%")
    col2.metric("總量", f"{final_data['vol']:,}")

    st.divider()

    # 4. AI 決策模型 (6 折成本計算)
    # 損平公式：價格 * (1 + 買賣手續費率*折扣 + 當沖稅 0.15%)
    # 註：0.001425*2*discount + 0.0015
    cost_rate = (0.001425 * discount * 2) + 0.0015
    be_price = p * (1 + cost_rate)
    tick = 0.5 if p >= 100 else 0.1
    
    st.success(f"🤖 AI 決策建議：當沖損平點 **{be_price:.2f}**")
    
    # 5. 操作點位參考
    t1, t2, t3 = st.columns(3)
    t1.error(f"停損\n{p - tick*3:.1f}")
    t2.warning(f"進場\n{p - tick:.1f}")
    t3.success(f"停利\n{p + tick*4:.1f}")

    if st.button("🔄 手動刷新行情"):
        st.rerun()

    # 如果使用的是 Yahoo 備援，底部顯示警告
    if "Yahoo" in final_data['source']:
        st.warning("⚠️ 富果 API 目前無法連線 (可能是 Key 權限未開通)，暫時使用 Yahoo 延遲數據。")

else:
    st.error("❌ 所有數據源連線失敗，請檢查網路設定。")

st.caption(f"系統時間：{datetime.now().strftime('%H:%M:%S')}")

