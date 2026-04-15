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

# --- 0. 台北時間與基礎配置 ---
def get_taipei_now():
    """獲取目前的台北時間 (UTC+8)"""
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz)

# 內建核心名單 (用於加速顯示)
CORE_STOCKS = {
    "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2449": "京元電子",
    "2603": "長榮", "2609": "陽明", "2618": "長榮航", "2382": "廣達",
    "3008": "大立光", "3231": "緯創", "2303": "聯電", "2881": "富邦金",
    "2882": "國泰金", "3711": "日月光投控", "2308": "台達電", "2891": "中信金"
}

# 擴大後的掃描池 (涵蓋 0050 + 0051 與熱門題材股)
SCAN_POOL = [
    "2330", "2317", "2454", "2449", "2382", "3231", "2603", "2609", "2618", "2303", 
    "3008", "2881", "2882", "2891", "2308", "3711", "2357", "2408", "2379", "3034",
    "3037", "3044", "2376", "2353", "2324", "4938", "2301", "2344", "2409", "3481",
    "2610", "2615", "1605", "1503", "1513", "1519", "1504", "1101", "2002", "2105"
]

# --- 1. Firebase 初始化 ---
@st.cache_resource
def init_db():
    try:
        if "firebase" in st.secrets:
            creds_dict = dict(st.secrets["firebase"])
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = service_account.Credentials.from_service_account_info(creds_dict)
            return firestore.Client(credentials=creds)
    except: return None
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

# --- 4. 名稱與技術指標工具 ---
@st.cache_data(ttl=86400)
def get_clean_cname(symbol):
    pure_id = symbol.split('.')[0]
    if pure_id in CORE_STOCKS: return CORE_STOCKS[pure_id]
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={pure_id}&lang=zh-Hant-TW&region=TW"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        quotes = res.json().get('quotes', [])
        for q in quotes:
            if q.get('symbol').startswith(pure_id):
                return (q.get('shortname') or q.get('longname')).replace("Ordinary Shares", "").strip()
    except: pass
    return symbol

def compute_indicators(df):
    if len(df) < 35: return df
    # 趨勢：均線
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    # 動能：KD (9, 3, 3)
    l9, h9 = df['Low'].rolling(window=9).min(), df['High'].rolling(window=9).max()
    df['K'] = ((df['Close'] - l9) / (h9 - l9) * 100).ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()
    # 力道：MACD
    e12, e26 = df['Close'].ewm(span=12).mean(), df['Close'].ewm(span=26).mean()
    df['MACD'] = (e12 - e26 - (e12 - e26).ewm(span=9).mean()) * 2
    return df

