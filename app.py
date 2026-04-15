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

# --- 0. 台北時間工具 (24H 格式) ---
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
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = service_account.Credentials.from_service_account_info(creds_dict)
            return firestore.Client(credentials=creds)
    except Exception:
        return None
    return None

db = init_db()
app_id = st.secrets.get("general", {}).get("app_id", "stock_ai_v3")

# --- 2. 雲端總表管理 (Master Directory) ---

def load_master_directory():
    """從雲端讀取全市場對照表"""
    if not db: return {}
    try:
        # 遵循 Rule 1 路徑
        doc_ref = db.collection("artifacts").document(app_id).collection("public").document("data").collection("directory").document("master_list")
        doc = doc_ref.get()
        return doc.to_dict().get("mapping", {}) if doc.exists else {}
    except:
        return {}

def save_master_directory(mapping):
    """將全市場對照表存回雲端"""
    if not db: return False
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("public").document("data").collection("directory").document("master_list")
        doc_ref.set({
            "mapping": mapping,
            "last_updated": get_taipei_now(),
            "count": len(mapping)
        }, merge=True)
        return True
    except:
        return False

@st.cache_data(ttl=86400)
def fetch_stock_name_online(symbol):
    """即時從網路獲取個股繁體中文名"""
    pure_id = symbol.split('.')[0]
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={pure_id}&lang=zh-Hant-TW&region=TW"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            quotes = res.json().get('quotes', [])
            for q in quotes:
                if q.get('symbol').startswith(pure_id):
                    name = q.get('shortname') or q.get('longname') or pure_id
                    return name.split(' ')[0].split('(')[0].strip()
    except: pass
    return pure_id

# --- 3. 雲端同步與登入管理 ---
def cloud_save_portfolio(uid, data):
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

# --- 4. AI 廣域分析引擎 ---

def compute_quant_score(df, adr_val):
    if len(df) < 30: return 0, 0, 0, "N/A"
    l, p = df.iloc[-1], df.iloc[-2]
    score = 35 + (adr_val * 2.2)
    if l['Close'] > l['MA5']: score += 15
    if l['K'] > l['D'] and p['K'] <= p['D']: score += 20
    if l['MACD'] > 0: score += 15
    if l['Volume'] > df['Volume'].tail(15).mean() * 1.1: score += 15
    
    rank = "⚡ 強力推薦" if score >= 85 else "✅ 建議布局" if score >= 70 else "整理"
    buy = round(max(l['MA5'], l['Close'] * 0.994), 2)
    target = round(l['Close'] * 1.055, 2)
    return int(score), buy, target, rank

def apply_tech(df):
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

# --- 5. 介面渲染 ---

if not st.session_state.authenticated:
    st.markdown("<div style='height: 80px;'></div>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center; color: #58a6ff;'>🚀 AI 實戰選股中心</h1>", unsafe_allow_html=True)
    login_id = st.text_input("通行碼", placeholder="請輸入通行碼", label_visibility="collapsed")
    if st.button("確認登入並同步", use_container_width=True, type="primary"):
        handle_login(login_id)
    st.stop()

