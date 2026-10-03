import streamlit as st
import time
import datetime
import pandas as pd
import os
from pathlib import Path
from broker import Broker
from agent import AlgoAgent
from engine import TradingEngine
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from broker import LiveDataManager
from utils import logger as algo_logger, current_log_file
import random

st.set_page_config(page_title="AlgoTrade Agent", layout="wide", initial_sidebar_state="collapsed")

# Custom CSS — compact navbar
st.markdown("""
<style>
    /* Hide defaults */
    #MainMenu, footer, header { visibility: hidden; }
    .stApp { background: #0e1117; }
    
    /* Navbar - moved to the very top with proper spacing */
    .navbar {
        background: #151821;
        border-radius: 0px;
        border: none;
        border-bottom: 1px solid #2d3139;
        padding: 8px 24px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 20px;
        margin-top: -20px;
        margin-left: -60px;
        margin-right: -60px;
        width: calc(100% + 120px);
    }
    .nav-brand {
        color: #4a90e2;
        font-weight: 700;
        font-size: 18px;
        white-space: nowrap;
        letter-spacing: 0.5px;
    }
    .nav-links { display: flex; gap: 6px; }
    .nav-link {
        padding: 8px 18px;
        border-radius: 8px;
        border: none;
        background: transparent;
        color: #8892a4;
        cursor: pointer;
        font-size: 14px;
        font-weight: 500;
        white-space: nowrap;
        transition: all 0.15s;
    }
    .nav-link:hover { background: #1a1c23; color: #fff; }
    .nav-link.active { background: #4a90e2; color: #fff; }
    .nav-auth {
        padding: 8px 18px;
        border-radius: 8px;
        border: none;
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
        white-space: nowrap;
    }
    .nav-auth.unauth { background: #e74c3c; color: #fff; }
    .nav-auth.unauth:hover { background: #c0392b; }
    .nav-auth.auth { background: #2ecc71; color: #000; }
    .nav-auth.auth:hover { background: #27ae60; }
    .nav-auth.mock { background: #f1c40f; color: #000; }
    .nav-auth.mock:hover { background: #d4ac0d; }

    /* Content cards */
    .strategy-container { background: #151821; padding: 25px; border-radius: 12px; border-left: 5px solid #4a90e2; margin-top: 15px; }
    .positive-change { color: #2ecc71; font-weight: bold; }
    .negative-change { color: #e74c3c; font-weight: bold; }
    .positive-bg { background-color: rgba(46, 204, 113, 0.15); }
    .negative-bg { background-color: rgba(231, 76, 60, 0.15); }

    /* Override stTabs to compact */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
        background: #151821;
        border-radius: 12px;
        padding: 5px;
        border: 1px solid #2d3139;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px !important;
        padding: 8px 16px !important;
        font-weight: 500;
        font-size: 13px;
        color: #8892a4;
    }
    .stTabs [aria-selected="true"] {
        background: #4a90e2 !important;
        color: white !important;
    }
    
    /* Order panel styling */
    .order-panel {
        background: #151821;
        border-radius: 12px;
        border: 1px solid #2d3139;
        padding: 20px;
        margin-bottom: 15px;
    }
    .order-panel h4 { color: #f1c40f; margin-top: 0; }
    
    /* Metric cards */
    .metric-card {
        background: #151821;
        border-radius: 12px;
        border: 1px solid #2d3139;
        padding: 15px;
        text-align: center;
    }
    .metric-card .value { font-size: 24px; font-weight: 700; }
    .metric-card .label { font-size: 12px; color: #8892a4; }
    
    /* Data tables */
    .dataframe { font-size: 13px; }
    
    /* Improve spacing */
    .block-container { padding-top: 1rem; }
    h1, h2, h3 { margin-top: 0; }
</style>
""", unsafe_allow_html=True)

import pandas as pd

def load_secrets_safely():
    try:
        if "ZERODHA_API_KEY" in st.secrets:
            return {k: st.secrets[k] for k in ["ZERODHA_API_KEY", "ZERODHA_API_SECRET", "GEMINI_API_KEY", "EMAIL_USER", "EMAIL_PASS", "MY_EMAIL"]}
    except Exception: pass
    secrets_file = Path(".streamlit/secrets.toml")
    if not secrets_file.exists():
        st.error("### ❌ Configuration Error: `.streamlit/secrets.toml` not found.")
        st.stop()
    parsed = {}
    with open(secrets_file, "r") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                parsed[k.strip()] = v.strip().strip('"').strip("'")
    return parsed

CONFIG = load_secrets_safely()

