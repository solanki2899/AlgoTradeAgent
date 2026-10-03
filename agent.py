import os
import json
from google import genai
from pydantic import BaseModel, Field
from typing import List, Optional
from utils import logger

class IndicatorConfig(BaseModel):
    name: str = Field(description="Technical indicator identifier name (e.g., EMA, RSI, SMA)")
    period: int = Field(description="Lookback math matrix context tracking period window")

class StrategySchema(BaseModel):
    strategy_name: str = Field(description="High performance designation title identifier")
    description: str = Field(description="Comprehensive algorithmic thesis statement breakdown")
    indicators: List[IndicatorConfig] = Field(description="Quant pipeline tracking configurations array")
    entry_logic: str = Field(description="Mathematical expression indicator trigger string pattern rules")
    sl_percentage: float = Field(description="Stop Loss ceiling calculation parameter")
    tp_percentage: float = Field(description="Target Profit floor realization value parameter")

class StockAnalysisResult(BaseModel):
    symbol: str = Field(description="Stock ticker symbol (e.g., RELIANCE, TCS)")
    recommendation: str = Field(description="BUY, SELL, or HOLD recommendation")
    profit_probability_percent: float = Field(description="Estimated probability of profit in percentage (0-100)")
    expected_return_percent: float = Field(description="Expected return percentage over the next trading session")
    risk_level: str = Field(description="LOW, MEDIUM, or HIGH risk assessment")
    reasoning: str = Field(description="Concise 2-3 sentence reasoning behind this recommendation")

class StockOpportunityReport(BaseModel):
    ranked_opportunities: List[StockAnalysisResult] = Field(description="Ranked list of stock opportunities from best to worst")
    best_opportunity: str = Field(description="The single best stock symbol to trade right now")
    market_sentiment: str = Field(description="Overall market sentiment: BULLISH, BEARISH, or NEUTRAL")

