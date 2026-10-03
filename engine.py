import time
import threading
import numpy as np
import pandas as pd
import random
import datetime
from utils import logger

class TradingEngine:
    def __init__(self, broker, agent, email_config):
        self.broker = broker
        self.agent = agent
        self.email_config = email_config
        self.is_running = True
        self.paper_trades = []
        self.intraday_paper_trades = []  # Intraday trades with SL/TP tracking
        logger.info("TradingEngine.__init__: Engine initialized with broker, agent, and email_config.")
        logger.info(f"TradingEngine.__init__: Engine is_running={self.is_running}")

    def evaluate_backtest(self, strategy_config, df):
        """
        Executes structural mathematical vectorized backtesting loops 
        on raw dataframe arrays passed from the broker abstraction layer.
        Returns detailed trade logs, buy/sell signals, and buy & hold comparison.
        """
        strategy_name = strategy_config.get('strategy_name', 'Unknown')
        logger.info(f"evaluate_backtest: Starting backtest for strategy='{strategy_name}' with {len(df)} data points.")

        try:
            if df.empty or 'close' not in df.columns:
                logger.error(f"evaluate_backtest: Invalid data stream. empty={df.empty}, columns={list(df.columns)}")
                return {"error": "Invalid data stream formatting passed."}
            
            logger.debug(f"evaluate_backtest: Data validated. Columns: {list(df.columns)}, rows: {len(df)}")
            
            # Ensure date column exists
            if 'date' not in df.columns:
                df['date'] = df.index
            
            close_arr = df['close'].to_numpy()
            df['Signal'] = 0
            
            sl = strategy_config.get('sl_percentage', 1.0) / 100.0
            tp = strategy_config.get('tp_percentage', 2.0) / 100.0
            logger.info(f"evaluate_backtest: Risk params: sl={sl*100:.2f}%, tp={tp*100:.2f}%")
            
            # Generate signals based on strategy entry logic
            signals = np.zeros(len(close_arr))
            entry_logic = strategy_config.get('entry_logic', '').lower()
            
            if 'rsi' in entry_logic and 'ema' in entry_logic:
                # Simple EMA/RSI based logic
                ema_period = 14
                for i in range(ema_period, len(close_arr)):
                    ema = np.mean(close_arr[i-ema_period:i])
                    if close_arr[i] > ema and close_arr[i] > close_arr[i-1]:
                        signals[i] = 1
                    elif close_arr[i] < ema and close_arr[i] < close_arr[i-1]:
                        signals[i] = -1
            elif 'bollinger' in entry_logic or 'channel' in entry_logic:
                # Volatility breakout logic
                period = 20
                for i in range(period, len(close_arr)):
                    sma = np.mean(close_arr[i-period:i])
                    std = np.std(close_arr[i-period:i])
                    upper = sma + 2 * std
                    lower = sma - 2 * std
                    if close_arr[i] > upper:
                        signals[i] = 1
                    elif close_arr[i] < lower:
                        signals[i] = -1
            else:
                # Default momentum logic
                for i in range(20, len(close_arr)):
                    if close_arr[i] > close_arr[i-1] and close_arr[i-1] > close_arr[i-2]:
                        signals[i] = 1
                    elif close_arr[i] < close_arr[i-1] and close_arr[i-1] < close_arr[i-2]:
                        signals[i] = -1
            
            df['Signal'] = signals
            buy_signals = int(np.sum(signals == 1))
            sell_signals = int(np.sum(signals == -1))
            logger.info(f"evaluate_backtest: Generated {buy_signals} BUY signals and {sell_signals} SELL signals.")
            
            # Track detailed trade info
            trade_log = []  # List of dicts with trade details
            df['cumulative_equity'] = np.nan
            df['buy_hold_equity'] = np.nan
            
            initial_capital = 100000.0
            equity = initial_capital
            equity_curve = [initial_capital]
            
            # Buy & hold baseline
            first_close = close_arr[0] if len(close_arr) > 0 else 1
            
            in_position = False
            entry_price = 0.0
            entry_idx = 0
            entry_date = None
            trade_count = 0
            trade_pnls = []
            trade_returns = []
            
            for idx, row in df.iterrows():
                current_price = row['close']
                
                # Buy & hold equity calculation
                bh_equity = initial_capital * (current_price / first_close) if first_close > 0 else initial_capital
                df.at[idx, 'buy_hold_equity'] = bh_equity
                
                if not in_position and row['Signal'] == 1:
                    in_position = True
                    entry_price = current_price
                    entry_idx = idx
                    entry_date = row['date'] if 'date' in row else idx
                    trade_count += 1
                    logger.debug(f"evaluate_backtest: Trade #{trade_count} ENTRY at ₹{entry_price:.2f} (idx={idx})")
                elif in_position:
                    return_pct = (current_price - entry_price) / entry_price
                    
                    # Check exit conditions
                    exit_reason = None
                    exit_price = current_price
                    exit_idx = idx
                    
                    if return_pct <= -sl:
                        exit_reason = "SL_HIT"
                        exit_price = entry_price * (1 - sl)
                    elif return_pct >= tp:
                        exit_reason = "TP_HIT"
                        exit_price = entry_price * (1 + tp)
                    elif row['Signal'] == -1:
                        exit_reason = "SIGNAL_EXIT"
                    elif idx == df.index[-1]:
                        exit_reason = "END_OF_DATA"
                    
                    if exit_reason:
                        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                        pnl_rupees = initial_capital * 0.10 * (pnl_pct / 100)
                        equity += pnl_rupees
                        trade_pnls.append(pnl_rupees)
                        trade_returns.append(pnl_pct)
                        
                        trade_log.append({
                            "Trade #": trade_count,
                            "Entry Date": entry_date,
                            "Exit Date": row['date'] if 'date' in row else exit_idx,
                            "Entry Price": round(entry_price, 2),
                            "Exit Price": round(exit_price, 2),
                            "PnL%": round(pnl_pct, 2),
                            "PnL (₹)": round(pnl_rupees, 2),
                            "Exit Reason": exit_reason
                        })
                        
                        logger.info(f"evaluate_backtest: Trade #{trade_count} EXIT at ₹{exit_price:.2f} ({exit_reason}), PnL={pnl_pct:+.2f}%")
                        in_position = False
                
                equity_curve.append(equity)
            
            # Pad equity_curve to match df length
            df['cumulative_equity'] = equity_curve[:len(df)]
            
            # Calculate metrics
            trade_series = pd.Series(trade_pnls) if trade_pnls else pd.Series([0])
            total_returns = ((equity - initial_capital) / initial_capital) * 100
            win_rate = (len(trade_series[trade_series > 0]) / len(trade_series)) * 100 if len(trade_series) > 0 else 0
            max_dd = ((pd.Series(equity_curve).cummax() - pd.Series(equity_curve)).max() / pd.Series(equity_curve).cummax().max()) * 100
            
            # Buy & Hold return
            bh_final = df['buy_hold_equity'].iloc[-1] if len(df) > 0 else initial_capital
            bh_return = ((bh_final - initial_capital) / initial_capital) * 100
            
            # Prepare buy/sell marker points for chart
            buy_dates = []
            buy_prices = []
            sell_dates = []
            sell_prices = []
            
            for t in trade_log:
                buy_dates.append(t["Entry Date"])
                buy_prices.append(t["Entry Price"])
                sell_dates.append(t["Exit Date"])
                sell_prices.append(t["Exit Price"])
            
            logger.info(f"evaluate_backtest: Backtest complete for '{strategy_name}'. "
                        f"Trades: {len(trade_log)}, Return: {total_returns:.2f}%, BH: {bh_return:.2f}%, WinRate: {win_rate:.1f}%, MaxDD: {max_dd:.2f}%")
            
            return {
                "metrics": {
                    "Total Return %": f"{total_returns:.2f}%",
                    "Buy & Hold Return %": f"{bh_return:.2f}%",
                    "Strategy Alpha %": f"{total_returns - bh_return:+.2f}%",
                    "Win Rate %": f"{win_rate:.1f}%",
                    "Total Executed Trades": len(trade_log),
                    "Max Drawdown %": f"{max_dd:.2f}%",
                    "Profit Factor": f"{abs(trade_series[trade_series > 0].sum() / trade_series[trade_series < 0].sum()):.2f}" if len(trade_series[trade_series < 0]) > 0 else "N/A"
                },
                "chart_data": df[['date', 'close', 'cumulative_equity', 'buy_hold_equity']],
                "trade_log": trade_log,
                "buy_signals": {"dates": buy_dates, "prices": buy_prices},
                "sell_signals": {"dates": sell_dates, "prices": sell_prices}
            }
        except Exception as e:
            logger.error(f"evaluate_backtest: Backtest engine calculation error: {e}", exc_info=True)
            return {"error": str(e)}

    def run_intraday_paper_trading(self):
        """
        Simulates intraday paper trading by generating synthetic tick data
        for all registered symbols and evaluating strategies.
        This runs every 5 minutes during market hours simulation.
        """
        logger.info("run_intraday_paper_trading: Running intraday paper trading cycle...")
        
        if not self.broker.symbol_registry:
            logger.warning("run_intraday_paper_trading: No symbols registered.")
            return
        
        # For each strategy, evaluate on random symbols
        strategies = getattr(self.broker, 'strategies_registry', [])
        if not strategies:
            logger.info("run_intraday_paper_trading: No strategies to evaluate.")
            return
        
        symbols = list(self.broker.symbol_registry.keys())
        if not symbols:
            return
        
        # Pick a few random symbols to simulate
        selected_symbols = random.sample(symbols, min(5, len(symbols)))
        current_time = datetime.datetime.now()
        
        for symbol in selected_symbols:
            try:
                # Get the base price from LTP
                base_price = 0
                try:
                    token = self.broker.symbol_registry[symbol]["token"]
                    if token in self.broker.data_manager.ticks:
                        base_price = self.broker.data_manager.ticks[token].get("ltp", 0)
                except:
                    pass
                
                if base_price == 0:
                    base_price = random.uniform(200.0, 3500.0)
                
                # Simulate price movement (intraday volatility)
                price_change_pct = random.uniform(-1.5, 1.5)
                simulated_price = base_price * (1 + price_change_pct / 100)
                simulated_price = round(max(simulated_price, 10.0), 2)
                
                # Check if we have an open position for this symbol
                open_trade = None
                for t in self.intraday_paper_trades:
                    if t.get("Symbol") == symbol and t.get("Status") == "OPEN":
                        open_trade = t
                        break
                
                # Pick a random strategy
                strategy = random.choice(strategies)
                strategy_name = strategy.get("strategy_name", "Unknown")
                sl_pct = strategy.get("sl_percentage", 1.0)
                tp_pct = strategy.get("tp_percentage", 2.0)
                
                if open_trade:
                    # Check SL/TP for existing trade
                    entry_price = open_trade["Entry Price"]
                    pnl_pct = ((simulated_price - entry_price) / entry_price) * 100
                    
                    if pnl_pct <= -sl_pct:
                        # SL Hit
                        open_trade["Exit Price"] = simulated_price
                        open_trade["Exit Time"] = current_time.isoformat()
                        open_trade["Status"] = "SL_HIT"
                        open_trade["PnL"] = round(pnl_pct, 2)
                        self.paper_trades.append({
                            "Symbol": symbol, "Strategy": strategy_name,
                            "Action": "BUY", "Price": entry_price,
                            "Exit Price": simulated_price, "PnL%": round(pnl_pct, 2),
                            "Time": current_time.isoformat(), "Status": "SL_HIT"
                        })
                        logger.info(f"Paper Trade: SL HIT {symbol} @ {simulated_price} (entry: {entry_price}, PnL: {pnl_pct:.2f}%)")
                    elif pnl_pct >= tp_pct:
                        # TP Hit
                        open_trade["Exit Price"] = simulated_price
                        open_trade["Exit Time"] = current_time.isoformat()
                        open_trade["Status"] = "TP_HIT"
                        open_trade["PnL"] = round(pnl_pct, 2)
                        self.paper_trades.append({
                            "Symbol": symbol, "Strategy": strategy_name,
                            "Action": "BUY", "Price": entry_price,
                            "Exit Price": simulated_price, "PnL%": round(pnl_pct, 2),
                            "Time": current_time.isoformat(), "Status": "TP_HIT"
                        })
                        logger.info(f"Paper Trade: TP HIT {symbol} @ {simulated_price} (entry: {entry_price}, PnL: {pnl_pct:.2f}%)")
                else:
                    # Generate random entry signal with ~20% probability per cycle
                    if random.random() < 0.20:
                        qty = random.choice([10, 25, 50, 100])
                        self.intraday_paper_trades.append({
                            "Symbol": symbol,
                            "Strategy": strategy_name,
                            "Action": "BUY",
                            "Entry Price": simulated_price,
                            "Entry Time": current_time.isoformat(),
                            "Qty": qty,
                            "SL%": sl_pct,
                            "TP%": tp_pct,
                            "Status": "OPEN",
                            "PnL": 0.0,
                        })
                        logger.info(f"Paper Trade: ENTRY {symbol} @ {simulated_price} x {qty} via {strategy_name}")
                    
            except Exception as e:
                logger.error(f"run_intraday_paper_trading: Error processing {symbol}: {e}")
        
        # Close any trades that have been open too long (end of day simulation)
        now = datetime.datetime.now()
        for trade in self.intraday_paper_trades[:]:
            if trade.get("Status") == "OPEN":
                entry_time = datetime.datetime.fromisoformat(trade["Entry Time"])
                if (now - entry_time).total_seconds() > 3600:  # Close after 1 hour
                    symbol = trade["Symbol"]
                    try:
                        token = self.broker.symbol_registry.get(symbol, {}).get("token", 0)
                        exit_price = self.broker.data_manager.ticks.get(token, {}).get("ltp", trade["Entry Price"])
                    except:
                        exit_price = trade["Entry Price"] * random.uniform(0.98, 1.02)
                    
                    pnl_pct = ((exit_price - trade["Entry Price"]) / trade["Entry Price"]) * 100
                    trade["Exit Price"] = round(exit_price, 2)
                    trade["Exit Time"] = now.isoformat()
                    trade["Status"] = "CLOSED"
                    trade["PnL"] = round(pnl_pct, 2)
                    self.paper_trades.append({
                        "Symbol": symbol, "Strategy": trade["Strategy"],
                        "Action": "SELL", "Price": trade["Entry Price"],
                        "Exit Price": round(exit_price, 2), "PnL%": round(pnl_pct, 2),
                        "Time": now.isoformat(), "Status": "CLOSED"
                    })
                    logger.info(f"Paper Trade: CLOSED {symbol} @ {exit_price:.2f} (PnL: {pnl_pct:.2f}%)")
        
        logger.info(f"run_intraday_paper_trading: Cycle complete. Open: {len([t for t in self.intraday_paper_trades if t.get('Status')=='OPEN'])}, Closed: {len(self.paper_trades)}")

    def get_paper_trading_summary(self):
        """Returns a summary of paper trading performance."""
        total_trades = len(self.paper_trades)
        winning_trades = len([t for t in self.paper_trades if t.get("PnL%", 0) > 0])
        losing_trades = len([t for t in self.paper_trades if t.get("PnL%", 0) <= 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        total_pnl = sum(t.get("PnL%", 0) for t in self.paper_trades)
        open_positions = len([t for t in self.intraday_paper_trades if t.get("Status") == "OPEN"])
        
        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 1),
            "total_pnl_pct": round(total_pnl, 2),
            "open_positions": open_positions,
        }

    def start(self):
        self.is_running = True
        logger.info("TradingEngine.start: Engine set to RUNNING state.")

    def stop(self):
        self.is_running = False
        logger.info("TradingEngine.stop: Engine set to IDLE state.")