# === HELPERS ===
def color_change_inline(val):
    try:
        v = float(val)
        if v > 0: return 'color: #2ecc71; font-weight: bold;'
        elif v < 0: return 'color: #e74c3c; font-weight: bold;'
        else: return 'color: #f1c40f; font-weight: bold;'
    except: return ''

def color_pnl_inline(val):
    try:
        v = float(val)
        if v > 0: return 'color: #2ecc71; font-weight: bold;'
        else: return 'color: #e74c3c; font-weight: bold;'
    except: return ''

def format_market_grid(df):
    if df.empty: return df
    return df.style.map(lambda v: color_change_inline(v), subset=["Day Change %"]).map(
        lambda v: color_change_inline(v), subset=["LTP (₹)"]).map(
        lambda v: color_change_inline(v), subset=["Change (₹)"])

def style_pnl(val):
    try:
        v = float(val)
        classes = "positive-change" if v >= 0 else "negative-change"
        return f'<span class="{classes}">₹{v:+,.2f}</span>'
    except: return str(val)

# === SESSION STATE ===
if "access_token" not in st.session_state: st.session_state["access_token"] = None
if "engine" not in st.session_state: st.session_state["engine"] = None
if "active_tab" not in st.session_state: st.session_state["active_tab"] = "explore"
if "websocket_started" not in st.session_state: st.session_state["websocket_started"] = False
if "last_paper_run" not in st.session_state: st.session_state["last_paper_run"] = None

# Load strategies from disk ONCE when session starts
if "strategies_registry" not in st.session_state:
    st.session_state["strategies_registry"] = []

def load_strategies_from_disk():
    """Load and normalize all .json strategy files from the strategies/ folder."""
    import json
    strat_dir = "strategies"
    loaded = []
    existing_names = {s.get("strategy_name", "") for s in st.session_state["strategies_registry"]}
    
    if not os.path.exists(strat_dir):
        return
    
    for fn in sorted(os.listdir(strat_dir)):
        if not fn.endswith(".json"):
            continue
        fp = os.path.join(strat_dir, fn)
        try:
            with open(fp, "r") as f:
                raw = json.load(f)
        except Exception as e:
            algo_logger.warning(f"Could not parse {fn}: {e}")
            continue
        
        normalized = {}
        normalized["strategy_name"] = raw.get("strategy_name") or raw.get("name") or fn.replace(".json", "").replace("_", " ").title()
        
        if normalized["strategy_name"] in existing_names:
            continue
        
        normalized["description"] = raw.get("description") or raw.get("desc") or ""
        normalized["entry_logic"] = raw.get("entry_logic") or raw.get("entry") or "No entry logic defined"
        normalized["sl_percentage"] = float(raw.get("sl_percentage") or raw.get("sl", 1.0))
        normalized["tp_percentage"] = float(raw.get("tp_percentage") or raw.get("tp", 2.0))
        
        indicators_raw = raw.get("indicators", [])
        normalized_indicators = []
        for ind in indicators_raw:
            if isinstance(ind, dict):
                normalized_indicators.append({
                    "name": ind.get("name", str(ind.get("type", "IND"))),
                    "period": int(ind.get("period", 14))
                })
            elif isinstance(ind, str):
                parts = ind.split("_")
                if len(parts) >= 2 and parts[-1].isdigit():
                    name = "_".join(parts[:-1])
                    period = int(parts[-1])
                else:
                    name = ind
                    period = 14
                normalized_indicators.append({"name": name, "period": period})
        normalized["indicators"] = normalized_indicators
        
        loaded.append(normalized)
        existing_names.add(normalized["strategy_name"])
        algo_logger.info(f"Loaded strategy: '{normalized['strategy_name']}' from {fn}")
    
    if not loaded and not st.session_state["strategies_registry"]:
        loaded.append({
            "strategy_name": "Structural Volatility Breakout",
            "description": "Multi-lookback channel extraction.",
            "indicators": [{"name": "EMA", "period": 20}, {"name": "RSI", "period": 14}],
            "entry_logic": "Close > High_Channel_Boundary and RSI > 55",
            "sl_percentage": 1.0,
            "tp_percentage": 2.5
        })
    
    st.session_state["strategies_registry"].extend(loaded)

# Run disk loading once
load_strategies_from_disk()

