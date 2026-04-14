import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime

# --- 頁面初始配置 (iPhone 優化) ---
st.set_page_config(page_title="台股 AI 實戰", layout="centered", initial_sidebar_state="collapsed")

# --- 核心邏輯：台股跳檔級距計算 ---
def get_tick_size(price):
    if price < 10: return 0.01
    elif price < 50: return 0.05
    elif price < 100: return 0.1
    elif price < 500: return 0.5
    elif price < 1000: return 1.0
    else: return 5.0

# --- 智慧全域搜尋引擎 (模糊查詢) ---
def fetch_search_results(query):
    """連線 Yahoo API 進行全台股模糊搜尋"""
    query = query.strip()
    if not query: return []
    
    # 若是純數字代號
    if query.isdigit() and len(query) >= 4:
        return [{"label": f"代號查詢: {query}", "symbol": f"{query}.TW"}]

    results = []
    try:
        # 使用 Yahoo 搜尋 API，指定台灣區域與繁體中文
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&lang=zh-Hant-TW&region=TW&quotesCount=20"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = requests.get(url, headers=headers, timeout=5)
        
        if res.status_code == 200:
            data = res.json()
            for quote in data.get('quotes', []):
                symbol = quote.get('symbol', '')
                # 只保留台股標的
                if symbol.endswith(".TW") or symbol.endswith(".TWO"):
                    name = quote.get('shortname') or quote.get('longname') or symbol
                    results.append({"label": f"{name} ({symbol.split('.')[0]})", "symbol": symbol})
    except:
        pass
    return results

