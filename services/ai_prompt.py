# services/ai_prompt.py
import os
import json
import requests
from typing import Dict, Optional

AI_PROMPT_TEMPLATE = """
You are a trading signal classifier.

RULES (MANDATORY):
- Output MUST be valid JSON ONLY
- No explanations
- No opinions
- No extra fields
- Choose ONE signal only

ALLOWED VALUES:
signal: ["BUY", "SELL", "HOLD"]
risk: ["low", "medium", "high"]
confidence: integer 0-100

TIMEFRAME: {timeframe}
SYMBOL: {symbol}

PRE-SCORED DATA:
{data}

TASK:
Choose the best signal based ONLY on the data above.

OUTPUT FORMAT (STRICT):
{{
  "symbol": "{symbol}",
  "signal": "BUY | SELL | HOLD",
  "confidence": 0-100,
  "risk": "low | medium | high"
}}
"""

ALLOWED_SIGNALS = {"BUY", "SELL", "HOLD"}
ALLOWED_RISK = {"low", "medium", "high"}

# API configuration
DEFAULT_TIMEOUT = 20
DEFAULT_MODEL = "mistralai/mixtral-8x7b-instruct"
DEFAULT_TEMPERATURE = 0.1
MAX_RETRIES = 2


def validate_pre_score_data(data: Dict, symbol: str) -> bool:
    """
    Validate that pre_score_data has the expected structure.
    
    Args:
        data: Dictionary from rank_top_setups() output
        symbol: Expected symbol name
        
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(data, dict):
        return False
    
    required_keys = {"symbol", "score", "bias", "confidence", "reasons"}
    
    if not required_keys.issubset(data.keys()):
        return False
    
    # Type validation
    try:
        if not isinstance(data["symbol"], str):
            return False
        if not isinstance(data["score"], (int, float)):
            return False
        if not isinstance(data["bias"], str):
            return False
        if not isinstance(data["confidence"], str):
            return False
        if not isinstance(data["reasons"], list):
            return False
        
        # Value validation
        if data["score"] < 0 or data["score"] > 100:
            return False
        if data["bias"] not in {"BUY", "SELL"}:
            return False
        if data["confidence"] not in {"strong", "medium", "weak", "very weak"}:
            return False
            
        # Symbol match validation
        if data["symbol"] != symbol:
            return False
            
    except (KeyError, TypeError):
        return False
    
    return True


def validate_ai_response(result: Dict, symbol: str) -> bool:
    """
    Validate AI response structure and values.
    
    Args:
        result: Parsed JSON response from AI
        symbol: Expected symbol name
        
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(result, dict):
        return False
    
    required_keys = {"symbol", "signal", "confidence", "risk"}
    if not required_keys.issubset(result.keys()):
        return False
    
    # Validate signal
    if result.get("signal") not in ALLOWED_SIGNALS:
        return False
    
    # Validate risk
    if result.get("risk") not in ALLOWED_RISK:
        return False
    
    # Validate confidence
    if not isinstance(result.get("confidence"), int):
        return False
    if result["confidence"] < 0 or result["confidence"] > 100:
        return False
    
    # Validate symbol
    if not isinstance(result.get("symbol"), str):
        return False
    
    return True


