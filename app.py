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

# --- 0. 台北時間工具 ---
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
    except: return None
    return None

db = init_db()
app_id = st.secrets.get("general", {}).get("app_id", "stock_ai_v3")

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

# --- 3. 登入管理 (URL 參數自動記憶) ---
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

# --- 4. AI 廣域掃描引擎 ---

@st.cache_data(ttl=86400)
def get_clean_cname(symbol):
    """獲取繁體中文名稱"""
    pure_id = symbol.split('.')[0]
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={pure_id}&lang=zh-Hant-TW&region=TW"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        quotes = res.json().get('quotes', [])
        for q in quotes:
            if q.get('symbol').startswith(pure_id):
                return (q.get('shortname') or q.get('longname') or pure_id).replace("Ordinary Shares", "").strip()
    except: pass
    return symbol

def compute_indicators(df):
    if len(df) < 35: return df
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    l9, h9 = df['Low'].rolling(window=9).min(), df['High'].rolling(window=9).max()
    df['K'] = ((df['Close'] - l9) / (h9 - l9) * 100).ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()
    e12, e26 = df['Close'].ewm(span=12).mean(), df['Close'].ewm(span=26).mean()
    df['MACD'] = (e12 - e26 - (e12 - e26).ewm(span=9).mean()) * 2
    return df

