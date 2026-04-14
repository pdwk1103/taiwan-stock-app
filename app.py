import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import time
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account

# --- 頁面配置 (針對 iPhone 寬度優化) ---
st.set_page_config(page_title="台股 AI 雲端實戰", layout="centered", initial_sidebar_state="collapsed")

# --- 1. Firebase / Firestore 初始化 ---
@st.cache_resource
def init_db():
    try:
        if "firebase" in st.secrets:
            creds_dict = dict(st.secrets["firebase"])
            # 確保私鑰換行符號正確
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = service_account.Credentials.from_service_account_info(creds_dict)
            return firestore.Client(credentials=creds)
    except:
        return None
    return None

db = init_db()
app_id = st.secrets.get("general", {}).get("app_id", "stock_ai_v2")

# --- 2. 雲端核心同步邏輯 ---
def cloud_save_data(uid, data_list):
    if not db or not uid: return
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("users").document(uid).collection("portfolio").document("data")
        doc_ref.set({"items": data_list, "updated": datetime.now()})
    except Exception as e:
        st.error(f"雲端寫入異常: {e}")

def cloud_load_data(uid):
    if not db or not uid: return []
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("users").document(uid).collection("portfolio").document("data")
        doc = doc_ref.get()
        return doc.to_dict().get("items", []) if doc.exists else []
    except:
        return []

# --- 3. 初始化或偵測 ID 變更 ---
def sync_portfolio_state(uid):
    if not uid:
        st.session_state.portfolio_list = []
        return
    # 如果用戶換了 ID，或者還沒載入過資料
    if 'current_cloud_id' not in st.session_state or st.session_state.current_cloud_id != uid:
        st.session_state.current_cloud_id = uid
        with st.spinner(f"正在連線至雲端空間..."):
            st.session_state.portfolio_list = cloud_load_data(uid)

# --- 4. 技術指標與行情工具 ---
def get_tick(p):
    if p < 10: return 0.01
    elif p < 50: return 0.05
    elif p < 100: return 0.1
    elif p < 500: return 0.5
    elif p < 1000: return 1.0
    else: return 5.0

def compute_tech(df):
    if len(df) < 35: return df
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    low_9 = df['Low'].rolling(window=9).min()
    high_9 = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - low_9) / (high_9 - low_9) * 100
    df['K'] = df['RSV'].ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = (exp1 - exp2 - (exp1 - exp2).ewm(span=9, adjust=False).mean()) * 2
    return df

