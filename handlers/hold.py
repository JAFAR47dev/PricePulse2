"""
/hold Command - REALISTIC Capital Preservation Analysis (Pro Only)

Uses conservative, multi-confirmation logic to avoid false signals.
Requires MULTIPLE confirmations before recommending holds in downtrends.
Defaults to caution rather than optimism.
"""

import os
import json
import asyncio
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timedelta
import requests
from telegram import Update
from telegram.ext import ContextTypes
from tasks.handlers import handle_streak
from models.user_activity import update_last_active
from models.user import get_user_plan
from utils.auth import is_pro_plan

# API Keys
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")

# Load top 100 coins
def load_top_100_coins():
    """Load top 100 coin symbols from JSON"""
    try:
        with open('services/top100_coingecko_ids.json', 'r') as f:
            data = json.load(f)
            return {symbol.upper(): coingecko_id for symbol, coingecko_id in data.items()}
    except Exception as e:
        print(f"Error loading top 100 coins: {e}")
        return {}

TOP_100_COINS = load_top_100_coins()

# Timeframe configurations (ALL PRO ONLY)
TIMEFRAME_CONFIG = {
    "30d": {"days": 30, "label": "30-DAY", "candles_needed": 180},
    "60d": {"days": 60, "label": "60-DAY", "candles_needed": 240},
    "90d": {"days": 90, "label": "90-DAY", "candles_needed": 270}
}


# ====== DATA FETCHING ======

async def fetch_coin_price_data(coingecko_id: str, days: int = 180) -> Optional[Dict]:
    """Fetch historical price data from CoinGecko"""
    try:
        headers = {}
        if COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = COINGECKO_API_KEY
        
        url = f"https://api.coingecko.com/api/v3/coins/{coingecko_id}/market_chart"
        params = {"vs_currency": "usd", "days": days, "interval": "daily"}
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    
    except Exception as e:
        print(f"Error fetching price data for {coingecko_id}: {e}")
        return None


