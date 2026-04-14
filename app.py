import streamlit as st
import yfinance as yf
import pandas as pd
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

# --- 智慧名稱轉代號對照表 (可持續擴充) ---
STOCK_MAP = {
    "台積電": "2330", "TSMC": "2330",
    "鴻海": "2317", "FOXCONN": "2317",
    "京元電": "2449", "京元電子": "2449",
    "聯發科": "2454", "發哥": "2454",
    "長榮": "2603", "長榮海": "2603",
    "陽明": "2609", "萬海": "2615",
    "長榮航": "2618", "華航": "2610",
    "富邦金": "2881", "國泰金": "2882",
    "廣達": "2382", "緯創": "3231", "技嘉": "2376",
    "大立光": "3008", "聯電": "2303", "華碩": "2357",
    "中鋼": "2002", "台塑": "1301", "南亞": "1303"
}

def resolve_symbol(input_str):
    """智慧解析輸入內容：代號或名稱"""
    s = input_str.strip()
    if not s: return ""
    
    # 1. 如果輸入是純數字
    if s.isdigit():
        return s
    
    # 2. 如果輸入在對照表中
    if s in STOCK_MAP:
        return STOCK_MAP[s]
    
    # 3. 模糊搜尋對照表中的名稱
    for name, code in STOCK_MAP.items():
        if s in name:
            return code
            
    return s # 若都找不到，傳回原始字串交給 Yahoo 嘗試

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

def fetch_stock_data(symbol):
    try:
        # 轉換輸入
        code = resolve_symbol(symbol)
        if not code: return None
        
        # 判斷上市或上櫃 (預設上市 .TW)
        clean_symbol = f"{code}.TW"
        
        ticker = yf.Ticker(clean_symbol)
        df = ticker.history(period="5d")
        
        # 若上市抓不到，嘗試上櫃 (.TWO)
        if df.empty:
            clean_symbol = f"{code}.TWO"
            ticker = yf.Ticker(clean_symbol)
            df = ticker.history(period="5d")
            
        if df.empty: return None
        
        info = ticker.info
        name = info.get('shortName', symbol)
        
        return {
            "symbol": code,
            "name": name,
            "price": round(df['Close'].iloc[-1], 2),
            "open": round(df['Open'].iloc[-1], 2),
            "high": round(df['High'].iloc[-1], 2),
            "low": round(df['Low'].iloc[-1], 2),
            "prev_close": df['Close'].iloc[-2],
            "vol": int(df['Volume'].iloc[-1] / 1000),
            "industry": info.get('industry', '多元產業')
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

st.markdown("<h2 style='text-align: center; font-size: 24px; margin-bottom: 10px;'>🚀 台股 AI 全方位實戰系統</h2>", unsafe_allow_html=True)

# 1. 前夜大盤指標 (緊湊呈現)
adr_val = fetch_adr_status()
st.markdown(f"""
<div style="background-color:#1e2329; padding:8px; border-radius:10px; border-left: 5px solid {'#00ff00' if adr_val > 0 else '#ff4b4b'}; margin-bottom: 15px; text-align:center;">
    <span style="color:#848e9c; font-size:12px;">前夜美股 ADR 指標：</span>
    <b style="color:{'#00ff00' if adr_val > 0 else '#ff4b4b'}; font-size:15px;">{adr_val:+.2f}%</b>
</div>
""", unsafe_allow_html=True)

# 2. 主頁控制區 (智慧輸入與選單)
col_in, col_pre = st.columns([1, 1])

with col_in:
    manual_search = st.text_input("🔍 搜尋名稱或代號", placeholder="例如: 京元電 或 2449")

with col_pre:
    presets = {
        "快速選取熱門標的...": "",
        "2449 京元電子": "2449",
        "2330 台積電": "2330",
        "2317 鴻海": "2317",
        "2603 長榮": "2603",
        "2881 富邦金": "2881",
        "2382 廣達": "2382",
        "2618 長榮航": "2618",
        "2454 聯發科": "2454"
    }
    selected_preset = st.selectbox("📌 常用清單", list(presets.keys()))

# 決定最後使用的搜尋字串
search_target = manual_search if manual_search else presets[selected_preset]

if not search_target:
    st.info("💡 請在上方輸入公司名稱、股票代號，或從清單選擇。")
    st.stop()

# 側邊欄隱藏設定
discount = st.sidebar.slider("券商折扣 (6折請選 0.6)", 0.1, 1.0, 0.6)

# 3. 獲取數據與運算
with st.spinner("AI 正在解析並同步報價..."):
    data = fetch_stock_data(search_target)

if data:
    p = data['price']
    tick = get_tick_size(p)
    cost_rate = (0.001425 * discount * 2) + 0.0015
    be_price = p * (1 + cost_rate)
    score, stars, note = get_ai_analysis(data, adr_val)

    # 4. 介面呈現
    st.markdown(f"### 📊 {data['name']} ({data['symbol']}) <small style='font-size:14px; color:#888;'>{data['industry']}</small>", unsafe_allow_html=True)
    
    # AI 評比卡片
    st.markdown(f"""
    <div style="background-color:#161b22; padding:12px; border-radius:12px; border:1px solid #58a6ff; margin-bottom:15px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="color:#8b949e; font-size:14px;">AI 實戰評分</span>
            <b style="color:#58a6ff; font-size:22px;">{score:.0f} / 100</b>
        </div>
        <div style="font-size:16px; color:#f0883e; margin:5px 0;">{stars}</div>
        <div style="color:#d1d5da; font-size:13px;">💡 指導：{note}</div>
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
        rec_buy = p - tick if adr_val > 0 else data['open']
        st.markdown(f"""
        <div style="background-color:#1c2128; padding:15px; border-radius:10px; border:1px solid #3fb950;">
            <p style="color:#8b949e; margin:0; font-size:14px;">AI 推薦買進價</p>
            <h2 style="color:#3fb950; margin:5px 0;">{rec_buy:.2f}</h2>
            <p style="font-size:11px; color:#8b949e;">(建議觀察委買量)</p>
        </div>
        """, unsafe_allow_html=True)
    
    with r2:
        st.markdown(f"""
        <div style="background-color:#1c2128; padding:15px; border-radius:10px; border:1px solid #f85149;">
            <p style="color:#8b949e; margin:0; font-size:14px;">當沖獲利損平點</p>
            <h2 style="color:#f85149; margin:5px 0;">{be_price:.2f}</h2>
            <p style="font-size:11px; color:#8b949e;">(賣出需高於此價)</p>
        </div>
        """, unsafe_allow_html=True)

    # 關鍵位階
    st.write("")
    st.write("🎯 **短線實戰位階導航：**")
    t1, t2, t3, t4 = st.columns(4)
    t1.error(f"極限停損\n{p - tick*4:.2f}")
    t2.warning(f"保守買點\n{p - tick*1:.2f}")
    t3.success(f"短線目標\n{p + tick*3:.2f}")
    t4.info(f"強勢目標\n{p + tick*6:.2f}")

    if st.button("🔄 刷新即時報價"):
        st.rerun()

else:
    st.error("❌ 找不到該標的數據。")
    st.info("請嘗試使用完整公司名稱（如：長榮）或 4 位數代號。")

st.caption(f"數據源：Yahoo Finance | 最後更新：{datetime.now().strftime('%H:%M:%S')}")

