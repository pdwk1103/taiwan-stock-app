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

# --- 0. 台北時間工具 (24小時制) ---
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
            # 確保私鑰換行符號正確
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = service_account.Credentials.from_service_account_info(creds_dict)
            return firestore.Client(credentials=creds)
    except:
        return None
    return None

db = init_db()
app_id = st.secrets.get("general", {}).get("app_id", "stock_ai_v2")

# --- 2. 雲端核心邏輯 (增加 API 未啟用檢查) ---
def cloud_save(uid, data):
    if not db or not uid: return False
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("users").document(uid).collection("portfolio").document("data")
        doc_ref.set({
            "items": data,
            "last_updated": get_taipei_now(),
            "user_id": uid
        })
        return True
    except Exception as e:
        if "SERVICE_DISABLED" in str(e):
            st.error("❌ 雲端服務未啟用：請前往 Google Cloud Console 點擊『啟用 Cloud Firestore API』。")
        else:
            st.error(f"雲端儲存失敗: {e}")
        return False

def cloud_load(uid):
    if not db or not uid: return []
    try:
        doc_ref = db.collection("artifacts").document(app_id).collection("users").document(uid).collection("portfolio").document("data")
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict().get("items", [])
        return []
    except Exception as e:
        if "SERVICE_DISABLED" in str(e):
            st.warning("⚠️ 雲端服務未啟用，目前僅能使用暫存模式。")
        return []

# --- 3. 登入與持久化管理 ---
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

# --- 4. 技術分析與行情工具 ---
def get_tick(p):
    if p < 10: return 0.01
    elif p < 50: return 0.05
    elif p < 100: return 0.1
    elif p < 500: return 0.5
    elif p < 1000: return 1.0
    else: return 5.0

def compute_tech(df):
    if len(df) < 35: return df
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    low_9, high_9 = df['Low'].rolling(window=9).min(), df['High'].rolling(window=9).max()
    df['K'] = ((df['Close'] - low_9) / (high_9 - low_9) * 100).ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()
    ema12, ema26 = df['Close'].ewm(span=12).mean(), df['Close'].ewm(span=26).mean()
    df['MACD'] = (ema12 - ema26 - (ema12 - ema26).ewm(span=9).mean()) * 2
    return df

