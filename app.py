import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import time
from datetime import datetime, timedelta, timezone
from google.cloud import firestore
from google.oauth2 import service_account

# --- 頁面配置 (行動裝置體驗最佳化) ---
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
            # 確保私鑰換行符號在雲端環境中正確解析
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = service_account.Credentials.from_service_account_info(creds_dict)
            return firestore.Client(credentials=creds)
    except Exception:
        return None
    return None

db = init_db()
app_id = st.secrets.get("general", {}).get("app_id", "stock_ai_v3")

# --- 2. 雲端同步邏輯 (符合 Rule 1) ---
def cloud_save(uid, data):
    if not db or not uid: return False
    try:
        # 路徑：/artifacts/{appId}/users/{userId}/portfolio/data
        doc_ref = db.collection("artifacts").document(app_id).collection("users").document(uid).collection("portfolio").document("data")
        doc_ref.set({
            "items": data,
            "last_updated": get_taipei_now(),
            "user_id": uid
        })
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

# --- 3. 登入與持久化記憶 ---
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

# --- 4. 技術分析與全自動中文名稱引擎 ---

def compute_tech_indicators(df):
    """計算趨勢與動能分數"""
    if len(df) < 35: return df
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    l, h = df['Low'].rolling(window=9).min(), df['High'].rolling(window=9).max()
    df['K'] = ((df['Close'] - l) / (h - l) * 100).ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()
    e12, e26 = df['Close'].ewm(span=12).mean(), df['Close'].ewm(span=26).mean()
    df['MACD'] = (e12 - e26 - (e12 - e26).ewm(span=9).mean()) * 2
    return df

@st.cache_data(ttl=86400)
def fetch_zh_name_from_web(symbol):
    """以編號為源頭，從網路公開資訊帶出繁體中文名"""
    pure_id = symbol.split('.')[0]
    try:
        # 直接調用 Yahoo Finance 繁體中文搜尋 API
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={pure_id}&lang=zh-Hant-TW&region=TW"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            quotes = res.json().get('quotes', [])
            for q in quotes:
                if q.get('symbol').startswith(pure_id):
                    name = q.get('shortname') or q.get('longname') or pure_id
                    # 清理名稱：移除英文後綴
                    return name.split(' ')[0].split('(')[0].strip()
    except Exception:
        pass
    return pure_id

