import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# --- 頁面配置 (iPhone 優化) ---
st.set_page_config(page_title="台股 AI 實戰早報", layout="centered", initial_sidebar_state="collapsed")

# --- 核心跳檔級距 (Tick Size) ---
def get_tick_size(price):
    if price < 10: return 0.01
    elif price < 50: return 0.05
    elif price < 100: return 0.1
    elif price < 500: return 0.5
    elif price < 1000: return 1.0
    else: return 5.0

# --- 市場環境分析 (ADR) ---
@st.cache_data(ttl=3600)
def get_market_sentiment():
    try:
        # 抓取台積電 ADR 與 Nvidia 作為科技股動能指標
        tsm = yf.Ticker("TSM").history(period="2d")
        nvda = yf.Ticker("NVDA").history(period="2d")
        
        tsm_change = ((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100
        nvda_change = ((nvda['Close'].iloc[-1] - nvda['Close'].iloc[-2]) / nvda['Close'].iloc[-2]) * 100
        
        return round(tsm_change, 2), round(nvda_change, 2)
    except:
        return 0.0, 0.0

# --- AI 個股分析與篩選引擎 ---
def analyze_stock_logic(symbol, adr_trend):
    try:
        ticker = yf.Ticker(f"{symbol}.TW")
        df = ticker.history(period="10d")
        if df.empty or len(df) < 5: return None
        
        # 基礎指標計算
        curr_price = round(df['Close'].iloc[-1], 2)
        ma5 = df['Close'].rolling(window=5).mean().iloc[-1]
        prev_close = df['Close'].iloc[-2]
        day_change = ((curr_price - prev_close) / prev_close) * 100
        
        # 趨勢評分 (1-100)
        score = 50
        score += (adr_trend * 3) # 美股連動
        if curr_price > ma5: score += 15 # 站上均線
        if day_change > 0: score += 10 # 當日強勢
        
        # 推薦價格計算 (根據跳檔級距)
        tick = get_tick_size(curr_price)
        # 建議進場價：回測 5MA 或目前價格下跳 1 檔
        rec_buy = max(round(ma5, 2), curr_price - tick)
        target = curr_price + (tick * 8) # 預期獲利空間
        stop_loss = curr_price - (tick * 5) # 嚴格停損
        
        return {
            "symbol": symbol,
            "name": ticker.info.get('shortName', symbol),
            "price": curr_price,
            "change": round(day_change, 2),
            "score": min(score, 99),
            "rec_buy": rec_buy,
            "target": target,
            "stop": stop_loss,
            "reason": "強勢站穩均線" if curr_price > ma5 else "低檔縮量轉強"
        }
    except:
        return None

# --- 主介面 ---

st.markdown("<h2 style='text-align: center; font-size: 24px; margin-bottom: 5px;'>🚀 台股 AI 每日自動推薦</h2>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888; font-size: 14px;'>系統自動分析前夜美股連動與個股趨勢</p>", unsafe_allow_html=True)

# 1. 頂部環境看板
tsm_adr, nvda_adr = get_market_sentiment()
c1, c2 = st.columns(2)
with c1:
    st.markdown(f"""
    <div style="background-color:#1e2329; padding:10px; border-radius:10px; border-left: 5px solid {'#3fb950' if tsm_adr > 0 else '#f85149'};">
        <span style="color:#848e9c; font-size:12px;">TSM ADR (台積電)</span><br>
        <b style="color:{'#3fb950' if tsm_adr > 0 else '#f85149'}; font-size:18px;">{tsm_adr:+.2f}%</b>
    </div>
    """, unsafe_allow_html=True)
with c2:
    st.markdown(f"""
    <div style="background-color:#1e2329; padding:10px; border-radius:10px; border-left: 5px solid {'#3fb950' if nvda_adr > 0 else '#f85149'};">
        <span style="color:#848e9c; font-size:12px;">NVDA (輝達)</span><br>
        <b style="color:{'#3fb950' if nvda_adr > 0 else '#f85149'}; font-size:18px;">{nvda_adr:+.2f}%</b>
    </div>
    """, unsafe_allow_html=True)

st.write("")

# 2. AI 掃描與推薦清單
st.markdown("### 🎯 今日 AI 推薦操作名單")

# 定義觀察池 (涵蓋各產業級距標的)
watch_pool = [
    "2449", "2330", "2317", "2603", "2618", "2382", "2454", "3008", "2303", "2881", "2609", "3231", "2376", "6669"
]

recommendations = []
progress_bar = st.progress(0)

for i, sid in enumerate(watch_pool):
    res = analyze_stock_logic(sid, tsm_adr)
    if res and res['score'] >= 60: # 只取評分 60 以上的標的
        recommendations.append(res)
    progress_bar.progress((i + 1) / len(watch_pool))

# 排序：評分越高排越前面
recommendations = sorted(recommendations, key=lambda x: x['score'], reverse=True)

if recommendations:
    for item in recommendations:
        with st.container():
            st.markdown(f"""
            <div style="background-color:#161b22; padding:15px; border-radius:12px; border:1px solid #30363d; margin-bottom:15px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <b style="font-size:18px; color:#f0f6fc;">{item['name']} ({item['symbol']})</b>
                    <span style="background-color:#238636; color:white; padding:2px 8px; border-radius:6px; font-size:12px;">AI 評分: {item['score']}</span>
                </div>
                <div style="margin:10px 0; color:#8b949e; font-size:14px;">策略：{item['reason']}</div>
                <div style="display:flex; justify-content:space-between; margin-top:10px;">
                    <div style="text-align:center;">
                        <small style="color:#8b949e;">建議進場</small><br>
                        <b style="color:#3fb950; font-size:20px;">{item['rec_buy']}</b>
                    </div>
                    <div style="text-align:center;">
                        <small style="color:#8b949e;">目標獲利</small><br>
                        <b style="color:#58a6ff; font-size:20px;">{item['target']}</b>
                    </div>
                    <div style="text-align:center;">
                        <small style="color:#8b949e;">停損防線</small><br>
                        <b style="color:#f85149; font-size:20px;">{item['stop']}</b>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
else:
    st.info("💡 目前市場波動較大或動能不足，AI 建議觀望暫不推薦標的。")

st.divider()

# 3. 交易參數與說明
st.sidebar.title("🛠️ 交易參數設定")
discount = st.sidebar.slider("券商手續費折扣", 0.1, 1.0, 0.6)

st.markdown("""
<div style="background-color:#0d1117; padding:10px; border-radius:8px; font-size:12px; color:#8b949e;">
    <b>操作提醒：</b><br>
    1. 本系統僅供參考，實際交易請務必搭配盤中即時大單動向。<br>
    2. 建議進場價考慮了台股跳檔級距 (Tick)，可作為掛單參考。<br>
    3. 數據來源：Yahoo Finance (延遲 15 分鐘)。
</div>
""", unsafe_allow_html=True)

if st.button("🔄 立即重新掃描市場"):
    st.rerun()

st.caption(f"最後更新：{datetime.now().strftime('%H:%M:%S')}")

