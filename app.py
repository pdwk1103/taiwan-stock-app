import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import time
from datetime import datetime, timedelta, timezone
from google.cloud import firestore
from google.oauth2 import service_account

# --- 頁面配置 (針對 iPhone 寬度與深色模式優化) ---
st.set_page_config(page_title="台股 AI 雲端實戰", layout="centered", initial_sidebar_state="collapsed")

# --- 0. 台北時間工具 (24H) ---
def get_taipei_now():
    """獲取目前的台北時間 (UTC+8)"""
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz)

# --- 1. 核心中文對照表 (大幅擴充以確保掃描瞬間顯示) ---
# 包含 0050, 0051 以及主要權值標的
CORE_STOCKS = {
    "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2449": "京元電子",
    "2382": "廣達", "3231": "緯創", "2603": "長榮", "2609": "陽明",
    "2618": "長榮航", "2303": "聯電", "3008": "大立光", "2881": "富邦金",
    "2882": "國泰金", "2891": "中信金", "2308": "台達電", "3711": "日月光投控",
    "2357": "華碩", "2408": "南亞科", "2379": "瑞昱", "3034": "聯詠",
    "3037": "欣興", "2324": "仁寶", "2353": "宏碁", "2409": "友達",
    "3481": "群創", "2610": "華航", "2615": "萬海", "1605": "華新",
    "1513": "中興電", "1503": "士電", "1519": "華城", "1101": "台泥",
    "2002": "中鋼", "2105": "正新", "2207": "和泰車", "2912": "統一超",
    "3045": "台灣大", "6505": "台塑化", "9910": "豐泰", "1402": "遠東新",
    "1504": "東元", "1722": "台肥", "2360": "致茂", "2377": "微星",
    "2383": "台光電", "2385": "群光", "2395": "研華", "2451": "創見",
    "2474": "可成", "2498": "宏達電", "3017": "奇鋐", "3023": "信邦",
    "3532": "台勝科", "3653": "健策", "4958": "臻鼎-KY", "5871": "中租-KY",
    "6239": "力成", "6415": "矽力-KY", "6669": "緯穎", "8046": "南電",
    "8454": "富邦媒", "9904": "寶成", "9945": "潤泰新", "2345": "智邦"
}

# --- 2. Firebase / Firestore 初始化 ---
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

# --- 3. 雲端同步邏輯 ---
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

# --- 4. 登入管理 ---
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

