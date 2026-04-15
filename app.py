import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import time
from datetime import datetime, timedelta, timezone
from google.cloud import firestore
from google.oauth2 import service_account

# --- 頁面配置 ---
st.set_page_config(page_title="台股 AI 雲端實戰", layout="centered", initial_sidebar_state="collapsed")

# --- 0. 核心配置與台北時間 ---
CORE_STOCKS = {
    "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2449": "京元電子",
    "2603": "長榮", "2609": "陽明", "2618": "長榮航", "2382": "廣達",
    "3008": "大立光", "3231": "緯創", "2303": "聯電", "2881": "富邦金",
    "2882": "國泰金", "1301": "台塑", "2002": "中鋼", "2357": "華碩"
}

def get_taipei_now():
    """獲取目前的台北時間 (UTC+8)"""
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz)

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
    if not db or not uid: return False
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("users").document(uid).collection("portfolio").document("data")
        doc_ref.set({"items": data, "last_updated": get_taipei_now(), "user_id": uid})
        return True
    except: return False

def cloud_load(uid):
    if not db or not uid: return []
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("users").document(uid).collection("portfolio").document("data")
        doc = doc_ref.get()
        return doc.to_dict().get("items", []) if doc.exists else []
    except: return []

# --- 3. 登入管理 ---
if "user_id" not in st.session_state:
    qp = st.query_params
    if "uid" in qp:
        st.session_state.user_id = qp["uid"]
        st.session_state.authenticated = True
        st.session_state.portfolio_list = cloud_load(qp["uid"])
    else:
        st.session_state.authenticated = False
        st.session_state.user_id = ""

def handle_login(uid):
    uid = uid.strip()
    if uid:
        st.session_state.user_id = uid
        st.session_state.authenticated = True
        st.session_state.portfolio_list = cloud_load(uid)
        st.query_params["uid"] = uid 
        st.rerun()

# --- 4. 增強版中文名稱抓取邏輯 ---
@st.cache_data(ttl=86400) # 名稱不會常變，快取一天
def get_clean_cname(symbol):
    """輸入 2330 或 2330.TW，回傳精準繁體中文名"""
    pure_id = symbol.split('.')[0]
    # 1. 優先從內建核心名單抓取 (最準)
    if pure_id in CORE_STOCKS:
        return CORE_STOCKS[pure_id]
    
    # 2. 從網路搜尋抓取 (針對自定義輸入)
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={pure_id}&lang=zh-Hant-TW&region=TW"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            quotes = res.json().get('quotes', [])
            for q in quotes:
                if q.get('symbol').startswith(pure_id):
                    name = q.get('shortname') or q.get('longname')
                    if name:
                        # 移除常見的英文後綴以保持介面乾淨
                        return name.replace("Ordinary Shares", "").replace("Common Stock", "").strip()
    except: pass
    return symbol

def find_stock_with_name(q):
    """搜尋引擎：支援代號與名稱搜尋"""
    q = q.strip()
    if q.isdigit() and len(q) >= 4:
        # 如果是純代號
        symbol = f"{q}.TW"
        return symbol, get_clean_cname(symbol)
    
    # 如果是輸入名稱搜尋
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={q}&lang=zh-Hant-TW&region=TW"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        for quote in res.json().get('quotes', []):
            s = quote.get('symbol', '')
            if ".TW" in s or ".TWO" in s:
                return s, quote.get('shortname', s)
    except: pass
    return None, None

# --- 5. 技術指標 ---
def compute_indicators(df):
    if len(df) < 35: return df
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    l, h = df['Low'].rolling(window=9).min(), df['High'].rolling(window=9).max()
    df['K'] = ((df['Close'] - l) / (h - l) * 100).ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()
    e12, e26 = df['Close'].ewm(span=12).mean(), df['Close'].ewm(span=26).mean()
    df['MACD'] = (e12 - e26 - (e12 - e26).ewm(span=9).mean()) * 2
    return df

