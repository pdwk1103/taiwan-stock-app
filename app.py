import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime

# --- 頁面初始配置 ---
st.set_page_config(page_title="台股 AI 實戰決策", layout="centered", initial_sidebar_state="collapsed")

# --- 核心邏輯：台股跳檔級距計算 (Tick Size) ---
def get_tick_size(price):
    if price < 10: return 0.01
    elif price < 50: return 0.05
    elif price < 100: return 0.1
    elif price < 500: return 0.5
    elif price < 1000: return 1.0
    else: return 5.0

# --- 智慧搜尋引擎：將中文名稱轉為正確代號 ---
def search_ticker(query):
    """透過 Yahoo Finance Search API 找尋最匹配的台股代號"""
    query = query.strip()
    if not query: return None
    
    # 如果已經是數字，直接回傳
    if query.isdigit():
        return f"{query}.TW"
    
    # 如果包含 .TW 或 .TWO，直接回傳
    if ".TW" in query.upper():
        return query.upper()

    try:
        # 使用 Yahoo Finance 的搜尋建議 API
        search_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&lang=zh-Hant-TW&region=TW&quotesCount=10"
        # 模擬瀏覽器 Headers 避免被封鎖
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(search_url, headers=headers, timeout=5)
        
        if res.status_code == 200:
            data = res.json()
            # 遍歷搜尋結果，尋找帶有 .TW 或 .TWO 的標的
            for quote in data.get('quotes', []):
                symbol = quote.get('symbol', '')
                if ".TW" in symbol or ".TWO" in symbol:
                    return symbol
    except:
        pass
    return None

# --- 數據抓取引擎 ---
@st.cache_data(ttl=300)
def fetch_adr_status():
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
        # 抓取 5 天確保資料完整
        df = ticker.history(period="5d")
        if df.empty: return None
        
        # 獲取公司基本資訊
        info = {}
        try:
            info = ticker.info
        except:
            pass

        name = info.get('shortName', ticker_symbol.replace('.TW', '').replace('.TWO', ''))
        industry = info.get('industry', '多元產業')
        
        return {
            "symbol": ticker_symbol,
            "name": name,
            "price": round(df['Close'].iloc[-1], 2),
            "open": round(df['Open'].iloc[-1], 2),
            "high": round(df['High'].iloc[-1], 2),
            "low": round(df['Low'].iloc[-1], 2),
            "prev_close": df['Close'].iloc[-2],
            "vol": int(df['Volume'].iloc[-1] / 1000),
            "industry": industry
        }
    except:
        return None

# --- AI 評分邏輯 ---
def get_ai_analysis(data, adr_pct):
    score = 60
    score += (adr_pct * 5)
    if data['price'] > data['open']: score += 10
    change_pct = ((data['price'] - data['prev_close']) / data['prev_close']) * 100
    score += (change_pct * 2)
    day_range = data['high'] - data['low']
    if day_range > 0:
        pos = (data['price'] - data['low']) / day_range
        score += (pos * 15)
    score = min(max(score, 0), 100)
    
    if score >= 80: return score, "⭐⭐⭐⭐⭐ (強勢)", "趨勢極強，適合短線進攻操作"
    elif score >= 65: return score, "⭐⭐⭐⭐ (偏多)", "多方佔優，回測支撐可尋找機會"
    elif score >= 50: return score, "⭐⭐⭐ (盤整)", "震盪格局，建議不追高，區間操作"
    else: return score, "⭐⭐ (弱勢)", "動能不足，注意破底風險，保守操作"

# --- 主介面介面 ---

st.markdown("<h2 style='text-align: center; font-size: 22px; margin-bottom: 5px;'>🚀 台股 AI 全方位實戰系統</h2>", unsafe_allow_html=True)

# 1. 市場指標指標 (緊湊呈現)
adr_val = fetch_adr_status()
st.markdown(f"""
<div style="background-color:#1e2329; padding:8px; border-radius:10px; border-left: 5px solid {'#3fb950' if adr_val > 0 else '#f85149'}; margin-bottom: 12px; text-align:center;">
    <span style="color:#848e9c; font-size:12px;">前夜美股 ADR 指標：</span>
    <b style="color:{'#3fb950' if adr_val > 0 else '#f85149'}; font-size:15px;">{adr_val:+.2f}%</b>
</div>
""", unsafe_allow_html=True)

# 2. 智慧控制區 (原本在側邊欄的內容移至此)
c_in, c_pre = st.columns([1, 1])

with c_in:
    manual_query = st.text_input("🔍 名稱或代號", placeholder="京元電, 長榮, 2330...")