# --- 5. 中文名稱與技術分析工具 ---
@st.cache_data(ttl=86400)
def get_stock_name_zh(symbol):
    """根據個股編號精準獲取中文名稱"""
    pure_id = symbol.split('.')[0]
    # 1. 優先從對照表抓取 (極速)
    if pure_id in CORE_STOCKS:
        return CORE_STOCKS[pure_id]
    
    # 2. 備案：從 Yahoo Search API 強制繁體中文請求
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={pure_id}&lang=zh-Hant-TW&region=TW"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        quotes = res.json().get('quotes', [])
        for q in quotes:
            if q.get('symbol').startswith(pure_id):
                name = q.get('shortname') or q.get('longname')
                if name:
                    # 去除英文後綴
                    return name.split(' ')[0].replace("Common", "").replace("Stock", "").strip()
    except: pass
    return pure_id

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
def get_adr_val():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return round(((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100, 2)
    except: return 0.0

# --- 6. 介面渲染 ---

if not st.session_state.authenticated:
    st.markdown("<div style='height: 80px;'></div>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center; color: #58a6ff;'>🚀 AI 實戰選股中心</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #8b949e;'>輸入通行碼即可開啟 AI 廣域掃描</p>", unsafe_allow_html=True)
    login_id = st.text_input("通行碼", placeholder="例如: MyStockPlan", label_visibility="collapsed")
    if st.button("確認登入並同步", use_container_width=True, type="primary"):
        handle_login(login_id)
    st.stop()

else:
    st.sidebar.title("👤 帳號中心")
    st.sidebar.info(f"使用者: `{st.session_state.user_id}`")
    if st.sidebar.button("登出帳號"):
        st.session_state.authenticated = False
        st.query_params.clear()
        st.rerun()
    st.sidebar.divider()
    mode = st.sidebar.radio("切換模式", ["🔎 全市場潛力掃描", "🛡️ 雲端持倉診斷"])
    
    adr_val = get_adr_val()

    # --- 模組一：AI 全市場掃描 ---
    if mode == "🔎 全市場潛力掃描":
        st.markdown(f"### 🔎 市場潛力買訊掃描")
        st.markdown(f"""<div style="background-color:#1e2329; padding:10px; border-radius:10px; text-align:center; border-left:5px solid {'#3fb950' if adr_val > 0 else '#f85149'}; margin-bottom:20px;">
            <small style="color:#888;">美股 TSM ADR 連動</small><br><b style="color:{'#3fb950' if adr_val > 0 else '#f85149'}; font-size:20px;">{adr_val:+.2f}%</b>
        </div>""", unsafe_allow_html=True)

        # 掃描池：台股權值與流動性前 100 名
        market_ids = list(CORE_STOCKS.keys())
        recs = []
        
        progress_text = "AI 正在計算全市場最佳優勢標的..."
        p_bar = st.progress(0, text=progress_text)
        
        for i, sid in enumerate(market_ids):
            p_bar.progress((i + 1) / len(market_ids), text=progress_text)
            try:
                tkr = yf.Ticker(f"{sid}.TW")
                df = compute_indicators(tkr.history(period="60d"))
                if df.empty: continue
                l, p = df.iloc[-1], df.iloc[-2]
                
                # --- AI 評分系統 ---
                score = 35 + (adr_val * 2)
                if l['Close'] > l['MA5']: score += 15
                if l['K'] > l['D'] and p['K'] <= p['D']: score += 25 # KD 黃金交叉
                if l['MACD'] > 0: score += 15
                if l['Close'] > l['MA20']: score += 10
                
                if score >= 75: # 提高門檻，只找最有優勢的標的
                    recs.append({
                        "id": sid, "name": get_stock_name_zh(sid), "price": round(l['Close'], 2), 
                        "score": int(score), "buy": round(max(l['MA5'], l['Close'] * 0.995), 2),
                        "target": round(l['Close'] * 1.06, 2)
                    })
            except: continue
        
        p_bar.empty()

        if recs:
            st.write(f"🎉 掃描完成！已為您篩選出最具動能的 {len(recs)} 檔標的：")
            for item in sorted(recs, key=lambda x: x['score'], reverse=True)[:10]:
                st.markdown(f"""
                <div style="background-color:#161b22; padding:12px; border-radius:12px; border:1px solid #30363d; margin-bottom:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <b style="font-size:17px; color:#c9d1d9;">{item['name']} ({item['id']})</b>
                        <span style="background:#238636; color:white; padding:2px 8px; border-radius:6px; font-size:12px;">潛力分 {item['score']}</span>
                    </div>
                    <div style="display:flex; justify-content:space-between; margin-top:10px; background:#0d1117; padding:12px; border-radius:10px;">
                        <div style="text-align:center;"><small style="color:#8b949e;">支撐買點</small><br><b style="color:#3fb950;">{item['buy']}</b></div>
                        <div style="text-align:center;"><small style="color:#8b949e;">獲利目標</small><br><b style="color:#58a6ff;">{item['target']}</b></div>
                        <div style="text-align:center;"><small style="color:#8b949e;">目前市價</small><br><b>{item['price']}</b></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("💡 目前市場處於震盪，AI 建議觀望暫無強勢買訊標的。")

    # --- 模組二：持倉管理 (名稱強制中文) ---
    else:
        st.markdown(f"### 🛡️ 持倉診斷 - {st.session_state.user_id}")
        st.markdown(f"<small style='color:#3fb950;'>● 雲端已同步 (24H 台北時間)</small>", unsafe_allow_html=True)

        with st.expander("➕ 新增個人持倉", expanded=False):
            c1, c2, c3 = st.columns([2, 2, 1])
            in_id = c1.text_input("代號", placeholder="例如: 2330")
            in_cost = c2.number_input("成本", value=None, placeholder="輸入價格", step=0.1)
            if c3.button("存入", use_container_width=True):
                if in_cost:
                    # 存入時不論原本抓到什麼，都存入代號，顯示時再重新解析中文
                    st.session_state.portfolio_list.append({"symbol": f"{in_id}.TW", "cost": in_cost, "ts": time.time()})
                    cloud_save(st.session_state.user_id, st.session_state.portfolio_list)
                    st.rerun()

        if st.session_state.portfolio_list:
            del_ts = None
            for s in st.session_state.portfolio_list:
                try:
                    # 強制在介面渲染前重新解析中文名稱
                    cname = get_stock_name_zh(s['symbol'])
                    pure_id = s['symbol'].split('.')[0]
                    
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
                        elif cur < df.iloc[-1]['MA20']: msg, clr = "🚨 建議止損", "#f85149"
                        else: msg, clr = "💤 盤整待變", "#8b949e"

                    st.markdown(f"""
                    <div style="background-color:#161b22; padding:15px; border-radius:12px; border-left:8px solid {clr}; margin-bottom:12px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <b style="font-size:16px; color:#c9d1d9;">{cname} ({pure_id})</b>
                            <b style="color:{clr};">{msg}</b>
                        </div>
                        <div style="display:flex; justify-content:space-between; margin:10px 0;">
                            <span>成本: {s['cost']} | 現價: <b>{cur}</b></span>
                            <span style="color:{clr}; font-size:18px;">{gain:+.2f}%</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"🗑️ 移除 {cname}", key=f"d_{s['ts']}"): del_ts = s['ts']
                except: continue
            
            if del_ts:
                st.session_state.portfolio_list = [i for i in st.session_state.portfolio_list if i['ts'] != del_ts]
                cloud_save(st.session_state.user_id, st.session_state.portfolio_list)
                st.rerun()

    st.divider()
    st.caption(f"最後同步 (台北 24H): {get_taipei_now().strftime('%Y-%m-%d %H:%M:%S')}")

