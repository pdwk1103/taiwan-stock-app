import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# --- 頁面初始配置 ---
st.set_page_config(page_title="台股 AI 實戰決策", layout="centered")

# --- 核心邏輯：台股跳檔級距計算 (Tick Size) ---
def get_tick_size(price):
    if price < 10: return 0.01
    elif price < 50: return 0.05
    elif price < 100: return 0.1
    elif price < 500: return 0.5
    elif price < 1000: return 1.0
    else: return 5.0

# --- 數據抓取引擎 ---
def fetch_adr_status():
    """獲取 TSM ADR 指標"""
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        if len(tsm) >= 2:
            change = ((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100
            return round(change, 2)
        return 0.0
    except:
        return 0.0

def fetch_stock_data(symbol):
    """獲取台股詳細數據 (改進穩定性)"""
    try:
        # 代號格式化
        symbol = symbol.strip().upper()
        if symbol.isdigit():
            clean_symbol = f"{symbol}.TW"
        else:
            clean_symbol = symbol if ".TW" in symbol or ".TWO" in symbol else f"{symbol}.TW"
        
        ticker = yf.Ticker(clean_symbol)
        # 抓取 5 天數據確保萬無一失
        df = ticker.history(period="5d")
        if df.empty: return None
        
        # 抓取基礎資訊 (若 info 失敗則用 symbol 代替名稱)
        try:
            name = ticker.info.get('shortName', symbol)
            industry = ticker.info.get('industry', '多元產業')
        except:
            name = symbol
            industry = "未知"

        last_idx = -1
        prev_idx = -2
        
        return {
            "symbol": symbol,
            "name": name,
            "price": round(df['Close'].iloc[last_idx], 2),
            "open": round(df['Open'].iloc[last_idx], 2),
            "high": round(df['High'].iloc[last_idx], 2),
            "low": round(df['Low'].iloc[last_idx], 2),
            "prev_close": df['Close'].iloc[prev_idx],
            "vol": int(df['Volume'].iloc[last_idx] / 1000),
            "industry": industry
        }
    except Exception as e:
        return None

# --- AI 評比與評分邏輯 ---
def get_ai_analysis(data, adr_pct):
    score = 60 # 初始分
    
    # 1. ADR 指標修正
    score += (adr_pct * 5)
    
    # 2. 當前價格與今日開盤價比較
    if data['price'] > data['open']: score += 10
    
    # 3. 相對於昨日收盤價的強度
    change_pct = ((data['price'] - data['prev_close']) / data['prev_close']) * 100
    score += (change_pct * 2)
    
    # 4. 位階得分 (收盤在當日高點附近則強勢)
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
st.title("🚀 台股 AI 全方位實戰系統")

# 1. 前夜大盤連動指標
adr_val = fetch_adr_status()
st.markdown(f"""
<div style="background-color:#1e2329; padding:12px; border-radius:10px; border-left: 5px solid {'#00ff00' if adr_val > 0 else '#ff4b4b'};">
    <span style="color:#848e9c; font-size:14px;">前夜美股台積電 ADR 表現：</span>
    <b style="color:{'#00ff00' if adr_val > 0 else '#ff4b4b'}; font-size:18px;">{adr_val:+.2f}%</b>
</div>
""", unsafe_allow_html=True)

# 2. 側邊欄：搜尋與產業推薦
st.sidebar.title("🔍 標的選取與搜尋")
manual_input = st.sidebar.text_input("手動輸入代號 (例如: 2603)", "")

# 推薦清單 (含跨產業級距)
presets = {
    "【半導體】2449 京元電子": "2449",
    "【權值王】2330 台積電": "2330",
    "【伺服器】2382 廣達": "2382",
    "【航運股】2603 長榮": "2603",
    "【金融股】2881 富邦金": "2881",
    "【手機鏈】3008 大立光": "3008",
    "【組裝廠】2317 鴻海": "2317",
    "【航空股】2618 長榮航": "2618",
    "【IC 設計】2454 聯發科": "2454"
}
selected_preset = st.sidebar.selectbox("或從常用清單中選擇", list(presets.keys()))

# 決定最後使用的代碼
final_sid = manual_input if manual_input else presets[selected_preset]

# 交易參數
discount = st.sidebar.slider("券商手續費折扣 (6折請選 0.6)", 0.1, 1.0, 0.6)

# 3. 獲取數據與運算
with st.spinner("AI 正在解析大數據與報價..."):
    data = fetch_stock_data(final_sid)

if data:
    p = data['price']
    tick = get_tick_size(p)
    # 計算獲利損平點
    cost_rate = (0.001425 * discount * 2) + 0.0015
    be_price = p * (1 + cost_rate)
    # AI 實戰評分
    score, stars, note = get_ai_analysis(data, adr_val)

    # 4. 介面呈現
    st.subheader(f"📊 {data['name']} ({final_sid}) - {data['industry']}")
    
    # AI 評比卡片
    st.markdown(f"""
    <div style="background-color:#161b22; padding:15px; border-radius:12px; border:1px solid #58a6ff; margin-bottom:20px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="color:#8b949e;">AI 綜合實戰評分</span>
            <b style="color:#58a6ff; font-size:26px;">{score:.0f} / 100</b>
        </div>
        <div style="font-size:18px; color:#f0883e; margin:10px 0;">{stars}</div>
        <div style="color:#d1d5da; font-size:14px;">💡 指導建議：{note}</div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("成交價", f"{p}", f"{((p-data['prev_close'])/data['prev_close'])*100:.2f}%")
    c2.metric("今日高/低", f"{data['high']} / {data['low']}")
    c3.metric("跳檔 (Tick)", f"{tick}")

    st.divider()

    # 5. 進出場建議
    st.subheader("🤖 AI 實戰掛單與損平分析")
    
    r1, r2 = st.columns(2)
    with r1:
        # 推薦進場：若強勢則在下一檔，若弱勢則在開盤價
        rec_buy = p - tick if adr_val > 0 else data['open']
        st.markdown(f"""
        <div style="background-color:#1c2128; padding:15px; border-radius:10px; border:1px solid #3fb950;">
            <p style="color:#8b949e; margin:0; font-size:14px;">AI 推薦買進參考價</p>
            <h2 style="color:#3fb950; margin:5px 0;">{rec_buy:.2f}</h2>
            <p style="font-size:12px; color:#8b949e;">(建議觀察五檔委買單量)</p>
        </div>
        """, unsafe_allow_html=True)
    
    with r2:
        st.markdown(f"""
        <div style="background-color:#1c2128; padding:15px; border-radius:10px; border:1px solid #f85149;">
            <p style="color:#8b949e; margin:0; font-size:14px;">當沖獲利損平點</p>
            <h2 style="color:#f85149; margin:5px 0;">{be_price:.2f}</h2>
            <p style="font-size:12px; color:#8b949e;">(賣出需高於此價才獲利)</p>
        </div>
        """, unsafe_allow_html=True)

    # 關鍵位階
    st.write("")
    st.write("🎯 **短線實戰導航位階：**")
    t1, t2, t3, t4 = st.columns(4)
    t1.error(f"極限停損\n{p - tick*4:.2f}")
    t2.warning(f"保守買點\n{p - tick*1:.2f}")
    t3.success(f"短線目標\n{p + tick*3:.2f}")
    t4.info(f"強勢目標\n{p + tick*6:.2f}")

    if st.button("🔄 立即刷新行情數據"):
        st.rerun()

else:
    st.error("❌ 找不到該標的，或是該代號暫無成交數據。")
    st.info("提示：搜尋請輸入 4 位數代號 (例如: 2603) 或完整代碼 (例如: 2317.TW)")

st.caption(f"數據源：Yahoo Finance (延遲 15 分) | 系統時間：{datetime.now().strftime('%H:%M:%S')}")

