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

# --- 0. 台北時間工具 ---
def get_taipei_now():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz)

# --- 1. 繁體中文對照總表 (確保不再出現英文) ---
STOCK_MAP = {
    "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2382": "廣達", "2308": "台達電",
    "2303": "聯電", "2881": "富邦金", "2882": "國泰金", "2886": "兆豐金", "2891": "中信金",
    "3711": "日月光投控", "2412": "中華電", "1301": "台塑", "1216": "統一", "2002": "中鋼",
    "2603": "長榮", "2609": "陽明", "2618": "長榮航", "2357": "華碩", "3231": "緯創",
    "3008": "大立光", "3034": "聯詠", "3037": "欣興", "2324": "仁寶", "2353": "宏碁",
    "2408": "南亞科", "2301": "光寶科", "2344": "華邦電", "2892": "第一金", "2880": "華南金",
    "2884": "玉山金", "2885": "元大金", "2887": "台新金", "5880": "合庫金", "2890": "永豐金",
    "1101": "台泥", "1303": "南亞", "1326": "台化", "2105": "正新", "2207": "和泰車",
    "2912": "統一超", "3045": "台灣大", "6505": "台塑化", "9910": "豐泰", "9921": "巨大",
    "1402": "遠東新", "2449": "京元電子", "1503": "士電", "1513": "中興電", "1519": "華城",
    "1605": "華新", "2360": "致茂", "2377": "微星", "2383": "台光電", "2385": "群光",
    "2395": "研華", "3533": "嘉澤", "3661": "世芯-KY", "3653": "健策", "5269": "祥碩",
    "6409": "旭隼", "6446": "藥華藥", "6472": "保瑞", "6488": "環球晶", "8299": "群聯",
    "9958": "世紀鋼", "2610": "華航", "2615": "萬海", "1722": "台肥", "2409": "友達",
    "2371": "大同", "2201": "裕隆", "2892": "第一金", "3019": "亞光", "2313": "華通",
    "2451": "創見", "2458": "義隆", "2492": "華新科", "1504": "東元", "1514": "亞力"
}