# === TOKEN EXTRACTION ===
qp = st.query_params
if "request_token" in qp and st.session_state["access_token"] is None:
    req_token = qp["request_token"]
    algo_logger.info(f"Dashboard: request_token detected: {req_token[:20]}...")
    temp_broker = Broker(CONFIG["ZERODHA_API_KEY"], CONFIG["ZERODHA_API_SECRET"])
    acc_token = temp_broker.generate_session(req_token)
    if acc_token:
        st.session_state["access_token"] = acc_token
        st.query_params.clear()
        st.rerun()

# ============================================================
# FULL-WIDTH NAVBAR at the very top
# ============================================================
st.markdown('<div class="navbar">', unsafe_allow_html=True)
nav_cols = st.columns([1.2, 4.0, 1.8])
with nav_cols[0]:
    st.markdown('<div class="nav-brand">🤖 AlgoTrade Agent</div>', unsafe_allow_html=True)
with nav_cols[1]:
    tabs = {"explore": "🔭 Explore", "live": "🔴 Live", "paper": "📝 Paper", "backtest": "📊 Backtest", "ai": "🧠 AI"}
    pill_cols = st.columns(len(tabs))
    for i, (key, label) in enumerate(tabs.items()):
        with pill_cols[i]:
            active = st.session_state["active_tab"] == key
            btn_class_style = "nav-link active" if active else "nav-link"
            if st.button(label, key=f"nav_{key}", help=key):
                st.session_state["active_tab"] = key
                st.rerun()
with nav_cols[2]:
    if st.session_state["access_token"]:
        btn_class = "nav-auth auth"
        if st.button("🔓 Disconnect", key="auth_btn_top"):
            st.session_state["access_token"] = None
            st.session_state["engine"] = None
            st.session_state["websocket_started"] = False
            st.rerun()
    else:
        a, b = st.columns(2)
        with a:
            login_url = f"https://kite.zerodha.com/connect/login?api_key={CONFIG['ZERODHA_API_KEY']}"
            st.markdown(f'<a href="{login_url}" target="_self"><button class="nav-auth unauth" style="width:100%;cursor:pointer;">🔑 Login</button></a>', unsafe_allow_html=True)
        with b:
            if st.button("🧪 Sandbox", key="sandbox_top"):
                st.session_state["access_token"] = "MOCK_DEVELOPER_TOKEN"
                st.rerun()
st.markdown('</div>', unsafe_allow_html=True)

# === ENGINE INIT ===
if st.session_state["access_token"] and st.session_state["engine"] is None:
    algo_logger.info("Dashboard: Creating Broker/Agent/Engine...")
    brk = Broker(CONFIG["ZERODHA_API_KEY"], CONFIG["ZERODHA_API_SECRET"], st.session_state["access_token"])
    agt = AlgoAgent(CONFIG["GEMINI_API_KEY"])
    eng = TradingEngine(brk, agt, {})
    st.session_state["engine"] = eng
    
    # Copy strategies to broker for paper trading
    brk.strategies_registry = st.session_state["strategies_registry"]

if st.session_state["engine"] and not st.session_state["websocket_started"]:
    try:
        # Limit WebSocket tokens to first 500 to avoid connection issues
        token_list = [meta["token"] for meta in st.session_state["engine"].broker.symbol_registry.values()][:500]
        if token_list:
            st.session_state["engine"].broker.start_live_tracking(token_list)
            st.session_state["websocket_started"] = True
        else:
            algo_logger.warning("No tokens available for WebSocket subscription.")
    except Exception as e:
        algo_logger.error(f"WS init: {e}")

eng = st.session_state["engine"]
active = st.session_state["active_tab"]

# ============================================================
# TAB CONTENT
# ============================================================

