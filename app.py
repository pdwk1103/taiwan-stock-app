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

# --- 1. Firebase / Firestore 初始化 ---
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

# --- 2. 雲端資料字典 (全台股自動補完) ---

@st.cache_data(ttl=43200)
def get_cloud_stock_directory():
    """從雲端讀取全台股對照表，若無則自動生成"""
    if not db: return {}
    try:
        # 遵循路徑: /artifacts/{appId}/public/data/stock_directory
        doc_ref = db.collection("artifacts").document(app_id).collection("public").document("data").collection("directory").document("all_stocks")
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict().get("mapping", {})
        else:
            # 雲端尚無資料，啟動初始化 (內建核心標的 + 自動補完)
            initial_map = {
                "2330":"台積電","2317":"鴻海","2454":"聯發科","2303":"聯電","2449":"京元電子",
                "2603":"長榮","2609":"陽明","2618":"長榮航","2382":"廣達","3231":"緯創"
            }
            # 此處可由管理員手動觸發全面更新，暫以基礎名單與動態抓取互補
            doc_ref.set({"mapping": initial_map, "last_updated": get_taipei_now()}, merge=True)
            return initial_map
    except:
        return {}

def update_cloud_directory_entry(symbol, name):
    """當發現新股票時，自動非同步更新雲端字典"""
    if not db: return
    try:
        pure_id = symbol.split('.')[0]
        doc_ref = db.collection("artifacts").document(app_id).collection("public").document("data").collection("directory").document("all_stocks")
        doc_ref.update({f"mapping.{pure_id}": name})
    except: pass

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

# --- 4. AI 廣域分析引擎 (數據優先、名稱最後映射) ---

def compute_quant_score(df, adr_val):
    """
    公平數據選美：純技術與量能分析
    """
    if len(df) < 30: return 0, 0, 0, "觀察"
    l, p = df.iloc[-1], df.iloc[-2]
    
    score = 35 + (adr_val * 2)
    if l['Close'] > l['MA5']: score += 15
    if l['K'] > l['D'] and p['K'] <= p['D']: score += 20 # 黃金交叉
    if l['MACD'] > 0: score += 15
    if l['Volume'] > df['Volume'].tail(10).mean() * 1.2: score += 15 # 出量
    
    rank = "⚡ 強力推薦" if score >= 85 else "✅ 建議布局" if score >= 70 else "整理中"
    buy = round(max(l['MA5'], l['Close'] * 0.994), 2)
    target = round(l['Close'] * 1.055, 2)
    
    return int(score), buy, target, rank

def get_mapped_name(symbol, directory):
    """選美後，透過雲端字典映射中文名稱"""
    pure_id = symbol.split('.')[0]
    if pure_id in directory:
        return directory[pure_id]
    
    # 若字典無此代號，啟動即時網路抓取並回寫雲端
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={pure_id}&lang=zh-Hant-TW&region=TW"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        quotes = res.json().get('quotes', [])
        for q in quotes:
            if q.get('symbol').startswith(pure_id):
                name = (q.get('shortname') or q.get('longname') or pure_id).split(' ')[0].split('(')[0]
                update_cloud_directory_entry(pure_id, name)
                return name
    except: pass
    return pure_id

def apply_indicators(df):
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
    st.markdown("<p style='text-align: center; color: #8b949e;'>全市場數據掃描 | 雲端中文同步</p>", unsafe_allow_html=True)
    login_id = st.text_input("個人通行碼", placeholder="請輸入通行碼", label_visibility="collapsed")
    if st.button("確認登入並同步", use_container_width=True, type="primary"):
        handle_login(login_id)
    st.stop()

