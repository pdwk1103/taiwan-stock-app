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

# --- 0. 台北時間工具 (24H 台北時間) ---
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
    except Exception:
        return None
    return None

db = init_db()
app_id = st.secrets.get("general", {}).get("app_id", "stock_ai_v3")

# --- 2. 雲端同步邏輯 ---
def cloud_save(uid, data):
    if not db or not uid: return False
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("users").document(uid).collection("portfolio").document("data")
        doc_ref.set({"items": data, "last_updated": get_taipei_now(), "user_id": uid})
        return True
    except Exception:
        return False

def cloud_load(uid):
    if not db or not uid: return []
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("users").document(uid).collection("portfolio").document("data")
        doc = doc_ref.get()
        return doc.to_dict().get("items", []) if doc.exists else []
    except Exception:
        return []

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

# --- 4. AI 多維度量化分析引擎 ---

def get_multi_dimension_score(ticker_obj, df, adr_val):
    """
    多維度評分系統：
    1. 技術面 (MA, KD, MACD) - 50%
    2. 量能面 (Volume) - 20%
    3. 基本面 (PE, Yield, EPS) - 30%
    """
    if len(df) < 35: return 0, 0, 0, "N/A"
    
    l, p = df.iloc[-1], df.iloc[-2]
    info = ticker_obj.info
    
    # --- A. 技術與量能評分 (盲測核心) ---
    tech_score = 30 + (adr_val * 2) 
    if l['Close'] > l['MA5']: tech_score += 10
    if l['K'] > l['D'] and p['K'] <= p['D']: tech_score += 20 # 黃金交叉
    if l['MACD'] > 0: tech_score += 10
    if l['Volume'] > df['Volume'].tail(20).mean() * 1.2: tech_score += 10 # 量能噴發
    
    # --- B. 基本面評分 (增加穩定性) ---
    fund_score = 0
    pe = info.get('trailingPE', 100)
    dy = info.get('dividendYield', 0)
    
    if pe < 25: fund_score += 10   # 估值合理
    if dy and dy > 0.03: fund_score += 5 # 殖利率 > 3%
    if info.get('forwardEps', 0) > info.get('trailingEps', 0): fund_score += 5 # 獲利成長中
    
    total_score = tech_score + fund_score
    
    # 決定推薦等級
    rank = "⚡ 強力推薦" if total_score >= 85 else "✅ 建議布局" if total_score >= 70 else "觀察"
    
    buy_p = round(max(l['MA5'], l['Close'] * 0.99), 2)
    target_p = round(l['Close'] * 1.06, 2)
    
    return int(total_score), buy_p, target_p, rank

@st.cache_data(ttl=86400)
def fetch_zh_name(symbol):
    """選美結束後的名稱標籤配對"""
    pure_id = symbol.split('.')[0]
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={pure_id}&lang=zh-Hant-TW&region=TW"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        quotes = res.json().get('quotes', [])
        for q in quotes:
            if q.get('symbol').startswith(pure_id):
                return (q.get('shortname') or q.get('longname') or pure_id).split(' ')[0]
    except: pass
    return pure_id