# ----- TAB: EXPLORE -----
if active == "explore":
    st.markdown('<h2 style="margin-bottom:0;">🔭 Market Explorer</h2>', unsafe_allow_html=True)
    
    if eng is None:
        st.warning("Connect to Zerodha using the Login button in the navbar above.")
    else:
        # Get available symbols
        symbols_list = eng.broker.get_symbols_list()
        
        e1, e2 = st.columns([2.5, 1])
        with e2:
            st.markdown('<div class="order-panel"><h4>⚙️ Chart Settings</h4>', unsafe_allow_html=True)
            # Dropdown for symbol instead of text input
            default_idx = 0
            if "RELIANCE" in symbols_list:
                default_idx = symbols_list.index("RELIANCE")
            ticker = st.selectbox("Select Symbol", symbols_list, index=default_idx, key="exp_tick")
            tf = st.selectbox("Timeframe", ["1D","1W","1M","5m","15m","30m","60m"], key="exp_tf",
                              help="1D=Daily, 5m=5 Minute, 15m=15 Minute, etc.")
            days = st.number_input("Data Days", 1, 1095, 30, 1, key="exp_days")
            st.markdown('</div>', unsafe_allow_html=True)
            
            # --- LIVE ORDER PLACEMENT ---
            st.markdown('<div class="order-panel"><h4>💰 Place Live Order</h4>', unsafe_allow_html=True)
            order_symbol = st.selectbox("Symbol", symbols_list, index=default_idx, key="ord_sym", label_visibility="collapsed")
            o1, o2 = st.columns(2)
            with o1:
                order_type = st.selectbox("Type", ["MARKET", "LIMIT"], key="ord_type")
            with o2:
                quantity = st.number_input("Qty", 1, 10000, 10, 1, key="ord_qty")
            limit_price = 0.0
            if order_type == "LIMIT":
                limit_price = st.number_input("Limit Price (₹)", 0.0, 100000.0, 100.0, 0.05, key="ord_price")
            
            col_buy, col_sell = st.columns(2)
            with col_buy:
                if st.button("✅ BUY", key="ord_buy", use_container_width=True, type="primary"):
                    result = eng.broker.place_order(order_symbol, "BUY", quantity, order_type, limit_price)
                    if result.get("status") == "success":
                        st.success(result["message"])
                    else:
                        st.error(result.get("message", "Order failed"))
            with col_sell:
                if st.button("❌ SELL", key="ord_sell", use_container_width=True):
                    result = eng.broker.place_order(order_symbol, "SELL", quantity, order_type, limit_price)
                    if result.get("status") == "success":
                        st.success(result["message"])
                    else:
                        st.error(result.get("message", "Order failed"))
            st.markdown('</div>', unsafe_allow_html=True)
        
        with e1:
            if st.button("📈 Load Chart", key="exp_load", type="primary"):
                with st.spinner("Loading chart data..."):
                    try:
                        # Map UI timeframe to days adjustment
                        interval_map = {"1D": "day", "1W": "week", "1M": "month", "5m": "5minute", 
                                        "15m": "15minute", "30m": "30minute", "60m": "60minute"}
                        kite_interval = interval_map.get(tf, "day")
                        
                        df = eng.broker.get_historical_bars(ticker, days=days, interval=kite_interval)
                        if df is not None and not df.empty:
                            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7,0.3])
                            fig.add_trace(go.Candlestick(x=df.get('date',df.index), open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="Price"), row=1, col=1)
                            fig.add_trace(go.Bar(x=df.get('date',df.index), y=df['volume'], name="Volume", marker_color='rgba(158,202,225,0.6)'), row=2, col=1)
                            fig.update_layout(height=650, template="plotly_dark", title=f"{ticker} - {tf} Timeframe", xaxis_rangeslider_visible=False)
                            st.plotly_chart(fig, width='stretch')
                            
                            # Stats
                            c1, c2, c3, c4 = st.columns(4)
                            with c1: st.metric("High", f"₹{df['high'].max():,.2f}")
                            with c2: st.metric("Low", f"₹{df['low'].min():,.2f}")
                            with c3: st.metric("Avg Vol", f"{df['volume'].mean():,.0f}")
                            with c4: st.metric("Return", f"{((df['close'].iloc[-1]-df['close'].iloc[0])/df['close'].iloc[0])*100:+.2f}%")
                        else:
                            st.warning("No data available for this symbol/timeframe combination.")
                    except Exception as e:
                        st.error(f"Failed to load chart: {e}")
            
            # Show live price if available
            if ticker in eng.broker.symbol_registry:
                token = eng.broker.symbol_registry[ticker]["token"]
                if token in eng.broker.data_manager.ticks:
                    tick_data = eng.broker.data_manager.ticks[token]
                    ltp = tick_data.get("ltp", 0)
                    chg = tick_data.get("change", 0)
                    st.info(f"**Live:** {ticker} @ ₹{ltp:,} ({chg:+.2f}%)")