class AlgoAgent:
    def __init__(self, gemini_api_key: str):
        logger.info("AlgoAgent.__init__: Initializing GenAI client with model='gemini-2.5-flash'.")
        self.client = genai.Client(api_key=gemini_api_key)
        self.model_name = "gemini-2.5-flash"
        logger.info("AlgoAgent.__init__: GenAI client initialized successfully.")

    def generate_daily_strategy(self, user_prompt: str = "") -> dict:
        """
        Generate a trading strategy using AI.
        
        Args:
            user_prompt: Optional user-specified strategy requirements.
                         If empty, AI generates autonomously.
                         
        Returns:
            dict with strategy config. Includes "_fallback": True if AI was unavailable.
        """
        logger.info(f"generate_daily_strategy: Sending strategy generation prompt to GenAI (user_prompt provided: {bool(user_prompt)})...")
        
        base_prompt = """
        You are an Elite Quantitative Strategy Discovery Engine. 
        Instead of limiting yourself to standard Moving Average Crossovers, you are explicitly commanded to explore advanced mathematical systems across multiple indicator classes:

        1. Volatility Regimes: Bollinger Bands, Keltner Channels, Average True Range (ATR) breakouts.
        2. Momentum & Divergences: RSI divergences, MACD Histograms, Stochastic Momentum Index (SMI).
        3. Volume & Structural Profiles: VWAP bands, Chaikin Money Flow (CMF), On-Balance Volume (OBV).
        4. Trend Quality Indicators: Ichimoku Cloud components, ADX strength filtering, Supertrend channels.

        Your goal is to autonomously compose experimental Alpha strategies. When generating a strategy config, look for confluence (e.g., combining Mean Reversion with Volatility constraints, or Momentum confirmation with Volume support).
        """
        
        user_section = ""
        if user_prompt.strip():
            user_section = f"""
        The user has specifically requested the following strategy requirements. Please design the strategy to match these specifications:
        
        USER REQUEST: {user_prompt.strip()}
        
        Follow the user's instructions carefully. If they mention specific indicators, use them. If they specify trade direction (long-only, short-only, both), respect that.
        """
        
        output_format = """
        You must ALWAYS output a strictly valid JSON response configuration that maps to the execution engine:
        {
        "strategy_name": "Name of experimental strategy",
        "indicator_setup": {
            "primary": {"type": "RSI", "period": 14, "overbought": 75, "oversold": 25},
            "secondary": {"type": "Bollinger_Bands", "period": 20, "std_dev": 2.5}
        },
        "entry_conditions": "Description of mathematical signal triggers",
        "exit_conditions": "Description of exit criteria",
        "risk_profile": {"initial_stop_loss_pct": 1.5, "trailing_stop_loss": true}
        }
        """
        
        prompt = base_prompt + user_section + output_format
        
        try:
            logger.debug(f"generate_daily_strategy: Calling GenAI model='{self.model_name}' with temperature=0.7.")
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    'response_mime_type': 'application/json',
                    'response_schema': StrategySchema,
                    'temperature': 0.7
                }
            )
            logger.info(f"generate_daily_strategy: GenAI response received. Has parsed: {hasattr(response, 'parsed') and response.parsed is not None}")

            if hasattr(response, 'parsed') and response.parsed:
                parsed = response.parsed.model_dump()
                logger.info(f"generate_daily_strategy: Successfully parsed response via schema. Strategy name: '{parsed.get('strategy_name')}'")
                return parsed
            text = response.text
            logger.info(f"generate_daily_strategy: Falling back to raw text parsing. Response length: {len(text)} chars.")
            return json.loads(text)
        except Exception as e:
            logger.error(f"generate_daily_strategy: GenAI Client generation fault interception: {e}")
            fallback = {
                "strategy_name": "Dynamic Momentum Alpha Breakout",
                "description": "Standard trend evaluation alpha framework deployed via mitigation logic.",
                "indicators": [{"name": "EMA", "period": 14}, {"name": "RSI", "period": 14}],
                "entry_logic": "Close > EMA_14 and RSI < 65",
                "sl_percentage": 1.2,
                "tp_percentage": 2.4,
                "_fallback": True  # Flag to indicate fallback was used
            }
            logger.info(f"generate_daily_strategy: Returning fallback strategy: {fallback['strategy_name']}")
            return fallback

    def analyze_stock_opportunities(self, market_data: list) -> dict:
        """
        Analyzes current market data for all tracked stocks and returns
        ranked opportunities with profit probabilities.
        
        market_data: List of dicts with keys: Symbol, LTP (₹), Daily Change %, Traded Volume
        """
        logger.info(f"analyze_stock_opportunities: Analyzing {len(market_data)} stocks from market data.")
        
        # Format market data as a concise text table for the AI
        market_summary_lines = ["Symbol | LTP | Change% | Volume"]
        market_summary_lines.append("-" * 50)
        for stock in market_data:
            sym = stock.get("Symbol", "?")
            ltp = stock.get("LTP (₹)", 0)
            chg = stock.get("Daily Change %", 0)
            vol = stock.get("Traded Volume", 0)
            market_summary_lines.append(f"{sym} | {ltp} | {chg}% | {vol}")
        
        market_table = "\n".join(market_summary_lines)
        
        prompt = f"""You are an Elite Stock Market Opportunity Scanner with deep expertise in technical analysis, 
        volume profiling, and price action reading.

        Below is the current real-time market snapshot for all tracked stocks:

        {market_table}

        Your task:
        1. Analyze each stock's current price, daily change percentage, and traded volume.
        2. Look for patterns: strong momentum (high positive change + high volume), 
           reversal signals (stock down on high volume after a rally), 
           or weakness (negative change with declining volume).
        3. Rank the stocks from BEST to WORST trading opportunity for TODAY.
        4. Assign a profit probability percentage (0-100) based on signal strength.
        5. Estimate expected return percentage for the next trading session.
        6. Assign risk level: LOW (stable, liquid), MEDIUM (moderate volatility), HIGH (highly volatile/uncertain).
        7. Provide concise 2-3 sentence reasoning for each stock.
        8. Determine overall market sentiment (BULLISH, BEARISH, NEUTRAL).

        Output MUST be valid JSON matching the schema exactly.
        """
        
        try:
            logger.debug("analyze_stock_opportunities: Sending analysis prompt to GenAI.")
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    'response_mime_type': 'application/json',
                    'response_schema': StockOpportunityReport,
                    'temperature': 0.3  # Lower temperature for more consistent analysis
                }
            )
            logger.info(f"analyze_stock_opportunities: GenAI response received. Has parsed: {hasattr(response, 'parsed') and response.parsed is not None}")

            if hasattr(response, 'parsed') and response.parsed:
                parsed = response.parsed.model_dump()
                logger.info(f"analyze_stock_opportunities: Successfully parsed. Best opportunity: {parsed.get('best_opportunity')}")
                return parsed
            
            text = response.text
            logger.info(f"analyze_stock_opportunities: Falling back to raw text parsing.")
            return json.loads(text)
            
        except Exception as e:
            logger.error(f"analyze_stock_opportunities: GenAI analysis failed: {e}")
            # Return fallback analysis based on simple heuristics
            fallback = self._heuristic_fallback_analysis(market_data)
            logger.info(f"analyze_stock_opportunities: Returning heuristic fallback analysis.")
            return fallback
    
    def _heuristic_fallback_analysis(self, market_data: list) -> dict:
        """Simple rule-based analysis when GenAI is unavailable."""
        opportunities = []
        for stock in market_data:
            sym = stock.get("Symbol", "?")
            chg = stock.get("Daily Change %", 0)
            
            # Simple heuristic
            if chg > 2.0:
                rec = "BUY"
                prob = min(60 + chg * 2, 85)
                exp_return = min(chg * 0.8, 5.0)
                risk = "MEDIUM"
                reason = f"Strong positive momentum with {chg:.1f}% gain. Momentum may continue."
            elif chg < -2.0:
                rec = "HOLD"
                prob = max(50 + chg, 25)
                exp_return = max(chg * 0.3, -3.0)
                risk = "HIGH"
                reason = f"Significant decline of {chg:.1f}%. Waiting for reversal confirmation advised."
            elif chg > 0.5:
                rec = "BUY"
                prob = 55 + chg * 5
                exp_return = chg * 0.6
                risk = "LOW"
                reason = f"Steady positive movement of {chg:.1f}% with controlled risk profile."
            else:
                rec = "HOLD"
                prob = 45
                exp_return = 1.0
                risk = "LOW"
                reason = f"Minimal price movement at {chg:.1f}%. No clear signal detected."
            
            opportunities.append({
                "symbol": sym,
                "recommendation": rec,
                "profit_probability_percent": round(min(prob, 100), 1),
                "expected_return_percent": round(exp_return, 1),
                "risk_level": risk,
                "reasoning": reason
            })
        
        # Sort by probability descending
        opportunities.sort(key=lambda x: x["profit_probability_percent"], reverse=True)
        
        # Determine best and sentiment
        best = opportunities[0]["symbol"] if opportunities else "NONE"
        avg_chg = sum(s.get("Daily Change %", 0) for s in market_data) / max(len(market_data), 1)
        sentiment = "BULLISH" if avg_chg > 0.5 else ("BEARISH" if avg_chg < -0.5 else "NEUTRAL")
        
        return {
            "ranked_opportunities": opportunities,
            "best_opportunity": best,
            "market_sentiment": sentiment
        }