@st.cache_data(ttl=3600)
def get_adr():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return round(((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100, 2)
    except: return 0.0

# --- 6. 介面渲染 ---

if not st.session_state.authenticated:
    st.markdown("<div style='height: 80px;'></div>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center; color: #58a6ff;'>🚀 AI 實戰航線</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #8b949e;'>輸入通行碼即可同步雲端持倉</p>", unsafe_allow_html=True)
    with st.container():
        st.markdown("<div style='background-color: #161b22; padding: 25px; border-radius: 15px; border: 1px solid #30363d;'>", unsafe_allow_html=True)
        login_id = st.text_input("通行碼", placeholder="例如: AlexStock", label_visibility="collapsed")
        if st.button("確認登入並同步", use_container_width=True, type="primary"):
            handle_login(login_id)
        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

else:
    # 側邊欄
    st.sidebar.title("👤 帳號中心")
    st.sidebar.info(f"當前使用者: `{st.session_state.user_id}`")
    if st.sidebar.button("登出帳號"):
        st.session_state.authenticated = False
        st.query_params.clear()
        st.rerun()
    st.sidebar.divider()
    mode = st.sidebar.radio("切換功能", ["📢 AI 盤前推薦", "🛡️ 雲端持倉診斷"])
    
    adr_val = get_adr()

    # 功能一：盤前推薦
    if mode == "📢 AI 盤前推薦":
        st.markdown(f"### 📢 今日 AI 推薦 - {st.session_state.user_id}")
        st.markdown(f"""<div style="background-color:#1e2329; padding:10px; border-radius:10px; text-align:center; border-left:5px solid {'#3fb950' if adr_val > 0 else '#f85149'}; margin-bottom:20px;">
            <small style="color:#888;">TSM ADR 連動強弱</small><br><b style="color:{'#3fb950' if adr_val > 0 else '#f85149'}; font-size:20px;">{adr_val:+.2f}%</b>
        </div>""", unsafe_allow_html=True)

        scan_pool = ["2330", "2317", "2454", "2449", "2603", "2618", "2382", "3231", "2303", "3008"]
        recs = []
        with st.spinner("AI 正在解析中文行情..."):
            for sid in scan_pool:
                try:
                    tkr = yf.Ticker(f"{sid}.TW")
                    df = compute_indicators(tkr.history(period="60d"))
                    l, p = df.iloc[-1], df.iloc[-2]
                    score = 50 + (adr_val * 2.5)
                    if l['Close'] > l['MA5']: score += 15
                    if l['K'] > l['D'] and p['K'] <= p['D']: score += 15
                    if l['MACD'] > 0: score += 10
                    if score >= 60:
                        recs.append({
                            "id": sid, "name": get_clean_cname(sid), "price": round(l['Close'], 2), 
                            "score": int(score), "buy": round(max(l['MA5'], l['Close'] - 0.5), 2)
                        })
                except: continue

        for item in sorted(recs, key=lambda x: x['score'], reverse=True):
            st.markdown(f"""
            <div style="background-color:#161b22; padding:12px; border-radius:10px; border:1px solid #30363d; margin-bottom:10px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <b style="font-size:16px; color:#c9d1d9;">{item['name']} <small style="color:#8b949e;">({item['id']})</small></b>
                    <span style="background:#238636; color:white; padding:2px 8px; border-radius:5px; font-size:12px;">評分 {item['score']}</span>
                </div>
                <div style="display:flex; justify-content:space-between; margin-top:8px; background:#0d1117; padding:10px; border-radius:8px;">
                    <div style="text-align:center;"><small style="color:#8b949e;">參考進場</small><br><b style="color:#3fb950;">{item['buy']}</b></div>
                    <div style="text-align:center;"><small style="color:#8b949e;">當前市價</small><br><b>{item['price']}</b></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # 功能二：持倉診斷
    else:
        st.markdown(f"### 🛡️ 持倉診斷 - {st.session_state.user_id}")
        st.markdown(f"<small style='color:#3fb950;'>● 雲端已同步 (台北 24H)</small>", unsafe_allow_html=True)

        with st.expander("➕ 新增個人持倉", expanded=False):
            c1, c2, c3 = st.columns([2, 2, 1])
            new_id = c1.text_input("代號", placeholder="例如: 2330")
            new_cost = c2.number_input("成本", value=None, placeholder="輸入單價", step=0.1)
            if c3.button("存入", use_container_width=True):
                if new_cost:
                    sym, name = find_stock_with_name(new_id)
                    if sym:
                        st.session_state.portfolio_list.append({"symbol": sym, "name": name, "cost": new_cost, "ts": time.time()})
                        cloud_save(st.session_state.user_id, st.session_state.portfolio_list)
                        st.rerun()
                else: st.error("請輸入價格")

        if not st.session_state.portfolio_list:
            st.info("目前雲端無持倉，請使用上方功能新增。")
        else:
            del_ts = None
            for s in st.session_state.portfolio_list:
                try:
                    tkr = yf.Ticker(s['symbol'])
                    df = compute_indicators(tkr.history(period="60d"))
                    l = df.iloc[-1]
                    cur = round(l['Close'], 2)
                    gain = ((cur - s['cost']) / s['cost']) * 100
                    msg, clr = "", "#ffffff"
                    if gain > 0:
                        if l['MACD'] > 0 and l['K'] > l['D']: msg, clr = "🚀 強勢續留", "#3fb950"
                        else: msg, clr = "⚠️ 漲勢放緩", "#f0883e"
                    else:
                        if l['MACD'] > 0: msg, clr = "💪 底部轉強", "#58a6ff"
                        elif cur < l['MA20']: msg, clr = "🚨 建議止損", "#f85149"
                        else: msg, clr = "💤 盤整待變", "#8b949e"

                    st.markdown(f"""
                    <div style="background-color:#161b22; padding:15px; border-radius:12px; border-left:8px solid {clr}; margin-bottom:12px;">
                        <div style="display:flex; justify-content:space-between;">
                            <b>{s['name']} <small style="color:#8b949e;">({s['symbol'].split('.')[0]})</small></b>
                            <b style="color:{clr};">{msg}</b>
                        </div>
                        <div style="display:flex; justify-content:space-between; margin:10px 0;">
                            <span>成本: {s['cost']} | 現價: <b>{cur}</b></span>
                            <span style="color:{clr}; font-size:18px;">{gain:+.2f}%</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"🗑️ 移除 {s['name']}", key=f"d_{s['ts']}"):
                        del_ts = s['ts']
                except: continue

            if del_ts:
                st.session_state.portfolio_list = [i for i in st.session_state.portfolio_list if i['ts'] != del_ts]
                cloud_save(st.session_state.user_id, st.session_state.portfolio_list)
                st.rerun()

    st.divider()
    now_tp = get_taipei_now()
    st.caption(f"最後更新 (台北 24H): {now_tp.strftime('%Y-%m-%d %H:%M:%S')}")

