import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import os
import json
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account

# --- 頁面配置 ---
st.set_page_config(page_title="台股 AI 雲端實戰", layout="centered", initial_sidebar_state="expanded")

# --- Firebase / Firestore 初始化 (遵循 MANDATORY RULES) ---
# 獲取環境變數中的 Firebase 配置
app_id = st.secrets.get("app_id", "default-stock-app")

# 建立 Firestore 客戶端
# 備註：在 Streamlit Cloud 環境中，建議將 Service Account 放入 Secrets
try:
    if "firebase" in st.secrets:
        creds = service_account.Credentials.from_service_account_info(st.secrets["firebase"])
        db = firestore.Client(credentials=creds)
    else:
        # 降級處理：若無資料庫配置則使用 Session State (提醒用戶)
        db = None
except Exception as e:
    db = None

# --- 核心跳檔級距 ---
def get_tick(p):
    if p < 10: return 0.01
    elif p < 50: return 0.05
    elif p < 100: return 0.1
    elif p < 500: return 0.5
    elif p < 1000: return 1.0
    else: return 5.0

# --- 技術指標計算 ---
def calculate_indicators(df):
    if len(df) < 30: return df
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    # KD (9, 3, 3)
    low_min = df['Low'].rolling(window=9).min()
    high_max = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - low_min) / (high_max - low_min) * 100
    df['K'] = df['RSV'].ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()
    # MACD (12, 26, 9)
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp1 - exp2
    df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD'] = (df['DIF'] - df['DEA']) * 2
    return df

# --- 搜尋引擎 ---
def search_ticker(query):
    query = query.strip()
    if not query: return None, None
    if query.isdigit() and len(query) >= 4: return f"{query}.TW", query
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&lang=zh-Hant-TW&region=TW"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        if res.status_code == 200:
            quotes = res.json().get('quotes', [])
            for q in quotes:
                symbol = q.get('symbol', '')
                if ".TW" in symbol or ".TWO" in symbol:
                    return symbol, q.get('shortname', symbol)
    except: pass
    return None, None