def extract_json_from_response(raw_response: str) -> Optional[Dict]:
    """
    Extract JSON from AI response, handling common formatting issues.
    
    Args:
        raw_response: Raw string response from AI
        
    Returns:
        Parsed JSON dict or None if parsing fails
    """
    if not raw_response or not isinstance(raw_response, str):
        return None
    
    # Remove common markdown formatting
    cleaned = raw_response.strip()
    
    # Remove markdown code blocks
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first line (```json or ```)
        if len(lines) > 1:
            lines = lines[1:]
        # Remove last line if it's closing backticks
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    
    # Try to find JSON object within the response
    start_idx = cleaned.find("{")
    end_idx = cleaned.rfind("}")
    
    if start_idx == -1 or end_idx == -1:
        return None
    
    json_str = cleaned[start_idx:end_idx + 1]
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def ai_refine_signal(
    symbol: str,
    timeframe: str,
    pre_score_data: Dict,
    api_key: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[Dict]:
    """
    PHASE 3 — AI refinement
    
    Sends pre-scored data to AI for final signal refinement.

    Args:
        symbol: Trading pair symbol (e.g., "BTCUSDT")
        timeframe: Trading timeframe (e.g., "1h", "4h")
        pre_score_data: Single item from rank_top_setups() output
        api_key: OpenRouter API key (defaults to env var)
        model: AI model to use
        temperature: Model temperature (0.0-1.0)
        timeout: Request timeout in seconds

    Returns:
        Dict with refined signal or None if failed
        
    Raises:
        ValueError: If input validation fails
    """
    # Input validation
    if not isinstance(symbol, str) or not symbol:
        raise ValueError("Symbol must be a non-empty string")
    
    if not isinstance(timeframe, str) or not timeframe:
        raise ValueError("Timeframe must be a non-empty string")
    
    if not isinstance(pre_score_data, dict):
        raise ValueError("pre_score_data must be a dictionary")
    
    # Validate pre_score_data structure
    if not validate_pre_score_data(pre_score_data, symbol):
        raise ValueError(
            f"Invalid pre_score_data for {symbol}. "
            f"Expected output from rank_top_setups() with keys: "
            f"symbol, score, bias, confidence, reasons"
        )
    
    # Get API key
    if api_key is None:
        api_key = os.getenv('OPENROUTER_API_KEY')
    
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not found in environment or parameters")
    
    # Build prompt
    try:
        data_json = json.dumps(pre_score_data, indent=2)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Failed to serialize pre_score_data: {e}")
    
    prompt = AI_PROMPT_TEMPLATE.format(
        symbol=symbol,
        timeframe=timeframe,
        data=data_json
    )
    
    # Retry loop
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a strict JSON-only trading engine."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": temperature
                },
                timeout=timeout
            )
            
            # Check response status
            if response.status_code != 200:
                last_error = f"API returned status {response.status_code}"
                continue
            
            # Parse response
            try:
                response_json = response.json()
            except json.JSONDecodeError:
                last_error = "Failed to parse API response as JSON"
                continue
            
            # Extract content
            if "choices" not in response_json:
                last_error = "Response missing 'choices' field"
                continue
            
            if not response_json["choices"]:
                last_error = "Response 'choices' array is empty"
                continue
            
            if "message" not in response_json["choices"][0]:
                last_error = "Response missing 'message' field"
                continue
            
            if "content" not in response_json["choices"][0]["message"]:
                last_error = "Response missing 'content' field"
                continue
            
            raw_content = response_json["choices"][0]["message"]["content"]
            
            if not isinstance(raw_content, str):
                last_error = "Response content is not a string"
                continue
            
            # Extract and parse JSON
            result = extract_json_from_response(raw_content)
            
            if result is None:
                last_error = "Failed to extract valid JSON from response"
                continue
            
            # Validate response structure
            if not validate_ai_response(result, symbol):
                last_error = "AI response failed validation"
                continue
            
            # Ensure symbol matches (defensive)
            result["symbol"] = symbol
            
            # Clamp confidence (defensive)
            result["confidence"] = max(0, min(100, result["confidence"]))
            
            return result
            
        except requests.exceptions.Timeout:
            last_error = f"Request timeout after {timeout}s"
            continue
            
        except requests.exceptions.ConnectionError:
            last_error = "Connection error"
            continue
            
        except requests.exceptions.RequestException as e:
            last_error = f"Request error: {str(e)}"
            continue
            
        except Exception as e:
            last_error = f"Unexpected error: {str(e)}"
            continue
    
    # All retries failed
    return None


def build_fallback_signal(pre_score_data: Dict, symbol: str) -> Dict:
    """
    Create a fallback signal when AI refinement fails.
    
    Args:
        pre_score_data: Pre-scored data
        symbol: Trading symbol
        
    Returns:
        Fallback signal dictionary
    """
    # Map bias to signal
    signal = pre_score_data.get("bias", "HOLD")
    if signal not in ALLOWED_SIGNALS:
        signal = "HOLD"
    
    # Map score to confidence
    score = pre_score_data.get("score", 0)
    confidence = min(100, max(0, int(score)))
    
    # Map confidence level to risk
    conf_level = pre_score_data.get("confidence", "medium")
    if conf_level in {"strong"}:
        risk = "low"
    elif conf_level in {"medium"}:
        risk = "medium"
    else:
        risk = "high"
    
    return {
        "symbol": symbol,
        "signal": signal,
        "confidence": confidence,
        "risk": risk,
    }