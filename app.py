import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account

# --- 頁面配置 (優化手機檢視) ---
st.set_page_config(page_title="台股 AI 雲端實戰", layout="centered", initial_sidebar_state="collapsed")

# --- Firebase / Firestore 初始化 ---
@st.cache_resource
def init_firestore():
    """初始化雲端資料庫連線"""
    try:
        if "firebase" in st.secrets:
            # 將 Secrets 轉為字典
            creds_dict = dict(st.secrets["firebase"])
            # 處理 private_key 可能出現的轉義字元
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            
            creds = service_account.Credentials.from_service_account_info(creds_dict)
            return firestore.Client(credentials=creds)
    except Exception as e:
        return None
    return None

db = init_firestore()
app_id = st.secrets.get("general", {}).get("app_id", "stock_ai_v2")

# --- 跳檔級距 (Tick Size) ---
def get_tick(p):
    if p < 10: return 0.01
    elif p < 50: return 0.05
    elif p < 100: return 0.1
    elif p < 500: return 0.5
    elif p < 1000: return 1.0
    else: return 5.0

# --- 技術指標計算 (MA + KD + MACD) ---
def compute_indicators(df):
    if len(df) < 35: return df
    # 均線
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

# --- 雲端數據存取邏輯 ---
def cloud_save(uid, portfolio):
    if not db: return
    # 強制路徑：/artifacts/{appId}/users/{userId}/data/portfolio
    doc_ref = db.document(f"artifacts/{app_id}/users/{uid}/data/portfolio")
    doc_ref.set({"items": portfolio, "last_updated": datetime.now()})

def cloud_load(uid):
    if not db: return []
    try:
        doc_ref = db.document(f"artifacts/{app_id}/users/{uid}/data/portfolio")
        doc = doc_ref.get()
        return doc.to_dict().get("items", []) if doc.exists else []
    except: return []