with c_pre:
    presets = {
        "常用標的...": "",
        "2449 京元電子": "2449.TW",
        "2330 台積電": "2330.TW",
        "2317 鴻海": "2317.TW",
        "2603 長榮": "2603.TW",
        "2881 富邦金": "2881.TW",
        "2382 廣達": "2382.TW",
        "2618 長榮航": "2618.TW",
        "2454 聯發科": "2454.TW"
    }
    selected_preset = st.selectbox("📌 快速選取", list(presets.keys()))

# 智慧解析標的
target_input = manual_query if manual_query else presets[selected_preset]

if not target_input:
    st.info("💡 請在上方輸入公司名稱、股票代號進行分析。")
    st.stop()

# 解析出正確的 Ticker 代號
resolved_ticker = search_ticker(target_input)

if not resolved_ticker:
    st.error(f"❌ 找不到與「{target_input}」相符的台股標的。")
    st.info("提示：請嘗試輸入完整名稱（如：京元電子）或四位數代號。")
    st.stop()

# 側邊欄隱藏設定 (折扣)
discount = st.sidebar.slider("券商折扣 (6折請選 0.6)", 0.1, 1.0, 0.6)

# 3. 獲取數據與分析
with st.spinner(f"正在分析 {target_input} ..."):
    data = fetch_stock_data(resolved_ticker)

if data:
    p = data['price']
    tick = get_tick_size(p)
    # 計算損平點
    cost_rate = (0.001425 * discount * 2) + 0.0015
    be_price = p * (1 + cost_rate)
    # AI 評分
    score, stars, note = get_ai_analysis(data, adr_val)

    # 4. 介面呈現
    st.markdown(f"### 📊 {data['name']} <small style='font-size:14px; color:#888;'>({data['symbol']})</small>", unsafe_allow_html=True)
    
    # AI 評比卡片
    st.markdown(f"""
    <div style="background-color:#161b22; padding:12px; border-radius:12px; border:1px solid #58a6ff; margin-bottom:15px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="color:#8b949e; font-size:14px;">AI 實戰評分</span>
            <b style="color:#58a6ff; font-size:22px;">{score:.0f} / 100</b>
        </div>
        <div style="font-size:16px; color:#f0883e; margin:5px 0;">{stars}</div>
        <div style="color:#d1d5da; font-size:13px;">💡 建議：{note}</div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("成交價", f"{p}", f"{((p-data['prev_close'])/data['prev_close'])*100:.2f}%")
    c2.metric("高 / 低", f"{data['high']} / {data['low']}")
    c3.metric("級距 (Tick)", f"{tick}")

    st.divider()

    # 5. 進出場建議
    st.subheader("🤖 AI 實戰進出場建議")
    
    r1, r2 = st.columns(2)
    with r1:
        # 推薦買進：若 ADR 強則參考支撐位
        rec_buy = p - tick if adr_val > 0 else data['open']
        st.markdown(f"""
        <div style="background-color:#1c2128; padding:15px; border-radius:10px; border:1px solid #3fb950;">
            <p style="color:#8b949e; margin:0; font-size:14px;">AI 推薦買進價</p>
            <h2 style="color:#3fb950; margin:5px 0;">{rec_buy:.2f}</h2>
            <p style="font-size:11px; color:#8b949e;">(建議觀察買盤力道)</p>
        </div>
        """, unsafe_allow_html=True)
    
    with r2:
        st.markdown(f"""
        <div style="background-color:#1c2128; padding:15px; border-radius:10px; border:1px solid #f85149;">
            <p style="color:#8b949e; margin:0; font-size:14px;">當沖獲利損平點</p>
            <h2 style="color:#f85149; margin:5px 0;">{be_price:.2f}</h2>
            <p style="font-size:11px; color:#8b949e;">(超過此價位才算賺錢)</p>
        </div>
        """, unsafe_allow_html=True)

    # 關鍵位階導航
    st.write("")
    st.write("🎯 **實戰位階導航：**")
    t1, t2, t3, t4 = st.columns(4)
    t1.error(f"極限停損\n{p - tick*4:.2f}")
    t2.warning(f"防守進場\n{p - tick*1:.2f}")
    t3.success(f"短線目標\n{p + tick*3:.2f}")
    t4.info(f"強勢目標\n{p + tick*6:.2f}")

    if st.button("🔄 刷新即時數據"):
        st.rerun()

else:
    st.error("❌ 無法獲取該標的數據，可能目前非開盤時間或 Yahoo 伺服器繁忙。")

st.caption(f"數據源：Yahoo Finance (延遲 15 分) | 系統時間：{datetime.now().strftime('%H:%M:%S')}")