else:
    # 預載雲端字典
    stock_dir = get_cloud_stock_directory()
    
    st.sidebar.title("👤 帳號中心")
    st.sidebar.info(f"帳號: `{st.session_state.user_id}`")
    if st.sidebar.button("登出帳號"):
        st.session_state.authenticated = False
        st.query_params.clear()
        st.rerun()
    st.sidebar.divider()
    mode = st.sidebar.radio("功能導航", ["🔎 全市場潛力掃描", "🛡️ 雲端持倉診斷"])
    
    adr_val = get_adr()

    if mode == "🔎 全市場潛力掃描":
        st.markdown(f"### 🔎 市場量化優勢掃描")
        st.markdown(f"""<div style="background-color:#1e2329; padding:10px; border-radius:10px; text-align:center; border-left:5px solid {'#3fb950' if adr_val > 0 else '#f85149'}; margin-bottom:20px;">
            <small style="color:#888;">美股 TSM ADR 連動強度</small><br><b style="color:{'#3fb950' if adr_val > 0 else '#f85149'}; font-size:20px;">{adr_val:+.2f}%</b>
        </div>""", unsafe_allow_html=True)

        # 掃描池：台股權值與流動性標的代碼
        pool = [
            "2330","2317","2454","2382","2308","2449","2603","2609","2618","2303","3008","2881",
            "2882","2891","3711","2357","3231","4938","2379","3034","3037","1503","1513","1519",
            "1605","1101","2002","2409","3481","2610","1504","1514","2327","2376","3035","3406",
            "3443","3661","5269","6409","6446","6472","6488","8299","9958","2313","2451","2458",
            "2492","2727","3533","5483","6239","8936","2352","3017","3653","4958","5871","6669"
        ]
        
        winners = []
        p_text = f"AI 正在對全場域標的進行公平數據分析..."
        p_bar = st.progress(0, text=p_text)
        
        # --- 純數據盲測 ---
        for i, sid in enumerate(pool):
            p_bar.progress((i + 1) / len(pool), text=p_text)
            try:
                tkr = yf.Ticker(f"{sid}.TW")
                hist = tkr.history(period="60d")
                if hist.empty or len(hist) < 25: continue
                
                df = apply_indicators(hist)
                score, buy, target, rank = compute_quant_score(df, adr_val)
                
                if score >= 70:
                    winners.append({"id": sid, "price": round(df.iloc[-1]['Close'], 2), "score": score, "buy": buy, "target": target, "rank": rank})
            except: continue
        
        p_bar.empty()

        if winners:
            st.write(f"🎉 選拔完成！共篩選出 {len(winners)} 檔高潛力標的：")
            # --- 渲染階段：從雲端對照表映射名稱 ---
            for item in sorted(winners, key=lambda x: x['score'], reverse=True)[:12]:
                zh_name = get_mapped_name(item['id'], stock_dir)
                st.markdown(f"""
                <div style="background-color:#161b22; padding:12px; border-radius:12px; border:1px solid #30363d; margin-bottom:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <b style="font-size:17px; color:#c9d1d9;">{zh_name} ({item['id']})</b>
                        <span style="background:#238636; color:white; padding:2px 8px; border-radius:6px; font-size:12px;">潛力分 {item['score']}</span>
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
            st.info("💡 目前市場標的多處於整理期，AI 建議觀望暫無強勢買訊。")

    else:
        st.markdown(f"### 🛡️ 雲端持倉實戰診斷")
        st.markdown(f"<small style='color:#3fb950;'>● 雲端資料庫同步中 (24H 台北時間)</small>", unsafe_allow_html=True)

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
                    # 強制比對雲端字典中文名
                    c_name = get_mapped_name(p_id, stock_dir)
                    
                    tkr = yf.Ticker(s['symbol'])
                    df = apply_indicators(tkr.history(period="60d"))
                    l = df.iloc[-1]
                    cur = round(l['Close'], 2)
                    gain = ((cur - s['cost']) / s['cost']) * 100
                    
                    msg, clr = "", "#ffffff"
                    if gain > 0:
                        if l['MACD'] > 0: msg, clr = "🚀 強勢續留", "#3fb950"
                        else: msg, clr = "⚠️ 漲勢轉弱", "#f0883e"
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