# --- 數據抓取引擎 ---
@st.cache_data(ttl=300)
def fetch_adr_info():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        if len(tsm) >= 2:
            change = ((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100
            return round(change, 2)
        return 0.0
    except:
        return 0.0

def fetch_stock_data(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period="5d")
        if df.empty: return None
        
        info = {}
        try: info = ticker.info
        except: pass

        return {
            "symbol": ticker_symbol,
            "name": info.get('shortName') or ticker_symbol.split('.')[0],
            "price": round(df['Close'].iloc[-1], 2),
            "open": round(df['Open'].iloc[-1], 2),
            "high": round(df['High'].iloc[-1], 2),
            "low": round(df['Low'].iloc[-1], 2),
            "prev_close": df['Close'].iloc[-2],
            "vol": int(df['Volume'].iloc[-1] / 1000),
            "industry": info.get('industry', '台股標的')
        }
    except:
        return None

# --- AI 評分模型 ---
def get_ai_score(data, adr_pct):
    score = 60
    score += (adr_pct * 4)
    if data['price'] > data['open']: score += 10
    change = ((data['price'] - data['prev_close']) / data['prev_close']) * 100
    score += (change * 2.5)
    day_range = data['high'] - data['low']
    if day_range > 0:
        pos = (data['price'] - data['low']) / day_range
        score += (pos * 12)
    score = min(max(score, 0), 100)
    
    if score >= 80: return score, "⭐⭐⭐⭐⭐ (極強)", "多頭動能充沛，適合進攻"
    elif score >= 65: return score, "⭐⭐⭐⭐ (偏多)", "趨勢樂觀，建議支撐位佈局"
    elif score >= 50: return score, "⭐⭐⭐ (中性)", "處於震盪區，不宜過度追高"
    else: return score, "⭐⭐ (弱勢)", "動能匱乏，注意回檔風險"

# --- 主介面 ---

st.markdown("<h3 style='text-align: center; font-size: 20px; color: #f0f2f6;'>🚀 台股 AI 全方位實戰系統</h3>", unsafe_allow_html=True)

# 1. ADR 指標 (頂部緊湊)
adr_val = fetch_adr_info()
st.markdown(f"""
<div style="background-color:#1e2329; padding:5px; border-radius:8px; border-left: 5px solid {'#3fb950' if adr_val > 0 else '#f85149'}; margin-bottom: 10px; text-align:center;">
    <span style="color:#848e9c; font-size:12px;">美股連動 (TSM ADR)：</span>
    <b style="color:{'#3fb950' if adr_val > 0 else '#f85149'}; font-size:14px;">{adr_val:+.2f}%</b>
</div>
""", unsafe_allow_html=True)

# 2. 智慧搜尋與選單 (核心優化區)
st.write("🔍 **智慧搜尋與選單**")
search_key = st.text_input("輸入公司名稱或代號 (如: 京元電, 長榮, 2330)", placeholder="請輸入關鍵字...", label_visibility="collapsed")

# 預設的重要標的
important_defaults = [
    {"label": "2449 京元電子", "symbol": "2449.TW"},
    {"label": "2330 台積電", "symbol": "2330.TW"},
    {"label": "2317 鴻海", "symbol": "2317.TW"},
    {"label": "2603 長榮", "symbol": "2603.TW"},
    {"label": "2881 富邦金", "symbol": "2881.TW"},
    {"label": "2382 廣達", "symbol": "2382.TW"},
    {"label": "2618 長榮航", "symbol": "2618.TW"}
]

# 如果有搜尋字詞，抓取全域結果；否則顯示預設清單
if search_key:
    with st.spinner("搜尋中..."):
        options = fetch_search_results(search_key)
    if not options:
        st.warning(f"查無「{search_key}」相關台股，請更換關鍵字。")
        st.stop()
    help_text = "🔎 搜尋結果"
else:
    options = important_defaults
    help_text = "📌 重要預設標的"

selected_stock = st.selectbox(help_text, options=options, format_func=lambda x: x["label"])

# 3. 執行分析
if selected_stock:
    with st.spinner("AI 數據同步中..."):
        data = fetch_stock_data(selected_stock["symbol"])
    
    if data:
        # 計算參數
        discount = st.sidebar.slider("券商折扣", 0.1, 1.0, 0.6)
        p = data['price']
        tick = get_tick_size(p)
        be_price = p * (1 + (0.001425 * discount * 2) + 0.0015)
        score, stars, note = get_ai_score(data, adr_val)

        # 顯示標題
        st.markdown(f"#### 📊 {data['name']} <small style='font-size:12px; color:#888;'>({data['symbol']})</small>", unsafe_allow_html=True)
        
        # AI 評分卡
        st.markdown(f"""
        <div style="background-color:#161b22; padding:10px; border-radius:10px; border:1px solid #58a6ff; margin-bottom:12px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="color:#8b949e; font-size:12px;">AI 實戰評分</span>
                <b style="color:#58a6ff; font-size:18px;">{score:.0f} / 100</b>
            </div>
            <div style="font-size:14px; color:#f0883e; margin:4px 0;">{stars}</div>
            <div style="color:#d1d5da; font-size:12px;">💡 建議：{note}</div>
        </div>
        """, unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        c1.metric("成交價", f"{p}", f"{((p-data['prev_close'])/data['prev_close'])*100:.2f}%")
        c2.metric("高/低", f"{data['high']}/{data['low']}")
        c3.metric("跳檔", f"{tick}")

        st.divider()

        # 4. 實戰建議
        st.write("🤖 **AI 進出場參考**")
        r1, r2 = st.columns(2)
        with r1:
            rec_buy = p - tick if adr_val > 0 else data['open']
            st.markdown(f"""
            <div style="background-color:#1c2128; padding:10px; border-radius:8px; border:1px solid #3fb950;">
                <p style="color:#8b949e; margin:0; font-size:12px;">AI 推薦買進價</p>
                <h2 style="color:#3fb950; margin:2px 0; font-size:20px;">{rec_buy:.2f}</h2>
            </div>
            """, unsafe_allow_html=True)
        with r2:
            st.markdown(f"""
            <div style="background-color:#1c2128; padding:10px; border-radius:8px; border:1px solid #f85149;">
                <p style="color:#8b949e; margin:0; font-size:12px;">當沖損平點</p>
                <h2 style="color:#f85149; margin:2px 0; font-size:20px;">{be_price:.2f}</h2>
            </div>
            """, unsafe_allow_html=True)

        st.write("")
        st.write("🎯 **操作導航：**")
        t1, t2, t3, t4 = st.columns(4)
        t1.error(f"停損\n{p - tick*4:.1f}")
        t2.warning(f"保守\n{p - tick*1:.1f}")
        t3.success(f"目標\n{p + tick*3:.1f}")
        t4.info(f"強勢\n{p + tick*6:.1f}")

        if st.button("🔄 刷新行情"):
            st.rerun()
    else:
        st.error("❌ 數據讀取失敗。")

st.caption(f"數據源：Yahoo Finance | 最後更新：{datetime.now().strftime('%H:%M:%S')}")

