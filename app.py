import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import time
from datetime import datetime, timedelta, timezone
from google.cloud import firestore
from google.oauth2 import service_account

# --- 頁面配置 (針對 iPhone PWA 模式優化) ---
st.set_page_config(
    page_title="台股 AI 實戰", 
    layout="centered", 
    initial_sidebar_state="collapsed"
)

# --- 0. 台北時間工具 (24H 格式) ---
def get_taipei_now():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz)

# --- 1. 富果 API 連線檢查與狀態顯示 (參考官方範例) ---
def check_fugle_connection():
    """
    驗證富果 API 金鑰與伺服器連線狀態
    """
    api_key = st.secrets.get("general", {}).get("fugle_api_key", "")
    if not api_key:
        return False, "無金鑰"
    
    # 使用富果 v1.0 Quote API 進行輕量化測試 (測試台積電 2330)
    test_url = "https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/2330"
    headers = {"X-FUGLE-API-KEY": api_key}
    try:
        res = requests.get(test_url, headers=headers, timeout=3)
        if res.status_code == 200:
            return True, "已連線"
        elif res.status_code == 401:
            return False, "權限錯誤"
        else:
            return False, f"狀態碼: {res.status_code}"
    except Exception:
        return False, "網路中斷"

def get_fugle_realtime_quote(symbol_id):
    """
    取得富果秒級即時行情
    """
    api_key = st.secrets.get("general", {}).get("fugle_api_key", "")
    if not api_key: return None
    headers = {"X-FUGLE-API-KEY": api_key}
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol_id}"
    try:
        res = requests.get(url, headers=headers, timeout=2)
        if res.status_code == 200:
            d = res.json()
            return {
                "price": d.get("lastPrice"),
                "high": d.get("high"),
                "low": d.get("low"),
                "volume": d.get("totalVolume"),
                "time": d.get("lastUpdatedAt")
            }
    except: return None
    return None

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
app_id = st.secrets.get("general", {}).get("app_id", "stock_ai_v3")

# --- 3. 雲端同步與字典管理 ---
def load_cloud_directory():
    if not db: return {}
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("public").document("data").collection("directory").document("master_list")
        doc = doc_ref.get()
        return doc.to_dict().get("mapping", {}) if doc.exists else {}
    except: return {}

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

# --- 4. 記憶登入邏輯 ---
query_params = st.query_params
url_uid = query_params.get("uid", None)

if "authenticated" not in st.session_state:
    if url_uid:
        st.session_state.user_id = url_uid
        st.session_state.authenticated = True
        st.session_state.portfolio_list = cloud_load_portfolio(url_uid)
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

# --- 5. 產業分類資料庫 ---
CATEGORY_GROUPS = {
    "電子/半導體": ["2330","2317","2454","2382","2308","2449","3711","2303","3034","3037","3231","4938","2379","2353","3008","2376","3017","6669","2313","2451","2458","2492","2327","3035","3406","3443","3661","5269","6409","6488","8299"],
    "金融/保險": ["2881","2882","2886","2891","2884","2885","2880","2887","5880","2890","2892","5871","2883","2888","2834"],
    "航運/傳產": ["2603","2609","2615","2618","2610","1301","1303","1326","6505","2002","1101","1605","2105","1503","1513","1519","9958"],
    "觀光/生技/其他": ["6446","6472","1760","1712","1723","2912","9910","9921","9904","2727","8454"]
}

# --- 6. AI 量化分析 (漏斗式結構) ---

def apply_tech_indicators(df):
    if len(df) < 25: return df
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    l, h = df['Low'].rolling(window=9).min(), df['High'].rolling(window=9).max()
    df['K'] = ((df['Close'] - l) / (h - l) * 100).ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()
    e12, e26 = df['Close'].ewm(span=12).mean(), df['Close'].ewm(span=26).mean()
    df['MACD'] = (e12 - e26 - (e12 - e26).ewm(span=9).mean()) * 2
    return df

def get_base_score(df, adr):
    """Yahoo 盲測評分邏輯"""
    l, p = df.iloc[-1], df.iloc[-2]
    score = 35 + (adr * 2.3)
    if l['Close'] > l['MA5']: score += 15
    if l['K'] > l['D'] and p['K'] <= p['D']: score += 20
    if l['MACD'] > 0: score += 15
    return int(score)

