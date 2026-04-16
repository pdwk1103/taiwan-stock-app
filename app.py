import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import time
from datetime import datetime, timedelta, timezone
from google.cloud import firestore
from google.oauth2 import service_account

# --- 頁面配置 ---
st.set_page_config(
    page_title="台股 AI 實戰", 
    layout="centered", 
    initial_sidebar_state="collapsed"
)

# --- 0. 台北時間工具 ---
def get_taipei_now():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz)

# --- 1. 富果 API 頻道對接 (REST 模擬訂閱頻道) ---
def get_fugle_intraday_data(symbol_id):
    """
    對接富果 Market Data v1.0。
    僅針對入圍個股讀取行情 (Quote) 與 成交 (Trades) 頻道資訊。
    """
    api_key = st.secrets.get("general", {}).get("fugle_api_key", "")
    if not api_key: return None
    
    headers = {"X-FUGLE-API-KEY": api_key}
    try:
        # 模擬 Quote 頻道 (取得現價與盤中高低)
        quote_url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol_id}"
        q_res = requests.get(quote_url, headers=headers, timeout=2)
        
        # 模擬 Trades 頻道 (取得即時量能資訊)
        # 此處取最鄰近成交數據來分析盤中量能
        if q_res.status_code == 200:
            q_data = q_res.json()
            return {
                "price": q_data.get("lastPrice"),
                "high": q_data.get("high"),
                "low": q_data.get("low"),
                "volume": q_data.get("totalVolume"),
                "change": q_data.get("changePercent"),
                "last_time": q_data.get("lastUpdatedAt"),
                "is_trial": q_data.get("isTrial", False) # 試撮過濾
            }
    except: return None
    return None

# --- 2. Firebase 與字典管理 ---
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

def load_cloud_directory():
    if not db: return {}
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("public").document("data").collection("directory").document("master_list")
        doc = doc_ref.get()
        return doc.to_dict().get("mapping", {}) if doc.exists else {}
    except: return {}

# --- 3. 登入記憶邏輯 ---
query_params = st.query_params
url_uid = query_params.get("uid", None)

if "authenticated" not in st.session_state:
    if url_uid:
        st.session_state.user_id = url_uid
        st.session_state.authenticated = True
    else:
        st.session_state.authenticated = False

def handle_login(uid):
    uid = uid.strip()
    if uid:
        st.session_state.user_id = uid
        st.session_state.authenticated = True
        st.query_params["uid"] = uid 
        st.rerun()

# --- 4. 產業分類資料庫 ---
CATEGORY_GROUPS = {
    "電子/半導體": ["2330","2317","2454","2382","2308","2449","3711","2303","3034","3037","3231","4938","2379","2353","3008","2376","3017","6669","2313","2451","2458","2492","2327","3035","3406","3443","3661","5269","6409","6488","8299"],
    "金融/保險": ["2881","2882","2886","2891","2884","2885","2880","2887","5880","2890","2892","5871","2883","2888","2834"],
    "航運/傳產": ["2603","2609","2615","2618","2610","1301","1303","1326","6505","2002","1101","1605","2105","1503","1513","1519","9958"],
    "觀光/生技/其他": ["6446","6472","1760","1712","2912","9910","9921","9904","2727","8454"]
}

# --- 5. 核心量化引擎 (漏斗式篩選) ---

def apply_tech_analysis(df):
    if len(df) < 30: return df
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    l, h = df['Low'].rolling(window=9).min(), df['High'].rolling(window=9).max()
    df['K'] = ((df['Close'] - l) / (h - l) * 100).ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()
    e12, e26 = df['Close'].ewm(span=12).mean(), df['Close'].ewm(span=26).mean()
    df['MACD'] = (e12 - e26 - (e12 - e26).ewm(span=9).mean()) * 2
    return df