@st.cache_data(ttl=3600)
def get_stock_cname(symbol):
    try:
        res = requests.get(f"https://query2.finance.yahoo.com/v1/finance/search?q={symbol}&lang=zh-Hant-TW&region=TW", headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        for q in res.json().get('quotes', []):
            if q.get('symbol') == symbol:
                return q.get('shortname') or q.get('longname') or symbol
    except: pass
    return symbol

@st.cache_data(ttl=3600)
def get_adr_val():
    try:
        tsm = yf.Ticker("TSM").history(period="2d")
        return round(((tsm['Close'].iloc[-1] - tsm['Close'].iloc[-2]) / tsm['Close'].iloc[-2]) * 100, 2)
    except: return 0.0

def find_stock_data(q):
    if q.isdigit() and len(q) >= 4: return f"{q}.TW", get_stock_cname(f"{q}.TW")
    try:
        res = requests.get(f"https://query2.finance.yahoo.com/v1/finance/search?q={q}&lang=zh-Hant-TW&region=TW", headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        for quote in res.json().get('quotes', []):
            s = quote.get('symbol', '')
            if ".TW" in s or ".TWO" in s: return s, quote.get('shortname', s)
    except: pass
    return None, None

# --- 5. 介面渲染 ---

if not st.session_state.authenticated:
    st.markdown("<div style='height: 80px;'></div>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center; color: #58a6ff;'>🚀 AI 實戰航線</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #8b949e;'>輸入通行碼即可同步雲端持倉</p>", unsafe_allow_html=True)
    
    with st.container():
        st.markdown("<div style='background-color: #161b22; padding: 25px; border-radius: 15px; border: 1px solid #30363d;'>", unsafe_allow_html=True)
        login_id = st.text_input("通行碼", placeholder="例如: Alex770801", label_visibility="collapsed")
        if st.button("確認登入並同步", use_container_width=True, type="primary"):
            handle_login(login_id)
        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

else:
    st.sidebar.title("👤 個人資訊")
    st.sidebar.info(f"帳號: `{st.session_state.user_id}`")
    if st.sidebar.button("登出帳號"):
        st.session_state.authenticated = False
        st.session_state.user_id = ""
        st.query_params.clear()
        st.rerun()
    
    st.sidebar.divider()
    mode = st.sidebar.radio("切換功能", ["📢 AI 盤前推薦", "🛡️ 雲端持倉管理"])
    discount = st.sidebar.slider("券商折扣", 0.1, 1.0, 0.6)
    
    adr = get_adr_val()

    if mode == "📢 AI 盤前推薦":
        st.markdown(f"### 📢 今日 AI 推薦 - {st.session_state.user_id}")
        st.markdown(f"""<div style="background-color:#1e2329; padding:8px; border-radius:8px; text-align:center; border-left:5px solid {'#3fb950' if adr > 0 else '#f85149'}; margin-bottom:15px;">
            <small style="color:#888;">TSM ADR 連動</small> <b style="color:{'#3fb950' if adr > 0 else '#f85149'};">{adr:+.2f}%</b>
        </div>""", unsafe_allow_html=True)

        scan_list = ["2449", "2330", "2317", "2603", "2618", "2382", "2454", "3008", "2609", "3231"]
        recs = []
        with st.spinner("AI 正在獲取最新行情..."):
            for sid in scan_list:
                try:
                    full_sid = f"{sid}.TW"
                    tkr = yf.Ticker(full_sid)
                    df = compute_tech(tkr.history(period="60d"))
                    l, p = df.iloc[-1], df.iloc[-2]
                    score = 50 + (adr * 2)
                    if l['Close'] > l['MA5']: score += 15
                    if l['K'] > l['D'] and p['K'] <= p['D']: score += 15
                    if l['MACD'] > 0: score += 10
                    
                    if score >= 60:
                        t = get_tick(l['Close'])
                        cname = get_stock_cname(full_sid)
                        recs.append({"id": sid, "name": cname, "price": round(l['Close'], 2), "score": int(score), "buy": round(max(l['MA5'], l['Close'] - t), 2), "target": round(l['Close'] + t * 8, 2)})
                except: continue

        for item in sorted(recs, key=lambda x: x['score'], reverse=True):
            st.markdown(f"""<div style="background-color:#161b22; padding:12px; border-radius:10px; border:1px solid #30363d; margin-bottom:10px;"><div style="display:flex; justify-content:space-between;"><b>{item['name']} ({item['id']})</b><span style="color:#3fb950;">分: {item['score']}</span></div><div style="display:flex; justify-content:space-between; margin-top:5px; background:#0d1117; padding:8px; border-radius:8px;"><div style="text-align:center;"><small style="color:#888;">建議買點</small><br><b style="color:#3fb950;">{item['buy']}</b></div><div style="text-align:center;"><small style="color:#888;">目標獲利</small><br><b style="color:#58a6ff;">{item['target']}</b></div><div style="text-align:center;"><small style="color:#888;">現價</small><br><b>{item['price']}</b></div></div></div>""", unsafe_allow_html=True)

    else:
        st.markdown(f"### 🛡️ 持倉診斷 - {st.session_state.user_id}")
        
        db_status = "🟢 雲端已連線" if db else "🔴 雲端未就緒"
        st.markdown(f"<small style='color:#3fb950;'>● {db_status} (24H 台北時間)</small>", unsafe_allow_html=True)

        with st.expander("➕ 新增持倉記錄", expanded=False):
            c1, c2, c3 = st.columns([2, 2, 1])
            new_id = c1.text_input("名稱/代號", placeholder="2449")
            new_cost = c2.number_input("成本", value=None, placeholder="輸入單價", step=0.1)
            if c3.button("存入", use_container_width=True):
                if new_cost:
                    sym, name = find_stock_data(new_id)
                    if sym:
                        st.session_state.portfolio_list.append({"symbol": sym, "name": name, "cost": new_cost, "ts": time.time()})
                        if cloud_save(st.session_state.user_id, st.session_state.portfolio_list):
                            st.success(f"已同步雲端: {name}")
                            time.sleep(0.5)
                            st.rerun()
                else: st.error("請填寫成本")

        if not st.session_state.portfolio_list:
            st.info("目前雲端尚無紀錄")
        else:
            del_ts = None
            for s in st.session_state.portfolio_list:
                try:
                    tkr = yf.Ticker(s['symbol'])
                    df = compute_tech(tkr.history(period="60d"))
                    l = df.iloc[-1]
                    cur = round(l['Close'], 2)
                    gain = ((cur - s['cost']) / s['cost']) * 100
                    t = get_tick(cur)
                    msg, clr = "", "#ffffff"
                    if gain > 0:
                        if l['MACD'] > 0 and l['K'] > l['D']: msg, clr = "🚀 強勢續留", "#3fb950"
                        else: msg, clr = "⚠️ 建議減碼", "#f0883e"
                    else:
                        if l['MACD'] > 0: msg, clr = "💪 底部轉強", "#58a6ff"
                        elif cur < l['MA20']: msg, clr = "🚨 果斷止損", "#f85149"
                        else: msg, clr = "💤 盤整待變", "#8b949e"

                    st.markdown(f"""<div style="background-color:#161b22; padding:15px; border-radius:12px; border-left:8px solid {clr}; margin-bottom:12px;"><div style="display:flex; justify-content:space-between;"><b>{s['name']}</b><b style="color:{clr};">{msg}</b></div><div style="display:flex; justify-content:space-between; margin:10px 0;"><span>成本: {s['cost']} | 現價: <b>{cur}</b></span><span style="color:{clr}; font-size:18px;">{gain:+.2f}%</span></div></div>""", unsafe_allow_html=True)
                    if st.button(f"🗑️ 移除 {s['name']}", key=f"d_{s.get('ts', s['symbol'])}"):
                        del_ts = s.get('ts')
                except: continue

            if del_ts:
                st.session_state.portfolio_list = [i for i in st.session_state.portfolio_list if i.get('ts') != del_ts]
                if cloud_save(st.session_state.user_id, st.session_state.portfolio_list):
                    st.rerun()

    st.divider()
    if st.button("🔄 立即同步雲端資料"):
        st.session_state.portfolio_list = cloud_load(st.session_state.user_id)
        st.rerun()
    
    # 底部顯示台北時間 (24小時制)
    now_tp = get_taipei_now()
    st.caption(f"最後同步 (台北時間 24H): {now_tp.strftime('%Y-%m-%d %H:%M:%S')}")
