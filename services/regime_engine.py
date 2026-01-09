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
- utils.regime_data (fetch data from Twelve Data API)
- utils.regime_indicators (calculate technical indicators)
- utils.auth (check user subscription tier)
"""
from utils.regime_data import fetch_regime_data, MarketDataError
from utils.regime_indicators import calculate_indicators
from typing import Dict, List
import logging

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
            # Fetch data for both timeframes
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
            # STEP 5: SUGGEST TRADING POSTURE
            # ================================================================
            posture = self._suggest_posture(regime, risk_level)
            
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
                    f"⚠️ Could not fetch {market_data['original_symbol']} data. "
                    f"Showing BTC instead."
                )
            
            # ================================================================
            # STEP 8: ADD PRO FEATURES (always - regime.py now enforces Pro)
            # ================================================================
            result.update({
                "strategy_rules": self._check_strategy_rules(
                    indicators_lower, indicators_upper
                ),
                "volume_behavior": self._analyze_volume(
                    market_data["data_lower"], market_data["data_upper"]
                ),
                "key_levels": self._find_key_levels(
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
    # REGIME DETERMINATION (TIMEFRAME-AGNOSTIC)
    # ========================================================================
    
    def _determine_regime(self, ind_lower: Dict, ind_upper: Dict) -> str:
        """
        Determine market regime based on trend and volatility
        
        Now timeframe-agnostic:
        - ind_lower: Lower timeframe indicators (1H or 4H)
        - ind_upper: Upper timeframe indicators (4H or Daily)
        
        Algorithm:
        1. Check Upper trend (primary timeframe)
        2. Check Upper volatility
        3. Check Lower for confirmation
        4. Classify into regime
        
        Regimes:
        - High-Risk Bearish: Bearish + High volatility
        - Controlled Bearish: Bearish + Low/Med volatility
        - Ranging: Neutral trend
        - Ranging (Bullish/Bearish Bias): Neutral Upper, directional Lower
        - Strong Bullish Trending: Bullish + Strong confirmation
        - Weak Bullish Trending: Bullish + Weak confirmation
        - Bullish Trending: Default bullish
        
        Args:
            ind_lower: Lower timeframe indicators
            ind_upper: Upper timeframe indicators
        
        Returns:
            Regime string
        """
        
        # Extract key indicators
        trend_upper = ind_upper.get("trend_bias", "neutral")
        trend_lower = ind_lower.get("trend_bias", "neutral")
        volatility_upper = ind_upper.get("volatility_level", "medium")
        volatility_lower = ind_lower.get("volatility_level", "medium")
        structure_upper = ind_upper.get("structure_bias", "choppy")
        structure_lower = ind_lower.get("structure_bias", "choppy")
        
        # ====================================================================
        # BEARISH REGIMES
        # ====================================================================
        if trend_upper == "bearish":
            
            # High volatility = dangerous market
            if volatility_upper == "high":
                return "High-Risk Bearish"
            
            # Medium upper vol + high lower vol = also dangerous
            if volatility_upper == "medium" and volatility_lower == "high":
                return "High-Risk Bearish"
            
            # Otherwise controlled decline
            return "Controlled Bearish"
        
        # ====================================================================
        # NEUTRAL REGIMES (RANGING)
        # ====================================================================
        elif trend_upper == "neutral":
            
            # Both neutral = clear ranging
            if trend_lower == "neutral" or structure_lower == "choppy":
                return "Ranging"
            
            # Lower bullish but Upper neutral = ranging with bullish bias
            if trend_lower == "bullish":
                return "Ranging (Bullish Bias)"
            
            # Lower bearish but Upper neutral = ranging with bearish bias
            if trend_lower == "bearish":
                return "Ranging (Bearish Bias)"
            
            # Default neutral
            return "Ranging"
        
        # ====================================================================
        # BULLISH REGIMES
        # ====================================================================
        elif trend_upper == "bullish":
            
            # Strong confirmation: Lower bullish + Upper structure bullish
            if trend_lower == "bullish" and structure_upper == "bullish":
                return "Strong Bullish Trending"
            
            # Weak confirmation: Lower neutral or structure choppy
            if trend_lower == "neutral" or structure_upper == "choppy":
                return "Weak Bullish Trending"
            
            # Default bullish
            return "Bullish Trending"
        
        # Fallback (should rarely reach here)
        return "Ranging"
    
    # ========================================================================
    # RISK LEVEL CALCULATION (TIMEFRAME-AGNOSTIC)
    # ========================================================================
    
    def _calculate_risk_level(
        self, 
        regime: str, 
        ind_lower: Dict, 
        ind_upper: Dict
    ) -> str:
        """
        Calculate risk level based on regime and market conditions
        
        Risk Levels:
        - 🔴 High: Dangerous conditions, high volatility, unclear structure
        - 🔶 Medium: Normal conditions, manageable risk
        - 🟢 Low: Favorable conditions, low volatility, clear structure
        
        Args:
            regime: Market regime string
            ind_lower: Lower timeframe indicators
            ind_upper: Upper timeframe indicators
        
        Returns:
            Risk level with emoji
        """
        
        # Extract relevant indicators
        volatility_upper = ind_upper.get("volatility_level", "medium")
        volatility_lower = ind_lower.get("volatility_level", "medium")
        structure_upper = ind_upper.get("structure_bias", "choppy")
        lower_highs = ind_upper.get("lower_highs", False)
        volume_ratio = ind_lower.get("volume_ratio", 1.0)
        
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
        if volatility_upper == "high" and volatility_lower == "high":
            return "🔴 High"
        
        # 4. Ranging with high volatility = whipsaw risk
        if "Ranging" in regime and volatility_upper == "high":
            return "🔴 High"
        
        # ====================================================================
        # LOW RISK CONDITIONS
        # ====================================================================
        
        # 1. Strong bullish + low volatility = ideal conditions
        if regime == "Strong Bullish Trending" and volatility_upper == "low":
            return "🟢 Low"
        
        # 2. Bullish + aligned structure + low/med volatility = safe
        if ("Bullish" in regime and 
            structure_upper == "bullish" and 
            volatility_upper in ["low", "medium"]):
            return "🟢 Low"
        
        # 3. Controlled bearish + low volatility = predictable
        if regime == "Controlled Bearish" and volatility_upper == "low":
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
    # CONFIDENCE SCORE (TIMEFRAME-AGNOSTIC)
    # ========================================================================
    
    def _calculate_confidence(self, ind_lower: Dict, ind_upper: Dict) -> int:
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
            ind_lower: Lower timeframe indicators
            ind_upper: Upper timeframe indicators
        
        Returns:
            Confidence score (0-100)
        """
        
        confidence = 0
        
        # Extract indicators
        trend_lower = ind_lower.get("trend_bias", "neutral")
        trend_upper = ind_upper.get("trend_bias", "neutral")
        volatility_lower = ind_lower.get("volatility_level", "medium")
        volatility_upper = ind_upper.get("volatility_level", "medium")
        structure_lower = ind_lower.get("structure_bias", "choppy")
        structure_upper = ind_upper.get("structure_bias", "choppy")
        
        # ====================================================================
        # TREND ALIGNMENT (40 points max)
        # ====================================================================
        
        if trend_lower == trend_upper:
            # Perfect alignment
            confidence += 40
        elif trend_lower == "neutral" or trend_upper == "neutral":
            # Partial alignment (one neutral)
            confidence += 20
        else:
            # Misalignment
            confidence += 0
        
        # ====================================================================
        # VOLATILITY CONFIRMATION (30 points max)
        # ====================================================================
        
        if volatility_lower == volatility_upper:
            # Both same level = stable
            confidence += 30
        elif volatility_lower == "high" or volatility_upper == "high":
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
            (trend_upper == "bullish" and structure_upper == "bullish") or
            (trend_upper == "bearish" and structure_upper == "bearish")
        )
        
        if trend_structure_match:
            confidence += 20
        
        # Check if both timeframes agree on structure
        if structure_lower == structure_upper:
            confidence += 10
        
        # Cap at 100
        return min(confidence, 100)
    
    # ========================================================================
    # PRO FEATURES (TIMEFRAME-AGNOSTIC)
    # ========================================================================
    
    def _check_strategy_rules(self, ind_lower: Dict, ind_upper: Dict) -> Dict:
        """
        Check which strategy rules are met (PRO only)
        
        Returns dictionary of rule names and boolean status
        """
        
        # Extract indicators safely
        trend_lower = ind_lower.get("trend_bias", "neutral")
        trend_upper = ind_upper.get("trend_bias", "neutral")
        structure_upper = ind_upper.get("structure_bias", "choppy")
        volume_ratio = ind_lower.get("volume_ratio", 1.0)
        price = ind_upper.get("current_price", 0)
        ema_50 = ind_upper.get("ema_50", 0)
        ma_200 = ind_upper.get("ma_200", 0)
        
        rules = {
            "Trend aligned across timeframes": trend_lower == trend_upper,
            "Price above 50 EMA": price > ema_50 if ema_50 > 0 else False,
            "Price above 200 MA": price > ma_200 if ma_200 > 0 else False,
            "Structure confirms trend": (
                (trend_upper == "bullish" and structure_upper == "bullish") or
                (trend_upper == "bearish" and structure_upper == "bearish")
            ),
            "Volume above average": volume_ratio > 1.0,
            "50 EMA above 200 MA": ema_50 > ma_200 if (ema_50 > 0 and ma_200 > 0) else False,
        }
        
        return rules
    
    def _analyze_volume(self, data_lower: List[Dict], data_upper: List[Dict]) -> str:
        """
        Analyze volume behavior (PRO only)
        
        Uses lower timeframe for more granular volume analysis
        
        Returns human-readable volume analysis with emoji
        """
        
        if not data_lower or len(data_lower) < 20:
            return "➡️ Normal (stable activity)"
        
        # Get recent volumes from lower timeframe
        recent_volumes = [float(c.get("volume", 0)) for c in data_lower[-5:]]
        avg_volume = sum([float(c.get("volume", 0)) for c in data_lower[-20:]]) / 20
        
        # Filter out zero volumes
        recent_volumes = [v for v in recent_volumes if v > 0]
        
        if not recent_volumes or avg_volume == 0:
            return "➡️ Normal (stable activity)"
        
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
    
    def _find_key_levels(self, data_lower: List[Dict], data_upper: List[Dict]) -> Dict:
        """
        Find support and resistance levels using price clustering.
        
        Real S&R forms at prices where the market has reacted multiple times.
        Uses upper timeframe (more significant levels).
        
        Returns:
            Dictionary with support, resistance, and strength indicators
        """
        
        if not data_upper or len(data_upper) < 20:
            return {
                "support": 0.0,
                "resistance": 0.0,
                "support_strength": "weak",
                "resistance_strength": "weak",
                "current_price": 0.0
            }
        
        # Get current price from most recent candle
        current_price = float(data_upper[-1]["close"])
        
        # Use last 30-50 candles for better level detection
        lookback = min(50, len(data_upper))
        recent_data = data_upper[-lookback:]
        
        # Collect all significant price points (highs and lows)
        price_points = []
        for candle in recent_data:
            price_points.append(float(candle["high"]))
            price_points.append(float(candle["low"]))
        
        # Find price clusters using tolerance (2% for crypto volatility)
        tolerance_pct = 0.02  # 2% tolerance for clustering
        clusters = self._cluster_prices(price_points, tolerance_pct)
        
        # Count touches for each cluster (strength indicator)
        cluster_strengths = []
        for cluster_price in clusters:
            touch_count = self._count_touches(recent_data, cluster_price, tolerance_pct)
            cluster_strengths.append({
                "price": cluster_price,
                "touches": touch_count,
                "recency": self._calculate_recency_score(recent_data, cluster_price, tolerance_pct)
            })
        
        # Find strongest support (below current price)
        supports = [c for c in cluster_strengths if c["price"] < current_price]
        support_level = None
        support_strength = "weak"
        
        if supports:
            # Sort by touches * recency score (recent touches matter more)
            supports.sort(key=lambda x: x["touches"] * x["recency"], reverse=True)
            support_level = supports[0]["price"]
            support_strength = self._get_strength_label(supports[0]["touches"])
        else:
            # Fallback to simple lowest low if no clusters below
            support_level = min(float(c["low"]) for c in recent_data[-20:])
        
        # Find strongest resistance (above current price)
        resistances = [c for c in cluster_strengths if c["price"] > current_price]
        resistance_level = None
        resistance_strength = "weak"
        
        if resistances:
            resistances.sort(key=lambda x: x["touches"] * x["recency"], reverse=True)
            resistance_level = resistances[0]["price"]
            resistance_strength = self._get_strength_label(resistances[0]["touches"])
        else:
            # Fallback to simple highest high if no clusters above
            resistance_level = max(float(c["high"]) for c in recent_data[-20:])
        
        return {
            "support": round(support_level, 2),
            "resistance": round(resistance_level, 2),
            "support_strength": support_strength,
            "resistance_strength": resistance_strength,
            "current_price": round(current_price, 2)
        }
    
    def _cluster_prices(self, prices: List[float], tolerance_pct: float) -> List[float]:
        """
        Group similar prices into clusters.
        Prices within tolerance_pct of each other are considered the same level.
        """
        if not prices:
            return []
        
        sorted_prices = sorted(prices)
        clusters = []
        current_cluster = [sorted_prices[0]]
        
        for price in sorted_prices[1:]:
            # Check if price is within tolerance of cluster average
            cluster_avg = sum(current_cluster) / len(current_cluster)
            tolerance = cluster_avg * tolerance_pct
            
            if abs(price - cluster_avg) <= tolerance:
                current_cluster.append(price)
            else:
                # Finalize current cluster and start new one
                clusters.append(sum(current_cluster) / len(current_cluster))
                current_cluster = [price]
        
        # Add final cluster
        if current_cluster:
            clusters.append(sum(current_cluster) / len(current_cluster))
        
        return clusters
    
    def _count_touches(self, candles: List[Dict], level: float, tolerance_pct: float) -> int:
        """
        Count how many times price touched this level.
        A "touch" is when high or low comes within tolerance of the level.
        """
        touches = 0
        tolerance = level * tolerance_pct
        
        for candle in candles:
            high = float(candle["high"])
            low = float(candle["low"])
            
            # Check if price touched the level
            if low <= level + tolerance and high >= level - tolerance:
                touches += 1
        
        return touches
    
    def _calculate_recency_score(self, candles: List[Dict], level: float, tolerance_pct: float) -> float:
        """
        Calculate recency score - recent touches are more important.
        Returns a score between 0 and 1, where 1 = most recent touch.
        """
        total_candles = len(candles)
        tolerance = level * tolerance_pct
        
        # Find most recent touch
        most_recent_touch = 0
        for i, candle in enumerate(candles):
            high = float(candle["high"])
            low = float(candle["low"])
            
            if low <= level + tolerance and high >= level - tolerance:
                most_recent_touch = i
        
        # Convert to recency score (0 to 1)
        if total_candles > 0:
            return (most_recent_touch + 1) / total_candles
        return 0.0
    
    def _get_strength_label(self, touch_count: int) -> str:
        """Convert touch count to strength label"""
        if touch_count >= 5:
            return "strong"
        elif touch_count >= 3:
            return "moderate"
        else:
            return "weak"