# 產業分類定義
CATEGORY_GROUPS = {
    "電子/半導體": ["2330","2317","2454","2382","2308","2449","3711","2303","3034","3037","3231","4938","2379","2353","3008","2376","3017","6669","2313","2451","2458","2492","2327","3035","3406","3443","3661","5269","6409","6488","8299"],
    "金融/保險": ["2881","2882","2886","2891","2884","2885","2880","2887","5880","2890","2892","5871","2883","2888","2834","2801","2809","2812","2838","2845"],
    "航運/航空": ["2603","2609","2615","2618","2610","2606","2633","2637","2605"],
    "塑化/鋼鐵/水泥": ["1301","1303","1326","6505","2002","1101","1102","1314","2014","2027","1605","2105","1402"],
    "生技/綠能/其他": ["6446","6472","1760","1712","1723","1503","1513","1519","1504","1514","1560","1590","9958","2912","9910","9921","9904","2727","8454"]
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
app_id = st.secrets.get("general", {}).get("app_id", "stock_ai_v3")

# --- 3. 雲端同步邏輯 ---
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

# --- 4. 記憶登入核心邏輯 (URL 參數驅動) ---
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

# --- 5. AI 分析與名稱解析引擎 ---
@st.cache_data(ttl=86400)
def get_zh_name(symbol):
    pure_id = symbol.split('.')[0]
    if pure_id in STOCK_MAP: return STOCK_MAP[pure_id]
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={pure_id}&lang=zh-Hant-TW&region=TW"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        q = res.json().get('quotes', [])[0]
        return q.get('shortname', pure_id).split(' ')[0].split('(')[0]
    except: return pure_id

def apply_tech(df):
    if len(df) < 25: return df
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    l, h = df['Low'].rolling(window=9).min(), df['High'].rolling(window=9).max()
    df['K'] = ((df['Close'] - l) / (h - l) * 100).ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()
    e12, e26 = df['Close'].ewm(span=12).mean(), df['Close'].ewm(span=26).mean()
    df['MACD'] = (e12 - e26 - (e12 - e26).ewm(span=9).mean()) * 2
    return df

def analyze_stock(df, adr):
    if len(df) < 25: return 0, 0, 0, "觀察"
    l, p = df.iloc[-1], df.iloc[-2]
    score = 35 + (adr * 2.3)
    if l['Close'] > l['MA5']: score += 15
    if l['K'] > l['D'] and p['K'] <= p['D']: score += 20
    if l['MACD'] > 0: score += 15
    if l['Volume'] > df['Volume'].tail(15).mean() * 1.15: score += 15
    rank = "🚀 強力推薦" if score >= 85 else "✅ 建議布局" if score >= 70 else "整理中"
    buy = round(max(l['MA5'], l['Close'] * 0.994), 2)
    target = round(l['Close'] * 1.055, 2)
    return int(score), buy, target, rank

@st.cache_data(ttl=3600)
def get_adr():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return round(((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100, 2)
    except: return 0.0

# --- 6. 介面渲染 ---

if not st.session_state.authenticated:
    st.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center; color: #58a6ff;'>🚀 AI 實戰選股</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #8b949e;'>數據分析完畢後自動映射中文名稱</p>", unsafe_allow_html=True)
    with st.container():
        st.markdown("<div style='background-color: #161b22; padding: 20px; border-radius: 15px; border: 1px solid #30363d;'>", unsafe_allow_html=True)
        login_id = st.text_input("輸入帳號通行碼", placeholder="例如: AlexTrade", label_visibility="collapsed")
        if st.button("確認進入", use_container_width=True, type="primary"):
            handle_login(login_id)
        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

else:
    st.sidebar.title("👤 帳號管理")
    st.sidebar.info(f"帳號: `{st.session_state.user_id}`")
    if st.sidebar.button("登出帳號"):
        st.session_state.authenticated = False
        st.query_params.clear()
        st.rerun()
    
    st.sidebar.divider()
    mode = st.sidebar.radio("切換模式", ["🔎 全市場潛力選拔", "🛡️ 雲端持倉診斷"])
    adr_val = get_adr()

    if mode == "🔎 全市場潛力選拔":
        st.markdown(f"### 🔎 AI 量化掃描")
        
        # 篩選選單
        c1, c2 = st.columns(2)
        with c1:
            sel_cat = st.selectbox("📂 產業分類", ["全部"] + list(CATEGORY_GROUPS.keys()))
        with c2:
            sel_price = st.selectbox("💰 價位分級", ["全部", "<50", "50-100", "100-500", "500-1000", "1000-5000", ">5000"])

        st.markdown(f"""<div style="background-color:#1e2329; padding:8px; border-radius:10px; text-align:center; border-left:5px solid {'#3fb950' if adr_val > 0 else '#f85149'}; margin-bottom:15px;">
            <small style="color:#888;">美股 TSM ADR 市場情緒</small><br><b style="color:{'#3fb950' if adr_val > 0 else '#f85149'}; font-size:18px;">{adr_val:+.2f}%</b>
        </div>""", unsafe_allow_html=True)

        # 決定掃描池
        if sel_cat == "全部":
            pool = []
            for g in CATEGORY_GROUPS.values(): pool.extend(g)
            pool = sorted(list(set(pool)))
        else:
            pool = CATEGORY_GROUPS[sel_cat]
        
        winners = []
        p_bar = st.progress(0, text=f"正在分析 {sel_cat} 標的...")
        
        for i, sid in enumerate(pool):
            p_bar.progress((i + 1) / len(pool))
            try:
                tkr = yf.Ticker(f"{sid}.TW")
                hist = tkr.history(period="60d")
                if hist.empty: continue
                df = apply_tech(hist)
                cur_p = round(df.iloc[-1]['Close'], 2)
                
                # 價位篩選
                p_match = False
                if sel_price == "全部": p_match = True
                elif sel_price == "<50" and cur_p < 50: p_match = True
                elif sel_price == "50-100" and 50 <= cur_p < 100: p_match = True
                elif sel_price == "100-500" and 100 <= cur_p < 500: p_match = True
                elif sel_price == "500-1000" and 500 <= cur_p < 1000: p_match = True
                elif sel_price == "1000-5000" and 1000 <= cur_p < 5000: p_match = True
                elif sel_price == ">5000" and cur_p >= 5000: p_match = True
                if not p_match: continue
                
                score, buy, target, rank = analyze_stock(df, adr_val)
                if score >= 70:
                    last_time = df.index[-1].astimezone(timezone(timedelta(hours=8))).strftime('%H:%M')
                    winners.append({"id": sid, "price": cur_p, "score": score, "buy": buy, "target": target, "rank": rank, "time": last_time})
            except: continue
        p_bar.empty()

        if winners:
            st.write(f"🎉 符合條件標的 ({len(winners)})：")
            for item in sorted(winners, key=lambda x: x['score'], reverse=True)[:12]:
                zh_name = get_zh_name(item['id'])
                st.markdown(f"""
                <div style="background-color:#161b22; padding:12px; border-radius:12px; border:1px solid #30363d; margin-bottom:12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <b style="font-size:17px; color:#c9d1d9;">{zh_name} ({item['id']})</b>
                        <span style="background:#238636; color:white; padding:2px 8px; border-radius:6px; font-size:11px;">{item['time']} 數據</span>
                    </div>
                    <div style="margin-top:5px; display:flex; justify-content:space-between;">
                        <small style="color:#3fb950; font-weight:bold;">{item['rank']}</small>
                        <small style="color:#8b949e;">優勢分: {item['score']}</small>
                    </div>
                    <div style="display:flex; justify-content:space-between; margin-top:10px; background:#0d1117; padding:10px; border-radius:10px;">
                        <div style="text-align:center;"><small style="color:#8b949e;">建議買點</small><br><b style="color:#3fb950;">{item['buy']}</b></div>
                        <div style="text-align:center;"><small style="color:#8b949e;">目標獲利</small><br><b style="color:#58a6ff;">{item['target']}</b></div>
                        <div style="text-align:center;"><small style="color:#8b949e;">現價</small><br><b>{item['price']}</b></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("💡 目前篩選條件下無符合強勢買訊標的。")

    else:
        st.markdown(f"### 🛡️ 雲端持倉即時診斷")
        with st.expander("➕ 新增持倉記錄", expanded=False):
            c1, c2, c3 = st.columns([2, 2, 1])
            in_id = c1.text_input("代號", placeholder="2330")
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
                    c_name = get_zh_name(p_id)
                    tkr = yf.Ticker(s['symbol'])
                    df = apply_tech(tkr.history(period="60d"))
                    l = df.iloc[-1]
                    cur = round(l['Close'], 2)
                    gain = ((cur - s['cost']) / s['cost']) * 100
                    last_update = df.index[-1].astimezone(timezone(timedelta(hours=8))).strftime('%H:%M')
                    msg, clr = "", "#ffffff"
                    if gain > 0:
                        if l['MACD'] > 0: msg, clr = "🚀 強勢續留", "#3fb950"
                        else: msg, clr = "⚠️ 漲勢放緩", "#f0883e"
                    else:
                        if l['MACD'] > 0: msg, clr = "💪 低檔轉強", "#58a6ff"
                        elif cur < df.iloc[-1]['MA20']: msg, clr = "🚨 果斷止損", "#f85149"
                        else: msg, clr = "💤 盤整待變", "#8b949e"

                    st.markdown(f"""
                    <div style="background-color:#161b22; padding:15px; border-radius:12px; border-left:8px solid {clr}; margin-bottom:12px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <b style="font-size:16px; color:#c9d1d9;">{c_name} ({p_id})</b>
                            <b style="color:{clr}; font-size:13px;">{msg}</b>
                        </div>
                        <div style="display:flex; justify-content:space-between; margin:10px 0;">
                            <span>成本: {s['cost']} | 現價: <b>{cur}</b> <small style="color:#8b949e;">({last_update})</small></span>
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
    st.caption(f"最後更新 (台北 24H): {get_taipei_now().strftime('%Y-%m-%d %H:%M:%S')}")