@st.cache_data(ttl=3600)
def get_adr():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return round(((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100, 2)
    except: return 0.0

# --- 5. 介面渲染 ---

if not st.session_state.authenticated:
    st.markdown("<div style='height: 80px;'></div>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center; color: #58a6ff;'>🚀 AI 實戰航線</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #8b949e;'>輸入通行碼即可進入掃描中心</p>", unsafe_allow_html=True)
    login_id = st.text_input("通行碼", placeholder="例如: MyStockPlan", label_visibility="collapsed")
    if st.button("確認登入並同步", use_container_width=True, type="primary"):
        handle_login(login_id)
    st.stop()

else:
    # 側邊欄
    st.sidebar.title("👤 帳號中心")
    st.sidebar.info(f"使用者: `{st.session_state.user_id}`")
    if st.sidebar.button("登出帳號"):
        st.session_state.authenticated = False
        st.query_params.clear()
        st.rerun()
    st.sidebar.divider()
    mode = st.sidebar.radio("切換功能", ["📢 全市場潛力掃描", "🛡️ 雲端持倉診斷"])
    
    adr_val = get_adr()

    # --- 功能一：全市場潛力掃描 ---
    if mode == "📢 全市場潛力掃描":
        st.markdown(f"### 📢 潛力買訊掃描 - {st.session_state.user_id}")
        st.markdown(f"""<div style="background-color:#1e2329; padding:10px; border-radius:10px; text-align:center; border-left:5px solid {'#3fb950' if adr_val > 0 else '#f85149'}; margin-bottom:20px;">
            <small style="color:#888;">美股 TSM ADR 連動</small><br><b style="color:{'#3fb950' if adr_val > 0 else '#f85149'}; font-size:20px;">{adr_val:+.2f}%</b>
        </div>""", unsafe_allow_html=True)

        recs = []
        with st.spinner("AI 正在深度掃描全市場標的買訊..."):
            for sid in SCAN_POOL:
                try:
                    tkr = yf.Ticker(f"{sid}.TW")
                    df = compute_indicators(tkr.history(period="60d"))
                    if df.empty: continue
                    l, p = df.iloc[-1], df.iloc[-2]
                    
                    # --- AI 潛力評分邏輯 ---
                    score = 40 + (adr_val * 2) # 基礎分 + ADR 連動
                    if l['Close'] > l['MA5']: score += 15 # 趨勢向上
                    if l['K'] > l['D'] and p['K'] <= p['D']: score += 20 # KD 黃金交叉 (強訊)
                    if l['MACD'] > 0: score += 10 # 力道轉強
                    if l['Close'] > l['MA20']: score += 15 # 支撐強勁
                    
                    # 只收錄 70 分以上的強勢潛力股
                    if score >= 70:
                        recs.append({
                            "id": sid, "name": get_clean_cname(sid), "price": round(l['Close'], 2), 
                            "score": int(score), "buy": round(max(l['MA5'], l['Close'] * 0.99), 2),
                            "target": round(l['Close'] * 1.05, 2)
                        })
                except: continue

        if recs:
            for item in sorted(recs, key=lambda x: x['score'], reverse=True)[:10]: # 只取最強前 10 名
                st.markdown(f"""
                <div style="background-color:#161b22; padding:12px; border-radius:10px; border:1px solid #30363d; margin-bottom:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <b style="font-size:16px; color:#c9d1d9;">{item['name']} ({item['id']})</b>
                        <span style="background:#238636; color:white; padding:2px 8px; border-radius:5px; font-size:12px;">潛力分 {item['score']}</span>
                    </div>
                    <div style="display:flex; justify-content:space-between; margin-top:8px; background:#0d1117; padding:10px; border-radius:8px;">
                        <div style="text-align:center;"><small style="color:#8b949e;">支撐買點</small><br><b style="color:#3fb950;">{item['buy']}</b></div>
                        <div style="text-align:center;"><small style="color:#8b949e;">短線目標</small><br><b style="color:#58a6ff;">{item['target']}</b></div>
                        <div style="text-align:center;"><small style="color:#8b949e;">當前價</small><br><b>{item['price']}</b></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("💡 目前全市場尚無強勢買訊，建議保留現金觀察。")

    # --- 功能二：持倉診斷 ---
    else:
        st.markdown(f"### 🛡️ 持倉診斷 - {st.session_state.user_id}")
        st.markdown(f"<small style='color:#3fb950;'>● 雲端已同步 (台北 24H)</small>", unsafe_allow_html=True)

        with st.expander("➕ 新增持倉記錄", expanded=False):
            c1, c2, c3 = st.columns([2, 2, 1])
            add_id = c1.text_input("代號", placeholder="例如: 2330")
            add_cost = c2.number_input("成本", value=None, placeholder="輸入價格", step=0.1)
            if c3.button("存入", use_container_width=True):
                if add_cost:
                    # 搜尋並存入
                    try:
                        name = get_clean_cname(add_id)
                        st.session_state.portfolio_list.append({"symbol": f"{add_id}.TW", "name": name, "cost": add_cost, "ts": time.time()})
                        cloud_save(st.session_state.user_id, st.session_state.portfolio_list)
                        st.rerun()
                    except: st.error("查無代號")

        if st.session_state.portfolio_list:
            del_ts = None
            for s in st.session_state.portfolio_list:
                try:
                    display_name = get_clean_cname(s['symbol'])
                    tkr = yf.Ticker(s['symbol'])
                    df = compute_indicators(tkr.history(period="60d"))
                    l = df.iloc[-1]
                    cur = round(l['Close'], 2)
                    gain = ((cur - s['cost']) / s['cost']) * 100
                    msg, clr = "", "#ffffff"
                    if gain > 0:
                        if l['MACD'] > 0: msg, clr = "🚀 強勢續留", "#3fb950"
                        else: msg, clr = "⚠️ 漲勢轉弱", "#f0883e"
                    else:
                        if l['MACD'] > 0: msg, clr = "💪 底部轉強", "#58a6ff"
                        elif cur < l['MA20']: msg, clr = "🚨 建議止損", "#f85149"
                        else: msg, clr = "💤 盤整待變", "#8b949e"

                    st.markdown(f"""
                    <div style="background-color:#161b22; padding:15px; border-radius:12px; border-left:8px solid {clr}; margin-bottom:12px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <b>{display_name} ({s['symbol'].split('.')[0]})</b>
                            <b style="color:{clr};">{msg}</b>
                        </div>
                        <div style="display:flex; justify-content:space-between; margin:10px 0;">
                            <span>成本: {s['cost']} | 現價: <b>{cur}</b></span>
                            <span style="color:{clr}; font-size:18px; font-weight:bold;">{gain:+.2f}%</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"🗑️ 移除 {display_name}", key=f"d_{s['ts']}"): del_ts = s['ts']
                except: continue
            if del_ts:
                st.session_state.portfolio_list = [i for i in st.session_state.portfolio_list if i['ts'] != del_ts]
                cloud_save(st.session_state.user_id, st.session_state.portfolio_list)
                st.rerun()

    st.divider()
    st.caption(f"最後同步 (台北 24H): {get_taipei_now().strftime('%Y-%m-%d %H:%M:%S')}")

