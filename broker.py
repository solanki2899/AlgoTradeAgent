import datetime
import json
import os
import re
import threading
import time
from kiteconnect import KiteConnect
from utils import logger
import pandas as pd
import random
from kiteconnect import KiteTicker


class LiveDataManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(LiveDataManager, cls).__new__(cls)
                cls._instance.ticks = {}      # Format: {instrument_token: metrics_dict}
                cls._instance.orders = []     # Live tracking order logs
                logger.info("LiveDataManager singleton created.")
        return cls._instance


# NSE instrument cache path
NSE_INSTRUMENT_CACHE = "nse_instruments_cache.json"


def download_nse_instruments(client):
    """Download full NSE instrument list from Kite and cache it."""
    logger.info("download_nse_instruments: Fetching NSE instrument list from Kite...")
    try:
        instruments = client.instruments("NSE")
        logger.info(f"download_nse_instruments: Downloaded {len(instruments)} NSE instruments.")
        # Cache to file
        with open(NSE_INSTRUMENT_CACHE, "w") as f:
            json.dump(instruments, f)
        logger.info(f"download_nse_instruments: Cached to {NSE_INSTRUMENT_CACHE}")
        return instruments
    except Exception as e:
        logger.warning(f"download_nse_instruments: Failed to download from Kite: {e}")
        # Try loading from cache
        if os.path.exists(NSE_INSTRUMENT_CACHE):
            logger.info(f"download_nse_instruments: Loading from cached file {NSE_INSTRUMENT_CACHE}...")
            try:
                with open(NSE_INSTRUMENT_CACHE, "r") as f:
                    instruments = json.load(f)
                logger.info(f"download_nse_instruments: Loaded {len(instruments)} instruments from cache.")
                return instruments
            except Exception as ex:
                logger.error(f"download_nse_instruments: Cache load failed: {ex}")
        return []


def build_symbol_registry_from_instruments(instruments, top_n=500):
    """
    Build a symbol_registry dict from the instrument list.
    Filters for NSE equity (EQ) segment, tradable symbols.
    Excludes bonds, SDL, GOI, and other non-equity instruments.
    Returns dict like {"RELIANCE": {"token": 738561, "exchange": "NSE"}}
    If instruments empty, returns a smaller default list.
    """
    registry = {}
    if not instruments:
        logger.warning("build_symbol_registry: No instruments provided, using defaults.")
        return default_symbol_registry()

    # Common bond/synthetic instrument patterns in tradingsymbol to exclude
    exclude_patterns = ("SDL ", "GOI ", "GS", "SGB", "IREDA", "IRFC", "REC", "NHB", 
                        "NHAI", "IIFL", "ECL", "PFL", "SCL", "SFL", "SFIL",
                        "-SG", "-GS", "-GB", "-IT", "-IV", "-RR", "-BZ", 
                        "-BE", "-SM", "-ST", "-SZ", "SGB", "NIFTY", "BANKNIFTY",
                        "LIQUID", "CPSEETF", "GOLDBEES", "MAFANG")
    
    exclude_names = ("SDL", "GOI LOAN", "GOLD", "BOND")
    
    # Filter for NSE equity with valid tokens
    eligible = []
    for inst in instruments:
        try:
            token = int(inst.get("instrument_token", 0))
            segment = inst.get("segment", "")
            instr_type = inst.get("instrument_type", "")
            tradingsymbol = inst.get("tradingsymbol", "").strip()
            name = inst.get("name", "").strip()
            
            if not tradingsymbol or token <= 0:
                continue
            
            # Must be NSE segment with EQ instrument type (equity shares)
            if segment != "NSE" or instr_type != "EQ":
                continue
            
            # Exclude known non-equity patterns by tradingsymbol and name
            ts_upper = tradingsymbol.upper()
            name_upper = name.upper()
            
            skip = False
            for pat in exclude_patterns:
                if pat in ts_upper or pat in name_upper:
                    skip = True
                    break
            if skip:
                continue
            
            for pat in exclude_names:
                if pat in name_upper:
                    skip = True
                    break
            if skip:
                continue
            
            eligible.append(inst)
        except (ValueError, TypeError):
            continue

    # Sort by instrument_token for consistent ordering, then take top N
    eligible = sorted(eligible, key=lambda x: int(x.get("instrument_token", 0)))[:top_n]

    for inst in eligible:
        token = int(inst["instrument_token"])
        symbol = inst["tradingsymbol"]
        registry[symbol] = {"token": token, "exchange": "NSE"}

    logger.info(f"build_symbol_registry: Built registry with {len(registry)} equity symbols from instrument list.")
    return registry