@st.cache_data(ttl=3600)
def get_market_sentiment():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return round(((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100, 2)
    except: return 0.0

@st.cache_data(ttl=43200)
def fetch_broad_market_pool():
    """模擬全市場掃描：動態生成台股流動性最強的 150 檔標的池"""
    # 這裡包含 0050, 0051 以及市場成交量常客
    base_ids = [
        "2330","2317","2454","2382","2308","2412","2881","2882","2303","3711",
        "2886","2891","1301","1216","2002","2409","3481","2603","2609","2618",
        "2357","3231","4938","2379","3034","3037","2324","2353","2408","3008",
        "2301","2344","2892","2880","2884","2885","2887","5880","2890","1101",
        "1303","1326","2105","2207","2912","3045","6505","9910","9921","1402",
        "1503","1513","1519","1605","1722","1773","2104","2201","2360","2371",
        "2376","2377","2383","2385","2395","2449","2451","2458","2474","2492",
        "2498","2606","2610","2615","2727","2903","3017","3023","3044","3532",
        "3653","4958","5871","5876","6239","6285","6415","6669","8046","8454",
        "9904","9945","2345","3533","2313","2355","2471","3019","5269","6409"
    ]
    return list(set(base_ids))

# --- 5. 介面渲染 ---

if not st.session_state.authenticated:
    st.markdown("<div style='height: 80px;'></div>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center; color: #58a6ff;'>🚀 AI 實戰選股中心</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #8b949e;'>輸入通行碼即可開啟 AI 廣域掃描</p>", unsafe_allow_html=True)
    login_id = st.text_input("通行碼", placeholder="例如: AlexTrade", label_visibility="collapsed")
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
    mode = st.sidebar.radio("功能模式", ["🔎 全市場潛力掃描", "🛡️ 雲端持倉診斷"])
    
    adr_val = get_market_sentiment()

    # --- 模組一：AI 廣域掃描 ---
    if mode == "🔎 全市場潛力掃描":
        st.markdown(f"### 🔎 市場潛力買訊掃描")
        st.markdown(f"""<div style="background-color:#1e2329; padding:10px; border-radius:10px; text-align:center; border-left:5px solid {'#3fb950' if adr_val > 0 else '#f85149'}; margin-bottom:20px;">
            <small style="color:#888;">美股 TSM ADR 連動強度</small><br><b style="color:{'#3fb950' if adr_val > 0 else '#f85149'}; font-size:20px;">{adr_val:+.2f}%</b>
        </div>""", unsafe_allow_html=True)

        # 獲取動態池
        market_pool = fetch_broad_market_pool()
        recs = []
        
        # 使用進度條，因為掃描 100+ 檔需要一點時間
        progress_text = "AI 正在掃描全市場最強買訊標的..."
        my_bar = st.progress(0, text=progress_text)
        
        for i, sid in enumerate(market_pool):
            my_bar.progress((i + 1) / len(market_pool), text=progress_text)
            try:
                tkr = yf.Ticker(f"{sid}.TW")
                df = compute_indicators(tkr.history(period="60d"))
                if df.empty or len(df) < 20: continue
                l, p = df.iloc[-1], df.iloc[-2]
                
                # --- AI 深度評分系統 ---
                score = 30 + (adr_val * 2) # 基礎分
                if l['Close'] > l['MA5']: score += 15
                if l['Close'] > l['MA20']: score += 10
                if l['K'] > l['D'] and p['K'] <= p['D']: score += 25 # KD 黃金交叉
                if l['MACD'] > 0: score += 10
                if l['Close'] > p['Close'] and l['Volume'] > df['Volume'].mean(): score += 10 # 價量齊揚
                
                # 門檻：只有 70 分以上 (代表多頭動能強勁) 的才錄取
                if score >= 70:
                    cname = get_clean_cname(sid)
                    recs.append({
                        "id": sid, "name": cname, "price": round(l['Close'], 2), 
                        "score": int(score), "buy": round(max(l['MA5'], l['Close'] * 0.995), 2),
                        "target": round(l['Close'] * 1.05, 2)
                    })
            except: continue
        
        my_bar.empty() # 掃描完畢清空進度條

        if recs:
            st.write(f"🎉 已為您在市場中篩選出 {len(recs)} 檔高潛力標的：")
            # 按分數排序並取前 12 檔
            for item in sorted(recs, key=lambda x: x['score'], reverse=True)[:12]:
                st.markdown(f"""
                <div style="background-color:#161b22; padding:12px; border-radius:10px; border:1px solid #30363d; margin-bottom:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <b style="font-size:16px; color:#c9d1d9;">{item['name']} ({item['id']})</b>
                        <span style="background:#238636; color:white; padding:2px 8px; border-radius:5px; font-size:12px;">潛力分 {item['score']}</span>
                    </div>
                    <div style="display:flex; justify-content:space-between; margin-top:8px; background:#0d1117; padding:10px; border-radius:8px;">
                        <div style="text-align:center;"><small style="color:#8b949e;">支撐買點</small><br><b style="color:#3fb950;">{item['buy']}</b></div>
                        <div style="text-align:center;"><small style="color:#8b949e;">首波目標</small><br><b style="color:#58a6ff;">{item['target']}</b></div>
                        <div style="text-align:center;"><small style="color:#8b949e;">現價</small><br><b>{item['price']}</b></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("💡 目前市場標的偏向整理，暫無高分買訊，請保持耐心。")

    # --- 模組二：持倉管理 ---
    else:
        st.markdown(f"### 🛡️ 持倉雲端診斷 - {st.session_state.user_id}")
        st.markdown(f"<small style='color:#3fb950;'>● 雲端已同步 (台北 24H)</small>", unsafe_allow_html=True)

        with st.expander("➕ 新增持倉記錄", expanded=False):
            c1, c2, c3 = st.columns([2, 2, 1])
            in_id = c1.text_input("代號", placeholder="例如: 2330")
            in_cost = c2.number_input("成本", value=None, placeholder="輸入價格", step=0.1)
            if c3.button("存入", use_container_width=True):
                if in_cost:
                    cname = get_clean_cname(in_id)
                    st.session_state.portfolio_list.append({
                        "symbol": f"{in_id}.TW", "name": cname, 
                        "cost": in_cost, "ts": time.time()
                    })
                    cloud_save(st.session_state.user_id, st.session_state.portfolio_list)
                    st.rerun()

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
                        elif cur < df.iloc[-1]['MA20']: msg, clr = "🚨 建議止損", "#f85149"
                        else: msg, clr = "💤 盤整待變", "#8b949e"

                    st.markdown(f"""
                    <div style="background-color:#161b22; padding:15px; border-radius:12px; border-left:8px solid {clr}; margin-bottom:12px;">
                        <div style="display:flex; justify-content:space-between;">
                            <b>{display_name} ({s['symbol'].split('.')[0]})</b>
                            <b style="color:{clr};">{msg}</b>
                        </div>
                        <div style="display:flex; justify-content:space-between; margin:10px 0;">
                            <span>成本: {s['cost']} | 現價: <b>{cur}</b></span>
                            <span style="color:{clr}; font-size:18px;">{gain:+.2f}%</span>
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
    now_tp = get_taipei_now()
    st.caption(f"最後同步 (台北 24H): {now_tp.strftime('%Y-%m-%d %H:%M:%S')}")