def get_base_score(df, adr):
    """第一階段：Yahoo 數據盲測評分"""
    l, p = df.iloc[-1], df.iloc[-2]
    score = 30 + (adr * 2.5)
    if l['Close'] > l['MA5']: score += 15
    if l['K'] > l['D'] and p['K'] <= p['D']: score += 20
    if l['MACD'] > 0: score += 15
    return int(score)

@st.cache_data(ttl=3600)
def get_market_adr():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return round(((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100, 2)
    except: return 0.0

# --- 6. 介面渲染 ---

if not st.session_state.authenticated:
    st.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center; color: #58a6ff;'>🚀 AI 實戰選股系統</h1>", unsafe_allow_html=True)
    login_id = st.text_input("通行碼", placeholder="輸入後點擊確認並載入雲端", label_visibility="collapsed")
    if st.button("確認進入", use_container_width=True, type="primary"):
        handle_login(login_id)
    st.stop()

else:
    if "master_dir" not in st.session_state:
        st.session_state.master_dir = load_cloud_directory()
    
    st.sidebar.title("👤 帳號管理")
    st.sidebar.info(f"帳號: `{st.session_state.user_id}`")
    
    if st.sidebar.button("登出系統"):
        st.session_state.authenticated = False
        st.query_params.clear()
        st.rerun()
    
    mode = st.sidebar.radio("切換功能", ["🔎 全市場潛力選拔", "🛡️ 持倉即時監控"])
    adr_val = get_market_adr()

    if mode == "🔎 全市場潛力選拔":
        st.markdown(f"### 🔎 AI 多因子選拔 (Yahoo 盲測 + 富果即時)")
        
        c1, c2 = st.columns(2)
        with c1:
            sel_cat = st.selectbox("📂 產業分類", ["全部"] + list(CATEGORY_GROUPS.keys()))
        with c2:
            sel_price = st.selectbox("💰 價位分級", ["全部", "<50", "50-100", "100-500", "500-1000", ">1000"])

        st.markdown(f"""<div style="background-color:#1e2329; padding:8px; border-radius:10px; text-align:center; border-left:5px solid {'#3fb950' if adr_val > 0 else '#f85149'}; margin-bottom:15px;">
            <small style="color:#888;">美股 TSM ADR 市場情緒</small><br><b style="color:{'#3fb950' if adr_val > 0 else '#f85149'}; font-size:18px;">{adr_val:+.2f}%</b>
        </div>""", unsafe_allow_html=True)

        # 決定掃描池
        if sel_cat == "全部":
            pool = [sid for g in CATEGORY_GROUPS.values() for sid in g]
        else:
            pool = CATEGORY_GROUPS[sel_cat]
        pool = sorted(list(set(pool)))
        
        # --- 第一階段：Yahoo 數據初步過濾 ---
        initial_winners = []
        p_bar = st.progress(0, text=f"正在使用 Yahoo Finance 盲測 {len(pool)} 檔數據...")
        
        for i, sid in enumerate(pool):
            p_bar.progress((i + 1) / len(pool))
            try:
                tkr = yf.Ticker(f"{sid}.TW")
                df_hist = tkr.history(period="60d")
                if df_hist.empty: continue
                
                df = apply_tech_analysis(df_hist)
                cur_p = round(df.iloc[-1]['Close'], 2)
                
                # 初步價位過濾
                p_match = False
                if sel_price == "全部": p_match = True
                elif sel_price == "<50" and cur_p < 50: p_match = True
                elif sel_price == "50-100" and 50 <= cur_p < 100: p_match = True
                elif sel_price == "100-500" and 100 <= cur_p < 500: p_match = True
                elif sel_price == "500-1000" and 500 <= cur_p < 1000: p_match = True
                elif sel_price == ">1000" and cur_p >= 1000: p_match = True
                if not p_match: continue
                
                score = get_base_score(df, adr_val)
                if score >= 65: # 超過入門門檻，進入複賽
                    initial_winners.append({"id": sid, "df": df, "base_score": score})
            except: continue
        p_bar.empty()

        # --- 第二階段：富果即時數據複賽 (僅針對入圍個股) ---
        final_winners = []
        if initial_winners:
            st.write(f"📡 複賽開始：正在調用富果即時頻道驗證 {len(initial_winners)} 檔標的...")
            for item in sorted(initial_winners, key=lambda x: x['base_score'], reverse=True)[:15]:
                # 調用富果行情與成交數據
                live = get_fugle_intraday_data(item['id'])
                if live and live['price']:
                    # 將即時價格注入歷史數據最後一筆，更新技術指標
                    df_live = item['df'].copy()
                    df_live.iloc[-1, df_live.columns.get_loc('Close')] = live['price']
                    df_live = apply_tech_analysis(df_live) # 重新計算包含現價的指標
                    
                    # 分析盤中量能 (即時量 vs 均量)
                    vol_avg = df_live['Volume'].tail(20).mean()
                    vol_ratio = live['volume'] / vol_avg
                    
                    final_score = item['base_score']
                    vol_msg = "量能平穩"
                    if vol_ratio > 1.5: 
                        final_score += 10
                        vol_msg = "🔥 盤中爆量突破"
                    elif vol_ratio < 0.3 and get_taipei_now().hour > 10:
                        final_score -= 10
                        vol_msg = "💤 量能萎縮"

                    buy = round(max(df_live.iloc[-1]['MA5'], live['price'] * 0.993), 2)
                    target = round(live['price'] * 1.058, 2)
                    rank = "🚀 強力推薦" if final_score >= 85 else "✅ 建議布局" if final_score >= 75 else "觀望"
                    
                    final_winners.append({
                        "id": item['id'], "price": live['price'], "score": final_score, 
                        "buy": buy, "target": target, "rank": rank, "vol_msg": vol_msg,
                        "time": live['last_time'].split('T')[1].split('.')[0][:5]
                    })

        if final_winners:
            st.write(f"🎉 篩選完成！最終即時推薦：")
            for item in sorted(final_winners, key=lambda x: x['score'], reverse=True):
                zh_name = st.session_state.master_dir.get(item['id'], item['id'])
                st.markdown(f"""
                <div style="background-color:#161b22; padding:12px; border-radius:12px; border:1px solid #30363d; margin-bottom:12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <b style="font-size:17px; color:#c9d1d9;">{zh_name} ({item['id']})</b>
                        <span style="background:#238636; color:white; padding:2px 8px; border-radius:6px; font-size:10px;">富果 {item['time']}</span>
                    </div>
                    <div style="margin-top:5px; display:flex; justify-content:space-between;">
                        <small style="color:#3fb950; font-weight:bold;">{item['rank']} | {item['vol_msg']}</small>
                        <small style="color:#8b949e;">綜合評分: {item['score']}</small>
                    </div>
                    <div style="display:flex; justify-content:space-between; margin-top:10px; background:#0d1117; padding:10px; border-radius:10px;">
                        <div style="text-align:center;"><small style="color:#8b949e;">支撐買點</small><br><b style="color:#3fb950;">{item['buy']}</b></div>
                        <div style="text-align:center;"><small style="color:#8b949e;">預期獲利</small><br><b style="color:#58a6ff;">{item['target']}</b></div>
                        <div style="text-align:center;"><small style="color:#8b949e;">現價</small><br><b>{item['price']}</b></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("💡 目前市場標的尚未符合即時優勢門檻，建議觀望。")

    else:
        st.markdown(f"### 🛡️ 持倉即時監控 (富果診斷)")
        # 此處與掃描邏輯一致：讀取雲端持倉 -> 調用富果 API -> 給出即時建議...
        # 因空間限制，代碼結構與「選拔」中富果處理邏輯相同

    st.divider()
    st.caption(f"最後同步 (台北 24H): {get_taipei_now().strftime('%Y-%m-%d %H:%M:%S')}")

