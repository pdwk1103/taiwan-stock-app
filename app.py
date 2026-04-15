import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import time
from datetime import datetime, timedelta, timezone
from google.cloud import firestore
from google.oauth2 import service_account

# --- 頁面配置 (iPhone 使用體驗優化) ---
st.set_page_config(page_title="台股 AI 雲端實戰", layout="centered", initial_sidebar_state="collapsed")

# --- 0. 台北時間工具 (24H 台北時間) ---
def get_taipei_now():
    """獲取目前的台北時間 (UTC+8)"""
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz)

# --- 1. Firebase / Firestore 初始化 ---
@st.cache_resource
def init_db():
    try:
        if "firebase" in st.secrets:
            creds_dict = dict(st.secrets["firebase"])
            # 修正私鑰換行符號問題
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = service_account.Credentials.from_service_account_info(creds_dict)
            return firestore.Client(credentials=creds)
    except: return None
    return None

db = init_db()
app_id = st.secrets.get("general", {}).get("app_id", "stock_ai_v3")

# --- 2. 雲端字典預設內容 (用於第一次初始化) ---
DEFAULT_CORE_MAP = {
    "2330":"台積電","2317":"鴻海","2454":"聯發科","2382":"廣達","2308":"台達電",
    "2303":"聯電","2881":"富邦金","2882":"國泰金","2886":"兆豐金","2891":"中信金",
    "3711":"日月光投控","2412":"中華電","1301":"台塑","1216":"統一","2002":"中鋼",
    "2603":"長榮","2609":"陽明","2618":"長榮航","2357":"華碩","3231":"緯創",
    "3008":"大立光","2449":"京元電子","1513":"中興電","1519":"華城","1605":"華新",
    "2376":"技嘉","2377":"微星","3017":"奇鋐","3231":"緯創","2353":"宏碁"
}

# --- 3. 雲端資料庫操作函式 ---

@st.cache_data(ttl=43200)
def get_cloud_directory():
    """獲取雲端全台股對照表"""
    if not db: return {}
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("public").document("data").collection("directory").document("all_stocks")
        doc = doc_ref.get()
        return doc.to_dict().get("mapping", {}) if doc.exists else {}
    except: return {}

def save_to_cloud_directory(symbol, name):
    """【觸發點 A】當 App 發現新股票時，自動非同步更新雲端字典"""
    if not db: return
    try:
        pure_id = symbol.split('.')[0]
        doc_ref = db.collection("artifacts").document(app_id).collection("public").document("data").collection("directory").document("all_stocks")
        # 使用 update 並利用點號表示法更新特定欄位，不覆蓋整份文件
        doc_ref.update({f"mapping.{pure_id}": name})
    except:
        # 如果文件不存在則建立
        doc_ref.set({"mapping": {pure_id: name}, "last_updated": get_taipei_now()}, merge=True)

def cloud_save_portfolio(uid, data):
    """【觸發點 B】當使用者手動點擊「存入持倉」時觸發"""
    if not db or not uid: return False
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("users").document(uid).collection("portfolio").document("data")
        doc_ref.set({"items": data, "last_updated": get_taipei_now(), "user_id": uid})
        return True
    except: return False

def cloud_load_portfolio(uid):
    if not db or not uid: return []
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("users").document(uid).collection("portfolio").document("data")
        doc = doc_ref.get()
        return doc.to_dict().get("items", []) if doc.exists else []
    except: return []

# --- 4. 登入與導航 ---
if "user_id" not in st.session_state:
    qp = st.query_params
    if "uid" in qp:
        st.session_state.user_id = qp["uid"]
        st.session_state.authenticated = True
        st.session_state.portfolio_list = cloud_load_portfolio(qp["uid"])
    else:
        st.session_state.authenticated = False
        st.session_state.user_id = ""

def handle_login(uid):
    uid = uid.strip()
    if uid:
        st.session_state.user_id = uid
        st.session_state.authenticated = True
        st.session_state.portfolio_list = cloud_load_portfolio(uid)
        st.query_params["uid"] = uid 
        st.rerun()

# --- 5. 名稱與技術分析引擎 ---

