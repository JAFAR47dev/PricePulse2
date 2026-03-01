import requests
from typing import Optional, Dict
import time

class SentimentService:
    """Fetches crypto sentiment data (Fear & Greed Index)"""
    
    def __init__(self):
        self.cache = {}
        self.cache_duration = 3600  # 1 hour
    
    # Sentiment zones with contextual insights
    SENTIMENT_ZONES = {
        "Extreme Fear": {
            "range": (0, 25),
            "emoji": "😱",
            "context": "Historically good buying opportunities, but catch falling knives carefully."
        },
        "Fear": {
            "range": (26, 45),
            "emoji": "😰",
            "context": "Market is fearful. Fake rallies are common—wait for confirmation."
        },
        "Neutral": {
            "range": (46, 55),
            "emoji": "😐",
            "context": "Market is undecided. No clear edge from sentiment alone."
        },
        "Greed": {
            "range": (56, 75),
            "emoji": "😄",
            "context": "Market heating up. Watch for signs of exhaustion or overextension."
        },
        "Extreme Greed": {
            "range": (76, 100),
            "emoji": "🤑",
            "context": "Everyone's euphoric. Consider taking profits—tops form in greed."
        }
    }
    
    def get_fear_greed_index(self) -> Optional[Dict]:
        """
        Get Fear & Greed Index from alternative.me with enhanced classification
        Returns: {
            "value": 52,
            "classification": "Neutral",
            "emoji": "😐",
            "context": "Market is undecided..."
        }
        """
        cache_key = "fear_greed"
        
        # Check cache
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_duration:
                return cached_data
        
        try:
            url = "https://api.alternative.me/fng/"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            value = int(data['data'][0]['value'])
            
            # Classify based on Phase 4 zones
            classification, zone_data = self._classify_sentiment(value)
            
            result = {
                "value": value,
                "classification": classification,
                "emoji": zone_data["emoji"],
                "context": zone_data["context"]
            }
            
            # Cache result
            self.cache[cache_key] = (result, time.time())
            return result
            
        except Exception as e:
            print(f"Error fetching Fear & Greed: {e}")
            return {
                "value": 50,
                "classification": "Unknown",
                "emoji": "❓",
                "context": "Unable to fetch sentiment data at this time."
            }
    
    def _classify_sentiment(self, value: int) -> tuple:
        """
        Classify sentiment value into Phase 4 zones
        Returns: (classification_name, zone_data)
        """
        for zone_name, zone_data in self.SENTIMENT_ZONES.items():
            min_val, max_val = zone_data["range"]
            if min_val <= value <= max_val:
                return zone_name, zone_data
        
        # Fallback (should never reach here)
        return "Unknown", {
            "emoji": "❓",
            "context": "Sentiment data out of expected range."
        }