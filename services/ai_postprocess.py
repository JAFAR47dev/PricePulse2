# services/ai_postprocess.py

from typing import List, Dict, Optional
from services.ai_prompt import ai_refine_signal, build_fallback_signal, ALLOWED_SIGNALS, ALLOWED_RISK


def validate_refined_signal(signal: Dict) -> bool:
    """
    Validate that a refined signal has all required fields and valid values.
    
    Args:
        signal: Refined signal dictionary
        
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(signal, dict):
        return False
    
    required_fields = {"symbol", "signal", "confidence", "risk"}
    if not required_fields.issubset(signal.keys()):
        return False
    
    # Type and value validation
    try:
        if not isinstance(signal["symbol"], str) or not signal["symbol"]:
            return False
        
        if signal["signal"] not in ALLOWED_SIGNALS:
            return False
        
        if not isinstance(signal["confidence"], int):
            return False
        if signal["confidence"] < 0 or signal["confidence"] > 100:
            return False
        
        if signal["risk"] not in ALLOWED_RISK:
            return False
            
    except (KeyError, TypeError):
        return False
    
    return True


def filter_weak_signals(signals: List[Dict], min_confidence: int = 30) -> List[Dict]:
    """
    Filter out signals below minimum confidence threshold.
    
    Args:
        signals: List of refined signals
        min_confidence: Minimum confidence to keep (0-100)
        
    Returns:
        Filtered list of signals
    """
    if not isinstance(signals, list):
        return []
    
    min_confidence = max(0, min(100, min_confidence))
    
    return [
        s for s in signals 
        if isinstance(s, dict) 
        and s.get("confidence", 0) >= min_confidence
    ]


def calculate_composite_score(signal: Dict) -> float:
    """
    Calculate a composite ranking score from multiple factors.
    
    Args:
        signal: Signal dictionary with confidence, pre_score, etc.
        
    Returns:
        Composite score for ranking
    """
    # Weighted scoring system
    confidence = signal.get("confidence", 0)
    pre_score = signal.get("pre_score", 0)
    trend_strength = signal.get("trend_strength", 0)
    
    # Risk penalty
    risk = signal.get("risk", "medium")
    risk_multiplier = {
        "low": 1.0,
        "medium": 0.95,
        "high": 0.85
    }.get(risk, 0.9)
    
    # Signal type weight (prefer strong directional signals)
    signal_type = signal.get("signal", "HOLD")
    signal_weight = {
        "BUY": 1.0,
        "SELL": 1.0,
        "HOLD": 0.7  # Penalize indecisive signals
    }.get(signal_type, 0.5)
    
    # Composite calculation
    composite = (
        confidence * 0.5 +           # AI confidence is most important
        pre_score * 0.3 +             # Pre-score provides base quality
        trend_strength * 0.2          # Trend strength adds conviction
    ) * risk_multiplier * signal_weight
    
    return composite


def post_process_and_rank(
    pre_scored_coins: List[Dict],
    timeframe: str,
    top_n: int = 10,
    min_confidence: int = 30,
    use_fallback: bool = True,
    api_key: Optional[str] = None
) -> List[Dict]:
    """
    Phase 4: Post-process AI signals and rank final results.
    
    - Calls AI refinement for each coin
    - Validates AI output
    - Optionally uses fallback for failed AI calls
    - Filters weak signals
    - Ranks by composite score
    
    Args:
        pre_scored_coins: List of pre-scored coins from rank_top_setups()
        timeframe: Trading timeframe (e.g., "1h", "4h")
        top_n: Number of top signals to return
        min_confidence: Minimum confidence threshold (0-100)
        use_fallback: Whether to use fallback signals when AI fails
        api_key: Optional API key override
        
    Returns:
        List of ranked, refined signals (up to top_n)
    """
    # Input validation
    if not isinstance(pre_scored_coins, list):
        return []
    
    if not isinstance(timeframe, str) or not timeframe:
        raise ValueError("timeframe must be a non-empty string")
    
    if not isinstance(top_n, int) or top_n < 1:
        top_n = 10
    
    if not isinstance(min_confidence, int):
        min_confidence = 30
    min_confidence = max(0, min(100, min_confidence))
    
    refined = []
    failed_count = 0
    
    for coin in pre_scored_coins:
        # Validate coin structure
        if not isinstance(coin, dict):
            continue
        
        if "symbol" not in coin:
            continue
        
        symbol = coin["symbol"]
        
        # Attempt AI refinement
        try:
            ai_result = ai_refine_signal(
                symbol=symbol,
                timeframe=timeframe,
                pre_score_data=coin,
                api_key=api_key
            )
        except ValueError as e:
            # Input validation error - skip this coin
            failed_count += 1
            ai_result = None
        except Exception as e:
            # Unexpected error - skip this coin
            failed_count += 1
            ai_result = None
        
        # Handle failed AI calls
        if not ai_result:
            if use_fallback:
                # Generate fallback signal from pre-score data
                ai_result = build_fallback_signal(coin, symbol)
            else:
                # Skip this coin
                failed_count += 1
                continue
        
        # Validate AI result
        if not validate_refined_signal(ai_result):
            if use_fallback:
                ai_result = build_fallback_signal(coin, symbol)
            else:
                failed_count += 1
                continue
        
        # Extract safe values with defaults
        pre_score = coin.get("score", 0)
        if not isinstance(pre_score, (int, float)):
            pre_score = 0
        pre_score = max(0, min(100, float(pre_score)))
        
        trend_strength = coin.get("trend_strength", 0)
        if not isinstance(trend_strength, (int, float)):
            trend_strength = 0
        trend_strength = max(0, min(100, float(trend_strength)))
        
        # Merge AI result with pre-score data
        merged = {
            **ai_result,
            "pre_score": round(pre_score, 2),
            "trend_strength": round(trend_strength, 2),
            "timeframe": timeframe,
        }
        
        # Add optional fields if present
        if "reasons" in coin:
            merged["reasons"] = coin["reasons"]
        if "rsi" in coin:
            merged["rsi"] = coin["rsi"]
        if "macd" in coin:
            merged["macd"] = coin["macd"]
        if "adx" in coin:
            merged["adx"] = coin["adx"]
        
        # Calculate composite score for ranking
        merged["composite_score"] = calculate_composite_score(merged)
        
        refined.append(merged)
    
    # Filter weak signals
    refined = filter_weak_signals(refined, min_confidence)
    
    # FINAL RANKING: Sort by composite score (descending)
    refined.sort(
        key=lambda x: (
            x.get("composite_score", 0),  # Primary: composite score
            x.get("confidence", 0),        # Secondary: AI confidence
            x.get("pre_score", 0),         # Tertiary: pre-score
            x.get("symbol", "")            # Stable sort by symbol
        ),
        reverse=True
    )
    
    # Return top N
    return refined[:top_n]


def get_signals_by_type(
    refined_signals: List[Dict],
    signal_type: str
) -> List[Dict]:
    """
    Filter signals by type (BUY, SELL, or HOLD).
    
    Args:
        refined_signals: List of refined signals
        signal_type: Signal type to filter ("BUY", "SELL", or "HOLD")
        
    Returns:
        Filtered list of signals
    """
    if not isinstance(refined_signals, list):
        return []
    
    signal_type = signal_type.upper()
    if signal_type not in ALLOWED_SIGNALS:
        return []
    
    return [
        s for s in refined_signals
        if isinstance(s, dict) and s.get("signal") == signal_type
    ]


def get_risk_summary(refined_signals: List[Dict]) -> Dict:
    """
    Generate risk distribution summary from refined signals.
    
    Args:
        refined_signals: List of refined signals
        
    Returns:
        Dictionary with risk level counts
    """
    if not isinstance(refined_signals, list):
        return {"low": 0, "medium": 0, "high": 0}
    
    summary = {"low": 0, "medium": 0, "high": 0}
    
    for signal in refined_signals:
        if isinstance(signal, dict):
            risk = signal.get("risk", "medium")
            if risk in summary:
                summary[risk] += 1
    
    return summary


def get_signal_distribution(refined_signals: List[Dict]) -> Dict:
    """
    Generate signal type distribution from refined signals.
    
    Args:
        refined_signals: List of refined signals
        
    Returns:
        Dictionary with signal type counts
    """
    if not isinstance(refined_signals, list):
        return {"BUY": 0, "SELL": 0, "HOLD": 0}
    
    distribution = {"BUY": 0, "SELL": 0, "HOLD": 0}
    
    for signal in refined_signals:
        if isinstance(signal, dict):
            signal_type = signal.get("signal")
            if signal_type in distribution:
                distribution[signal_type] += 1
    
    return distribution