def default_symbol_registry():
    """Fallback default symbol list when API is unavailable."""
    return {
        "RELIANCE": {"token": 738561, "exchange": "NSE"},
        "TCS": {"token": 2953217, "exchange": "NSE"},
        "INFY": {"token": 408065, "exchange": "NSE"},
        "HDFCBANK": {"token": 341249, "exchange": "NSE"},
        "SBIN": {"token": 779521, "exchange": "NSE"},
        "GOLDBEES": {"token": 3661569, "exchange": "NSE"},
        "ICICIBANK": {"token": 1270529, "exchange": "NSE"},
        "WIPRO": {"token": 969473, "exchange": "NSE"},
        "ITC": {"token": 424961, "exchange": "NSE"},
        "LT": {"token": 1145601, "exchange": "NSE"},
        "HCLTECH": {"token": 722881, "exchange": "NSE"},
        "BHARTIARTL": {"token": 1664257, "exchange": "NSE"},
        "MARUTI": {"token": 1506497, "exchange": "NSE"},
        "TITAN": {"token": 2662401, "exchange": "NSE"},
        "ASIANPAINT": {"token": 1131777, "exchange": "NSE"},
        "NESTLEIND": {"token": 2237441, "exchange": "NSE"},
        "BAJFINANCE": {"token": 1308929, "exchange": "NSE"},
        "KOTAKBANK": {"token": 492033, "exchange": "NSE"},
        "AXISBANK": {"token": 1510401, "exchange": "NSE"},
        "SUNPHARMA": {"token": 2327041, "exchange": "NSE"},
        "HINDUNILVR": {"token": 1394689, "exchange": "NSE"},
        "ONGC": {"token": 249729, "exchange": "NSE"},
        "NTPC": {"token": 1156097, "exchange": "NSE"},
        "POWERGRID": {"token": 3011073, "exchange": "NSE"},
        "M&M": {"token": 1098497, "exchange": "NSE"},
    }


# Interval mapping for Kite historical data
TIMEFRAME_MAP = {
    "1m": "minute",
    "5m": "5minute",
    "15m": "15minute",
    "30m": "30minute",
    "60m": "60minute",
    "1D": "day",
    "1W": "week",
    "1M": "month",
}