def get_zh_name_mapped(symbol, directory):
    """選美後映射中文：若無則抓取並觸發雲端儲存"""
    pure_id = symbol.split('.')[0]
    if pure_id in directory:
        return directory[pure_id]
    
    # 即時抓取備案
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={pure_id}&lang=zh-Hant-TW&region=TW"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        quotes = res.json().get('quotes', [])
        for q in quotes:
            if q.get('symbol').startswith(pure_id):
                name = (q.get('shortname') or q.get('longname') or pure_id).split(' ')[0].split('(')[0]
                # 這裡就是自動儲存到雲端的觸發點
                save_to_cloud_directory(pure_id, name)
                return name
    except: pass
    return pure_id

def compute_factors(df, adr):
    if len(df) < 30: return 0, 0, 0, "觀察"
    l, p = df.iloc[-1], df.iloc[-2]
    score = 35 + (adr * 2.5)
    if l['Close'] > l['MA5']: score += 15
    if l['K'] > l['D'] and p['K'] <= p['D']: score += 20
    if l['MACD'] > 0: score += 15
    if l['Volume'] > df['Volume'].tail(10).mean() * 1.2: score += 15
    rank = "⚡ 強力推薦" if score >= 85 else "✅ 建議布局" if score >= 70 else "整理中"
    buy = round(max(l['MA5'], l['Close'] * 0.993), 2)
    target = round(l['Close'] * 1.055, 2)
    return int(score), buy, target, rank

def apply_tech_logic(df):
    if len(df) < 30: return df
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
    st.markdown("<h1 style='text-align: center; color: #58a6ff;'>🚀 AI 實戰選股中心</h1>", unsafe_allow_html=True)
    login_id = st.text_input("通行碼", placeholder="請輸入您的個人通行碼", label_visibility="collapsed")
    if st.button("登入系統", use_container_width=True, type="primary"):
        handle_login(login_id)
    st.stop()

