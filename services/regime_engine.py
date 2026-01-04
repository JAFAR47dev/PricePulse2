# ============================================================================
# PHASE 4 — REGIME ENGINE (PRODUCTION-READY)
# ============================================================================

# ----------------------------------------------------------------------------
# services/regime_engine.py
# ----------------------------------------------------------------------------
"""
Core logic for regime analysis
Determines market regime, risk level, and trading posture

Integrates with:
- utils.market_data (fetch data from Twelve Data API)
- utils.regime_indicators (calculate technical indicators)
- utils.auth (check user subscription tier)
"""
from utils.regime_data import fetch_regime_data, MarketDataError
from utils.regime_indicators import calculate_indicators
from typing import Dict, List


class RegimeEngine:
    """
    Engine for calculating market regime and risk
    
    Uses multi-timeframe analysis (4H + Daily) to determine:
    - Market regime (Bullish, Bearish, Ranging, etc.)
    - Risk level (Low, Medium, High)
    - Trading posture (what to do)
    - Confidence score (0-100%)
    """
    
    def __init__(self):
        """Initialize regime engine"""
        self.timeframes = ["4h", "1day"]
        self.min_candles_4h = 100
        self.min_candles_daily = 50
    
    async def analyze(self, symbol: str, plan: str) -> Dict:
        """
        Analyze market regime for given symbol
        Returns different detail levels based on user plan
        
        Args:
            symbol: Trading symbol (e.g., "BTC", "ETH")
            plan: User plan tier (from get_user_plan)
        
        Returns:
            Dictionary with regime analysis results
            
        Raises:
            Exception: If data fetch or analysis fails
        """
        
        try:
            # ================================================================
            # STEP 1: FETCH MARKET DATA
            # ================================================================
            # This will automatically fallback to BTC if symbol fails
            market_data = await fetch_regime_data(symbol)
            
            # Validate data was received
            if not market_data["data_4h"] or not market_data["data_daily"]:
                raise Exception("No market data received")
            
            # ================================================================
            # STEP 2: CALCULATE INDICATORS
            # ================================================================
            indicators_4h = calculate_indicators(market_data["data_4h"], "4h")
            indicators_daily = calculate_indicators(market_data["data_daily"], "1day")
            
            # ================================================================
            # STEP 3: DETERMINE REGIME
            # ================================================================
            regime = self._determine_regime(indicators_4h, indicators_daily)
            
            # ================================================================
            # STEP 4: CALCULATE RISK LEVEL
            # ================================================================
            risk_level = self._calculate_risk_level(regime, indicators_4h, indicators_daily)
            
            # ================================================================
            # STEP 5: SUGGEST TRADING POSTURE
            # ================================================================
            posture = self._suggest_posture(regime, risk_level)
            
            # ================================================================
            # STEP 6: CALCULATE CONFIDENCE
            # ================================================================
            confidence = self._calculate_confidence(indicators_4h, indicators_daily)
            
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
                    f"⚠️ Could not fetch {market_data['original_symbol']} data. "
                    f"Showing BTC instead."
                )
            
            # ================================================================
            # STEP 8: ADD PRO FEATURES (if applicable)
            # ================================================================
            from utils.auth import is_pro_plan
            
            if is_pro_plan(plan):
                result.update({
                    "strategy_rules": self._check_strategy_rules(
                        indicators_4h, indicators_daily
                    ),
                    "volume_behavior": self._analyze_volume(
                        market_data["data_4h"], market_data["data_daily"]
                    ),
                    "key_levels": self._find_key_levels(
                        market_data["data_4h"], market_data["data_daily"]
                    )
                })
            
            return result
            
        except MarketDataError as e:
            # Data fetch error - re-raise with clear message
            raise Exception(f"Failed to fetch market data: {str(e)}")
        except ValueError as e:
            # Indicator calculation error
            raise Exception(f"Failed to calculate indicators: {str(e)}")
        except Exception as e:
            # Catch-all for unexpected errors
            if "data" in str(e).lower():
                raise Exception(f"Data error: {str(e)}")
            raise Exception(f"Analysis error: {str(e)}")
    
    # ========================================================================
    # REGIME DETERMINATION
    # ========================================================================
    
    def _determine_regime(self, ind_4h: Dict, ind_daily: Dict) -> str:
        """
        Determine market regime based on trend and volatility
        
        Algorithm:
        1. Check Daily trend (primary timeframe)
        2. Check Daily volatility
        3. Check 4H for confirmation
        4. Classify into regime
        
        Regimes:
        - High-Risk Bearish: Bearish + High volatility
        - Controlled Bearish: Bearish + Low/Med volatility
        - Ranging: Neutral trend
        - Ranging (Bullish/Bearish Bias): Neutral Daily, directional 4H
        - Strong Bullish Trending: Bullish + Strong confirmation
        - Weak Bullish Trending: Bullish + Weak confirmation
        - Bullish Trending: Default bullish
        
        Args:
            ind_4h: 4H timeframe indicators
            ind_daily: Daily timeframe indicators
        
        Returns:
            Regime string
        """
        
        # Extract key indicators
        trend_daily = ind_daily.get("trend_bias", "neutral")
        trend_4h = ind_4h.get("trend_bias", "neutral")
        volatility_daily = ind_daily.get("volatility_level", "medium")
        volatility_4h = ind_4h.get("volatility_level", "medium")
        structure_daily = ind_daily.get("structure_bias", "choppy")
        structure_4h = ind_4h.get("structure_bias", "choppy")
        
        # ====================================================================
        # BEARISH REGIMES
        # ====================================================================
        if trend_daily == "bearish":
            
            # High volatility = dangerous market
            if volatility_daily == "high":
                return "High-Risk Bearish"
            
            # Medium daily vol + high 4H vol = also dangerous
            if volatility_daily == "medium" and volatility_4h == "high":
                return "High-Risk Bearish"
            
            # Otherwise controlled decline
            return "Controlled Bearish"
        
        # ====================================================================
        # NEUTRAL REGIMES (RANGING)
        # ====================================================================
        elif trend_daily == "neutral":
            
            # Both neutral = clear ranging
            if trend_4h == "neutral" or structure_4h == "choppy":
                return "Ranging"
            
            # 4H bullish but Daily neutral = ranging with bullish bias
            if trend_4h == "bullish":
                return "Ranging (Bullish Bias)"
            
            # 4H bearish but Daily neutral = ranging with bearish bias
            if trend_4h == "bearish":
                return "Ranging (Bearish Bias)"
            
            # Default neutral
            return "Ranging"
        
        # ====================================================================
        # BULLISH REGIMES
        # ====================================================================
        elif trend_daily == "bullish":
            
            # Strong confirmation: 4H bullish + Daily structure bullish
            if trend_4h == "bullish" and structure_daily == "bullish":
                return "Strong Bullish Trending"
            
            # Weak confirmation: 4H neutral or structure choppy
            if trend_4h == "neutral" or structure_daily == "choppy":
                return "Weak Bullish Trending"
            
            # Default bullish
            return "Bullish Trending"
        
        # Fallback (should rarely reach here)
        return "Ranging"
    
    # ========================================================================
    # RISK LEVEL CALCULATION
    # ========================================================================
    
    def _calculate_risk_level(
        self, 
        regime: str, 
        ind_4h: Dict, 
        ind_daily: Dict
    ) -> str:
        """
        Calculate risk level based on regime and market conditions
        
        Risk Levels:
        - 🔴 High: Dangerous conditions, high volatility, unclear structure
        - 🔶 Medium: Normal conditions, manageable risk
        - 🟢 Low: Favorable conditions, low volatility, clear structure
        
        Args:
            regime: Market regime string
            ind_4h: 4H indicators
            ind_daily: Daily indicators
        
        Returns:
            Risk level with emoji
        """
        
        # Extract relevant indicators
        volatility_daily = ind_daily.get("volatility_level", "medium")
        volatility_4h = ind_4h.get("volatility_level", "medium")
        structure_daily = ind_daily.get("structure_bias", "choppy")
        lower_highs = ind_daily.get("lower_highs", False)
        volume_ratio = ind_4h.get("volume_ratio", 1.0)
        
        # ====================================================================
        # HIGH RISK CONDITIONS
        # ====================================================================
        
        # 1. High-Risk Bearish regime is always high risk
        if regime == "High-Risk Bearish":
            return "🔴 High"
        
        # 2. Bearish + lower highs + high volume = panic selling
        if "Bearish" in regime and lower_highs and volume_ratio > 1.5:
            return "🔴 High"
        
        # 3. High volatility on both timeframes = unstable
        if volatility_daily == "high" and volatility_4h == "high":
            return "🔴 High"
        
        # 4. Ranging with high volatility = whipsaw risk
        if "Ranging" in regime and volatility_daily == "high":
            return "🔴 High"
        
        # ====================================================================
        # LOW RISK CONDITIONS
        # ====================================================================
        
        # 1. Strong bullish + low volatility = ideal conditions
        if regime == "Strong Bullish Trending" and volatility_daily == "low":
            return "🟢 Low"
        
        # 2. Bullish + aligned structure + low/med volatility = safe
        if ("Bullish" in regime and 
            structure_daily == "bullish" and 
            volatility_daily in ["low", "medium"]):
            return "🟢 Low"
        
        # 3. Controlled bearish + low volatility = predictable
        if regime == "Controlled Bearish" and volatility_daily == "low":
            return "🟢 Low"
        
        # ====================================================================
        # MEDIUM RISK (DEFAULT)
        # ====================================================================
        
        return "🔶 Medium"
    
    # ========================================================================
    # POSTURE SUGGESTION
    # ========================================================================
    
    def _suggest_posture(self, regime: str, risk_level: str) -> str:
        """
        Suggest trading posture based on regime and risk level
        
        Returns actionable advice for traders
        
        Args:
            regime: Market regime
            risk_level: Risk level with emoji
        
        Returns:
            Trading posture string with emoji
        """
        
        # ====================================================================
        # HIGH RISK POSTURES (🔴)
        # ====================================================================
        if "🔴" in risk_level:
            
            if regime == "High-Risk Bearish":
                return "❌ Stay in stables or short only with tight stops"
            
            if "Bearish" in regime:
                return "⚠️ Avoid trading or reduce position size significantly"
            
            if "Ranging" in regime:
                return "⚠️ Range trade only with very tight stops"
            
            return "⚠️ Trade carefully with reduced size and tight stops"
        
        # ====================================================================
        # MEDIUM RISK POSTURES (🔶)
        # ====================================================================
        elif "🔶" in risk_level:
            
            if "Bearish" in regime:
                return "⚠️ Trade carefully, prefer shorts, use tight stops"
            
            if "Ranging" in regime:
                return "📊 Range trade: buy support, sell resistance"
            
            if "Bullish" in regime:
                return "✅ Trade normally with standard risk management"
            
            return "✅ Trade carefully with standard stops"
        
        # ====================================================================
        # LOW RISK POSTURES (🟢)
        # ====================================================================
        elif "🟢" in risk_level:
            
            if "Bullish" in regime:
                return "✅ Trade normally, favorable conditions for longs"
            
            if regime == "Controlled Bearish":
                return "✅ Trade carefully, good for shorts with defined risk"
            
            return "✅ Trade normally with standard risk management"
        
        # Fallback
        return "✅ Trade with caution and proper risk management"
    
    # ========================================================================
    # CONFIDENCE SCORE
    # ========================================================================
    
    def _calculate_confidence(self, ind_4h: Dict, ind_daily: Dict) -> int:
        """
        Calculate confidence score (0-100%)
        
        Scoring breakdown:
        - Trend Alignment (40 points max)
          - Perfect: 40 pts
          - Partial: 20 pts
          - Misaligned: 0 pts
        
        - Volatility Confirmation (30 points max)
          - Same level: 30 pts
          - One high: 10 pts
          - Mixed: 20 pts
        
        - Structure Confirmation (30 points max)
          - Structure matches trend: 20 pts
          - Both timeframes agree: 10 pts
        
        Args:
            ind_4h: 4H indicators
            ind_daily: Daily indicators
        
        Returns:
            Confidence score (0-100)
        """
        
        confidence = 0
        
        # Extract indicators
        trend_4h = ind_4h.get("trend_bias", "neutral")
        trend_daily = ind_daily.get("trend_bias", "neutral")
        volatility_4h = ind_4h.get("volatility_level", "medium")
        volatility_daily = ind_daily.get("volatility_level", "medium")
        structure_4h = ind_4h.get("structure_bias", "choppy")
        structure_daily = ind_daily.get("structure_bias", "choppy")
        
        # ====================================================================
        # TREND ALIGNMENT (40 points max)
        # ====================================================================
        
        if trend_4h == trend_daily:
            # Perfect alignment
            confidence += 40
        elif trend_4h == "neutral" or trend_daily == "neutral":
            # Partial alignment (one neutral)
            confidence += 20
        else:
            # Misalignment
            confidence += 0
        
        # ====================================================================
        # VOLATILITY CONFIRMATION (30 points max)
        # ====================================================================
        
        if volatility_4h == volatility_daily:
            # Both same level = stable
            confidence += 30
        elif volatility_4h == "high" or volatility_daily == "high":
            # One high = less confident
            confidence += 10
        else:
            # Mixed but not high
            confidence += 20
        
        # ====================================================================
        # STRUCTURE CONFIRMATION (30 points max)
        # ====================================================================
        
        # Check if structure aligns with trend
        trend_structure_match = (
            (trend_daily == "bullish" and structure_daily == "bullish") or
            (trend_daily == "bearish" and structure_daily == "bearish")
        )
        
        if trend_structure_match:
            confidence += 20
        
        # Check if both timeframes agree on structure
        if structure_4h == structure_daily:
            confidence += 10
        
        # Cap at 100
        return min(confidence, 100)
    
    # ========================================================================
    # PRO FEATURES
    # ========================================================================
    
    def _check_strategy_rules(self, ind_4h: Dict, ind_daily: Dict) -> Dict:
        """
        Check which strategy rules are met (PRO only)
        
        Returns dictionary of rule names and boolean status
        """
        
        # Extract indicators safely
        trend_4h = ind_4h.get("trend_bias", "neutral")
        trend_daily = ind_daily.get("trend_bias", "neutral")
        structure_daily = ind_daily.get("structure_bias", "choppy")
        volume_ratio = ind_4h.get("volume_ratio", 1.0)
        price = ind_daily.get("current_price", 0)
        ema_50 = ind_daily.get("ema_50", 0)
        ma_200 = ind_daily.get("ma_200", 0)
        
        rules = {
            "Trend aligned across timeframes": trend_4h == trend_daily,
            "Price above 50 EMA": price > ema_50,
            "Price above 200 MA": price > ma_200,
            "Structure confirms trend": (
                (trend_daily == "bullish" and structure_daily == "bullish") or
                (trend_daily == "bearish" and structure_daily == "bearish")
            ),
            "Volume above average": volume_ratio > 1.0,
            "50 EMA above 200 MA": ema_50 > ma_200,
        }
        
        return rules
    
    def _analyze_volume(self, data_4h: List[Dict], data_daily: List[Dict]) -> str:
        """
        Analyze volume behavior (PRO only)
        
        Returns human-readable volume analysis with emoji
        """
        
        if not data_4h or len(data_4h) < 20:
            return "➡️ Normal (stable activity)"
        
        # Get recent volumes
        recent_volumes = [float(c["volume"]) for c in data_4h[-5:]]
        avg_volume = sum([float(c["volume"]) for c in data_4h[-20:]]) / 20
        
        # Check if volume is consistently increasing
        if len(recent_volumes) >= 3:
            increasing = all(
                recent_volumes[i] <= recent_volumes[i+1] 
                for i in range(len(recent_volumes)-1)
            )
            
            if increasing:
                return "📈 Increasing (strong momentum)"
        
        # Compare current to average
        current_volume = recent_volumes[-1]
        ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
        
        if ratio > 1.5:
            return "⚡ Above average (high activity)"
        elif ratio < 0.7:
            return "📉 Below average (low activity)"
        else:
            return "➡️ Normal (stable activity)"
    
    def _find_key_levels(self, data_4h: List[Dict], data_daily: List[Dict]) -> Dict:
        """
        Find support and resistance levels (PRO only)
        
        Uses recent highs/lows from Daily timeframe
        
        Returns:
            Dictionary with support and resistance prices
        """
        
        if not data_daily or len(data_daily) < 20:
            return {"support": 0.0, "resistance": 0.0}
        
        # Use last 20 Daily candles for key levels
        recent_candles = data_daily[-20:]
        
        # Find support (lowest low)
        support = min(float(c["low"]) for c in recent_candles)
        
        # Find resistance (highest high)
        resistance = max(float(c["high"]) for c in recent_candles)
        
        return {
            "support": round(support, 2),
            "resistance": round(resistance, 2)
        }