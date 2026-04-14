import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import time
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account

# --- 頁面配置 ---
st.set_page_config(page_title="台股 AI 雲端實戰", layout="centered", initial_sidebar_state="collapsed")

# --- 1. Firebase 初始化 ---
@st.cache_resource
def init_db():
    try:
        if "firebase" in st.secrets:
            creds_dict = dict(st.secrets["firebase"])
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = service_account.Credentials.from_service_account_info(creds_dict)
            return firestore.Client(credentials=creds)
    except:
        return None
    return None

db = init_db()
app_id = st.secrets.get("general", {}).get("app_id", "stock_ai_v2")

# --- 2. 雲端核心邏輯 ---
def cloud_save(uid, data):
    if not db or not uid: return
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("users").document(uid).collection("portfolio").document("data")
        doc_ref.set({"items": data, "updated": datetime.now()})
    except: pass

def cloud_load(uid):
    if not db or not uid: return []
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("users").document(uid).collection("portfolio").document("data")
        doc = doc_ref.get()
        return doc.to_dict().get("items", []) if doc.exists else []
    except: return []

# --- 3. 登入與 Session 狀態管理 ---
# 檢查 URL 是否帶有 uid 參數 (實現自動登入)
query_params = st.query_params
if "uid" in query_params and "user_id" not in st.session_state:
    st.session_state.user_id = query_params["uid"]
    st.session_state.authenticated = True

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# 登入處理函式
def login_user(uid):
    if uid.strip():
        st.session_state.user_id = uid.strip()
        st.session_state.authenticated = True
        st.session_state.portfolio_list = cloud_load(uid.strip())
        # 將 uid 寫入網址參數，以便下次自動登入
        st.query_params["uid"] = uid.strip()
        st.rerun()
    else:
        st.error("請輸入有效的通行碼")

# --- 4. 技術面工具 ---
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
    low_9, high_9 = df['Low'].rolling(window=9).min(), df['High'].rolling(window=9).max()
    df['K'] = ((df['Close'] - low_9) / (high_9 - low_9) * 100).ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()
    ema12, ema26 = df['Close'].ewm(span=12).mean(), df['Close'].ewm(span=26).mean()
    df['MACD'] = (ema12 - ema26 - (ema12 - ema26).ewm(span=9).mean()) * 2
    return df