# ----- TAB: LIVE -----
elif active == "live":
    st.markdown('<h2 style="margin-bottom:0;">🔴 Live Tracking</h2>', unsafe_allow_html=True)
    if eng:
        # Compact status bar - WebSocket status as a small badge at top right
        ws_status = "🟢" if (eng.broker.kws is not None) else "🔴"
        sym_count = len(eng.broker.symbol_registry)
        st.markdown(f'<div style="display:flex;justify-content:space-between;align-items:center;background:#151821;border-radius:8px;padding:6px 16px;margin-bottom:12px;border:1px solid #2d3139;font-size:13px;">'
                    f'<span>💰 <strong>Balance:</strong> <span id="bal_val">Loading...</span></span>'
                    f'<span>⚡ <strong>Engine:</strong> {"RUNNING" if eng.is_running else "IDLE"}</span>'
                    f'<span>{ws_status} <strong>WS:</strong> {"Connected" if eng.broker.kws else "Idle"}</span>'
                    f'<span>📊 <strong>Symbols:</strong> {sym_count}</span>'
                    f'</div>', unsafe_allow_html=True)
        # Update balance asynchronously
        try: 
            bal = eng.broker.get_live_funds()
            st.markdown(f'<script>document.getElementById("bal_val").innerText="₹{bal:,.2f}"</script>', unsafe_allow_html=True)
        except: 
            pass

        # Scanner results in Live tab (moved from AI tab)
        st.subheader("🎯 Market Scan")
        scan_col1, scan_col2 = st.columns([1, 3])
        with scan_col1:
            if st.button("🔍 Scan Market Now", key="live_scan_btn", type="primary"):
                with st.spinner("AI analyzing market opportunities..."):
                    try:
                        # Use limited symbols for scan to avoid rate limiting
                        md = eng.broker.get_live_market_grid(max_symbols=100)
                        if md is not None and not md.empty:
                            analysis = eng.agent.analyze_stock_opportunities(md.to_dict('records'))
                            st.session_state["last_scan"] = analysis
                            st.success("Scan complete!")
                        else:
                            st.error("No market data available.")
                    except Exception as e:
                        st.error(f"Scan failed: {e}")
        
        with scan_col2:
            if "last_scan" in st.session_state:
                a = st.session_state["last_scan"]
                sent = a.get("market_sentiment", "NEUTRAL")
                sent_color = {"BULLISH":"#2ecc71","BEARISH":"#e74c3c","NEUTRAL":"#f1c40f"}.get(sent,"#f1c40f")
                st.markdown(f'<span style="color:{sent_color};font-weight:700;">📊 Sentiment: {sent}</span> | '
                            f'🏆 Best: <strong style="color:{sent_color};">{a.get("best_opportunity","N/A")}</strong>', unsafe_allow_html=True)

        # Show scan results in a table if available
        if "last_scan" in st.session_state:
            scan_data = st.session_state["last_scan"]
            opportunities = scan_data.get("ranked_opportunities", [])
            if opportunities:
                scan_df = pd.DataFrame(opportunities)
                # Rename columns for display
                scan_df_display = scan_df.rename(columns={
                    "symbol": "Symbol", "recommendation": "Rec", 
                    "profit_probability_percent": "Profit %", "expected_return_percent": "Exp Return %",
                    "risk_level": "Risk", "reasoning": "Reason"
                })
                
                # Style the dataframe
                def highlight_rec(val):
                    if val == "BUY": return 'background-color: rgba(46,204,113,0.3); color: #2ecc71; font-weight: bold;'
                    elif val == "SELL": return 'background-color: rgba(231,76,60,0.3); color: #e74c3c; font-weight: bold;'
                    return ''
                
                def highlight_prob(val):
                    try:
                        v = float(val)
                        if v >= 60: return 'color: #2ecc71; font-weight: bold;'
                        elif v >= 40: return 'color: #f1c40f; font-weight: bold;'
                        else: return 'color: #e74c3c; font-weight: bold;'
                    except: return ''
                
                styled_scan = scan_df_display.style.map(highlight_rec, subset=["Rec"]).map(highlight_prob, subset=["Profit %"])
                st.dataframe(styled_scan, width='stretch', hide_index=True, use_container_width=True)

        st.divider()

        # Enhanced Live Watchlist
        st.subheader("📋 Enhanced Watchlist")
        w1, w2 = st.columns([1, 1])
        with w1:
            st.markdown("**Market Summary**")
            try:
                md = eng.broker.get_live_market_grid()
                if not md.empty:
                    # Calculate summary stats
                    avg_change = md["Day Change %"].mean()
                    advancers = len(md[md["Day Change %"] > 0])
                    decliners = len(md[md["Day Change %"] < 0])
                    total_volume = md["Traded Volume"].sum()
                    
                    sc1, sc2, sc3, sc4 = st.columns(4)
                    with sc1: st.metric("Avg Change", f"{avg_change:+.2f}%")
                    with sc2: st.metric("🟢 Advancers", advancers)
                    with sc3: st.metric("🔴 Decliners", decliners)
                    with sc4: st.metric("Total Vol", f"{total_volume/1000000:.1f}M")
                    
                    st.dataframe(format_market_grid(md), width='stretch', hide_index=True)
            except:
                st.warning("Market data unavailable.")

        with w2:
            st.markdown("**💰 Holdings & P&L**")
            try:
                h = eng.broker.get_portfolio_holdings()
                st.dataframe(h, width='stretch', hide_index=True)
                # Calculate total P&L
                pnl_cols = [c for c in h.columns if 'pnl' in c.lower() or 'p&l' in c.lower() or 'P&L' in c]
                if pnl_cols:
                    tp = h[pnl_cols[0]].sum() if not h.empty else 0
                else:
                    tp = h.get("Unrealized PnL", pd.Series([0])).sum() if not h.empty else 0
                st.markdown(f'#### Total P&L: <span class="{"positive-change" if tp>=0 else "negative-change"}">₹{tp:+,.2f}</span>', unsafe_allow_html=True)
            except:
                st.info("Holdings unavailable.")

        st.divider()
        
        o1, o2 = st.columns(2)
        with o1:
            st.subheader("📂 Orders")
            try: st.dataframe(eng.broker.get_order_book(), width='stretch', hide_index=True)
            except: st.info("Order book unavailable.")
        with o2:
            st.subheader("📈 Positions")
            try:
                pos = eng.broker.get_positions()
                if not pos.empty:
                    st.dataframe(pos, width='stretch', hide_index=True)
                else:
                    st.info("No open positions.")
            except:
                st.info("Positions unavailable.")

        try:
            if st.session_state["access_token"] != "MOCK_DEVELOPER_TOKEN":
                eng.broker.sync_live_orders()
        except:
            pass

        st.divider()
        st.subheader("🖥️ Logs")
        if os.path.exists(current_log_file):
            with open(current_log_file, "r") as f:
                logs = "".join(f.readlines()[-30:])
                st.code(logs, language="bash", line_numbers=True)
        else:
            st.code("Initializing...", language="bash")
    else:
        st.info("Connect to Zerodha using the Login button in the navbar above.")

