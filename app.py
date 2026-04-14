import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# --- 頁面配置 ---
st.set_page_config(page_title="台股 AI 實戰決策", layout="centered")

# --- 核心邏輯：台股跳檔級距計算 (Tick Size) ---
def get_tick_size(price):
    if price < 10: return 0.01
    elif price < 50: return 0.05
    elif price < 100: return 0.1
    elif price < 500: return 0.5
    elif price < 1000: return 1.0
    else: return 5.0

# --- 數據抓取：指標與行情 ---
def fetch_adr_context():
    """獲取 TSM ADR 指標"""
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        if len(tsm) < 2: return 0.0
        change = ((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100
        return round(change, 2)
    except:
        return 0.0

def fetch_stock_data(symbol):
    """獲取台股詳細數據"""
    try:
        # 自動處理代號格式
        clean_sid = symbol.strip().upper()
        if clean_sid.isdigit():
            clean_sid = f"{clean_sid}.TW"
        
        ticker = yf.Ticker(clean_sid)
        df = ticker.history(period="2d")
        if df.empty: return None
        
        info = ticker.info
        return {
            "symbol": symbol,
            "name": info.get('shortName', symbol),
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

# --- AI 評比邏輯 ---
def calculate_ai_rating(data, adr_pct):
    score = 50 # 基礎分
    # 1. ADR 連動加分
    if adr_pct > 1.0: score += 15
    elif adr_pct > 0: score += 5
    elif adr_pct < -1.0: score -= 15
    
    # 2. 當日強弱加分 (相對於開盤價)
    if data['price'] > data['open']: score += 10
    
    # 3. 位階加分 (是否接近當日高點)
    day_range = data['high'] - data['low']
    if day_range > 0:
        position = (data['price'] - data['low']) / day_range
        score += (position * 20)
        
    score = min(max(score, 0), 100) # 限制在 0-100
    
    if score >= 80: return score, "⭐⭐⭐⭐⭐ (極佳)", "強勢進攻型，適合追價操作"
    elif score >= 65: return score, "⭐⭐⭐⭐ (優良)", "趨勢偏多，建議支撐位佈局"
    elif score >= 50: return score, "⭐⭐⭐ (中性)", "震盪格局，不宜過度追高"
    else: return score, "⭐⭐ (偏弱)", "動能不足，建議觀望或保守停損"

# --- 主介面 ---
st.title("🚀 台股 AI 全方位實戰系統")

# 1. 頂部大盤環境
adr_val = fetch_adr_context()
st.markdown(f"""
<div style="background-color:#1e2329; padding:12px; border-radius:10px; border-left: 5px solid {'#00ff00' if adr_val > 0 else '#ff4b4b'};">
    <span style="color:#848e9c; font-size:14px;">前夜美股連動指標 (TSM ADR)：</span>
    <b style="color:{'#00ff00' if adr_val > 0 else '#ff4b4b'}; font-size:18px;">{adr_val:+.2f}%</b>
</div>
""", unsafe_allow_html=True)

# 2. 側邊欄：搜尋與設定
st.sidebar.title("🔍 智慧搜尋")
# 手動搜尋輸入
search_input = st.sidebar.text_input("輸入公司代號或名稱 (如: 2603)", "")

# 預設標的清單 (代號 + 名稱)
stock_presets = {
    "2449 京元電子": "2449",
    "2330 台積電": "2330",
    "2317 鴻海": "2317",
    "2603 長榮": "2603",
    "2881 富邦金": "2881",
    "2382 廣達": "2382",
    "2618 長榮航": "2618",
    "2454 聯發科": "2454",
    "3008 大立光": "3008",
    "2303 聯電": "2303"
}
selected_preset = st.sidebar.selectbox("或從常用清單選取", list(stock_presets.keys()))

# 決定最後使用的代號
final_sid = search_input if search_input else stock_presets[selected_preset]

discount = st.sidebar.slider("券商手續費折扣", 0.1, 1.0, 0.6)

# 3. 抓取數據與分析
with st.spinner("AI 正在評估報價與風險..."):
    data = fetch_stock_data(final_sid)

if data:
    p = data['price']
    tick = get_tick_size(p)
    # 損平點
    cost_rate = (0.001425 * discount * 2) + 0.0015
    be_price = p * (1 + cost_rate)
    # AI 評比
    score, stars, comment = calculate_ai_rating(data, adr_val)

    # 介面呈現
    st.subheader(f"📊 {data['name']} ({final_sid}) - {data['industry']}")
    
    # 評比區塊
    st.markdown(f"""
    <div style="background-color:#161b22; padding:15px; border-radius:12px; border:1px solid #58a6ff; margin-bottom:20px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="color:#8b949e;">AI 綜合實戰評比</span>
            <b style="color:#58a6ff; font-size:24px;">{score:.0f} / 100</b>
        </div>
        <div style="font-size:18px; color:#f0883e; margin:10px 0;">{stars}</div>
        <div style="color:#d1d5da; font-size:14px;">💡 AI 點評：{comment}</div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("當前成交價", f"{p}", f"{((p-data['prev_close'])/data['prev_close'])*100:.2f}%")
    c2.metric("今日高 / 低", f"{data['high']} / {data['low']}")
    c3.metric("跳檔級距 (Tick)", f"{tick}")

    st.divider()

    # --- 決策卡片 ---
    st.subheader("🤖 AI 實戰進出場建議")
    
    r1, r2 = st.columns(2)
    with r1:
        # 推薦價計算邏輯 (簡單支撐位)
        rec_buy = p - tick if adr_val > 0 else data['open']
        st.markdown(f"""
        <div style="background-color:#1c2128; padding:15px; border-radius:10px; border:1px solid #3fb950;">
            <p style="color:#8b949e; margin:0; font-size:14px;">AI 推薦買進參考價</p>
            <h2 style="color:#3fb950; margin:5px 0;">{rec_buy:.2f}</h2>
            <p style="font-size:12px; color:#8b949e;">(建議配合即時大單動向)</p>
        </div>
        """, unsafe_allow_html=True)
    
    with r2:
        st.markdown(f"""
        <div style="background-color:#1c2128; padding:15px; border-radius:10px; border:1px solid #f85149;">
            <p style="color:#8b949e; margin:0; font-size:14px;">當沖獲利損平點</p>
            <h2 style="color:#f85149; margin:5px 0;">{be_price:.2f}</h2>
            <p style="font-size:12px; color:#8b949e;">(賣出需高於此價位才算賺)</p>
        </div>
        """, unsafe_allow_html=True)

    # 操作導航
    st.write("")
    st.write("🎯 **關鍵位階參考：**")
    t1, t2, t3, t4 = st.columns(4)
    t1.error(f"極限停損\n{p - tick*4:.2f}")
    t2.warning(f"防守進場\n{p - tick*1:.2f}")
    t3.success(f"短線目標\n{p + tick*3:.2f}")
    t4.info(f"強勢挑戰\n{p + tick*6:.2f}")

    if st.button("🔄 刷新最新即時報價"):
        st.rerun()

else:
    st.error("❌ 找不到該標的，或數據格式有誤。")
    st.info("提示：搜尋請輸入 4 位數代號 (例如: 2330) 或標準代碼 (例如: 2603.TW)")

st.caption(f"數據源：Yahoo Finance (延遲 15 分) | 系統時間：{datetime.now().strftime('%H:%M:%S')}")