@st.cache_data(ttl=3600)
def get_adr_sentiment():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return round(((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100, 2)
    except: return 0.0

# --- 7. 介面渲染 ---

if not st.session_state.authenticated:
    st.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center; color: #58a6ff;'>🚀 AI 實戰選股中心</h1>", unsafe_allow_html=True)
    login_id = st.text_input("通行碼", placeholder="例如: MyStockAI", label_visibility="collapsed")
    if st.button("確認進入", use_container_width=True, type="primary"):
        handle_login(login_id)
    st.stop()

else:
    # 預載雲端總表
    if "master_dir" not in st.session_state:
        st.session_state.master_dir = load_cloud_directory()
    
    # --- 頂部狀態欄 (加入富果 API 狀態顯示) ---
    is_connected, status_msg = check_fugle_connection()
    adr_val = get_adr_sentiment()
    
    st.markdown(f"""
    <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
        <div style="background: #1e2329; padding: 5px 12px; border-radius: 8px; border-left: 4px solid {'#3fb950' if is_connected else '#f85149'};">
            <small style="color: #8b949e;">Fugle API</small><br>
            <b style="color: {'#3fb950' if is_connected else '#f85149'}; font-size: 13px;">{status_msg}</b>
        </div>
        <div style="background: #1e2329; padding: 5px 12px; border-radius: 8px; border-left: 4px solid {'#3fb950' if adr_val > 0 else '#f85149'}; text-align: right;">
            <small style="color: #8b949e;">TSM ADR</small><br>
            <b style="color: {'#3fb950' if adr_val > 0 else '#f85149'}; font-size: 13px;">{adr_val:+.2f}%</b>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.sidebar.title("👤 帳號管理")
    st.sidebar.info(f"帳號: `{st.session_state.user_id}`")
    if not url_uid:
        st.sidebar.success("💡 技巧：點擊 Safari「分享」並選擇「加入主畫面」，即可實現一鍵自動登入。")
    if st.sidebar.button("登出系統"):
        st.session_state.authenticated = False
        st.query_params.clear()
        st.rerun()
    
    st.sidebar.divider()
    mode = st.sidebar.radio("切換模式", ["🔎 即時選拔分析", "🛡️ 持倉實時診斷"])

    # --- 模式一：選拔分析 (Yahoo 廣域 -> Fugle 精確) ---
    if mode == "🔎 即時選拔分析":
        c1, c2 = st.columns(2)
        with c1:
            sel_cat = st.selectbox("📂 產業分類", ["全部"] + list(CATEGORY_GROUPS.keys()))
        with c2:
            sel_price = st.selectbox("💰 價位分級", ["全部", "<50", "50-100", "100-500", "500-1000", ">1000"])

        # 決定掃描池
        if sel_cat == "全部":
            pool = [sid for g in CATEGORY_GROUPS.values() for sid in g]
        else:
            pool = CATEGORY_GROUPS[sel_cat]
        pool = sorted(list(set(pool)))
        
        # 1. 第一階段：Yahoo 廣域盲測
        initial_winners = []
        p_bar = st.progress(0, text=f"正在盲測 {len(pool)} 檔數據...")
        
        for i, sid in enumerate(pool):
            p_bar.progress((i + 1) / len(pool))
            try:
                tkr = yf.Ticker(f"{sid}.TW")
                df_hist = tkr.history(period="60d")
                if df_hist.empty: continue
                
                df = apply_tech_indicators(df_hist)
                cur_p = round(df.iloc[-1]['Close'], 2)
                
                # 初步過濾
                p_match = False
                if sel_price == "全部": p_match = True
                elif sel_price == "<50" and cur_p < 50: p_match = True
                elif sel_price == "50-100" and 50 <= cur_p < 100: p_match = True
                elif sel_price == "100-500" and 100 <= cur_p < 500: p_match = True
                elif sel_price == "500-1000" and 500 <= cur_p < 1000: p_match = True
                elif sel_price == ">1000" and cur_p >= 1000: p_match = True
                if not p_match: continue
                
                score = get_base_score(df, adr_val)
                if score >= 65: # 門檻
                    initial_winners.append({"id": sid, "df": df, "score": score})
            except: continue
        p_bar.empty()

        # 2. 第二階段：Fugle 精確量能分析
        final_winners = []
        if initial_winners:
            st.write(f"📡 複賽：正在調用富果即時數據驗證前 {len(initial_winners[:15])} 檔...")
            for item in sorted(initial_winners, key=lambda x: x['score'], reverse=True)[:15]:
                live = get_fugle_realtime_quote(item['id'])
                if live and live['price']:
                    # 注入現價重新計算技術指標
                    df_live = item['df'].copy()
                    df_live.iloc[-1, df_live.columns.get_loc('Close')] = live['price']
                    df_live = apply_tech_indicators(df_live)
                    
                    # 分析盤中量能 (比對 20 日均量)
                    vol_avg = df_live['Volume'].tail(20).mean()
                    vol_ratio = live['volume'] / vol_avg
                    
                    f_score = item['score']
                    vol_msg = "量能平穩"
                    if vol_ratio > 1.5: 
                        f_score += 10
                        vol_msg = "🔥 盤中爆量突破"
                    
                    buy = round(max(df_live.iloc[-1]['MA5'], live['price'] * 0.993), 2)
                    target = round(live['price'] * 1.058, 2)
                    rank = "🚀 強力推薦" if f_score >= 85 else "✅ 建議布局" if f_score >= 75 else "盤整中"
                    
                    final_winners.append({
                        "id": item['id'], "price": live['price'], "score": f_score, 
                        "buy": buy, "target": target, "rank": rank, "vol": vol_msg,
                        "time": live['time'].split('T')[1][:5]
                    })

        if final_winners:
            st.write(f"🎉 篩選完成！本時段即時推薦：")
            for item in sorted(final_winners, key=lambda x: x['score'], reverse=True):
                zh_name = st.session_state.master_dir.get(item['id'], item['id'])
                st.markdown(f"""
                <div style="background-color:#161b22; padding:12px; border-radius:12px; border:1px solid #30363d; margin-bottom:12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <b style="font-size:17px; color:#c9d1d9;">{zh_name} ({item['id']})</b>
                        <span style="background:#238636; color:white; padding:2px 8px; border-radius:6px; font-size:10px;">富果 {item['time']}</span>
                    </div>
                    <div style="margin-top:5px; display:flex; justify-content:space-between;">
                        <small style="color:#3fb950; font-weight:bold;">{item['rank']} | {item['vol']}</small>
                        <small style="color:#8b949e;">量化評分: {item['score']}</small>
                    </div>
                    <div style="display:flex; justify-content:space-between; margin-top:10px; background:#0d1117; padding:10px; border-radius:10px;">
                        <div style="text-align:center;"><small style="color:#8b949e;">支撐買點</small><br><b style="color:#3fb950;">{item['buy']}</b></div>
                        <div style="text-align:center;"><small style="color:#8b949e;">獲利預期</small><br><b style="color:#58a6ff;">{item['target']}</b></div>
                        <div style="text-align:center;"><small style="color:#8b949e;">現價</small><br><b>{item['price']}</b></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("💡 目前市場標的尚未符合即時優勢，建議觀望。")

    # --- 模式二：持倉診斷 ---
    else:
        st.markdown(f"### 🛡️ 持倉實時診斷 (Fugle 秒級)")
        with st.expander("➕ 新增持倉記錄", expanded=False):
            c1, c2, c3 = st.columns([2, 2, 1])
            in_id = c1.text_input("代號", placeholder="例如: 2330")
            in_cost = c2.number_input("成本", value=None, placeholder="價格", step=0.1)
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
                    zh_name = st.session_state.master_dir.get(p_id, p_id)
                    # 診斷同樣調用富果即時現價
                    live = get_fugle_realtime_quote(p_id)
                    tkr = yf.Ticker(s['symbol'])
                    df = apply_tech_indicators(tkr.history(period="60d"))
                    cur = live['price'] if live else round(df.iloc[-1]['Close'], 2)
                    gain = ((cur - s['cost']) / s['cost']) * 100
                    
                    msg, clr = "數據分析中...", "#ffffff"
                    if gain > 0:
                        msg, clr = ("🚀 強勢續留", "#3fb950") if df.iloc[-1]['MACD'] > 0 else ("⚠️ 建議減碼", "#f0883e")
                    else:
                        if df.iloc[-1]['MACD'] > 0: msg, clr = "💪 低檔轉強", "#58a6ff"
                        elif cur < df.iloc[-1]['MA20']: msg, clr = "🚨 果斷止損", "#f85149"
                        else: msg, clr = "💤 盤整待變", "#8b949e"

                    st.markdown(f"""
                    <div style="background-color:#161b22; padding:15px; border-radius:12px; border-left:8px solid {clr}; margin-bottom:12px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <b style="font-size:16px; color:#c9d1d9;">{zh_name} ({p_id})</b>
                            <b style="color:{clr}; font-size:13px;">{msg}</b>
                        </div>
                        <div style="display:flex; justify-content:space-between; margin:10px 0;">
                            <span>成本: {s['cost']} | 現價: <b>{cur}</b></span>
                            <span style="color:{clr}; font-size:18px; font-weight:bold;">{gain:+.2f}%</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"🗑️ 移除 {zh_name}", key=f"d_{s['ts']}"): del_ts = s['ts']
                except: continue
            if del_ts:
                st.session_state.portfolio_list = [i for i in st.session_state.portfolio_list if i['ts'] != del_ts]
                cloud_save_portfolio(st.session_state.user_id, st.session_state.portfolio_list)
                st.rerun()

    st.divider()
    st.caption(f"最後更新 (台北 24H): {get_taipei_now().strftime('%Y-%m-%d %H:%M:%S')}")

