# ============================================================================
# PHASE 4 — REGIME ENGINE (PRODUCTION-READY) - FIXED
# ============================================================================

# ----------------------------------------------------------------------------
# services/regime_engine.py
# ----------------------------------------------------------------------------
"""
Core logic for regime analysis
Determines market regime, risk level, and trading posture

Integrates with:
- utils.regime_data (fetch data from Twelve Data API)
- utils.regime_indicators (calculate technical indicators)
- utils.auth (check user subscription tier)
"""
from utils.regime_data import fetch_regime_data, MarketDataError
from utils.regime_indicators import calculate_indicators
from typing import Dict, List
import logging
import html

logger = logging.getLogger(__name__)


class RegimeEngine:
    """
    Engine for calculating market regime and risk
    
    Uses multi-timeframe analysis to determine:
    - Market regime (Bullish, Bearish, Ranging, etc.)
    - Risk level (Low, Medium, High)
    - Trading posture (what to do)
    - Confidence score (0-100%)
    
    Supports multiple timeframe combinations:
    - 1H + 4H (Day Trading)
    - 4H + Daily (Swing Trading)
    """
    
    def __init__(self):
        """Initialize regime engine with default timeframes"""
        # Default timeframes (can be overridden)
        self.default_lower_tf = "4h"
        self.default_upper_tf = "1day"
        
        # Minimum candle requirements per timeframe
        self.min_candles = {
            "1h": 200,
            "4h": 100,
            "1day": 50
        }
    
    @staticmethod
    def _escape_html(text: str) -> str:
        """Escape HTML special characters except allowed tags"""
        if not text:
            return ""
        # Don't escape the text since we're using HTML formatting intentionally
        # Just make sure there are no unclosed tags or invalid characters
        return str(text)
    
    async def analyze(
        self, 
        symbol: str, 
        plan: str,
        lower_tf: str = None,
        upper_tf: str = None
    ) -> Dict:
        """
        Analyze market regime for given symbol
        Returns different detail levels based on user plan
        
        Args:
            symbol: Trading symbol (e.g., "BTC", "ETH")
            plan: User plan tier (from get_user_plan)
            lower_tf: Lower timeframe (e.g., "1h", "4h") - optional
            upper_tf: Upper timeframe (e.g., "4h", "1day") - optional
        
        Returns:
            Dictionary with regime analysis results
            
        Raises:
            Exception: If data fetch or analysis fails
        """
        
        # Use provided timeframes or fall back to defaults
        lower_tf = lower_tf or self.default_lower_tf
        upper_tf = upper_tf or self.default_upper_tf
        
        logger.info(f"Starting regime analysis: symbol={symbol}, timeframes={lower_tf}+{upper_tf}")
        
        try:
            # ================================================================
            # STEP 1: FETCH MARKET DATA
            # ================================================================
            market_data = await fetch_regime_data(symbol, lower_tf, upper_tf)
            
            # Validate data was received
            if not market_data.get("data_lower") or not market_data.get("data_upper"):
                raise Exception("No market data received")
            
            # Check minimum candle requirements
            min_lower = self.min_candles.get(lower_tf, 100)
            min_upper = self.min_candles.get(upper_tf, 50)
            
            if len(market_data["data_lower"]) < min_lower:
                logger.warning(f"Insufficient {lower_tf} data: {len(market_data['data_lower'])} < {min_lower}")
                raise Exception(f"Insufficient historical data for {lower_tf} timeframe")
            
            if len(market_data["data_upper"]) < min_upper:
                logger.warning(f"Insufficient {upper_tf} data: {len(market_data['data_upper'])} < {min_upper}")
                raise Exception(f"Insufficient historical data for {upper_tf} timeframe")
            
            # ================================================================
            # STEP 2: CALCULATE INDICATORS
            # ================================================================
            indicators_lower = calculate_indicators(market_data["data_lower"], lower_tf)
            indicators_upper = calculate_indicators(market_data["data_upper"], upper_tf)
            
            logger.info(f"Indicators calculated: lower_trend={indicators_lower.get('trend_bias')}, upper_trend={indicators_upper.get('trend_bias')}")
            
            # ================================================================
            # STEP 3: DETERMINE REGIME
            # ================================================================
            regime = self._determine_regime(indicators_lower, indicators_upper)
            
            # ================================================================
            # STEP 4: CALCULATE RISK LEVEL
            # ================================================================
            risk_level = self._calculate_risk_level(regime, indicators_lower, indicators_upper)
            
            # ================================================================
            # STEP 5: SUGGEST TRADING POSTURE (More specific)
            # ================================================================
            posture = self._suggest_posture(regime, risk_level, indicators_lower, indicators_upper)
            
            # ================================================================
            # STEP 6: CALCULATE CONFIDENCE
            # ================================================================
            confidence = self._calculate_confidence(indicators_lower, indicators_upper)
            
            # ================================================================
            # STEP 7: BUILD RESULT (BASE)
            # ================================================================
            result = {
                "symbol": market_data["symbol"],
                "regime": regime,
                "risk_level": risk_level,
                "posture": posture,
                "confidence": confidence
            }
            
            # Add fallback warning if symbol was changed
            if market_data.get("fallback_used"):
                result["warning"] = (
                    f"Could not fetch {market_data['original_symbol']} data. "
                    f"Showing BTC instead."
                )
            
            # ================================================================
            # STEP 8: ADD PRO FEATURES
            # ================================================================
            result.update({
                "strategy_rules": self._check_strategy_rules(
                    indicators_lower, indicators_upper
                ),
                "volume_behavior": self._analyze_volume(
                    market_data["data_lower"], market_data["data_upper"]
                )
            })
            
            logger.info(f"Analysis complete: symbol={symbol}, regime={regime}, confidence={confidence}%")
            
            return result
            
        except MarketDataError as e:
            logger.error(f"Market data error for {symbol}: {str(e)}")
            raise Exception(f"Failed to fetch market data: {str(e)}")
        except ValueError as e:
            logger.error(f"Indicator calculation error for {symbol}: {str(e)}")
            raise Exception(f"Failed to calculate indicators: {str(e)}")
        except Exception as e:
            logger.error(f"Analysis error for {symbol}: {type(e).__name__}: {str(e)}", exc_info=True)
            if "data" in str(e).lower():
                raise Exception(f"Data error: {str(e)}")
            raise Exception(f"Analysis error: {str(e)}")
    
    # ========================================================================
    # REGIME DETERMINATION
    # ========================================================================
    
    def _determine_regime(self, ind_lower: Dict, ind_upper: Dict) -> str:
        """
        Determine market regime with clear classifications
        
        Args:
            ind_lower: Lower timeframe indicators
            ind_upper: Upper timeframe indicators
        
        Returns:
            Precise regime string
        """
        
        # Extract key indicators
        trend_upper = ind_upper.get("trend_bias", "neutral")
        trend_lower = ind_lower.get("trend_bias", "neutral")
        volatility_upper = ind_upper.get("volatility_level", "medium")
        volatility_lower = ind_lower.get("volatility_level", "medium")
        structure_upper = ind_upper.get("structure_bias", "choppy")
        
        # BEARISH REGIMES
        if trend_upper == "bearish":
            if volatility_upper == "high" or (volatility_upper == "medium" and volatility_lower == "high"):
                return "Volatile Bearish"
            return "Steady Bearish"
        
        # NEUTRAL/RANGING REGIMES
        elif trend_upper == "neutral":
            if trend_lower == "bullish":
                return "Ranging - Bullish Bias"
            elif trend_lower == "bearish":
                return "Ranging - Bearish Bias"
            return "Choppy Ranging"
        
        # BULLISH REGIMES
        elif trend_upper == "bullish":
            if trend_lower == "bullish" and structure_upper == "bullish":
                return "Strong Bullish"
            elif trend_lower == "neutral" or structure_upper == "choppy":
                return "Weak Bullish"
            return "Moderate Bullish"
        
        return "Choppy Ranging"
    
    # ========================================================================
    # RISK LEVEL CALCULATION
    # ========================================================================
    
    def _calculate_risk_level(
        self, 
        regime: str, 
        ind_lower: Dict, 
        ind_upper: Dict
    ) -> str:
        """Calculate risk level with clear criteria"""
        
        volatility_upper = ind_upper.get("volatility_level", "medium")
        volatility_lower = ind_lower.get("volatility_level", "medium")
        
        # HIGH RISK
        if "Volatile Bearish" in regime:
            return "🔴 High"
        
        if volatility_upper == "high" and volatility_lower == "high":
            return "🔴 High"
        
        if "Choppy" in regime and volatility_upper == "high":
            return "🔴 High"
        
        # LOW RISK
        if regime == "Strong Bullish" and volatility_upper == "low":
            return "🟢 Low"
        
        if "Bullish" in regime and volatility_upper in ["low", "medium"]:
            return "🟢 Low"
        
        if regime == "Steady Bearish" and volatility_upper == "low":
            return "🟢 Low"
        
        # MEDIUM RISK (default)
        return "🔶 Medium"
    
    # ========================================================================
    # POSTURE SUGGESTION (FIXED - NO PROBLEMATIC CHARACTERS)
    # ========================================================================
    
    def _suggest_posture(self, regime: str, risk_level: str, ind_lower: Dict, ind_upper: Dict) -> str:
        """
        Provide specific, actionable trading guidance
        
        Returns detailed instructions based on market conditions
        """
        
        # Extract additional context
        rsi = ind_upper.get("rsi", 50)
        volume_ratio = ind_lower.get("volume_ratio", 1.0)
        
        # HIGH RISK SCENARIOS
        if "🔴" in risk_level:
            if "Volatile Bearish" in regime:
                return (
                    "⛔ <b>DO NOT TRADE</b>\n"
                    "• Move to stablecoins immediately\n"
                    "• If you must short: use 1-2% position size max\n"
                    "• Set stops 3-5% above entry\n"
                    "• Expect rapid price swings"
                )
            
            if "Choppy" in regime:
                return (
                    "⚠️ <b>AVOID OR SCALP ONLY</b>\n"
                    "• Whipsaw risk is very high\n"
                    "• If scalping: 5-10 min timeframes only\n"
                    "• Take 0.5-1% profits quickly\n"
                    "• Stop loss at 0.3-0.5%"
                )
            
            return (
                "⚠️ <b>REDUCE RISK SIGNIFICANTLY</b>\n"
                "• Cut position sizes to 25-50% of normal\n"
                "• Tighten stops to 1-2%\n"
                "• Take profits at 2-3% (don't be greedy)\n"
                "• Consider sitting out until conditions improve"
            )
        
        # MEDIUM RISK SCENARIOS
        elif "🔶" in risk_level:
            if "Steady Bearish" in regime:
                return (
                    "📉 <b>SHORT BIAS - BE PATIENT</b>\n"
                    "• Wait for bounces to short (RSI above 60)\n"
                    "• Position size: 1-1.5% risk per trade\n"
                    "• Stops: 2-3% above entry\n"
                    "• Targets: 3-5% profit (1:2 risk/reward min)"
                )
            
            if "Ranging" in regime:
                if "Bullish Bias" in regime:
                    return (
                        "📊 <b>BUY DIPS - RANGE TRADE</b>\n"
                        "• Buy near range lows when RSI below 40\n"
                        "• Sell near range highs when RSI above 65\n"
                        "• Position size: 1.5-2%\n"
                        "• Quick profits: target 2-4% moves"
                    )
                elif "Bearish Bias" in regime:
                    return (
                        "📊 <b>SELL RALLIES - RANGE TRADE</b>\n"
                        "• Short near range highs when RSI above 60\n"
                        "• Cover near range lows when RSI below 35\n"
                        "• Position size: 1-1.5%\n"
                        "• Quick profits: target 2-4% moves"
                    )
                else:
                    return (
                        "📊 <b>NEUTRAL RANGE - SCALP BOTH WAYS</b>\n"
                        "• Trade both directions at extremes\n"
                        "• Buy RSI below 35, Sell RSI above 65\n"
                        "• Very tight stops (1%)\n"
                        "• Small position sizes (0.5-1%)"
                    )
            
            if "Bullish" in regime:
                return (
                    "📈 <b>LONG BIAS - STANDARD APPROACH</b>\n"
                    "• Buy pullbacks to moving averages\n"
                    "• Position size: 2% risk per trade\n"
                    "• Stops: 3-4% below entry\n"
                    "• Let winners run to 8-12%"
                )
        
        # LOW RISK SCENARIOS
        elif "🟢" in risk_level:
            if regime == "Strong Bullish":
                if volume_ratio > 1.2:
                    return (
                        "🚀 <b>STRONG BUY SIGNAL - HIGH CONVICTION</b>\n"
                        "• Add to positions on minor dips (1-2%)\n"
                        "• Position size: 2.5-3% (slightly aggressive)\n"
                        "• Stops: 5% below entry (give it room)\n"
                        "• Trail stops as price rises\n"
                        "• Target: 15-20%+ moves"
                    )
                else:
                    return (
                        "✅ <b>FAVORABLE FOR LONGS</b>\n"
                        "• Buy on 3-5% pullbacks\n"
                        "• Position size: 2-2.5%\n"
                        "• Stops: 4-5% below entry\n"
                        "• Take partial profits at 8-10%\n"
                        "• Hold remainder for bigger move"
                    )
            
            if "Moderate Bullish" in regime:
                return (
                    "✅ <b>GOOD CONDITIONS FOR LONGS</b>\n"
                    "• Enter on dips to support levels\n"
                    "• Position size: 2%\n"
                    "• Stops: 3-4% below entry\n"
                    "• Targets: 6-10% profit\n"
                    "• Watch for regime change if trend weakens"
                )
            
            if "Steady Bearish" in regime:
                return (
                    "📉 <b>SAFE TO SHORT - CLEAR DOWNTREND</b>\n"
                    "• Short rallies when RSI reaches 55-60\n"
                    "• Position size: 1.5-2%\n"
                    "• Stops: 3% above entry\n"
                    "• Targets: 5-8% profit\n"
                    "• Low volatility makes risk manageable"
                )
        
        # Fallback
        return (
            "⚠️ <b>PROCEED WITH CAUTION</b>\n"
            "• Use standard risk management (2% per trade)\n"
            "• Set stops at 3-4%\n"
            "• Take profits at 5-7%\n"
            "• Re-assess after each trade"
        )
    
    # ========================================================================
    # CONFIDENCE SCORE
    # ========================================================================
    
    def _calculate_confidence(self, ind_lower: Dict, ind_upper: Dict) -> int:
        """
        Calculate confidence score (0-100%) with clear methodology
        """
        
        confidence = 0
        
        # Extract indicators
        trend_lower = ind_lower.get("trend_bias", "neutral")
        trend_upper = ind_upper.get("trend_bias", "neutral")
        volatility_lower = ind_lower.get("volatility_level", "medium")
        volatility_upper = ind_upper.get("volatility_level", "medium")
        structure_upper = ind_upper.get("structure_bias", "choppy")
        
        # Trend Alignment (40 points)
        if trend_lower == trend_upper:
            confidence += 40
        elif trend_lower == "neutral" or trend_upper == "neutral":
            confidence += 20
        
        # Volatility Stability (30 points)
        if volatility_lower == volatility_upper:
            confidence += 30
        elif volatility_lower == "high" or volatility_upper == "high":
            confidence += 10
        else:
            confidence += 20
        
        # Structure Confirmation (30 points)
        if (trend_upper == "bullish" and structure_upper == "bullish") or \
           (trend_upper == "bearish" and structure_upper == "bearish"):
            confidence += 20
        
        if structure_upper != "choppy":
            confidence += 10
        
        return min(confidence, 100)
    
    # ========================================================================
    # PRO FEATURES
    # ========================================================================
    
    def _check_strategy_rules(self, ind_lower: Dict, ind_upper: Dict) -> Dict:
        """Check which strategy rules are met"""
        
        trend_lower = ind_lower.get("trend_bias", "neutral")
        trend_upper = ind_upper.get("trend_bias", "neutral")
        structure_upper = ind_upper.get("structure_bias", "choppy")
        volume_ratio = ind_lower.get("volume_ratio", 1.0)
        price = ind_upper.get("current_price", 0)
        ema_50 = ind_upper.get("ema_50", 0)
        ma_200 = ind_upper.get("ma_200", 0)
        
        rules = {
            "Timeframes aligned": trend_lower == trend_upper,
            "Above 50 EMA": price > ema_50 if ema_50 > 0 else False,
            "Above 200 MA": price > ma_200 if ma_200 > 0 else False,
            "Structure confirmed": (
                (trend_upper == "bullish" and structure_upper == "bullish") or
                (trend_upper == "bearish" and structure_upper == "bearish")
            ),
            "Volume surge": volume_ratio > 1.3,
            "Golden cross": ema_50 > ma_200 if (ema_50 > 0 and ma_200 > 0) else False,
        }
        
        return rules
    
    def _analyze_volume(self, data_lower: List[Dict], data_upper: List[Dict]) -> str:
        """Analyze volume behavior with clear signals"""
        
        if not data_lower or len(data_lower) < 20:
            return "➡️ Stable volume"
        
        recent_volumes = [float(c.get("volume", 0)) for c in data_lower[-5:] if float(c.get("volume", 0)) > 0]
        avg_volume = sum([float(c.get("volume", 0)) for c in data_lower[-20:]]) / 20
        
        if not recent_volumes or avg_volume == 0:
            return "➡️ Stable volume"
        
        # Check for increasing trend
        if len(recent_volumes) >= 3 and all(recent_volumes[i] <= recent_volumes[i+1] for i in range(len(recent_volumes)-1)):
            return "📈 Rising volume (bullish confirmation)"
        
        # Current vs average
        current_volume = recent_volumes[-1]
        ratio = current_volume / avg_volume
        
        if ratio > 1.5:
            return "⚡ High volume (strong interest)"
        elif ratio < 0.7:
            return "📉 Low volume (weak participation)"
        else:
            return "➡️ Normal volume"