# --- 市場搜尋與 ADR 分析 ---
@st.cache_data(ttl=3600)
def get_adr_sentiment():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        adr_change = ((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100
        return round(adr_change, 2)
    except: return 0.0

def find_stock(query):
    query = query.strip()
    if not query: return None, None
    if query.isdigit() and len(query) >= 4: return f"{query}.TW", query
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&lang=zh-Hant-TW&region=TW"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        if res.status_code == 200:
            qs = res.json().get('quotes', [])
            for q in qs:
                s = q.get('symbol', '')
                if ".TW" in s or ".TWO" in s: return s, q.get('shortname', s)
    except: pass
    return None, None

# --- 主介面與導覽 ---
st.sidebar.title("🎮 AI 實戰導航")
mode = st.sidebar.radio("功能切換：", ["📢 AI 盤前推薦", "🛡️ 雲端持倉管理"])
user_cloud_id = st.sidebar.text_input("🔑 雲端通行碼 (Cloud ID)", value="My_Portfolio_V1")
discount = st.sidebar.slider("券商手續費折扣", 0.1, 1.0, 0.6)

adr_val = get_adr_sentiment()

# --- 模式一：盤前推薦 ---
if mode == "📢 AI 盤前推薦":
    st.markdown("<h2 style='text-align: center; font-size: 22px;'>🚀 今日 AI 盤前選股推薦</h2>", unsafe_allow_html=True)
    st.markdown(f"""<div style="background-color:#1e2329; padding:10px; border-radius:10px; text-align:center; margin-bottom:15px; border-left:5px solid {'#3fb950' if adr_val > 0 else '#f85149'};"><span style="color:#888; font-size:12px;">前夜美股連動 (TSM ADR)</span><br><b style="color:{'#3fb950' if adr_val > 0 else '#f85149'}; font-size:18px;">{adr_val:+.2f}%</b></div>""", unsafe_allow_html=True)

    scan_targets = ["2449", "2330", "2317", "2603", "2618", "2382", "2454", "3008", "2609", "2303"]
    recs = []
    
    with st.spinner("AI 全面掃描市場數據中..."):
        for sid in scan_targets:
            try:
                ticker = yf.Ticker(f"{sid}.TW")
                df = compute_indicators(ticker.history(period="60d"))
                if df.empty: continue
                last, prev = df.iloc[-1], df.iloc[-2]
                
                # AI 綜合買訊分值
                score = 50
                if last['Close'] > last['MA5']: score += 15
                if last['K'] > last['D'] and prev['K'] <= prev['D']: score += 15
                if last['MACD'] > 0: score += 10
                score += (adr_val * 2.5)
                
                if score >= 60:
                    tick = get_tick(last['Close'])
                    recs.append({
                        "id": sid, "name": ticker.info.get('shortName', sid),
                        "price": round(last['Close'], 2), "score": int(score),
                        "buy": round(max(last['MA5'], last['Close'] - tick), 2),
                        "target": round(last['Close'] + tick * 8, 2)
                    })
            except: continue

    for item in sorted(recs, key=lambda x: x['score'], reverse=True):
        st.markdown(f"""<div style="background-color:#161b22; padding:15px; border-radius:12px; border:1px solid #30363d; margin-bottom:12px;">
            <div style="display:flex; justify-content:space-between;"><b>{item['name']} ({item['id']})</b><span style="color:#3fb950;">評分: {item['score']}</span></div>
            <div style="display:flex; justify-content:space-between; margin-top:8px; background:#0d1117; padding:10px; border-radius:8px;">
                <div style="text-align:center;"><small style="color:#888;">建議買進</small><br><b style="color:#3fb950;">{item['buy']}</b></div>
                <div style="text-align:center;"><small style="color:#888;">目標獲利</small><br><b style="color:#58a6ff;">{item['target']}</b></div>
                <div style="text-align:center;"><small style="color:#888;">目前參考</small><br><b>{item['price']}</b></div>
            </div>
        </div>""", unsafe_allow_html=True)

# --- 模式二：雲端持倉管理 ---
else:
    st.markdown("<h2 style='text-align: center; font-size: 22px;'>🛡️ 雲端持倉實戰診斷</h2>", unsafe_allow_html=True)
    
    if 'portfolio_list' not in st.session_state or st.sidebar.button("🔄 同步資料庫"):
        st.session_state.portfolio_list = cloud_load(user_cloud_id)

    with st.expander("➕ 新增個人持倉", expanded=False):
        c1, c2, c3 = st.columns([2, 2, 1])
        new_sid = c1.text_input("代號或名稱")
        new_cost = c2.number_input("平均成本", min_value=0.0, step=0.1)
        if c3.button("存入"):
            sym, name = find_stock(new_sid)
            if sym:
                st.session_state.portfolio_list.append({"symbol": sym, "name": name, "cost": new_cost})
                cloud_save(user_cloud_id, st.session_state.portfolio_list)
                st.success(f"同步成功 {name}")
                st.rerun()
            else:
                st.error("查無此標的")

    if not st.session_state.portfolio_list:
        st.info(f"通行碼「{user_cloud_id}」目前無雲端紀錄。")
    else:
        st.write(f"### 📍 即時雲端診斷 (ID: {user_cloud_id})")
        for i, stock in enumerate(st.session_state.portfolio_list):
            try:
                ticker = yf.Ticker(stock['symbol'])
                df = compute_indicators(ticker.history(period="60d"))
                last = df.iloc[-1]
                curr_p = round(last['Close'], 2)
                profit = ((curr_p - stock['cost']) / stock['cost']) * 100
                tk = get_tick(curr_p)
                
                # 診斷狀態分析
                d_status, d_action, d_color = "", "", "#ffffff"
                if profit > 0: # 獲利
                    if last['MACD'] > 0 and last['K'] > last['D']:
                        d_status, d_action, d_color = "🚀 強勢續強", f"指標維持多頭。建議續留讓獲利奔跑。目標上看 {curr_p + tk*10}", "#3fb950"
                    else:
                        d_status, d_action, d_color = "⚠️ 漲勢轉弱", "指標出現轉折訊號。建議分批減碼獲利了結。", "#f0883e"
                else: # 虧損
                    if last['MACD'] > 0 or (last['K'] > last['D'] and last['K'] < 30):
                        d_status, d_action, d_color = "💪 底部轉強", "目前虧損但技術面已現轉機指標，建議續抱等待解套。", "#58a6ff"
                    elif curr_p < last['MA20']:
                        d_status, d_action, d_color = "🚨 趨勢走壞", "股價跌破關鍵均線支撐。為了資金安全，建議果斷止損離場。", "#f85149"
                    else:
                        d_status, d_action, d_color = "💤 盤整待變", "尚在盤整區域。只要不破今日低點，可持股觀察動能。", "#8b949e"

                st.markdown(f"""<div style="background-color:#161b22; padding:15px; border-radius:12px; border-left:8px solid {d_color}; margin-bottom:12px;">
                    <div style="display:flex; justify-content:space-between;"><b>{stock['name']}</b><b style="color:{d_color};">{d_status}</b></div>
                    <div style="display:flex; justify-content:space-between; margin:10px 0;">
                        <span>成本: {stock['cost']} | 現價: <b>{curr_p}</b></span>
                        <span style="color:{d_color}; font-size:18px;">{profit:+.2f}%</span>
                    </div>
                    <div style="background:#0d1117; padding:10px; border-radius:8px; font-size:14px; border:1px solid #30363d;">
                        <b>💡 AI 建議：</b>{d_action}
                    </div>
                </div>""", unsafe_allow_html=True)
                
                if st.button(f"🗑️ 移除 {stock['name']}", key=f"del_{i}"):
                    st.session_state.portfolio_list.pop(i)
                    cloud_save(user_cloud_id, st.session_state.portfolio_list)
                    st.rerun()
            except: continue

# 底部狀態
st.write("---")
if db:
    st.success("🟢 雲端資料庫已連線 (Firestore Ready)")
else:
    st.warning("🔴 雲端未連線：請依照教學修正 Secrets 格式")
st.caption(f"數據時間：{datetime.now().strftime('%H:%M:%S')} (延遲 15 分鐘)")

