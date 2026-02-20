import asyncio
import httpx
import os
import json
from dotenv import load_dotenv
from services.levels_engine import LevelsEngine
from utils.patterns import (
    detect_divergences,
    detect_engulfing_patterns,
    detect_trendline_breaks,
    detect_golden_death_crosses,
    detect_double_top_bottom
)

load_dotenv()

# ============================================================================
# COINGECKO API CONFIGURATION
# ============================================================================

COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

def load_coingecko_ids():
    """Load symbol to CoinGecko ID mapping"""
    try:
        with open("services/top100_coingecko_ids.json", "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading CoinGecko IDs: {e}")
        return {}

COINGECKO_IDS = load_coingecko_ids()

TIMEFRAME_MAP = {
    "5m": "5min", "15m": "15min", "30m": "30min",
    "1h": "1h", "2h": "2h", "4h": "4h", "8h": "8h", "1d": "1day"
}

COINGECKO_CANDLE_DAYS = {
    "5m": 1, "15m": 1, "30m": 3, "1h": 7,
    "2h": 14, "4h": 30, "8h": 60, "1d": 90
}

# ============================================================================
# DATA FETCHING FUNCTIONS
# ============================================================================

async def fetch_candles_from_coingecko(symbol: str, timeframe: str, limit: int = 200) -> list:
    """Fetch OHLCV candles from CoinGecko API"""
    try:
        symbol_upper = symbol.upper()
        coin_id = COINGECKO_IDS.get(symbol_upper)
        
        if not coin_id:
            print(f"❌ {symbol} not found in CoinGecko mapping")
            return None
        
        days = COINGECKO_CANDLE_DAYS.get(timeframe, 7)
        url = f"{COINGECKO_BASE_URL}/coins/{coin_id}/ohlc"
        params = {"vs_currency": "usd", "days": days}
        
        headers = {}
        if COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = COINGECKO_API_KEY
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params, headers=headers)
        
        if resp.status_code != 200:
            print(f"❌ CoinGecko API error: {resp.status_code}")
            return None
        
        data = resp.json()
        if not data:
            return None
        
        candles = []
        for item in data:
            candles.append({
                "datetime": item[0],
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": 0
            })
        
        candles = calculate_candle_indicators(candles)
        print(f"✅ Fetched {len(candles)} candles for {symbol} on {timeframe}")
        return candles
        
    except Exception as e:
        print(f"❌ Error fetching candles for {symbol}: {e}")
        return None


def calculate_candle_indicators(candles: list) -> list:
    """Calculate basic indicators from candle data"""
    if not candles or len(candles) < 50:
        return candles
    
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    
    ema20_values = calculate_ema_series(closes, 20)
    ema50_values = calculate_ema_series(closes, 50)
    ema200_values = calculate_ema_series(closes, 200)
    rsi_values = calculate_rsi_series(closes, 14)
    macd_values = calculate_macd_series(closes)
    
    for i, candle in enumerate(candles):
        candle["ema"] = ema20_values[i] if i < len(ema20_values) else 0
        candle["ema50"] = ema50_values[i] if i < len(ema50_values) else 0
        candle["ema200"] = ema200_values[i] if i < len(ema200_values) else 0
        candle["rsi"] = rsi_values[i] if i < len(rsi_values) else 50
        
        if i < len(macd_values):
            candle["macd"] = macd_values[i]["macd"]
            candle["macdSignal"] = macd_values[i]["signal"]
            candle["macdHist"] = macd_values[i]["histogram"]
        else:
            candle["macd"] = 0
            candle["macdSignal"] = 0
            candle["macdHist"] = 0
    
    return candles


def calculate_ema_series(prices: list, period: int) -> list:
    """Calculate EMA for entire series"""
    if len(prices) < period:
        return [0] * len(prices)
    
    k = 2 / (period + 1)
    ema_values = []
    sma = sum(prices[:period]) / period
    ema_values.append(sma)
    
    for i in range(period, len(prices)):
        ema = prices[i] * k + ema_values[-1] * (1 - k)
        ema_values.append(ema)
    
    return [0] * (period - 1) + ema_values