# ----- TAB: PAPER -----
elif active == "paper":
    st.markdown('<h2 style="margin-bottom:0;">📝 Paper Trading</h2>', unsafe_allow_html=True)
    if eng:
        # Run paper trading cycle
        now = datetime.datetime.now()
        if st.session_state["last_paper_run"] is None or (now - st.session_state["last_paper_run"]).total_seconds() > 300:
            eng.run_intraday_paper_trading()
            st.session_state["last_paper_run"] = now
        
        # Summary
        summary = eng.get_paper_trading_summary()
        p1, p2, p3, p4, p5 = st.columns(5)
        with p1: st.metric("Total Trades", summary["total_trades"])
        with p2: st.metric("✅ Wins", summary["winning_trades"])
        with p3: st.metric("❌ Losses", summary["losing_trades"])
        with p4: st.metric("Win Rate", f'{summary["win_rate"]}%')
        with p5: st.metric("Open Positions", summary["open_positions"])
        
        st.markdown(f'<h3>Total P&L: <span class="{"positive-change" if summary["total_pnl_pct"]>=0 else "negative-change"}">{summary["total_pnl_pct"]:+.2f}%</span></h3>', unsafe_allow_html=True)
        
        st.subheader("📊 Active Positions")
        open_trades = [t for t in eng.intraday_paper_trades if t.get("Status") == "OPEN"]
        if open_trades:
            open_df = pd.DataFrame(open_trades)
            st.dataframe(open_df, width='stretch', hide_index=True)
        else:
            st.info("No open positions.")
        
        st.subheader("📜 Trade History")
        if eng.paper_trades:
            pt_df = pd.DataFrame(eng.paper_trades)
            # Show last 50 trades
            st.dataframe(pt_df.tail(50), width='stretch', hide_index=True)
        else:
            st.info("No trades yet. The system will automatically generate intraday trades.")
        
        # Manual trade option
        st.divider()
        st.markdown("**🧪 Manual Test Trade**")
        p_col1, p_col2, p_col3 = st.columns(3)
        with p_col1:
            symbols_list = eng.broker.get_symbols_list()
            sym = st.selectbox("Symbol", symbols_list, key="ppt_s")
        with p_col2:
            act = st.selectbox("Action", ["BUY","SELL"], key="ppt_a")
        with p_col3:
            qty = st.number_input("Qty", 1, 10000, 10, 1, key="ppt_qty")
        
        if st.button("🚀 Execute Paper Trade", key="ppt_b"):
            mp = round(random.uniform(200, 3500), 2)
            eng.paper_trades.append({
                "Symbol": sym, "Strategy": "Manual", "Action": act, 
                "Price": mp, "Qty": qty,
                "Time": datetime.datetime.now().isoformat(), "Status": "SIMULATED"
            })
            st.success(f"✅ {act} {qty} x {sym} @ ₹{mp}")
            st.rerun()
    else:
        st.warning("Connect first.")