# --- 市場環境分析 ---
@st.cache_data(ttl=3600)
def get_market_sentiment():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        tsm_c = ((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100
        return round(tsm_c, 2)
    except: return 0.0

# --- 雲端儲存邏輯 ---
def save_to_cloud(user_id, portfolio):
    if not db: return
    # 遵循路徑規則: /artifacts/{appId}/users/{userId}/{collectionName}
    doc_ref = db.document(f"artifacts/{app_id}/users/{user_id}/data/portfolio")
    doc_ref.set({"items": portfolio})

def load_from_cloud(user_id):
    if not db: return []
    try:
        doc_ref = db.document(f"artifacts/{app_id}/users/{user_id}/data/portfolio")
        doc = doc_ref.get()
        return doc.to_dict().get("items", []) if doc.exists else []
    except: return []

# --- 側邊欄導航 ---
st.sidebar.title("🎮 功能模式")
mode = st.sidebar.radio("選擇操作功能：", ["📢 AI 盤前推薦", "☁️ 雲端持倉管理"])
user_cloud_id = st.sidebar.text_input("🔑 雲端通行碼 (Cloud ID)", value="Guest_User", help="輸入你的專屬代碼以同步資料")
discount = st.sidebar.slider("券商手續費折扣", 0.1, 1.0, 0.6)

adr_val = get_market_sentiment()

# --- 模式一：AI 盤前推薦 ---
if mode == "📢 AI 盤前推薦":
    st.markdown("<h2 style='text-align: center; font-size: 22px;'>🚀 AI 盤前推薦分析</h2>", unsafe_allow_html=True)
    st.markdown(f"""<div style="background-color:#1e2329; padding:10px; border-radius:10px; text-align:center; margin-bottom:15px;"><span style="color:#888; font-size:12px;">美股連動指標 (TSM ADR)</span><br><b style="color:{'#3fb950' if adr_val > 0 else '#f85149'}; font-size:18px;">{adr_val:+.2f}%</b></div>""", unsafe_allow_html=True)

    scan_pool = ["2449", "2330", "2317", "2603", "2618", "2382", "2454", "3008", "2303", "2881"]
    recommendations = []
    
    with st.spinner("AI 正在掃描市場訊號..."):
        for sid in scan_pool:
            try:
                ticker = yf.Ticker(f"{sid}.TW")
                df = calculate_indicators(ticker.history(period="60d"))
                if df.empty: continue
                last = df.iloc[-1]
                prev = df.iloc[-2]
                
                score = 50
                if last['Close'] > last['MA5']: score += 15
                if last['K'] > last['D'] and prev['K'] <= prev['D']: score += 15
                if last['MACD'] > 0: score += 10
                score += (adr_val * 2)
                
                if score >= 60:
                    tick = get_tick(last['Close'])
                    recommendations.append({
                        "id": sid, "name": ticker.info.get('shortName', sid),
                        "price": round(last['Close'], 2), "score": int(score),
                        "in": round(max(last['MA5'], last['Close'] - tick), 2),
                        "out": round(last['Close'] + tick * 8, 2)
                    })
            except: continue

    for item in sorted(recommendations, key=lambda x: x['score'], reverse=True):
        st.markdown(f"""
        <div style="background-color:#161b22; padding:15px; border-radius:12px; border:1px solid #30363d; margin-bottom:12px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <b style="font-size:18px;">{item['name']} ({item['id']})</b>
                <span style="color:#3fb950;">評分: {item['score']}</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin-top:10px; background:#0d1117; padding:8px; border-radius:8px;">
                <div><small style="color:#888;">建議進場</small><br><b style="color:#3fb950;">{item['in']}</b></div>
                <div style="text-align:center;"><small style="color:#888;">目標獲利</small><br><b style="color:#58a6ff;">{item['out']}</b></div>
                <div style="text-align:right;"><small style="color:#888;">目前參考</small><br><b>{item['price']}</b></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

# --- 模式二：雲端持倉管理 ---
else:
    st.markdown("<h2 style='text-align: center; font-size: 22px;'>☁️ 雲端持倉診斷系統</h2>", unsafe_allow_html=True)
    
    # 載入雲端資料
    if 'current_portfolio' not in st.session_state or st.sidebar.button("🔄 同步雲端資料"):
        st.session_state.current_portfolio = load_from_cloud(user_cloud_id)

    # 1. 新增功能
    with st.expander("➕ 新增持倉紀錄", expanded=False):
        c1, c2, c3 = st.columns([2, 2, 1])
        in_stock = c1.text_input("代號/名稱", key="add_name")
        in_cost = c2.number_input("買進成本", min_value=0.0, step=0.1, key="add_cost")
        if c3.button("存入", use_container_width=True):
            sym, name = search_ticker(in_stock)
            if sym:
                st.session_state.current_portfolio.append({'symbol': sym, 'name': name, 'cost': in_cost})
                save_to_cloud(user_cloud_id, st.session_state.current_portfolio)
                st.success(f"已存入 {name}")
                st.rerun()
            else:
                st.error("找不到標的")

    # 2. 持倉診斷列表
    if not st.session_state.current_portfolio:
        st.info(f"通行碼「{user_cloud_id}」目前無雲端紀錄。")
    else:
        st.write(f"### 📍 當前持倉診斷 (ID: {user_cloud_id})")
        for i, stock in enumerate(st.session_state.current_portfolio):
            try:
                ticker = yf.Ticker(stock['symbol'])
                df = calculate_indicators(ticker.history(period="60d"))
                last = df.iloc[-1]
                curr_p = round(last['Close'], 2)
                profit_pct = ((curr_p - stock['cost']) / stock['cost']) * 100
                tick = get_tick(curr_p)
                
                # 診斷模型
                diag_status, diag_action, diag_color = "", "", "#ffffff"
                
                if profit_pct > 0: # 獲利中
                    if last['MACD'] > 0 and last['K'] > last['D']:
                        diag_status, diag_action, diag_color = "🚀 強勢續強", "【建議續留】指標多頭排列，讓獲利奔跑。上看目標 " + str(curr_p + tick*10), "#3fb950"
                    else:
                        diag_status, diag_action, diag_color = "⚠️ 漲勢轉弱", "【建議減碼】指標高檔轉折，可先獲利入袋一半，確保戰果。", "#f0883e"
                else: # 虧損中
                    if last['MACD'] > 0 or (last['K'] > last['D'] and last['K'] < 30):
                        diag_status, diag_action, diag_color = "💪 底部轉強", "【建議續抱】雖然目前套牢，但技術面轉強，具備反彈潛力。", "#58a6ff"
                    elif curr_p < last['MA20']:
                        diag_status, diag_action, diag_color = "🚨 趨勢走壞", "【建議止損】結構已破位。為了保護資金，建議果斷離場。", "#f85149"
                    else:
                        diag_status, diag_action, diag_color = "💤 盤整待變", "【持平觀察】目前方向不明，守住前低即可暫留。", "#8b949e"

                # 顯示卡片
                st.markdown(f"""
                <div style="background-color:#161b22; padding:15px; border-radius:12px; border-left:8px solid {diag_color}; margin-bottom:15px;">
                    <div style="display:flex; justify-content:space-between;">
                        <b style="font-size:18px;">{stock['name']}</b>
                        <b style="color:{diag_color};">{diag_status}</b>
                    </div>
                    <div style="display:flex; justify-content:space-between; margin:10px 0;">
                        <div><small style="color:#888;">成本: {stock['cost']}</small><br>現價: <b>{curr_p}</b></div>
                        <div style="text-align:right;"><small style="color:#888;">累積損益</small><br><b style="color:{'#3fb950' if profit_pct > 0 else '#f85149'}; font-size:18px;">{profit_pct:+.2f}%</b></div>
                    </div>
                    <div style="background:#0d1117; padding:10px; border-radius:8px; font-size:14px; border:1px solid #30363d;">
                        <b>💡 AI 實戰建議：</b>{diag_action}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # 刪除按鈕
                if st.button(f"🗑️ 移除 {stock['name']} 紀錄", key=f"del_{i}"):
                    st.session_state.current_portfolio.pop(i)
                    save_to_cloud(user_cloud_id, st.session_state.current_portfolio)
                    st.rerun()
            except:
                st.error(f"無法同步 {stock['name']} 數據")

# 頁尾
st.write("---")
st.caption(f"數據來源：Yahoo Finance (延遲 15 分鐘) | 系統時間：{datetime.now().strftime('%H:%M:%S')}")
if not db:
    st.warning("⚠️ 尚未偵測到雲端資料庫配置，目前僅能使用暫存模式。請於設定中加入 Firebase Secrets。")
