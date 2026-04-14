import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# --- 頁面配置 ---
st.set_page_config(page_title="台股 AI 盤前分析", layout="centered", initial_sidebar_state="collapsed")

# --- 技術指標計算函數 ---
def calculate_indicators(df):
    # 1. 均線 (MA)
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()

    # 2. KD 指標 (9, 3, 3)
    low_min = df['Low'].rolling(window=9).min()
    high_max = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - low_min) / (high_max - low_min) * 100
    df['K'] = df['RSV'].ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()

    # 3. MACD (12, 26, 9)
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp1 - exp2
    df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD'] = (df['DIF'] - df['DEA']) * 2
    
    return df

# --- 跳檔級距 (Tick Size) ---
def get_tick(p):
    if p < 10: return 0.01
    elif p < 50: return 0.05
    elif p < 100: return 0.1
    elif p < 500: return 0.5
    elif p < 1000: return 1.0
    else: return 5.0

# --- 市場環境分析 ---
@st.cache_data(ttl=3600)
def get_adr_context():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        nvda = yf.Ticker("NVDA").history(period="2d")
        tsm_c = ((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100
        nvda_c = ((nvda['Close'].iloc[-1] - nvda['Close'].iloc[-2]) / nvda['Close'].iloc[-2]) * 100
        return round(tsm_c, 2), round(nvda_c, 2)
    except:
        return 0.0, 0.0

# --- AI 核心診斷邏輯 ---
def ai_scanner(symbol, adr_trend):
    try:
        ticker = yf.Ticker(f"{symbol}.TW")
        # 抓取 80 天資料確保 MA60 與 MACD 準確
        df = ticker.history(period="80d")
        if len(df) < 60: return None
        
        df = calculate_indicators(df)
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        score = 50
        tags = []
        
        # A. 均線分析 (多頭排列加分)
        if last['MA5'] > last['MA20'] > last['MA60']:
            score += 20
            tags.append("📈 均線多頭排列")
        elif last['Close'] > last['MA5']:
            score += 10
            tags.append("✅ 站上 5 日線")
            
        # B. KD 分析
        if last['K'] > last['D'] and prev['K'] <= prev['D']:
            score += 15
            tags.append("⭐ KD 黃金交叉")
        elif last['K'] > last['D']:
            score += 5
            tags.append("🔼 KD 向上")
            
        # C. MACD 分析
        if last['MACD'] > 0 and prev['MACD'] <= 0:
            score += 15
            tags.append("🔥 MACD 轉紅柱")
        elif last['MACD'] > 0:
            score += 5
            
        # D. 美股連動
        score += (adr_trend * 2)
        
        # 價格與操作建議
        p = round(last['Close'], 2)
        tick = get_tick(p)
        
        # 建議進場價：支撐位 (5日線或今日低點向上跳一檔)
        rec_in = max(round(last['MA5'], 2), p - tick)
        target = p + (tick * 10) # 預設目標空間
        stop = p - (tick * 6)   # 預設止損空間
        
        return {
            "id": symbol,
            "name": ticker.info.get('shortName', symbol),
            "price": p,
            "score": min(round(score), 100),
            "tags": tags,
            "rec_in": rec_in,
            "target": target,
            "stop": stop,
            "kd": f"K:{last['K']:.1f} D:{last['D']:.1f}",
            "macd": "多方控盤" if last['MACD'] > 0 else "空方修正"
        }
    except:
        return None

# --- 主介面 ---

st.markdown("<h2 style='text-align: center; font-size: 22px; margin-bottom: 0;'>🚀 AI 盤前實戰選股助手</h2>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888; font-size: 13px;'>技術指標全掃描：MA + KD + MACD</p>", unsafe_allow_html=True)

# 1. 盤前環境診斷
t_adr, n_adr = get_adr_context()
c1, c2 = st.columns(2)
with c1:
    st.markdown(f"<div style='background-color:#1e2329; padding:10px; border-radius:10px; text-align:center;'> <small style='color:#888;'>台積電 ADR</small><br><b style='color:{'#3fb950' if t_adr > 0 else '#f85149'}; font-size:18px;'>{t_adr:+.2f}%</b></div>", unsafe_allow_html=True)
with c2:
    st.markdown(f"<div style='background-color:#1e2329; padding:10px; border-radius:10px; text-align:center;'> <small style='color:#888;'>Nvidia (NVDA)</small><br><b style='color:{'#3fb950' if n_adr > 0 else '#f85149'}; font-size:18px;'>{n_adr:+.2f}%</b></div>", unsafe_allow_html=True)

st.write("")

# 2. 自動掃描與推薦
st.write("🔍 **AI 盤前自動掃描清單** (依分數排序)")
# 擴大掃描池，包含更多潛力股
scan_list = ["2449", "2330", "2317", "2603", "2618", "2382", "2454", "3008", "2609", "3231", "2303", "2881", "2376"]

all_rec = []
prog = st.progress(0)
for i, sid in enumerate(scan_list):
    res = ai_scanner(sid, t_adr)
    if res and res['score'] >= 55:
        all_rec.append(res)
    prog.progress((i+1)/len(scan_list))

# 排序
all_rec = sorted(all_rec, key=lambda x: x['score'], reverse=True)

if all_rec:
    for item in all_rec:
        with st.container():
            # 製作精美實戰卡片
            st.markdown(f"""
            <div style="background-color:#161b22; padding:15px; border-radius:12px; border:1px solid #30363d; margin-bottom:12px;">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <div>
                        <b style="font-size:18px;">{item['name']} ({item['id']})</b><br>
                        <small style="color:#8b949e;">{item['kd']} | {item['macd']}</small>
                    </div>
                    <div style="text-align:right;">
                        <span style="background-color:#238636; color:white; padding:2px 8px; border-radius:6px; font-size:12px;">評分 {item['score']}</span><br>
                        <b style="color:#3fb950; font-size:20px;">{item['price']}</b>
                    </div>
                </div>
                <div style="margin:8px 0;">
                    {" ".join([f'<span style="background-color:#388bfd26; color:#79c0ff; border:1px solid #388bfd66; padding:1px 5px; border-radius:4px; font-size:10px; margin-right:4px;">{tag}</span>' for tag in item['tags']])}
                </div>
                <div style="display:flex; justify-content:space-between; background-color:#0d1117; padding:10px; border-radius:8px; margin-top:5px;">
                    <div style="text-align:center; flex:1;">
                        <small style="color:#8b949e;">建議進場</small><br>
                        <b style="color:#3fb950;">{item['rec_in']}</b>
                    </div>
                    <div style="text-align:center; flex:1; border-left:1px solid #30363d; border-right:1px solid #30363d;">
                        <small style="color:#8b949e;">目標獲利</small><br>
                        <b style="color:#58a6ff;">{item['target']}</b>
                    </div>
                    <div style="text-align:center; flex:1;">
                        <small style="color:#8b949e;">停損防線</small><br>
                        <b style="color:#f85149;">{item['stop']}</b>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
else:
    st.info("💡 目前技術面尚無強烈買訊標的，建議保守觀望。")

st.divider()

# 3. 底部資訊
st.sidebar.title("🛠️ 參數設定")
discount = st.sidebar.slider("券商折扣", 0.1, 1.0, 0.6)

st.markdown("""
<div style="background-color:#0d1117; padding:10px; border-radius:8px; font-size:11px; color:#8b949e;">
    <b>盤前操作指南：</b><br>
    1. 建議在 08:30 - 09:00 參閱此清單，作為開盤掛單依據。<br>
    2. <b>進場建議：</b> 優先選取評分 > 75 且 KD 向上、MACD 紅柱之標的。<br>
    3. <b>先買後賣：</b> 建議於目標獲利價位附近分批掛單賣出。
</div>
""", unsafe_allow_html=True)

if st.button("🔄 手動刷新市場診斷"):
    st.rerun()

st.caption(f"數據時點：{datetime.now().strftime('%H:%M:%S')} (延遲 15 分鐘)")
.