async def fetch_coin_details(coingecko_id: str) -> Optional[Dict]:
    """Fetch detailed coin information"""
    try:
        headers = {}
        if COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = COINGECKO_API_KEY
        
        url = f"https://api.coingecko.com/api/v3/coins/{coingecko_id}"
        params = {
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "false",
            "developer_data": "false"
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    
    except Exception as e:
        print(f"Error fetching coin details: {e}")
        return None


async def fetch_btc_data(days: int = 180) -> Optional[List[float]]:
    """Fetch BTC price data for correlation analysis"""
    try:
        btc_data = await fetch_coin_price_data("bitcoin", days)
        if btc_data:
            return [p[1] for p in btc_data.get("prices", [])]
        return None
    except:
        return None


async def fetch_fear_greed_index() -> Optional[Tuple[int, str]]:
    """Fetch Fear & Greed Index"""
    try:
        response = requests.get("https://api.alternative.me/fng/", timeout=5)
        response.raise_for_status()
        data = response.json().get("data", [{}])[0]
        return int(data.get("value", 50)), data.get("value_classification", "Neutral")
    except:
        return None


# ====== ADVANCED TECHNICAL INDICATORS ======

def calculate_sma(prices: List[float], period: int) -> Optional[float]:
    """Simple Moving Average"""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def calculate_ema(prices: List[float], period: int) -> Optional[float]:
    """Exponential Moving Average"""
    if len(prices) < period:
        return None
    
    k = 2 / (period + 1)
    ema = prices[0]
    
    for price in prices[1:]:
        ema = price * k + ema * (1 - k)
    
    return ema


def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """RSI with proper smoothing"""
    if len(prices) < period + 1:
        return None
    
    gains = []
    losses = []
    
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    
    if len(gains) < period:
        return None
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    # Smooth remaining values
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def detect_rsi_divergence(prices: List[float], rsi_values: List[float], lookback: int = 14) -> Tuple[bool, bool]:
    """
    Detect bullish/bearish divergence between price and RSI
    Returns: (bullish_divergence, bearish_divergence)
    """
    if len(prices) < lookback or len(rsi_values) < lookback:
        return False, False
    
    recent_prices = prices[-lookback:]
    recent_rsi = rsi_values[-lookback:]
    
    # Bullish divergence: price making lower lows, RSI making higher lows
    price_trend_down = recent_prices[-1] < recent_prices[0]
    rsi_trend_up = recent_rsi[-1] > recent_rsi[0]
    bullish_div = price_trend_down and rsi_trend_up
    
    # Bearish divergence: price making higher highs, RSI making lower highs
    price_trend_up = recent_prices[-1] > recent_prices[0]
    rsi_trend_down = recent_rsi[-1] < recent_rsi[0]
    bearish_div = price_trend_up and rsi_trend_down
    
    return bullish_div, bearish_div


def calculate_volume_profile(volumes: List[float], lookback: int = 30) -> str:
    """Analyze volume patterns"""
    if len(volumes) < lookback * 2:
        return "Unknown"
    
    recent_vol = sum(volumes[-lookback:]) / lookback
    previous_vol = sum(volumes[-lookback*2:-lookback]) / lookback
    
    if recent_vol > previous_vol * 1.5:
        return "Surging"
    elif recent_vol > previous_vol * 1.2:
        return "Increasing"
    elif recent_vol < previous_vol * 0.7:
        return "Collapsing"
    elif recent_vol < previous_vol * 0.85:
        return "Decreasing"
    else:
        return "Stable"


def detect_volume_capitulation(prices: List[float], volumes: List[float]) -> bool:
    """
    Detect volume capitulation: price down + volume spike
    True capitulation = potential bottom
    """
    if len(prices) < 30 or len(volumes) < 30:
        return False
    
    # Last 7 days
    recent_price_change = (prices[-1] - prices[-7]) / prices[-7]
    recent_vol = sum(volumes[-7:]) / 7
    previous_vol = sum(volumes[-14:-7]) / 7
    
    # Capitulation: price down >5% AND volume spike >40%
    price_declining = recent_price_change < -0.05
    volume_spike = recent_vol > previous_vol * 1.4
    
    return price_declining and volume_spike


def calculate_correlation(prices1: List[float], prices2: List[float]) -> float:
    """Calculate correlation coefficient between two price series"""
    if len(prices1) != len(prices2) or len(prices1) < 30:
        return 0.0
    
    # Use last 90 days max
    n = min(90, len(prices1))
    prices1 = prices1[-n:]
    prices2 = prices2[-n:]
    
    mean1 = sum(prices1) / n
    mean2 = sum(prices2) / n
    
    numerator = sum((prices1[i] - mean1) * (prices2[i] - mean2) for i in range(n))
    denominator1 = sum((prices1[i] - mean1) ** 2 for i in range(n)) ** 0.5
    denominator2 = sum((prices2[i] - mean2) ** 2 for i in range(n)) ** 0.5
    
    if denominator1 == 0 or denominator2 == 0:
        return 0.0
    
    return numerator / (denominator1 * denominator2)


def detect_market_regime(prices: List[float]) -> str:
    """
    Detect overall market regime using trend analysis
    Returns: Bull, Bear, or Sideways
    """
    if len(prices) < 100:
        return "Unknown"
    
    sma_20 = calculate_sma(prices, 20)
    sma_50 = calculate_sma(prices, 50)
    sma_200 = calculate_sma(prices, 200) if len(prices) >= 200 else None
    
    if not sma_20 or not sma_50:
        return "Unknown"
    
    # Bull: 20 > 50 > 200 (golden cross)
    if sma_200:
        if sma_20 > sma_50 > sma_200:
            return "Bull"
        elif sma_20 < sma_50 < sma_200:
            return "Bear"
    else:
        if sma_20 > sma_50 * 1.02:
            return "Bull"
        elif sma_20 < sma_50 * 0.98:
            return "Bear"
    
    return "Sideways"


def calculate_volatility_percentile(prices: List[float], period: int = 30) -> float:
    """Calculate current volatility vs historical"""
    if len(prices) < period * 3:
        return 50.0
    
    def volatility(price_list):
        if len(price_list) < 2:
            return 0
        mean = sum(price_list) / len(price_list)
        variance = sum((p - mean) ** 2 for p in price_list) / len(price_list)
        return (variance ** 0.5) / mean * 100
    
    current_vol = volatility(prices[-period:])
    
    # Calculate historical volatility percentiles
    historical_vols = []
    for i in range(period, len(prices) - period, period // 2):
        historical_vols.append(volatility(prices[i:i+period]))
    
    if not historical_vols:
        return 50.0
    
    # Percentile: what % of historical periods had lower volatility
    lower_count = sum(1 for v in historical_vols if v < current_vol)
    percentile = (lower_count / len(historical_vols)) * 100
    
    return percentile


# ====== REALISTIC DECISION ENGINE ======

def analyze_hold_decision(
    symbol: str,
    current_price: float,
    prices: List[float],
    volumes: List[float],
    btc_prices: Optional[List[float]],
    market_data: Dict,
    market_cap_rank: int,
    fear_greed: Optional[Tuple[int, str]],
    timeframe_days: int
) -> Dict:
    """
    CONSERVATIVE decision engine with multi-confirmation requirements
    """
    
    # Extract core data
    ath = market_data.get("ath", {}).get("usd", 0)
    
    # Calculate ALL indicators
    sma_20 = calculate_sma(prices, 20)
    sma_50 = calculate_sma(prices, 50)
    sma_200 = calculate_sma(prices, 200) if len(prices) >= 200 else None
    ema_12 = calculate_ema(prices, 12)
    ema_26 = calculate_ema(prices, 26)
    
    rsi = calculate_rsi(prices)
    
    # Calculate RSI history for divergence detection
    rsi_history = []
    for i in range(14, len(prices)):
        rsi_val = calculate_rsi(prices[:i+1])
        if rsi_val:
            rsi_history.append(rsi_val)
    
    bullish_div, bearish_div = detect_rsi_divergence(prices, rsi_history) if len(rsi_history) > 14 else (False, False)
    
    # Market regime
    regime = detect_market_regime(prices)
    
    # Volume analysis
    volume_profile = calculate_volume_profile(volumes)
    capitulation = detect_volume_capitulation(prices, volumes)
    
    # Volatility
    vol_percentile = calculate_volatility_percentile(prices)
    
    # BTC correlation (critical for altcoins)
    btc_correlation = 0.0
    if btc_prices and len(btc_prices) == len(prices):
        btc_correlation = calculate_correlation(prices, btc_prices)
    
    # Drawdowns
    drawdown_ath = ((current_price - ath) / ath) * 100 if ath > 0 else 0
    local_high_30d = max(prices[-30:]) if len(prices) >= 30 else current_price
    drawdown_local = ((current_price - local_high_30d) / local_high_30d) * 100
    
    # Price vs MAs
    price_vs_50 = ((current_price - sma_50) / sma_50) * 100 if sma_50 else 0
    price_vs_200 = ((current_price - sma_200) / sma_200) * 100 if sma_200 else 0
    
    # ====== CONSERVATIVE SCORING SYSTEM ======
    # Default = EXIT, must prove reasons to HOLD
    
    score = -20  # Start with bearish bias
    signals = {"bullish": [], "bearish": [], "neutral": []}
    confirmations_required = 3  # Need 3+ bullish confirmations to recommend HOLD
    confirmations_count = 0
    
    # === 1. MARKET REGIME (35 points) - MOST IMPORTANT ===
    if regime == "Bull":
        score += 35
        confirmations_count += 1
        signals["bullish"].append(f"Confirmed bull market (MA alignment)")
    elif regime == "Bear":
        score -= 35
        signals["bearish"].append(f"Confirmed bear market - high risk")
    else:
        score -= 10
        signals["neutral"].append("Sideways market - uncertain")
    
    # === 2. TREND STRUCTURE (25 points) ===
    if sma_50 and sma_200:
        # Golden cross
        if sma_50 > sma_200:
            score += 15
            confirmations_count += 1
            signals["bullish"].append("Golden cross (50 > 200 MA)")
        # Death cross
        elif sma_50 < sma_200 * 0.98:
            score -= 15
            signals["bearish"].append("Death cross (50 < 200 MA)")
    
    # Price vs key MAs
    if price_vs_50 > 5:
        score += 10
        confirmations_count += 1
        signals["bullish"].append(f"Strong above 50 MA (+{price_vs_50:.1f}%)")
    elif price_vs_50 < -5:
        score -= 10
        signals["bearish"].append(f"Weak below 50 MA ({price_vs_50:.1f}%)")
    
    # === 3. MOMENTUM WITH DIVERGENCE (20 points) ===
    if rsi:
        # CRITICAL FIX: Oversold alone is NOT bullish
        if rsi < 30:
            # Only bullish if BULLISH DIVERGENCE confirmed
            if bullish_div:
                score += 20
                confirmations_count += 1
                signals["bullish"].append(f"Bullish divergence (RSI={rsi:.0f})")
            else:
                score -= 15
                signals["bearish"].append(f"RSI oversold without divergence ({rsi:.0f}) - still falling")
        
        elif rsi > 70:
            if bearish_div:
                score -= 20
                signals["bearish"].append(f"Bearish divergence (RSI={rsi:.0f})")
            else:
                score -= 10
                signals["bearish"].append(f"RSI overbought ({rsi:.0f})")
        
        # Healthy momentum
        elif 45 < rsi < 65:
            score += 5
            signals["bullish"].append("Healthy momentum (RSI neutral)")
    
    # === 4. VOLUME CONFIRMATION (15 points) ===
    if capitulation:
        score += 15
        confirmations_count += 1
        signals["bullish"].append("Volume capitulation detected (potential bottom)")
    elif volume_profile == "Surging":
        if regime == "Bull":
            score += 10
            confirmations_count += 1
            signals["bullish"].append("Volume surge confirms uptrend")
        else:
            score -= 10
            signals["bearish"].append("Volume surge in downtrend (distribution)")
    elif volume_profile == "Collapsing":
        if regime == "Bear":
            score += 5
            signals["bullish"].append("Weak selling volume (exhaustion)")
        else:
            score -= 5
            signals["neutral"].append("Low volume - lacks conviction")
    
    # === 5. VOLATILITY RISK (10 points) ===
    if vol_percentile > 90:
        score -= 10
        signals["bearish"].append(f"Extreme volatility (top {100-vol_percentile:.0f}% of range)")
    elif vol_percentile > 75:
        score -= 5
        signals["bearish"].append("Elevated volatility")
    elif vol_percentile < 25:
        score += 5
        signals["bullish"].append("Low volatility environment")
    
    # === 6. BTC CORRELATION (10 points) - Critical for altcoins ===
    if symbol != "BTC" and btc_correlation != 0:
        if btc_correlation > 0.7:
            # High correlation to BTC
            if regime == "Bear":
                score -= 10
                signals["bearish"].append(f"High BTC correlation ({btc_correlation:.2f}) in bear market")
            else:
                signals["neutral"].append(f"High BTC correlation ({btc_correlation:.2f})")
        elif btc_correlation < 0.3:
            # Low correlation = independent strength or weakness
            if regime == "Bull":
                score += 10
                confirmations_count += 1
                signals["bullish"].append("Independent strength (low BTC correlation)")
            signals["neutral"].append(f"Low BTC correlation ({btc_correlation:.2f})")
    
    # === 7. RISK TIER BASED ON RANK (5 points) ===
    # Safe handling of market_cap_rank
    rank = market_cap_rank if market_cap_rank is not None else 999
    
    if rank <= 3:
        score += 5
        signals["bullish"].append("Top 3 asset - lowest risk")
    elif rank <= 10:
        score += 3
        signals["bullish"].append("Top 10 asset - low risk")
    elif rank > 50:
        score -= 5
        signals["bearish"].append(f"Rank #{rank} - elevated risk")
    
    # === 8. FEAR & GREED CONTRARIAN (5 points) ===
    if fear_greed:
        fg_value, fg_class = fear_greed
        if fg_value < 15:
            score += 5
            signals["bullish"].append(f"Extreme fear ({fg_value}) - contrarian signal")
        elif fg_value > 85:
            score -= 5
            signals["bearish"].append(f"Extreme greed ({fg_value}) - frothy")
    
    # === 9. DRAWDOWN ANALYSIS (Reality check) ===
    # Deep drawdown is NOT automatically bullish
    if drawdown_ath < -70 and regime == "Bear":
        score -= 10
        signals["bearish"].append(f"Severe drawdown ({drawdown_ath:.0f}%) in bear market - knife falling")
    elif drawdown_ath < -50 and capitulation:
        score += 10
        confirmations_count += 1
        signals["bullish"].append(f"Deep discount ({drawdown_ath:.0f}%) + capitulation = opportunity")
    elif drawdown_ath > -5:
        score -= 10
        signals["bearish"].append("Near ATH - limited upside, high risk")
    
    # ====== DETERMINE VERDICT (Conservative thresholds) ======
    
    # CRITICAL: For HOLD/ACCUMULATE, require multiple confirmations
    if score >= 50 and confirmations_count >= 4:
        verdict = "🟢 ACCUMULATE"
        confidence = min(90, 60 + (score - 50) * 0.5)
    elif score >= 25 and confirmations_count >= 3:
        verdict = "🟢 HOLD"
        confidence = min(80, 50 + (score - 25) * 1.0)
    elif score >= -10:
        verdict = "🟡 PARTIAL EXIT"
        confidence = 55 + abs(score) * 2
    elif score >= -40:
        verdict = "🔴 EXIT NOW"
        confidence = min(85, 60 + abs(score + 10) * 0.8)
    else:
        verdict = "🔴 EXIT NOW"
        confidence = min(95, 70 + abs(score + 40) * 0.5)
    
    # Calculate realistic probabilities
    if score < -20:
        prob_decline = min(85, 55 + abs(score + 20) * 0.6)
    elif score > 20:
        prob_decline = max(20, 50 - score * 0.5)
    else:
        prob_decline = 50 + abs(score) * 0.5
    
    # Realistic price ranges
    downside_factor = (prob_decline / 100) * 0.25
    upside_factor = ((100 - prob_decline) / 100) * 0.30
    
    expected_low = current_price * (1 - downside_factor)
    expected_high = current_price * (1 + upside_factor)
    
    downside_risk = -downside_factor * 100
    upside_potential = upside_factor * 100
    risk_reward = abs(upside_potential / downside_risk) if downside_risk != 0 else 1.0
    
    # Preservation score (realistic)
    preservation_score = max(1, min(10, (score + 50) / 10))
    
    return {
        "verdict": verdict,
        "confidence": round(confidence, 0),
        "score": score,
        "confirmations": confirmations_count,
        "required_confirmations": confirmations_required,
        "prob_decline": round(prob_decline, 0),
        "expected_low": expected_low,
        "expected_high": expected_high,
        "downside_risk": round(downside_risk, 1),
        "upside_potential": round(upside_potential, 1),
        "risk_reward": round(risk_reward, 2),
        "regime": regime,
        "sma_50": sma_50,
        "sma_200": sma_200,
        "price_vs_50": round(price_vs_50, 1),
        "price_vs_200": round(price_vs_200, 1),
        "rsi": round(rsi, 0) if rsi else None,
        "bullish_divergence": bullish_div,
        "bearish_divergence": bearish_div,
        "volume_profile": volume_profile,
        "capitulation": capitulation,
        "volatility_percentile": round(vol_percentile, 0),
        "btc_correlation": round(btc_correlation, 2),
        "drawdown_ath": round(drawdown_ath, 1),
        "drawdown_local": round(drawdown_local, 1),
        "fear_greed": fear_greed,
        "signals": signals,
        "preservation_score": round(preservation_score, 1)
    }


# ====== MESSAGE FORMATTER ======

def format_hold_message(
    symbol: str,
    coin_name: str,
    current_price: float,
    market_cap_rank: int,
    analysis: Dict,
    timeframe: str
) -> str:
    """Format comprehensive hold analysis message"""
    
    tf_label = TIMEFRAME_CONFIG[timeframe]["label"]
    
    # Safe rank handling
    rank = market_cap_rank if market_cap_rank is not None else 999
    
    verdict = analysis["verdict"]
    if "ACCUMULATE" in verdict:
        action_detail = "Strong buy opportunity"
    elif "HOLD" in verdict and "PARTIAL" not in verdict:
        action_detail = "Maintain position"
    elif "PARTIAL" in verdict:
        action_detail = "Reduce exposure"
    else:
        action_detail = "Exit position"
    
    msg = f"""🛡️ *HOLD ANALYSIS: {symbol}*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 ASSET: {coin_name} ({symbol})
📍 Price: ${current_price:,.2f}
📊 Market Cap Rank: #{rank}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 *VERDICT: {verdict}*

_{action_detail}_

Confidence: `{analysis['confidence']:.0f}%`
Confirmations: `{analysis['confirmations']}/{analysis['required_confirmations']}`

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📉 *{tf_label} OUTLOOK*

Probability of Further Decline: `{analysis['prob_decline']:.0f}%`
Expected Price Range: `${analysis['expected_low']:,.2f}` - `${analysis['expected_high']:,.2f}`

Downside Risk: `{analysis['downside_risk']:+.1f}%`
Upside Potential: `{analysis['upside_potential']:+.1f}%`
Risk/Reward Ratio: `{analysis['risk_reward']:.2f}`

Current Drawdown from ATH: `{analysis['drawdown_ath']:.1f}%`
Current Drawdown from Local High: `{analysis['drawdown_local']:.1f}%`

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 *SIGNAL MATRIX*

*Market Structure:*
"""
    
    # Market regime
    regime_emoji = "✅" if analysis['regime'] == "Bull" else "❌" if analysis['regime'] == "Bear" else "⚠️"
    msg += f"  {regime_emoji} Market Regime: {analysis['regime']}\n"
    
    # Moving averages
    if analysis['sma_50']:
        ma50_emoji = "✅" if analysis['price_vs_50'] > 0 else "❌"
        msg += f"  {ma50_emoji} Price vs 50-day MA: "
        msg += f"Above by {analysis['price_vs_50']:.1f}%\n" if analysis['price_vs_50'] > 0 else f"Below by {abs(analysis['price_vs_50']):.1f}%\n"
    
    if analysis['sma_200']:
        ma200_emoji = "✅" if analysis['price_vs_200'] > 0 else "❌"
        msg += f"  {ma200_emoji} Price vs 200-day MA: "
        msg += f"Above by {analysis['price_vs_200']:.1f}%\n" if analysis['price_vs_200'] > 0 else f"Below by {abs(analysis['price_vs_200']):.1f}%\n"
    
    msg += "\n*Momentum:*\n"
    
    # RSI with divergence
    if analysis['rsi']:
        rsi_val = analysis['rsi']
        if analysis['bullish_divergence']:
            msg += f"  ✅ RSI: {rsi_val:.0f} (Bullish Divergence 📈)\n"
        elif analysis['bearish_divergence']:
            msg += f"  ❌ RSI: {rsi_val:.0f} (Bearish Divergence 📉)\n"
        else:
            rsi_emoji = "❌" if rsi_val > 70 else "⚠️" if rsi_val < 30 else "✅"
            rsi_status = "Overbought" if rsi_val > 70 else "Oversold" if rsi_val < 30 else "Neutral"
            msg += f"  {rsi_emoji} RSI: {rsi_val:.0f} ({rsi_status})\n"
    
    # Volume
    vol_emoji = "✅" if analysis['capitulation'] else "⚠️"
    vol_status = "CAPITULATION ⚠️" if analysis['capitulation'] else analysis['volume_profile']
    msg += f"  {vol_emoji} Volume: {vol_status}\n"
    
    # Volatility
    vol_pct = analysis['volatility_percentile']
    vol_emoji = "❌" if vol_pct > 75 else "⚠️" if vol_pct > 50 else "✅"
    msg += f"  {vol_emoji} Volatility: {vol_pct:.0f}th percentile\n"
    
    # BTC correlation (if not BTC)
    if symbol != "BTC" and analysis['btc_correlation'] != 0:
        corr = analysis['btc_correlation']
        corr_emoji = "⚠️" if corr > 0.7 else "✅"
        msg += f"\n*Market Correlation:*\n"
        msg += f"  {corr_emoji} BTC Correlation: {corr:.2f}\n"
    
    # Fear & Greed
    if analysis['fear_greed']:
        fg_value, fg_class = analysis['fear_greed']
        fg_emoji = "✅" if fg_value < 30 else "❌" if fg_value > 70 else "⚠️"
        msg += f"\n*Sentiment:*\n"
        msg += f"  {fg_emoji} Fear & Greed: {fg_value} ({fg_class})\n"
    
    msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += "💡 *RECOMMENDED ACTION*\n\n"
    
    # Specific recommendations
    if "ACCUMULATE" in verdict:
        msg += f"*Reason:* {', '.join(analysis['signals']['bullish'][:3])}\n\n"
        msg += f"Optimal Buy Zone: `${analysis['expected_low']:,.2f}` - `${current_price:,.2f}`\n"
        msg += f"Position Size: Add 25-40% to holdings\n"
        target1 = current_price * 1.15
        target2 = current_price * 1.30
        target3 = current_price * 1.50
        msg += f"Profit Targets: `${target1:,.2f}` / `${target2:,.2f}` / `${target3:,.2f}`\n"
    
    elif "HOLD" in verdict and "PARTIAL" not in verdict:
        msg += f"*Reason:* {', '.join(analysis['signals']['bullish'][:2])}\n\n"
        msg += f"Patience Required: {TIMEFRAME_CONFIG[timeframe]['days']//3}-{TIMEFRAME_CONFIG[timeframe]['days']//2} days\n"
        watch_level = current_price * 0.90
        msg += f"Watch Level: Break below `${watch_level:,.2f}` = re-evaluate\n"
    
    elif "PARTIAL" in verdict:
        msg += f"*Exit Target:* 40-60% of position\n"
        msg += f"*Reason:* {', '.join(analysis['signals']['bearish'][:2])}\n\n"
        reentry = analysis['expected_low']
        msg += f"Re-Entry Zone: `${reentry * 0.95:,.2f}` - `${reentry * 1.05:,.2f}`\n"
        msg += f"Est. Timeline: {TIMEFRAME_CONFIG[timeframe]['days']//4}-{TIMEFRAME_CONFIG[timeframe]['days']//2} days\n"
        capital_saved = (current_price - reentry) * 0.50
        if capital_saved > 0:
            msg += f"Capital Saved (projected): `${capital_saved:,.2f}` per {symbol}\n"
    
    else:  # EXIT NOW
        msg += f"*Exit Target:* 80-100% of position\n"
        msg += f"*Reason:* {', '.join(analysis['signals']['bearish'][:3])}\n\n"
        reentry = analysis['expected_low']
        msg += f"Re-Entry Zone: `${reentry:,.2f}` - `${reentry * 1.10:,.2f}`\n"
        msg += f"Est. Timeline: {TIMEFRAME_CONFIG[timeframe]['days']//2}-{TIMEFRAME_CONFIG[timeframe]['days']} days\n"
        capital_saved = (current_price - reentry) * 0.85
        if capital_saved > 0:
            msg += f"Capital Saved (projected): `${capital_saved:,.2f}` per {symbol}\n"
    
    msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Key signals
    if analysis['signals']['bullish']:
        msg += "✅ *Bullish Factors:*\n"
        for signal in analysis['signals']['bullish'][:5]:
            msg += f"  • {signal}\n"
    
    if analysis['signals']['bearish']:
        msg += "\n❌ *Bearish Factors:*\n"
        for signal in analysis['signals']['bearish'][:5]:
            msg += f"  • {signal}\n"
    
    if analysis['signals']['neutral']:
        msg += "\n⚠️ *Neutral Factors:*\n"
        for signal in analysis['signals']['neutral'][:3]:
            msg += f"  • {signal}\n"
    
    msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += "⚠️ *INVALIDATION SIGNALS*\n\n"
    msg += "This analysis changes if:\n"
    
    if "EXIT" in verdict or "PARTIAL" in verdict:
        if analysis['sma_50']:
            msg += f"  • Price breaks above `${analysis['sma_50'] * 1.05:,.2f}` with volume\n"
        msg += f"  • Market regime shifts to Bull\n"
        msg += f"  • Volume capitulation confirmed\n"
    else:
        if analysis['sma_50']:
            msg += f"  • Price breaks below `${analysis['sma_50'] * 0.95:,.2f}`\n"
        msg += f"  • Market regime shifts to Bear\n"
        msg += f"  • Bearish divergence appears\n"
    
    msg += f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += f"⏰ Next Update: {TIMEFRAME_CONFIG[timeframe]['days'] // 7} days\n"
    msg += f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    msg += f"💎 *PRESERVATION SCORE: {analysis['preservation_score']}/10*\n\n"
    
    return msg


# ====== COMMAND HANDLER ======

async def hold_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main /hold command handler (PRO ONLY)"""
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/hold")
    await handle_streak(update, context)
    
    # Check Pro status FIRST
    plan = get_user_plan(user_id)
    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 */hold is a Pro-only feature*\n\n"
            "Get conservative, multi-confirmed hold/exit analysis:\n"
            "• Market regime detection\n"
            "• Divergence analysis\n"
            "• Volume capitulation signals\n"
            "• BTC correlation tracking\n"
            "• Multi-timeframe outlook\n\n"
            "💎 /upgrade to unlock",
            parse_mode="Markdown"
        )
        return
    
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "📊 *HOLD Command Usage*\n\n"
            "`/hold <SYMBOL> [timeframe]`\n\n"
            "*Examples:*\n"
            "• `/hold BTC` (30-day)\n"
            "• `/hold ETH 60d`\n"
            "• `/hold SOL 90d`\n\n"
            "*Timeframes:* 30d, 60d, 90d",
            parse_mode="Markdown"
        )
        return
    
    symbol = args[0].upper()
    timeframe = args[1].lower() if len(args) > 1 else "30d"
    
    if symbol not in TOP_100_COINS:
        await update.message.reply_text(
            f"❌ {symbol} not in top 100 coins",
            parse_mode="Markdown"
        )
        return
    
    if timeframe not in TIMEFRAME_CONFIG:
        await update.message.reply_text(
            f"❌ Invalid timeframe. Use: 30d, 60d, or 90d",
            parse_mode="Markdown"
        )
        return
    
    processing_msg = await update.message.reply_text(
        f"⏳ Analyzing {symbol} ({timeframe})...\n"
        "_Running conservative multi-confirmation analysis_",
        parse_mode="Markdown"
    )
    
    try:
        coingecko_id = TOP_100_COINS[symbol]
        days_needed = TIMEFRAME_CONFIG[timeframe]["candles_needed"]
        
        # Fetch all data
        price_data, coin_details, btc_prices, fear_greed = await asyncio.gather(
            fetch_coin_price_data(coingecko_id, days_needed),
            fetch_coin_details(coingecko_id),
            fetch_btc_data(days_needed),
            fetch_fear_greed_index()
        )
        
        if not price_data or not coin_details:
            await processing_msg.edit_text(
                f"⚠️ Failed to fetch data for {symbol}"
            )
            return
        
        prices = [p[1] for p in price_data.get("prices", [])]
        volumes = [v[1] for v in price_data.get("total_volumes", [])]
        
        if len(prices) < 100:
            await processing_msg.edit_text(
                f"⚠️ Insufficient data for {symbol}"
            )
            return
        
        market_data = coin_details.get("market_data", {})
        current_price = market_data.get("current_price", {}).get("usd", 0)
        coin_name = coin_details.get("name", symbol)
        market_cap_rank = coin_details.get("market_cap_rank")  # Can be None
        
        # Run realistic analysis
        analysis = analyze_hold_decision(
            symbol=symbol,
            current_price=current_price,
            prices=prices,
            volumes=volumes,
            btc_prices=btc_prices,
            market_data=market_data,
            market_cap_rank=market_cap_rank,
            fear_greed=fear_greed,
            timeframe_days=TIMEFRAME_CONFIG[timeframe]["days"]
        )
        
        message = format_hold_message(
            symbol=symbol,
            coin_name=coin_name,
            current_price=current_price,
            market_cap_rank=market_cap_rank,
            analysis=analysis,
            timeframe=timeframe
        )
        
        await processing_msg.edit_text(message, parse_mode="Markdown")
    
    except Exception as e:
        print(f"Error in hold command: {e}")
        import traceback
        traceback.print_exc()
        await processing_msg.edit_text(
            "❌ Analysis error. Please try again."
        )


def register_hold_handler(app):
    """Register /hold command"""
    from telegram.ext import CommandHandler
    app.add_handler(CommandHandler("hold", hold_command))