@st.cache_data(ttl=3600)
def get_adr():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return round(((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100, 2)
    except: return 0.0

def find_stock(q):
    q = q.strip()
    if q.isdigit() and len(q) >= 4: return f"{q}.TW", q
    try:
        res = requests.get(f"https://query2.finance.yahoo.com/v1/finance/search?q={q}&lang=zh-Hant-TW&region=TW", headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        for quote in res.json().get('quotes', []):
            s = quote.get('symbol', '')
            if ".TW" in s or ".TWO" in s: return s, quote.get('shortname', s)
    except: pass
    return None, None

# --- 5. 主介面 ---
st.sidebar.title("🎮 AI 實戰控制台")
mode = st.sidebar.radio("切換模式", ["📢 AI 盤前推薦", "🛡️ 雲端持倉管理"])
user_id = st.sidebar.text_input("🔑 雲端通行碼", value="", placeholder="請輸入您的個人帳號代碼")
discount = st.sidebar.slider("券商手續費折扣", 0.1, 1.0, 0.6)

# 同步雲端資料 (若無 ID 則不動作)
sync_portfolio_state(user_id)
adr_val = get_adr()

# 如果通行碼為空，強制顯示引導畫面
if not user_id:
    st.markdown("""
    <div style="text-align: center; padding: 50px 20px;">
        <h1 style="font-size: 60px;">🗝️</h1>
        <h2>請先輸入雲端通行碼</h2>
        <p style="color: #888;">請在左側選單中設定您的個人通行碼（個人帳號），<br>設定後即可開始同步雲端選股與持倉診斷。</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# --- 模式一：推薦 ---
if mode == "📢 AI 盤前推薦":
    st.markdown("<h2 style='text-align: center; font-size: 22px;'>🚀 今日 AI 選股推薦</h2>", unsafe_allow_html=True)
    st.markdown(f"""<div style="background-color:#1e2329; padding:10px; border-radius:10px; text-align:center; margin-bottom:15px; border-left:5px solid {'#3fb950' if adr_val > 0 else '#f85149'};"><span style="color:#888; font-size:12px;">前夜美股連動 (TSM ADR)</span><br><b style="color:{'#3fb950' if adr_val > 0 else '#f85149'}; font-size:18px;">{adr_val:+.2f}%</b></div>""", unsafe_allow_html=True)

    scan_list = ["2449", "2330", "2317", "2603", "2618", "2382", "2454", "3008", "2609", "3231", "2303"]
    recs = []
    with st.spinner("掃描技術面指標中..."):
        for sid in scan_list:
            try:
                ticker = yf.Ticker(f"{sid}.TW")
                df = compute_tech(ticker.history(period="60d"))
                last, prev = df.iloc[-1], df.iloc[-2]
                score = 50 + (adr_val * 2)
                if last['Close'] > last['MA5']: score += 15
                if last['K'] > last['D'] and prev['K'] <= prev['D']: score += 15
                if last['MACD'] > 0: score += 10
                if score >= 60:
                    tk = get_tick(last['Close'])
                    recs.append({"id": sid, "name": ticker.info.get('shortName', sid), "price": round(last['Close'], 2), "score": int(score), "buy": round(max(last['MA5'], last['Close'] - tk), 2), "target": round(last['Close'] + tk * 8, 2)})
            except: continue

    for item in sorted(recs, key=lambda x: x['score'], reverse=True):
        st.markdown(f"""<div style="background-color:#161b22; padding:15px; border-radius:12px; border:1px solid #30363d; margin-bottom:12px;"><div style="display:flex; justify-content:space-between;"><b>{item['name']} ({item['id']})</b><span style="color:#3fb950;">評分: {item['score']}</span></div><div style="display:flex; justify-content:space-between; margin-top:8px; background:#0d1117; padding:10px; border-radius:8px;"><div style="text-align:center;"><small style="color:#888;">買進參考</small><br><b style="color:#3fb950;">{item['buy']}</b></div><div style="text-align:center;"><small style="color:#888;">目標獲利</small><br><b style="color:#58a6ff;">{item['target']}</b></div><div style="text-align:center;"><small style="color:#888;">目前</small><br><b>{item['price']}</b></div></div></div>""", unsafe_allow_html=True)

# --- 模式二：雲端持倉 ---
else:
    st.markdown("<h2 style='text-align: center; font-size: 22px;'>🛡️ 雲端持倉實戰診斷</h2>", unsafe_allow_html=True)
    
    with st.expander("➕ 新增持倉標的", expanded=False):
        c1, c2, c3 = st.columns([2, 2, 1])
        new_sid = c1.text_input("代號或名稱", placeholder="2449")
        # 這裡改為 value=None，讓輸入框預設為空
        new_cost = c2.number_input("買進成本", value=None, placeholder="請輸入單價", step=0.1)
        
        if c3.button("存入雲端", use_container_width=True):
            if not new_cost:
                st.error("請輸入買進成本")
            else:
                sym, name = find_stock(new_sid)
                if sym:
                    st.session_state.portfolio_list.append({"symbol": sym, "name": name, "cost": new_cost, "ts": time.time()})
                    cloud_save_data(user_id, st.session_state.portfolio_list)
                    st.success(f"已儲存至雲端: {name}")
                    st.rerun()
                else: st.error("查無此標的")

    if not st.session_state.portfolio_list:
        st.info(f"ID: 「{user_id}」目前雲端無紀錄。")
    else:
        delete_target_ts = None
        
        for stock in st.session_state.portfolio_list:
            try:
                ticker = yf.Ticker(stock['symbol'])
                df = compute_tech(ticker.history(period="60d"))
                last = df.iloc[-1]
                curr_p = round(last['Close'], 2)
                profit = ((curr_p - stock['cost']) / stock['cost']) * 100
                tk = get_tick(curr_p)
                
                status, action, color = "", "", "#ffffff"
                if profit > 0:
                    if last['MACD'] > 0 and last['K'] > last['D']: status, action, color = "🚀 強勢續強", "建議續留，讓獲利奔跑。目標 " + str(curr_p + tk*10), "#3fb950"
                    else: status, action, color = "⚠️ 漲勢轉弱", "指標轉折，建議分批減碼獲利入袋。", "#f0883e"
                else:
                    if last['MACD'] > 0 or (last['K'] > last['D'] and last['K'] < 30): status, action, color = "💪 低檔轉強", "虧損中但指標轉強，建議續抱等待解套。", "#58a6ff"
                    elif curr_p < last['MA20']: status, action, color = "🚨 趨勢破位", "跌破關鍵支撐，建議果斷止損。", "#f85149"
                    else: status, action, color = "💤 盤整待變", "盤整中，守住低點可暫留。", "#8b949e"

                st.markdown(f"""<div style="background-color:#161b22; padding:15px; border-radius:12px; border-left:8px solid {color}; margin-bottom:12px;"><div style="display:flex; justify-content:space-between;"><b>{stock['name']}</b><b style="color:{color};">{status}</b></div><div style="display:flex; justify-content:space-between; margin:10px 0;"><span>成本: {stock['cost']} | 現價: <b>{curr_p}</b></span><span style="color:{color}; font-size:18px;">{profit:+.2f}%</span></div><div style="background:#0d1117; padding:10px; border-radius:8px; font-size:13px; border:1px solid #30363d;"><b>AI 指導：</b>{action}</div></div>""", unsafe_allow_html=True)
                
                if st.button(f"🗑️ 移除 {stock['name']}", key=f"del_{stock.get('ts', stock['symbol'])}"):
                    delete_target_ts = stock.get('ts')
            except: continue

        if delete_target_ts:
            st.session_state.portfolio_list = [s for s in st.session_state.portfolio_list if s.get('ts') != delete_target_ts]
            cloud_save_data(user_id, st.session_state.portfolio_list)
            st.toast("✅ 雲端資料已移除")
            time.sleep(0.5)
            st.rerun()

st.write("---")
st.success(f"🟢 雲端同步中 (帳號: {user_id})")
st.caption(f"更新時間：{datetime.now().strftime('%H:%M:%S')}")