@st.cache_data(ttl=3600)
def get_market_sentiment():
    """獲取 ADR 市場氛圍"""
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return round(((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100, 2)
    except: return 0.0

# --- 5. 介面渲染 ---

if not st.session_state.authenticated:
    st.markdown("<div style='height: 80px;'></div>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center; color: #58a6ff;'>🚀 AI 實戰航線</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #8b949e;'>輸入通行碼即可同步雲端持倉</p>", unsafe_allow_html=True)
    with st.container():
        st.markdown("<div style='background-color: #161b22; padding: 25px; border-radius: 15px; border: 1px solid #30363d;'>", unsafe_allow_html=True)
        login_id = st.text_input("通行碼", placeholder="例如: AlexInvest", label_visibility="collapsed")
        if st.button("確認登入並同步", use_container_width=True, type="primary"):
            handle_login(login_id)
        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

else:
    # 側邊欄配置
    st.sidebar.title("👤 帳號中心")
    st.sidebar.info(f"當前帳號: `{st.session_state.user_id}`")
    if st.sidebar.button("登出帳號"):
        st.session_state.authenticated = False
        st.query_params.clear()
        st.rerun()
    st.sidebar.divider()
    mode = st.sidebar.radio("切換模式", ["🔎 全市場潛力掃描", "🛡️ 雲端持倉診斷"])
    
    adr_val = get_market_sentiment()

    # --- 模式一：AI 全市場掃描 (公平競爭邏輯) ---
    if mode == "🔎 全市場潛力掃描":
        st.markdown(f"### 🔎 市場高優勢潛力標的")
        st.markdown(f"""<div style="background-color:#1e2329; padding:10px; border-radius:10px; text-align:center; border-left:5px solid {'#3fb950' if adr_val > 0 else '#f85149'}; margin-bottom:20px;">
            <small style="color:#888;">美股 TSM ADR 連動強度</small><br><b style="color:{'#3fb950' if adr_val > 0 else '#f85149'}; font-size:20px;">{adr_val:+.2f}%</b>
        </div>""", unsafe_allow_html=True)

        # 全市場核心標的池 (涵蓋 0050/0051/0056 等高流動性標的，不設名稱，只認代號)
        scan_pool = [
            "2330","2317","2454","2382","2308","2449","2603","2609","2618","2303","3008","2881",
            "2882","2891","3711","2357","3231","4938","2379","3034","3037","1503","1513","1519",
            "1605","1101","2002","2409","3481","2610","1504","1514","2327","2376","3035","3406",
            "3443","3661","5269","6409","6446","6472","6488","8299","9958","2313","2451","2458",
            "2492","2727","3533","5483","6239","8936","2352","3017","3653","4958","5871","6669"
        ]
        
        winners = []
        progress_text = f"AI 正在對全市場 {len(scan_pool)} 檔標的進行數據選拔..."
        p_bar = st.progress(0, text=progress_text)
        
        # 核心數據選拔：只認代號與技術指標
        for i, sid in enumerate(scan_pool):
            p_bar.progress((i + 1) / len(scan_pool), text=progress_text)
            try:
                tkr = yf.Ticker(f"{sid}.TW")
                df = compute_tech_indicators(tkr.history(period="60d"))
                if df.empty or len(df) < 20: continue
                l, p = df.iloc[-1], df.iloc[-2]
                
                # AI 評分公式
                score = 35 + (adr_val * 2.5)
                if l['Close'] > l['MA5']: score += 15
                if l['K'] > l['D'] and p['K'] <= p['D']: score += 25 # KD 黃金交叉
                if l['MACD'] > 0: score += 15
                if l['Volume'] > df['Volume'].mean() * 1.2: score += 10
                
                if score >= 75:
                    winners.append({
                        "id": sid, "price": round(l['Close'], 2), 
                        "score": int(score), "buy": round(max(l['MA5'], l['Close'] * 0.995), 2),
                        "target": round(l['Close'] * 1.06, 2)
                    })
            except: continue
        
        p_bar.empty()

        if winners:
            st.write(f"🎉 數據選拔完成！最具優勢標的：")
            # 渲染階段才進行「名稱映射」
            for item in sorted(winners, key=lambda x: x['score'], reverse=True)[:10]:
                item_name = fetch_zh_name_from_web(item['id'])
                st.markdown(f"""
                <div style="background-color:#161b22; padding:12px; border-radius:12px; border:1px solid #30363d; margin-bottom:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <b style="font-size:17px; color:#c9d1d9;">{item_name} ({item['id']})</b>
                        <span style="background:#238636; color:white; padding:2px 8px; border-radius:6px; font-size:12px;">優勢分 {item['score']}</span>
                    </div>
                    <div style="display:flex; justify-content:space-between; margin-top:10px; background:#0d1117; padding:12px; border-radius:10px;">
                        <div style="text-align:center;"><small style="color:#8b949e;">分批進場點</small><br><b style="color:#3fb950;">{item['buy']}</b></div>
                        <div style="text-align:center;"><small style="color:#8b949e;">預期目標</small><br><b style="color:#58a6ff;">{item['target']}</b></div>
                        <div style="text-align:center;"><small style="color:#8b949e;">現價</small><br><b>{item['price']}</b></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("💡 市場整理中，目前數據庫尚未發現符合優勢門檻的買訊標的。")

    # --- 模式二：雲端持倉管理 ---
    else:
        st.markdown(f"### 🛡️ 持倉診斷 - {st.session_state.user_id}")
        st.markdown(f"<small style='color:#3fb950;'>● 雲端資料庫已同步 (24H 台北時間)</small>", unsafe_allow_html=True)

        with st.expander("➕ 新增個人持倉", expanded=False):
            c1, c2, c3 = st.columns([2, 2, 1])
            in_id = c1.text_input("代號", placeholder="例如: 2330")
            in_cost = c2.number_input("成本", value=None, placeholder="輸入價格", step=0.1)
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
                    # 動態帶出中文名稱
                    cname = fetch_zh_name_from_web(p_id)
                    
                    tkr = yf.Ticker(s['symbol'])
                    df = compute_tech_indicators(tkr.history(period="60d"))
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