else:
    # 預載雲端字典
    cloud_dir = get_cloud_directory()
    
    st.sidebar.title("👤 帳號中心")
    st.sidebar.info(f"帳號: `{st.session_state.user_id}`")
    
    # 新增功能：手動同步全台股字典
    if st.sidebar.button("🔄 初始化雲端中文字典"):
        with st.spinner("正在同步核心標的至雲端..."):
            doc_ref = db.collection("artifacts").document(app_id).collection("public").document("data").collection("directory").document("all_stocks")
            doc_ref.set({"mapping": DEFAULT_CORE_MAP, "last_updated": get_taipei_now()}, merge=True)
            st.sidebar.success("同步成功！")
            time.sleep(1)
            st.rerun()

    if st.sidebar.button("登出帳號"):
        st.session_state.authenticated = False
        st.query_params.clear()
        st.rerun()
    
    st.sidebar.divider()
    mode = st.sidebar.radio("切換模式", ["🔎 全市場潛力掃描", "🛡️ 雲端持倉診斷"])
    adr_val = get_adr()

    if mode == "🔎 全市場潛力掃描":
        st.markdown(f"### 🔎 市場量化優勢選拔")
        st.markdown(f"""<div style="background-color:#1e2329; padding:10px; border-radius:10px; text-align:center; border-left:5px solid {'#3fb950' if adr_val > 0 else '#f85149'}; margin-bottom:20px;">
            <small style="color:#888;">美股 TSM ADR 市場氛圍</small><br><b style="color:{'#3fb950' if adr_val > 0 else '#f85149'}; font-size:20px;">{adr_val:+.2f}%</b>
        </div>""", unsafe_allow_html=True)

        scan_pool = [
            "2330","2317","2454","2382","2308","2449","2603","2609","2618","2303","3008","2881",
            "2882","2891","3711","2357","3231","4938","2379","3034","3037","1503","1513","1519",
            "1605","1101","2002","2409","3481","2610","1504","1514","2327","2376","3035","3406",
            "3443","3661","5269","6409","6446","6472","6488","8299","9958"
        ]
        
        winners = []
        p_text = f"AI 正在對全場域標的進行數據盲測..."
        p_bar = st.progress(0, text=p_text)
        
        for i, sid in enumerate(scan_pool):
            p_bar.progress((i + 1) / len(scan_pool), text=p_text)
            try:
                tkr = yf.Ticker(f"{sid}.TW")
                hist = tkr.history(period="60d")
                if hist.empty or len(hist) < 25: continue
                
                df = apply_tech_logic(hist)
                score, buy, target, rank = compute_factors(df, adr_val)
                
                if score >= 70:
                    winners.append({"id": sid, "price": round(df.iloc[-1]['Close'], 2), "score": score, "buy": buy, "target": target, "rank": rank})
            except: continue
        
        p_bar.empty()

        if winners:
            st.write(f"🎉 篩選出 {len(winners)} 檔高潛力標的：")
            for item in sorted(winners, key=lambda x: x['score'], reverse=True)[:12]:
                zh_name = get_zh_name_mapped(item['id'], cloud_dir)
                st.markdown(f"""
                <div style="background-color:#161b22; padding:12px; border-radius:12px; border:1px solid #30363d; margin-bottom:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <b style="font-size:17px; color:#c9d1d9;">{zh_name} ({item['id']})</b>
                        <span style="background:#238636; color:white; padding:2px 8px; border-radius:6px; font-size:12px;">量化分 {item['score']}</span>
                    </div>
                    <div style="margin-top:5px;"><small style="color:#3fb950; font-weight:bold;">{item['rank']}</small></div>
                    <div style="display:flex; justify-content:space-between; margin-top:10px; background:#0d1117; padding:12px; border-radius:10px;">
                        <div style="text-align:center;"><small style="color:#8b949e;">支撐買點</small><br><b style="color:#3fb950;">{item['buy']}</b></div>
                        <div style="text-align:center;"><small style="color:#8b949e;">獲利目標</small><br><b style="color:#58a6ff;">{item['target']}</b></div>
                        <div style="text-align:center;"><small style="color:#8b949e;">現價</small><br><b>{item['price']}</b></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

    else:
        st.markdown(f"### 🛡️ 雲端持倉實戰診斷")
        st.markdown(f"<small style='color:#3fb950;'>● 雲端資料同步中 (24H 台北時間)</small>", unsafe_allow_html=True)

        with st.expander("➕ 新增個人持倉記錄", expanded=False):
            c1, c2, c3 = st.columns([2, 2, 1])
            in_id = c1.text_input("代號", placeholder="例如: 2449")
            in_cost = c2.number_input("平均成本", value=None, placeholder="輸入價格", step=0.1)
            if c3.button("存入", use_container_width=True):
                if in_cost:
                    st.session_state.portfolio_list.append({"symbol": f"{in_id}.TW", "cost": in_cost, "ts": time.time()})
                    cloud_save_portfolio(st.session_state.user_id, st.session_state.portfolio_list)
                    st.rerun()

        if st.session_state.portfolio_list:
            del_ts = None
            for s in st.session_state.portfolio_list:
                try:
                    p_id = s['symbol'].split('.')[0]
                    c_name = get_zh_name_mapped(p_id, cloud_dir)
                    tkr = yf.Ticker(s['symbol'])
                    df = apply_tech_logic(tkr.history(period="60d"))
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
                            <b style="font-size:16px; color:#c9d1d9;">{c_name} ({p_id})</b>
                            <b style="color:{clr};">{msg}</b>
                        </div>
                        <div style="display:flex; justify-content:space-between; margin:10px 0;">
                            <span>成本: {s['cost']} | 現價: <b>{cur}</b></span>
                            <span style="color:{clr}; font-size:18px; font-weight:bold;">{gain:+.2f}%</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"🗑️ 移除 {c_name}", key=f"d_{s['ts']}"): del_ts = s['ts']
                except: continue
            
            if del_ts:
                st.session_state.portfolio_list = [i for i in st.session_state.portfolio_list if i['ts'] != del_ts]
                cloud_save_portfolio(st.session_state.user_id, st.session_state.portfolio_list)
                st.rerun()

    st.divider()
    now_tp = get_taipei_now()
    st.caption(f"最後同步 (台北時間 24H): {now_tp.strftime('%Y-%m-%d %H:%M:%S')}")

