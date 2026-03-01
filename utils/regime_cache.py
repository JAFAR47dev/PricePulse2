
import time
import threading
from typing import Optional, Dict, List


class RegimeCache:
    """
    In-memory cache for regime analysis results
    
    Structure:
        {
            "BTC": {
                "result": {...},
                "expires_at": 1234567890,
                "cached_at": 1234567890
            },
            "ETH": {...}
        }
    """
    
    def __init__(self, ttl_minutes: int = 5):
        """
        Initialize cache
        
        Args:
            ttl_minutes: Time-to-live in minutes (default 5)
        """
        self.ttl_minutes = ttl_minutes
        self.cache: Dict[str, Dict] = {}
        self.lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._last_cleanup = time.time()
    
    def get(self, symbol: str, plan: str) -> Optional[Dict]:
        """
        Get cached result if available and not expired
        
        Args:
            symbol: Trading symbol (e.g., "BTC")
            plan: User plan tier (not used, kept for compatibility)
        
        Returns:
            Cached result dict or None if not found/expired
        """
        
        with self.lock:
            symbol = symbol.upper().strip()
            
            if symbol not in self.cache:
                self._misses += 1
                return None
            
            cached_item = self.cache[symbol]
            
            if time.time() > cached_item["expires_at"]:
                del self.cache[symbol]
                self._misses += 1
                return None
            
            self._hits += 1
            return cached_item["result"].copy()
    
    def set(self, symbol: str, plan: str, result: Dict) -> None:
        """
        Cache a result
        
        Args:
            symbol: Trading symbol
            plan: User plan tier (not used, kept for compatibility)
            result: Regime analysis result to cache
        """
        
        with self.lock:
            symbol = symbol.upper().strip()
            
            expires_at = time.time() + (self.ttl_minutes * 60)
            
            self.cache[symbol] = {
                "result": result.copy(),
                "expires_at": expires_at,
                "cached_at": time.time()
            }
            
            if time.time() - self._last_cleanup > 300:
                self._cleanup_expired()
    
    def delete(self, symbol: str, plan: Optional[str] = None) -> bool:
        """
        Delete cached entry
        
        Args:
            symbol: Trading symbol
            plan: User plan tier (not used, kept for compatibility)
        
        Returns:
            True if something was deleted, False otherwise
        """
        
        with self.lock:
            symbol = symbol.upper().strip()
            
            if symbol not in self.cache:
                return False
            
            del self.cache[symbol]
            return True
    
    def clear(self) -> None:
        """Clear entire cache"""
        with self.lock:
            self.cache.clear()
            self._hits = 0
            self._misses = 0
    
    def _cleanup_expired(self) -> int:
        """
        Remove all expired entries from cache
        
        Returns:
            Number of entries removed
        """
        current_time = time.time()
        removed_count = 0
        
        symbols_to_remove = []
        
        for symbol in list(self.cache.keys()):
            if current_time > self.cache[symbol]["expires_at"]:
                symbols_to_remove.append(symbol)
                removed_count += 1
        
        for symbol in symbols_to_remove:
            del self.cache[symbol]
        
        self._last_cleanup = current_time
        return removed_count
    
    def cleanup_expired(self) -> int:
        """
        Public method to manually trigger cleanup
        
        Returns:
            Number of entries removed
        """
        with self.lock:
            return self._cleanup_expired()
    
    def get_cache_age_minutes(self, symbol: str, plan: str) -> Optional[float]:
        """
        Get age of cached entry in minutes
        
        Args:
            symbol: Trading symbol
            plan: User plan tier (not used, kept for compatibility)
        
        Returns:
            Age in minutes or None if not cached
        """
        with self.lock:
            symbol = symbol.upper().strip()
            
            if symbol not in self.cache:
                return None
            
            cached_item = self.cache[symbol]
            
            if time.time() > cached_item["expires_at"]:
                return None
            
            age_seconds = time.time() - cached_item["cached_at"]
            return age_seconds / 60
    
    def get_stats(self) -> Dict:
        """
        Get cache statistics
        
        Returns:
            Dictionary with cache stats
        """
        with self.lock:
            total_entries = len(self.cache)
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                "symbols_cached": total_entries,
                "total_entries": total_entries,
                "ttl_minutes": self.ttl_minutes,
                "hits": self._hits,
                "misses": self._misses,
                "total_requests": total_requests,
                "hit_rate_pct": round(hit_rate, 1)
            }
    
    def get_cached_symbols(self) -> List[str]:
        """
        Get list of currently cached symbols
        
        Returns:
            List of symbol strings
        """
        with self.lock:
            return list(self.cache.keys())
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """
        Get information about cached entry for a symbol
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Dictionary with cache info or None if not cached
        """
        with self.lock:
            symbol = symbol.upper().strip()
            
            if symbol not in self.cache:
                return None
            
            data = self.cache[symbol]
            expires_in = data["expires_at"] - time.time()
            cached_ago = time.time() - data["cached_at"]
            
            return {
                "symbol": symbol,
                "expires_in_seconds": int(expires_in),
                "cached_ago_seconds": int(cached_ago),
                "cached_ago_minutes": round(cached_ago / 60, 1),
                "is_expired": expires_in <= 0
            }
    
    def reset_stats(self) -> None:
        """Reset hit/miss statistics"""
        with self.lock:
            self._hits = 0
            self._misses = 0


def test_cache():
    """Test cache functionality"""
    
    cache = RegimeCache(ttl_minutes=1)
    
    result = {"regime": "Bullish", "risk": "Low"}
    cache.set("BTC", "FREE", result)
    cached = cache.get("BTC", "FREE")
    assert cached == result, "Cache get failed"
    print("✓ Test 1: Basic set/get")
    
    assert cache.get("ETH", "FREE") is None, "Cache miss failed"
    print("✓ Test 2: Cache miss")
    
    cache.set("BTC", "PRO", {"extra": "data"})
    assert cache.get("BTC", "FREE") == cache.get("BTC", "PRO"), "Same cache for all plans"
    print("✓ Test 3: Unified cache")
    
    cache_short = RegimeCache(ttl_minutes=0.01)
    cache_short.set("SOL", "FREE", result)
    time.sleep(1)
    assert cache_short.get("SOL", "FREE") is None, "Expiration failed"
    print("✓ Test 4: Expiration")
    
    stats = cache.get_stats()
    assert stats["total_requests"] > 0, "Stats failed"
    print("✓ Test 5: Statistics")
    
    age = cache.get_cache_age_minutes("BTC", "FREE")
    assert age is not None and age >= 0, "Cache age failed"
    print("✓ Test 6: Cache age")
    
    cache.delete("BTC")
    assert cache.get("BTC", "FREE") is None, "Delete failed"
    print("✓ Test 7: Delete")
    
    cache.clear()
    assert cache.get_stats()["symbols_cached"] == 0, "Clear failed"
    print("✓ Test 8: Clear")
    
    print("\n✅ All cache tests passed!")


if __name__ == "__main__":
    test_cache()