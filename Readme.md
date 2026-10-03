# AI-Driven Quantitative Algo Trading Agent

This project is an enterprise-grade algorithmic trading framework using Python, Streamlit, Zerodha Kite API v4, and Google Gemini. 

## System Architecture Data Flow
1. **Frontend (Streamlit):** Serves as the Control Room. Captures the OAuth tokens automatically via `st.query_params`.
2. **Background Threads:** `engine.py` operates in isolated Python threads so `dashboard.py` never freezes. 
3. **Agentic Strategy (Gemini):** Every afternoon, the `agent.py` queries `gemini-1.5-pro` using strict JSON schemas to output new Backtestable rules.
4. **Promotion Pipeline:** - `BACKTEST` -> (If successful) -> `PAPER TRADING` (10 days).
   - `PAPER TRADING` -> (If 7/10 days profitable) -> `LIVE EXECUTION`.
5. **Risk Gateways:** `engine.py` strictly forces `Capital * 0.10` per trade. At 15:20 IST, it flushes open Intraday orders. At 15:30 IST, `utils.py` securely emails the system log files.

## Environment Setup

1. Clone repo and install requirements:
```bash
pip install streamlit pandas plotly kiteconnect google-generativeai pytz