# ----- TAB: BACKTEST -----
elif active == "backtest":
    st.markdown('<h2 style="margin-bottom:0;">📊 Backtest Lab</h2>', unsafe_allow_html=True)
    if eng:
        names = [s["strategy_name"] for s in st.session_state["strategies_registry"] if "strategy_name" in s]
        if not names:
            st.warning("No strategies. Generate one in AI Hub.")
        else:
            c1, c2 = st.columns(2)
            with c1:
                sel = st.selectbox("Strategy", names, key="bt_s")
                chosen = next(s for s in st.session_state["strategies_registry"] if s.get("strategy_name") == sel)
            with c2:
                symbols_list = eng.broker.get_symbols_list()
                sym = st.selectbox("Symbol", symbols_list, key="bt_sym")
            
            bt_col1, bt_col2, bt_col3 = st.columns(3)
            with bt_col1:
                bt_days = st.number_input("Days", 30, 1095, 365, 30, key="bt_days")
            with bt_col2:
                bt_tf = st.selectbox("Timeframe", ["1D", "1W", "5m", "15m", "30m"], key="bt_tf")
            with bt_col3:
                st.markdown("<br>", unsafe_allow_html=True)
                run_bt = st.button("🚀 Run Backtest", key="bt_run", type="primary", use_container_width=True)
            
            if run_bt:
                with st.spinner("Running backtest..."):
                    interval_map = {"1D": "day", "1W": "week", "5m": "5minute", "15m": "15minute", "30m": "30minute"}
                    kite_interval = interval_map.get(bt_tf, "day")
                    hist = eng.broker.get_historical_bars(sym, days=bt_days, interval=kite_interval)
                    res = eng.evaluate_backtest(chosen, hist)
                    if "error" in res:
                        st.error(res["error"])
                    else:
                        st.success("Backtest completed!")
                        # Metrics
                        cols = st.columns(len(res["metrics"]))
                        for i, (k, v) in enumerate(res["metrics"].items()):
                            cols[i].metric(k, v)
                        
                        # Chart with buy/sell markers and buy & hold comparison
                        cdf = res["chart_data"]
                        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.6, 0.4])
                        
                        # Price line
                        fig.add_trace(go.Scatter(x=cdf['date'], y=cdf['close'], name="Price", line=dict(color='#4a90e2', width=1.5)), row=1, col=1)
                        
                        # Buy signals (green triangles)
                        buy_data = res.get("buy_signals", {"dates": [], "prices": []})
                        if buy_data["dates"]:
                            fig.add_trace(go.Scatter(
                                x=buy_data["dates"], y=buy_data["prices"],
                                mode='markers', name='BUY',
                                marker=dict(symbol='triangle-up', size=12, color='#2ecc71', line=dict(width=1, color='white'))
                            ), row=1, col=1)
                        
                        # Sell signals (red triangles)
                        sell_data = res.get("sell_signals", {"dates": [], "prices": []})
                        if sell_data["dates"]:
                            fig.add_trace(go.Scatter(
                                x=sell_data["dates"], y=sell_data["prices"],
                                mode='markers', name='SELL',
                                marker=dict(symbol='triangle-down', size=12, color='#e74c3c', line=dict(width=1, color='white'))
                            ), row=1, col=1)
                        
                        # Strategy equity curve
                        fig.add_trace(go.Scatter(x=cdf['date'], y=cdf['cumulative_equity'], name="Strategy Equity", line=dict(color='#2ecc71', width=2)), row=2, col=1)
                        
                        # Buy & Hold equity curve
                        if 'buy_hold_equity' in cdf.columns:
                            fig.add_trace(go.Scatter(x=cdf['date'], y=cdf['buy_hold_equity'], name="Buy & Hold", line=dict(color='#f1c40f', width=1.5, dash='dash')), row=2, col=1)
                        
                        fig.update_layout(height=550, template="plotly_dark", hovermode='x unified')
                        st.plotly_chart(fig, width='stretch')
                        
                        # Trade Log Table
                        trade_log = res.get("trade_log", [])
                        if trade_log:
                            st.subheader("📋 Trade Log")
                            tl_df = pd.DataFrame(trade_log)
                            # Color PnL column
                            def color_pnl_bt(val):
                                try:
                                    v = float(str(val).replace('₹','').replace(',',''))
                                    if v > 0: return 'color: #2ecc71; font-weight: bold;'
                                    elif v < 0: return 'color: #e74c3c; font-weight: bold;'
                                except: return ''
                            styled_tl = tl_df.style.map(lambda v: color_pnl_bt(v), subset=["PnL%", "PnL (₹)"])
                            st.dataframe(styled_tl, width='stretch', hide_index=True, use_container_width=True)
    else:
        st.warning("Connect first.")

