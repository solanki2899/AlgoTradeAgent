import os
import json

# Define directory target path
STRATEGY_DIR = "strategies"
os.makedirs(STRATEGY_DIR, exist_ok=True)

# 1. Moving Average Crossover (Trend Following)
mac_strat = {
    "strategy_name": "Moving_Average_Crossover_9_21",
    "indicators": ["EMA_9", "EMA_21"],
    "entry": "Buy when EMA_9 crosses above EMA_21 from below. Volume must be above 20-period average.",
    "exit": "Sell when EMA_9 crosses below EMA_21 from above.",
    "parameters": {"fast_period": 9, "slow_period": 21}
}

# 2. RSI Mean Reversion (Counter-Trend)
rsi_strat = {
    "strategy_name": "RSI_Mean_Reversion",
    "indicators": ["RSI_14", "EMA_200"],
    "entry": "Price is above EMA_200 (bullish regime) and RSI_14 drops below 30 (oversold pullback).",
    "exit": "RSI_14 crosses back above 70 or trailing stop hit.",
    "parameters": {"rsi_period": 14, "oversold": 30, "overbought": 70}
}

# 3. Bollinger Band Breakout (Volatility Expansion)
bb_strat = {
    "strategy_name": "Bollinger_Band_Breakout",
    "indicators": ["Bollinger_Bands_20_2", "ATR_14"],
    "entry": "Closing price breaks above the Upper Bollinger Band during a low-volatility squeeze interval.",
    "exit": "Closing price drops below the 20-period Middle Moving Average band.",
    "parameters": {"bb_period": 20, "bb_std": 2.0, "atr_period": 14}
}

# 4. MACD Momentum Divergence
macd_strat = {
    "strategy_name": "MACD_Momentum_Trend",
    "indicators": ["MACD_12_26_9", "Supertrend_10_3"],
    "entry": "Supertrend is green and MACD Histogram line crosses above zero line.",
    "exit": "MACD line drops below Signal Line, or Supertrend flips to red.",
    "parameters": {"macd_fast": 12, "macd_slow": 26, "macd_signal": 9}
}

# Write configs out as cleanly parsed JSON assets
strategies_to_save = [mac_strat, rsi_strat, bb_strat, macd_strat]
for strat in strategies_to_save:
    file_path = os.path.join(STRATEGY_DIR, f"{strat['strategy_name'].lower()}.json")
    with open(file_path, "w") as f:
        json.dump(strat, f, indent=4)

print(f"✅ Strategy Library generated successfully! 4 blueprints written to /{STRATEGY_DIR}")