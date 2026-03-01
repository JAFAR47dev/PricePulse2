import requests
from typing import Dict, Optional, List
import time
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class MacroDataService:
    """Fetches macro indicators that affect crypto using CoinGecko API"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize with CoinGecko API key from environment or parameter
        Looks for COINGECKO_API_KEY in .env file
        """
        self.cache = {}
        self.cache_duration = 3600  # 1 hour for macro data
        
        # Get API key from parameter, env, or use free tier
        self.api_key = api_key or os.getenv('COINGECKO_API_KEY')
        
        # Set base URL and headers
        self.base_url = "https://api.coingecko.com/api/v3"
        
        if self.api_key:
            self.headers = {"x-cg-demo-api-key": self.api_key}
        else:
            self.headers = {}
        
        # Expanded stablecoin list for better accuracy
        self.stablecoins = {
            'tether': 'USDT',
            'usd-coin': 'USDC',
            'dai': 'DAI',
            'first-digital-usd': 'FDUSD',
            'true-usd': 'TUSD',
            'paxos-standard': 'USDP',
            'gemini-dollar': 'GUSD',
            'liquity-usd': 'LUSD',
            'frax': 'FRAX',
            'usdd': 'USDD'
        }
    
    def get_macro_indicators(self, include_alt_season: bool = True) -> Optional[Dict]:
        """
        Get comprehensive macro market indicators
        
        Args:
            include_alt_season: Whether to include altcoin season calculation (slower)
        """
        cache_key = f"macro_data_alt{include_alt_season}"
        
        # Check cache
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_duration:
                return cached_data
        
        try:
            # Get dominance data
            dominance_data = self._get_dominance_data()
            
            # Get volume and flow indicators
            volume_data = self._get_volume_indicators()
            
            # Get funding rate estimate
            funding_rate = self._get_funding_rate_estimate()
            
            # Get market fear/greed from price action
            market_sentiment = self._calculate_market_sentiment()
            
            # Build result
            result = {
                **dominance_data,
                **volume_data,
                "funding_rate": funding_rate,
                "market_sentiment": market_sentiment
            }
            
            # Add altcoin season if requested
            if include_alt_season:
                alt_season = self.get_altcoin_season_index()
                result["altcoin_season"] = alt_season
            
            # Cache result
            self.cache[cache_key] = (result, time.time())
            return result
            
        except Exception as e:
            print(f"Error fetching macro data: {e}")
            import traceback
            traceback.print_exc()
            
            # Return fallback data
            return self._get_fallback_data(include_alt_season)
    
    def _get_dominance_data(self) -> Dict:
        """
        Get BTC dominance, ETH dominance, and stablecoin dominance
        Returns comprehensive dominance metrics
        """
        try:
            # Get global market data
            url = f"{self.base_url}/global"
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            global_data = response.json()['data']
            
            # BTC and ETH dominance (from global data)
            btc_dominance = round(global_data['market_cap_percentage'].get('btc', 50.0), 2)
            eth_dominance = round(global_data['market_cap_percentage'].get('eth', 15.0), 2)
            
            # Total market cap
            total_market_cap = global_data['total_market_cap']['usd']
            
            # Calculate stablecoin dominance (batch request)
            stablecoin_data = self._get_stablecoin_dominance(total_market_cap)
            
            # Calculate "others" dominance (everything except BTC, ETH, stables)
            others_dominance = round(
                100 - btc_dominance - eth_dominance - stablecoin_data['total_stablecoin_dominance'], 
                2
            )
            
            # Determine market structure
            market_structure = self._determine_market_structure(
                btc_dominance, 
                eth_dominance, 
                stablecoin_data['total_stablecoin_dominance']
            )
            
            return {
                "btc_dominance": btc_dominance,
                "eth_dominance": eth_dominance,
                "usdt_dominance": stablecoin_data['usdt_dominance'],
                "total_stablecoin_dominance": stablecoin_data['total_stablecoin_dominance'],
                "others_dominance": max(0, others_dominance),  # Ensure non-negative
                "market_structure": market_structure,
                "stablecoin_breakdown": stablecoin_data['breakdown']
            }
            
        except Exception as e:
            print(f"Error in _get_dominance_data: {e}")
            return {
                "btc_dominance": 50.0,
                "eth_dominance": 15.0,
                "usdt_dominance": 5.0,
                "total_stablecoin_dominance": 7.0,
                "others_dominance": 28.0,
                "market_structure": "unknown",
                "stablecoin_breakdown": {}
            }
    
    def _get_stablecoin_dominance(self, total_market_cap: float) -> Dict:
        """
        Calculate stablecoin dominance with breakdown
        Uses batch API call for efficiency
        """
        try:
            # Get stablecoin IDs
            coin_ids = list(self.stablecoins.keys())
            
            # Batch request (more efficient than individual calls)
            url = f"{self.base_url}/coins/markets"
            params = {
                "vs_currency": "usd",
                "ids": ",".join(coin_ids),
                "per_page": len(coin_ids),
                "page": 1
            }
            
            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            response.raise_for_status()
            stablecoin_markets = response.json()
            
            # Calculate dominances
            total_stablecoin_mcap = 0
            usdt_mcap = 0
            breakdown = {}
            
            for coin in stablecoin_markets:
                coin_id = coin['id']
                mcap = coin.get('market_cap', 0)
                symbol = self.stablecoins.get(coin_id, coin['symbol'].upper())
                
                total_stablecoin_mcap += mcap
                breakdown[symbol] = round((mcap / total_market_cap) * 100, 2) if total_market_cap > 0 else 0
                
                if symbol == 'USDT':
                    usdt_mcap = mcap
            
            usdt_dominance = round((usdt_mcap / total_market_cap) * 100, 2) if total_market_cap > 0 else 5.0
            total_stablecoin_dominance = round((total_stablecoin_mcap / total_market_cap) * 100, 2) if total_market_cap > 0 else 7.0
            
            return {
                "usdt_dominance": usdt_dominance,
                "total_stablecoin_dominance": total_stablecoin_dominance,
                "breakdown": breakdown
            }
            
        except Exception as e:
            print(f"Error in _get_stablecoin_dominance: {e}")
            return {
                "usdt_dominance": 5.0,
                "total_stablecoin_dominance": 7.0,
                "breakdown": {}
            }
    
    def _determine_market_structure(self, btc_dom: float, eth_dom: float, stable_dom: float) -> str:
        """
        Determine market structure based on dominance levels
        """
        # BTC dominance thresholds
        if btc_dom > 60:
            return "btc_dominant"  # Flight to safety
        elif btc_dom > 55:
            return "btc_leading"   # BTC outperforming
        elif btc_dom < 40:
            return "alt_season"    # Alts thriving
        elif stable_dom > 10:
            return "risk_off"      # Money in stables (fearful)
        elif stable_dom < 5:
            return "risk_on"       # Money deployed (confident)
        else:
            return "balanced"      # Healthy distribution
    
    def _get_volume_indicators(self) -> Dict:
        """
        Get volume-based indicators including exchange flow estimates
        """
        try:
            # Get BTC market data for volume analysis
            url = f"{self.base_url}/coins/bitcoin/market_chart"
            params = {
                "vs_currency": "usd",
                "days": 14,  # 2 weeks for better trend
                "interval": "daily"
            }
            
            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            volumes = [v[1] for v in data['total_volumes']]
            
            if len(volumes) < 7:
                return self._get_fallback_volume_data()
            
            # Calculate volume trends
            recent_7d_avg = sum(volumes[-7:]) / 7
            previous_7d_avg = sum(volumes[-14:-7]) / 7
            
            volume_change_pct = ((recent_7d_avg - previous_7d_avg) / previous_7d_avg) * 100
            
            # Determine exchange flow
            exchange_flow = self._classify_exchange_flow(volume_change_pct)
            
            # Volume trend
            if volume_change_pct > 15:
                volume_trend = "increasing_strong"
            elif volume_change_pct > 5:
                volume_trend = "increasing"
            elif volume_change_pct > -5:
                volume_trend = "stable"
            elif volume_change_pct > -15:
                volume_trend = "decreasing"
            else:
                volume_trend = "decreasing_strong"
            
            return {
                "exchange_flow": exchange_flow['status'],
                "exchange_flow_signal": exchange_flow['signal'],
                "volume_trend": volume_trend,
                "volume_change_7d": round(volume_change_pct, 2),
                "recent_volume_7d_avg": round(recent_7d_avg, 0)
            }
            
        except Exception as e:
            print(f"Error in _get_volume_indicators: {e}")
            return self._get_fallback_volume_data()
    
    def _classify_exchange_flow(self, volume_change: float) -> Dict:
        """
        Classify exchange flow with signal interpretation
        """
        if volume_change > 30:
            return {
                "status": "heavy_inflow",
                "signal": "bearish"  # Lots of coins moving to exchanges = selling pressure
            }
        elif volume_change > 15:
            return {
                "status": "inflow",
                "signal": "slightly_bearish"
            }
        elif volume_change > -15:
            return {
                "status": "neutral",
                "signal": "neutral"
            }
        elif volume_change > -30:
            return {
                "status": "outflow",
                "signal": "slightly_bullish"  # Coins leaving exchanges = accumulation
            }
        else:
            return {
                "status": "heavy_outflow",
                "signal": "bullish"
            }
    
    def _get_funding_rate_estimate(self) -> Dict:
        """
        Enhanced funding rate estimate with confidence level
        """
        try:
            # Get BTC price data
            url = f"{self.base_url}/coins/bitcoin"
            params = {
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "false",
                "developer_data": "false"
            }
            
            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            response.raise_for_status()
            market_data = response.json()['market_data']
            
            # Multiple momentum indicators for better estimate
            price_change_24h = market_data.get('price_change_percentage_24h', 0)
            price_change_7d = market_data.get('price_change_percentage_7d', 0)
            
            # Weighted momentum (24h has more weight)
            weighted_momentum = (price_change_24h * 0.7) + (price_change_7d * 0.3)
            
            # Estimate funding rate
            if weighted_momentum > 7:
                rate = 0.04
                sentiment = "extremely_bullish"
            elif weighted_momentum > 4:
                rate = 0.02
                sentiment = "bullish"
            elif weighted_momentum > 1:
                rate = 0.01
                sentiment = "slightly_bullish"
            elif weighted_momentum > -1:
                rate = 0.005
                sentiment = "neutral"
            elif weighted_momentum > -4:
                rate = -0.01
                sentiment = "slightly_bearish"
            elif weighted_momentum > -7:
                rate = -0.02
                sentiment = "bearish"
            else:
                rate = -0.04
                sentiment = "extremely_bearish"
            
            return {
                "rate": round(rate, 4),
                "sentiment": sentiment,
                "confidence": "estimated",  # Not real funding data
                "based_on": "price_momentum"
            }
            
        except Exception as e:
            print(f"Error in _get_funding_rate_estimate: {e}")
            return {
                "rate": 0.01,
                "sentiment": "neutral",
                "confidence": "low",
                "based_on": "fallback"
            }
    
    def _calculate_market_sentiment(self) -> Dict:
        """
        Calculate overall market sentiment from price action
        """
        try:
            # Get top 100 coins
            url = f"{self.base_url}/coins/markets"
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 100,
                "page": 1,
                "price_change_percentage": "24h"
            }
            
            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            response.raise_for_status()
            coins = response.json()
            
            # Count positive vs negative
            positive_count = sum(1 for c in coins if c.get('price_change_percentage_24h', 0) > 0)
            total_count = len(coins)
            
            positive_pct = (positive_count / total_count) * 100 if total_count > 0 else 50
            
            # Classify sentiment
            if positive_pct >= 75:
                sentiment = "very_bullish"
                emoji = "🟢🟢"
            elif positive_pct >= 60:
                sentiment = "bullish"
                emoji = "🟢"
            elif positive_pct >= 40:
                sentiment = "neutral"
                emoji = "🔶"
            elif positive_pct >= 25:
                sentiment = "bearish"
                emoji = "🔴"
            else:
                sentiment = "very_bearish"
                emoji = "🔴🔴"
            
            return {
                "sentiment": sentiment,
                "emoji": emoji,
                "positive_pct": round(positive_pct, 1),
                "coins_positive": positive_count,
                "coins_total": total_count
            }
            
        except Exception as e:
            print(f"Error in _calculate_market_sentiment: {e}")
            return {
                "sentiment": "neutral",
                "emoji": "🔶",
                "positive_pct": 50.0,
                "coins_positive": 0,
                "coins_total": 0
            }
    
    def get_altcoin_season_index(self) -> Dict:
        """
        Enhanced Altcoin Season Index with more granular analysis
        Returns score 0-100 where >75 = alt season, <25 = BTC season
        """
        cache_key = "altseason_index_v2"
        
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_duration:
                return cached_data
        
        try:
            # Get top 100 coins for better representation
            url = f"{self.base_url}/coins/markets"
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 100,
                "page": 1,
                "price_change_percentage": "30d"
            }
            
            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            response.raise_for_status()
            coins = response.json()
            
            # Get BTC 30d performance
            btc_performance = next((c['price_change_percentage_30d_in_currency'] 
                                   for c in coins if c['symbol'].lower() == 'btc'), 0)
            
            # Count alts outperforming BTC (by market cap tier)
            large_cap_outperform = 0  # Top 10
            mid_cap_outperform = 0     # 11-50
            small_cap_outperform = 0   # 51-100
            
            large_cap_total = 0
            mid_cap_total = 0
            small_cap_total = 0
            
            for i, coin in enumerate(coins):
                if coin['symbol'].lower() == 'btc':
                    continue
                
                alt_performance = coin.get('price_change_percentage_30d_in_currency')
                if alt_performance is None:
                    continue
                
                # Categorize by rank
                rank = i + 1
                if rank <= 10:
                    large_cap_total += 1
                    if alt_performance > btc_performance:
                        large_cap_outperform += 1
                elif rank <= 50:
                    mid_cap_total += 1
                    if alt_performance > btc_performance:
                        mid_cap_outperform += 1
                else:
                    small_cap_total += 1
                    if alt_performance > btc_performance:
                        small_cap_outperform += 1
            
            # Calculate weighted index (large caps weighted more)
            total_outperform = (large_cap_outperform * 3) + (mid_cap_outperform * 2) + small_cap_outperform
            total_checked = (large_cap_total * 3) + (mid_cap_total * 2) + small_cap_total
            
            index = int((total_outperform / total_checked) * 100) if total_checked > 0 else 50
            
            # Determine season with more granularity
            if index >= 80:
                season = "extreme_alt_season"
                description = "Extreme alt season - Nearly all alts outperforming BTC"
                emoji = "🚀🚀"
            elif index >= 70:
                season = "strong_alt_season"
                description = "Strong alt season - Most alts outperforming BTC"
                emoji = "🚀"
            elif index >= 55:
                season = "alt_favorable"
                description = "Alt-friendly market - Majority of alts doing well"
                emoji = "🟢"
            elif index >= 45:
                season = "neutral"
                description = "Neutral market - Mixed performance"
                emoji = "🔶"
            elif index >= 30:
                season = "btc_favorable"
                description = "BTC-friendly market - BTC outperforming most alts"
                emoji = "🔴"
            elif index >= 20:
                season = "strong_btc_season"
                description = "Strong BTC season - Most alts underperforming"
                emoji = "₿"
            else:
                season = "extreme_btc_season"
                description = "Extreme BTC season - Nearly all alts underperforming"
                emoji = "₿₿"
            
            result = {
                "index": index,
                "season": season,
                "emoji": emoji,
                "description": description,
                "btc_performance_30d": round(btc_performance, 2),
                "breakdown": {
                    "large_cap": {
                        "outperforming": large_cap_outperform,
                        "total": large_cap_total,
                        "pct": round((large_cap_outperform / large_cap_total * 100), 1) if large_cap_total > 0 else 0
                    },
                    "mid_cap": {
                        "outperforming": mid_cap_outperform,
                        "total": mid_cap_total,
                        "pct": round((mid_cap_outperform / mid_cap_total * 100), 1) if mid_cap_total > 0 else 0
                    },
                    "small_cap": {
                        "outperforming": small_cap_outperform,
                        "total": small_cap_total,
                        "pct": round((small_cap_outperform / small_cap_total * 100), 1) if small_cap_total > 0 else 0
                    }
                }
            }
            
            self.cache[cache_key] = (result, time.time())
            return result
            
        except Exception as e:
            print(f"Error calculating altcoin season index: {e}")
            return {
                "index": 50,
                "season": "neutral",
                "emoji": "🔶",
                "description": "Unable to determine market leadership",
                "btc_performance_30d": 0,
                "breakdown": {}
            }
    
    def _get_fallback_data(self, include_alt_season: bool) -> Dict:
        """Return fallback data when API fails"""
        base_data = {
            "btc_dominance": 50.0,
            "eth_dominance": 15.0,
            "usdt_dominance": 5.0,
            "total_stablecoin_dominance": 7.0,
            "others_dominance": 28.0,
            "market_structure": "unknown",
            "stablecoin_breakdown": {},
            "exchange_flow": "neutral",
            "exchange_flow_signal": "neutral",
            "volume_trend": "stable",
            "volume_change_7d": 0,
            "recent_volume_7d_avg": 0,
            "funding_rate": {
                "rate": 0.01,
                "sentiment": "neutral",
                "confidence": "low",
                "based_on": "fallback"
            },
            "market_sentiment": {
                "sentiment": "neutral",
                "emoji": "🔶",
                "positive_pct": 50.0,
                "coins_positive": 0,
                "coins_total": 0
            }
        }
        
        if include_alt_season:
            base_data["altcoin_season"] = {
                "index": 50,
                "season": "neutral",
                "emoji": "🔶",
                "description": "Unable to determine",
                "btc_performance_30d": 0,
                "breakdown": {}
            }
        
        return base_data
    
    def _get_fallback_volume_data(self) -> Dict:
        """Fallback volume data"""
        return {
            "exchange_flow": "neutral",
            "exchange_flow_signal": "neutral",
            "volume_trend": "stable",
            "volume_change_7d": 0,
            "recent_volume_7d_avg": 0
        }