# ----- TAB: AI HUB -----
elif active == "ai":
    st.markdown('<h2 style="margin-bottom:0;">🧠 AI Alpha Hub</h2>', unsafe_allow_html=True)
    if eng:
        # Strategy Generator
        st.subheader("🎯 AI Strategy Generator")
        st.info("Generate a new quantitative trading strategy using AI. Strategies are saved and available in other tabs.")
        
        # Custom strategy input
        user_prompt = st.text_area(
            "📝 Describe your strategy (optional)",
            placeholder="e.g., Create a strategy using Supertrend for long-only trades with RSI confirmation\n\nLeave blank for AI to generate autonomously.",
            key="ai_user_prompt",
            height=80
        )
        
        gen_col1, gen_col2 = st.columns([1, 3])
        with gen_col1:
            generate_clicked = st.button("🧠 Generate New Strategy", key="gen_strat", type="primary", use_container_width=True)
        with gen_col2:
            if user_prompt.strip():
                st.caption(f"🔧 Custom request: {user_prompt.strip()[:80]}{'...' if len(user_prompt.strip()) > 80 else ''}")
            else:
                st.caption("🤖 Autonomous mode - AI will choose the strategy design")
        
        if generate_clicked:
            with st.spinner("AI creating strategy..."):
                try:
                    ns = eng.agent.generate_daily_strategy(user_prompt=user_prompt)
                    
                    # Check if fallback was used (AI unavailable)
                    was_fallback = isinstance(ns, dict) and ns.get("_fallback")
                    if was_fallback:
                        st.warning("⚠️ **AI service unavailable** (503). Using fallback strategy instead. Check logs for details.")
                        # Remove _fallback flag before saving
                        if isinstance(ns, dict):
                            ns.pop("_fallback", None)
                    
                    import re, json
                    if isinstance(ns, str):
                        cs = ns.strip()
                        if cs.startswith("```json"):
                            cs = cs.split("```json")[1].split("```")[0].strip()
                        elif cs.startswith("```"):
                            cs = cs.split("```")[1].split("```")[0].strip()
                        sd = json.loads(cs)
                    else:
                        sd = dict(ns) if not isinstance(ns, dict) else ns
                    os.makedirs("strategies", exist_ok=True)
                    fn = re.sub(r'[^a-zA-Z0-9_\-]', '_', sd.get("strategy_name", "AI")).lower()
                    fp = os.path.join("strategies", f"{fn}.json")
                    with open(fp, "w") as f:
                        json.dump(sd, f, indent=4)
                    st.session_state["strategies_registry"].append(sd)
                    st.success(f"✅ Strategy '{sd.get('strategy_name')}' generated and saved!")
                    if not was_fallback:
                        st.balloons()
                except Exception as e:
                    st.error(f"Strategy generation failed: {e}")

        st.divider()
        st.subheader("📚 Strategy Library")
        
        # Show strategy count
        st.markdown(f"**Loaded Strategies:** {len(st.session_state['strategies_registry'])}")
        
        for idx, strat in enumerate(st.session_state["strategies_registry"]):
            st.markdown(f'<div class="strategy-container">'
                        f'<h3>⚡ #{idx+1}: {strat.get("strategy_name","?")}</h3>'
                        f'<p style="color:#b3b9c1;">{strat.get("description","")}</p>'
                        f'<hr style="border:0.5px solid #2d3139;margin:15px 0;">'
                        f'<div style="display:flex;gap:30px;flex-wrap:wrap;">'
                        f'<div><strong>SL:</strong> <span style="color:#e74c3c;">{strat.get("sl_percentage","0")}%</span></div>'
                        f'<div><strong>TP:</strong> <span style="color:#2ecc71;">{strat.get("tp_percentage","0")}%</span></div>'
                        f'<div><strong>Logic:</strong> <code style="background:#0e1117;padding:4px 8px;border-radius:4px;color:#f1c40f;">{strat.get("entry_logic","")}</code></div>'
                        f'</div></div>', unsafe_allow_html=True)
    else:
        st.warning("Connect to Zerodha to use AI features.")