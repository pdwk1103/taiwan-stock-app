import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# --- 頁面配置 ---
st.set_page_config(page_title="台股 AI 全方位決策", layout="centered")

# --- 核心邏輯：台股跳檔級距計算 (Tick Size) ---
def get_tick_size(price):
    if price < 10: return 0.01
    elif price < 50: return 0.05
    elif price < 100: return 0.1
    elif price < 500: return 0.5
    elif price < 1000: return 1.0
    else: return 5.0

# --- 數據抓取：美股 ADR 與台股行情 ---
def fetch_adr_context():
    """獲取台積電 ADR (TSM) 表現作為大盤指標"""
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        if len(tsm) < 2: return 0.0
        change = ((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100
        return round(change, 2)
    except:
        return 0.0

def fetch_stock_data(symbol):
    """抓取 Yahoo Finance 數據"""
    try:
        ticker = yf.Ticker(f"{symbol}.TW")
        df = ticker.history(period="1d")
        if df.empty: return None
        
        info = ticker.info
        return {
            "name": info.get('shortName', '未知'),
            "price": round(df['Close'].iloc[-1], 2),
            "open": round(df['Open'].iloc[-1], 2),
            "high": round(df['High'].iloc[-1], 2),
            "low": round(df['Low'].iloc[-1], 2),
            "vol": int(df['Volume'].iloc[-1] / 1000), # 換算為張
            "prev_close": info.get('regularMarketPreviousClose', df['Close'].iloc[-1]),
            "industry": info.get('industry', '多元產業')
        }
    except:
        return None

# --- 主介面 ---
st.title("🚀 台股 AI 全方位決策實戰")

# 1. 頂部市場環境資訊
adr_pct = fetch_adr_context()
st.markdown(f"""
<div style="background-color:#1e2329; padding:12px; border-radius:10px; border-left: 5px solid {'#00ff00' if adr_pct > 0 else '#ff4b4b'};">
    <span style="color:#848e9c; font-size:14px;">前夜美股連動指標 (TSM ADR)：</span>
    <b style="color:{'#00ff00' if adr_pct > 0 else '#ff4b4b'}; font-size:18px;">{adr_pct:+.2f}%</b>
</div>
""", unsafe_allow_html=True)

# 2. 側邊欄：產業與級距篩選
st.sidebar.title("🔍 標的篩選器")
price_range = st.sidebar.selectbox(
    "價格級距分類",
    ["全部", "10-100 (銅板/穩健)", "100-500 (中堅/成長)", "500-1000 (高價/權值)", "1000+ (股王/領先)"]
)

# 定義多樣化標的清單
stock_pool = {
    "科技": ["2330", "2454", "2317", "2449", "2382", "2357", "3008", "5274"],
    "航運": ["2603", "2609", "2618", "2610"],
    "金融": ["2881", "2882", "2891", "2886"],
    "傳產/塑化": ["1301", "1303", "2002", "2105"],
    "生技/能源": ["1760", "6446", "6806"]
}

# 整合並分類
all_stocks = {}
for cat, codes in stock_pool.items():
    for code in codes:
        all_stocks[code] = cat

# 3. 標的選取與篩選邏輯
selected_sid = st.selectbox(
    "選擇實戰標的",
    list(all_stocks.keys()),
    format_func=lambda x: f"{x} - {all_stocks[x]}"
)

# 交易參數
discount = st.sidebar.slider("券商手續費折扣", 0.1, 1.0, 0.6)

# 4. 數據抓取與 AI 決策
with st.spinner("AI 模型分析中..."):
    data = fetch_stock_data(selected_sid)

if data:
    p = data['price']
    tick = get_tick_size(p)
    
    # 損平點計算 (含手續費與稅)
    cost_rate = (0.001425 * discount * 2) + 0.0015
    be_price = p * (1 + cost_rate)

    # UI 展示
    st.write(f"### 📊 {selected_sid} {data['name']} ({all_stocks[selected_sid]})")
    c1, c2, c3 = st.columns(3)
    c1.metric("當前成交價", f"{p}", f"{((p-data['prev_close'])/data['prev_close'])*100:.2f}%")
    c2.metric("今日高/低", f"{data['high']} / {data['low']}")
    c3.metric("跳檔級距 (Tick)", f"{tick}")

    st.divider()

    # --- AI 推薦區塊 ---
    st.subheader("🤖 AI 短中線實戰建議")
    
    # 策略判定邏輯
    is_up = adr_pct > 0.3
    recommend_buy = p - tick if is_up else data['open']
    if p < data['low'] + (tick * 2): # 跌深反彈策略
        recommend_buy = p
        strategy = "【分盤低吸】目前接近低點，具備支撐優勢。"
    else:
        strategy = "【擇優進場】參考美股連動，建議回測支撐位掛單。"

    # 決策卡片
    r1, r2 = st.columns(2)
    with r1:
        st.markdown(f"""
        <div style="background-color:#161b22; padding:15px; border-radius:10px; border:1px solid #3fb950;">
            <p style="color:#8b949e; margin:0; font-size:14px;">AI 推薦買進價</p>
            <h2 style="color:#3fb950; margin:5px 0;">{recommend_buy:.2f}</h2>
            <p style="font-size:12px; color:#8b949e;">策略：{strategy}</p>
        </div>
        """, unsafe_allow_html=True)
    
    with r2:
        st.markdown(f"""
        <div style="background-color:#161b22; padding:15px; border-radius:10px; border:1px solid #f85149;">
            <p style="color:#8b949e; margin:0; font-size:14px;">當沖獲利損平點</p>
            <h2 style="color:#f85149; margin:5px 0;">{be_price:.2f}</h2>
            <p style="font-size:12px; color:#8b949e;">(賣出價需高於此位才獲利)</p>
        </div>
        """, unsafe_allow_html=True)

    # 關鍵位階導航
    st.write("")
    st.write("🎯 **操作關鍵檔位導航：**")
    t1, t2, t3, t4 = st.columns(4)
    t1.error(f"極限停損\n{p - (tick * 4):.2f}")
    t2.warning(f"保守買點\n{p - (tick * 1):.2f}")
    t3.success(f"短線目標\n{p + (tick * 3):.2f}")
    t4.info(f"強勢攻頂\n{p + (tick * 6):.2f}")

    if st.button("🔄 刷新最新行情"):
        st.rerun()

else:
    st.error("❌ 無法獲取該標的數據。請確認代碼是否正確。")

st.caption(f"數據源：Yahoo Finance (延遲 15 分) | 系統時間：{datetime.now().strftime('%H:%M:%S')}")