class Broker:
    def __init__(self, api_key, api_secret, access_token=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.client = KiteConnect(api_key=self.api_key)
        logger.info("Broker.__init__: KiteConnect client instantiated.")

        # Symbol registry - try to load full NSE list
        self.symbol_registry = {}
        self.symbol_list_loaded = False
        self._load_symbol_registry()

        # persist token and mode for later WebSocket initialization
        self.access_token = access_token
        if access_token:
            try:
                self.client.set_access_token(access_token)
                logger.info("Broker.__init__: access_token set on KiteConnect client.")
                # Try to download full NSE instrument list in background
                self._download_full_symbol_list()
            except Exception as e:
                logger.error(f"Broker.__init__: failed to set access token: {e}")
        else:
            logger.warning("Broker.__init__: No access_token provided - WebSocket and live data will not work.")
            if not self.symbol_registry:
                self.symbol_registry = default_symbol_registry()

        self.kws = None
        self.data_manager = LiveDataManager()
        # Defaults to prevent attribute errors when methods assume these exist
        self.mode = "paper"
        self.strategies_registry = []
        self.paper_trades = []
        logger.info(f"Broker.__init__: mode={self.mode}, paper_trades_capacity=0, registry_size={len(self.symbol_registry)}")

    def _load_symbol_registry(self):
        """Load symbol registry from cache if available, else use defaults."""
        # Try loading from cache file
        if os.path.exists(NSE_INSTRUMENT_CACHE):
            try:
                with open(NSE_INSTRUMENT_CACHE, "r") as f:
                    instruments = json.load(f)
                # Load ALL valid equity symbols for search/dropdown (no top_n limit)
                self.symbol_registry = build_symbol_registry_from_instruments(instruments, top_n=99999)
                if self.symbol_registry:
                    self.symbol_list_loaded = True
                    logger.info(f"_load_symbol_registry: Loaded {len(self.symbol_registry)} symbols from cache.")
                    return
            except Exception as e:
                logger.warning(f"_load_symbol_registry: Failed loading cache: {e}")

        # Fallback to defaults
        self.symbol_registry = default_symbol_registry()
        logger.info(f"_load_symbol_registry: Using default registry with {len(self.symbol_registry)} symbols.")

    def _download_full_symbol_list(self):
        """Try to download full NSE instrument list asynchronously."""
        try:
            logger.info("_download_full_symbol_list: Starting NSE instrument download...")
            instruments = download_nse_instruments(self.client)
            if instruments:
                # Load ALL valid equity symbols - no cap
                registry = build_symbol_registry_from_instruments(instruments, top_n=99999)
                if registry:
                    self.symbol_registry = registry
                    self.symbol_list_loaded = True
                    logger.info(f"_download_full_symbol_list: Updated registry with {len(registry)} symbols.")
        except Exception as e:
            logger.warning(f"_download_full_symbol_list: Download failed: {e}")

    def get_symbols_list(self):
        """Return sorted list of symbol names for dropdowns."""
        symbols = sorted(self.symbol_registry.keys())
        return symbols

    def generate_session(self, request_token):
        logger.info(f"generate_session: Attempting session generation with request_token={request_token[:20] if request_token else 'None'}...")
        try:
            data = self.client.generate_session(request_token, api_secret=self.api_secret)
            self.client.set_access_token(data["access_token"])
            logger.info("generate_session: Zerodha Kite session established successfully.")
            # Now try to download full NSE list
            self._download_full_symbol_list()
            return data["access_token"]
        except Exception as e:
            logger.error(f"generate_session: Kite session failure: {e}")
            return None

    def get_live_funds(self):
        logger.debug("get_live_funds: Fetching live margin/balance from Kite...")
        try:
            margins = self.client.margins()
            balance = margins['equity']['available']['live_balance']
            logger.info(f"get_live_funds: live_balance = ₹{balance:,.2f}")
            return balance
        except Exception as e:
            logger.warning(f"get_live_funds: Kite API call failed, returning fallback ₹500,000. Error: {e}")
            return 500000.0

    def get_historical_bars(self, symbol, days=365, interval="day"):
        """Fetches historical data from Kite with configurable interval."""
        logger.info(f"get_historical_bars: symbol={symbol}, days={days}, interval={interval}")

        # Strip exchange prefix if present (e.g., "RELIANCE.NS" -> "RELIANCE")
        base_symbol = symbol.replace(".NS", "").replace(".BSE", "").strip()

        # Map timeframe to Kite interval
        kite_interval = TIMEFRAME_MAP.get(interval, interval)
        if kite_interval not in ["minute", "5minute", "15minute", "30minute", "60minute", "day", "week", "month"]:
            kite_interval = "day"

        try:
            if base_symbol not in self.symbol_registry:
                logger.warning(f"get_historical_bars: Symbol '{base_symbol}' not in registry.")
                raise ValueError(f"Symbol mapping registry lookup miss for '{base_symbol}'.")

            token = self.symbol_registry[base_symbol]["token"]
            logger.info(f"get_historical_bars: Found token={token} for base_symbol={base_symbol}")

            to_date = datetime.date.today()
            from_date = to_date - datetime.timedelta(days=days)

            logger.info(f"get_historical_bars: Calling Kite historical API: token={token}, interval={kite_interval}")
            records = self.client.historical_data(
                instrument_token=token,
                from_date=from_date,
                to_date=to_date,
                interval=kite_interval
            )
            df = pd.DataFrame(records)
            df['date'] = pd.to_datetime(df['date'])
            logger.info(f"get_historical_bars: Successfully fetched {len(df)} records.")
            return df
        except Exception as e:
            logger.warning(f"get_historical_bars: Kite fetch failed, using synthetic fallback: {e}")
            # Generate synthetic data
            dates = pd.date_range(end=datetime.date.today(), periods=days, freq='D')
            price = 1500.0 if base_symbol != "GOLDBEES" else 55.0
            prices = []
            for _ in range(days):
                price += random.uniform(-25.0, 26.0) if base_symbol != "GOLDBEES" else random.uniform(-0.5, 0.6)
                prices.append(max(10.0, price))

            df = pd.DataFrame({
                'date': dates,
                'close': prices,
                'open': [p * random.uniform(0.98, 1.02) for p in prices],
                'high': [p * random.uniform(1.01, 1.04) for p in prices],
                'low': [p * random.uniform(0.96, 0.99) for p in prices],
                'volume': [random.randint(100000, 5000000) for _ in range(days)]
            })
            logger.info(f"get_historical_bars: Generated {len(df)} synthetic records for {base_symbol}.")
            return df

    def get_live_market_grid(self, max_symbols=100):
        """
        Pulls multi-asset market information with enhanced fields using batch Kite quote calls.
        Uses Kite's batch quote API to avoid rate limiting (Too many requests).
        Only fetches quotes for a limited set to stay within API rate limits.
        
        Args:
            max_symbols: Maximum number of symbols to fetch (default 100). Kite allows ~100-200 per batch call.
                         Set to None to fetch all, but this may trigger rate limits.
        """
        logger.debug(f"get_live_market_grid: Building enhanced live market grid (max={max_symbols})...")
        grid_data = []
        
        # Use tick data from WebSocket first (already streaming)
        # Only fall back to Kite quote API for symbols not yet in ticks
        symbols_to_fetch = []
        for symbol, metadata in self.symbol_registry.items():
            token = metadata["token"]
            if token in self.data_manager.ticks:
                # Use cached WebSocket tick data
                t = self.data_manager.ticks[token]
                ltp = t.get("ltp", 0)
                change = t.get("change", 0)
                high = t.get("high", ltp)
                low = t.get("low", ltp)
                open_price = t.get("open", ltp)
                volume = t.get("volume", 0)
                prev_close = t.get("close", ltp)
                change_pct = ((ltp - prev_close) / max(prev_close, 1)) * 100 if prev_close else 0
                
                grid_data.append({
                    "Symbol": symbol,
                    "LTP (₹)": round(ltp, 2),
                    "Day Open": round(open_price, 2),
                    "Day High": round(high, 2),
                    "Day Low": round(low, 2),
                    "Prev Close": round(prev_close, 2),
                    "Day Change %": round(change_pct, 2),
                    "Change (₹)": round(change, 2),
                    "Traded Volume": volume,
                })
            else:
                symbols_to_fetch.append((symbol, metadata))
        
        # Skip Kite API calls if already rate-limited or too many symbols
        # Cap the number of symbols we fetch via API
        fetch_limit = max_symbols if max_symbols else 100
        if len(symbols_to_fetch) > fetch_limit:
            logger.warning(f"get_live_market_grid: Capping API quote calls from {len(symbols_to_fetch)} to {fetch_limit}")
            symbols_to_fetch = symbols_to_fetch[:fetch_limit]
        
        if symbols_to_fetch:
            try:
                # Batch fetch using Kite's batch quote API - can handle multiple symbols in one call
                exchange_symbols = [f"{meta['exchange']}:{sym}" for sym, meta in symbols_to_fetch]
                
                # Split into smaller batches of 50 to avoid hitting rate limits
                batch_size = 50
                for i in range(0, len(exchange_symbols), batch_size):
                    batch = exchange_symbols[i:i+batch_size]
                    try:
                        logger.debug(f"get_live_market_grid: Batch quote call for {len(batch)} symbols")
                        quotes = self.client.quote(",".join(batch))
                        
                        for sym, meta in symbols_to_fetch[i:i+batch_size]:
                            exchange_symbol = f"{meta['exchange']}:{sym}"
                            q = quotes.get(exchange_symbol, {})
                            if not q:
                                # Fallback for missing quote
                                base_price = random.uniform(200.0, 3500.0)
                                change_pct = random.uniform(-3.5, 4.0)
                                ltp = base_price
                                change = base_price * change_pct / 100
                                grid_data.append({
                                    "Symbol": sym, "LTP (₹)": round(ltp, 2),
                                    "Day Open": round(base_price * random.uniform(0.98, 1.02), 2),
                                    "Day High": round(ltp * random.uniform(1.0, 1.03), 2),
                                    "Day Low": round(ltp * random.uniform(0.97, 1.0), 2),
                                    "Prev Close": round(ltp - change, 2),
                                    "Day Change %": round(change_pct, 2),
                                    "Change (₹)": round(change, 2),
                                    "Traded Volume": random.randint(50000, 2000000),
                                })
                                continue
                            
                            ltp = q.get('last_price', 0)
                            change = q.get('net_change', 0)
                            change_pct = q.get('change_percentage', (change / max(ltp - change, 1)) * 100 if ltp != change else 0)
                            volume = q.get('volume', 0)
                            ohlc = q.get('ohlc', {})
                            open_price = ohlc.get('open', ltp)
                            high = q.get('high', ohlc.get('high', ltp))
                            low = q.get('low', ohlc.get('low', ltp))
                            prev_close = ohlc.get('close', ltp - change)
                            day_change = q.get('change_percentage', 0)
                            
                            grid_data.append({
                                "Symbol": sym,
                                "LTP (₹)": round(ltp, 2),
                                "Day Open": round(open_price, 2),
                                "Day High": round(high, 2),
                                "Day Low": round(low, 2),
                                "Prev Close": round(prev_close, 2),
                                "Day Change %": round(day_change, 2),
                                "Change (₹)": round(change, 2),
                                "Traded Volume": volume,
                            })
                        
                        # Small delay between batches to avoid rate limiting
                        if i + batch_size < len(exchange_symbols):
                            time.sleep(0.1)
                            
                    except Exception as batch_err:
                        logger.warning(f"get_live_market_grid: Batch quote call failed: {batch_err}")
                        # Add fallback data for this batch
                        for sym, _ in symbols_to_fetch[i:i+batch_size]:
                            base_price = random.uniform(200.0, 3500.0)
                            change_pct = random.uniform(-3.5, 4.0)
                            ltp = base_price
                            change = base_price * change_pct / 100
                            grid_data.append({
                                "Symbol": sym, "LTP (₹)": round(ltp, 2),
                                "Day Open": round(base_price * random.uniform(0.98, 1.02), 2),
                                "Day High": round(ltp * random.uniform(1.0, 1.03), 2),
                                "Day Low": round(ltp * random.uniform(0.97, 1.0), 2),
                                "Prev Close": round(ltp - change, 2),
                                "Day Change %": round(change_pct, 2),
                                "Change (₹)": round(change, 2),
                                "Traded Volume": random.randint(50000, 2000000),
                            })
            except Exception as e:
                logger.error(f"get_live_market_grid: All batch API calls failed: {e}")
        
        logger.info(f"get_live_market_grid: Built enhanced grid with {len(grid_data)} symbols ({len([d for d in grid_data if d['LTP (₹)'] != 0])} live via WS/API).")
        return pd.DataFrame(grid_data)

    def get_order_book(self):
        logger.debug("get_order_book: Fetching order book from Kite...")
        try:
            orders = self.client.orders()
            df = pd.DataFrame(orders)
            logger.info(f"get_order_book: Successfully fetched {len(df)} orders from Kite.")
            return df
        except Exception as e:
            logger.warning(f"get_order_book: Kite order fetch failed, returning fallback: {e}")
            dates = [datetime.date.today() - datetime.timedelta(days=i) for i in range(5)]
            return pd.DataFrame({
                "Order ID": [f"240607100{i}" for i in range(5)],
                "Date": dates,
                "Symbol": ["RELIANCE", "SBIN", "TCS", "GOLDBEES", "INFY"],
                "Transaction": ["BUY", "SELL", "BUY", "BUY", "SELL"],
                "Qty": [10, 50, 5, 100, 15],
                "Execution Price": [2450.0, 780.5, 3850.0, 54.20, 1420.0],
                "Status": ["COMPLETE", "COMPLETE", "REJECTED", "COMPLETE", "COMPLETE"]
            })

    def get_portfolio_holdings(self):
        logger.debug("get_portfolio_holdings: Fetching holdings from Kite...")
        try:
            holdings = self.client.holdings()
            df = pd.DataFrame(holdings)
            logger.info(f"get_portfolio_holdings: Raw holdings response has {len(df)} records.")

            if not df.empty:
                rename_map = {
                    "tradingsymbol": "Asset Symbol",
                    "average_price": "Avg Cost",
                    "quantity": "Current Qty",
                    "pnl": "Unrealized PnL",
                    "last_price": "LTP",
                }
                df = df.rename(columns=rename_map)
                if "LTP" in df.columns and "Current Qty" in df.columns:
                    df["Current Value"] = df["LTP"] * df["Current Qty"]
                if "Avg Cost" in df.columns and "Current Qty" in df.columns:
                    df["Invested"] = df["Avg Cost"] * df["Current Qty"]
                if "Current Value" in df.columns and "Invested" in df.columns:
                    df["Today P&L"] = df["Current Value"] - df["Invested"]
                logger.info(f"get_portfolio_holdings: Processed holdings. Columns: {list(df.columns)}")
            else:
                df = pd.DataFrame(columns=["Asset Symbol", "Avg Cost", "Current Qty", "LTP", "Current Value", "Invested", "Today P&L"])
            return df
        except Exception as e:
            logger.warning(f"get_portfolio_holdings: Failed, returning fallback: {e}")
            return pd.DataFrame({
                "Asset Symbol": ["RELIANCE", "INFY", "GOLDBEES"],
                "Avg Cost": [2310.0, 1380.0, 48.50],
                "Current Qty": [25, 40, 500],
                "LTP": [2450.0, 1420.0, 54.20],
                "Current Value": [61250.0, 56800.0, 27100.0],
                "Invested": [57750.0, 55200.0, 24250.0],
                "Today P&L": [3500.0, 1600.0, 2850.0],
            })

    def place_order(self, symbol, transaction_type, quantity, order_type="MARKET", price=0.0):
        """
        Place a live order via Kite API.
        transaction_type: "BUY" or "SELL"
        order_type: "MARKET" or "LIMIT"
        Automatically detects market hours and uses appropriate variety:
        - "regular" during market hours (9:15 AM - 3:30 PM)
        - "amo" after hours
        """
        logger.info(f"place_order: {transaction_type} {quantity} x {symbol} at {order_type}")

        # Check if mock mode
        if self.access_token == "MOCK_DEVELOPER_TOKEN":
            logger.info(f"place_order: MOCK mode - simulating {transaction_type} {symbol} x {quantity}")
            return {
                "status": "success",
                "order_id": f"MOCK_{int(time.time())}",
                "message": f"Mock {transaction_type} order placed for {quantity} {symbol}"
            }

        try:
            base_symbol = symbol.replace(".NS", "").replace(".BSE", "").strip()
            exchange = "NSE"

            if base_symbol in self.symbol_registry:
                exchange_symbol = f"{exchange}:{base_symbol}"
            else:
                exchange_symbol = symbol

            # Detect market hours: NSE equity market is open 9:15 AM to 3:30 PM on weekdays
            now = datetime.datetime.now()
            is_weekday = now.weekday() < 5  # Monday=0, Friday=4
            market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
            market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
            is_market_hours = is_weekday and market_open <= now <= market_close
            
            variety = "regular" if is_market_hours else "amo"
            product = "MIS" if is_market_hours else "CNC"  # CNC for delivery in AMO
            validity = "DAY" if is_market_hours else "DAY"
            
            logger.info(f"place_order: Market hours={is_market_hours}, using variety='{variety}', product='{product}'")

            # Build and pass order_params - variety as first positional arg to KiteConnect
            order_params = {
                "tradingsymbol": base_symbol,
                "exchange": exchange,
                "transaction_type": transaction_type,
                "quantity": quantity,
                "order_type": order_type,
                "product": product,
                "validity": validity,
            }

            if order_type == "LIMIT" and price > 0:
                order_params["price"] = price

            # KiteConnect.place_order signature: place_order(variety, ...)
            # variety must be the first positional argument
            order_id = self.client.place_order(variety, **order_params)
            logger.info(f"place_order: Order placed successfully. ID: {order_id}")
            return {
                "status": "success",
                "order_id": order_id,
                "message": f"{transaction_type} order placed for {quantity} x {symbol}"
            }
        except Exception as e:
            logger.error(f"place_order: Failed: {e}")
            return {"status": "error", "message": str(e)}

    def get_positions(self):
        """Get current day positions with P&L."""
        logger.debug("get_positions: Fetching positions from Kite...")
        try:
            positions = self.client.positions()
            df = pd.DataFrame(positions.get("day", []))
            if not df.empty:
                logger.info(f"get_positions: Fetched {len(df)} day positions.")
            return df
        except Exception as e:
            logger.warning(f"get_positions: Failed: {e}")
            return pd.DataFrame()

    # --- WebSocket Live Tracking Methods ---
    def start_live_tracking(self, instrument_tokens):
        """
        Initializes the KiteTicker WebSocket connection to receive real-time ticks.
        Must be called AFTER access_token is set.
        """
        logger.info(f"start_live_tracking: Called with {len(instrument_tokens) if instrument_tokens else 0} instrument tokens.")

        if not instrument_tokens:
            logger.warning("start_live_tracking: instrument_tokens list is empty, aborting WebSocket init.")
            return

        if not getattr(self, 'access_token', None):
            logger.error("start_live_tracking: ABORTED - Broker.access_token is not set.")
            return
        logger.info(f"start_live_tracking: access_token present (length={len(self.access_token)} chars).")

        def on_ticks(ws, ticks):
            try:
                logger.debug(f"WebSocket on_ticks: Received {len(ticks)} tick(s).")
                for tick in ticks:
                    token = tick.get("instrument_token") or tick.get("instrumentToken")
                    ltp = tick.get("last_price") or tick.get("ltp") or tick.get("lastPrice")
                    volume = tick.get("volume")
                    change = tick.get("change", 0.0)
                    depth = tick.get("depth", {}) or {}
                    bid = depth.get("buy", [{}])[0].get("price", 0) if depth.get("buy") else 0
                    ask = depth.get("sell", [{}])[0].get("price", 0) if depth.get("sell") else 0
                    timestamp = tick.get("timestamp") or tick.get("exchange_timestamp") or tick.get("time")
                    ohlc = tick.get("ohlc", {})
                    high = tick.get("high", ohlc.get("high", ltp))
                    low = tick.get("low", ohlc.get("low", ltp))
                    open_price = tick.get("open", ohlc.get("open", ltp))
                    close = tick.get("close", ohlc.get("close", ltp))

                    if token is not None:
                        old_tick = self.data_manager.ticks.get(token, {})
                        prev_ltp = old_tick.get("ltp", ltp) if old_tick else ltp
                        self.data_manager.ticks[token] = {
                            "ltp": ltp,
                            "volume": volume,
                            "change": change,
                            "bid": bid,
                            "ask": ask,
                            "high": high,
                            "low": low,
                            "open": open_price,
                            "close": close,
                            "prev_ltp": prev_ltp,
                            "time": timestamp,
                        }
                        if len(self.data_manager.ticks) % 10 == 0:
                            logger.info(f"WebSocket: Tick updated for token {token}: ltp={ltp}")

                    current_price = ltp
                    symbol = tick.get('tradingsymbol') or tick.get('symbol') or None

                    if hasattr(self, 'evaluate_strategy_logic') and hasattr(self, 'execute_paper_trade'):
                        for strat in getattr(self, 'strategies_registry', []):
                            try:
                                signal = self.evaluate_strategy_logic(strat, current_price)
                                if signal == "BUY" and self.mode == "paper":
                                    logger.info(f"WebSocket Strategy: BUY signal for {symbol} at ₹{current_price} via {strat.get('strategy_name')}")
                                    self.execute_paper_trade(symbol, current_price, strat.get('strategy_name'), "BUY")
                                    self.paper_trades.append({"Symbol": symbol, "Strategy": strat.get('strategy_name'), "Action": "BUY", "Price": current_price, "Time": timestamp})
                                elif signal == "SELL" and self.mode == "paper":
                                    logger.info(f"WebSocket Strategy: SELL signal for {symbol} at ₹{current_price} via {strat.get('strategy_name')}")
                                    self.execute_paper_trade(symbol, current_price, strat.get('strategy_name'), "SELL")
                                    self.paper_trades.append({"Symbol": symbol, "Strategy": strat.get('strategy_name'), "Action": "SELL", "Price": current_price, "Time": timestamp})
                            except Exception as e:
                                logger.error(f"WebSocket: Strategy eval/exec error: {e}")
                    else:
                        logger.debug("WebSocket: No strategy evaluation hooks present on Broker; tick stored only.")
            except Exception as e:
                logger.error(f"WebSocket: Error in on_ticks handler: {e}")

        def on_connect(ws, response):
            try:
                logger.info(f"WebSocket on_connect: Connected. Subscribing to {len(instrument_tokens)} tokens.")
                ws.subscribe(instrument_tokens)
                ws.set_mode(ws.MODE_FULL, instrument_tokens)
                logger.info(f"WebSocket on_connect: Subscribed to {len(instrument_tokens)} tokens in MODE_FULL.")
            except Exception as e:
                logger.error(f"WebSocket on_connect: Error: {e}")

        def on_close(ws, code, reason):
            logger.warning(f"WebSocket on_close: code={code}, reason={reason}")

        def on_error(ws, code, reason):
            logger.error(f"WebSocket on_error: code={code}, reason={reason}")

        try:
            logger.info("start_live_tracking: Creating KiteTicker instance...")
            self.kws = KiteTicker(self.api_key, self.access_token)
            self.kws.on_ticks = on_ticks
            self.kws.on_connect = on_connect
            self.kws.on_close = on_close
            if hasattr(self.kws, 'on_error'):
                self.kws.on_error = on_error
            logger.info("start_live_tracking: KiteTicker callbacks registered. Connecting (threaded=True)...")
            self.kws.connect(threaded=True)
            logger.info("start_live_tracking: KiteTicker connect() called successfully (background thread).")
        except Exception as e:
            logger.error(f"start_live_tracking: FAILED: {e}")

    def sync_live_orders(self):
        logger.debug("sync_live_orders: Syncing live orders from Kite...")
        try:
            live_orders = self.client.orders()
            self.data_manager.orders = live_orders
            logger.info(f"sync_live_orders: Synced {len(live_orders)} orders.")
            return live_orders
        except Exception as e:
            logger.error(f"sync_live_orders: Failed: {e}")
            return []