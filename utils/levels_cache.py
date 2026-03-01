# ----------------------------------------------------------------------------
# utils/levels_cache.py
# ----------------------------------------------------------------------------
"""
Cache for levels analysis (longer TTL than regime)
"""

import time
import threading
from typing import Optional, Dict


class LevelsCache:
    """Simple cache for levels (10 min TTL)"""
    
    def __init__(self, ttl_minutes: int = 10):
        self.ttl_minutes = ttl_minutes
        self.cache: Dict[str, Dict] = {}
        self.lock = threading.Lock()
    
    def get(self, symbol: str, timeframe: str) -> Optional[Dict]:
        """Get cached levels"""
        with self.lock:
            key = f"{symbol}:{timeframe}"
            if key not in self.cache:
                return None
            
            item = self.cache[key]
            if time.time() > item["expires_at"]:
                del self.cache[key]
                return None
            
            return item["result"].copy()
    
    def set(self, symbol: str, timeframe: str, result: Dict) -> None:
        """Cache levels"""
        with self.lock:
            key = f"{symbol}:{timeframe}"
            self.cache[key] = {
                "result": result.copy(),
                "expires_at": time.time() + (self.ttl_minutes * 60)
            }
    
    def clear(self) -> None:
        """Clear cache"""
        with self.lock:
            self.cache.clear()