else:
    # 啟動時先載入雲端總表到記憶體
    if "master_dir" not in st.session_state:
        st.session_state.master_dir = load_master_directory()

    st.sidebar.title("👤 帳號管理")
    st.sidebar.info(f"帳號: `{st.session_state.user_id}`")
    
    # --- 重要：初始化總表功能 ---
    with st.sidebar.expander("⚙️ 雲端總表維護"):
        if st.button("🔄 建立/更新全市場總表"):
            with st.spinner("正在掃描全台股清單並同步雲端..."):
                # 這裡預設一個大範圍的核心清單
                base_pool = [
                    "2330","2317","2454","2382","2308","2449","2603","2609","2618","2303","3008","2881",
                    "2882","2891","3711","2357","3231","4938","2379","3034","3037","1503","1513","1519",
                    "1605","1101","2002","2409","3481","2610","1504","1514","2327","2376","3035","3406",
                    "3443","3661","5269","6409","6446","6472","6488","8299","9958","2313","2451","2458",
                    "2492","2727","3533","5483","6239","8936","2352","3017","3653","4958","5871","6669"
                ]
                new_map = st.session_state.master_dir.copy()
                for sid in base_pool:
                    if sid not in new_map:
                        new_map[sid] = fetch_stock_name_online(sid)
                if save_master_directory(new_map):
                    st.session_state.master_dir = new_map
                    st.success("總表已更新至雲端！")
    
    if st.sidebar.button("登出系統"):
        st.session_state.authenticated = False
        st.query_params.clear()
        st.rerun()

    mode = st.sidebar.radio("切換模式", ["🔎 全市場潛力選拔", "🛡️ 雲端持倉診斷"])
    adr_val = get_adr()

    if mode == "🔎 全市場潛力選拔":
        st.markdown(f"### 🔎 市場量化優勢選拔")
        st.markdown(f"""<div style="background-color:#1e2329; padding:10px; border-radius:10px; text-align:center; border-left:5px solid {'#3fb950' if adr_val > 0 else '#f85149'}; margin-bottom:20px;">
            <small style="color:#888;">美股 TSM ADR 市場情緒</small><br><b style="color:{'#3fb950' if adr_val > 0 else '#f85149'}; font-size:20px;">{adr_val:+.2f}%</b>
        </div>""", unsafe_allow_html=True)

        # 這裡從雲端載入的代號進行盲測
        scan_pool = list(st.session_state.master_dir.keys())
        # 如果雲端沒資料，至少給一組預設標的
        if not scan_pool: scan_pool = ["2330","2317","2454","2303","2603"]
        
        winners = []
        p_text = f"AI 正在對全市場進行盲測數據選拔..."
        p_bar = st.progress(0, text=p_text)
        
        # --- 純數據盲測階段 ---
        for i, sid in enumerate(scan_pool):
            p_bar.progress((i + 1) / len(scan_pool), text=p_text)
            try:
                tkr = yf.Ticker(f"{sid}.TW")
                hist = tkr.history(period="60d")
                if hist.empty or len(hist) < 25: continue
                
                df = apply_tech(hist)
                score, buy, target, rank = compute_quant_score(df, adr_val)
                
                if score >= 70:
                    winners.append({"id": sid, "price": round(df.iloc[-1]['Close'], 2), "score": score, "buy": buy, "target": target, "rank": rank})
            except: continue
        
        p_bar.empty()

        if winners:
            st.write(f"🎉 篩選出 {len(winners)} 檔高潛力標的：")
            # --- 渲染時才帶出中文名稱 ---
            for item in sorted(winners, key=lambda x: x['score'], reverse=True)[:12]:
                zh_name = st.session_state.master_dir.get(item['id'], fetch_stock_name_online(item['id']))
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
                        <div style="text-align:center;"><small style="color:#8b949e;">目前市價</small><br><b>{item['price']}</b></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("💡 目前市場標的偏向整理，尚未發現符合量化優勢門檻的買訊標的。")

    else:
        st.markdown(f"### 🛡️ 雲端持倉實戰診斷")
        st.markdown(f"<small style='color:#3fb950;'>● 雲端已同步 (台北 24H)</small>", unsafe_allow_html=True)

        with st.expander("➕ 新增個人持倉記錄", expanded=False):
            c1, c2, c3 = st.columns([2, 2, 1])
            in_id = c1.text_input("代號", placeholder="例如: 2330")
            in_cost = c2.number_input("平均成本", value=None, placeholder="輸入價格", step=0.1)
            if c3.button("存入", use_container_width=True):
                if in_cost:
                    # 如果代號不在雲端字典，立即補完
                    if in_id not in st.session_state.master_dir:
                        name = fetch_stock_name_online(in_id)
                        st.session_state.master_dir[in_id] = name
                        save_master_directory(st.session_state.master_dir)
                    
                    st.session_state.portfolio_list.append({"symbol": f"{in_id}.TW", "cost": in_cost, "ts": time.time()})
                    cloud_save_portfolio(st.session_state.user_id, st.session_state.portfolio_list)
                    st.rerun()

        if st.session_state.portfolio_list:
            del_ts = None
            for s in st.session_state.portfolio_list:
                try:
                    p_id = s['symbol'].split('.')[0]
                    c_name = st.session_state.master_dir.get(p_id, fetch_stock_name_online(p_id))
                    
                    tkr = yf.Ticker(s['symbol'])
                    df = apply_tech(tkr.history(period="60d"))
                    l = df.iloc[-1]
                    cur = round(l['Close'], 2)
                    gain = ((cur - s['cost']) / s['cost']) * 100
                    
                    msg, clr = "", "#ffffff"
                    if gain > 0:
                        if l['MACD'] > 0: msg, clr = "🚀 強勢續留", "#3fb950"
                        else: msg, clr = "⚠️ 漲勢放緩", "#f0883e"
                    else:
                        if l['MACD'] > 0: msg, clr = "💪 低檔轉強", "#58a6ff"
                        elif cur < df.iloc[-1]['MA20']: msg, clr = "🚨 建議止損", "#f85149"
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