def calculate_rsi_series(prices: list, period: int = 14) -> list:
    """Calculate RSI for entire series"""
    if len(prices) < period + 1:
        return [50] * len(prices)
    
    rsi_values = [50] * period
    
    gains = []
    losses = []
    for i in range(1, period + 1):
        diff = prices[i] - prices[i - 1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    for i in range(period + 1, len(prices)):
        diff = prices[i] - prices[i - 1]
        gain = max(diff, 0)
        loss = abs(min(diff, 0))
        
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        
        rsi_values.append(rsi)
    
    return rsi_values


def calculate_macd_series(prices: list) -> list:
    """Calculate MACD for entire series"""
    if len(prices) < 26:
        return [{"macd": 0, "signal": 0, "histogram": 0}] * len(prices)
    
    ema12 = calculate_ema_series(prices, 12)
    ema26 = calculate_ema_series(prices, 26)
    macd_line = [ema12[i] - ema26[i] for i in range(len(prices))]
    signal_line = calculate_ema_series(macd_line, 9)
    histogram = [macd_line[i] - signal_line[i] for i in range(len(prices))]
    
    result = []
    for i in range(len(prices)):
        result.append({
            "macd": macd_line[i],
            "signal": signal_line[i],
            "histogram": histogram[i]
        })
    
    return result


async def get_indicators_from_candles(candles: list) -> dict:
    """Extract indicators from candle data (last candle)"""
    if not candles:
        return None
    
    latest = candles[-1]
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    
    from utils.indicators import (
        calculate_stochastic, calculate_cci, calculate_atr,
        calculate_bbands, calculate_adx, calculate_williams_r, calculate_roc
    )
    
    stoch_k, stoch_d = calculate_stochastic(highs, lows, closes)
    cci = calculate_cci(highs, lows, closes)
    atr = calculate_atr(highs, lows, closes)
    bb_upper, bb_middle, bb_lower = calculate_bbands(closes)
    adx, plus_di, minus_di = calculate_adx(highs, lows, closes)
    williams_r = calculate_williams_r(highs, lows, closes)
    roc = calculate_roc(closes)
    
    return {
        "symbol": latest.get("symbol", ""),
        "interval": latest.get("interval", ""),
        "price": latest["close"],
        "ema20": latest.get("ema", 0),
        "ema50": latest.get("ema50", 0),
        "ema200": latest.get("ema200", 0),
        "rsi": latest.get("rsi", 50),
        "macd": latest.get("macd", 0),
        "macdSignal": latest.get("macdSignal", 0),
        "macdHist": latest.get("macdHist", 0),
        "stochK": stoch_k,
        "stochD": stoch_d,
        "cci": cci,
        "atr": atr,
        "bbUpper": bb_upper,
        "bbMiddle": bb_middle,
        "bbLower": bb_lower,
        "adx": adx,
        "plusDI": plus_di,
        "minusDI": minus_di,
        "williamsR": williams_r,
        "roc": roc,
        "mfi": None,
        "vwap": None,
        "obv": None,
    }


# ============================================================================
# PROFESSIONAL SETUP ANALYZER
# ============================================================================

class SetupAnalyzer:
    """
    Professional-grade trade setup analyzer
    
    Uses institutional methodology:
    - Unbiased bullish/bearish scoring
    - Multi-timeframe trend context
    - Proper risk assessment
    - Conservative confidence thresholds
    """
    
    def __init__(self):
        self.levels_engine = LevelsEngine()
        
    async def analyze_setup(self, symbol: str, timeframe: str) -> dict:
        """Main analysis function with professional-grade methodology"""
        try:
            print(f"🔄 Fetching data for {symbol} on {timeframe}...")
            
            # Fetch data
            candles = await fetch_candles_from_coingecko(symbol, timeframe, limit=200)
            if not candles or len(candles) < 30:
                print(f"❌ Insufficient candles for {symbol} {timeframe}")
                return None
            
            indicators = await get_indicators_from_candles(candles)
            if not indicators:
                print(f"❌ Failed to calculate indicators for {symbol}")
                return None
            
            # Get S/R levels
            try:
                sr_data = await self.levels_engine.calculate_levels(
                    symbol=symbol, timeframe=timeframe, max_levels=5
                )
                support_levels = sr_data.get('support_levels', [])
                resistance_levels = sr_data.get('resistance_levels', [])
                current_price = sr_data.get('current_price')
            except Exception as e:
                print(f"⚠️ S/R levels failed for {symbol}: {e}")
                support_levels = []
                resistance_levels = []
                current_price = indicators['price']
            
            # Detect patterns
            patterns = (
                detect_divergences(candles) +
                detect_engulfing_patterns(candles) +
                detect_trendline_breaks(candles) +
                detect_golden_death_crosses(candles) +
                detect_double_top_bottom(candles)
            )
            
            print(f"✅ Detected {len(patterns)} chart patterns")
            
            # PROFESSIONAL ANALYSIS
            score_data = self._calculate_professional_score(
                candles, indicators, support_levels, resistance_levels, patterns
            )
            
            direction = self._determine_direction_v2(indicators, score_data, candles)
            
            trade_levels = self._calculate_professional_trade_levels(
                candles, indicators, support_levels, resistance_levels, direction
            )
            
            wait_conditions = self._generate_professional_conditions(
                candles, indicators, direction, timeframe, score_data
            )
            
            # Confidence assessment
            confidence = self._calculate_confidence(score_data, indicators, candles)
            
            print(f"✅ Analysis complete: {symbol} - Score: {score_data['score']}/100, Confidence: {confidence}%")
            
            return {
                'score': score_data['score'],
                'quality': self._get_quality_rating(score_data['score']),
                'confidence': confidence,  # NEW: Trading confidence
                'direction': direction,
                'current_price': current_price,
                'bullish_signals': score_data['bullish_signals'],
                'bearish_signals': score_data['bearish_signals'],  # NEW
                'risk_factors': score_data['risk_factors'],
                'entry_zone': trade_levels['entry_zone'],
                'stop_loss': trade_levels['stop_loss'],
                'take_profit_1': trade_levels['tp1'],
                'take_profit_2': trade_levels['tp2'],
                'risk_reward': trade_levels['rr_ratio'],
                'wait_for': wait_conditions,
                'indicators': indicators,
                'support_levels': support_levels,
                'resistance_levels': resistance_levels,
                'patterns': patterns[:5],
                'trend_context': score_data['trend_context']  # NEW
            }
            
        except Exception as e:
            print(f"❌ Setup analyzer error for {symbol} {timeframe}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _safe_get(self, indicators: dict, key: str, default=0):
        """Safely get indicator value"""
        value = indicators.get(key, default)
        return value if value is not None else default
    
    def _calculate_professional_score(self, candles, indicators, support_levels, resistance_levels, patterns) -> dict:
        """
        PROFESSIONAL SCORING SYSTEM
        - Unbiased (works for both bullish and bearish)
        - Trend context aware
        - Proper risk assessment
        """
        bullish_score = 0
        bearish_score = 0
        bullish_signals = []
        bearish_signals = []
        risk_factors = []
        
        # Extract all indicators
        current_price = self._safe_get(indicators, 'price')
        ema20 = self._safe_get(indicators, 'ema20')
        ema50 = self._safe_get(indicators, 'ema50')
        ema200 = self._safe_get(indicators, 'ema200')
        rsi = self._safe_get(indicators, 'rsi', 50)
        macd_hist = self._safe_get(indicators, 'macdHist')
        adx = self._safe_get(indicators, 'adx')
        plus_di = self._safe_get(indicators, 'plusDI')
        minus_di = self._safe_get(indicators, 'minusDI')
        stoch_k = self._safe_get(indicators, 'stochK', 50)
        stoch_d = self._safe_get(indicators, 'stochD', 50)
        bb_upper = self._safe_get(indicators, 'bbUpper')
        bb_lower = self._safe_get(indicators, 'bbLower')
        bb_middle = self._safe_get(indicators, 'bbMiddle')
        cci = self._safe_get(indicators, 'cci')
        williams_r = self._safe_get(indicators, 'williamsR', -50)
        roc = self._safe_get(indicators, 'roc')
        
        # ═══════════════════════════════════════════════════════════════
        # 1. TREND ANALYSIS (Multi-timeframe context)
        # ═══════════════════════════════════════════════════════════════
        
        trend_context = self._analyze_trend_context(current_price, ema20, ema50, ema200)
        
        if trend_context == "STRONG_UPTREND":
            bullish_score += 20
            bullish_signals.append("Strong uptrend (all EMAs aligned)")
        elif trend_context == "UPTREND":
            bullish_score += 15
            bullish_signals.append("Uptrend (price above key EMAs)")
        elif trend_context == "STRONG_DOWNTREND":
            bearish_score += 20
            bearish_signals.append("Strong downtrend (all EMAs aligned)")
        elif trend_context == "DOWNTREND":
            bearish_score += 15
            bearish_signals.append("Downtrend (price below key EMAs)")
        else:
            risk_factors.append("No clear trend - range-bound")
        
        # Trend strength (ADX)
        if adx:
            if adx > 25:
                if plus_di and minus_di:
                    if plus_di > minus_di:
                        bullish_score += 10
                        bullish_signals.append(f"Strong bullish trend (ADX: {adx:.0f})")
                    else:
                        bearish_score += 10
                        bearish_signals.append(f"Strong bearish trend (ADX: {adx:.0f})")
            elif adx < 20:
                risk_factors.append(f"Weak trend (ADX: {adx:.0f}) - avoid trading")
        
        # ═══════════════════════════════════════════════════════════════
        # 2. MOMENTUM ANALYSIS (Unbiased)
        # ═══════════════════════════════════════════════════════════════
        
        # RSI - Unbiased approach
        if rsi:
            if 55 < rsi < 70:
                bullish_score += 12
                bullish_signals.append(f"Bullish momentum (RSI: {rsi:.0f})")
            elif 40 < rsi <= 55:
                bullish_score += 5
                bullish_signals.append(f"Neutral-bullish (RSI: {rsi:.0f})")
            elif 30 < rsi < 45:
                bearish_score += 5
                bearish_signals.append(f"Neutral-bearish (RSI: {rsi:.0f})")
            elif rsi <= 30:
                bearish_score += 12
                bearish_signals.append(f"Bearish momentum (RSI: {rsi:.0f})")
                bullish_signals.append(f"Oversold - potential bounce")
            elif rsi >= 70:
                bullish_score += 12
                bullish_signals.append(f"Strong bullish (RSI: {rsi:.0f})")
                risk_factors.append(f"Overbought - risk of pullback")
        
        # MACD - Unbiased
        if macd_hist is not None:
            if macd_hist > 0:
                bullish_score += 10
                bullish_signals.append("MACD bullish (positive histogram)")
            elif macd_hist < 0:
                bearish_score += 10
                bearish_signals.append("MACD bearish (negative histogram)")
        
        # Stochastic - Unbiased
        if stoch_k and stoch_d:
            if stoch_k > stoch_d:
                if stoch_k < 80:
                    bullish_score += 5
                    bullish_signals.append("Stochastic bullish crossover")
                else:
                    risk_factors.append(f"Stochastic overbought ({stoch_k:.0f})")
            elif stoch_k < stoch_d:
                if stoch_k > 20:
                    bearish_score += 5
                    bearish_signals.append("Stochastic bearish crossover")
                else:
                    bullish_signals.append(f"Stochastic oversold - bounce potential")
        
        # CCI - Unbiased
        if cci is not None:
            if cci > 100:
                bullish_score += 3
                bullish_signals.append(f"CCI bullish ({cci:.0f})")
                if cci > 200:
                    risk_factors.append("CCI extremely overbought")
            elif cci < -100:
                bearish_score += 3
                bearish_signals.append(f"CCI bearish ({cci:.0f})")
                if cci < -200:
                    bullish_signals.append("CCI oversold - bounce potential")
        
        # ROC - Unbiased
        if roc is not None:
            if roc > 5:
                bullish_score += 5
                bullish_signals.append(f"Strong upward momentum (ROC: {roc:.1f}%)")
            elif roc < -5:
                bearish_score += 5
                bearish_signals.append(f"Strong downward momentum (ROC: {roc:.1f}%)")
        
        # ═══════════════════════════════════════════════════════════════
        # 3. SUPPORT/RESISTANCE ANALYSIS
        # ═══════════════════════════════════════════════════════════════
        
        if support_levels:
            valid_supports = [lvl for lvl in support_levels if lvl['price'] < current_price]
            if valid_supports:
                nearest_support = max(valid_supports, key=lambda x: x['price'])
                support_distance = ((current_price - nearest_support['price']) / current_price) * 100
                
                if support_distance < 2:
                    bullish_score += 12
                    bullish_signals.append(
                        f"At {nearest_support['strength'].lower()} support "
                        f"(${nearest_support['price']:.2f}, -{support_distance:.1f}%)"
                    )
                elif support_distance < 5:
                    bullish_score += 6
                    bullish_signals.append(f"Near support (-{support_distance:.1f}%)")
        
        if resistance_levels:
            valid_resistances = [lvl for lvl in resistance_levels if lvl['price'] > current_price]
            if valid_resistances:
                nearest_resistance = min(valid_resistances, key=lambda x: x['price'])
                resistance_distance = ((nearest_resistance['price'] - current_price) / current_price) * 100
                
                if resistance_distance < 2:
                    bearish_score += 12
                    bearish_signals.append(
                        f"At {nearest_resistance['strength'].lower()} resistance "
                        f"(${nearest_resistance['price']:.2f}, +{resistance_distance:.1f}%)"
                    )
                    risk_factors.append("Price at resistance - rejection risk")
                elif resistance_distance < 5:
                    risk_factors.append(f"Approaching resistance (+{resistance_distance:.1f}%)")
                elif resistance_distance > 5:
                    bullish_score += 6
                    bullish_signals.append(f"Room to resistance (+{resistance_distance:.1f}%)")
        
        # ═══════════════════════════════════════════════════════════════
        # 4. VOLATILITY ANALYSIS
        # ═══════════════════════════════════════════════════════════════
        
        if bb_upper and bb_lower and bb_middle:
            bb_width = ((bb_upper - bb_lower) / bb_middle) * 100
            
            if current_price > bb_upper:
                risk_factors.append("Price above upper BB - high risk")
                bearish_score += 3
            elif current_price < bb_lower:
                bullish_signals.append("Price below lower BB - bounce potential")
                bullish_score += 5
            elif current_price > bb_middle:
                bullish_score += 3
                bullish_signals.append("Price in upper BB half")
            else:
                bearish_score += 3
                bearish_signals.append("Price in lower BB half")
        
        # ═══════════════════════════════════════════════════════════════
        # 5. CHART PATTERNS
        # ═══════════════════════════════════════════════════════════════
        
        if patterns:
            pattern_score = min(len(patterns) * 3, 10)
            bullish_score += pattern_score
            for pattern in patterns[:2]:
                bullish_signals.append(f"Pattern: {pattern}")
        
        # ═══════════════════════════════════════════════════════════════
        # CALCULATE FINAL SCORE (Unbiased)
        # ═══════════════════════════════════════════════════════════════
        
        # Net score (bullish - bearish)
        net_score = bullish_score - bearish_score
        
        # Normalize to 0-100 scale
        if net_score > 0:
            final_score = 50 + min(net_score, 50)  # 50-100 range for bullish
        else:
            final_score = 50 + max(net_score, -50)  # 0-50 range for bearish
        
        final_score = int(max(0, min(100, final_score)))
        
        return {
            'score': final_score,
            'bullish_score': bullish_score,
            'bearish_score': bearish_score,
            'bullish_signals': bullish_signals,
            'bearish_signals': bearish_signals,
            'risk_factors': risk_factors,
            'trend_context': trend_context
        }
    
    def _analyze_trend_context(self, price, ema20, ema50, ema200) -> str:
        """Analyze multi-timeframe trend context"""
        if ema20 and ema50 and ema200:
            if price > ema20 > ema50 > ema200:
                return "STRONG_UPTREND"
            elif price > ema20 and price > ema50:
                return "UPTREND"
            elif price < ema20 < ema50 < ema200:
                return "STRONG_DOWNTREND"
            elif price < ema20 and price < ema50:
                return "DOWNTREND"
        
        return "RANGING"
    
    def _determine_direction_v2(self, indicators, score_data, candles) -> str:
        """
        Professional direction determination
        - Considers net score
        - Validates with trend context
        - Requires strong confirmation
        """
        score = score_data['score']
        trend_context = score_data['trend_context']
        
        # Strong bullish: score > 65 AND uptrend
        if score > 65 and trend_context in ["STRONG_UPTREND", "UPTREND"]:
            return "BULLISH"
        
        # Strong bearish: score < 35 AND downtrend
        elif score < 35 and trend_context in ["STRONG_DOWNTREND", "DOWNTREND"]:
            return "BEARISH"
        
        # Moderate bullish: score 55-65
        elif 55 <= score <= 65:
            return "BULLISH"
        
        # Moderate bearish: score 35-45
        elif 35 <= score <= 45:
            return "BEARISH"
        
        # Mixed signals - default to neutral
        else:
            return "NEUTRAL"
    
    def _calculate_professional_trade_levels(self, candles, indicators, support_levels, resistance_levels, direction) -> dict:
        """
        Professional trade level calculation
        - Uses ATR for stop placement
        - Respects key S/R levels
        - Ensures minimum 2:1 R:R
        """
        current_price = self._safe_get(indicators, 'price')
        atr = self._safe_get(indicators, 'atr', current_price * 0.02)
        
        # Use 1.5x ATR minimum for stops (professional standard)
        min_stop_distance = atr * 1.5
        
        valid_supports = [lvl for lvl in support_levels if lvl['price'] < current_price] if support_levels else []
        valid_resistances = [lvl for lvl in resistance_levels if lvl['price'] > current_price] if resistance_levels else []
        
        nearest_support = max(valid_supports, key=lambda x: x['price']) if valid_supports else None
        nearest_resistance = min(valid_resistances, key=lambda x: x['price']) if valid_resistances else None
        
        if direction == "BULLISH":
            # Entry zone (tight)
            entry_low = current_price * 0.998
            entry_high = current_price * 1.002
            
            # Stop loss: below support OR 2x ATR
            if nearest_support:
                stop_loss = min(
                    nearest_support['price_lower'] * 0.995,
                    current_price - (2 * atr)
                )
            else:
                stop_loss = current_price - (2 * atr)
            
            # Ensure minimum stop distance
            if abs(current_price - stop_loss) < min_stop_distance:
                stop_loss = current_price - min_stop_distance
            
            # TP1: Before resistance OR 2:1 R:R minimum
            risk = abs(current_price - stop_loss)
            
            if nearest_resistance:
                tp1 = min(
                    nearest_resistance['price_lower'] * 0.995,
                    current_price + (risk * 2)
                )
            else:
                tp1 = current_price + (risk * 2)
            
            # TP2: Next resistance OR 3:1 R:R
            tp2 = current_price + (risk * 3)
            
        elif direction == "BEARISH":
            entry_low = current_price * 0.998
            entry_high = current_price * 1.002
            
            # Stop loss: above resistance OR 2x ATR
            if nearest_resistance:
                stop_loss = max(
                    nearest_resistance['price_upper'] * 1.005,
                    current_price + (2 * atr)
                )
            else:
                stop_loss = current_price + (2 * atr)
            
            if abs(stop_loss - current_price) < min_stop_distance:
                stop_loss = current_price + min_stop_distance
            
            risk = abs(stop_loss - current_price)
            
            if nearest_support:
                tp1 = max(
                    nearest_support['price_upper'] * 1.005,
                    current_price - (risk * 2)
                )
            else:
                tp1 = current_price - (risk * 2)
            
            tp2 = current_price - (risk * 3)
            
        else:  # NEUTRAL
            entry_low = current_price * 0.995
            entry_high = current_price * 1.005
            stop_loss = current_price - (2 * atr)
            tp1 = current_price + (2 * atr)
            tp2 = current_price + (4 * atr)
        
        risk = abs(current_price - stop_loss)
        reward = abs(tp1 - current_price)
        rr_ratio = reward / risk if risk > 0 else 0
        
        return {
            'entry_zone': (entry_low, entry_high),
            'stop_loss': stop_loss,
            'tp1': tp1,
            'tp2': tp2,
            'rr_ratio': round(rr_ratio, 2)
        }
    
    def _generate_professional_conditions(self, candles, indicators, direction, timeframe, score_data) -> list:
        """Generate professional wait conditions"""
        conditions = []
        current_price = self._safe_get(indicators, 'price')
        rsi = self._safe_get(indicators, 'rsi')
        adx = self._safe_get(indicators, 'adx')
        
        # Only provide conditions if score is reasonable
        if score_data['score'] < 60:
            conditions.append("⚠️ Setup quality too low - wait for better opportunity")
            return conditions
        
        if direction == "BULLISH":
            conditions.append(f"Wait for {timeframe} close above ${current_price * 1.005:,.2f}")
            
            if rsi and rsi > 70:
                conditions.append("Wait for RSI cooldown to 60-65 range")
            
            if adx and adx < 20:
                conditions.append("Wait for trend strength (ADX > 20)")
            
            conditions.append("Confirm with volume increase on breakout")
            
        elif direction == "BEARISH":
            conditions.append(f"Wait for {timeframe} close below ${current_price * 0.995:,.2f}")
            
            if rsi and rsi < 30:
                conditions.append("Wait for RSI relief rally to 35-40")
            
            if adx and adx < 20:
                conditions.append("Wait for trend strength (ADX > 20)")
            
            conditions.append("Confirm with volume on breakdown")
            
        else:
            conditions.append("⚠️ No clear direction - avoid trading")
            conditions.append("Wait for trend confirmation")
        
        return conditions
    
    def _calculate_confidence(self, score_data, indicators, candles) -> int:
        """
        Calculate trading confidence (0-100%)
        Based on:
        - Signal alignment
        - Trend clarity
        - Setup quality
        """
        confidence = 50  # Base confidence
        
        bullish_count = len(score_data['bullish_signals'])
        bearish_count = len(score_data['bearish_signals'])
        risk_count = len(score_data['risk_factors'])
        
        # Signal alignment
        if bullish_count > bearish_count * 2:
            confidence += 20
        elif bearish_count > bullish_count * 2:
            confidence += 20
        elif abs(bullish_count - bearish_count) <= 2:
            confidence -= 20  # Mixed signals = lower confidence
        
        # Trend context
        if score_data['trend_context'] in ["STRONG_UPTREND", "STRONG_DOWNTREND"]:
            confidence += 15
        elif score_data['trend_context'] == "RANGING":
            confidence -= 15
        
        # ADX (trend strength)
        adx = self._safe_get(indicators, 'adx')
        if adx:
            if adx > 30:
                confidence += 10
            elif adx < 20:
                confidence -= 15
        
        # Risk factors
        if risk_count > 3:
            confidence -= 15
        
        # Score quality
        score = score_data['score']
        if score > 75 or score < 25:
            confidence += 10  # Extreme scores = high confidence
        elif 45 <= score <= 55:
            confidence -= 15  # Neutral = low confidence
        
        return max(0, min(100, confidence))
    
    def _get_quality_rating(self, score: int) -> str:
        """Convert score to quality rating"""
        if score >= 75:
            return "EXCELLENT"
        elif score >= 65:
            return "GOOD"
        elif score >= 55:
            return "FAIR"
        elif score >= 45:
            return "NEUTRAL"
        elif score >= 35:
            return "FAIR (Bearish)"
        elif score >= 25:
            return "GOOD (Bearish)"
        else:
            return "EXCELLENT (Bearish)"