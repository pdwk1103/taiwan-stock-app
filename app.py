import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime

st.set_page_config(page_title="系統連線診斷", layout="centered")

st.title("🔍 系統連線與數據診斷")

# 1. 環境診斷
st.subheader("1. 環境狀態")
st.write(f"目前時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# 2. Yahoo Finance 壓力測試
st.subheader("2. Yahoo 數據測試 (免金鑰)")
target_stock = "2449.TW" # 京元電子

try:
    with st.spinner(f"嘗試抓取 {target_stock} ..."):
        ticker = yf.Ticker(target_stock)
        # 獲取最近一天的數據
        df = ticker.history(period="1d")
        
        if not df.empty:
            curr_price = df['Close'].iloc[-1]
            st.success(f"✅ Yahoo 連線成功！{target_stock} 目前價格: {curr_price}")
            
            # 顯示簡單計算
            st.metric("京元電子價格", f"{curr_price}")
            st.info("如果看到這個，代表你的 App 基礎環境是正常的！")
        else:
            st.error("❌ Yahoo 回傳空數據。")
            st.write("這通常是 Yahoo 暫時封鎖了 Cloud 伺服器的請求。")
            
except Exception as e:
    st.error(f"❌ Yahoo 連線崩潰: {str(e)}")
    st.write("這代表 yfinance 程式庫在目前環境下無法運行。")

# 3. 富果連線壓力測試 (用你最新的金鑰)
st.subheader("3. 富果 API 測試 (需金鑰)")
FUGLE_KEY = "4f1b5371-6a2d-4253-8eb0-373e0858f210"

if st.button("點擊執行富果連線測試"):
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/snapshot/2449"
    headers = {"X-API-KEY": FUGLE_KEY}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            st.success("✅ 富果 API 連線成功！")
            st.json(res.json())
        else:
            st.error(f"❌ 富果連線失敗代碼: {res.status_code}")
            st.write(f"伺服器訊息: {res.text}")
    except Exception as e:
        st.error(f"❌ 富果請求崩潰: {str(e)}")

st.divider()
st.caption("診斷完成後，請將看到的錯誤訊息截圖告訴我。")

