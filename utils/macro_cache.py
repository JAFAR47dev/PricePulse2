# ----------------------------------------------------------------------------
# utils/macro_cache.py
# ----------------------------------------------------------------------------
"""
Simple cache for macro data (5 minute TTL)
Macro data doesn't need symbol-specific caching
"""

import time
import threading
from typing import Optional, Dict


class MacroCache:
    """
    Simple cache for macro snapshot
    Single cache entry since macro is same for all users
    """
    
    def __init__(self, ttl_minutes: int = 5):
        """Initialize cache"""
        self.ttl_minutes = ttl_minutes
        self.cache: Optional[Dict] = None
        self.expires_at: float = 0
        self.lock = threading.Lock()
    
    def get(self) -> Optional[Dict]:
        """
        Get cached macro snapshot
        
        Returns:
            Cached snapshot or None if expired/empty
        """
        with self.lock:
            if not self.cache:
                return None
            
            if time.time() > self.expires_at:
                self.cache = None
                return None
            
            return self.cache.copy()
    
    def set(self, snapshot: Dict) -> None:
        """
        Cache macro snapshot
        
        Args:
            snapshot: Macro data dictionary
        """
        with self.lock:
            self.cache = snapshot.copy()
            self.expires_at = time.time() + (self.ttl_minutes * 60)
    
    def clear(self) -> None:
        """Clear cache"""
        with self.lock:
            self.cache = None
            self.expires_at = 0