def apply_indicators(df):
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
def get_adr_sentiment():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return round(((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100, 2)
    except: return 0.0

@st.cache_data(ttl=43200)
def get_scan_pool():
    """廣域掃描池：台股 300 檔權值與熱門標的代號"""
    ids = [
        "2330","2317","2454","2382","2308","2412","2881","2882","2303","3711",
        "2886","2891","1301","1216","2002","2409","3481","2603","2609","2618",
        "2357","3231","4938","2379","3034","3037","2324","2353","2408","3008",
        "1503","1513","1519","1605","2449","3017","3653","4958","5871","6669",
        "2313","2451","2458","2492","2727","3533","5483","6239","8936","2352"
    ]
    # 這裡可繼續擴充至 300 檔...
    return sorted(list(set(ids)))

# --- 5. 介面渲染 ---

if not st.session_state.authenticated:
    st.markdown("<div style='height: 80px;'></div>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center; color: #58a6ff;'>🚀 AI 實戰選股中心</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #8b949e;'>數據優先、全市場盲測、多維度分析</p>", unsafe_allow_html=True)
    login_id = st.text_input("通行碼", placeholder="例如: MyStockAI", label_visibility="collapsed")
    if st.button("確認登入並同步", use_container_width=True, type="primary"):
        handle_login(login_id)
    st.stop()

else:
    st.sidebar.title("👤 帳號管理")
    st.sidebar.info(f"使用者: `{st.session_state.user_id}`")
    if st.sidebar.button("登出系統"):
        st.session_state.authenticated = False
        st.query_params.clear()
        st.rerun()
    st.sidebar.divider()
    mode = st.sidebar.radio("切換功能", ["🔎 全市場潛力選拔", "🛡️ 雲端持倉診斷"])
    
    adr_val = get_adr_sentiment()

    if mode == "🔎 全市場潛力選拔":
        st.markdown(f"### 🔎 AI 多維度量化掃描")
        st.markdown(f"""<div style="background-color:#1e2329; padding:10px; border-radius:10px; text-align:center; border-left:5px solid {'#3fb950' if adr_val > 0 else '#f85149'}; margin-bottom:20px;">
            <small style="color:#888;">美股 TSM ADR 市場情緒</small><br><b style="color:{'#3fb950' if adr_val > 0 else '#f85149'}; font-size:20px;">{adr_val:+.2f}%</b>
        </div>""", unsafe_allow_html=True)

        pool = get_scan_pool()
        winners = []
        p_text = f"AI 正在對全市場標的進行技術與基本面多維度運算..."
        p_bar = st.progress(0, text=p_text)
        
        for i, sid in enumerate(pool):
            p_bar.progress((i + 1) / len(pool), text=p_text)
            try:
                tkr = yf.Ticker(f"{sid}.TW")
                hist = tkr.history(period="60d")
                if hist.empty or len(hist) < 30: continue
                
                df = apply_indicators(hist)
                score, buy, target, rank = get_multi_dimension_score(tkr, df, adr_val)
                
                if score >= 70:
                    winners.append({"id": sid, "price": round(df.iloc[-1]['Close'], 2), "score": score, "buy": buy, "target": target, "rank": rank})
            except: continue
        
        p_bar.empty()

        if winners:
            st.write(f"🎉 掃描完成！篩選出 {len(winners)} 檔高潛力優勢標的：")
            for item in sorted(winners, key=lambda x: x['score'], reverse=True)[:12]:
                cname = fetch_zh_name(item['id'])
                st.markdown(f"""
                <div style="background-color:#161b22; padding:12px; border-radius:12px; border:1px solid #30363d; margin-bottom:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <b style="font-size:17px; color:#c9d1d9;">{cname} ({item['id']})</b>
                        <span style="background:#238636; color:white; padding:2px 8px; border-radius:6px; font-size:12px;">量化分 {item['score']}</span>
                    </div>
                    <div style="margin-top:5px;"><small style="color:#3fb950; font-weight:bold;">{item['rank']}</small></div>
                    <div style="display:flex; justify-content:space-between; margin-top:10px; background:#0d1117; padding:12px; border-radius:10px;">
                        <div style="text-align:center;"><small style="color:#8b949e;">支撐買點</small><br><b style="color:#3fb950;">{item['buy']}</b></div>
                        <div style="text-align:center;"><small style="color:#8b949e;">預期目標</small><br><b style="color:#58a6ff;">{item['target']}</b></div>
                        <div style="text-align:center;"><small style="color:#8b949e;">現價</small><br><b>{item['price']}</b></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("💡 目前市場標的偏向整理，尚未發現符合量化優勢門檻的買訊。")

    else:
        st.markdown(f"### 🛡️ 雲端持倉實戰診斷")
        st.markdown(f"<small style='color:#3fb950;'>● 雲端資料同步中 (24H 台北時間)</small>", unsafe_allow_html=True)

        with st.expander("➕ 新增個人持倉記錄", expanded=False):
            c1, c2, c3 = st.columns([2, 2, 1])
            in_id = c1.text_input("代號", placeholder="例如: 2330")
            in_cost = c2.number_input("平均成本", value=None, placeholder="輸入價格", step=0.1)
            if c3.button("存入", use_container_width=True):
                if in_cost:
                    st.session_state.portfolio_list.append({"symbol": f"{in_id}.TW", "cost": in_cost, "ts": time.time()})
                    cloud_save(st.session_state.user_id, st.session_state.portfolio_list)
                    st.rerun()

        if st.session_state.portfolio_list:
            del_ts = None
            for s in st.session_state.portfolio_list:
                try:
                    p_id = s['symbol'].split('.')[0]
                    cname = fetch_zh_name(p_id)
                    tkr = yf.Ticker(s['symbol'])
                    df = apply_indicators(tkr.history(period="60d"))
                    l = df.iloc[-1]
                    cur = round(l['Close'], 2)
                    gain = ((cur - s['cost']) / s['cost']) * 100
                    
                    msg, clr = "", "#ffffff"
                    if gain > 0:
                        if l['MACD'] > 0: msg, clr = "🚀 強勢續留", "#3fb950"
                        else: msg, clr = "⚠️ 建議減碼", "#f0883e"
                    else:
                        if l['MACD'] > 0: msg, clr = "💪 低檔轉強", "#58a6ff"
                        elif cur < df.iloc[-1]['MA20']: msg, clr = "🚨 果斷止損", "#f85149"
                        else: msg, clr = "💤 盤整待變", "#8b949e"

                    st.markdown(f"""
                    <div style="background-color:#161b22; padding:15px; border-radius:12px; border-left:8px solid {clr}; margin-bottom:12px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <b style="font-size:16px; color:#c9d1d9;">{cname} ({p_id})</b>
                            <b style="color:{clr};">{msg}</b>
                        </div>
                        <div style="display:flex; justify-content:space-between; margin:10px 0;">
                            <span>成本: {s['cost']} | 現價: <b>{cur}</b></span>
                            <span style="color:{clr}; font-size:18px; font-weight:bold;">{gain:+.2f}%</span>
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
    now_tp = get_taipei_now()
    st.caption(f"最後同步 (台北時間 24H): {now_tp.strftime('%Y-%m-%d %H:%M:%S')}")

