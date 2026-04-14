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

# --- 智慧模糊搜尋：獲取匹配清單 ---
def get_search_candidates(query):
    """根據輸入關鍵字回傳台股候選名單"""
    query = query.strip()
    if not query: return []
    
    # 如果直接輸入 4 位數代號，優先處理
    if query.isdigit() and len(query) == 4:
        return [{"label": f"{query} (直接查詢)", "symbol": f"{query}.TW"}]

    candidates = []
    try:
        # 呼叫 Yahoo 搜尋建議 API (繁體中文語系)
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&lang=zh-Hant-TW&region=TW&quotesCount=15"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        
        if res.status_code == 200:
            data = res.json()
            for quote in data.get('quotes', []):
                symbol = quote.get('symbol', '')
                # 只保留台股上市 (.TW) 或上櫃 (.TWO)
                if symbol.endswith(".TW") or symbol.endswith(".TWO"):
                    shortname = quote.get('shortname', '')
                    longname = quote.get('longname', '')
                    # 優先顯示中文名稱
                    display_name = shortname if shortname else longname
                    if display_name:
                        candidates.append({
                            "label": f"{display_name} ({symbol.replace('.TW','').replace('.TWO','')})",
                            "symbol": symbol
                        })
    except:
        pass
    return candidates

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
        df = ticker.history(period="5d")
        if df.empty: return None
        
        try:
            name = ticker.info.get('shortName', ticker_symbol.split('.')[0])
            industry = ticker.info.get('industry', '多元產業')
        except:
            name = ticker_symbol.split('.')[0]
            industry = "未知"
            
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

# --- 主介面 ---

# 標題縮小化
st.markdown("<h2 style='text-align: center; font-size: 20px; margin-bottom: 5px; color: #f0f2f6;'>🚀 台股 AI 全方位實戰系統</h2>", unsafe_allow_html=True)

# 1. 市場指標 (緊湊呈現)
adr_val = fetch_adr_status()
st.markdown(f"""
<div style="background-color:#1e2329; padding:6px; border-radius:10px; border-left: 5px solid {'#3fb950' if adr_val > 0 else '#f85149'}; margin-bottom: 12px; text-align:center;">
    <span style="color:#848e9c; font-size:11px;">前夜美股 ADR 指標：</span>
    <b style="color:{'#3fb950' if adr_val > 0 else '#f85149'}; font-size:14px;">{adr_val:+.2f}%</b>
</div>
""", unsafe_allow_html=True)

# 2. 智慧搜尋控制區
st.markdown("#### 🔍 智慧搜尋標的")
search_query = st.text_input("第一步：輸入公司簡稱或代號", placeholder="例如: 京元電, 長榮, 2330", label_visibility="collapsed")

final_ticker = None

if search_query:
    candidates = get_search_candidates(search_query)
    if candidates:
        # 顯示下拉選單讓使用者確認
        selection = st.selectbox(
            "第二步：請從搜尋結果中選擇正確的標的",
            options=candidates,
            format_func=lambda x: x["label"],
            help="若沒看到目標，請嘗試輸入更完整的名稱"
        )
        if selection:
            final_ticker = selection["symbol"]
    else:
        st.warning(f"😭 找不到與「{search_query}」相關的台股標的，請更換關鍵字再試一次。")
else:
    # 預設顯示常用清單 (當沒搜尋時)
    default_presets = [
        {"label": "2449 京元電子", "symbol": "2449.TW"},
        {"label": "2330 台積電", "symbol": "2330.TW"},
        {"label": "2317 鴻海", "symbol": "2317.TW"},
        {"label": "2603 長榮", "symbol": "2603.TW"},
        {"label": "2881 富邦金", "symbol": "2881.TW"}
    ]
    selection = st.selectbox("或從常用清單中選取", options=default_presets, format_func=lambda x: x["label"])
    final_ticker = selection["symbol"]

# 側邊欄設定 (折扣)
discount = st.sidebar.slider("券商折扣 (6折請選 0.6)", 0.1, 1.0, 0.6)

# 3. 獲取數據與分析結果
if final_ticker:
    with st.spinner("AI 正在同步行情..."):
        data = fetch_stock_data(final_ticker)

    if data:
        p = data['price']
        tick = get_tick_size(p)
        cost_rate = (0.001425 * discount * 2) + 0.0015
        be_price = p * (1 + cost_rate)
        score, stars, note = get_ai_analysis(data, adr_val)

        # 4. 介面呈現
        st.markdown(f"### 📊 {data['name']} <small style='font-size:14px; color:#888;'>({data['symbol']})</small>", unsafe_allow_html=True)
        
        # AI 評比卡片
        st.markdown(f"""
        <div style="background-color:#161b22; padding:12px; border-radius:12px; border:1px solid #58a6ff; margin-bottom:15px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="color:#8b949e; font-size:13px;">AI 實戰綜合評分</span>
                <b style="color:#58a6ff; font-size:20px;">{score:.0f} / 100</b>
            </div>
            <div style="font-size:15px; color:#f0883e; margin:5px 0;">{stars}</div>
            <div style="color:#d1d5da; font-size:12px;">💡 建議：{note}</div>
        </div>
        """, unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        c1.metric("成交價", f"{p}", f"{((p-data['prev_close'])/data['prev_close'])*100:.2f}%")
        c2.metric("高 / 低", f"{data['high']} / {data['low']}")
        c3.metric("級距 (Tick)", f"{tick}")

        st.divider()

        # 5. 進出場建議
        st.subheader("🤖 AI 實戰掛單與損平點")
        
        r1, r2 = st.columns(2)
        with r1:
            rec_buy = p - tick if adr_val > 0 else data['open']
            st.markdown(f"""
            <div style="background-color:#1c2128; padding:15px; border-radius:10px; border:1px solid #3fb950;">
                <p style="color:#8b949e; margin:0; font-size:14px;">AI 推薦買進價</p>
                <h2 style="color:#3fb950; margin:5px 0;">{rec_buy:.2f}</h2>
                <p style="font-size:11px; color:#8b949e;">(建議觀察盤中委買力道)</p>
            </div>
            """, unsafe_allow_html=True)
        
        with r2:
            st.markdown(f"""
            <div style="background-color:#1c2128; padding:15px; border-radius:10px; border:1px solid #f85149;">
                <p style="color:#8b949e; margin:0; font-size:14px;">當沖獲利損平點</p>
                <h2 style="color:#f85149; margin:5px 0;">{be_price:.2f}</h2>
                <p style="font-size:11px; color:#8b949e;">(賣出價需高於此才獲利)</p>
            </div>
            """, unsafe_allow_html=True)

        # 位階導航
        st.write("")
        st.write("🎯 **短線實戰位階導航：**")
        t1, t2, t3, t4 = st.columns(4)
        t1.error(f"極限停損\n{p - tick*4:.2f}")
        t2.warning(f"防守進場\n{p - tick*1:.2f}")
        t3.success(f"短線目標\n{p + tick*3:.2f}")
        t4.info(f"強勢目標\n{p + tick*6:.2f}")

        if st.button("🔄 立即刷新行情"):
            st.rerun()

    else:
        st.error("❌ 無法獲取該標的數據，請確認後重試。")

st.caption(f"數據源：Yahoo Finance | 最後更新：{datetime.now().strftime('%H:%M:%S')}")