@st.cache_data(ttl=3600)
def get_adr():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return round(((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100, 2)
    except: return 0.0

def find_stock(q):
    if q.isdigit() and len(q) >= 4: return f"{q}.TW", q
    try:
        res = requests.get(f"https://query2.finance.yahoo.com/v1/finance/search?q={q}&lang=zh-Hant-TW&region=TW", headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        for quote in res.json().get('quotes', []):
            s = quote.get('symbol', '')
            if ".TW" in s or ".TWO" in s: return s, quote.get('shortname', s)
    except: pass
    return None, None

# --- 5. 介面渲染邏輯 ---

# 登入頁面
if not st.session_state.authenticated:
    st.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center; color: #58a6ff;'>🚀 AI 實戰航線</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #8b949e;'>請輸入您的雲端通行碼以開啟功能</p>", unsafe_allow_html=True)
    
    with st.container():
        st.markdown("<div style='background-color: #161b22; padding: 30px; border-radius: 20px; border: 1px solid #30363d;'>", unsafe_allow_html=True)
        login_id = st.text_input("個人通行碼 (Passcode)", placeholder="例如: Alex770801", label_visibility="collapsed")
        if st.button("確認登入", use_container_width=True, type="primary"):
            login_user(login_id)
        st.markdown("</div>", unsafe_allow_html=True)
        
    st.markdown("<p style='text-align: center; font-size: 12px; color: #444; margin-top: 20px;'>提示：登入後請將網址加入書籤，下次可自動登入</p>", unsafe_allow_html=True)
    st.stop()

# 主功能頁面
else:
    # 側邊欄改為顯示用戶資訊與登出按鈕
    st.sidebar.title("👤 帳號資訊")
    st.sidebar.write(f"當前帳號: `{st.session_state.user_id}`")
    if st.sidebar.button("登出帳號"):
        st.session_state.authenticated = False
        st.session_state.user_id = ""
        st.query_params.clear()
        st.rerun()
    
    st.sidebar.divider()
    mode = st.sidebar.radio("功能模組", ["📢 AI 盤前推薦", "🛡️ 雲端持倉管理"])
    discount = st.sidebar.slider("券商折扣", 0.1, 1.0, 0.6)
    
    # 初始化資料
    if "portfolio_list" not in st.session_state:
        st.session_state.portfolio_list = cloud_load(st.session_state.user_id)

    adr_val = get_adr()

    if mode == "📢 AI 盤前推薦":
        st.markdown(f"<h3 style='text-align: center; font-size: 20px;'>📢 AI 推薦 - {st.session_state.user_id}</h3>", unsafe_allow_html=True)
        st.markdown(f"""<div style="background-color:#1e2329; padding:10px; border-radius:10px; text-align:center; margin-bottom:15px; border-left:5px solid {'#3fb950' if adr_val > 0 else '#f85149'};"><span style="color:#888; font-size:12px;">美股 TSM ADR 連動</span><br><b style="color:{'#3fb950' if adr_val > 0 else '#f85149'}; font-size:18px;">{adr_val:+.2f}%</b></div>""", unsafe_allow_html=True)

        scan_list = ["2449", "2330", "2317", "2603", "2618", "2382", "2454", "3008", "2609", "3231"]
        recs = []
        with st.spinner("分析中..."):
            for sid in scan_list:
                try:
                    tkr = yf.Ticker(f"{sid}.TW")
                    df = compute_tech(tkr.history(period="60d"))
                    l, p = df.iloc[-1], df.iloc[-2]
                    score = 50 + (adr_val * 2)
                    if l['Close'] > l['MA5']: score += 15
                    if l['K'] > l['D'] and p['K'] <= p['D']: score += 15
                    if l['MACD'] > 0: score += 10
                    if score >= 60:
                        t = get_tick(l['Close'])
                        recs.append({"id": sid, "name": tkr.info.get('shortName', sid), "price": round(l['Close'], 2), "score": int(score), "buy": round(max(l['MA5'], l['Close'] - t), 2), "target": round(l['Close'] + t * 8, 2)})
                except: continue

        for item in sorted(recs, key=lambda x: x['score'], reverse=True):
            st.markdown(f"""<div style="background-color:#161b22; padding:15px; border-radius:12px; border:1px solid #30363d; margin-bottom:12px;"><div style="display:flex; justify-content:space-between;"><b>{item['name']} ({item['id']})</b><span style="color:#3fb950;">分: {item['score']}</span></div><div style="display:flex; justify-content:space-between; margin-top:8px; background:#0d1117; padding:10px; border-radius:8px;"><div style="text-align:center;"><small style="color:#888;">買點</small><br><b style="color:#3fb950;">{item['buy']}</b></div><div style="text-align:center;"><small style="color:#888;">目標</small><br><b style="color:#58a6ff;">{item['target']}</b></div><div style="text-align:center;"><small style="color:#888;">現價</small><br><b>{item['price']}</b></div></div></div>""", unsafe_allow_html=True)

    else:
        st.markdown(f"<h3 style='text-align: center; font-size: 20px;'>🛡️ 持倉診斷 - {st.session_state.user_id}</h3>", unsafe_allow_html=True)
        
        with st.expander("➕ 新增持倉", expanded=False):
            c1, c2, c3 = st.columns([2, 2, 1])
            new_id = c1.text_input("代號/名稱", placeholder="2449")
            new_cost = c2.number_input("買進成本", value=None, placeholder="輸入價格", step=0.1)
            if c3.button("儲存", use_container_width=True):
                if new_cost:
                    sym, name = find_stock(new_id)
                    if sym:
                        st.session_state.portfolio_list.append({"symbol": sym, "name": name, "cost": new_cost, "ts": time.time()})
                        cloud_save(st.session_state.user_id, st.session_state.portfolio_list)
                        st.success("已同步")
                        st.rerun()
                else: st.error("請輸入價格")

        if not st.session_state.portfolio_list:
            st.info("尚無雲端紀錄")
        else:
            del_ts = None
            for s in st.session_state.portfolio_list:
                try:
                    tkr = yf.Ticker(s['symbol'])
                    df = compute_tech(tkr.history(period="60d"))
                    l = df.iloc[-1]
                    cur = round(l['Close'], 2)
                    gain = ((cur - s['cost']) / s['cost']) * 100
                    t = get_tick(cur)
                    msg, clr = "", "#ffffff"
                    if gain > 0:
                        if l['MACD'] > 0 and l['K'] > l['D']: msg, clr = "🚀 強勢續留", "#3fb950"
                        else: msg, clr = "⚠️ 建議減碼", "#f0883e"
                    else:
                        if l['MACD'] > 0: msg, clr = "💪 底部轉強", "#58a6ff"
                        elif cur < l['MA20']: msg, clr = "🚨 果斷止損", "#f85149"
                        else: msg, clr = "💤 盤整待變", "#8b949e"

                    st.markdown(f"""<div style="background-color:#161b22; padding:15px; border-radius:12px; border-left:8px solid {clr}; margin-bottom:12px;"><div style="display:flex; justify-content:space-between;"><b>{s['name']}</b><b style="color:{clr};">{msg}</b></div><div style="display:flex; justify-content:space-between; margin:10px 0;"><span>成本: {s['cost']} | 現價: <b>{cur}</b></span><span style="color:{clr}; font-size:18px;">{gain:+.2f}%</span></div></div>""", unsafe_allow_html=True)
                    if st.button(f"🗑️ 移除 {s['name']}", key=f"d_{s.get('ts', s['symbol'])}"):
                        del_ts = s.get('ts')
                except: continue

            if del_ts:
                st.session_state.portfolio_list = [i for i in st.session_state.portfolio_list if i.get('ts') != del_ts]
                cloud_save(st.session_state.user_id, st.session_state.portfolio_list)
                st.rerun()

    st.write("---")
    st.caption(f"帳號: {st.session_state.user_id} | 更新於: {datetime.now().strftime('%H:%M:%S')}")

